# Swangz AI Hub — project guide

This file is the starting point for anyone (or any assistant) opening this repo. Read it, then
`docs/STATE.md` for the current status and the roadmap. Keep both up to date as the project moves.

## What this is

An enterprise AI-tool **licensing and access-control platform** for Swangz Avenue. Staff reach AI
through one controlled door; the company keeps its provider keys, decides which tools each person
may use, and keeps a record for billing, security and support.

Two apps on one address, plus a browser extension:

| Where | What |
|---|---|
| `/` | **Swangz AI Hub** — the staff app: Home (a launchpad: a state-aware hero whose one action goes back to the tool you opened last, three compact recent tool rows, and beside them Updates and allowance when visible), Tools (the whole catalogue: search, categories, sort, a details drawer per tool saying why you have it, how sign-in works and what's recorded), Studio (Create · Your creations), Devices (Connected · Connect a tool · Disconnected; the key is shown once), Requests (Updates · Access requests · Procurement · Department reports — the bell opens Updates), Weekly reports (mandatory per-tool accountability), Adoption & impact (declarations, scoped department views, analytics, projects and history), Projects (focused deliverable detail), Privacy (*How Swangz AI Hub works* — six sections with an index). A page's views live in `?view=` (`viewTabs()` in `portal.js`). **Open** goes through `/go/<tool>`, which checks access, logs the launch and sends the person to the tool's company sign-in link (SSO) or website |
| `/admin` | **Control room** — MONITOR: Overview, Live (in-flight requests; *Inspect* follows one into its record), Needs attention, Activity (Timeline = who did what, when, where — requests, opens, visits, shared turns, sign-ins and access changes · Who used what · AI requests · Tools opened · Websites visited), Health. GOVERN: People, Access requests, Tools, **Models** (the registry), **Policies** (rules + Simulate + Explain a decision). MONEY: Licences & spend (incl. *What cost us money?*), **Reports**. TRUST: Security, **Incidents**, Devices, Audit log (before/after, reason, outcome), Settings (a grouped rail — Gateway: Access & privacy · Purpose & location · Providers & pricing · Company browsers; Emergency; Console access: Console users · Your account — each category opening with a header that holds its sections; Access & privacy is Records · Safeguards · Staff controls). A tool's profile is a side sheet (Overview · Usage · Access · Subscription · Configuration · Workspace for shared accounts); a person's is Overview · Access · Activity · Devices · Security · Account. A **notifications bell** sits by the search. Ctrl+K opens a command menu that searches everything. Dense pages are split with `pageTabs(base, params, tabs, opts)`: each tab builds on demand, the choice lives in `?tab=` (or `opts.param`, e.g. Settings' `?section=`, with `opts.clears` so a parent resets its child), every switch is a history entry, Back/Forward switch in place, and a form with unsaved changes calls `A.setDirty(fn)` so leaving asks first. Time ranges and filters live in the address too (`A.keepParams`). Where each kind of information lives, and why, is `docs/UI.md` — one home per kind, summaries elsewhere link to it. Arnold asked for fewer tiles (Oct 7, 2026): lists put their counts in the filter tabs, headline numbers sit in one `.kpis` strip or a slim `.statline`, and long catalogues are tables, not cards. Settings-style pages use `A.settingRow()` / `A.switchInput()` and `pageTabs(…, { vertical: true })`; a panel's save actions go in `A.panelFoot()`. |
| `swangz_client/` | **The Swangz app** — what people install on their own devices (Windows, macOS, Linux; phones use the installable staff web app): a desktop window (Home · Apps · Packages · This device) over a shared core that signs the device in with a code approved in the person's own browser (`/device`), installs exactly what the server says it is offered (coding agents pointed at the gateway, the browser access gate, published packages, website tools opened through `/go/`), checks in, and removes everything when the device is disconnected. Personal devices: nothing outside the app's folder is touched (`swangz run claude`); company devices: Claude Code/Codex are pointed at the gateway for good. Server side `gateway/enroll.py`, schema v21. `docs/CLIENT.md` |
| `extension/` | **Swangz AI Hub Access** — a browser extension that governs AI *websites* (ChatGPT, Midjourney, …): opens the ones a person is entitled to, blocks the rest, logs access-level use only |

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
- **V2 (Oct 9, 2026) — the control plane.** Every AI action should be attributable: who, what, for what,
  when, where, which machine, under which authority, which account, at what cost, with what outcome.
  The map of what V2 built, the migrations and what is still open is `docs/V2.md`; the threat model is
  `docs/SECURITY.md`. Three rules that run through it: **the server decides** (roles, policies, model
  rules — the UI only hides buttons); **no LLM is ever the authority** for access (policies are data,
  evaluated deterministically; purpose inference is keyword rules that only label); **never present an
  inference as a fact** (a purpose says declared / derived / inferred with its confidence and evidence;
  a cost says estimated / unpriced / allocated and which price or rate; a place says named network /
  approximate / address type).
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
  `admin-monitor.js`, `admin-records.js`, `admin-govern.js`, `admin-money.js`, `admin-rules.js` and
  `admin-trust.js` and register routes with `SWA.page()`. Owner-supplied Oct 9 artwork is `static/home-welcome.webp` on staff Home and
  `static/login-welcome.webp` on staff sign-in and the distinct `static/admin-welcome.webp` on admin sign-in. Keep imagery separate from controls and data. Show evidence honestly: a cost is *estimated*
  (from which price or rate) or *unpriced*, a platform comes *from the user agent*, a place is a *named
  network*, *approximate* (offline table) or just the address type, a purpose is *declared*, *from the
  tool* or *inferred* with its confidence — never present an inference as a fact.
- **Visual design (Nov 7, 2026): the "Glass" redesign in `docs/design/BRIEF.md` is the target** — Arnold's three
  reference videos (glass dashboard + CRM, glass login, liquid glass footer) define the look and motion. Where the
  older rules below (tight radii, imagery kept apart from controls) disagree with the brief, the brief wins; the
  structure rules in `docs/UI.md` (one home per kind of information, tabs, URLs) still apply.
- **Earlier finish (Oct 7), superseded where the brief differs:** The finish follows Swangz Avenue Bookings (`arnoldkigozi0/swangz-avenue-bookings-uiux`, Arnold's
  reference, Oct 7, 2026): tight radii, sentence-case buttons that are outlines by default, one primary
  per place (off-white, gold sweeps in on hover), danger outlined. Page actions sit on the title's line
  at the right; panel actions in the header (add) or footer (save), right-aligned; Cancel before the
  action in every dialog.
- **Console roles are areas** (`gateway/authz.py`): govern (people, tools, access, models, policies,
  purposes, company browsers), money (prices, rates, subscriptions, budgets), trust (incidents, networks,
  security settings), emergency (the stops), admin (console users, retention, privacy). Owner = all;
  operations = govern + emergency; security = trust + emergency; billing = money; viewer = none; or custom.
  Everyone in the console can *see* everything. In the console use `A.can(area)`, not `isOwner()`.

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
  enroll.py     the Swangz app's server side: device codes, the per-person manifest, check-ins, package download and publish
  backup.py     verified, compressed database copies (SQLite backup API, never migrates), optional rsync off-server
  pricing.py    model price table and cost per request
  live.py       requests in flight, and cutting them
  db.py         SQLite + append-only numbered migrations (currently schema v21)
  security.py   key/password hashing, sign-in throttle, per-person rate limiter
  admin.py      control-room API: the route decorator (role + area), people, keys, tools, settings, audit
  authz.py      roles as areas, and the one place that says who may change what
  geo.py        WHERE: named networks, an offline GeoIP table (approximate), address types — no outside lookups
  purpose.py    FOR WHAT: declared / derived / inferred (keyword rules) / unknown, with confidence and evidence
  policy.py     the deterministic policy engine (deny, permitted hours, monthly cap) and the model registry rules
  govern.py     API: purposes, models, policies, the read-only simulators, explain
  money.py      API: media rates by effective date (cost provenance), reports and CSV
  trust.py      API: named networks, the location table, incidents, notifications
  notify.py     notifications from conditions (attention, switches, failing providers, incidents); optional SMTP
  insight.py    the control room's read-only lenses: trends, attention, security, devices, timeline, usage, spend, search
  staff.py      staff-app API, /go/<tool> launches, Studio, and the browser access gate
  google.py     Sign in with Google (OIDC code flow) for staff and admins: /auth/google/start|callback
  guides.py     per-tool connection steps shown to staff
  config.py     settings from the environment; provider definitions
  static/       ui.js + ui.css (shared), index.html + portal.* (staff), admin.html + admin*.js + admin.css (console), tokens.css, fonts/
                (admin-rules.js = Models + Policies; admin-trust.js = Incidents + Health)
extension/      the MV3 browser access gate (its own README)
swangz_client/  the Swangz app for people's devices (stdlib; core.py, agents.py, bundles.py, shell.py, cli.py, gui.py — docs/CLIENT.md)
packaging/      building the app into a standalone program (build.py; README.md says what signing needs)
workspace_agent/ agent.py — the Swangz Workspace Agent, alone on the workspace machine (stdlib);
                computer.py — runs it on a Windows PC or Mac: setup, tunnel, start with the computer
tests/          unittest suite + fake_upstream.py (a stand-in for every provider)
deploy/         systemd units (+ nightly backup timer), Caddyfile (HSTS), firewall.sh, setup scripts, laptop-demo.sh, NETLIFY.md, WORKSPACE.md
docs/STATE.md   current status, what's done, what's next  ← read this after this file
docs/HANDOFF.md moving to another machine: what is NOT in git, and how to carry it across
docs/GO-LIVE.md the rollout checklist (who does what) and the monthly cost — Swangz uses paid accounts, not API keys
docs/V2.md      the V2 control plane: what existed, what V2 built (with tests), migrations v13–v18, what is open
docs/SECURITY.md threat model: assets, actors, boundaries, threats → controls → tests, privacy, limits
docs/CLIENT.md  the Swangz app on people's devices: how a device joins, what it is offered, what is recorded, packages
docs/UI.md      the interface map: each page's job, the one home of each kind of information, the tab/view rules
```

## Working conventions (follow these)

- **Tests before every commit.** `python3 -m unittest discover -s tests -t .` — keep it green. Add a
  test for each change; the suite runs against `tests/fake_upstream.py`, never a real provider.
- **Migrations are append-only.** Add a new entry to `SCHEMA` in `db.py`; never edit an old one.
  Existing databases upgrade themselves on start-up.
- **Routes** use the `@route` decorator (signed-in or not, and `area=` for anything that changes state —
  a string, a tuple meaning any of them, or a function of the request), and get a permissions test
  (`tests/test_v2.V2PermissionTests` sweeps the V2 ones). Significant changes call `ctx.audit(...)` with
  `before=`/`after=` and a `correlation=` like `person:7`; refusals are audited by the dispatcher.
- **Policies only take access away**, and an unreadable one **fails closed** (refused, recorded as
  `policy check failed`). With no policies, behaviour is exactly as before V2.
- **Secrets never get committed.** `.gitignore` covers `.env`, `data/`, `*.db`. Provider keys live
  only in the environment; staff keys are stored as a SHA-256 only.
- **No AI attribution** in commits, docs, READMEs, or anything that could be shared — it is Arnold's
  work under his name. Write commit messages and public copy with no "generated by" / "Co-Authored-By"
  lines. (This is a standing instruction; it is not about denying AI help if someone directly asks.)
- **The Swangz app never reads a device's content.** It records the device's name, system, version, installed
  packages and last check-in, and what passes through the gateway — not files, screens, keystrokes or other
  programs. On a personal device it changes nothing outside its own folder. Don't add device-content capture or
  silent changes to a person's own tools. (`docs/CLIENT.md`)
- **Website monitoring is an access gate + access-level logging only** (which tool, when, how long —
  never page content or keystrokes). This is deliberate and keeps it lawful under Uganda's Data
  Protection and Privacy Act. Do not add covert content capture of third-party sites. Full-content
  logging exists only as an admin setting, off by default, with staff told in the extension's policy.

## Run it

```bash
read -r -p "Verified owner email: " HUB_OWNER_EMAIL
python3 -m gateway add-admin "$HUB_OWNER_EMAIL" # first owner (asks for a password)
python3 -m gateway serve                 # http://localhost:8787
```

Command line: `serve | add-admin [--role owner|operations|security|billing|viewer] | add-person | issue-key | revoke-key | people | pause | resume | purge | geoip-import FILE --source "DB-IP Lite 2026-10" | backup [--dir D] [--keep N] [--no-remote] | backup-verify FILE | package-publish FILE --id I --version V --name N [--department D] [--person ID]`.

**Demo online from a laptop** (a stand-in model answers, so nothing is spent):

```bash
DEMO_MODEL=1 bash deploy/laptop-demo.sh  # starts the gateway + a free https tunnel, prints the links
```

**Automatic Linux startup and direct tunnel recovery:** `deploy/LAPTOP-AUTO.md` describes the
installed user service, recovery checks, logs and restart procedure. The direct tunnel serves both
apps without Netlify; legacy Netlify synchronisation requires `GATEWAY_NETLIFY_SYNC=1`. Existing
OAuth callbacks remain configured until a verified first-party hostname is selected. The laptop
still has to be awake and online; use the documented VPS deployment for permanent availability.

**Configuration** (environment): provider keys `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`ELEVENLABS_API_KEY`, `HIGGSFIELD_CREDENTIALS`; address `GATEWAY_PUBLIC_URL`; `GATEWAY_HOST/PORT/DATA`;
`GATEWAY_TRUST_PROXY` / `GATEWAY_FORCE_HTTPS` behind a proxy or tunnel; `GATEWAY_FETCH_ICONS=0` to stop
logo fetching (the tests set it); `GATEWAY_WEB_URL` (the first-party HTTPS address people open);
`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (both set = "Continue with Google" appears; admins match by
username = Google email); `GATEWAY_WORKSPACE_AGENT` / `GATEWAY_WORKSPACE_AGENT_TOKEN` (the Workspace
Agent on the rented server); `GATEWAY_TURN_CLOUDFLARE_KEY_ID` / `_TOKEN` or `GATEWAY_TURN_URLS` /
`GATEWAY_TURN_SECRET` (the video relay for company browsers on Swangz's own computers);
`GATEWAY_WORKSPACE_TOKEN` (fallback: fixed browsers' Neko API token); `GATEWAY_CORS_ORIGINS` to let a Netlify-hosted front-end call the API (see `deploy/NETLIFY.md`); `GATEWAY_TZ_OFFSET`;
`GATEWAY_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `_FROM` and `GATEWAY_NOTIFY_TO` (optional: email high and critical notifications);
`GATEWAY_BACKUP_REMOTE` (+ `_SSH_PORT`, `_KEEP`, `_DIR`, `_SSH`) for off-server copies of the nightly backup. Runtime
settings (retention, rate limit, kill switch, …) live in the control room under Settings.

## Picking the project up on a new machine

**See `docs/HANDOFF.md`** for the full version — what travels in git, what does not (`.env`,
`data/gateway.db`), and how to move the secrets safely.

With git and your coding agent installed and signed in:

```bash
git clone https://github.com/arnoldkigozi0/swangz-gateway.git
cd swangz-gateway
# Open AGENTS.md and docs/STATE.md in your coding agent
```

Then `python3 -m unittest discover -s tests -t .` to confirm the suite is green, and
`python3 -m gateway serve` (or the demo script) to run it. The database and `.env` do not travel with
the repo — on a new machine you start with a fresh `data/gateway.db` and your own keys.

For native Hub reporting, migrations, identity policy and review status, read docs/HUB-INTEGRATION.md and docs/HUB-OPERATIONS.md. Never widen the two explicitly approved owner exceptions, rewrite migrations 1–18, replace a production database or represent historic adoption entries as weekly activity.

## Native Tracker parity and first-party delivery

Schema20 extends the existing Hub with typed purchase drafts/business projects, immutable proposal corrections, governed department-report scopes, plan references, auditable adoption amendments/archival and traceable business calculations. The two wizards are separate from weekly evidence and tool entitlements. Native adoption workflows do not call Supabase or Google Sheets. Source features and intentional replacements are mapped in docs/TRACKER-PARITY.md.

Production serves staff and admin on the same Caddy/systemd host; Netlify is optional legacy infrastructure. Use docs/HUB-DELIVERY.md for backup/rehearsal/cutover/recovery and isolated Railway staging. Run the full Python suite, tests/browser/check.cjs, hub.cjs, business.cjs and staging.cjs; pinned npm packages are test-only. Record actual verification in docs/HUB-COMPLETION.md.

## Amendment 01 — product operating blueprint (2 November 2026)

This extends the product overview above and preserves existing functionality. Authority:
`/home/inquiline/swangz-team/mission/amendment-01-operating-model.md`, read in full.
Where historical shared-account descriptions above differ, this amendment governs future work:
never turn an individual's subscription into a shared login. Existing catalogue, subscriptions,
assignments, keys, histories and connected environments remain intact. Production identity,
provider billing and account ownership changes require Arnold's explicit approval after reviewing
this blueprint and the assignments in the 22:00 report.

Status evidence is source inspection at main `ba82a2a`, plus the explicitly identified unmerged
credential artifact `865250c7d5ae0873112069696f87be79accbe312`. Implemented means code exists;
it does not mean deployed or independently verified. Partial means only some required behavior exists.
Missing means no implementation evidence was established here. Technically restricted means a
provider or platform capability must be established before that route can be supported.

### 1. Provider and account operating model

**Partial.** `gateway/catalog.py`, `entitle.py`, `staff.py` and `proxy.py` support own accounts,
company seats, SSO launches and company-key API routing. `/go` checks access and records a redirect;
Hub Google sign-in does not authenticate to the vendor. Existing paid ChatGPT, Claude and Google AI
subscriptions remain valid routes through officially supported login/CLI mechanisms where permitted.
Each connected account belongs to its authorized individual; company seats are individually assigned.
One account holder may use supported personal devices. No employee receives another's credentials.
Provider connection ownership and typed subscription/seat/API/enterprise records need Forge's design.
**Technically restricted:** provider-specific subscription CLI support, scopes and organization controls
remain unverified until official-source research and actual compatibility checks establish them.

### 2. Individual workspace architecture

**Partial.** `swangz_client/core.py` provides local device state and scoped client integration;
`gateway/enroll.py` provides per-person manifests. This is not evidence of a complete personal
conversation/files/automation workspace or cross-user isolation. Preserve personal projects,
conversations, history, folders, agent configurations, connections, automations, preferences and resume
state on users' devices. Connected OpenMausBot environments retain their own bots, memory, execution
context and workspace; no recreation or migration is authorized. **Missing:** verified ownership and
explicit sharing boundaries across these objects. Forge defines server rules; Prism defines local
profile/workspace integration; Probe independently tests cross-user denial and automation ownership.

### 3. Small-server responsibilities

**Implemented in source, deployment unverified:** identity, authorization, SQLite metadata, device
enrollment/manifests, audit and notification facilities (`gateway/google.py`, `enroll.py`, `db.py`,
`notify.py`); verified-backup tooling (`gateway/backup.py`). **Missing:** the new account-sync layer.
The small VPS is for these lightweight services, callbacks, signed webhooks, configuration, health
and backups. Hosted providers perform inference. Ordinary agent work and automations stay on employee
devices. No local models, GPUs, fleet expansion or automatic per-employee VPS browsers.

### 4. Provider account synchronization design

**Missing:** a unified, verified account-sync implementation. Forge must propose provider adapters
over official APIs, approved OAuth scopes and signed webhooks, preferring read-only access. Metadata
must distinguish provider/account identity, owner, subscription or seat type, account status, quota,
credit balance, period/reset, usage, last successful sync, sync errors, source and reliability.
Unsupported fields stay unavailable or explicitly manually verified; stale data carries its timestamp.
Do not scrape private pages or infer balances from Gateway estimated costs. Verify webhook signatures,
timestamps, replay protection and idempotency. No passwords, cookies, card data or authentication
secrets in ordinary database records. Storage/access/revocation and secret references await Sentinel.
**Technically restricted:** each field depends on documented provider support and authorized scopes.

### 5. Managed Chrome architecture

**Partial.** `workspace_agent/agent.py` has Chromium policy and per-slot persistent profile volumes;
`extension/background.js` provides an access gate. Per-slot saved profiles are acceptable only for company-held `shared` accounts. Seat profiles
are tied to one person and wiped when the seat is reassigned (D-015). Prefer local official Chrome/Chromium with a separate managed
profile per authorized user or seat, distinct from personal browsing. Keep cookies/storage isolated,
show the signed-in provider account and accessible data, and record ownership/access events.
**Missing:** verified local provisioning, ownership, lifecycle and workspace integration. Remote isolated
browsers require a demonstrated company-session need and measured capacity. Existing workspace
features remain; no automatic conversion of personal subscriptions to shared sessions.

### 6. Browser restrictions and threat model

**Partial.** `workspace_agent/agent.py:POLICY` disables sync, extra profiles, guest mode, developer
tools and downloads. Its URL policy allows one local folder and blocks `file://*` plus four
`chrome://` pages; there is no block-everything rule, no `RemoteDebuggingAllowed=false`, and no
external-protocol control (`workspace_agent/agent.py:96-97`). This does not prove approved-site-only
browsing. Browser boundaries are governed by Sentinel D-015/D-016. Design must address local administrator escape, cross-user session access, redirect/popup/new-tab
bypasses, alternate hosts, direct IPs, local resources and external protocols. Design URLAllowlist and
URLBlocklist together; remote browsers also need network restrictions. Evaluate Gmail, Drive,
Google account/security/session pages, account switching and unapproved provider account management.
Do not indiscriminately block OAuth endpoints. Restrict unapproved extensions, debugging, downloads,
external protocols and sensitive local resources, and test the effective policy on each supported OS.
**Partial:** device approval opens a browser through `swangz_client/core.py` and `shell.py`; Hub OIDC
lives in `gateway/google.py`. **Missing:** verified managed-browser/system-browser return flows and refusal to start production
Google sign-in without a fixed return address (D-017); current fallback derives it from Host.
Google OAuth must use secure system-browser authorization, never an embedded WebView, credential
interception, cookie reading or automated password entry. URL blocking cannot prevent use on another
device; provider-side identity, assigned seats and supported organization controls remain authoritative.

### 7. Subscription and optional API/Enterprise strategy

**Partial.** Existing subscription/assignment gates and API routing remain (`gateway/entitle.py`,
`proxy.py`, `money.py`). Preserve existing paid subscriptions; APIs and Business/Enterprise are optional,
never mandatory or an automatic billing migration. Keep individual subscription, assigned seat, API
billing and enterprise agreement visibly distinct. **Technically restricted:** vendor terms and
metadata availability require Probe evidence; research is not vendor permission or a live setup check.
Provider documentation PR #9 at `4929d349` has Sentinel's research-only approval; G6 remains open.

### 8. Actual implementation status and verification

**Implemented in source:** staff/admin UI, catalogue, device enrollment, packages, weekly reporting,
access policies, audit and subscriptions (`gateway/enroll.py`, `reporting.py`, `policy.py`, `staff.py`,
`gateway/static/`, `swangz_client/`). Preserve them and production history with forward-only changes;
every migration shipped at `ba82a2a` (through schema v21) is immutable. Exact company-domain identity rules and the two approved owner
exceptions remain in force. Personal workspace completeness, browser isolation, sync and real provider
compatibility remain partial/missing/restricted as above, regardless of design documents.

Unmerged PR #11 credential work at `865250c` (tree `6edfcd5`) adds native keystore adapters and
migration. Probe VERIFIED this exact artifact outside the sandbox with
`python3 -m unittest tests.test_client tests.test_client_credentials tests.test_client_gui tests.test_devices -v`:
**104 tests in 67.4s, OK (skipped=14 Tk/display), exit 0**. This is Probe's recorded evidence.
Sentinel APPROVED the same artifact; Hub CI run `41506599142` passed Python 3.10/3.12, browser
and app-window checks. Native credential stores, Windows DACL/macOS ACL checks and real vendor
clients remain unverified. Managed Claude, Windows managed Codex and managed Codex on Python 3.10
(scoped mode; `swangz_client/agents.py:204`) remain gated. Every fix produces a new artifact requiring
renewed Probe verification and Sentinel review before proceeding.
Key rotation follows in PR #12 (server, schema v22) and PR #13 (client); neither is merged.
Canonical main baseline supplied by Arnold: **426 tests in 1191.8s, OK (skipped=13), exit 0**.
Not run for this documentation update: Python, browser, native platform or live-provider checks.

### 9. Infrastructure cost assumptions

**Missing:** measured capacity and a verified monthly cost estimate. Existing deployment sizing guidance
is not a benchmark of the purchased VPS. Record actual VPS RAM/CPU, concurrent baseline load, browser
RAM/CPU per active session, network latency and concurrency limits before selecting remote hosting.
Expected monthly cost must separately show the verified base VPS price, backups/storage/egress and
optional measured browser capacity; unknown amounts remain unknown. Do not invent a monthly total.
Prefer device-local managed browsers; authorize expansion only after demand and business case review.
No purchases, system changes or production benchmarks are authorized by this document.

### 10. Implementation and test plan

| Task | Owner | Dependency | Testable exit |
|---|---|---|---|
| Independent credential QA/full regression at 6cbe7dd | Probe | Existing priority, no amendment interruption | Exact commit/tree, command, count/time/skips/exit, defects and unavailable native checks |
| Credential security review then PR | Sentinel, then Chief | Probe VERIFIED | Exact-artifact APPROVED, truthful checks and CI; no merge |
| Amendment account/server/browser/OAuth decision | Sentinel | Read amendment in full; precedes other designs | Threat note and explicit decisions/conditions in docs; no code |
| Official account/quota/subscription/usage matrix | Probe | Read-only; credentials QA first, may overlap Sentinel | Official sources/scopes/field availability and limitations; no scraping or live accounts |
| Metadata hooks/sync/isolation/access design | Forge | Wait for Sentinel decision | Owned records, server denials, webhook/secret/replay design and test plan in docs |
| Managed Chrome/profiles/workspace design | Prism | Wait for Sentinel decision; preserve credential work | Profile ownership, policies, system OAuth/return flow and capacity plan in docs |
| Integrate decisions and present approval gate | Chief | Designs/evidence returned | Revised blueprint, assignments and production-impact decisions in 22:00 report |
| Implement smallest approved increments | One owner at a time | Sentinel approval; Arnold OK before production identity/billing/ownership changes | Focused tests, independent QA, critical review, reviewable PR and CI |
| Isolation/browser/provider-failure QA | Probe | Implemented isolated fixtures | Cross-user files/history/credentials/automations denial, redirects/popups/tabs/IP bypasses, OAuth, failure/stale states and revocation |

Full regression uses fake services through Probe/Forge outside Codex or Actions, not real providers.
Use CI for expensive browser/platform matrices. Record native and manual checks as unavailable when
not executed. No designs count as implemented. Keep one code writer, preserve existing worktrees and
leave no background tasks running after handoff. A credits/usage outage triggers independent work on
another available engine; retry at the next heartbeat, without loops or model changes.

The product remains: one Swangz identity, personal workspaces, authorized provider accounts,
one controlled application environment and low infrastructure cost.

Sentinel decisions D-012–D-018 authorize documentation design only. D-012 separates account holder
from payer and forbids gateway relay/storage of individual subscription tokens. D-013 keeps the VPS
lightweight: company sync secrets use environment/service-file references, never ordinary DB records;
per-user token storage waits for an encryption decision and any required dependency approval. D-014
keeps personal content/automations in existing device environments; the server holds ownership,
explicit bounded sharing grants and access events only. D-015 distinguishes machine-enforced company
Chrome from advisory personal profiles; cloud profile policy remains unverified and needs Arnold OK.
D-016 requires default-deny navigation, approved login exceptions and actual bypass tests. D-017 keeps
device-code handoff and system-browser sign-in; future provider OAuth needs fixed callback, PKCE,
session/person/provider-bound state, read-only sourced scopes, explicit account consent and revocation.
D-018 requires value provenance/freshness, provider-specific documented webhook verification before
exposing any receiver, timestamp/replay/idempotency/body/rate controls, and hourly polling with backoff.
Unsupported fields stay unavailable/manual; research is provisional until citations are verified.
