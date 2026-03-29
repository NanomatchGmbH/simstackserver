from dataclasses import dataclass, field
from typing import Optional
import os

from appdirs import AppDirs
from os import path
import psutil
import yaml

import logging
from logging.handlers import RotatingFileHandler


from SimStackServer.Util.FileUtilities import mkdir_p

from SimStackServer.Util.NoEnterPIDLockFile import NoEnterPIDLockFile


@dataclass
class ServerConfig:
    """Server-level configuration: how the server itself runs."""

    rest_port: int
    client_secret: str
    server_version: str
    resources: Optional["Resources"] = field(default=None, repr=False)  # noqa: F821

    def to_dict(self) -> dict:
        d = {
            "rest_port": self.rest_port,
            "client_secret": self.client_secret,
            "server_version": self.server_version,
        }
        if self.resources is not None:
            resources_dict = {}
            self.resources.to_dict(resources_dict)
            d["resources"] = resources_dict
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ServerConfig":
        from SimStackServer.WorkflowModel import Resources

        resources = None
        if "resources" in d and d["resources"] is not None:
            resources = Resources()
            resources.from_dict(d["resources"])
        return cls(
            rest_port=int(d["rest_port"]),
            client_secret=str(d.get("client_secret", "")),
            server_version=str(d.get("server_version", "")),
            resources=resources,
        )


class Config:
    _dirs = AppDirs(appname="SimStackServer", appauthor="Nanomatch", roaming=False)
    _logger_setup = False
    _server_config: Optional[ServerConfig] = None

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

    @classmethod
    def save_server_config(cls, server_config: ServerConfig) -> str:
        """
        Save the ServerConfig to the config directory.

        :param server_config: ServerConfig to save
        :return (str): Path to the saved file
        """
        filepath = cls._get_config_file("server_config.yml")

        with open(filepath, "w") as f:
            yaml.safe_dump(server_config.to_dict(), f, default_flow_style=False)

        cls._server_config = server_config
        cls._get_cls_logger().info(f"Saved server configuration to {filepath}")
        return filepath

    @classmethod
    def load_server_config(cls) -> Optional[ServerConfig]:
        """
        Load ServerConfig from the config directory.

        :return: ServerConfig, or None if no config exists
        """
        filepath = cls._get_config_file("server_config.yml")

        if not path.exists(filepath):
            cls._get_cls_logger().warning(f"No configuration file found at {filepath}")
            return None

        with open(filepath, "r") as f:
            config_dict = yaml.safe_load(f)

        server_config = ServerConfig.from_dict(config_dict)
        cls._server_config = server_config
        cls._get_cls_logger().info(f"Loaded server configuration from {filepath}")
        return server_config

    @classmethod
    def get_server_config(cls) -> Optional[ServerConfig]:
        """
        Get the cached ServerConfig, loading from disk if necessary.

        :return: ServerConfig, or None if no config exists
        """
        if cls._server_config is None:
            cls.load_server_config()
        return cls._server_config

    @classmethod
    def get_resources(cls):
        """
        Get the cached Resources object from the ServerConfig.

        :return: Resources object, or None if not configured
        """
        server_config = cls.get_server_config()
        if server_config is None:
            return None
        return server_config.resources

    # Maps environment variable name -> Resources field name
    _ENV_RESOURCES_MAP = {
        "SIMSTACK_RESOURCE_NAME": "resource_name",
        "SIMSTACK_WALLTIME": "walltime",
        "SIMSTACK_CPUS_PER_NODE": "cpus_per_node",
        "SIMSTACK_NODES": "nodes",
        "SIMSTACK_QUEUE": "queue",
        "SIMSTACK_MEMORY": "memory",
        "SIMSTACK_CUSTOM_REQUESTS": "custom_requests",
        "SIMSTACK_BASE_URI": "base_URI",
        "SIMSTACK_SSH_PORT": "port",
        "SIMSTACK_RESOURCE_REST_PORT": "rest_port",
        "SIMSTACK_USERNAME": "username",
        "SIMSTACK_BASEPATH": "basepath",
        "SIMSTACK_QUEUEING_SYSTEM": "queueing_system",
        "SIMSTACK_SW_DIR": "sw_dir_on_resource",
        "SIMSTACK_EXTRA_CONFIG": "extra_config",
        "SIMSTACK_SSH_KEY": "ssh_private_key",
        "SIMSTACK_RESOURCE_SECRET": "client_secret",
        "SIMSTACK_USE_SSH_TUNNEL": "use_ssh_tunnel",
        "SIMSTACK_SGE_PE": "sge_pe",
        "SIMSTACK_REUSE_RESULTS": "reuse_results",
    }

    @classmethod
    def apply_env_overrides(cls, server_config: "ServerConfig") -> "ServerConfig":
        """Apply SIMSTACK_* environment variable overrides onto a ServerConfig.

        Server-level variables:
          SIMSTACK_SERVER_PORT   — overrides rest_port
          SIMSTACK_SERVER_SECRET — overrides client_secret

        Resources variables (see _ENV_RESOURCES_MAP for full list):
          SIMSTACK_BASEPATH, SIMSTACK_QUEUEING_SYSTEM, SIMSTACK_CPUS_PER_NODE, …

        Only variables that are actually set in the environment are applied;
        unset variables leave the corresponding field unchanged.

        :param server_config: ServerConfig to modify in-place.
        :return: The same ServerConfig instance (for convenience).
        """
        from SimStackServer.WorkflowModel import Resources

        port_env = os.environ.get("SIMSTACK_SERVER_PORT")
        if port_env is not None:
            server_config.rest_port = int(port_env)

        secret_env = os.environ.get("SIMSTACK_SERVER_SECRET")
        if secret_env is not None:
            server_config.client_secret = secret_env

        # Build a partial Resources dict from env vars and apply via from_dict,
        # which handles bool coercion ("true"/"false") and numeric casting.
        resources_overrides = {
            field: os.environ[env_var]
            for env_var, field in cls._ENV_RESOURCES_MAP.items()
            if env_var in os.environ
        }
        if resources_overrides:
            if server_config.resources is None:
                server_config.resources = Resources()
            server_config.resources.from_dict(resources_overrides)  # type: ignore[union-attr]

        return server_config
