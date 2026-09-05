#!/usr/bin/env python3
"""Development-only static server. Serves the built public assets, never source or credentials."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import mimetypes
class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cross-Origin-Opener-Policy','same-origin-allow-popups')
        super().end_headers()
    def list_directory(self,path):
        self.send_error(404);return None
if __name__=='__main__':
    root=Path(__file__).resolve().parent
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',default='dist-preview');p.add_argument('--bind',default='127.0.0.1');p.add_argument('--port',type=int,default=8080)
    a=p.parse_args();directory=(root/a.directory).resolve()
    if not (directory/'build-info.json').is_file():p.error('Choose a built dist-preview or dist-lvgl directory. The source tree is not a web root.')
    mimetypes.add_type('application/wasm','.wasm');mimetypes.add_type('text/javascript','.mjs')
    print(f'Serving public app assets at http://{a.bind}:{a.port}. Ctrl-C stops the server.',flush=True)
    if a.bind not in ('localhost','127.0.0.1','::1'):print('LAN HTTP: demo only. Use HTTPS for Google sign-in, installation and wake lock.',flush=True)
    server=ThreadingHTTPServer((a.bind,a.port),partial(Handler,directory=str(directory)))
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
