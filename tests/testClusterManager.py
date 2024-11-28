import unittest

from os import path
from os.path import join

from shutil import rmtree
import getpass

from SimStackServer.ClusterManager import ClusterManager, SSHExpectedDirectoryError
from SimStackServer.Util.FileUtilities import mkdir_p
from SimStackServer.WorkflowModel import Resources


class TestClusterManager(unittest.TestCase):
    def setUp(self):
        self._input_dir = "%s/input_dirs/ClusterManager" % path.dirname(
            path.realpath(__file__)
        )
        self._testfilename = join(self._input_dir, "testfile")
        self._exec_dir = "%s/exec_dirs/ClusterManager" % path.dirname(
            path.realpath(__file__)
        )
        self._output_testfilename = join(self._exec_dir, "output_testfilename.txt")
        mkdir_p(self._exec_dir)
        self._remote_dir = "UnitTests/ClusterManager"
        self._username = getpass.getuser()

    def tearDown(self):
        rmtree(self._exec_dir)

    def test_connect(self):
        cm = ClusterManager(
            "nmc.nanomatch.de",
            37321,
            self._remote_dir,
            self._username,
            "UseSystemDefault",
            "None Required",
            "slurm",
            "default",
        )
        cm.connect()
        cm.exec_command("uptime")
        cm.put_file(self._testfilename, "unittest_testfile.txt")
        cm.get_file("unittest_testfile.txt", self._output_testfilename)

        Resources()

        # cm.write_jobfile("test.jobscript","echo HELLO WORLD\n",res,"HELLO_WORLD")
        assert cm.exists_as_directory("huubbertt") is False
        assert cm.exists_as_directory("/") is True
        self.assertRaises(
            SSHExpectedDirectoryError, cm.exists_as_directory, "/dev/urandom"
        )
        cm.mkdir_p("2del", basepath_override="")
        cm.mkdir_p("/Test/hubababbiiibidi", basepath_override="2del")
        return
        assert (
            cm.exists_as_directory(self._remote_dir + "2del/Test/hubababbiiibidi")
            is True
        )

        with open(self._testfilename, "rt") as in1:
            file1 = in1.read()
        with open(self._output_testfilename, "rt") as in2:
            file2 = in2.read()

        self.assertEqual(file1, file2)

        cm.disconnect()
