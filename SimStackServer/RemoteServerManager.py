from SimStackServer.ClusterManager import ClusterManager

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from SimStackServer.WorkflowModel import Resources



class RemoteServerManager:
    instance = None

    def __init__(self):
        self._other_servers = {}

    @classmethod
    def get_instance(cls):
        if cls.instance is None:
            cls.instance = RemoteServerManager()
        return cls.instance

    def _get_key_from_resource(self, resource: 'Resources') -> str:
        return f"{resource.username}@{resource.base_URI}:{resource.port}"

    def server_from_resource(self, resource: 'Resources'):
        key = self._get_key_from_resource(resource)
        if key not in self._other_servers:
            cm = ClusterManager(
                url=resource.base_URI,
                port=resource.port,
                calculation_basepath=resource.basepath,
                user=resource.username,
                sshprivatekey=resource.ssh_private_key,
                extra_config=resource.extra_config,
                queueing_system=resource.queueing_system,
                default_queue=resource.queue,
                software_directory=resource.sw_dir_on_resource,
            )
            self._other_servers[key] = cm
        return self._other_servers[key]
