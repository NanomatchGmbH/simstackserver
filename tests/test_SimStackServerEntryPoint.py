import os
import pathlib
import tempfile
from contextlib import nullcontext

import lockfile
import pytest
from unittest.mock import patch, MagicMock
import logging

# Add SimStackServer to path

from SimStackServer.SimStackServerEntryPoint import (
    get_my_runtime,
    setup_pid,
    flush_port_and_password_to_stdout,
    InputFileError,
    main,
)


@pytest.fixture
def tmpdir() -> tempfile.TemporaryDirectory:
    with tempfile.TemporaryDirectory() as mydir:
        yield mydir


@pytest.fixture
def tmpfile(tmp_path):
    tmpfile = tmp_path / "tmp_file.dat"

    # Just touching the file ensures it exists; or you can open/write to it.
    tmpfile.touch()

    yield tmpfile


class TestSimStackServerEntryPoint:
    def test_none(self):
        pass

    def test_get_my_runtime(self):
        # Test the runtime command generation
        with patch("sys.executable", "python3"):
            with patch("sys.argv", ["script.py", "arg1", "arg2"]):
                result = get_my_runtime()
                assert result == "python3 script.py"

    def test_setup_pid_new(self):
        # Test successful PID file setup
        mock_lock = MagicMock()
        with patch(
            "SimStackServer.Util.NoEnterPIDLockFile.NoEnterPIDLockFile",
            return_value=mock_lock,
        ):
            lock = setup_pid()
            assert lock == mock_lock

    def test_flush_port_and_password_to_stdout(self, tmpdir, capsys):
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"port=12345\npassword=test_password\n")
            temp_file_path = temp_file.name

        try:
            # Patch the functions to use our test file
            mock_zmq = MagicMock()
            mock_zmq.zmp_version.return_value = "1.0.2"
            with patch(
                "SimStackServer.SimStackServerEntryPoint.zmq", return_value=mock_zmq
            ):
                with patch("sys.stdout") as mock_stdout:
                    appdir = MagicMock()
                    appdir.user_config_dir = tmpdir

                    # file does not exist, go into time.sleep()
                    with pytest.raises(FileNotFoundError):
                        flush_port_and_password_to_stdout(
                            appdir, other_process_setup=True
                        )

                    tmpfile = pathlib.Path(tmpdir) / "portconfig.txt"
                    tmpfile.touch()
                    with pytest.raises(InputFileError):
                        flush_port_and_password_to_stdout(appdir)

                    with open(tmpfile, "w") as of:
                        of.write("Name name2 12345 mypass some")

                    # Check that stdout received the expected data
                    flush_port_and_password_to_stdout(appdir)

                    write_calls = [
                        call[0][0] for call in mock_stdout.write.call_args_list
                    ]
                    assert write_calls[0].startswith("Port Pass 12345 mypass")

        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)

    def test_main_secure_mode(self, tmpdir, caplog, capsys):
        tmppath = pathlib.Path(tmpdir)
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = None
        with patch(
            "SimStackServer.Util.NoEnterPIDLockFile.NoEnterPIDLockFile",
            return_value=mock_lock,
        ):
            mock_zmq = MagicMock()
            mock_zmq.zmp_version.return_value = "1.0.2"
            appdir = MagicMock()
            appdir.user_config_dir = tmpdir
            tmpfile = tmppath / "portconfig.txt"
            appdir.user_log_dir = tmppath / "logs"

            with patch(
                "SimStackServer.SimStackServerEntryPoint.zmq", return_value=mock_zmq
            ), patch("sys.stdout"), patch(
                "daemon.DaemonContext", return_value=nullcontext()
            ), patch(
                "SimStackServer.SimStackServerMain.SimStackServer.get_appdirs",
                return_value=appdir,
            ) as mock_get_appdirs:
                mock_pid = MagicMock()
                mock_pid.acquire.side_effect = lockfile.AlreadyLocked
                with patch(
                    "SimStackServer.SimStackServerEntryPoint.setup_pid",
                    return_value=mock_pid,
                ), patch("sys.exit") as mock_exit:
                    with pytest.raises(FileNotFoundError):
                        main()
                        output = capsys.readouterr()
                        assert "App Lock was found" in output
                        assert "Please check logs" in output
                        mock_exit.assert_called_once_with(0)

                os.mkdir(appdir.user_log_dir)
                tmpfile.touch()
                with caplog.at_level(logging.DEBUG, logger="Startup"):
                    main()
                    mock_get_appdirs.assert_called()
                    mock_lock.acquire.assert_called()

                with open(tmpfile, "w") as of:
                    of.write("Name name2 12345 mypass some")

                mock_pid = MagicMock()
                mock_pid.acquire.side_effect = lockfile.AlreadyLocked

                with patch(
                    "SimStackServer.SimStackServerEntryPoint.SimStackServer.register_pidfile",
                    return_value=mock_pid,
                ), patch("sys.exit", side_effect=SystemExit) as mock_exit:
                    with pytest.raises(SystemExit):
                        main()
                        # Assert that sys.exit was called with 0.
                    mock_exit.assert_called_once_with(0)
