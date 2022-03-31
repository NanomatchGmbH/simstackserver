import socket
from ipaddress import ip_address

def is_localhost(host):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            r = socket.getaddrinfo(host, None, family, socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        for _, _, _, _, sockaddr in r:
            if ip_address(sockaddr[0]).is_loopback:
                return True
    return False
