"""ASGI application: authenticated display API, admin API and public app shell."""
from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import date
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import __version__
from .settings import DisplayConfig, Settings
from .storage import Store, dumps
from .security import COOKIE, Limiter, digest, password_ok, session, new_session
from .google import Google, CalendarError
from .sync import Synchronizer

PUBLIC_ASSETS = {
    'server.html', 'admin.html', 'backend-app.mjs', 'admin.mjs', 'backend-client.mjs',
    'backend.css', 'config.mjs', 'dates.mjs', 'events.mjs', 'renderer.mjs',
    'styles.css', 'manifest.webmanifest', 'icon.svg', 'icon-192.png', 'icon-512.png',
    'paperweek-preview.wasm', 'paperweek-lvgl.wasm', 'paperweek-lvgl.mjs',
    'build-info.json', 'sw.js', 'server-sw.js', 'LICENSE.txt', 'THIRD_PARTY.md',
    'LVGL-LICENSE.txt', 'EMSCRIPTEN-LICENSE.txt',
}


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Login(Body):
    password: str = Field(min_length=1, max_length=512)


class PairCreate(Body):
    label: str = Field(default='Kitchen display', min_length=1, max_length=64)
    days: int = Field(default=365, ge=1, le=365)


class PairRedeem(Body):
    code: str = Field(min_length=8, max_length=32)


class ConfigUpdate(Body):
    revision: int = Field(ge=1)
    config: DisplayConfig


def create_app(settings: Settings | None = None, transport=None):
    settings = settings or Settings.from_env()
    os.umask(0o077)

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.data_dir, settings.token_key)
        app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=False,
                                          transport=transport, trust_env=False)
        app.state.google = Google(app.state.store, settings, app.state.http)
        app.state.sync = Synchronizer(app.state.store, app.state.google, settings)
        app.state.limiter = Limiter()
        # A configured client change requires explicit relinking, not a loop of
        # invalid refresh requests using credentials from a previous deployment.
        fingerprint = hashlib.sha256((settings.client_id + ':' + settings.client_secret).encode()).hexdigest()
        old = app.state.store.get('client_fingerprint')
        if old and old != fingerprint and app.state.store.get('google_token'):
            app.state.store.set('google_status', 'reconnect_required')
        app.state.store.set('client_fingerprint', fingerprint)
        # Resetting the administrator password invalidates old admin sessions.
        auth_fingerprint = hashlib.sha256(settings.admin_hash.encode()).hexdigest()
        if app.state.store.get('admin_fingerprint') != auth_fingerprint:
            app.state.store.execute("DELETE FROM sessions WHERE role='admin'")
            app.state.store.set('admin_fingerprint', auth_fingerprint)
        if settings.scheduler:
            app.state.sync.start()
        try:
            yield
        finally:
            await app.state.sync.stop()
            await app.state.http.aclose()
            app.state.store.close()

    app = FastAPI(title='Paperweek local service', version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlsplit(settings.public_url).hostname, '127.0.0.1', 'localhost'])

    @app.middleware('http')
    async def protection(request: Request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            # Cookies alone are not enough: every write is same-origin JSON from
            # our app. A cross-site form cannot supply this header/content type.
            if request.headers.get('origin') != settings.public_url or request.headers.get('x-paperweek-request') != '1':
                return JSONResponse({'detail':'Same-origin application request required.'}, status_code=403, headers={'Cache-Control':'no-store'})
            if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail':'JSON required.'}, status_code=415)
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 65536:
                    return JSONResponse({'detail':'Request too large.'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)  # CachedRequest replays this downstream.
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
            "img-src 'self' data: blob:; connect-src 'self'; worker-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if request.url.path.startswith('/api/') or request.url.path in ('/', '/admin', '/sw.js'):
            response.headers['Cache-Control'] = 'no-store'
        else:
            response.headers.setdefault('Cache-Control', 'no-cache')
        return response

    @app.exception_handler(RequestValidationError)
    async def bad_body(request, exc):
        return JSONResponse({'detail':'Invalid request fields.', 'errors':[
            {'field':'.'.join(map(str, e['loc'])), 'message':e['msg']} for e in exc.errors()
        ]}, status_code=422, headers={'Cache-Control':'no-store'})

    @app.exception_handler(CalendarError)
    async def google_error(request, exc):
        return JSONResponse({'detail':str(exc), 'kind':exc.kind}, status_code=503, headers={'Cache-Control':'no-store'})

    def limited(request, label, maximum=10, seconds=900):
        # NPM commonly shares one source IP. Do not trust arbitrary forwarded
        # headers; the generous action limits work for a single household.
        ip = request.client.host if request.client else 'local'
        app.state.limiter.check((label, ip), maximum, seconds)

    @app.get('/healthz')
    def health():
        app.state.store.rows('SELECT 1')
        return {'status':'running', 'version':__version__}

    @app.get('/api/meta')
    def meta():
        return {'backend':True, 'version':__version__}

    @app.get('/api/session')
    def who(request: Request):
        row = session(request)
        return {'role':row['role'], 'label':row['label'], 'expires':row['expires']}

    @app.post('/api/admin/login')
    async def login(body: Login, request: Request):
        limited(request, 'login')
        # Password KDF runs in a worker thread so it cannot block synchronization.
        from starlette.concurrency import run_in_threadpool
        good = await run_in_threadpool(password_ok, body.password, settings.admin_hash)
        if not good:
            raise HTTPException(401, 'Invalid administrator password.')
        old = request.cookies.get(COOKIE)
        if old:
            app.state.store.execute('DELETE FROM sessions WHERE digest=?', (digest(old),))
        response = JSONResponse({'ok':True})
        new_session(app.state.store, response, settings, 'admin', 'Administrator', 0.5)
        return response

    @app.post('/api/logout')
    def logout(request: Request):
        row = session(request)
        app.state.store.execute('DELETE FROM sessions WHERE digest=?', (row['digest'],))
        response = JSONResponse({'ok':True})
        response.delete_cookie(COOKIE, path='/', secure=settings.secure, httponly=True, samesite='lax')
        return response

    @app.post('/api/admin/pairings')
    def create_pair(body: PairCreate, request: Request):
        session(request, admin=True)
        limited(request, 'create-pair', 30, 3600)
        alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        code = ''.join(secrets.choice(alphabet) for _ in range(8))
        app.state.store.execute('INSERT INTO pairs VALUES(?,?,?,?)', (digest(code), body.label.strip(), time.time()+600, body.days))
        return {'code':code[:4]+'-'+code[4:], 'expiresIn':600, 'days':body.days}

    @app.post('/api/pair')
    def redeem_pair(body: PairRedeem, request: Request):
        limited(request, 'redeem-pair')
        code = body.code.replace('-', '').replace(' ', '').upper()
        row = app.state.store.consume('pairs', digest(code), time.time())
        if not row:
            raise HTTPException(400, 'Pairing code is incorrect, expired or already used.')
        old = request.cookies.get(COOKIE)
        if old:
            app.state.store.execute('DELETE FROM sessions WHERE digest=?', (digest(old),))
        response = JSONResponse({'ok':True})
        new_session(app.state.store, response, settings, 'display', row['label'], row['days'])
        return response

    @app.get('/api/admin/devices')
    def devices(request: Request):
        session(request, admin=True)
        return app.state.store.rows("SELECT digest AS id,label,created,expires,last_seen AS lastSeen FROM sessions WHERE role='display' AND expires>?", (time.time(),))

    @app.delete('/api/admin/devices/{device_id}')
    def revoke_device(device_id: str, request: Request):
        session(request, admin=True)
        app.state.store.execute("DELETE FROM sessions WHERE digest=? AND role='display'", (device_id,))
        return {'ok':True}

    @app.get('/api/admin/config')
    def admin_config(request: Request):
        session(request, admin=True)
        config, revision = app.state.store.config_record()
        return {'config':config.model_dump(), 'revision':revision}

    @app.put('/api/admin/config')
    def put_config(body: ConfigUpdate, request: Request):
        session(request, admin=True)
        if body.config.source == 'google':
            choices = {c['id'] for c in app.state.store.get('calendar_choices', [])}
            old = {m.calendarId for m in app.state.store.config().members}
            if any(m.calendarId not in choices | old for m in body.config.members):
                raise HTTPException(422, 'Load calendar choices and map every calendar before saving.')
        try:
            revision = app.state.store.save_config(body.config, body.revision)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None
        app.state.sync.wake.set()
        return {'revision':revision, 'config':body.config.model_dump()}

    @app.get('/api/admin/status')
    def status(request: Request):
        session(request, admin=True)
        return app.state.sync.status()

    @app.post('/api/admin/sync')
    def manual_sync(request: Request):
        session(request, admin=True)
        limited(request, 'sync', 2, 60)
        app.state.sync.request_sync()
        return JSONResponse({'queued':True}, status_code=202)

    @app.get('/api/admin/calendars')
    async def calendars(request: Request):
        session(request, admin=True)
        limited(request, 'list-calendars', 6, 60)
        return {'calendars':await app.state.google.calendars()}

    @app.post('/api/admin/google/connect')
    def connect(request: Request):
        row = session(request, admin=True)
        limited(request, 'oauth-start', 10, 3600)
        return {'url':app.state.google.start(row['digest'])}

    @app.get('/api/oauth/callback')
    async def callback(request: Request):
        row = session(request, admin=True)
        try:
            await app.state.google.finish(row['digest'], request.query_params)
            app.state.sync.wake.set()
            # A scope/account switch can make old mappings invalid. Never guess.
            try:
                await app.state.google.calendars()
            except CalendarError:
                app.state.store.set('oauth_notice', 'Connected; load calendar choices when Google is reachable.')
            response = RedirectResponse('/admin?google=connected', status_code=303)
        except CalendarError as e:
            # Never echo code, state, token response, account identifiers or raw
            # exception details in the callback URL or logs.
            app.state.store.set('oauth_notice', str(e))
            response = RedirectResponse('/admin?google=attention', status_code=303)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/admin/google/disconnect')
    async def disconnect(request: Request):
        session(request, admin=True)
        await app.state.google.disconnect()
        return {'ok':True, 'message':'Server credentials and cached events removed. Google consent was not revoked.'}

    @app.get('/api/display/config')
    def display_config(request: Request):
        session(request)
        config, revision = app.state.store.config_record()
        return {'config':config.public(), 'revision':revision, 'dataEpoch':app.state.google.generation}

    @app.get('/api/display/snapshot')
    def snapshot(request: Request, first: date, days: int = 42):
        session(request)
        if not 1 <= days <= 62:
            raise HTTPException(422, 'Request 1–62 days.')
        try:
            result = app.state.sync.snapshot(first, days)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        result['serverTime'] = time.time()
        return JSONResponse(result, status_code=200 if result['ready'] else 202)

    def file(name):
        target = settings.site_dir / name
        if not target.is_file():
            raise HTTPException(404, 'Asset not found. Build the browser preview first.')
        media = {'wasm':'application/wasm', 'mjs':'text/javascript', 'webmanifest':'application/manifest+json'}.get(target.suffix[1:])
        return FileResponse(target, media_type=media)

    @app.get('/')
    @app.get('/index.html')
    def root():
        return file('server.html')

    @app.get('/admin')
    def admin_page():
        return file('admin.html')

    @app.get('/{asset:path}')
    def assets(asset: str):
        if asset not in PUBLIC_ASSETS:
            raise HTTPException(404, 'Not found.')
        return file(asset)

    return app
