# Unattended backend: deployment and operation

## Scope

Version 0.4 is a single-household, private-LAN/VPN service. It synchronises selected calendars with
read-only Google access, stores shared settings and serves paired displays. It keeps the existing
portable C calendar engine and layout. It is not an OCR importer, event editor or finished e-paper
firmware. No GPU or permanently running Mac is needed.

Use a Linux Docker host and Docker Compose v2, local DNS and a trusted HTTPS reverse proxy. The
hostname examples below are intentionally generic. Keep real configuration out of the public repo.
The backend is a **single process/one Uvicorn worker**: scheduler, token-refresh lock and rate limits
are in-process. Do not scale workers or run a second writer against the same database.

## 1. Back up the old browser settings

Before upgrading, use the v0.3 UI's **Export private settings**. Save that JSON outside the repository.
It contains names/calendar IDs, not a portable Google refresh credential. Its old browser token does
not migrate to the server. The server accepts the v3 settings format and ignores the old client ID.

Changing hosts/origins does not automatically transfer localStorage, cookies or installed apps.

## 2. Google configuration

In Google Cloud select the intended project and enable **Google Calendar API**. Configure Google
Auth platform branding/audience. For a private Workspace application, use **Internal** if the project
belongs to the Workspace organisation and only that organisation's accounts need authorising it.
External apps can be used, but an External app in Testing normally has seven-day refresh tokens for
Calendar scopes. Internal is not a promise that tokens can never be revoked.

Create a **Web application** client named, for example, `Paperweek server`. A separate client from
the existing browser prototype is recommended to leave the old deployment intact during migration.

Register this exact **Authorized redirect URI**, replacing the origin:

```text
https://paperweek.example.net/api/oauth/callback
```

The backend uses a server redirect callback, not the legacy popup token flow. An Authorized
JavaScript origin alone is insufficient. No redirect URI wildcard or arbitrary LAN IP is used.
For the backend, you do not need a browser API key. The client secret belongs only on the server.

The application requests exactly these scopes:

```text
https://www.googleapis.com/auth/calendar.events.readonly
https://www.googleapis.com/auth/calendar.calendarlist.readonly
```

Configure the corresponding data-access permissions in the consent configuration when required.
The signed-in account must already have permission to read the calendars. Newly created calendars
can be discovered using **Load calendar choices**, without creating a new OAuth client.

Download the **Web application client JSON** and transfer it privately to the Linux guest. Do not
paste its secret into the Paperweek frontend, an issue, a screenshot or the repository. If a download
is no longer available in the console, create a new Web client and retain its downloaded credentials.

Google redirects the administrator's browser back to the private HTTPS hostname. The browser must
have LAN/VPN access and working local DNS. No incoming Google webhook is required: synchronization
uses outgoing requests. The host must reach Google's authorisation/token/Calendar endpoints.

## 3. Generate private configuration

In a fresh extracted or checked-out project folder:

```sh
python3 tools/configure_backend.py \
  --public-url https://paperweek.example.net \
  --google-client /private/path/web-client.json
```

Python 3.10+ on the host is sufficient for this script; runtime dependencies are installed inside the
container. It generates a random administrator password, a scrypt hash, a Fernet encryption key and
private Google client configuration. **Save the printed password in your password manager.**

The files `.env` and `.env.private` are ignored by Git and written with mode 0600. The downloaded
client JSON should remain outside the repository/build context. Docker administrators can read
container environment variables; encryption does not protect against a compromised host.

To try demo mode first, omit `--google-client`. Add the JSON later by rerunning the command. Reruns
preserve the existing password hash and encryption key. Recreate the container after changes.

To reset only the administrator password:

```sh
python3 tools/configure_backend.py --public-url https://paperweek.example.net --reset-admin
```

This preserves the encryption key and Google client, and invalidates previous administrator
sessions on the next start. It does not revoke paired display sessions. `--prompt-password` permits
a chosen password of at least 14 characters. Never delete the encryption key to reset a password.

## 4. Choose one networking overlay

### NPM on the same Docker engine

Find a network NPM already uses:

```sh
docker inspect YOUR_NPM_CONTAINER --format '{{json .NetworkSettings.Networks}}'
```

Set `NPM_NETWORK` in `.env` to the existing network name, then:

```sh
docker compose -f compose.yml -f compose.npm.yml config --quiet
docker compose -f compose.yml -f compose.npm.yml up -d --build
docker compose -f compose.yml -f compose.npm.yml ps
```

`config --quiet` validates without printing resolved secrets. Ordinary `docker compose config`
prints environment values: do not paste its output into public issues. No host port is published
in this mode. NPM reaches `paperweek:8080` through the shared Docker network.

### NPM on another host/VM

Set `PAPERWEEK_BIND_IP` to the Docker guest's private IPv4 address and `PAPERWEEK_HOST_PORT=8080`
(or an unused port) in `.env`, then:

```sh
docker compose -f compose.yml -f compose.lan.yml config --quiet
docker compose -f compose.yml -f compose.lan.yml up -d --build
```

The default bind is loopback-only and will not work from a separate NPM host. Restrict the published
port to NPM using your network/Docker firewall. Do not forward this port from the internet. Avoid
publicly exposing the experimental service even though it includes authentication.

### Resources and build

The image compiles its own lightweight C/WASM preview from source, then runs Python/FastAPI as a
non-root user. It uses a read-only root filesystem, a writable private volume and a temporary
filesystem. Compose limits the runtime to 512 MB and one CPU as starting bounds, not benchmarked
capacity guarantees. Building requires registry, Debian package and PyPI access. Base-image updates
are not fully pinned; set `PYTHON_IMAGE` to a reviewed digest when reproducibility is required.

The `paperweek-data` named volume is created with the image's data-directory ownership. Existing
custom volumes/bind mounts must be writable by UID/GID 10001. Check the startup log for errors.

## 5. Configure NPM

| Setting | Value |
| --- | --- |
| Domain | Your hostname, matching `PAPERWEEK_PUBLIC_URL` exactly |
| Forward scheme | `http` |
| Forward hostname/IP | `paperweek` on the shared network, otherwise the Docker guest's private IP |
| Forward port | `8080` internally, or the chosen published port |
| SSL certificate | Trusted certificate covering the hostname |
| Force SSL | On |
| Cache Assets | **Off** |
| Websockets | Off; not used |
| Advanced configuration | Empty for this setup |
| Access restrictions | Existing trusted LAN/VPN policy |

Local DNS must resolve the public-facing hostname to NPM, not directly to the container. NPM must
preserve the original Host header. The backend uses the configured origin, not forwarded headers,
for cookies, callback URLs and CSRF checks. Do not inject a second incompatible CSP at the proxy.
An extra HTTP-basic-auth access list is not required by Paperweek and may complicate tablet setup;
LAN/IP restrictions can still be used. Protect any NPM access logs: OAuth callback requests can
contain short-lived authorisation codes in query strings. The app disables Uvicorn access logging.

## 6. First start and migration

Open `https://paperweek.example.net/admin` **directly**, rather than the old root page. Sign in with
the generated administrator password. An old static service worker may temporarily keep serving
the previous display UI; `/admin` bypasses that old route and registers the new worker. Close old
tabs and reopen the site. If necessary, after saving old settings, unregister the previous service
worker / clear that site's cached application data in the browser. Do not clear the new server volume.

In Administration:

1. Click **Connect / reconnect Google**, select the intended Workspace account and approve the
   read-only access. The server obtains offline access using its authorisation-code flow. Reconnection
   deliberately requests consent so a refresh credential can be obtained.
2. Use **Load calendar choices** if not already populated. Import the old private settings, or add
   and label members. Map each member to its actual Google calendar. Choose timezone and rota member.
3. Set data source to **My Google calendars** and **Save shared settings**. Use **Synchronise now**.
   The health table initially fills as the current/nearby months are retrieved.
4. Under **Pair your tablet**, choose a label/session duration and create a one-use code.

Pairing codes expire after ten minutes. Read-only display sessions may last 1–365 days; administrator
sessions last 12 hours. On the tablet, open the root site `/` and enter the pairing code. Do not use
an administrator session as the permanent wall display. Every display session is independently
revocable in Administration. Cookie expiry/clearing requires re-pairing, not reauthorising Google.

Chrome may offer installation / Add to home screen over HTTPS. **Keep awake** is opt-in and depends
on browser support, the page remaining visible and device power policy. Configure power/battery
settings yourself. The app is not an Android kiosk/device-owner package and does not automatically
launch after a reboot. Fullscreen, PWA installation and physical-device behaviour need local testing.

## 7. Cache and synchronization behaviour

Google remains the source of truth. Default polling is five minutes, configurable from 1–60. The
browser checks the local API roughly every 20 seconds while visible. These are polling targets,
not latency guarantees. Worker heartbeats and per-calendar/month success/error state are visible.

The previous, current and next two months are warmed. Other periods within two years either side
are queued when a display requests them; requested windows remain warm for seven days after use.
Google queries expand recurrences and paginate; deleted/cancelled entries disappear only after a
successful full-window replacement. A failed page does not partially replace a saved window.

Each display range is 1–62 days. The server caps provider pages and event counts; an over-capacity
calendar raises an error rather than silently truncating. Single displayed datasets are bounded to
2,048 entries. Filter/partition extremely busy calendars before using this household-scale prototype.

A snapshot is complete only when all selected calendar/month windows have data. Until then the UI
shows loading or retains its previous view. Browsing an uncached month offline does not create an
empty month. Cached but stale data is served with a warning. Errors back off; invalid refresh grants
become an explicit reconnect-required state. UTC offsets and IANA zones are validated; Google timed
entries without an offset are treated as invalid rather than guessed.

Status words on a physical e-paper screen would eventually require a redraw when they change,
but a poll with identical visible content does not redraw merely for a timestamp. The tablet's
status line can update without re-rendering the C calendar framebuffer.

### Optional tablet offline copy

Under **Text agenda & this device**, enable storing the last complete view only on a trusted tablet.
This is **unencrypted localStorage**, not an encrypted vault. It holds at most one displayed view
and expires after seven days or the session expiry, whichever is sooner. No Google token is stored
in it. The service worker caches only public app assets, never API responses or OAuth URLs.

An online display receiving a revoked/expired session clears its private copy. A disconnected device
cannot receive a revocation immediately; it can retain the copy until local expiry or manual removal.
The public application shell may still be cached when private offline copying is disabled.

## 8. Backup, update and restore

The database contains private settings, event data and hashed display sessions; Google credentials
are encrypted with the key in `.env.private`. Back up both, encrypt the backup destination and keep
it outside your public repository.

Consistent live SQLite export, using the overlay for your deployment:

```sh
umask 077
mkdir -p /private/backup/location
docker compose -f compose.yml -f compose.npm.yml exec -T paperweek \
  python -m backend.backup > /private/backup/location/paperweek-backup.private.sqlite3
cp .env.private /private/backup/location/runtime.private.env
```

A copied SQLite main file without its active WAL is not a reliable live backup. Use the backup
command. The private key is deliberately not included in that stdout export.

Before upgrades, back up, retain `.env`/`.env.private` and the volume, replace/update public source,
and rebuild/recreate with the same Compose project name. **Do not use `docker compose down -v`.**
Changing the project name can create a new empty volume, which looks like a lost setup.

To restore: stop the app, replace the volume's `paperweek.sqlite3` with the consistent backup, remove
old WAL/SHM files while stopped, preserve UID/GID 10001 ownership, restore the original encryption key
and private configuration, and start again. The schema version is checked; there is no automatic
migration from an unrelated application database. Restoring an older database also restores the
then-valid display sessions: review/revoke them after restoration.

Lost key: saved refresh credentials cannot be decrypted. Preserve/export the data separately, create
new private storage/key, and reauthorise Google rather than attempting to change the key in-place.
The application intentionally refuses a database encrypted under a different key.

## 9. Smoke checks and troubleshooting

```sh
python3 tools/backend_smoke.py --url https://paperweek.example.net
```

This checks the public shell, health and unauthenticated API boundary; it is not a Google integration
or security audit. Container health means the app/database are running, **not** that calendars are fresh.
Check the administration health table too.

- **502:** NPM cannot reach the container; check shared network/private IP, port, health and logs.
- **403 on login/save:** exact browser origin must match `PAPERWEEK_PUBLIC_URL`; keep JSON and the app's
  anti-CSRF header. Never disable origin validation as a workaround.
- **OAuth redirect mismatch:** register `/api/oauth/callback` exactly in the Web client; use the right
  scheme, hostname and client. JS-origin configuration is not the callback setting.
- **Connected but blank:** choose Google data source, map every member, save, and inspect per-month
  health. The display does not automatically switch from demo on authorisation alone.
- **Access blocked / 403 from Google:** check API enablement, requested scopes, Workspace admin policy,
  chosen account and calendar sharing. Read-only/free-busy-only sharing may not expose details.
- **Old UI:** visit `/admin` directly, update/remove the old service worker after exporting settings.
- **Wrong key:** restore the matching private key/volume pair; do not delete the database casually.
- **Unauthenticated tablet after reset:** cookies were cleared/expired; generate another pairing code.

## 10. Validation boundary

See [TESTING.md](TESTING.md). Real HTTP/API and component browser tests used mocked Google responses.
No live OAuth grant, user calendars, physical Android device, TLS proxy or Docker daemon was available
in the release environment. No hardware or cloud service has been configured on your behalf.

## Primary references

- [Google server-side OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google token expiry and testing restrictions](https://developers.google.com/identity/protocols/oauth2)
- [Workspace OAuth consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent)
- [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth)
- [Calendar events.list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
- [NPM shared Docker networks](https://nginxproxymanager.com/advanced-config/)
- [FastAPI container deployment](https://fastapi.tiangolo.com/deployment/docker/)
- [Fernet key management](https://cryptography.io/en/latest/fernet/)
