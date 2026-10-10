# First-party delivery, without Netlify

## Architecture

A single Python standard-library process serves `/`, `/admin`, `/static`, `/auth/google/callback`, `/go`, `/api`, `/admin/api` and the provider proxies. Production uses the existing systemd service behind Caddy. Netlify is a historical optional front door, not a required build, proxy, authentication or hosting service. Keep the GitHub repository slug and actual configured production domain; do not change DNS/OAuth simply by copying an example hostname.

GitHub Actions runs Python 3.10/3.12 tests, JavaScript syntax checks and synthetic Playwright/axe checks on standard Ubuntu hosted runners. Browser dependencies are test-only and pinned in `tests/browser/package-lock.json`; production remains dependency-free. Test artifacts contain isolated synthetic identities and databases, never a live database or provider secret.

## Optional Railway staging

`railway.json` builds `deploy/railway/Dockerfile`. It launches the explicit `deploy/railway/staging.py` entrypoint, which is not imported by production `python -m gateway serve`.

1. Create a **new staging project/service** from this feature branch or reviewed commit. Select the included Dockerfile. Do not attach a production service or database.
2. Add a dedicated persistent volume mounted at `/data`. Set `GATEWAY_DATA=/data`, `GATEWAY_STAGING=synthetic`, `GATEWAY_HOST=0.0.0.0`, `GATEWAY_FETCH_ICONS=0`. Railway's `PORT` supplies the HTTP port; do not pin `GATEWAY_PORT` over it.
3. Generate the Railway service hostname, then set both `GATEWAY_PUBLIC_URL` and `GATEWAY_WEB_URL` to that separate HTTPS `*.up.railway.app` URL. Set `GATEWAY_TRUST_PROXY=1` and `GATEWAY_FORCE_HTTPS=1`.
4. Configure `STAGING_OWNER_EMAIL` to a separate verified company-domain owner, and `STAGING_OWNER_PASSWORD` / `STAGING_STAFF_PASSWORD` as separate strong passwords (at least 14 characters). Store them as private Railway variables. Never publish or commit their values.
5. Leave all production provider keys, Google OAuth and SMTP settings unset. The staging launcher refuses them. It runs a local fake provider, seeds only synthetic staff/data, and enforces the same company identity, roles and reporting gates as production. No authentication bypass is added.
6. Set the health path to `/healthz`. Visit staff `/` and admin `/admin`. Synthetic staff address: `staging-fixture@swangzavenue.com`. Verify assigned Canva, gated ChatGPT, reporting submission/unlock, adoption/procurement drafts, admin review, denial without entitlement, navigation and exports.
7. Restart/redeploy the service. Confirm prior submissions, request IDs and admin reviews persist on `/data`, and the seed does not duplicate them. An existing unmarked database is refused **before migrations**. Never remedy that guard by marking a production database as staging.

Railway creation requires authorised account access; prepared configuration is not proof of an online deployment. The actual verification status is recorded in `HUB-COMPLETION.md`.

## Production VPS

Use `deploy/setup-gateway-server.sh` and `deploy/swangz-gateway.service` for the existing `/opt/swangz-gateway` layout. The setup defaults the staff web URL to the supplied first-party domain. Node, Netlify and the old Tracker frontend are not needed on the VPS.

Before installation, verify the real hostname and the server's current deployment/configuration. Record the reviewed commit, running commit, schema version, owner identities and health. Keep secret `.env` files out of the checkout and preserve their permissions. Set `GATEWAY_PUBLIC_URL` and `GATEWAY_WEB_URL` to the verified same first-party HTTPS URL, bind Python to `127.0.0.1:8787`, and let Caddy terminate HTTPS. Existing provider, workspace, SMTP and subscription configuration stays intact. Exact Google callback: `https://VERIFIED_HOST/auth/google/callback`; change it only after the real host is authorised and verified. Same-origin deployment needs no cross-origin allowlist.

### Backup and rehearsal

Stop writes for the final cutover. Do not copy only a live WAL database with `cp`; use SQLite's backup API. With the service running, a read-only rehearsal can use:

```bash
python3 -m gateway.hub_import --database /PRODUCTION_DATA/gateway.db --backfill-v20 --summary /PRIVATE_BACKUP/v20-dry-run.json
```

Dry-run mode backs up into a temporary scratch database and applies forward migrations **only to that scratch copy**. The production file is not opened through the migrating `DB` class. Inspect the private summary, errors and counts. Rehearse existing catalogue, people, keys, entitlements, subscriptions, request history and immutable report versions, and test the backup's integrity. Keep a pre-migration v19 backup and its SHA-256. Store backups outside Git with mode 0600.

For an approved historical import:

```bash
python3 -m gateway.hub_import --database /PRODUCTION_DATA/gateway.db --file /PRIVATE_EXPORT/reviewed-tracker.json --source tracker-reviewed --summary /PRIVATE_BACKUP/import-dry-run.json
```

Only after reviewing the actual source, matching and exceptions, apply with a new `--backup` path and `--apply`. Existing ledger/digest matches are idempotent; conflicts do not overwrite records. Import does not create accounts or tool assignments. Keep the original source/export intact.

### Cutover and health

1. Record the running commit and securely back up the database using SQLite's backup API. Verify integrity and recovery in a separate directory.
2. Stop `swangz-gateway` to pause writes. Deploy the reviewed code without overwriting the data directory or `.env`.
3. Run the approved `--backfill-v20 --apply --backup NEW_PRIVATE_BACKUP --summary NEW_PRIVATE_SUMMARY` command. This takes a verified backup before opening the target with v20 migrations and restores only missing typed historical projections. Original submitted JSON versions remain intact. Inspect the summary before restart.
4. Start the systemd service. Check `systemctl status swangz-gateway`, Caddy status, local and public `/healthz`, authenticated staff/admin login and the verified callback configuration. Logs must not contain credentials or raw user declarations.
5. Check reporting draft/reload/submission, tool-specific gate clearance, independent suspension/entitlement denial, procurement review, department-report scopes and export authorisation. Compare the pre/post counts and preserved historical rows. Do not send a production test to a live provider merely to prove health.
6. Retain the old Tracker data/read-only backup until authoritative history is reconciled. Normal Hub use does not call the old backend.

### Rollback/recovery

There is no destructive down migration. **Do not run v19 code against a database that already contains v20.** Stop writes and the service; preserve the post-upgrade database for investigation. Restore the verified pre-upgrade SQLite backup into a separate directory, rehearse integrity, then atomically replace the stopped database and deploy the recorded prior commit/configuration. Handle any writes made after cutover through a reviewed reconciliation; never silently discard them. Restart and verify health, owner access and counts. Do not delete a live `-wal`/`-shm` file while the process is running.

### Laptop/tunnel availability

The existing automatic laptop service remains separate from VPS deployment. A quick tunnel URL can change and a sleeping/disconnected PC cannot provide permanent service. A VPS with a configured first-party domain is the stable production path. This feature branch does not alter live DNS, Google callbacks, tunnel credentials or the current laptop process.
