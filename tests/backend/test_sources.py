"""Source integration tests: fake provider HTTP, real parser/cache/API."""
import base64
from datetime import date, timedelta
import json
from urllib.parse import urlsplit
import pytest
from backend.google import CalendarError
from backend.sources import SourceInput, PREFIX
from backend.ical_parser import parse_calendar
from backend.storage import Store
from backend.sync import month_start
from test_service import setup, login, link, configure, ready, snapshot, HEADERS, MONTH, event

URL='https://feeds.example.net/rota.ics?key=synthetic-subscription'


def feed(day=MONTH.replace(day=10), title='Duty', uid='feed-event', extra=''):
    return ('BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:'+uid+'\nDTSTART;VALUE=DATE:'+day.strftime('%Y%m%d')+'\nSUMMARY:'+title+'\n'+extra+'\nEND:VEVENT\nEND:VCALENDAR').encode()


class FeedRunner:
    def __init__(self):
        self.data=feed();self.calls=[];self.failure=None;self.not_modified=False
    async def __call__(self,job):
        self.calls.append(job)
        if job.get('action')=='fetch':
            if self.failure:raise CalendarError('ical',self.failure)
            if self.not_modified:return {'notModified':True}
            assert urlsplit(job['url']).hostname=='feeds.example.net'
            return {'notModified':False,'data':base64.b64encode(self.data).decode(),'etag':'"fixture-etag"','modified':''}
        return parse_calendar(base64.b64decode(job['data']),job['start'],job['stop'],job['fallback'],job['zone'])


def source_payload(**changes):
    return dict(label='Work feed',member='member-2',kind='ical',url=URL,enabled=True,mode='rota',timezone='Europe/London',
                pollMinutes=30,defaultRota='unknown',rules=[dict(field='title',match='equals',text='Duty',action='work')],**changes)


def add(c,payload=None):
    r=c.post('/api/admin/sources',json=payload or source_payload(),headers=HEADERS)
    assert r.status_code==200,r.text
    return r.json()['source']


def attach(app):
    runner=FeedRunner();app.state.ical.runner=runner
    return runner


def no_google_config(c):
    record=c.get('/api/admin/config').json();cfg=record['config'];cfg['source']='google'
    for m in cfg['members']:m['calendarId']=''
    r=c.put('/api/admin/config',json={'revision':record['revision'],'config':cfg},headers=HEADERS)
    assert r.status_code==200,r.text


def test_ical_only_no_google_auth_required(setup):
    app,c,_,_=setup;login(c);runner=attach(app);s=add(c);no_google_config(c)
    r=ready(app,c)
    assert r['connection']=='connected' and r['googleConnection']=='disconnected'
    assert r['batches'][1]['items'][0]['summary']=='[PW:WORK]'
    assert not r['stale']
    assert r['unmappedMembers']==['member-1','member-3','member-4']
    assert sum(j.get('action')=='fetch' for j in runner.calls)==1


def test_google_and_feed_merge_one_person_no_extra_column(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c);attach(app);add(c)
    fake.events['calendar-b']=[event(title='Personal appointment', id='personal-b')]
    result=ready(app,c)
    assert len(result['config']['members'])==2
    assert result['batches'][0]['items'][0]['summary']=='Appointment'
    assert {i['summary'] for i in result['batches'][1]['items']}=={'Personal appointment','[PW:WORK]'}
    assert {w['kind'] for w in result['coverage']}=={'google','ical'}


def test_multiple_feeds_on_same_member(setup):
    app,c,_,_=setup;login(c);attach(app)
    a=add(c)
    p=source_payload();p.update(label='Another feed',mode='events',url=URL+'&other=1')
    b=add(c,p);no_google_config(c)
    # Same UID + interval from the two feeds is deduplicated; rota marker wins.
    r=ready(app,c);assert len(r['batches'][1]['items'])==1
    assert r['batches'][1]['items'][0]['summary']=='[PW:WORK]'
    assert a['id']!=b['id']


def test_urls_write_only_encrypted_not_exported_or_sent_to_displays(setup):
    app,c,_,settings=setup;login(c);attach(app);s=add(c);no_google_config(c);r=ready(app,c)
    text=json.dumps([r,c.get('/api/admin/config').json(),c.get('/api/admin/status').json(),c.get('/api/admin/sources').json()])
    assert URL not in text and 'synthetic-subscription' not in text and 'feeds.example.net' not in text
    assert s['hasUrl'] and 'url' not in s
    stored=json.dumps(app.state.store.rows('SELECT * FROM kv')+app.state.store.rows('SELECT * FROM sources'))
    assert 'synthetic-subscription' not in stored and 'BEGIN:VCALENDAR' not in stored
    assert app.state.store.get_secret('source-secret:'+s['id'])['url']==URL
    assert not (settings.data_dir/'subscription.ics').exists()


def test_source_edit_blank_keeps_url_revision_conflict_and_reprojection(setup):
    app,c,_,_=setup;login(c);attach(app);s=add(c);no_google_config(c);ready(app,c)
    p=source_payload();p['url']='';p['rules'][0]['action']='oncall'
    r=c.put('/api/admin/sources/'+s['id'],json={'revision':s['revision'],'source':p},headers=HEADERS)
    assert r.status_code==200,r.text
    assert c.put('/api/admin/sources/'+s['id'],json={'revision':s['revision'],'source':p},headers=HEADERS).status_code==409
    assert app.state.store.get_secret('source-secret:'+s['id'])['url']==URL
    assert ready(app,c)['batches'][1]['items'][0]['summary']=='[PW:ONCALL]'


def test_preview_disabled_real_parse_rules_and_http_date(setup):
    app,c,_,_=setup;login(c);attach(app);p=source_payload();p['enabled']=False;s=add(c,p)
    r=c.post('/api/admin/sources/'+s['id']+'/preview',json={'first':MONTH.isoformat(),'days':28},headers=HEADERS)
    assert r.status_code==200,r.text
    assert r.json()['items'][0]['title']=='Duty' and r.json()['counts']=={'work':1}
    assert app.state.store.rows('SELECT * FROM windows')==[]


def test_disabled_preview_and_unknown_rules_no_shift_guess(setup):
    app,c,_,_=setup;login(c);runner=attach(app);runner.data=feed(title='Unrecognised duty code')
    p=source_payload();s=add(c,p);no_google_config(c)
    r=ready(app,c)
    assert r['warnings'] and r['batches'][1]['items']==[]
    status=c.get('/api/admin/status').json()
    assert any(w['warnings'] for w in status['windows'])
    # Empty dates are not manufactured into OFF entries.
    assert 'PW:OFF' not in str(r)


def test_category_rule_and_no_title_leak(setup):
    app,c,_,_=setup;login(c);runner=attach(app);runner.data=feed(title='Private shift name',extra='CLASS:PRIVATE\nCATEGORIES:Standby')
    p=source_payload();p['rules']=[dict(field='category',match='equals',text='Standby',action='oncall')]
    add(c,p);no_google_config(c);r=ready(app,c)
    assert r['batches'][1]['items'][0]['summary']=='[PW:ONCALL]' and 'Private shift name' not in str(r)


def test_source_failure_retains_last_data_and_does_not_block_google(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c);runner=attach(app);add(c);old=ready(app,c)
    fake.events['calendar-a'][0]['summary']='Updated appointment'
    runner.failure='Feed temporarily unavailable.';app.state.sync.request_sync()
    c.portal.call(app.state.sync.tick);new=snapshot(c).json()
    assert new['stale'] and new['batches'][1]==old['batches'][1]
    assert new['batches'][0]['items'][0]['summary']=='Updated appointment'


def test_google_failure_does_not_block_feed(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c);runner=attach(app);add(c);ready(app,c)
    fake.fail=503;runner.data=feed(title='[PW:ONCALL]')
    app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    assert snapshot(c).json()['batches'][1]['items'][0]['summary']=='[PW:ONCALL]'


def test_google_disconnect_does_not_delete_ical_cache(setup):
    app,c,_,_=setup;login(c);link(c);configure(c);attach(app);s=add(c);ready(app,c)
    assert c.post('/api/admin/google/disconnect',json={},headers=HEADERS).status_code==200
    rows=app.state.store.rows('SELECT * FROM windows')
    assert rows and all(r['calendar']==PREFIX+s['id'] for r in rows)
    no_google_config(c);r=ready(app,c)
    assert r['connection']=='connected' and not r['stale']


def test_full_feed_replacement_removes_deleted_events(setup):
    app,c,_,_=setup;login(c);runner=attach(app);add(c);no_google_config(c);assert ready(app,c)['batches'][1]['items']
    runner.data=b'BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR'
    app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    assert snapshot(c).json()['batches'][1]['items']==[]


def test_conditional_get_and_304_reuses_validated_feed(setup):
    app,c,_,_=setup;login(c);runner=attach(app);add(c);no_google_config(c);old=ready(app,c)
    runner.not_modified=True;app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    assert snapshot(c).json()['batches']==old['batches']
    assert [j for j in runner.calls if j.get('action')=='fetch'][-1]['etag']=='"fixture-etag"'


def test_bad_new_feed_does_not_replace_good_body(setup):
    app,c,_,_=setup;login(c);runner=attach(app);s=add(c);no_google_config(c);old=ready(app,c)
    saved=app.state.store.get_secret('source-cache:'+s['id'])['data']
    runner.data=b'<html>Login</html>';app.state.sync.request_sync();c.portal.call(app.state.sync.tick)
    assert app.state.store.get_secret('source-cache:'+s['id'])['data']==saved
    assert snapshot(c).json()['batches']==old['batches']


def test_inflight_source_change_cannot_commit_stale_results(setup):
    app,c,_,_=setup;login(c);runner=attach(app);s=add(c);no_google_config(c)
    original=runner.__call__
    async def changed(job):
        result=await original(job)
        if job.get('action')=='parse':app.state.store.delete_source(s['id'],s['revision'])
        return result
    app.state.ical.runner=changed
    snapshot(c);c.portal.call(app.state.sync.tick)
    assert not app.state.store.rows('SELECT * FROM windows WHERE calendar=?',(PREFIX+s['id'],))
    assert app.state.store.get_secret('source-cache:'+s['id']) is None


def test_add_extra_google_source(setup):
    app,c,fake,_=setup;login(c);link(c);attach(app)
    p=source_payload();p.update(kind='google',calendarId='calendar-a',url='',mode='events')
    add(c,p);no_google_config(c);r=ready(app,c)
    assert r['batches'][1]['items'][0]['summary']=='Appointment'


def test_source_delete_removes_url_body_and_windows(setup):
    app,c,_,_=setup;login(c);attach(app);s=add(c);no_google_config(c);ready(app,c)
    r=c.request('DELETE','/api/admin/sources/'+s['id'],json={'revision':s['revision']},headers=HEADERS)
    assert r.status_code==200
    assert app.state.store.source(s['id']) is None
    assert app.state.store.get_secret('source-secret:'+s['id']) is None
    assert app.state.store.get_secret('source-cache:'+s['id']) is None


def test_new_source_requires_url_and_known_member(setup):
    _,c,_,_=setup;login(c)
    p=source_payload();p['url']=''
    assert c.post('/api/admin/sources',json=p,headers=HEADERS).status_code==422
    p=source_payload();p['member']='missing'
    assert c.post('/api/admin/sources',json=p,headers=HEADERS).status_code==422
    p=source_payload();p['member']='member-1'
    assert c.post('/api/admin/sources',json=p,headers=HEADERS).status_code==422


def test_sources_admin_only_and_csrf(setup):
    _,c,_,_=setup
    assert c.get('/api/admin/sources').status_code==401
    login(c)
    assert c.post('/api/admin/sources',json=source_payload()).status_code==403
    code=c.post('/api/admin/pairings',json={},headers=HEADERS).json()['code']
    c.cookies.clear();c.post('/api/pair',json={'code':code},headers=HEADERS)
    assert c.get('/api/admin/sources').status_code==403
    assert c.post('/api/admin/sources',json=source_payload(),headers=HEADERS).status_code==403


def test_primary_mapping_can_be_absent_and_rota_disabled_never_leaks_shift_title(setup):
    app,c,_,_=setup;login(c);attach(app);add(c);no_google_config(c);ready(app,c)
    record=c.get('/api/admin/config').json();record['config']['rotaMember']=''
    assert c.put('/api/admin/config',json=record,headers=HEADERS).status_code==200
    r=ready(app,c)
    assert all(not batch['items'] for batch in r['batches'])


def test_migration_preserves_old_cache_pairings_and_config(setup):
    app,c,_,settings=setup;login(c);link(c);configure(c);ready(app,c)
    app.state.store.set('schema_version',1)
    other=Store(settings.data_dir,settings.token_key)
    try:
        assert other.get('schema_version')==2
        assert other.config().source=='google'
        assert other.rows('SELECT * FROM sessions') and other.rows('SELECT * FROM windows')
        assert other.get_secret('google_token')
    finally:other.close()


def test_adjacent_month_reuses_feed_without_claiming_new_provider_check(setup):
    from backend.sync import add_month
    app,c,_,_=setup;login(c);runner=attach(app);s=add(c);no_google_config(c);ready(app,c)
    checked=app.state.store.get_secret('source-cache:'+s['id'])['checked']
    app.state.ical.clock=lambda:checked+100
    other=add_month(MONTH,1)
    c.get('/api/display/snapshot',params={'first':other.isoformat(),'days':10})
    c.portal.call(app.state.sync.tick)
    rows=app.state.store.rows('SELECT * FROM windows WHERE calendar=?',(PREFIX+s['id'],))
    assert len(rows)>=2 and all(r['success']==checked for r in rows)
    assert all(r['next_at']==checked+30*60 for r in rows)
    assert sum(j['action']=='fetch' for j in runner.calls)==1


def test_new_complete_feed_replaces_all_retained_months_atomically(setup):
    from backend.sync import add_month
    app,c,_,_=setup;login(c);runner=attach(app);s=add(c);no_google_config(c);ready(app,c)
    other=add_month(MONTH,1)
    c.get('/api/display/snapshot',params={'first':other.isoformat(),'days':10});c.portal.call(app.state.sync.tick)
    sid=PREFIX+s['id']
    app.state.store.execute('UPDATE windows SET next_at=9999999999 WHERE calendar=?',(sid,))
    app.state.store.execute('UPDATE windows SET next_at=0 WHERE calendar=? AND month=?',(sid,other.isoformat()))
    cache=app.state.store.get_secret('source-cache:'+s['id']);cache['checked']=0;app.state.store.set_secret('source-cache:'+s['id'],cache)
    runner.data=b'BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR'
    c.portal.call(app.state.sync.tick)
    assert all(json.loads(r['data'])==[] for r in app.state.store.rows('SELECT * FROM windows WHERE calendar=?',(sid,)))


def test_six_people_and_additional_source_not_seventh_person(setup):
    app,c,_,_=setup;login(c);attach(app)
    record=c.get('/api/admin/config').json();cfg=record['config'];cfg['source']='google'
    for n in (5,6):
        cfg['members'].append(dict(key=f'member-{n}',label=f'Person {n}',badge=str(n),colour='black',calendarId='',maskTitles=False))
    assert c.put('/api/admin/config',json=record,headers=HEADERS).status_code==200
    add(c)
    out=ready(app,c)
    assert len(out['config']['members'])==6 and len(out['batches'])==6
    assert out['batches'][1]['items'][0]['summary']=='[PW:WORK]'
    record=c.get('/api/admin/config').json()
    record['config']['members'].append(dict(key='member-7',label='Person 7',badge='7',colour='black',calendarId='',maskTitles=False))
    assert c.put('/api/admin/config',json=record,headers=HEADERS).status_code==422


def test_member_remove_also_removes_sources_without_google_write(setup):
    app,c,fake,_=setup;login(c);link(c);configure(c);attach(app);s=add(c);ready(app,c)
    record=c.get('/api/admin/config').json()
    record['config']['members']=record['config']['members'][:1];record['config']['rotaMember']=''
    assert c.put('/api/admin/config',json=record,headers=HEADERS).status_code==200
    assert c.get('/api/admin/sources').json()['sources']==[]
    assert app.state.store.get_secret('source-secret:'+s['id']) is None
    assert all(r.method=='GET' or r.url.host=='oauth2.googleapis.com' for r in fake.calls)
