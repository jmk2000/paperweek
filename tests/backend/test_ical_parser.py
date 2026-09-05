"""Synthetic calendar fixtures only; no household information or real URLs."""
import asyncio
import base64
from datetime import datetime
import pytest
from backend.ical_parser import parse_calendar, ICalError
from backend.ical import isolated
from backend.sources import classify, normalise_url

START='2026-10-01T00:00:00+01:00'
STOP='2026-11-01T00:00:00+00:00'


def calendar(*events, head=''):
    return ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n'+head+'\r\n'+'\r\n'.join(events)+'\r\nEND:VCALENDAR\r\n').encode()


def event(body, uid='fixture'):
    return 'BEGIN:VEVENT\nUID:'+uid+'\n'+body+'\nEND:VEVENT'


def parse(data, start=START, stop=STOP, fallback='Europe/London'):
    return parse_calendar(data,start,stop,fallback,'Europe/London')


def test_all_day_exclusive_end_and_missing_end():
    items=parse(calendar(event('DTSTART;VALUE=DATE:20261002\nDTEND;VALUE=DATE:20261005\nSUMMARY:Break'),event('DTSTART;VALUE=DATE:20261006',uid='two')))['items']
    assert items[0]['end']=={'date':'2026-10-05'}
    assert items[1]['end']=={'date':'2026-10-07'}


def test_unicode_folded_text_escaped_categories_and_private():
    data=calendar(event('DTSTART:20261002T100000Z\nDTEND:20261002T110000Z\nSUMMARY:Club\\, music\n  and caf\u00e9\nCATEGORIES:Duty\\, call,Training\nCLASS:CONFIDENTIAL'))
    r=parse(data)['items'][0]
    assert r['summary']=='Club, music and caf\u00e9'
    assert r['categories']==['Duty, call','Training'] and r['visibility']=='private'


def test_folding_inside_utf8_character():
    data=calendar(event('DTSTART;VALUE=DATE:20261002\nSUMMARY:caf\u00e9')).replace(b'\xc3\xa9',b'\xc3\r\n \xa9')
    assert parse(data)['items'][0]['summary']=='caf\u00e9'


def test_floating_and_calendar_timezone_override():
    raw=event('DTSTART:20261002T100000\nDTEND:20261002T110000')
    assert parse(calendar(raw))['items'][0]['start']['dateTime'].endswith('+01:00')
    assert parse(calendar(raw,head='X-WR-TIMEZONE:America/New_York'))['items'][0]['start']['dateTime'].endswith('-04:00')


def test_timezone_quoted_and_utc_and_zero_duration():
    data=calendar(event('DTSTART;TZID="Europe/London":20261002T100000\nDTEND:20261002T100000Z'))
    r=parse(data)['items'][0]
    assert datetime.fromisoformat(r['end']['dateTime'])>datetime.fromisoformat(r['start']['dateTime'])
    r=parse(calendar(event('DTSTART:20261002T100000Z')))['items'][0]
    assert r['start']==r['end']


def test_embedded_vtimezone():
    head='''BEGIN:VTIMEZONE
TZID:Fixture Zone
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:+0200
TZOFFSETTO:+0200
TZNAME:FIXTURE
END:STANDARD
END:VTIMEZONE'''
    r=parse(calendar(event('DTSTART;TZID="Fixture Zone":20261002T100000'),head=head))['items'][0]
    assert r['start']['dateTime'].endswith('+02:00')


def test_recurrence_dst_exdate_rdate():
    data=calendar(event('''DTSTART;TZID=Europe/London:20261005T090000
DTEND;TZID=Europe/London:20261005T170000
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=Europe/London:20261012T090000
RDATE;TZID=Europe/London:20261013T090000'''))
    r=parse(data)['items']
    assert [x['start']['dateTime'][:10] for x in r]==['2026-10-05','2026-10-13','2026-10-19','2026-10-26']
    assert r[-1]['start']['dateTime'].endswith('+00:00')
    assert len({x['id'] for x in r})==4


def test_all_day_recurrence_until():
    r=parse(calendar(event('DTSTART;VALUE=DATE:20261005\nRRULE:FREQ=WEEKLY;UNTIL=20261026')))['items']
    assert len(r)==4 and r[-1]['start']['date']=='2026-10-26'


def test_monthly_byday_and_yearly():
    r=parse(calendar(event('DTSTART;VALUE=DATE:20200101\nRRULE:FREQ=MONTHLY;BYDAY=2MO'),event('DTSTART;VALUE=DATE:20001010\nRRULE:FREQ=YEARLY',uid='yearly')))['items']
    assert {x['start']['date'] for x in r}=={'2026-10-12','2026-10-10'}


def test_moved_and_cancelled_occurrences():
    master=event('DTSTART:20261005T090000Z\nDTEND:20261005T100000Z\nRRULE:FREQ=WEEKLY;COUNT=4\nSUMMARY:Original')
    moved=event('RECURRENCE-ID:20261012T090000Z\nDTSTART:20261013T110000Z\nDTEND:20261013T123000Z\nSUMMARY:Moved')
    cancelled=event('RECURRENCE-ID:20261019T090000Z\nSTATUS:CANCELLED')
    r=parse(calendar(master,moved,cancelled))['items']
    assert len(r)==3
    assert [x['start']['dateTime'][:10] for x in r]==['2026-10-05','2026-10-13','2026-10-26']
    assert r[1]['summary']=='Moved'


def test_override_moved_into_query_from_outside():
    master=event('DTSTART:20260901T090000Z\nDTEND:20260901T100000Z\nRRULE:FREQ=DAILY;COUNT=2')
    moved=event('RECURRENCE-ID:20260902T090000Z\nDTSTART:20261012T110000Z\nSUMMARY:Moved')
    r=parse(calendar(master,moved))['items']
    assert len(r)==1 and r[0]['end']['dateTime'].startswith('2026-10-12T12:00')


def test_cancel_whole_series_and_latest_sequence():
    a=event('DTSTART;VALUE=DATE:20261001\nSEQUENCE:1\nSUMMARY:Old')
    b=event('DTSTART;VALUE=DATE:20261002\nSEQUENCE:2\nSUMMARY:New')
    assert parse(calendar(a,b))['items'][0]['summary']=='New'
    assert parse(calendar(b,event('SEQUENCE:3\nSTATUS:CANCELLED')))['items']==[]


def test_overnight_month_overlap_and_nominal_duration():
    a=event('DTSTART;TZID=Europe/London:20260930T220000\nDTEND;TZID=Europe/London:20261001T080000')
    b=event('DTSTART;TZID=Europe/London:20261024T090000\nDURATION:P1D',uid='nominal')
    r=parse(calendar(a,b))['items']
    assert len(r)==2 and r[-1]['end']['dateTime']=='2026-10-25T09:00:00+00:00'


def test_repeated_dtend_preserves_exact_duration():
    r=parse(calendar(event('DTSTART;TZID=Europe/London:20261018T090000\nDTEND;TZID=Europe/London:20261018T170000\nRRULE:FREQ=WEEKLY;COUNT=2')))['items']
    assert r[1]['end']['dateTime']=='2026-10-25T17:00:00+00:00'


def test_spring_gap_generated_occurrence_does_not_count():
    r=parse(calendar(event('DTSTART;TZID=Europe/London:20260328T013000\nRRULE:FREQ=DAILY;COUNT=3')),
            start='2026-03-28T00:00:00+00:00',stop='2026-04-02T00:00:00+01:00')['items']
    assert [x['start']['dateTime'][:10] for x in r]==['2026-03-28','2026-03-30','2026-03-31']


def test_alarms_and_attachments_never_fetched():
    r=parse(calendar(event('DTSTART;VALUE=DATE:20261002\nATTACH:https://invalid.example/file\nBEGIN:VALARM\nACTION:DISPLAY\nTRIGGER:-PT5M\nEND:VALARM')))
    assert len(r['items'])==1
    assert 'invalid.example' not in str(r)


@pytest.mark.parametrize('body',[
 'DTSTART;TZID=Missing/Zone:20261002T100000',
 'DTSTART;VALUE=DATE:20261002\nDTEND;VALUE=DATE:20261001',
 'DTSTART;VALUE=DATE:20261002\nDURATION:PT1H',
 'DTSTART:20261002T100000Z\nRRULE:FREQ=SECONDLY',
 'DTSTART:20261002T100000Z\nRRULE:FREQ=DAILY;COUNT=2;UNTIL=20261020T100000Z',
 'DTSTART:20261002T100000Z\nRECURRENCE-ID;RANGE=THISANDFUTURE:20261002T100000Z',
 'DTSTART:20261002T100000Z\nRDATE;VALUE=PERIOD:20261003T100000Z/20261003T120000Z',
 'DTSTART:20261002T100000Z\nEXRULE:FREQ=WEEKLY',
 'DTSTART:20261002T100000Z\nRRULE:FREQ=DAILY;INTERVAL=0',
 'DTSTART:20261002T100000Z\nRRULE:FREQ=DAILY\nRRULE:FREQ=WEEKLY',
 'DTSTART;TZID=Europe/London:20260329T013000',
 'DTSTART;VALUE=DATE:20261002\nDURATION:P999999999999D',
])
def test_reject_unsupported_or_invalid_atomically(body):
    with pytest.raises(ICalError):parse(calendar(event(body)))


@pytest.mark.parametrize('data',[
 b'<html>Sign in</html>',b'BEGIN:VCALENDAR\nVERSION:2.0\n',
 calendar(event('DTSTART;VALUE=DATE:20261002'),head='METHOD:REQUEST'),
 calendar(event('DTSTART;VALUE=DATE:20261002')).replace(b'UID:fixture\n',b''),
 b'x'*(2*1024*1024+1),
])
def test_bad_whole_feed(data):
    with pytest.raises(ICalError):parse(data)


def test_ignored_tasks_and_empty_calendar_warning():
    r=parse(calendar('BEGIN:VTODO\nSUMMARY:Task\nEND:VTODO'))
    assert not r['items'] and len(r['warnings'])==2


def test_parser_subprocess_real():
    data=calendar(event('DTSTART;VALUE=DATE:20261002'))
    r=asyncio.run(isolated({'data':base64.b64encode(data).decode(),'start':START,'stop':STOP,'fallback':'Europe/London','zone':'Europe/London'}))
    assert len(r['items'])==1


def test_expansion_limit():
    # 31*24*60 > 6000 entries, despite a DAILY base frequency.
    body='DTSTART:20261001T000000Z\nRRULE:FREQ=DAILY;BYHOUR='+','.join(map(str,range(24)))+';BYMINUTE='+','.join(map(str,range(60)))
    with pytest.raises(ICalError):parse(calendar(event(body)))


def test_rota_rules_precedence_and_oncall():
    src={'mode':'rota','defaultRota':'unknown','rules':[
        {'field':'title','match':'equals','text':'Not on call','action':'ignore'},
        {'field':'title','match':'contains','text':'on call','action':'oncall'},
        {'field':'category','match':'equals','text':'Duty','action':'work'}]}
    r={'summary':'Night ON CALL','start':{'date':'2026-10-01'},'categories':[]}
    assert classify(r,src)[0]['summary']=='[PW:ONCALL]'
    assert classify({**r,'summary':'Not on call'},src)==(None,'ignore')
    assert classify({**r,'summary':'Unknown'},src)==(None,'unknown')
    assert classify({**r,'summary':'Unknown','categories':['Duty']},src)[1]=='work'
    assert classify({**r,'summary':'[PW:OFF]'},src)[1]=='off'
    assert classify({**r,'summary':'Unknown'},{**src,'defaultRota':'work'})[1]=='work'


def test_timed_off_rule_rejected():
    with pytest.raises(ValueError):classify({'summary':'[PW:OFF]','start':{'dateTime':'2026-10-01T10:00:00Z'}},{'mode':'rota'})


@pytest.mark.parametrize('url',['http://example.net/feed','file:///etc/passwd','https://127.0.0.1/x','https://169.254.169.254/x','https://10.1.2.3/x','https://[::1]/x','https://[::ffff:127.0.0.1]/x','https://user:secret@example.net/x','https://example.net:8443/x','https://example.net/x#frag','https://localhost/x','https://machine.local/x','https://example.net/\nsecret','https://example.net\\@127.0.0.1/x'])
def test_url_policy(url):
    with pytest.raises(ValueError):normalise_url(url)


def test_webcal_and_https_normalisation():
    assert normalise_url('webcal://feeds.example.net/a?key=fixture')=='https://feeds.example.net/a?key=fixture'
    assert normalise_url('https://feeds.example.net:443/a')=='https://feeds.example.net/a'
