import unittest

from os import path

from SimStackServer.Config import Config


class TestConfig(unittest.TestCase):
    def setUp(self):
        self._input_dir = "%s/input_dirs/Config" % path.dirname(path.realpath(__file__))
        Config.backup_config()

    def tearDown(self):
        Config.restore_config()

    def test_ConfigObject(self):
        config = Config()
        config.add_server(
            "NMC",
            "strunk",
            "int-nanomatchcluster.int.kit.edu",
            22,
            "/home/strunk",
            "torque",
        )
        config.write()
        otherconfig = Config()
        self.assertDictEqual(config._servers, otherconfig._servers)

    def test_is_running_and_pid(self):
        config = Config()
        assert config.is_running() == False
        config.register_pid()
        assert config.is_running() == True
        config.teardown_pid()
        assert config.is_running() == False
