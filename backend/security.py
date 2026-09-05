"""Local administration, one-time pairing and server-side session storage."""
from __future__ import annotations
import base64
from collections import defaultdict, deque
import hashlib
import hmac
import secrets
import time
from fastapi import HTTPException, Request, Response

COOKIE = 'paperweek_session'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def password_hash(password: str):
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=67108864)
    return 'scrypt:' + base64.urlsafe_b64encode(salt).decode() + ':' + base64.urlsafe_b64encode(derived).decode()


def password_ok(password: str, stored: str):
    if not isinstance(password, str) or not 1 <= len(password) <= 512:
        return False
    try:
        _, salt, expected = stored.split(':')
        actual = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=32768, r=8, p=1, maxmem=67108864)
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


class Limiter:
    """Single-worker rate limiter, intentionally does not trust forwarded IPs."""
    def __init__(self, clock=time.time):
        self.clock = clock
        self.buckets = defaultdict(deque)

    def check(self, key, maximum=10, seconds=900):
        now = self.clock()
        queue = self.buckets[key]
        while queue and queue[0] <= now - seconds:
            queue.popleft()
        if len(queue) >= maximum:
            raise HTTPException(429, 'Too many attempts. Wait before trying again.', headers={'Retry-After': str(seconds)})
        queue.append(now)
        if len(self.buckets) > 4096:
            # Retain recent buckets; do not allow unbounded remote-key growth.
            self.buckets = defaultdict(deque, {k:v for k,v in self.buckets.items() if v and v[-1] > now - 3600})


def session(request: Request, admin=False):
    token = request.cookies.get(COOKIE, '')
    store = request.app.state.store
    rows = store.rows('SELECT * FROM sessions WHERE digest=? AND expires>?', (digest(token), time.time())) if token else []
    if not rows:
        raise HTTPException(401, 'Pair this display or sign in as administrator.')
    row = rows[0]
    if admin and row['role'] != 'admin':
        raise HTTPException(403, 'Administrator access required.')
    if row['last_seen'] < time.time() - 60:
        store.execute('UPDATE sessions SET last_seen=? WHERE digest=?', (time.time(), row['digest']))
    return row


def new_session(store, response: Response, settings, role, label, days):
    token = secrets.token_urlsafe(32)
    now = time.time()
    max_age = int(days * 86400)
    store.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)', (digest(token), role, label, now, now + max_age, now))
    response.set_cookie(COOKIE, token, max_age=max_age, httponly=True, secure=settings.secure, samesite='lax', path='/')
    return digest(token)
