import os
import sys
import json
import tempfile
import shutil
import pytest
from unittest.mock import patch, MagicMock

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.Util.ClusterSettings import (
    get_clustersettings_filename_from_folder,
    remove_clustersettings_from_folder,
    get_cluster_settings_from_folder,
    save_cluster_settings_to_folder
)
from SimStackServer.WorkflowModel import Resources


class TestClusterSettings:
    
    def setup_method(self):
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        
        # Create sample cluster settings files
        self.create_sample_cluster_settings()
    
    def teardown_method(self):
        # Remove the temporary directory after tests
        shutil.rmtree(self.test_dir)
    
    def create_sample_cluster_settings(self):
        # Define sample data for test clusters
        clusters = {
            "cluster1": {
                "host": "host1.example.com",
                "port": 22,
                "username": "user1",
                "queue": "queue1",
                "scheduler": "slurm"
            },
            "cluster2": {
                "host": "host2.example.com",
                "port": 22,
                "username": "user2",
                "queue": "queue2",
                "scheduler": "pbs"
            }
        }
        
        # Create cluster settings files
        for cluster_name, settings in clusters.items():
            filename = os.path.join(self.test_dir, f"{cluster_name}.clustersettings")
            with open(filename, 'w') as f:
                json.dump(settings, f)
    
    def test_get_clustersettings_filename_from_folder(self):
        # Test getting filename for a cluster
        cluster_name = "testcluster"
        expected_filename = os.path.join(self.test_dir, "testcluster.clustersettings")
        
        filename = get_clustersettings_filename_from_folder(self.test_dir, cluster_name)
        assert filename == expected_filename
    
    def test_remove_clustersettings_from_folder(self):
        # Create a test file
        test_cluster = "removeme"
        test_file = os.path.join(self.test_dir, f"{test_cluster}.clustersettings")
        with open(test_file, 'w') as f:
            f.write("{}")
        
        # Verify file exists
        assert os.path.exists(test_file)
        
        # Remove the file
        remove_clustersettings_from_folder(self.test_dir, test_cluster)
        
        # Verify file no longer exists
        assert not os.path.exists(test_file)
    
    def test_remove_clustersettings_nonexistent(self):
        # Try to remove a non-existent file
        remove_clustersettings_from_folder(self.test_dir, "nonexistent")
        # Should not raise an exception
    
    def test_get_cluster_settings_from_folder(self):
        # Test getting all cluster settings
        settings = get_cluster_settings_from_folder(self.test_dir)
        
        # Verify both clusters were loaded
        assert len(settings) == 2
        assert "cluster1" in settings
        assert "cluster2" in settings
        
        # Verify content of settings
        assert settings["cluster1"]["host"] == "host1.example.com"
        assert settings["cluster1"]["scheduler"] == "slurm"
        assert settings["cluster2"]["host"] == "host2.example.com"
        assert settings["cluster2"]["scheduler"] == "pbs"
    
    def test_get_cluster_settings_empty_folder(self):
        # Create an empty folder
        empty_dir = tempfile.mkdtemp()
        try:
            # Test getting settings from empty folder
            settings = get_cluster_settings_from_folder(empty_dir)
            
            # Should return an empty dictionary
            assert settings == {}
        finally:
            shutil.rmtree(empty_dir)
    
    def test_save_cluster_settings_to_folder(self):
        # Create a new folder
        dest_dir = tempfile.mkdtemp()
        try:
            # Create sample resources
            resources = {
                "new_cluster1": Resources("new_cluster1", "new_host1.example.com", "new_user1", "new_queue1", "new_scheduler1"),
                "new_cluster2": Resources("new_cluster2", "new_host2.example.com", "new_user2", "new_queue2", "new_scheduler2")
            }
            
            # Save settings
            save_cluster_settings_to_folder(dest_dir, resources)
            
            # Verify files were created
            assert os.path.exists(os.path.join(dest_dir, "new_cluster1.clustersettings"))
            assert os.path.exists(os.path.join(dest_dir, "new_cluster2.clustersettings"))
            
            # Load settings and verify content
            loaded_settings = get_cluster_settings_from_folder(dest_dir)
            assert len(loaded_settings) == 2
            assert loaded_settings["new_cluster1"]["host"] == "new_host1.example.com"
            assert loaded_settings["new_cluster1"]["scheduler"] == "new_scheduler1"
            assert loaded_settings["new_cluster2"]["host"] == "new_host2.example.com"
            assert loaded_settings["new_cluster2"]["scheduler"] == "new_scheduler2"
        finally:
            shutil.rmtree(dest_dir)
    
    def test_save_cluster_settings_to_nonexistent_folder(self):
        # Create a temporary base directory
        base_dir = tempfile.mkdtemp()
        try:
            # Specify a non-existent subfolder
            dest_dir = os.path.join(base_dir, "nonexistent")
            
            # Create sample resources
            resources = {
                "test_cluster": Resources("test_cluster", "test_host.example.com", "test_user", "test_queue", "test_scheduler")
            }
            
            # Save settings - should create the directory
            save_cluster_settings_to_folder(dest_dir, resources)
            
            # Verify directory was created and file exists
            assert os.path.exists(dest_dir)
            assert os.path.exists(os.path.join(dest_dir, "test_cluster.clustersettings"))
        finally:
            shutil.rmtree(base_dir)