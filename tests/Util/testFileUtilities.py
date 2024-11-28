import unittest

from os import path
from shutil import rmtree
from SimStackServer.Util.FileUtilities import mkdir_p, split_directory_in_subdirectories


class TestDataRegistry(unittest.TestCase):
    def setUp(self):
        self._exec_dir = "%s/exec_dirs/FileUtilities" % path.dirname(
            path.realpath(__file__)
        )

    def tearDown(self):
        if path.isdir(self._exec_dir):
            rmtree(self._exec_dir)

    def test_mkdir_p(self):
        mypath = path.join(self._exec_dir, "testdir/othertestdir")
        mkdir_p(mypath)
        assert path.isdir(mypath)

    def test_split_directory_in_subdirectories(self):
        mydir = "/a/b/c/d/"
        print(split_directory_in_subdirectories(mydir))
        self.assertListEqual(
            split_directory_in_subdirectories(mydir),
            ["/a", "/a/b", "/a/b/c", "/a/b/c/d"],
        )
        mydir = "/a/b/c/d"
        self.assertListEqual(
            split_directory_in_subdirectories(mydir),
            ["/a", "/a/b", "/a/b/c", "/a/b/c/d"],
        )
        mydir = "/"
        self.assertListEqual(split_directory_in_subdirectories(mydir), [])
        mydir = ""
        self.assertListEqual(split_directory_in_subdirectories(mydir), [])
