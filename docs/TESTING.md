# Testing record — v0.3.0

## Executed for this release

- Native C compiler/CMake build: **1,278 core assertions**, including 1,212 Gregorian
  round-trip date cases, month/week ranges, leap years, overnight/exclusive ends, rota,
  event sorting, deduplication, overflow and button-help timing.
- Node.js test runner: **49 tests**, including configuration validation, privacy fields,
  Google response normalisation, DST, fake REST pagination/error handling and direct execution
  of the actual compiled **preview WASM** binary.
- System Chromium, through Playwright's **offline in-memory component fixture**:
  **27 checks**, including settings, member limits, week/month navigation, overlay timeout,
  refresh lockout, missing Google mappings, forgetting local settings and viewport layout.
- Week, month, overlay, settings and tablet-sized preview screenshots visually inspected.

The browser fixture loads the application's actual JS sources and compiled WASM bytes from
memory. It substitutes storage and static-file fetches and inlines CSS. It does not claim to test
an HTTPS origin or Google. It does not modify browser/network policy. Test fixtures contain only
invented data.

## Not verified here

The environment blocked dependency/network downloads and browser network navigation. Consequently:

- **The real LVGL/Emscripten target was not downloaded, compiled or executed here.**
- Native source structure and public upstream API references were checked, but that is not a build.
- Live Google sign-in, Workspace policy, the deployed CSP with Google's popup, token renewal and
  real calendar responses were not tested against an account.
- The real HTTP smoke script, GitHub Actions workflows, Pages deployment, service-worker lifecycle,
  PWA installation, wake-lock/full-screen behaviour and an actual Android tablet remain untested.
- No physical e-paper panel, refresh waveform, ESP32 driver, RAM budget or GPIO wiring was tested.

Do not interpret unit tests with injected Google responses as a live integration test.

## Commands

```sh
cmake -S . -B build/core -DCMAKE_BUILD_TYPE=Release
cmake --build build/core
ctest --test-dir build/core --output-on-failure
bash tools/build-preview.sh
node --test tests/*.test.mjs
python3 tools/privacy_check.py
```

For the offline browser component tests, install Playwright and a Chromium browser, then:

```sh
python3 tools/browser_test.py
# Or provide an existing Chromium executable:
python3 tools/browser_test.py --chromium /path/to/chromium
```

On a normal development machine, after building the actual LVGL frontend:

```sh
bash tools/build-web.sh
python3 tools/http_smoke.py --backend lvgl
```

The HTTP smoke test starts a localhost server, loads the unchanged HTML/modules/WASM under the
page's CSP, checks real raster output and toggles the view. CI and manual Pages publishing run
that smoke test before uploading a selected build. Those workflows were supplied, not run here.

## On-device acceptance checklist

Verify all selected calendars appear; compare an all-day, recurring and overnight event against
Google Calendar; confirm the chosen timezone across a DST change; test a private title; create
rota markers including work on a weekend and a work/off conflict; verify next/previous/today;
let the Google token expire and reconnect; turn Wi-Fi off and confirm the stale warning; reload
and verify no private events are silently persisted; then test installation and waking the tablet.
Use real calendar edits in Google, since Paperweek is read-only.
