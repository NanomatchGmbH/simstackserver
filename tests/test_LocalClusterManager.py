# test_local_cluster_manager.py
import copy
import os
import pathlib
import posixpath
import shutil
import socket
import subprocess

import getpass
import pytest
from unittest.mock import MagicMock, patch

import paramiko
from paramiko.hostkeys import HostKeys
from paramiko.rsakey import RSAKey

import sshtunnel

from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError
from SimStackServer.LocalClusterManager import LocalClusterManager
import SimStackServer


#############################
# Fixtures and Helpers
#############################


@pytest.fixture
def ssh_client_with_host_keys():
    """Return a real SSHClient with a dummy host key so save_host_keys writes content."""
    client = paramiko.SSHClient()
    host_keys = HostKeys()
    private_key = RSAKey.generate(bits=1024)
    host_keys.add("example.com", "ssh-rsa", private_key)
    client._host_keys = host_keys
    return client


@pytest.fixture
def mock_sshclient():
    """Return a MagicMock for paramiko.SSHClient with a working transport and open_sftp."""
    mock_client = MagicMock(spec=paramiko.SSHClient)
    transport = MagicMock()
    transport.is_active.return_value = True
    mock_client.get_transport.return_value = transport
    mock_sftp = MagicMock(spec=paramiko.SFTPClient)
    mock_client.open_sftp.return_value = mock_sftp
    return mock_client


@pytest.fixture
def mock_sftpclient(mock_sshclient):
    """Return the SFTP client mock with basic stat and listdir_attr behavior."""
    sftp = mock_sshclient.open_sftp()
    # Default: stat returns directory mode
    stat_mock = MagicMock(spec=paramiko.SFTPAttributes)
    stat_mock.st_mode = 0o040755
    sftp.stat.return_value = stat_mock

    def fake_listdir_attr(path):
        # By default, return a list with one file entry.
        file_attr = MagicMock(spec=paramiko.SFTPAttributes)
        file_attr.filename = "testfile"
        file_attr.st_mode = 0o100644
        return [file_attr]

    sftp.listdir_attr.side_effect = fake_listdir_attr
    return sftp


@pytest.fixture
def mock_sshtunnel_forwarder():
    """Return a MagicMock for sshtunnel.SSHTunnelForwarder."""
    forwarder = MagicMock(spec=sshtunnel.SSHTunnelForwarder)
    forwarder.is_alive = False
    return forwarder


@pytest.fixture
@patch("paramiko.SSHClient", autospec=True)
@patch("sshtunnel.SSHTunnelForwarder", autospec=True)
def cluster_manager(
    mock_sshtunnel_forwarder_class,
    mock_sshclient_class,
    mock_sshclient,
    mock_sftpclient,
    mock_sshtunnel_forwarder,
):
    """
    Return a LocalClusterManager instance with patched dependencies.
    """
    # Whenever SSHClient() is called, return our mock.
    mock_sshclient_class.return_value = mock_sshclient
    # Whenever SSHTunnelForwarder is constructed, return our mock.
    mock_sshtunnel_forwarder_class.return_value = mock_sshtunnel_forwarder

    lcm = LocalClusterManager(
        url="fake-url",
        port=22,
        calculation_basepath="/fake/basepath",
        user="fake-user",
        sshprivatekey="UseSystemDefault",
        extra_config="None",
        queueing_system="Internal",
        default_queue="fake-queue",
        software_directory="/fake/software_dir",
    )
    return lcm


#############################
# Tests
#############################


def test_init(cluster_manager):
    assert cluster_manager._url == "fake-url"
    assert cluster_manager._port == 22
    assert cluster_manager._user == "fake-user"
    assert cluster_manager._calculation_basepath == "/fake/basepath"
    assert cluster_manager._default_queue == "fake-queue"
    # Test conversion of port from non-int value:
    cm = LocalClusterManager(
        "fake-url",
        "bad_port",
        "/fake/basepath",
        "fake-user",
        "UseSystemDefault",
        "None",
        "Internal",
        "fake-queue",
        "/fake/software_dir",
    )
    assert cm._port == 22


def test_dummy_callback(capfd, cluster_manager):
    cluster_manager._dummy_callback(50, 100)
    out, err = capfd.readouterr()
    assert "50" in out


def test_get_ssh_url(cluster_manager):
    assert cluster_manager.get_ssh_url() == "fake-user@fake-url:22"


def test_connection_context_already_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=True)
    with patch.object(
        cluster_manager, "connect_if_disconnected"
    ) as mock_conn, patch.object(cluster_manager, "disconnect") as mock_disconn:
        with cluster_manager.connection_context() as result:
            assert result is None
            mock_conn.assert_not_called()
        mock_disconn.assert_called_once()


def test_connection_context_not_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=False)
    with patch.object(
        cluster_manager,
        "connect_if_disconnected",
        return_value=None,
    ) as mock_conn, patch.object(cluster_manager, "disconnect") as mock_disconn:
        with cluster_manager.connection_context() as result:
            assert result is None
            mock_conn.assert_called_once()
        mock_disconn.assert_called_once()


def test_connect_if_disconnected_already_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=True)
    with patch.object(cluster_manager, "connect") as mock_connect:
        cluster_manager.connect_if_disconnected()
    mock_connect.assert_not_called()


def test_connect_if_disconnected_not_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=False)
    with patch.object(cluster_manager, "connect") as mock_connect:
        cluster_manager.connect_if_disconnected()
    mock_connect.assert_called_once()


def test_disconnect_all_set(cluster_manager):
    # Create mocks for all connections (without ZMQ).
    mock_http = MagicMock()
    mock_http._server_list = [MagicMock(), MagicMock()]
    for srv in mock_http._server_list:
        srv.timeout = None
    mock_http._transport = MagicMock()
    cluster_manager._http_server_tunnel = mock_http
    cluster_manager.disconnect()
    for srv in mock_http._server_list:
        assert srv.timeout == 0.01
    mock_http._transport.close.assert_called_once()
    mock_http.stop.assert_called_once()


def test_resolve_file_in_basepath(cluster_manager):
    # When basepath_override is None, it should use _calculation_basepath.
    cluster_manager._calculation_basepath = "/fake/basepath"
    # If the resolved path doesn't start with "/", it prepends the home directory.
    resolved = cluster_manager.resolve_file_in_basepath("myfile.txt", None)
    if not resolved.startswith("/"):
        expected = str(pathlib.Path.home() / "myfile.txt")
    else:
        expected = resolved
    assert resolved == expected


def test_resolve_file_in_basepath_no_abspath(cluster_manager):
    # When basepath_override is None, it should use _calculation_basepath.
    cluster_manager._calculation_basepath = "fake/basepath"
    # If the resolved path doesn't start with "/", it prepends the home directory.
    resolved = cluster_manager.resolve_file_in_basepath("myfile.txt", None)
    if not resolved.startswith("/"):
        expected = str(pathlib.Path.home() / "myfile.txt")
    else:
        expected = resolved
    assert resolved == expected


def test_delete_file(tmp_path, cluster_manager):
    # Create a dummy file to be deleted.
    testfile = tmp_path / "delete_me.txt"
    testfile.write_text("data")
    # Override resolve_file_in_basepath to simply return the file's path.
    cluster_manager.resolve_file_in_basepath = lambda f, b: str(testfile)
    # Now call delete_file and ensure the file is gone.
    cluster_manager.delete_file("delete_me.txt")
    assert not testfile.exists()


def test_rmtree(tmpdir, cluster_manager):
    # Create a dummy directory tree.
    base = pathlib.Path(tmpdir + "/rmtree_test")
    base.mkdir()
    (base / "subdir").mkdir()
    (base / "file1.txt").write_text("data")
    (base / "subdir" / "file2.txt").write_text("data")
    # Override resolve_file_in_basepath to simply return the directory path.
    # cluster_manager.resolve_file_in_basepath = lambda d, b: str(base / d)
    # Call rmtree.
    cluster_manager.rmtree("rmtree_test", basepath_override=tmpdir)
    assert not base.exists()


def test_put_directory(tmpdir, cluster_manager):
    # Prepare a dummy source directory tree.
    cluster_manager._calculation_basepath = tmpdir
    src = pathlib.Path(tmpdir + "/src_dir")
    src.mkdir()
    (src / "fileA.txt").write_text("A")
    (src / "sub").mkdir()
    (src / "sub" / "fileB.txt").write_text("B")
    # Override put_file to simply copy the file using shutil.
    cluster_manager.put_file = lambda frm, to, cb=None, bo=None: shutil.copyfile(
        frm, pathlib.Path(tmpdir) / to
    )
    # Call put_directory.
    with patch(
        "SimStackServer.LocalClusterManager.LocalClusterManager.exists_as_directory",
        return_value=True,
    ):
        dest = cluster_manager.put_directory(str(src), "dest_dir")
    # dest should be resolved relative to _calculation_basepath.
    expected = cluster_manager.resolve_file_in_basepath("dest_dir", None)
    assert dest == expected
    # Check that the files exist.
    assert os.path.exists(os.path.join(expected, "fileA.txt"))
    assert os.path.exists(os.path.join(expected, "sub", "fileB.txt"))


def test_mkdir_p(cluster_manager, tmpdir):
    """
    the above test calls mkdir_p with put_directory, but not with a real directory so this tests covers one missing line
    """
    cluster_manager._calculation_basepath = tmpdir
    # tmp_path = pathlib.Path(tmpdir) / "some_new_folder"
    assert (
        cluster_manager.mkdir_p(pathlib.Path("some_new_folder"))
        == str(tmpdir) + "/some_new_folder"
    )


def test_exists_remote(cluster_manager, temporary_file):
    # In LocalClusterManager, exists_remote simply calls os.path.exists.
    assert cluster_manager.exists_remote(temporary_file) is True
    # Non-existent file returns False.
    assert cluster_manager.exists_remote("/non/existent/path") is False


def test_get_queueing_system(cluster_manager):
    assert cluster_manager.get_queueing_system() == "Internal"


def test_get_directory(tmpdir, cluster_manager):
    # Prepare a dummy "remote" tree in the local filesystem.
    cluster_manager._calculation_basepath = tmpdir
    tmp_path = pathlib.Path(tmpdir)
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    (remote_dir / "file1.txt").write_text("F1")
    (remote_dir / "subdir").mkdir()
    (remote_dir / "subdir" / "file2.txt").write_text("F2")
    # Call get_directory to copy the "remote" tree to a destination.
    dest_dir = tmp_path / "dest"
    cluster_manager.get_directory("remote", str(dest_dir))
    assert (dest_dir / "file1.txt").exists()
    assert (dest_dir / "subdir" / "file2.txt").exists()


def test_remote_open(tmp_path, cluster_manager):
    # Create a dummy file.
    file_path = tmp_path / "remote.txt"
    file_path.write_text("remote content")
    # Override resolve_file_in_basepath to return the actual file path.
    cluster_manager.resolve_file_in_basepath = lambda f, b: str(file_path)
    with cluster_manager.remote_open("remote.txt", "r") as f:
        content = f.read()
    assert content == "remote content"


def test_list_dir(tmpdir, cluster_manager):
    cluster_manager._calculation_basepath = tmpdir
    # Create a dummy directory with a file and a subdirectory.
    tmp_path = pathlib.Path(tmpdir)
    test_dir = tmp_path / "list_test"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("data")
    (test_dir / "subdir").mkdir()
    # Use os.scandir in list_dir.
    result = cluster_manager.list_dir("list_test")
    expected = []
    for entry in os.scandir(str(test_dir)):
        typ = "d" if entry.is_dir() else "f"
        expected.append({"name": entry.name, "path": str(test_dir), "type": typ})
    assert result == expected


def test_get_default_queue(cluster_manager):
    assert cluster_manager.get_default_queue() == "fake-queue"


def test_exec_command(cluster_manager):
    # If connection is local, exec_command runs subprocess.
    # We simulate that by forcing connection_is_localhost_and_same_user() to return True.
    cluster_manager.connection_is_localhost_and_same_user = lambda: True
    # Patch subprocess.run to return a dummy CompletedProcess.
    dummy_proc = subprocess.CompletedProcess(
        args="echo test", returncode=0, stdout=b"out\n", stderr=b""
    )
    with patch("subprocess.run", return_value=dummy_proc) as mock_run:
        stdout, stderr = cluster_manager.exec_command("echo test")
    mock_run.assert_called_once_with("echo test", shell=True, capture_output=True)
    assert stdout == ["out", ""]


def test_get_server_command_from_software_directory(cluster_manager):
    # Test the branch that finds micromamba.
    # Override exists() to simulate that the micromamba binary exists.
    cluster_manager._queueing_system = "AiiDA"
    cluster_manager.exists = lambda p: p.endswith(
        "/envs/simstack_server_v6/bin/micromamba"
    )
    res = cluster_manager.get_server_command_from_software_directory(
        "/fake/software_dir"
    )
    expected = "/fake/software_dir/envs/simstack_server_v6/bin/micromamba run -r /fake/software_dir --name=simstack_server_v6 SimStackServer"
    assert res == expected


def test_get_server_command_from_software_directory_conda_sh_file(cluster_manager):
    # Test the branch that finds micromamba.
    # Override exists() to simulate that the micromamba binary exists.
    cluster_manager.exists = lambda p: p.endswith("/etc/profile.d/conda.sh")
    res = cluster_manager.get_server_command_from_software_directory(
        "/fake/software_dir"
    )
    expected = "source /fake/software_dir/etc/profile.d/conda.sh; conda activate simstack_server_v6;  SimStackServer"
    assert res == expected


def test_get_server_command_from_software_directory_FileNotFound(cluster_manager):
    with pytest.raises(FileNotFoundError):
        cluster_manager.get_server_command_from_software_directory("/fake/software_dir")


def test__get_server_command(cluster_manager):
    with patch.object(
        cluster_manager,
        "get_server_command_from_software_directory",
        return_value="dummy_cmd",
    ) as mock_method:
        result = cluster_manager._get_server_command()
        assert result == "dummy_cmd"
        mock_method.assert_called_once_with(cluster_manager._software_directory)


def test_connection_is_localhost_and_same_user(cluster_manager):
    cluster_manager._url = "localhost"
    cluster_manager._user = getpass.getuser()
    assert cluster_manager.connection_is_localhost_and_same_user() is True
    cluster_manager._url = "remotehost"
    assert cluster_manager.connection_is_localhost_and_same_user() is False


def test_exists_as_directory(cluster_manager, tmpdir, tmpfile):
    with patch.object(
        cluster_manager, "connection_is_localhost_and_same_user", return_value=True
    ) as mock_connection_to_localhost:
        assert cluster_manager.exists_as_directory(tmpdir) is True
        mock_connection_to_localhost.assert_called_once()
        with pytest.raises(SSHExpectedDirectoryError):
            cluster_manager.exists_as_directory(tmpfile)


def test_exists(cluster_manager, tmpdir, tmpfile):
    with patch.object(
        cluster_manager, "connection_is_localhost_and_same_user", return_value=True
    ):
        assert cluster_manager.exists(tmpdir) is True
        assert cluster_manager.exists(tmpfile) is True


def test_get_url_for_workflow(cluster_manager):
    cluster_manager._http_base_address = "http://dummy:404@localhost:9999"
    url = cluster_manager.get_url_for_workflow("workflow1")
    assert url == "http://dummy:404@localhost:9999/workflow1"


def test__is_socket_closed_returns_false_when_data():
    """
    Simulate an open socket by having recv return non-empty data.
    _is_socket_closed should return False.
    """
    dummy_sock = MagicMock(spec=socket.socket)
    dummy_sock.recv.return_value = b"hello"  # non-empty data
    result = LocalClusterManager._is_socket_closed(dummy_sock)
    assert result is False


def test__is_socket_closed_returns_true_when_empty():
    """
    Simulate a closed socket by having recv return empty bytes.
    _is_socket_closed should return True.
    """
    dummy_sock = MagicMock(spec=socket.socket)
    dummy_sock.recv.return_value = b""
    result = LocalClusterManager._is_socket_closed(dummy_sock)
    assert result is True


def test__is_socket_closed_returns_false_on_blocking_error():
    """
    If recv raises BlockingIOError, the socket is open (but no data available),
    so _is_socket_closed should return False.
    """
    dummy_sock = MagicMock(spec=socket.socket)
    dummy_sock.recv.side_effect = BlockingIOError
    result = LocalClusterManager._is_socket_closed(dummy_sock)
    assert result is False


def test__is_socket_closed_returns_true_on_connection_reset():
    """
    If recv raises ConnectionResetError, _is_socket_closed should return True.
    """
    dummy_sock = MagicMock(spec=socket.socket)
    dummy_sock.recv.side_effect = ConnectionResetError
    result = LocalClusterManager._is_socket_closed(dummy_sock)
    assert result is True


def test__is_socket_closed_unexpected_exception():
    """
    If recv raises an unexpected exception (e.g. OSError with errno 9),
    _is_socket_closed prints a message and returns False.
    """
    dummy_sock = MagicMock(spec=socket.socket)
    # Simulate an OSError (Bad file descriptor) for example.
    dummy_sock.recv.side_effect = OSError(9, "Bad file descriptor")
    result = LocalClusterManager._is_socket_closed(dummy_sock)
    assert result is False


def test___del___(cluster_manager):
    mock_http_server_tunnel = MagicMock()
    mock_http_server_tunnel.is_alive = True
    cluster_manager._http_server_tunnel = mock_http_server_tunnel
    cluster_manager.connect()
    cluster_manager.__del__()
    mock_http_server_tunnel.stop.assert_called_once()


def test_is_directory(cluster_manager, tmpdir):
    cluster_manager._calculation_basepath = tmpdir
    assert cluster_manager.is_directory(tmpdir) is False


def test_get_newest_version_directory_envs_last(cluster_manager, mock_sftpclient):
    """
    Test get_newest_version_directory when entries are in order:
    "V2", "V8", then "envs", then a non-matching entry.
    In this order, even though V8 would set largest_version to 8,
    the later "envs" forces largest_version to 6.
    Final result should be "V6".
    """

    def fake_listdir_V6(path):
        # By default, return a list with one file entry.
        dir_attr = MagicMock(spec=paramiko.SFTPAttributes)
        dir_attr.filename = "V6"
        dir_attr.st_mode = 0o040755
        return [dir_attr]

    def fake_listdir_V2(path):
        # By default, return a list with one file entry.
        dir_attr = MagicMock(spec=paramiko.SFTPAttributes)
        dir_attr.filename = "V2"
        dir_attr.st_mode = 0o040755
        return [dir_attr]

    def fake_listdir_VV(path):
        # By default, return a list with one file entry.
        dir_attr = MagicMock(spec=paramiko.SFTPAttributes)
        dir_attr.filename = "VV"
        dir_attr.st_mode = 0o040755
        return [dir_attr]

    def fake_listdir_envs(path):
        # By default, return a list with one file entry.
        dir_attr = MagicMock(spec=paramiko.SFTPAttributes)
        dir_attr.filename = "envs"
        dir_attr.st_mode = 0o040755
        return [dir_attr]

    def fake_listdir_no_dir(path):
        # By default, return a list with one file entry.
        dir_attr = MagicMock(spec=paramiko.SFTPAttributes)
        dir_attr.filename = "V2"
        dir_attr.st_mode = 0o100644
        return [dir_attr]

    mock_sftpclient.listdir_attr.side_effect = fake_listdir_V6
    cluster_manager._sftp_client = mock_sftpclient
    result = cluster_manager.get_newest_version_directory("/fake/path")
    assert result == "V6"

    mock_sftpclient.listdir_attr.side_effect = fake_listdir_V2
    cluster_manager._sftp_client = mock_sftpclient
    result = cluster_manager.get_newest_version_directory("/fake/path")
    assert result == "V2"

    mock_sftpclient.listdir_attr.side_effect = fake_listdir_envs
    cluster_manager._sftp_client = mock_sftpclient
    result = cluster_manager.get_newest_version_directory("/fake/path")
    assert result == "V6"

    mock_sftpclient.listdir_attr.side_effect = fake_listdir_no_dir
    cluster_manager._sftp_client = mock_sftpclient
    result = cluster_manager.get_newest_version_directory("/fake/path")
    assert result == "V-1"

    mock_sftpclient.listdir_attr.side_effect = fake_listdir_VV
    cluster_manager._sftp_client = mock_sftpclient
    result = cluster_manager.get_newest_version_directory("/fake/path")
    assert result == "V-1"

    mock_sftpclient.listdir_attr.side_effect = FileNotFoundError(2, "Not found")
    with pytest.raises(FileNotFoundError) as excinfo:
        cluster_manager.get_newest_version_directory("/nonexistent")
    # Check that the error message includes the expected text.
    assert "No such file" in str(excinfo.value)


def test_is_connected(cluster_manager):
    cluster_manager._url = "localhost"
    cluster_manager._user = "testuser"
    # Patch getpass.getuser to return "testuser"
    with patch("getpass.getuser", return_value="testuser"):
        assert cluster_manager.is_connected() is False


def test_put_file_success(cluster_manager, tmpdir, tmpfile):
    # Create a local source file.

    tmpfile.write_text("hello world")

    # Create an absolute base directory.
    base_dir = pathlib.Path(tmpdir) / "base"
    base_dir.mkdir()
    cluster_manager._calculation_basepath = str(base_dir)

    # Override exists_as_directory to return False (simulate that remote file is not a directory).
    cluster_manager.exists_as_directory = lambda p: False

    # Call put_file to "upload" the file.
    cluster_manager.put_file(str(tmpfile), "remote.txt")

    # Since the basepath is absolute, abstofile is constructed as:
    #    base_dir + "/" + "remote.txt"
    dest_file = pathlib.Path(str(base_dir) + "/remote.txt")
    assert dest_file.exists(), f"Destination file {dest_file} does not exist."
    assert dest_file.read_text() == "hello world"


def test_put_file_success_rel_path(cluster_manager, tmpdir, tmpfile):
    # Create a local source file.

    tmpfile.write_text("hello world")
    fake_home = "/tmp"
    with patch.object(pathlib.Path, "home", return_value=pathlib.Path(fake_home)):
        # Create an absolute base directory.
        base_dir = pathlib.Path(tmpdir) / "base"
        base_dir.mkdir()
        remote_dir = base_dir / "remote_directory"
        remote_dir.mkdir()

        base_dir_from_fake_home = str(base_dir).split("/tmp/")[1]
        # Override exists_as_directory to return False (simulate that remote file is not a directory).
        cluster_manager.exists_as_directory = lambda p: True

        # Call put_file to "upload" the file.
        cluster_manager.put_file(
            str(tmpfile),
            "remote_directory",
            None,
            basepath_override=base_dir_from_fake_home,
        )

        dest_file = pathlib.Path(
            str(base_dir) + "/remote_directory/" + posixpath.basename(tmpfile)
        )
        assert dest_file.exists(), f"Destination file {dest_file} does not exist."
        assert dest_file.read_text() == "hello world"


def test_put_file_not_found(cluster_manager):
    # Call put_file with a non-existent source file, expecting FileNotFoundError.
    with pytest.raises(FileNotFoundError):
        cluster_manager.put_file("nonexistent.txt", "remote.txt")


def test_get_file(cluster_manager, tmpfile, tmpdir):
    tmpfile.write_text("hello world")

    # Create an absolute base directory.
    base_dir = pathlib.Path(tmpdir) / "base"
    base_dir.mkdir()
    cluster_manager._calculation_basepath = "/"

    dest_file = pathlib.Path(str(base_dir) + "/" + posixpath.basename(tmpfile))
    cluster_manager.get_file(str(tmpfile), dest_file)
    assert dest_file.exists(), f"Destination file {dest_file} does not exist."
    assert dest_file.read_text() == "hello world"


def test_mkdir_random_singlejob_exec_directory_success(cluster_manager):
    # Set a fake calculation basepath.
    cluster_manager._calculation_basepath = "/fake/basepath"

    # Force exists() to always return False, so the branch for creating a new directory is executed.
    cluster_manager.exists = lambda p: False

    # Override mkdir_p so it simply returns the trial directory as a string (simulate creation).
    cluster_manager.mkdir_p = (
        lambda trialdir, basepath_override=None, mode_override=None: str(trialdir)
    )

    # Call the function. Use a small number of retries for the test.
    trial_directory = cluster_manager.mkdir_random_singlejob_exec_directory(
        "jobname", num_retries=3
    )

    # trial_directory is a Path. Assert it starts with "singlejob_exec_directories"
    # and that "jobname" is part of the directory name.
    trial_directory_str = str(trial_directory)
    assert trial_directory_str.startswith("singlejob_exec_directories")
    assert "jobname" in trial_directory_str


def test_mkdir_random_singlejob_exec_directory_failure(cluster_manager):
    # Set a fake calculation basepath.
    cluster_manager._calculation_basepath = "/fake/basepath"

    # Force exists() to always return True so that the loop never finds a free directory.
    cluster_manager.exists = lambda p: True

    # With a low num_retries, the function should eventually raise a FileExistsError.
    with pytest.raises(
        FileExistsError, match="Could not generate new directory in time."
    ):
        cluster_manager.mkdir_random_singlejob_exec_directory("jobname", num_retries=3)


def test_load_extra_host_keys(cluster_manager):
    assert cluster_manager.load_extra_host_keys("dummyfile") is None


def test_save_hostkeyfile(cluster_manager):
    assert cluster_manager.save_hostkeyfile("dummyfile") is None


def test_set_connect_to_unknown_hosts(cluster_manager):
    prev = copy.deepcopy(cluster_manager._unknown_host_connect_workaround)
    cluster_manager.set_connect_to_unknown_hosts(not prev)
    assert cluster_manager._unknown_host_connect_workaround is not prev


def test_sshtunnel_lib():
    # Tests if get_keys works (breaks with paramiko > 3.5.1)
    sshtunnel.SSHTunnelForwarder.get_keys()
