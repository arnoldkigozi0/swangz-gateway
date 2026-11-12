# Server setup rehearsal (12 November 2026)

What was run, what was measured, what was not proven. Written for `docs/SERVER-DAY.md`.

## Method

The team laptop has no Docker, LXD, KVM or root. The script was run inside an unprivileged `bwrap`
sandbox over a fresh Ubuntu 24.04.5 base image (checksum verified against Ubuntu's SHA256SUMS), inside a
user cgroup scope of 1 GB memory, no swap, 100% of one CPU. Source: `origin/feature/managed-workspace`
at `0135ac2`. Everything lived outside the repository. No `.env` of the team's, no provider key and no
real database was used.

Stand-ins: `systemctl` (logs calls, starts the gateway, runs the backup command), `chown` (no-op,
only one user id exists in the sandbox), `journalctl` (tails the log), `policy-rc.d`, a hosts file,
`SKIP_FIREWALL=1`. Caddy was run over the real `Caddyfile` with only the port numbers changed (8080 and
8443), because the sandbox cannot bind 80 or 443.

## Timings (first run, total about 12 min)

| Step | Time |
|---|---|
| Packages (python3, rsync, curl, gnupg, Caddy 2.11.9 from Caddy's repo) | about 580 s, network bound |
| Copy to `/opt/swangz-gateway` and `.env` (207 MB) | about 75 s |
| Service start | 13 s |
| Backup | 1 s |
| Update run (changed tree) | about 2.5 min, of which apt update 138 s |

## Memory

Cgroup peak 854,650,880 bytes for the entire 22-minute session including page cache. Idle:
gateway 32 to 37 MB, Caddy about 52 MB. No out-of-memory kill.

## Checks that passed

- Exit code 0 on the first run. `/healthz`: ok, version 1.0.0; `commit` is empty unless the script
  runs from a git clone.
- Through Caddy: http redirects to https (308); `/`, `/admin`, `/static/ui.js` answer 200;
  `/go/nonexistent` 302. Headers present: HSTS (1 year), X-Frame-Options DENY, nosniff, CSP,
  Referrer-Policy no-referrer. 400 requests took about 21 s.
- `health-check` up (exit 0). `backup` made a verified copy; `backup-verify --latest`: restore check ok,
  schema v25, 61 tables.
- `add-admin` accepts `@swangzavenue.com` and refuses `someone@gmail.com`.
- Update: new code arrived, data and `.env` survived. Rollback to the old tree: code reverted, data and
  `.env` intact. Restore drill from the oldest backup: owners 1 to 0, service healthy.

## Not run

Firewall (ufw); the systemd units themselves and the `swangz` user sandbox (the service ran as the
sandbox's root); ports 80 and 443; a real Let's Encrypt certificate; DNS; a real 1 vCPU VM; data-centre
download speed; Ubuntu 22.04 and 26.04; schema v26 (managed workspace W2) on a server.

## Findings (deploy/ belongs to Sentinel)

1. The copy includes about 199 MB of `docs/screenshots`. Excluding them would cut the 75 s copy and the disk use.
2. The script does not install git; without a git clone `/healthz` shows no commit. SERVER-DAY says to clone.
3. The script creates no first owner (`GATEWAY_BOOTSTRAP_ADMIN` is empty). SERVER-DAY runs `add-admin` as `swangz`.
4. The script says Ubuntu 22.04 or 24.04; only 24.04 was rehearsed.
5. No previous release is kept; `rsync --delete` replaces the code. Rollback after a schema change must be a backup restore.
6. The on-box health timer cannot see the machine being off; an outside monitor is needed.
7. Whether the repository is private, and so whether a deploy key is needed, is UNVERIFIED.
8. How enrolled devices and the extension move to a new address without re-enrolling is UNVERIFIED.
9. Caddy comes from Caddy's own apt repository (2.11.9), not Ubuntu's (2.6.2): a third-party source on the server.
