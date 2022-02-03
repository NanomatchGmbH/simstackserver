from SimStackServer import ClusterManager
from WorkflowModel import Resources

class RemoteServerManager:
    def __init__(self):
        self._other_servers = {}

    def _get_key_from_resource(self, resource : Resources) -> str:
        key = f"{resource.host}"

    def add_server_from_resource(self, resource: Resources):
        key = self._get_key_from_resource(resource)
        cm = ClusterManager