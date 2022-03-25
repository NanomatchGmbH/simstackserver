import os
from pathlib import Path

from SimStackServer.Util.ClusterSettings import get_cluster_settings_from_folder, save_cluster_settings_to_folder, \
    remove_clustersettings_from_folder


class ClusterSettingsProvider:
    _instance = None

    def __init__(self):
        self._settings_container = {}
        self._parse_settings()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = ClusterSettingsProvider()
        return cls._instance

    def _get_settings_folder(self) -> Path:
        import appdirs
        ucd = Path(appdirs.user_config_dir(appname="SimStack", appauthor="Nanomatch", roaming=False))
        clusterconfig = ucd/"ClusterSettings"
        os.makedirs(clusterconfig, exist_ok=True)
        return clusterconfig

    @classmethod
    def get_registries(cls):
        return cls.get_instance()._settings_container

    @classmethod
    def remove_resource(cls, resource_name: str) -> None:
        instance = cls.get_instance()
        sc = instance._settings_container
        folder = instance._get_settings_folder()
        remove_clustersettings_from_folder(folder, resource_name)
        if resource_name in sc:
            del sc[resource_name]

    def _parse_settings(self):
        self._settings_container = get_cluster_settings_from_folder(self._get_settings_folder())

    def write_settings(self):
        save_cluster_settings_to_folder(self._get_settings_folder(),self._settings_container)
