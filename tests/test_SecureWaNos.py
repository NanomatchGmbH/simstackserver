import os
import sys
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from SimStackServer.SecureWaNos import SecureModeGlobal, SecureWaNos


class TestSecureModeGlobal:
    
    def setup_method(self):
        # Reset secure mode for each test
        SecureModeGlobal._secure_mode = False
    
    def test_secure_mode_default(self):
        # Test default secure mode is False
        assert SecureModeGlobal.get_secure_mode() is False
    
    def test_set_secure_mode(self):
        # Test setting secure mode
        SecureModeGlobal.set_secure_mode(True)
        assert SecureModeGlobal.get_secure_mode() is True
        
        # Test changing it back
        SecureModeGlobal.set_secure_mode(False)
        assert SecureModeGlobal.get_secure_mode() is False


class TestSecureWaNos:
    
    def setup_method(self):
        # Reset singleton state
        SecureWaNos._instance = None
        
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        
        # Create a mock WaNo file
        self.setup_test_wanos()
    
    def teardown_method(self):
        # Clean up the temporary directory
        shutil.rmtree(self.test_dir)
    
    def setup_test_wanos(self):
        # Create a test WaNo XML file
        wano_xml = """<?xml version="1.0" encoding="UTF-8"?>
<WaNoTemplate>
    <WaNoMeta>
        <WaNoName>TestWaNo</WaNoName>
        <WaNoVersion>1.0</WaNoVersion>
        <WaNoDescription>Test WaNo for unit tests</WaNoDescription>
    </WaNoMeta>
    <WaNoRoot>
        <WaNoFloat name="testFloat" description="Test float parameter">1.0</WaNoFloat>
    </WaNoRoot>
</WaNoTemplate>
"""
        # Create test WaNo directory
        test_wano_dir = os.path.join(self.test_dir, "TestWaNo")
        os.makedirs(test_wano_dir, exist_ok=True)
        
        # Create test WaNo file
        with open(os.path.join(test_wano_dir, "TestWaNo.xml"), "w") as f:
            f.write(wano_xml)
    
    def test_singleton_pattern(self):
        # Test that instances are the same
        with patch('SimStackServer.SecureWaNos.Config') as mock_config:
            mock_config.secure_wanos_path = self.test_dir
            
            instance1 = SecureWaNos.get_instance()
            instance2 = SecureWaNos.get_instance()
            
            assert instance1 is instance2
    
    def test_secure_wanos_loading(self):
        # Test loading WaNos from config directory
        with patch('SimStackServer.SecureWaNos.Config') as mock_config:
            mock_config.secure_wanos_path = self.test_dir
            
            secure_wanos = SecureWaNos.get_instance()
            
            # Test that our test WaNo was loaded
            loaded_wanos = secure_wanos.wanos
            assert "TestWaNo" in loaded_wanos
            assert os.path.join(self.test_dir, "TestWaNo") in loaded_wanos.values()
    
    def test_get_wano_by_name(self):
        # Test getting a WaNo by name
        with patch('SimStackServer.SecureWaNos.Config') as mock_config:
            mock_config.secure_wanos_path = self.test_dir
            
            secure_wanos = SecureWaNos.get_instance()
            
            # Test getting an existing WaNo
            path = secure_wanos.get_wano_by_name("TestWaNo")
            assert path == os.path.join(self.test_dir, "TestWaNo")
            
            # Test getting a non-existent WaNo
            path = secure_wanos.get_wano_by_name("NonExistentWaNo")
            assert path is None
    
    def test_nonexistent_config_directory(self):
        # Test behavior when config directory doesn't exist
        with patch('SimStackServer.SecureWaNos.Config') as mock_config:
            mock_config.secure_wanos_path = os.path.join(self.test_dir, "nonexistent")
            
            secure_wanos = SecureWaNos.get_instance()
            
            # WaNos dictionary should be empty
            assert secure_wanos.wanos == {}