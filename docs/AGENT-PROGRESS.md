# Agent progress

Last updated: 2026-11-02. Coordination branch: `team/log`. Product baseline: main
`ba82a2ad0c1516db9877263e9cac6eb01825618a`.

| Task | Owner | Branch | Status | Next step |
|---|---|---|---|---|
| G1: verify actual main, PR #6–#8, Actions and client gaps; record baseline | Chief | `team/log` | verified | Keep this audit synchronized with specialist findings. |
| Provider compatibility research and independent testability matrix | Probe | `feature/provider-compatibility` | todo | Read `/home/inquiline/swangz-team/mission/probe.md`; create/update only `docs/PROVIDER-COMPATIBILITY.md`; cite official sources and separate mock from live tests; report exact checks and unknowns. Starts after G1. |
| G2: architecture and security approval for desktop work | Sentinel | read-only audit | doing | Complete G2 decision note and explicit approve/conditions before any builder starts. |
| G3: OS credential storage and safe legacy file migration | Prism | `feature/device-credentials` | todo (after G2) | Read `/home/inquiline/swangz-team/mission/prism.md`; wait for Sentinel G2; use smallest bounded client task. |
| G4: signed/verifiable updater and rollback | Prism (client); Forge only if G2 assigns server changes | `feature/verified-updates` | todo (after G2/G3) | Wait for G2 and G3; implement only the approved signing/update protocol. Forge reads `/home/inquiline/swangz-team/mission/forge.md` before any later assigned backend task. |
| G5: Windows/macOS/Linux artifact workflow | Prism | `feature/desktop-distribution` | todo (after G2/G4) | Read Prism brief; verify unsigned test artifacts separately from signed installers; use Actions runners. |
| Approved coding-client setup with consent and rollback | Prism | `feature/client-setup` | todo (after G2) | Read Prism brief; wait for approved source/version list and consent/rollback requirements. |
| G5 continuity: device, web and browser revocation journeys | Forge then Prism, sequential | `feature/device-continuity` | todo (after G2) | Read Forge brief before backend work; no shared workspace writes in parallel. |
| G7 PWA/mobile verification and native-app decision | Prism; Probe independent check | `feature/mobile-readiness` | todo (after G2) | Read Prism brief; test install/update/logout on available devices; report unavailable device checks. |
| G8/G9 release evidence and independent approval | Probe, Sentinel; Chief consolidates | `team/log` | todo | Record actual output and unresolved risks; no merge/deploy without Arnold. |

## Baseline and audit evidence

- `python3 -m unittest discover -s tests -t .`: **Ran 426 tests in 503.976s — OK (skipped=13)**, Python 3.14. The first sandboxed attempt could not bind loopback fake services and reported 309 setup errors; the same command with localhost test access passed. Cleanup `ResourceWarning`s and intentional fake failure logs were visible. This is a local baseline, not cross-platform or browser verification.
- Latest `main` push: GitHub **Hub checks run 13**, `ba82a2a`, success (31 Oct 2026). PR #8 check run 12 also succeeded. The 13-run Actions history contains only `Hub checks`; `.github/workflows/build-app.yml` has no run there. No open PRs were returned by GitHub. PR #6 (`fdde8da`), #7 (`3cb203a`) and #8 (`ba82a2a`) are merged.
- Browser/staging and Windows/macOS client checks are not run locally in this audit. Use Actions for broad checks; no live provider API usage is claimed.
- Current PWA files include `gateway/static/hub.webmanifest` and `hub-install.js`. Native mobile builds are absent. Desktop key remains a local file; update availability is announced without binary replacement; `build-app.yml` is manual and unsigned.

## Decisions awaiting Arnold

- Confirm whether existing Windows code-signing and Apple Developer ID/notarization accounts/certificates are available for this work; no new purchases or account changes are assumed.
- Review the final internal-beta scope and release candidate at G9.

## Blockers

- Builders cannot start before Sentinel's explicit G2 approval. Sentinel was already conducting the read-only assessment when this audit began.
- Signed installers cannot be scheduled as committed scope until certificate/account availability is confirmed. Native app-store readiness is outside the 14-day plan.
- Live provider compatibility/attribution remains unverified; no provider credentials or real API tests were used in the baseline.
