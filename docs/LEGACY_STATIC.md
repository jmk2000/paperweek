# Legacy static browser application (v0.3 architecture)

This is historical documentation for running the **browser-only** application. It is not the unattended server. Use [the backend guide](BACKEND.md) for the v0.4 Docker deployment. Static GitHub Pages does not host the backend.

A configurable shared calendar for a tablet today and a colour e-paper display later.
The calendar model, rota rules, week/month layout and button behaviour are portable C.
The browser handles Google authorisation, timezone conversion, device settings and hosting.

**Prototype v0.3.0 — not finished ESP32 firmware.**

## Two rendering builds

| Build | Reused implementation | Rendering | Status of this release |
| --- | --- | --- | --- |
| `preview` | Real C calendar model, layout and controls compiled to WASM | Browser Canvas text and rectangles; browser font metrics | Compiled and tested in this environment |
| `lvgl` | The same C core and layout, plus `ui/canvas_lvgl.c` | Actual LVGL 9.3 framebuffer, compiled with Emscripten | Source/build target supplied; full dependency download and build **not verified here** |

The ready-to-host preview is **not secretly an LVGL binary**. Its header identifies it as
“C/WASM preview · browser fonts”. It is useful immediately for data and interaction testing;
use the LVGL build to validate LVGL's own text rasterisation. Both use the same calendar
logic and the same C layout functions. There is no separate HTML calendar implementation.

## Features

- One to six configurable calendars, generic demo data, unique badges and six-colour design palette.
- Week and month views, Sunday/Monday first, previous/next/today controls and date selection.
- One optional rota band: working, working + on-call, explicit off, unknown, or conflict.
- Read-only Google Calendar access through Google Identity Services; recurring instances expanded by Google.
- Privacy masking; optional cross-calendar deduplication; midnight/overnight and timezone handling.
- Always-visible button labels or first-press help; configurable non-flashing refresh delay.
- Frame-change hashing avoids redraws just because a poll happened.
- Android-friendly touch buttons, full-screen request, optional screen wake lock and app manifest.
- Settings import/export; PNG export; accessible text agenda.

## Quickest start: supplied web build

The release's `paperweek-web` ZIP contains `site/`, a precompiled preview and `serve.py`.
Extract it, open a terminal in that folder, and run:

```sh
python3 serve.py --directory site --bind 0.0.0.0 --port 8080
```

Open `http://YOUR-MAC-LAN-IP:8080` on a tablet on the same trusted network.
The Mac must remain running while serving the page. Stop the server with Ctrl-C.
Use **Settings** to configure the household. Start with invented events.

**This LAN HTTP route is for the demo.** Google browser OAuth, PWA installation and wake lock
need HTTPS on the tablet (localhost exceptions apply only to the device itself).
The secure deployment route below removes the always-on-Mac requirement.
Do not open the HTML using `file://`.

## Build from source

Requirements: Git, CMake 3.20+, Python 3.10+, Node 22+ for tests.

### Actual LVGL / Emscripten

Install ordinary command-line developer tools and CMake first. On a Mac, CMake is
available through Homebrew (`brew install cmake`). Then:

```sh
bash tools/install-emsdk.sh
source "$HOME/.cache/paperweek-emsdk/emsdk_env.sh"
bash tools/build-web.sh
python3 serve.py --directory dist-lvgl --port 8080
```

The toolchain script installs Emscripten 4.0.14 into a separate cache directory.
The build fetches LVGL 9.3.0. Downloads require internet access. They are not bundled
as source or font files in this repository. No personal configuration is embedded.

### Dependency-light C/WASM preview

Install LLVM with `clang` and `wasm-ld` on PATH, then:

```sh
bash tools/build-preview.sh
python3 serve.py --directory dist-preview --port 8080
```

On macOS, Apple's default Clang installation may not include the WebAssembly linker;
use Homebrew LLVM or the Emscripten build instead. `CLANG=/path/to/clang` overrides the compiler.

## Put it on the Android tablet over HTTPS

See [Deployment](docs/DEPLOYMENT.md). The repository includes a **manual** GitHub Pages workflow.
It builds either frontend, runs core/JavaScript/browser smoke tests, and publishes only the
allowlisted static assets. No account, calendar or client ID is stored in the workflow.

Open the resulting HTTPS page in Chrome. Use **Settings** to enter a Google **Web application**
OAuth client ID, prepare sign-in, then sign in and choose the calendars for each member.
Use Chrome's installation / Add to home screen option when offered. This is a browser app,
not an APK. The tablet needs a modern browser with WebAssembly; the project also uses
modern browser APIs such as `structuredClone` and `<dialog>`.

Full Google setup: [Google Workspace / Calendar](docs/GOOGLE_SETUP.md).

## Rota markers

Choose the tracked calendar in Settings. Create normal Google events with these exact
prefixes (prefix matching is case-insensitive):

```text
[PW:WORK] Day shift
[PW:ONCALL] On-call shift
[PW:OFF] Off duty
```

Work and on-call can be timed or all-day. Off-duty must be all-day. An on-call marker
always implies working; no second work event is required. A work/off overlap on a civil
calendar day produces `CHECK ROTA`. Missing data is `? ROTA`, never automatically OFF.
The markers are converted to the rota band and do not consume ordinary appointment slots.
Overnight shifts affect every day actually overlapped; an exclusive midnight end does not
spill into the next day. One person's rota is supported in this release.

## Privacy and public source

The source and demo use **generic labels and invented events only**. Configure actual names,
calendar IDs and the client ID through the settings interface on each device.

Settings are stored in that browser's **unencrypted localStorage**; scripts on the same origin
can read them. Access tokens and event data are **in-memory only** and lost on reload. There is
no server database, analytics, telemetry, write permission or bundled account credential.
Google Identity Services is loaded only after a user chooses to prepare/connect it.

Settings exports and screenshots can contain private information. They are named `*.private.*`
and excluded by `.gitignore`; do not drag them into GitHub uploads. Browser data and Git history
are different things: `.gitignore` does not remove a secret that was already committed.
Read [Security](SECURITY.md) before public hosting.

## Testing

```sh
cmake -S . -B build/core -DCMAKE_BUILD_TYPE=Release
cmake --build build/core
ctest --test-dir build/core --output-on-failure
bash tools/build-preview.sh
node --test tests/*.test.mjs
python3 tools/privacy_check.py
```

See [Testing and limitations](docs/TESTING.md) for exactly what was run and what was not.
GitHub Actions contains an additional real-LVGL build and HTTP browser smoke test. Those
workflow runs have not been executed as part of this artifact delivery.

## Portability boundary

```text
Google API / demo adapter
  -> local-day event records
  -> core/calendar.c: overlap, rota, sorting, density, navigation
  -> core/view_model.h: fixed-size view
  -> ui/calendar_ui.c: shared 1600 x 1200 layout
  -> LVGL framebuffer OR lightweight browser preview
```

The Google browser adapter is not ESP32 authentication code. The ESP32 still needs its
own data adapter, panel-specific refresh driver, six-colour quantisation, power/memory
configuration and button wiring. [Architecture and porting](docs/ARCHITECTURE.md) describes
those boundaries. Source reuse does not make this a tested firmware image.

## Licence

Paperweek code: MIT. Third-party components retain their own licences; see
[Third-party notices](docs/THIRD_PARTY.md). No endorsement by Google, LVGL or any hardware vendor
is implied. Do not rely on a prototype display as the sole reminder for critical commitments.
