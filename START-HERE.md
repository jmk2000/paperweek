# Paperweek v0.5 — people with multiple calendar sources

This release combines a person's Google appointments and an iCalendar rota without a second
person/colour on the display. It extends the v0.4 unattended backend; the shared C calendar model
and layout are unchanged. It has not been deployed on your host.

## Downloads and contents

`paperweek-v0.5-sources.zip` contains the complete source project, Docker/Compose deployment,
precompiled browser-font C/WebAssembly preview, source-editor UI, tests and documentation.
There are no configured household names, domain, private subscription links or Google credentials.
The renderer is still the browser-font preview, not a verified LVGL firmware or native Android app.

## Upgrade a working v0.4 service

First back up the database and `.env.private`. Keep `.env`, the encryption key and the same
Compose project/data volume. Replace public source files and rebuild using your existing overlay:

```sh
docker compose -f compose.yml -f compose.npm.yml up -d --build
```

Use `compose.lan.yml` instead if that is your current networking arrangement. No new NPM hostname,
Google callback URI or permissions are needed for this upgrade alone. Do not use `down -v`.
Read `docs/UPGRADE_v05.md` before updating: it includes backup and rollback instructions.
A fresh installation should follow `docs/BACKEND.md`.

## Add people or sources

In `/admin`, **People and shared layout → Add person** adds a display person/group (up to six).
A person is a name/colour, not an account. Select their optional primary Google calendar and save.
The older confusing button label “Add calendar” has been replaced by “Add person”.

For another feed belonging to someone already listed, use **Add source for this person**. Keep
the personal Google calendar selected. Additional sources share that person's colour/slot.
Up to 24 additional Google/iCalendar sources are supported; they do not use more person slots.
A shared Family group is optional and counts as one display slot.

## Work rota

1. Select the person in **Rota status band** and **Save shared settings**.
2. Use their **Add source for this person** button. Name it, choose **iCalendar subscription**,
   paste the private URL, and set **Use on display → Rota band only**.
3. Choose the fallback timezone, for example `Europe/London`, and polling interval (default 30
   minutes). Leave disabled, save, choose the month and **Preview saved source**.
4. Inspect the actual titles/categories. Add explicit rules for Working, On-call + working,
   Not working or Ignore; save and preview again. Then enable and save the source.
5. Select **Live calendars · Google + iCalendar** as the shared data mode. **Synchronise now**
   checks providers; the health table tracks each feed separately.

Existing `[PW:…]` tags are recognised. Otherwise no shift type is guessed: unmatched events stay
unknown unless you deliberately select Working as the default. No feed event or empty cell ever
implies OFF automatically. OFF must be all-day; on-call always implies working. Ordinary Google
appointments remain visible while rota entries become the existing status band.

Do not rename/copy feed events into Google. This is a live read-only subscription, not an import.

## URLs, accounts and provider limits

Enter subscription URLs only in the local administration form. They are encrypted server-side,
write-only and omitted from display data/layout exports. Private token URLs are accepted; you do
not need to make the calendar public. Existing URLs show as saved, not displayed in full.

Supported: internet-reachable HTTPS iCalendar 2.0 VEVENT feeds (`webcal` upgraded to HTTPS), and
Google Calendar through the existing backend account. Common recurrence/timezone forms and
exceptions are tested, but your actual provider has not been tested. Private-LAN URLs, login
pages, Basic authentication, CalDAV, Exchange-account authentication and Google Tasks are not
implemented. Unsupported or oversized feeds report an error and retain last-good data.

For Google calendars owned by another account, share them with the account connected to the
server and add them to its calendar list. This release does not add multiple Google account grants
or additional administrator logins. The iCalendar feed does not require Google authentication.

`docs/CALENDAR_SOURCES.md` explains limits, duplicate handling, categories/rules, provider scope,
privacy and failure behaviour. Back up the database and matching key: a layout export alone does
not contain sources or subscription URLs.

## Validation

179 Python tests, 60 JavaScript/WASM tests, 1,278 native C assertions, 32 browser-component checks
and 23 actual HTTP checks passed. These use synthetic Google/feed responses. The browser checks
use a Python HTTP bridge, not browser-enforced HTTPS/cookies/CSP. Preview build and source-editor
screenshots were inspected. The real Google/rota providers, Docker build, NPM, physical Android,
PWA installation, complete LVGL build and e-paper hardware remain unverified here.
See `docs/TESTING.md`. This is an experimental household service, not an independently audited
public multi-tenant application. Photo OCR, event writes and voice features are not included.
