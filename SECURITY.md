# Security and privacy — v0.5

This is an experimental **single-household LAN/VPN** service, not an audited public multi-tenant
platform. The backend holds private calendar data and Google refresh credentials. Keep it behind
trusted HTTPS and private-network access, patch the host/dependencies, and review this document.

## Publication is not deployment

The repository contains generic demo data and no configured OAuth identity. `.env`, `.env.private`,
exports, images of calendars, credentials, runtime databases and backups must remain private. The
Docker build uses an allowlisted context; it does not copy private environment files into the image.
Public source, compiled public assets and personal runtime storage are different things.

Use `python3 tools/privacy_check.py --tracked` after staging source. It is a heuristic, not a proof.
Review binary files, screenshots and Git history yourself. An arbitrary photo filename is not
necessarily ignored. Ignore rules do not remove previously committed secrets. Never post raw
`docker compose config`, environment dumps, callback URLs, tokens or databases in public issues.

## Credentials and authentication

- One administrator password is generated during setup; only its scrypt hash is stored in private
  configuration. Administrator sessions expire after 12 hours. Change the hash through the setup
  tool to revoke old administrator sessions on restart.
- Tablets use random one-time pairing codes, valid ten minutes. Session cookies are opaque,
  HttpOnly, SameSite=Lax and Secure for HTTPS. Only their digests are in SQLite. Read-only display
  sessions last at most 365 days and can be independently revoked. Clear/re-pair lost devices.
- Mutations require exact Origin, JSON and a custom same-origin header. There is no open CORS API.
  OAuth uses random one-use state bound to the administrator session, a PKCE verifier and a fixed
  redirect origin. Authentication and pairing attempts are rate-limited within the single process.
- All paired displays belong to the same household and share its selected-calendar visibility.
  There is no per-child ACL. A visitor with a paired tablet can browse the allowed display period.
- Google credentials are encrypted using Fernet before saving to SQLite. The key and Web client
  secret are private environment configuration. Google passwords are never collected or stored.
  Docker/host administrators can still read process environments and decrypted process memory.
- The provider scopes are read-only, but broader than the app's selected-calendar list: they cover
  accessible calendars in the authorised Google account. The app enforces selection itself. A
  dedicated Google account shared only the intended calendars can give a narrower upstream boundary.

The original browser-only adapter remains in source for legacy development, but the backend does
not serve that adapter or accept browser-supplied Google tokens. Do not use a static file server
pointed at the source root as a substitute for the authenticated backend.

## Private calendar storage and display masking

The SQLite cache and settings are **not encrypted**, apart from the Google-token blob, OAuth
verifier, subscription URLs and raw subscription payloads. Protect its volume, filesystem and backups accordingly; consider host disk encryption.
Removing a calendar clears its active cache windows, but does not promise forensic erasure from
SQLite free pages, snapshots or old backups. Rotation/retention of backups is the operator's job.

Google calendar IDs and original event IDs are not exposed through the read-only display API.
Descriptions/attendee lists are not sent to it. Private/masked titles become `Busy` server-side.
**Rota status remains visible**: a masked shift becomes a generic working/on-call/off marker so the
shared C rota band still works. Its descriptive title is hidden, not the existence/time of a shift.
This is deliberately not a mechanism for hiding working status from a paired household display.

The tablet's optional offline view is unencrypted localStorage. It is off by default, contains at
most one complete view, and expires within seven days or the session expiry. It has no Google token.
Revocation clears an online device's private copy on its next check. A disconnected device cannot
receive that revocation and may retain the saved view until local expiry/manual clearing.
Public service-worker assets are cached separately; API/OAuth responses are not cached there.

## Deployment and operational limits

Run exactly one application worker, as supplied. Do not run multiple independent schedulers against
one database. Keep the runtime non-root, root filesystem read-only and data volume private. Limit
NPM reachability to your LAN/VPN. The app trusts its configured origin, not arbitrary forwarded headers.

The synchroniser uses outgoing Google calls; it needs no incoming Google webhook. `/healthz` proves
process/database availability only. Check calendar freshness separately in Administration. Offline,
quota/policy errors, data-volume loss or a revoked Google grant can interrupt fresh calendar data.
Do not use this prototype as the sole source of critical reminders.

Application access logging is disabled to avoid recording OAuth query codes. **NPM can still log
those URLs**; restrict its logs and retention, and redact them before sharing. Unexpected exception
tracebacks may expose operational details. Never enable HTTP body/token debugging in a live deployment.

The setup generator preserves keys across reruns. Back up both a consistent database export and
`.env.private`; encrypt the backups. The app refuses an encrypted database token under the wrong key.
Restoring old backups may restore previously valid session records, so review device access afterward.

## Google disconnect and provider revocation

The administration **Disconnect server** action removes local saved Google credentials and active
Google cached events; independent iCalendar sources are retained. It does not automatically revoke the whole Google application grant, which may also
be used by another deployment. To withdraw permission at Google as well, remove the application's
access through your Google Account's third-party connections controls. This is important on
retirement/compromise. Cached copies/backups/device data must be removed separately as appropriate.

A permanent revoked/invalid grant is reported rather than silently replaced with an empty calendar.
External OAuth apps in Testing may require reconnection after seven days. Administrator/provider
restrictions can also prevent linking; review Google's current policies for your Workspace project.

## Subscribed calendar security

Only an administrator can add/edit/preview sources. URLs are write-only, excluded from layout
exports, encrypted at rest and never included in display responses or errors. The fetch worker
has no inherited Google credentials. Google and iCalendar adapters never share auth headers.
Feed queries may contain bearer secrets; do not include real URLs in screenshots, source labels,
issues or diagnostic logs. The private admin preview intentionally shows original event text.

Network policy accepts public HTTPS on port 443; DNS answers are vetted and connections pinned
to those numerical addresses while TLS checks the original hostname. Redirects are limited and
revalidated. Loopback/LAN/link-local/reserved targets, non-HTTPS redirects, embedded passwords and
nonstandard ports are blocked. Environment proxies and automatic cookie/auth forwarding are not
used. This is intentionally not an internal CalDAV adapter or generic URL-fetching proxy.

Feed bytes, decompression, component/occurrence counts, recursion, subprocess CPU/memory and wall
clock are bounded. Parse errors do not replace complete event caches. Subprocess resource limits
are **not** a security sandbox: the server user and host still require normal protection. The
parser does not execute HTML, alarms or attachments and does not dereference event URLs.

Raw feeds and URL secrets are encrypted; normalised display-event caches remain plaintext like
Google cache records. Deleting a source removes its active records but cannot erase old backups.
Shared layout exports omit sources; a complete recovery requires the database and matching key.
Local tests use fake network transports and synthetic calendars, not real rota providers.

## Validation and reporting

Local tests cover role boundaries, state binding, refresh handling, persistence, masking and HTTP
headers, but they are **not an independent security audit**. Live Google, browser-to-NPM TLS and
physical Android behaviour were not tested in the artifact-generation environment. Dependencies
are pinned to tested versions, not claimed to be newest or vulnerability-free. Update deliberately.

When publishing a repository, enable GitHub private vulnerability reporting. Use private reporting
for suspected credential leaks or authentication issues; never post exploitable secrets in an issue.
No private-reporting destination or security response SLA is claimed by this source package itself.

References: [Google OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[Google API scopes](https://developers.google.com/workspace/calendar/api/auth),
[Fernet](https://cryptography.io/en/latest/fernet/).
