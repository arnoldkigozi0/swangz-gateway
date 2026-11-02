# Agent progress

Last updated: 2026-11-02. Coordination branch: `team/log`. Product baseline: main
`ba82a2ad0c1516db9877263e9cac6eb01825618a`.

| Task | Owner | Branch | Status | Next step |
|---|---|---|---|---|
| G1: verify actual main, PR #6–#8, Actions and client gaps; record baseline | Chief | `team/log` | verified | G1 closed: audit, matrix and exact outside-sandbox baseline recorded; refresh evidence at integration milestones. |
| G2: architecture and security approval for desktop work | Sentinel | `docs/architecture-review` (`bf8ebfc`, pushed; GitHub branch verified 2 Nov) | verified | Arnold to decide outstanding product, budget and signing-key items below. |
| G3a: client OS credentials, migration and removal of copied keys | Prism | `feature/device-credentials` | doing | First bounded implementation handoff below. Sole code writer; targeted checks through Forge or CI, then Probe verification and Sentinel review. |
| G3b: server credential lifecycle and rotation | Forge | `feature/device-credential-lifecycle` | todo | Start after Prism hands back workspace ownership. D-001 heartbeat storage report, D-002 idle expiry/rotation and append-only v22; technical ambiguities go to Sentinel before implementation. |
| G4: signed/verifiable updater and rollback | Prism | `feature/verified-updates` | todo; TEST-key work approved | Implement only D-003/D-004/D-005 with TEST keys, signed/expiring manifest, anti-rollback, staged swap, 60-second self-test and rollback. Production signing prerequisites remain unresolved. |
| Provider authentication boundaries and per-tool compatibility | Probe | `feature/provider-compatibility` | doing | Correction request `01e42059-61f5-4bf9-aa91-5e10a0b1e05b` remains active. Initial `dee2d87` covers all 49 IDs but needs field/source corrections. Research only; no live provider tests. |
| G5: Windows/macOS/Linux artifact workflow | Prism | `feature/desktop-distribution` | todo (after G2/G4) | Read Prism brief; verify unsigned test artifacts separately from signed installers; use Actions runners. |
| Approved coding-client setup with consent and rollback | Prism | `feature/client-setup` | todo (after G2) | Read Prism brief; wait for approved source/version list and consent/rollback requirements. |
| G5 continuity: device, web and browser revocation journeys | Forge then Prism, sequential | `feature/device-continuity` | todo (after G2) | Read Forge brief before backend work; no shared workspace writes in parallel. |
| G7 PWA/mobile verification and native-app decision | Prism; Probe independent check | `feature/mobile-readiness` | todo (after G2) | Read Prism brief; test install/update/logout on available devices; report unavailable device checks. |
| G8/G9 release evidence and independent approval | Probe, Sentinel; Chief consolidates | `team/log` | todo | Record actual output and unresolved risks; no merge/deploy without Arnold. |

## Baseline and audit evidence

- **G1 test baseline, supplied by Arnold on 2026-11-02:** `python3 -m unittest discover -s tests -t .` on main `ba82a2a`, outside any sandbox on this laptop: **Ran 426 tests in 1191.8s, OK (skipped=13). Exit code 0.** This exact result supersedes the earlier timing as the canonical G1 evidence. It is a fake-service baseline, not browser, platform or live-provider verification.
- The earlier 309 fixture setup errors came from sandbox port restrictions, not product failures. Chief and Prism must not run the suite under Codex. Forge runs backend checks; Probe runs independent verification; GitHub Actions handles broad checks. Full suite once per integration milestone, targeted modules between milestones. Always record exact output and commit/tree checked.
- `docs/STATE.md` contains historical test counts including 347; use the G1 evidence here for the current main baseline. No product change or new test run is claimed for this documentation correction.
- Latest `main` push: GitHub **Hub checks run 13**, `ba82a2a`, success (31 Oct 2026). PR #8 check run 12 also succeeded. The 13-run Actions history contains only `Hub checks`; `.github/workflows/build-app.yml` has no run there. No open PRs were returned by GitHub. PR #6 (`fdde8da`), #7 (`3cb203a`) and #8 (`ba82a2a`) are merged.
- Browser/staging and Windows/macOS client checks are not run locally in this audit. Use Actions for broad checks; no live provider API usage is claimed.
- Current PWA files include `gateway/static/hub.webmanifest` and `hub-install.js`. Native mobile builds are absent. Desktop key remains a local file; update availability is announced without binary replacement; `build-app.yml` is manual and unsigned.

## Decisions awaiting Arnold

- Decide D-011: console password login off when Google is configured, with server-shell break-glass; if password login stays, require TOTP. This changes Arnold's sign-in and must not be activated without his agreement.
- Confirm whether Windows Authenticode and Apple Developer ID/notarization accounts or certificates are available, and approve any associated budget before purchase or account changes.
- Hold the offline release-signing private keys on Arnold's machine; the G4 implementation is limited to TEST keys until the production signing ceremony and certificates are settled.
- Review the final internal-beta scope and release candidate at G9.

## Blockers

- G2 is approved for credential storage (D-001/D-002), TEST-key self-update implementation (D-003/D-004/D-005), and provider-authentication boundaries (D-007). G3 client/server work can start; G4 must remain on TEST keys. Probe must verify vendor-specific facts before any tool is marked supported.
- Before G8, resolve F-01/D-011 console sign-in, F-04/D-010 session kinds, F-05/D-009 device-code phishing, F-07 Google `hd`, and F-10/F-15 session lifetimes. D-008 desktop-to-web handoff starts only after D-010. F-08 encrypted backups remains a deployment decision for Arnold.
- Signed production installers remain blocked on the signing-key ceremony, code-signing certificates, installer build-tool choice and pinned PyInstaller hashes. Native app-store readiness is outside the 14-day plan.
- Live provider compatibility/attribution remains unverified; no provider credentials or real API tests were used in the recorded baseline.
- Sentinel's G2 branch `docs/architecture-review` is pushed at `bf8ebfc8aeabf3cc576ba7608c25ee80885371ef`, confirmed through GitHub on 2026-11-02. Its own commit changes four architecture/security documents; the branch also carries the four coordination documents from parent `fcaef01`. This is design approval, not an implementation/security release verdict. No browser checks were run in this checkpoint.

## G3a bounded implementation specification

- **Owner / branch:** Prism, `feature/device-credentials`, based on main `ba82a2a`; first and only active code writer. Probe continues its separately owned provider document. Use an isolated worktree inside the authorized repository root; preserve the shared `team/log` checkout and other threads' changes.
- **Authority / dependencies:** Sentinel G2 credential approval, D-001/D-002 and F-02/F-06 at `docs/architecture-review` `bf8ebfc`. Read `/home/inquiline/swangz-team/mission/prism.md` and canonical repo instructions before work. Vendor-specific Claude/Codex configuration must have official evidence from Probe before it is marked supported; do not enable an unverified path.
- **Expected files:** `swangz_client/keystore.py`, `core.py`, `agents.py`, `cli.py`, `gui.py`; focused credential/client tests under `tests/`; client documentation `docs/CLIENT.md`. No backend, migrations, workflows, dependencies, production settings or provider-document edits.
- **Scope:** implement the native Windows Credential Manager, macOS Keychain and Linux Secret Service adapters specified in D-001; recoverable legacy-file migration with put/read/compare before removal; visible protected-file fallback; non-roaming Windows storage; clear the right credentials on logout/revocation; replace managed persistent secret copies with the approved helpers/scoped execution; pin the configured origin and validate/escape managed configuration under F-06. Report client key-storage mode; server ingestion/rotation/expiry remain G3b.
- **Acceptance:** mocked platform adapters cover success/unavailable/error cases; interrupted/failed migration preserves a usable original until verified storage; restart succeeds; logout/revocation clear the correct managed item; unknown-device errors do not silently destroy data; no secrets appear in argv/logs/managed config; unrelated personal settings survive; foreign-origin manifests and configuration injection are refused. Safe fallback is visibly reported. Native OS smoke checks remain explicitly unverified until CI/native evidence exists.
- **Testing / review:** Prism must not run the suite under Codex. Request Forge as a test-only runner for targeted finished-artifact checks or use Actions; record exact branch/commit or working-tree identity, command, counts, skips, duration and exit code. Full regression runs once at the G3 integration milestone through Forge/Probe or CI. Probe independently verifies the finished artifact, Sentinel reviews critical changes, then Chief opens the PR. No self-approval, merge or deployment.
- **Handoff:** return changed paths, test evidence, reviewable commit/branch (or precise uncommitted status if checks are pending), remaining risks and unavailable OS checks; stop writing before the next owner starts.
