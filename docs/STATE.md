# Project state and roadmap

Last updated: 2026-10-02. Read `../CLAUDE.md` first for the overview and conventions.

## Where it stands

A working platform, built and tested. **79 unit tests pass** (`python3 -m unittest discover -s tests -t .`).
Schema is **v5**. Nothing real has been called by a provider yet — there are no company API keys, and
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

### Security model (summary)

Staff keys are `sgw_<id>_<secret>`, stored as a SHA-256 only, shown once. Provider keys live only in
the environment. Passwords use PBKDF2-SHA256; sign-in is throttled. Separate HttpOnly cookies for
staff and admin, a required header on every change, strict CSP, formula-injection-safe CSV. Only
model endpoints are forwarded (account-wide endpoints are refused). The audit log records admin
actions, including opening a record and playing back a generation.

## Not built yet (likely next, in rough priority)

1. **Google Workspace sign-in (SSO)** alongside the existing email/password. Needs a real Google
   OAuth client ID + secret, so it can't be fully tested here until those exist.
2. **Media costs in dollars.** Voice/image/video are currently metered in characters/images, not
   dollars. Add per-tool media rates (ElevenLabs per 1k characters, Higgsfield per credit/image) and
   compute cost, the way `pricing.py` does for tokens.
3. **Renewal reminders and spend-threshold alerts** — surface subscriptions renewing soon and people
   nearing budget, in the control room (and optionally by email through the existing mail path).
4. **Reports** — spend by person / team / tool over a window, usage trends, exportable CSV.
5. **Billing-only admin role** — a third tier beyond owner/viewer (needs a migration to relax the
   `admins.role` CHECK).
6. **Audit-log filtering** in the admin UI (by actor, action, date).

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
4. **Back up `data/gateway.db`** — it is the record.

## Gotchas worth knowing

- `pkill -f <pattern>` can kill the calling shell; match the exact process with `ps -eo pid,args | awk`.
- The CSP blocks inline `style=""` attributes — set styles via a CSS class or `element.style.x` in JS,
  never a `style` attribute string.
- A request's record is written just after its reply ends; tests and Studio must wait for it to land.
- The public address is derived per request (or from `GATEWAY_PUBLIC_URL`), so setup instructions
  always match the link the person actually used. localhost.run free links rotate; the demo prefers a
  Cloudflare quick tunnel (stable while it runs).
