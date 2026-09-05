# Contributing

Keep calendar semantics in `core/`, visual layout in `ui/`, and platform integrations outside them.
Use generic labels and invented events in fixtures, examples and screenshots. Never contribute
personal configuration, a real client ID, access tokens or actual calendar data.

Run the C tests, JavaScript/WASM tests and privacy heuristic before proposing a change. Add regression
cases for DST, end exclusivity, month length, privacy masking and stale-data handling when relevant.
A C change should be tested in native compilation and a WASM build. A UI change should be reviewed
at the 1600 × 1200 logical size in both week and month modes.

The actual LVGL and lightweight preview adapters have different font rasterisation; keep those
labels and limitations explicit. Do not claim a preview screenshot proves panel behaviour.

Changes that add calendar writes, an unattended auth backend or persisted event caching need an
explicit design and security review. Read-only access and memory-only event storage are intentional
boundaries of version 0.3.
