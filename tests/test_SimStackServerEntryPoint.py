import os
import pathlib
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Add SimStackServer to path

from SimStackServer.SimStackServerEntryPoint import (
    get_my_runtime,
    setup_pid,
    flush_port_and_password_to_stdout,
    InputFileError,
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
                    with pytest.raises(InputFileError):
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

    """
    def test_main_secure_mode(self):
        # Test main function with secure mode argument
        with patch("sys.argv", ["script.py", "--secure"]):
            with patch("SimStackServer.SimStackServerEntryPoint.setup_pid"):
                with patch(
                    "SimStackServer.SimStackServerEntryPoint.Config"
                ) as mock_config:
                    with patch(
                        "SimStackServer.SimStackServerEntryPoint.SecureModeGlobal"
                    ) as mock_secure:
                        with patch(
                            "SimStackServer.SimStackServerEntryPoint.SecureWaNos"
                        ):
                            with patch(
                                "SimStackServer.SimStackServerEntryPoint.SimStackServer"
                            ):
                                main()
                                mock_secure.set_secure_mode.assert_called_once_with(
                                    True
                                )


    def test_main_normal_mode(self):
        # Test main function in normal mode
        with patch("sys.argv", ["script.py"]):
            with patch("SimStackServer.SimStackServerEntryPoint.setup_pid"):
                with patch(
                    "SimStackServer.SimStackServerEntryPoint.Config"
                ) as mock_config:
                    with patch(
                        "SimStackServer.SimStackServerEntryPoint.SecureModeGlobal"
                    ) as mock_secure:
                        with patch(
                            "SimStackServer.SimStackServerEntryPoint.SimStackServer"
                        ):
                            main()
                            # Check secure mode was not set
                            mock_secure.set_secure_mode.assert_not_called()
    """
