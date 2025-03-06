from unittest.mock import patch

from SimStackServer.RemoteServerManager import RemoteServerManager
from SimStackServer.WorkflowModel import Resources


class TestRemoteServerManager:
    def setup_method(self):
        # Reset the singleton instance for each test
        RemoteServerManager._instance = None
        RemoteServerManager._cluster_managers = {}

    def test_singleton_pattern(self):
        # Test that instances are the same
        instance1 = RemoteServerManager.get_instance()
        instance2 = RemoteServerManager.get_instance()

        assert instance1 is instance2

    def test_get_key_from_resource(self):
        # Test key generation
        resource = Resources(
            resource_name="test_cluster",
            base_URI="test_host.example.com",
            username="test_user",
            queue="test_queue",
            queueing_system="test_scheduler",
            port=2222,
        )

        manager = RemoteServerManager.get_instance()
        key = manager._get_key_from_resource(resource)

        assert key == "test_user@test_host.example.com:2222"

    @patch("SimStackServer.RemoteServerManager.ClusterManager")
    def test_server_from_resource(self, _):
        # Test creating a new cluster manager
        resource = Resources(
            resource_name="test_cluster",
            base_URI="test_host.example.com",
            username="test_user",
            queue="test_queue",
            queueing_system="test_scheduler",
            port=2222,
        )
        inst = RemoteServerManager.get_instance()
        inst.server_from_resource(resource)
        assert "test_user@test_host.example.com:2222" in inst._other_servers
