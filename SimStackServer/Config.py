from appdirs import AppDirs
from os import path
import psutil

import logging
from logging.handlers import RotatingFileHandler


from SimStackServer.Util.FileUtilities import mkdir_p

from SimStackServer.Util.NoEnterPIDLockFile import NoEnterPIDLockFile


class Config:
    _dirs = AppDirs(appname="SimStackServer", appauthor="Nanomatch", roaming=False)
    _logger_setup = False

    def __init__(self):
        self._setup_root_logger()
        self._logger = self._get_cls_logger()
        mkdir_p(self._dirs.user_config_dir)

    @staticmethod
    def _get_cls_logger():
        return logging.getLogger("Config")

    @classmethod
    def _setup_root_logger(cls):
        if not Config._logger_setup:
            mkdir_p(cls._dirs.user_log_dir)
            mypath = path.join(cls._dirs.user_log_dir, "simstack_server.log")
            rotate_size = 1024 * 1024  # 1M
            handler = RotatingFileHandler(mypath, maxBytes=rotate_size, backupCount=5)
            logging.basicConfig(
                format="%(asctime)s %(message)s", level=logging.INFO, handlers=[handler]
            )
            return handler

    @classmethod
    def register_pid(cls):
        """
        Registers a new pid. Throws Error, if pidfile exists.
        :return:
        """
        pidfilename = cls.get_pid_file()

        return NoEnterPIDLockFile(pidfilename, timeout=0.0)

    @classmethod
    def get_pid_file(cls):
        """
        Returns filename of pid file.
        :return (str): Path to pidfile
        """
        pidfilename = cls._get_config_file("SimStackServer.pid")
        return pidfilename

    @classmethod
    def is_running(cls):
        """
        Checks if this process is already running. Removes pidfile and returns False, if a process is
        running on this pid, which is not python.
        :return (bool): True, if already running
        """
        pidfile = cls.register_pid()

        if not pidfile.is_locked():
            return False
        pid = pidfile.read_pid()

        cls._get_cls_logger().debug("PID was %d" % pid)
        if not psutil.pid_exists(pid):
            try:
                cls._get_cls_logger().warning(
                    "Process was locked, but process did not exist anymore. Restarting server"
                )
                pidfile.break_lock()
                cls._get_cls_logger().debug("Breaking lock %d" % pid)
            except FileNotFoundError:
                # This exception might occur if a server was just in the process of shutting down.
                pass
            return False
        else:
            cls._get_cls_logger().debug("PID existed already %d" % pid)
            proc = psutil.Process(pid)
            if "SimStackServer" not in "".join(proc.cmdline()):
                try:
                    cls._get_cls_logger().warning(
                        "Process was locked, but process name %s was different."
                        % proc.name()
                    )
                    pidfile.break_lock()
                except FileNotFoundError:
                    # This exception might occur if a server was just in the process of shutting down.
                    pass
                return False
        return True

    @classmethod
    def _get_config_file(cls, filename):
        """
        Returns the filename in the user config directory.
        :param filename (str): Relative filename
        :return (str): Filename in directory
        """
        mkdir_p(cls._dirs.user_config_dir)
        return path.join(cls._dirs.user_config_dir, filename)
