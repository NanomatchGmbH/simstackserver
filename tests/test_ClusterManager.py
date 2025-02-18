# test_cluster_manager.py
import pathlib

import pytest
from unittest.mock import MagicMock, patch

import paramiko
import sshtunnel
import zmq

from SimStackServer import ClusterManager
from SimStackServer.MessageTypes import Message
from SimStackServer.MessageTypes import SSS_MESSAGETYPE as MTS
from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError


@pytest.fixture
def mock_sshclient():
    """Creates a MagicMock for paramiko.SSHClient."""
    mock_ssh = MagicMock(spec=paramiko.SSHClient)
    transport = MagicMock()
    transport.is_active.return_value = True
    mock_ssh.get_transport.return_value = transport

    mock_sftp = MagicMock(spec=paramiko.SFTPClient)
    mock_ssh.open_sftp.return_value = mock_sftp
    return mock_ssh


@pytest.fixture
def mock_sftpclient(mock_sshclient):
    sftp_mock = mock_sshclient.open_sftp()

    # Mock the return value of .stat() with a paramiko.SFTPAttributes-like object
    stat_mock = MagicMock(spec=paramiko.SFTPAttributes)
    stat_mock.st_mode = 0o040755  # For example, a directory bit
    sftp_mock.stat.return_value = stat_mock

    # Mock the return value of .listdir_attr() to return a list of SFTPAttributes-like objects
    def _mock_listdir_attr(path):
        file_attr = MagicMock(spec=paramiko.SFTPAttributes)
        file_attr.filename = "testfile"
        file_attr.st_mode = 0o100644  # For example, a regular file bit
        return [file_attr]

    sftp_mock.listdir_attr.side_effect = _mock_listdir_attr

    return sftp_mock


@pytest.fixture
def mock_sshtunnel_forwarder():
    """Creates a MagicMock for sshtunnel.SSHTunnelForwarder."""
    mock_forwarder = MagicMock(spec=sshtunnel.SSHTunnelForwarder)
    mock_forwarder.is_alive = False
    return mock_forwarder


@pytest.fixture
def mock_zmq_context():
    """Creates a MagicMock for zmq.Context and zmq.Socket."""
    mock_context = MagicMock(spec=zmq.Context)
    mock_socket = MagicMock(spec=zmq.Socket)
    mock_context.socket.return_value = mock_socket
    return mock_context


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
    Creates a ClusterManager with the paramiko, sshtunnel, and zmq classes all patched.
    We inject our MagicMock instances as the return_value of those patched classes.
    """
    # Whenever someone does paramiko.SSHClient(), return our mock_sshclient
    mock_sshclient_class.return_value = mock_sshclient

    # Whenever someone constructs a sshtunnel.SSHTunnelForwarder, return our mock_sshtunnel_forwarder
    mock_sshtunnel_forwarder_class.return_value = mock_sshtunnel_forwarder

    # Whenever someone calls zmq.Context.instance(), return our mock_zmq_context
    mock_zmq_context_class.return_value = mock_zmq_context

    # Now we create the real ClusterManager
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


def test_init(cluster_manager):
    """
    Test basic initialization parameters.
    """
    assert cluster_manager._url == "fake-url"
    assert cluster_manager._port == 22
    assert cluster_manager._user == "fake-user"
    assert cluster_manager._calculation_basepath == "/fake/basepath"
    assert cluster_manager._default_queue == "fake-queue"
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
    """
    Test that _dummy_callback prints the expected output.
    """
    # Call the method under test
    cluster_manager._dummy_callback(50, 100)

    # Capture everything that was printed to stdout/stderr
    captured = capsys.readouterr()

    # Assert that the printed output contains the expected text
    # In this case, "50.0 % done"
    assert "50 % done" in captured.out.strip()


def test_get_ssh_url(cluster_manager):
    assert cluster_manager.get_ssh_url() == "fake-user@fake-url:22"


def test_connect_success(cluster_manager, mock_sshclient, mock_sftpclient):
    """
    Test that connect() calls paramiko.SSHClient.connect and opens SFTP.
    """
    mock_sftpclient.st_mode = 0
    cluster_manager.connect()
    mock_sshclient.connect.assert_called_once_with(
        "fake-url", 22, username="fake-user", key_filename=None, compress=True
    )
    assert cluster_manager.is_connected() is True
    mock_sftpclient.get_channel.assert_called_once()


def test_is_connected_false_when_transport_none(cluster_manager, mock_sshclient):
    """
    If get_transport() returns None, is_connected should be False.
    """
    mock_sshclient.get_transport.return_value = None
    assert cluster_manager.is_connected() is False


def test_disconnect(
    cluster_manager,
    mock_zmq_context,
    mock_sshclient,
    mock_sftpclient,
    mock_sshtunnel_forwarder,
):
    """
    #Test that disconnect() closes the SFTP client and SSH client.
    """
    # Simulate an open tunnel

    mock_sshtunnel_forwarder.is_alive = True

    """fake_stdout = ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.3.4"]
    fake_stderr = []
    # Patch exec_command to return mocked stdout/stderr
    cluster_manager.exec_command = MagicMock(return_value=(fake_stdout, fake_stderr))

    # We'll need a mock socket for ZMQ so we don't do actual network calls:
    mock_socket = mock_zmq_context.socket.return_value
    mock_socket.recv.return_value = Message.dict_message(MTS.CONNECT, {"info": "connected"})
    with patch("zmq.ssh.tunnel.paramiko_tunnel") as mock_paramiko_tunnel:
        # paramiko_tunnel normally returns (new_url, tunnel),
        # so let's return a dummy URL and a mock tunnel object.
        mock_tunnel = MagicMock()
        mock_paramiko_tunnel.return_value = ("tcp://127.0.0.1:5555", mock_tunnel)

        # Make the normal connect (SSH) call; it will run our patch
        cluster_manager.connect()
        cluster_manager.connect_zmq_tunnel("some_fake_command", connect_http=False)"""

    cluster_manager.connect()
    cluster_manager.disconnect()

    mock_sftpclient.close.assert_called_once()
    mock_sshclient.close.assert_called_once()

    # mock_sshtunnel_forwarder.stop.assert_called_once()


def test_put_file_success(cluster_manager, mock_sftpclient, tmp_path):
    """
    #Test that put_file calls sftp_client.put with correct arguments.
    """
    local_file = tmp_path / "local.txt"
    local_file.write_text("hello world")

    cluster_manager.connect()
    cluster_manager.put_file(str(local_file), "remote.txt")

    mock_sftpclient.put.assert_called_once()
    put_args, put_kwargs = mock_sftpclient.put.call_args
    assert put_args[0] == str(local_file)
    # ToDo: Not sure this should be the output, tbh
    assert put_args[1] == "/fake/basepath/remote.txt/local.txt"


def test_put_file_not_found(cluster_manager, mock_sftpclient):
    """
    #put_file should raise FileNotFoundError if local file does not exist.
    """
    with pytest.raises(FileNotFoundError):
        cluster_manager.put_file("non_existent_file.txt", "remote.txt")


def test_get_file_success(cluster_manager, mock_sftpclient, tmp_path):
    """
    #Test that get_file calls sftp_client.get with correct arguments.
    """
    local_dest = tmp_path / "downloaded.txt"
    cluster_manager.connect()
    cluster_manager.get_file("remote.txt", str(local_dest))

    mock_sftpclient.get.assert_called_once_with(
        "/fake/basepath/remote.txt", str(local_dest), None
    )


def test_exists_as_directory_true(cluster_manager, mock_sftpclient):
    """
    #exists_as_directory should return True for a directory (mocked).
    """
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o040755  # Directory bit
    mock_sftpclient.stat.return_value = stat_mock

    res = cluster_manager.exists_as_directory("/fake/dir")
    assert res is True


def test_exists_as_directory_not_dir(cluster_manager, mock_sftpclient, tmp_path):
    """
    #exists_as_directory should raise SSHExpectedDirectoryError if it is not a directory.
    """
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o100755  # Regular file
    mock_sftpclient.stat.return_value = stat_mock

    with pytest.raises(SSHExpectedDirectoryError):
        cluster_manager.exists_as_directory("/test/dir")


def test_exists_as_directory_not_found(cluster_manager, mock_sftpclient):
    """
    #If stat() raises FileNotFoundError, exists_as_directory should return False.
    """
    cluster_manager.connect()
    mock_sftpclient.stat.side_effect = FileNotFoundError

    res = cluster_manager.exists_as_directory("/fake/dir")
    assert res is False


def test_exists(cluster_manager, mock_sftpclient):
    """
    #If path is not a directory but does not raise FileNotFoundError,
    #test_exists will still return True (since there's a file).
    """
    # If it's a file, exists_as_directory() will raise SSHExpectedDirectoryError.
    # Then the code for exists() just catches that and returns True.
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o100755  # File
    mock_sftpclient.stat.return_value = stat_mock
    assert cluster_manager.exists("/some/file") is True


def test_mkdir_p_creates_subdirectories(cluster_manager, mock_sftpclient):
    """
    #Test mkdir_p calls sftp_client.mkdir for each subdirectory that does not exist.
    """

    # Mock out exists_as_directory so that it returns False for the final subdir
    # but True for partial. We'll simplify here and let everything be "non-existent".
    def side_effect(path_str):
        # Return False the first time, so it tries to create
        return False

    cluster_manager.exists_as_directory = MagicMock(side_effect=side_effect)

    cluster_manager.connect()
    mydir = cluster_manager.mkdir_p(pathlib.Path("foo/bar/baz"))
    assert mydir == "foo/bar/baz"
    # We expect mkdir to have been called 3 times:
    # /fake/basepath/foo, /fake/basepath/foo/bar, /fake/basepath/foo/bar/baz
    expected_calls = [
        ("fake",),
        ("fake/basepath",),
        ("/fake/basepath/foo",),
        ("/fake/basepath/foo/bar",),
        ("/fake/basepath/foo/bar/baz",),
    ]
    actual_calls = [call[0] for call in mock_sftpclient.mkdir.call_args_list]
    assert actual_calls == expected_calls


def test_rmtree(cluster_manager, mock_sftpclient):
    """
    #Test rmtree calls remove on all files and rmdir on directories recursively.
    #We simulate a small directory tree.
    """
    cluster_manager.connect()

    # We'll pretend /fake/basepath/testdir is a directory that has
    # subfile1 (file), subdir1 (dir) -> subfile2 (file)
    def mock_listdir_attr(path):
        if path == "/fake/basepath/testdir":
            return [
                MagicMock(filename="subfile1", st_mode=0o100755),  # file
                MagicMock(filename="subdir1", st_mode=0o040755),  # dir
            ]
        elif path == "/fake/basepath/testdir/subdir1":
            return [
                MagicMock(filename="subfile2", st_mode=0o100755),  # file
            ]
        return []

    mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr

    # Mock out exists_as_directory to always True for these paths
    cluster_manager.exists_as_directory = MagicMock(return_value=True)

    cluster_manager.rmtree("testdir")

    # We expect remove calls to subfile1 and subfile2, and rmdir calls to subdir1 and testdir
    mock_sftpclient.remove.assert_any_call("/fake/basepath/testdir/subfile1")
    mock_sftpclient.remove.assert_any_call("/fake/basepath/testdir/subdir1/subfile2")
    mock_sftpclient.rmdir.assert_any_call("/fake/basepath/testdir/subdir1")
    mock_sftpclient.rmdir.assert_any_call("/fake/basepath/testdir")


def test_connect_zmq_tunnel(cluster_manager, mock_zmq_context):
    """
    #Test connect_zmq_tunnel logic:
    #it should call exec_command on the remote to start the server,
    #parse the result, and connect to the ZMQ socket with the returned port & password.
    """
    fake_stdout = ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.3.4"]
    fake_stderr = []
    # Patch exec_command to return mocked stdout/stderr
    cluster_manager.exec_command = MagicMock(return_value=(fake_stdout, fake_stderr))

    # We'll need a mock socket for ZMQ so we don't do actual network calls:
    mock_socket = mock_zmq_context.socket.return_value
    mock_socket.recv.return_value = Message.dict_message(
        MTS.CONNECT, {"info": "connected"}
    )
    with patch("zmq.ssh.tunnel.paramiko_tunnel") as mock_paramiko_tunnel:
        # paramiko_tunnel normally returns (new_url, tunnel),
        # so let's return a dummy URL and a mock tunnel object.
        mock_tunnel = MagicMock()
        mock_paramiko_tunnel.return_value = ("tcp://127.0.0.1:5555", mock_tunnel)

        # Make the normal connect (SSH) call; it will run our patch
        cluster_manager.connect()
        cluster_manager.connect_zmq_tunnel("some_fake_command", connect_http=False)

    # Check that we set the correct plain_username/password
    mock_socket = mock_zmq_context.socket.return_value
    assert mock_socket.plain_username == b"simstack_client"
    assert mock_socket.plain_password == b"secretkey"

    # We also expect a .send call to send a CONNECT message
    mock_socket.send.assert_called()
    # And a .recv call to read the server response
    mock_socket.recv.assert_called()


def test_send_shutdown_message(cluster_manager, mock_zmq_context):
    """
    #Test that send_shutdown_message sends a shutdown message via ZMQ.
    """
    # Mock out the reply from the server
    mock_socket = mock_zmq_context.socket.return_value
    # Fake an ACK response for the shutdown
    mock_socket.recv.return_value = Message.dict_message(
        MTS.ACK, {"info": "acknowledge WF submission"}
    )
    cluster_manager._socket = mock_socket
    cluster_manager.connect()
    cluster_manager.send_shutdown_message()

    assert mock_socket.send.called
    assert mock_socket.recv.called
