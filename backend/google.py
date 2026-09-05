"""Google's read-only Calendar API and offline web OAuth.

OAuthlib constructs/parses OAuth messages; HTTPX provides bounded HTTPS I/O.
No Google endpoint, redirect URL or scope is supplied by an untrusted browser.
"""
from __future__ import annotations
import asyncio
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode, quote
import httpx
from oauthlib.oauth2 import WebApplicationClient, OAuth2Error
from .security import digest
from .storage import dumps

SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly',
          'https://www.googleapis.com/auth/calendar.calendarlist.readonly']
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
API_URL = 'https://www.googleapis.com/calendar/v3/'


class CalendarError(Exception):
    def __init__(self, kind, message, retry_after=0):
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


def retry_after(response):
    value = response.headers.get('retry-after', '')
    try:
        seconds = int(value)
    except ValueError:
        try:
            seconds = int(parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            seconds = 0
    return max(0, min(seconds, 86400))


class Google:
    def __init__(self, store, settings, client):
        self.store, self.settings, self.client = store, settings, client
        self.lock = asyncio.Lock()
        self.generation = int(store.get('google_generation', 0))

    @property
    def configured(self):
        return bool(self.settings.client_id and self.settings.client_secret)

    @property
    def connection(self):
        return self.store.get('google_status', 'disconnected')

    def start(self, admin_session):
        if not self.configured:
            raise CalendarError('config', 'Install the Web application client credentials on the server first.')
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        payload = self.store.cipher.encrypt(dumps({'verifier':verifier}).encode()).decode()
        self.store.execute('DELETE FROM oauth_states WHERE session=?', (admin_session,))
        self.store.execute('INSERT INTO oauth_states VALUES(?,?,?,?)', (digest(state), admin_session, payload, time.time()+600))
        return WebApplicationClient(self.settings.client_id).prepare_request_uri(
            AUTH_URL, redirect_uri=self.settings.callback_url, scope=SCOPES, state=state,
            code_challenge=challenge, code_challenge_method='S256', access_type='offline',
            prompt='consent', include_granted_scopes='true')

    async def token_request(self, body):
        try:
            response = await self.client.post(TOKEN_URL, content=body,
                headers={'Content-Type':'application/x-www-form-urlencoded', 'Accept':'application/json'})
        except httpx.HTTPError:
            raise CalendarError('network', 'Google could not be reached. Saved data is retained.') from None
        if len(response.content) > 131072:
            raise CalendarError('response', 'Unexpected Google token response.')
        if response.status_code >= 500 or response.status_code == 429:
            raise CalendarError('temporary', 'Google is temporarily unavailable.', retry_after(response))
        try:
            payload = response.json()
        except ValueError:
            raise CalendarError('response', 'Unexpected Google token response.') from None
        if payload.get('error') == 'invalid_grant':
            raise CalendarError('reauth', 'Google reconnection required.')
        if payload.get('error') in ('invalid_client', 'unauthorized_client'):
            raise CalendarError('config', 'Google rejected the server client credentials. Check private configuration.')
        if not response.is_success:
            raise CalendarError('oauth', 'Google authorisation failed. Check the client and retry sign-in.')
        try:
            # Parse standard OAuth errors and token metadata via OAuthlib.
            result = WebApplicationClient(self.settings.client_id).parse_request_body_response(response.text)
            lifetime = int(result.get('expires_in', 3600))
            if not result.get('access_token') or not 0 < lifetime <= 86400:
                raise ValueError('invalid token')
            granted = result.get('scope')
            if granted and not set(SCOPES).issubset(set(granted if isinstance(granted, list) else granted.split())):
                raise CalendarError('scope', 'Both read-only Calendar permissions must be approved.')
            result['expires_at'] = time.time() + lifetime
            return result
        except (OAuth2Error, ValueError, TypeError, Warning):
            raise CalendarError('oauth', 'Google returned an invalid authorisation response.') from None

    async def finish(self, admin_session, query):
        states = query.getlist('state') if hasattr(query, 'getlist') else [query.get('state', '')]
        codes = query.getlist('code') if hasattr(query, 'getlist') else [query.get('code', '')]
        if len(states) != 1 or len(states[0]) > 512 or len(codes) > 1:
            raise CalendarError('state', 'Invalid or expired Google sign-in. Start again from administration.')
        row = self.store.consume('oauth_states', digest(states[0]), time.time(), admin_session)
        if not row:
            raise CalendarError('state', 'Invalid or expired Google sign-in. Start again from administration.')
        if query.get('error'):
            raise CalendarError('cancelled', 'Google sign-in was not completed. Existing data has not changed.')
        if not codes or not codes[0] or len(codes[0]) > 8192:
            raise CalendarError('oauth', 'Google did not return an authorisation code.')
        verifier = json.loads(self.store.cipher.decrypt(row['payload'].encode()))['verifier']
        body = WebApplicationClient(self.settings.client_id).prepare_request_body(
            code=codes[0], redirect_uri=self.settings.callback_url,
            code_verifier=verifier, client_secret=self.settings.client_secret)
        async with self.lock:
            token = await self.token_request(body)
            # Do not combine a new account's access token with an old refresh token.
            if not token.get('refresh_token'):
                raise CalendarError('refresh', 'Google did not grant offline access. Reconnect and approve consent.')
            self.generation += 1
            self.store.set_secret('google_token', token)
            self.store.set('google_status', 'connected')
            self.store.set('google_generation', self.generation)
            self.store.delete('calendar_choices')
            self.store.clear_google_windows()
            self.store.delete('oauth_notice')

    async def access_token(self, force=False):
        async with self.lock:
            token = self.store.get_secret('google_token')
            if not token or self.connection in ('disconnected', 'reconnect_required', 'configuration_error'):
                raise CalendarError('reauth', 'Google reconnection required.')
            if not force and token.get('expires_at', 0) > time.time() + 90:
                return token['access_token']
            body = urlencode({'grant_type':'refresh_token', 'refresh_token':token['refresh_token'],
                              'client_id':self.settings.client_id, 'client_secret':self.settings.client_secret})
            try:
                refreshed = await self.token_request(body)
            except CalendarError as error:
                if error.kind in ('reauth', 'config'):
                    self.store.set('google_status', 'reconnect_required' if error.kind == 'reauth' else 'configuration_error')
                raise
            refreshed['refresh_token'] = refreshed.get('refresh_token') or token['refresh_token']
            self.store.set_secret('google_token', refreshed)
            self.store.set('google_status', 'connected')
            return refreshed['access_token']

    async def request(self, path, params):
        # All callers pass hardcoded paths plus quoted calendar IDs.
        if path.startswith('/') or '..' in path.split('/') or '://' in path:
            raise CalendarError('path', 'Invalid Calendar API path.')
        for attempt in range(2):
            token = await self.access_token(force=attempt == 1)
            try:
                response = await self.client.get(API_URL + path, params=params,
                    headers={'Authorization':f'Bearer {token}', 'Accept':'application/json'})
            except httpx.HTTPError:
                raise CalendarError('network', 'Google could not be reached. Saved data is retained.') from None
            if response.status_code == 401 and attempt == 0:
                continue
            if response.status_code == 401:
                self.store.set('google_status', 'reconnect_required')
                raise CalendarError('reauth', 'Google reconnection required.')
            if response.status_code == 429 or response.status_code >= 500:
                raise CalendarError('temporary', 'Google temporarily unavailable or rate-limited.', retry_after(response))
            if response.status_code == 403:
                try:
                    reasons = {e.get('reason') for e in response.json().get('error', {}).get('errors', [])}
                except (ValueError, TypeError, AttributeError):
                    reasons = set()
                if reasons & {'rateLimitExceeded','userRateLimitExceeded','quotaExceeded','dailyLimitExceeded'}:
                    raise CalendarError('quota', 'Google Calendar quota limit; retry scheduled.', max(900, retry_after(response)))
                raise CalendarError('access', 'Google denied calendar access. Check sharing, API enablement and Workspace policy.')
            if response.status_code == 404:
                raise CalendarError('access', 'Calendar not found or no longer shared with this account.')
            if not response.is_success or len(response.content) > 8_000_000:
                raise CalendarError('response', 'Invalid Calendar response; previous data retained.')
            try:
                data = response.json()
                if not isinstance(data, dict) or not isinstance(data.get('items', []), list):
                    raise ValueError()
                return data
            except ValueError:
                raise CalendarError('response', 'Invalid Calendar response; previous data retained.') from None
        raise CalendarError('reauth', 'Google reconnection required.')

    async def pages(self, path, params, max_items=6000):
        results, seen = [], set()
        token = None
        for _ in range(40):
            page = await self.request(path, {**params, **({'pageToken':token} if token else {})})
            results.extend(page.get('items', []))
            if len(results) > max_items:
                raise CalendarError('limit', 'Calendar range exceeds the safety limit; no partial data was saved.')
            token = page.get('nextPageToken')
            if not token:
                return results
            if not isinstance(token, str) or token in seen:
                break
            seen.add(token)
        raise CalendarError('pagination', 'Google pagination did not complete; previous data retained.')

    async def calendars(self):
        generation = self.generation
        rows = await self.pages('users/me/calendarList', {'maxResults':250, 'showHidden':'true'}, max_items=1000)
        result = [{'id':str(r['id']), 'label':str(r.get('summaryOverride') or r.get('summary') or 'Calendar')[:250]}
                  for r in rows if r.get('id') and r.get('accessRole') in ('owner','writer','reader','writerWithoutPrivateAccess')]
        if self.generation != generation:
            raise CalendarError('changed', 'Google account changed during the request. Retry.')
        self.store.set('calendar_choices', result)
        return result

    async def events(self, calendar_id, start, end, zone):
        return await self.pages('calendars/' + quote(calendar_id, safe='') + '/events', {
            'timeMin':start, 'timeMax':end, 'singleEvents':'true', 'orderBy':'startTime',
            'showDeleted':'false', 'maxResults':250, 'timeZone':zone,
            'fields':'nextPageToken,items(id,iCalUID,summary,status,visibility,start,end,attendees(self,responseStatus))',
        })

    async def disconnect(self):
        # Local disconnection, not provider-wide revocation of other deployments.
        async with self.lock:
            self.generation += 1
            self.store.set('google_generation', self.generation)
            self.store.delete('google_token')
            self.store.set('google_status', 'disconnected')
            self.store.delete('calendar_choices')
            self.store.clear_google_windows()
            self.store.execute('DELETE FROM oauth_states')
