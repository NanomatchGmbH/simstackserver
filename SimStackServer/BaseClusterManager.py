import abc
import logging
import os
import stat
import string
import time
from contextlib import contextmanager
from datetime import datetime
import random

import warnings
from cryptography.utils import CryptographyDeprecationWarning


from os import path
from pathlib import Path

import sshtunnel
import zmq

from SimStackServer.Util.FileUtilities import filewalker

with warnings.catch_warnings(action="ignore", category=CryptographyDeprecationWarning):
    import paramiko


class SSHExpectedDirectoryError(Exception):
    pass


class BaseClusterManager:
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
        except ValueError:
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
        self._sftp_client: paramiko.SFTPClient = None
        self._queueing_system = queueing_system
        self._default_mode = 770
        self._context = zmq.Context.instance()
        self._socket = None
        self._http_server_tunnel: sshtunnel.SSHTunnelForwarder
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
        print("%d %% done" % (100.0 * bytes_written / total_bytes))

    @abc.abstractmethod
    def get_ssh_url(self):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def load_extra_host_keys(self, filename):
        """
        Loads extra host keys into ssh_client
        :param filename (str): Filename of the extra hostkey db
        :return:
        """
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def save_hostkeyfile(self, filename):
        """
        Save the read hostkeys, plus eventual new ones back to disk.
        :param filename (str): File to save to.
        :return:
        """
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def get_new_connected_ssh_channel(self):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def set_connect_to_unknown_hosts(self, connect_to_unknown_hosts):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def connect(self):
        """
        Connect the ssh_client and setup the sftp tunnel.
        :return: Nothing
        """
        raise NotImplementedError("Implement in child class")

    @contextmanager
    def connection_context(self):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def connect_ssh_and_zmq_if_disconnected(self, connect_http=True, verbose=True):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
        raise NotImplementedError("Implement in child class")

    def resolve_file_in_basepath(self, filename, basepath_override):
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        return basepath_override + "/" + filename

    @abc.abstractmethod
    def delete_file(self, filename, basepath_override=None):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def rmtree(self, dirname, basepath_override=None):
        raise NotImplementedError("Implement in child class")

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

    @abc.abstractmethod
    def exists_remote(self, path):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def get_directory(
        self,
        from_directory_on_server: str,
        to_directory: str,
        optional_callback=None,
        basepath_override=None,
    ):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
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
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def remote_open(self, filename, mode, basepath_override=None):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def list_dir(self, path, basepath_override=None):
        raise NotImplementedError("Implement in child class")

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

    @abc.abstractmethod
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
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def exec_command(self, command):
        """
        Executes a command.

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def get_server_command_from_software_directory(self, software_directory: str):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def get_url_for_workflow(self, workflow):
        raise NotImplementedError("Implement in child class")

    @abc.abstractmethod
    def submit_wf(self, filename, basepath_override=None):
        raise NotImplementedError("Implement in Child class")

    @abc.abstractmethod
    def submit_single_job(self, wfem):
        raise NotImplementedError("Implement in Child class")

    @abc.abstractmethod
    def send_jobstatus_message(self, wfem_uid: str):
        raise NotImplementedError("Implement in Child class")

    def send_abortsinglejob_message(self, wfem_uid: str):
        raise NotImplementedError("Implement in Child class")

    def send_noop_message(self):
        raise NotImplementedError("Implement in Child class")

    def send_shutdown_message(self):
        raise NotImplementedError("Implement in Child class")

    def abort_wf(self, workflow_submitname):
        raise NotImplementedError("Implement in Child class")

    def send_clearserverstate_message(self):
        raise NotImplementedError("Implement in Child class")

    def delete_wf(self, workflow_submitname):
        raise NotImplementedError("Implement in Child class")

    def get_workflow_list(self):
        raise NotImplementedError("Implement in Child class")

    def get_workflow_job_list(self, workflow):
        raise NotImplementedError("Implement in Child class")

    def is_connected(self):
        """
        Returns True if the ssh transport is currently connected. Returns not True otherwise
        :return (bool): True or not True
        """
        raise NotImplementedError("Implement in Child class")

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
        raise NotImplementedError("Implement in Child class")

    def get_http_server_address(self):
        """
        Function, which communicates with the server asking for the server port and setting up the
        server tunnel if it is not present.
        :return:
        """
        raise NotImplementedError("Implement in Child class")

    def exists_as_directory(self, path):
        """
        Checks if an absolute path on remote exists and is a directory. Throws if it exists as file
        :param path (str): The path to check
        :return bool: Exists, does not exist
        """
        raise NotImplementedError("Implement in Child class")

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
        raise NotImplementedError("Implement in Child class")

    def get_calculation_basepath(self):
        return self._calculation_basepath

    def get_queueing_system(self):
        return self._queueing_system
