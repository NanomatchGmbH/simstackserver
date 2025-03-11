import os.path
import pathlib
import tempfile

from os import path
from unittest.mock import patch, MagicMock
from lxml import etree

import zipfile

import pytest

from SimStackServer.Util.FileUtilities import (
    mkdir_p,
    split_directory_in_subdirectories,
    PathSplitError,
    abs_resolve_file,
    xml_to_file,
    file_to_xml,
    trace_to_logger,
    StringLoggingHandler,
    copytree,
    copytree_pathlib,
)


@pytest.fixture
def tmpdir() -> tempfile.TemporaryDirectory:
    with tempfile.TemporaryDirectory() as mydir:
        yield mydir


@pytest.fixture
def tmpfile(tmpdir):
    tmpfile = pathlib.Path(tmpdir) / "tmp_file.dat"

    # Just touching the file ensures it exists; or you can open/write to it.
    tmpfile.touch()

    yield tmpfile


class TestDataRegistry:
    def test_mkdir_p(self, tmpdir):
        mypath = path.join(tmpdir, "testdir/othertestdir")
        mkdir_p(mypath)
        assert path.isdir(mypath)

    def test_split_directory_in_subdirectories(self):
        mydir = "/a/b/c/d/"
        print(split_directory_in_subdirectories(mydir))
        assert split_directory_in_subdirectories(mydir) == [
            "/a",
            "/a/b",
            "/a/b/c",
            "/a/b/c/d",
        ]
        mydir = "/a/b/c/d"
        assert split_directory_in_subdirectories(mydir) == [
            "/a",
            "/a/b",
            "/a/b/c",
            "/a/b/c/d",
        ]

        mydir = "/"
        assert split_directory_in_subdirectories(mydir) == []
        mydir = ""
        assert split_directory_in_subdirectories(mydir) == []

        mydir = "a/"
        for i in range(5001):
            mydir += "a/"
        with pytest.raises(PathSplitError):
            split_directory_in_subdirectories(mydir)

    def test_abs_resolve_file(self):
        mydir = "a/test.txt"
        with patch("pathlib.Path.home", return_value="/my/home"):
            absdir = abs_resolve_file(mydir)
            assert absdir == "/my/home/a/test.txt"
        mydir = "/a/test.txt"
        assert abs_resolve_file(mydir) == mydir

    def test_xml_to_file(self, tmpfile):
        root = etree.Element("root")
        child = etree.SubElement(root, "child")
        child.text = "content"

        # Serialize the original XML element to a bytes string.
        original_xml_bytes = etree.tostring(root)

        # Write the XML element to file.
        xml_to_file(root, tmpfile)

        # Read the XML element back from the file.
        loaded_root = file_to_xml(tmpfile)
        loaded_xml_bytes = etree.tostring(loaded_root)

        assert (
            original_xml_bytes == loaded_xml_bytes
        ), "The reloaded XML does not match the original."

    @trace_to_logger
    def dummy_success(self, x):
        return x * 2

    @trace_to_logger
    def dummy_fail(self, x):
        raise ValueError("Test exception")

    def test_trace_to_logger_success(self):
        # When no exception occurs, the function should return the correct result.
        result = self.dummy_success(3)
        assert result == 6

    def test_trace_to_logger_exception(self):
        # Patch logging.getLogger so we can inspect calls to logger.exception.
        mock_logger = MagicMock()
        with patch(
            "SimStackServer.Util.FileUtilities.logging.getLogger",
            return_value=mock_logger,
        ):
            with pytest.raises(ValueError, match="Test exception"):
                self.dummy_fail(3)
        # Check that logger.exception was called once with the expected message.
        mock_logger.exception.assert_called_once_with("Exception occured:")

    def test_StringLoggingHandler(self):
        my_logging_handler = StringLoggingHandler()
        assert my_logging_handler.getvalue() == ""

    def test_copytree(self, tmpdir):
        tmppath = pathlib.Path(tmpdir)
        for i in range(3):
            this_file = tmppath / f"{i}.dat"
            this_file.touch()
        targetpath = tmppath / "target"
        os.mkdir(targetpath)
        copytree(tmppath, targetpath)
        for i in range(3):
            this_file = targetpath / f"{i}.dat"
            assert os.path.exists(this_file)

    def test_copytree_pathlib_directory(self, tmpdir):
        tmp_path = pathlib.Path(tmpdir)
        # Create some dummy files in a source directory.
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        filenames = []
        for i in range(3):
            file_path = src_dir / f"{i}.dat"
            file_path.write_text(f"File {i} contents")
            filenames.append(file_path.name)

        # Create a target directory.
        target_dir = tmp_path / "target"
        target_dir.mkdir()

        # Call the function with a directory source.
        copytree_pathlib(src_dir, target_dir)

        # Verify that all files have been copied.
        copied_files = os.listdir(str(target_dir))
        assert set(copied_files) == set(filenames), "Not all files were copied."

    def test_copytree_pathlib_zip(self, tmpdir):
        tmp_path = pathlib.Path(tmpdir)

        # Create a source directory with some files.
        src_dir = tmp_path / "src_zip"
        src_dir.mkdir()
        file_name = "testfile.txt"
        file_content = "Hello from zip"
        (src_dir / file_name).write_text(file_content)

        # Create a zip archive from src_dir.
        zip_path = tmp_path / "test_archive.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file in src_dir.iterdir():
                zf.write(file, arcname=file.name)

        target_dir = tmp_path / "target_zip"
        target_dir.mkdir()

        copytree_pathlib(zipfile.Path(zip_path), target_dir)

        extracted_file = target_dir / file_name
        assert (
            extracted_file.exists()
        ), "The file was not extracted from the zip archive."
        assert (
            extracted_file.read_text() == file_content
        ), "Extracted file content does not match."
