from unittest.mock import patch, MagicMock

import tempfile
import os
import yaml

import pytest

from SimStackServer.Config import Config
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
        yield conf_obj


@pytest.fixture
def mock_psutil():
    with patch("SimStackServer.Config.psutil") as mock_psutil:
        yield mock_psutil


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


# ==================== Tests for save_config and load_config ====================


def test_save_config(config):
    """Test saving a Resources configuration"""
    # Create a Resources object
    resources = Resources()
    resources_dict = {
        "resource_name": "test_cluster",
        "walltime": 3600,
        "cpus_per_node": 8,
        "nodes": 2,
        "memory": 8192,
        "queue": "default",
        "queueing_system": "slurm",
    }
    resources.from_dict(resources_dict)

    # Save configuration
    filepath = Config.save_config(resources)

    # Verify file was created
    assert os.path.exists(filepath)
    assert filepath.endswith("resources.yml")

    # Verify content - note that to_dict saves as strings
    with open(filepath, 'r') as f:
        saved_data = yaml.safe_load(f)

    assert saved_data["resource_name"] == "test_cluster"
    assert saved_data["walltime"] == "3600"
    assert saved_data["cpus_per_node"] == "8"
    assert saved_data["nodes"] == "2"
    assert saved_data["memory"] == "8192"
    assert saved_data["queue"] == "default"
    assert saved_data["queueing_system"] == "slurm"


def test_load_config(config):
    """Test loading a Resources configuration"""
    # Create and save a configuration first
    resources = Resources()
    resources_dict = {
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
    resources.from_dict(resources_dict)
    Config.save_config(resources)

    # Load configuration
    loaded_resources = Config.load_config()

    # Verify loaded data
    assert loaded_resources is not None
    assert loaded_resources.resource_name == "load_test_cluster"
    assert loaded_resources.walltime == 7200
    assert loaded_resources.cpus_per_node == 16
    assert loaded_resources.nodes == 4
    assert loaded_resources.memory == 16384
    assert loaded_resources.queue == "gpu"
    assert loaded_resources.queueing_system == "pbs"
    assert loaded_resources.username == "testuser"
    assert loaded_resources.base_URI == "cluster.example.com"


def test_load_config_nonexistent(config):
    """Test loading configuration when file doesn't exist"""
    # Ensure the config file doesn't exist
    config_path = Config._get_config_file("resources.yml")
    if os.path.exists(config_path):
        os.remove(config_path)

    # Should return None
    loaded_resources = Config.load_config()
    assert loaded_resources is None


def test_save_config_overwrites_existing(config):
    """Test that save_config overwrites existing configuration"""
    # Create and save first configuration
    resources1 = Resources()
    resources1.from_dict({
        "resource_name": "first_config",
        "walltime": 1000,
        "cpus_per_node": 4,
    })
    Config.save_config(resources1)

    # Create and save second configuration
    resources2 = Resources()
    resources2.from_dict({
        "resource_name": "second_config",
        "walltime": 2000,
        "cpus_per_node": 8,
    })
    Config.save_config(resources2)

    # Load and verify it's the second configuration
    loaded_resources = Config.load_config()
    assert loaded_resources is not None
    assert loaded_resources.resource_name == "second_config"
    assert loaded_resources.walltime == 2000
    assert loaded_resources.cpus_per_node == 8


def test_save_load_config_with_all_fields(config):
    """Test saving and loading configuration with all possible fields"""
    # Create a Resources object with all fields populated
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
        "reuse_results": "true",  # Must be string for from_dict
    }
    resources.from_dict(resources_dict)

    # Save configuration
    filepath = Config.save_config(resources)
    assert os.path.exists(filepath)

    # Load configuration
    loaded_resources = Config.load_config()
    assert loaded_resources is not None

    # Verify all fields
    assert loaded_resources.resource_name == "full_config"
    assert loaded_resources.walltime == 86400
    assert loaded_resources.cpus_per_node == 32
    assert loaded_resources.nodes == 8
    assert loaded_resources.queue == "production"
    assert loaded_resources.memory == 32768
    assert loaded_resources.custom_requests == "feature=avx2,gpu=v100"
    assert loaded_resources.base_URI == "hpc.research.org"
    assert loaded_resources.port == 2222
    assert loaded_resources.username == "researcher"
    assert loaded_resources.basepath == "workspace/simstack"
    assert loaded_resources.queueing_system == "slurm"
    assert loaded_resources.sw_dir_on_resource == "/opt/software"
    assert loaded_resources.extra_config == "/etc/cluster/config.sh"
    assert loaded_resources.ssh_private_key == "/home/user/.ssh/id_rsa"
    assert loaded_resources.sge_pe == "mpi"
    assert loaded_resources.reuse_results is True


def test_save_config_creates_directory_if_not_exists(config):
    """Test that save_config creates the config directory if it doesn't exist"""
    # Remove the config directory
    import shutil
    config_dir = Config._dirs.user_config_dir
    if os.path.exists(config_dir):
        shutil.rmtree(config_dir)

    # Create and save configuration
    resources = Resources()
    resources.from_dict({"resource_name": "test", "walltime": 1000})
    filepath = Config.save_config(resources)

    # Verify directory and file were created
    assert os.path.exists(config_dir)
    assert os.path.exists(filepath)


def test_load_config_with_minimal_fields(config):
    """Test loading configuration with only minimal fields"""
    # Create a minimal Resources configuration
    resources = Resources()
    resources.from_dict({
        "resource_name": "minimal_config",
        "walltime": 100,
    })
    Config.save_config(resources)

    # Load configuration
    loaded_resources = Config.load_config()
    assert loaded_resources is not None
    assert loaded_resources.resource_name == "minimal_config"
    assert loaded_resources.walltime == 100

    # Other fields should have defaults
    assert loaded_resources.cpus_per_node == 1  # default
    assert loaded_resources.nodes == 1  # default
    assert loaded_resources.memory == 4096  # default


def test_get_resources_loads_config_on_first_call(config):
    """Test that get_resources loads config on first call"""
    # Clear the cached resources
    Config._resources = None

    # Create and save a configuration
    resources = Resources()
    resources.from_dict({
        "resource_name": "cached_config",
        "walltime": 5000,
        "cpus_per_node": 12,
    })
    Config.save_config(resources)

    # First call should load from file
    loaded_resources = Config.get_resources()
    assert loaded_resources is not None
    assert loaded_resources.resource_name == "cached_config"
    assert loaded_resources.walltime == 5000
    assert loaded_resources.cpus_per_node == 12


def test_get_resources_returns_cached_value(config):
    """Test that get_resources returns cached value on subsequent calls"""
    # Clear the cached resources
    Config._resources = None

    # Create and save a configuration
    resources = Resources()
    resources.from_dict({
        "resource_name": "cache_test",
        "walltime": 3000,
    })
    Config.save_config(resources)

    # First call loads from file
    first_call = Config.get_resources()
    assert first_call is not None

    # Modify the file to ensure second call doesn't reload
    different_resources = Resources()
    different_resources.from_dict({
        "resource_name": "different_config",
        "walltime": 9999,
    })
    Config.save_config(different_resources)

    # Second call should return cached value (not reload from file)
    second_call = Config.get_resources()
    assert second_call is not None
    assert second_call.resource_name == "cache_test"  # Still the original
    assert second_call.walltime == 3000  # Still the original


def test_get_resources_returns_none_if_no_config(config):
    """Test that get_resources returns None when no config file exists"""
    # Clear the cached resources
    Config._resources = None

    # Ensure no config file exists
    config_path = Config._get_config_file("resources.yml")
    if os.path.exists(config_path):
        os.remove(config_path)

    # Should return None
    resources = Config.get_resources()
    assert resources is None


def test_get_resources_after_save_config(config):
    """Test that get_resources can be used after save_config"""
    # Clear the cached resources
    Config._resources = None

    # Create and save a configuration
    resources = Resources()
    resources.from_dict({
        "resource_name": "save_then_get",
        "walltime": 7777,
        "memory": 20480,
    })
    Config.save_config(resources)

    # get_resources should load it
    loaded = Config.get_resources()
    assert loaded is not None
    assert loaded.resource_name == "save_then_get"
    assert loaded.walltime == 7777
    assert loaded.memory == 20480
