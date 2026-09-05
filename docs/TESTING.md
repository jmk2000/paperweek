# Release validation — v0.5.0

Recorded on 2026-09-05. These are local release tests, not evidence of deployment into a real
household. No private calendar account, domain configuration or Google credential was used.

## Executed successfully

| Test group | Result | Actual boundary |
| --- | --- | --- |
| Python backend/configuration/backup | **179 tests passed** | FastAPI ASGI application, real SQLite/Fernet, mock Google/feed transports, real bounded parser, temporary private storage |
| JavaScript/WebAssembly | **60 tests passed** | Existing calendar adapters/C-WASM bridge plus new API/offline-cache helpers |
| Compiled C core | **1,278 assertions passed** | Native build using CMake/GCC, with warnings treated as errors |
| Browser/admin/tablet components | **32 checks passed** | Real Chromium DOM and C/WASM; real local API through a Python HTTP bridge; mocked Google provider |
| Public HTTP smoke | **23 checks passed** | Actual Uvicorn over loopback HTTP and urllib: MIME, public shell, health, no-store and protected/private routes |
| Preview build | **Compiled successfully** | LLVM/Clang plus wasm-ld; shared C rules/layout, browser-font drawing backend |
| Visual inspection | Week, month, administration and source-editor views inspected | Generic invented demo data; screenshots from the browser component fixture |

The backend tests exercise session roles, pairing replay/expiry/revocation, same-origin protections,
password hashing, shared settings and optimistic revisions, PKCE/state binding and replay, OAuth
refresh/failure/persistence, missing scopes/refresh grants, encrypted credentials, pagination,
quota/network/provider failures, failed-page cache preservation, cancellations, declined invitations,
server-side title masking, rota markers, missing-window loading, cached stale data, midnight/DST,
account-change cache invalidation, key mismatch, configuration generation and consistent SQLite backup.

The component browser test performs administrator login, settings save, pairing, tablet navigation,
Google fixture linking, server-fetched event display, **automatic access-token renewal without another
tablet login**, shared-config refresh, offline retention, and device revocation. It checks for unhandled
JavaScript exceptions. Screenshots are demonstration data, not the user's calendars.

New source tests exercise many-to-one Google/feed merging, iCalendar-only mode without Google,
paused source preview, mapping rules, feed deletion/replacement, conditional GET/304, stale-data
retention, independent provider failures, secret URL masking/encryption, schema migration, six-person
capacity and removal cleanup. Parser fixtures cover recurrence, DST, all-day dates, overnight shifts,
recurrence exceptions/cancellations, folding and unsupported-data rejection. Fetcher tests use fake
DNS/connections to check pinned-public-IP policy, redirect validation, compression/body caps and
credential isolation. Resource-worker parsing executes in a real subprocess. They do not establish
compatibility with an untested rota provider or replace independent security review.

The updated browser component test also uses **Add person**, the per-person **Add source** action,
saves/previews/enables a synthetic rota and verifies that the same member has both a Google
appointment and an on-call marker. No real subscription URL is used.

## Browser test limitation

Direct browser navigation to the environment's local HTTP server was blocked by an environment
policy. That restriction was not disabled. For component testing, HTML/modules were supplied to
Chromium and local API calls were bridged through isolated Python HTTP clients. Thus the test covers
actual application JavaScript/DOM/WASM and server API semantics, **not browser-enforced cookie,
Origin/CSP, redirect, TLS, service-worker or PWA behaviour**. Separate real HTTP checks verify response
headers, not whether a particular browser enforces them as intended. The difference matters.

## Not executed / not verified here

- Docker daemon/image build, runtime filesystem permissions inside Docker, Compose/NPM deployment.
- Real iCalendar provider downloads, provider-specific rota labels or a live private feed.
- Live Google sign-in/consent, Workspace policies, real offline grant, quota behaviour or real calendars.
- Browser-to-NPM HTTPS, authorised callback at a real domain, service-worker upgrade end to end.
- A physical Android tablet, home-screen installation, wake lock, screen timeout or restart behaviour.
- Actual LVGL/Emscripten dependency build. The Docker default is the tested **browser-font preview**,
  not secretly LVGL. The LVGL adapter/toolchain remains in source for further work.
- ESP32 firmware, Spectra panel driver, colour calibration, physical refresh/button/power behaviour.
- OCR, photo import, Google writes or voice integration; these are not implemented in v0.5.
- A penetration test, independent security audit, dependency vulnerability audit or long-duration soak.

The Python execution environment used Python 3.13; the supplied Docker/CI target is Python 3.12.
The pinned dependency versions were exercised in the former; the container build on the latter
still needs to run. Version pins do not claim latest or vulnerability-free releases.

## Reproduce core/backend tests

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
python -m pytest tests/backend -q
bash tools/build-preview.sh
node --test tests/*.test.mjs
cmake -S . -B build/core -DCMAKE_BUILD_TYPE=Release
cmake --build build/core
ctest --test-dir build/core --output-on-failure
```

Preview build requires LLVM/Clang/wasm-ld; CMake/GCC or Clang is needed for native tests. Node 22+
is the tested JavaScript target. The component fixture additionally needs Playwright and Chromium:

```sh
pip install playwright==1.57.0
playwright install chromium
python tools/backend_browser_test.py
```

Where a system Chromium is installed, pass `--chromium /path/to/chromium`. `--screenshots PATH`
optionally writes generic fixture screenshots. The test prints its HTTP-bridge limitation.

## Check the real deployment

After starting the Docker service behind trusted HTTPS:

```sh
python3 tools/backend_smoke.py --url https://paperweek.example.net
```

Then sign in through `/admin`, connect the real Google account, choose calendars, watch per-month
sync success, pair the actual tablet and add/change a harmless test event **in Google Calendar**.
Confirm its appearance/update/removal, current timezone, recurring instances and rota status. Leave
the display running beyond an access-token lifetime and check that no tablet sign-in is requested.
Test a network interruption and recovery, restart the container without deleting its volume, and
verify backup restoration in a disposable environment before relying on the service.

The `backend.yml` GitHub workflow adds a clean-source Docker build and container/public-HTTP smoke
check. It has been supplied but **not run on GitHub** for this artifact. Legacy frontend/LVGL workflow
files remain; Pages deployment is still only the static demonstration, not the backend.

## Publication check

Run `python tools/privacy_check.py --tracked` after staging. Scan any release build separately,
review images and Git history, and keep private deployments separate. This heuristic is not a
security audit or a guarantee that arbitrary future contributions contain no identifying information.
