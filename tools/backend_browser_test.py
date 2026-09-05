#!/usr/bin/env python3
"""Browser component tests against the real backend over a Python HTTP bridge.

Browser navigation to local servers is policy-blocked in the authoring sandbox.
This mounts the actual DOM/CSS/C/WASM and calls a real local HTTP backend using an
exposed test bridge. It DOES NOT test browser CSP, cookie handling, Google login,
service workers, Android or NPM. Those require a normal end-to-end host run.
"""
import argparse
import base64
from datetime import date, timedelta
import json
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app import create_app
from backend.settings import Settings
from backend.security import password_hash
from cryptography.fernet import Fernet
from backend.google import SCOPES
from backend.ical_parser import parse_calendar

PASSWORD='component test administrator password'


def bundle(entry):
    modules=['config','dates','events','renderer','backend-client',entry]
    result=['globalThis.__modules={};']
    for name in modules:
        s=(ROOT/'web'/f'{name}.mjs').read_text()
        exports=re.findall(r'export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)',s)
        s=re.sub(r"import\s+\{([^}]+)\}\s+from\s+['\"]\./([^'\"]+)\.mjs['\"];?",lambda m:f'const {{{m[1]}}}=__modules[{json.dumps(m[2])}];',s)
        s=re.sub(r'\bexport\s+','',s)
        if name==entry:
            result.append(f'globalThis.__app=(async()=>{{{s}\n}})();')
        else:
            result.append(f'__modules[{json.dumps(name)}]=(()=>{{{s}\nreturn {{{",".join(exports)}}};}})();')
    return '\n'.join(result)


def mount(page, entry, client, origin):
    html=(ROOT/'web'/('admin.html' if entry=='admin' else 'server.html')).read_text()
    html=re.sub(r'<link[^>]+>','',html)
    html=re.sub(r'<script type="module"[^>]+></script>','',html)
    html=html.replace('</head>','<style>'+(ROOT/'web/styles.css').read_text()+(ROOT/'web/backend.css').read_text()+'</style></head>')
    page.set_content(html)
    wasm=base64.b64encode((ROOT/'dist-preview/paperweek-preview.wasm').read_bytes()).decode()
    def bridge(data):
        opts=data.get('opts') or {}
        headers={**(opts.get('headers') or {}),'origin':origin}
        response=client.request(opts.get('method','GET'),data['path'],headers=headers,content=opts.get('body'))
        return {'status':response.status_code,'text':response.text}
    page.expose_function('python_api',bridge)
    page.add_script_tag(content="""
    globalThis.__settings=new Map();
    Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:k=>__settings.get(k)||null,setItem:(k,v)=>__settings.set(k,v),removeItem:k=>__settings.delete(k)}});
    globalThis.fetch=async(path,opts={})=>{
      if(String(path).endsWith('build-info.json'))return Response.json({backend:'preview',version:'0.5.0'});
      if(String(path).endsWith('paperweek-preview.wasm'))return new Response(Uint8Array.from(atob('@WASM@'),c=>c.charCodeAt(0)));
      const r=await python_api({path,opts:{method:opts.method,headers:opts.headers,body:opts.body}});
      return new Response(r.text,{status:r.status,headers:{'content-type':'application/json'}});
    };
    """.replace('@WASM@',wasm))
    page.add_script_tag(content=bundle(entry))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chromium');parser.add_argument('--screenshots',type=Path);args=parser.parse_args()
    checks=0
    def check(condition,message):
        nonlocal checks
        checks+=1
        if not condition:raise AssertionError(message)
    socket_=socket.socket();socket_.bind(('127.0.0.1',0));port=socket_.getsockname()[1];socket_.close()
    origin=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory() as folder:
        settings=Settings(origin,password_hash(PASSWORD),Fernet.generate_key().decode(),Path(folder),ROOT/'dist-preview')
        from dataclasses import replace
        settings=replace(settings,client_id='example.apps.googleusercontent.com',client_secret='fixture-secret')
        state={'title':'HTTP integration fixture event','refreshes':0}
        def fake_google(request):
            if request.url.host=='oauth2.googleapis.com':
                form=parse_qs(request.content.decode())
                refresh=form.get('grant_type')==['refresh_token']
                if refresh:state['refreshes']+=1
                return httpx.Response(200,json={'access_token':'fixture-access','token_type':'Bearer','expires_in':3600,'scope':' '.join(SCOPES),**({} if refresh else {'refresh_token':'fixture-refresh'})})
            if request.url.path.endswith('calendarList'):
                return httpx.Response(200,json={'items':[{'id':f'fixture-{i}','summary':f'Calendar {i}','accessRole':'owner'} for i in range(1,5)]})
            today=date.today()
            return httpx.Response(200,json={'items':[{'id':'fixture-event','iCalUID':'fixture-uid','summary':state['title'],'start':{'date':today.isoformat()},'end':{'date':(today+timedelta(days=1)).isoformat()}}]})
        async def fake_feed(job):
            if job['action']=='fetch':
                data=('BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:rota-fixture\nDTSTART;VALUE=DATE:'+date.today().strftime('%Y%m%d')+'\nSUMMARY:Standby\nEND:VEVENT\nEND:VCALENDAR').encode()
                return {'data':base64.b64encode(data).decode(),'etag':'"demo"','modified':'','notModified':False}
            return parse_calendar(base64.b64decode(job['data']),job['start'],job['stop'],job['fallback'],job['zone'])
        app=create_app(settings,httpx.MockTransport(fake_google),feed_runner=fake_feed)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        deadline=time.time()+10
        while not server.started:
            if time.time()>deadline:raise RuntimeError('Test backend did not start.')
            time.sleep(.02)
        try:
            with httpx.Client(base_url=origin) as admin_client,httpx.Client(base_url=origin) as display_client,sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=args.chromium)
                page=browser.new_page(viewport={'width':1280,'height':1000})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                mount(page,'admin',admin_client,origin)
                check(page.locator('#login-panel').is_visible(),'admin login visible')
                page.locator('#password').fill(PASSWORD);page.locator('#login-form button').click()
                page.locator('#admin-content').wait_for(state='visible')
                page.wait_for_function("document.querySelectorAll('.member-card').length===4")
                check(page.locator('.member-card').count()==4,'four generic mappings')
                check(page.locator('#add-member').inner_text()=='Add person','people are separate from sources')
                page.locator('#add-member').click()
                check(page.locator('.member-card').count()==5,'adding a fifth person creates one display slot')
                page.locator('.member-card').last.locator('.remove-member').click()
                check(page.locator('.member-card').count()==4,'removing unsaved extra person restores four slots')
                check('disconnected' in page.locator('#google-state').inner_text(),'no misleading Google connection')
                page.locator('[name="title"]').fill('Our household calendar')
                page.locator('#config-form [name="timezone"]').fill('Europe/London')
                page.locator('#config-form button[type="submit"]').click()
                page.wait_for_function("document.querySelector('#save-state').textContent.startsWith('Saved')")
                check(admin_client.get('/api/admin/config').json()['config']['timezone']=='Europe/London','shared config persisted through HTTP')
                # Additional source form uses a fake feed transport but real
                # parser, API, encrypted storage, preview and rule classification.
                page.locator('.member-card').nth(1).locator('.attach-source').click()
                check(page.locator('#source-form [name="member"]').input_value()=='member-2','attach-source button keeps the same owner')
                page.locator('#source-form [name="label"]').fill('Work rota')
                page.locator('#source-form [name="member"]').select_option('member-2')
                page.locator('#source-form [name="mode"]').select_option('rota')
                page.locator('#source-form [name="timezone"]').fill('Europe/London')
                page.locator('#source-form [name="url"]').fill('https://calendar.example.net/fixture.ics?key=not-a-secret')
                page.locator('#add-rota-rule').click()
                page.locator('.rota-rule [data-field="text"]').fill('Standby')
                page.locator('.rota-rule [data-field="action"]').select_option('oncall')
                page.locator('#source-form button[type="submit"]').click()
                page.wait_for_function("document.querySelector('#source-state').textContent.includes('Saved')")
                check('paused' in page.locator('#source-state').inner_text(),'new subscription paused until reviewed')
                check(page.locator('#source-form [name="url"]').input_value()=='','saved private URL never prefilled')
                source_rows=admin_client.get('/api/admin/sources').json()['sources']
                check(source_rows[0]['hasUrl'] and 'url' not in source_rows[0],'admin source response omits secret URL')
                page.locator('#preview-source').click()
                page.wait_for_function("document.querySelector('#source-preview-state').textContent.includes('oncall: 1')")
                check('Standby' in page.locator('#source-preview-results').inner_text(),'preview shows original and interpreted feed entries')
                page.locator('#source-form [name="enabled"]').check()
                page.locator('#source-form button[type="submit"]').click()
                page.wait_for_function("document.querySelector('#source-state').textContent.includes('enabled')")
                check(admin_client.get('/api/admin/sources').json()['sources'][0]['enabled'],'reviewed subscription enabled')
                if args.screenshots:
                    args.screenshots.mkdir(parents=True,exist_ok=True)
                    page.locator('#preview-source').click()
                    page.wait_for_function("document.querySelector('#source-preview-state').textContent.includes('oncall: 1')")
                    page.locator('#source-panel').screenshot(path=str(args.screenshots/'sources.png'))
                page.locator('#pair-create button').click()
                page.wait_for_function("document.querySelector('#pair-code-output').textContent.length>0")
                code=page.locator('#pair-code-output').inner_text()
                check(len(code)==9,'pair code generated')
                if args.screenshots:
                    args.screenshots.mkdir(parents=True,exist_ok=True)
                    # Hide the usable test pairing code, even though server is temporary.
                    page.locator('#pair-code-output').evaluate('(e)=>e.textContent="DEMO-CODE"')
                    page.locator('#notice').evaluate('(e)=>e.textContent="Demonstration administration screen · invented settings"')
                    page.screenshot(path=str(args.screenshots/'admin.png'),full_page=True)
                tablet=browser.new_page(viewport={'width':1280,'height':850},has_touch=True)
                tablet.on('pageerror',lambda e:errors.append(str(e)))
                mount(tablet,'backend-app',display_client,origin)
                tablet.locator('#pair-dialog').wait_for(state='visible')
                check('Pair this display' in tablet.locator('#pair-dialog').inner_text(),'tablet requires pairing')
                tablet.locator('#pair-code').fill(code);tablet.locator('#pair-form button').click()
                tablet.wait_for_function("document.querySelector('#message').textContent.includes('Invented demo')")
                check(display_client.get('/api/session').json()['role']=='display','paired read-only role')
                check(display_client.get('/api/admin/config').status_code==403,'tablet cannot read admin configuration')
                check(tablet.locator('#agenda-text li').count()>0,'actual WASM agenda rendered')
                check('C/WASM' in tablet.locator('#engine-label').inner_text(),'renderer provenance label correct')
                if args.screenshots:tablet.screenshot(path=str(args.screenshots/'tablet-month.png'),full_page=True)
                tablet.locator('[data-nav="2"]').click();tablet.wait_for_function("document.querySelector('[data-nav=\"2\"] span').textContent==='Month view'")
                check('Month view'==tablet.locator('[data-nav="2"] span').inner_text(),'week/month toggle')
                if args.screenshots:tablet.screenshot(path=str(args.screenshots/'tablet-week.png'),full_page=True)
                before=tablet.locator('#agenda-text').text_content();tablet.locator('[data-nav="3"]').click();tablet.wait_for_function("old=>document.querySelector('#agenda-text').textContent!==old",arg=before,timeout=15000)
                check(tablet.locator('#agenda-text').text_content()!=before,'next week navigation')
                # Real HTTP backend + fake Google transport: no browser token flow.
                headers={'origin':origin,'x-paperweek-request':'1'}
                start=admin_client.post('/api/admin/google/connect',json={},headers=headers).json()
                oauth_state=parse_qs(urlsplit(start['url']).query)['state'][0]
                response=admin_client.get('/api/oauth/callback',params={'state':oauth_state,'code':'fixture-code'},follow_redirects=False)
                check(response.status_code==303,'server OAuth callback completed with fake Google')
                saved=admin_client.get('/api/admin/config').json()
                saved['config']['source']='google'
                for i,m in enumerate(saved['config']['members'],1):m['calendarId']=f'fixture-{i}'
                check(admin_client.put('/api/admin/config',json=saved,headers=headers).status_code==200,'server Google calendar mappings saved')
                tablet.locator('[data-nav="1"]').click()
                tablet.wait_for_function("document.querySelector('#agenda-text').textContent.includes('HTTP integration fixture event')",timeout=20000)
                check(tablet.locator('#source-badge').inner_text()=='SERVER','Google data arrives via backend, not demo')
                status=admin_client.get('/api/admin/status').json()
                check(any(w['kind']=='ical' and w['success'] for w in status['windows']),'iCalendar cache ready alongside Google')
                day=date.today().isoformat()
                snapshot=display_client.get('/api/display/snapshot',params={'first':day,'days':1}).json()
                check(any(e['summary']=='[PW:ONCALL]' for b in snapshot.get('batches',[]) for e in b['items']),'rota feed becomes status marker in same shared renderer')
                owner=next(b for b in snapshot['batches'] if b['member']=='member-2')
                check({e['summary'] for e in owner['items']}=={'HTTP integration fixture event','[PW:ONCALL]'},'Google appointments and subscribed rota coexist under one person')
                token=app.state.store.get_secret('google_token');token['expires_at']=0;app.state.store.set_secret('google_token',token)
                state['title']='Updated after automatic token refresh'
                admin_client.post('/api/admin/sync',json={},headers=headers)
                deadline=time.time()+15
                while state['refreshes']==0:
                    if time.time()>deadline:raise AssertionError('Refresh did not run')
                    tablet.wait_for_timeout(50)
                tablet.locator('#display-menu > summary').click()
                tablet.locator('#refresh').click()
                tablet.wait_for_function("document.querySelector('#agenda-text').textContent.includes('Updated after automatic token refresh')",timeout=15000)
                check(state['refreshes']>0,'expired Google token refreshed without tablet sign-in')
                tablet.locator('.agenda summary').click();tablet.locator('#offline-copy').check()
                check(tablet.evaluate("__settings.has('paperweek.offline.v4')"),'offline view saved only when enabled')
                # Simulate a network break at the browser bridge; no invented events replace saved data.
                tablet.evaluate("()=>{globalThis.__liveFetch=globalThis.fetch;globalThis.fetch=async()=>{throw new Error('offline');};}")
                tablet.locator('#display-menu > summary').click()
                tablet.locator('#refresh').click();tablet.wait_for_timeout(150)
                check('last loaded view' in tablet.locator('#message').inner_text(),'offline warning retains existing view')
                tablet.evaluate('()=>{globalThis.fetch=globalThis.__liveFetch;}')
                headers={'origin':origin,'x-paperweek-request':'1'}
                device=admin_client.get('/api/admin/devices').json()[0]
                admin_client.request('DELETE','/api/admin/devices/'+device['id'],json={},headers=headers)
                tablet.locator('#display-menu > summary').click()
                tablet.locator('#refresh').click();tablet.locator('#pair-dialog').wait_for(state='visible')
                check(not tablet.evaluate("__settings.has('paperweek.offline.v4')"),'online revocation erases local cache')
                check(not errors,'no browser script exceptions: '+str(errors))
                browser.close()
        finally:
            server.should_exit=True;thread.join(10)
    print(f'{checks} backend/browser component checks passed (Python HTTP bridge; not browser HTTPS/CSP/PWA).')


if __name__=='__main__':main()
