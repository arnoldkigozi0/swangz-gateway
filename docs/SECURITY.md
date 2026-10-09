# Swangz Gateway — threat model and security controls

What the gateway protects, from whom, how, and where the edges are. It describes the code as it is
(schema v18, Oct 9, 2026). When something here stops being true, fix the code or fix this file.

## What is worth protecting

| Asset | Where it lives | Why it matters |
|---|---|---|
| Provider API keys (Anthropic, OpenAI, ElevenLabs, Higgsfield) | the server's environment only | one key pays for everyone; whoever holds it bypasses every rule |
| Staff gateway keys | SHA-256 only in `keys` | a stolen key is that person's access and their name on the bill |
| What people typed and what the AI replied | `requests` + `blobs` (bodies, deduplicated) | company work, sometimes personal data |
| The audit log | `audit` | the record of what admins did, so the watchers are watched |
| Console and staff sessions | `admin_sessions`, `staff_sessions` (SHA-256 of the cookie token) | a session is a person's authority |
| Shared company accounts | signed in by hand inside company browsers (Neko); never stored by the gateway | vendor accounts Swangz pays for |
| Location and purpose data | `networks`, `geoip_ranges`, `requests.purpose*` | personal data about where and why someone worked |

## Who might act against it

- **A staff member** using AI for something it shouldn't be used for, using a tool they weren't given,
  or sharing their key. Usually a mistake, rarely malice; the gateway records and refuses, it doesn't judge.
- **Someone with a staff member's key or laptop** (lost device, key pasted into a public repo).
- **A console user acting outside their role** — or an attacker with a console user's password.
- **Anyone on the internet** reaching the gateway's address: guessing passwords, probing endpoints,
  replaying requests, trying to reach the provider through the gateway's key.
- **A compromised AI tool or website**, sending crafted content (prompt text, model replies, file names)
  that the console then displays.
- **The server's own operator** (whoever has a shell on it). Out of scope for most controls below; see Limits.

## Trust boundaries

1. Internet → gateway (HTTPS via Caddy or a tunnel; `GATEWAY_TRUST_PROXY` decides whether forwarded
   headers are believed).
2. Gateway → providers (TLS; the provider key is added here and nowhere else).
3. Staff browser ↔ staff app (`/api`, cookie `sgw_staff`) and the browser extension (bearer token).
4. Console browser ↔ control room (`/admin/api`, cookie `sgw_admin`, plus the `x-gateway-admin` header on
   every change).
5. Gateway ↔ Workspace Agent / company computers (bearer keys; the agent never sees provider keys).

## Threats and the controls that answer them

| Threat | Control | Where | Tested in |
|---|---|---|---|
| A staff tool reaches more of the provider than chat/coding (files, batches, the org's admin API) | endpoint allowlist per dialect | `proxy.ALLOWED_ENDPOINTS` | `test_gateway` |
| A stolen or old key keeps working | revoke cuts in-flight requests; keys stored as SHA-256; unknown keys refused and surfaced as a security signal | `admin.revoke_key`, `live.cut`, `insight.security_events` | `test_gateway`, `test_insight` |
| A person uses something they weren't given | entitlements; model and service rules; dev-tool assignment; **model registry** (disabled / restricted); **policies** (deny, permitted hours, monthly cap) on requests, portal opens and website visits | `server.gate`, `server.policy_gate`, `server.tool_policy`, `policy.py` | `test_v2.ModelRegistryTests`, `PolicyTests` |
| A rule can't be evaluated (bug, corrupt row) | **fails closed**: the request/open is refused with "policy check failed", recorded with `rule = policy:error` | `server.policy_gate` | `test_v2.PolicyTests` |
| An LLM is talked into granting access | no model is ever asked about access; policies are data evaluated by deterministic code; purpose inference is keyword rules and only ever labels, never decides | `policy.py`, `purpose.py` | by construction |
| A console user changes something outside their role | every console route names its **area**; the server checks it; refusals are audited with outcome `denied` | `authz.py`, `admin.dispatch` | `test_v2.AuthorityTests`, `V2PermissionTests` |
| Changes go unaccounted for | audit log with actor, action, target, address, **reason, before/after, outcome, correlation, area**; no console route edits or deletes it; retention can't be set below a year; purges are themselves audited | `server.audit`, `store.purge_categories`, `server.maintain` | `test_v2.AuditFabricTests`, `RetentionTests` |
| Bulk exfiltration through exports | CSV exports are audited with range and scope; the activity export includes prompts only for roles with the **trust** area | `admin.export_csv`, `money.report` | `test_v2.TimelineAndExportTests`, `ReportTests` |
| Spreadsheet formula injection from prompts | cells starting `= + - @` are prefixed | `admin._csv_safe` | `test_gateway` |
| Stored XSS from prompts, replies, names, tool output | the console and staff app build every node with `textContent`; strict CSP (`script-src 'self'`, no inline script); launch pages escape | `ui.js el()`, `server.CONSOLE_HEADERS`, `staff._launch_page` | review |
| Password guessing | PBKDF2 hashes; sign-in throttle per address; failed sign-ins are a security signal | `security.py` | `test_gateway` |
| CSRF on the console | changes need the `x-gateway-admin` header (not sendable cross-site without CORS); the session cookie is HttpOnly and SameSite=Strict — None only when the console is served from another origin, which `GATEWAY_CORS_ORIGINS` must then name | `admin.dispatch`, `admin` session cookie | `test_gateway` |
| A runaway agent burns money | per-person rate limit, budgets, monthly **cap** policies, kill switch, **switch one provider off**, cut one request | `server.gate`, Settings → Emergency | `test_v2.EmergencyTests` |
| Credentials pasted into prompts | pattern detection; refuse or flag (setting); never echoed in signals | `parse.find_secrets` | `test_gateway` |
| Email header injection through names in notification titles | subject flattened to one line; failures logged, never raised into the console | `notify.email_new` | `test_v2.NotificationTests` |
| Location data leaking to third parties | no external geolocation: an offline table imported by an admin on the server; named networks; everything approximate is labelled so | `geo.py` | `test_v2.LocationTests` |
| Inferences presented as facts | every purpose carries its source (declared / derived / inferred) and confidence and evidence; costs carry their basis; places say approximate | `purpose.py`, `money.describe_source`, `geo.describe` | `test_v2.PurposeTests`, `MediaCostTests` |
| Shared-account password exposure | the gateway never stores or types vendor passwords (deliberately — see CLAUDE.md); company browsers are signed in by hand | `workspace.py` | `test_workspace` |
| Covert monitoring of third-party sites | the browser gate records which approved tool, when and how long; full-content logging is an admin setting, off by default, disclosed to staff | `staff.gate_open`, extension | `test_gateway.AccessGateTests` |

## Privacy (Uganda Data Protection and Privacy Act, 2019)

- Staff are told what is recorded, for how long, and who can see it (staff app → *How Swangz AI works*),
  including that a purpose may be guessed from keywords and is shown to admins as a guess.
- Retention is per category (records, bodies, website visits, opens, audit) and enforced hourly.
- Purpose inference can be switched off; location tables are offline; no content of third-party sites.
- Admins who open a full record, export records or play back a generation leave an audit entry.

## Limits — what this does not protect against

- **Someone with a shell on the server** can read the environment (provider keys), the database and edit
  the audit log directly. The audit log is append-only *through the gateway*, not tamper-proof. For that,
  ship the audit log off the box (a log collector or a periodic signed export) — not built yet.
- **A console owner** can do anything, including removing other users; roles narrow everyone else.
- **Staff with a key** can always use what they are entitled to for something unwise; the gateway records,
  limits and refuses, it doesn't read minds. Purpose labels are evidence, not proof.
- **Vendor-side activity** on shared accounts is attributed by matching the vendor's history to turns; the
  gateway can't see inside a vendor's own logs. Invoice import (actual costs) isn't built.
- **TLS termination** is Caddy's or the tunnel's; misconfiguring `GATEWAY_TRUST_PROXY` lets a client spoof
  its address (and so its "place").
- **Approximate places** come from a third-party table that can be wrong, stale or VPN-shifted.

## Reporting a problem

Tell Arnold directly; don't open a public issue for anything that could expose keys or people's data.
