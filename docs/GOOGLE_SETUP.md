# Google Workspace setup

This is for your own Google Workspace account on your Mac. You do not need to make your calendars public, create a service account, enable domain-wide delegation, or give the app write access.

## Create the project and client

1. Sign in to Google Cloud Console with your Workspace account. Create a project such as **Paperweek**. For an Internal app, the project must belong to the organisation associated with your Workspace domain, not an unrelated personal project.
2. In the API Library, enable **Google Calendar API** for that project.
3. Open **Google Auth platform**. Complete **Branding** with a name such as Paperweek and your contact email. Under **Audience**, select **Internal** when available for your organisation.
4. Under **Data Access**, add the two read-only scopes below where applicable. An Internal application's consent configuration may not require you to list scopes in the same way as an External application, but the code still requests them.
5. Under **Clients**, create an OAuth client with application type **Desktop app**. Do not choose Web application, TV/limited-input device, or service account.
6. Download the client JSON. Save it as `credentials.json` in the Paperweek project folder. Alternatively, use the explicit path option shown below.

```text
https://www.googleapis.com/auth/calendar.events.readonly
https://www.googleapis.com/auth/calendar.calendarlist.readonly
```

Official setup reference:
`https://developers.google.com/workspace/calendar/api/quickstart/python`

The reference uses a broader read-only Calendar scope in its example. Paperweek intentionally uses the narrower event-read and calendar-list-read scopes.

## Sign in and choose what is displayed

From the project directory:

```bash
./run.sh connect
```

Or specify the downloaded JSON's path without renaming it:

```bash
./run.sh connect --credentials "$HOME/Downloads/client_secret_your_file.json"
```

The app copies the validated client configuration into `~/.paperweek/credentials.json` with owner-only file permissions. The browser opens Google sign-in using a temporary loopback callback on `127.0.0.1`. Select your Workspace account and approve both read-only permissions. Return to Terminal and select calendar numbers, display names, colours, and optional whole-calendar title masking.

The wizard asks about **hiding all titles** separately from its default handling of events explicitly marked private. A calendar being private to its owner does not mean every event is marked `visibility=private`. For a work calendar that should only display occupied time, choose whole-calendar masking.

Start the connected view:

```bash
./run.sh google
```

The token lives in macOS Keychain under **Paperweek Calendar Prototype**. macOS may ask permission for Python to access that Keychain item. The original downloaded client JSON can be removed after a successful connection; the private local copy remains available for later sign-ins.

## Family members outside your domain

Only your account authenticates to this prototype. Share a partner's or household calendar with that account through Google Calendar, with permission to see event details, then add it to that account's calendar list. Rerun `./run.sh connect` to reselect calendars.

Google and Workspace sharing policies still apply. The app cannot bypass restrictions or reveal details that your account is not permitted to read. Free/busy-only calendars are excluded from the wizard in this version; supporting them would require a separate free/busy adapter.

## Internal versus External

Internal apps are for sign-ins within the associated Workspace organisation. They are not automatically available to unrelated Gmail accounts, even if you own the domain. You do not need external sign-in merely to read calendars shared with your internal account.

If Internal is unavailable, check the project's organisation and the signed-in account. An **External / Testing** app with your account added as a test user is an alternative for a prototype. For Calendar permissions, Google normally expires refresh tokens from that testing configuration after **seven days**. That is not a bug in the display. Use `./run.sh connect` to renew access, or configure the appropriate longer-term app audience/publishing arrangement under Google's rules.

Workspace admin app-access restrictions can still block an Internal app. Check Calendar API enablement, Cloud-project access, and Workspace app-access controls rather than weakening the application scopes.

## Troubleshooting

**Access blocked / 403:** verify that Calendar API is enabled in the same project as the downloaded client, your account is an allowed Internal or test user, and Workspace policy permits the app.

**Redirect mismatch:** confirm that the downloaded client is a **Desktop app**. The application uses an ephemeral local loopback port, not a public URL that you need to host.

**Browser did not open:** run the command directly on your Mac desktop, not in a remote/headless session. The prototype does not implement an alternative code-copy sign-in flow.

**Missing calendar:** add it to the signed-in account's calendar list and ensure that account has permission to read events. Rerun the connection wizard.

**Sign-in needs renewing:** close the preview, then run `./run.sh connect`. This version deliberately does not open an unexpected sign-in browser from its background refresh worker.

**Keychain error:** check that your login Keychain is unlocked and permit this local Python app to use its own credential item. There is no silent plaintext token fallback on macOS.

## Disconnect

Close the preview, then run:

```bash
./run.sh disconnect
```

This removes its local access/refresh credential and cached event snapshots. It leaves the non-token client configuration and display preferences. It does **not** revoke the Google-side OAuth grant or delete screenshots. To revoke the grant, remove Paperweek in your Google Account's third-party connections settings. Delete exports separately when no longer needed.

Never include `credentials.json`, a token, real calendar caches, or screenshots of private events in a support message or public repository.
