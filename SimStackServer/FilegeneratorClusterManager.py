import abc
import logging
import os
import pathlib
import shutil
import time

from os import path
import posixpath
from pathlib import Path

import sshtunnel

from SimStackServer.BaseClusterManager import BaseClusterManager
from SimStackServer.SimStackServerMain import WorkflowManager
from SimStackServer.WorkflowModel import Workflow


class NotImplementedForFilegeneratorClusterManager(Exception):
    pass


class FilegeneratorClusterManager(BaseClusterManager):
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
        self._should_be_connected = False
        self._queueing_system = queueing_system
        self._default_mode = 770
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

    def get_ssh_url(self):
        raise NotImplementedForFilegeneratorClusterManager("Implement in child class")

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

    def get_new_connected_ssh_channel(self):
        raise NotImplementedForFilegeneratorClusterManager("Implement in child class")

    @abc.abstractmethod
    def set_connect_to_unknown_hosts(self, connect_to_unknown_hosts):
        return

    def connect(self):
        """
        Connect the ssh_client and setup the sftp tunnel.
        :return: Nothing
        """
        return True

    def connection_context(self):
        raise NotImplementedForFilegeneratorClusterManager("Implement in child class")

    def connect_ssh_and_zmq_if_disconnected(self, connect_http=True, verbose=True):
        raise NotImplementedForFilegeneratorClusterManager("Implement in child class")

    @abc.abstractmethod
    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
        return True

    def resolve_file_in_basepath(self, filename, basepath_override):
        if basepath_override is None:
            basepath_override = self._calculation_basepath

        target_filename = basepath_override + "/" + filename
        if not target_filename.startswith("/"):
            target_filename = str(Path.home() / target_filename)
        print(target_filename)
        return target_filename

    def delete_file(self, filename, basepath_override=None):
        resolved_filename = self.resolve_file_in_basepath(filename, basepath_override)
        os.unlink(resolved_filename)

    def rmtree(self, dirname, basepath_override=None):
        abspath = self.resolve_file_in_basepath(dirname, basepath_override)
        shutil.rmtree(abspath)

    def exists_remote(self, path):
        return os.path.exists(path)

    def get_directory(
        self,
        from_directory_on_server: str,
        to_directory: str,
        optional_callback=None,
        basepath_override=None,
    ):
        raise NotImplementedForFilegeneratorClusterManager(
            "Not implemented for Filegenerator"
        )

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

    @abc.abstractmethod
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
        shutil.copyfile(getpath, to_file)

    def exec_command(self, command):
        """
        Executes a command.

        :param command (str): Command to execute remotely.
        :return: Nothing (currently)
        """
        raise NotImplementedError("Not implemented in FilegeneratorClusterManager")

    def get_server_command_from_software_directory(self, software_directory: str):
        raise NotImplementedError("Not implemented in FilegeneratorClusterManager")

    def get_url_for_workflow(self, workflow):
        if not workflow.startswith("/"):
            workflow = "/%s" % workflow
        return self._calculation_basepath + workflow

    def submit_wf(self, filename, basepath_override=None):
        resolved_filename = self.resolve_file_in_basepath(filename, basepath_override)
        workflow = Workflow.new_instance_from_xml(resolved_filename)
        wf_storage = workflow.get_field_value("storage")
        if not wf_storage.startswith("/"):
            workflow.set_field_value("storage", str(Path.home() / wf_storage))
        wm = WorkflowManager()
        wm.restore()
        wm.add_finished_workflow(resolved_filename)
        workflow.jobloop()
        wm.backup_and_save()

    def submit_single_job(self, wfem):
        raise NotImplementedError("Not implemented in FGCM")

    def send_jobstatus_message(self, wfem_uid: str):
        raise NotImplementedError("Not implemented in FGCM")

    def send_abortsinglejob_message(self, wfem_uid: str):
        raise NotImplementedError("Not implemented in FGCM")

    def send_noop_message(self):
        return

    def send_shutdown_message(self):
        return

    def abort_wf(self, workflow_submitname):
        raise NotImplementedError("Not implemented in FGCM")

    def send_clearserverstate_message(self):
        raise NotImplementedError("Not implemented in FGCM")

    def delete_wf(self, workflow_submitname):
        raise NotImplementedError("Not implemented in FGCM")

    def get_workflow_list(self):
        return []

    def get_workflow_job_list(self, workflow):
        return []

    def is_connected(self):
        """
        Returns True if the ssh transport is currently connected. Returns not True otherwise
        :return (bool): True or not True
        """
        return True

    def exists(self, path):
        return self.exists_as_directory(path)

    def get_newest_version_directory(self, path):
        return "V6"

    def is_directory(self, path, basepath_override=None):
        resolved = self.resolve_file_in_basepath(path, basepath_override)
        return os.path.isdir(resolved)

    def get_http_server_address(self):
        """
        Function, which communicates with the server asking for the server port and setting up the
        server tunnel if it is not present.
        :return:
        """
        raise NotImplementedError("No")

    def exists_as_directory(self, path):
        """
        Checks if an absolute path on remote exists and is a directory. Throws if it exists as file
        :param path (str): The path to check
        :return bool: Exists, does not exist
        """
        # Note this needs to be extended still
        return os.path.isdir(path)

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
