import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem


class TestInternalBatchSystem:
    
    def setup_method(self):
        # Reset the singleton state before each test
        InternalBatchSystem._processfarm = None
        InternalBatchSystem._processfarm_thread = None
    
    def test_init(self):
        # Test that initialization doesn't do anything
        batch_system = InternalBatchSystem()
        assert InternalBatchSystem._processfarm is None
        assert InternalBatchSystem._processfarm_thread is None
    
    @patch('threadfarm.processfarm.ProcessFarm')
    def test_get_instance_first_call(self, mock_processfarm_class):
        # Create mock process farm instance
        mock_processfarm = MagicMock()
        mock_processfarm_class.return_value = mock_processfarm
        
        # Create mock thread
        mock_thread = MagicMock()
        mock_processfarm.start_processfarm_as_thread.return_value = mock_thread
        
        # Call get_instance for the first time
        processfarm, thread = InternalBatchSystem.get_instance()
        
        # Assert the class variables were set correctly
        assert InternalBatchSystem._processfarm == mock_processfarm
        assert InternalBatchSystem._processfarm_thread == mock_thread
        assert processfarm == mock_processfarm
        assert thread == mock_thread
        
        # Assert the process farm was created and started
        mock_processfarm_class.assert_called_once()
        mock_processfarm.start_processfarm_as_thread.assert_called_once()
    
    @patch('threadfarm.processfarm.ProcessFarm')
    def test_get_instance_subsequent_calls(self, mock_processfarm_class):
        # Create mock process farm instance
        mock_processfarm = MagicMock()
        mock_processfarm_class.return_value = mock_processfarm
        
        # Create mock thread
        mock_thread = MagicMock()
        mock_processfarm.start_processfarm_as_thread.return_value = mock_thread
        
        # Call get_instance for the first time
        processfarm1, thread1 = InternalBatchSystem.get_instance()
        
        # Reset the mock to check if it's called again
        mock_processfarm_class.reset_mock()
        mock_processfarm.start_processfarm_as_thread.reset_mock()
        
        # Call get_instance for the second time
        processfarm2, thread2 = InternalBatchSystem.get_instance()
        
        # Assert the same instances are returned
        assert processfarm1 == processfarm2
        assert thread1 == thread2
        
        # Assert the process farm was not created or started again
        mock_processfarm_class.assert_not_called()
        mock_processfarm.start_processfarm_as_thread.assert_not_called()