import unittest

from os import path
from shutil import rmtree
from SimStackServer.Util.FileUtilities import mkdir_p

class TestDataRegistry(unittest.TestCase):
    def setUp(self):
        self._exec_dir = "%s/exec_dirs/FileUtilities" % path.dirname(path.realpath(__file__))

    def tearDown(self):
        rmtree(self._exec_dir)

    def test_mkdir_p(self):
        mypath = path.join(self._exec_dir,"testdir/othertestdir")
        mkdir_p(mypath)
        assert path.isdir(mypath)
