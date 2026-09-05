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
            'start':clean_start, 'end':clean_end}


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
    def __init__(self, store, google, settings, clock=time.time):
        self.store, self.google, self.settings, self.clock = store, google, settings, clock
        self.wake = asyncio.Event()
        self.lock = asyncio.Lock()
        self.task = None
        self.last_tick = 0
        self.heartbeat = 0

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
        for m in config.members:
            if not m.calendarId:
                continue
            for month in months:
                self.store.execute('''INSERT INTO windows(calendar,zone,month,requested) VALUES(?,?,?,?)
                    ON CONFLICT(calendar,zone,month) DO NOTHING''', (m.calendarId, config.timezone, month, now if demand else 0))
                if demand:
                    self.store.execute('UPDATE windows SET requested=? WHERE calendar=? AND zone=? AND month=?',
                                       (now, m.calendarId, config.timezone, month))
        self.wake.set()

    def warm(self):
        config = self.store.config()
        if config.source != 'google':
            return
        today = datetime.fromtimestamp(self.clock(), ZoneInfo(config.timezone)).date()
        current = month_start(today)
        months = [add_month(current, i).isoformat() for i in range(-self.settings.warm_before, self.settings.warm_after+1)]
        # Do not wake our own worker on every loop iteration.
        for m in config.members:
            for month in months:
                self.store.execute('INSERT OR IGNORE INTO windows(calendar,zone,month) VALUES(?,?,?)', (m.calendarId, config.timezone, month))
        placeholders = ','.join('?' for _ in months)
        self.store.execute(f'DELETE FROM windows WHERE requested<? AND month NOT IN ({placeholders})', (self.clock()-7*86400, *months))

    async def tick(self):
        async with self.lock:
            self.heartbeat = self.clock()
            config = self.store.config()
            self.warm()
            if config.source != 'google' or self.google.connection != 'connected':
                return
            jobs = self.store.rows('SELECT * FROM windows WHERE next_at<=? ORDER BY requested DESC,next_at ASC LIMIT 48', (self.clock(),))
            ids = {m.calendarId for m in config.members}
            rota_id = next((m.calendarId for m in config.members if m.key == config.rotaMember), None)
            generation = self.google.generation
            for row in jobs:
                self.heartbeat = self.clock()
                key = (row['calendar'], row['zone'], row['month'])
                if row['calendar'] not in ids or row['zone'] != config.timezone:
                    continue
                self.store.execute('UPDATE windows SET attempted=? WHERE calendar=? AND zone=? AND month=?', (self.clock(), *key))
                try:
                    start, end = bounds(row['month'], row['zone'])
                    raw = await self.google.events(row['calendar'], start, end, row['zone'])
                    items = []
                    for r in raw:
                        cleaned = validate_raw(r, row['calendar'] == rota_id)
                        if cleaned is not None:
                            items.append(cleaned)
                    # Don't commit old-account results after a relink/disconnect.
                    latest = self.store.config()
                    if generation != self.google.generation:
                        return
                    if latest.timezone != row['zone'] or latest.source != 'google' or row['calendar'] not in {m.calendarId for m in latest.members}:
                        continue
                    self.store.execute('''UPDATE windows SET data=?,success=?,error=NULL,failures=0,next_at=?
                        WHERE calendar=? AND zone=? AND month=?''',
                        (dumps(items), self.clock(), self.clock()+latest.pollMinutes*60, *key))
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    known = isinstance(e, CalendarError)
                    error = str(e) if known else 'Invalid calendar data or internal sync error; previous data retained.'
                    failures = min(row['failures']+1, 12)
                    wait = max(min(60*2**(failures-1), 3600), getattr(e, 'retry_after', 0)) + random.uniform(0, 5)
                    self.store.execute('UPDATE windows SET error=?,failures=?,next_at=? WHERE calendar=? AND zone=? AND month=?',
                                       (error, failures, self.clock()+wait, *key))
                    # Deliberately omit exception text, IDs and payloads from logs.
                    log.warning('Calendar sync failed (%s); retained previous snapshot.', e.kind if known else 'invalid-data')
                    if known and e.kind in ('reauth', 'config', 'network', 'temporary', 'quota'):
                        # Back off the remaining due jobs too, not one request per calendar.
                        self.store.execute('UPDATE windows SET next_at=? WHERE next_at<=?', (self.clock()+wait, self.clock()))
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
        self.wake.set()

    def snapshot(self, first, days):
        config, revision = self.store.config_record()
        epoch = self.google.generation
        today = datetime.fromtimestamp(self.clock(), ZoneInfo(config.timezone)).date()
        if first < add_month(today, -24) or first + timedelta(days=days) > add_month(today, 25):
            raise ValueError('Browse within two years of today. This is a bounded household cache.')
        if config.source == 'demo':
            return {'ready':True, 'config':config.public(), 'batches':[], 'stale':False, 'connection':self.google.connection,
                    'coverage':[], 'lastSuccess':None, 'first':first.isoformat(), 'days':days, 'revision':revision, 'dataEpoch':epoch}
        months = months_for(first, days)
        self.register(config, months)
        batches, coverage = [], []
        all_ready = True
        threshold = max(900, config.pollMinutes*180)
        for m in config.members:
            items, seen = [], set()
            for month in months:
                rows = self.store.rows('SELECT * FROM windows WHERE calendar=? AND zone=? AND month=?', (m.calendarId, config.timezone, month))
                row = rows[0] if rows else {'data':None,'success':None,'error':'Settings changed; retrying.'}
                ready = row['data'] is not None
                all_ready &= ready
                coverage.append({'member':m.key, 'month':month, 'ready':ready, 'lastSuccess':row['success'],
                    'error':row['error'], 'stale':bool(not ready or row['error'] or self.clock()-(row['success'] or 0)>threshold)})
                if not ready:
                    continue
                for r in json.loads(row['data']):
                    identity = r['id'] or r['iCalUID'] + dumps(r['start'])
                    if identity in seen or not intersects(r, first, days, config.timezone):
                        continue
                    seen.add(identity)
                    title = r['summary']
                    marker = TAG.match(title) if m.key == config.rotaMember else None
                    if marker:
                        # The display intentionally receives working/on-call status,
                        # but never the original shift title when it is private.
                        title = '[PW:' + marker[1].upper() + ']'
                    elif m.maskTitles or (config.maskPrivate and r.get('visibility') == 'private'):
                        title = 'Busy'
                    def opaque(value):
                        return hmac.new(self.settings.token_key.encode(), value.encode(), hashlib.sha256).hexdigest()
                    items.append({'id':opaque(identity), 'iCalUID':opaque(r['iCalUID'] or m.key+':'+identity),
                                  'summary':title, 'start':r['start'], 'end':r['end']})
            batches.append({'member':m.key, 'items':items})
        if sum(len(b['items']) for b in batches) > 2048:
            raise ValueError('More than 2048 expanded records in this view; use a shorter range or fewer calendars.')
        successes = [c['lastSuccess'] for c in coverage if c['lastSuccess'] is not None]
        stale = any(c['stale'] for c in coverage) or self.google.connection != 'connected'
        return {'ready':all_ready, 'config':config.public(), 'batches':batches if all_ready else [],
                'coverage':coverage, 'stale':stale, 'connection':self.google.connection,
                'lastSuccess':min(successes) if len(successes)==len(coverage) else None,
                'first':first.isoformat(), 'days':days, 'revision':revision, 'dataEpoch':epoch}

    def status(self):
        config = self.store.config()
        members = {m.calendarId:m.key for m in config.members}
        windows = self.store.rows('SELECT calendar,month,success,attempted,error,next_at FROM windows ORDER BY month,calendar')
        for w in windows:
            w['member'] = members.get(w.pop('calendar'), 'removed')
        return {'connection':self.google.connection, 'oauthConfigured':self.google.configured,
                'callbackUrl':self.settings.callback_url, 'windows':windows,
                'schedulerRunning':bool(self.task and not self.task.done()),
                'heartbeat':self.heartbeat or None, 'lastCycle':self.last_tick or None,
                'notice':self.store.get('oauth_notice'), 'pollMinutes':config.pollMinutes}
