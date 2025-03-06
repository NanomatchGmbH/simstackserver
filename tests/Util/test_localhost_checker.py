import os
import sys
import pytest
import socket
from unittest.mock import patch, MagicMock

# Add SimStackServer to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from SimStackServer.Util.localhost_checker import is_localhost


class TestLocalhostChecker:
    
    def test_is_localhost_localhost(self):
        # Test that "localhost" is recognized as local
        assert is_localhost("localhost") is True
    
    def test_is_localhost_127_0_0_1(self):
        # Test that "127.0.0.1" is recognized as local
        assert is_localhost("127.0.0.1") is True
    
    @patch('socket.getaddrinfo')
    def test_is_localhost_ipv6_loopback(self, mock_getaddrinfo):
        # Setup mock to return IPv6 loopback address
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::1', 0, 0, 0))
        ]
        
        # Test that "::1" is recognized as local
        assert is_localhost("::1") is True
    
    @patch('socket.getaddrinfo')
    def test_is_localhost_external_host(self, mock_getaddrinfo):
        # Setup mock to return a non-local address
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0))
        ]
        
        # Test that an external host is not recognized as local
        assert is_localhost("example.com") is False
    
    @patch('socket.getaddrinfo')
    def test_is_localhost_multiple_addresses(self, mock_getaddrinfo):
        # Setup mock to return multiple addresses, one of which is local
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('93.184.216.34', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('127.0.0.1', 0))
        ]
        
        # Test that a host with multiple addresses, one being local, is recognized as local
        assert is_localhost("multi-address-host") is True
    
    @patch('socket.getaddrinfo')
    def test_is_localhost_resolution_error(self, mock_getaddrinfo):
        # Setup mock to raise an exception
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
        
        # Test that a resolution error returns False
        assert is_localhost("nonexistent-host") is False
    
    @patch('socket.getaddrinfo')
    def test_is_localhost_multiple_address_families(self, mock_getaddrinfo):
        # Setup mock to return addresses from different families
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('192.168.1.1', 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 0, '', ('::1', 0, 0, 0))
        ]
        
        # Test that a host with both IPv4 and IPv6 addresses, one being local, is recognized as local
        assert is_localhost("dual-stack-host") is True