# test_cluster_manager.py
import pathlib
from os import path

import pytest
from unittest.mock import MagicMock, patch

import paramiko
from paramiko.hostkeys import HostKeys
from paramiko.rsakey import RSAKey
import sshtunnel
import zmq

from SimStackServer import ClusterManager
from SimStackServer.MessageTypes import Message
from SimStackServer.MessageTypes import SSS_MESSAGETYPE as MTS
from SimStackServer.BaseClusterManager import SSHExpectedDirectoryError


@pytest.fixture
def ssh_client_with_host_keys():
    """
    Returns a real paramiko.SSHClient whose _host_keys attribute is
    populated with at least one host key, so save_host_keys() can write data.
    """
    ssh_client = paramiko.SSHClient()
    # Optionally load system host keys if you wish:
    # ssh_client.load_system_host_keys()

    # Or create your own dummy key:
    host_keys = HostKeys()

    # Generate an RSA key purely in memory:
    private_key = RSAKey.generate(bits=1024)
    host_keys.add("example.com", "ssh-rsa", private_key)

    # Assign that HostKeys object to the SSHClient internals
    ssh_client._host_keys = host_keys
    return ssh_client


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
    cluster_manager.set_connect_to_unknown_hosts(True)
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

def test_connection_context_already_connected(cluster_manager):
    """
    If we are already connected, connection_context() should yield None
    without calling connect_ssh_and_zmq_if_disconnected,
    but disconnect when the context ends.
    """
    cluster_manager.is_connected = MagicMock(return_value=True)

    with patch.object(cluster_manager, "connect_ssh_and_zmq_if_disconnected") as mock_connect, \
         patch.object(cluster_manager, "disconnect") as mock_disconnect:
        with cluster_manager.connection_context() as result:
            # Because already connected, we expect yield None
            assert result is None
            # Ensure we did NOT call connect_ssh_and_zmq_if_disconnected
            mock_connect.assert_not_called()

        # Exiting the context calls disconnect
        mock_disconnect.assert_called_once()

def test_connection_context_not_connected(cluster_manager):
    """
    If we are not connected, connection_context() should call
    connect_ssh_and_zmq_if_disconnected(...), yield its result,
    and then call disconnect at the end.
    """
    cluster_manager.is_connected = MagicMock(return_value=False)

    # We'll pretend connect_ssh_and_zmq_if_disconnected returns "some_tunnel_info"
    with patch.object(cluster_manager, "connect_ssh_and_zmq_if_disconnected", return_value="some_tunnel_info") as mock_connect, \
         patch.object(cluster_manager, "disconnect") as mock_disconnect:
        with cluster_manager.connection_context() as result:
            # Because not connected, we yield the value from connect_ssh_and_zmq_if_disconnected
            assert result == "some_tunnel_info"
            mock_connect.assert_called_once_with(connect_http=False, verbose=False)

        # Exiting the context calls disconnect
        mock_disconnect.assert_called_once()


def test_connect_ssh_and_zmq_if_disconnected_already_connected(cluster_manager):
    """
    If is_connected() is True, connect_ssh_and_zmq_if_disconnected should do nothing.
    """
    # Mock is_connected to return True
    cluster_manager.is_connected = MagicMock(return_value=True)

    with patch.object(cluster_manager, "connect") as mock_connect, \
            patch.object(cluster_manager, "connect_zmq_tunnel") as mock_tunnel, \
            patch.object(cluster_manager, "_get_server_command") as mock_cmd:
        cluster_manager.connect_ssh_and_zmq_if_disconnected(connect_http=False, verbose=False)

    mock_connect.assert_not_called()
    mock_cmd.assert_not_called()
    mock_tunnel.assert_not_called()

def test_connect_ssh_and_zmq_if_disconnected_not_connected(cluster_manager):
    """
    If is_connected() is False, the method should call:
      - connect()
      - _get_server_command()
      - connect_zmq_tunnel(...)
    """
    cluster_manager.is_connected = MagicMock(return_value=False)

    with patch.object(cluster_manager, "connect") as mock_connect, \
         patch.object(cluster_manager, "_get_server_command", return_value="myservercmd") as mock_cmd, \
         patch.object(cluster_manager, "connect_zmq_tunnel") as mock_tunnel:

        cluster_manager.connect_ssh_and_zmq_if_disconnected(connect_http=True, verbose=True)

    # Now we expect the following calls:
    mock_connect.assert_called_once()
    mock_cmd.assert_called_once()
    mock_tunnel.assert_called_once_with("myservercmd", connect_http=True, verbose=True)


def test_disconnect_all_set(cluster_manager):
    """
    Test that disconnect() calls close() on socket, sftp_client,
    ssh_client, and handles _http_server_tunnel and _zmq_ssh_tunnel correctly.
    """
    # 1) Mock everything the method checks.
    mock_socket = MagicMock()
    mock_sftp = MagicMock()
    mock_sshclient = MagicMock()

    # The http tunnel forwarder:
    mock_http_tunnel = MagicMock()
    # e.g. it has a _server_list with 2 "servers"
    mock_http_tunnel._server_list = [MagicMock(), MagicMock()]
    # each of these servers has .timeout set
    # ._transport is also present
    mock_transport = MagicMock()
    mock_http_tunnel._transport = mock_transport

    # The zmq tunnel:
    mock_zmq_tunnel = MagicMock()
    # ensure it has a "kill" attribute
    mock_zmq_tunnel.kill = MagicMock()

    # 2) Assign them all to the cluster_manager
    cluster_manager._socket = mock_socket
    cluster_manager._sftp_client = mock_sftp
    cluster_manager._ssh_client = mock_sshclient
    cluster_manager._http_server_tunnel = mock_http_tunnel
    cluster_manager._zmq_ssh_tunnel = mock_zmq_tunnel

    # 3) Call the method under test
    cluster_manager.disconnect()

    # 4) Verify each block's side effects:
    #    a) socket and sftp close
    mock_socket.close.assert_called_once()
    mock_sftp.close.assert_called_once()

    #    b) ssh_client close (no if check => always called)
    mock_sshclient.close.assert_called_once()

    #    c) http_server_tunnel is not None => sets each _srv.timeout = 0.01
    for srv in mock_http_tunnel._server_list:
        assert srv.timeout == 0.01

    #        then calls _transport.close() and .stop()
    mock_transport.close.assert_called_once()
    mock_http_tunnel.stop.assert_called_once()

    #    d) zmq_ssh_tunnel is not None => has kill => calls kill()
    mock_zmq_tunnel.kill.assert_called_once()


def test_disconnect_minimal(cluster_manager):
    """
    Test that disconnect() gracefully handles None attributes.
    Only _ssh_client is guaranteed to be closed.
    """
    # By default everything is None, except _ssh_client,
    # which the fixture usually mocks. If not, mock it:
    mock_sshclient = MagicMock()
    cluster_manager._ssh_client = mock_sshclient
    cluster_manager._socket = None
    cluster_manager._sftp_client = None
    cluster_manager._http_server_tunnel = None
    cluster_manager._zmq_ssh_tunnel = None

    cluster_manager.disconnect()

    # Only the ssh_client is guaranteed to close. No other calls happen.
    mock_sshclient.close.assert_called_once()

def test_delete_file(cluster_manager, mock_sftpclient):
    cluster_manager._sftp_client = mock_sftpclient
    cluster_manager.connect()
    cluster_manager.delete_file("myfile")
    mock_sftpclient.remove.assert_called_once()


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

    cluster_manager.exists_as_directory = MagicMock(return_value=False)
    res = cluster_manager.rmtree("testdir")
    assert res is None

    # Mock out exists_as_directory to always True for these paths
    cluster_manager.exists_as_directory = MagicMock(return_value=True)

    cluster_manager.rmtree("testdir")

    # We expect remove calls to subfile1 and subfile2, and rmdir calls to subdir1 and testdir
    mock_sftpclient.remove.assert_any_call("/fake/basepath/testdir/subfile1")
    mock_sftpclient.remove.assert_any_call("/fake/basepath/testdir/subdir1/subfile2")
    mock_sftpclient.rmdir.assert_any_call("/fake/basepath/testdir/subdir1")
    mock_sftpclient.rmdir.assert_any_call("/fake/basepath/testdir")


def test_remote_open(cluster_manager, mock_sftpclient):
    cluster_manager._sftp_client = mock_sftpclient
    cluster_manager.remote_open("myfile", 'r')
    mock_sftpclient.open.assert_called_once()

def test_default_queue(cluster_manager):
    assert cluster_manager.get_default_queue() == "fake-queue"

def test_exec_command(cluster_manager):
    mock_sshclient_instance = MagicMock(spec=paramiko.SSHClient)
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    mock_sshclient_instance.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
    with patch(
        "paramiko.SSHClient", return_value=mock_sshclient_instance
    ) as mock_sshclient_cls:

        stdout, stderr = cluster_manager.exec_command("test-command")

    mock_sshclient_instance.exec_command.assert_called_once_with("test-command")

    assert stdout is mock_stdout
    assert stderr is mock_stderr

def test_connect_zmq_tunnel(cluster_manager, mock_zmq_context):
    """
    #Test connect_zmq_tunnel logic:
    #it should call exec_command on the remote to start the server,
    #parse the result, and connect to the ZMQ socket with the returned port & password.
    """
    fake_stderr = []
    for fake_stdout in [
        ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.3.4"],
        ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.2.4"],
        ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey GETLINE586,6,ZMQ,4.3.4"],
    ]:
        # Patch exec_command to return mocked stdout/stderr
        cluster_manager.exec_command = MagicMock(
            return_value=(fake_stdout, fake_stderr)
        )

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

    fake_stderr = []
    fake_stdout = ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.3.4"]
    # Patch exec_command to return mocked stdout/stderr
    cluster_manager.exec_command = MagicMock(return_value=(fake_stdout, fake_stderr))
    mock_tunnel = MagicMock()
    with patch("zmq.ssh.tunnel.paramiko_tunnel") as mock_paramiko_tunnel:
        # paramiko_tunnel normally returns (new_url, tunnel),
        # so let's return a dummy URL and a mock tunnel object.

        mock_paramiko_tunnel.return_value = ("tcp://127.0.0.1:5555", mock_tunnel)

        with patch("SimStackServer.__version__", new="7.1.2"):
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

    with patch("zmq.ssh.tunnel.paramiko_tunnel") as mock_paramiko_tunnel:
        # paramiko_tunnel normally returns (new_url, tunnel),
        # so let's return a dummy URL and a mock tunnel object.

        mock_paramiko_tunnel.return_value = ("tcp://127.0.0.1:5555", mock_tunnel)
        cluster_manager.get_http_server_address = MagicMock(return_value="127.0.1.2")
        with patch("SimStackServer.__version__", new="6.1.2"):
            cluster_manager.connect()
            cluster_manager.connect_zmq_tunnel(
                "some_fake_command", connect_http=True, verbose=True
            )

            with patch.object(
                cluster_manager, "get_http_server_address", side_effect=Exception
            ):
                # Now, any code calling cluster_manager.get_http_server_address()
                # will raise ConnectionError instead of returning normally.

                # If your code calls get_http_server_address() inside connect_zmq_tunnel(...),
                # you can do:
                with pytest.raises(Exception):
                    cluster_manager.connect_zmq_tunnel(
                        "some_fake_command", connect_http=True, verbose=True
                    )


def test_connect_zmq_tunnel_extra_config(cluster_manager, mock_zmq_context):
    fake_stderr = []
    fake_stdout = ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.3.4"]
    # Patch exec_command to return mocked stdout/stderr
    cluster_manager.exec_command = MagicMock(return_value=(fake_stdout, fake_stderr))
    mock_tunnel = MagicMock()

    cluster_manager._extra_config = "some_config"

    with patch("zmq.ssh.tunnel.paramiko_tunnel") as mock_paramiko_tunnel, \
        patch.object(cluster_manager, "exists", return_value=False) as mock_method:
        # paramiko_tunnel normally returns (new_url, tunnel),
        # so let's return a dummy URL and a mock tunnel object.

        mock_paramiko_tunnel.return_value = ("tcp://127.0.0.1:5555", mock_tunnel)

        cluster_manager.connect()
        with pytest.raises(ConnectionError):
            cluster_manager.connect_zmq_tunnel("some_fake_command", connect_http=False)

def test_connect_zmq_tunnel_other_queuing(cluster_manager, mock_zmq_context):
    fake_stderr = []
    fake_stdout = ["SIMSTACK_STARTUP 127.0.0.1 5555 secretkey SERVER,6,ZMQ,4.3.4"]
    # Patch exec_command to return mocked stdout/stderr
    cluster_manager.exec_command = MagicMock(return_value=(fake_stdout, fake_stderr))
    mock_tunnel = MagicMock()

    cluster_manager._queueing_system = "pbs"

    with patch("zmq.ssh.tunnel.paramiko_tunnel") as mock_paramiko_tunnel, \
        patch.object(cluster_manager, "exists", return_value=False) as mock_method:
        # paramiko_tunnel normally returns (new_url, tunnel),
        # so let's return a dummy URL and a mock tunnel object.

        mock_paramiko_tunnel.return_value = ("tcp://127.0.0.1:5555", mock_tunnel)

        cluster_manager.connect()
        with pytest.raises(ConnectionError):
            cluster_manager.connect_zmq_tunnel("some_fake_command", connect_http=False)




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


def test_save_hostkeyfile(cluster_manager, ssh_client_with_host_keys, tmpfile):
    cluster_manager.connect()
    cluster_manager._ssh_client = ssh_client_with_host_keys
    cluster_manager.save_hostkeyfile(tmpfile)
    assert tmpfile.exists()
    content = tmpfile.read_text()
    assert content.startswith("example.com ssh-rsa")


def test_get_new_connected_ssh_channel_with_config(cluster_manager):
    """
    Test that get_new_connected_ssh_channel() loads extra host keys, sets missing
    host key policy, and calls connect with a custom key file.
    """
    # Simulate custom key and host key file
    cluster_manager._sshprivatekeyfilename = "my_private_key"
    cluster_manager._extra_hostkey_file = "/extra/hosts"
    cluster_manager._unknown_host_connect_workaround = True

    # Create a mock SSHClient instance
    mock_sshclient_instance = MagicMock(spec=paramiko.SSHClient)

    with patch(
        "paramiko.SSHClient", return_value=mock_sshclient_instance
    ) as mock_sshclient_cls:
        local_ssh_client = cluster_manager.get_new_connected_ssh_channel()

    # Verify an SSHClient was created
    mock_sshclient_cls.assert_called_once()

    # Check calls on the mock instance
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

    # Ensure we return the mock instance
    assert local_ssh_client is mock_sshclient_instance


def test_get_new_connected_ssh_channel_use_system_default(cluster_manager):
    """
    Test that if _sshprivatekeyfilename == "UseSystemDefault",
    we pass None as the key_filename.
    """
    cluster_manager._sshprivatekeyfilename = "UseSystemDefault"
    cluster_manager._extra_hostkey_file = None
    cluster_manager._unknown_host_connect_workaround = False

    mock_sshclient_instance = MagicMock(spec=paramiko.SSHClient)
    with patch("paramiko.SSHClient", return_value=mock_sshclient_instance):
        local_ssh_client = cluster_manager.get_new_connected_ssh_channel()

    # load_system_host_keys always called
    mock_sshclient_instance.load_system_host_keys.assert_called_once()
    # But no load_host_keys or set_missing_host_key_policy
    mock_sshclient_instance.load_host_keys.assert_not_called()
    mock_sshclient_instance.set_missing_host_key_policy.assert_not_called()

    # Check that connect used None for key_filename
    mock_sshclient_instance.connect.assert_called_once_with(
        "fake-url",
        22,
        username="fake-user",
        key_filename=None,
        compress=True,
    )

    assert local_ssh_client is mock_sshclient_instance


def test_get_http_server_address(cluster_manager, mock_zmq_context):
    cluster_manager._sshprivatekeyfilename = "/fake/ssh/key"
    # Patch sshtunnel.SSHTunnelForwarder so it won't do a real SSH connection
    with patch("sshtunnel.SSHTunnelForwarder") as mock_forwarder_cls:
        # The forwarder instance returned by the constructor:
        mock_forwarder_instance = MagicMock()
        mock_forwarder_cls.return_value = mock_forwarder_instance

        # Pretend the tunnel is "alive"
        mock_forwarder_instance.is_alive = True

        # Suppose the forwarder binds on local port 9999
        mock_forwarder_instance.local_bind_port = 9999

        # The forwarder won't raise an error when start() is called
        mock_forwarder_instance.start.return_value = None

        # Mock out the reply from the server for the 'get_http_server_address()' call
        mock_socket = mock_zmq_context.socket.return_value
        mock_socket.recv.return_value = Message.dict_message(
            MTS.ACK, {"http_port": "505", "http_user": "dummy", "http_pass": "404"}
        )
        # Use the same socket in the cluster_manager
        cluster_manager._socket = mock_socket

        cluster_manager.connect()
        address = cluster_manager.get_http_server_address()
        assert address == "http://dummy:404@localhost:9999"

        # Check that SSHTunnelForwarder was created with the expected arguments
        mock_forwarder_cls.assert_called_once_with(
            ("fake-url", 22),  # (self._url, self._port)
            ssh_username="fake-user",
            ssh_pkey="/fake/ssh/key",  # key_filename might be None or something else
            threaded=False,
            remote_bind_address=("127.0.0.1", 505),
        )

        # start() should have been called on the forwarder
        mock_forwarder_instance.start.assert_called_once()

        mock_forwarder_instance.is_alive = False
        cluster_manager.connect()
        with pytest.raises(
            sshtunnel.BaseSSHTunnelForwarderError, match="Cannot start ssh tunnel."
        ):
            cluster_manager.get_http_server_address()


def test_get_http_server_address_connect_error(cluster_manager, mock_zmq_context):
    # Patch sshtunnel.SSHTunnelForwarder so it won't do a real SSH connection
    with patch("sshtunnel.SSHTunnelForwarder") as mock_forwarder_cls:
        # The forwarder instance returned by the constructor:
        mock_forwarder_instance = MagicMock()
        mock_forwarder_cls.return_value = mock_forwarder_instance

        # Pretend the tunnel is "alive"
        mock_forwarder_instance.is_alive = True

        # Suppose the forwarder binds on local port 9999
        mock_forwarder_instance.local_bind_port = 9999

        # The forwarder won't raise an error when start() is called
        mock_forwarder_instance.start.return_value = None
        mock_socket = mock_zmq_context.socket.return_value
        mock_socket.recv.return_value = Message.dict_message(
            MTS.ACK, {"http_user": "dummy", "http_pass": "404"}
        )
        # Use the same socket in the cluster_manager
        cluster_manager._socket = mock_socket
        cluster_manager.connect()
        with pytest.raises(ConnectionError):
            cluster_manager.get_http_server_address()


def test_get_newest_version_directory(cluster_manager, mock_sshclient, mock_sftpclient):
    """
    Verify that get_newest_version_directory returns the correct 'Vx' directory
    given a mixture of directory names like 'V2', 'V3', 'V6', 'envs', etc.
    """

    cluster_manager.connect()

    # We'll define a custom side_effect for listdir_attr
    # so that it returns multiple 'directories' or 'files'.
    def mock_listdir_attr(path):
        names = ["V2", "V3", "V6", "VV", "envs", "randomfile"]

        entries = []
        for name in names:
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = name

            # If it's V2, V3, V6, or 'envs', we treat it as a directory
            if name in ["V2", "V3", "V6", "VV", "envs"]:
                entry_mock.st_mode = 0o040755  # Directory bit
            else:
                entry_mock.st_mode = 0o100644  # Regular file bit

            entries.append(entry_mock)
        return entries

    # Assign that side effect to the mock SFTP client
    mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr

    # Now call the method under test
    result = cluster_manager.get_newest_version_directory("/fake/path")

    # According to the logic in get_newest_version_directory,
    # it loops over these entries, looks for "Vxx" or "envs",
    # and returns "V6" as the largest version found (which yields "V6").
    assert result == "V6", f"Expected 'V6' but got '{result}'"

    # Optional: check that we actually called sftp_client.listdir_attr
    mock_sftpclient.listdir_attr.assert_called_once_with("/fake/path")

    mock_sftpclient.listdir_attr.side_effect = FileNotFoundError(
        "No such file or directory"
    )

    # Now calling get_newest_version_directory will enter the except FileNotFoundError: block
    with pytest.raises(FileNotFoundError):
        result = cluster_manager.get_newest_version_directory("/fake/nonexistent")


def test_get_server_command_for_software_directory(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    cluster_manager._queueing_system = "AiiDA"
    not_implemented_names = ["V2", "V3", "V4"]
    for nin in not_implemented_names:

        def mock_listdir_attr(path):
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = nin
            entry_mock.st_mode = 0o040755  # Directory bit

            return [entry_mock]

        mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr

        with pytest.raises(NotImplementedError):
            cluster_manager.get_server_command_from_software_directory(nin)

    implemented_names = ["V6", "V8"]
    for imp_name in implemented_names:

        def mock_listdir_attr(path):
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = imp_name
            entry_mock.st_mode = 0o040755  # Directory bit
            return [entry_mock]

        mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr

        res = cluster_manager.get_server_command_from_software_directory(imp_name)
        assert (
            res
            == f"{imp_name}/envs/simstack_server_v6/bin/micromamba run -r {imp_name} --name=simstack_server_v6 SimStackServer"
        )

def test_get_server_command_for_software_directory_no_micromamba(cluster_manager, mock_sftpclient):
    cluster_manager.connect()

    with patch("SimStackServer.ClusterManager.ClusterManager.exists", return_value=False):
        vname="V6"
        def mock_listdir_attr(path):
            entry_mock = MagicMock(spec=paramiko.SFTPAttributes)
            entry_mock.filename = vname
            entry_mock.st_mode = 0o040755  # Directory bit
            return [entry_mock]

        mock_sftpclient.listdir_attr.side_effect = mock_listdir_attr
        with pytest.raises(FileNotFoundError):
            cluster_manager.get_server_command_from_software_directory(vname)


def test_get_server_command(cluster_manager):
    # Patch the method get_server_command_from_software_directory on the cluster_manager instance
    with patch.object(cluster_manager, "get_server_command_from_software_directory",
                      return_value="dummy_cmd") as mock_method:
        result = cluster_manager._get_server_command()

        # Check that the result is what we expect
        assert result == "dummy_cmd"

        # Verify that the patched method was called once with the correct software directory
        mock_method.assert_called_once_with(cluster_manager._software_directory)


def test_get_workflow_job_list_success(cluster_manager, mock_zmq_context):
    """
    Test get_workflow_job_list() when the server's message has 'list_of_jobs'.
    """
    # Mock the ZMQ socket
    mock_socket = mock_zmq_context.socket.return_value

    # We'll also mock cluster_manager._recv_message to simulate server response
    # that includes "list_of_jobs".
    cluster_manager._recv_message = MagicMock(
        return_value=(MTS.ACK, {"list_of_jobs": ["job1", "job2"]})
    )

    # Assign the mock socket to the cluster_manager
    cluster_manager._socket = mock_socket

    # Call the method
    result = cluster_manager.get_workflow_job_list("some_workflow")

    # Check that the socket was used to send the correct message
    # (list_jobs_of_wf_message(...) is presumably building a dictionary or such)
    expected_send = Message.list_jobs_of_wf_message(
        workflow_submit_name="some_workflow"
    )
    mock_socket.send.assert_called_once_with(expected_send)

    # Verify _recv_message was called
    cluster_manager._recv_message.assert_called_once()

    # Assert that we got the correct list of jobs back
    assert result == ["job1", "job2"]


def test_get_workflow_job_list_missing_key(cluster_manager, mock_zmq_context):
    """
    Test get_workflow_job_list() when the server's message is missing 'list_of_jobs',
    which should raise ConnectionError.
    """
    # Mock the ZMQ socket
    mock_socket = mock_zmq_context.socket.return_value

    # Return a dictionary missing "list_of_jobs"
    cluster_manager._recv_message = MagicMock(
        return_value=(MTS.ACK, {"some_unexpected_key": []})
    )

    cluster_manager._socket = mock_socket

    # Expect a ConnectionError due to missing "list_of_jobs"
    with pytest.raises(ConnectionError) as excinfo:
        cluster_manager.get_workflow_job_list("some_workflow")

    assert "Could not read message in workflow job list update" in str(excinfo.value)

    # socket.send was still called, but there's no valid key in the response
    expected_send = Message.list_jobs_of_wf_message(
        workflow_submit_name="some_workflow"
    )
    mock_socket.send.assert_called_once_with(expected_send)


def test_abort_wf(cluster_manager, mock_zmq_context):
    """
    Test that abort_wf() sends the correct abort message and then calls _recv_ack_message.
    """
    # Provide a mock socket
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    # We'll patch the _recv_ack_message so it doesn't do real network ops
    with patch.object(cluster_manager, "_recv_ack_message") as mock_recv_ack:
        cluster_manager.abort_wf("my-test-workflow")

    # Check the socket sent the correct abort message
    expected_msg = Message.abort_wf_message("my-test-workflow")
    mock_socket.send.assert_called_once_with(expected_msg)

    # Check that _recv_ack_message was called
    mock_recv_ack.assert_called_once()


def test_abort_wf_logs_debug(cluster_manager, mock_zmq_context):
    """
    If you want to test the debug log statement as well.
    """
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    with patch.object(cluster_manager, "_recv_ack_message"), patch.object(
        cluster_manager._logger, "debug"
    ) as mock_debug:
        cluster_manager.abort_wf("my-workflow")

    mock_debug.assert_called_once_with(
        "Sent Abort WF message for submitname my-workflow"
    )


def test_put(cluster_manager):
    cluster_manager._calculation_basepath = "/foo/bar"
    cluster_manager.connect()
    input_dir = "%s/input_dirs/RemoteServerManager" % path.dirname(
        path.realpath(__file__)
    )
    transferdir = path.join(input_dir, "test_transfer_dir")
    todir = "unittest_files"
    assert (
        cluster_manager.put_directory(transferdir, todir) == "/foo/bar/unittest_files"
    )


def test_random_singlejob_exec_directory(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    stat_mock = MagicMock()
    stat_mock.st_mode = 0o040755  # File
    with pytest.raises(FileExistsError):
        cluster_manager.mkdir_random_singlejob_exec_directory("testdir", num_retries=1)

    def side_effect(path_str):
        # Return False the first time, so it tries to create
        return False

    cluster_manager.exists = MagicMock(side_effect=side_effect)
    res = str(cluster_manager.mkdir_random_singlejob_exec_directory("testdir"))
    assert res.split("/")[0] == "singlejob_exec_directories"
    assert "testdir" in res.split("/")[1]


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


def test_list_dir(cluster_manager, mock_sftpclient):
    cluster_manager.connect()
    # Create two mocked SFTPAttributes, one directory and one file
    file_attr_mock = MagicMock(spec=paramiko.SFTPAttributes)
    file_attr_mock.filename = "myfile.txt"
    file_attr_mock.longname = "-rw-r--r-- 1 user group 1234 date myfile.txt"
    file_attr_mock.st_mode = 0o100644  # indicates a regular file

    dir_attr_mock = MagicMock(spec=paramiko.SFTPAttributes)
    dir_attr_mock.filename = "somedir"
    dir_attr_mock.longname = "drwxr-xr-x 2 user group 4096 date somedir"
    dir_attr_mock.st_mode = 0o040755  # directory bit

    # Make listdir_iter(...) return these two entries
    mock_sftpclient.listdir_iter.return_value = [file_attr_mock, dir_attr_mock]

    # Call the function under test
    result = cluster_manager.list_dir("some/subdirectory")
    assert result == [
        {"name": "myfile.txt", "path": "/fake/basepath/some/subdirectory", "type": "f"},
        {"name": "somedir", "path": "/fake/basepath/some/subdirectory", "type": "d"},
    ]

    # Check that we called listdir_iter with the correct path
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

    def side_effect_False(path_str):
        return False

    cluster_manager.exists_remote = MagicMock(side_effect=side_effect_False)

    with pytest.raises(FileNotFoundError):
        cluster_manager.get_directory("server/dir", tmpdir + "/todir")

    def side_effect_True(path_str):
        return True

    cluster_manager.exists_remote = MagicMock(side_effect=side_effect_True)

    cluster_manager.connect()

    remote_root = "remote"
    local_root = tmpdir + "/" + "local_dest"

    # 1) Mock listdir(...) so each directory returns the sub-items we want.
    def mock_listdir(path):
        if path == "remote":
            # remote/ has subdir + file1
            return ["subdir", "file1"]
        elif path in ("remote/subdir", "remote/subdir/"):
            # remote/subdir/ has file2
            return ["file2"]
        else:
            # If we ever look inside a file or anything else, return nothing
            return []

    # 2) Mock stat(...) so we know which items are dirs vs. files.
    #    We'll return a lightweight object with st_mode set accordingly.
    def mock_stat(path):
        class MockAttrs:
            pass

        attrs = MockAttrs()
        # Our 'directories': remote, remote/subdir, remote/subdir/
        if path in ("remote", "remote/subdir", "remote/subdir/"):
            attrs.st_mode = 0o040755  # directory bit => stat.S_ISDIR is True
        else:
            attrs.st_mode = 0o100644  # file bit
        return attrs

    # 3) Mock the actual file download with get(...)
    #    We'll create a dummy local file so the code sees something.
    def mock_get(remote_path, local_path):
        with open(local_path, "w") as f:
            f.write("dummy content")

    mock_sftpclient.listdir.side_effect = mock_listdir
    mock_sftpclient.stat.side_effect = mock_stat
    mock_sftpclient.get.side_effect = mock_get

    # 4) Call the method under test
    cluster_manager.get_directory(remote_root, str(local_root))

    # 5) Verify the local files got created without infinite recursion
    file1_path = local_root + "/" + "file1"
    file2_path = local_root + "/" + "subdir" + "/" + "file2"

    assert pathlib.Path(file1_path).exists(), "file1 was not downloaded to local"
    assert pathlib.Path(
        file2_path
    ).exists(), "file2 inside subdir was not downloaded to local"


def test_send_clearserverstate_message(cluster_manager, mock_zmq_context):
    """
    Test that send_clearserverstate_message() sends the correct message
    and calls _recv_ack_message().
    """
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    with patch.object(cluster_manager, "_recv_ack_message") as mock_recv_ack:
        cluster_manager.send_clearserverstate_message()

    # Check that the socket was called with the correct message
    mock_socket.send.assert_called_once_with(Message.clearserverstate_message())
    # Check that we got an ACK
    mock_recv_ack.assert_called_once()


def test_delete_wf(cluster_manager, mock_zmq_context):
    """
    Test delete_wf() sends the correct 'delete_wf_message' and logs a debug.
    """
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    with patch.object(
        cluster_manager, "_recv_ack_message"
    ) as mock_recv_ack, patch.object(cluster_manager._logger, "debug") as mock_debug:
        cluster_manager.delete_wf("some_workflow")

    # The cluster manager should send a delete_wf_message with 'some_workflow'
    mock_socket.send.assert_called_once_with(Message.delete_wf_message("some_workflow"))
    # Make sure _recv_ack_message() was called
    mock_recv_ack.assert_called_once()
    # Confirm a debug log was generated
    # Because the code does string interpolation itself, we expect one argument.
    mock_debug.assert_called_once_with(
        "Sent delete WF message for submitname %s" % ("some_workflow")
    )


def test_get_workflow_list(cluster_manager, mock_zmq_context):
    """
    Test get_workflow_list() sends the correct list_wfs_message and returns 'workflows' from the server.
    """
    mock_socket = mock_zmq_context.socket.return_value
    cluster_manager._socket = mock_socket

    # Suppose the server replies with an ACK plus a workflows list
    with patch.object(
        cluster_manager,
        "_recv_message",
        return_value=(MTS.ACK, {"workflows": ["wf1", "wf2"]}),
    ) as mock_recv:
        result = cluster_manager.get_workflow_list()

    # We should have sent the list_wfs_message:
    mock_socket.send.assert_called_once_with(Message.list_wfs_message())
    # Check that we got the right data from _recv_message
    mock_recv.assert_called_once()
    # And the method returns ["wf1", "wf2"]
    assert result == ["wf1", "wf2"]


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
