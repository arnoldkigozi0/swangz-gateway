# Picking this up on another machine

Read `../CLAUDE.md` first (what the project is and its conventions), then `STATE.md` (what is built
and what is next). This file is only about **moving to a different computer**.

```bash
git clone https://github.com/arnoldkigozi0/swangz-gateway.git
cd swangz-gateway
claude                      # Claude Code reads CLAUDE.md automatically
python3 -m unittest discover -s tests -t .    # should be 151 tests, all passing
```

Python 3.10+ and git are the only requirements. There is nothing to install — the whole gateway is
the standard library.

## What is in the repo, and what is not

**In git, so it travels by itself:** all the code, the 49-tool catalog, both front-ends, the browser
extension, the tests, the deploy guides, and these docs.

**Deliberately NOT in git** (`.gitignore`), because secrets must never go to GitHub:

| Not in git | What it is | How to move it |
|---|---|---|
| `.env` | provider keys, the Google client secret, addresses | copy by hand, see below |
| `data/gateway.db` | **the record** — people, tools, turns, launches, every request | copy only if this machine becomes the main one |
| `CREDENTIALS.txt` | the demo sign-ins | re-create, or copy by hand |

## Moving the secrets safely

**Do not** email them, paste them into a chat, or commit them. Use a USB stick, or type them again
from the source they came from.

On the old machine the live settings are in `~/swangz-gateway-demo/.env`. On the new machine:

```bash
mkdir -p ~/swangz-gateway-demo
cp .env.example ~/swangz-gateway-demo/.env
nano ~/swangz-gateway-demo/.env     # fill in from the old machine, then:
chmod 600 ~/swangz-gateway-demo/.env
```

`.env.example` lists every setting with a note on what it is for. The ones that matter today:

- `GATEWAY_WEB_URL` — `https://swangz-ai.netlify.app`
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from the Google Cloud project `swangz-ai`; the client
  id is also visible in the Google console, the secret can be regenerated there if it is lost
- provider keys — still empty; Swangz has not supplied real ones

**If the Google secret is lost:** Google Cloud console → project `swangz-ai` → Clients → "Swangz Ai"
→ add a new secret, paste it into `.env`, restart. Nothing else changes.

## The database

`data/gateway.db` holds everything that has happened — people, who was assigned what, turns, launches,
every recorded request. It is one file.

- **Starting fresh on the new machine?** Do nothing. It is created on first run, the 49-tool catalog
  seeds itself, and `GATEWAY_BOOTSTRAP_ADMIN` / `..._PASSWORD` make the first owner account.
- **Moving the real thing across?** Stop the gateway on the old machine first, then copy
  `gateway.db` (and any `-wal` / `-shm` files next to it). Migrations run themselves on start-up, so a
  database from an older schema upgrades without any work.

## Where things stand right now (3 Oct 2026)

- **Live:** `https://swangz-ai.netlify.app` (staff) and `/admin` (console). Netlify project
  `swangz-ai` builds from `main`, base directory `deploy/netlify`.
- **Netlify needs one variable:** `SWANGZ_GATEWAY` = the gateway's https address. It is currently the
  laptop's Cloudflare quick-tunnel link, **which changes every time the tunnel restarts**. When it
  changes: Netlify → Site configuration → Environment variables → edit it → Deploys → Trigger deploy.
- **Google sign-in** works, in Testing mode, with two test users (`arnoldkigozi0@gmail.com`,
  `webdev02022007@gmail.com`). Publishing it needs the Branding page completed first.
- **Not done:** real provider keys, and a permanent home for the gateway.

## The next job, in order

1. **A small VPS (~$5/month)** for the gateway, at `ai.swangzavenue.com`. `deploy/` has the systemd
   unit and a Caddyfile; Caddy gets the certificate by itself. Then set `GATEWAY_PUBLIC_URL`, point
   Netlify's `SWANGZ_GATEWAY` at it, and the changing-link problem is gone for good.
2. **Real provider keys** from Swangz, into `.env`.
3. **The shared workspace server** — the gateway side (browser pool, a sign-in per turn) is built; the
   Neko server it talks to is not. `deploy/WORKSPACE.md`, and read its warnings before spending money.

## Things that will trip you up

- **`pkill -f <pattern>` can kill the calling shell.** Match the exact process with
  `ps -eo pid,args | awk ...` instead.
- **The CSP blocks inline `style=""`.** Set styles with a class or `element.style.x`, never a style
  attribute string.
- **A request's record is written just after its reply ends** — tests and Studio must wait for it.
- **Migrations are append-only.** Add a new entry to `SCHEMA` in `db.py`; never edit an old one.
- **Tests before every commit**, and no AI attribution in commit messages or public copy.
