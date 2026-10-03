# Swangz AI Gateway — project guide

This file is the starting point for anyone (or any assistant) opening this repo. Read it, then
`docs/STATE.md` for the current status and the roadmap. Keep both up to date as the project moves.

## What this is

An enterprise AI-tool **licensing and access-control platform** for Swangz Avenue. Staff reach AI
through one controlled door; the company keeps its provider keys, decides which tools each person
may use, and keeps a record for billing, security and support.

Two apps on one address, plus a browser extension:

| Where | What |
|---|---|
| `/` | **Swangz AI** — the staff app: a launchpad of the company's AI tools. **Open** goes through `/go/<tool>`, which checks access, logs the launch and sends the person to the tool's company sign-in link (SSO) or website. Studio for voice/image/video; connect coding tools; manage own devices |
| `/admin` | **Control room** — owners and viewers: live requests and launches, people (budgets, end dates, suspend, remove all tools), the tool catalog (add / edit / remove / delete, logos, sign-in method), who can use each tool (with end dates), subscriptions, **Licences & spend** (seats vs real use, idle seats, renewals), access requests, activity & records, settings, audit log |
| `extension/` | **Swangz AI Access** — a browser extension that governs AI *websites* (ChatGPT, Midjourney, …): opens the ones a person is entitled to, blocks the rest, logs access-level use only |

The core rule everywhere: **a tool is enabled for a person only when the company subscription is
active AND the person is assigned it** (directly or through their department). API and dev tools run
on the company key, so they gate on assignment alone; Claude Code and Codex are assignment-only.
A grant can carry an end date, and a person's whole account can (`access_until`).

**How people get into website tools — deliberately not a shared login.** The company pays one bill;
each person gets their own seat on the company plan (`signin = seat`) or signs in through the tool's
single sign-on with their Swangz account (`signin = sso`, with the SSO link as `launch_url`). Do **not**
build a mechanism that types one shared company login into many people's browsers: most AI vendors'
terms forbid sharing one account, and they suspend accounts for it. Arnold asked for that once
(Oct 3, 2026); it was declined and the seat/SSO model was built instead.

## Stack and layout

- **Python 3.10+, standard library only.** Nothing to install. One SQLite file (`data/gateway.db`).
- Front ends are plain JS/CSS on a self-hosted Archivo design system; strict Content-Security-Policy.
  Design tokens ("Porcelain & Midnight") live in `static/tokens.css`: light porcelain page, white
  cards, midnight-navy ink and primary, champagne gold accent; a navy (never black) dark theme on
  `html[data-theme="dark"]`, toggled in both apps and remembered per browser.

```
gateway/
  server.py     HTTP server, routing, the per-request rule checks, static files, health
  proxy.py      the core: one request from arrival through forward/stream to the record
  parse.py      reads each provider's dialect (Anthropic / OpenAI / ElevenLabs / Higgsfield)
  catalog.py    the 49-tool catalog, descriptions/colours, sign-in methods, launch targets, host matching
  icons.py      tool logos: fetched once server-side (public hosts only, sniffed, size-capped) or uploaded
  entitle.py    who may use which tool, and why (enabled / locked / not_assigned / past_due / suspended)
  store.py      request bodies stored once per message by hash; retention clean-up
  pricing.py    model price table and cost per request
  live.py       requests in flight, and cutting them
  db.py         SQLite + append-only numbered migrations (currently schema v6)
  security.py   key/password hashing, sign-in throttle, per-person rate limiter
  admin.py      control-room API
  staff.py      staff-app API, /go/<tool> launches, Studio, and the browser access gate
  google.py     Sign in with Google (OIDC code flow) for staff and admins: /auth/google/start|callback
  guides.py     per-tool connection steps shown to staff
  config.py     settings from the environment; provider definitions
  static/       index.html + portal.* (staff), admin.html + admin.* (console), tokens.css, fonts/
extension/      the MV3 browser access gate (its own README)
tests/          unittest suite + fake_upstream.py (a stand-in for every provider)
deploy/         systemd unit, Caddyfile, laptop-demo.sh
docs/STATE.md   current status, what's done, what's next  ← read this after this file
```

## Working conventions (follow these)

- **Tests before every commit.** `python3 -m unittest discover -s tests -t .` — keep it green. Add a
  test for each change; the suite runs against `tests/fake_upstream.py`, never a real provider.
- **Migrations are append-only.** Add a new entry to `SCHEMA` in `db.py`; never edit an old one.
  Existing databases upgrade themselves on start-up.
- **Routes** use the `@route` decorator (owner/viewer and signed-in/not), and get a permissions test.
- **Secrets never get committed.** `.gitignore` covers `.env`, `data/`, `*.db`. Provider keys live
  only in the environment; staff keys are stored as a SHA-256 only.
- **No AI attribution** in commits, docs, READMEs, or anything that could be shared — it is Arnold's
  work under his name. Write commit messages and public copy with no "generated by" / "Co-Authored-By"
  lines. (This is a standing instruction; it is not about denying AI help if someone directly asks.)
- **Website monitoring is an access gate + access-level logging only** (which tool, when, how long —
  never page content or keystrokes). This is deliberate and keeps it lawful under Uganda's Data
  Protection and Privacy Act. Do not add covert content capture of third-party sites. Full-content
  logging exists only as an admin setting, off by default, with staff told in the extension's policy.

## Run it

```bash
python3 -m gateway add-admin <name>      # first owner (asks for a password)
python3 -m gateway serve                 # http://localhost:8787
```

Command line: `serve | add-admin | add-person | issue-key | revoke-key | people | pause | resume | purge`.

**Demo online from a laptop** (a stand-in model answers, so nothing is spent):

```bash
DEMO_MODEL=1 bash deploy/laptop-demo.sh  # starts the gateway + a free https tunnel, prints the links
```

**Configuration** (environment): provider keys `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`ELEVENLABS_API_KEY`, `HIGGSFIELD_CREDENTIALS`; address `GATEWAY_PUBLIC_URL`; `GATEWAY_HOST/PORT/DATA`;
`GATEWAY_TRUST_PROXY` / `GATEWAY_FORCE_HTTPS` behind a proxy or tunnel; `GATEWAY_FETCH_ICONS=0` to stop
logo fetching (the tests set it); `GATEWAY_WEB_URL` (the address people open, e.g. a Netlify front door);
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (both set = "Continue with Google" appears; admins match by
username = Google email); `GATEWAY_CORS_ORIGINS` to let a Netlify-hosted front-end call the API (see `deploy/NETLIFY.md`); `GATEWAY_TZ_OFFSET`. Runtime
settings (retention, rate limit, kill switch, …) live in the control room under Settings.

## Picking the project up on a new machine

With git and Claude Code installed and signed in:

```bash
git clone https://github.com/arnoldkigozi0/swangz-gateway.git
cd swangz-gateway
claude            # Claude Code reads this file automatically; then open docs/STATE.md
```

Then `python3 -m unittest discover -s tests -t .` to confirm the suite is green, and
`python3 -m gateway serve` (or the demo script) to run it. The database and `.env` do not travel with
the repo — on a new machine you start with a fresh `data/gateway.db` and your own keys.
