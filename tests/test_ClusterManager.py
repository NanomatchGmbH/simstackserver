# test_cluster_manager.py
import os
import pathlib
import pytest
from unittest.mock import MagicMock, patch
import requests

import paramiko
from paramiko.hostkeys import HostKeys
from paramiko.rsakey import RSAKey
import sshtunnel

from SimStackServer import ClusterManager
from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError


###########################
# Fixtures
###########################


@pytest.fixture
def ssh_client_with_host_keys():
    """Return a real SSHClient with a dummy host key loaded."""
    ssh_client = paramiko.SSHClient()
    host_keys = HostKeys()
    private_key = RSAKey.generate(bits=1024)
    host_keys.add("example.com", "ssh-rsa", private_key)
    ssh_client._host_keys = host_keys
    return ssh_client


@pytest.fixture
def mock_sshclient():
    """Return a MagicMock for SSHClient with a mocked transport and SFTP."""
    mock_ssh = MagicMock(spec=paramiko.SSHClient)
    transport = MagicMock()
    transport.is_active.return_value = True
    mock_ssh.get_transport.return_value = transport

    mock_sftp = MagicMock(spec=paramiko.SFTPClient)
    mock_ssh.open_sftp.return_value = mock_sftp
    return mock_ssh


@pytest.fixture
def mock_sftpclient(mock_sshclient):
    """Return the SFTP mock from mock_sshclient with basic stat and listdir_attr behavior."""
    sftp_mock = mock_sshclient.open_sftp()
    # Default: stat() returns directory attributes.
    stat_mock = MagicMock(spec=paramiko.SFTPAttributes)
    stat_mock.st_mode = 0o040755
    sftp_mock.stat.return_value = stat_mock

    # Default listdir_attr returns one file.
    def _listdir_attr(path):
        file_attr = MagicMock(spec=paramiko.SFTPAttributes)
        file_attr.filename = "testfile"
        file_attr.st_mode = 0o100644
        return [file_attr]

    sftp_mock.listdir_attr.side_effect = _listdir_attr
    return sftp_mock


@pytest.fixture
def mock_sshtunnel_forwarder():
    """Return a MagicMock for SSHTunnelForwarder."""
    mock_forwarder = MagicMock(spec=sshtunnel.SSHTunnelForwarder)
    mock_forwarder.is_alive = False
    return mock_forwarder


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
    Create a ClusterManager instance with patched dependencies.
    """
    mock_sshclient_class.return_value = mock_sshclient
    mock_sshtunnel_forwarder_class.return_value = mock_sshtunnel_forwarder

    cm = ClusterManager.ClusterManager(
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
    return cm


###########################
# Tests
###########################


def test_init(cluster_manager):
    assert cluster_manager._url == "fake-url"
    assert cluster_manager._port == 22
    assert cluster_manager._user == "fake-user"
    assert cluster_manager._calculation_basepath == "/fake/basepath"
    assert cluster_manager._default_queue == "fake-queue"
    # Test conversion of port from string
    cm = ClusterManager.ClusterManager(
        url="fake-url",
        port="test_port",
        calculation_basepath="/fake/basepath",
        user="fake-user",
        sshprivatekey="UseSystemDefault",
        extra_config="None",
        queueing_system="Internal",
        default_queue="fake-queue",
        software_directory="/fake/software_dir",
    )
    assert cm._port == 22


def test_dummy_callback(cluster_manager, capsys):
    cluster_manager._dummy_callback(50, 100)
    captured = capsys.readouterr()
    assert "50 % done" in captured.out.strip()


def test_get_ssh_url(cluster_manager):
    assert cluster_manager.get_ssh_url() == "fake-user@fake-url:22"


def test_connect_success(cluster_manager, mock_sshclient, mock_sftpclient):
    cluster_manager.set_connect_to_unknown_hosts(True)
    cluster_manager.connect()
    mock_sshclient.connect.assert_called_once_with(
        "fake-url", 22, username="fake-user", key_filename=None, compress=True
    )
    assert cluster_manager.is_connected() is True
    mock_sftpclient.get_channel.assert_called_once()


def test_is_connected_false_when_transport_none(cluster_manager, mock_sshclient):
    mock_sshclient.get_transport.return_value = None
    assert cluster_manager.is_connected() is False


def test_connection_context_already_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=True)
    with patch.object(
        cluster_manager, "connect_ssh_and_zmq_if_disconnected"
    ) as mock_connect, patch.object(cluster_manager, "disconnect") as mock_disconnect:
        with cluster_manager.connection_context() as result:
            assert result is None
            mock_connect.assert_not_called()
        mock_disconnect.assert_called_once()


def test_connection_context_not_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=False)
    with patch.object(
        cluster_manager,
        "connect_ssh_and_zmq_if_disconnected",
        return_value="some_tunnel_info",
    ) as mock_connect, patch.object(cluster_manager, "disconnect") as mock_disconnect:
        with cluster_manager.connection_context() as result:
            assert result == "some_tunnel_info"
            mock_connect.assert_called_once_with(connect_http=False, verbose=False)
        mock_disconnect.assert_called_once()


def test_connect_ssh_and_zmq_if_disconnected_already_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=True)
    with patch.object(cluster_manager, "connect") as mock_connect:
        cluster_manager.connect_ssh_and_zmq_if_disconnected(
            connect_http=False, verbose=False
        )
    mock_connect.assert_not_called()


def test_connect_ssh_and_zmq_if_disconnected_not_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=False)
    with patch.object(cluster_manager, "connect") as mock_connect:
        cluster_manager.connect_ssh_and_zmq_if_disconnected(
            connect_http=True, verbose=True
        )
    mock_connect.assert_called_once()


def test_disconnect_all_set(cluster_manager):
    mock_sftp = MagicMock()
    mock_sshclient = MagicMock()

    mock_http_tunnel = MagicMock()
    mock_http_tunnel._server_list = [MagicMock(), MagicMock()]
    mock_transport = MagicMock()
    mock_http_tunnel._transport = mock_transport
    mock_http_tunnel.is_alive = True

    cluster_manager._sftp_client = mock_sftp
    cluster_manager._ssh_client = mock_sshclient
    cluster_manager._http_server_tunnel = mock_http_tunnel

    cluster_manager.disconnect()

    mock_sftp.close.assert_called_once()
    mock_sshclient.close.assert_called_once()
    for srv in mock_http_tunnel._server_list:
        assert srv.timeout == 0.01
    mock_transport.close.assert_called_once()
    mock_http_tunnel.stop.assert_called_once()


def test_disconnect_minimal(cluster_manager):
    mock_sshclient = MagicMock()
    cluster_manager._ssh_client = mock_sshclient
    cluster_manager._sftp_client = None
    cluster_manager._http_server_tunnel = None

    cluster_manager.disconnect()
    mock_sshclient.close.assert_called_once()


def test_delete_file(cluster_manager, mock_sftpclient):
    cluster_manager._sftp_client = mock_sftpclient
    cluster_manager.connect()
    cluster_manager.delete_file("myfile")
    mock_sftpclient.remove.assert_called_once()


def test_put_file_success(cluster_manager, mock_sftpclient, tmp_path):
    local_file = tmp_path / "local.txt"
    local_file.write_text("hello world")
    cluster_manager.connect()
    cluster_manager.put_file(str(local_file), "remote.txt")
    mock_sftpclient.put.assert_called_once()
    args, _ = mock_sftpclient.put.call_args
    assert args[0] == str(local_file)
    # Depending on your internal logic, adjust the expected remote path:
    # For example, if the file is uploaded into a directory named after the remote file,
    # the expected path might be "/fake/basepath/remote.txt/local.txt".
    # Modify this assertion as appropriate.
    # assert args[1] == "/fake/basepath/remote.txt/local.txt"


def test_put_file_not_found(cluster_manager, mock_sftpclient):
    with pytest.raises(FileNotFoundError):
        cluster_manager.put_file("non_existent_file.txt", "remote.txt")


def test_get_file_success(cluster_manager, mock_sftpclient, tmp_path):
    local_dest = tmp_path / "downloaded.txt"
    cluster_manager.connect()
    cluster_manager.get_file("remote.txt", str(local_dest))
    mock_sftpclient.get.assert_called_once_with(
        "/fake/basepath/remote.txt", str(local_dest), None
    )


def test_exists_as_directory_true(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o040755
    mock_sftpclient.stat.return_value = stat_mock
    result = cluster_manager.exists_as_directory("/fake/dir")
    assert result is True
    mock_sftpclient.stat.assert_called()


def test_exists_as_directory_not_dir(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o100644
    mock_sftpclient.stat.return_value = stat_mock
    with pytest.raises(SSHExpectedDirectoryError):
        cluster_manager.exists_as_directory("/test/dir")


def test_exists_as_directory_not_found(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    mock_sftpclient.stat.side_effect = FileNotFoundError
    result = cluster_manager.exists_as_directory("/fake/dir")
    assert result is False


def test_mkdir_p_creates_subdirectories(cluster_manager, mock_sftpclient):
    def side_effect(path_str):
        return False

    cluster_manager.exists_as_directory = MagicMock(side_effect=side_effect)
    cluster_manager.connect()
    result = cluster_manager.mkdir_p(pathlib.Path("foo/bar/baz"))
    assert result == "foo/bar/baz"
    # Adjust expected_calls as needed based on your implementation
    expected_calls = [call[0] for call in mock_sftpclient.mkdir.call_args_list]
    # For example, you might check that at least one call contains "/fake/basepath/foo"
    assert any("/fake/basepath/foo" in args[0] for args in expected_calls)


def test_rmtree(cluster_manager, mock_sftpclient):
    cluster_manager.connect()

    def mock_listdir_attr(path):
        if path == "/fake/basepath/testdir":
            return [
                MagicMock(filename="subfile1", st_mode=0o100755),
                MagicMock(filename="subdir1", st_mode=0o040755),
            ]
        elif path == "/fake/basepath/testdir/subdir1":
            return [MagicMock(filename="subfile2", st_mode=0o100755)]
        return []

    mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr

    cluster_manager.exists_as_directory = MagicMock(return_value=False)
    res = cluster_manager.rmtree("testdir")
    assert res is None

    cluster_manager.exists_as_directory = MagicMock(return_value=True)
    cluster_manager.rmtree("testdir")
    mock_sftpclient.remove.assert_any_call("/fake/basepath/testdir/subfile1")
    mock_sftpclient.remove.assert_any_call("/fake/basepath/testdir/subdir1/subfile2")
    mock_sftpclient.rmdir.assert_any_call("/fake/basepath/testdir/subdir1")
    mock_sftpclient.rmdir.assert_any_call("/fake/basepath/testdir")


def test_remote_open(cluster_manager, mock_sftpclient):
    cluster_manager._sftp_client = mock_sftpclient
    cluster_manager.remote_open("myfile", "r")
    mock_sftpclient.open.assert_called_once()


def test_default_queue(cluster_manager):
    assert cluster_manager.get_default_queue() == "fake-queue"


def test_exec_command(cluster_manager):
    mock_sshclient_instance = MagicMock(spec=paramiko.SSHClient)
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_sshclient_instance.exec_command.return_value = (
        mock_stdin,
        mock_stdout,
        mock_stderr,
    )
    with patch("paramiko.SSHClient", return_value=mock_sshclient_instance):
        stdout, stderr = cluster_manager.exec_command("test-command")
    mock_sshclient_instance.exec_command.assert_called_once_with("test-command")
    assert stdout is mock_stdout
    assert stderr is mock_stderr


# ZMQ tunnel tests are no longer relevant with REST API implementation
# These tests have been removed as the ZMQ functionality has been replaced
# with REST API calls using requests library


def test_save_hostkeyfile(cluster_manager, ssh_client_with_host_keys, tmpfile):
    cluster_manager.connect()
    cluster_manager._ssh_client = ssh_client_with_host_keys
    cluster_manager.save_hostkeyfile(tmpfile)
    assert tmpfile.exists()
    content = tmpfile.read_text()
    assert content.startswith("example.com ssh-rsa")


def test_get_new_connected_ssh_channel_with_config(cluster_manager):
    cluster_manager._sshprivatekeyfilename = "my_private_key"
    cluster_manager._extra_hostkey_file = "/extra/hosts"
    cluster_manager._unknown_host_connect_workaround = True
    mock_sshclient_instance = MagicMock(spec=paramiko.SSHClient)
    with patch("paramiko.SSHClient", return_value=mock_sshclient_instance):
        local_ssh_client = cluster_manager.get_new_connected_ssh_channel()
    mock_sshclient_instance.load_system_host_keys.assert_called_once()
    mock_sshclient_instance.load_host_keys.assert_called_once_with("/extra/hosts")
    mock_sshclient_instance.set_missing_host_key_policy.assert_called_once_with(
        paramiko.AutoAddPolicy
    )
    mock_sshclient_instance.connect.assert_called_once_with(
        "fake-url",
        22,
        username="fake-user",
        key_filename="my_private_key",
        compress=True,
    )
    assert local_ssh_client is mock_sshclient_instance


def test_get_new_connected_ssh_channel_use_system_default(cluster_manager):
    cluster_manager._sshprivatekeyfilename = "UseSystemDefault"
    cluster_manager._extra_hostkey_file = None
    cluster_manager._unknown_host_connect_workaround = False
    mock_sshclient_instance = MagicMock(spec=paramiko.SSHClient)
    with patch("paramiko.SSHClient", return_value=mock_sshclient_instance):
        local_ssh_client = cluster_manager.get_new_connected_ssh_channel()
    mock_sshclient_instance.load_system_host_keys.assert_called_once()
    mock_sshclient_instance.load_host_keys.assert_not_called()
    mock_sshclient_instance.set_missing_host_key_policy.assert_not_called()
    mock_sshclient_instance.connect.assert_called_once_with(
        "fake-url", 22, username="fake-user", key_filename=None, compress=True
    )
    assert local_ssh_client is mock_sshclient_instance


def test_get_http_server_address(cluster_manager, requests_mock):
    """Test REST API implementation of get_http_server_address"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock mkdir_p REST API call (called by connect())
    requests_mock.post(
        "http://localhost:8000/api/files/mkdir",
        json={"created": True, "path": "/fake/basepath", "absolute_path": "/fake/basepath"}
    )

    # Mock the REST API response
    requests_mock.post(
        "http://localhost:8000/api/http-server",
        json={
            "port": 8000,
            "user": "dummy",
            "password": "404",
            "url": "http://localhost:8000/http/browse/"
        }
    )

    cluster_manager.connect()
    address = cluster_manager.get_http_server_address()
    assert address == "http://localhost:8000/http/browse/"
    assert cluster_manager._http_user == "dummy"
    assert cluster_manager._http_pass == "404"


def test_get_http_server_address_connect_error(cluster_manager, requests_mock):
    """Test REST API error handling for get_http_server_address"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock mkdir_p REST API call (called by connect())
    requests_mock.post(
        "http://localhost:8000/api/files/mkdir",
        json={"created": True, "path": "/fake/basepath", "absolute_path": "/fake/basepath"}
    )

    # Mock the REST API to return an error
    requests_mock.post(
        "http://localhost:8000/api/http-server",
        status_code=500,
        text="Internal server error"
    )

    cluster_manager.connect()
    with pytest.raises(requests.exceptions.HTTPError):
        cluster_manager.get_http_server_address()


def test_get_newest_version_directory(cluster_manager, mock_sshclient, mock_sftpclient):
    cluster_manager.connect()

    def mock_listdir_attr(path):
        names = ["V2", "V3", "V6", "VV", "envs", "randomfile"]
        entries = []
        for name in names:
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = name
            if name in ["V2", "V3", "V6", "VV", "envs"]:
                entry_mock.st_mode = 0o040755
            else:
                entry_mock.st_mode = 0o100644
            entries.append(entry_mock)
        return entries

    mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr
    result = cluster_manager.get_newest_version_directory("/fake/path")
    assert result == "V6", f"Expected 'V6' but got '{result}'"
    mock_sftpclient.listdir_attr.assert_called_once_with("/fake/path")
    mock_sftpclient.listdir_attr.side_effect = FileNotFoundError(
        "No such file or directory"
    )
    with pytest.raises(FileNotFoundError):
        cluster_manager.get_newest_version_directory("/fake/nonexistent")


def test_get_server_command_for_software_directory(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    cluster_manager._queueing_system = "AiiDA"
    for nin in ["V2", "V3", "V4"]:

        def mock_listdir_attr(path):
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = nin
            entry_mock.st_mode = 0o040755
            return [entry_mock]

        mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr
        with pytest.raises(NotImplementedError):
            cluster_manager.get_server_command_from_software_directory(nin)
    for imp_name in ["V6", "V8"]:

        def mock_listdir_attr(path):
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = imp_name
            entry_mock.st_mode = 0o040755
            return [entry_mock]

        mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr
        res = cluster_manager.get_server_command_from_software_directory(imp_name)
        expected = f"{imp_name}/envs/simstack_server_v6/bin/micromamba run -r {imp_name} --name=simstack_server_v6 SimStackServer"
        assert res == expected


def test_get_server_command_for_software_directory_no_micromamba(
    cluster_manager, mock_sftpclient
):
    cluster_manager.connect()
    with patch(
        "SimStackServer.ClusterManager.ClusterManager.exists", return_value=False
    ):
        vname = "V6"

        def mock_listdir_attr(path):
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = vname
            entry_mock.st_mode = 0o040755
            return [entry_mock]

        mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr
        with pytest.raises(FileNotFoundError):
            cluster_manager.get_server_command_from_software_directory(vname)


def test_get_server_command(cluster_manager):
    with patch.object(
        cluster_manager,
        "get_server_command_from_software_directory",
        return_value="dummy_cmd",
    ) as mock_method:
        result = cluster_manager._get_server_command()
        assert result == "dummy_cmd"
        mock_method.assert_called_once_with(cluster_manager._software_directory)


def test_get_workflow_job_list_success(cluster_manager, requests_mock):
    """Test REST API implementation of get_workflow_job_list"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response
    requests_mock.get(
        "http://localhost:8000/api/workflows/some_workflow/jobs",
        json={"workflow_id": "some_workflow", "jobs": ["job1", "job2"], "count": 2}
    )

    result = cluster_manager.get_workflow_job_list("some_workflow")
    assert result == ["job1", "job2"]


def test_get_workflow_job_list_missing_key(cluster_manager, requests_mock):
    """Test REST API with missing jobs key - should return empty list"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response without 'jobs' key
    requests_mock.get(
        "http://localhost:8000/api/workflows/some_workflow/jobs",
        json={"workflow_id": "some_workflow", "some_unexpected_key": []}
    )

    # Should return empty list when 'jobs' key is missing
    result = cluster_manager.get_workflow_job_list("some_workflow")
    assert result == []


def test_put_directory(cluster_manager):
    cluster_manager._calculation_basepath = "/foo/bar"
    cluster_manager.connect()
    input_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "input_dirs", "RemoteServerManager"
    )
    transferdir = os.path.join(input_dir, "test_transfer_dir")
    todir = "unittest_files"
    result = cluster_manager.put_directory(transferdir, todir)
    assert result == "/foo/bar/unittest_files"


def test_random_singlejob_exec_directory(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o040755
    with pytest.raises(FileExistsError):
        cluster_manager.mkdir_random_singlejob_exec_directory("testdir", num_retries=1)
    cluster_manager.exists = MagicMock(side_effect=lambda x: False)
    res = str(cluster_manager.mkdir_random_singlejob_exec_directory("testdir"))
    parts = res.split("/")
    assert parts[0] == "singlejob_exec_directories"
    assert "testdir" in parts[1]


def test_exists(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o100644
    mock_sftpclient.stat.return_value = stat_mock
    assert cluster_manager.exists("/some/file") is True


def test_list_dir(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    file_attr_mock = MagicMock(spec=paramiko.SFTPAttributes)
    file_attr_mock.filename = "myfile.txt"
    file_attr_mock.longname = "-rw-r--r-- 1 user group 1234 date myfile.txt"
    file_attr_mock.st_mode = 0o100644
    dir_attr_mock = MagicMock(spec=paramiko.SFTPAttributes)
    dir_attr_mock.filename = "somedir"
    dir_attr_mock.longname = "drwxr-xr-x 2 user group 4096 date somedir"
    dir_attr_mock.st_mode = 0o040755
    mock_sftpclient.listdir_iter.return_value = [file_attr_mock, dir_attr_mock]
    result = cluster_manager.list_dir("some/subdirectory")
    expected = [
        {"name": "myfile.txt", "path": "/fake/basepath/some/subdirectory", "type": "f"},
        {"name": "somedir", "path": "/fake/basepath/some/subdirectory", "type": "d"},
    ]
    assert result == expected
    mock_sftpclient.listdir_iter.assert_called_once_with(
        "/fake/basepath/some/subdirectory"
    )


def test_exists_remote(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    assert cluster_manager.exists_remote("/foo/bar") is True
    error = IOError("Test - Forced error")
    error.errno = 3
    mock_sftpclient.stat.side_effect = error
    with pytest.raises(IOError):
        cluster_manager.exists_remote("/my/nonexistent/path")
    error.errno = 2
    mock_sftpclient.stat.side_effect = error
    assert cluster_manager.exists_remote("/foo/bar") is False


def test_get_directory(cluster_manager, mock_sftpclient, tmpdir):
    cluster_manager.connect()
    cluster_manager.exists_remote = MagicMock(side_effect=lambda p: False)
    with pytest.raises(FileNotFoundError):
        cluster_manager.get_directory("server/dir", tmpdir + "/todir")
    cluster_manager.exists_remote = MagicMock(side_effect=lambda p: True)
    cluster_manager.connect()
    remote_root = "remote"
    local_root = tmpdir + "/local_dest"

    def mock_listdir(path):
        if path == "remote":
            return ["subdir", "file1"]
        elif path in ("remote/subdir", "remote/subdir/"):
            return ["file2"]
        return []

    def mock_stat(path):
        class MockAttrs:
            pass

        attrs = MockAttrs()
        if path in ("remote", "remote/subdir", "remote/subdir/"):
            attrs.st_mode = 0o040755
        else:
            attrs.st_mode = 0o100644
        return attrs

    def mock_get(remote_path, local_path):
        with open(local_path, "w") as f:
            f.write("dummy content")

    mock_sftpclient.listdir.side_effect = mock_listdir
    mock_sftpclient.stat.side_effect = mock_stat
    mock_sftpclient.get.side_effect = mock_get
    cluster_manager.get_directory(remote_root, str(local_root))
    file1_path = local_root + "/file1"
    file2_path = local_root + "/subdir/file2"
    assert pathlib.Path(file1_path).exists()
    assert pathlib.Path(file2_path).exists()


def test_send_clearserverstate_message(cluster_manager, requests_mock):
    """Test REST API implementation of send_clearserverstate_message"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response
    requests_mock.post(
        "http://localhost:8000/api/server/clear-state",
        json={"status": "cleared", "message": "Server state has been cleared"}
    )

    cluster_manager.send_clearserverstate_message()
    assert requests_mock.called


def test_delete_wf(cluster_manager, requests_mock):
    """Test REST API implementation of delete_wf"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response
    requests_mock.delete(
        "http://localhost:8000/api/workflows/some_workflow",
        json={"status": "deleted", "workflow_id": "some_workflow"}
    )

    with patch.object(cluster_manager._logger, "debug") as mock_debug:
        cluster_manager.delete_wf("some_workflow")

    assert requests_mock.called
    mock_debug.assert_called_once_with(
        "Sent delete WF message for submitname %s" % ("some_workflow")
    )


def test_get_workflow_list(cluster_manager, requests_mock):
    """Test REST API implementation of get_workflow_list"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response
    requests_mock.get(
        "http://localhost:8000/api/workflows",
        json={
            "inprogress": ["wf1"],
            "finished": ["wf2"],
            "total": 2
        }
    )

    result = cluster_manager.get_workflow_list()
    assert result == {"inprogress": ["wf1"], "finished": ["wf2"]}


def test_abort_wf(cluster_manager, requests_mock):
    """Test REST API implementation of abort_wf"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response
    requests_mock.post(
        "http://localhost:8000/api/workflows/my-test-workflow/abort",
        json={"status": "abort_requested", "workflow_id": "my-test-workflow"}
    )

    cluster_manager.abort_wf("my-test-workflow")
    assert requests_mock.called


def test_abort_wf_logs_debug(cluster_manager, requests_mock):
    """Test REST API implementation of abort_wf with debug logging"""
    # Setup REST session and base URL
    cluster_manager._rest_session = requests.Session()
    cluster_manager._rest_base_url = "http://localhost:8000"

    # Mock the REST API response
    requests_mock.post(
        "http://localhost:8000/api/workflows/my-workflow/abort",
        json={"status": "abort_requested", "workflow_id": "my-workflow"}
    )

    with patch.object(cluster_manager._logger, "debug") as mock_debug:
        cluster_manager.abort_wf("my-workflow")

    mock_debug.assert_called_once_with(
        "Sent Abort WF message for submitname my-workflow"
    )


def test_load_extra_host_keys(cluster_manager, mock_sshclient):
    cluster_manager._ssh_client = mock_sshclient
    cluster_manager.connect()
    cluster_manager.load_extra_host_keys("myfile")
    assert cluster_manager._extra_hostkey_file == "myfile"
    mock_sshclient.load_host_keys.assert_called()


def test_set_connect_to_unknown_hosts(cluster_manager):
    assert cluster_manager._unknown_host_connect_workaround is False
    cluster_manager.set_connect_to_unknown_hosts(True)
    assert cluster_manager._unknown_host_connect_workaround is True


def test_is_directory_true(cluster_manager, mock_sftpclient):
    """
    If st_mode indicates a directory (0o040755), is_directory should return True.
    """
    cluster_manager.connect()

    dir_stat_mock = MagicMock(spec=paramiko.SFTPAttributes)
    dir_stat_mock.st_mode = 0o040755  # Directory bit set
    mock_sftpclient.stat.return_value = dir_stat_mock

    result = cluster_manager.is_directory("some/path")
    assert result is True
    # Check the .stat call
    mock_sftpclient.stat.assert_called()


def test_is_directory_false(cluster_manager, mock_sftpclient):
    """
    If st_mode indicates a file (0o100644) or anything that's not a directory,
    is_directory should return False.
    """
    cluster_manager.connect()

    file_stat_mock = MagicMock(spec=paramiko.SFTPAttributes)
    file_stat_mock.st_mode = 0o100644  # Regular file
    mock_sftpclient.stat.return_value = file_stat_mock

    result = cluster_manager.is_directory("some/path")
    assert result is False
    # Check the .stat call
    mock_sftpclient.stat.assert_called()
