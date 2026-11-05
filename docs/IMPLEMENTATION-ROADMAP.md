# Swangz AI Hub — 14-day implementation roadmap

**Window:** 2–16 November 2026. **Baseline:** main `ba82a2a`; outside-sandbox baseline supplied by Arnold: Ran 426 tests in 1191.8s, OK (skipped=13), exit 0. See [remaining-work matrix](REMAINING-WORK.md) and [release readiness](RELEASE-READINESS.md).

## Order and gates

| Stage | Window | Owner(s) | Exit evidence |
|---|---|---|---|
| G1 — audit actual main, PRs, Actions, implementation and local baseline | 2 Nov | Chief | Matrix and actual test/CI evidence recorded; completed PR #6–#8 are not reopened without a defect. |
| G2 — architecture/security decisions | 2–3 Nov | Sentinel, read-only | Written approval/conditions for OS credential storage and migration, signed update trust/rollback, package channels, setup consent and device continuity. Builders wait until this is explicit. |
| G6 research in parallel | begins after G1; target 4 Nov | Probe | Official-source provider matrix; real-vs-mock verification scope and any credential requirement stated. |
| G3 — native credential storage | target 3–6 Nov | Prism client first; Forge backend next, sequential | Linux/Windows/macOS adapters and safe existing-file migration; CI tests each platform. |
| G4 — signed/verifiable app update | target 6–10 Nov | Prism; Forge only if G2 assigns server work | Signed metadata/artifact validation, tamper/rollback/interruption coverage and a documented recovery path. |
| G5 — desktop CI packages | target 9–12 Nov | Prism | Three-OS build/smoke workflow; test artifacts labelled unsigned; production signing only if authorised certificates and services are available. |
| G4 — optional coding-client setup | target 10–12 Nov | Prism | Per-client consent, approved pinned sources, integrity and rollback; otherwise leave out of beta scope. |
| G5/G7 — continuity and mobile verification | target 11–13 Nov | Forge then Prism, sequential workspace ownership; Probe verifies | Revocation and browser/PWA journeys pass; iOS/Android device results or explicit unavailable checks; native packaging decision documented. |
| G8 — full regression and independent review | target 13–15 Nov | Probe, Sentinel; Chief integrates | Actual Python, browser/staging and OS CI logs; independent security approval; all remaining issues triaged. |
| G9 — release candidate dossier | 16 Nov | Chief | Exact reviewed commit, available artifacts and signature status, test results, rollback/operations, known bugs, cost/provider usage, Arnold decisions. No merge/deploy. |

Only one builder writes in the shared workspace at a time. Each implementation task gets its own
`feature/<task>` branch, a short specification, independent review and PR. The team uses GitHub Actions
for broad platform builds and expensive browser work. If a gate or required account access slips, keep
work moving on independent research/docs and revise beta scope rather than skipping security gates.

G1 is closed. G2 credential work is approved at `bf8ebfc` (pushed); G4 remains TEST-key-only.
Prism begins G3a per [the bounded specification](AGENT-PROGRESS.md#g3a-bounded-implementation-specification).
Chief and Prism do not run tests under Codex: use Forge/Probe or Actions. Full suite at integration
milestones; targeted tests between them.

## Beta scope decision

Aim for a controlled internal beta of the existing web/PWA and whichever desktop builds meet G3/G4.
Do not call unsigned packages production installers. Defer a native mobile app and any signed installer
whose required identity/certificate is unavailable. Never treat a Swangz session as a provider session;
retain official provider OAuth/SSO, company-seat and approved user-login flows.

## Amendment 01 backend proposal — 22:06 review checkpoint

Forge returned a design proposal only, not implemented or security-approved. Proposed additive tables
cover provider-account ownership/payer/route, per-field provenance and freshness, sync state, verified
webhook replay/idempotency, consent, workspace pointers and expiring explicit sharing grants. Personal
content and subscription tokens remain on devices/existing environments. Company admin secrets use
references only; per-user tokens remain gated. Official adapters require provider evidence; unsupported
fields remain unavailable/manual; hourly polling uses backoff. No shipped migration changes or backfill.

Required design corrections before acceptance: document a workable PKCE verifier lifecycle (a hash
alone cannot redeem a code; token-storage prohibition still holds); preserve metadata/audit on ending
a connection; define company-held versus person-held identity and route enums consistently with D012;
restrict console listing by area and classify personal metadata; make sharing grants metadata/pointer
permissions only, with no server content access; scope event deduplication to the authenticated provider
connection/tenant; require documented signature algorithm rather than assuming HMAC comparison;
allowlist secret references and outbound destinations against file-read/SSRF abuse; describe disconnect
revocation failures honestly; remove unsupported zero-cost claims. Await Forge corrected text and
Sentinel review. No migration/code/production change authorized by this proposal.

Prism's Chrome/profile/workspace design remains next documentation work after the credential fix
handoff, under D015/016/017. Company machine policy versus personal advisory profiles, system-browser
OAuth, seat/profile lifecycle, bypass checks and measured remote capacity must be explicit.


## Amendment 01 backend design v3 — 6 November 01:22 (proposal)

Forge returned corrected text only (delegation bc04d42d-2663-43c4-96bc-e7adb75e25c1).
No code, files, tests, credentials or provider calls; no technical acceptance yet.

First proposed task: manual provider-account registry, with additive provider_accounts and
provider_account_values tables at the next available migration version after a deliberate integration
base decision. No existing-table writes/backfill or shipped migration edits. Staff list/register
individual or seat accounts, append manual values, and end their own accounts; ended records and
before/after/correlation audit remain. Console reads pass a single field-level access rule.
route = individual|seat|api|enterprise; account_holder_kind = person|company, holder_person_id iff
person (two-way CHECK); payer = person|company|none. Individual/seat holders must be people.
No secret_ref_id in this task. Existing shared-tool turns stay unchanged.

Proposed visibility: holder sees own metadata; other-person IDs 404. govern sees company/seat metadata,
but individual accounts only existence/provider/route/status/sync health. money sees financial/quota/
credit/period fields only for company-paid accounts. trust sees sync/webhook error counts; console
viewer sees nothing. Labels/values for individual accounts never reach console. These overlapping
rules and the existing console visibility convention require Sentinel's ruling before implementation.
No provider identity, seat or financial manual declaration becomes verified evidence or entitlement.

Task 1 acceptance: own-data IDOR matrix for list/read/end/add-value; console area and field matrix;
enum and bidirectional holder CHECK failures; unavailable defaults and explicit manual provenance;
idempotent end retains values/audit; permission sweep for every new route; existing data and schemas
preserved, prior migrations byte-identical; no secrets in responses/logs. Tests use synthetic data/fake
upstreams. Also require Sentinel to settle paused-account write denial, who may assert company payer
or seat records, bounded values/labels, duplicate accounts and audit privacy before build authorization.

Deferred tasks (separate branches/reviews): (2) metadata-only expiring sharing_grants/workspace_refs,
no content proxy; (3) secret_refs/sync state without adapter; (4) cited official adapter; (5) cited
vendor webhook receiver; (6) OAuth after D-017 ruling. No task 1 outbound traffic/OAuth/sync/webhooks/
secret refs/grants/workspace pointers. Unsupported provider quota, credit, period, seat/account identity,
usage, PKCE and revoke claims stay unavailable/manual until Probe verifies official sources.

Later design proposals, NOT approved: device-generated PKCE verifier/challenge, server hashed state
bound to person/session/device/provider/challenge (10-minute single use), memory-only auth-code pickup
(120 seconds), device redemption and device-only tokens. This conflicts with D-017 confidential client;
callback context, atomic pickup and public-client vendor support need security review. Event dedup
(provider, connection_id, event_id) only after cited raw-byte signature and timestamp validation;
64 KB cap, content/rate bounds, uniform refusal, ordered events, rotation overlap, bounded ledger.
Proposed secret allowlist: owner-approved references, fixed env prefix GATEWAY_PSEC_ or service-owned
0600 files inside fixed directory without symlinks; never expose paths. Adapter endpoints fixed HTTPS,
exact hosts, no redirects/private IPs, rebinding defense, response/time limits. Disconnect has ending/
ended/revoke_failed, retry/notification without false confirmation; personal revocation remains holder's
vendor action. Polling hourly sequential with jitter/backoff/Retry-After, capped and measured before
enabling; costs unknown, no actual VPS access authorized.

Sentinel decisions requested: D1 integration base/migration numbering; D2 public-device vs confidential
OAuth and D-017; D3 console privacy/incident access; D4 future adapter location/capacity evidence;
D5 grant duration/ledger retention (Forge floated seven days, not accepted); D6 secret-ref owner-only
management; D7 fixed callback/Host fallback. Decide first-task blockers now and defer unrelated later
choices rather than prematurely approving all six tasks. Return bounded threat note and explicit verdict.


## Task 1 security gate — Sentinel, 6 November 01:29

APPROVED WITH CONDITIONS for manual registry only; supersedes conflicting v3 proposals above.
Review covered team/log 6052187, amendment and relevant staff/authz/audit/db/tool-delete code;
Sentinel wrote nothing and ran no tests. Tasks 2–6 remain unapproved.

Base: 4aaccf8 (tree 87b8862), feature/provider-registry. Append v24, preserve SCHEMA[:23]
byte-for-byte. Base includes pending v22/v23 stack; inherits holds and cannot merge ahead of required
#19–#27 dependencies. If stack changes, merge base without rebase/force-push, renumber only own
migration if necessary, and obtain renewed review. No main merge authorized.

D-019 proposed ruling: central server visibility = record-kind field ceiling intersect actor areas,
then union across allowed areas. Ceiling applies even to console owner. Console GET list/detail use
area=(govern,money), enforce inside handler/function if dispatcher skips GET areas. 403 for viewer,
security/emergency/admin-only; no trust access. No break-glass, search/Timeline/insight/notifications/
CSV/exports additions. Exact field matrix:

| Fields | Holder | govern | money |
|---|---|---|---|
| Individual id/tool/route/status/created/ended | yes | yes | no |
| Individual payer/label/values/creator | yes | no | no |
| Seat core/payer/assertor/label | yes | yes | yes |
| Seat plan/quota_limit/quota_used/period_end | yes | yes | no |
| Seat credit_balance/monthly_price | yes | no | yes |

Holder staff routes: GET/POST /provider-accounts; GET /provider-accounts/<id>;
POST /provider-accounts/<id>/values; POST /provider-accounts/<id>/end. Console list/detail only.
All routes require ordinary active approved web identity; none paused_ok; paused/ended people,
extension sessions and device keys refused. EXTENSION_PATHS and pinned paused route set unchanged.
Writes require x-swangz-app CSRF guard. Global AI pause alone does not block registry.

Session fixes holder_person_id; account_holder_kind=person; assertion=holder_declared. Strict allowed
request fields; reject extras/holder/company assertions with 400. individual payer=person|none;
seat payer=company, labelled declared by holder, unconfirmed. Never count these declarations in
spend/licences/totals or feed entitlement/policy/turns/subscriptions/notifications. api/enterprise/
admin_declared enums exist but routes cannot write them; no company-held creation. Refuse tools
with signin shared or api. No provider-account email/identity field. Missing fields represented as
{state: unavailable}, never zero. Existing enum/holder two-way constraints still required.

Bounds: NFC + trim optional label <=80 chars, plan <=60; reject controls, U+202A–202E/U+2066–2069,
text starting sk-/AKIA/ghp_/xox/Bearer-space and >=32 contiguous key-like characters without spaces.
Fixed kinds plan/quota_limit/quota_used/period_end/credit_balance/monthly_price, last two financial.
Finite decimal numbers 0..1e12; ISO dates 2000..2100; as_of <= tomorrow; three-letter ISO 4217 currency.
20 active accounts/person, 200 values/account; existing per-person limiter only. Partial unique index
allows one active (holder,tool,route); ended registration may be recreated.

Immutable value rows: triggers abort UPDATE/DELETE, account trigger aborts DELETE. End active->ended
transactionally; repeated end 200 same timestamp/no new audit; append value to ended 409. Store purge
must leave registry alone. FK to tools/people ON DELETE RESTRICT; adjust existing admin tool-delete
handler to give clear 409 rather than 500 (explicitly within scope). Audit is broadly console-readable:
before/after may contain status/route/tool_id/value-kind/value-id only; never label/value in audit,
detail or logs. Correlation person:<id> and provider_account:<id>.

Acceptance tests, synthetic/no outbound:
1. Ownership IDOR, indistinguishable missing vs other-person 404 on all relevant operations.
2. Exact matrix for holder, console owner/govern/money/combined/security/admin-only/viewer.
3. Enum, holder, route/payer, status/timestamp checks, active duplicate index and immutable triggers.
4. Strict bodies/assertions; company/api/enterprise/admin_declared unreachable; shared/api tool denial.
5. All input/count/rate limits including decimal/date/currency/secret/control/bidi boundaries.
6. Every route denies paused/ended/wrong session kinds; missing CSRF header 403; pinned route set unchanged.
7. Entitlement, subscription, licence/spend, search/insight/notification behavior unchanged.
8. End idempotent, records retained, no values after end; tool-delete 409 and purge exclusion.
9. Unique private label/value markers absent from audit, stderr/access logs and individual console responses.
10. len(SCHEMA)==24, SCHEMA[:23] hash matches base; fresh DB and populated synthetic v23 upgrade preserve rows.
11. Permission sweep every new staff/console route; full suite green before implementation commit.

Implementation paths: gateway/registry_schema.py (new), gateway/db.py append, gateway/registry.py
(new routes/visibility), route import, existing admin tool-delete conflict handler, tests/test_provider_registry.py,
permission sweep coverage, short existing doc section and CLAUDE.md schema line. No static/UI, outbound,
OAuth/sync/webhooks/secrets/sharing/workspace pointers/admin writes/new dependencies/production access.
Builder targeted checks then milestone full suite (outside Codex); exact output/tree required. Probe verifies
exact artifact, then Sentinel reviews full diff from 4aaccf8 before Chief opens PR.

Deferred: D2 public-device OAuth rejected for now, D-017 confidential server client + PKCE stands;
changing it requires ADR/Arnold/task6 review. D4 capacity/adapter location task4; D5 grant/ledger limits
remain unapproved (seven days not accepted); D6 secret-ref management task3; D7 fixed callback/Host
fallback task6 (existing defect retained). Sentinel's permanent D-019 ADR write remains queued until
writer handoff; this coordination record preserves the ruling without modifying Sentinel-owned files.


## Registry correction gate R1–R5 — Sentinel, 6 November 02:27

48cc003/tree 4145f9f remains BLOCKED, not approved implementation. Sentinel read full diff and
local c388134 QA entry; no writes/tests. Required correction scope follows; supersedes earlier
conflicting parser/audit prescriptions. Forge owns correction, then Probe exact-artifact QA, then
Sentinel full diff 4aaccf8...new-head. No rebase/force-push, no merge/deploy.

R1: amend unshipped v24 with BEFORE INSERT abort for existing NEW.id on both account and value
tables; account trigger ALSO aborts an active holder/tool/route conflict (partial-index REPLACE
under new id). Do NOT enable recursive_triggers globally. Test INSERT OR REPLACE, REPLACE INTO,
partial-index replace, account with/without child values; original rows/values/audit unchanged.
Normal register/append/end still pass.

R2: _text rejects Unicode categories starting C (Cc/Cf/Cs/Co/Cn) plus Zl/Zp. Separate bidi ranges
unnecessary; rejecting ZWJ sequences accepted. Catch UnicodeEncodeError at write boundary -> 400
bad_text, no traceback. Test lone D800/DFFF labels/plans, 200B/200E/200F/FEFF/2065/206A/00AD/E000;
normal accented text and standalone emoji accepted.

R3: registry audit ONLY: actor holder name, existing three action verbs, target provider_account:<id>;
before/after status only or value_id only. No tool_id/route/kind/payer/label/value. Correlation
provider_account:<id>, NOT person:<id>, to exclude registry from person Timeline. General audit
semantics unchanged. Document in V2: all console users can see named person changed declarations
and when, while tool/route/kind/contents only through field-gated registry reads. Before RELEASE,
Privacy page must disclose this; separate UI task, registry unreleased until complete. Tests viewer,
money-only/security-only Audit/search/Timeline reveal no individual tool/route/kind; person Timeline
has no registry rows; existing marker-leak checks retained.

R4: remove statements() parser. Preserve original str migration split(';') loop exactly; tuple entry
executes each element as one statement (sqlite rejects multi-statement elements). v24 tuple; all
SCHEMA[:23] strings unchanged; future trigger migrations tuple too. Tests fresh DB, populated v23
upgrade unchanged data, failed tuple statement rolls back to v23/no partial tables/triggers, len=24.

R5 required now: gateway-local settings.tz_offset_minutes for default as_of/tomorrow, test Kampala
00:30 at previous UTC date. Reject >6 decimal places for number and string alike; Decimal(repr(float)),
no silent rounding of 1e-7; test seven-place pairs. Casefold secret prefixes sk-/akia/ghp_/xox/bearer-space;
test SK-, Ghp_, BEARER x. Currency set from Probe-verified SIX ISO4217 List One, date comment,
active codes only; if unavailable preserve old list and explicitly record missing citation, do not
infer individual codes from memory. Probe must compare against actual file. Remove V2 EOF blank.
Whitespace-only optional label acceptable, required plan whitespace rejected by test. Refused writes
counting toward existing limiter intentional, leave unchanged.

Correction files: registry_schema.py/db.py/registry.py/test_provider_registry.py/docs/V2.md. No UI,
outbound product traffic/OAuth/sync/webhooks/secrets/sharing/admin writes/deps. All R regressions
and Probe adversarial cases, prior 54 checks and diff --check required; full suite once with retained
raw log/exit/tree. D-019 permanent ADR still queued after writer slot, with amended R3 wording.
