import datetime
import http.server
import cgi
import base64
import json
import logging
import os
import html
import sys
import io
import time
import urllib
from functools import partial
from http import HTTPStatus
from urllib.parse import urlparse, parse_qs
import string
import random
from threading import Thread
import SimStackServer.Data as DataDir




def random_string(stringLength=10):
    """Generate a random string of fixed length """
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(stringLength))


class CustomServerHandler(http.server.SimpleHTTPRequestHandler):
    static_files = [
        "/dirlist.css"
    ]
    def __init__(self,*args,**kwargs):
        self._logger = logging.getLogger("HTTPServerHandler")
        self._favicon = self._read_static_binary_file_to_memory("favicon.ico")
        super().__init__(*args,**kwargs)

        super().extensions_map.update({
            '.lsf': 'text/plain',
            '.body': 'text/plain',
            '.ini': 'text/plain',
            '.stderr': 'text/plain',
            '.stdout': 'text/plain',
            '.yml': 'text/plain',
            '.json': 'text/plain',
            '.dat': 'text/plain',
            '.txt': 'text/plain',
            '.sge': 'text/plain',
            '.log': 'text/plain',
            '.script': 'text/plain',
            '.pbs': 'text/plain',
            '.slr': 'text/plain',
            '': 'text/plain'
        })

    def _get_static_http_path(self):
        data_dir = os.path.join(os.path.dirname(os.path.realpath(DataDir.__file__)), "static_http")
        return data_dir

    def _read_static_binary_file_to_memory(self, filename):
        data_dir = self._get_static_http_path()
        favpath = os.path.join(data_dir, filename)
        with open(favpath,'rb') as infile:
            return infile.read()

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
            """
            """
            if base_path == '/path1':
                # Do some work
                pass
            elif base_path == '/path2':
                # Do some work
                pass
            """

            """Serve a GET request."""
            if self.path == "/favicon.ico":
                ctype = self.guess_type(self.path)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-type", ctype)
                self.send_header("Content-Length", len(self._favicon)-1)
                self.end_headers()
                self.wfile.write(self._favicon)
                return

            if self.path in self.static_files:
                ctype = self.guess_type(self.path)
                mypath = self.path[1:]
                data = self._read_static_binary_file_to_memory(mypath)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-type", ctype)
                self.send_header("Content-Length", len(data) - 1)
                self.end_headers()
                self.wfile.write(data)
                return

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

    @staticmethod
    def human_readable_size(size, decimal_places=3):
        for unit in ['B','KiB','MiB','GiB','TiB']:
            if size < 1024.0:
                break
            size /= 1024.0
        return f"{size:.{decimal_places}f}{unit}"

    def list_directory(self, path):
        """Helper to produce a directory listing (absent index.html).
        Override of same file in server.py

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().

        """
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(
                HTTPStatus.NOT_FOUND,
                "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        displaypath = html.escape(displaypath, quote=False)
        enc = sys.getfilesystemencoding()
        title = 'Directory listing for %s' % displaypath
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<link rel="stylesheet" href="/dirlist.css" />')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc)
        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<br/><center><b>Index of %s</b></center><br/>' % title)
        r.append('<div class="list">')
        r.append('<table summary="Directory Listing" cellpadding="0" cellspacing="0">')
        r.append('<thead><tr><th class="n">Name</th><th class="m">Last Modified</th><th class="s">Size</th><th class="t">Type</th></tr></thead>')
        #r.append('<thead><tr><th class="n">Name</th><th class="m">Last Modified</th><th class="t">Type</th></thead>')
        r.append('<tbody>')
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            filetype = "File"
            lastmodified = "-"
            filesize = ""
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
                filetype = "Link"
            elif os.path.islink(fullname):
                displayname = name + "@"
                filetype = "Directory"
                # Note: a link to a directory displays with @ and links with /
            elif os.path.isfile(fullname):
                statdict = os.stat(fullname)
                lastmodified = datetime.datetime.fromtimestamp(statdict.st_mtime)
                filesize = self.human_readable_size(statdict.st_size,decimal_places=2)
            r.append('<tr>'
                     '<td class="n"><a href="%s">%s</a></td>'
                     '<td class="m">%s</td>'
                     '<td class="s">%s</td>'
                     '<td class="t">%s</td>'
                     '</tr>'
                    % (urllib.parse.quote(linkname,
                                          errors='surrogatepass'),
                       html.escape(displayname, quote=False),lastmodified,filesize,filetype))

        r.append('</tbody>')
        r.append('</div></body>\n</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f




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
