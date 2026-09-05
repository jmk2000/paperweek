# Docker / Nginx Proxy Manager — v0.4 server

The Dockerfile now builds and serves the unattended backend and browser application, not the
v0.3 static Nginx site. The image builds WASM from source; `dist-preview/` need not be committed.

**Use [docs/BACKEND.md](docs/BACKEND.md) for deployment, Google setup, migration and backups.**

- NPM on the same Docker engine: `compose.yml` + `compose.npm.yml` and an existing shared network.
- NPM in another VM/host: `compose.yml` + `compose.lan.yml`, a private bind IP and a restrictive firewall.
- Configure private runtime files with `python3 tools/configure_backend.py` before Compose.
- NPM forwards HTTP to port 8080; browsers must use the configured HTTPS origin.
- `/admin` is the new administration page. `/` pairs and displays the tablet.
- Persist the `paperweek-data` volume and the private token-encryption key.

The files in `deploy/` and the original `hosting_smoke.py` are retained only as the legacy static
hosting reference. They are not used by the v0.4 Dockerfile. Use `tools/backend_smoke.py` to check
the new service's unauthenticated HTTP/security boundary after deployment.

The Docker runtime has not been executed in the artifact-generation environment. Review the
configuration, run the smoke check and inspect Google sync status on your own host before relying
on the calendar.
