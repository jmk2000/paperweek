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
