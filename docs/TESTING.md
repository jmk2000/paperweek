# Validation report

## Completed in the development environment

**Environment:** Linux, Python 3, CMake and a native C++ compiler. No access to a Mac or to the user's Google account.

**41 Python unit tests passed.** They cover weekday/year boundaries, London spring/autumn clock changes, all-day exclusive endings, overnight events, midnight boundaries, zero-duration events, private and whole-calendar masking, declined/cancelled events, recurrence-instance identities, duplicate invitations, explicit overflow, malformed events, ASCII/control sanitisation, event serialisation, calendar/event pagination, empty intermediate pages, read-only query construction, transient retries, partial-refresh rejection, pagination-loop rejection, error sanitisation, atomic private files, cache isolation, preservation of the last good snapshot, unavailable-versus-empty display states, and PNG dimensions/chunks/CRCs/physical metadata.

**19 checks in a compiled C++ protocol test passed.** The test validates normal views, text bounding, day/calendar/event limits, field validation, malformed records, and incomplete input. Tests use explicit runtime checks, so Release builds do not disable them with `NDEBUG`.

**Cross-language check passed:** Python generated `examples/demo-week.pwv`, and the compiled C++ reader accepted it.

**Python syntax compilation and shell syntax checks passed.**

## Not completed here

The full LVGL/SDL preview could not be built because the environment lacked SDL development headers and could not download native dependencies. The LVGL UI and SDL adapter have therefore **not been compiled, run, or visually checked here**. Native APIs were checked against the LVGL 9.3.0 headers/build configuration, but that is not a substitute for a complete build.

macOS window creation, Apple Silicon/Intel compatibility, Keychain access, browser callback, live Google Calendar responses, and token renewal were not exercised. No ESP32 compilation, panel driver, native six-colour packing, memory profiling, or hardware refresh test is included.

## Run the complete local build/check

```bash
bash setup.sh
```

This builds the native app and runs both test suites. It then asks the actual LVGL renderer to create `build/smoke-test.png` from invented events. Open that PNG to inspect the native rendering before connecting your real account.

To run just the tests without installing Google authentication libraries or native rendering dependencies:

```bash
python3 -m unittest discover -s tests -v
cmake -S . -B build-model -DPAPERWEEK_MODEL_ONLY=ON
cmake --build build-model
ctest --test-dir build-model --output-on-failure
./build-model/model_test examples/demo-week.pwv
```

A full native demo build without the Google Python dependencies is also possible after installing the native prerequisites:

```bash
PAPERWEEK_SKIP_GOOGLE_DEPS=1 bash setup.sh
```

Install the dependencies later by running setup normally before trying Google sign-in.

## Manual acceptance checks on the Mac

Open the sample view, navigate both directions and return to today. Resize the window and try full screen; the 4:3 layout should letterbox, not reflow. Toggle both palettes and export a frame. Confirm seven day columns, colour labels, legible text, and clean footer spacing.

Connect your own Workspace account and compare a few events with Google Calendar, including an all-day event and a recurring event. Check that a private-marked event is displayed as Busy. Test whole-calendar masking separately. Navigate to a different week and confirm its dates/events agree.

Temporarily disconnect the Mac from the network and press R. A previously fetched week should retain its data with a failure/last-success indication. An unfetched week should say not loaded rather than showing an empty schedule. Restore connectivity and refresh.

Test the 19-second delay independently from normal operation. Check exported/printed text at the intended physical dimensions. Keep real calendar screenshots private.
