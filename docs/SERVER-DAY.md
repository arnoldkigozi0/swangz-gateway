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
- After your first SSH login, check that the server refuses passwords and installs security
  updates by itself:

  ```bash
  # Not run here, needs the server
  sudo sshd -T | grep -E '^(passwordauthentication|permitrootlogin)'   # "no" and "prohibit-password" (or "no")
  systemctl is-enabled unattended-upgrades                             # "enabled"
  ```

  If either is wrong, fix it before step 3: set `PasswordAuthentication no` in
  `/etc/ssh/sshd_config` and run `sudo systemctl reload ssh`, or
  `sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades`.

## 2. Point the name at it (5 min plus waiting, Arnold)

- DNS: an **A record** `ai.swangzavenue.com` to the server IP. If the DNS host is Cloudflare, set it
  to **DNS only** (grey cloud) so Caddy can get its certificate.
- Check from your own computer: `dig +short ai.swangzavenue.com` prints the server IP. Not run here, needs the server and DNS.
- No domain yet? Use `203-0-113-7.sslip.io` (the IP with dashes). It gets a real certificate too, but
  it is not a name to give staff.

## 3. The one command (about 12 min in the rehearsal, Arnold or whoever holds the login)

On the server, as a user that can use `sudo`:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/arnoldkigozi0/swangz-gateway.git swangz-gateway
cd swangz-gateway && git checkout <commit Chief named>
sudo bash deploy/setup-gateway-server.sh ai.swangzavenue.com
```

Expected: `git checkout` says `HEAD is now at <commit> ...`. The script prints `== packages`, `== firewall`,
`== the gateway, in /opt/swangz-gateway`, `== Caddy: https://ai.swangzavenue.com`, `== the service`,
`== nightly backup`, then `The gateway is running. Next:` and the staff and control-room addresses.
`echo $?` straight after prints `0`. In the rehearsal it ended with exit 0.

Caddy comes from Caddy's own apt repository rather than Ubuntu's, because Ubuntu's 2.6.2 is behind on
fixes; apt checks every package against that repository's signing key, which the script fetches once over https.

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

The repository is public (checked 14 Nov with `gh repo view`), so the clone needs no login. If it ever
asks for a password, the repository has been made private: do not paste a GitHub password on a server,
ask Chief for a read-only deploy key.

## 4. Health check (2 min)

```bash
curl -s https://ai.swangzavenue.com/healthz        # {"ok": true, "uptime_seconds": N, "version": "...", "commit": "<the commit>"}
cd /opt/swangz-gateway
sudo -u swangz python3 -m gateway health-check --url https://ai.swangzavenue.com/healthz --expect-commit <commit>
                                                   # up: version ..., commit <the commit>, running N seconds
sudo -u swangz python3 -m gateway preflight         # one line per check (OK / WARN / FAIL), then
                                                   # preflight: 0 to fix, N to review. Nothing was contacted and nothing was changed.
# Not run here, needs the server (systemd and timers were stubbed in the rehearsal)
sudo systemctl status swangz-gateway caddy --no-pager
systemctl list-timers | grep -E 'swangz|backup|health'
```

`health-check` saying `wrong build` means the checkout in step 3 is not the commit Chief named.
`preflight` is allowed to warn: "Google sign-in off" and "no provider keys" are expected until steps 6
and 7. A FAIL about the public address means step 2 is not done. If `commit` is empty, the script was
not run from a git clone; redo step 3.

After step 6, run `preflight` again: `GATEWAY_REQUIRE_FIXED_RETURN` must show `ok`.

Open `https://ai.swangzavenue.com/` and `/admin` in a browser: both must load with a padlock.

The rehearsal could not test the firewall, the service user or the port binding, so check them here.
All four must pass before anyone signs in:

```bash
# Not run here, needs the server
sudo ufw status verbose                    # Status: active; allowed only SSH, 80/tcp, 443/tcp and 443/udp
sudo ss -ltnp | grep 8787                  # 127.0.0.1:8787 only, never 0.0.0.0 or [::]
systemctl show swangz-gateway -p User      # User=swangz
```

And from your own computer, not the server:

```bash
curl -m5 http://<server ip>:8787/healthz   # must fail (time out or connection refused)
```

If any of these is wrong, stop and send Chief the output; do not continue to step 5.

## 5. First owners (3 min each, Arnold)

```bash
cd /opt/swangz-gateway
sudo -u swangz python3 -m gateway add-admin name@swangzavenue.com     # asks for a password twice, 10+ characters
```

Expected: `Owner name@swangzavenue.com created`. Run it as `swangz`, not root, so the database files stay
owned by the service user. A non-company email is refused (the rehearsal tried `someone@gmail.com`). Then
sign in at `/admin`: the Overview page loads and your name is in the avatar menu.

## 6. Google sign-in (10 min, Arnold)

1. Google Cloud console, Credentials, the existing OAuth client, add the authorised redirect URI
   exactly: `https://ai.swangzavenue.com/auth/google/callback`. **Keep the old addresses in the list**
   until step 11 is finished, so the laptop keeps working.
2. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `/opt/swangz-gateway/.env` (file mode 600).
3. Add the line `GATEWAY_REQUIRE_FIXED_RETURN=1` to the same `.env`. It is required in production:
   without it `preflight` fails once the Google client is set, and Google sign-in could take its
   return address from a request's Host header.
4. `sudo systemctl restart swangz-gateway`. The sign-in pages now show Continue with Google. Run
   `preflight` again (step 4): `GATEWAY_REQUIRE_FIXED_RETURN` must say `ok`.

Screens and field names: `deploy/NETLIFY.md` Part 2.

## 7. Provider keys (5 min, Arnold)

Add only the ones in use to `/opt/swangz-gateway/.env`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`ELEVENLABS_API_KEY`, `HIGGSFIELD_CREDENTIALS`. Restart the service. Keep them out of chat, email and
the repository. Check: `preflight` no longer warns about provider keys, and still ends `0 to fix`.
`preflight` prints only whether a key is set, never the key.

## 8. Backups (5 min)

The nightly backup is installed by the script, and a restore check runs weekly. Both stay on the
same server, so set `GATEWAY_BACKUP_REMOTE` in `.env` to copy them off the box (`docs/HUB-DELIVERY.md`).
Take a manual one now and before every update, then check it opens:

```bash
cd /opt/swangz-gateway
sudo -u swangz python3 -m gateway backup               # backup <path>.gz (N bytes, sha256 ...) integrity ok
sudo -u swangz python3 -m gateway backup-verify --latest
                                                       # restore check ok: <path> (0.0 hours old, schema vN, N tables)
systemctl list-timers | grep swangz-gateway-backup     # the nightly and weekly timers, with their next run (not run here, needs the server)
```

Until `GATEWAY_BACKUP_REMOTE` is set, `backup` also prints `note: GATEWAY_BACKUP_REMOTE is not set, so this
copy lives only on this server`. With it set, the last line is `sent off the server to <remote>`.

Monitoring: the on-box health timer cannot notice the machine being off. Sign up to an outside
uptime monitor (any free one) that checks `https://ai.swangzavenue.com/healthz` every 5 minutes. This
is your choice and your signup.

## 9. Point the apps at the new address (about 30 min)

Do this only after steps 4 to 6 pass. The staff web app and extension bullets are UNVERIFIED; they were not rehearsed.

- Staff web app: people open the new address. Update any link you gave out.
- Desktop app: an enrolled device keeps the old server address, and there is no command to change it
  (the app refuses to connect elsewhere while it is enrolled). Move each device by signing out, then
  connecting again: `swangz logout`, then `swangz login --server https://ai.swangzavenue.com` and approve the code in the browser as on the first day. Sign out while the
  laptop is still serving, so the old key is disconnected there. Proven against the test server, not on a real device:
  `tests/test_client.py` `test_moving_to_a_new_server_address_means_signing_out_then_connecting_again`.
- Browser extension: it keeps the Hub address it was connected with. On one test computer first: click
  the extension's icon, press **Sign out**, type `https://ai.swangzavenue.com` in the address box, sign in
  with the person's Hub email and password, press **Connect**. Expected: `Guarding N AI sites.` Not run here, needs the server; not rehearsed
  on a real browser.
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

## 12. Managed workspace dry run on the server (about 25 min, a test device only)

Run this only when the deployed commit includes the managed workspace (`feature/managed-workspace` merged into
`main`, Arnold's written approval on #204). Otherwise skip it: the server works without it. Use one Linux test
computer with Google Chrome or the distribution's Chromium (.deb) installed, a test staff person, and a tool of kind
`site` assigned to them. Never a staff member's own computer or account. The full recording version of these steps
is `docs/W-DEMO-PLAN.md`; this is the short check that the server serves them.

| # | Who, where | Command or action | Expected |
|---|---|---|---|
| 1 | Server | `sudo -u swangz python3 -m gateway backup-verify --latest` | `restore check ok: ... schema v26` or higher |
| 2 | Test device | `swangz logout` (if enrolled), then `swangz login --server https://ai.swangzavenue.com --name "Server-day test"` | `To connect this device, open <link> and check that the code is <code>. Then press Approve. Waiting…` |
| 3 | Test person's browser | open the link, check the code matches, press Approve | the terminal says `Signed in as <test person> (personal device).` (or `company device`) |
| 4 | Test device | `swangz apps`, then `swangz open gemini` | `Opened in the Swangz workspace window.`; Chrome opens on gemini.google.com with `--user-data-dir=.../browser-profiles/...`; the default browser starts nothing new |
| 5 | Console | Activity, Tools opened | one launch for this device, outcome opened |
| 6 | Test device | `swangz open gemini` again | still one folder in `browser-profiles`; a new tab in the same window is UNVERIFIED |
| 7 | Owner, signed in to `/admin` | `POST /admin/api/devices/<device_id>/workspace` with `{"action": "suspend"}` and header `x-gateway-admin: 1` (the device id is the `device_id` field of `GET /admin/api/devices`; it is not shown on the Devices page or by `swangz status`) | 200; an audit log entry |
| 8 | Test device | `swangz sync`, then `swangz open gemini` | the window closes; `This device's workspace is paused. Close any open workspace window, and ask your admin.` The app refuses on its own after the check-in, so the Hub keeps no row for this Open; a refused row (rule `workspace_suspended`) appears in Activity only for an Open sent before the check-in |
| 9 | Owner | same call with `{"action": "reactivate"}`, then `swangz sync` and `swangz open gemini` on the device | opens again; a sign-in made before step 7 is still there |
| 10 | Owner | same call with `{"action": "retire"}`, then `swangz sync` on the device | the folder under `browser-profiles` is gone; `swangz open gemini` says `Your admin removed the Swangz workspace from this device, ...` |
| 11 | Test device | `swangz logout` | the device shows as disconnected on Devices |

Any row that does not match: stop, note the row number and the exact message, and send it to Chief. The server's
part is rows 1, 5, 7 and the console checks; the client part was already checked on the team laptop and in CI
(`docs/W-DEMO-PLAN.md`). Not proven on the server before 15 Nov: the policy pack (it is installed on company
computers, not on the server), Windows and macOS devices, and the 15-minute heartbeat without `swangz sync`.

## If something fails

- Certificate never arrives: `dig` must show the server IP, ports 80 and 443 must be open at the
  provider, and the name must not be behind the Cloudflare proxy. `journalctl -u caddy -n 50`.
- Service will not start: `journalctl -u swangz-gateway -n 50`.
- Ask Chief with the last 20 lines of output. Never send `.env` or the output of `cat .env`.
