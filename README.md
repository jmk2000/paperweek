# Paperweek

A configurable shared calendar for an Android tablet now and a colour e-paper display later.
**v0.5 adds multiple Google/iCalendar sources per person to the unattended backend.** The portable C calendar rules and
week/month layout are retained; the tablet no longer manages Google authorisation.

**Experimental single-household release.** The backend and compiled C/WASM preview have local
automated tests. Real Google/iCalendar providers, an Android device, Docker image build and NPM deployment
have not been exercised in the release environment. This is not finished ESP32 firmware.

## What is included

- Server-side Google OAuth with encrypted refresh credentials, scheduled read-only synchronisation,
  paginated recurring-event retrieval, retry/backoff and a persistent SQLite cache.
- A browser administration screen for shared configuration, Google connection and sync health.
- One-use tablet pairing codes and independently revocable read-only display sessions. Google
  credentials and calendar IDs are not sent to paired displays.
- One to six configurable people/display groups, with up to 24 additional sources. A person can
  have Google appointments and an independent iCalendar work feed without another display slot.
- Private subscription URLs, isolated bounded recurrence parsing, per-source health, preview and
  explicit rota rules; feeds can be appointments or status-band-only.
- Generic demo data; week/month views; previous/next/today;
  one optional rota band; privacy masking; six-colour design palette; physical-button simulation.
- The actual existing C model and layout compiled to WebAssembly. The supplied preview uses
  browser fonts, **not an LVGL framebuffer**. The separate LVGL build target remains available.
- Opt-in, bounded private offline storage for the last complete tablet view; optional wake lock,
  full-screen controls, a service worker and a home-screen app manifest.
- Docker Compose deployment behind an existing HTTPS reverse proxy. No GPU is needed.

## Start with Docker and Nginx Proxy Manager

The image now compiles its own WASM assets: a clean Git clone is sufficient. No build output,
credentials or household settings need committing.

1. Create a Google **Web application** OAuth client with Calendar API enabled and the two read-only
   scopes described in [the backend guide](docs/BACKEND.md). Register the exact callback
   `https://paperweek.example.net/api/oauth/callback`. Keep the downloaded client JSON private.
2. In the repository, generate private runtime configuration:

   ```sh
   python3 tools/configure_backend.py \
     --public-url https://paperweek.example.net \
     --google-client /private/path/web-client.json
   ```

   Save the generated administrator password in your password manager. The script writes ignored,
   permission-restricted `.env` and `.env.private` files. The public example hostname must be
   replaced with your own LAN-resolvable HTTPS hostname. Omit `--google-client` to try demo mode first.
3. For NPM on the same Docker engine, set `NPM_NETWORK` in `.env` to its existing network, then:

   ```sh
   docker compose -f compose.yml -f compose.npm.yml up -d --build
   ```

   For NPM on another host/VM, use `compose.lan.yml` instead and explicitly set the guest's private
   bind IP and port in `.env`. Restrict that port to the proxy.
4. Point NPM at `paperweek:8080` on the shared Docker network, or at the guest IP/port. Use HTTP to
   the container, trusted HTTPS to browsers, **Cache Assets off**, and no custom Advanced headers.
5. Visit `/admin`, sign in, configure people and choose **Live calendars · Google + iCalendar**.
   Connect Google for Google sources, or add iCalendar sources without a Google account. Existing private v0.3 settings exports can be imported. Create a pairing code, then enter
   it at `/` on the tablet. The tablet does not need your administrator password or Google sign-in.

See **[People, calendar sources and rota subscriptions](docs/CALENDAR_SOURCES.md)** for the new editor.
See **[complete deployment, migration and backup instructions](docs/BACKEND.md)** before upgrading.
An old service worker can temporarily show the legacy UI: export old settings first, then visit
`/admin` directly at the new deployment and close/reopen the old display tab.

## What “unattended” means

Google access tokens are renewed by the backend using its refresh credential. The default Google
poll interval is five minutes. The tablet checks the local service roughly every 20 seconds while
visible. Unchanged calendar content does not force a display redraw. Temporary errors retain the
last complete data and show stale status; missing cache coverage is not presented as an empty month.

The service warms the previous month, current month and next two months. Other requested periods
within approximately two years either side are queued on demand. A first load can take a minute;
large calendars and provider limits can take longer. All enabled sources/months must be available
before a complete snapshot is delivered. Caches are a working copy; The configured providers remain authoritative.

Revocation, expired refresh credentials and Workspace policy changes can still require an
administrator to reconnect. A backend cannot force Android to restart a browser after reboot,
keep a sleeping tablet online or guarantee a reminder. See [limits and tests](docs/TESTING.md).

## Rota markers

For a subscribed rota, attach the feed to the existing person, select **Rota band only** and review
explicit matching rules in the source preview. Keep that person's personal Google calendar in
place. You do not need to copy shifts into Google or add another person.

Choose a tracked member in Administration. Create ordinary events in that calendar with prefixes:

```text
[PW:WORK] Day shift
[PW:ONCALL] On-call shift
[PW:OFF] Off duty
```

Work/on-call may be timed or all-day; OFF must be all-day. On-call implies working. An overlapping
work/off day is a conflict; missing information is unknown, not off. Weekends are treated normally.
The shared C code turns these records into the rota band instead of ordinary appointments. Overnight
shifts affect every day actually overlapped; an exclusive midnight end does not include the next day.
The **status** remains visible even if the underlying shift's descriptive title is privacy-masked.

## Source reuse and boundaries

```text
Google + iCalendar -> private Python backend -> bounded, privacy-filtered event data
                                      |
                           shared JS timezone adapter
                                      |
                       C rules + C week/month layout
                                      |
                      browser preview OR LVGL backend
```

The default Docker build is the dependency-light **C/WASM/browser-font preview**, compiled and
labelled as such. `ui/canvas_lvgl.c` and the Emscripten build are supplied, but a complete LVGL build
was not verified for this release. The ESP32 still needs device authentication, a network adapter,
LVGL/panel integration, colour conversion, memory/power configuration and physical input wiring.

This release does **not** include photograph/OCR import, direct event creation, voice integration,
multiple separate households, push notifications from Google or an Internet-exposed multi-tenant
service. Those should not be confused with unattended read-only synchronisation.

## Development and testing

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest tests/backend -q
bash tools/build-preview.sh              # LLVM clang + wasm-ld required
node --test tests/*.test.mjs             # Node 22+
cmake -S . -B build/core -DCMAKE_BUILD_TYPE=Release
cmake --build build/core
ctest --test-dir build/core --output-on-failure
python3 tools/privacy_check.py
```

[Testing](docs/TESTING.md) documents the local API/UI checks, their mocked external boundaries and
what remains unverified. The backend CI workflow adds a clean Docker build; no workflow publishes
or deploys a server automatically. Static GitHub Pages is only a legacy frontend demonstration.

For the older standalone browser and LVGL toolchains, see [legacy static documentation](docs/LEGACY_STATIC.md).

## Privacy, backups and licence

Public defaults are generic. Runtime configuration, event data, tokens and device sessions live in
private files/volumes, not source. Google credentials, subscription URLs and raw feeds are encrypted at rest; cached events and
settings in SQLite are not. Read [SECURITY.md](SECURITY.md), protect the host/backups, and never
commit `.env.private`, photos, exported settings or your database.

Back up **both** the consistent database export and `.env.private`; the encryption key cannot be
recovered from source. Do not remove the data volume during upgrades.

Paperweek code is MIT licensed. Keep [third-party notices](docs/THIRD_PARTY.md) with distributions.
No endorsement by Google, LVGL or a hardware vendor is implied. Do not rely on a prototype display
as the sole reminder for critical commitments.
