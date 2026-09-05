# Paperweek: Docker hosting behind Nginx Proxy Manager

This is a **hosting add-on to v0.3**, not a new server-side calendar release.
The included `dist-preview` folder contains the same portable C/WASM preview,
rebuilt from the included source. It uses browser fonts, not the full LVGL build.
There is no GPU requirement, Google client secret, database or photo-import API.
The ZIP includes built assets for immediate use; Git intentionally ignores them.

## 1. Put this directory on the Linux Docker guest

Extract the whole release, not just `web/`. From the `paperweek` directory:

```sh
cp .env.example .env
```

Docker Engine with the Compose v2 plugin is required. No Node or C compiler is
needed to build the hosting image from this ZIP. Docker must be able to pull the
base image. A fresh source-only Git clone must first build the preview with
`bash tools/build-preview.sh` (LLVM/Clang and a WebAssembly linker required).

Choose **one** network option below. Do not combine the two overlays.

### A. NPM is on the same Docker engine — preferred

Use an existing Docker network that NPM is already attached to. Inspect the
running NPM container's networks rather than guessing a name:

```sh
docker ps --format 'table {{.Names}}\t{{.Image}}'
docker inspect NPM_CONTAINER_NAME --format '{{json .NetworkSettings.Networks}}'
```

Replace `NPM_CONTAINER_NAME` with the real container name. Set `NPM_NETWORK` in
`.env` to one of its existing networks. Do not create a new network and assume
NPM has joined it. Another VM's identically named network is not the same network.
Only trusted containers should share the proxy network.

```sh
docker compose -f compose.yml -f compose.npm.yml config --quiet
docker compose -f compose.yml -f compose.npm.yml build --pull
docker compose -f compose.yml -f compose.npm.yml up -d
```

NPM's upstream is **`http://paperweek:8080`**. There is no published host port.
The name `paperweek` must be unique on that shared network.

### B. NPM is in another VM/host

Set `PAPERWEEK_BIND_IP` in `.env` to the Docker guest's **private LAN IPv4 address**.
Do not leave it as `127.0.0.1` for a remote proxy and do not use a public IP.
Keep `PAPERWEEK_HOST_PORT=8080`, or change it if occupied.

```sh
docker compose -f compose.yml -f compose.lan.yml config --quiet
docker compose -f compose.yml -f compose.lan.yml build --pull
docker compose -f compose.yml -f compose.lan.yml up -d
```

NPM's upstream is **`http://DOCKER_GUEST_LAN_IP:8080`** (or your chosen host port).
Restrict this published port to NPM using the appropriate network/Docker-aware
firewall; binding to a LAN IP alone does not enforce that restriction. Do not
expose it through router port forwarding. `127.0.0.1` inside NPM means NPM's own
network namespace, not a different container or VM.

## 2. Create one Proxy Host in NPM

Use a real subdomain you control; `paperweek.home.example.com` below is only a
placeholder. Your local DNS must point this name at **NPM's LAN IP**, not directly
at the Paperweek guest unless they happen to be the same host.

| NPM field | Value |
| --- | --- |
| Domain Names | Your actual Paperweek hostname |
| Scheme | `http` (the private upstream) |
| Forward Hostname / IP | `paperweek` for A, or Docker guest LAN IP for B |
| Forward Port | `8080` for A, or the host port chosen for B |
| Cache Assets | Off |
| Websockets Support | Off; this version does not use WebSockets |
| Access List | Your existing trusted LAN/VPN policy |
| SSL Certificate | Your existing trusted wildcard certificate covering this name |
| Force SSL | On |
| HTTP/2 Support | On, when offered |

The browser URL is **HTTPS**, although the private upstream is HTTP. No Caddy,
second TLS proxy, custom locations or path rewrite is needed. Do not put the app
under a path prefix for this deployment. There is no need to edit the Advanced
box. In particular, do not add a conflicting COOP/COEP/CSP policy there. TLS
certificates and DNS validation credentials remain managed by NPM, not Paperweek.

Keep any existing private-network restrictions. This guide is not an instruction
to expose the host publicly. NPM can still log incoming request metadata even
though access logging is disabled in the app container.

## 3. Move settings and authorise the new HTTPS origin

In the old Mac prototype, use **Settings > Export private settings**. Keep this
file private. Open your new HTTPS address and import the file. Settings are
per-browser and per-origin; the container does not store a household profile.

In Google Cloud > Google Auth platform > Clients, edit the **existing Web
application** client used by v0.3. Add the exact new HTTPS origin, for example:

```text
https://paperweek.home.example.com
```

Substitute your real hostname. Do not add a trailing path, a wildcard or the
upstream HTTP address. You may keep `http://127.0.0.1:8080` for development.
**This browser-only build does not need a redirect URI or client secret.** The
previous discussion of a callback endpoint applies to a future backend only.

Then prepare Google sign-in, sign in, and select/review the calendar mappings.
Connecting at the new origin is expected. Share the private settings file with
another trusted device only when needed; there is no cross-device settings sync.

On Android, open the HTTPS address in Chrome. Use the install/Add to Home screen
option when offered and the app's Keep awake button. The device must be able to
resolve and reach your local hostname and must trust its certificate. Test live
sign-in and installation on the actual tablet; this package does not automate them.

## 4. Check and maintain

Use the same `-f` pair you used at startup for subsequent Compose commands:

```sh
docker compose -f compose.yml -f compose.npm.yml ps
docker compose -f compose.yml -f compose.npm.yml logs --tail=50
```

For option B, substitute `compose.lan.yml`. You can test the NPM route from a LAN
client with `curl -fsS https://YOUR_REAL_HOSTNAME/healthz` (should print `ok`).
A 502 normally means NPM cannot reach the selected upstream; check the network,
host/IP, port and container status before changing Google credentials.

For a future release, replace the public source/assets, rebuild the image and
restart using the same Compose files. The app's service worker is content-hashed;
close all tabs/installed-app windows for this origin and reopen after an update
so an old worker does not keep displaying an earlier build. Do not routinely clear
site storage: that deletes local settings. Export a private backup first.

The base image defaults to `nginxinc/nginx-unprivileged:stable-alpine`, a mutable
maintained tag, **not a digest-pinned reproducible dependency**. After reviewing an
image, an administrator can set `NGINX_IMAGE` to its approved digest in `.env`.
The container has a read-only root filesystem, no added capabilities and one
small writable `/tmp` tmpfs. Nothing needs the Proxmox host itself or the GPU.

## What this does NOT add

- No unattended token refresh. Google access still expires in the browser.
- No server-side settings, calendar sync, API cache or durable event store.
- No photograph upload, OCR, reviewed import queue or Google write permission.
- No finished ESP32 driver or verified LVGL build.

Those are separate backend/firmware tasks. Hosting the current UI this way keeps
its existing C layout and rules intact but does not silently implement them.
The static service has no application login: calendar access still requires a
Google sign-in in each browser, and device/NPM access controls remain important.

## Verification and public repository

`deploy/VALIDATION.md` records what was actually tested. Use
`python3 tools/hosting_smoke.py --url http://127.0.0.1:8080` against a reachable
upstream, or the HTTPS URL. Do not bypass certificate checks to claim HTTPS works.
The optional `--browser --chromium /path/to/chromium` runs a real-browser smoke
test and requires Playwright. It never signs in to Google.

Only explicitly allowlisted public assets enter the Docker build context.
`.env`, photographs, exports, calendars and source files are excluded. The
release has no household-specific settings or Google credentials. Inspect your
Git staging area and history as well as running `tools/privacy_check.py` before
publishing; no heuristic is a guarantee. The ignore list is not a backup system.

Primary documentation (deployment behaviour checked September 2026):
- NPM Docker networking: https://nginxproxymanager.com/advanced-config/
- Docker Compose networking: https://docs.docker.com/compose/how-tos/networking/
- Docker published ports: https://docs.docker.com/engine/network/port-publishing/
- Unprivileged NGINX image: https://github.com/nginx/docker-nginx-unprivileged
- Google browser client setup: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- Browser token model: https://developers.google.com/identity/oauth2/web/guides/use-token-model
