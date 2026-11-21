# Owner runbook: the Hub on https://51-21-160-193.sslip.io/

One ordered list for Arnold, 21 Nov 2026. Each step says **who** does it. Detail, expected output and the rehearsal
timings are in `docs/SERVER-DAY.md`; this page fills in the real address and points to the step there. Where the
two disagree, the code wins, then `SERVER-DAY.md`.

**State on 21 Nov:** Arnold reports the server and the address are done (Chief, 09:05). The team has not logged in to
the server, run anything on it or checked it. Every command below is **Not run by the team: it needs the server**.

**Two different things, do not mix them up:**

| Value | Set to | Why |
|---|---|---|
| Web address: `GATEWAY_WEB_URL` and `GATEWAY_PUBLIC_URL` | `https://51-21-160-193.sslip.io` | Where people open the Hub |
| Staff email domain: `GATEWAY_COMPANY_DOMAIN` | **leave it unset** (the default is `swangzavenue.com`) | Decides who may sign in. Setting it to the sslip.io name would lock every `@swangzavenue.com` account out, and `preflight` fails on any other domain unless `GATEWAY_COMPANY_DOMAIN_CONFIRM` repeats it (#323, #324) |

`sslip.io` turns the name back into the IP `51.21.160.193`, so no DNS record is needed, and Caddy gets a real
certificate for it. It is fine for go-live, but a `swangzavenue.com` name is easier to give staff. Moving to one
later means repeating steps 3, 5 and 9 with the new name.

## Steps in order

| # | Who | Step | Done when |
|---|---|---|---|
| 1 | Arnold | **Server checks** before anything else: SSH refuses passwords and security updates are on (`SERVER-DAY.md` section 1). The provider's firewall allows TCP 22, 80, 443 and UDP 443 | `passwordauthentication no`; `unattended-upgrades` is `enabled` |
| 2 | Chief | **Name the commit to deploy** (a merged `main` commit with green CI) | Arnold has the commit written down |
| 3 | Arnold | **Install** (`SERVER-DAY.md` section 3): clone, `git checkout <commit>`, then `sudo bash deploy/setup-gateway-server.sh 51-21-160-193.sslip.io`. The script writes `GATEWAY_PUBLIC_URL` and `GATEWAY_WEB_URL` as `https://51-21-160-193.sslip.io` into `/opt/swangz-gateway/.env` (mode 600) the first time, and never overwrites an existing `.env`. If the script was already run, re-running it after pulling is safe | Script ends with `The gateway is running. Next:` and exit code 0 |
| 4 | Arnold | **Check the environment file.** In `/opt/swangz-gateway/.env`, check: `GATEWAY_WEB_URL=https://51-21-160-193.sslip.io`, `GATEWAY_PUBLIC_URL=https://51-21-160-193.sslip.io`, `GATEWAY_HOST=127.0.0.1`, `GATEWAY_TRUST_PROXY=1`, `GATEWAY_FORCE_HTTPS=1` (the last three come from `.env.example`). `GATEWAY_COMPANY_DOMAIN` is absent. `DEMO_MODEL` is absent. Add `GATEWAY_REQUIRE_FIXED_RETURN=1` (it is not in `.env.example`). Never paste the file into chat | Each line reads as listed |
| 5 | Arnold | **Health and preflight** (`SERVER-DAY.md` section 4): `curl -s https://51-21-160-193.sslip.io/healthz`, then `sudo -u swangz python3 -m gateway health-check --url https://51-21-160-193.sslip.io/healthz --expect-commit <commit>`, then `cd /opt/swangz-gateway && sudo -u swangz python3 -m gateway preflight`. Then the four server checks in section 4 (ufw, port 8787 on 127.0.0.1 only, `User=swangz`, and port 8787 refused from outside) | `healthz` shows `"ok": true` and the commit; `preflight` ends `0 to fix` (warnings "Google sign-in off" and "no provider keys" are expected until steps 7 and 8); the four checks pass. Anything else: stop and send Chief the output |
| 6 | Arnold | **First owner** (`SERVER-DAY.md` section 5): `sudo -u swangz python3 -m gateway add-admin <name>@swangzavenue.com`. Run as `swangz`, not root. Then sign in at `https://51-21-160-193.sslip.io/admin` with that password | `Owner ... created`; the Overview page loads |
| 7 | Arnold | **Google sign-in client** (`SERVER-DAY.md` section 6). In the Google Cloud console add this authorised redirect URI exactly: `https://51-21-160-193.sslip.io/auth/google/callback` (path from `gateway/google.py`, `redirect_uri`). Keep the laptop's old URIs until step 12. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, leave `GOOGLE_REDIRECT_URI` unset (the return address then follows `GATEWAY_WEB_URL`), and run `sudo systemctl restart swangz-gateway` | `preflight` prints the same return address, `GATEWAY_REQUIRE_FIXED_RETURN` shows `ok`, and the sign-in pages show **Continue with Google**. Sign in once with Google at `/admin` |
| 8 | Arnold | **Provider keys**, only for providers used through the gateway (`SERVER-DAY.md` section 7). Into `.env`, then restart | `preflight` no longer warns about keys, still `0 to fix` |
| 9 | Arnold | **Backup check** (`SERVER-DAY.md` section 8): `sudo -u swangz python3 -m gateway backup`, then `sudo -u swangz python3 -m gateway backup-verify --latest`, then `systemctl list-timers \| grep swangz-gateway-backup`. Set `GATEWAY_BACKUP_REMOTE` for a copy off the server (`docs/HUB-DELIVERY.md`), and point an outside uptime monitor at `https://51-21-160-193.sslip.io/healthz` | `integrity ok`; `restore check ok: ... schema vN`; both timers listed. Until the remote is set, `backup` notes that the copy lives only on this server |
| 10 | Arnold | **Data: fresh start or carry over** (`SERVER-DAY.md` section 10). Carry-over uses the backup-first procedure in `docs/HUB-DELIVERY.md`. The team never copies the laptop's database | Decided and, for carry-over, the counts match |
| 11 | Arnold (or the person with each device) | **Point the apps at the address** (`SERVER-DAY.md` section 9). **Staff web app:** give out `https://51-21-160-193.sslip.io/`. **Swangz desktop app:** an enrolled device keeps its old address, so run `swangz logout`, then `swangz login --server https://51-21-160-193.sslip.io` and approve the code in the browser. **Browser extension:** click its icon, **Sign out**, type `https://51-21-160-193.sslip.io`, sign in, **Connect**. **Managed Chrome pack** (company computers): `python3 deploy/chrome-policy/prepare.py --hub-host 51-21-160-193.sslip.io --extension-id <id> --update-url <url> --output <new file>` (`ARNOLD-ONLY.md` item 12; the extension id and update address are still Arnold's to supply). **Netlify:** only if it is kept, change `SWANGZ_GATEWAY` (`deploy/NETLIFY.md`) | The app says `Signed in as ...`; the extension says `Guarding N AI sites.` Extension and Chrome pack steps are UNVERIFIED on a real browser |
| 12 | Arnold | **Cut over, then keep the way back** (`SERVER-DAY.md` section 11): leave the laptop serving until the server has been stable for a few days, then remove the laptop's old redirect URIs from the Google client | Staff use only the new address |

Provider sign-in inside the managed Chrome is **Sign in with Google only, signed in by hand** by the person. The Hub
never stores, shares or types a provider password (`CLAUDE.md`). Which Google hosts that sign-in needs is being
checked by Probe from the providers' own documentation; the Chrome pack is extended after that (Forge).

## If something fails

`SERVER-DAY.md` "If something fails": certificate (`journalctl -u caddy -n 50`; ports 80 and 443 must be open at the
provider), service (`journalctl -u swangz-gateway -n 50`). Send Chief the last 20 lines of output, never `.env`.
