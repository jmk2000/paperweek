"""Validated runtime and shared display settings. No household defaults."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .school import SchoolProfile, validate_school_members, public_school


@dataclass(frozen=True)
class Settings:
    public_url: str
    admin_hash: str
    token_key: str
    data_dir: Path
    site_dir: Path
    client_id: str = ''
    client_secret: str = ''
    scheduler: bool = True
    warm_before: int = 1
    warm_after: int = 2

    def __post_init__(self):
        u = urlsplit(self.public_url)
        local = u.hostname in ('localhost', '127.0.0.1', '::1')
        if (u.scheme != 'https' and not (u.scheme == 'http' and local)) or not u.hostname:
            raise ValueError('PAPERWEEK_PUBLIC_URL must use HTTPS (HTTP only for localhost).')
        if u.path or u.query or u.fragment or u.username or u.password:
            raise ValueError('PAPERWEEK_PUBLIC_URL must be an origin without path or trailing slash.')
        if not self.admin_hash.startswith('scrypt:') or not self.token_key:
            raise ValueError('Run tools/configure_backend.py to initialise private secrets.')
        if not 0 <= self.warm_before <= 3 or not 0 <= self.warm_after <= 6:
            raise ValueError('Invalid warm-cache month count.')

    @property
    def secure(self):
        return self.public_url.startswith('https://')

    @property
    def callback_url(self):
        return self.public_url + '/api/oauth/callback'

    @classmethod
    def from_env(cls):
        return cls(
            public_url=os.environ.get('PAPERWEEK_PUBLIC_URL', '').rstrip('/'),
            admin_hash=os.environ.get('PAPERWEEK_ADMIN_HASH', ''),
            token_key=os.environ.get('PAPERWEEK_TOKEN_KEY', ''),
            data_dir=Path(os.environ.get('PAPERWEEK_DATA_DIR', '/data')),
            site_dir=Path(os.environ.get('PAPERWEEK_SITE_DIR', 'dist-preview')),
            client_id=os.environ.get('PAPERWEEK_GOOGLE_CLIENT_ID', ''),
            client_secret=os.environ.get('PAPERWEEK_GOOGLE_CLIENT_SECRET', ''),
        )


class Member(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)
    key: str = Field(min_length=1, max_length=48, pattern=r'^[a-zA-Z0-9_-]+$')
    label: str = Field(min_length=1, max_length=40)
    badge: str = Field(min_length=1, max_length=2, pattern=r'^[A-Z0-9]{1,2}$')
    colour: Literal['blue', 'green', 'red', 'yellow', 'black']
    calendarId: str = Field(default='', max_length=512)
    maskTitles: bool = False

    @field_validator('label', 'calendarId')
    @classmethod
    def clean(cls, v):
        if re.search(r'[\x00-\x1f\x7f]', v):
            raise ValueError('Control characters are not allowed.')
        return v.strip()


class DisplayConfig(BaseModel):
    # v3 import format intentionally retained for existing private exports.
    model_config = ConfigDict(extra='ignore', strict=True)
    version: Literal[3] = 3
    title: str = Field(default='Our calendar', min_length=1, max_length=80)
    timezone: str = Field(default='UTC', min_length=1, max_length=64)
    weekStart: Literal[0, 1] = 1
    defaultView: Literal['rolling', 'week', 'month'] = 'rolling'
    school: list[SchoolProfile] = Field(default_factory=list, max_length=6)
    paperPalette: bool = True
    maskPrivate: bool = True
    deduplicate: bool = False
    rotaMember: str = Field(default='member-2', max_length=48)
    persistentLabels: bool = True
    helpSeconds: int = Field(default=20, ge=5, le=120)
    refreshSeconds: int = Field(default=0, ge=0, le=60)
    pollMinutes: int = Field(default=5, ge=1, le=60)
    clientId: str = ''  # Discarded: the server's OAuth identity is private configuration.
    # 'google' is the backwards-compatible wire value for all live sources.
    source: Literal['demo', 'google'] = 'demo'
    members: list[Member] = Field(min_length=1, max_length=6, default_factory=lambda: [
        Member(key=f'member-{i}', label=label, badge=str(i), colour=colour)
        for i, label, colour in [(1, 'Adult 1', 'blue'), (2, 'Adult 2', 'green'),
                                (3, 'Child 1', 'red'), (4, 'Child 2', 'yellow')]])

    @field_validator('title')
    @classmethod
    def clean_title(cls, v):
        if not v.strip() or re.search(r'[\x00-\x1f\x7f]', v):
            raise ValueError('Invalid display title.')
        return v.strip()

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, v):
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Use a valid IANA timezone.') from None
        return v

    @model_validator(mode='after')
    def unique(self):
        for attr in ['key', 'badge', 'calendarId']:
            values = [getattr(m, attr) for m in self.members if getattr(m, attr)]
            if len(values) != len(set(values)):
                raise ValueError(f'Each {attr} must be unique.')
        if self.rotaMember and self.rotaMember not in {m.key for m in self.members}:
            raise ValueError('Rota member must be a configured member.')
        if any(not m.label.strip() for m in self.members):
            raise ValueError('Names cannot be blank.')
        validate_school_members(self.school, self.members)
        self.clientId = ''
        return self

    def public(self):
        result = self.model_dump()
        result['school'] = public_school(self.school, self.members)
        for m in result['members']:
            # Stable local identifiers, NOT Google calendar IDs.
            m['calendarId'] = m['key'] if self.source == 'google' else ''
        return result
