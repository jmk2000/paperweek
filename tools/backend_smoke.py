#!/usr/bin/env python3
"""Public HTTP smoke check. No credentials, no Google calls, no mutations.

Run against your real HTTPS deployment. Trusted TLS validation stays enabled.
This tests the HTTP boundary, not Android, OAuth or an independent security audit.
"""
import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def run(origin):
    passed = 0
    def check(condition, label):
        nonlocal passed
        if not condition:
            raise RuntimeError(label)
        passed += 1
        print('PASS ' + label)
    def fetch(path):
        req = Request(origin + path, headers={'Accept':'*/*', 'User-Agent':'Paperweek-smoke/0.4'})
        try:
            r = urlopen(req, timeout=15)
        except HTTPError as e:
            r = e
        with r:
            return r.status, r.headers, r.read(4 * 1024 * 1024)
    status, headers, data = fetch('/healthz')
    check(status == 200 and json.loads(data).get('status') == 'running', 'application health')
    status, headers, data = fetch('/api/meta')
    check(status == 200 and json.loads(data).get('backend') is True, 'backend API, not legacy static hosting')
    status, headers, data = fetch('/')
    check(status == 200 and b'backend-app.mjs' in data, 'unattended display shell')
    check('no-store' in headers.get('Cache-Control',''), 'display shell cache policy')
    check("frame-ancestors 'none'" in headers.get('Content-Security-Policy',''), 'frame restriction / CSP')
    check(headers.get('X-Content-Type-Options') == 'nosniff', 'MIME sniffing disabled')
    status, headers, data = fetch('/admin')
    check(status == 200 and b'admin.mjs' in data, 'administration shell')
    status, headers, data = fetch('/paperweek-preview.wasm')
    check(status == 200 and data.startswith(b'\0asm'), 'compiled C WebAssembly served')
    check(headers.get_content_type() == 'application/wasm', 'WebAssembly content type')
    status, headers, data = fetch('/server-sw.js')
    check(status == 200 and b'addEventListener' in data, 'backend service worker served')
    for path in ('/api/session', '/api/admin/config', '/api/display/config', '/api/admin/devices'):
        status, headers, data = fetch(path)
        check(status == 401, path + ' requires a session')
        check('no-store' in headers.get('Cache-Control',''), path + ' is not cacheable')
    for path in ('/.env.private', '/backend/app.py', '/data/paperweek.sqlite3'):
        status, headers, data = fetch(path)
        check(status == 404, path + ' is not served')
    print(f'\n{passed} public HTTP checks passed. Next check live Google sync and the physical tablet in Administration.')
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='HTTPS origin; HTTP allowed only for loopback development')
    args = parser.parse_args()
    origin = args.url.rstrip('/')
    u = urlsplit(origin)
    if not u.hostname or u.path or u.query or u.fragment or u.username or u.password or not (u.scheme == 'https' or u.scheme == 'http' and u.hostname in ('localhost','127.0.0.1','::1')):
        parser.error('Use an HTTPS origin without a path (HTTP only for loopback).')
    try:
        run(origin)
    except (RuntimeError, URLError, ValueError, OSError) as e:
        raise SystemExit('CHECK FAILED: ' + str(e)) from None


if __name__ == '__main__':
    main()
