#!/usr/bin/env python3
"""Exercise the real browser and packaged C/WASM, with mocked authenticated API.

Run from the repository: python tests/browser/planner_smoke.py --site dist-preview
Requires: pip install playwright; playwright install chromium (or --chromium PATH).
No providers, real credentials, or private household data are used. The temporary
server uses the deployment's CSP. Run only against a freshly packaged build.
"""
from __future__ import annotations
import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright, expect
from planner_fixture import fixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.settings import DisplayConfig

CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
       "img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs':'text/javascript', '.wasm':'application/wasm'}
    def do_GET(self):
        if self.path == '/': self.path = '/server.html'
        if self.path == '/admin': self.path = '/admin.html'
        return super().do_GET()
    def end_headers(self):
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def log_message(self, *_): pass

class API:
    def __init__(self):
        self.config, self.events = fixture()
        self.revision = 1
        self.offline = False
        self.revoked = False
        self.warning = False
        self.ready = True
        self.role = 'display'
        self.conflict = False
        self.puts = []
        self.requests = []

    async def handle(self, route):
        req = route.request
        u = urlparse(req.url)
        self.requests.append(u.path)
        if self.offline:
            await route.abort('internetdisconnected'); return
        if self.revoked:
            await route.fulfill(status=401, json={'detail':'Display session expired.'}); return
        public = DisplayConfig.model_validate(self.config).public()
        record = dict(config=public, revision=self.revision, dataEpoch=1)
        if u.path == '/api/session': result = dict(role=self.role, label='Test display', expires=1800000000)
        elif u.path == '/api/display/config': result = record
        elif u.path == '/api/display/snapshot':
            query = parse_qs(u.query)
            result = dict(**record, first=query['first'][0], days=int(query['days'][0]), ready=self.ready,
                          batches=[dict(member=member,items=items) for member,items in self.events.items()],
                          stale=False, warnings=self.warning, coverage=[] if self.ready else [{'ready':False}],
                          connection='connected', lastSuccess=1788687000, unmappedMembers=[])
        elif u.path == '/api/admin/config' and req.method == 'PUT':
            body = req.post_data_json
            assert req.headers.get('x-paperweek-request') == '1'
            if self.conflict or body['revision'] != self.revision:
                await route.fulfill(status=409,json={'detail':'Settings changed in another browser. Reload before saving.'}); return
            self.config = DisplayConfig.model_validate(body['config']).model_dump()
            self.puts.append(deepcopy(body)); self.revision += 1
            result = dict(config=self.config,revision=self.revision)
        elif u.path == '/api/admin/config': result = dict(config=self.config,revision=self.revision)
        elif u.path == '/api/admin/status':
            result = dict(connection='connected',schedulerRunning=True,pollMinutes=5,windows=[],callbackUrl='http://localhost/api/oauth/callback',oauthConfigured=False)
        elif u.path == '/api/admin/devices': result = []
        elif u.path == '/api/admin/sources': result = {'sources':[]}
        elif u.path == '/api/admin/calendars': result = {'calendars':[]}
        elif u.path == '/api/logout': result = {'ok':True}
        else: raise AssertionError(f'Unexpected API request {req.method} {u.path}')
        await route.fulfill(status=200,json=result)

async def run(args):
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler,directory=str(args.site.resolve())))
    Thread(target=server.serve_forever,daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    def passed(label): checks.append(label); print('PASS',label,flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=args.chromium, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width':1704,'height':1050},service_workers='block', timezone_id='Europe/London')
        api = API()
        await context.route('**/api/**',api.handle)
        page = await context.new_page()
        errors = []
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.on('console',lambda msg:errors.append(msg.text) if 'Content Security Policy' in msg.text else None)
        await page.clock.install(time=datetime(2026,9,6,9,0,tzinfo=timezone.utc))
        if args.in_memory:
            from memory_host import MemoryHost
            host=MemoryHost(page,args.site,api);await host.setup()
        async def load_page(admin=False):
            if args.in_memory: await host.load(admin)
            else: await page.goto(url+('/admin' if admin else '/'))
        await load_page()
        print('START',await page.locator('#message').text_content(),errors,flush=True)
        await expect(page.locator('.planner-day')).to_have_count(7)
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-09-06')
        await expect(page.locator('.school-focus')).to_contain_text('Monday 7 Sept')
        await expect(page.locator('.planner-day[data-date="2026-09-10"] .planner-rota')).to_contain_text('ON CALL')
        await expect(page.locator('.planner-day[data-date="2026-09-10"] .planner-rota')).to_contain_text('18:00–08:00 (+1 day)')
        await expect(page.locator('.planner-day[data-date="2026-09-11"] .planner-rota')).to_contain_text('Until 08:00')
        await expect(page.locator('.planner-day[data-date="2026-09-08"] .planner-rota')).to_contain_text('Off duty')
        await expect(page.locator('.planner-day').first.locator('.planner-rota')).to_contain_text('Rota not confirmed')
        await expect(page.locator('.lesson-list')).to_have_count(0)
        passed('Sunday starts a rolling seven-day range; real C engine separates work, overnight on-call, off and unknown')
        await page.screenshot(path=str(args.output/'desktop-next-seven-days.png'),full_page=True)
        await page.locator('#toggle-lessons').click()
        await expect(page.locator('.planner-week .lesson-list')).to_have_count(10)
        await expect(page.locator('.school-focus .lesson-list')).to_have_count(0)
        await page.locator('#toggle-school').click()
        await expect(page.locator('.school-focus')).to_have_count(0)
        await expect(page.locator('.ready-line')).to_have_count(0)
        await expect(page.locator('.planner-week .lesson-list')).to_have_count(10)
        await expect(page.locator('.planner-week')).to_contain_text('Orchestra')
        await page.locator('#toggle-lessons').click()
        await expect(page.locator('.school-essential')).to_have_count(0)
        await expect(page.locator('.planner-week')).to_contain_text('Piano lesson')
        await page.locator('#toggle-school').click()
        passed('Independent essentials and timetable toggles never hide clubs; preparation strip stays compact')
        # Unchanged source snapshots must not replace the board DOM.
        await page.locator('.planner-day').first.evaluate("n=>n.dataset.retained='yes'")
        await page.locator('#refresh').evaluate('n=>n.click()')
        await expect(page.locator('#view-mode')).to_be_enabled()
        await expect(page.locator('.planner-day').first).to_have_attribute('data-retained','yes')
        passed('Unchanged API snapshot leaves the planner DOM intact')
        # Extra appointments should not disappear off a canvas or truncate silently.
        api.events['member-2'] += [dict(id=f'extra-{n}',summary=f'Extra appointment {n}',start={'dateTime':f'2026-09-07T{10+n}:00:00+01:00'},end={'dateTime':f'2026-09-07T{10+n}:30:00+01:00'}) for n in range(5)]
        await page.locator('#refresh').evaluate('n=>n.click()')
        await expect(page.locator('.more-events')).to_have_count(1)
        await page.locator('.more-events summary').click()
        await expect(page.get_by_text('Extra appointment 4',exact=True).first).to_be_visible()
        api.warning=True
        await page.locator('#refresh').evaluate('n=>n.click()')
        await expect(page.locator('#message')).to_contain_text('Review source rules')
        await expect(page.locator('.more-events')).to_have_attribute('open','')
        passed('Busy days have explicit overflow disclosure; feed warnings stay distinct from off-duty')
        api.config,api.events=fixture();api.warning=False
        await page.locator('#refresh').evaluate('n=>n.click()')
        await expect(page.locator('.more-events')).to_have_count(0)
        await page.select_option('#view-mode','week')
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-08-31')
        await page.select_option('#view-mode','rolling')
        await page.locator('[data-nav="3"]').click()
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-09-13')
        await expect(page.locator('.school-focus')).to_contain_text('Week B')
        await page.locator('[data-nav="1"]').click()
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-09-06')
        await page.select_option('#view-mode','month')
        await expect(page.locator('.month-day')).to_have_count(35)
        await page.screenshot(path=str(args.output/'desktop-month-overview.png'),full_page=True)
        await page.locator('.month-day[data-day="2026-09-07"]').click()
        await expect(page.locator('#day-dialog')).to_be_visible()
        await expect(page.locator('#day-dialog')).to_contain_text('PE uniform')
        await expect(page.locator('#day-dialog')).to_contain_text('Maths')
        await expect(page.locator('#day-dialog')).to_contain_text('Orchestra')
        await page.keyboard.press('Escape')
        await expect(page.locator('#day-dialog')).not_to_be_visible()
        passed('Calendar week, A/B following week, Today, compact month and keyboard-dismissable full-day detail')
        await page.select_option('#view-mode','rolling')
        for width,height,name in [(768,1024,'tablet-portrait'),(390,844,'phone'),(320,740,'small-phone'),(1280,960,'eink-monochrome')]:
            await page.set_viewport_size({'width':width,'height':height})
            if name == 'eink-monochrome': await page.locator('#toggle-mono').click()
            await page.screenshot(path=str(args.output/f'{name}.png'),full_page=True)
            overflow = await page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not overflow, f'Horizontal overflow at {width}px'
            await expect(page.locator('.planner-day')).to_have_count(7)
            targets=await page.locator('button:visible, select:visible').evaluate_all('ns=>ns.filter(n=>n.getBoundingClientRect().height<44).map(n=>[n.textContent,n.getBoundingClientRect().height])')
            assert not targets, f'Targets shorter than 44 CSS pixels: {targets}'
            if width==320:
                await page.select_option('#view-mode','month')
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
                await page.locator('.month-day[data-day="2026-09-07"]').click()
                assert not await page.evaluate('document.documentElement.scrollWidth > innerWidth')
                await page.locator('#close-day').click()
                await page.select_option('#view-mode','rolling')
        passed('320/390/768/1280px reflow without horizontal overflow, 44px controls, monochrome and narrow month detail')
        await page.locator('#display-menu').evaluate('n=>n.open=true')
        await page.locator('#fullscreen').click()
        await expect(page.locator('body')).to_have_class('web-display planner-display planner-mono planner-fullscreen')
        for width,height in [(1280,960),(390,844),(844,390)]:
            await page.set_viewport_size({'width':width,'height':height})
            for mode in ['rolling','month']:
                await page.locator('#display-menu').evaluate('n=>n.open=true')
                await page.select_option('#view-mode',mode)
                await page.locator('#display-menu').evaluate('n=>n.open=false')
                await expect(page.locator('.planner-month' if mode=='month' else '.planner-week')).to_be_visible()
                assert not await page.evaluate('document.documentElement.scrollHeight>innerHeight || document.documentElement.scrollWidth>innerWidth')
                assert await page.locator('#planner').evaluate('n=>n.clientHeight>innerHeight*.75')
                await page.screenshot(path=str(args.output/f'fullscreen-{width}-{mode}.png'))
            await page.locator('.month-day').first.click()
            await expect(page.locator('#day-dialog')).to_be_visible()
            await page.locator('#close-day').click()
        await page.evaluate('document.exitFullscreen()')
        await expect(page.locator('body')).not_to_have_class('web-display planner-display planner-mono planner-fullscreen')
        await page.select_option('#view-mode','rolling')
        assert await page.locator('.planner-toolbar').evaluate('n=>n.parentElement.tagName==="MAIN"')
        passed('Fullscreen phone/tablet week and month fill the viewport; display options and full-day details remain accessible')
        await load_page()
        await expect(page.locator('body')).to_have_class('web-display planner-display planner-mono')
        await expect(page.locator('#view-mode')).to_have_value('rolling')
        passed('Device view and monochrome preferences persist across reload')
        if not args.in_memory:
            installed=await context.new_page()
            await installed.set_viewport_size({'width':390,'height':844})
            await installed.add_init_script("""const originalMatchMedia=window.matchMedia.bind(window);
                window.matchMedia=query=>{const m=originalMatchMedia(query);if(query==='(display-mode: standalone)')Object.defineProperty(m,'matches',{value:true});return m;};""")
            await installed.goto(url+'/')
            await expect(installed.locator('body.planner-fullscreen.planner-mono')).to_be_visible()
            await expect(installed.locator('.planner-day')).to_have_count(7)
            assert await installed.locator('.planner-toolbar').evaluate('n=>!!n.closest("#display-menu")')
            assert not await installed.evaluate('document.documentElement.scrollHeight>innerHeight')
            await installed.close()
            passed('Standalone media activates the compact layout at startup without requesting fullscreen')

        # Failed navigation never displays a newly requested range as falsely empty.
        await page.locator('#offline-copy').evaluate('n=>{n.checked=true;n.dispatchEvent(new Event("change"));}')
        api.offline=True
        await page.locator('[data-nav="3"]').click()
        await expect(page.locator('#message')).to_contain_text('last loaded view')
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-09-06')
        await load_page()
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-09-06')
        await expect(page.locator('#message')).to_contain_text('saved view')
        await expect(page.locator('#view-mode')).to_have_value('rolling')
        passed('Failed navigation and offline reload retain exactly the last complete rolling range, with an explicit warning')
        api.offline=False;api.revoked=True
        await page.locator('#refresh').evaluate('n=>n.click()')
        await expect(page.locator('#pair-dialog')).to_be_visible()
        await expect(page.locator('.planner-day')).to_have_count(0)
        assert await page.evaluate('localStorage.getItem("paperweek.offline.v4")') is None
        passed('Online revocation clears visible and saved private data')
        api.revoked=False
        await load_page()
        await expect(page.locator('.planner-day')).to_have_count(7)
        await page.clock.set_system_time(datetime(2026,9,7,0,1,tzinfo=timezone.utc))
        await page.clock.run_for(22000)
        await expect(page.locator('.planner-day').first).to_have_attribute('data-date','2026-09-07')
        passed('Following Today advances the rolling window after household-local midnight')
        assert not errors, '\n'.join(errors)
        passed('No browser exceptions'+(' (CSP not exercised in memory host)' if args.in_memory else ' or CSP violations'))
        # Same real administration UI and server validation models, mocked persistence.
        api.role='admin'
        await load_page(admin=True)
        await expect(page.locator('#school-editor')).to_contain_text('Child 1')
        await page.set_viewport_size({'width':1280,'height':960})
        await page.locator('#school-editor').scroll_into_view_if_needed()
        await page.screenshot(path=str(args.output/'school-administration.png'),full_page=True)
        # Unchanged routines survive a settings save. This catches the editor accidentally dropping A/B.
        original = deepcopy(api.config['school'])
        await page.locator('#config-form').evaluate('f=>f.requestSubmit()')
        await expect(page.locator('#save-state')).to_contain_text('Saved')
        assert api.puts and api.puts[-1]['revision']==1
        assert api.config['school']==DisplayConfig.model_validate({**api.config,'school':original}).model_dump()['school']
        api.conflict=True
        await page.locator('#config-form').evaluate('f=>f.requestSubmit()')
        await expect(page.locator('#save-state')).to_contain_text('Settings changed')
        assert len(api.puts)==1
        passed('School editor round-trips weekly/A/B lessons and clubs through versioned save; concurrent edit conflict is surfaced')
        assert not errors, '\n'.join(errors)
        await browser.close()
    server.shutdown()
    (args.output/'results.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'api':'mocked','engine':'real packaged C/WASM','physical_eink':False,'host':'memory' if args.in_memory else 'HTTP','csp_tested':not args.in_memory},indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--in-memory',action='store_true',help='Native local modules and mock storage; no network/CSP/SW test')
    parser.add_argument('--site',type=Path,default=ROOT/'dist-preview')
    parser.add_argument('--output',type=Path,default=ROOT/'build'/'planner-smoke')
    parser.add_argument('--chromium',default=None,help='Optional system Chromium executable')
    args=parser.parse_args()
    if not (args.site/'build-info.json').is_file(): parser.error('Package the WASM preview before running this test.')
    asyncio.run(run(args))
