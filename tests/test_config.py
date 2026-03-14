from unittest.mock import patch, MagicMock

import tempfile
import os
import yaml

import pytest

from SimStackServer.Config import Config, ServerConfig
from SimStackServer.WorkflowModel import Resources


@pytest.fixture
def config():
    with tempfile.TemporaryDirectory() as tempdir:
        conf_obj = Config()
        mock_dirs = MagicMock()
        mock_dirs.user_config_dir = f"{tempdir}/config"
        mock_dirs.user_log_dir = f"{tempdir}/log"
        conf_obj._dirs = mock_dirs
        Config._dirs = mock_dirs
        Config._server_config = None
        yield conf_obj


@pytest.fixture
def mock_psutil():
    with patch("SimStackServer.Config.psutil") as mock_psutil:
        yield mock_psutil


def _make_server_config(resources=None):
    return ServerConfig(
        rest_port=8080,
        client_secret="test-secret",
        server_version="SERVER,1.0,REST,1.0",
        resources=resources,
    )


def test_setup_root_logger(config):
    handler = config._setup_root_logger()
    assert handler is not None
    assert handler.baseFilename.endswith("simstack_server.log")


def test_register_pid(config):
    with patch("SimStackServer.Config.NoEnterPIDLockFile") as MockLockFile:
        mock_lock_file = MockLockFile.return_value
        pidfile = config.register_pid()
        assert pidfile == mock_lock_file
        MockLockFile.assert_called_once_with(config.get_pid_file(), timeout=0.0)


def test_get_pid_file(config):
    pid_file = config.get_pid_file()
    assert pid_file.endswith("SimStackServer.pid")


def test_is_running_not_locked(config, mock_psutil):
    with patch.object(config, "register_pid") as mock_register_pid:
        mock_register_pid.return_value.is_locked.return_value = False
        assert not config.is_running()


def test_is_running_pid_not_exists(config, mock_psutil):
    with patch.object(Config, "register_pid") as mock_register_pid:
        mock_register_pid.return_value.is_locked.return_value = True
        mock_register_pid.return_value.read_pid.return_value = 1234
        mock_psutil.pid_exists.return_value = False
        assert not config.is_running()
        mock_register_pid.return_value.break_lock.assert_called_once()


def test_is_running_pid_exists(config, mock_psutil):
    with patch.object(Config, "register_pid") as mock_register_pid:
        mock_register_pid.return_value.is_locked.return_value = True
        mock_register_pid.return_value.read_pid.return_value = 1234
        mock_psutil.pid_exists.return_value = True
        mock_process = MagicMock()
        mock_process.cmdline.return_value = ["python", "SimStackServer"]
        mock_psutil.Process.return_value = mock_process
        assert config.is_running()


def test_is_running_pid_exists_different_process(config, mock_psutil):
    with patch.object(Config, "register_pid") as mock_register_pid:
        mock_register_pid.return_value.is_locked.return_value = True
        mock_register_pid.return_value.read_pid.return_value = 1234
        mock_psutil.pid_exists.return_value = True
        mock_process = MagicMock()
        mock_process.cmdline.return_value = ["python", "other_process"]
        mock_psutil.Process.return_value = mock_process
        assert not config.is_running()
        mock_register_pid.return_value.break_lock.assert_called_once()


# ==================== Tests for ServerConfig ====================


def test_server_config_to_dict_without_resources():
    sc = ServerConfig(rest_port=9090, client_secret="s3cret", server_version="v1")
    d = sc.to_dict()
    assert d == {
        "rest_port": 9090,
        "client_secret": "s3cret",
        "server_version": "v1",
    }
    assert "resources" not in d


def test_server_config_to_dict_with_resources():
    resources = Resources()
    resources.from_dict({"resource_name": "test", "walltime": 100})
    sc = ServerConfig(
        rest_port=9090, client_secret="s3cret", server_version="v1", resources=resources
    )
    d = sc.to_dict()
    assert d["rest_port"] == 9090
    assert "resources" in d
    assert d["resources"]["resource_name"] == "test"


def test_server_config_roundtrip_without_resources():
    sc = ServerConfig(rest_port=9090, client_secret="s3cret", server_version="v1")
    restored = ServerConfig.from_dict(sc.to_dict())
    assert restored.rest_port == 9090
    assert restored.client_secret == "s3cret"
    assert restored.server_version == "v1"
    assert restored.resources is None


def test_server_config_roundtrip_with_resources():
    resources = Resources()
    resources.from_dict({"resource_name": "cluster1", "walltime": 3600})
    sc = ServerConfig(
        rest_port=8080, client_secret="pw", server_version="v2", resources=resources
    )
    restored = ServerConfig.from_dict(sc.to_dict())
    assert restored.rest_port == 8080
    assert restored.resources is not None
    assert restored.resources.resource_name == "cluster1"
    assert restored.resources.walltime == 3600


# ==================== Tests for save/load server config ====================


def test_save_server_config(config):
    """Test saving a ServerConfig with resources"""
    resources = Resources()
    resources.from_dict(
        {
            "resource_name": "test_cluster",
            "walltime": 3600,
            "cpus_per_node": 8,
            "nodes": 2,
            "memory": 8192,
            "queue": "default",
            "queueing_system": "slurm",
        }
    )
    sc = _make_server_config(resources)
    filepath = Config.save_server_config(sc)

    assert os.path.exists(filepath)
    assert filepath.endswith("server_config.yml")

    with open(filepath, "r") as f:
        saved_data = yaml.safe_load(f)

    assert saved_data["rest_port"] == 8080
    assert saved_data["client_secret"] == "test-secret"
    assert saved_data["resources"]["resource_name"] == "test_cluster"


def test_load_server_config(config):
    """Test loading a ServerConfig"""
    resources = Resources()
    resources.from_dict(
        {
            "resource_name": "load_test_cluster",
            "walltime": 7200,
            "cpus_per_node": 16,
            "nodes": 4,
            "memory": 16384,
            "queue": "gpu",
            "queueing_system": "pbs",
            "username": "testuser",
            "base_URI": "cluster.example.com",
        }
    )
    Config.save_server_config(_make_server_config(resources))

    loaded = Config.load_server_config()
    assert loaded is not None
    assert loaded.rest_port == 8080
    assert loaded.client_secret == "test-secret"
    assert loaded.resources is not None
    assert loaded.resources.resource_name == "load_test_cluster"
    assert loaded.resources.walltime == 7200
    assert loaded.resources.username == "testuser"


def test_load_server_config_nonexistent(config):
    """Test loading configuration when file doesn't exist"""
    config_path = Config._get_config_file("server_config.yml")
    if os.path.exists(config_path):
        os.remove(config_path)

    loaded = Config.load_server_config()
    assert loaded is None


def test_save_server_config_overwrites_existing(config):
    """Test that save_server_config overwrites existing configuration"""
    resources1 = Resources()
    resources1.from_dict({"resource_name": "first_config", "walltime": 1000, "cpus_per_node": 4})
    Config.save_server_config(
        ServerConfig(rest_port=8080, client_secret="s1", server_version="v1", resources=resources1)
    )

    resources2 = Resources()
    resources2.from_dict({"resource_name": "second_config", "walltime": 2000, "cpus_per_node": 8})
    Config.save_server_config(
        ServerConfig(rest_port=9090, client_secret="s2", server_version="v2", resources=resources2)
    )

    loaded = Config.load_server_config()
    assert loaded is not None
    assert loaded.rest_port == 9090
    assert loaded.resources.resource_name == "second_config"
    assert loaded.resources.walltime == 2000


def test_save_load_config_with_all_fields(config):
    """Test saving and loading configuration with all possible fields"""
    resources = Resources()
    resources_dict = {
        "resource_name": "full_config",
        "walltime": 86400,
        "cpus_per_node": 32,
        "nodes": 8,
        "queue": "production",
        "memory": 32768,
        "custom_requests": "feature=avx2,gpu=v100",
        "base_URI": "hpc.research.org",
        "port": 2222,
        "username": "researcher",
        "basepath": "workspace/simstack",
        "queueing_system": "slurm",
        "sw_dir_on_resource": "/opt/software",
        "extra_config": "/etc/cluster/config.sh",
        "ssh_private_key": "/home/user/.ssh/id_rsa",
        "sge_pe": "mpi",
        "reuse_results": "true",
    }
    resources.from_dict(resources_dict)
    Config.save_server_config(_make_server_config(resources))

    loaded = Config.load_server_config()
    assert loaded is not None
    r = loaded.resources
    assert r is not None
    assert r.resource_name == "full_config"
    assert r.walltime == 86400
    assert r.cpus_per_node == 32
    assert r.nodes == 8
    assert r.queue == "production"
    assert r.memory == 32768
    assert r.custom_requests == "feature=avx2,gpu=v100"
    assert r.base_URI == "hpc.research.org"
    assert r.port == 2222
    assert r.username == "researcher"
    assert r.basepath == "workspace/simstack"
    assert r.queueing_system == "slurm"
    assert r.sw_dir_on_resource == "/opt/software"
    assert r.extra_config == "/etc/cluster/config.sh"
    assert r.ssh_private_key == "/home/user/.ssh/id_rsa"
    assert r.sge_pe == "mpi"
    assert r.reuse_results is True


def test_save_server_config_creates_directory_if_not_exists(config):
    """Test that save_server_config creates the config directory if it doesn't exist"""
    import shutil

    config_dir = Config._dirs.user_config_dir
    if os.path.exists(config_dir):
        shutil.rmtree(config_dir)

    sc = _make_server_config()
    filepath = Config.save_server_config(sc)

    assert os.path.exists(config_dir)
    assert os.path.exists(filepath)


def test_load_server_config_without_resources(config):
    """Test loading a ServerConfig that has no resources"""
    sc = ServerConfig(rest_port=5555, client_secret="pw", server_version="v1")
    Config.save_server_config(sc)

    loaded = Config.load_server_config()
    assert loaded is not None
    assert loaded.rest_port == 5555
    assert loaded.resources is None


def test_get_resources_loads_config_on_first_call(config):
    """Test that get_resources loads config on first call"""
    Config._server_config = None

    resources = Resources()
    resources.from_dict({"resource_name": "cached_config", "walltime": 5000, "cpus_per_node": 12})
    Config.save_server_config(_make_server_config(resources))

    loaded_resources = Config.get_resources()
    assert loaded_resources is not None
    assert loaded_resources.resource_name == "cached_config"
    assert loaded_resources.walltime == 5000
    assert loaded_resources.cpus_per_node == 12


def test_get_server_config_returns_cached_value(config):
    """Test that get_server_config returns cached value on subsequent calls"""
    Config._server_config = None

    resources = Resources()
    resources.from_dict({"resource_name": "cache_test", "walltime": 3000})
    Config.save_server_config(_make_server_config(resources))

    first_call = Config.get_server_config()
    assert first_call is not None

    # Manually write a different file to disk (bypassing save which updates cache)
    import yaml

    different_resources = Resources()
    different_resources.from_dict({"resource_name": "different_config", "walltime": 9999})
    sc2 = _make_server_config(different_resources)
    filepath = Config._get_config_file("server_config.yml")
    with open(filepath, "w") as f:
        yaml.safe_dump(sc2.to_dict(), f)

    # Second call should return cached value (not reload from file)
    second_call = Config.get_server_config()
    assert second_call is not None
    assert second_call.resources.resource_name == "cache_test"  # Still the original
    assert second_call.resources.walltime == 3000  # Still the original


def test_get_resources_returns_none_if_no_config(config):
    """Test that get_resources returns None when no config file exists"""
    Config._server_config = None

    config_path = Config._get_config_file("server_config.yml")
    if os.path.exists(config_path):
        os.remove(config_path)

    resources = Config.get_resources()
    assert resources is None


def test_get_resources_returns_none_if_no_resources_in_config(config):
    """Test that get_resources returns None when ServerConfig has no resources"""
    Config._server_config = None

    sc = ServerConfig(rest_port=5555, client_secret="pw", server_version="v1")
    Config.save_server_config(sc)

    resources = Config.get_resources()
    assert resources is None


def test_get_resources_after_save_server_config(config):
    """Test that get_resources can be used after save_server_config"""
    Config._server_config = None

    resources = Resources()
    resources.from_dict({"resource_name": "save_then_get", "walltime": 7777, "memory": 20480})
    Config.save_server_config(_make_server_config(resources))

    loaded = Config.get_resources()
    assert loaded is not None
    assert loaded.resource_name == "save_then_get"
    assert loaded.walltime == 7777
    assert loaded.memory == 20480


def test_get_server_config(config):
    """Test that get_server_config loads and caches"""
    Config._server_config = None

    sc = _make_server_config()
    Config.save_server_config(sc)
    Config._server_config = None  # clear cache

    loaded = Config.get_server_config()
    assert loaded is not None
    assert loaded.rest_port == 8080

    # Second call returns cached
    loaded2 = Config.get_server_config()
    assert loaded2 is loaded
