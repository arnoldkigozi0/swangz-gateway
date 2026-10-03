# Project state and roadmap

Last updated: 2026-10-03. Read `../CLAUDE.md` first for the overview and conventions.

## Where it stands

A working platform, built and tested. **128 unit tests pass** (`python3 -m unittest discover -s tests -t .`).
Schema is **v7**. Nothing real has been called by a provider yet — there are no company API keys, and
the demo uses a stand-in model (`tests/fake_upstream.py --demo`).

### Done and verified

- **The gateway core.** Staff hold a personal key (one per device); the gateway swaps it for the
  company provider key, passes the request through in the provider's own dialect byte-for-byte (so
  Claude Code, Codex and the SDKs work unchanged), streams it back, and records who/tool/model/tokens/
  cost plus the body. Admins can cut a request mid-stream. Verified against the real Claude Code
  2.1.286 and Codex 0.155 CLIs.
- **Voice / image / video.** ElevenLabs and Higgsfield through the gateway (Studio in the staff app,
  or the official SDKs pointed at the gateway). Any other API service can be added as a `media`
  provider in `providers.json`.
- **Tool catalog + entitlements (schema v5).** 49 tools (47 from the Swangz AI Tracker registry with
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
  then update `SWANGZ_GATEWAY` in Netlify and redeploy.

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

### How it compares (Oct 2026)

| Need | What established products do | Swangz AI |
|---|---|---|
| One launchpad for company apps | Okta / Microsoft Entra / JumpCloud dashboards; Google Workspace app launcher | ✅ staff launchpad, logos, recently opened |
| Sign in once to every tool | SAML/OIDC SSO through the identity provider | ✅ Swangz AI itself: Continue with Google; ⚠️ each tool: launches its own SSO link |
| Turn access on/off, time-limited | Okta/Entra assignments; SCIM deprovisioning | ✅ per person / team, end dates; ❌ no SCIM (vendor seats still removed by hand) |
| Licence use and waste | Zluri, Torii, Productiv, Zylo | ✅ seats vs use, idle seats, reclaim, renewals; ❌ no vendor API sync or invoice import |
| AI API gateway with budgets | Portkey, LiteLLM, Cloudflare AI Gateway, Kong AI | ✅ keys, budgets, model rules, live cut-off, full records; ❌ no caching or provider failover |
| Browser governance for AI sites | Island, LayerX, Microsoft Edge for Business | ✅ extension gate + access-level log + sign-out on turn end and browser restart; ❌ not a managed browser |
| Shared/service accounts | 1Password & Bitwarden shared vaults (fill a team credential) | ✅ turns + auto sign-out give **attribution**, which a shared vault does not; ❌ no credential filling, by decision (see CLAUDE.md) |
| Audit trail | all of the above | ✅ every admin action, every launch, every API call |

### Accounts are restricted to Swangz emails

A person can only be given an account with a `@swangzavenue.com` email (configurable via
`SWANGZ_EMAIL_DOMAINS`). The only exceptions are the owner `arnoldkigozi0@gmail.com` and the demo
account `webdev02022007@gmail.com` (extendable via `SWANGZ_EMAIL_EXCEPTIONS`). Enforced when an admin
adds or edits a person, so only allowed emails can ever sign in.

### Security model (summary)

Staff keys are `sgw_<id>_<secret>`, stored as a SHA-256 only, shown once. Provider keys live only in
the environment. Passwords use PBKDF2-SHA256; sign-in is throttled. Separate HttpOnly cookies for
staff and admin, a required header on every change, strict CSP, formula-injection-safe CSV. Only
model endpoints are forwarded (account-wide endpoints are refused). The audit log records admin
actions, including opening a record and playing back a generation.

## Not built yet (likely next, in rough priority)

1. ~~Google sign-in~~ — built Oct 3 (needs Arnold's Google client to switch on).
2. **Shared-account credit reconciliation** — pull each vendor's own usage/credit history (where it
   has an API) and line it up with the turn log, so the console can say "Grace: 180 credits" instead
   of the admin matching timestamps by hand. Turns already make that matching possible.
3. **SCIM / vendor seat sync** — when a person is removed here, remove their seat at the vendor too
   (ChatGPT Enterprise, Claude for Work, Canva, Figma, Notion… each has an admin API). Today that last
   step is manual.
4. **Media costs in dollars.** Voice/image/video are currently metered in characters/images, not
   dollars. Add per-tool media rates (ElevenLabs per 1k characters, Higgsfield per credit/image) and
   compute cost, the way `pricing.py` does for tokens.
5. **Renewal and spend alerts by email** — renewals in the next 30 days and idle seats are now on the
   Licences page; sending them as email/WhatsApp alerts is not built.
6. **Reports** — spend by person / team / tool over a window, usage trends, exportable CSV.
7. **Billing-only admin role** — a third tier beyond owner/viewer (needs a migration to relax the
   `admins.role` CHECK).
8. **Audit-log filtering** in the admin UI (by actor, action, date).

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
