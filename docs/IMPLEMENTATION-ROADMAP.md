# Swangz AI Hub — 14-day implementation roadmap

**Window:** 2–16 November 2026. **Baseline:** main `ba82a2a`; 426 Python tests passed in 503.976s
(13 skipped). See [remaining-work matrix](REMAINING-WORK.md) and [release readiness](RELEASE-READINESS.md).

## Order and gates

| Stage | Window | Owner(s) | Exit evidence |
|---|---|---|---|
| G1 — audit actual main, PRs, Actions, implementation and local baseline | 2 Nov | Chief | Matrix and actual test/CI evidence recorded; completed PR #6–#8 are not reopened without a defect. |
| G2 — architecture/security decisions | 2–3 Nov | Sentinel, read-only | Written approval/conditions for OS credential storage and migration, signed update trust/rollback, package channels, setup consent and device continuity. Builders wait until this is explicit. |
| G6 research in parallel | begins after G1; target 4 Nov | Probe | Official-source provider matrix; real-vs-mock verification scope and any credential requirement stated. |
| G3 — native credential storage | target 3–6 Nov | Prism | Linux/Windows/macOS adapters and safe existing-file migration; CI tests each platform. |
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

## Beta scope decision

Aim for a controlled internal beta of the existing web/PWA and whichever desktop builds meet G3/G4.
Do not call unsigned packages production installers. Defer a native mobile app and any signed installer
whose required identity/certificate is unavailable. Never treat a Swangz session as a provider session;
retain official provider OAuth/SSO, company-seat and approved user-login flows.
