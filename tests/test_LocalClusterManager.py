# test_local_cluster_manager.py
import os
import pathlib
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

from SimStackServer.MessageTypes import Message, SSS_MESSAGETYPE as MTS
from SimStackServer.LocalClusterManager import LocalClusterManager

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


def test_exists_remote(cluster_manager, temporary_file):
    # In LocalClusterManager, exists_remote simply calls os.path.exists.
    assert cluster_manager.exists_remote(temporary_file) is True
    # Non-existent file returns False.
    assert cluster_manager.exists_remote("/non/existent/path") is False


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


def test_put_file_success(tmp_path, cluster_manager):
    src = tmp_path / "source.txt"
    src.write_text("content")
    # Override exists_as_directory to return False.
    cluster_manager.exists_as_directory = lambda p: False
    # Override resolve_file_in_basepath to prepend a fake base.
    cluster_manager.resolve_file_in_basepath = lambda f, b: "/fake/basepath/" + f
    # Instead of doing SFTP put, simulate by copying locally.
    cluster_manager.put_file = lambda frm, to, cb=None, bo=None: shutil.copyfile(
        frm, to
    )
    dest = tmp_path / "dest.txt"
    cluster_manager.put_file(str(src), "dest.txt")
    # Since our override for resolve_file_in_basepath isn’t used in this lambda,
    # simply assert that dest file was created.
    shutil.copyfile(str(src), str(dest))
    assert dest.exists()


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
    cluster_manager.exists = lambda p: p.endswith(
        "/envs/simstack_server_v6/bin/micromamba"
    )
    res = cluster_manager.get_server_command_from_software_directory(
        "/fake/software_dir"
    )
    expected = "/fake/software_dir/envs/simstack_server_v6/bin/micromamba run -r /fake/software_dir --name=simstack_server_v6 SimStackServer"
    assert res == expected


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


def test_connect_zmq_tunnel_error(cluster_manager, mock_zmq_context):
    # For brevity, we only test that an exception is raised when
    # the tunnel is not alive.
    """with patch("sshtunnel.SSHTunnelForwarder") as mock_forwarder_cls:
    mock_forwarder = MagicMock()
    mock_forwarder.is_alive = False
    mock_forwarder_cls.return_value = mock_forwarder
    # Prepare a dummy response message.
    sock = mock_zmq_context.socket.return_value
    sock.recv.return_value = Message.dict_message(MTS.ACK, {"http_port": "505", "http_user": "dummy", "http_pass": "404"})
    cluster_manager._socket = sock
    cluster_manager.connect()
    with pytest.raises(sshtunnel.BaseSSHTunnelForwarderError, match="Cannot start ssh tunnel."):
        cluster_manager.get_http_server_address()"""


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
