# Swangz AI Hub integration

## Source audit — 10 October 2026

Gateway base: `3dad662`, current GitHub main verified by fetch. Tracker base: `95cba831`, current GitHub main verified by fetch. Work is isolated on `feature/swangz-ai-hub`; the running Gateway and Tracker are untouched.

Gateway is Python standard library + SQLite + vanilla JS/CSS. `gateway/db.py` has 18 append-only migrations, individually transactional, with the version stored in `meta.schema`. Existing authentication, roles/areas, provider isolation, entitlements, subscriptions, policy evaluation, shared turns, workspace agent, audit, retention and notifications remain authoritative.

Evidence sources: `requests` (API/media with client, provider, model, outcomes, tokens, estimated cost and cost provenance), `launches` (website access-level opens/refusals), `site_usage` (extension allows/blocks and tab-open seconds), `tool_turns` (shared-account occupancy). Occupancy and tab-open time are not confirmed working time. API attribution follows `policy.request_tool`: developer client first, otherwise provider API catalogue tool. Studio routes call the same proxy over authenticated loopback. Enforcement paths are `/go/<tool>`, `/api/gate/open`, and `proxy.Call.run`, including Studio. Following an existing media job does not create a new obligation or block delivery of completed work.

Tracker `entries` stores `id`, JSONB `payload`, backend timestamps; `app_config` stores shared settings. Actual entry tags are report/request, with registry-only stubs. Fields include identity/department, canonical/raw tool names, official URL/category, reason/impact, projects, working-time units, manual costs, frequency, subscription/credit costs, metered usage/pricing provenance, revenue, timestamps and administrative status/notes. Historical records have no trustworthy reporting-week key. Import them as adoption/procurement history, never as weekly evidence. Do not copy Tracker client-side authorisation or additional identity exceptions.

Security conflicts: Settings currently allow two personal-email exceptions and subdomains. Password/session/device-key paths do not uniformly recheck the company domain; admin Google login checks the account before the domain. Bootstrap and CLI accept non-company usernames. The user explicitly approved only arnoldkigozi0@gmail.com and marvinmusokessekatawa@gmail.com as owner/admin exceptions. All other identities, including administrators and custom roles, require the exact @swangzavenue.com domain. Legacy environment allowlists cannot widen this policy. A backed-up, audited identity migration must preserve IDs and historical attribution.

Deployment: existing VPS systemd/Caddy and laptop systemd/Cloudflare/Netlify proxy. Preserve repository slug, public URLs, Google callbacks and provider paths. Existing hourly maintenance can compile completed weeks before retention removes evidence and resume after restart. Email is optional; in-app notifications remain primary and delivery failures must be visible.

## Implementation plan

1. Audit/architecture: inspect source instructions, route/auth/test/deployment contracts; record this plan and baseline results. No production mutation.
2. Data/backend: append v19 with typed weekly/adoption declarations, projects, frozen evidence metrics and references, immutable submission versions and review actions, procurement, import ledger, recipient notifications and management snapshots. Implement Kampala ZoneInfo half-open weeks, aggregation, reconciliation, validated lifecycles, filtered/paginated APIs, CSV and management snapshots. Build actual Tracker JSON/Supabase read-only export import with dry run, hash deduplication, safe matching, backup checks and transactional writes.
3. Enforcement: share overdue lookup across launch, extension and proxy; preserve independent controls. Submissions clear the report requirement immediately; returned corrections re-block that tool. Emergency overrides require emergency permission, bounded expiry, exact scope and reason; audit every override.
4. Identity/governance: exact canonical company-domain accounts across password, OAuth, invitations, sessions, keys, account management and bootstrap. Provide offline identity preflight/migration instead of silently activating production and stranding the owner.
5. UI: native staff Weekly reports and adoption wizard, Requests tabs separating access/procurement, compact Home reminder; admin weekly workspace with URL-state tabs, filters, review drawer, evidence/declaration comparison, management exports. Reuse shared accessible DOM primitives, tokens and existing navigation.
6. Hardening: unit suite and critical regression coverage for migration preservation, time boundaries, duplicate/concurrent writes, gates, authorisation, imports, reconciliation and notification failures. Run available browser checks on desktop/tablet/mobile and both themes; inspect actual output.
7. Delivery: branding, guides, .env.example and operations/recovery docs; logical commits and a reviewable PR against main. Do not merge or deploy this integration automatically.

## Decisions

- A submitted declaration clears ordinary work; review/confirmation is administrative, never a prerequisite.
- A returned report blocks its own tool until resubmission, preserving all prior versions.
- Frozen evidence is independent of staff declarations and retained beyond source-record retention. No raw prompts/page contents go into it.
- Unknown amounts stay NULL. Staff business value/time/cost are estimates, not verified vendor spend.
- Imported registry metadata can fill explicitly approved blank descriptive fields; it never overwrites plans, sign-in, subscriptions or assignments. Ambiguous matches are validation errors.
- Historical external submitters may be preserved as record attribution without creating Hub accounts.
- No production import, identity switch or restart before backup and reconciliation approval.

## Phase record

1. Audit complete: both repositories and project instructions inspected at the commits above. The existing 265-test baseline passed (257.136s). The implementation plan preceded edits.
2. Data/backend implemented: `hub_schema.py`, `reporting.py`, `hub_api.py`, `hub_import.py`, `hub_export.py` and `hub_delivery.py`; append-only migration 19, typed declarations/projects, immutable evidence/submission/review snapshots, procurement, reconciliation, management revisions, CSV/print and transactional dry-run import. Actual Tracker time units, metered fields and project narratives are mapped. Unknown monetary currency and legacy department-access requests require explicit reconciliation instead of invented purchase records. Import regression tests use representative source-shaped fixtures; no live export was available.
3. Enforcement implemented: `staff.py`, `proxy.py`, `turns.py`, `workspace.py` and reporting helpers gate launches, extension opens, device-key proxy and Studio requests. Existing entitlement, suspension, subscription and policy controls remain independent. Drafts do not unlock access; submission does; returned corrections re-block the same tool. Bounded emergency overrides and shared-lease rollover are audited.
4. Identity/governance implemented: `config.py`, `google.py`, `admin.py`, `staff.py`, `__main__.py` and `hub_identity.py` enforce the exact company domain across account roles and entry paths. Only the two explicitly approved owner/admin Gmail identities are exceptions. Offline identity preflight and backed-up recovery retain person IDs/history and revoke sessions. No production identity change ran.
5. Staff/admin UI implemented: shared `hub-ui.js`, `portal-hub.js`, `admin-hub.js`, `hub.css` and existing portal/admin navigation provide native six-step reports, adoption history, separate request workflows, compact summaries, responsive navigation, URL-state tabs, filters, pagination, guarded forms, review/procurement drawers and management exports. Existing Home/sign-in raster backgrounds remain in place. Visual review corrected oversized sidebar SVGs and clipped mobile reporting dates; browser assertions now cover icon dimensions.
6. Hardening implemented: dedicated tests cover aggregation, Kampala/year/DST boundaries, frozen provenance, blank drafts, concurrent/idempotent submission, lifecycle/reconciliation, server gates and independent controls, selected historical exports, exact identity policy, migration preservation, import idempotency and notification failure states. Legacy fixture assumptions and account-management regressions found during development were corrected without removing security tests. Final verification results are recorded below.
7. Delivery implemented: README, project instructions, schema/state/security documentation, `.env.example` and `HUB-OPERATIONS.md` describe activation, import reconciliation, backup/recovery and operational limits. Changes are isolated on a reviewable feature branch; production rollout remains a separate controlled operation.

## Verification and limitations

The existing browser harness passed 201 interaction assertions and 289 screen checks in each executed desktop-light and mobile-dark run. The dedicated Hub browser harness passed 17 screen/accessibility checks and 13 workflow groups, including dark/light themes at 1440, 768 and 390 pixels, saved draft/reload/submission, immediate gate clearance, corrections, procurement deep links, drawers and tab Back/refresh. Its result contained no JavaScript errors or unexpected failed API requests. Screenshots were inspected manually; attached images use synthetic fixtures only.

The final full Python suite passed 300 tests (264.894s), including 35 dedicated Hub regression tests and the compiler-watermark regression. The preceding full run also passed 299 tests (267.882s). Earlier fixture ResourceWarnings and deliberate mock-provider failure messages are not real vendor/production tests. Compileall, syntax checks for all 17 JavaScript/browser files and git diff whitespace checks passed.

Live Tracker credentials/export have not been supplied, so live dry-run counts, historic import and production reconciliation are outstanding. Neither source application's production database was changed, and this integration was not merged, deployed or activated. Real SMTP delivery, provider billing and production browser/extension rollout were not tested.

Legacy unscoped device keys cannot reliably distinguish multiple tools on one provider; they conservatively enforce outstanding reports across that provider. New tool-scoped keys give tool-specific API enforcement. Direct vendor access outside a managed Hub browser/extension is outside the Hub's enforcement boundary. These limits and the safe activation procedure are documented in `HUB-OPERATIONS.md`.

Compilation uses per-source ID watermarks between week boundaries to avoid rescanning history on every access. Restart, rollover and maintenance rebuild the scan; late source IDs are considered without rewriting frozen evidence. Regression coverage verifies this behaviour.

## Review screenshots

Synthetic fixtures: [staff report wizard](screenshots/hub-staff-dark.png), [mobile admin reporting](screenshots/hub-admin-mobile-light.png).

## Continuation and activation preparation — 10 October 2026

The user requested completion after connectivity returned, including the earlier merge/hosting instruction. GitHub main remained at the audited base; PR #4 was mergeable and its Netlify checks passed. The existing laptop service is running from the original Gateway checkout with its existing database/configuration.

Read-only identity preflight found the approved owner and five company-domain staff accounts; one existing personal-email staff account is retained as history but denied authentication by the requested rule. No replacement company address was invented.

A private online SQLite backup passed integrity/hash checks. Migration 19 was rehearsed on its copy, preserving every original row in all 30 existing tables. Counts before activation: 49 tools, 6 people, 1 admin, 6 keys, 14 assignments, 9 subscriptions, 1 access request, 50 API records, 17 launches and 2 website records. Backup/recovery files remain outside Git and public assets.

Tracker-specific browser storage was recovered from isolated profile copies without running its application sync code. The owner cache contains 48 rows; the second account's 44 overlapping rows are identical. The configured Supabase hostname returns NXDOMAIN (public DNS status 3) despite GitHub and Supabase's main domain resolving. Backend export cannot run against that missing host.

Reconciliation preserves the complete original cache privately, quarantines three explicit test/probe records without changing them, and skips twelve browser-only demos. Thirty-three eligible records passed dry-run and staged import: 29 historical adoption declarations, 3 procurement requests and 1 registry record. Beeble's existing official registry URL was verified at https://beeble.ai/; a new catalogue row has no subscription or assignment and grants no access. The staged rerun detects 33 duplicates and creates none. Existing catalogue rows, subscriptions, assignments, keys and access requests remain intact.

All 32 historical submitters remain external attribution because they have no exact match among existing Gateway people; six non-company historical addresses create no accounts. Five historic report tools remain unmatched catalogue references. No identity, tool assignment, procurement approval or currency was invented. Native report/procurement details now expose safe import provenance, explicitly stating that browser history has not been reconciled against the unavailable backend; raw archived payloads stay private.

Activation is performed only after the new regression run and browser checks pass. The final activation record below captures the actual merged revision, verified backup, migration/import counts and public checks; preparation is not a deployment claim.

Continuation verification: the complete Python suite passed **301 tests in 271.275s**, including recovered-import provenance. The browser rerun passed 7 screens and 13 workflow groups, with no accessibility violations, JavaScript errors or failed API requests. The original full dark/light size matrix remains recorded above. Python compilation, changed JavaScript syntax and whitespace checks passed. The user-authorised merge and backed-up activation proceed against this tested revision.
