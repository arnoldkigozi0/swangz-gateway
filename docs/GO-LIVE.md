# Swangz AI Hub production activation

Use [Hub delivery](HUB-DELIVERY.md) for the exact backup, migration, deployment, recovery and optional Railway staging procedure. Both staff and admin run on the same first-party Caddy/systemd host. Netlify is optional legacy infrastructure. Permanent availability requires an always-on host; the existing automatic laptop tunnel can recover after waking but cannot serve while asleep or offline.

## Confirm the real deployment

- Identify the actual server, current commit/configuration, database path and schema version. Do not choose a production hostname, rewrite DNS or change Google callbacks from an example.
- Verify legitimate owner sign-in. Every staff/admin/custom role must use exactly `@swangzavenue.com`, with only the two organisation-authorised owner exceptions already documented in code.
- Preserve provider keys, subscriptions, sign-in settings, seats, tool assignments, staff/device keys and historical requests/audit records. Paid website subscriptions and API-provider credentials are separate access models; configure only what the company actually uses.
- Back up the existing database using SQLite's backup API, verify integrity and recovery, then run schema20/backfill/import dry runs on a scratch copy. Review every error, ambiguity and reconciliation count before applying changes.

## Host and cutover

Use the existing `deploy/setup-gateway-server.sh`, Caddy configuration and `deploy/swangz-gateway.service`. Python binds to localhost and Caddy serves HTTPS. Set both web/public URLs to the verified first-party host; register its exact `/auth/google/callback` only after the change is authorised and verified. Node, Netlify and the old Tracker frontend are not runtime dependencies.

Stop writes for final transfer/deployment. Keep one writable primary database. Deploy reviewed code, apply the additive migration/metadata backfill with a new verified private backup and summary, inspect the result, then restart. Verify local/public health, owner/staff sign-in, preserved counts, report-gate enforcement, entitlement denial, adoption/procurement review, exports and persistence. Keep the previous code/configuration and pre-upgrade backup for recovery; follow the matching-code recovery procedure rather than a destructive down migration.

## Tool access and staff rollout

| Tool configuration | Staff experience | Required organisation action |
|---|---|---|
| Own seat (`seat`) | Tool opens using the person's work account | Active company subscription and an assigned seat |
| Company SSO (`sso`) | Verified company SSO launch | Supported vendor plan and correct SSO launch URL |
| Shared account (`shared`) | Audited bounded turn; company browser where configured | Admin signs each company browser in, and verifies the relevant vendor plan/terms |
| API / developer tools | Device-key/API access through the Hub | Tool assignment and configured provider credentials, with policy/budget/report checks |

Keep passwords in the vendor's authenticated company browser; the Hub does not inject stored credentials into staff browsers. Company browsers run in one selected workspace location, using the existing Workspace Agent. [Workspace deployment](../deploy/WORKSPACE.md) describes the infrastructure and optional relay configuration.

Invite only eligible company identities and grant the minimum appropriate admin areas. Configure actual subscription plans/costs and assignments in Tools/People; procurement approval alone does not grant access. Install the existing extension where website access gating is required. Explain access-level telemetry and weekly reporting to staff. Verify submitted weekly reports clear only their matching reporting gate while independent suspension, entitlement and policy checks remain effective.

## Operations and acceptance

Configure appropriate retention, privacy, budgets and policies through the existing console. Try policies in the simulator before applying them. Optional SMTP failure must remain visible; in-app notifications continue without it. The setup script installs the nightly verified backup timer and a host firewall; set `GATEWAY_BACKUP_REMOTE` so copies also leave the server, and rehearse restores ([Hub delivery](HUB-DELIVERY.md#nightly-backups-and-the-firewall)). Restrict host/database access and retain immutable report/amendment/import history.

Inspect the Python suite, browser checks and GitHub Actions results; do not mistake prepared files for a deployed environment. Screenshots use synthetic data only. Historical Tracker cache records remain unverified until authorised backend/export recovery succeeds; normal Hub workflows do not depend on that recovery.

Hosting, storage, backups, domain and tool-subscription prices require current vendor quotations before purchase; old illustrative prices are not a deployment budget. Review actual spend separately from estimated API cost, administrative allocations and staff-reported benefits. Actual implementation/testing and external blockers are in [Hub completion](HUB-COMPLETION.md).
