import hashlib
import os
import pathlib
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open


from SimStackServer.Util.ResultRepo import (
    compute_files_hash,
    list_files,
    compute_dir_hash, ResultRepo
)

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

class TestResultRepo:
    def setup_method(self):
        # Create temporary directories for testing
        self.test_dir = pathlib.Path(tempfile.mkdtemp())
        self.results_dir = pathlib.Path(tempfile.mkdtemp())

        # Create sample files
        self.create_sample_files()

        self.rm = ResultRepo()

    def teardown_method(self):
        # Clean up temporary directories
        shutil.rmtree(self.test_dir)
        shutil.rmtree(self.results_dir)

    def create_sample_files(self):
        # Create a directory structure with sample files
        os.makedirs(os.path.join(self.test_dir, "subdir1"), exist_ok=True)
        os.makedirs(os.path.join(self.test_dir, "subdir2"), exist_ok=True)

        # Create sample files with content
        with open(os.path.join(self.test_dir, "file1.txt"), "w") as f:
            f.write("Content of file 1")

        with open(os.path.join(self.test_dir, "subdir1", "file2.txt"), "w") as f:
            f.write("Content of file 2")

        with open(os.path.join(self.test_dir, "subdir2", "file3.txt"), "w") as f:
            f.write("Content of file 3")

    def test_list_files(self):
        # Test listing files in a directory
        file_list = list_files(pathlib.Path(self.test_dir))

        # Verify all files are listed
        assert len(file_list) == 5
        assert pathlib.Path(os.path.join(self.test_dir, "file1.txt")) in file_list
        assert pathlib.Path(os.path.join(self.test_dir, "subdir1", "file2.txt")) in file_list
        assert pathlib.Path(os.path.join(self.test_dir, "subdir2", "file3.txt")) in file_list

    def test_compute_files_hash(self):
        # Test hashing a list of files
        file_list = [
            pathlib.Path(os.path.join(self.test_dir, "file1.txt")),
            pathlib.Path(os.path.join(self.test_dir, "subdir1", "file2.txt")),
        ]

        # Compute hash
        file_hash = compute_files_hash(file_list, pathlib.Path(self.test_dir))

        # Verify it's a non-empty string
        #assert isinstance(file_hash, hashlib.md5)
        a = file_hash.hexdigest()
        assert len(a) == 32


        # Verify different files produce different hashes
        different_file_list = [
            pathlib.Path(os.path.join(self.test_dir, "file1.txt")),
            pathlib.Path(os.path.join(self.test_dir, "subdir2", "file3.txt")),
        ]
        different_hash = compute_files_hash(different_file_list, pathlib.Path(self.test_dir))
        assert file_hash != different_hash

    def test_compute_dir_hash(self):
        # Test hashing a directory
        dir_hash = compute_dir_hash(self.test_dir)

        # Verify it's a non-empty string
        a = dir_hash.hexdigest()
        assert len(a) == 32

    def test_compute_input_hash(self):



        # Create a mock execution module
        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1", "param2": 123}
        mock_module.get_inpath.return_value = self.test_dir
        mock_module.runtime_directory = self.test_dir
        mock_module.outputpath = str(self.test_dir)
        # Test computing input hash
        input_hash = self.rm.compute_input_hash(mock_module)

        # Verify it's a non-empty string
        assert isinstance(input_hash, str)
        assert len(input_hash) > 0

        # Verify it's deterministic
        second_hash = self.rm.compute_input_hash(mock_module)
        assert input_hash == second_hash



    def test_load_results(self):
        # Mock database engine and query result

        mock_wfem = MagicMock()
        mock_resources = MagicMock()
        mock_resources.basepath = self.test_dir
        mock_wfem.resources = mock_resources
        mock_wfem.runtime_directory = self.test_dir

        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1"}
        mock_module.get_inpath.return_value = self.test_dir

        with patch("SimStackServer.Util.ResultRepo.Session") as MockSession:
            mock_session_factory = MockSession.return_value
            mock_session = mock_session_factory.__enter__.return_value
            mock_session.scalar.return_value = None
            a,b = self.rm.load_results(mock_module, mock_wfem)

            assert a is False
            assert b is None

            mock_shutil = MagicMock()
            mock_shutil.copytree.return_value = None
            mock_solution=MagicMock()
            mock_solution.output_directory="output_dir"
            mock_session.scalar.return_value = mock_solution
            output_dir = self.test_dir / "output_dir"
            with patch("SimStackServer.Util.ResultRepo.shutil", return_value=mock_shutil):
                a,b = self.rm.load_results(mock_module, mock_wfem)
                # Verify no results were found
                assert a is False
                assert b is None

                os.mkdir(output_dir)
                a, b = self.rm.load_results(mock_module, mock_wfem)
                assert a is False
                assert b is None


            mock_solution=MagicMock()
            mock_solution.output_directory="output_dir"
            mock_solution.output_hash = compute_dir_hash(output_dir).hexdigest()
            mock_session.scalar.return_value = mock_solution
            with patch("SimStackServer.Util.ResultRepo.shutil", return_value=mock_shutil):
                a,b = self.rm.load_results(mock_module, mock_wfem)
                # Verify no results were found
                assert a is True
                assert b == str(output_dir)


    def test_store_results(self):
        mock_wfem = MagicMock()
        mock_resources = MagicMock()
        mock_resources.basepath = self.test_dir
        mock_wfem.resources = mock_resources
        mock_wfem.runtime_directory = self.test_dir

        mock_module = MagicMock()
        mock_module.get_name.return_value = "test_module"
        mock_module.get_configuration.return_value = {"param1": "value1"}
        mock_module.get_inpath.return_value = self.test_dir
        mock_engine = MagicMock()
        output_dir = self.test_dir / "output_dir"
        with patch("SimStackServer.Util.ResultRepo.Session") as MockSession:
            mock_session_factory = MockSession.return_value
            mock_session = mock_session_factory.__enter__.return_value

            mock_solution=MagicMock()
            mock_solution.output_directory="output_dir"
            mock_solution.output_hash = compute_dir_hash(output_dir).hexdigest()
            mock_session.scalar.return_value = mock_solution


            with patch.object(self.rm, "_get_engine", return_value = mock_engine):
                self.rm.store_results("ladida", mock_wfem)

                mock_session.merge.assert_called_once()
                mock_session.commit.assert_called_once()

                newfile = self.test_dir / "original_job.txt"
                assert newfile.exists()