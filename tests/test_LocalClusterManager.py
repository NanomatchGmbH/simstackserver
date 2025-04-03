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
import zmq

from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError
from SimStackServer.MessageTypes import Message, SSS_MESSAGETYPE as MTS
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
def mock_zmq_context():
    """Return a MagicMock for a zmq.Context and its socket."""
    ctx = MagicMock(spec=zmq.Context)
    sock = MagicMock(spec=zmq.Socket)
    ctx.socket.return_value = sock
    return ctx


@pytest.fixture
@patch("paramiko.SSHClient", autospec=True)
@patch("sshtunnel.SSHTunnelForwarder", autospec=True)
@patch("zmq.Context.instance", autospec=True)
def cluster_manager(
    mock_zmq_context_class,
    mock_sshtunnel_forwarder_class,
    mock_sshclient_class,
    mock_sshclient,
    mock_sftpclient,
    mock_sshtunnel_forwarder,
    mock_zmq_context,
):
    """
    Return a LocalClusterManager instance with patched dependencies.
    """
    # Whenever SSHClient() is called, return our mock.
    mock_sshclient_class.return_value = mock_sshclient
    # Whenever SSHTunnelForwarder is constructed, return our mock.
    mock_sshtunnel_forwarder_class.return_value = mock_sshtunnel_forwarder
    # Whenever zmq.Context.instance() is called, return our mock context.
    mock_zmq_context_class.return_value = mock_zmq_context

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
        cluster_manager, "connect_ssh_and_zmq_if_disconnected"
    ) as mock_conn, patch.object(cluster_manager, "disconnect") as mock_disconn:
        with cluster_manager.connection_context() as result:
            assert result is None
            mock_conn.assert_not_called()
        mock_disconn.assert_called_once()


def test_connection_context_not_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=False)
    with patch.object(
        cluster_manager,
        "connect_ssh_and_zmq_if_disconnected",
        return_value="tunnel_info",
    ) as mock_conn, patch.object(cluster_manager, "disconnect") as mock_disconn:
        with cluster_manager.connection_context() as result:
            assert result == "tunnel_info"
            mock_conn.assert_called_once_with(connect_http=False, verbose=False)
        mock_disconn.assert_called_once()


def test_connect_ssh_and_zmq_if_disconnected_already_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=True)
    with patch.object(cluster_manager, "connect") as mock_connect, patch.object(
        cluster_manager, "connect_zmq_tunnel"
    ) as mock_tunnel, patch.object(cluster_manager, "_get_server_command") as mock_cmd:
        cluster_manager.connect_ssh_and_zmq_if_disconnected(
            connect_http=False, verbose=False
        )
    mock_connect.assert_not_called()
    mock_cmd.assert_not_called()
    mock_tunnel.assert_not_called()


def test_connect_ssh_and_zmq_if_disconnected_not_connected(cluster_manager):
    cluster_manager.is_connected = MagicMock(return_value=False)
    with patch.object(cluster_manager, "connect") as mock_connect, patch.object(
        cluster_manager, "_get_server_command", return_value="cmd"
    ) as mock_cmd, patch.object(cluster_manager, "connect_zmq_tunnel") as mock_tunnel:
        cluster_manager.connect_ssh_and_zmq_if_disconnected(
            connect_http=True, verbose=True
        )
    mock_connect.assert_called_once()
    mock_cmd.assert_called_once()
    mock_tunnel.assert_called_once_with("cmd", connect_http=True, verbose=True)


def test_disconnect_all_set(cluster_manager):
    # Create mocks for all connections.
    mock_socket = MagicMock()
    mock_sftp = MagicMock()
    mock_ssh = MagicMock()
    mock_http = MagicMock()
    mock_http._server_list = [MagicMock(), MagicMock()]
    for srv in mock_http._server_list:
        srv.timeout = None
    mock_http._transport = MagicMock()
    mock_zmq = MagicMock()
    mock_zmq.kill = MagicMock()
    cluster_manager._socket = mock_socket
    cluster_manager._sftp_client = mock_sftp
    cluster_manager._ssh_client = mock_ssh
    cluster_manager._http_server_tunnel = mock_http
    cluster_manager._zmq_ssh_tunnel = mock_zmq
    cluster_manager.disconnect()
    mock_socket.close.assert_called_once()
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


def test_get_http_server_address_port_error(cluster_manager, mock_zmq_context):
    # For brevity, we only test that an exception is raised when
    # the tunnel is not alive.
    with patch("sshtunnel.SSHTunnelForwarder") as mock_forwarder_cls:
        mock_forwarder = MagicMock()
        mock_forwarder.is_alive = False
        mock_forwarder_cls.return_value = mock_forwarder
        # Prepare a dummy response message.
        sock = mock_zmq_context.socket.return_value
        sock.recv.return_value = Message.dict_message(
            MTS.ACK, {"http_user": "dummy", "http_pass": "404"}
        )
        cluster_manager._socket = sock
        cluster_manager.connect()
        with pytest.raises(ConnectionError):
            cluster_manager.get_http_server_address()
        sock.recv.return_value = Message.dict_message(
            MTS.ACK, {"http_port": "505", "http_user": "dummy", "http_pass": "404"}
        )
        cluster_manager._socket = sock
        cluster_manager.connect()
        assert (
            cluster_manager.get_http_server_address()
            == "http://dummy:404@localhost:505"
        )


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


def test_get_workflow_job_list(cluster_manager, mock_zmq_context):
    sock = mock_zmq_context.socket.return_value
    cluster_manager._socket = sock
    cluster_manager._recv_message = MagicMock(
        return_value=(MTS.ACK, {"list_of_jobs": ["job1", "job2"]})
    )
    result = cluster_manager.get_workflow_job_list("wf")
    expected_send = Message.list_jobs_of_wf_message(workflow_submit_name="wf")
    sock.send.assert_called_once_with(expected_send)
    cluster_manager._recv_message.assert_called_once()
    assert result == ["job1", "job2"]

    cluster_manager._recv_message = MagicMock(
        return_value=(MTS.ACK, {"somkey": "somevalue"})
    )
    with pytest.raises(ConnectionError):
        cluster_manager.get_workflow_job_list("wf")


def test_abort_wf(cluster_manager, mock_zmq_context):
    sock = mock_zmq_context.socket.return_value
    cluster_manager._socket = sock
    with patch.object(cluster_manager, "_recv_ack_message") as mock_ack:
        cluster_manager.abort_wf("wf123")
    expected_msg = Message.abort_wf_message("wf123")
    sock.send.assert_called_once_with(expected_msg)
    mock_ack.assert_called_once()


def test_send_clearserverstate_message(cluster_manager, mock_zmq_context):
    sock = mock_zmq_context.socket.return_value
    cluster_manager._socket = sock
    with patch.object(cluster_manager, "_recv_ack_message") as mock_ack:
        cluster_manager.send_clearserverstate_message()
    sock.send.assert_called_once_with(Message.clearserverstate_message())
    mock_ack.assert_called_once()


def test_delete_wf(cluster_manager, mock_zmq_context):
    sock = mock_zmq_context.socket.return_value
    cluster_manager._socket = sock
    with patch.object(cluster_manager, "_recv_ack_message") as mock_ack, patch.object(
        cluster_manager._logger, "debug"
    ) as mock_debug:
        cluster_manager.delete_wf("wf_del")
    sock.send.assert_called_once_with(Message.delete_wf_message("wf_del"))
    mock_ack.assert_called_once()
    mock_debug.assert_called_once_with(
        "Sent delete WF message for submitname %s" % ("wf_del")
    )


def test_get_workflow_list(cluster_manager, mock_zmq_context):
    sock = mock_zmq_context.socket.return_value
    cluster_manager._socket = sock
    with patch.object(
        cluster_manager,
        "_recv_message",
        return_value=(MTS.ACK, {"workflows": ["wf1", "wf2"]}),
    ) as mock_recv:
        result = cluster_manager.get_workflow_list()
    sock.send.assert_called_once_with(Message.list_wfs_message())
    mock_recv.assert_called_once()
    assert result == ["wf1", "wf2"]

    cluster_manager._filegen_mode = True
    assert cluster_manager.get_workflow_list() == []


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
    mock_http_server_tunnel.is_alive = False
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


# Test for submit_single_job
def test_submit_single_job(cluster_manager, mock_zmq_context):
    # Use the mock socket from the zmq context fixture.
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket
    with patch(
        "SimStackServer.MessageTypes.Message.submit_single_job_message",
        return_value="test_message",
    ):  # Patch _recv_ack_message so we don't have to simulate a real ACK.
        with patch.object(cluster_manager, "_recv_ack_message") as mock_recv_ack:
            wfem = {"job": "details"}  # Dummy job details
            cluster_manager.submit_single_job(wfem)

    # Check that the socket sent the correct message.
    expected_msg = "test_message"
    mock_socket.send.assert_called_once_with(expected_msg)
    # And that the ack method was called.
    mock_recv_ack.assert_called_once()


# Test for send_jobstatus_message
def test_send_jobstatus_message(cluster_manager, mock_zmq_context):
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    wfem_uid = "job123"
    # Create a dummy response that _recv_message should return.
    dummy_response = (MTS.ACK, {"job_status": "running"})
    with patch.object(
        cluster_manager, "_recv_message", return_value=dummy_response
    ) as mock_recv:
        result = cluster_manager.send_jobstatus_message(wfem_uid)

    expected_msg = Message.getsinglejobstatus_message(wfem_uid=wfem_uid)
    mock_socket.send.assert_called_once_with(expected_msg)
    mock_recv.assert_called_once()
    # The function should return the message part of the response.
    assert result == {"job_status": "running"}


# Test for send_abortsinglejob_message
def test_send_abortsinglejob_message(cluster_manager, mock_zmq_context):
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    wfem_uid = "job123"
    # Patch _recv_message to simulate receiving an answer.
    with patch.object(cluster_manager, "_recv_message") as mock_recv:
        cluster_manager.send_abortsinglejob_message(wfem_uid)

    expected_msg = Message.abortsinglejob_message(wfem_uid=wfem_uid)
    mock_socket.send.assert_called_once_with(expected_msg)
    mock_recv.assert_called_once()


# Test for send_noop_message
def test_send_noop_message(cluster_manager, mock_zmq_context):
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    with patch.object(cluster_manager, "_recv_ack_message") as mock_recv_ack:
        cluster_manager.send_noop_message()

    expected_msg = Message.noop_message()
    mock_socket.send.assert_called_once_with(expected_msg)
    mock_recv_ack.assert_called_once()


# Test for send_shutdown_message
def test_send_shutdown_message(cluster_manager, mock_zmq_context):
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    with patch.object(cluster_manager, "_recv_ack_message") as mock_recv_ack:
        cluster_manager.send_shutdown_message()

    expected_msg = Message.shutdown_message()
    mock_socket.send.assert_called_once_with(expected_msg)
    mock_recv_ack.assert_called_once()


def test_submit_wf(cluster_manager, tmpfileWaNoXml, mock_zmq_context):
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket
    with patch.object(cluster_manager, "_recv_ack_message") as mock_recv_ack:
        with patch(
            "SimStackServer.MessageTypes.Message.submit_wf_message",
            return_value="test_message",
        ):  # Patch _recv_ack_message so we don't have to simulate a real ACK.
            cluster_manager.submit_wf(str(tmpfileWaNoXml))
            expected_msg = "test_message"
            mock_socket.send.assert_called_once_with(expected_msg)
            # And that the ack method was called.
            mock_recv_ack.assert_called_once()


def test_submit_wf_filegen_mode(cluster_manager):
    # Force file-generation mode so the workflow branch is taken.
    cluster_manager._filegen_mode = True
    # Override resolve_file_in_basepath to return a known value.
    cluster_manager.resolve_file_in_basepath = (
        lambda filename, base_override: "resolved.xml"
    )

    # Create a dummy workflow object.
    dummy_workflow = MagicMock()
    # Simulate that the workflow's "storage" field is a relative path.
    dummy_workflow.get_field_value.return_value = "relative_storage"
    dummy_workflow.jobloop.return_value = None

    # Create a dummy WorkflowManager instance.
    dummy_wm = MagicMock()
    dummy_wm.restore.return_value = None
    dummy_wm.add_finished_workflow.return_value = None
    dummy_wm.backup_and_save.return_value = None

    with patch(
        "SimStackServer.WorkflowModel.Workflow.new_instance_from_xml",
        return_value=dummy_workflow,
    ) as wf_patch:
        with patch(
            "SimStackServer.LocalClusterManager.WorkflowManager", autospec=True
        ) as WM_patch:
            WM_patch.return_value = dummy_wm

            # Now call submit_wf.
            cluster_manager.submit_wf("workflow.xml")

            # Verify that the workflow was instantiated with the resolved filename.
            wf_patch.assert_called_once_with("resolved.xml")

            # Verify that the workflow's storage was checked and then updated.
            dummy_workflow.get_field_value.assert_called_once_with("storage")
            # Since get_field_value returns "relative_storage" (not starting with "/"),
            # the code should update the storage field to be absolute by prepending Path.home()
            dummy_workflow.set_field_value.assert_called_once_with(
                "storage", str(pathlib.Path.home() / "relative_storage")
            )

            # Verify that the WorkflowManager instance was created and its methods were called.
            dummy_wm.restore.assert_called_once()
            dummy_wm.add_finished_workflow.assert_called_once_with("resolved.xml")
            dummy_workflow.jobloop.assert_called_once()
            dummy_wm.backup_and_save.assert_called_once()


def test_recv_ack_message_success(cluster_manager):
    # Simulate a successful ACK response.
    dummy_message = {"status": "ok"}
    cluster_manager._recv_message = lambda: (MTS.ACK, dummy_message)

    # This call should complete without raising an exception.
    # _recv_ack_message doesn't return a value, so we just call it.
    cluster_manager._recv_ack_message()


def test_recv_ack_message_failure(cluster_manager):
    # Simulate a response that is not an ACK.
    dummy_message = {"error": "failed"}
    cluster_manager._recv_message = lambda: (MTS.CONNECT, dummy_message)

    with pytest.raises(
        ConnectionAbortedError,
        match="Did not receive acknowledge after workflow submission.",
    ):
        cluster_manager._recv_ack_message()


def test_connect_zmq_tunnel_success(cluster_manager, mock_zmq_context):
    """
    Test a successful execution of connect_zmq_tunnel() when:
      - _queueing_system is not "Internal", "AiiDA" or "Filegenerator"
      - _extra_config starts with "None" (so extra_conf_mode is False)
      - exec_command returns valid output simulating:
            "dummy 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"
        so that:
            password = "secretkey" and port = 555.
      - Message.unpack returns (MTS.CONNECT, {...})
      - connect_http is False so get_http_server_address() is not called.
    """
    cluster_manager._queueing_system = "Filegenerator"
    assert cluster_manager.connect_zmq_tunnel("some command") is None
    cluster_manager._queueing_system = "pbs"
    cluster_manager._extra_config = "SomeConfigNotNone"
    cluster_manager.exists = lambda x: False
    with pytest.raises(ConnectionError):
        cluster_manager.connect_zmq_tunnel("some command")

    # Set up the instance so that the queue branch is triggered.
    cluster_manager._queueing_system = "pbs"  # not Internal/AiiDA/Filegenerator
    cluster_manager.exists = lambda x: True  # Dummy; not used in this branch

    # Prepare dummy stdout/stderr from exec_command.
    # For the first exec_command call (for the queue check), the command is built as:
    #   "bash -c \"which qsub\""
    # We simulate its output as a valid line:
    #   "dummy 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"
    dummy_stdout = ["dummy 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"]
    dummy_stderr = []
    # Have exec_command always return these values.
    cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)

    # Patch time.sleep to avoid delays.
    with patch("time.sleep", return_value=None):
        with patch(
            "SimStackServer.MessageTypes.Message.unpack",
            return_value=(MTS.CONNECT, {"dummy": "data"}),
        ):
            # Ensure that _context is our mocked zmq context.
            cluster_manager._context = mock_zmq_context
            # Get the mock socket from the context.
            mock_socket = mock_zmq_context.socket.return_value
            # When socket.recv() is called, return some dummy bytes.
            mock_socket.recv.return_value = b"dummy_recv_data"
            dummy_stdout = ["dummy 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"]
            dummy_stderr = []
            # Have exec_command always return these values.
            cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)

            # Call the function with connect_http False.
            with pytest.raises(ConnectionError):
                cluster_manager.connect_zmq_tunnel(
                    "some_command", connect_http=False, verbose=True
                )

            dummy_stdout = ["qsub\n"]
            dummy_stderr = []
            # Have exec_command always return these values.
            cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)
            with pytest.raises(ConnectionError):
                cluster_manager.connect_zmq_tunnel(
                    "some_command", connect_http=False, verbose=True
                )

            cluster_manager._queueing_system = "Internal"
            dummy_stdout = ["qsub 0 555 secretkey SERVER,6,ZMQ,4.2.4\n"]
            dummy_stderr = []
            cluster_manager.connect_zmq_tunnel(
                "some_command", connect_http=False, verbose=True
            )
            with patch.object(SimStackServer, "__version__", "8.1.1"):
                cluster_manager.connect_zmq_tunnel(
                    "some_command", connect_http=False, verbose=True
                )
            mock_socket.connect.assert_called_with("tcp://127.0.0.1:555")
            assert mock_socket.plain_username == b"simstack_client"
            assert mock_socket.plain_password == b"secretkey"

            dummy_stdout = ["qsub 0 555 secretkey NOSERVER,6,ZMQ,4.3.4\n"]
            dummy_stderr = []
            cluster_manager.connect_zmq_tunnel(
                "some_command", connect_http=False, verbose=True
            )
            mock_socket.connect.assert_called_with("tcp://127.0.0.1:555")
            assert mock_socket.plain_username == b"simstack_client"
            assert mock_socket.plain_password == b"secretkey"

            with patch.object(
                cluster_manager, "get_http_server_address", return_value="1.0.0.1"
            ):
                cluster_manager.connect_zmq_tunnel(
                    "some_command", connect_http=True, verbose=True
                )
            mock_socket.connect.assert_called_with("tcp://127.0.0.1:555")
            assert mock_socket.plain_username == b"simstack_client"
            assert mock_socket.plain_password == b"secretkey"
            with patch.object(
                cluster_manager, "get_http_server_address", side_effect=Exception
            ):
                with pytest.raises(Exception):
                    cluster_manager.connect_zmq_tunnel(
                        "some_fake_command", connect_http=True, verbose=True
                    )

            # repeat with extra_conf_mode false
            cluster_manager._extra_config = "None"  # forces extra_conf_mode = False
            cluster_manager._queueing_system = "pbs"
            # Call the function with connect_http False.
            with pytest.raises(ConnectionError):
                cluster_manager.connect_zmq_tunnel(
                    "some_command", connect_http=False, verbose=True
                )


def test_connect_zmq_tunnel_ConnectError(cluster_manager, mock_zmq_context):
    with patch("time.sleep", return_value=None):
        with patch(
            "SimStackServer.MessageTypes.Message.unpack",
            return_value=(MTS.LISTWFS, {"dummy": "data"}),
        ):
            # Ensure that _context is our mocked zmq context.
            cluster_manager._context = mock_zmq_context
            # Get the mock socket from the context.
            mock_socket = mock_zmq_context.socket.return_value
            # When socket.recv() is called, return some dummy bytes.
            mock_socket.recv.return_value = b"dummy_recv_data"

            cluster_manager._queueing_system = "Internal"

            dummy_stdout = ["qsub 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"]
            dummy_stderr = []
            cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)
            with pytest.raises(ConnectionError):
                cluster_manager.connect_zmq_tunnel(
                    "some_command", connect_http=False, verbose=True
                )


def test_connect_zmq_tunnel_retry_loop(cluster_manager, mock_zmq_context, capsys):
    with patch(
        "SimStackServer.MessageTypes.Message.unpack",
        return_value=(MTS.LISTWFS, {"dummy": "data"}),
    ):
        # Ensure that _context is our mocked zmq context.
        cluster_manager._context = mock_zmq_context
        # Get the mock socket from the context.
        mock_socket = mock_zmq_context.socket.return_value
        # Force recv to always raise zmq.error.Again.
        mock_socket.recv.side_effect = zmq.error.Again("timeout")

        cluster_manager._queueing_system = "Internal"

        dummy_stdout = ["qsub 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"]
        dummy_stderr = []
        cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)

        # Patch time.sleep so that it doesn't actually delay.
        with patch("time.sleep", return_value=None) as mock_sleep:
            with pytest.raises(Exception):
                cluster_manager.connect_zmq_tunnel(
                    "dummy_command", connect_http=False, verbose=True
                )

        # Assert that time.sleep was called 11 times.
        assert mock_sleep.call_count == 11

        # Optionally, capture printed output and assert that the retry message was printed 10 times.
        output = capsys.readouterr().out
        retry_message = "Port was not setup in time. Trying to connect again. Trial"
        # Check that the retry message appears 10 times.
        assert output.count(retry_message) == 10


def test_connect_zmq_tunnel_stderr(cluster_manager, mock_zmq_context):
    with patch(
        "SimStackServer.MessageTypes.Message.unpack",
        return_value=(MTS.CONNECT, {"dummy": "data"}),
    ):
        # Ensure that _context is our mocked zmq context.
        cluster_manager._context = mock_zmq_context
        # Get the mock socket from the context.
        mock_socket = mock_zmq_context.socket.return_value
        # When socket.recv() is called, return some dummy bytes.
        mock_socket.recv.return_value = b"dummy_recv_data"

        cluster_manager._queueing_system = "Internal"

        dummy_stdout = ["qsub 0 555 secretkey SERVER,6,ZMQ,4.3.4\n"]
        dummy_stderr = ["FAIL"]
        cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)

        # Patch time.sleep so that it doesn't actually delay.
        with patch("time.sleep", return_value=None):
            with pytest.raises(ConnectionError):
                cluster_manager.connect_zmq_tunnel(
                    "dummy_command", connect_http=False, verbose=True
                )

        dummy_stdout = []
        dummy_stderr = []
        cluster_manager.exec_command = lambda cmd: (dummy_stdout, dummy_stderr)

        # Patch time.sleep so that it doesn't actually delay.
        with patch("time.sleep", return_value=None):
            with pytest.raises(ConnectionError):
                cluster_manager.connect_zmq_tunnel(
                    "dummy_command", connect_http=False, verbose=True
                )


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
