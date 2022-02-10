from SimStackServer import ClusterManager


class RemoteServerManager:
    def __init__(self):
        self._other_servers = {}

    def _get_key_from_resource(self, resource) -> str:
        from SimStackServer.WorkflowModel import Resources
        resource: Resources
        return f"{resource.username}@{resource.base_URI}:{resource.port}"

    def server_from_resource(self, resource):
        from SimStackServer.WorkflowModel import Resources
        resource:Resources
        key = self._get_key_from_resource(resource)
        if not key in self._other_servers:
            cm = ClusterManager.ClusterManager(url=resource.base_URI,
                                               port=resource.port,
                                               calculation_basepath=resource.basepath,
                                               user=resource.username,
                                               sshprivatekey=resource.ssh_private_key,
                                               extra_config=resource.extra_config,
                                               queueing_system=resource.queueing_system,
                                               default_queue=resource.queue,
                                               software_directory=resource.sw_dir_on_resource)
            self._other_servers[key] = cm
        return self._other_servers[key]