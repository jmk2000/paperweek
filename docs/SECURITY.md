# Privacy and security notes

## What leaves the Mac

During setup, dependency managers fetch public software. During Google sign-in, the browser and Google's OAuth client libraries contact Google. Connected refreshes send read-only requests to the Google Calendar API. There is no telemetry, external renderer, analytics service, or developer-controlled endpoint.

No Google requests are made by demo mode. The OAuth callback binds to loopback only and stops after sign-in; no LAN port is left open by the preview.

## Credentials

The app uses Google's supported OAuth client library, PKCE, and a desktop loopback flow rather than handling your Google password. HTTPS certificate verification is not disabled. Only event-read and calendar-list-read scopes are requested. No event/calendar create/update/delete endpoints are implemented.

On macOS, the app explicitly uses the macOS Keychain backend. It does not fall back to a plaintext token when Keychain fails. The downloaded Desktop app client configuration is copied into `~/.paperweek/credentials.json` with owner-only permissions. It is not the same thing as an access/refresh token, but should still be kept out of support messages and repositories.

Linux Google development is disabled by default unless you explicitly set `PAPERWEEK_ALLOW_FILE_TOKEN=1`. That opt-in stores a bearer token in a local `0600` file and is **not recommended for ordinary use**. It is not needed for Linux model tests or demo development. There is no such fallback on macOS.

## Calendar data

Selected calendar IDs, names, times, and redacted summaries are stored locally. Cache files and view files are `0600` inside the `0700` `~/.paperweek` directory. These permission controls are not encryption: anyone who can access your unlocked user account, or a readable backup, can access this information.

Descriptions, locations, conferencing links, and other attendees' names/email addresses are not requested by the events query. Only `self` and `responseStatus` attendee fields are requested to filter declined invitations. Private-title masking happens before caching.

The OAuth grant is broader than the display selection: it authorises reading calendar events the account can access. Selecting calendars is an application-level filter. Leave sensitive calendars unselected, or explicitly mask all of a work calendar's titles for a shared household display. Event-level `visibility=private` and calendar-level privacy are different things.

API error bodies and event titles are not logged. The calendar-selection wizard necessarily displays calendar names locally in your Terminal. PNG exports contain whatever was actually visible; share them carefully.

## Disconnecting and sharing the project

Close the preview before disconnecting or changing the account. `./run.sh disconnect` removes the local token and event snapshots, but it does not revoke the Google-side grant, erase backups, or delete exported PNGs. Revocation is a separate action in your Google Account settings.

The provided `.gitignore` excludes credentials, build files, virtual environments, and exports. That is a convenience, not a guarantee. Before publishing or sending a modified project, inspect the files being included. The original downloadable bundle contains no credentials, tokens, real calendar data, or third-party font files.

This is a prototype rather than a hardened multi-user appliance. Do not use it as a public display of confidential information or as the only place a critical appointment is recorded.
