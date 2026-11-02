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
