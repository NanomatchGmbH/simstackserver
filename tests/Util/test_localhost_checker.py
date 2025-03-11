import os
import sys
import socket
from unittest.mock import patch

import pytest

from SimStackServer.Util.localhost_checker import is_localhost

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestLocalhostChecker:
    def test_islocalhost(self):
        with patch("SimStackServer.Util.localhost_checker.socket") as mock_socket:
            mock_socket.getaddrinfo.return_value = [(0, 1, 2, 3, ["127.0.0.1"])]
            mock_socket.AF_INET = "dummyINET"
            mock_socket.AF_INET6 = "dummyINET6"
            assert is_localhost("myhost") is True

            mock_socket.getaddrinfo.side_effect = socket.gaierror
            with pytest.raises(TypeError):
                assert is_localhost("myhost") is False