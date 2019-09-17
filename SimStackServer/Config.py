from collections import namedtuple

from appdirs import AppDirs
from os import path
import json

from SimStackServer.Util.FileUtilities import mkdir_p


"""
Server entry, self explanatorty
    calculation_basepath is the path on the server, where calculations are carried out and stored.
    queueing_system: torque, lsf, slurm
"""
ServerEntry = namedtuple('ServerEntry',["name", "username", "url", "port", "calculation_basepath", "queueing_system"])

class Config(object):
    """
    Config handles config serialization for all server entries
    """
    _dirs = AppDirs(appname = "SimStackServer",
                               appauthor="Nanomatch",
                               roaming = False)
    _config_filename = "config.json"
    def __init__(self):
        self._servers = {}
        mkdir_p(self._dirs.user_config_dir)
        if path.isfile(self.filename()):
            self._parse()


    @classmethod
    def backup_config(cls):
        """
        Moves the existing config to a temporary backup file.
        This should only be used in unit testing and is therefore not unit tested itself
        """
        bakfile = cls.filename() + ".bak"
        if path.isfile(cls.filename()):
            from shutil import move
            move(cls.filename(),bakfile)

    @classmethod
    def restore_config(cls):
        """
        Moves the existing backup back to the previous config
        This should only be used in unit testing and is therefore not unit tested itself
        """
        bakfile = cls.filename() + ".bak"
        if path.isfile(bakfile):
            from shutil import move
            move(bakfile, cls.filename())

    @classmethod
    def filename(cls):
        """
        Convenience function, which returns the filename in the correct directory.
        :return (str): Filename in directory
        """
        return cls._get_config_file(cls._config_filename)

    @classmethod
    def _get_config_file(cls, filename):
        """
        Returns the filename in the user config directory.
        :param filename (str): Relative filename
        :return (str): Filename in directory
        """
        return path.join(cls._dirs.user_config_dir, filename)

    def _parse(self):
        """
        Deserializes the Config object from file
        :return:
        """
        with open(self.filename(), 'rt') as infile:
            config_data = json.load(infile)
            for key, value in config_data.items():
                se = ServerEntry(**value)
                self._servers[se.name] = se

    def write(self):
        """
        Saves the current config object to the default homedirectory config.
        :return:
        """
        outdict = {}
        for se in self._servers.values():
            outdict[se.name] = se._asdict()

        with open(self.filename(),'wt') as outfile:
            json.dump(outdict,outfile)

    def add_server(self, name, username, url, port, calculation_basepath, queueing_system):
        """
        Adds a server to the config. If it already exists, overwrites the existing entry.
        :param name (str): Given name of the server, e.g. NMC
        :param username (str): Username ssh uses to login
        :param url (str): int-nanomatchcluster.int.kit.edu, URL of the server
        :param port (int): 22
        :param calculation_basepath (str): Path to the basefolder. E.g. /home/you/nanomatch_calculations
        :param queueing_system (str): torque, slurm, lsf, Name of the queueing system
        :return:
        """
        se = ServerEntry(name=name,
                    username=username,
                    url=url,
                    port=port,
                    calculation_basepath=calculation_basepath,
                    queueing_system=queueing_system
        )
        self._servers[name] = se


