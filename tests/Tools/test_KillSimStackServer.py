import os
import sys
from unittest.mock import patch, MagicMock
from SimStackServer.Tools.KillSimStackServer import main

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestKillSimStackServer:
    @patch("os.fork")
    @patch("os.geteuid")
    @patch("SimStackServer.Tools.KillSimStackServer.subprocess.Popen")
    def test_main_parent_process(
        self, mock_popen, mock_geteuid, mock_fork
    ):
        # Simulate parent process
        mock_fork.return_value = 42  # Non-zero PID means parent

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = None
        mock_popen.return_value = mock_proc
        # Simulate running as root
        mock_geteuid.return_value = 0

        # Call the main function
        main()

        # Parent process should just return
        mock_fork.assert_called_once()
        mock_popen.assert_not_called()
        mock_proc.communicate.assert_not_called()

    @patch("os.fork")
    @patch("os.geteuid")
    @patch("SimStackServer.Tools.KillSimStackServer.subprocess.Popen")
    def test_main_child_process_as_root(
        self, mock_popen, mock_geteuid, mock_fork
    ):
        # Simulate child process
        mock_fork.return_value = 0  # Zero PID means child

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = None
        mock_popen.return_value = mock_proc
        # Simulate running as root
        mock_geteuid.return_value = 0

        # Call the main function
        main()

        # Verify proper script was executed with correct parameters
        mock_popen.assert_called_once()
        mock_proc.communicate.assert_called_once()


