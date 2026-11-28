# Swangz AI Hub operations and migration

The Hub uses the existing Python standard-library server, SQLite database, vanilla UI, provider configuration and deployment URLs. The repository remains `swangz-gateway`. PR #4 was merged and the existing laptop instance activated after the user requested completion. Actual backup, migration, recovered-history import and public verification results are recorded in HUB-INTEGRATION.md. DNS and Google callback configuration were preserved.

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

## A company login after someone loses access

A tool set up as one company login (`signin = 'shared'`) is a password people sign in with themselves. Removing the tool or suspending a person blocks it wherever Swangz controls the browser, but **does not end a session already open with that login, or make anyone forget the password**: on a personal browser without the extension they can keep using it. Only changing the password with the provider ends that, and Swangz cannot do it.

So when a console change takes such a tool from someone (removing their grant or their team's, suspending them, or changing their team or account end date), **Needs attention** lists *Change the password of …'s company login* with their names. It stays until they have the tool again, the tool stops being one company login or is archived, or an admin with the govern role records the change: `POST /admin/api/tools/{tool}/login-password-changed` (no body, no password; answers `{"ok": true, "cleared": n}` and is audited). The console has no button for this yet. A grant or account that simply reaches its end date raises nothing, and neither does access removed before this reminder existed: check those by hand.

## Weekly operation

`GATEWAY_TIMEZONE=Africa/Kampala` defines Monday 00:00–following Monday 00:00, a half-open interval. Period labels show Monday–Sunday. Keep this zone stable after activation: closed snapshots retain their stored zone and boundaries. Budget periods continue using the existing `GATEWAY_TZ_OFFSET`.

Existing maintenance compiles completed weeks before retention, runs after restart and periodically, and resumes safely. Access checks also compile missing periods, using process-local source-ID watermarks between week boundaries; restart, rollover and maintenance rescan safely, and late records never rewrite frozen evidence. No separate scheduler or external service is required. Only admitted API requests, opened launches, allowed website visits and shared-account occupancy create obligations. Blocked-only evidence creates no required report. Closed evidence snapshots are frozen; late events do not silently rewrite submitted history. Existing retention means older missing evidence cannot be reconstructed; explicitly disclose those gaps.

Staff Home shows outstanding counts. Weekly reports has pending/returned, submitted and adoption views. The six-step wizard saves drafts and prefills observed activity. Tracker/staff metered allowances, unit prices, allocations and flat-subscription flags remain typed declarations with their original pricing basis and USD units; no declaration becomes verified vendor spend. Unknown numerical amounts stay blank/NULL; zero means known zero. Opening a site can be declared “opened but not used” with a reason. Business impact, savings and revenue remain estimates.

Drafts and returned reports block that tool. Submission/resubmission clears that report's gate immediately; review or confirmation is not required to resume. Other independent controls still apply: suspension, entitlement, subscription, policy, budgets/rates and emergency stop. Reports and help remain accessible. Emergency overrides require emergency authority, exact person/tool scope, a reason and an expiry of at most 24 hours; every override is audited.

Launches, extension decisions, provider API calls with existing keys and Studio creation paths enforce the server gate. On unscoped keys, housekeeping/media-status requests may retrieve existing results; tool-scoped keys are gated on those too. Shared turns end at the week boundary; the existing workspace sweep revokes remote sign-ins and retries failed revocations. The Gateway cannot enforce vendor-site access in an unmanaged browser outside the Hub or its installed extension; managed extension/company-browser deployment remains necessary. Denials expose `weekly_report_required`, the relevant report ID and its authenticated link. Extension website telemetry remains access-level only, with no keystrokes or page contents.

### API key attribution

New staff connection keys are scoped to the selected catalogue tool. Administrators may pass `tool_id` when issuing a key; CLI supports `issue-key PERSON_ID --tool TOOL_ID`. Scope checks require an available assigned API/developer tool. Provider mismatch and entitlement failures remain denied. Scope determines the audited API tool; a supplied user-agent cannot change it.

Only leaving `tool_id` out (CLI: no `--tool`) issues an unscoped key. A `tool_id` that is empty, blank, `null` or not a tool answers 400 (the CLI exits with the reason) and no key is made. A tool-scoped key may make model requests, start and follow media jobs, and these other requests, matched exactly (`SCOPED_KEY_OTHER` in `gateway/parse.py`): Anthropic `GET /v1/models`, `GET /v1/models/{id}`, `POST /v1/messages/count_tokens`; OpenAI `GET /v1/models`, `GET /v1/models/{id}`, `POST /v1/responses/compact`; ElevenLabs `GET /v1/voices`, `GET /v1/voices/{id}`, `GET /v1/models`; Higgsfield `POST …/requests/{id}/cancel`. All of them, job polling included, need the key's own provider, an assigned and unarchived tool and no overdue weekly report; the listed requests are also checked against company policies and model rules. Everything else answers 403 and is recorded as `key tool scope`, including `/v1/completions`, `/v1/embeddings`, ElevenLabs `/v2/voices` and Higgsfield `/v1/job-sets/*` and `/v1/motions`. A scoped key follows or cancels only jobs recorded under its own tool.

### Media job ownership

A voice, image or video job belongs to the person who started it: the person on the first `media` request, successful, that the same provider answered with that job ID. Only they can follow or cancel it, from any of their keys and devices; a tool-scoped key must also be for the job's tool. The checks above run first. The job ID is taken only from the provider's answer, never from anything the calling tool sends, and a poll's result is copied only onto the poller's own records.

- Higgsfield: every request with `requests` in its path, whatever the method, must be written exactly `/requests/{id}`, `/requests/{id}/status` or `/requests/{id}/cancel` (a prefix such as `/v1` is allowed) and name the person's own job. The same applies to job sets: every request with `job-sets` in its path must be written exactly `/v1/job-sets/{id}` and name the person's own (tool-scoped keys can't use job sets at all).
- A custom provider with `dialect: "media"` (`GATEWAY_PROVIDERS`): a `GET` is forwarded only when a whole path segment equals one of the person's own job IDs on that provider and no segment is someone else's (so listing and other account-wide `GET` paths, `/v1/models` for example, are refused for every key); a cancel (a `POST` path with `requests` and `cancel` segments) must be written `…/requests/{id}/cancel` with the person's own `{id}`; any other `POST` may start a job but is refused when a path segment is someone else's job ID; every `POST`, a cancel included, is also refused when a top-level string of its JSON body is someone else's job ID (a value of the top-level object, including each of a repeated name, an item of a top-level array, or a body that is one string; whatever content type it is sent as); every other method (`PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`) is refused for every key. A path with empty, `.`, `..`, `%`-encoded, `;`, `#` or backslash segments is refused. Any query string is refused, for every key. So is a `POST` body that can't be checked: one sent with a `Content-Encoding` other than `identity`, one that says or looks like it is JSON (content type, or a first character of `{`, `[` or `"`) and can't be read, or one with more than 1000 different top-level strings. All of these are recorded as `job ownership`.

An unknown job, a poll or cancel that names none, and a job whose record retention has purged answer 403, recorded as `job ownership`. If the records can't be read, the answer is 503, recorded as `job ownership check failed`. A poll that arrives while the request starting the job is still being written down waits for it, for at most ten seconds.

Not covered by this check: ElevenLabs `GET` requests on unscoped keys; and, on a custom provider, a job ID that is not a whole path segment or a whole top-level JSON string exactly as recorded (nested deeper, an object name, part of a longer string, in another letter case or with something attached such as `{id}:cancel`, `{id}.json` or `{a},{b}`), a job ID in a header or in a body that is not JSON (a form or file upload), and a job with no recorded owner: its record purged, its start not successful, or its starting request still being written down (a `POST` naming it is forwarded, and so is a `GET` that also names one of the person's own jobs; an answer to a `POST` naming a purged job makes it the sender's). Company policies and model rules do not apply to a custom provider's `GET` or to job polling.

Company policies, their monthly caps and the policy simulator take a scoped key's tool from the key, whatever the user agent says; a request on an unscoped key is placed by its user agent as before. The separate Claude Code / Codex assignment check on the user agent still applies to every key, so a client that names itself as one of them also needs that assignment. Usage reports follow the same attribution: Who used what, spend by tool, a tool's usage page, the timeline's tool filter and label, and the revoke and seat simulators count a scoped key's requests under the key's tool. A request's full record names the key's tool, and on Licences & spend (and its idle-seat count under Needs attention) a scoped key's use fills only the seat of the key's tool; unscoped use fills seats as before. For keys without a tool they are as before, so a tool's page and the timeline filter can show one provider request under each API tool of that provider. **Policies → Explain** answers the same way when the person holds a live key scoped to the tool you pick: it adds a **Their key's tool** check (assigned, available and not removed), applies the rules to that tool and says so in its note. It does not check overdue weekly reports.

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

1. Review the PR and preserve existing environment/provider configuration, auth callback URLs and systemd/Caddy/Cloudflare service settings; use first-party delivery without a required Netlify proxy.
2. Stop writes during the final deployment window. Verify a SQLite online backup and hash, test opening it read-only with `PRAGMA integrity_check`, and record counts of catalogue, people, admins, assignments, subscriptions, keys, access requests and audit records. Store it outside any public/static or Git directory.
3. Run identity preflight and resolve every non-approved active account. Retain both approved owners and verify owner login before closing the deployment window.
4. Upgrade using migration v20; never alter migrations 1–19 or replace the live database with an empty one. Run a dry-run import and review its counts before any authorised apply.
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

## Native business workflows and v20

See [delivery and recovery](HUB-DELIVERY.md) for the reviewed v20 backfill command, verified backup and first-party VPS cutover. [Parity](TRACKER-PARITY.md) maps the complete source workflows; [actual checks](HUB-COMPLETION.md) distinguishes local proof from external deployment/history blockers. Test tooling can be installed with `npm ci --prefix tests/browser`; it is not a runtime dependency. Run `node tests/browser/business.cjs` for the five-width, two-theme matrix and both wizards, and `node tests/browser/staging.cjs` for isolated restart persistence.

Use Business value → Management for plan references, unknown-tool association, department-report scope review, current financial assumptions, company project folder and notification delivery/retry. Staff business declarations remain separate from weekly accountability. Never treat recovered browser provenance as a complete authoritative Supabase recovery.
