# Google setup: v0.4 server versus legacy browser

For the unattended Docker service, use [BACKEND.md, Google configuration](BACKEND.md#2-google-configuration). It needs a **Web application client secret on the server** and the exact **Authorized redirect URI** `/api/oauth/callback`. The browser-only instructions below are retained for the standalone v0.3 frontend and are not the v0.4 server setup.

---

# Google Calendar and Workspace setup

This browser build uses Google Identity Services' **token model**, with a popup triggered
by a button press. It calls the Calendar REST API directly. There is no client secret,
API key or refresh-token file in the browser application.

## Register the application

1. In Google Cloud, create/select a project and enable **Google Calendar API**.
2. Configure the Google Auth platform branding and consent audience. A project owned by
   a Workspace organisation may offer **Internal**, appropriate for organisation-only use.
   Otherwise choose External and add test users during development. Public distribution
   of the source code does not make your OAuth app public; each household can register
   its own app. A public multi-user OAuth service is a separate deployment/verification task.
3. Create an OAuth client with application type **Web application**. The Desktop app
   credential from a previous native prototype is not interchangeable with this one.
4. Add the exact **Authorized JavaScript origin**. For a local Mac test this can be
   `http://localhost:8080` (or the loopback origin actually used). For a tablet, use the
   deployed HTTPS site's origin, for example `https://YOUR-USERNAME.github.io`.
   An origin has no repository path or trailing route. Register custom domains separately.
   Do not enter `https://YOUR-USERNAME.github.io/paperweek/` as an origin.
5. Add these read-only scopes to consent settings as appropriate:

```text
https://www.googleapis.com/auth/calendar.events.readonly
https://www.googleapis.com/auth/calendar.calendarlist.readonly
```

The events scope can read calendars that the signed-in account can access; the application's
selection is not a Google-enforced per-calendar permission boundary. Use an appropriately
limited Google account where stronger separation is required. Workspace admin policy can
block an app or restrict sharing; resolve that in the Workspace admin controls rather than
making calendars public or enabling domain-wide delegation for this prototype.

## Connect on the tablet

Open the deployed HTTPS page in Chrome, then Settings. Paste **only the client ID**. Set the
correct display timezone. Tap **Prepare Google sign-in**. Once ready, tap **Sign in & load
calendar choices**. The second, explicit press preserves the browser's popup user gesture.

Sign in with the one account that can access all intended calendars and grant both read-only
permissions. Select a Google calendar for each configured person, select Google as the data
source, and press Apply settings. Remove unused people instead of leaving their calendars blank.

For existing mapped settings, the header Connect Google button prepares the library on the
first use and asks for a second press to sign in. Later reconnects can open the popup directly.
Calendars shared with you may need to be added to your Google Calendar list before appearing.

## Important limitations

**A plain `http://192.168...` address on an Android tablet is not the localhost exception.**
Use LAN HTTP for the demo and HTTPS for live Google use. `localhost` on the tablet means the
tablet, not a Mac serving the files.

Google browser access tokens are short-lived. This version does not quietly refresh them
on a timer or store refresh tokens in browser storage. A button press is required to reconnect
when access expires, and after reloading the app. You can test real calendars, but you should
not expect an unattended multi-week household appliance from this auth arrangement.

Events are kept only in memory. A failed calendar request retains the last successful view
and marks it stale; a partly fetched set of calendars is never committed. Reloading loses
those events. The service worker caches the app shell, not Google responses or private events.
The app polls only while open/foregrounded and does not promise background browser sync.

Calendar API expands recurring events (`singleEvents=true`). All-day dates are date-only
with exclusive ends; timed records are converted to the configured display timezone before
the C core handles day overlap. Ambiguous timestamps missing an offset are rejected rather
than interpreted using the tablet's accidental local timezone. The current display is
English and ASCII-focused; accents are transliterated, unsupported characters become `?`.

## Privacy masks

Private-marked event titles are hidden by default; any selected calendar can be configured to
show only “Busy”. Rota tags are classified before title masking so the chosen status band still
works. Rota status and event timing remain visible; a title mask is not a hide-the-event control.
Free/busy-only calendar permissions do not provide enough detail for a title-based rota band.

## Troubleshooting

- **Origin mismatch:** confirm the exact scheme, hostname and port; use a Web client.
- **Access blocked / 403:** check the API is enabled, both scopes were granted, the app's
  audience includes the user, Workspace policy permits it, and the account can read each calendar.
- **Popup cancelled/blocked:** prepare the library first, then press the sign-in button again.
- **Blank choices:** confirm the calendars are in the signed-in account's calendar list and
  have at least read access, not just free/busy access.
- **Wrong day/time:** check Paperweek's IANA display timezone, not only the tablet timezone.
- **Expired connection:** press Connect/Reconnect Google. Forgetting local settings is not
  the same as revoking Google consent; use Revoke while connected or Google Account settings.

## Official references

[Google Calendar JavaScript quickstart](https://developers.google.com/workspace/calendar/api/quickstart/js),
[Google Identity Services token model](https://developers.google.com/identity/oauth2/web/guides/use-token-model),
[Calendar scopes](https://developers.google.com/workspace/calendar/api/auth),
[Events list and recurrence expansion](https://developers.google.com/workspace/calendar/api/v3/reference/events/list),
[OAuth consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent).
