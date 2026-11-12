# Server day: moving the Hub to its own server (Arnold, 15 November 2026)

One page, in order. Each step says who does it and how long it took in the rehearsal
(`docs/SERVER-REHEARSAL.md`). Rehearsal times are from a slow home link; a data-centre link is
probably faster, which is UNVERIFIED. Nothing here touches the laptop: it keeps running until step 11
says otherwise.

What the rehearsal did not prove, so nobody is surprised: the firewall (ufw), the hardened service
user, binding ports 80/443, a real https certificate, DNS, and a real 1 vCPU machine. The setup
script ran for real on Ubuntu 24.04 under a 1 GB / 1 CPU limit; those parts were skipped or stubbed.

## 0. What you need in hand (about 10 min)

- A card for the server (your purchase; the team buys nothing).
- Access to the DNS for `swangzavenue.com`.
- The Google Cloud console login that owns the existing sign-in client.
- Two work emails for the first owners (`@swangzavenue.com`; the two approved exceptions are
  already allowed).
- Provider keys, only for providers staff will use through the gateway. The Hub never stores a
  vendor password.
- The commit to deploy: Chief names it (a merged `main` commit). Write it down.

## 1. Rent the server (about 10 min, Arnold)

- Ubuntu **24.04** LTS (22.04 is claimed by the script but was not rehearsed; 26.04 was not tried).
- 1 vCPU, 1 GB RAM, **25 GB disk or more**, public IPv4, your SSH public key.
- Firewall at the provider, if it has one: allow TCP 22, 80, 443 and UDP 443.
- Write down the server's IP address.

## 2. Point the name at it (5 min plus waiting, Arnold)

- DNS: an **A record** `ai.swangzavenue.com` to the server IP. If the DNS host is Cloudflare, set it
  to **DNS only** (grey cloud) so Caddy can get its certificate.
- Check from your own computer: `dig +short ai.swangzavenue.com` prints the server IP.
- No domain yet? Use `203-0-113-7.sslip.io` (the IP with dashes). It gets a real certificate too, but
  it is not a name to give staff.

## 3. The one command (about 12 min in the rehearsal, Arnold or whoever holds the login)

On the server, as a user that can use `sudo`:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone <repo address> swangz-gateway        # see "If the clone asks for a password" below
cd swangz-gateway && git checkout <commit Chief named>
sudo bash deploy/setup-gateway-server.sh ai.swangzavenue.com
```

Expected: it prints `== packages`, `== firewall`, and so on, and ends with the address. In the
rehearsal it ended with exit 0.

Rehearsal timings (fresh Ubuntu 24.04, 1 GB memory cap, no swap, 1 CPU):

| Step | Time |
|---|---|
| Packages, including Caddy from Caddy's own apt repository | about 9.5 min (the link was 0.3 to 4 MB/s) |
| Copy of the Hub into `/opt/swangz-gateway` | about 75 s |
| Start the service | 13 s |
| First backup | 1 s |
| **Total** | **about 12 min** |

Memory: the whole session peaked at 0.85 GB including file cache from apt and the copy, so that is
an upper bound. At rest the gateway used about 35 MB and Caddy about 52 MB.

Re-running the script after pulling new code is safe: it updates the code and restarts the service,
and keeps `.env` and the database. It took about 2.5 min.

If the clone asks for a password: it means the repository is private. Do not paste your GitHub
password on a server. Ask Chief for a read-only deploy key; this is UNVERIFIED because the team could not check
the repository's visibility from the laptop.

## 4. Health check (2 min)

```bash
curl -s https://ai.swangzavenue.com/healthz        # {"ok": true, ... "commit": "<the commit>"}
cd /opt/swangz-gateway && sudo -u swangz python3 -m gateway preflight
sudo systemctl status swangz-gateway caddy --no-pager
systemctl list-timers | grep -E 'swangz|backup|health'
```

`preflight` is allowed to warn: "Google sign-in off" and "no provider keys" are expected until steps 6
and 7. A FAIL about the public address means step 2 is not done. If `commit` is empty, the script was
not run from a git clone; redo step 3.

Open `https://ai.swangzavenue.com/` and `/admin` in a browser: both must load with a padlock.

## 5. First owners (3 min each, Arnold)

```bash
cd /opt/swangz-gateway
sudo -u swangz python3 -m gateway add-admin name@swangzavenue.com     # asks for a password twice, 10+ characters
```

Run it as `swangz`, not root, so the database files stay owned by the service user. A non-company
email is refused. Then sign in at `/admin`.

## 6. Google sign-in (10 min, Arnold)

1. Google Cloud console, Credentials, the existing OAuth client, add the authorised redirect URI
   exactly: `https://ai.swangzavenue.com/auth/google/callback`. **Keep the old addresses in the list**
   until step 11 is finished, so the laptop keeps working.
2. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `/opt/swangz-gateway/.env` (file mode 600).
3. `sudo systemctl restart swangz-gateway`. The sign-in pages now show Continue with Google.

Screens and field names: `deploy/NETLIFY.md` Part 2.

## 7. Provider keys (5 min, Arnold)

Add only the ones in use to `/opt/swangz-gateway/.env`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`ELEVENLABS_API_KEY`, `HIGGSFIELD_CREDENTIALS`. Restart the service. Keep them out of chat, email and
the repository. Check: `preflight` no longer warns about provider keys.

## 8. Backups (5 min)

The nightly backup is installed by the script, and a restore check runs weekly. Both stay on the
same server, so set `GATEWAY_BACKUP_REMOTE` in `.env` to copy them off the box (`docs/HUB-DELIVERY.md`).
Take a manual one before every update: `sudo -u swangz python3 -m gateway backup`.

Monitoring: the on-box health timer cannot notice the machine being off. Sign up to an outside
uptime monitor (any free one) that checks `https://ai.swangzavenue.com/healthz` every 5 minutes. This
is your choice and your signup.

## 9. Point the apps at the new address (about 30 min)

Do this only after steps 4 to 6 pass. The first three are UNVERIFIED; they were not rehearsed.

- Staff web app: people open the new address. Update any link you gave out.
- Desktop app: an enrolled device stores the old server address. Whether it can be moved without
  enrolling again is UNVERIFIED; plan on re-enrolling a test device first.
- Browser extension: it stores the Hub address in its settings. Change it on one test computer first.
- Netlify: if the Netlify site is kept, change its `SWANGZ_GATEWAY` setting to the new address
  (`deploy/NETLIFY.md`). Do not change Netlify without deciding to keep it.

## 10. The data: carry it over or start fresh (Arnold decides)

Fresh: nothing to do; people and tools are entered again. Carry over: the verified-backup and
restore procedure in `docs/HUB-DELIVERY.md`. The laptop's database is never copied by the team and
is not touched by this page.

## 11. Rollback

- **Before cutover:** do nothing. The laptop is untouched and still serves everyone; delete the
  new DNS record to abandon the move.
- **After cutover:** point DNS (and the apps from step 9) back at the laptop. Leave the laptop
  running until the server has been stable for a few days.
- **Bad update on the server:** there is no previous release kept and no down-migration. Do not run
  older code on a newer database. Restore the last verified backup instead: stop the service,
  `gunzip -c <backup>.gz > data/gateway.db.restoring`, move it over `data/gateway.db`, delete
  `gateway.db-wal` and `-shm`, check out the older commit, run the setup script, start. Rehearsed:
  the restore returned a healthy service and the older data. Check the older commit's schema is not older
  than the backup's.

## If something fails

- Certificate never arrives: `dig` must show the server IP, ports 80 and 443 must be open at the
  provider, and the name must not be behind the Cloudflare proxy. `journalctl -u caddy -n 50`.
- Service will not start: `journalctl -u swangz-gateway -n 50`.
- Ask Chief with the last 20 lines of output. Never send `.env` or the output of `cat .env`.
