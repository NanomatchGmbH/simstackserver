import pathlib
import tempfile
from contextlib import nullcontext

import lockfile
import pytest
from unittest.mock import patch, MagicMock

from SimStackServer.SimStackServerEntryPoint import (
    get_my_runtime,
    setup_pid,
    flush_port_and_password_to_stdout,
    main,
)
from SimStackServer.Config import Config, ServerConfig


@pytest.fixture
def tmpdir() -> tempfile.TemporaryDirectory:
    with tempfile.TemporaryDirectory() as mydir:
        yield mydir


@pytest.fixture
def tmpfile(tmp_path):
    tmpfile = tmp_path / "tmp_file.dat"
    tmpfile.touch()
    yield tmpfile


class TestSimStackServerEntryPoint:
    def test_none(self):
        pass

    def test_get_my_runtime(self):
        with patch("sys.executable", "python3"):
            with patch("sys.argv", ["script.py", "arg1", "arg2"]):
                result = get_my_runtime()
                assert result == "python3 script.py"

    def test_setup_pid_new(self):
        mock_lock = MagicMock()
        with patch(
            "SimStackServer.Util.NoEnterPIDLockFile.NoEnterPIDLockFile",
            return_value=mock_lock,
        ):
            lock = setup_pid()
            assert lock == mock_lock

    def test_flush_port_and_password_to_stdout_no_config(self):
        """Test that flush raises FileNotFoundError when no config exists"""
        with tempfile.TemporaryDirectory() as config_tmpdir:
            mock_dirs = MagicMock()
            mock_dirs.user_config_dir = config_tmpdir
            mock_dirs.user_log_dir = f"{config_tmpdir}/log"
            original_dirs = Config._dirs
            Config._dirs = mock_dirs
            Config._server_config = None
            try:
                with pytest.raises(FileNotFoundError):
                    flush_port_and_password_to_stdout()
            finally:
                Config._dirs = original_dirs
                Config._server_config = None

    def test_flush_port_and_password_to_stdout_with_config(self, capsys):
        """Test that flush prints port/pass when config exists"""
        with tempfile.TemporaryDirectory() as config_tmpdir:
            mock_dirs = MagicMock()
            mock_dirs.user_config_dir = config_tmpdir
            mock_dirs.user_log_dir = f"{config_tmpdir}/log"
            original_dirs = Config._dirs
            Config._dirs = mock_dirs
            Config._server_config = None
            try:
                sc = ServerConfig(
                    rest_port=12345,
                    client_secret="mypass",
                    server_version="SERVER,1.0,REST,1.0",
                )
                Config.save_server_config(sc)
                Config._server_config = None  # clear cache

                flush_port_and_password_to_stdout()
                captured = capsys.readouterr()
                assert "Port Pass 12345 mypass" in captured.out
            finally:
                Config._dirs = original_dirs
                Config._server_config = None

    def test_main_already_running(self, tmpdir, caplog):
        """Test that main exits cleanly when server is already running"""
        tmppath = pathlib.Path(tmpdir)
        mock_dirs = MagicMock()
        mock_dirs.user_config_dir = tmpdir
        mock_dirs.user_log_dir = str(tmppath / "logs")
        original_dirs = Config._dirs
        Config._dirs = mock_dirs
        Config._server_config = None

        try:
            # Create server config so flush works
            (tmppath / "logs").mkdir(exist_ok=True)
            sc = ServerConfig(
                rest_port=12345,
                client_secret="mypass",
                server_version="SERVER,1.0,REST,1.0",
            )
            Config.save_server_config(sc)

            mock_lock = MagicMock()
            mock_lock.acquire.return_value = None

            with patch("sys.stdout"), patch(
                "daemon.DaemonContext", return_value=nullcontext()
            ), patch(
                "SimStackServer.SimStackServerMain.SimStackServer.get_appdirs",
                return_value=MagicMock(
                    user_config_dir=tmpdir, user_log_dir=str(tmppath / "logs")
                ),
            ):
                # Simulate server already running via register_pidfile
                mock_server_pid = MagicMock()
                mock_server_pid.acquire.side_effect = lockfile.AlreadyLocked
                with patch(
                    "SimStackServer.SimStackServerMain.SimStackServer.register_pidfile",
                    return_value=mock_server_pid,
                ), patch("sys.exit", side_effect=SystemExit) as mock_exit:
                    with pytest.raises(SystemExit):
                        main()
                    mock_exit.assert_called_once_with(0)
        finally:
            Config._dirs = original_dirs
            Config._server_config = None

    def test_main_locked_no_config(self, tmpdir):
        """Test that main exits with error when locked but no config exists"""
        tmppath = pathlib.Path(tmpdir)
        mock_dirs = MagicMock()
        mock_dirs.user_config_dir = tmpdir
        mock_dirs.user_log_dir = str(tmppath / "logs")
        original_dirs = Config._dirs
        Config._dirs = mock_dirs
        Config._server_config = None

        try:
            mock_pid = MagicMock()
            mock_pid.acquire.side_effect = lockfile.AlreadyLocked

            with patch("sys.stdout"), patch(
                "SimStackServer.SimStackServerMain.SimStackServer.get_appdirs",
                return_value=MagicMock(
                    user_config_dir=tmpdir, user_log_dir=str(tmppath / "logs")
                ),
            ), patch(
                "SimStackServer.SimStackServerEntryPoint.setup_pid",
                return_value=mock_pid,
            ), patch("sys.exit", side_effect=SystemExit) as mock_exit:
                with pytest.raises(SystemExit):
                    main()
                mock_exit.assert_called_once_with(1)
        finally:
            Config._dirs = original_dirs
            Config._server_config = None
