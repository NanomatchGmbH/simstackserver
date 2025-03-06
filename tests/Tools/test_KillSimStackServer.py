import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.Tools.KillSimStackServer import main


class TestKillSimStackServer:
    
    @patch('os.fork')
    def test_main_parent_process(self, mock_fork):
        # Simulate parent process
        mock_fork.return_value = 42  # Non-zero PID means parent
        
        # Call the main function
        main()
        
        # Parent process should just return
        mock_fork.assert_called_once()
    
    @patch('os.fork')
    @patch('os._exit')
    @patch('os.geteuid')
    @patch('subprocess.call')
    def test_main_child_process_as_root(self, mock_call, mock_geteuid, mock_exit, mock_fork):
        # Simulate child process
        mock_fork.return_value = 0  # Zero PID means child
        
        # Simulate running as root
        mock_geteuid.return_value = 0
        
        # Call the main function
        main()
        
        # Verify proper script was executed with correct parameters
        script = "for pid in $(pgrep -f SimStackServerMain.py); do kill -15 $pid; done; sleep 20; for pid in $(pgrep -f SimStackServerMain.py); do kill -9 $pid; done;"
        mock_call.assert_called_once_with(script, shell=True)
        
        # Verify process exited
        mock_exit.assert_called_once_with(0)
    
    @patch('os.fork')
    @patch('os._exit')
    @patch('os.geteuid')
    @patch('subprocess.call')
    def test_main_child_process_as_user(self, mock_call, mock_geteuid, mock_exit, mock_fork):
        # Simulate child process
        mock_fork.return_value = 0  # Zero PID means child
        
        # Simulate running as non-root user
        mock_geteuid.return_value = 1000
        
        # Call the main function
        main()
        
        # Verify proper script was executed with correct parameters - note user-specific version
        script = "for pid in $(pgrep -u $USER -f SimStackServerMain.py); do kill -15 $pid; done; sleep 20; for pid in $(pgrep -u $USER -f SimStackServerMain.py); do kill -9 $pid; done;"
        mock_call.assert_called_once_with(script, shell=True)
        
        # Verify process exited
        mock_exit.assert_called_once_with(0)
    
    @patch('os.fork')
    @patch('os._exit')
    @patch('os.geteuid')
    @patch('subprocess.call')
    def test_main_child_process_error(self, mock_call, mock_geteuid, mock_exit, mock_fork):
        # Simulate child process
        mock_fork.return_value = 0  # Zero PID means child
        
        # Simulate running as non-root user
        mock_geteuid.return_value = 1000
        
        # Simulate error in subprocess call
        mock_call.side_effect = Exception("Command failed")
        
        # Call the main function
        main()
        
        # Verify process exited with error code
        mock_exit.assert_called_once_with(1)