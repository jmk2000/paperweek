"""Subscription lifecycle and isolated parsing. No feed URL leaves admin input."""
from __future__ import annotations
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import time
from .google import CalendarError
from .sources import PREFIX


async def isolated(job):
    env = {k:v for k,v in os.environ.items() if k in ('PATH', 'SYSTEMROOT', 'LANG', 'LC_ALL', 'TZ')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    proc = await asyncio.create_subprocess_exec(sys.executable, '-m', 'backend.ical_worker',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        cwd=str(Path(__file__).resolve().parents[1]), env=env)
    try:
        output, _ = await asyncio.wait_for(proc.communicate(json.dumps(job).encode()), timeout=25 if job.get('action')=='fetch' else 12)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0 or len(output)>12*1024*1024:
        raise CalendarError('ical', 'Calendar worker exceeded a resource limit; previous data retained.')
    try:
        result = json.loads(output)
    except (ValueError, UnicodeError):
        raise CalendarError('ical', 'Calendar worker did not complete; previous data retained.') from None
    if result.get('error'):
        raise CalendarError('ical', str(result['error']))
    return result


class ICalendar:
    def __init__(self, store, runner=isolated, clock=time.time):
        self.store, self.runner, self.clock = store, runner, clock
        self.lock = asyncio.Lock()

    async def events(self, source, start, stop, zone, force=False):
        async with self.lock:
            sid = source['id'].removeprefix(PREFIX)
            row = self.store.source(sid)
            if not row or row['revision'] != source['revision']:
                raise CalendarError('changed', 'Calendar source changed. Retrying.')
            secret = self.store.get_secret('source-secret:'+sid)
            if not secret or not secret.get('url'):
                raise CalendarError('ical', 'Install a private subscription URL for this source.')
            cached = self.store.get_secret('source-cache:'+sid) or {}
            download_result = None
            # Reuse one validated full feed across adjacent month windows, rather
            # than downloading the same subscription once per visible month.
            if force or not cached or self.clock()-cached.get('checked', 0) >= source['pollMinutes']*60:
                try:
                    download_result = await self.runner({'action':'fetch', 'url':secret['url'],
                        'etag':cached.get('etag',''), 'modified':cached.get('modified','')})
                except (asyncio.TimeoutError, OSError):
                    raise CalendarError('ical', 'Feed request timed out or failed; previous data retained.') from None
                if download_result.get('notModified'):
                    if not cached.get('data'):
                        raise CalendarError('ical', 'Provider returned Not Modified without a saved feed.')
                else:
                    cached = download_result
            if not cached.get('data'):
                raise CalendarError('ical', 'No complete subscribed calendar was returned.')
            try:
                parsed = await self.runner({'action':'parse', 'data':cached['data'], 'start':start, 'stop':stop,
                                             'fallback':source['timezone'], 'zone':zone})
            except (asyncio.TimeoutError, OSError):
                raise CalendarError('ical', 'Calendar parsing exceeded its resource limit; previous data retained.') from None
            latest = self.store.source(sid)
            if not latest or latest['revision'] != source['revision']:
                raise CalendarError('changed', 'Calendar source changed during refresh. Retrying.')
            if download_result is not None:
                cached['checked'] = self.clock()
                self.store.set_secret('source-cache:'+sid, cached)
            # Reprojecting a recent full feed is not a new provider check.
            parsed['checked'] = cached.get('checked', self.clock())
            return parsed
