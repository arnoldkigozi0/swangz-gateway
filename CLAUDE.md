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
| `/` | **Swangz AI** — the staff app: Home (a restrained hero, notifications, *Your approved AI tools*), Tools (the whole catalogue: search, categories, sort, a details drawer per tool saying why you have it, how sign-in works and what's recorded), Studio, Devices (device cards + a step-by-step Connect flow), Requests (your access requests + notifications), Privacy (*How Swangz AI works* — what is and isn't recorded, retention, who can see it). **Open** goes through `/go/<tool>`, which checks access, logs the launch and sends the person to the tool's company sign-in link (SSO) or website |
| `/admin` | **Control room** — Overview, Live (in-flight requests; *Inspect* follows one into its record), Needs attention, Activity (Timeline = who did what, when, where · Who used what · AI requests · Tools opened · Websites visited), People and person profiles, Devices and device pages, Tools (each with its own usage profile), Access requests, Licences & spend (incl. *What cost us money?*), Security, Audit log, Settings. Ctrl+K opens a command menu that searches everything. Dense pages are split with `pageTabs()`, which builds each tab on demand and keeps the chosen one in `?tab=`; time ranges and filters live in the address too. |
| `extension/` | **Swangz AI Access** — a browser extension that governs AI *websites* (ChatGPT, Midjourney, …): opens the ones a person is entitled to, blocks the rest, logs access-level use only |

The core rule everywhere: **a tool is enabled for a person only when the company subscription is
active AND the person is assigned it** (directly or through their department). API and dev tools run
on the company key, so they gate on assignment alone; Claude Code and Codex are assignment-only.
A grant can carry an end date, and a person's whole account can (`access_until`).

**How people get into website tools.** `tools.signin` is one of:

- `sso` — the tool's single sign-on, with their Swangz Google account (`launch_url` = the SSO link);
- `seat` — their own seat on the company plan, invited to their work email (Swangz pays one bill);
- `shared` — **one company account the team takes turns on** (`gateway/turns.py`): the portal hands it
  to one person at a time for `turn_minutes`, blocks everyone else at the gate, and the extension
  signs the browser out when the turn ends or Chrome restarts, so vendor credit history can be
  matched to a person. With a workspace, Open gives each turn-holder a **company browser of their own**
  (Neko on a Swangz server, signed in once by an admin) instead of the tool's site, so several people
  can work at once and nobody sees the password. Production: `workspace_mode = 'agent'` — the **Swangz
  Workspace Agent** (`workspace_agent/agent.py`, on the workspace server, next to Docker) starts the
  browser, makes a Neko sign-in for the turn, and on release deletes it and recycles the container; the
  gateway holds only the agent's URL + token. **Where the agent runs is the admin's choice, one place at a
  time** (Settings → Company browsers; `workspace.HOSTS`): the rented server (env) or one of Swangz's own
  computers, the Windows PC or the Mac (`workspace_agent/computer.py`: Docker Desktop + a Cloudflare quick
  tunnel + a TURN relay the gateway hands out; it checks in at `/api/workspace/hello` with its key and gets
  its browser list from the shared tools). Switching ends turns at the old place; each turn's `ws_host`
  says where to release it. Arnold asked for this on Oct 6, 2026 ("one at a time, not both").
  Fallback: fixed browsers listed in `workspace_url` (with
  `GATEWAY_WORKSPACE_TOKEN`, the gateway manages their sign-ins itself) — `deploy/WORKSPACE.md`;
- `own` — their own account, access still gated and logged;
- `api` — nothing to sign in to; it runs on the company key through the gateway.

**Do not build credential injection** — storing the shared account's password and having the portal or
extension type it into a tool's login form. Arnold asked three times (Oct 3, 2026). The third time he
proposed a remote browser on a VPS instead, which **is** a legitimate answer to "arrive already signed
in" and is now supported as `workspace_url`: the admin signs that browser in by hand, once, and the
gateway only ever redirects to it. That is the shape to build (Oct 3: built on **Neko**, not Kasm —
Kasm's free edition is non-commercial only and its Starter plan has no API; Neko is Apache-2.0). On
Oct 3 he also asked for several people on one tool at once: that is a **pool of browsers**, one per
person, sized by `seats_at_once`; then for the gateway to allocate them through a small agent rather
than a hand-kept list — built as the Workspace Agent. Browser slots stay fixed in the agent's config,
because each Chromium profile must be signed in by hand once and can't be shared by two running browsers;
"dynamic" means containers start on demand, recycle after each turn and stop when idle. What stays out is the gateway holding
the password and typing it for people. Reasons, in order: the
password would have to sit in every staff browser where anyone can read it; it breaks on 2FA, captcha
and bot checks, so it is unreliable the moment a vendor changes a form; vendors' terms forbid one
account being used by many people and they suspend accounts for it; and it does not actually solve
the problem he has, which is *attribution*. Turns solve attribution. If asked again, explain turns
rather than reopening this.

## Stack and layout

- **Python 3.10+, standard library only.** Nothing to install. One SQLite file (`data/gateway.db`).
- Front ends are plain JS/CSS on a self-hosted Archivo design system; strict Content-Security-Policy.
  Design tokens ("Obsidian & Gold") live in `static/tokens.css`: near-black neutral surfaces (no blue
  cast), champagne gold as the brand, bright mint/sky/coral for states. **Dark is the default**; a
  light "Porcelain" theme is on `html[data-theme="light"]`, toggled in both apps and remembered per
  browser. Arnold asked for black over navy on Oct 3, 2026.
- **Both apps are built from shared primitives** in `static/ui.js` + `static/ui.css` (`window.SUI`):
  icons, theme, time formatting (gateway / your / UTC time, chosen per browser), status dots that always
  carry a word, skeleton/empty/error states, tooltips, accessible charts (validated colours, a table
  view, arrow-key reading), sortable tables that turn into cards on phones, the time-range control and
  the command menu. Build new UI from these rather than one-off markup. The console's core is
  `admin.js` (frame, nav, routing, shared event renderers, exported as `window.SWA`); its pages live in
  `admin-monitor.js`, `admin-records.js`, `admin-govern.js` and `admin-money.js` and register routes
  with `SWA.page()`. Show evidence honestly: a cost is *estimated*, a platform comes *from the user
  agent*, an address is *not geolocated* — never present an inference as a fact.

```
gateway/
  server.py     HTTP server, routing, the per-request rule checks, static files, health
  proxy.py      the core: one request from arrival through forward/stream to the record
  parse.py      reads each provider's dialect (Anthropic / OpenAI / ElevenLabs / Higgsfield)
  catalog.py    the 49-tool catalog, descriptions/colours, sign-in methods, launch targets, host matching
  turns.py      shared company accounts handed out one turn at a time, so their spend has a name on it
  workspace.py  company browsers for shared accounts: the Workspace Agent's client, and fixed-list mode
  icons.py      tool logos: fetched once server-side (public hosts only, sniffed, size-capped) or uploaded
  entitle.py    who may use which tool, and why (enabled / locked / not_assigned / past_due / suspended)
  store.py      request bodies stored once per message by hash; retention clean-up
  pricing.py    model price table and cost per request
  live.py       requests in flight, and cutting them
  db.py         SQLite + append-only numbered migrations (currently schema v12)
  security.py   key/password hashing, sign-in throttle, per-person rate limiter
  admin.py      control-room API
  insight.py    the control room's read-only lenses: trends, attention, security, devices, timeline, usage, spend, search
  staff.py      staff-app API, /go/<tool> launches, Studio, and the browser access gate
  google.py     Sign in with Google (OIDC code flow) for staff and admins: /auth/google/start|callback
  guides.py     per-tool connection steps shown to staff
  config.py     settings from the environment; provider definitions
  static/       ui.js + ui.css (shared), index.html + portal.* (staff), admin.html + admin*.js + admin.css (console), tokens.css, fonts/
extension/      the MV3 browser access gate (its own README)
workspace_agent/ agent.py — the Swangz Workspace Agent, alone on the workspace machine (stdlib);
                computer.py — runs it on a Windows PC or Mac: setup, tunnel, start with the computer
tests/          unittest suite + fake_upstream.py (a stand-in for every provider)
deploy/         systemd unit, Caddyfile, laptop-demo.sh, NETLIFY.md, WORKSPACE.md
docs/STATE.md   current status, what's done, what's next  ← read this after this file
docs/HANDOFF.md moving to another machine: what is NOT in git, and how to carry it across
docs/GO-LIVE.md the rollout checklist (who does what) and the monthly cost — Swangz uses paid accounts, not API keys
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
username = Google email); `GATEWAY_WORKSPACE_AGENT` / `GATEWAY_WORKSPACE_AGENT_TOKEN` (the Workspace
Agent on the rented server); `GATEWAY_TURN_CLOUDFLARE_KEY_ID` / `_TOKEN` or `GATEWAY_TURN_URLS` /
`GATEWAY_TURN_SECRET` (the video relay for company browsers on Swangz's own computers);
`GATEWAY_WORKSPACE_TOKEN` (fallback: fixed browsers' Neko API token); `GATEWAY_CORS_ORIGINS` to let a Netlify-hosted front-end call the API (see `deploy/NETLIFY.md`); `GATEWAY_TZ_OFFSET`. Runtime
settings (retention, rate limit, kill switch, …) live in the control room under Settings.

## Picking the project up on a new machine

**See `docs/HANDOFF.md`** for the full version — what travels in git, what does not (`.env`,
`data/gateway.db`), and how to move the secrets safely.

With git and Claude Code installed and signed in:

```bash
git clone https://github.com/arnoldkigozi0/swangz-gateway.git
cd swangz-gateway
claude            # Claude Code reads this file automatically; then open docs/STATE.md
```

Then `python3 -m unittest discover -s tests -t .` to confirm the suite is green, and
`python3 -m gateway serve` (or the demo script) to run it. The database and `.env` do not travel with
the repo — on a new machine you start with a fresh `data/gateway.db` and your own keys.
