# People, Google calendars and iCalendar subscriptions — v0.5

## A person is not a source or a login

A **person** is a named, coloured display slot. You can also use a slot for a shared group such
as Family. There are one to six slots, with one optional rota band. A **source** supplies events
for a slot. One person can have a primary Google calendar and several additional Google or
subscribed iCalendar feeds without consuming another slot. These are not administrator accounts:
the service still has one household administrator password and independently paired displays.

Examples (not configured defaults):

```text
Adult 1 <- personal Google calendar
Adult 2 <- personal Google calendar + subscribed work rota
Child 1 <- personal Google calendar + a club fixtures subscription
Child 2 <- personal Google calendar
Family  <- shared Google calendar + a school dates subscription
```

Every source belongs to exactly one person/group. The UI supports up to 24 additional sources,
in addition to the optional primary Google mapping on each person. The display event cap remains
2,048 expanded records per requested view. Extra feeds do not increase text capacity or add rows.

## Add a person

At `/admin`, sign in and open **People and shared layout**. Under **People & display groups**, use
**Add person**, enter a display name, a unique one- or two-character badge and a colour. Choose an
optional **Primary Google calendar** and **Save shared settings**. Use **Family** as a display name
for shared events; this does not create any calendar at the provider.

If the person is already present, do not add a second person for their work calendar. Keep their
primary Google mapping and attach the feed to the existing person. **Add source for this person**
opens the source editor with its owner selected. Save any person/layout changes before using it.
Removing a person and saving removes their attached sources, URL credentials and local caches,
not events at Google or another provider. The UI asks for confirmation when sources are attached.

## Attach an iCalendar feed for ordinary events

1. Under **Additional calendar sources**, choose **Add a source**, or use the person's attach-source
   button. Give the source a descriptive name and select its person/display group.
2. Set **Source type** to **iCalendar subscription (.ics / webcal)** and **Use on display** to
   **Normal appointments**. Paste the private subscription URL into the password-style field.
3. Set the fallback timezone for feed times with no timezone information. Explicit TZID/UTC times
   and embedded VTIMEZONE take precedence. Set the check interval (5–1,440 minutes; default 30).
4. Leave **Enable this source** unchecked and **Save source**. Choose a relevant month and click
   **Preview saved source**. Check dates, timezone and names against the provider, then enable/save.
5. Set the shared data mode to **Live calendars · Google + iCalendar** and save, if not already set.
   **Synchronise now** requests a fresh check. The source health table shows each retained month.

The URL field becomes blank after saving. **Saved securely** means the existing address is retained;
leave it blank when editing rules, or paste a replacement to change it. The address is not returned
by the administration API or included in layout exports. A `.ics` filename suffix is not required;
the response must actually be a complete iCalendar document, not an HTML calendar/login page.

An iCalendar-only installation does not need Google credentials or Google authorisation. Leave
primary Google mappings empty. The Google status card can remain disconnected while iCalendar
sources synchronise normally. The serialized data mode remains `google` for v0.4 compatibility;
the UI calls it Live calendars and the mode includes both adapters.

## Attach an iCalendar work rota to an existing person

Keep the person's ordinary Google calendar mapped as normal. Select that person in **Rota status
band**, then **Save shared settings**. Add their subscribed work feed as above, but select
**Rota band only · hide appointment entries**. There is no need to import or rename feed events in
Google. Its provider remains authoritative, and Paperweek only reads it.

Rota mapping is deliberately explicit. Start disabled, save and preview to inspect original
titles and categories, then create rules for the provider's actual labels. Example rules only:

| Match field | Match type | Text | Interpret as |
| --- | --- | --- | --- |
| Title | Equals | On call | On-call + working |
| Title | Equals | Day shift | Working |
| Title | Equals | Rest day | Not working |
| Title | Equals | Information | Ignore |

Rules are case-insensitive and run top to bottom; first match wins. Existing `[PW:WORK]`,
`[PW:ONCALL]` and `[PW:OFF]` prefixes take priority. Use Equals for short codes; Contains can also
match negative phrases such as "not on call", so put exceptions first. The preview uses saved
rules; save edits before previewing again. It shows original title/categories, start/end and
interpretation, including invalid matches. It fetches real data privately at your server, not
through a public screenshot or support service. All-day end dates are exclusive.

**Unmatched entries** default to Unknown and generate a warning, rather than becoming guessed
shifts. You can explicitly choose Working for all unmatched entries only after verifying that the
feed contains nothing else. Ignore rules suppress known non-shift notices. No inference is made
from weekdays, weekends or empty dates. Unknown entries do not occupy appointment slots.

On-call always implies working. All-day or timed work/on-call are accepted; timed overnight shifts
affect every day actually overlapped, with an exclusive midnight end. OFF must be all-day: a timed
annual-leave appointment is not proof of a whole day off. A timed OFF match is flagged as invalid
and prevents that source from replacing its previous valid snapshot. Overlapping work and OFF
records become CHECK ROTA in the shared C renderer. An empty feed or blank day never means OFF.

Only one rota band is supported. A rota-only source for a different person becomes inactive when
the band is moved/disabled; it never turns its hidden shift entries into ordinary appointments.
The source remains available to the administrator for reconfiguration.

## Other Google calendars and accounts

Use **Load calendar choices**, then select **Another Google calendar** as an additional source
and choose the intended Google calendar. The same event/rota mapping is available. No new OAuth
scope is required. A primary mapping cannot also be added as an additional Google source; that
would duplicate the same input.

There is still **one connected Google account**, not one grant per person. Calendars belonging
to another account must be shared with that account and added to its calendar list before they
can be selected. Read permission is sufficient; full details are needed to display titles. Each
person can continue editing their own calendar in Google independently of Paperweek.

## Providers, supported data and limits

Implemented adapters are Google Calendar API and **iCalendar 2.0 VEVENT subscriptions over HTTPS**.
School, sports/club, holiday, Outlook or iCloud calendars can work when they supply such a feed;
a provider's name alone does not establish compatibility. We have not tested your real rota feed.

- `webcal://` is upgraded to HTTPS. Only port 443 and internet-routable destinations are accepted;
  private token URLs are supported. You do **not** need to make your calendar publicly listed.
- Local IPs, intranet destinations, self-signed HTTPS, plain HTTP, embedded username/passwords,
  login/cookie/SSO pages and additional authentication headers are not supported. No CalDAV,
  Exchange/Graph account login, Apple-account login, `.ics` file upload or Google Tasks adapter.
- Common all-day/timed/overnight events, UTF-8 line folding, UTC/TZID/embedded timezones, RRULE,
  RDATE/EXDATE, single-instance RECURRENCE-ID replacements and cancelled instances are tested.
  This is a bounded reader, not a full iTIP scheduling implementation.
- Unsupported recurrence forms (including sub-daily rules, EXRULE, RDATE PERIOD and
  RANGE=THISANDFUTURE) reject the new feed with a safe error. Unknown timezones, explicit times in
  a DST gap, malformed/truncated feeds and oversized datasets also reject it. Previous valid
  data remain saved. Recurrent nonexistent clock times are skipped; ambiguous fall-back times
  use the first occurrence. Verify your provider's conventions in the private preview.
- VTODO/tasks, free/busy and journals are ignored with a warning. Alarm components, attachments,
  description HTML and external URLs inside events are not fetched or executed.
- At most 2 MiB compressed/on-wire and expanded feed data, 6,000 event components/expanded
  occurrences, bounded recurrence stepping, download/parse timeouts and subprocess CPU/memory
  limits. Exceeding a cap is an explicit failure, not a silently incomplete calendar.

The portable C calendar layout is unchanged. Adapters normalise provider records and classify
explicit rota rules; shared C still owns date overlap, status combinations, layout and density.

## Refreshes, duplicates and failure behaviour

Each source has its own interval/health. Feeds are fetched by the server, never the tablet. ETag
and Last-Modified enable conditional requests when supported. A validated full feed is reused
for all retained months and replaced atomically across those windows when a new version succeeds.
Changes/removals at the provider therefore replace the previous view, not append a second import.
The provider may itself publish updates slowly; Paperweek cannot make its upstream feed fresher.

An old complete snapshot is retained on an error, with stale status. Google failure does not stop
independent iCalendar polling, or vice versa. Initial delivery still requires coverage from all
enabled sources; an enabled source that has never succeeded can hold the view in loading state.
Previewing while disabled avoids adding an untested dependency. Pause a broken source to exclude it.

Duplicate UID + identical start/end within one person is merged across sources. This is not fuzzy
matching: independent calendars may assign different UIDs to the same real-world appointment.
A rota interpretation takes precedence over an otherwise identical appointment. Existing optional
cross-person invitation deduplication is unchanged. Do not subscribe to the same feed twice merely
to change colours; use the source-to-person mapping.

## Upgrade, privacy and backup

Back up the v0.4 database and `.env.private` first. The v0.5 migration adds source storage and a
warnings column without replacing person mappings, Google tokens or paired sessions. Keep the
same Compose project/data volume, `.env`, encryption key and public origin, then rebuild the service.
No new callback URI, OAuth client or tablet pairing is required solely for this upgrade. Do not
run `down -v`. A downgrade requires the matching pre-upgrade database backup; v0.4 does not read
schema version 2.

Subscription links often grant access by possession. Enter them only in the local administration
page; never commit, log or post them. Source URLs and raw feeds are encrypted using the existing
server key, but processed event caches/settings are not encrypted. The display API gets neither
URL nor original source titles/rules. Administrators see original event text in private preview.
Source labels are local/private too; use a non-secret label, not a copy of the URL.

Layout exports do not include additional sources or encrypted URLs. Back up the consistent database
and matching `.env.private`, not just an exported layout. See [BACKEND.md](BACKEND.md) and
[SECURITY.md](../SECURITY.md). URL fetching has SSRF guards; this is not an independent security audit.

## Primary references

[iCalendar RFC 5545](https://www.rfc-editor.org/rfc/rfc5545),
[python-dateutil recurrence](https://dateutil.readthedocs.io/en/stable/rrule.html),
[Google calendar sharing](https://developers.google.com/workspace/calendar/api/concepts/sharing),
[Google secret iCalendar addresses](https://support.google.com/calendar/answer/37648).
