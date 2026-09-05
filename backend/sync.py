"""Bounded, full-window polling with atomic per-calendar/month cache replacement.

Full window fetches deliberately avoid combining syncToken with timeMin/timeMax.
Recurring expansion and cancellations come from Google; the C UI retains rota,
layout, day-overlap and density rules. No job performs Google writes.
"""
from __future__ import annotations
import asyncio
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import random
import re
import time
from zoneinfo import ZoneInfo
from .google import CalendarError
from .storage import dumps
from .sources import effective_sources, classify, PREFIX
from .ical import ICalendar

log = logging.getLogger('paperweek.sync')
UTC = timezone.utc
TAG = re.compile(r'^\[PW:(WORK|ONCALL|OFF)\](?:\s|$)', re.I)


def month_start(d):
    return date(d.year, d.month, 1)


def add_month(d, n):
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def months_for(first: date, days: int):
    end = first + timedelta(days=days-1)
    result, m = [], month_start(first)
    while m <= end:
        result.append(m.isoformat())
        m = add_month(m, 1)
    return result


def bounds(month, zone):
    start = date.fromisoformat(month)
    z = ZoneInfo(zone)
    return (datetime.combine(d, datetime.min.time(), z).astimezone(UTC).isoformat()
            for d in (start, add_month(start, 1)))


def parsed_time(value):
    if not isinstance(value, str) or not re.search(r'(Z|[+-]\d{2}:\d{2})$', value):
        raise ValueError('Timed event has no explicit UTC offset.')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def validate_raw(raw, rota=False):
    if not isinstance(raw, dict):
        raise ValueError('Invalid event record.')
    if raw.get('status') == 'cancelled' or any(a.get('self') and a.get('responseStatus') == 'declined' for a in raw.get('attendees', [])):
        return None
    start, end = raw.get('start', {}), raw.get('end', {})
    if start.get('date'):
        a, b = date.fromisoformat(start['date']), date.fromisoformat(end['date'])
        if a >= b:
            raise ValueError('All-day end must be exclusive.')
        clean_start, clean_end = {'date':a.isoformat()}, {'date':b.isoformat()}
    else:
        a, b = parsed_time(start.get('dateTime')), parsed_time(end.get('dateTime'))
        if b < a:
            raise ValueError('Event ends before it starts.')
        clean_start, clean_end = {'dateTime':a.isoformat()}, {'dateTime':b.isoformat()}
    title = str(raw.get('summary') or 'Busy')[:4096]
    marker = TAG.match(title) if rota else None
    if marker and marker[1].upper() == 'OFF' and not start.get('date'):
        raise ValueError('An OFF marker must be all-day.')
    if not 1900 <= a.year <= b.year <= 2199:
        raise ValueError('Event date is outside supported years.')
    return {'id':str(raw.get('id') or ''), 'iCalUID':str(raw.get('iCalUID') or ''),
            'summary':title, 'visibility':raw.get('visibility', 'default'),
            'start':clean_start, 'end':clean_end,
            'categories':[str(c)[:120] for c in raw.get('categories', [])[:50]]}


def intersects(raw, first, days, zone):
    start, end = raw['start'], raw['end']
    until = first + timedelta(days=days)
    if start.get('date'):
        return date.fromisoformat(start['date']) < until and date.fromisoformat(end['date']) > first
    a, b = parsed_time(start['dateTime']), parsed_time(end['dateTime'])
    z = ZoneInfo(zone)
    left = datetime.combine(first, datetime.min.time(), z)
    right = datetime.combine(until, datetime.min.time(), z)
    return a < right and (b > left or (a == b and a >= left))


class Synchronizer:
    def __init__(self, store, google, settings, clock=time.time, ical=None):
        self.store, self.google, self.settings, self.clock = store, google, settings, clock
        self.ical = ical or ICalendar(store, clock=clock)
        self.wake = asyncio.Event()
        self.lock = asyncio.Lock()
        self.task = None
        self.last_tick = 0
        self.heartbeat = 0

    def sources(self, config=None):
        return effective_sources(self.store, config or self.store.config())

    def connection(self, sources):
        # An iCalendar-only household does not need Google credentials at all.
        return self.google.connection if any(s['kind']=='google' for s in sources) else 'connected'

    def start(self):
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    def register(self, config, months, demand=True):
        now = self.clock()
        for s in self.sources(config):
            for month in months:
                self.store.execute('''INSERT INTO windows(calendar,zone,month,requested) VALUES(?,?,?,?)
                    ON CONFLICT(calendar,zone,month) DO NOTHING''', (s['id'], config.timezone, month, now if demand else 0))
                if demand:
                    self.store.execute('UPDATE windows SET requested=? WHERE calendar=? AND zone=? AND month=?',
                                       (now, s['id'], config.timezone, month))
        self.wake.set()

    def warm(self):
        config = self.store.config()
        if config.source != 'google':
            return
        today = datetime.fromtimestamp(self.clock(), ZoneInfo(config.timezone)).date()
        months = [add_month(month_start(today), i).isoformat() for i in range(-self.settings.warm_before, self.settings.warm_after+1)]
        for s in self.sources(config):
            for month in months:
                self.store.execute('INSERT OR IGNORE INTO windows(calendar,zone,month) VALUES(?,?,?)', (s['id'], config.timezone, month))
        placeholders = ','.join('?' for _ in months)
        self.store.execute(f'DELETE FROM windows WHERE requested<? AND month NOT IN ({placeholders})', (self.clock()-7*86400, *months))

    def current(self, source, zone, generation):
        config = self.store.config()
        if config.source != 'google' or config.timezone != zone:
            return False
        if source['kind']=='google' and generation != self.google.generation:
            return False
        return any(s['id']==source['id'] and s['revision']==source['revision'] and s['member']==source['member'] for s in self.sources(config))

    async def tick(self):
        async with self.lock:
            self.heartbeat = self.clock()
            config = self.store.config()
            self.warm()
            if config.source != 'google':
                return
            sources = {s['id']:s for s in self.sources(config)}
            jobs = self.store.rows('SELECT * FROM windows WHERE next_at<=? ORDER BY requested DESC,next_at ASC LIMIT 160', (self.clock(),))
            generation = self.google.generation
            google_wait = 0
            for sid, source in sources.items():
                rows = [r for r in jobs if r['calendar']==sid and r['zone']==config.timezone]
                if not rows:
                    continue
                if source['kind']=='google' and google_wait:
                    self.store.execute('UPDATE windows SET next_at=? WHERE calendar=? AND next_at<=?', (google_wait, sid, self.clock()))
                    continue
                # Group iCal windows: one download + expansion serves a whole
                # warm cache cycle. Google keeps its provider-side month query.
                if source['kind']=='ical':
                    # A subscription is one complete file. Refresh every retained
                    # month together, even when only a newly browsed month is due.
                    rows = self.store.rows('SELECT * FROM windows WHERE calendar=? AND zone=?', (sid, config.timezone))
                groups = [rows] if source['kind']=='ical' else [[r] for r in rows]
                for group in groups:
                    self.heartbeat = self.clock()
                    for row in group:
                        self.store.execute('UPDATE windows SET attempted=? WHERE calendar=? AND zone=? AND month=?',
                                           (self.clock(), sid, row['zone'], row['month']))
                    try:
                        warnings = []
                        if source['kind']=='google':
                            if self.google.connection != 'connected':
                                raise CalendarError('reauth', 'Google reconnection required. Independent iCalendar sources can still synchronise.')
                            start, end = bounds(group[0]['month'], config.timezone)
                            raw = await self.google.events(source['calendarId'], start, end, config.timezone)
                        else:
                            start = list(bounds(min(r['month'] for r in group), config.timezone))[0]
                            end = list(bounds(max(r['month'] for r in group), config.timezone))[1]
                            parsed = await self.ical.events(source, start, end, config.timezone)
                            raw, warnings = parsed['items'], parsed['warnings']
                        items, unmatched = [], 0
                        for r in raw:
                            cleaned = validate_raw(r, source['member']==config.rotaMember)
                            if cleaned is None:
                                continue
                            try:
                                mapped, interpretation = classify(cleaned, source)
                            except ValueError as e:
                                raise CalendarError('rota', str(e)) from None
                            if interpretation=='unknown':
                                unmatched += 1
                                items.append({**cleaned, '_rotaUnknown': True})
                            if mapped is not None:
                                items.append(mapped)
                        if unmatched:
                            warnings = [*warnings, f'{unmatched} rota occurrence(s) did not match a rule; those entries are not interpreted as work or off. Review the source preview.']
                        if not self.current(source, config.timezone, generation):
                            continue
                        now = self.clock()
                        checked = parsed['checked'] if source['kind']=='ical' else now
                        # Atomic source-group commit. A bad month cannot leave a
                        # partly replaced subscription after removals/changes.
                        with self.store.lock, self.store.db:
                            for row in group:
                                first = date.fromisoformat(row['month'])
                                days = (add_month(first, 1)-first).days
                                selected = [r for r in items if intersects(r, first, days, config.timezone)]
                                self.store.db.execute('''UPDATE windows SET data=?,success=?,error=NULL,warnings=?,failures=0,next_at=?
                                    WHERE calendar=? AND zone=? AND month=?''',
                                    (dumps(selected), checked, dumps(warnings), max(now+1, checked+source['pollMinutes']*60), sid, config.timezone, row['month']))
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        known = isinstance(e, CalendarError)
                        error = str(e) if known else 'Invalid calendar data or internal sync error; previous data retained.'
                        failures = min(max(r['failures'] for r in group)+1, 12)
                        wait = max(min(60*2**(failures-1), 3600), getattr(e,'retry_after',0)) + random.uniform(0,5)
                        self.store.execute('UPDATE windows SET error=?,failures=?,next_at=? WHERE calendar=? AND zone=? AND (next_at<=? OR ?)',
                                           (error, failures, self.clock()+wait, sid, config.timezone, self.clock(), int(source['kind']=='ical')))
                        log.warning('Calendar sync failed (%s); retained previous snapshot.', e.kind if known else 'invalid-data')
                        if source['kind']=='google' and known and e.kind in ('reauth','config','network','temporary','quota'):
                            google_wait = self.clock()+wait
                        break
            self.last_tick = self.clock()
            self.heartbeat = self.clock()

    async def loop(self):
        while True:
            try:
                self.wake.clear()
                self.store.cleanup(self.clock())
                await self.tick()
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                log.error('Synchronisation loop failed; will retry. Private exception details suppressed.')
                await asyncio.sleep(30)

    def request_sync(self):
        self.store.execute('UPDATE windows SET next_at=0')
        # Retain last-known-good body and validators, but check the provider now.
        for s in self.store.sources():
            if s['kind']=='ical':
                cached = self.store.get_secret('source-cache:'+s['id'])
                if cached:
                    cached['checked'] = 0
                    self.store.set_secret('source-cache:'+s['id'], cached)
        self.wake.set()

    def snapshot(self, first, days):
        config, revision = self.store.config_record()
        epoch = self.google.generation
        sources = self.sources(config)
        connection = self.connection(sources)
        today = datetime.fromtimestamp(self.clock(), ZoneInfo(config.timezone)).date()
        if first < add_month(today,-24) or first+timedelta(days=days)>add_month(today,25):
            raise ValueError('Browse within two years of today. This is a bounded household cache.')
        common = {'config':config.public(), 'first':first.isoformat(), 'days':days, 'revision':revision, 'dataEpoch':epoch,
                  'connection':connection, 'googleConnection':self.google.connection}
        if config.source=='demo':
            return {**common, 'ready':True,'batches':[],'stale':False,'coverage':[],'lastSuccess':None}
        months = months_for(first, days)
        self.register(config, months)
        batches, coverage = [], []
        all_ready = True
        for m in config.members:
            items, seen = {}, set()
            off_candidates, occupied = set(), set()
            inference_safe = True
            mine = [s for s in sources if s['member']==m.key]
            for source in mine:
                threshold = max(900, source['pollMinutes']*180)
                for month in months:
                    rows = self.store.rows('SELECT * FROM windows WHERE calendar=? AND zone=? AND month=?', (source['id'],config.timezone,month))
                    row = rows[0] if rows else {'data':None,'success':None,'error':'Settings changed; retrying.','warnings':None}
                    ready = row['data'] is not None
                    all_ready &= ready
                    warning = bool(row.get('warnings') and json.loads(row['warnings']))
                    # Safe source labels are administration-only; tablets get an
                    # opaque key + type and never the feed URL, host or rules.
                    coverage.append({'member':m.key, 'source':hashlib.sha256(source['id'].encode()).hexdigest()[:16],
                        'kind':source['kind'], 'month':month,'ready':ready,'lastSuccess':row['success'], 'error':row['error'],
                        'warning':warning, 'stale':bool(not ready or row['error'] or self.clock()-(row['success'] or 0)>threshold)})
                    if source['mode'] == 'rota':
                        fresh = ready and not coverage[-1]['stale']
                        # Unmatched entries are retained below as occupied days.
                        warnings = json.loads(row.get('warnings') or '[]')
                        safe_warnings = all('rota occurrence(s) did not match a rule' in w for w in warnings)
                        inference_safe &= fresh and safe_warnings
                        if source.get('emptyDaysOff') and fresh and safe_warnings:
                            start = max(first, date.fromisoformat(month))
                            end = min(first + timedelta(days=days), add_month(date.fromisoformat(month), 1))
                            off_candidates.update(start + timedelta(days=i) for i in range((end-start).days))
                    if not ready:
                        continue
                    for r in json.loads(row['data']):
                        if source['mode'] == 'rota' or TAG.match(r['summary']):
                            occupied.update(first + timedelta(days=i) for i in range(days)
                                            if intersects(r, first + timedelta(days=i), 1, config.timezone))
                        if r.get('_rotaUnknown'):
                            continue
                        identity = r['id'] or r['iCalUID']+dumps(r['start'])
                        item_key = (source['id'], identity, dumps(r['start']))
                        if item_key in seen or not intersects(r,first,days,config.timezone):
                            continue
                        seen.add(item_key)
                        title = r['summary']
                        marker = TAG.match(title) if m.key==config.rotaMember else None
                        if marker:
                            title = '[PW:'+marker[1].upper()+']'
                        elif m.maskTitles or (config.maskPrivate and r.get('visibility')=='private'):
                            title = 'Busy'
                        def opaque(value):
                            return hmac.new(self.settings.token_key.encode(),value.encode(),hashlib.sha256).hexdigest()
                        def instant(value):
                            return 'D:'+value['date'] if 'date' in value else 'T:'+parsed_time(value['dateTime']).astimezone(UTC).isoformat()
                        # Same UID + interval within one member deduplicates direct
                        # ICS and Google subscriptions without fuzzy title guesses.
                        duplicate = (r['iCalUID'] or source['id']+identity, instant(r['start']), instant(r['end']))
                        out = {'id':opaque(source['id']+':'+identity), 'iCalUID':opaque(r['iCalUID'] or m.key+':'+identity),
                               'summary':title,'start':r['start'],'end':r['end']}
                        if duplicate not in items or marker:
                            items[duplicate] = out
            if inference_safe and m.key == config.rotaMember:
                for day in sorted(off_candidates - occupied):
                    identity = 'inferred-off:' + m.key + ':' + day.isoformat()
                    items[identity] = {'id':identity, 'iCalUID':identity, 'summary':'[PW:OFF]',
                                       'start':{'date':day.isoformat()},
                                       'end':{'date':(day+timedelta(days=1)).isoformat()}}
            batches.append({'member':m.key,'items':list(items.values())})
        if sum(len(b['items']) for b in batches)>2048:
            raise ValueError('More than 2048 expanded records in this view; use a shorter range or fewer sources.')
        successes = [c['lastSuccess'] for c in coverage if c['lastSuccess'] is not None]
        stale = any(c['stale'] for c in coverage) or connection!='connected'
        return {**common,'ready':all_ready,'batches':batches if all_ready else [], 'coverage':coverage,'stale':stale,
                'warnings':any(c.get('warning') for c in coverage),
                'unmappedMembers':[m.key for m in config.members if not any(s['member']==m.key for s in sources)],
                'lastSuccess':min(successes) if successes and len(successes)==len(coverage) else None}

    def status(self):
        config = self.store.config()
        sources = {s['id']:s for s in self.sources(config)}
        windows = self.store.rows('SELECT calendar,month,success,attempted,error,warnings,next_at FROM windows ORDER BY month,calendar')
        for w in windows:
            source = sources.get(w.pop('calendar'), {})
            w['member'] = source.get('member','removed')
            w['source'] = source.get('label','Removed source')
            w['kind'] = source.get('kind','')
            w['warnings'] = json.loads(w['warnings']) if w['warnings'] else []
        return {'connection':self.google.connection,'oauthConfigured':self.google.configured,
                'callbackUrl':self.settings.callback_url,'windows':windows,'sources':self.store.sources(),
                'schedulerRunning':bool(self.task and not self.task.done()),'heartbeat':self.heartbeat or None,
                'lastCycle':self.last_tick or None,'notice':self.store.get('oauth_notice'),'pollMinutes':config.pollMinutes}
