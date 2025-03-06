import os
import sys
import pytest
import tempfile
import shutil
import hashlib
import json
from unittest.mock import patch, MagicMock, mock_open

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.Util.ResultRepo import (
    compute_files_hash,
    list_files,
    compute_dir_hash,
    compute_input_hash,
    load_results,
    store_results
)


class TestResultRepo:
    
    def setup_method(self):
        # Create temporary directories for testing
        self.test_dir = tempfile.mkdtemp()
        self.results_dir = tempfile.mkdtemp()
        
        # Create sample files
        self.create_sample_files()
    
    def teardown_method(self):
        # Clean up temporary directories
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.results_dir)
    
    def create_sample_files(self):
        # Create a directory structure with sample files
        os.makedirs(os.path.join(self.test_dir, "subdir1"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "subdir2"), exist_ok=True)
        
        # Create sample files with content
        with open(os.path.join(self.test_dir, "file1.txt"), "w") as f:
            f.write("Content of file 1")
        
        with open(os.path.join(self.test_dir, "subdir1", "file2.txt"), "w") as f:
            f.write("Content of file 2")
        
        with open(os.path.join(self.test_dir, "subdir2", "file3.txt"), "w") as f:
            f.write("Content of file 3")
    
    def test_list_files(self):
        # Test listing files in a directory
        file_list = list_files(self.test_dir)
        
        # Verify all files are listed
        assert len(file_list) == 3
        assert os.path.join(self.test_dir, "file1.txt") in file_list
        assert os.path.join(self.test_dir, "subdir1", "file2.txt") in file_list
        assert os.path.join(self.test_dir, "subdir2", "file3.txt") in file_list
    
    def test_compute_files_hash(self):
        # Test hashing a list of files
        file_list = [
            os.path.join(self.test_dir, "file1.txt"),
            os.path.join(self.test_dir, "subdir1", "file2.txt")
        ]
        
        # Compute hash
        file_hash = compute_files_hash(file_list)
        
        # Verify it's a non-empty string
        assert isinstance(file_hash, str)
        assert len(file_hash) > 0
        
        # Verify it's deterministic (same files should produce same hash)
        second_hash = compute_files_hash(file_list)
        assert file_hash == second_hash
        
        # Verify different files produce different hashes
        different_file_list = [
            os.path.join(self.test_dir, "file1.txt"),
            os.path.join(self.test_dir, "subdir2", "file3.txt")
        ]
        different_hash = compute_files_hash(different_file_list)
        assert file_hash != different_hash
    
    def test_compute_dir_hash(self):
        # Test hashing a directory
        dir_hash = compute_dir_hash(self.test_dir)
        
        # Verify it's a non-empty string
        assert isinstance(dir_hash, str)
        assert len(dir_hash) > 0
        
        # Verify it's deterministic (same directory should produce same hash)
        second_hash = compute_dir_hash(self.test_dir)
        assert dir_hash == second_hash
        
        # Modify a file and verify hash changes
        with open(os.path.join(self.test_dir, "file1.txt"), "w") as f:
            f.write("Modified content")
        
        modified_hash = compute_dir_hash(self.test_dir)
        assert dir_hash != modified_hash
    
    def test_compute_input_hash(self):
        # Create a mock execution module
        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1", "param2": 123}
        mock_module.get_inpath.return_value = self.test_dir
        
        # Test computing input hash
        input_hash = compute_input_hash(mock_module)
        
        # Verify it's a non-empty string
        assert isinstance(input_hash, str)
        assert len(input_hash) > 0
        
        # Verify it's deterministic
        second_hash = compute_input_hash(mock_module)
        assert input_hash == second_hash
        
        # Change configuration and verify hash changes
        mock_module.get_configuration.return_value = {"param1": "different", "param2": 456}
        different_hash = compute_input_hash(mock_module)
        assert input_hash != different_hash
    
    @patch('SimStackServer.Util.ResultRepo.sqlalchemy')
    @patch('SimStackServer.Util.ResultRepo.os.path.exists')
    def test_load_results_not_found(self, mock_exists, mock_sqlalchemy):
        # Mock database engine and query result
        mock_engine = MagicMock()
        mock_sqlalchemy.create_engine.return_value = mock_engine
        
        # Configure connection and query to return no results
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []
        
        # Mock execution module
        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1"}
        mock_module.get_inpath.return_value = self.test_dir
        
        # Load results (should not find any)
        result = load_results(mock_module)
        
        # Verify no results were found
        assert result is None
    
    @patch('SimStackServer.Util.ResultRepo.sqlalchemy')
    @patch('SimStackServer.Util.ResultRepo.os.path.exists')
    @patch('SimStackServer.Util.ResultRepo.shutil.copytree')
    def test_load_results_found(self, mock_copytree, mock_exists, mock_sqlalchemy):
        # Mock database engine and query result
        mock_engine = MagicMock()
        mock_sqlalchemy.create_engine.return_value = mock_engine
        
        # Configure connection and query to return a result
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn
        
        # Mock a successful result with source directory
        source_dir = os.path.join(self.results_dir, "results123")
        mock_conn.execute.return_value.fetchall.return_value = [(source_dir,)]
        
        # Mock source directory exists
        mock_exists.return_value = True
        
        # Mock execution module
        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1"}
        mock_module.get_inpath.return_value = self.test_dir
        mock_module.get_outpath.return_value = os.path.join(self.test_dir, "output")
        
        # Load results
        result = load_results(mock_module)
        
        # Verify results were found and copying was attempted
        assert result == source_dir
        mock_copytree.assert_called_once()
    
    @patch('SimStackServer.Util.ResultRepo.sqlalchemy')
    @patch('SimStackServer.Util.ResultRepo.os.path.exists')
    @patch('SimStackServer.Util.ResultRepo.shutil.copytree')
    def test_store_results(self, mock_copytree, mock_exists, mock_sqlalchemy):
        # Mock database engine and create tables
        mock_engine = MagicMock()
        mock_sqlalchemy.create_engine.return_value = mock_engine
        
        # Mock the metadata and table
        mock_metadata = MagicMock()
        mock_sqlalchemy.MetaData.return_value = mock_metadata
        
        # Mock Table and Column
        mock_sqlalchemy.Table = MagicMock()
        mock_sqlalchemy.Column = MagicMock()
        mock_sqlalchemy.String = MagicMock()
        
        # Configure connection for insert
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn
        
        # Mock execution module
        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1"}
        mock_module.get_inpath.return_value = self.test_dir
        mock_module.get_outpath.return_value = os.path.join(self.test_dir, "output")
        
        # Make the test directories exist
        os.makedirs(os.path.join(self.test_dir, "output"), exist_ok=True)
        mock_exists.return_value = True
        
        # Store results
        with patch('builtins.open', mock_open()):
            result_dir = store_results(mock_module)
        
        # Verify results were stored and operations performed
        assert result_dir is not None
        mock_copytree.assert_called_once()
        # Verify that insert was called
        assert mock_conn.execute.call_count >= 1