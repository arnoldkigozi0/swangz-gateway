# Project state and roadmap

Last updated: 2026-10-10. Read `../CLAUDE.md` first for the overview and conventions; `V2.md` for the
control plane added on Oct 9, and `SECURITY.md` for the threat model.

## Where it stands

A working platform, built and tested. **301 unit tests** (`python3 -m unittest discover -s tests -t .`).
Schema is **v19**. Nothing real has been called by a provider yet — there are no company API keys, and
the demo uses a stand-in model (`tests/fake_upstream.py --demo`).

### Hub integration and activation — 10 October 2026

PR #4 merged at `91f3b3f`; the existing laptop database was backed up, migrated to schema 19 and retained its original people, owner, keys, assignments, subscriptions and access request. Native weekly reporting, evidence/reconciliation, procurement, management exports and layered staff/admin workspaces are active. The complete suite passed 301 tests; browser verification is recorded in [the integration log](HUB-INTEGRATION.md).

Recovered owner Tracker history imported 29 adoption declarations, 3 procurement requests and 1 registry record. Twelve demos were skipped and three explicit test records preserved separately. The original backend hostname returns NXDOMAIN, so recovered views explicitly disclose that backend reconciliation is pending. Historic declarations do not create weekly obligations; actual Gateway evidence created 17 required weekly reports.

The automatic laptop service is enabled, running and has lingering enabled. Direct HTTPS tunnel health and owner/company-staff password sign-in passed. Netlify production builds are blocked by its account credit limit; direct deployment was rejected too. Restore the account's credits before expecting the stable Netlify front door or its Google callback to work. Existing callback/domain configuration was preserved. See [the operations guide](HUB-OPERATIONS.md) for backup/recovery, API-key attribution and enforcement limits.

### Done and verified

- **The gateway core.** Staff hold a personal key (one per device); the gateway swaps it for the
  company provider key, passes the request through in the provider's own dialect byte-for-byte (so
  Claude Code, Codex and the SDKs work unchanged), streams it back, and records who/tool/model/tokens/
  cost plus the body. Admins can cut a request mid-stream. Verified against the real Claude Code
  2.1.286 and Codex 0.155 CLIs.
- **Voice / image / video.** ElevenLabs and Higgsfield through the gateway (Studio in the staff app,
  or the official SDKs pointed at the gateway). Any other API service can be added as a `media`
  provider in `providers.json`.
- **Tool catalog + entitlements (schema v5).** 49 tools (47 from the Swangz Avenue AI Adoption Tracker registry with
  real pricing, plus Claude Code and Codex). A tool is enabled only when the company subscription is
  active AND the person is assigned it (direct or by department). `gateway/entitle.py` resolves every
  state. Dev tools (Claude Code, Codex) are enforced at the proxy by client name.
- **Budgets hidden from staff** until an admin sets `budget_visible` on the person.
- **Premium UI.** Staff app is a tool catalog (state chips, category filter, right action per tool).
  Control room has a Tools page (subscriptions + who-can-use-each), per-person tool toggles, an
  access-request inbox, and a per-person "show budget" toggle.
- **The website access gate.** A MV3 browser extension (`extension/`) signs a person in, opens the
  AI sites they're entitled to, blocks the rest with a Request-access page, and logs **access-level
  use only** — which tool, when, how long. No page content, no keystrokes; `site_usage` has no column
  for it. Verified end-to-end in headless Chromium against the live gateway. Loads in Chrome 152 and
  Chromium 153.
- **Hardening.** `/healthz` (DB check + uptime, 503 when down) and `/admin/api/health`; a per-person
  rate limit (Settings → requests per minute, 0 = off → 429).

### Oct 3, 2026 — the launchpad, catalog control, licences, and the redesign

- **Open from the portal.** Every staff tile opens through `/go/<tool>`: the gateway checks the person
  may use it *now* (subscription, assignment, end dates, suspension, kill switch), logs the launch
  (`launches`: who, tool, when, IP, browser), and redirects to the tool's company sign-in link or
  website. Refusals get a branded page and are logged too. Only http(s) targets are ever opened.
- **How people sign in, per tool:** company SSO (`sso` + the SSO link), a company seat under the
  person's work email (`seat`), their own login (`own`), or the company API key (`api`). Staff see
  which on each tile. *Not built, by decision:* a shared company login typed into many browsers —
  vendors' terms forbid account sharing (see CLAUDE.md).
- **Admins add, edit, remove (restorable) and delete tools** from a side sheet on the Tools page:
  Overview · Who can use it (teams, people, per-person end dates) · Subscription · Settings (name,
  category, type, description, website, sign-in method and link, domains, brand colour, logo upload
  or fetch, remove/delete).
- **Logos.** Fetched once on the server from each tool's site (apple-touch-icon / favicon), falling back
  to DuckDuckGo's icon service for sites that refuse automated requests; public hosts only, content
  sniffed, ≤300 KB; served from `/icons/<id>` with a sandbox CSP. 48 of the 49 built-ins resolve.
- **Time limits.** A grant can end on a date; a whole account can end on a date (`access_until`) —
  keys, launches and the catalog all stop after it. **Remove all tools** from a person in one step.
- **Licences & spend** page: spend this month (plans + API), seats given vs paid (over-assignment
  flagged), who actually used each tool in 30 days, idle seats and what they cost, cost per active
  user, one-click **Reclaim**, renewals in the next 30 days, API spend per person against budget.
- **Live** shows portal launches as they happen; each person's page shows what they opened.
- **Redesign — "Porcelain & Midnight".** Light, warm porcelain page, white cards, midnight-navy type
  and buttons, champagne-gold accent, 8–16px radii, soft shadows, real tool logos. A navy (not black)
  midnight theme, toggled in both apps. Staff app is now a launchpad (greeting, stats, recently
  opened, Your tools, the catalog). Console has a grouped icon sidebar. Extension restyled to match.
  Checked at 1440px and 390px, light and dark, in headless Chrome.

### Oct 3, 2026 (later) — Sign in with Google + Netlify front door

- **Continue with Google** on the staff app and the console (`gateway/google.py`, OIDC authorization-
  code flow; state bound to the browser by a cookie and single-use; issuer, audience, expiry, nonce and
  `email_verified` checked). Staff match a person by email (Swangz-email rule applies; suspended/ended
  refused); admins match a console user whose username is the Google email. The button only shows when
  `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set. 10 tests + a real-browser run through a
  Netlify-like proxy with a cross-site fake Google (staff in, admin in, unknown account refused).
- **Netlify front door** (`deploy/netlify/build-netlify.sh` default): Netlify proxies `/api`,
  `/admin/api`, `/auth`, `/go`, `/icons` to the gateway; first-party cookies; one fixed address for
  Google. `GATEWAY_WEB_URL` tells the gateway that address. Step-by-step in `deploy/NETLIFY.md`.
- Demo accounts (Oct 3): the owner's console user is now `arnoldkigozi0@gmail.com` (renamed from
  `arnold`); the webdev demo staff account has a password. Both live only in the demo database.
- **LIVE (Oct 3, 2026):** `https://swangz-ai.netlify.app` (staff) and `/admin` (console), Netlify
  project `swangz-ai`, building from `main` (base `deploy/netlify`). Env var `SWANGZ_GATEWAY` = the
  laptop's Cloudflare quick-tunnel link. Production visibility **Public**, Deploy Previews **Private**.
  Google Cloud project `swangz-ai`, OAuth client "Swangz Ai", redirect URI
  `https://swangz-ai.netlify.app/auth/google/callback`. Consent screen is in **Testing** with two test
  users (arnoldkigozi0@gmail.com, webdev02022007@gmail.com); publishing it needs the Branding page
  completed. Verified through Netlify: staff + admin password sign-in (cookies survive the proxy),
  Open → tool redirect, Google start → accounts.google.com → back to the Netlify callback.
- **Fragile until moved to a server:** the tunnel link changes whenever the laptop's tunnel restarts —
  then update `SWANGZ_GATEWAY` in Netlify and redeploy. (Oct 3, Windows: `deploy/windows-demo.ps1` does
  both itself through the Netlify API when `NETLIFY_AUTH_TOKEN` is in the demo `.env`. Also learned that
  day: Netlify cancelled push builds when `deploy/netlify` didn't change, so app changes never deployed —
  `netlify.toml` now sets `ignore = "exit 1"`; and the variable only counts once a deploy has used it.)

### Oct 3, 2026 (third pass) — shared accounts, black theme, tabbed console

- **Shared company accounts, a turn at a time** (`gateway/turns.py`, schema v7). Swangz pays for one
  account on some tools and everyone uses it, so nobody can tell who burned the credits. A tool set to
  `signin = 'shared'` is now handed to **one person at a time** (`seats_at_once`) for `turn_minutes`:
  the portal's Open takes the turn, the browser gate blocks everyone else, staff can hand it back, it
  expires by itself, and an admin can take it back. Suspending someone ends their turns. Live and the
  tool sheet show who is on what; `/admin/api/turns` keeps the history. **This is the answer to
  "who spent the credits" — the vendor's usage at a given hour belongs to whoever held the turn.**
- **Automatic sign-out** (extension 1.1.0, `browsingData` permission). When a turn ends, when an admin
  takes it back, and every time **Chrome restarts**, the extension clears that tool's cookies and
  stored data, so the tool is signed out and the person must come back through the portal. Nothing
  outside the governed tools' own domains is touched.
- **"Obsidian & Gold" theme**, now the default: near-black neutral surfaces (no blue cast), champagne
  gold brand, bright mint/sky/coral states. The light "Porcelain" theme is still there behind the
  toggle. Arnold asked for black over navy, and for a brighter accent.
- **The console is tabbed.** `pageTabs()` builds each tab on demand and keeps the choice in `?tab=`.
  Person → Overview / Tools / Activity / Devices & sign-in / Details. Settings → Access & records /
  Addresses / Model prices / Console users / Your account. **Staff activity** (renamed from Activity)
  → AI requests / Tools opened / Websites visited, which is where "what did staff do" now lives.
  Nav renamed "Requests" → "Tool requests" so the two senses of "request" stop colliding.

### Oct 3, 2026 (fourth pass) — the shared workspace

A shared tool can now carry a **`workspace_url`**: the address of a remote browser Swangz runs on its
own server, which an admin has signed in to that tool once. `Open` then sends whoever holds the turn
there instead of to the tool's website, so they arrive signed in and the password never leaves the
server. Turns still decide who gets in; launches are still logged. Empty = Open goes to the tool's own
site as before. Set under **Tools → the tool → Settings → Shared workspace address**.

`deploy/WORKSPACE.md` is the honest build guide: what it fixes (staff never hold the password, one
person at a time, nothing left signed in on laptops), what it does **not** fix (vendors still forbid
one subscription serving several people — buy seats where a team plan exists), and what it costs
(a separate 4–8 GB machine at ~$12–30/month, plus real latency streaming a desktop to Kampala).

### Oct 3, 2026 (fifth pass) — the browser pool, with a sign-in per turn

Work moved to a Windows laptop (Python 3.13; the suite passes there too). Arnold asked for the
workspace to let **several people use one tool at once**. A remote browser is one screen, so that means
**a pool of company browsers per tool, one per person on a turn**:

- `workspace_url` now lists browsers, one address per line (≤20). Each turn is given a free browser for
  its whole length (`tool_turns.workspace`, schema v9); the pool caps `seats_at_once`. Taking a turn and
  picking a browser happen in one transaction, so two people opening at once can't collide.
- With `GATEWAY_WORKSPACE_TOKEN` (the Neko API token), `gateway/workspace.py` makes a Neko sign-in for
  the person on their browser at Open — fixed username `swangz-<id>` (Neko's page prefers a remembered
  name over the link's), a new random password each time, never stored — and sends them in with
  `?usr=&pwd=`. When the turn ends (handed back, run out, taken back, suspended, tool deleted) it deletes
  that member, which ends the Neko session. A 15-second sweep catches turns that run out and retries
  browsers that were down. A leftover sign-in is overwritten, never trusted.
- **Neko, not Kasm** (checked Oct 2026): Kasm Community is non-commercial only; Starter ($10/user) has
  no developer API; only Enterprise (quote) has both. Neko is Apache-2.0. Its default Chromium policy
  turns developer tools off, which stops staff copying the session cookie out — the guide keeps it.
- Console: the tool sheet takes the browser list, shows who is on which browser, and says whether the
  gateway is managing sign-ins. 19 tests against a stand-in Neko (`tests/fake_neko.py`).
- **Not done:** the workspace server itself — see the next section.

### Oct 3, 2026 (sixth pass) — the Swangz Workspace Agent

Arnold asked for the gateway to allocate browsers through an agent on the workspace server rather
than a hand-kept list, keeping the list as a fallback. Built:

- **`workspace_agent/agent.py`** — standalone, stdlib, deployed alone on the workspace VPS next to
  Docker, behind Caddy, reachable only from the gateway's IP and with a token. API: `/health`,
  `/status`, `/allocate`, `/release`, `/admin-open`, `/admin-close`. Browsers ("slots") are fixed in
  its config per tool, by number (ports = base + number), because a Chromium profile is signed in by
  hand once and can't be used by two running browsers. Containers start when a turn needs one, are
  **recycled** after every turn (fresh container, profile volume kept, so still signed in) and stop
  after `idle_minutes`. Every container start gets a new random Neko API token that only the agent
  holds (passed by `--env-file`, never on the command line); no fixed Neko password exists. Release
  deletes the Neko member, or removes the container if Neko doesn't answer; if Docker is down too the
  lease is kept and the gateway retries. Profiles are named volumes (`swangz-ws-profile-<slot>`), so
  the browser's uid 1000 owns them. State survives an agent restart (`state.json`, 0600).
- **Gateway:** `tools.workspace_mode = 'agent'` (schema v10). Open asks the agent; while the browser
  starts, the person sees a self-refreshing *Starting your browser…* page (no request held open past
  Netlify's 26 s). Leases are `t<turn id>.<start ms>`, so a fresh database can't collide with old
  leases. A turn that never got a browser is ended, not left holding a seat. Console: *Company
  browsers* setting, and the tool's **Who can use it** lists the server's browsers with **Sign in to
  the tool / Done** for admins (`/admin/api/workspace…`). The static list (fifth pass) is unchanged.
- **Tests:** 28 new — the agent against a fake Docker (which reads the env file, so each restart's new
  token really reaches the stand-in Neko) and the gateway end-to-end through a real agent.
- **Not done:** a real workspace server. Nothing here has run against real Docker or Neko yet; the
  first deployment should walk `deploy/WORKSPACE.md` and check each step.

### Oct 5, 2026 — 20 people at once, across many tools

Arnold wants the workspace on a VPS with about 20 people in company browsers at once, across many
tools (ChatGPT, Claude, Midjourney, Canva and more). Browsers stay fixed per tool, so the agent gained
**`max_running`**: a server-wide cap on running containers. List a few browsers for every tool; when
the cap is reached, the free browser unused longest (any tool) stops to make room, a released browser
is only kept ready if there is room, and with every running browser in use the agent answers 409
`{"full": "server"}` and staff are told the workspace is full. Sizing for 20: ~64 GB, 16 threads,
`screen` 1280x720@25 (`deploy/WORKSPACE.md`, `docs/GO-LIVE.md`). Server not chosen yet.

### Oct 6, 2026 — the company browsers on Swangz's own computer, as an option

Arnold has a strong computer (64 GB+) — a Windows PC and a Mac — and asked to run the browsers there as
an option, chosen by the admin, **one place at a time, not both**. Built (schema **v11**):

- **Three places, one switch.** Settings → **Company browsers** lists the rented server (env, as before),
  the Windows PC and the Mac, with **Use this one**. `workspace.use()` ends every turn whose browser is
  elsewhere (reason "the company browsers moved to …"); each turn records `ws_host`, so its sign-in is
  released at the place it was made, retried until that place answers. Each place's browsers can be
  signed in from that page before switching (`?host=` on the workspace routes).
- **A computer connects itself.** Connect… gives a key (shown once, inside the setup command).
  `workspace_agent/computer.py setup` (Windows or Mac, Python 3.9+, stdlib): checks the gateway, starts
  Docker Desktop, sizes `max_running` from Docker's memory (and says how to give it more), downloads
  cloudflared and the image, registers itself to start at sign-in (Windows: HKCU Run + pythonw, no
  window; Mac: a LaunchAgent), keeps the machine awake, runs a quick tunnel and re-opens it if it drops.
  The agent checks in every minute at `POST /api/workspace/hello` (through the Netlify front door) with
  its tunnel address; the gateway answers with the browsers it needs (every shared tool in agent mode,
  `seats_at_once` each — a tool keeps its browser numbers, so its profiles, for good) and relay credentials.
- **No Caddy on a computer:** the agent passes `/<slot>/…` straight to that browser, WebSocket included.
- **Video relay** (`workspace.Relay`): Cloudflare TURN (`GATEWAY_TURN_CLOUDFLARE_KEY_ID/_TOKEN`) or your own
  coturn (`GATEWAY_TURN_URLS/_SECRET`); 48-hour credentials; Neko runs full ICE with them, and `lan_ip`
  lets people in the office connect straight to the computer.
- **Tests:** 20 new (check-in, numbering, relay env, pass-through incl. WebSocket, switching both ways,
  release while the old place is down, Cloudflare/coturn credentials).
- **Not done:** nothing has run on a real Docker Desktop yet, and no TURN key exists yet. First run:
  follow WORKSPACE.md → "On a Windows PC or a Mac", then test from outside the office.

### Oct 6–7, 2026 — mission control: the control room and staff app rebuilt

Arnold briefed a full premium UI/UX pass ("Mission Control for company AI": calm, trustworthy, deep
visibility for admins, simplicity for staff). Built on real data only:

- **Design system.** Obsidian & Gold evolved (`tokens.css`: chart colours validated for colour-blind
  separation in both themes, a 5:1 tertiary text, layers, motion), plus `ui.css` / `ui.js` — the shared
  primitives both apps are now built from (see CLAUDE.md). Live things breathe slowly; nothing flashes;
  reduced motion and forced colours are respected. Every state is a dot *and* a word.
- **Control room.** New nav (Monitor · Govern · Money · Trust), an emergency *Stop all AI* in the
  sidebar instead of on every page, a phone drawer, and **Ctrl+K** — jump to any page or search people,
  tools, devices, requests (`#123`), sessions and the audit log. New pages: **Overview** (spend with
  its trend and change, active people, live, tools, security; usage and spend charts; top tools and
  people; needs attention; licence opportunities), **Needs attention** (one list: security signals,
  budgets, idle/over-assigned seats, renewals, full shared accounts, an offline computer running the
  company browsers, waiting tool requests, missing provider keys, unpriced models), **Live** (in-flight requests with elapsed time and state; *Inspect*
  follows a request until it finishes and opens its record), **Activity → Timeline** (who did what,
  when, where — requests, portal opens and website visits in one stream, grouped by day, filterable,
  paged) and **Who used what**, **Devices** + a page per device (apps, platform, addresses, models,
  sessions, flagged requests, 30-day chart, revoke), **Security** (posture + events with severity and
  the evidence behind each — credentials, unknown keys, rule refusals, opens without access, blocked
  sites, failed console sign-ins, revoked keys, and *unusual usage* measured against the person's own
  last 14 days), **What cost us money?** (spend for any range by person / tool / department / model
  against the period before, unexpected increases, idle subscriptions, and how spend is worked out).
  Person pages gained KPIs (last seen, current device, live, spend, tools, alerts) and Activity /
  Security tabs; tools gained a usage profile (seats vs active, use per day, who, devices, denials);
  the record page became a forensic view (each fact labelled with how it's known, and a request
  timeline: prompt → first word → actions by category → reply → outcome); the audit log is filterable.
  A time range (Today … Custom) and a time zone (gateway / mine / UTC) apply wherever time matters.
- **Fewer tiles per page (Oct 7, Arnold: "too many tiles").** Headline numbers sit in one joined strip,
  not separate cards. Overview is tabbed — *Right now* (needs attention + live), *Trends*, *Top tools &
  people*, *Licences*. Activity rows are two lines (time · who did what with which tool · cost · outcome,
  then device / address / duration underneath); filters fold behind a **Filters** button and show as
  removable chips once set. Security's nine count tiles became one row of filter chips, listing only the
  kinds that happened. On a phone the tab bars scroll sideways with a fade at the edge.
- **The same for People, Licences and the rest (Oct 7).** Lists put their counts in the filter tabs
  instead of a tile per number: People (Everyone · Active · Working now · Not signed in · Suspended ·
  Ended), Devices (All · Active · Idle · Never used · Revoked), Tools (In use · Given, not opened · Not
  subscribed · All · Removed), each with search on the same row and a one-line summary under it. Tools
  became a table (49 cards before); the staff catalogue keeps cards only for *your* tools and lists the
  rest compactly. A person's and a device's headline facts are a slim stat line; a person's tools are a
  table with one *Give another tool* picker; a device page is tabbed (Activity · Flagged · Sessions ·
  Apps & models · Addresses · Key). *What cost us money?* is a headline strip, one *Rising fast* line
  (the full list on demand), the chart, *Where it went*, and the method folded away; idle seats live on
  the Licences tab only. The audit log's filters share one row.
- **One finish across both apps (Oct 7), after Swangz Avenue Bookings.** Arnold pointed at starlink.com
  and at his own bookings app (`arnoldkigozi0/swangz-avenue-bookings-uiux`) as the bar; the bookings
  app's system is the one adopted, since it is Swangz's own and already shares Archivo and the neutral
  surfaces. Buttons: tight corners (3px, 2px small), sentence-case 13px labels, an outline by default;
  the one primary action per place is solid off-white and fills with gold from the left on hover;
  danger is outlined until it is the confirmation itself. Radii tightened everywhere (controls 3px,
  containers 12px; only badges and counts are pills). Placement is fixed: page actions sit on the
  title's line at the right; a panel's actions sit in its header (adding) or its footer (saving),
  right-aligned; dialogs always offer Cancel before the action. **Settings** has a section list on
  the left, one row per setting (what it is on the left, a switch or field on the right) and a single
  *unsaved changes* bar with Discard / Save changes. **Access requests** put Open / Granted / Declined
  counts in the tabs, one row per request with Decline · Grant at the right edge, search, and an
  optional note when declining (staff see it). `/access-requests` returns every state's count.
- **Staff app.** Home with a restrained hero and notifications worked out from the person's own
  account; the full catalogue with filters, sort and a details drawer (what it does, *why you have it*,
  how sign-in works, who manages access, your recent use, what's recorded); device cards; a clearer
  Connect flow (device, gateway address, masked key with Show/Copy, then the steps); access requests
  with decisions; and **How Swangz AI Hub works** — what is recorded, what isn't, retention, who can see it,
  and the support contact (new Settings field). Bottom tab bar on phones.
- **API** (`gateway/insight.py`, all read-only, viewers included): `/trends`, `/attention`, `/security`,
  `/devices`, `/devices/<key>`, `/timeline`, `/usage`, `/spend`, `/search`, `/tools/<id>/usage`; audit
  filters; requests by `until` and department; device names on live and listed requests. Staff `/me`
  adds their access requests, each tool's grant source and 30-day opens, each device's app, and the
  privacy facts. Schema v12 indexes requests by key. Checked in headless Chromium at 1440 and 390,
  dark and light, as owner and viewer, with no console errors.
- **Not built then, and why** (location and purpose were built in V2, Oct 9): *location* — no IP-geolocation source is bundled (stdlib-only, nothing sent
  out), so addresses show as public/private, never a city; *declared purpose* and *AI-inferred purpose*
  — tools don't send one and nothing classifies prompts; *saved searches, AND/OR filter builder, column
  chooser, bulk actions, virtualised tables* — lists page instead; *role-specific dashboards* — waits on
  the billing/security admin roles; side-by-side *comparison* charts (A vs B) beyond period-over-period;
  staff *notifications* are derived on each visit, not stored or pushed. Coding tools rarely name their
  operating system, so a device's platform is often just the app.

### Oct 9, 2026 — V2: the AI control plane

Arnold's V2 brief: make every AI action attributable (who, what, for what, when, where, which machine,
under which authority, which account, at what cost, with what outcome) and give admins the means to
govern, investigate, restrict, revoke and respond — without rebuilding what works. Full map, migrations
(v13–v18) and what's still open: `docs/V2.md`. Threat model: `docs/SECURITY.md`. In short:

- **Authority.** Console roles are areas (owner, operations, security, billing, viewer, custom); the
  server checks the area on every change and audits refusals. The console hides what a role can't use.
- **Audit fabric.** Reason, before/after, outcome, correlation and area on every significant change;
  the audit page shows what changed. Staff sign-ins and self-service changes are recorded too.
- **Where.** Named networks (exact) and an offline GeoIP table imported on the server (approximate, with
  its source). No address is ever sent to an outside service.
- **For what.** Declared (header, or Studio's new picker), derived from the tool, or inferred from keywords
  with confidence and the matched words — or unknown. Editable taxonomy; inference can be switched off;
  staff are told on the privacy page.
- **Model registry and policies.** Approved / experimental / restricted / deprecated / disabled models with a
  data class; deny, permitted-hours and monthly-cap policies for people, departments or everyone, on
  gateway requests, portal opens and website visits. Each refusal names its rule. A read-only simulator
  replays real history against a draft; *Explain* walks every check in the gateway's own order.
- **Money.** Media rates by effective date (voice/image/video costs in dollars at last, never recalculated),
  the price or rate behind every cost, nine reports with audited CSV.
- **Trust.** Incidents (evidence, notes, transitions, resolution), persisted notifications with a bell and
  optional email, risk signals against each person's own history (new place, new device, unusual hours,
  new model, repeated refusals), sign-ins/access changes/turns on the timeline, per-category retention with
  audited purges, switch one provider off, pause company browsers, per-provider latency and errors on Health.
- Checked in headless Chromium at 1440 / 1280 / 1024 / 768 / 390, dark and light, owner and viewer; a v12
  demo database with 825 records upgraded to v18 on start-up with nothing lost.

### Oct 9, 2026 (later) — V2.1: the clarity pass (branch `ui/v2-clarity-navigation`)

No new backend, no schema change: the same features, each in one place, with navigation that holds its state.
The page-by-page map — what each page is for, what moved, and the one home of each kind of information — is
`docs/UI.md`.

- **Foundations.** `pageTabs()` has real ARIA wiring, arrow/Home/End keys, its own query parameter (nested sets
  don't overwrite each other; `clears` resets a child's), a history entry per tab, Back/Forward switching views
  in place without refetching, and an unsaved-changes guard (`A.setDirty(fn)`) on tab switches, page changes and
  unload. A page that has been left can no longer draw over the one now showing (its reads never answer).
  Sidebar groups fold, all open by default, the current one always open; breadcrumbs say the area and parents,
  never the title. Page tabs are underlined so they don't look like segmented filters.
- **Control room.** Settings is a category list (Access & privacy · Emergency · Purpose & location · Providers &
  pricing · Company browsers · Console users · Your account) with `?section=` inside two of them; old `?tab=`
  links land in the right place; number errors show beside the control; changes that delete records or widen
  logging ask first. Tool profile: Overview · Usage · Access · Subscription · Configuration · Workspace (shared
  accounts). Person profile: Overview · Access · Activity · Devices · Security · Account. Overview's *Right now*
  previews the three most urgent items. Activity, Security and the Audit log state their own jobs. Device
  addresses show the place and how it is known (`/devices/<id>` now carries `geo.describe` per address).
  Licences no longer leads with spend; Renewals is commitments only. Reports is a catalogue with a page per
  report (`#/reports/<kind>`). The policy editor is six numbered steps ending with the rule read back.
- **Staff app.** Home: up to three updates and six tools, Studio, quick links. The tool drawer is five
  sections. Studio: Create · Your creations. Devices: Connected · Connect a tool · Disconnected. Requests:
  Updates · Access requests (the bell opens Updates). Privacy: six sections with an index and details on demand.
  Views live in `?view=` with the same keyboard and history behaviour as the console's tabs.
- **Art.** One self-hosted SVG (`static/door.svg`, the doorway — "every AI tool, one door"), on the two sign-in
  pages and the staff Home hero only; nothing behind data. No motion beyond a fade, skipped for reduced motion.
- Checked in headless Chromium: owner and staff on every page at 1440 / 1280 / 1024 / 768 / 430 / 390, dark and
  light; viewer, operations, security and billing on the role-sensitive pages at 1440 / 768 / 390 in both
  themes; deep links, refresh and Back/Forward scripted; what each role is offered asserted page by page.

### Oct 9, 2026 (V2.2) — Settings and staff Home redesigned (branch `ui/v2.2-settings-home-polish`)

- **Settings** became a workspace: a grouped rail (Gateway · Emergency · Console access) with icons, a view-only lock per
  category for the role and the stop state on Emergency; a header per category with its sections inside it; rows that
  say which access they need when the role can't change them; an Emergency status board with the one big stop; a grid of
  tiles below 1100px. Choosing a category opens its first section. No setting, permission or endpoint changed.
- **Staff Home** became a launchpad: a state-aware hero with one action (back to the last tool opened, through `/go/`),
  the other approved tools as the main column, and Updates, allowance (only when visible), Studio (only when available)
  and supporting links beside them. Paused, suspended, no-tools and one-tool states each have their own composition.
- Checked in headless Chromium at 1440×900, 1280×800, 1024×768, 768×1024, 430×932 and 390×844, dark and light (owner and
  viewer on every Settings category and section; four staff states on Home), plus scripted navigation, role, form,
  emergency and Home-state checks and axe-core (WCAG 2.1 AA) scans. Details in the PR.

### How it compares (Oct 2026)

| Need | What established products do | Swangz AI Hub |
|---|---|---|
| One launchpad for company apps | Okta / Microsoft Entra / JumpCloud dashboards; Google Workspace app launcher | ✅ staff launchpad, logos, recently opened |
| Sign in once to every tool | SAML/OIDC SSO through the identity provider | ✅ Swangz AI Hub itself: Continue with Google; ⚠️ each tool: launches its own SSO link |
| Turn access on/off, time-limited | Okta/Entra assignments; SCIM deprovisioning | ✅ per person / team, end dates; ❌ no SCIM (vendor seats still removed by hand) |
| Licence use and waste | Zluri, Torii, Productiv, Zylo | ✅ seats vs use, idle seats, reclaim, renewals; ❌ no vendor API sync or invoice import |
| AI API gateway with budgets | Portkey, LiteLLM, Cloudflare AI Gateway, Kong AI | ✅ keys, budgets, model rules, live cut-off, full records; ❌ no caching or provider failover |
| Browser governance for AI sites | Island, LayerX, Microsoft Edge for Business | ✅ extension gate + access-level log + sign-out on turn end and browser restart; ❌ not a managed browser |
| Shared/service accounts | 1Password & Bitwarden shared vaults (fill a team credential) | ✅ turns + auto sign-out give **attribution**, which a shared vault does not; ✅ company browser pool with a sign-in per turn; ❌ no credential filling, by decision (see CLAUDE.md) |
| Audit trail | all of the above | ✅ every admin action, every launch, every API call |

### Accounts are restricted to Swangz emails

Every account, including all administrator roles, requires the exact `@swangzavenue.com` domain. Only `arnoldkigozi0@gmail.com` and `marvinmusokessekatawa@gmail.com` are approved owner/admin exceptions. Environment allowlists cannot widen this policy. Server checks cover password/OAuth login, invitations, existing sessions, device keys, account management and bootstrap. See [Hub operations](HUB-OPERATIONS.md).

### Security model (summary)

Staff keys are `sgw_<id>_<secret>`, stored as a SHA-256 only, shown once. Provider keys live only in
the environment. Passwords use PBKDF2-SHA256; sign-in is throttled. Separate HttpOnly cookies for
staff and admin, a required header on every change, strict CSP, formula-injection-safe CSV. Only
model endpoints are forwarded (account-wide endpoints are refused). The audit log records admin
actions, including opening a record, exporting and playing back a generation, with before/after.
Console roles are checked per area on the server; policies fail closed. Full threat model:
`docs/SECURITY.md`.

## Not built yet (likely next, in rough priority)

1. ~~Google sign-in~~ — built Oct 3 (needs Arnold's Google client to switch on).
2. **Shared-account credit reconciliation** — pull each vendor's own usage/credit history (where it
   has an API) and line it up with the turn log, so the console can say "Grace: 180 credits" instead
   of the admin matching timestamps by hand. Turns already make that matching possible.
3. **SCIM / vendor seat sync** — when a person is removed here, remove their seat at the vendor too
   (ChatGPT Enterprise, Claude for Work, Canva, Figma, Notion… each has an admin API). Today that last
   step is manual.
4. ~~Media costs in dollars~~ — built Oct 9 (media rates by effective date, Settings → Media rates).
5. **Alerts beyond the console** — notifications are persisted and high/critical ones can be emailed
   (SMTP, Oct 9); WhatsApp and a daily digest are not built.
6. **Reports** — nine reports with CSV built Oct 9; scheduled or emailed reports are not.
7. ~~Billing-only admin role~~ — built Oct 9 as roles-as-areas (billing, security, operations, custom).
8. ~~Audit-log filtering~~ — built Oct 6; before/after, reason and outcome added Oct 9.
9. ~~IP location~~ — built Oct 9 as an offline table an admin imports (`geoip-import`); none ships with
   the code, so someone has to load and refresh it monthly.
10. **Audit log off the box** — ship it to a collector or a signed export, so a shell on the server can't
    quietly rewrite it.
11. **Vendor usage and invoice import** — so costs can be *actual*, not only estimated or allocated.

## Going live for Swangz (operational)

1. Company API keys in the environment: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`,
   `HIGGSFIELD_CREDENTIALS` (`KEY_ID:KEY_SECRET`).
2. A small always-on server (a ~$4–6/month VPS) with an address like `ai.swangz.com`. `deploy/` has a
   systemd unit and a Caddy config (Caddy gets https automatically). The laptop + free tunnel is a
   demo only.
3. Set subscriptions and assignments in the control room; invite staff (email → sign-in link); roll
   out the browser extension (Load unpacked, or packed via Chrome Enterprise policy).
4. Optionally host the staff app + admin console on Netlify (static), pointed at the gateway API —
   see `deploy/NETLIFY.md`. Set `GATEWAY_CORS_ORIGINS` to the Netlify URL.
5. **Back up `data/gateway.db`** — it is the record.

## Gotchas worth knowing

- `pkill -f <pattern>` can kill the calling shell; match the exact process with `ps -eo pid,args | awk`.
- The CSP blocks inline `style=""` attributes — set styles via a CSS class or `element.style.x` in JS,
  never a `style` attribute string.
- A request's record is written just after its reply ends; tests and Studio must wait for it to land.
- The public address is derived per request (or from `GATEWAY_PUBLIC_URL`), so setup instructions
  always match the link the person actually used. localhost.run free links rotate; the demo prefers a
  Cloudflare quick tunnel (stable while it runs).

### Interface elevation after V2.2

The staff and console frontends gained clearer headings, champagne selection accents, readable
supporting text, consistent tables/empty states, quieter secondary launch actions and bounded dialogs.
Staff catalogue filters now survive deep links and refresh; mobile navigation includes Studio when
available. Studio retains drafts across media/view switches, announces submission outcomes and offers
progress-read recovery. Overview's summary-note CSS collision and measured contrast issues were fixed.
The implementation, audit and optional local browser-test commands are documented in
[UI-ELEVATION.md](UI-ELEVATION.md). No server route, authentication, database or enforcement code changed.

### October 9 — supplied artwork and Settings information design

- Selected two clean images from `Oct 09 - 13_57.zip`: the circular portal sculpture for staff Home,
  and the architectural doorway for staff/admin sign-in. Optimized to self-hosted WebP (about 124 KB
  combined); checkerboard-background JPEGs were excluded. Replaces the decorative doorway SVG
  references; interface and tool icons retain their existing vector assets.
- Settings navigation now explains each destination. Access & privacy has Records, Safeguards and
  Staff controls, each with its own save/dirty guard. Saved configuration summaries lead each section;
  nested sections have task headings and explanations. Retention copy distinguishes category limits.
- Provider connections distinguish a missing key from an emergency stop. Emergency counts configured,
  enabled providers and directs users to Health for live availability. Pricing exposes one-hour cache
  writes and all cache rates on phones, with explicit units and fallback-rate explanations.
- WebP assets are served with the correct MIME type. Existing provider forwarding, authentication,
  permissions, database and policy behavior are unchanged.

### October 9 — automatic Linux laptop hosting and Netlify recovery

Netlify's production gateway variable pointed at a dead quick tunnel. Updated and verified its
front-door health. Added `deploy/laptop-service.py` and the user service `swangz-laptop.service`:
boot startup with lingering, independent child recovery, local/public health checks and automatic
Netlify repoint/build/verification on tunnel changes. Uses the existing demo configuration/database
and saved Netlify CLI login; credentials remain local. Continuous availability still needs an
always-on host. Installation and maintenance are documented in `deploy/LAPTOP-AUTO.md`.


### October 10 — Home artwork updated after visual review

Replaced the circular sculpture on staff Home with the sixteenth supplied reference: nested dark
architecture with a warm lit entrance. The wide image matches the existing hero panel proportion;
the design is framed beside Home's copy on desktop and beneath the action on phones. Sign-in art is
unchanged. Updated the review documentation to record the final selection.
