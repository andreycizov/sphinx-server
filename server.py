import sphinx_autobuild
import os
import sys
from contextlib import contextmanager
import base64
from livereload import Server
import BaseHTTPServer
import SimpleHTTPServer
import SocketServer
import yaml


class AuthHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """
    Authentication handler used to support HTTP authentication
    """
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm=\"Restricted area\"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        global key
        if self.headers.getheader('Authorization') is None:
            self.do_AUTHHEAD()
            self.wfile.write('Credentials required.')
            pass
        elif self.headers.getheader('Authorization') == 'Basic ' + key:
            SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
            pass
        else:
            self.do_AUTHHEAD()
            self.wfile.write('Credentials required.')
            pass


'''
This function is used to simulate the manipulation of the stack (like pushd and popd in BASH)
and change the folder with the usage of the context manager
'''
@contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    yield
    os.chdir(previous_dir)

from tornado import web
from tornado import escape
from livereload.handlers import LiveReloadHandler, LiveReloadJSHandler
from livereload.handlers import ForceReloadHandler, StaticFileHandler
from livereload.server import LiveScriptInjector

def server_application(self, port, host, liveport=None, debug=None, live_css=True):
    override_endpoint_client = True

    LiveReloadHandler.watcher = self.watcher
    LiveReloadHandler.live_css = live_css
    if liveport is None:
        liveport = port
    if debug is None and self.app:
        debug = True

    live_handlers = [
        (r'/livereload', LiveReloadHandler),
        (r'/forcereload', ForceReloadHandler),
        (r'/livereload.js', LiveReloadJSHandler)
    ]

    # The livereload.js snippet.
    # Uses JavaScript to dynamically inject the client's hostname.
    # This allows for serving on 0.0.0.0.

    live_reload_path = ":{port}/livereload.js?port={port}".format(port=liveport)
    if liveport == 80 or liveport == 443:
        live_reload_path = "/livereload.js?port={port}".format(port=liveport)

    src_script = ' + window.location.hostname + "{path}">'.format(path=live_reload_path)

    if override_endpoint_client:
        src_script = (
            ' + window.location.host + "/livereload.js?port="'
            ' + window.location.port + "'
            '>'
        )

    live_script = escape.utf8((
        '<script type="text/javascript">'
        'document.write("<script src=''//"'
        '{src_script}'
        ' </"+"script>");'
        '</script>'
    ).format(src_script=src_script))

    web_handlers = self.get_web_handlers(live_script)

    class ConfiguredTransform(LiveScriptInjector):
        script = live_script

    if liveport == port:
        handlers = live_handlers + web_handlers
        app = web.Application(
            handlers=handlers,
            debug=debug,
            transforms=[ConfiguredTransform]
        )
        app.listen(port, address=host)
    else:
        app = web.Application(
            handlers=web_handlers,
            debug=debug,
            transforms=[ConfiguredTransform]
        )
        app.listen(port, address=host)
        live = web.Application(handlers=live_handlers, debug=False)
        live.listen(liveport, address=host)


if __name__ == '__main__':

    key = ''
    config_file = '.sphinx-server.yml'
    install_folder = '/opt/sphinx-server/'
    build_folder = os.path.realpath('_build/html')
    source_folder = os.path.realpath('.')
    configuration = None
    with open(install_folder + config_file, 'r') as config_stream:
        configuration = yaml.load(config_stream)

        if os.path.isfile(source_folder + '/' + config_file):
            with open(source_folder + '/' + config_file, "r") as custom_stream:
                configuration.update(yaml.load(custom_stream))

    if not os.path.exists(build_folder):
        os.makedirs(build_folder)

    if configuration.get('autobuild'):

        ignored_files = []
        for path in configuration.get('ignore'):
            ignored_files.append(os.path.realpath(path))

        builder = sphinx_autobuild.SphinxBuilder(
            outdir=build_folder,
            args=['-b', 'html', source_folder, build_folder]+sys.argv[1:],
            ignored=ignored_files
        )

        server = Server(watcher=sphinx_autobuild.LivereloadWatchdogWatcher())
        server.watch(source_folder, builder)
        server.watch(build_folder)

        builder.build()

        server.application = server_application.__get__(server, Server)
        server.serve(port=8000, host='0.0.0.0', root=build_folder)
    else:
        # Building once when server starts
        builder = sphinx_autobuild.SphinxBuilder(outdir=build_folder, args=['-b', 'html', source_folder, build_folder]+sys.argv[1:])
        builder.build()

        sys.argv = ['nouser', '8000']

        if configuration.get('credentials')['username'] is not None:
            auth = configuration.get('credentials')['username'] + ':' + configuration.get('credentials')['password']
            key = base64.b64encode(auth)

            with pushd(build_folder):
                BaseHTTPServer.test(AuthHandler, BaseHTTPServer.HTTPServer)
        else:
            with pushd(build_folder):
                Handler = SimpleHTTPServer.SimpleHTTPRequestHandler
                httpd = SocketServer.TCPServer(('', 8000), Handler)
                httpd.serve_forever()
