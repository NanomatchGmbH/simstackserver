import http.server
import cgi
import base64
import json
import time
import urllib
from functools import partial
from urllib.parse import urlparse, parse_qs
import string
import random
from threading import Thread


def random_string(stringLength=10):
    """Generate a random string of fixed length """
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(stringLength))


class CustomServerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)

        super().extensions_map.update({
            '.lsf': 'text/plain',
            '.ini': 'text/plain',
            '.stderr': 'text/plain',
            '.stdout': 'text/plain',
            '.yml': 'text/plain',
            '.json': 'text/plain',
            '.script': 'text/plain',
            '.pbs': 'text/plain',
            '.slr': 'text/plain'
        })

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header(
            'WWW-Authenticate', 'Basic realm="Demo Realm"')
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        key = self.server.get_auth_key()

        ''' Present frontpage with user authentication. '''
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()

            response = {
                'success': False,
                'error': 'No auth header received'
            }

            self.wfile.write(bytes(json.dumps(response), 'utf-8'))

        elif self.headers.get('Authorization') == 'Basic ' + str(key):
            """
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            getvars = self._parse_GET()

            response = {
                'path': self.path,
                'get_vars': str(getvars)
            }

            base_path = urlparse(self.path).path
            print(base_path)
            if base_path == '/path1':
                # Do some work
                pass
            elif base_path == '/path2':
                # Do some work
                pass
            """

            """Serve a GET request."""
            f = self.send_head()
            if f:
                try:
                    self.copyfile(f, self.wfile)
                finally:
                    f.close()
            #self.wfile.write(bytes(json.dumps(response), 'utf-8'))
        else:
            self.do_AUTHHEAD()

            response = {
                'success': False,
                'error': 'Invalid credentials'
            }

            self.wfile.write(bytes(json.dumps(response), 'utf-8'))

    def do_POST(self):
        key = self.server.get_auth_key()

        ''' Present frontpage with user authentication. '''
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()

            response = {
                'success': False,
                'error': 'No auth header received'
            }

            self.wfile.write(bytes(json.dumps(response), 'utf-8'))

        elif self.headers.get('Authorization') == 'Basic ' + str(key):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            postvars = self._parse_POST()
            getvars = self._parse_GET()

            response = {
                'path': self.path,
                'get_vars': str(getvars),
                'post_vars': str(postvars)
            }

            base_path = urlparse(self.path).path
            print(base_path)
            if base_path == '/path1':
                # Do some work
                pass
            elif base_path == '/path2':
                # Do some work
                pass

            self.wfile.write(bytes(json.dumps(response), 'utf-8'))
        else:
            self.do_AUTHHEAD()

            response = {
                'success': False,
                'error': 'Invalid credentials'
            }

            self.wfile.write(bytes(json.dumps(response), 'utf-8'))

        response = {
            'path': self.path,
            'get_vars': str(getvars),
            'post_vars': str(postvars)
        }

        self.wfile.write(bytes(json.dumps(response), 'utf-8'))

    def _parse_POST(self):
        ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
        if ctype == 'multipart/form-data':
            postvars = cgi.parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers.getheader('content-length'))
            postvars = urllib.parse.parse_qs(
                self.rfile.read(length), keep_blank_values=1)
        else:
            postvars = {}

        return postvars

    def _parse_GET(self):
        getvars = parse_qs(urlparse(self.path).query)

        return getvars




class GracefulShutdownHTTPServerException(Exception):
    pass


class CustomHTTPServer(http.server.HTTPServer):
    key = random_string(100)

    def __init__(self, address, directory, handlerClass=CustomServerHandler):
        self.timeout = 1.0
        self.directory = directory
        self._do_shutdown = False
        handlerClass = partial(handlerClass, directory = self.directory)
        super().__init__(address, handlerClass)

    def set_auth(self, username, password):
        self.key = base64.b64encode(
            bytes('%s:%s' % (username, password), 'utf-8')).decode('ascii')

    def do_graceful_shutdown(self):
        # By default, we do a graceful shutdown after timeout anyways, so we really do that.
        self.timeout = 0.01
        # In case we are being hammered with requests, we also explicitly shutdown here:
        self._do_shutdown = True

    def get_auth_key(self):
        return self.key

    def serve_for_duration(self):
        try:
            while True:
                self.handle_request()
                if self._do_shutdown:
                    break
        except GracefulShutdownHTTPServerException:
            pass

    def handle_timeout(self):
        super().handle_timeout()

class CustomHTTPServerThread(Thread, CustomHTTPServer):
    def __init__(self, address, directory, *args, **kwargs):
        Thread.__init__(self, target=self.serve_for_duration, *args, **kwargs)
        handlerClass = kwargs["handlerClass"] if "handlerClass" in kwargs else CustomServerHandler
        CustomHTTPServer.__init__(self, address, directory, handlerClass)


if __name__ == '__main__':
    server = CustomHTTPServerThread(('', 8888), ".")
    server.set_auth('demo', 'demo')
    server.start()
    server.join()
