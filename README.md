# Paperweek
## A native, six-colour family-calendar prototype for your Mac

**Version 0.1 · Source prototype · 1600 × 1200 · Read-only Google Calendar**

Paperweek is a weekly wall-calendar preview, not a web page. The display is drawn in C with **LVGL 9.3.0**, shown in an SDL window, and deliberately constrained to six colours. A separate Python companion retrieves Google Calendar events. The same `native/calendar_ui.c` layout is intended to be reusable in the eventual ESP32 project.

**Validation boundary:** 41 Python tests and 19 checks in a compiled C++ protocol test passed in the Linux development environment. A Python-generated sample was also accepted by the C++ reader. **The complete LVGL/SDL application has not been compiled or visually inspected here, and macOS launch, Keychain integration, and live Google OAuth have not been tested.** This environment could not obtain the native dependencies. The setup script builds and tests those components on your Mac, including a real LVGL PNG smoke test. This is not a signed, prebuilt `.app`.

## 1. Try the demo first

Unzip the project into an ordinary folder, then open Terminal in that folder. These commands assume Homebrew is installed. Homebrew's official installation instructions are at `https://brew.sh`.

```bash
cd ~/Downloads/paperweek   # Adjust this to wherever you extracted the folder.
brew install cmake pkgconf sdl2-compat python@3.12
bash setup.sh
./run.sh demo
```

If setup reports missing Apple command-line tools, run `xcode-select --install`, complete Apple's installer, and rerun `bash setup.sh`.

Setup creates a project-local Python virtual environment, installs the Google libraries, fetches LVGL's tagged source from its official repository, compiles the preview, runs the tests, and renders `build/smoke-test.png`. It does not install anything with `sudo`, alter calendars, or contact Google with your credentials. The initial dependency downloads need internet access; the sample-data demo subsequently runs offline.

Homebrew now supplies the SDL2 interface through `sdl2-compat`. A working existing SDL2 development installation also works through `pkg-config`.

The sample contains **invented** events for Alex, Sam, Kids, Together, and Home. It repeats relative to whichever week you select. It never writes these events into Google Calendar. The display is explicitly marked **DEMO**.

After setup, `Paperweek.command` offers a small Terminal menu for demo, Google preview, or connection setup. Running `bash run.sh demo` is an alternative when Finder will not launch a downloaded command file; do not disable macOS security globally.

## 2. Connect your Workspace calendar

Follow **`docs/GOOGLE_SETUP.md`** to create your own Google Cloud project and **Desktop app** OAuth client. Save the downloaded client JSON as `credentials.json` beside this README, then run:

```bash
./run.sh connect
./run.sh google
```

The connection wizard opens your browser for Google sign-in, lists calendars subscribed to by your account, and asks which ones to display. Choose up to six, give them short family-friendly labels and colours, and optionally hide all titles in a calendar.

Google credentials stay on your Mac. On macOS, access/refresh credentials are stored in **Keychain**, not in the source folder or a browser. Do not send your downloaded credentials or token to anyone helping you with the project.

The app requests only these permissions:

```text
https://www.googleapis.com/auth/calendar.events.readonly
https://www.googleapis.com/auth/calendar.calendarlist.readonly
```

**Important:** these permissions can read events across calendars your account can access. The wizard's selection controls what this application fetches and displays; it does not narrow Google's OAuth grant to specific calendars. No write permission is requested and no event-editing functionality is implemented.

The prototype signs into one Google account. Family calendars can be shared with that account and added to its calendar list. It does not require everyone to have an account in your Workspace domain.

## 3. Use the preview

Click the calendar window so it receives keyboard input.

| Key | Action |
| --- | --- |
| Left / Right | Previous / next week |
| T | Return to the current week |
| R | Request a fresh Google read |
| E | Toggle representative paper / clean-monitor palettes |
| D | Toggle a 19-second refresh-delay simulation |
| F | Enter / leave full-screen mode |
| S | Save the currently visible LVGL frame as a PNG in `exports/` |
| Q | Quit |
| Escape | Leave full screen, or quit when windowed |

These are **computer controls standing in for physical frame buttons**. The prototype is not a touchscreen design. It has no scrolling or animated calendar interface.

There are up to six visible entries per day. Busy days show an explicit `+ n more - check phone` message rather than silently dropping excess appointments. Long event titles are shortened on the display. All-day entries appear before timed entries. Overnight events appear on each affected day; an event ending exactly at midnight does not spill into the following day.

The default time zone is `Europe/London`. Recurring events are expanded by Google. Cancelled events and invitations declined by the signed-in user are excluded. Duplicate shared invitations are merged by default, with the first selected calendar supplying the label and colour.

The app checks Google every ten minutes while it is running. Network work stays outside the native rendering thread. A refresh is published only when **all selected calendars** succeed. Cached data has a visible last-success timestamp; failures are marked. A week with no loaded data says **not loaded**, rather than suggesting the family is free. There is no automatic switch from Google data to sample events on failure.

While connected, use `./run.sh config` to locate `~/.paperweek/config.json`. Close the app before editing it, then restart. A commented explanation of its fields is in `docs/ARCHITECTURE.md`; JSON itself does not allow comments.

## 4. Get family feedback at the intended size

The window always renders at 1600 × 1200 internally and scales to your screen without changing the layout. A 4:3 image will be letterboxed on a widescreen Mac in full-screen mode.

Press **S**, or export without opening a window:

```bash
./run.sh demo --export ./family-preview.png
./run.sh google --export ./my-week.png
```

This PNG comes from the **actual LVGL framebuffer**, not a second HTML or Python renderer. Exported frames contain six representative RGB colours. Exports of real calendars contain personal information.

For a useful wall-readability trial, print the image with an image area approximately **270.4 × 202.8 mm**, or **27.04 × 20.28 cm**, and put it where the calendar might go. Check the measured result; print dialogs may override image sizing metadata. The PNG includes advisory physical-size metadata.

**Correction to the earlier discussion:** 1600 pixels across 270.4 mm is about **150 pixels per inch**, not 200. This prototype uses the correct 1600 × 1200 pixel target; the physical-size calculation is independent of the display software.

Decide whether seven columns are readable, whether the labels make sense, and whether six visible items per day are sufficient. Neither a backlit Mac screen nor a print can accurately reproduce the panel's colours, contrast, refresh waveform, or real lighting conditions. The `D` option simply holds the old frame for 19 seconds; it does not model the panel's electrical refresh process.

## What is portable, and what is not

```text
Google Workspace Calendar
        |
        | Browser OAuth + read-only HTTPS requests
        v
Python calendar adapter on your Mac
        |
        | Normalised events -> bounded weekly view
        | Atomic local file; no web server
        v
C view model + LVGL renderer     <-- intended firmware reuse
        |
        v
SDL window / six-colour PNG      <-- desktop-only adapter
```

`native/calendar_ui.c` and `native/view_model.h` contain the reusable display layout and its bounded input structure. They do not import Python, Google, SDL, or macOS APIs. The renderer does depend on LVGL and its configured fonts.

The Python OAuth, Google API, time-zone, caching, and event-normalisation code is **not ESP32 firmware**. The desktop adapter deliberately uses full 32-bit buffers and is not the board's eventual memory configuration. An ESP32 port still needs a data/authentication strategy, panel driver, allocation/PSRAM work, bounded rendering buffers, panel-specific six-colour packing, refresh scheduling, and hardware testing. This is more than replacing one driver file.

## Project map

```text
main.py                   Entry point
setup.sh / run.sh         Build and launch scripts
Paperweek.command         Optional Mac Terminal launcher
lv_conf.h                 Desktop LVGL configuration
app/auth.py               Desktop OAuth and macOS Keychain
app/google_source.py      Read-only Calendar API + pagination
app/model.py              Calendar semantics and weekly view
app/cli.py                Wizard, background fetcher, native launcher
app/export.py             Framebuffer-to-PNG conversion
native/calendar_ui.c      Reusable LVGL layout
native/view_model.h       Bounded, pure-C view structure
native/view_reader.cpp    Desktop input-file reader
native/main.cpp           SDL, keys, six-colour conversion, frame export
examples/                 Invented sample view data
tests/                   Python and C++ tests
docs/                    Google setup, security, architecture, testing
```

## Known limits

This is a weekly, read-only, single-account prototype. It does not implement editing, drag-and-drop, month/fortnight views, weather, meals, notifications, or ESP32 firmware. The included font configuration uses LVGL's built-in Latin/ASCII-focused fonts. Accents and common punctuation are simplified for this first version; unsupported scripts and emoji become `?`. The original non-private Unicode event text remains in the local event model, so broader font support can be added later.

Refresh uses full-week queries, not push notifications or incremental sync. Cache retention is bounded to twelve snapshots. Existing screenshots are not deleted by disconnecting. Closing during a Google request may leave Terminal waiting for the bounded in-flight network request to finish. This is not intended as the sole record of a time-critical appointment.

## Tests and reference documentation

See `docs/TESTING.md` for exact checks completed and the untested integration boundaries. See `docs/SOURCES.md` for the official Google, LVGL, and Homebrew references used for this implementation. `docs/SECURITY.md` explains token storage and local cached data.

The source in this project is MIT-licensed. Third-party dependencies keep their own licences and are fetched during setup; no third-party font files or credentials are included in the download.
