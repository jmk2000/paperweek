# Architecture and the ESP32 boundary

## Shared C, not two unrelated calendars

`core/calendar.c` owns Gregorian date arithmetic, period navigation, day overlap, rota rules,
optional invitation deduplication, event ordering, visible density and overflow counts.
`core/view_model.h` holds bounded display-ready structures. `ui/calendar_ui.c` owns the actual
1600 × 1200 layout: headings, badges, date cells, rota bands, status and control pointers.
These files are compiled into both browser builds. They do not import browser, Google, SDL,
LVGL or ESP-IDF headers.

`ui/canvas.h` is a small immediate drawing interface. `ui/canvas_lvgl.c` creates real LVGL
objects/labels, using the configured LVGL fonts. `platform/web/display_lvgl.c` connects LVGL's
flush callback to a browser ImageData buffer. It uses a 60-row partial **software rendering
buffer**; this does not claim fast partial refresh support on an e-paper panel.

The lightweight `platform/web/canvas_browser.c` adapter imports rectangle/text callbacks into
WASM instead. It preserves C layout and model behaviour but uses the browser's font metrics,
wrapping and rasterisation. It is deliberately labelled differently in the app. It is not a
replacement implementation of LVGL and cannot validate LVGL-specific clipping or memory use.

## Browser responsibilities

The browser adapter expands no recurrence itself. Google Calendar is queried with
`singleEvents=true`; the adapter requests all pages for all selected calendars. An operation is
committed only after the complete bounded dataset is received and validated. An aborted or
obsolete request cannot replace a newer requested period.

Timed events are converted from actual instants into the chosen display timezone's civil date
and seconds since midnight. Epoch milliseconds are preserved for ordering. Date-only all-day
records keep their exclusive end dates. This model avoids treating a DST day as always 24 hours.
The adapter validates actual start/end ordering, including fall-back cases where local wall time
moves backwards. The C core handles midnight/overnight overlap without consulting a host timezone.

Limits: six calendars, 2,048 expanded records per query, 42 visible dates and six entries per day
in week view. Month density is five, four or three entries per cell for four-, five- or six-row
months. Excess visible entries become an explicit overflow count. Exceeding the global event
limit is an error, not a silently incomplete calendar. One tracked rota is supported.

The current normalised record ABI contains a dedup key, title, calendar index, local start/end
day ordinals, local start/end seconds, all-day flag, marker kind and an epoch sort key. Google
calendar IDs never enter the UI model. The browser uses a compact non-cryptographic identity hash
for deduplication; it is not a security or anonymisation feature.

Settings and import/export are plain JavaScript. The display does not reflow using HTML/CSS:
CSS sizes the outer canvas and controls only. The accessible agenda is an alternate text view,
not the portable visual renderer. Google is read-only in this release; Alexa/write operations
from earlier design discussion are not included.

## Redraw and button model

The C view is deterministically cleared/built and hashed. A poll timestamp is not part of the
view. An unchanged image is not redrawn merely because a fetch succeeded. The footer's next event,
today indicator, changed data, stale state and the help overlay can require an update.

The four logical actions are previous, today, toggle week/month and next. The C help state
machine consumes the first press in overlay mode, ignores presses while busy, and starts its
timeout once rendering has completed. Showing/hiding help each incurs the configured demo delay.
The delay is a **non-flashing explanatory placeholder**, not a waveform simulation or a device
latency guarantee. Permanent labels are the practical default for a slow full-refresh panel.

While following today, the browser advances the selected date when the local date changes.
Manually browsing previous/next suspends that follow-today behaviour; pressing Today restores it.

## What changes on ESP32

Keep `core/calendar.c`, `core/calendar.h`, `core/view_model.h`, `ui/calendar_ui.c`,
`ui/calendar_ui.h`, `ui/canvas.h` and, for an LVGL-based firmware, `ui/canvas_lvgl.c`.
Replace the browser platform display bridge and the browser input/auth adapter.

The remaining hardware work is real engineering, not a two-line driver swap:

- Choose the exact panel/controller pair and its supported refresh waveform, pinout and driver.
- Convert the LVGL raster output (including anti-aliased colours) to the panel's supported six
  colours and packing. Different 13.3-inch boards need not share packing or controller commands.
- Arrange a native framebuffer or streaming conversion, panel BUSY handling, deep sleep/power
  sequencing, safe refresh intervals, and memory placement in PSRAM/flash.
- Wire and debounce physical buttons; feed the same logical actions/help state.
- Implement an ESP32 data adapter and credential lifecycle. Browser OAuth tokens are not a
  deployable appliance credential strategy. A private authenticated relay that returns the
  normalised records is one option; direct device integration needs a separate secure design.

The web build's memory allowances are browser defaults, not an ESP32 budget. The bounded event
array is under a megabyte; the exact total includes view, fonts, LVGL objects, draw buffers and the
panel buffer. Measure the chosen firmware configuration rather than inferring it from Chrome.

For development on a Mac, this release runs in the same browser as Android. The old Python/SDL
launcher is not included in the clean public package; desktop/native integration can link the
same C core/UI. No tested ESP32 firmware or native Android APK is included.

## Primary references

[LVGL Emscripten port](https://github.com/lvgl/lv_web_emscripten),
[LVGL 9.3.0 source](https://github.com/lvgl/lvgl/tree/v9.3.0),
[Emscripten build documentation](https://emscripten.org/docs/compiling/Building-Projects.html),
[Google Calendar event list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list).
