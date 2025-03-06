import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open

# Add SimStackServer to path

from SimStackServer.SimStackServerEntryPoint import get_my_runtime, setup_pid, flush_port_and_password_to_stdout, main


class TestSimStackServerEntryPoint:
    
    def test_get_my_runtime(self):
        # Test the runtime command generation
        with patch('sys.executable', 'python3'):
            with patch('sys.argv', ['script.py', 'arg1', 'arg2']):
                result = get_my_runtime()
                assert result == 'python3 script.py arg1 arg2'
    
    def test_setup_pid_new(self):
        # Test successful PID file setup
        mock_lock = MagicMock()
        with patch('SimStackServer.SimStackServerEntryPoint.NoEnterPIDLockFile', return_value=mock_lock):
            with patch('os.makedirs'):
                with patch('SimStackServer.SimStackServerEntryPoint.piddir', '/tmp/test_dir'):
                    lock = setup_pid()
                    assert lock == mock_lock
                    mock_lock.acquire.assert_called_once()
    
    def test_setup_pid_exists(self):
        # Test when PID file exists and can't be acquired
        mock_lock = MagicMock()
        mock_lock.acquire.side_effect = Exception("Already running")
        
        with patch('SimStackServer.SimStackServerEntryPoint.NoEnterPIDLockFile', return_value=mock_lock):
            with patch('os.makedirs'):
                with patch('SimStackServer.SimStackServerEntryPoint.piddir', '/tmp/test_dir'):
                    with pytest.raises(SystemExit):
                        setup_pid()
    
    def test_flush_port_and_password_to_stdout(self):
        # Create a temporary file for testing
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"port=12345\npassword=test_password\n")
            temp_file_path = temp_file.name
        
        try:
            # Patch the functions to use our test file
            with patch('SimStackServer.SimStackServerEntryPoint.zmq_info_path', temp_file_path):
                with patch('sys.stdout') as mock_stdout:
                    flush_port_and_password_to_stdout()
                    
                    # Check that stdout received the expected data
                    write_calls = [call[0][0] for call in mock_stdout.write.call_args_list]
                    assert 'port=12345' in write_calls
                    assert 'password=test_password' in write_calls
        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)
    
    def test_main_secure_mode(self):
        # Test main function with secure mode argument
        with patch('sys.argv', ['script.py', '--secure']):
            with patch('SimStackServer.SimStackServerEntryPoint.setup_pid'):
                with patch('SimStackServer.SimStackServerEntryPoint.Config') as mock_config:
                    with patch('SimStackServer.SimStackServerEntryPoint.SecureModeGlobal') as mock_secure:
                        with patch('SimStackServer.SimStackServerEntryPoint.SecureWaNos'):
                            with patch('SimStackServer.SimStackServerEntryPoint.SimStackServer'):
                                main()
                                mock_secure.set_secure_mode.assert_called_once_with(True)
    
    def test_main_normal_mode(self):
        # Test main function in normal mode
        with patch('sys.argv', ['script.py']):
            with patch('SimStackServer.SimStackServerEntryPoint.setup_pid'):
                with patch('SimStackServer.SimStackServerEntryPoint.Config') as mock_config:
                    with patch('SimStackServer.SimStackServerEntryPoint.SecureModeGlobal') as mock_secure:
                        with patch('SimStackServer.SimStackServerEntryPoint.SimStackServer'):
                            main()
                            # Check secure mode was not set
                            mock_secure.set_secure_mode.assert_not_called()