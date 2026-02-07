"""
SSH Tunnel Forwarder implementation using paramiko.

This module provides a replacement for the abandoned sshtunnel library,
implementing SSH port forwarding that works with httpx and other network clients.
"""

import logging
import select
import socketserver
import threading
from typing import Optional, Tuple, Union

import warnings
from cryptography.utils import CryptographyDeprecationWarning

with warnings.catch_warnings(action="ignore", category=CryptographyDeprecationWarning):
    import paramiko


logger = logging.getLogger(__name__)


class _ForwardServer(socketserver.ThreadingTCPServer):
    """
    TCP server that forwards connections through an SSH tunnel.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        RequestHandlerClass,
        ssh_transport: paramiko.Transport,
        remote_address: Tuple[str, int],
    ):
        self.ssh_transport = ssh_transport
        self.remote_address = remote_address
        self.timeout = None
        super().__init__(server_address, RequestHandlerClass)


class _ForwardHandler(socketserver.BaseRequestHandler):
    """
    Handler for forwarded connections. Handles data transfer between
    local socket and remote host through SSH tunnel.
    """

    def handle(self):
        try:
            # Open channel to remote host through SSH
            chan = self.server.ssh_transport.open_channel(
                "direct-tcpip",
                self.server.remote_address,
                self.request.getpeername(),
            )
        except Exception as e:
            logger.error(f"Failed to open SSH channel: {e}")
            return

        if chan is None:
            logger.error("SSH channel could not be established")
            return

        logger.debug(
            f"Connected! Tunnel open {self.request.getpeername()} -> "
            f"{self.server.remote_address}"
        )

        try:
            self._forward_data(chan)
        finally:
            chan.close()
            self.request.close()

    def _forward_data(self, chan: paramiko.Channel):
        """
        Forward data between local socket and SSH channel.
        """
        while True:
            # Check if channel or socket is closed
            if chan.closed or not chan.active:
                break

            # Wait for data on either socket or channel
            r, w, x = select.select([self.request, chan], [], [], 1.0)

            if self.request in r:
                data = self.request.recv(4096)
                if len(data) == 0:
                    break
                try:
                    chan.send(data)
                except (BrokenPipeError, OSError):
                    break

            if chan in r:
                data = chan.recv(4096)
                if len(data) == 0:
                    break
                try:
                    self.request.send(data)
                except (BrokenPipeError, OSError):
                    break


class SSHTunnelForwarder:
    """
    SSH Tunnel Forwarder that creates local port forwarding to a remote host/port
    through an SSH connection.

    This class provides a drop-in replacement for sshtunnel.SSHTunnelForwarder
    with a simplified interface suitable for use with httpx and other HTTP clients.

    Usage:
        # Basic usage with context manager
        with SSHTunnelForwarder(
            ssh_address_or_host=('example.com', 22),
            ssh_username='user',
            ssh_pkey='/path/to/key',
            remote_bind_address=('localhost', 8000),
            local_bind_address=('127.0.0.1', 0)  # 0 = auto-assign port
        ) as tunnel:
            tunnel.start()
            # Use tunnel.local_bind_port with httpx
            client = httpx.Client(base_url=f'http://127.0.0.1:{tunnel.local_bind_port}')

        # Manual start/stop
        tunnel = SSHTunnelForwarder(...)
        tunnel.start()
        try:
            # Use tunnel
            pass
        finally:
            tunnel.stop()

    Args:
        ssh_address_or_host: SSH host address as string or tuple (host, port)
        ssh_username: SSH username
        ssh_password: SSH password (optional if using key)
        ssh_pkey: Path to SSH private key file or paramiko.PKey object
        ssh_private_key_password: Password for encrypted private key
        remote_bind_address: Remote address to forward to as tuple (host, port)
        local_bind_address: Local address to bind to as tuple (host, port).
                          Use ('127.0.0.1', 0) to auto-assign a free port.
        host_pkey_dict: Dict of known host keys (optional)
        allow_unknown_hosts: If True, automatically accept unknown host keys
    """

    def __init__(
        self,
        ssh_address_or_host: Union[str, Tuple[str, int]],
        ssh_username: str,
        ssh_password: Optional[str] = None,
        ssh_pkey: Optional[Union[str, paramiko.PKey]] = None,
        ssh_private_key_password: Optional[str] = None,
        remote_bind_address: Tuple[str, int] = ("localhost", 22),
        local_bind_address: Tuple[str, int] = ("127.0.0.1", 0),
        host_pkey_dict: Optional[dict] = None,
        allow_unknown_hosts: bool = False,
        compress: bool = True,
    ):
        # Parse SSH address
        if isinstance(ssh_address_or_host, tuple):
            self.ssh_host, self.ssh_port = ssh_address_or_host
        else:
            self.ssh_host = ssh_address_or_host
            self.ssh_port = 22

        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.ssh_pkey = ssh_pkey
        self.ssh_private_key_password = ssh_private_key_password
        self.remote_bind_address = remote_bind_address
        self.local_bind_address = local_bind_address
        self.allow_unknown_hosts = allow_unknown_hosts
        self.compress = compress

        self._ssh_client: Optional[paramiko.SSHClient] = None
        self._transport: Optional[paramiko.Transport] = None
        self._server_list: list = []
        self._server_threads: list = []
        self._is_started = False
        self._local_bind_port: Optional[int] = None

        logger.debug(
            f"SSHTunnelForwarder initialized: {self.ssh_host}:{self.ssh_port} -> "
            f"{remote_bind_address}"
        )

    def start(self):
        """
        Start the SSH tunnel and local port forwarding.
        """
        if self._is_started:
            logger.warning("Tunnel already started")
            return

        logger.debug("Starting SSH tunnel")

        # Create SSH client
        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.load_system_host_keys()

        if self.allow_unknown_hosts:
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load private key if provided
        pkey = None
        if self.ssh_pkey:
            if isinstance(self.ssh_pkey, paramiko.PKey):
                pkey = self.ssh_pkey
            elif isinstance(self.ssh_pkey, str):
                # Try to load the key file
                try:
                    pkey = paramiko.RSAKey.from_private_key_file(
                        self.ssh_pkey, password=self.ssh_private_key_password
                    )
                except paramiko.SSHException:
                    try:
                        pkey = paramiko.Ed25519Key.from_private_key_file(
                            self.ssh_pkey, password=self.ssh_private_key_password
                        )
                    except paramiko.SSHException:
                        try:
                            pkey = paramiko.ECDSAKey.from_private_key_file(
                                self.ssh_pkey, password=self.ssh_private_key_password
                            )
                        except paramiko.SSHException:
                            pkey = paramiko.DSSKey.from_private_key_file(
                                self.ssh_pkey, password=self.ssh_private_key_password
                            )

        # Connect to SSH server
        self._ssh_client.connect(
            hostname=self.ssh_host,
            port=self.ssh_port,
            username=self.ssh_username,
            password=self.ssh_password,
            pkey=pkey,
            compress=self.compress,
        )

        self._transport = self._ssh_client.get_transport()
        self._transport.set_keepalive(30)

        # Create forwarding server
        server = _ForwardServer(
            self.local_bind_address,
            _ForwardHandler,
            self._transport,
            self.remote_bind_address,
        )

        self._server_list.append(server)
        self._local_bind_port = server.server_address[1]

        # Start server in a thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self._server_threads.append(server_thread)

        self._is_started = True

        logger.info(
            f"Tunnel started: localhost:{self._local_bind_port} -> "
            f"{self.remote_bind_address[0]}:{self.remote_bind_address[1]} "
            f"through {self.ssh_host}:{self.ssh_port}"
        )

    def stop(self):
        """
        Stop the SSH tunnel and close all connections.
        """
        if not self._is_started:
            logger.warning("Tunnel not started")
            return

        logger.debug("Stopping SSH tunnel")

        # Stop all forwarding servers
        for server in self._server_list:
            if server.timeout is None:
                server.timeout = 0.01
            server.shutdown()
            server.server_close()

        # Close SSH connection
        if self._transport:
            self._transport.close()

        if self._ssh_client:
            self._ssh_client.close()

        self._server_list.clear()
        self._server_threads.clear()
        self._is_started = False
        self._local_bind_port = None

        logger.info("Tunnel stopped")

    @property
    def local_bind_port(self) -> Optional[int]:
        """
        Get the local port that was bound for forwarding.
        Returns None if tunnel is not started.
        """
        return self._local_bind_port

    @property
    def local_bind_host(self) -> str:
        """
        Get the local host address that was bound.
        """
        return self.local_bind_address[0]

    @property
    def is_alive(self) -> bool:
        """
        Check if the tunnel is currently active.
        """
        return (
            self._is_started
            and self._transport is not None
            and self._transport.is_active()
        )

    def __enter__(self):
        """
        Context manager entry.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit - ensures tunnel is stopped.
        """
        if self._is_started:
            self.stop()
        return False

    def __del__(self):
        """
        Destructor - ensures tunnel is stopped.
        """
        if self._is_started:
            try:
                self.stop()
            except Exception:
                pass

    def __repr__(self):
        status = "active" if self.is_alive else "inactive"
        return (
            f"<SSHTunnelForwarder {status}: "
            f"localhost:{self._local_bind_port} -> "
            f"{self.remote_bind_address[0]}:{self.remote_bind_address[1]} "
            f"via {self.ssh_host}:{self.ssh_port}>"
        )
