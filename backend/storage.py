"""SQLite persistence. One application worker; short atomic transactions only."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import threading
import secrets
from cryptography.fernet import Fernet, InvalidToken
from .settings import DisplayConfig


def dumps(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=True, sort_keys=True)


class Store:
    def __init__(self, folder: Path, key: str):
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.path = folder / 'paperweek.sqlite3'
        self.cipher = Fernet(key.encode('ascii'))
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA busy_timeout=15000')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS sources(
                id TEXT PRIMARY KEY, config TEXT NOT NULL, revision INTEGER NOT NULL);

            CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(
                digest TEXT PRIMARY KEY, role TEXT NOT NULL, label TEXT NOT NULL,
                created REAL NOT NULL, expires REAL NOT NULL, last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pairs(
                digest TEXT PRIMARY KEY, label TEXT NOT NULL, expires REAL NOT NULL,
                days INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_states(
                digest TEXT PRIMARY KEY, session TEXT NOT NULL, payload TEXT NOT NULL,
                expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS windows(
                calendar TEXT NOT NULL, zone TEXT NOT NULL, month TEXT NOT NULL,
                data TEXT, success REAL, attempted REAL, error TEXT,
                next_at REAL NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
                requested REAL NOT NULL DEFAULT 0,
                PRIMARY KEY(calendar,zone,month));
        ''')
        self.db.commit()
        os.chmod(self.path, 0o600)
        sentinel = self.get('key-check')
        if sentinel is None:
            self.set_secret('key-check', {'ok': True})
        else:
            try:
                assert self.get_secret('key-check') == {'ok': True}
            except (InvalidToken, AssertionError):
                self.close()
                raise ValueError('Token encryption key does not match this database. Restore the original private configuration.') from None
        if self.get('config') is None:
            self.set('config', DisplayConfig().model_dump())
            self.set('config_revision', 1)
        if self.get('schema_version', 1) not in (1, 2):
            self.close()
            raise ValueError('Unsupported database schema. Do not downgrade without a backup.')
        # Non-destructive v0.4 migration; old sessions, token and cache survive.
        columns = {r['name'] for r in self.rows('PRAGMA table_info(windows)')}
        if 'warnings' not in columns:
            self.execute('ALTER TABLE windows ADD COLUMN warnings TEXT')
        self.set('schema_version', 2)

    def execute(self, query, args=()):
        with self.lock, self.db:
            return self.db.execute(query, args)

    def rows(self, query, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(query, args).fetchall()]

    def get(self, key, default=None):
        rows = self.rows('SELECT value FROM kv WHERE key=?', (key,))
        return json.loads(rows[0]['value']) if rows else default

    def set(self, key, value):
        self.execute('INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, dumps(value)))

    def delete(self, key):
        self.execute('DELETE FROM kv WHERE key=?', (key,))

    def get_secret(self, key):
        value = self.get(key)
        return json.loads(self.cipher.decrypt(value.encode())) if value else None

    def set_secret(self, key, value):
        self.set(key, self.cipher.encrypt(dumps(value).encode()).decode())

    def config(self):
        return DisplayConfig.model_validate(self.get('config'))

    def config_record(self):
        with self.lock:
            return self.config(), self.get('config_revision', 1)

    def save_config(self, config, expected_revision):
        with self.lock, self.db:
            current = self.get('config_revision', 1)
            if current != expected_revision:
                raise ValueError('Settings changed in another browser. Reload before saving.')
            self.db.execute('UPDATE kv SET value=? WHERE key=?', (dumps(config.model_dump()), 'config'))
            self.db.execute('UPDATE kv SET value=? WHERE key=?', (dumps(current + 1), 'config_revision'))
            from .sources import effective_sources
            keys = {m.key for m in config.members}
            # Remove orphan sources, including encrypted URL/raw-feed storage.
            for source in self.sources():
                if source['member'] not in keys:
                    self._delete_source(source['id'])
            ids = [source['id'] for source in effective_sources(self, config)]
            if config.source != 'google' or not ids:
                self.db.execute('DELETE FROM windows')
            else:
                marks = ','.join('?' for _ in ids)
                self.db.execute(f'DELETE FROM windows WHERE zone<>? OR calendar NOT IN ({marks})', (config.timezone, *ids))
                self.db.execute('UPDATE windows SET next_at=0')
        return current + 1

    def sources(self):
        return [dict(json.loads(r['config']), id=r['id'], revision=r['revision'],
                     hasUrl=bool(self.get('source-secret:'+r['id'])))
                for r in self.rows('SELECT * FROM sources ORDER BY rowid')]

    def source(self, sid):
        return next((s for s in self.sources() if s['id'] == sid), None)

    def save_source(self, source, sid=None, expected_revision=None):
        from .sources import PREFIX
        with self.lock, self.db:
            old = self.source(sid) if sid else None
            if sid and not old:
                raise ValueError('Calendar source no longer exists.')
            if old and expected_revision != old['revision']:
                raise ValueError('Source changed in another browser. Reload before saving.')
            if not sid and len(self.sources()) >= 24:
                raise ValueError('Up to 24 additional sources are supported.')
            sid = sid or secrets.token_hex(12)
            if source.kind == 'ical' and not source.url and not (old and old['kind']=='ical' and old['hasUrl']):
                raise ValueError('Enter the private subscription URL for a new iCalendar source.')
            revision = (old['revision']+1) if old else 1
            encoded = dumps(source.safe())
            self.db.execute('INSERT INTO sources VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config,revision=excluded.revision', (sid, encoded, revision))
            if source.url:
                encrypted = self.cipher.encrypt(dumps({'url':source.url}).encode()).decode()
                self.db.execute('INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('source-secret:'+sid, dumps(encrypted)))
            if source.kind != 'ical':
                self.db.execute('DELETE FROM kv WHERE key=?', ('source-secret:'+sid,))
            # Changed rules, owner, URL or enabled status invalidate this source's
            # projection, not other calendars or the Google authorisation.
            self.db.execute('DELETE FROM kv WHERE key=?', ('source-cache:'+sid,))
            self.db.execute('DELETE FROM windows WHERE calendar=?', (PREFIX+sid,))
            self._bump_config()
        return self.source(sid)

    def _bump_config(self):
        revision = self.get('config_revision', 1)+1
        self.db.execute('UPDATE kv SET value=? WHERE key=?', (dumps(revision), 'config_revision'))

    def _delete_source(self, sid):
        from .sources import PREFIX
        self.db.execute('DELETE FROM sources WHERE id=?', (sid,))
        self.db.execute('DELETE FROM kv WHERE key IN (?,?)', ('source-secret:'+sid, 'source-cache:'+sid))
        self.db.execute('DELETE FROM windows WHERE calendar=?', (PREFIX+sid,))

    def delete_source(self, sid, expected_revision):
        with self.lock, self.db:
            old = self.source(sid)
            if not old or old['revision'] != expected_revision:
                raise ValueError('Source changed or no longer exists. Reload before deleting.')
            self._delete_source(sid)
            self._bump_config()

    def clear_google_windows(self):
        """An OAuth account switch never discards independent iCalendar data."""
        from .sources import PREFIX
        ids = [PREFIX+s['id'] for s in self.sources() if s['kind']=='ical']
        if not ids:
            self.execute('DELETE FROM windows')
        else:
            marks = ','.join('?' for _ in ids)
            self.execute(f'DELETE FROM windows WHERE calendar NOT IN ({marks})', ids)

    def consume(self, table, digest, now, session=None):
        if table not in ('pairs', 'oauth_states'):
            raise ValueError('Unknown one-time token table.')
        with self.lock, self.db:
            row = self.db.execute(f'SELECT * FROM {table} WHERE digest=?', (digest,)).fetchone()
            if not row or row['expires'] <= now or (session is not None and row['session'] != session):
                return None
            self.db.execute(f'DELETE FROM {table} WHERE digest=?', (digest,))
            return dict(row)

    def cleanup(self, now):
        for table in ('sessions', 'pairs', 'oauth_states'):
            self.execute(f'DELETE FROM {table} WHERE expires<?', (now,))

    def close(self):
        with self.lock:
            self.db.close()
