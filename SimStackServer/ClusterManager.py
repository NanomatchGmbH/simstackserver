import stat


import paramiko
from os import path
import posixpath

from paramiko import SFTPAttributes

from SimStackServer.Util.FileUtilities import split_directory_in_subdirectories
from SimStackServer.WorkflowModel import Resources

class SSHExpectedDirectoryError(Exception):
    pass

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
        self._sftp_client : paramiko.SFTPClient = None
        self._queueing_system = queueing_system
        self._default_mode = 770

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
        self._sftp_client = self._ssh_client.open_sftp()
        self.mkdir_p(self._calculation_basepath,basepath_override="")

    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
        self._ssh_client.close()
        if self._sftp_client != None:
            self._sftp_client.close()

    def write_jobfile(self, remote_file, exec_script, resources : Resources, jobname):
        import clusterjob
        jobscript = clusterjob.Job(exec_script, backend=self._queueing_system, jobname = jobname,
                                         queue = resources.queue, time = resources.walltime, nodes = resources.nodes,
                                         threads = resources.cpus_per_node, mem = resources.memory,
                                         stdout = jobname + ".stdout", stderr = jobname + ".stderr"
        )
        #print(jobscript.backends[self._queueing_system].keys())

        M=1024*1024
        with self._sftp_client.file(remote_file, 'w', bufsize = 16*M ) as outfile:
            outfile.write(str(jobscript))

    def put_file(self, from_file, to_file, optional_callback = None, basepath_override = None):
        """
        Transfer a file from_file (local) to to_file(remote)

        Throws FileNotFoundError in case file does not exist on local host.

        :param from_file (str): Existing file on host
        :param to_file (str): Remote file (will be overwritten)
        :param optional_callback (function): Function looking like this: callback(bytes_written, total_bytes)
        :param basepath_override (str): Overrides the basepath in case of uploads somewhere else.
        :return: Nothing
        """
        if not path.isfile(from_file):
            raise FileNotFoundError("File %s was not found during ssh put file on local host"%(from_file))
        if basepath_override is None:
            basepath_override = self._calculation_basepath
        abstofile = basepath_override + "/" + to_file
        self._sftp_client.put(from_file,abstofile,optional_callback)

    def get_file(self, from_file, to_file, optional_callback = None):
        """
        Transfer a file from_file (remote) to to_file(local)

        Throws FileNotFoundError in case file does not exist on remote host. TODO

        :param from_file (str): Existing file on remote
        :param to_file (str): Local file (will be overwritten)
        :param optional_callback (function): Function looking like this: callback(bytes_written, total_bytes)
        :return: Nothing
        """
        self._sftp_client.get(from_file, to_file, optional_callback)

    def exec_command(self, command):
        """
        Executes a command.

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """
        stdin, stdout, stderr = self._ssh_client.exec_command(command)
        for line in stdout:
            print(line)

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

    def exists_as_directory(self, path):
        """
        Checks if an absolute path on remote exists and is a directory. Throws if it exists as file
        :param path (str): The path to check
        :return bool: Exists, does not exist
        """
        try:
            sftpa : SFTPAttributes = self._sftp_client.stat(path)
        except FileNotFoundError as e:
            return False
        if stat.S_ISDIR(sftpa.st_mode):
            return True
        raise SSHExpectedDirectoryError("Path <%s> to expected directory exists, but was not directory"%path )

    def mkdir_p(self,directory,basepath_override = None, mode_override = None):
        """
        Creates a directory, if not existing. Does nothing if it exists. Throws if the path cannot be generated or is a file
        The function will make sure every directory in "directory" is generated but not in basepath or basepath_override.
        Bug: Mode is still ignored! I think this might be a bug in ubuntu 14.04 ssh and we should try again later.
        :param directory (str): Directory to be generated on the server. basepath will be appended
        :param basepath_override (str): If set, a custom basepath is used. If you want create a specific absolute directory, used basepath_override=""
        :param mode_override (int): Mode such as 1777
        :return (str): The absolute path of the generated directory.
        """

        if mode_override is None:
            mode_override = self._default_mode
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        if self._calculation_basepath is not "":
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


    def __del__(self):
        """
        We make sure that the connections are closed on destruction.
        :return:
        """
        self._ssh_client.close()
        if self._sftp_client != None:
            self._sftp_client.close()
