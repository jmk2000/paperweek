"""Private, many-to-one calendar sources and explicit rota classification.

Google primary mappings stay compatible with v0.4. Additional sources have
opaque IDs; subscription URLs are encrypted separately and are write-only.
"""
from __future__ import annotations
import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PREFIX = '@source:'
TAG = re.compile(r'^\[PW:(WORK|ONCALL|OFF)\](?:\s|$)', re.I)


def clean_text(value):
    if re.search(r'[\x00-\x1f\x7f]', value):
        raise ValueError('Control characters are not allowed.')
    return value.strip()


def normalise_url(value: str) -> str:
    """Only public HTTPS subscriptions. No credentials/ports or LAN targets."""
    value = value.strip()
    if value.lower().startswith('webcal://'):
        value = 'https://' + value[9:]
    if re.search(r'[\x00-\x20\x7f\\]', value):
        raise ValueError('Use a valid HTTPS calendar subscription address.')
    try:
        u = urlsplit(value)
        host = (u.hostname or '').rstrip('.').lower()
        if u.scheme != 'https' or not host or u.username or u.password or u.fragment or u.port not in (None, 443):
            raise ValueError()
        host = host.encode('idna').decode('ascii')
        if '%' in host or host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host):
                raise ValueError()
        else:
            if not ip.is_global or ip.is_multicast or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped):
                raise ValueError()
        netloc = '[' + host + ']' if ':' in host else host
        return urlunsplit(('https', netloc, u.path or '/', u.query, ''))
    except (ValueError, UnicodeError):
        raise ValueError('Use a public HTTPS subscription URL (webcal is upgraded to HTTPS). LAN, loopback, embedded passwords and non-443 ports are blocked.') from None


class RotaRule(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    field: Literal['title', 'category'] = 'title'
    match: Literal['equals', 'contains'] = 'equals'
    text: str = Field(min_length=1, max_length=120)
    action: Literal['work', 'oncall', 'off', 'ignore']

    @field_validator('text')
    @classmethod
    def clean(cls, v):
        v = clean_text(v)
        if not v:
            raise ValueError('A match needs some text.')
        return v


class SourceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    label: str = Field(min_length=1, max_length=80)
    member: str = Field(min_length=1, max_length=48, pattern=r'^[a-zA-Z0-9_-]+$')
    kind: Literal['ical', 'google'] = 'ical'
    calendarId: str = Field(default='', max_length=512)
    url: str = Field(default='', max_length=4096, repr=False)
    enabled: bool = False
    timezone: str = Field(default='UTC', max_length=64)
    pollMinutes: int = Field(default=30, ge=5, le=1440)
    mode: Literal['events', 'rota'] = 'events'
    defaultRota: Literal['unknown', 'work'] = 'unknown'
    rules: list[RotaRule] = Field(default_factory=list, max_length=20)

    @field_validator('label', 'calendarId')
    @classmethod
    def clean(cls, v):
        return clean_text(v)

    @field_validator('timezone')
    @classmethod
    def zone(cls, v):
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Choose an IANA timezone.') from None
        return v

    @field_validator('url')
    @classmethod
    def url_ok(cls, v):
        return normalise_url(v) if v.strip() else ''

    @model_validator(mode='after')
    def valid(self):
        if not self.label:
            raise ValueError('Enter a source name.')
        if self.kind == 'google' and (not self.calendarId or self.url):
            raise ValueError('A Google source needs a calendar ID and no URL.')
        if self.kind == 'ical' and self.calendarId:
            raise ValueError('An iCalendar source uses a URL, not a Google calendar ID.')
        return self

    def safe(self):
        return self.model_dump(exclude={'url'})


def effective_sources(store, config):
    """All active mappings. Source addresses never appear in returned jobs."""
    result = [dict(id=m.calendarId, member=m.key, label=m.label+' · Google', kind='google',
                   calendarId=m.calendarId, mode='events', rules=[], defaultRota='unknown',
                   timezone=config.timezone, pollMinutes=config.pollMinutes, revision=0, primary=True)
              for m in config.members if m.calendarId]
    keys = {m.key for m in config.members}
    for s in store.sources():
        if s['enabled'] and s['member'] in keys:
            # A rota-only source never leaks shift entries into another person's
            # appointments if the rota band is moved/disabled in shared settings.
            if s['mode'] == 'rota' and s['member'] != config.rotaMember:
                continue
            result.append({**s, 'id':PREFIX+s['id'], 'primary':False})
    return result


def classify(raw: dict, source: dict):
    """Returns (display event or None, interpretation). Rules are first-match.

    Explicit PW tags precede user rules. Defaults never turn absent days into OFF.
    Original titles are only retained in private cache/admin preview.
    """
    if source['mode'] != 'rota':
        return raw, 'appointment'
    title = str(raw.get('summary', ''))
    tag = TAG.match(title)
    action = tag[1].lower() if tag else None
    if action is None:
        for rule in source.get('rules', []):
            values = [title] if rule['field'] == 'title' else raw.get('categories', [])
            needle = rule['text'].casefold()
            if any((needle == str(v).casefold() if rule['match'] == 'equals' else needle in str(v).casefold()) for v in values):
                action = rule['action']
                break
    if action is None:
        action = source.get('defaultRota', 'unknown')
    if action in ('unknown', 'ignore'):
        return None, action
    if action == 'off' and not raw['start'].get('date'):
        raise ValueError('An OFF rota match is timed. Use an all-day OFF entry or Ignore this rule; partial-day leave is not a whole day off.')
    return {**raw, 'summary':'[PW:'+action.upper()+']'}, action
