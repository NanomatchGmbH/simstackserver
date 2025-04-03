import logging
from pathlib import Path

from SimStackServer.Util.Exceptions import SecurityError
from SimStackServer.WaNo.MiscWaNoTypes import WaNoListEntry_from_folder_or_zip
from SimStackServer.WaNo.WaNoFactory import wano_constructor


class SecureModeGlobal:
    _secure_mode = False

    @classmethod
    def set_secure_mode(cls):
        cls._secure_mode = True

    @classmethod
    def get_secure_mode(cls):
        return cls._secure_mode


class SecureWaNos:
    _instance = None

    def __init__(self):
        self._wano_dict = {}
        self._init_wano_dict()

    def get_wano_by_name(self, wano_name: str):
        return self._wano_dict[wano_name]

    def _init_wano_dict(self):
        from SimStackServer.SimStackServerMain import SimStackServer

        appdirs = SimStackServer.get_appdirs()

        wano_config_directory = Path(appdirs.user_config_dir) / "secure_wanos"
        logging.info(f"Reading secure wanos from {wano_config_directory}")
        if not wano_config_directory.is_dir():
            raise SecurityError(
                f"SimStackSecure WaNo Directory {wano_config_directory} not found. Please create and fill with WaNos."
            )
        for wano_dir in wano_config_directory.iterdir():
            try:
                wle = WaNoListEntry_from_folder_or_zip(str(wano_dir))
                wano_model_root, _ = wano_constructor(wle, model_only=True)
                from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

                wano_model_root: WaNoModelRoot
                logging.info(f"Parsing secure wano {wano_model_root.name}")
                self._wano_dict[wano_model_root.name] = wano_model_root
            except Exception as _:
                logging.exception(f"Could not parse file as WaNo {wano_dir}")

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SecureWaNos()
        return cls._instance
