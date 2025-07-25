import getpass
import logging
import shutil
import socket
import os
import pathlib
import stat
import string
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
import random

import warnings
from cryptography.utils import CryptographyDeprecationWarning

from SimStackServer.SimStackServerMain import WorkflowManager
from SimStackServer.WorkflowModel import Workflow

with warnings.catch_warnings(action="ignore", category=CryptographyDeprecationWarning):
    import paramiko

from os import path
import posixpath
from pathlib import Path

import sshtunnel
import zmq


from SimStackServer.MessageTypes import Message
from SimStackServer.MessageTypes import SSS_MESSAGETYPE as MTS
from SimStackServer.Util.FileUtilities import filewalker

from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError


class LocalClusterManager:
    def __init__(
        self,
        url,
        port,
        calculation_basepath,
        user,
        sshprivatekey,
        extra_config,
        queueing_system,
        default_queue,
        software_directory=None,
        filegen_mode=False,
    ):
        """

        :param default_queue:
        :param url (str): URL to connect to (int-nanomatchcluster.int.kit.edu, ipv4, ipv6)
        :param port (int): Port to connect to, i.e. 22
        :param calculation_basepath (str): Where everything will be stored by default. "" == home directory.
        :param user (str): Username on the respective server.
        :param sshprivatekey (str): Filename of ssh private key
        :param default_queue (str): Jobs will be submitted to this queue, if none is given.
        :param filegen_mode (bool): If True: Do not submit anything and stop once the first WaNo is rendered
        """
        self._logger = logging.getLogger("ClusterManager")
        self._url = url
        try:
            self._port = int(port)
        except ValueError:
            print(f"Port was set to >{port}<. Using default port of 22")
            self._port = 22
        self._calculation_basepath = calculation_basepath
        self._extra_config = extra_config
        self._user = user
        self._sshprivatekeyfilename = sshprivatekey
        self._default_queue = default_queue
        self._should_be_connected = False
        self._sftp_client: paramiko.SFTPClient = None
        self._queueing_system = queueing_system
        self._default_mode = 770
        self._context = zmq.Context.instance()
        self._socket = None
        self._http_server_tunnel: sshtunnel.SSHTunnelForwarder
        self._http_server_tunnel = None
        self._http_user = None
        self._http_pass = None
        self._http_base_address = None
        self._unknown_host_connect_workaround = False
        self._extra_hostkey_file = None
        self._software_directory = software_directory
        self._filegen_mode = filegen_mode

    def _dummy_callback(self, bytes_written, total_bytes):
        """
        Just an example callback for the file transfer

        :param arg1 (int): Number of bytes already written by transport
        :param arg2 (int): Number of bytes in total
        :return: Nothing
        """
        print("%d %% done" % (100.0 * bytes_written / total_bytes))

    def get_ssh_url(self):
        return "%s@%s:%d" % (self._user, self._url, self._port)

    def load_extra_host_keys(self, filename):
        """
        Loads extra host keys into ssh_client
        :param filename (str): Filename of the extra hostkey db
        :return:
        """
        return

    def save_hostkeyfile(self, filename):
        """
        Save the read hostkeys, plus eventual new ones back to disk.
        :param filename (str): File to save to.
        :return:
        """
        return

    def set_connect_to_unknown_hosts(self, connect_to_unknown_hosts):
        self._unknown_host_connect_workaround = connect_to_unknown_hosts

    def connect(self):
        """
        Connect the ssh_client and setup the sftp tunnel.
        :return: Nothing
        """
        self._should_be_connected = True

    @contextmanager
    def connection_context(self):
        # Code to acquire resource, e.g.:
        try:
            if self.is_connected():
                yield None
            else:
                yield self.connect_ssh_and_zmq_if_disconnected(
                    connect_http=False, verbose=False
                )
        finally:
            self.disconnect()

    def connect_ssh_and_zmq_if_disconnected(self, connect_http=True, verbose=True):
        if not self.is_connected():
            self.connect()
            com = self._get_server_command()
            self.connect_zmq_tunnel(com, connect_http=connect_http, verbose=verbose)

    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
        if self._socket is not None:
            self._socket.close()

        if self._http_server_tunnel is not None:
            # This handling here is purely for windows. Somehow, the transport is not closed, if not set.
            for _srv in self._http_server_tunnel._server_list:
                _srv.timeout = 0.01

            self._http_server_tunnel._transport.close()
            self._http_server_tunnel.stop()

    def resolve_file_in_basepath(self, filename, basepath_override):
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        target_filename = basepath_override + "/" + filename
        if not target_filename.startswith("/"):
            target_filename = str(Path.home() / target_filename)
        return target_filename

    def delete_file(self, filename, basepath_override=None):
        resolved_filename = self.resolve_file_in_basepath(filename, basepath_override)
        os.unlink(resolved_filename)

    def rmtree(self, dirname, basepath_override=None):
        abspath = self.resolve_file_in_basepath(dirname, basepath_override)
        shutil.rmtree(abspath)

    def put_directory(
        self,
        from_directory: str,
        to_directory: str,
        optional_callback=None,
        basepath_override=None,
    ):
        for filename in filewalker(from_directory):
            cp = os.path.commonprefix([from_directory, filename])
            relpath = os.path.relpath(filename, cp)
            submitpath = path.join(to_directory, relpath)
            mydir = path.dirname(submitpath)
            self.mkdir_p(mydir)
            self.put_file(filename, submitpath, optional_callback, basepath_override)
        return self.resolve_file_in_basepath(
            str(to_directory), basepath_override=basepath_override
        )

    def exists_remote(self, path):
        return os.path.exists(path)

    # ToDo: Check if in usage anywhere except in test -
    def get_directory(
        self,
        from_directory_on_server: str,
        to_directory: str,
        optional_callback=None,  # not used?
        basepath_override=None,
    ):
        from_directory_on_server_resolved = self.resolve_file_in_basepath(
            from_directory_on_server, basepath_override=basepath_override
        )
        shutil.copytree(from_directory_on_server_resolved, to_directory)

    def put_file(
        self, from_file, to_file, optional_callback=None, basepath_override=None
    ):
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
            raise FileNotFoundError(
                "File %s was not found during ssh put file on local host" % (from_file)
            )
        if basepath_override is None:
            basepath_override = self._calculation_basepath
        abstofile = basepath_override + "/" + to_file
        if not abstofile.startswith("/"):
            abstofile = str(Path.home() / abstofile)
        # In case a directory was specified, we have to add the filename to upload into it as paramiko does not automatically.
        if self.exists_as_directory(abstofile):
            abstofile += "/" + posixpath.basename(from_file)

        shutil.copyfile(from_file, abstofile)

    def remote_open(self, filename, mode, basepath_override=None):
        abspath = self.resolve_file_in_basepath(filename, basepath_override)
        return open(abspath, mode)

    def list_dir(self, path, basepath_override=None):
        files = []
        abspath = self.resolve_file_in_basepath(
            path, basepath_override=basepath_override
        )

        for file_entry in os.scandir(abspath):
            file_char = "d" if file_entry.is_dir() else "f"
            fname = file_entry.name
            files.append({"name": fname, "path": abspath, "type": file_char})
        return files

    def get_default_queue(self):
        """
        :return (str): Name of default queue
        """
        return self._default_queue

    def _get_job_directory_path(self, given_name):
        now = datetime.now()
        random_string = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=5)
        )
        nowstr = now.strftime("%Y-%m-%d-%Hh%Mm%Ss")
        submitname = "%s-%s-%s" % (nowstr, given_name, random_string)
        return submitname

    def mkdir_random_singlejob_exec_directory(self, given_name, num_retries=10):
        for i in range(0, num_retries):
            trialdirectory = Path(
                "singlejob_exec_directories"
            ) / self._get_job_directory_path(given_name)
            if self.exists(Path(self._calculation_basepath) / trialdirectory):
                time.sleep(1.05)
            else:
                self.mkdir_p(trialdirectory)
                return trialdirectory

        raise FileExistsError("Could not generate new directory in time.")

    def get_file(
        self, from_file, to_file, basepath_override=None, optional_callback=None
    ):
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

        getpath = basepath_override + "/" + from_file
        getpath_path = Path(getpath)
        if not getpath_path.is_absolute():
            getpath = str(Path.home() / getpath)
        shutil.copyfile(getpath, to_file)

    def exec_command(self, command):
        """
        Executes a command.

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """

        p = subprocess.run(command, shell=True, capture_output=True)
        stdout = p.stdout.decode().split("\n")
        stderr = p.stderr.decode().split("\n")
        return stdout, stderr

    def get_server_command_from_software_directory(self, software_directory: str):
        myenv = "simstack_server_v6"

        if self._queueing_system == "AiiDA":
            myenv = "aiida"

        found_micromamba = False

        micromamba_bin = f"{software_directory}/envs/simstack_server_v6/bin/micromamba"
        if self.exists(micromamba_bin):
            found_micromamba = True
        found_conda_shell = False
        conda_sh_files = [
            f"{software_directory}/etc/profile.d/conda.sh",
            f"{software_directory}/V6/local_anaconda/etc/profile.d/conda.sh",
            f"{software_directory}/V6/simstack_conda_userenv.sh",
        ]
        if not found_micromamba:
            for conda_sh_file in conda_sh_files:
                if self.exists(conda_sh_file):
                    found_conda_shell = conda_sh_file
                    break

        if not found_conda_shell and not found_micromamba:
            errmsg = f"""Could not find setup file for conda environment. Please either run postinstall.sh to unpack the embedded conda environment or
        create "{software_directory}/simstack_conda_userenv.sh" to source your own environment with an installed simstack_server environment.
        """
            raise FileNotFoundError(errmsg)

        if found_micromamba:
            execproc = f"{micromamba_bin} run -r {software_directory} --name=simstack_server_v6"
            serverproc = "SimStackServer"
        else:
            execproc = f"source {found_conda_shell}; conda activate {myenv}; "
            serverproc = "SimStackServer"

        return "%s %s" % (execproc, serverproc)

    def _get_server_command(self):
        software_dir = self._software_directory
        return self.get_server_command_from_software_directory(software_dir)

    def connection_is_localhost_and_same_user(self) -> bool:
        return self._url == "localhost" and getpass.getuser() == self._user

    def connect_zmq_tunnel(self, command, connect_http=True, verbose=True):
        """
        Executes the servercommand command and sets up the ZMQ tunnel

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """
        if self._queueing_system == "Filegenerator":
            return
        if not self._extra_config.startswith("None"):
            extra_conf_mode = True
            exists = self.exists(self._extra_config)
            if not exists:
                raise ConnectionError(
                    "The extra_config file %s was not found on the server, please make sure it exists."
                    % self._extra_config
                )
        else:
            extra_conf_mode = False

        queue_to_submission_com = {
            "slurm": "sbatch",
            "pbs": "qsub",
            "lsf": "bsub",
            "sge_multi": "qsub",
        }
        if self._queueing_system not in ["Internal", "AiiDA"]:
            mycom = queue_to_submission_com[self._queueing_system]
            if extra_conf_mode:
                com = '"source %s; which %s"' % (self._extra_config, mycom)
            else:
                com = '"which %s"' % mycom
            stdout, stderr = self.exec_command("bash -c %s" % com)
            stdout_line = None
            for line in stdout:
                stdout_line = line[:-1]
                break
            if stdout_line is None or not os.path.basename(stdout_line) == mycom:
                raise ConnectionError(
                    "Could not find batch system execution command %s in path. "
                    "Please try changing the extra_command setting in the settings"
                    " to include the setup file to the queueing system." % mycom
                )

        if extra_conf_mode:
            command = '"source %s; %s"' % (self._extra_config, command)
        else:
            command = '"%s"' % command

        stdout, stderr = self.exec_command("bash -c %s" % command)
        stderrmessage = None
        password = None
        port = None
        for line in stdout:
            firstline = line[:-1]
            myline = firstline.split()
            if not len(myline) == 5:
                raise ConnectionError(
                    "Expected port and secret key and zmq version but myline was: <%s>"
                    % firstline
                )
            password = myline[3]
            port = int(myline[2])
            server_zmq_version_string = myline[4].strip()
            if server_zmq_version_string.startswith("SERVER"):
                # Versionstring is now SERVER,VERSION,ZMQ,VERSION,FUTUREPACKAGE,VERSION
                splitversion = server_zmq_version_string.split(",")
                serverversion = splitversion[1]

                semver_serversion = serverversion.split(".")[0:2]
                from SimStackServer import __version__ as myversion

                semver_myversion = myversion.split(".")[0:2]
                for client_single, server_single in zip(
                    semver_myversion, semver_serversion
                ):
                    if server_single > client_single:
                        print(
                            f"Server version {serverversion} newer than Client version {myversion}. This might lead to issues. Please update client."
                        )
                        print("Will still try to connect")
                        break
                    if client_single > server_single:
                        print(
                            f"Client version {myversion} newer than Server version {serverversion}. This might lead to issues. Please update server."
                        )
                        print("Will still try to connect")
                        break

                zmq_version_string = splitversion[3]
            else:
                print(
                    "Client version newer than Server version. This might lead to issues. Please update server."
                )

                zmq_version_string = server_zmq_version_string

            if zmq_version_string.startswith("4.2."):
                # If new issues with ZMQ versions crop up, please specify here.
                errstring = (
                    "ZMQ version mismatch: Client requires version newer than 4.3.x"
                )
                print(errstring)

            break
        stderrmessage = " - ".join(stderr)
        if stderrmessage != "":
            raise ConnectionError(
                "Stderr was not empty during connect. Message was: %s" % stderrmessage
            )
        if password is None:
            raise ConnectionError("Did not receive correct response to connection.")

        if verbose:
            print("Connecting to ZMQ serve at %d with password %s" % (port, password))

        self._socket = self._context.socket(zmq.REQ)

        socket = self._socket
        socket.plain_username = b"simstack_client"
        socket.plain_password = password.encode("utf8").strip()
        socket.setsockopt(zmq.LINGER, True)
        socket.setsockopt(zmq.SNDTIMEO, 2000)
        socket.setsockopt(zmq.RCVTIMEO, 2000)
        connect_address = "tcp://127.0.0.1:%d" % port

        socket.connect(connect_address)
        print("Not connecting zmq ssh tunnel, as connection is going to localhost.")
        # For testing if localhost == jump host, don't do anything. Otherwise, test with different user
        socket.send(Message.connect_message())
        # Windows somehow needs this amount of time before the socket is ready:
        time.sleep(0.25)
        for i in range(0, 10):
            try:
                data = socket.recv()
                break
            except zmq.error.Again:
                print(
                    "Port was not setup in time. Trying to connect again. Trial %d of 10."
                    % i
                )
                time.sleep(0.15)
        messagetype, message = Message.unpack(data)
        if messagetype == MTS.CONNECT:
            self._should_be_connected = True
        else:
            raise ConnectionError(
                "Received message different from connect: %s" % message
            )

        if not connect_http:
            return

        try:
            self._http_base_address = self.get_http_server_address()
            if verbose:
                print("Connected HTTP", self._http_base_address)
        except Exception as e:
            print(e)
            raise ConnectionError(
                "Could not connect http tunnel. Error was: %s" % e
            ) from e

    def _recv_ack_message(self):
        messagetype, message = self._recv_message()
        if not messagetype == MTS.ACK:
            raise ConnectionAbortedError(
                "Did not receive acknowledge after workflow submission."
            )

    def get_url_for_workflow(self, workflow):
        if not workflow.startswith("/"):
            workflow = "/%s" % workflow
        return self._http_base_address + workflow

    def _recv_message(self):
        messagetype, message = Message.unpack(self._socket.recv())
        return messagetype, message

    def submit_wf(self, filename, basepath_override=None):
        resolved_filename = self.resolve_file_in_basepath(filename, basepath_override)
        if self._filegen_mode:
            workflow = Workflow.new_instance_from_xml(resolved_filename)
            wf_storage = workflow.get_field_value("storage")
            if not wf_storage.startswith("/"):
                workflow.set_field_value("storage", str(Path.home() / wf_storage))
            wm = WorkflowManager()
            wm.restore()
            wm.add_finished_workflow(resolved_filename)
            workflow.jobloop()
            wm.backup_and_save()
        else:
            self._socket.send(Message.submit_wf_message(resolved_filename))
            self._recv_ack_message()

    def submit_single_job(self, wfem):
        self._socket.send(Message.submit_single_job_message(wfem))
        self._recv_ack_message()

    def send_jobstatus_message(self, wfem_uid: str):
        message = Message.getsinglejobstatus_message(wfem_uid=wfem_uid)
        self._socket.send(message)
        # This has to be the actual answer message:
        messagetype, message = self._recv_message()
        return message

    def send_abortsinglejob_message(self, wfem_uid: str):
        message = Message.abortsinglejob_message(wfem_uid=wfem_uid)
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
        self._logger.debug(
            "Sent Abort WF message for submitname %s" % (workflow_submitname)
        )
        self._socket.send(Message.abort_wf_message(workflow_submitname))
        self._recv_ack_message()

    def send_clearserverstate_message(self):
        self._socket.send(Message.clearserverstate_message())
        self._recv_ack_message()

    def delete_wf(self, workflow_submitname):
        self._logger.debug(
            "Sent delete WF message for submitname %s" % (workflow_submitname)
        )
        self._socket.send(Message.delete_wf_message(workflow_submitname))
        self._recv_ack_message()

    def get_workflow_list(self):
        if self._filegen_mode:
            self._logger.info("Listing workflows not supported in Filegenerator mode.")
            return []
        self._socket.send(Message.list_wfs_message())
        messagetype, message = self._recv_message()
        workflows = message["workflows"]
        return workflows

    def get_workflow_job_list(self, workflow):
        self._socket.send(
            Message.list_jobs_of_wf_message(workflow_submit_name=workflow)
        )
        messagetype, message = self._recv_message()
        if "list_of_jobs" not in message:
            raise ConnectionError(
                "Could not read message in workflow job list update %s" % message
            )

        files = message["list_of_jobs"]
        return files

    @staticmethod
    def _is_socket_closed(sock: socket.socket) -> bool:
        try:
            # this will try to read bytes without blocking and also without removing them from buffer (peek only)
            data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
            if len(data) == 0:
                return True
        except BlockingIOError:
            return False  # socket is open and reading from it would block
        except ConnectionResetError:
            return True  # socket was closed for some other reason
        except Exception:
            print("unexpected exception when checking if a socket is closed")
            return False
        return False

    def is_connected(self):
        """
        Returns True if the ssh transport is currently connected. Returns not True otherwise
        :return (bool): True or not True
        """
        if self.connection_is_localhost_and_same_user():
            return self._should_be_connected

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
                if entry.filename == "envs":
                    largest_version = 6
        except FileNotFoundError as e:
            newfilenotfounderror = FileNotFoundError(
                e.errno, "No such file %s on remote %s" % (path, self._url), path
            )
            raise newfilenotfounderror from e

        return "V%d" % largest_version

    def is_directory(self, path, basepath_override=None):
        resolved = self.resolve_file_in_basepath(path, basepath_override)
        return (Path.home() / resolved).is_dir()

    def get_http_server_address(self):
        """
        Function, which communicates with the server asking for the server port and setting up the
        server tunnel if it is not present.
        :return:
        """

        self._socket.send(
            Message.get_http_server_request_message(
                basefolder=self.get_calculation_basepath()
            )
        )
        messagetype, message = self._recv_message()
        if "http_port" not in message:
            raise ConnectionError("Could not read message in http job starter.")
        # print(message)
        myport = int(message["http_port"])
        self._http_user = message["http_user"]
        self._http_pass = message["http_pass"]
        return "http://%s:%s@localhost:%d" % (
            self._http_user,
            self._http_pass,
            myport,
        )

    def exists_as_directory(self, path):
        """
        Checks if an absolute path on remote exists and is a directory. Throws if it exists as file
        :param path (str): The path to check
        :return bool: Exists, does not exist
        """
        if self.connection_is_localhost_and_same_user():
            if Path(path).is_file():
                raise SSHExpectedDirectoryError(
                    "Path <%s> to expected directory exists, but was not directory"
                    % path
                )
            else:
                return Path(path).is_dir()

    def mkdir_p(self, directory, basepath_override=None, mode_override=None):
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

        absdir = self.resolve_file_in_basepath(directory, basepath_override)

        os.makedirs(absdir, exist_ok=True)

        return absdir

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

        if (
            self._http_server_tunnel is not None
            and not self._http_server_tunnel.is_alive
        ):
            self._http_server_tunnel.stop()
