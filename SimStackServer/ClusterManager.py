import errno
import logging
import os
import pathlib
import stat
import string
import time
from contextlib import contextmanager
from datetime import datetime
import random

import paramiko
from os import path
import posixpath
from pathlib import Path

import sshtunnel
import zmq
from paramiko import SFTPAttributes

from SimStackServer.MessageTypes import Message, ErrorCodes
from SimStackServer.MessageTypes import SSS_MESSAGETYPE as MTS
from SimStackServer.Util.FileUtilities import split_directory_in_subdirectories, filewalker
from SimStackServer.WorkflowModel import Resources, WorkflowExecModule


class SSHExpectedDirectoryError(Exception):
    pass

class ClusterManager(object):
    def __init__(self,
                 url,
                 port,
                 calculation_basepath,
                 user,
                 sshprivatekey,
                 extra_config,
                 queueing_system,
                 default_queue,
                 software_directory = None
                 ):
        """

        :param default_queue:
        :param url (str): URL to connect to (int-nanomatchcluster.int.kit.edu, ipv4, ipv6)
        :param port (int): Port to connect to, i.e. 22
        :param calculation_basepath (str): Where everything will be stored by default. "" == home directory.
        :param user (str): Username on the respective server.
        :param sshprivatekey (str): Filename of ssh private key
        :param default_queue (str): Jobs will be submitted to this queue, if none is given.
        """
        self._logger = logging.getLogger("ClusterManager")
        self._url = url
        try:
            self._port = int(port)
        except ValueError as e:
            print(f"Port was set to >{port}<. Using default port of 22")
            self._port = 22
        self._calculation_basepath = calculation_basepath
        self._extra_config = extra_config
        self._user = user
        self._sshprivatekeyfilename = sshprivatekey
        self._default_queue = default_queue
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.load_system_host_keys()
        self._should_be_connected = False
        self._sftp_client : paramiko.SFTPClient = None
        self._queueing_system = queueing_system
        self._default_mode = 770
        self._context = zmq.Context.instance()
        self._socket = None
        self._http_server_tunnel : sshtunnel.SSHTunnelForwarder
        self._http_server_tunnel = None
        self._zmq_ssh_tunnel = None
        self._http_user = None
        self._http_pass = None
        self._http_base_address = None
        self._unknown_host_connect_workaround = False
        self._extra_hostkey_file = None
        self._software_directory = software_directory


    def _dummy_callback(self, bytes_written, total_bytes):
        """
        Just an example callback for the file transfer

        :param arg1 (int): Number of bytes already written by transport
        :param arg2 (int): Number of bytes in total
        :return: Nothing
        """
        print("%d %% done"%(100.0*bytes_written/total_bytes))

    def get_ssh_url(self):
        return "%s@%s:%d"%(self._user,self._url,self._port)

    def load_extra_host_keys(self, filename):
        """
        Loads extra host keys into ssh_client
        :param filename (str): Filename of the extra hostkey db
        :return:
        """
        assert self._ssh_client is not None, "SSH Client not yet initialized"
        self._extra_hostkey_file = filename
        self._ssh_client.load_host_keys(filename)

    def save_hostkeyfile(self, filename):
        """
        Save the read hostkeys, plus eventual new ones back to disk.
        :param filename (str): File to save to.
        :return:
        """
        self._ssh_client.save_host_keys(filename)


    def get_new_connected_ssh_channel(self):
        key_filename = None
        if self._sshprivatekeyfilename != "UseSystemDefault":
            key_filename = self._sshprivatekeyfilename


        local_ssh_client = paramiko.SSHClient()
        local_ssh_client.load_system_host_keys()
        if self._extra_hostkey_file is not None:
            local_ssh_client.load_host_keys(self._extra_hostkey_file)
        if self._unknown_host_connect_workaround:
            local_ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy)

        local_ssh_client.connect(self._url, self._port, username=self._user, key_filename = key_filename, compress=True)
        return local_ssh_client

    def set_connect_to_unknown_hosts(self, connect_to_unknown_hosts):
        self._unknown_host_connect_workaround = connect_to_unknown_hosts

    def connect(self):
        """
        Connect the ssh_client and setup the sftp tunnel.
        :return: Nothing
        """
        key_filename = None
        if self._sshprivatekeyfilename != "UseSystemDefault":
            key_filename = self._sshprivatekeyfilename

        if self._unknown_host_connect_workaround:
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
        self._ssh_client.connect(self._url,self._port, username=self._user, key_filename=key_filename, compress=True)
        self._ssh_client.get_transport().set_keepalive(30)
        self._should_be_connected = True
        self._sftp_client = self._ssh_client.open_sftp()
        self._sftp_client.get_channel().settimeout(1.0)
        self.mkdir_p(self._calculation_basepath,basepath_override="")

    @contextmanager
    def connection_context(self):
        # Code to acquire resource, e.g.:
        try:
            if self.is_connected():
                yield None
            else:
                yield self.connect_ssh_and_zmq_if_disconnected(connect_http = False, verbose = False)
        finally:
            self.disconnect()

    def connect_ssh_and_zmq_if_disconnected(self, connect_http = True, verbose = True):
        if not self.is_connected():
            self.connect()
            com = self._get_server_command()
            self.connect_zmq_tunnel(com, connect_http = connect_http, verbose = verbose)

    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
        if self._socket is not None:
            self._socket.close()
        
        if self._sftp_client != None:
            self._sftp_client.close()
        
        self._ssh_client.close()
        
        if self._http_server_tunnel is not None:
            #This handling here is purely for windows. Somehow, the transport is not closed, if not set.
            for _srv in self._http_server_tunnel._server_list:
                _srv.timeout = 0.01

            self._http_server_tunnel._transport.close()
            self._http_server_tunnel.stop()
            #print("http server stopped")
            
        #print("Killing ZMQ tunnel")
        if self._zmq_ssh_tunnel is not None:
            if hasattr(self._zmq_ssh_tunnel,"kill"):
                #This is because it can be that the tunnel was not done via paramiko subprocess
                self._zmq_ssh_tunnel.kill()
                #print("Killed zmq tunnel")

    def resolve_file_in_basepath(self, filename, basepath_override):
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        return basepath_override + '/' + filename

    def delete_file(self, filename, basepath_override = None):
        resolved_filename = self.resolve_file_in_basepath(filename, basepath_override)
        self._sftp_client.remove(resolved_filename)

    def __rmtree_helper(self,abspath):
        postremove_files = []
        for file_attr in self._sftp_client.listdir_attr(abspath):
            fname = file_attr.filename

            newabspath = abspath + '/' + fname
            if stat.S_ISDIR(file_attr.st_mode):
                self.__rmtree_helper(newabspath)
            else:
                postremove_files.append(newabspath)
        for myfile in postremove_files:
            #print("Im deleting: %s" %myfile)
            self._sftp_client.remove(myfile)
        self._sftp_client.rmdir(abspath)
        #print("Im deleting %s"%abspath)

    def rmtree(self, dirname, basepath_override = None):
        abspath = self.resolve_file_in_basepath(dirname, basepath_override)
        if not self.exists_as_directory(abspath):
            return
        self.__rmtree_helper(abspath)

    def put_directory(self, from_directory : str, to_directory: str, optional_callback = None, basepath_override = None):
        for filename in filewalker(from_directory):
            cp = os.path.commonprefix([from_directory, filename])
            relpath = os.path.relpath(filename, cp)
            submitpath = path.join(to_directory, relpath)
            mydir = path.dirname(submitpath)
            self.mkdir_p(mydir)
            self.put_file(filename,submitpath, optional_callback, basepath_override)
        return self.resolve_file_in_basepath(str(to_directory), basepath_override=basepath_override)

    def exists_remote(self, path):
        try:
            self._sftp_client.stat(path)
        except IOError as e:
            if e.errno == errno.ENOENT:
                return False
            raise
        else:
            return True

    def get_directory(self, from_directory_on_server: str, to_directory: str, optional_callback = None, basepath_override =None):
        #from_directory_on_server_resolved = self.resolve_file_in_basepath(from_directory_on_server, basepath_override=basepath_override)
        self._get_directory_recurse_helper(from_directory_on_server, to_directory, optional_callback, basepath_override)

    def _get_directory_recurse_helper(self, from_directory_on_server_resolved: str, to_directory: str, optional_callback = None, basepath_override =None):

        if not self.exists_remote(from_directory_on_server_resolved):
            raise FileNotFoundError(f"Directory {from_directory_on_server_resolved} not found on server.")

        if not os.path.exists(to_directory):
            os.mkdir(to_directory)

        for filename in self._sftp_client.listdir(from_directory_on_server_resolved):
            tocheck = f"{from_directory_on_server_resolved}/{filename}"
            if stat.S_ISDIR(self._sftp_client.stat(tocheck).st_mode):
                # uses '/' path delimiter for remote server
                self._get_directory_recurse_helper(tocheck + '/', os.path.join(to_directory, filename))
            else:
                if not os.path.isfile(os.path.join(to_directory, filename)):
                    self._sftp_client.get(tocheck, os.path.join(to_directory, filename))

    def put_file(self, from_file, to_file, optional_callback = None, basepath_override = None):
        """
        Transfer a file from_file (local) to to_file(remote)

        Throws FileNotFoundError in case file does not exist on local host.

        :param from_file (str): Existing file on host
        :param to_file (str): Remote file (will be overwritten)
        :param optional_callWorkback (function): Function looking like this: callback(bytes_written, total_bytes)
        :param basepath_override (str): Overrides the basepath in case of uploads somewhere else.
        :return: Nothing
        """
        if not path.isfile(from_file):
            raise FileNotFoundError("File %s was not found during ssh put file on local host"%(from_file))
        if basepath_override is None:
            basepath_override = self._calculation_basepath
        abstofile = basepath_override + "/" + to_file
        # In case a directory was specified, we have to add the filename to upload into it as paramiko does not automatically.
        if self.exists_as_directory(abstofile):
            abstofile += "/" + posixpath.basename(from_file)
        self._sftp_client.put(from_file,abstofile,optional_callback)

    def remote_open(self,filename, mode, basepath_override= None):
        abspath = self.resolve_file_in_basepath(filename, basepath_override)
        return self._sftp_client.open(abspath, mode)

    def list_dir(self, path, basepath_override = None):
        files = []
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        abspath = basepath_override + '/' + path


        for file_attr in self._sftp_client.listdir_iter(abspath):
            file_attr : SFTPAttributes
            file_char = 'd' if stat.S_ISDIR(file_attr.st_mode) else 'f'
            fname  = file_attr.filename
            longname = file_attr.longname
            print(fname, longname, file_char)
            files.append(
                {
                    'name': fname,
                    'path': abspath,
                    'type': file_char
                }
            )
        return files

    def get_default_queue(self):
        """
        :return (str): Name of default queue
        """
        return self._default_queue

    def _get_job_directory_path(self, given_name):
        now = datetime.now()
        random_string = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        nowstr = now.strftime("%Y-%m-%d-%Hh%Mm%Ss")
        submitname = "%s-%s-%s" %(nowstr, given_name, random_string)
        return submitname

    def mkdir_random_singlejob_exec_directory(self, given_name, num_retries = 10):
        for i in range(0, num_retries):
            trialdirectory = Path("singlejob_exec_directories") / self._get_job_directory_path(given_name)
            if self.exists(Path(self._calculation_basepath) / trialdirectory):
                time.sleep(1.05)
            else:
                self.mkdir_p(trialdirectory)
                return trialdirectory

        raise FileExistsError("Could not generate new directory in time.")

    def get_file(self, from_file, to_file, basepath_override = None, optional_callback = None):
        """
        Transfer a file from_file (remote) to to_file(local)

        Throws FileNotFoundError in case file does not exist on remote host. TODO

        :param from_file (str): Existing file on remote
        :param to_file (str): Local file (will be overwritten)
        :param basepath_override (str): If set, this custom basepath is used for lookup
        :param optional_callback (function): Function looking like this: callback(bytes_written, total_bytes)
        :return: Nothing
        """
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        getpath = basepath_override + '/' + from_file
        self._sftp_client.get(getpath, to_file, optional_callback)

    def exec_command(self, command):
        """
            Executes a command.

            :param command (str): Command to execute remotely.
            :return: Nothing (currently)
        """

        myclient = self.get_new_connected_ssh_channel()
        stdin, stdout, stderr = myclient.exec_command(command)
        return stdout, stderr

    def get_server_command_from_software_directory(self, software_directory: str):
        VDIR = self.get_newest_version_directory(software_directory)
        if VDIR == "V2":
            raise NotImplementedError("V2 connection capability removed from SimStack client. Please upgrade to V4.")
        elif VDIR == "V3":
            raise NotImplementedError("V3 connection capability removed from SimStack client. Please upgrade to V4.")
        elif VDIR == "V4":
            pass
        elif VDIR == "V6":
            pass
        else:
            print(
                "Found a newer server installation than this client supports (Found: %s). Please upgrade your client. Trying to connect with V4." % VDIR)
            VDIR = "V4"

        if VDIR != "V6":
            software_directory += '/' + VDIR
            myenv = "simstack_server"
        else:
            myenv = "simstack_server_v6"

        if self._queueing_system == "AiiDA":
            myenv = "aiida"

        found_conda_shell = False
        conda_sh_files = [f"{software_directory}/etc/profile.d/conda.sh",
                          f"{software_directory}/local_anaconda/etc/profile.d/conda.sh",
                          f"{software_directory}/simstack_conda_userenv.sh"]
        for conda_sh_file in conda_sh_files:
            print(f"Checking for {conda_sh_file}")
            if self.exists(conda_sh_file):
                found_conda_shell = conda_sh_file
                break

        if not found_conda_shell:
            errmsg = f"""Could not find setup file for conda environment. Please either run postinstall.sh to unpack the embedded conda environment or
        create "{software_directory}/simstack_conda_userenv.sh" to source your own environment with an installed simstack_server environment.
        """
            raise FileNotFoundError(errmsg)

        if VDIR == "V6":
            execproc = f"source {found_conda_shell}; conda activate {myenv}; "
            serverproc = "SimStackServer"
        else:
            execproc = f"source {found_conda_shell}; conda activate {myenv}; python"
            serverproc = software_directory + '/SimStackServer/SimStackServer.py'

        if VDIR != "V6" and not self.exists(serverproc):
            raise FileNotFoundError(
                "%s serverproc was not found. Please check, whether the software directory in Configuration->Servers is correct and the file exists" % serverproc)

        return "%s %s" % (execproc, serverproc)

    def _get_server_command(self):
        software_dir = self._software_directory
        return self.get_server_command_from_software_directory(software_dir)

    def connect_zmq_tunnel(self, command, connect_http = True, verbose = True):
        """
        Executes the servercommand command and sets up the ZMQ tunnel

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """

        if not self._extra_config.startswith("None"):
            extra_conf_mode = True
            exists = self.exists(self._extra_config)
            if not exists:
                raise ConnectionError("The extra_config file %s was not found on the server, please make sure it exists."%self._extra_config)
        else:
            extra_conf_mode = False

        queue_to_submission_com = {
            "slurm": "sbatch",
            "pbs": "qsub",
            "lsf": "bsub",
            "sge_smp": "qsub"
        }
        if not self._queueing_system in ["Internal", "AiiDA"]:
            mycom = queue_to_submission_com[self._queueing_system]
            if extra_conf_mode:
                com = '"source %s; which %s"'%(self._extra_config, mycom)
            else:
                com = '"which %s"'%mycom
            stdout, stderr = self.exec_command("bash -c %s" % com)
            stdout_line = None
            for line in stdout:
                stdout_line = line[:-1]
                break
            if stdout_line is None or not os.path.basename(stdout_line) == mycom:
                raise ConnectionError("Could not find batch system execution command %s in path. "
                                      "Please try changing the extra_command setting in the settings"
                                      " to include the setup file to the queueing system."%mycom)

        if extra_conf_mode:
            command = '"source %s; %s"' % (self._extra_config, command)
        else:
            command = '"%s"' % command

        stdout, stderr = self.exec_command("bash -c %s"%command)
        stderrmessage = None
        password = None
        port = None
        for line in stdout:
            firstline = line[:-1]
            myline = firstline.split()
            if not len(myline) == 5:
                raise ConnectionError("Expected port and secret key and zmq version but myline was: <%s>"%firstline )
            password = myline[3]
            port = int(myline[2])
            zmq_version_string = myline[4].strip()
            if zmq_version_string != zmq.zmq_version():
                errstring = "ZMQ version mismatch: Client: %s != Server: %s"%(zmq.zmq_version(), zmq_version_string)
                # We should simply check if both version are above 4.3.2, then the version mismatch does not matter.
                #print(errstring)

            break
        stderrmessage = " - ".join(stderr)
        if stderrmessage != "":
            raise ConnectionError("Stderr was not empty during connect. Message was: %s"%stderrmessage)
        if password is None:
            raise ConnectionError("Did not receive correct response to connection.")

        if verbose:
            print("Connecting to ZMQ serve at %d with password %s"%(port, password))

        self._socket = self._context.socket(zmq.REQ)

        socket = self._socket
        socket.plain_username = b"simstack_client"
        socket.plain_password = password.encode("utf8").strip()
        socket.setsockopt(zmq.LINGER, True)
        socket.setsockopt(zmq.SNDTIMEO, 2000)
        socket.setsockopt(zmq.RCVTIMEO, 2000)

        from zmq import ssh
        key_filename = None
        if self._sshprivatekeyfilename != "UseSystemDefault":
            key_filename = self._sshprivatekeyfilename

        connect_address = "tcp://127.0.0.1:%d"%port
        if self._url != "localhost":
            ssh_url = self.get_ssh_url()
            self._zmq_ssh_tunnel = ssh.tunnel_connection(socket, connect_address, ssh_url, keyfile=key_filename, paramiko=True)
        else:
            self._zmq_ssh_tunnel = None
            socket.connect(connect_address)
            print("Not connecting zmq ssh tunnel, as connection is going to localhost.")
        # For testing if localhost == jump host, don't do anything. Otherwise, test with different user
        socket.send(Message.connect_message())
        # Windows somehow needs this amount of time before the socket is ready:
        time.sleep(0.25)
        for i in range(0,10):
            try:
                data = socket.recv()
                break
            except zmq.error.Again as e:
                print("Port was not setup in time. Trying to connect again. Trial %d of 10."%i)
                time.sleep(0.15)
        messagetype, message = Message.unpack(data)
        if messagetype == MTS.CONNECT:
            self._should_be_connected = True
        else:
            raise ConnectionError("Received message different from connect: %s"%message)

        if not connect_http:
            return

        try:
            self._http_base_address = self.get_http_server_address()
            if verbose:
                print("Connected HTTP",self._http_base_address)
        except Exception as e:
            print(e)
            raise ConnectionError("Could not connect http tunnel. Error was: %s"%e) from e

    def _recv_ack_message(self):
        messagetype, message = self._recv_message()
        if not messagetype == MTS.ACK:
            raise ConnectionAbortedError("Did not receive acknowledge after workflow submission.")

    def get_url_for_workflow(self, workflow):
        if not workflow.startswith("/"):
            workflow = "/%s"%workflow
        return self._http_base_address + workflow

    def _recv_message(self):
        messagetype, message = Message.unpack(self._socket.recv())
        return messagetype, message

    def submit_wf(self, filename, basepath_override = None):
        resolved_filename = self.resolve_file_in_basepath(filename, basepath_override)
        self._socket.send(Message.submit_wf_message(resolved_filename))
        self._recv_ack_message()

    def submit_single_job(self, wfem):
        wfem : WorkflowExecModule
        self._socket.send(Message.submit_single_job_message(wfem))
        self._recv_ack_message()

    def send_jobstatus_message(self, wfem_uid: str):
        message = Message.getsinglejobstatus_message(wfem_uid = wfem_uid)
        self._socket.send(message)
        # This has to be the actual answer message:
        messagetype, message = self._recv_message()
        return message

    def send_abortsinglejob_message(self, wfem_uid: str):
        message = Message.abortsinglejob_message(wfem_uid = wfem_uid)
        self._socket.send(message)
        # This has to be the actual answer message:
        self._recv_message()

    def send_noop_message(self):
        self._socket.send(Message.noop_message())
        self._recv_ack_message()

    def send_shutdown_message(self):
        self._socket.send(Message.shutdown_message())
        self._recv_ack_message()

    def abort_wf(self, workflow_submitname):
        self._logger.debug("Sent Abort WF message for submitname %s"%(workflow_submitname))
        self._socket.send(Message.abort_wf_message(workflow_submitname))
        self._recv_ack_message()

    def send_clearserverstate_message(self):
        self._socket.send(Message.clearserverstate_message())
        self._recv_ack_message()

    def delete_wf(self, workflow_submitname):
        self._logger.debug("Sent delete WF message for submitname %s" % (workflow_submitname))
        self._socket.send(Message.delete_wf_message(workflow_submitname))
        self._recv_ack_message()

    def get_workflow_list(self):
        self._socket.send(Message.list_wfs_message())
        messagetype, message = self._recv_message()
        workflows = message["workflows"]
        return workflows
    
    def get_workflow_job_list(self, workflow):
        self._socket.send(Message.list_jobs_of_wf_message(workflow_submit_name=workflow))
        messagetype, message = self._recv_message()
        if not "list_of_jobs" in message:
            raise ConnectionError("Could not read message in workflow job list update %s"%message)

        files = message["list_of_jobs"]
        return files

    def is_connected(self):
        """
        Returns True if the ssh transport is currently connected. Returns not True otherwise
        :return (bool): True or not True
        """
        transport = self._ssh_client.get_transport()
        if transport is None:
            return False
        return transport.is_active()

    def exists(self, path):
        try:
            return self.exists_as_directory(path)
        except SSHExpectedDirectoryError:
            return True

    def get_newest_version_directory(self, path):
        largest_version = -1
        try:
            for entry in self._sftp_client.listdir_attr(path):
                mode = entry.st_mode
                if stat.S_ISDIR(mode):
                    fn = entry.filename
                    if fn[0] == "V":
                        try:
                            myint = int(fn[1:])
                            if myint > largest_version:
                                largest_version = myint
                        except ValueError:
                            pass
                if entry.filename == "condabin":
                    largest_version = 6
        except FileNotFoundError as e:
            newfilenotfounderror = FileNotFoundError(e.errno,"No such file %s on remote %s"%(path,self._url), path)
            raise newfilenotfounderror from e

        return "V%d"%largest_version

    def is_directory(self, path, basepath_override = None):
        resolved = self.resolve_file_in_basepath(path, basepath_override)
        sftpa : SFTPAttributes = self._sftp_client.stat(resolved)
        if stat.S_ISDIR(sftpa.st_mode):
            return True
        return False

    def get_http_server_address(self):
        """
        Function, which communicates with the server asking for the server port and setting up the
        server tunnel if it is not present.
        :return:
        """
        self._http_server_tunnel:sshtunnel.SSHTunnelForwarder

        if self._http_server_tunnel is None or not self._http_server_tunnel.is_alive:
            if self._http_server_tunnel is not None:
                self._http_server_tunnel.stop()
            """ Reconnect starting here """
            self._socket.send(Message.get_http_server_request_message(basefolder=self.get_calculation_basepath()))
            messagetype, message = self._recv_message()
            if not "http_port" in message:
                raise ConnectionError("Could not read message in http job starter.")
            #print(message)
            myport = int(message["http_port"])
            self._http_user = message["http_user"]
            self._http_pass = message["http_pass"]
            key_filename = None
            if self._sshprivatekeyfilename != "UseSystemDefault":
                key_filename = self._sshprivatekeyfilename
            self._http_server_tunnel = sshtunnel.SSHTunnelForwarder((self._url, self._port),
                                                                    ssh_username=self._user,
                                                                    ssh_pkey=key_filename,
                                                                    threaded=False,
                                                                    remote_bind_address=("127.0.0.1",myport))
            self._http_server_tunnel.start()

        if not self._http_server_tunnel.is_alive:
            raise sshtunnel.BaseSSHTunnelForwarderError("Cannot start ssh tunnel.")

        return "http://%s:%s@localhost:%d"%(
            self._http_user,
            self._http_pass,
            self._http_server_tunnel.local_bind_port
        )

    def exists_as_directory(self, path):
        """
        Checks if an absolute path on remote exists and is a directory. Throws if it exists as file
        :param path (str): The path to check
        :return bool: Exists, does not exist
        """
        try:
            sftpa : SFTPAttributes = self._sftp_client.stat(str(path))
        except FileNotFoundError as e:
            return False
        if stat.S_ISDIR(sftpa.st_mode):
            return True
        raise SSHExpectedDirectoryError("Path <%s> to expected directory exists, but was not directory"%path )

    def mkdir_p(self,directory, basepath_override = None, mode_override = None):
        """
        Creates a directory, if not existing. Does nothing if it exists. Throws if the path cannot be generated or is a file
        The function will make sure every directory in "directory" is generated but not in basepath or basepath_override.
        Bug: Mode is still ignored! I think this might be a bug in ubuntu 14.04 ssh and we should try again later.
        :param directory (str): Directory to be generated on the server. basepath will be appended
        :param basepath_override (str): If set, a custom basepath is used. If you want create a specific absolute directory, used basepath_override=""
        :param mode_override (int): Mode such as 1777
        :return (str): The absolute path of the generated directory.
        """
        if isinstance(directory, pathlib.Path):
            directory = str(directory)

        if mode_override is None:
            mode_override = self._default_mode
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        if not self._calculation_basepath == "":
            if directory.startswith("/"):
                directory = directory[1:]

        subdirs = split_directory_in_subdirectories(directory)
        complete_subdirs = []
        for mydir in subdirs:
            complete_subdirs.append(posixpath.join(basepath_override,mydir))


        for dir in complete_subdirs:
            if self.exists_as_directory(dir):
                continue
            else:
                #self._sftp_client.mkdir(dir,mode = mode_override)
                self._sftp_client.mkdir(dir)

        return directory

    def get_calculation_basepath(self):
        return self._calculation_basepath

    def get_queueing_system(self):
        return self._queueing_system

    def __del__(self):
        """
        We make sure that the connections are closed on destruction.
        :return:
        """
        if self._socket is not None:
            self._socket.close()
        if self._sftp_client != None:
            self._sftp_client.close()
        self._ssh_client.close()
        if self._http_server_tunnel is not None and not self._http_server_tunnel.is_alive:
            self._http_server_tunnel.stop()

        if self._zmq_ssh_tunnel is not None:
            if hasattr(self._zmq_ssh_tunnel, "kill"):
                # This is because it can be that the tunnel was not done via paramiko subprocess
                self._zmq_ssh_tunnel.kill()

