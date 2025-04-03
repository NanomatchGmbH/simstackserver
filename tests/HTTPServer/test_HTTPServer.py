import io

import time

import pytest
import os
import tempfile
from unittest import mock
import base64

from SimStackServer.HTTPServer.HTTPServer import (
    CustomHTTPServerThread,
    CustomServerHandler,
)


@pytest.fixture
def temp_html_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        sample_html_path = os.path.join(temp_dir, "sample.html")
        with open(sample_html_path, "w") as f:
            f.write("<html><body><h1>Sample HTML</h1></body></html>")
        os.makedirs(os.path.join(temp_dir, "subdir"), exist_ok=False)
        os.symlink(
            os.path.join(temp_dir, "sample.html"), os.path.join(temp_dir, "link.html")
        )
        yield temp_dir


@pytest.fixture
def custom_http_server_thread(temp_html_dir) -> CustomHTTPServerThread:
    server = CustomHTTPServerThread(("", 8888), str(temp_html_dir))
    server.set_auth("demo", "demo")
    server.start()
    yield server
    server.do_graceful_shutdown()
    server.join()


@pytest.fixture
def custom_http_server_thread_mocked(temp_html_dir):
    with mock.patch.object(
        CustomHTTPServerThread, "serve_for_duration", new_callable=mock.Mock
    ) as mock_serve:
        server = CustomHTTPServerThread(("", 8888), str(temp_html_dir))
        server.set_auth("demo", "demo")
        yield server, mock_serve


def test_custom_http_server_thread_smoke(custom_http_server_thread_mocked):
    server, mock_serve = custom_http_server_thread_mocked
    assert server.key == base64.b64encode(b"demo:demo").decode("ascii")
    mock_serve.assert_not_called()
    server.start()
    mock_serve.assert_called_once()
    server.join()


def test_custom_http_server_thread_shutdown(temp_html_dir):
    server = CustomHTTPServerThread(("", 8888), str(temp_html_dir))
    server.start()
    assert server.is_alive()
    server.do_graceful_shutdown()
    time.sleep(1.1)
    assert server.is_alive() is False


def test_custom_http_server_thread_get_auth_key(custom_http_server_thread):
    assert custom_http_server_thread.get_auth_key() == base64.b64encode(
        b"demo:demo"
    ).decode("ascii")


class MockRequest:
    def __init__(self, request_bin):
        self.request = request_bin
        self.reponse_cache = b""

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.request)

    def sendall(self, bytestring):
        self.reponse_cache = bytestring


class ServerMock(mock.MagicMock):
    def get_auth_key(self):
        return base64.b64encode(b"demo:demo").decode("ascii")


def test_handler_ops(temp_html_dir, monkeypatch):
    """Test the custom HTTP request handler by mocking a server"""

    good_get = MockRequest(
        b"""GET / HTTP/1.1
Authorization: Basic ZGVtbzpkZW1v
"""
    )
    servermock = ServerMock()
    monkeypatch.chdir(temp_html_dir)
    CustomServerHandler(good_get, ("0.0.0.0", 8000), servermock)
    res = good_get.reponse_cache.decode("utf-8")
    assert '<a href="sample.html">sample.html</a>' in res
    assert '<a href="subdir/">subdir/</a>' in res
    assert '<a href="link.html">link.html@</a>' in res
    bad_auth = MockRequest(
        b"""GET / HTTP/1.1
Authorization: Basic wrong_auth
    """
    )
    CustomServerHandler(bad_auth, ("0.0.0.0", 8000), servermock)
    res = bad_auth.reponse_cache.decode("utf-8")
    assert "Invalid credentials" in res

    no_auth = MockRequest(b"""GET / HTTP/1.1""")
    CustomServerHandler(no_auth, ("0.0.0.0", 8000), servermock)
    res = no_auth.reponse_cache.decode("utf-8")
    assert "No auth header received" in res

    get_favicon = MockRequest(
        b"""GET /favicon.ico HTTP/1.1
Authorization: Basic ZGVtbzpkZW1v"""
    )
    CustomServerHandler(get_favicon, ("0.0.0.0", 8000), servermock)
    res = get_favicon.reponse_cache
    assert len(res) == 591

    get_dirlist = MockRequest(
        b"""GET /dirlist.css HTTP/1.1
Authorization: Basic ZGVtbzpkZW1v"""
    )
    CustomServerHandler(get_dirlist, ("0.0.0.0", 8000), servermock)
    res = get_dirlist.reponse_cache
    assert len(res) == 549

    get_sample = MockRequest(
        b"""GET /sample.html HTTP/1.1
Authorization: Basic ZGVtbzpkZW1v"""
    )
    handler = CustomServerHandler(get_sample, ("0.0.0.0", 8000), servermock)
    res = get_sample.reponse_cache.decode("utf-8")
    assert res == "<html><body><h1>Sample HTML</h1></body></html>"

    get_sample.response_cache = b""
    handler.do_HEAD()
    res = get_sample.reponse_cache.decode("utf-8")
    assert "200" in res
    assert "Content-type: application/json" in res

    get_sample.response_cache = b""
    handler.do_AUTHHEAD()
    res = get_sample.reponse_cache.decode("utf-8")
    assert 'Basic realm="Demo Realm"' in res

    post = MockRequest(b"""POST / HTTP/1.1""")
    with pytest.raises(NotImplementedError):
        CustomServerHandler(post, ("0.0.0.0", 8000), servermock)


def test_handler_invalid_dir(temp_html_dir, monkeypatch):
    """Test the custom HTTP request handler by mocking a server"""

    good_get = MockRequest(
        b"""GET / HTTP/1.1
Authorization: Basic ZGVtbzpkZW1v
"""
    )
    servermock = ServerMock()
    monkeypatch.chdir(temp_html_dir)
    handler = CustomServerHandler(good_get, ("0.0.0.0", 8000), servermock)
    handler.list_directory("/i_dont_exist_11623f")
    res = good_get.reponse_cache.decode("utf-8")
    assert "404" in res
    assert "No permission to list directory" in res
    handler.path = b"C:\\Users\\me\\OneDrive\\\xe0\xcd\xa1\xca\xd2\xc3\\my.txt"
    good_get.reponse_cache = b""
    handler.list_directory(str(temp_html_dir))
    res = good_get.reponse_cache.decode("utf-8")
    assert "Content-Length: 1083" in res


def test_human_readable_size():
    assert CustomServerHandler.human_readable_size(1023) == "1023.000B"
    assert CustomServerHandler.human_readable_size(1024) == "1.000KiB"
    assert CustomServerHandler.human_readable_size(1048576) == "1.000MiB"
    assert CustomServerHandler.human_readable_size(1073741824) == "1.000GiB"
    assert CustomServerHandler.human_readable_size(1099511627776) == "1.000TiB"
