# Security and privacy

This is prototype code, not a security-audited appliance. Do not put sensitive clinical,
commercial or other confidential calendars on a public/shared household display.

## What is stored where

| Data | Storage | Sent to the static host? |
| --- | --- | --- |
| Names, badges, calendar IDs, timezone, OAuth client ID and preferences | Browser localStorage, unencrypted | Not by application code |
| OAuth access token | JavaScript memory only | No; used in an Authorization header to Google |
| Calendar event data and rendered display | Browser/WASM/canvas memory | Not by application code |
| Public app code, images and WASM binary | Static host and optional app-shell cache | These files are the public site |
| Exported settings or screenshot | User-chosen local download | Not automatically uploaded |

The hosting provider can still see normal page requests, IP addresses and access metadata.
Google receives OAuth and Calendar API requests. The application has no analytics/telemetry.
This does not mean all data is invisible to the platform, browser, hosting account or device owner.

## Important boundaries

The Google scopes are read-only but allow event access to calendars accessible by the account;
the selected member list is an application filter, not an OAuth-enforced calendar allowlist.
The tablet must be physically trusted. Anyone able to use the app can see displayed information;
title masking leaves time and rota status visible. localStorage can be read by same-origin scripts.
Protect the hosting account/repository and use a dedicated origin where possible.

No refresh token or client secret is needed in this browser design. A client ID is not a secret,
but use your own app/client ID and avoid baking project identifiers into a public example.
Import validation drops unknown fields; it does not turn a private settings file into public data.

Disconnecting/forgetting locally does not delete Google events or revoke older Google consent.
Use Revoke Google access while connected or remove the app in Google Account settings. After
changing accounts/settings, reconnect deliberately and verify the selected calendars.

Service-worker caching is allowlisted to code/assets only. API fetches use `cache: no-store` and
omit cookies to the Calendar API. Event titles are passed as text into the renderer and agenda,
not interpolated into HTML. The app shell's CSP is intended to limit script sources, but live
OAuth and the actual deployed host's headers still need acceptance testing.

## Before publishing

Run `python3 tools/privacy_check.py` and inspect the repository, assets, staged changes and history.
The script detects some common credentials, email addresses and accidentally named private files;
it is not a comprehensive secrets scanner or a guarantee. Supply `--deny-string` for additional
private strings during your own audit; those values are not written to the repository.

Do not publish earlier demo screenshots, exports, OAuth files, local settings, `.ics` feeds or logs
without review. If a secret was committed, remove it from history where appropriate **and revoke or
rotate it**. `.gitignore` alone does not remediate an exposed credential.

Do not post a vulnerability report containing real credentials or calendar content. Once a public
repository exists, use its private vulnerability-reporting mechanism where enabled. No maintainer
email address is embedded in this starter project.

## Docker hosting add-on

The container serves only public assets from an explicit Docker build-context
allowlist. It adds no token store or server-side calendar API. Use the shared NPM
network where possible. An explicitly published LAN port needs network/Docker
firewall restrictions; it is not protected by an NPM access list when bypassed.
NPM can log client request metadata. Its certificates, access lists and private
DNS settings must be administered separately. Do not put household data inside
`dist-preview`; even public assets should be reviewed before building an image.
