# Owner runbook: the Hub on https://hub.ictconnect.org

One ordered list for Arnold, written 21 Nov 2026, address changed 25 Nov. Each step says **who** does it. Detail,
expected output and the rehearsal timings are in `docs/SERVER-DAY.md`; this page fills in the real address and points
to the step there. Where the two disagree, the code wins, then `SERVER-DAY.md`.

**Address (25 Nov):** the Hub is `https://hub.ictconnect.org` (Arnold, relayed by Chief). The Swangz desktop app and
the browser extension start with it filled in at sign-in, and the person can still type another. It replaces
`https://51-21-160-193.sslip.io` (21 Nov); whether that older name still answers was not checked.

**What the team has checked (25 Nov, from outside the server, read only):** the name resolves to `13.63.32.73`, and
`https://hub.ictconnect.org/healthz` answered 200 over a valid certificate with `"ok": true` and commit
`7c2071125a54` (on `main`, older than its head). The team has not logged in to the server. Its `.env`, `preflight`,
backups, firewall and Google sign-in are **not checked**, and every command below is **Not run by the team: it needs
the server**.

**Two different things, do not mix them up:**

| Value | Set to | Why |
|---|---|---|
| Web address: `GATEWAY_WEB_URL` and `GATEWAY_PUBLIC_URL` | `https://hub.ictconnect.org` | Where people open the Hub |
| Staff email domain: `GATEWAY_COMPANY_DOMAIN` | **leave it unset** (the default is `swangzavenue.com`) | Decides who may sign in. Setting it to `ictconnect.org` would lock every `@swangzavenue.com` account out, and `preflight` fails on any other domain unless `GATEWAY_COMPANY_DOMAIN_CONFIRM` repeats it (#323, #324) |

If the server was first set up under another name, change `GATEWAY_WEB_URL` and `GATEWAY_PUBLIC_URL` in `.env` by hand
(the script never overwrites `.env`), re-run step 3 for Caddy, then steps 7 and 11 and step 5 to re-check.

## Steps in order

| # | Who | Step | Done when |
|---|---|---|---|
| 1 | Arnold | **Server checks** before anything else: SSH refuses passwords and security updates are on (`SERVER-DAY.md` section 1). The provider's firewall allows TCP 22, 80, 443 and UDP 443 | `passwordauthentication no`; `unattended-upgrades` is `enabled` |
| 2 | Chief | **Name the commit to deploy** (a merged `main` commit with green CI) | Arnold has the commit written down |
| 3 | Arnold | **Install** (`SERVER-DAY.md` section 3): clone, `git checkout <commit>`, then `sudo bash deploy/setup-gateway-server.sh hub.ictconnect.org`. The script writes `GATEWAY_PUBLIC_URL` and `GATEWAY_WEB_URL` as `https://hub.ictconnect.org` into `/opt/swangz-gateway/.env` (mode 600) the first time, and never overwrites an existing `.env`. If the script was already run, re-running it after pulling is safe | Script ends with `The gateway is running. Next:` and exit code 0 |
| 4 | Arnold | **Check the environment file.** In `/opt/swangz-gateway/.env`, check: `GATEWAY_WEB_URL=https://hub.ictconnect.org`, `GATEWAY_PUBLIC_URL=https://hub.ictconnect.org`, `GATEWAY_HOST=127.0.0.1`, `GATEWAY_TRUST_PROXY=1`, `GATEWAY_FORCE_HTTPS=1` (the last three come from `.env.example`). `GATEWAY_COMPANY_DOMAIN` is absent. `DEMO_MODEL` is absent. Add `GATEWAY_REQUIRE_FIXED_RETURN=1` (it is not in `.env.example`). Never paste the file into chat | Each line reads as listed |
| 5 | Arnold | **Health and preflight** (`SERVER-DAY.md` section 4): `curl -s https://hub.ictconnect.org/healthz`, then `sudo -u swangz python3 -m gateway health-check --url https://hub.ictconnect.org/healthz --expect-commit <commit>`, then `cd /opt/swangz-gateway && sudo -u swangz python3 -m gateway preflight`. Then the four server checks in section 4 (ufw, port 8787 on 127.0.0.1 only, `User=swangz`, and port 8787 refused from outside) | `healthz` shows `"ok": true` and the commit; `preflight` ends `0 to fix` (warnings "Google sign-in off" and "no provider keys" are expected until steps 7 and 8); the four checks pass. Anything else: stop and send Chief the output |
| 6 | Arnold | **First owner** (`SERVER-DAY.md` section 5): `cd /opt/swangz-gateway && sudo -u swangz python3 -m gateway add-admin <name>@swangzavenue.com`. Run as `swangz`, not root. Then sign in at `https://hub.ictconnect.org/admin` with that password | `Owner ... created`; the Overview page loads |
| 7 | Arnold | **Google sign-in client** (`SERVER-DAY.md` section 6). In the Google Cloud console add this authorised redirect URI exactly: `https://hub.ictconnect.org/auth/google/callback` (path from `gateway/google.py`, `redirect_uri`). Keep the laptop's old URIs until step 12. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, leave `GOOGLE_REDIRECT_URI` unset (the return address then follows `GATEWAY_WEB_URL`), and run `sudo systemctl restart swangz-gateway` | `preflight` prints the same return address, `GATEWAY_REQUIRE_FIXED_RETURN` shows `ok`, and the sign-in pages show **Continue with Google**. Sign in once with Google at `/admin` |
| 8 | Arnold | **Provider keys**, only for providers used through the gateway (`SERVER-DAY.md` section 7). Into `.env`, then restart | `preflight` no longer warns about keys, still `0 to fix` |
| 9 | Arnold | **Backup check** (`SERVER-DAY.md` section 8): `cd /opt/swangz-gateway && sudo -u swangz python3 -m gateway backup`, then `sudo -u swangz python3 -m gateway backup-verify --latest` (from the same folder: the `.env` and `data/` are read from the current directory), then `systemctl list-timers \| grep swangz-gateway-backup`. Set `GATEWAY_BACKUP_REMOTE` for a copy off the server (`docs/HUB-DELIVERY.md`), and point an outside uptime monitor at `https://hub.ictconnect.org/healthz` | `integrity ok`; `restore check ok: ... schema vN`; both timers listed. Until the remote is set, `backup` notes that the copy lives only on this server |
| 10 | Arnold | **Data: fresh start or carry over** (`SERVER-DAY.md` section 10). Carry-over uses the backup-first procedure in `docs/HUB-DELIVERY.md`. The team never copies the laptop's database | Decided and, for carry-over, the counts match |
| 11 | Arnold (or the person with each device) | **Point the apps at the address** (`SERVER-DAY.md` section 9). **Staff web app:** give out `https://hub.ictconnect.org/`. **Swangz desktop app:** a new install already shows this address on its sign-in page. An enrolled device keeps its old address, so run `swangz logout`, then `swangz login --server https://hub.ictconnect.org` and approve the code in the browser. **Browser extension:** click its icon, **Sign out**, check the address box reads `https://hub.ictconnect.org` (it keeps the last address it was connected with), sign in, **Connect**. **Managed Chrome pack** (company computers): `python3 deploy/chrome-policy/prepare.py --hub-host hub.ictconnect.org --extension-id <id> --update-url <url> --output <new file>` (`ARNOLD-ONLY.md` item 12; the extension id and update address are still Arnold's to supply). **Netlify:** only if it is kept, change `SWANGZ_GATEWAY` (`deploy/NETLIFY.md`) | The app says `Signed in as ...`; the extension says `Guarding N AI sites.` Extension and Chrome pack steps are UNVERIFIED on a real browser |
| 12 | Arnold | **Cut over, then keep the way back** (`SERVER-DAY.md` section 11): leave the laptop serving until the server has been stable for a few days, then remove the laptop's old redirect URIs from the Google client | Staff use only the new address |

**Google and this name (step 7).** Google's documented redirect-URI rules (https, a name not a raw IP, a top-level
domain on the public suffix list, exact match) do not rule the address out ([Manage OAuth
Clients](https://support.google.com/cloud/answer/15549257)). Adding `ictconnect.org` as an authorised domain ([Manage
OAuth App Branding](https://support.google.com/cloud/answer/15549049)) and brand verification, which requires owning
the domain but is not needed for an **Internal** app or one in **Testing** ([Manage App
Audience](https://support.google.com/cloud/answer/15549945)), are not tried in the console. Check which user type the
existing client uses. If Google refuses the redirect URI or the authorised domain, stop and send Chief what it says.

Provider sign-in inside the managed Chrome is **Sign in with Google only, signed in by hand** by the person. The Hub
never stores, shares or types a provider password (`CLAUDE.md`). Which Google hosts that sign-in needs is being
checked by Probe from the providers' own documentation; the Chrome pack is extended after that (Forge).

## Update the server

For a server that already runs the Hub. **Not run on the server: it needs the server, so every command here is
Arnold's.** What the team did (25 and 26 Nov, East Africa time), on a laptop with a throwaway data folder and sample
people, tools and devices: ran `7c2071125a54` (the commit seen on the server on 25 Nov), backed it up, ran `801f37d`
on the same data, then rolled back. **Not rehearsed:** the setup script itself, `sudo`, systemd, Caddy, a browser
running the extension, and the Windows and macOS apps (the app was driven from its Python code on Linux, old version
and new).

**Which commit.** Chief names a merged `main` commit with green CI (`<new>` below). The rehearsal covers `801f37d`.
Chief runs `git diff --stat 801f37d <new> -- gateway deploy .env.example`; if it lists anything, the rehearsal is
repeated before the update.

### What changes from `7c2071125a54` to `801f37d`

| Area | Change |
|---|---|
| Database | Schema v29 becomes v30 (three new columns on devices) when the new code first starts. No rows were lost in the rehearsal. There is no way down: **the old code starts and answers on a v30 database without complaint, so nothing stops that mistake. Never do it**; roll back as below |
| `.env`, systemd units, Caddyfile | No change between these commits. The same `.env` gave the same `preflight` result |
| Sessions, app and extension tokens, staff keys | An admin session, a staff session, a connected extension's token and an issued key made before the update still worked |
| Swangz app 0.1.0 | Synced, checked in, rotated its key and enrolled against the new Hub. The Hub now reports 0.1.100 as the latest version |
| Shared accounts on `google.com` | The new Hub refuses to add or edit such a tool (even its description) until its sign-in method is changed, and leaves `google.com` out of its list of sites to sign out. Reading the extension's code (not run in a browser), it can still clear one for the person whose turn ends; a fix is open. **Before updating**, look in Tools for a shared account whose address, sign-in link or company browser is under `google.com`, and choose another method |
| Marking a device company or personal | The new Hub has a request for it; the console has no control for it yet. Known gap seen in the rehearsal: after a company device is changed to personal, the app keeps checking the browser policy |

### Update

Pick a quiet time: the gateway restarts, which cuts any AI request in flight.

1. **Write down what runs now.** This is the commit to roll back to:

   ```bash
   cat /opt/swangz-gateway/COMMIT
   ```

2. **Back up first, into its own folder.** The setup script also takes a backup, but only after the new code has
   started and changed the database, so that one cannot be used with the old code. The separate folder keeps this copy
   from being pruned with the nightly ones.

   ```bash
   cd /opt/swangz-gateway
   sudo -u swangz python3 -m gateway backup --dir data/backups/pre-update
   sudo -u swangz python3 -m gateway backup-verify data/backups/pre-update/<file>.db.gz
   ```

   Expected: `... integrity ok`, then `... checksum and integrity ok`. Write down the file name. If either fails, stop.

3. **Install the new commit**, from the clone made at install (`SERVER-DAY.md` section 3):

   ```bash
   cd <the swangz-gateway clone>
   git fetch origin && git checkout <new>
   sudo bash deploy/setup-gateway-server.sh hub.ictconnect.org
   ```

   Expected: it ends with `The gateway is running. Next:`. It keeps `.env` and the database.

4. **Check.**

   ```bash
   curl -s https://hub.ictconnect.org/healthz
   cd /opt/swangz-gateway
   sudo -u swangz python3 -m gateway health-check --url https://hub.ictconnect.org/healthz --expect-commit <new>
   sudo -u swangz python3 -m gateway preflight
   sudo -u swangz python3 -m gateway backup-verify --latest
   ```

   | Check | Expected |
   |---|---|
   | `healthz` | `"ok": true` and the first 12 characters of `<new>` |
   | `health-check` | `up: version ..., commit ...` |
   | `preflight` | `0 to fix` |
   | `backup-verify --latest` | `restore check ok: ... schema v30` (the backup the script just took) |
   | `/admin` | Sign in; People, Tools and Devices show what they showed before |
   | One staff person | Opens an assigned tool from the Hub; an unassigned one stays refused; Activity shows the Open |
   | Their browser extension and Swangz app | The extension still guards sites; `swangz sync` finishes without an error |

   Any other result: stop, send Chief the output (never `.env`), and decide whether to roll back.

### Roll back

This is the restore in `SERVER-DAY.md` section 11, spelled out. It brings back the backup from step 2, so **everything recorded after it is undone. Access removed after that
backup works again**: tools turned off, suspended people, revoked keys, disconnected devices, removed console users and
emergency stops. Later password changes and sign-ins are lost too.

```bash
cd /opt/swangz-gateway
sudo -u swangz python3 -m gateway backup --dir data/backups/after-update
sudo systemctl stop swangz-gateway-health.timer swangz-gateway-backup.timer swangz-gateway-backup-verify.timer swangz-gateway
sudo -u swangz mkdir -p data/after-update
sudo -u swangz sh -c 'mv data/gateway.db* data/after-update/'
sudo -u swangz sh -c 'umask 077; gunzip -c data/backups/pre-update/<file>.db.gz > data/gateway.db'
```

Run them one at a time; each must succeed before the next. The exception is the first one: if the new version cannot
take a backup, carry on, because the newer database is moved aside, not deleted. If `gunzip` fails, do not start
anything (the service would run on an empty or partial database); send Chief the output.

**List what changed after the backup**, before starting the old code, and keep the output:

```bash
sudo -u swangz python3 - <<'EOF'
import sqlite3
new = sqlite3.connect("data/after-update/gateway.db")
old = sqlite3.connect("data/gateway.db")
last = old.execute("SELECT COALESCE(MAX(id),0) FROM audit").fetchone()[0]
for row in new.execute("SELECT datetime(ts,'unixepoch'), actor, action, target, outcome FROM audit WHERE id > ? ORDER BY id", (last,)):
    print(*row, sep=" | ")
EOF
```

Times are UTC. Then start the old version (the script restarts the gateway and turns the timers back on):

```bash
cd <the swangz-gateway clone>
git checkout <the commit written down in step 1>
sudo bash deploy/setup-gateway-server.sh hub.ictconnect.org
curl -s https://hub.ictconnect.org/healthz
cd /opt/swangz-gateway
sudo -u swangz python3 -m gateway backup-verify --latest
```

Expected: `healthz` shows the old commit; `restore check ok: ... schema v29` when that commit is `7c2071125a54`.

**Immediately afterwards**, sign in at `/admin` and repeat every removal in the list. Until then that access is live.
A device that was enrolled, or whose key was renewed, after the backup says `The Hub no longer recognises this device.
Local data was kept. Retry, or sign out and reconnect.` On it, run `swangz logout`, then
`swangz login --server https://hub.ictconnect.org`, and approve the code in the browser.

## If something fails

`SERVER-DAY.md` "If something fails": certificate (`journalctl -u caddy -n 50`; ports 80 and 443 must be open at the
provider), service (`journalctl -u swangz-gateway -n 50`). Send Chief the last 20 lines of output, never `.env`.
