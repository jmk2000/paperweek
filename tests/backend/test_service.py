"""Offline integration tests with a fake Google HTTPS transport, not live Google."""
from __future__ import annotations
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit, unquote
import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.google import SCOPES
from backend.security import COOKIE, digest, password_hash, password_ok
from backend.settings import DisplayConfig, Settings
from backend.storage import Store, dumps
from backend.sync import add_month, bounds, month_start, months_for, validate_raw, intersects

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = 'test administrator password, not a credential'
ADMIN_HASH = password_hash(PASSWORD)
ORIGIN = 'https://paperweek.example.net'
HEADERS = {'origin':ORIGIN, 'x-paperweek-request':'1'}
TODAY = date.today()
MONTH = month_start(TODAY)
DAY = MONTH.replace(day=10)


def event(title='Appointment', id='event-a', day=DAY, **more):
    return {'id':id, 'iCalUID':id+'-uid', 'summary':title, 'start':{'date':day.isoformat()},
            'end':{'date':(day+timedelta(days=1)).isoformat()}, **more}


class FakeGoogle:
    def __init__(self):
        self.calls = []
        self.token_calls = []
        self.events = {'calendar-a':[event()], 'calendar-b':[]}
        self.fail = None
        self.pagination = False
        self.repeat_page = False
        self.next_refresh_error = None
        self.omit_refresh = False
        self.scope = ' '.join(SCOPES)
        self.calendar_items = [{'id':k,'summary':k,'accessRole':'owner'} for k in self.events]

    def __call__(self, request):
        self.calls.append(request)
        if request.url.host == 'oauth2.googleapis.com':
            form = parse_qs(request.content.decode())
            self.token_calls.append(form)
            if form.get('grant_type') == ['refresh_token'] and self.next_refresh_error:
                return httpx.Response(400, json={'error':self.next_refresh_error})
            token = {'access_token':'FAKE_ACCESS_TOKEN', 'token_type':'Bearer', 'expires_in':3600, 'scope':self.scope}
            if not self.omit_refresh and form.get('grant_type') == ['authorization_code']:
                token['refresh_token'] = 'FAKE_REFRESH_TOKEN'
            return httpx.Response(200, json=token)
        assert request.url.host == 'www.googleapis.com'
        assert request.headers['authorization'] == 'Bearer FAKE_ACCESS_TOKEN'
        if request.url.path.endswith('/calendarList'):
            return httpx.Response(200, json={'items':self.calendar_items})
        if self.fail:
            if self.fail == 'network':
                raise httpx.ConnectError('private details must not leak', request=request)
            return httpx.Response(self.fail, json={'error':{'message':'private server error'}})
        cid = unquote(request.url.path.split('/calendars/',1)[1].rsplit('/events',1)[0])
        items = self.events.get(cid, [])
        if self.pagination:
            if request.url.params.get('pageToken'):
                return httpx.Response(200, json={'items':items[1:], **({'nextPageToken':'repeated'} if self.repeat_page else {})})
            return httpx.Response(200, json={'items':items[:1], 'nextPageToken':'repeated'})
        return httpx.Response(200, json={'items':items})


@pytest.fixture
def setup(tmp_path):
    fake = FakeGoogle()
    settings = Settings(ORIGIN, ADMIN_HASH, Fernet.generate_key().decode(), tmp_path/'data', ROOT/'dist-preview',
                        client_id='example.apps.googleusercontent.com', client_secret='test-client-secret', scheduler=False,
                        warm_before=0, warm_after=0)
    app = create_app(settings, httpx.MockTransport(fake))
    with TestClient(app, base_url=ORIGIN) as client:
        yield app, client, fake, settings


def login(c):
    response = c.post('/api/admin/login', json={'password':PASSWORD}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response


def link(c):
    start = c.post('/api/admin/google/connect', json={}, headers=HEADERS)
    assert start.status_code == 200, start.text
    query = parse_qs(urlsplit(start.json()['url']).query)
    response = c.get('/api/oauth/callback', params={'state':query['state'][0], 'code':'fake-code'}, follow_redirects=False)
    return query, response


def configure(c, rota=True, **fields):
    record = c.get('/api/admin/config').json()
    cfg = DisplayConfig().model_dump()
    cfg['members'] = cfg['members'][:2]
    cfg['members'][0]['calendarId'] = 'calendar-a'
    cfg['members'][1]['calendarId'] = 'calendar-b'
    cfg['source'] = 'google'
    cfg['rotaMember'] = 'member-2' if rota else ''
    cfg.update(fields)
    response = c.put('/api/admin/config', json={'revision':record['revision'],'config':cfg}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def snapshot(c, first=MONTH, days=28):
    return c.get('/api/display/snapshot', params={'first':first.isoformat(), 'days':days})


def ready(app,c):
    response = snapshot(c)
    c.portal.call(app.state.sync.tick)
    response = snapshot(c)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('path', ['/api/admin/config','/api/admin/devices','/api/admin/calendars','/api/admin/status','/api/display/config','/api/display/snapshot?first=2026-10-01'])
def test_protected_gets(setup,path):
    assert setup[1].get(path).status_code == 401


@pytest.mark.parametrize('path', ['/.env','/.env.private','/backend/app.py','/private/client_secret.json','/data/paperweek.sqlite3','/../../etc/passwd','/google.mjs'])
def test_static_allowlist(setup,path):
    assert setup[1].get(path).status_code == 404


def test_login_cookie_and_csrf(setup):
    app,c,_,_=setup
    assert c.post('/api/admin/login',json={'password':PASSWORD}).status_code == 403
    assert c.post('/api/admin/login',json={'password':PASSWORD},headers={**HEADERS,'origin':'https://attacker.example'}).status_code == 403
    assert c.post('/api/admin/login',json={'password':'wrong'},headers=HEADERS).status_code == 401
    response=login(c)
    cookie=response.headers['set-cookie']
    assert all(x in cookie for x in ['HttpOnly','Secure','SameSite=lax'])
    assert c.get('/api/session').json()['role']=='admin'
    assert PASSWORD not in json.dumps(app.state.store.rows('SELECT * FROM sessions'))
    assert c.get('/api/admin/config').headers['cache-control']=='no-store'


def test_request_limits(setup):
    _,c,_,_=setup
    assert c.post('/api/admin/login',content='a'*70000,headers={**HEADERS,'content-type':'application/json'}).status_code==413
    assert c.post('/api/admin/login',content='password=a',headers={**HEADERS,'content-type':'application/x-www-form-urlencoded'}).status_code==415
    response=c.post('/api/admin/login',json={'password':PASSWORD,'secret':'not-to-echo'},headers=HEADERS)
    assert response.status_code==422 and 'not-to-echo' not in response.text


def test_pairing_one_use_read_only_and_revoke(setup):
    app,c,_,_=setup
    login(c)
    code=c.post('/api/admin/pairings',json={'label':'Hall display','days':365},headers=HEADERS).json()['code']
    admin_cookie=c.cookies.get(COOKIE)
    c.cookies.clear()
    assert c.post('/api/pair',json={'code':code},headers=HEADERS).status_code==200
    display_cookie=c.cookies.get(COOKIE)
    assert c.get('/api/session').json()['role']=='display'
    assert c.get('/api/display/config').status_code==200
    assert c.get('/api/admin/config').status_code==403
    assert c.post('/api/admin/sync',json={},headers=HEADERS).status_code==403
    assert c.post('/api/pair',json={'code':code},headers=HEADERS).status_code==400
    c.cookies.clear();c.cookies.set(COOKIE,admin_cookie)
    devices=c.get('/api/admin/devices').json()
    assert len(devices)==1
    assert display_cookie not in json.dumps(devices)
    assert c.request('DELETE','/api/admin/devices/'+devices[0]['id'],json={},headers=HEADERS).status_code==200
    c.cookies.clear();c.cookies.set(COOKIE,display_cookie)
    assert c.get('/api/display/config').status_code==401


def test_pairing_expiry_and_rate_limit(setup):
    app,c,_,_=setup
    login(c)
    code=c.post('/api/admin/pairings',json={},headers=HEADERS).json()['code']
    app.state.store.execute('UPDATE pairs SET expires=0')
    assert c.post('/api/pair',json={'code':code},headers=HEADERS).status_code==400
    for _ in range(9):
        assert c.post('/api/pair',json={'code':'ABCDEFGH'},headers=HEADERS).status_code==400
    assert c.post('/api/pair',json={'code':'ABCDEFGH'},headers=HEADERS).status_code==429


def test_config_optimistic_lock_and_public_projection(setup):
    app,c,_,_=setup;login(c);link(c)
    rec=configure(c)
    assert rec['revision']==2
    public=c.get('/api/display/config').json()
    assert 'calendar-a' not in json.dumps(public)
    assert public['config']['members'][0]['calendarId']=='member-1'
    assert c.put('/api/admin/config',json={'revision':1,'config':rec['config']},headers=HEADERS).status_code==409
    assert c.put('/api/admin/config',json={'revision':2,'config':{**rec['config'],'timezone':'Invented/Zone'}},headers=HEADERS).status_code==422


def test_offline_oauth_pkce_and_encryption(setup):
    app,c,fake,_=setup;login(c)
    q,response=link(c)
    assert response.status_code==303 and 'connected' in response.headers['location']
    assert q['access_type']==['offline'] and q['prompt']==['consent'] and q['code_challenge_method']==['S256']
    assert 'test-client-secret' not in json.dumps(q)
    assert fake.token_calls[0]['redirect_uri']==[ORIGIN+'/api/oauth/callback']
    import base64,hashlib
    challenge=base64.urlsafe_b64encode(hashlib.sha256(fake.token_calls[0]['code_verifier'][0].encode()).digest()).rstrip(b'=').decode()
    assert challenge==q['code_challenge'][0]
    assert 'FAKE_REFRESH_TOKEN' not in app.state.store.path.read_bytes().decode(errors='ignore')
    assert 'FAKE_REFRESH_TOKEN' not in json.dumps(app.state.store.get('google_token'))
    assert app.state.store.get_secret('google_token')['refresh_token']=='FAKE_REFRESH_TOKEN'
    assert c.get('/api/oauth/callback',params={'state':q['state'][0],'code':'replay'},follow_redirects=False).headers['location'].endswith('attention')


def test_oauth_state_session_binding(setup):
    app,c,fake,_=setup;login(c)
    start=c.post('/api/admin/google/connect',json={},headers=HEADERS).json()
    state=parse_qs(urlsplit(start['url']).query)['state'][0]
    login(c)  # a different admin session
    result=c.get('/api/oauth/callback',params={'state':state,'code':'fake'},follow_redirects=False)
    assert result.headers['location'].endswith('attention') and not fake.token_calls


@pytest.mark.parametrize('case',['no-refresh','missing-scope','expired-state','denied','duplicate-state'])
def test_failed_oauth_does_not_save_token(setup,case):
    app,c,fake,_=setup;login(c)
    start=c.post('/api/admin/google/connect',json={},headers=HEADERS).json()
    state=parse_qs(urlsplit(start['url']).query)['state'][0]
    params={'state':state,'code':'fake'}
    if case=='no-refresh':fake.omit_refresh=True
    if case=='missing-scope':fake.scope=SCOPES[0]
    if case=='expired-state':app.state.store.execute('UPDATE oauth_states SET expires=0')
    if case=='denied':params={'state':state,'error':'access_denied'}
    if case=='duplicate-state':params=[('state',state),('state',state),('code','fake')]
    result=c.get('/api/oauth/callback',params=params,follow_redirects=False)
    assert result.headers['location'].endswith('attention')
    assert not app.state.store.get('google_token')


def test_refresh_token_automatic_and_preserved(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c)
    token=app.state.store.get_secret('google_token');token['expires_at']=0;app.state.store.set_secret('google_token',token)
    data=ready(app,c)
    assert data['ready'] and data['batches'][0]['items'][0]['summary']=='Appointment'
    assert any(t.get('grant_type')==['refresh_token'] for t in fake.token_calls)
    assert app.state.store.get_secret('google_token')['refresh_token']=='FAKE_REFRESH_TOKEN'


def test_invalid_grant_preserves_calendar_cache(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c);good=ready(app,c)
    token=app.state.store.get_secret('google_token');token['expires_at']=0;app.state.store.set_secret('google_token',token)
    fake.next_refresh_error='invalid_grant';app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    data=snapshot(c).json()
    assert data['ready'] and data['stale'] and data['connection']=='reconnect_required'
    assert data['batches']==good['batches']


@pytest.mark.parametrize('failure',[429,500,503,403,404,'network'])
def test_failed_sync_retains_previous_complete_data(setup,failure):
    app,c,fake,_=setup;login(c);link(c);configure(c);good=ready(app,c)
    fake.events['calendar-a']=[event('Not yet fetched')];fake.fail=failure
    app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    data=snapshot(c).json()
    assert data['ready'] and data['stale'] and data['batches']==good['batches']
    status=c.get('/api/admin/status').json()
    assert any(w['error'] for w in status['windows'])
    assert 'private server error' not in json.dumps(status)


def test_cache_fill_is_not_partial_and_deletions_replace(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c)
    pending=snapshot(c)
    assert pending.status_code==202 and pending.json()['batches']==[]
    good=ready(app,c)
    assert len(good['batches'][0]['items'])==1
    fake.events['calendar-a']=[]
    app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    assert snapshot(c).json()['batches'][0]['items']==[]


def test_pagination_and_failed_pages_do_not_replace(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c)
    fake.events['calendar-a']=[event('One'),event('Two',id='event-b')];fake.pagination=True
    good=ready(app,c)
    assert len(good['batches'][0]['items'])==2
    fake.repeat_page=True;fake.events['calendar-a']=[event('Unsafe new data')]
    app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    assert snapshot(c).json()['batches']==good['batches']


def test_privacy_masking_happens_before_browser(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c)
    fake.events['calendar-a']=[event('Secret appointment title', visibility='private')]
    fake.events['calendar-b']=[event('[PW:ONCALL] Sensitive shift department',id='shift',visibility='private')]
    data=ready(app,c);serialized=json.dumps(data)
    assert 'Secret appointment title' not in serialized and 'Sensitive shift department' not in serialized
    assert 'calendar-a' not in serialized and '-uid' not in serialized
    assert data['batches'][0]['items'][0]['summary']=='Busy'
    assert data['batches'][1]['items'][0]['summary']=='[PW:ONCALL]'


def test_member_wide_mask_and_declined_cancelled(setup):
    app,c,fake,_=setup;login(c);link(c);record=configure(c)
    cfg=record['config'];cfg['members'][0]['maskTitles']=True
    assert c.put('/api/admin/config',json={'revision':record['revision'],'config':cfg},headers=HEADERS).status_code==200
    fake.events['calendar-a']=[event('Hide this'),event('Cancelled',id='gone',status='cancelled'),event('Declined',id='declined',attendees=[{'self':True,'responseStatus':'declined'}])]
    data=ready(app,c)
    assert [r['summary'] for r in data['batches'][0]['items']]==['Busy']


def test_bad_data_does_not_replace_good_cache(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c);good=ready(app,c)
    fake.events['calendar-a']=[{'summary':'broken','start':{'date':'invalid'},'end':{'date':'invalid'}}]
    app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    data=snapshot(c).json()
    assert data['stale'] and data['batches']==good['batches']


def test_settings_remove_unselected_cached_calendars(setup):
    app,c,_,_=setup;login(c);link(c);rec=configure(c);ready(app,c)
    cfg=rec['config'];cfg['members']=cfg['members'][:1];cfg['rotaMember']=''
    assert c.put('/api/admin/config',json={'revision':rec['revision'],'config':cfg},headers=HEADERS).status_code==200
    assert not app.state.store.rows('SELECT * FROM windows WHERE calendar=?',('calendar-b',))
    assert len(snapshot(c).json()['batches'])==1


def test_disconnect_purges_tokens_cache_and_epoch(setup):
    app,c,_,_=setup;login(c);link(c);configure(c);ready(app,c)
    before=c.get('/api/display/config').json()['dataEpoch']
    assert c.post('/api/admin/google/disconnect',json={},headers=HEADERS).status_code==200
    assert not app.state.store.get('google_token') and not app.state.store.rows('SELECT * FROM windows')
    assert c.get('/api/display/config').json()['dataEpoch']>before


def test_database_restart_restores_sessions_and_data(setup):
    app,c,fake,s=settings_tuple=setup;login(c);link(c);configure(c);before=ready(app,c)
    token=c.cookies.get(COOKIE)
    # Separate process-style Store/API instance reads the same persistent SQLite file.
    app2=create_app(s,httpx.MockTransport(fake))
    with TestClient(app2,base_url=ORIGIN) as second:
        second.cookies.set(COOKIE,token)
        data=snapshot(second).json()
        assert data['ready'] and data['batches']==before['batches']
        assert second.get('/api/admin/status').json()['connection']=='connected'


def test_wrong_encryption_key_refuses_start(setup):
    _,_,_,s=setup
    with pytest.raises(ValueError,match='encryption key'):
        Store(s.data_dir,Fernet.generate_key().decode())


def test_change_admin_password_revokes_old_admin_not_displays(setup):
    app,c,fake,s=setup;login(c);old=c.cookies.get(COOKIE)
    app2=create_app(replace(s,admin_hash=password_hash('another administrator password')),httpx.MockTransport(fake))
    with TestClient(app2,base_url=ORIGIN) as second:
        second.cookies.set(COOKIE,old)
        assert second.get('/api/admin/config').status_code==401


@pytest.mark.parametrize('first,days',[(MONTH,0),(MONTH,63),(add_month(MONTH,-25),28),(add_month(MONTH,26),28)])
def test_range_bounds(setup,first,days):
    _,c,_,_=setup;login(c)
    assert snapshot(c,first,days).status_code==422


@pytest.mark.parametrize('url',['http://192.0.2.1','https://calendar.example/path','https://calendar.example/','https://user:pass@example.net','not a URL'])
def test_origin_validation(tmp_path,url):
    with pytest.raises(ValueError):Settings(url,ADMIN_HASH,Fernet.generate_key().decode(),tmp_path,ROOT/'dist-preview')


@pytest.mark.parametrize('zone,month,expected',[
    ('Europe/London','2026-03-01',31*24-1),('Europe/London','2026-10-01',31*24+1),
    ('UTC','2028-02-01',29*24),('Australia/Sydney','2026-10-01',31*24-1)])
def test_timezone_month_bounds(zone,month,expected):
    a,b=list(bounds(month,zone))
    assert (datetime.fromisoformat(b)-datetime.fromisoformat(a)).total_seconds()==expected*3600


def test_overnight_event_and_exclusive_all_day():
    r={'id':'x','summary':'Night','start':{'dateTime':'2026-10-03T20:00:00+01:00'},'end':{'dateTime':'2026-10-04T08:00:00+01:00'}}
    raw=validate_raw(r)
    assert intersects(raw,date(2026,10,3),1,'Europe/London')
    assert intersects(raw,date(2026,10,4),1,'Europe/London')
    assert not intersects(raw,date(2026,10,5),1,'Europe/London')
    raw=validate_raw(event(day=date(2026,10,3)))
    assert not intersects(raw,date(2026,10,4),1,'UTC')


def test_off_requires_all_day_and_ambiguous_time_rejected():
    raw={'summary':'[PW:OFF]','start':{'dateTime':'2026-10-01T12:00:00+01:00'},'end':{'dateTime':'2026-10-01T13:00:00+01:00'}}
    with pytest.raises(ValueError):validate_raw(raw,rota=True)
    raw['start']['dateTime']='2026-10-01T12:00:00'
    with pytest.raises(ValueError):validate_raw(raw)


def test_password_hash():
    assert password_ok(PASSWORD,ADMIN_HASH)
    assert not password_ok('wrong',ADMIN_HASH)
    assert not password_ok('a'*600,ADMIN_HASH)


def test_health_and_security_headers(setup):
    _,c,_,_=setup
    assert c.get('/healthz').json()['status']=='running'
    r=c.get('/')
    assert r.status_code==200 and 'backend-app.mjs' in r.text
    assert 'no-store' in r.headers['cache-control']
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert c.get('/paperweek-preview.wasm').headers['content-type']=='application/wasm'
    assert c.get('/',headers={'host':'attacker.example'}).status_code==400
    assert '/api/' in c.get('/server-sw.js').text
