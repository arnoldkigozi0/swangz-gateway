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

## PR11 app-window correction — 2026-11-02

Fetched the actual GitHub job logs through the GitHub connector for run `41504842126`, job
`125481373931`, on PR merge SHA `9e7818f404d0a388b3e70b87ae9b8fe9bbf98777` (head `6cbe7dd`).
The runner was Ubuntu 24.04.5 with CPython 3.12.15 and a working Tk/Xvfb installation.
Command: `xvfb-run -a python -m unittest tests.test_client_gui`.
Exact summary: `Ran 13 tests in 0.527s`, `FAILED (errors=7)`, exit 1. A Tk callback also raised the
same exception during sign-out. All errors stemmed from `page_signin()` accessing `client.store`:
`AttributeError: 'FakeClient' object has no attribute 'store'`. This was not an installation or
network failure. The earlier CLI log-fetch attempt could not reach GitHub; the connector succeeded.

Minimal correction: read `cleanup_pending` from the existing `Client.status()` interface, which
already reports that field. The GUI no longer reaches into storage. Extend the GUI stand-in's
status/cleanup contract and exercise failed cleanup followed by a successful retry with a real Tk
window on an available display. Existing signed-out/login/sign-out/revocation assertions remain.
No credential behavior, helper gates, personal settings, workflows or dependencies changed.

Read-only Forge runner request `2d5a37c2-a585-45c2-ba3b-bd5d1a9d5393`: targeted Tk coverage
unavailable. Python 3.14.4 (GCC 15.2.0), Linux 7.0.0-38-generic x86_64, outside Codex.
`xvfb-run -a python3 -m unittest tests.test_client_gui` exited 127 (`command not found`).
With existing `DISPLAY=:0`, `python3 -m unittest -v tests.test_client_gui` reported
`Ran 14 tests in 0.002s`, `OK (skipped=14)`, exit 0; importing `tkinter` failed with
`ModuleNotFoundError`. All tests skipped: this is unavailable Tk coverage, not a passing check.
No installation or system changes. Raw runner output: `/tmp/pr11-tk-fix.out`.
HEAD remained `6cbe7dde5354fab78a6a9580206f2b904aaa775b`; GUI source digest before and after:
`a4b3140f7483148e5740b10dbce55b5fc99cb30cd91b56f5ffbd49c1e221366f`.
Digest construction: SHA-256 over sorted `swangz_client/gui.py`, `tests/test_client_gui.py`,
updating with each path's UTF-8 bytes, NUL, complete file bytes, NUL. Rechecked unchanged before
commit; syntax parsing and `git diff --check` passed (exit 0). Neither substitutes for tests.

Push this bounded correction to the existing PR for the existing Actions Tk/full regression/browser
checks; no blind rerun of the old failing job. No suite or browser matrix run under Codex.
Prior Probe full regression (`Ran 449 tests in 447.083s`, `OK (skipped=13)`, exit 0) and Sentinel
approval cover `6cbe7dd` only; corrected-tree CI and renewed independent verification/security review
remain required. Native credential checks remain unverified. Managed Claude and Windows helper
gates are unchanged; amendment work remains paused until Chief releases writing.

### Python 3.10 follow-up from the same CI run

While awaiting corrected-tree CI, fetched original run `41504842126` Python 3.10 job
`125481373997` logs. CPython 3.10.22: `Ran 449 tests in 339.986s`,
`FAILED (failures=2, errors=2, skipped=13)`, exit 1. Four credential/client tests assumed managed
Codex files/profile existed or conflicting settings failed installation. On Python 3.10 the existing
production gate deliberately returns scoped mode before reading/writing TOML (`tomllib` requires
Python 3.11); this documented gate remains unchanged. Two missing-file errors and two managed-mode
assertions were test expectation defects; these were not provider or sandbox failures.

Corrected the expectations to assert gated scoped mode, unchanged personal configuration, no profile
or backup creation, child-only credential/CLI overrides and safe removal on Python 3.10. Existing
managed-mode checks still run on Python 3.11+. Added a synthetic Python 3.10 gate regression that also
runs on newer Python. No further product code changed. Corrected-tree Actions evidence pending;
the local machine still cannot execute Tk and no suite/browser matrix was started under Codex.

### Corrected Tk evidence

GitHub Actions run `41506089806`, job `125486297145`, completed successfully. Fetched and read the
actual logs: Ubuntu 24.04.5, CPython 3.12.15, PR merge SHA
`6fe32b76214c15b17ff77f973241fe21294d2183` (head `fd81576a752f3c5cecec99ce7a41b82012b917dd`).
`xvfb-run -a python -m unittest tests.test_client_gui`: `Ran 14 tests in 0.752s`, `OK`, no skips
reported, successful step/job (exit 0). No Tk callback traceback appeared in the log. This verifies
the corrected sign-in and cleanup retry GUI fixture on Linux. GUI/test files are unchanged by the
Python 3.10 expectation follow-up; final-head full CI and Probe/Sentinel reviews remain required.

## Glass R1 review correction — 7 November 2026

Branch `feature/glass-r1`, worktree `.worktrees/glass-r1`, draft PR #38.
Probe rejected initial head `1e0a319`: its actual browser check reproduced KPI
overflow from Jakarta font metrics, mobile catalogue label clipping and the
decorative scene printing behind black text. Chief confirmed no Forge/R3 shared
CSS work had started and reserved the bounded correction for Prism.

Kept Arnold-authorized self-hosted Plus Jakarta Sans. Raised `.kpi .value`
line-height to 1.3; allowed `.tr-sub` metadata to wrap; hid `body::before` in
print. Added metadata overflow detection to the existing CI browser harness;
extended the focused glass harness to check all three defects. No auth/product
logic, dependencies, production services, providers, merge or deployment changed.

Actual corrected-tree checks (synthetic local fixtures, socket access enabled):

- `UI_WIDTH=<1440|390> UI_THEME=<dark|light> UI_PAGES_ONLY=1
  UI_OUTPUT=/tmp/prism-glass-r1-<theme><width> node tests/browser/check.cjs`:
  four separate runs, each `PASS principal pages 27 interaction assertions;
  25 screen checks`, exit 0. Total 108 assertions/100 screens, no browser errors,
  axe findings, KPI clipping or tool metadata clipping. Deliberate Studio 400 is
  expected; no unexpected API failures. Full role matrix stays on Actions.
- `node docs/screenshots/glass-r1/check.cjs`: `PASS 81 targeted checks;
  8 screenshots; 20 contrast bounds`, exit 0; minimum contrast bound 4.63:1.
- `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in
  30.576s`, `OK`, exit 0. Only fake upstream; no full suite repeated locally.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `git diff --check`: exit 0.

Screenshots and result summaries: `docs/screenshots/glass-r1/`. Inspected all
four exact 1440×900/390×844 admin screenshots and both new staff metadata
screenshots. Print checks use Chromium media emulation, not physical output or
a report PDF. Not run: real devices, Safari/Firefox, screen readers, full local
role matrix/full suite, 60fps/CLS/MotionScore. Earlier Actions Python/app-window
success applies only to `1e0a319`; browser failed there. Corrected-head CI and
Probe re-verification are pending. No processes left running after checks.


## Glass R3 floating toolbar — 8 November 2026

Resumed `feature/glass-r3` in `.worktrees/glass-r3` from R2 head
`4f6cf7e5cb5fae63b1642e9e30f5766ecbb6e5f5`, preserving existing uncommitted
admin.css/admin.js and task screenshots. Header-only product changes provide
workspace navigation, centered existing command search, timezone-aware real clock,
existing notifications and the signed-in account link. No shared UI/backend/auth
changes. No global New action or invented online presence. R2 PR42 remains an
open dependency; inherited navigation is included against main.

Actual checks on the resumed tree (synthetic fixtures, authorized local ports):

- `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit 0, no browser exceptions/scoped axe findings. Includes keyboard/focus, clock tick/timezone, real destinations, viewer identity, 44px controls and 320/768/1280 widths, print/reduced-motion/no-blur checks. Initial invocation without tooling failed `MODULE_NOT_FOUND`; no packages installed.
- `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 38.042s`, `OK`, exit 0.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `python3 docs/screenshots/glass-r3/contrast.py`: `PASS 8 text contrast bounds; minimum 5.64`, exit 0. Bounds cover strong-pill primary text and scene secondary area text, over black/white photographs with shipped scrim. Initial ad-hoc parser failed by matching a comment; saved script matches the actual rule.
- `NODE_PATH=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_WIDTH=<1440|390> UI_THEME=<dark|light> UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r3-<theme>-<width> node tests/browser/check.cjs`: four separate runs each `PASS principal pages 27 interaction assertions; 25 screen checks`, exit 0. Total 108 assertions/100 screens; zero browser errors, axe findings or unexpected API failures. The deliberately rejected Studio request is expected. Summaries: `regression-results.json`.

Inspected exact 1440x900/390x844 dark/light screenshots alongside the dashboard
reference; differences and artifacts are in `docs/screenshots/glass-r3/`.
Not run: full local suite/role matrix (Actions), real devices, other engines,
screen readers, native OS settings, hardware performance/60fps/CLS/MotionScore.
Mounted browser, Chrome DevTools and Motion tools unavailable. Independent QA and
new-head CI pending; no merge or deployment.

Queue preflight: R4 PR44 remains open at `8cdc8ea`, built on old PR40
`42ce9b7`; PR40 is open at corrected `cb4a5ba`. Read-only merge-tree confirms
refresh includes shared ui.css/ui.js changes. Those files remain Forge-owned;
no R4 integration performed or R8 worktree started pending dependency clearance.

R3 final whitespace check passed. All local check processes finished. Peer coordination tools were not exposed on this turn; independent Probe review is requested in the final handoff, not claimed as performed.
## PR42 browser CI diagnosis and main refresh — 8 November 2026

Branch `feature/glass-r2`, `.worktrees/glass-r2`. Inspected actual failed
GitHub run42382080869/job128431709285 and downloaded the synthetic artifact:
first light1440 staff Home axe scan flagged Canva/ChatGPT/Claude launch links.
`ci-failure.json` retains the artifact summary. Staff portal/shared UI files are
identical to main; R2 had not modified those files.

Task diagnostic `docs/screenshots/glass-r2/ci-contrast.cjs` freezes native colour
transitions at30ms for CPU-independent inspection: reproduced all three targets
at3.04:1 (#979391 on white). Fully settled page passes. Existing harness now
awaits fonts and finite theme transitions before auditing. No accessibility
assertions/thresholds/rules disabled; no retries or product styling changes.
This does not assert that transient theme colours themselves meet AA.

Normally merged main7ce5407 conflict-free as4423482. No edits to inherited
backend/device files; admin.css/admin.js byte-identical to4f6cf7e and recorded
performance SHA256s, so prior mixed performance result/limitations still stand.
Actual synthetic local checks with existing R1 pinned tooling and ports enabled:

- Focused navigation: `PASS 75 navigation checks; 8 screenshots; 6 axe scans`, exit0.
- Prior review regressions: `PASS 23 review regression checks`, exit0.
- `python3 -m unittest tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 99 tests in 60.789s`, `OK`, exit0. Fixture socket ResourceWarnings appeared without failures.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit0.
- `NODE_PATH=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r42-corrected node tests/browser/check.cjs`: `PASS principal pages 27 interaction assertions; 25 screen checks`, exit0, no browser/axe/unexpected API findings. `ci-regression-results.json` retains the summary. Updated `UI_TOOLING=<same existing R1 tooling> node docs/screenshots/glass-r2/ci-contrast.cjs`: `PASS 3 CI contrast diagnosis checks; native 30ms state fails, settled state passes`, exit0; after reproduction it resumes and awaits real transitions rather than force-finishing them. `git diff --check`: exit0. All local processes finished. Independent exact-head QA and final-head CI pending.

Regenerated navigation screenshots; inspected desktop light and phone dark
drawer for unchanged selection/readability. References and existing differences
remain in the task README. Full local matrix/suite, real devices/other engines,
screen readers, new performance/CLS/MotionScore: Not run; bounded test correction,
full suite/matrix stay on Actions. Independent exact-head QA remains required.
No shared ui.css/ui.js, production, providers, dependencies, merge to main or deploy.


## PR48 corrected dependency integration — 8 November 2026

After PR42 was tested, clean and pushed at
`d31bfe81ba28736cc70d00b27accda4e9307f1d5`, normally integrated it (including
main7ce5407) into `feature/glass-r3`, existing draft PR48. The only conflict was
append-only progress records; retained both complete sections. No product/test
conflict resolution. Admin CSS/JS match original R3b5986c6 exactly; no shared
ui.css/ui.js edits. R2's original mixed performance gate is not cleared by this
CI audit synchronization correction.

Actual integrated-tree synthetic local checks, existing pinned R1 tooling:

- `UI_TOOLING=<existing R1 tests/browser/node_modules> node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit0.
- `python3 -m unittest tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 99 tests in 62.813s`, `OK`, exit0. Non-failing fixture socket ResourceWarnings recorded.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit0.
- `python3 docs/screenshots/glass-r3/contrast.py`: `PASS 8 text contrast bounds; minimum 5.64`, exit0.
- Integrated-tree results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit0. `NODE_PATH=<same tooling> UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r48-integrated node tests/browser/check.cjs`: `PASS principal pages 27 interaction assertions; 25 screen checks`, exit0; zero browser errors/axe/unexpected API findings, summary in `integration-regression-results.json`. `python3 -m unittest tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 99 tests in 62.813s`, `OK`, exit0 (non-failing fixture socket ResourceWarnings). Syntax:23 JavaScript files checked; eight text contrast bounds min5.64; working/staged whitespace checks passed. All local check processes finished.

Regenerated four exact required viewport/theme screenshots; inspected desktop
dark and phone light against preserved reference differences. Full local
suite/role matrix, real devices, other engines, screen readers, fresh hardware
performance/CLS/MotionScore: Not run. Actions and independent final exact-head
Probe QA remain required. No new PR, shared UI source change, deployment or merge
to main. Peer coordination tools unavailable; final handoff requests routing QA.
## New-main integration before final QA — 8 November 2026

Normally merged main `2b30af5f0c47c6bf447671a8de2f91742fec6ff6` into
`feature/glass-r2` without conflicts. Main delta from7ce5407 is limited to
docs/CLIENT.md, gateway/enroll.py and tests/test_browser_contract.py: negotiated
`browser_contract=1` adds an inert authenticated person/device browser block to
the manifest; non-negotiating clients retain their original manifest shape.
No hand edits to inherited implementation or tests.

Own-source verification against `d31bfe81ba28736cc70d00b27accda4e9307f1d5`:
admin.css, admin.js and tests/browser/check.cjs are byte-identical. Shared
ui.css/ui.js also unchanged. Five exact comparisons, baseline Git blob IDs and
current SHA256s recorded in `docs/screenshots/glass-r2/main-refresh-identity.json`.
Earlier transition diagnosis, all assertions, reference differences and mixed
performance evidence remain unchanged; no CI diagnosis repeated.

Fresh results: `python3 -m unittest tests.test_browser_contract tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 119 tests in 95.128s`, `OK`, exit0; a non-failing fixture socket ResourceWarning appeared. `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r2/check.cjs`: `PASS 75 navigation checks; 8 screenshots; 6 axe scans`, exit0. `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit0. Five byte-identity comparisons and working/staged whitespace checks passed. Local checks finished. Full local
suite/role matrix, new performance/CLS/MotionScore, real devices, other engines
and screen readers: Not run. Fresh final-head Actions and independent Probe QA
remain required. No new build/PR, shared UI edits, merge to main or deployment.


## Main2b30af5 integration for final QA — 8 November

Normally integrated refreshed PR42 `1b8c8d913b7c7612abe67e122d0275e978415ed5`,
including main `2b30af5f0c47c6bf447671a8de2f91742fec6ff6`, into existing PR48.
Only append-only progress records conflicted; retained both complete records.
No product/test resolution edits. Main adds the reviewed negotiated browser
manifest contract in enroll.py plus its documentation and tests.

Five byte-identity comparisons against previous PR48 head
`1af8d0f9a828a8770ecdc62aca090d73329605a1` passed: admin.css, admin.js,
tests/browser/check.cjs and shared ui.css/ui.js. Baseline Git blob IDs/current
SHA256s recorded in `docs/screenshots/glass-r3/main-refresh-identity.json`.
Earlier transition-wait assertions, diagnosis and mixed R2 performance evidence
are unchanged; no repeated diagnosis/performance sampling.

Latest integrated-tree results: `python3 -m unittest tests.test_browser_contract tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 119 tests in 61.188s`, `OK`, exit0; non-failing fixture socket ResourceWarnings appeared. `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit0. Five own/shared source byte-identity comparisons and working/staged whitespace checks passed. All local check processes finished. Full local
suite/role matrix, hardware performance/CLS/MotionScore, real devices/other
engines/screen readers: Not run. Final-head Actions and independent Probe QA
remain required. No new build/PR, shared UI edits, merge to main or deployment.


## PR48 refresh after parent42 merge — 8 November

Normally merged exact main `743815ca836032385e5f14cd1e93516e4e745d95` as
`d9ee991317f69382261530309fa597bf751e8e11`, no conflicts. Before evidence
updates, the entire merge tree is byte-identical to previous verified48 head
`b1a2544ab18ca156c4feeb5904055cb278129aaa`: tree
`fbdb54a8d8d20fcfbf2301c0265c8edae4357429`. This merge changes ancestry only.

Seven own/shared source comparisons passed: admin.css/admin.js, the existing
browser harness, task check.cjs/contrast.py, and shared ui.css/ui.js. Git blob
IDs and SHA256 evidence: `docs/screenshots/glass-r3/parent-merge-identity.json`.
No harness changes outside the normal merge and no diagnosis repeated.

Fresh results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit0. `NODE_PATH=<same tooling> UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r48-parent-merged node tests/browser/check.cjs`: `PASS principal pages 27 interaction assertions; 25 screen checks`, exit0; no browser exceptions, axe findings or unexpected API failures; summary in `parent-merge-regression-results.json`. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 36.926s`, `OK`, exit0. Seven source identity checks and working/staged whitespace checks passed. All local check processes finished. Full
local suite/role matrix, new hardware performance/CLS/MotionScore, real devices,
other engines and screen readers: Not run. Fresh final-head Actions and Probe
QA remain required. Parent42 is now merged; PR48's diff is header/task evidence
only. No scope expansion, new build/PR, deployment or merge to main.


## Bell badge WCAG correction — 8 November 08:00 shift

Branch feature/bell-badge-contrast from main4cf653b, isolated matching worktree.
Confirmed original dark badge white/#FF5D52 at3.026119928029301:1 via expected
failing assertion; changed only admin.css `.bell-n` foreground to existing
`--on-bad`. Actual computed ratios: dark6.361659258042617:1, light4.736397633724517:1
at1440x900 and390x844. Reference fill/shape maintained; dark numeral is the
necessary contrast difference. Existing header harness adds four measured
contrast assertions and task output routing; shared check.cjs/ui.css/ui.js and
workflows untouched. G2 boundaries unchanged: presentation/token reuse only,
no new architecture/security behavior or approval claimed.

Actual commands/output and complete measurements/negative control/references:
`docs/screenshots/bell-badge-contrast/README.md`, baseline-results.json/results.json.
Focused existing admin harness:67checks,4screenshots,4axe scans, exit0, no
exceptions/scoped findings. Python portal+hub:56tests in52.014s, OK/exit0.
Node syntax and whitespace checks passed. Inspected all four exact screenshots.
Full local suite/matrix, real devices/other engines/screen readers, hardware
performance/CLS/MotionScore: Not run; Actions/independent QA remain required.
No new fonts/dependencies, providers, auth/data changes, merge or deployment.


## PR50 latest-main integration after46 — 8 November

Normally merged exact main `a0dbcfe140dfcde4e7d1e4e1904b75c014abd222` as
`68f23bdf2dbe415ede16b126ed3c27fc5c37249a`, no conflicts. Main contributes
reviewed shared list/UI code and browser-contract tests/docs. No hand edits to
shared source or any harness. Own admin.css and focused admin assertion harness
remain byte-identical to previous PR50 head
`1048e6f91b2540c2db9e308766a460d0f37d7b60`; tokens.css and shared browser
harness also identical. Shared ui.css/ui.js exactly match integrated main.
Baseline Git blob IDs/current SHA256s: `docs/screenshots/bell-badge-contrast/main-refresh-identity.json`.

Fresh commands/results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs`: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. Zero browser exceptions/scoped axe findings. Actual contrast at both widths: dark6.361659258042617:1, light4.736397633724517:1. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 38.514s`, `OK`, exit0. Four source identity comparisons, inherited shared UI/main equality and working/staged whitespace checks passed. All local check processes finished. No new PR/build or
repeated diagnosis. Full local suite/matrix, real devices, other engines/screen
readers and new hardware performance/CLS/MotionScore: Not run. Fresh final-head
CI and independent Probe QA remain required. PR44 stays queued; no shared-file
release assumed or corrected40 integration performed. Peer tools unavailable;
final exact-head handoff is returned to Chief for Probe routing.


## PR50 amendment after45 merge — 8 November

At clean PR44 checkpoint, normally merged exact main
`be81749aadb7b9b1eeb3e61f4839d02903a09cae` as
`3309f5c889a3cc3396cad51074d9f4c6a178f5a2`, no conflicts. Incoming product
delta is only main's two-line empty-line chart fix, plus its chart tests.
No own source/harness/style edits. Four byte-identity checks against previously
verified `c8dfcb10e1aa419c4cefc55f50b69ccdd134ab64` pass: admin.css, focused
admin harness, tokens.css and shared browser harness. Shared ui.css/ui.js match
requested main exactly. Baseline blob IDs/SHA256s: `docs/screenshots/bell-badge-contrast/after45-identity.json`.

Fresh commands/results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs`: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. No browser exceptions/scoped axe findings. Actual badge contrast remains dark6.361659258042617:1/light4.736397633724517:1 at both widths. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 50.038s`, `OK`, exit0. Source identity and working/staged whitespace checks passed. All local check processes finished. No repeated diagnosis or
new PR/build. PR44 was clean and remains untouched. Full local suite/matrix,
real devices, other engines/screen readers, new hardware performance/CLS/MotionScore:
Not run. Fresh final-head CI and independent exact-head Probe QA remain required;
previous verdict is not claimed as new-head approval.


## PR50 refresh at final44 clean checkpoint — 8 November 09:30

PR44 was tested/pushed/clean atd89f3e7 before starting this optional refresh.
PR50 remained open; normally merged latest main
`6ee3ed3aeaa5244cb88df8302b1435546112d524` without conflicts. Main brings
merged R5 chart code/evidence. Own badge CSS, focused admin harness, tokens and
shared browser harness remain byte-identical to previous c37571e; shared UI
exactly matches requested main. Blob/SHA256 proof: `docs/screenshots/bell-badge-contrast/parent40-identity.json`.
No source changes, repeated diagnosis or new build/PR.

Fresh commands/results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs`: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. No browser exceptions/scoped axe findings; actual badge contrast remains dark6.361659258042617:1/light4.736397633724517:1 at both widths. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 43.684s`, `OK`, exit0. Source identity/whitespace checks passed; all local checks finished. Full local
suite/matrix, real devices/other engines/screen readers and new hardware
performance/CLS/MotionScore: Not run. Fresh exact-head CI and independent Probe
QA remain required. No ready/merge/deploy action.

## Console Overview details — 10 November sprint

Branch feature/console-header-tubes, rebased on origin/main f580cb4. Changes: admin-monitor.js header emoji and role-safe greeting, shorter spend caption (plans amount remains in detail tooltip), zero-day tube option; ui.js opt-in zero stubs/labels/value chip; console mobileNav uses four specified routes, separate All pages attention badge; phone-nav.js extracts staff #70 lens for both apps with arrow-key focus; admin/index HTML load shared helper. CSS only in NEW exact-console-details.css, reusing exact-staff-bar.css; admin.css untouched to avoid Anvil's scene/panel work.

Identity limitation: Forge checked /admin/api/me and confirmed there is no existing name field. Header now uses only the first whitespace-separated token of display_name, with neutral Hello when absent; never username or role. (Superseded on the merged head `585b42c`: the greeting uses the full trimmed display_name, so titles and full names are kept.) Forge's proposed read-only company people.name match requires its backend addition. This token is a display heuristic, not a guaranteed stored first name (titles may precede names). Item 3 remains dependent on that server contract.

Validation: browser syntax script checked39 JS files and staff synthetic model18PASS before rebase; node --check ui.js and extended charts.cjs passed. git diff --check passed. Added CI browser assertions for eight tubes/table rows, five zero stubs labelled0, selected-zero chip. Not run locally: Python/full suite, Chromium, screenshots/50%overlay, contrast/CLS/performance/fallback checks — Anvil holds sole browser slot and Chief explicitly assigned CI-only work. CI runs the chart regression. No claim of exact-match visual acceptance; architect review remains required. No new dependencies, production changes or admin.css edits.


## PR97 Sentinel corrections — 10 November 21:07 sprint

Attention refresh now updates the console phone badge and accessible label after a deep link and on subsequent refreshes, including clearing it. Lens initialization is guarded. Bar C returns to 260px/104px geometry with 44px inactive targets, truncating only the visible long active label (full accessible name retained, §10.1.1). At 320px the bar is 256px (4px narrower) to fit beside the round button. The shared lens cancels only the duplicate click following pointer navigation. Drawer hides the bar; footer clearance replaces existing main padding. Primary hover retains amber by suppressing the inherited sweep; ghost buttons have explicit hover feedback. CSS remains in exact-console-details.css; admin.css untouched. Greeting uses full trimmed display_name from #99 (including titles), or neutral Hello when null (§10.1.1/5).

Validation: syntax checked 39 JavaScript files; synthetic staff model 18 checks PASS; node --check charts.cjs and git diff --check passed. Extended the existing CI charts.cjs job with phone deep-link coverage in both themes: delayed attention, updated and cleared badges, four links/current route, drawer open/close, helper missing, 260px/104px widths, narrow inactive targets, full recorded name. These new rendered assertions have NOT run locally: Chief assigns CI only and Anvil owns Chromium. Python/full suite, screenshots/overlay, measured contrast, CLS and video timing remain unverified for this revision until CI/architect evidence. Previous a228af7 CI was all green, not evidence for these corrections.


## Sprint day — 10 November 2026 (Kampala time)

61 pull requests merged to main between 00:04 and 21:36; main is `42d8088`. Every merge had green
GitHub CI on its head. The list is drawn from `git log --merges origin/main`.

| Time | PR | Merge | What |
|---|---|---|---|
| 00:04 | #59 | `f1c50fa` | Design brief: navigation tabs reference (§10.8, R16) + beyond-the-reference fixes (§10.9, R17) |
| 00:12 | #10 | `5196617` | Extend product blueprint with Amendment 01 operating model |
| 01:07 | #50 | `8aa97c1` | Fix notification badge text contrast in dark mode |
| 01:40 | #49 | `fc4c278` | Browser check: wait for finite animations before axe (theme-flip race) |
| 04:02 | #9 | `1d663e6` | Document provider authentication, billing and observation boundaries |
| 07:18 | #13 | `32dfad9` | Rotate device keys in the Swangz app (G3b client) |
| 07:54 | #16 | `5ed064d` | Serve signed app releases from the gateway (G4 server) |
| 07:54 | #19 | `9fc0d11` | Revoke people, devices and sessions on the next request (G5 continuity, backend) |
| 08:00 | #17 | `5296054` | Reuse a verified staged update instead of downloading it again |
| 08:01 | #20 | `ecdb141` | Extension fails closed on governed sites (G5 continuity, extension) |
| 08:44 | #26 | `0f29579` | Read-only paused view, session kinds (v23) and Google hd check |
| 08:44 | #18 | `a1bc0e3` | Unsigned desktop test builds for Windows, macOS and Linux (G5) |
| 08:44 | #21 | `3b847cd` | Verify extension continuity in real Chromium on CI |
| 09:05 | #27 | `16dce34` | Fix paused navigation and add read-only reports and updates |
| 09:05 | #22 | `16eef13` | Close the previous tool's record when a site leaves governance (extension follow-up) |
| 09:30 | #57 | `704ead6` | Split sign-in: console and staff (Sentinel G2) |
| 09:52 | #23 | `3a8fe8e` | Extension: close the tab's running record on every navigation |
| 09:53 | #30 | `2ed1da0` | Keep logout terminal across paused and mobile session races |
| 10:00 | #56 | `9324599` | Isolate staff shell and exclude seed console grid |
| 10:41 | #64 | `6a7d881` | Fix main: paused-view harness lacked clearTimeout, which the new staff shell calls |
| 11:03 | #62 | `a53203e` | Staff: the font hold can never stop the shell rendering |
| 11:24 | #33 | `279ff5c` | Reject missing and empty unsigned desktop build outputs |
| 11:33 | #65 | `37ef6ac` | Staff footer: liquid glass panel with the cut-out wordmark (BRIEF §6, §10.3) |
| 11:47 | #61 | `31ba412` | Core proof: device lifecycle journey and per-person isolation sweeps |
| 11:48 | #60 | `afadef7` | Ops: running version and commit, scheduled restore check, audit coverage |
| 12:01 | #66 | `76c4498` | R15 piece 1: console scene in the warm room at the 10.3 scrim |
| 13:02 | #63 | `c6d7382` | Extension sign-out ends its session at the Hub; paused-view docstrings |
| 13:26 | #68 | `93c2b6e` | R15 piece 2: 38px top-bar pills and no area eyebrow on desktop |
| 14:01 | #67 | `c78a1db` | R16 piece 1: staff view tabs as glass bars A and B with a sliding pill (BRIEF 10.8) |
| 14:06 | #69 | `5013026` | R15 piece 3: console rail, top bar positions and page header per BRIEF 10.3 |
| 14:30 | #71 | `08bf6be` | Console version line no longer shifts on cold load |
| 15:06 | #72 | `8ea5979` | Console avatar menu: theme, Sign out and Stop all AI reachable from the top bar (BRIEF 10.7) |
| 15:13 | #70 | `f2a0e5d` | R16 piece 2: staff phone bottom bar with the pointer lens (BRIEF 10.8 bar C) |
| 15:36 | #74 | `50a5488` | Staff Updates: say Emailed only when the email was sent |
| 15:36 | #75 | `eaf5b60` | Live: no layout shift on a cold load |
| 16:01 | #76 | `cd0208d` | Staff bar badge: valid font declaration (9px) |
| 16:05 | #77 | `fd9bd14` | Tool initials: 4.5:1 on every brand colour |
| 16:07 | #73 | `b8d1489` | Console Overview: four KPI cards per BRIEF 10.3 (R16) |
| 16:25 | #78 | `25d6e32` | Console menu: Stop all AI readable in the light theme |
| 16:25 | #80 | `f8b95d5` | Audit log: a person changing their own Hub password |
| 16:32 | #81 | `be16b0f` | Go-live readiness: offline configuration check, Google return-address tests, owner asks |
| 16:35 | #83 | `5d740ae` | Money under a cent reads "< $0.01" in both apps (BRIEF 10.9.2) |
| 16:42 | #82 | `f68f16f` | Registry: console can list one person's seats (person= filter) |
| 16:42 | #85 | `d7f2476` | Chrome policy pack for company devices (deploy/chrome-policy) |
| 17:01 | #86 | `3db1199` | Empty charts keep their card's size and say what will appear and why (BRIEF 10.9.2) |
| 17:01 | #84 | `90515d9` | Console at 390: the room shows around the page, not only above it (draft, unmeasured) |
| 17:02 | #79 | `a67ffb9` | Console Overview: the body per BRIEF 10.7 (R17) |
| 17:09 | #87 | `794e3c6` | Staff password follow-ups: end other sessions, throttle guesses, audit failed sign-ins |
| 17:24 | #88 | `28fe3d9` | Uptime check on the server: health-check command + five-minute timer |
| 17:47 | #90 | `e155c34` | Password and sign-in ruling: console password change, failed sign-in audit, preflight domain, Chrome pack notes |
| 19:55 | #89 | `2ac674d` | Overview: a count of zero says why (BRIEF 10.9(2)) |
| 20:27 | #91 | `aaf5f82` | Sign-in ruling follow-ups, audit coverage sweep, Chrome policy names checked |
| 20:28 | #92 | `f580cb4` | Overview: first card in the reference amber, and the page fits 1440x852 |
| 20:53 | #94 | `bddf68c` | Overview: Uses by tool as a donut with a legend (BRIEF 10.7) |
| 20:55 | #95 | `4e4ef5d` | Arnold-only list, go-live asks, real-phone checklist, Chrome pack limits |
| 20:57 | #93 | `3162bf2` | Security follow-ups: Google fixed-address switch (off by default), company-browser audit row, staff failed sign-ins on Security |
| 21:18 | #98 | `8ee5856` | Overview: round icons on the two count cards (dashboard-02) |
| 21:31 | #100 | `6106663` | Real-user journey over HTTP: add, grant, sign in, open, Activity, revoke, sign out |
| 21:34 | #96 | `4bcc80b` | Decisions: record D-001 to D-019 on main |
| 21:35 | #99 | `9332c5f` | Console /me: display_name for the signed-in console user |
| 21:36 | #97 | `42d8088` | Overview header, zero-day tubes and console phone navigation |

What this covers, by track:

- **Backlog from 4 November landed:** #9 #10 #13 #16 #17 #18 #19 #20 #21 #22 #23 #26 #27 #30 #33.
- **Function:** device key rotation, signed-release serving, revoke on the next request, session kinds
  (schema v23) and the read-only paused view, provider registry (v24, v25), core proof (#61: device
  lifecycle journey, per-person isolation sweeps), running version and scheduled restore check (#60),
  uptime check (#88), staff and console password changes throttled, audited and ending other sessions
  (#80 #87 #90), audit-coverage sweep of every console route (#91), Google fixed-address switch (#93),
  offline go-live configuration check (#81), Chrome policy pack for company devices (#85).
- **Exact-match UI:** split sign-in (#57), staff shell (#56), staff footer (#65), console scene, rail,
  top bar and Overview (#66 #68 #69 #73 #79 #89 #92 #94 #98 #97), staff tabs and phone bar (#67 #70), avatar
  menu (#72).
- **Owner documents:** `docs/ARNOLD-ONLY.md`, `docs/GO-LIVE-ASKS.md`, `docs/MOBILE-READINESS.md` (#95).

Overlays recorded for BRIEF 10.2 (1440x852, dark):

- Sign-in: `docs/screenshots/exact-signin/overlay-{console,staff}-{login,access}-1440.png`
- Staff shell: `docs/screenshots/exact-staff-shell-v2/verified-eca2728/overlay-{home,tools,requests,projects,weekly}-1440x852-dark.png`
- Staff footer: `docs/screenshots/exact-footer/overlay-footer-1440x852-dark.png`
- Console Overview: `docs/screenshots/exact-r15/overlay-overview-1440x852-dark.png`,
  `piece2-` and `piece3-` beside it, and `docs/screenshots/exact-r16/r17-overlay-overview-1440x852-dark.png`

Console header greeting (#97, with #99): the greeting uses the full trimmed `display_name` from
`GET /admin/api/me` and says a plain hello when that is null; it never uses the username or the role.
#97 merged on head `585b42c` with python 3.10, python 3.12, app-window and browser all passing, and
Chief reports Sentinel approved that head on code and security. Its visual acceptance is **not
verified**: no screenshots, 50% overlays, colour samples or lens timing were recorded for it, because
no local browser ran for that work. BRIEF 10.2 acceptance for #97 is still owed.

### Exact-match status at the end of the day

Reported by Chief from Probe's verdicts; this document's author did not re-run them.

- **Probe PASS per BRIEF 10** on main `8ee5856`, dark and light, 1440x852 and 390x844 (axe clean, CLS 0,
  no overflow): #92 first KPI card tint and Overview fitting 1440x852; #94 Uses by tool donut and
  legend; #98 round icons on the count cards.
- **Merged on green CI, not yet visually verified by Probe:** #97 (Overview header, zero-day tubes,
  console phone navigation).

Team work that is **not finished**. None of it is waiting on Arnold, and none of it belongs in
`ARNOLD-ONLY.md`:

1. The page-wide plane `.shell #main::before` still hides the room photo; the AI usage and Uses by tool
   panels are opaque, not glass (Probe confirmed); the BRIEF sample points are not met.
2. Light theme: the top-bar "Monitor" pill shows as a white box (Probe confirmed).
3. The 50% overlay images for #92, #94 and #98 are missing; the donut colours were matched by eye; the
   light-theme yellow arc is likely under 3:1; the legend is not centred with five rows.
4. The wave line on the second count card is not built.
5. The phone KPI caption overflow is not started.
6. What #97 leaves of the header (emoji, amber primary, the recorded name), the eight tubes and phone bar C is
   unchecked.
7. Sign-in, staff shell, light theme and phone rounds are untouched since their first merges.
8. The "Collecting since…" wording and threshold decision is pending.
9. Footer scroll measures 28-39 fps against the 55 fps gate: **not met**. The reveal change was tried
   twice with no gain. The figure comes mostly from this laptop's headless browser; a real number needs
   a device with a real GPU.
10. The D-016 bypass tests are partly built: `chrome-policy.yml` (#107) runs groups A, B and D on Linux
    Google Chrome. Groups C, E, F, X, P, G, H, I and the Windows and macOS cells are not built, so the
    pack's enforcement is proven only for those three groups on that one system. The plan itself
    (`docs/CHROME-POLICY-BYPASS-TESTS.md`) is still draft PR #106, not on main.
11. `SECURITY-REVIEW.md` exists only on the `docs/architecture-review` branch, not on main.
12. Sentinel's post-merge review of #97, #99 and #100 is pending.

Not run today: the full suite on the laptop (CI runs it), any real phone, the Chrome policy pack on a
real device, signed desktop builds. Desktop auto-update stays off until builds are signed.

### Late merges, 21:50 to 22:16

Six more pull requests merged on green CI after the block above was written; main is `4e5b610` and the
day's count is 67.

| Time | PR | Merge | What |
|---|---|---|---|
| 21:50 | #102 | `8a501c6` | Donut follow-up: light-theme arc contrast, legend pitch, 50% overlay |
| 22:01 | #103 | `7a89e8c` | Overview: room visible in dark, glass lower panels, no page-wide plane |
| 22:02 | #104 | `4281820` | Light top bar: area label backing is a 38px pill |
| 22:09 | #101 | `3f6faad` | Progress and state: the 10 November sprint day |
| 22:13 | #105 | `01a34b3` | Browser check: Overview card text stays inside its card on phones |
| 22:16 | #107 | `4e5b610` | Chrome policy pack: bypass checks in CI, step 1 |

Probe's verdicts on main `4e5b610`, as relayed by Chief at 22:51: #97, #102, #104 and #105 PASS; #103
PARTIAL (the lower sample point cannot be reached with `room-warm.webp`). This supersedes item 6 and the
"not yet visually verified" note on #97 above. Probe's own written report is the record; it was not read
for this entry.


### 11 November, 01:00 — control kit page (`feature/kit-page`)

`#/kit` (also `#kit`) in the console: owners only, not in the navigation, every kit control in every state,
built from the same `SUI` functions the pages use; it calls no API. Files: `gateway/static/admin-kit.js`,
one script tag in `admin.html`, `.kit-*` rules at the end of `admin.css`, `ControlKitPageTests`, and a browser
pass in `tests/browser/kit.cjs` (1440x852 and 390x844, dark and light; screenshots in the CI artifact). Seen in
CI's Chromium at `dd5bffa`, no findings; viewing the renders found filter chips cutting off descenders, fixed.

### Dark donut orange contrast follow-up — 10 November 2026

Branch `feature/donut-dark-contrast`, based on main `4e5b610`. The dark first arc and its legend dot
use `--donut-orange: #F7AE62` (the reference amber) instead of `#F2793A`. BRIEF 10.1.3 allows this
contrast adjustment; it changes no geometry. Light retains its existing darker orange.

Computed WCAG contrast against the brightest ring-adjacent pixel in the existing #103 capture
(`docs/screenshots/overview-room/overview-1440x852-dark.png`, pixel 845,626 = RGB 111,92,84) improves
from 2.270:1 to 3.354:1. The sample covers radii 42–46 and 70–76 around ring centre 891,686, avoiding
the coloured stroke and centre text. This is a calculation using an earlier capture, not a new
rendered measurement. The regression also checks the BRIEF panel target and opaque fallback.

Validation: `python3 -m unittest tests.test_static_js -v`: 9 tests in 3.016s, OK; `git diff --check`
passed. Not run locally: Chromium, fresh screenshots/overlay, axe, motion/fallback captures, full
Python suite. Chief assigned CI-only checks and Anvil holds the browser slot. CI must pass before
merge; fresh visual acceptance remains unverified.


## Overview as an L1 — 11 November 2026, 01:00 block (Kampala time)

Asked for by Chief at 01:02. Draft PR #120, branch `feature/overview-l1`, based on main `31ecbfc`.

Built: Overview holds seven blocks (four number cards, the AI usage chart, two count cards); every card
opens its list filtered to what it counts; one "Next step" line under the title (`A.frame({ next })`);
the trail in the top bar (`A.frame({ trail })`), also on Needs attention, Live and Activity so each
links back; one primary button. *Uses by tool* shows on Activity → Who used what when grouped by tool.
`docs/UI.md` Page levels and Canonical homes are updated.

Validation: `python3 -m unittest tests.test_static_js tests.test_static_css`: 21 tests, OK;
`node --check` on both changed scripts. Not run: any browser check. No-scroll at 1440×852, the 390×844
layout, light and dark screenshots and the 2/3 + 1/3 layout are unverified; the one Chromium slot was
held by Probe. Not built: the kit's breadcrumb dropdown, and Back restoring scroll position.

Next step: when the browser slot is free, screenshot #120 at 1440×852 and 390×844 in both themes, fix
what that shows, then merge on green CI. #119 (kit page, `feature/kit-page`, WIP `cb3e8f9`) is untouched
and comes after Overview.

## Probe: point-7 basic-user test, 11 November 2026 (Kampala time)

Two runs on a throwaway demo (`DEMO_MODEL=1`, `tests/browser/demo.py`), owner account, fresh browser context,
headless Chromium 1248 through Playwright 1.63, 1440×852 dark and 390×844 dark. Nothing on the live Hub was
touched; the demo process and the browser were stopped afterwards. Chromium slot taken 13:58 and released ~14:20.
No second opinion asked (QA walk, not a final verdict). Not run: the full suite, light theme beyond one Overview
shot, a real phone, hover/animation checks.

### Run 2: main c863c7d (has #136 Overview, Simple/Detailed, six task tiles) — screenshots in `docs/screenshots/point7-basic-user-c863c7d/`

Overview at 1440×852: no scroll (852 px). A one-sentence answer ("1 person is waiting for a tool.") plus **three
blocks**: What do you want to do? (six tiles), How it is going, Waiting for you. At 390×844 the sentence and the
tile block fill the first screen, the other two blocks follow (page 1371 px, no sideways scroll).

| # | Task | Clicks to start | Clicks to finish | Result |
|---|---|---|---|---|
| 1 | Add a person | 1 (tile) | 5 (tile, 3× Next, Add) | PASS. 4 steps, "No team yet" pre-selected, "Here is what will happen" screen, result offers "Give Kato Brian a tool". |
| 2 | Give that person a tool | 1 | 7 (tile, person, Next, tool, Next, Next, Give access) | PASS. "30 days" default, plain summary ("It works on their next visit"), result offers "See Kato Brian's access". |
| 3 | Answer a waiting request | 1 | 5 (tile, Next, Give access, Next, confirm) | PASS. Oldest chosen for you, safe default "Decide later", result offers "Answer the next request". |
| 4 | Find what was spent this week | 1 | 3 (tile, Next, Show the total) | PASS with a caveat: the choices are "last 7 days / last 30 days"; there is no calendar "this week". Result "< $0.01 in the last 7 days" and a "See where it went" link. |
| 5 | See what one person used | 1 | 5 (tile, person, Next, Next, Show the use) | PASS. "Nansubuga Grace used 1 tool in the last 7 days. That is 3 uses in all." |
| 6 | Stop all AI | 1 | 4 (tile, "Yes, stop everything", Next, Stop all AI) | PASS and effective: banner "AI access is paused for everyone…" with "Resume access"; the Resume button turned it back on ("Access resumed."). Default answer is "No, keep it running". |

All six start in one click from the landing page, none needs scrolling to find the way, every step is one
question with a Back, and each ends with a next-step button. This is the first run where the guided flows exist,
so the earlier "4 clicks to start" and "stop all AI hidden in the avatar menu" findings no longer apply.

### Defects still on main c863c7d (exact element)

- **F1, person page "LAST SEEN … visited a site" is false (honesty rule).** Kato Brian was only given a tool by an admin and
  has never signed in, yet his page says "LAST SEEN just now · visited a site"; Grace, who only signed in and asked for a tool,
  shows "6 min ago · visited a site". The stat counts any timeline event (admin and sign-in events too) and labels it a site visit.
  Fix: count only the person's own requests, launches and visits, and word the label per event type. Owner: Forge.
- **F2, Access requests (`#/requests`) shows only "GOVERN" in the trail**, at 1440 and 390: no page crumb (People shows
  "Govern › People"). Page not restructured yet.
- **F6, person header has a primary "Issue a key" button** beside Next step ("They can't sign in yet. See how to connect them"):
  two competing primaries and an unexplained word. Still there.
- **New, "Waiting for you · See all 3"** on Overview counts "5 seats unused for 30 days" and "Providers without a company key"
  next to "1 tool request waiting", while the sentence above says only the one person is waiting. "Seats" is jargon on a default screen.
- **New, Task 4 wording**: asks for "this week", offers "last 7 days". Add a "This week" choice or word the tile "last 7 days".
- Not re-checked in run 2 (not on the six-task path): F4 "1 uses" plural, F5 block counts of the L2/L3 pages, F7, F9 phone scroll
  lengths of person pages (person Access still scrolls: 1028 px at 1440×852, 1920 px at 390×844).

### Fixed since run 1 (b4a9972)

F3 (breadcrumb of Spend by person is now full: "Money › Licences & spend › Spend reports › Spend by person" at both sizes);
F5 for Overview (three blocks); F8 (toast now "0 requests were cut."); the Add-person sheet no longer shows the internal
owner-exceptions sentence.

### Words a new user may still not know on the six-task path

"seats", "company key", "audit log" (in "This is written in the audit log"), "Gateway time", "metered".

### Verdict

**Point-7 basic-user test on main c863c7d: PASS for all six tasks, with the four defects above to fix (F1 is the one that must not ship).**
Observation for Sentinel carried over from run 1: staff prompt text appears in Grace's timeline because `store_bodies` defaults on; check
against the point-3 rule that admins see metadata only.


## Probe: ordered fix list from the point-7 failures, 11 November 2026 22:30 (main fa19c0d, static review)

Checked against main fa19c0d by reading the code and the earlier browser runs. Browser re-check only when the Chromium slot is free after #141.
Fixed and verified earlier: F2, F3, F6, F7, F8. F1 is fixed by 769a91b (#140), code-read only, not yet seen in a browser.

Still open, in this order:

1. **F4, "1 uses"** (gateway/static/admin-govern.js:289). Use "1 use" / "N uses". Owner: Forge. Done when a person with one use reads "1 use".
2. **"Waiting for you" mixes unlike things** (gateway/insight.py:983 "N seats unused for 30 days", :1017 "Providers without a company key").
   They are low-priority licence notes counted next to "1 tool request waiting". Keep them out of the Overview count (still on Needs attention),
   or reword in plain terms ("5 paid licences nobody opened in 30 days"). Done when Overview's count matches the sentence above it.
3. **Task 4 wording** (gateway/static/admin-guide.js:11 and :153). The guide asks "this week", the choices say "The last 7 days". Add a "This week"
   choice or word the task "last 7 days". Done when the task text and the visible choice use the same words.
4. Needs attention lists a renewal for a cancelled plan (gateway/insight.py:987, no cancelled filter; Money L1 #131 already skips it). Add the same filter.
5. F5, block counts of the L2/L3 pages (only Overview is at three blocks); F9, person Access scroll (1028 px at 1440x852, 1920 px at 390x844).
6. Jargon left on default screens: "seats", "company key", "audit log", "Gateway time", "metered". Reword or explain on first use.

Not mine to fix (read-only QA). Top three go to @Forge/@Anvil.

### Run 1: main b4a9972 (Overview before #136), 8:20

Result: four tasks PASS, one PARTIAL (spend this week), one PASS but hard to find (Stop all AI, only in the avatar menu). Failures F1–F9 are
listed in the run-2 section above where they still apply. Screenshots of that run were not committed (8 MB of PNG); the run-2 set above replaces them.
## Forge: rest handoff, 11 Nov 2026 14:10 EAT (PR #141, feature/bookings-buttons, draft)
Head 2dba13f is pushed; the worktree is clean. Built: buttons on the Bookings model, kit page showing every state (hover, focus, pressed, loading, glass, icon buttons, tab strip). Not run: any browser screenshot (Chromium slot was not mine).
CI on the head: the `browser` job failed (run 43009285809); the python jobs were still pending when I stopped. I did not read the failure log (run was still in progress).
Exact next step at 16:00, in this order:
1. `gh pr checks 141`; if `browser` is red, `gh run view 43009285809 --log-failed`, fix the product first (the test only if the test is wrong), push.
2. Chromium check on the kit page (`/admin#kit`): light and dark, 390x844 and 1440x900, screenshots into docs/screenshots/bookings-buttons/, one line per remaining difference. Kill the browser after.
3. Then F3, F6, F7, F2, then #134 (see its handoff above). #141 stays a draft until Chief says otherwise.

## Forge: handoff, 11 Nov 2026 20:30 EAT
- **#141** (feature/bookings-buttons): head 78eee73 pushed. Earlier CI failures were my radius change leaking into the kit's box controls (fixed with `--box-r*` tokens in tokens.css, ui.css uses them), the tab strip radius (12px) and a stale panel count in kit.cjs (9 to 11). Locally green, one at a time: people, touch, tools, lists, kit, charts, staff-font, admin-cls, updates-copy, logo-contrast, exact-footer. `signin.cjs` timed out on this laptop at 420 s (no assertion failed): CI decides it. Still draft; screenshots at 1440x852 / 390x844 not taken.
- **#147** (Access requests) and **#148** (Last seen + panel cap): CI fully green at last look (python 3.10/3.12, browser, app-window). `gh pr ready` / `gh pr merge` are refused for me by the permission classifier, so @Chief marks ready and merges.
- Next step: `gh pr checks 141`; if only `signin` is red, read its log and fix the product. Then merge main into #147/#148 if they conflict, then the next §10.10 page (Policies, Weekly reporting, Settings).


## Lane B D3b: Models/Audit phone buttons — 12 November 2026

Split from the preserved combined implementation `c85be0f` onto main `0135ac2`.
At widths <=640px the Models See all button is visibly 36px and small Models/Audit pager buttons are 30px. The existing shared pseudo-element retains a 44px target. Models reserves 8px under See all for the target and focus ring. Existing browser checks cover visible size and target height at 390 and 640 in both themes, and click below the visible See all box.
## Lane B M1: Models desktop scrolling — 12 November 2026

Split from the preserved combined implementation `c85be0f` onto main `0135ac2`.
Models Simple uses the existing Audit Simple table-height allowance for the sentence and next step above the list. A long table scrolls inside its panel at 1440x852. Existing browser coverage adds 80 synthetic rows and checks internal scrolling and no document overflow.

The combined version passed 102 targeted checks in 124.398s and syntax checks for 53 JavaScript files.
Not run on this split: local browser, screenshots/overlays or test suites (Probe owns the sole
browser/test slot after the 22:43 crash). Full suites run on CI; fresh rendered review is pending.
Reference differences follow BRIEF 10.10.6/7 (10.1.6); hit-area padding follows 10.1.3.
Copy and keyboard semantics are retained. No visual acceptance is claimed.

Split validation: changed browser scripts pass `node --check`; `git diff --check` passes.

Probe reviewed #189 product head `fa6fab4`: CSS passes; shipped `models.cjs` fails because
its raw mouse click targets a button below the viewport. `audit.cjs` passed 162/162.
The test now scrolls See all into view before measuring/clicking its expanded target.
Probe's temporary copy with this exact one-line correction passed `models.cjs` 164/164;
that is separate from fresh verification of this committed artifact, which is pending.
Evidence is saved in `docs/screenshots/models-audit-phone-buttons/`, with unmodified
and patched runs labelled separately. Prism inspected the 390px light focus capture.
The measured visible heights are 36px See all / 30px small pager with 44px targets;
focus is not clipped at 390/640 light/dark. No new product CSS changed in this correction.

Probe subsequently ran the unmodified committed `tests/browser/models.cjs` at local
`d09774a`: 164 checks passed, exit 0, all six cells. This closes the earlier test FAIL.
The result applies to the corrected script; `audit.cjs` was not repeated (unchanged,
162/162 on `fa6fab4`). Fresh remote CI remains required before #189 is ready.
Probe verified #188 product head `d4eff95` in real Chromium: `models.cjs` 100/100. At
1440x852, Simple light/dark default/long have zero document overflow; the wrapper is
352px high and scrolls internally. Without this CSS, overflow is 24px. Detailed remains
462px with no overflow. Evidence is saved in `docs/screenshots/models-scroll-height/`.
Prism inspected the long-list dark capture and notes. Probe's verdict is single-model.
No Models reference still exists: BRIEF 10.10.2 is the criterion; no overlay was made.
Phone checks and fresh CI on the evidence commit remain unverified here.
## Lane B: sign-in system-colour fallback — 12 November 2026

Branch `fix/lane-b-signin`, based on main `0135ac2`. Forced-colours mode now explicitly uses
Canvas/CanvasText, ButtonFace/ButtonText, Field/FieldText and Highlight, removes the scene photo
and blur, and keeps keyboard focus visible. BRIEF 10.1.3 permits this system-palette difference.
Ordinary light/dark geometry and the later box-control requirement are retained.

Validation: `python3 -m unittest tests.test_static_css tests.test_static_js -q`: 102 tests in
86.962s, OK. `node --check tests/browser/signin.cjs` and `git diff --check` passed. The existing
sign-in browser suite now includes both apps at 390x844 in light/dark forced-colours palettes,
checking the effective system colours, photo removal, no blur and keyboard reachability.
Not run: new browser cases, screenshots/overlays, axe, full suite or real Windows High Contrast.
Probe must inspect the finished artifact; this is not a completed sign-in exact-match verdict.

Lane B queue remains open: sign-in full visual pass; light theme/Monitor; phone bar and KPI caption;
staff shell; Probe's remaining fix lists. The 10 Nov twelve-item list above remains historical:
each item needs reconciliation against merged PRs and actual reviewer evidence, including glass/photo,
donut/legend, count-card wave, Collecting since, D-016 C-I and SECURITY-REVIEW.md. No item is dropped.

### #182 review follow-up — 12 November 2026

Probe posted real-Chromium review of `ceea4db` on #182 (comment 6833397250): 24/24 isolated
forced-colours checks passed on the synthetic demo, both apps, light/dark at 390x844. Full GitHub
CI passed on that head (Python 3.10/3.12, app-window and browser). Probe found a visible eye-toggle
border extending 10px beyond its field at 390 and 1440. The forced-colours rule now resets its right
margin to zero; the browser check asserts containment and the existing 44px touch target.
New-head rendered verification and CI remain pending. No reference overlay was produced; normal
sign-in exact-match acceptance remains open. Probe's historical light-theme focus-ring contrast
finding also remains open pending verification on current main. Windows High Contrast and other
browser engines were not tested. No local browser or fixture was started for this follow-up.
Follow-up validation: `python3 -m unittest tests.test_static_css -q`: 27 tests in 1.423s, OK;
`node --check tests/browser/signin.cjs` and `git diff --check` passed. Full suites run on GitHub CI.

Probe independently verified local product head `5ea4a64` in real Chromium: 32/32 isolated
forced-colours checks passed, both apps light/dark at 390x844. Eight additional forced-colours
geometry cases at 390 and 1440 show the eye contained, 44x44, no horizontal scroll. Captures,
geometry JSON and scope notes are saved in `docs/screenshots/lane-b-signin/`; Prism inspected the
phone-light console and desktop-dark staff captures and the geometry JSON. This closes the eye
overhang finding for this product head. Probe's verdict is single-model. Normal-mode overlays,
the main re-test and real Windows High Contrast remain unverified. The historical 2.39:1 focus
finding was on People, not a current sign-in measurement. New-head CI remains pending.

## Lane B O2: light breadcrumb backing — 13 November 2026

The light console area/trail now follows BRIEF 10.3 as bare text instead of a white
backing. Primary ink also colours the separators. The obsolete CSS assertions
requiring the backing are replaced by a rendered check in `tests/browser/money.cjs`
that rejects a background or rim on the Licences breadcrumb. No new tokens or dependencies.

Code checks: JavaScript syntax and whitespace checks passed. Not run locally:
Python or browser suites (one laptop test/browser slot, reserved for Probe). Full
Python and browser checks run on CI. Photo contrast, keyboard focus, 390/1440 light
and dark screenshots and exact-match acceptance remain pending Probe's actual review.
