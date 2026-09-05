# Upgrade v0.4 to v0.5

Use the existing hostname, NPM proxy host, OAuth client/callback and Compose project name.
Keep the same database volume and encryption key. There is no additional Google permission for
iCalendar subscriptions. Migration adds sources and window warnings without intentionally resetting
Google tokens, people or paired displays. Always take a backup first; this was tested locally with
synthetic data, not on your actual installation.

From the existing deployment folder, with the correct overlay for your environment:

```sh
# Choose a private backup directory outside Git; adjust the example path first.
umask 077
mkdir -p "$HOME/paperweek-private-backups"
stamp=$(date +%Y%m%d-%H%M%S)
docker compose -f compose.yml -f compose.npm.yml exec -T paperweek \
  python -m backend.backup > "$HOME/paperweek-private-backups/pre-v05-$stamp.private.sqlite3"
cp .env.private "$HOME/paperweek-private-backups/pre-v05-$stamp.private.env"
cp .env "$HOME/paperweek-private-backups/pre-v05-$stamp.deployment.private.env"
```

Confirm the backup command succeeded before upgrading. Protect/encrypt this directory. Replace
only public project files with v0.5 (the release contains no `.env`, `.env.private` or database),
then rebuild in the same deployment folder:

```sh
docker compose -f compose.yml -f compose.npm.yml config --quiet
docker compose -f compose.yml -f compose.npm.yml up -d --build
```

For NPM on another host, substitute `compose.lan.yml` for `compose.npm.yml` in every command.
Do not run `down -v`, delete the volume or generate a new encryption key. A fresh installation
should follow BACKEND.md instead. Do not import an old settings export over an already migrated
working configuration unless you deliberately intend to replace it.

Visit `/admin`, close/reopen old display tabs and check the v0.5 label. An old browser/service-worker
cache may need a reload; do not wipe the server data to fix cached browser assets. Follow
CALENDAR_SOURCES.md to attach the rota, preview it while disabled, then enable/save.

The six-person limit is independent of the additional-source limit. Keep the existing member's
personal Google calendar; add their subscribed work feed to the same person, not a second member.

Check your live deployment:

```sh
python3 tools/backend_smoke.py --url https://paperweek.example.net
```

Replace the example origin with your own. Then confirm a known Google appointment and rota shift
appear together, timezone and on-call/off interpretation are correct, and both source health rows
refresh. No hosted deployment or real-account test has been performed by the release author.

Rollback requires the matching pre-upgrade database/private configuration and v0.4 code. Do not
point v0.4 at a schema-2 database. Stop the service and follow the consistent restore instructions
in BACKEND.md. Backups themselves contain private calendar data and device authorisations.
