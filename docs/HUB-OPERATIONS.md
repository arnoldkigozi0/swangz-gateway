# Swangz AI Hub operations and migration

The Hub uses the existing Python standard-library server, SQLite database, vanilla UI, provider configuration and deployment URLs. The repository remains `swangz-gateway`. This integration is on a feature branch for review; no production restart, import, DNS change or merge is part of the development checks.

## Identity policy

Every staff, administrator and custom-role account requires the exact `@swangzavenue.com` domain. Subdomains and lookalikes are rejected. Only `arnoldkigozi0@gmail.com` and `marvinmusokessekatawa@gmail.com` are explicitly approved owner/admin exceptions. `SWANGZ_EMAIL_DOMAINS` and `SWANGZ_EMAIL_EXCEPTIONS` no longer widen access. There is no development domain bypass. Existing sessions and device keys recheck the policy; invalid historic identities are preserved as records but cannot authenticate.

Run read-only preflight before activation:

```sh
python3 -m gateway.hub_identity --database /private/gateway.db
```

Verify ownership of a replacement address through the organisation before using recovery. To migrate a legacy administrator, use their actual ID; do not create an assumed owner address:

```sh
python3 -m gateway.hub_identity --database /private/gateway.db --admin-id 7 --email verified@swangzavenue.com --apply --backup /private/backups/before-identity.sqlite3
```

This requires a new exclusive backup, checks its integrity and records a hash, keeps the same administrator ID/password/role, revokes their sessions and appends an audit entry. Historical actors are not rewritten. The two approved owners can remain unchanged. Bootstrap requires an approved identity; the example environment leaves its address blank. Correct ordinary legacy staff emails through an authorised owner before their next login; do not delete accounts or keys to migrate identity.

## Weekly operation

`GATEWAY_TIMEZONE=Africa/Kampala` defines Monday 00:00–following Monday 00:00, a half-open interval. Period labels show Monday–Sunday. Keep this zone stable after activation: closed snapshots retain their stored zone and boundaries. Budget periods continue using the existing `GATEWAY_TZ_OFFSET`.

Existing maintenance compiles completed weeks before retention, runs after restart and periodically, and resumes safely. Access checks also compile missing periods, using process-local source-ID watermarks between week boundaries; restart, rollover and maintenance rescan safely, and late records never rewrite frozen evidence. No separate scheduler or external service is required. Only admitted API requests, opened launches, allowed website visits and shared-account occupancy create obligations. Blocked-only evidence creates no required report. Closed evidence snapshots are frozen; late events do not silently rewrite submitted history. Existing retention means older missing evidence cannot be reconstructed; explicitly disclose those gaps.

Staff Home shows outstanding counts. Weekly reports has pending/returned, submitted and adoption views. The six-step wizard saves drafts and prefills observed activity. Tracker/staff metered allowances, unit prices, allocations and flat-subscription flags remain typed declarations with their original pricing basis and USD units; no declaration becomes verified vendor spend. Unknown numerical amounts stay blank/NULL; zero means known zero. Opening a site can be declared “opened but not used” with a reason. Business impact, savings and revenue remain estimates.

Drafts and returned reports block that tool. Submission/resubmission clears that report's gate immediately; review or confirmation is not required to resume. Other independent controls still apply: suspension, entitlement, subscription, policy, budgets/rates and emergency stop. Reports and help remain accessible. Emergency overrides require emergency authority, exact person/tool scope, a reason and an expiry of at most 24 hours; every override is audited.

Launches, extension decisions, provider API calls with existing keys and Studio creation paths enforce the server gate. Housekeeping/media-status requests may retrieve existing results. Shared turns end at the week boundary; the existing workspace sweep revokes remote sign-ins and retries failed revocations. The Gateway cannot enforce vendor-site access in an unmanaged browser outside the Hub or its installed extension; managed extension/company-browser deployment remains necessary. Denials expose `weekly_report_required`, the relevant report ID and its authenticated link. Extension website telemetry remains access-level only, with no keystrokes or page contents.

### API key attribution

New staff connection keys are scoped to the selected catalogue tool. Administrators may pass `tool_id` when issuing a key; CLI supports `issue-key PERSON_ID --tool TOOL_ID`. Scope checks require an available assigned API/developer tool. Provider mismatch and entitlement failures remain denied. Scope determines the audited API tool; a supplied user-agent cannot change it.

Existing unscoped keys are preserved. Their caller-controlled user-agent is insufficient to prove which of several tools sharing a provider is being used. Accordingly, any outstanding report on that provider conservatively gates a legacy unscoped key. This can affect another client on that same provider; use separate tool-scoped keys for exact per-tool API isolation. Website tools are always gated independently. This limitation must remain visible in rollout review; do not claim every legacy key has trustworthy tool attribution.

## Review, reconciliation and management

The control room Weekly reporting workspace provides overview, staff/tool groups, reconciliation, review queue, all reports, historical adoption, management trends/exports and policy tabs. Filters and tabs live in the URL. Detail drawers preserve original declaration versions, separate evidence and review decisions. Governance permission is required for review; viewers cannot write. Returning requires an explanatory note and consistently re-blocks the tool until resubmission.

Compare API/access/day counts only with like evidence. One event or the configurable relative tolerance is allowed for numerical differences. Store the tolerance and explanation with each submitted version. API count agreement does not verify estimated work time, financial savings or business outcomes. Access-only telemetry is explicitly insufficient to verify website work.

Management snapshots are dated, revisioned and immutable. Recompile creates a new revision when inputs change. Weekly trends use the latest retained revision per week. CSV and print exports use the selected historical revision, with observations separate from declarations and administrative subscription prices. CSV formula prefixes are escaped; print and UI text are escaped. All exports require console authentication and are audited.

## Historic Tracker import

Both source repositories were inspected. The continuation recovered corroborated Tracker browser history from this machine. The configured Supabase hostname currently returns NXDOMAIN, so a live backend export and reconciliation remain unavailable. Recovered imports use the distinct `tracker-browser-recovered` source and show an explicit provenance notice in native report/procurement details. Source repository access alone does not provide backend data. See HUB-INTEGRATION.md for actual recovery/import and activation records.

Supply an authorised JSON export with actual `entries` payloads, keeping credentials and personal data in a private directory outside Git. Optional read-only Supabase export uses `TRACKER_SUPABASE_URL` and `TRACKER_SUPABASE_SERVICE_KEY` in the server shell only. It restricts the destination to the Supabase HTTPS host and rejects redirects. Never put the service-role key into browser code or reports:

```sh
python3 -m gateway.hub_import --export-supabase /private/tracker.json --summary /private/export-summary.json
```

Validate a dry run first; the source Gateway database is opened read-only and cloned to a temporary migrated database:

```sh
python3 -m gateway.hub_import --database /private/gateway.db --file /private/tracker.json --source tracker-production --summary /private/dry-run.json
```

Monetary records require an explicit currency; legacy Tracker values can be UGX, so missing currencies produce validation errors rather than assumed dollar amounts. Review counts, demo skips, exact email matches, unmatched identities/tools, ambiguous names/URLs and validation errors. Supply a reviewed JSON mapping `{ "source-entry-id": "gateway-tool-id" }` via `--mapping` where needed. Never infer entitlement or overwrite existing subscriptions/sign-in settings from Tracker data. Registry metadata fills only blank descriptive URL/category fields. Legacy Tracker department-access entries (`kind=access`) require separate governance reconciliation and produce validation errors; they are never misclassified as purchases or Gateway tool access. Reports become adoption history, requests become procurement history (purchase subtype remains “other” where the old source does not specify it), and neither creates weekly obligations. External historical identities create no account. Original payloads remain in a private server import archive for reconciliation; they are not sent to staff browsers.

After reconciliation approval and a tested recovery plan:

```sh
python3 -m gateway.hub_import --database /private/gateway.db --file /private/tracker.json --source tracker-production --apply --backup /private/backups/before-hub-import.sqlite3 --summary /private/applied.json
```

Apply requires a new backup, integrity check and hash. Validation errors stop import. Writes are transactional. `(source, source ID)` plus content digests make unchanged re-runs idempotent; changed source records require explicit investigation rather than silently overwriting history. Summary/export files are exclusive and mode 0600. Preserve the original Tracker application/data until counts and individual records are verified and approved.

## Deployment and recovery

1. Review the PR and preserve existing environment/provider configuration, auth callback URLs, Netlify proxy and systemd/Caddy/Cloudflare service settings.
2. Stop writes during the final deployment window. Verify a SQLite online backup and hash, test opening it read-only with `PRAGMA integrity_check`, and record counts of catalogue, people, admins, assignments, subscriptions, keys, access requests and audit records. Store it outside any public/static or Git directory.
3. Run identity preflight and resolve every non-approved active account. Retain both approved owners and verify owner login before closing the deployment window.
4. Upgrade using migration v19; never alter migrations 1–18 or replace the live database with an empty one. Run a dry-run import and review its counts before any authorised apply.
5. Verify preserved Gateway rows/counts, new data reconciliation, role visibility, each access path, notification delivery state and backup restoration. Keep the separate Tracker operational until sign-off.
6. Restart the existing service using the established deployment guide. Keep URLs/slugs unchanged. Verify `/healthz` and authenticated flows from the public front door.

Recovery uses the verified pre-upgrade backup plus the matching prior application version. Stop all writers first; retain the failed database/WAL files for investigation and post-deployment record reconciliation. Restore with SQLite's backup API into the service's intended database path, then integrity-check and compare the recorded baseline counts before restarting the prior release. There is no reverse/destructive schema migration and no automated database replacement in these tools. A backup taken before activation cannot contain later writes; reconcile those explicitly.

## Notifications and validation

In-app reporting/procurement notifications work without email. Existing administrator notifications surface outstanding submissions, discrepancies and procurement queues. Optional SMTP uses existing settings and records `not_configured`, `pending`, `failed` or `sent`; delivery failure is never represented as success. Subjects/previews contain no prompts, secrets or provider credentials.

Run `python3 -m unittest discover`. Browser tooling remains temporary and is not a runtime dependency. With Playwright and axe installed outside the repository:

```sh
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome node tests/browser/check.cjs
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome node tests/browser/hub.cjs
```

These use temporary fixture databases and fake upstream providers. Check screenshots and actual logs. Production email, live import, public deployment and real vendor billing are separate operational verifications; local success must not be presented as those checks.
