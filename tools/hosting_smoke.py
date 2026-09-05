#!/usr/bin/env python3
"""Test the static Docker host or its proxy over real HTTP(S); never signs into Google.

Requires only Python 3.10+ for HTTP tests. --browser additionally needs Playwright
and a Chromium installation. TLS validation is deliberately never disabled.
"""
import argparse
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--chromium', help='Optional Chromium executable path')
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if parts.scheme not in ('http', 'https') or not parts.netloc or parts.path not in ('', '/') or parts.query or parts.fragment or parts.username or parts.password:
        parser.error('--url must be an HTTP(S) origin, not a path, query or URL with credentials')
    origin = args.url.rstrip('/')
    checks = 0

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok:
            raise AssertionError(label)

    def request(path, method='GET'):
        try:
            response = urlopen(Request(origin + path, method=method), timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.headers, response.read()

    status, headers, body = request('/healthz')
    check(status == 200 and body == b'ok\n', 'Health endpoint')
    status, headers, body = request('/')
    check(status == 200 and b'<title>Paperweek</title>' in body, 'Application served')
    check(headers.get_content_type() == 'text/html', 'HTML MIME type')
    check(headers.get('X-Content-Type-Options') == 'nosniff', 'nosniff header')
    check(headers.get('Cross-Origin-Opener-Policy') == 'same-origin-allow-popups', 'Popup-compatible COOP header')
    check(headers.get('Referrer-Policy') == 'no-referrer', 'Referrer policy')
    check("'wasm-unsafe-eval'" in headers.get('Content-Security-Policy', ''), 'WASM permitted by CSP')
    check('no-cache' in headers.get('Cache-Control', ''), 'HTML revalidation')
    for path, mime in [('/app.mjs', 'text/javascript'), ('/paperweek-preview.wasm', 'application/wasm'), ('/manifest.webmanifest', 'application/manifest+json')]:
        status, headers, body = request(path)
        check(status == 200 and headers.get_content_type() == mime, f'MIME for {path}')
        if path.endswith('.wasm'):
            check(body[:4] == b'\0asm', 'Actual WebAssembly, not HTML fallback')
        if path.endswith('webmanifest'):
            check(json.loads(body)['start_url'] == './', 'Manifest stays at app origin')
    status, headers, body = request('/sw.js')
    check(status == 200 and 'no-store' in headers.get('Cache-Control', ''), 'Service-worker revalidation')
    status, _, body = request('/build-info.json')
    check(status == 200 and json.loads(body)['backend'] == 'preview', 'Renderer label is preview')
    for path in ['/.env', '/.git/config', '/web/app.mjs', '/Dockerfile', '/not-a-real-file', '/api/calendar']:
        status, _, _ = request(path)
        check(status == 404, f'Not publicly available: {path}')
    status, _, _ = request('/', method='POST')
    check(status == 405, 'No upload endpoint')
    status, headers, body = request('/app.mjs', method='HEAD')
    check(status == 200 and not body, 'HEAD supported')

    if args.browser:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=args.chromium)
            page = browser.new_page(viewport={'width':1280, 'height':900})
            errors = []
            violations = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: violations.append(message.text) if 'violates the following Content Security Policy' in message.text else None)
            page.goto(origin, wait_until='networkidle')
            page.wait_for_function("document.documentElement.dataset.ready === 'true'", timeout=30000)
            check('C/WASM preview' in page.locator('#engine-label').inner_text(), 'C/WASM preview actually launched')
            check(page.locator('#source-badge').inner_text() == 'DEMO', 'Generic demo, not live data')
            check(page.locator('#agenda-text li').count() > 0, 'Agenda populated')
            dark = page.locator('#calendar').evaluate('''(c) => {
                const data = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
                let n=0; for(let i=0;i<data.length;i+=4) if(data[i]<100 && data[i+1]<100 && data[i+2]<100) ++n;
                return n;
            }''')
            check(dark > 1000, 'Calendar text drawn by WASM')
            before = page.locator('[data-nav="2"] span').inner_text()
            page.locator('[data-nav="2"]').click()
            page.wait_for_timeout(200)
            check(page.locator('[data-nav="2"] span').inner_text() != before, 'Week/month navigation')
            page.locator('#settings-button').click()
            check(page.locator('.member-card').count() == 4, 'Four configurable generic members')
            page.locator('[name="title"]').fill('Docker smoke test')
            page.locator('button[type="submit"]').click()
            page.reload(wait_until='networkidle')
            page.wait_for_function("document.documentElement.dataset.ready === 'true'")
            page.locator('#settings-button').click()
            check(page.locator('[name="title"]').input_value() == 'Docker smoke test', 'Settings survive reload at same origin')
            check(not errors, f'No runtime errors: {errors}')
            check(not violations, f'No CSP violations: {violations}')
            page.locator('#cancel-settings').click()
            # localhost HTTP counts as secure for this test. This does not certify
            # the real tablet's certificate, DNS or PWA installation UI.
            if page.evaluate('isSecureContext'):
                page.wait_for_function("navigator.serviceWorker.getRegistration().then(r => Boolean(r && r.active))", timeout=15000)
                check(True, 'Public-assets service worker activated')
            browser.close()
    print(f'{checks} static-host checks passed. Google OAuth, NPM, Android and Docker itself are not exercised by this script.')


if __name__ == '__main__':
    main()
