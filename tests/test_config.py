from unittest.mock import patch, MagicMock

import tempfile

import pytest

from SimStackServer.Config import Config


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
