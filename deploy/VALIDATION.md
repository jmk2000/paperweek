# Legacy static hosting notes

This directory is retained as a v0.3 Nginx reference and is not used by the v0.4 Dockerfile. The current validation record is [docs/TESTING.md](../docs/TESTING.md). Use `tools/backend_smoke.py`, not the legacy hosting checks, for the new authenticated service.

---

# Hosting add-on validation — 5 September 2026

## Passed in the build environment

- Preview rebuilt from the included C source using Clang's WebAssembly target.
- Native C test executable passed (1,278 assertions).
- All 49 JavaScript/WASM tests passed.
- All 27 existing offline Chromium component checks passed. These use an
  in-memory fixture, not the network server.
- NGINX 1.26.3 accepted the supplied configuration with test-only substitutions
  for the document root, temporary paths and listening port.
- Native NGINX ran as unprivileged UID/GID 65534, serving the real built assets.
- All 23 real-HTTP hosting checks passed, including JavaScript/WASM MIME types,
  health response, security/cache headers, invalid paths and rejection of POST.
- The three Compose YAML files parsed successfully with PyYAML. This is NOT
  Docker Compose schema validation or proof that a container will start.
- The source/privacy heuristic passed, including additional private-string checks.

## Not verified

Docker Engine/CLI was not installed in this environment. The image pull/build,
Compose overlays, image health check and container security settings were not
executed. A maintained image tag is used by default, not an immutable digest.

A real-network Chromium smoke test was attempted but the environment's browser
policy rejected navigation to localhost with `ERR_BLOCKED_BY_ADMINISTRATOR`.
Therefore HTTP serving and offline browser behaviour were tested separately;
end-to-end browser loading with the NGINX headers, service-worker activation and
CSP enforcement remain unverified. The included `tools/hosting_smoke.py --browser`
can perform that acceptance test on a host where local navigation is permitted.

No live Google sign-in, Nginx Proxy Manager instance, user LAN/DNS/certificate,
Android tablet or PWA installation was accessed or tested. No actual LVGL build,
server-side Google refresh-token flow, OCR service or ESP32 firmware was added.

Passing these checks is not a security audit. No live calendar data or account
credentials were used during testing.
