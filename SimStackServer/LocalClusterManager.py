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
from typing import Optional
import httpx

import sshtunnel


from SimStackServer.Util.FileUtilities import filewalker

from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError
from SimStackServer.ClusterManager import ClusterManager


class LocalClusterManager(ClusterManager):
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
        rest_port=None,
    ):
        """
        LocalClusterManager operates on local files directly without SSH/SFTP.

        :param default_queue:
        :param url (str): URL to connect to (int-nanomatchcluster.int.kit.edu, ipv4, ipv6)
        :param port (int): Port to connect to, i.e. 22
        :param calculation_basepath (str): Where everything will be stored by default. "" == home directory.
        :param user (str): Username on the respective server.
        :param sshprivatekey (str): Filename of ssh private key
        :param default_queue (str): Jobs will be submitted to this queue, if none is given.
        :param filegen_mode (bool): If True: Do not submit anything and stop once the first WaNo is rendered
        :param rest_port (int): Port the REST server is running on
        """
        # Call parent constructor
        super().__init__(
            url=url,
            port=port,
            calculation_basepath=calculation_basepath,
            user=user,
            sshprivatekey=sshprivatekey,
            extra_config=extra_config,
            queueing_system=queueing_system,
            default_queue=default_queue,
            software_directory=software_directory,
            rest_port=rest_port,
        )
        # Add LocalClusterManager-specific attribute
        self._filegen_mode = filegen_mode


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
                yield self.connect_if_disconnected()
        finally:
            self.disconnect()

    def connect_if_disconnected(self):
        if not self.is_connected():
            self.connect()

    def disconnect(self):
        """
        disconnect the ssh client
        :return: Nothing
        """
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

    def connection_is_localhost_and_same_user(self) -> bool:
        return self._url == "localhost" and getpass.getuser() == self._user

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

    def is_directory(self, path, basepath_override=None):
        resolved = self.resolve_file_in_basepath(path, basepath_override)
        return (Path.home() / resolved).is_dir()

    def get_http_server_address(self):
        """
        Function, which communicates with the server asking for the server port and setting up the
        server tunnel if it is not present.
        :return:
        """
        # ZMQ functionality removed - this method no longer works without ZMQ
        raise NotImplementedError("HTTP server address retrieval requires ZMQ, which has been removed")

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

    def __del__(self):
        """
        We make sure that the connections are closed on destruction.
        :return:
        """
        if (
            hasattr(self, "_http_server_tunnel")
            and self._http_server_tunnel is not None
            and self._http_server_tunnel.is_alive
        ):
            self._http_server_tunnel.stop()
