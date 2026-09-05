# Architecture and the route to hardware

## Separation of responsibilities

The prototype uses a native C/LVGL view, not an HTML mock-up. The desktop-only Python process performs Google OAuth, HTTPS fetching, date/time handling, privacy filtering, deduplication, caching, and weekly presentation-model construction. It starts one C++/SDL process and listens for its navigation commands on a pipe.

The Python process publishes a complete bounded weekly view through an atomic replacement of a private local file. The C++ process polls that file and rejects malformed/incomplete views. Network operations do not call LVGL and do not block its event loop. Only the native process calls LVGL, on its main thread.

The temporary HTTP listener used by Google sign-in exists only on loopback during OAuth. There is no always-running local web server and no internet-hosted renderer.

## Source files to carry forward

`native/view_model.h` is a plain C structure with seven days, six calendar legend entries, and up to six visible entries per day. `native/calendar_ui.c` consumes it without knowing where events came from. These are the main reusable pieces.

`native/view_reader.cpp` is a desktop convenience, not a required firmware parser. A microcontroller can populate the structure from another authenticated data source, a small JSON feed, or an embedded calendar adapter. That choice remains open.

## View protocol

`PAPERWEEK1` identifies the first line. Each following record uses tab-separated ASCII fields, with no embedded tabs/newlines. Text is sanitised before encoding; numeric ranges, record widths, day count and event limits are validated when reading.

```text
META     title  month  week-span  week-number  today  timezone  mode
LEGEND   index  label  colour
DAY      index  weekday  day-number  is-today  month-abbreviation
EVENT    day-index  time-label  title  owner  colour  all-day
OVERFLOW day-index  hidden-count
FOOTER   text
STATUS   text  stale
```

The actual file contains tabs, not the spaces in that explanatory block. `examples/demo-week.pwv` is a valid sample; `examples/demo-view.json` shows the same view before wire encoding. Neither contains real calendar data.

## Calendar semantics

Queries have explicit local-week start/end boundaries converted to RFC3339 offsets. London daylight-saving changes therefore affect each boundary independently. The Calendar API expands recurrence using `singleEvents=true`; responses are paginated even when an intermediate page is empty.

All-day end dates are exclusive. Timed events are included on each local day they overlap. Midnight endings do not create a false extra day. Declined invitations and cancelled events are omitted. A malformed event rejects the refresh instead of being silently dropped.

Privacy masking happens before disk caching. Duplicate invitation suppression uses iCalUID plus occurrence start when available; the first selected calendar wins. Set `deduplicate` to false to see the copies separately.

The currently displayed week is the query/cache unit. Navigating to another week cannot relabel an old week's events as the new week. A response for an earlier navigation request is cached, but not displayed over a newer requested week. There is no incremental sync-token or push-notification implementation.

## Configuration

The wizard writes `~/.paperweek/config.json`. The `PAPERWEEK_DATA_DIR` environment variable can redirect local storage for tests. Close the app before changing configuration.

```json
{
  "title": "Our week",
  "timezone": "Europe/London",
  "poll_seconds": 600,
  "mask_private": true,
  "deduplicate": true,
  "calendars": [
    {
      "id": "your-calendar-id-from-the-wizard",
      "label": "Family",
      "colour": "blue",
      "mask_titles": false
    }
  ]
}
```

`mask_private` hides summaries on events explicitly marked private. `mask_titles` hides every summary from a chosen calendar. Colours are blue, red, green, black, and yellow; white is reserved for the background. `poll_seconds` accepts 60 to 86400. UI labels are independent of Google calendar names.

The preference for hiding titles is local; it does not change the corresponding Google events. Editing the configuration requires restarting the prototype.

## Rendering and exports

LVGL renders a complete 1600 × 1200 XRGB8888 frame. A desktop flush callback quantises it to exactly six representative RGB colours, then presents it using SDL. Neutral text-edge pixels are constrained to black/white to avoid coloured antialiasing fringes.

The native process can write its actual visible frame as RGB PPM. Python wraps those pixels in a lossless PNG; it does not redraw the calendar. The PNG is not a native packed panel buffer. Its pHYs metadata targets roughly 270.4 × 202.8 mm.

The paper palette is an approximation, not a device profile. A real panel's palette/reflectance/lighting must be checked with the hardware. Refresh simulation holds the old image for 19 seconds and reports progress in the window title. It does not flash or pretend to model the physical waveform.

## ESP32 work that remains

The desktop process has two full 32-bit framebuffers: about **15.36 MB in total**, before LVGL objects, fonts, networking, stacks, or other allocations. Do not copy this desktop allocation strategy onto the ESP32 just because it has PSRAM.

A native 1600 × 1200 image at 4 bits per pixel is **960,000 bytes**, but creating that image also needs a rendering plan. A hardware port should evaluate bounded draw strips/tiles, a packed target buffer in appropriate RAM, alignment, conversion costs, PSRAM bandwidth, font storage, and driver transfer requirements. Those choices must be tested on the actual board.

The port also needs a secure calendar-access strategy. The Mac's Python OAuth flow is not a ready-made embedded authentication solution. Possibilities to evaluate separately include a protected minimal-data relay or suitable secret ICS feeds. None is silently provisioned by this project.

Finally, add the panel's real driver and power sequencing, six-colour code mapping/packing, refresh policy, timeout/retry handling, physical button input, and realistic memory/power tests. The renderer can be reused; production firmware and authentication still require engineering.
