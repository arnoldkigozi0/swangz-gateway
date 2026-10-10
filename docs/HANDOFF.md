# Moving Swangz AI Hub to another machine

Read [AGENTS.md](../AGENTS.md), [CLAUDE.md](../CLAUDE.md), [State](STATE.md), then [Hub delivery](HUB-DELIVERY.md). Use the existing Gateway repository; staff and admin are one Python/SQLite application. Netlify and the old Tracker frontend/backend are not required.

```bash
git clone https://github.com/arnoldkigozi0/swangz-gateway.git
cd swangz-gateway
python3 -m unittest discover -s tests -t .
```

Production requires Python 3.10+ and Git. Browser-check npm dependencies are test-only. Current source schema is 20; the recorded final local suite contains 331 tests. Verify the checkout's actual test result rather than relying on this count.

## What travels in Git

Code, catalogue definitions, shared UI assets, browser extension, migrations, synthetic fixtures, tests and deployment documentation travel in Git. Provider keys, Google client secrets, environment files, actual staff databases, private exports and backup/reconciliation summaries do not.

## Secrets and identity

Transfer the existing private `.env` securely outside Git; never paste secrets in chat or email. Use mode 0600. Preserve all provider/workspace/SMTP configuration and explicitly verify the destination's absolute `GATEWAY_DATA` path. Do not replace live configuration with `.env.example`.

Both `GATEWAY_PUBLIC_URL` and `GATEWAY_WEB_URL` should reference the verified first-party HTTPS host. Preserve registered Google callbacks until an authorised change is verified. An old Netlify callback is historical configuration, not a required hosting architecture. First-party production needs no Netlify token or proxy; laptop legacy synchronisation is opt-in only.

Every staff/admin/custom-role identity must use exactly `@swangzavenue.com`, except the two explicitly authorised owners `arnoldkigozi0@gmail.com` and `marvinmusokessekatawa@gmail.com`. Environment allowlists and historical imported email addresses cannot widen this rule. Verify legitimate owner access before cutover.

## Database transfer and recovery

The database holds people, assignments, subscriptions, keys, access requests, launches, evidence, weekly/adoption declarations, purchasing and audit history. Never create a fresh database as a substitute for it.

1. Verify the actual running commit, `meta` schema version, absolute database path and current counts.
2. Make a private SQLite backup using the backup API and check integrity/hash. Do not copy only a live WAL database. Rehearse the additive migration and metadata backfill on a scratch copy.
3. Stop writes on the original host for final transfer. Copy the verified stopped backup and private configuration securely to the destination. Keep only one writable primary host.
4. Follow [Hub delivery](HUB-DELIVERY.md) for migration, backfill, restart, health, login, entitlement/report gates and count-preservation checks. Keep a verified pre-upgrade backup and the old code/configuration.
5. For rollback, stop writes, preserve the upgraded database, restore the verified backup with the matching prior code and reconcile any post-cutover writes. Never run old code against a newer schema or silently discard activity.

A separate clean development/staging environment may use a new synthetic database. Railway's explicit staging launcher refuses an unmarked existing database and production provider/OAuth/SMTP credentials before migration; never mark the real database as staging.

## Historical Tracker recovery

Normal native Hub workflows operate independently. Recovered cache entries retain provenance and remain unverified against the unavailable Supabase endpoint. Retain original exports; use the read-only recovery diagnostic and idempotent dry-run import before any approved import. [Tracker parity](TRACKER-PARITY.md) and [completion evidence](HUB-COMPLETION.md) document actual scope and limitations.

## Operational checks

Use [automatic laptop hosting](../deploy/LAPTOP-AUTO.md) for the existing Linux service/direct tunnel, or [Hub delivery](HUB-DELIVERY.md) for permanent Caddy/systemd hosting. Verify health from the actual address. Inspect test outputs and GitHub checks. Migrations are forward-only; audit measured facts, estimates and declarations separately; keep private data out of commits, screenshots and CI.
