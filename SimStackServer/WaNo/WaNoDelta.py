import pathlib

from SimStackServer.WaNo.read_wano_delta import read_wano_delta


class WaNoDelta:
    def __init__(self, folderpath: pathlib.Path):
        config_path = folderpath / "wano_configuration.json"
        self._delta_dict = read_wano_delta(config_path)
        self._metadata = self._delta_dict["metadata"]

    @property
    def delta_dict(self):
        return self._delta_dict

    @property
    def name(self):
        return self._metadata["name"]

    @property
    def metadata(self):
        return self._metadata

    @property
    def command_dict(self):
        return self._delta_dict["commands"]

    @property
    def value_dict(self):
        return self._delta_dict["values"]

