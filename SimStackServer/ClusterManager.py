import socket
import clusterjob

import paramiko
from os import path

from SimStackServer.WorkflowModel import Resources


class ClusterManager(object):
    def __init__(self, url, port, calculation_basepath, user, queueing_system):
        """

        :param url (str): URL to connect to (int-nanomatchcluster.int.kit.edu, ipv4, ipv6)
        :param port (int): Port to connect to, i.e. 22
        :param calculation_basepath (str): Where everything will be stored by default. "" == home directory.
        :param user (str): Username on the respective server.
        """
        self._url = url
        self._port = port
        self._calculation_basepath = calculation_basepath
        self._user = user
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.load_system_host_keys()
        self._should_be_connected = False
        self._sftp_client = None
        self._queueing_system = queueing_system

    def _dummy_callback(self, bytes_written, total_bytes):
        """
        Just an example callback for the file transfer

        :param arg1 (int): Number of bytes already written by transport
        :param arg2 (int): Number of bytes in total
        :return: Nothing
        """
        print("%d %% done"%(100.0*bytes_written/total_bytes))

    def connect(self):
        """
        Connect the ssh_client and setup the sftp tunnel.
        :return: Nothing
        """
        self._ssh_client.connect(self._url,self._port, username=self._user)
        self._should_be_connected = True
        self._sftp_client =self._ssh_client.open_sftp()

    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
        self._ssh_client.close()
        if self._sftp_client != None:
            self._sftp_client.close()

    def write_jobfile(self, remote_file, exec_script, resources : Resources, jobname):
        jobscript = clusterjob.Job(exec_script, backend=self._queueing_system, jobname = jobname,
                                         queue = resources.queue, time = resources.walltime, nodes = resources.nodes,
                                         threads = resources.cpus_per_node, mem = resources.memory,
                                         stdout = jobname + ".stdout", stderr = jobname + ".stderr"
        )
        #print(jobscript.backends[self._queueing_system].keys())

        M=1024*1024
        with self._sftp_client.file(remote_file, 'w', bufsize = 16*M ) as outfile:
            outfile.write(str(jobscript))

    def put_file(self, from_file, to_file):
        """
        Transfer a file from_file (local) to to_file(remote)

        Throws FileNotFoundError in case file does not exist on local host.

        :param from_file (str): Existing file on host
        :param to_file (str): Remote file (will be overwritten)
        :return: Nothing
        """
        if not path.isfile(from_file):
            raise FileNotFoundError("File %s was not found during ssh put file on local host"%(from_file))
        self._sftp_client.put(from_file,to_file,self._dummy_callback)

    def get_file(self, from_file, to_file):
        """
        Transfer a file from_file (remote) to to_file(local)

        Throws FileNotFoundError in case file does not exist on remote host. TODO

        :param from_file (str): Existing file on remote
        :param to_file (str): Local file (will be overwritten)
        :return: Nothing
        """
        self._sftp_client.get(from_file, to_file, self._dummy_callback)

    def exec_command(self, command):
        """
        Executes a command.

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """
        stdin, stdout, stderr = self._ssh_client.exec_command(command)
        for line in stdout:
            print(line)

    def __del__(self):
        """
        We make sure that the connections are closed on destruction.
        :return:
        """
        self._ssh_client.close()
        if self._sftp_client != None:
            self._sftp_client.close()
