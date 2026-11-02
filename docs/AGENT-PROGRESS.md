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


## G3a implementation checkpoint — 2026-11-02

Worktree: `/home/inquiline/swangz-team/swangz-gateway/.worktrees/device-credentials`;
branch `feature/device-credentials`, parent `ba82a2a`. The shared `team/log` checkout is unchanged.

- Native stdlib adapters, verified credential migration with restart recovery, visible protected-file
  fallback, Windows local storage, cleanup retry markers, and `key_storage` heartbeat/status reporting.
- Managed credential-copy migration, pipe-only key helpers, scoped Windows execution, preservation of
  unrelated settings, and pinned-origin/configuration validation. Server/schema work remains G3b.
- `python3 -m py_compile swangz_client/keystore.py swangz_client/core.py swangz_client/agents.py
  swangz_client/cli.py swangz_client/gui.py tests/test_client_credentials.py tests/test_client.py`: exit 0,
  no output. Syntax check only, not a test run. `git diff --check`: exit 0, no output.
- First targeted run by the read-only Forge runner: `python3 -m unittest tests.test_client_credentials
  tests.test_client tests.test_devices`, outside Codex. Python 3.14.4 (GCC 15.2.0), Linux
  7.0.0-38-generic x86_64. HEAD `ba82a2a`; source hash before and after
  `d3699bf7ffb53faee7b6eb19d3c7c9145dd6fec3e1135ff5e8db82fd00821897`.
  Exact summary: `Ran 88 tests in 90.395s`, `FAILED (failures=1)`, exit 1, no skips reported;
  reported wall clock 95.0s. Failure: interrupted managed-Claude helper rewrite left an authentication
  conflict on restart. This was a real failure, not sandbox setup noise. Fixed by recognising the exact
  deterministic helper and allowing its own missing/unchanged environment fields during retry, while
  preserving conflicting values. The corrected source rerun passed as recorded below.
  Prism has not run the suite under Codex. Full regression remains at the G3 integration milestone.
- Probe's corrected consultation `d454fc9f-c3b0-40b5-87b6-4dea84c6a07f` directly read the official
  Claude/Codex pages. It is not implementation verification. `/anthropic` preservation in the Claude
  CLI remains unverified: managed Claude is gated in code on every OS, old managed token copies are
  removed, and the existing scoped integration is retained. Tests explicitly enable the synthetic
  helper branch without lifting rollout gates. Windows managed Codex remains gated too. Exact sources
  and version limitations are in `docs/CLIENT.md`; no supported-version or live provider claim is made.
- Native Windows/macOS/Linux credential services, Windows file DACL and macOS item ACL smoke checks:
  Not run: native runners unavailable in this Codex session. GUI/browser checks: Not run: no display
  or browser fixture started; no web assets changed. Probe should check This device fallback/locked
  states, unknown-device recovery, explicit revocation, cleanup retry and personal settings.
- G3 remains open for server lifecycle/rotation/expiry, independent Probe verification and Sentinel
  security review. No merge, release, production action or self-approval.

### G3a corrected targeted run

Read-only Forge runner request `9ae02a06-be5e-430e-b585-b43824671405`, 2026-11-02. Ran outside Codex
on Python 3.14.4, Linux 7.0.0-38-generic x86_64, with fake services only; no tracked files changed.

Command (from the feature worktree):

```text
python3 -m unittest tests.test_client_credentials tests.test_client tests.test_devices
```

Exact summary:

```text
Ran 89 tests in 84.486s

OK
```

Exit code **0**; no skips or failures reported; runner wall clock **86.4s**. Expected checksum-mismatch
test diagnostics were printed twice; they were not failures. Raw local runner output: `/tmp/g3a-r2.out`
(first failed run: `/tmp/g3a.out`). Native stores and real vendor clients were not used.

HEAD during both sides of the run was `ba82a2a`. Before/after source digest, also independently checked
before committing: `707de085f54f08dd22b97b84b06e3f3d34ceb822268c6e0e8ceade934b51ef9a`.
Digest construction: SHA-256 over sorted paths, updating with each path's UTF-8 bytes, NUL, complete file
bytes, NUL. Paths: `swangz_client/agents.py`, `swangz_client/cli.py`, `swangz_client/core.py`,
`swangz_client/gui.py`, `swangz_client/keystore.py`, `tests/test_client.py`,
`tests/test_client_credentials.py`. Other executable code remains at the main parent `ba82a2a`.
Only documentation evidence changed after this run. Syntax compilation and `git diff --check` also
passed; these are not substitutes for tests. The full suite was not rerun at this bounded milestone,
per Arnold's G3 integration test rule.

Implementation handoff is ready for Chief to route independent Probe verification and Sentinel review.
G3a does not claim native platform support, verified vendor versions or rollout approval. Managed Claude
remains gated pending observed CLI prefix behavior, and Windows managed helpers remain gated.
