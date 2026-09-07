# v0.5.0 — people with multiple calendar sources

- Separate People / Add person from source creation. A person keeps one colour and can combine
  a primary Google calendar with additional Google and iCalendar subscriptions.
- Up to six display people/groups and 24 additional sources. Added per-person Add source action.
- Encrypted, write-only subscription links; HTTPS/webcal adapter, vetted/pinned DNS, conditional
  downloads, resource-limited iCalendar parsing, recurrence exceptions and per-source cache health.
- Rota-only sources with explicit title/category rules, private preview, unknown-by-default
  classification and safeguards against timed OFF and exposing shifts as appointments.
- Additive migration from v0.4 retains Google credentials, settings and device pairings.
- No Google writes, multiple separate Google authorisations, CalDAV, OCR or voice integration.
- See CALENDAR_SOURCES.md and TESTING.md for supported forms, limits and tested boundaries.

---

# Changelog

## 0.4.0 — Unattended local service

- Add server OAuth with offline grant, PKCE/state, encrypted refresh credentials and read-only scopes.
- Add persistent shared settings and bounded per-calendar/month cache, scheduled full-window polling,
  retry/backoff, account-change isolation, explicit missing/stale states and health reporting.
- Add administrator and paired read-only device sessions, private tablet offline opt-in and revocation.
- Reuse the C calendar engine/layout through new server-data browser adapter; preserve legacy adapters.
- Add admin UI for calendar mapping, privacy, rota, polling, pairing and existing private settings import.
- Make Docker build WASM from source; add NPM networking overlays and persistent private volume.
- Add private configuration generator, consistent backup command, tests and operational documentation.
- Bound footer strings without printf precision syntax unsupported by the freestanding WASM formatter.

Not included: Google writes, photo importer, voice integration, real ESP32 hardware driver or a verified
LVGL build. Review docs/TESTING.md for executed checks and external deployment boundaries.

### Web display and tablet installation

- Drag/swipe and previous/next controls slide calendar views together; reduced-motion preferences are respected.
- The display fits the viewport without page scrolling. Short landscape screens use a compact header and overflow counts; the text agenda and settings scroll in their own panels.
- Menu → Install app opens the browser install prompt where supported, with home-screen instructions otherwise. Added a maskable calendar icon and an Apple touch icon.
- The backend already stores settings and calendar windows in SQLite with WAL, revision checks and atomic settings updates. No database migration is needed. PWA caching still stores only public app assets; private offline snapshots remain opt-in.

Install from the HTTPS deployment on a tablet. Android: Menu → Install app (or the browser's Install app option). iPad: Safari → Share → Add to Home Screen. Rebuild/redeploy the web package to deliver these changes to existing installations.

### Readable phone calendar

- Web text now sizes against CSS pixels instead of shrinking a fixed 1600-pixel canvas. The visible month/year, week range and day numbers stay prominent.
- Portrait week view uses seven stacked day rows. The calendar replaces the duplicate branding header; navigation and agenda share one bottom row, with sync details in the agenda and warnings still visible.
- On the web display, blank rota means assumed off when loaded without warnings. Empty and explicit OFF boxes are omitted. Unavailable, stale or warning-bearing data is labelled unconfirmed; WORK, on-call and conflicts remain visible. Source data and the physical e-paper layout are unchanged.

### Automatic offline calendar downloads

- Enable private device caching by default, preserving existing opt-outs. Show the saved view immediately at startup.
- Download all supported months (roughly two years past and future), future first, into IndexedDB while the app is open and connected. Display progress in the agenda.
- Allow offline navigation across downloaded months, including after restarting the PWA. Missing dates remain explicitly unavailable; copies expire after seven days or pairing expiry.
- Clear all downloaded dates on opt-out, configuration change or online session revocation.

### Planner swipe restoration

- Restore sliding left/right navigation on the visible web/PWA planner after the move from canvas to DOM rendering. Preserve date taps, vertical scrolling and reduced-motion preferences.
