# Release evidence matrix: Windows and macOS apps (sprint 17 to 21 Nov 2026)

Status: **draft, updated 18 Nov 2026 22:30 EAT against `main` `612282e`.** Rows say PASS only where Probe read the runner log (see "Results read by Probe"); every other row is NOT TESTED, PARTIAL or OWNER. Not production: the builds are unsigned.

For each of deliverables 1 to 10 it lists the evidence that must exist before the row may say PASS, where that
evidence comes from, and what exists today. It extends `docs/RELEASE-ACCEPTANCE-GATE.md` (G7 and G11 especially);
where the two differ, the stricter one applies.

## Rules

- **PASS needs a link** (CI run URL and job, or an owner record) **for the exact release commit and the exact artifact
  SHA-256.** A run for another commit, or for a rebuild, does not count. Anything else is FAIL, BLOCKED, NOT TESTED or OWNER.
- **A green build is not evidence of installation, sign-in or upgrade** unless the job did that step and uploaded its log.
- **Runners:** `windows-latest` and `macos-latest` (GitHub-hosted, a clean image per run, no interactive desktop login).
  They are not company devices: no real SmartScreen or Gatekeeper prompt, no keychain unlock dialog, no sleep or Wi-Fi
  change, no second human user. Those rows are marked **OWNER** and only Arnold's device runs close them.
- **Test data only:** a Hub started by the job on 127.0.0.1 with `tests/fake_upstream.py`, fixture people, no provider key,
  no company address, no real account. Uploaded logs must not contain keys, cookies or passwords (each row names the grep).
- **Unsigned means unsigned.** Every artifact from this sprint is named and described `RC — UNSIGNED — INTERNAL TEST ONLY`.
  No row may say "production-ready" while a signing or acceptance row is open.
- Legend: **W** = `windows-latest`, **M** = `macos-latest`, **OWNER** = physical device or owner decision only,
  **TODAY** = what exists on `main` now.

## What exists today (so nobody assumes more)

| Piece | State on `main` 8ad23d1 | Source |
|---|---|---|
| Build: PyInstaller on ubuntu, windows and macos, manual `workflow_dispatch`; unsigned archives plus a SHA-256 sidecar | exists | `.github/workflows/build-app.yml`, `packaging/archive.py` |
| Smoke of the built binary: `--version`, fresh `status` exits 2, `--self-check`, `login` approved by a fixture Hub, second `sync`, signed-in `status`, `logout` | exists, one straight pass, **no restart in the middle** | `packaging/smoke.py`, `packaging/README.md` |
| App commands usable by a script: `login`, `status`, `sync`, `apps`, `open`, `autostart on|off`, `logout`, `cleanup`, `update status|check|apply` | exist | `swangz_client/cli.py` |
| Credential storage: platform keychain, with a file fallback recorded as `key_storage` | exists (`swangz_client/core.py`, `keystore`); which one a CI runner uses is **not yet recorded** | `swangz_client/core.py` |
| Hub no longer recognises the device | client keeps local data and tells the person to retry or sign out (`core.py`) | `swangz_client/core.py` |
| Windows installer (Start menu, desktop shortcut option, uninstaller) | **merged** (#243, then #250 for a running copy). Latest run read by Probe: #251's run 44355833898 at 493dd07, all steps PASS (Results below). Still unsigned | deliverable 1 |
| macOS DMG, signing and Gatekeeper document | **merged** (#244). Latest run read by Probe: #251's macOS job 134983573486 at 493dd07, journey passed 31 steps (Results below). `docs/MACOS-SIGNING.md` exists; #251 (draft) adds an evidence section | deliverable 2 |
| Updates | disabled by design (`ENABLED=False`, no pinned release key) | `packaging/README.md` |
| Managed workspace | **merged** (#204). Demo record is PR #236 (steps 1 to 4, Linux, headless). #204's `Inert profiles` jobs on `windows-latest` and `macos-latest` were green (names and status only; Probe did not read their logs). No real-Chrome run on Windows or macOS | `docs/W-DEMO-RESULT-20261114.md` |
| Prompt and reply privacy exposure (F-18, `store_bodies`) | **merged** (#249, 612282e): off by default, content readable only with the trust area. Probe VERIFIED at 58da416 (12 tests plus a whole-database marker scan; no second opinion, codex unreachable). Old stored content stays until retention (Arnold's call). No packaged-app round trip | `docs/DECISIONS.md` D-023 |
| Machine-policy integrity (W6 / R-8) | **merged** (#248, D-024). Company devices report and verify before Open. Probe has not read a Windows or macOS runner run of a tampered pack; Linux Chrome CI only (`w6-step5`) | `.github/workflows/w6-step5.yml` |

## Evidence kinds

| Code | What it proves | Minimum artifact |
|---|---|---|
| **I** Install | clean machine to a working app, files where documented, shortcuts, registered uninstaller | silent-install exit code 0, file listing, registry or `.app` listing |
| **A** Auth | enrolment with an approved code; key stored only where documented; wrong, expired and reused codes refused | smoke log, Hub audit rows, grep showing no key in logs or files outside the keystore |
| **R** Restart | app killed and relaunched, still signed in; Hub stopped and restarted, the app reconnects without a new code; a revoked device is refused | log with timestamps, `status` before and after |
| **S** Security | no secret in the artifact or logs, data-folder permissions, one person cannot read another's profile, policy tamper detected, checksum, SBOM | scan output, ACL or mode listing, checksum file, SBOM |
| **U** Upgrade | N+1 over N keeps sign-in, profile folders and settings; a bad or older build is refused | before and after listing, `status`, profile marker still present |
| **X** Uninstall | everything the installer made is gone; the data folder is kept or removed as documented; the Hub shows the device disconnected | listing after, Hub device row |

## The matrix

Each cell is the evidence a runner job must produce. `n/a` = does not apply to that deliverable.

### 1. Windows installer (Start menu, desktop shortcut option, uninstall, optional start on login)

| Kind | Runner evidence (W) | TODAY | OWNER-only |
|---|---|---|---|
| I | silent install exits 0; Start-menu entry present; desktop shortcut present only when chosen; uninstaller listed in Add or remove programs | PASS on runner (run 44355833898) | SmartScreen prompt on a real PC; how the shortcut looks |
| A | the installed binary completes the smoke login | PASS on runner, installed copy | |
| R | kill and relaunch the installed app, still signed in | PASS on runner: relaunch, Hub down then back | start on login after a real reboot and sign-in (`swangz autostart on` writes the entry; a runner can only check the entry exists) |
| S | install folder ACL listed; no secret inside the installer; log shows no Defender or policy command | PARTIAL: self-check only (updates off, 0 release keys) | |
| U | see row 9 | PASS on runner: 0.1.0 to 0.1.14 over a running copy (run 44397268970, main `e27ceb4`) | a second Windows user |
| X | silent uninstall removes folder, shortcuts, startup entry and uninstaller entry; leftover list matches the doc | PASS on runner, also with the app running (#250) | |

### 2. macOS `.app` and DMG, with signing and Gatekeeper documented

| Kind | Runner evidence (M) | TODAY | OWNER-only |
|---|---|---|---|
| I | mount the DMG, copy the `.app`, record `codesign -dv` and `spctl -a -vv` output as it is (unsigned is expected to be rejected; the document must say so) | PASS on runner (31-step journey); Gatekeeper rejects the unsigned RC as expected | Developer ID signing, notarization, `spctl` accepted, the first-open Gatekeeper dialog on a real Mac |
| A | smoke login from the copied `.app` | PASS on runner | Keychain prompt on a real Mac |
| R | kill and relaunch | PASS: relaunch and sync. **Hub-down reconnect not in the macOS journey** | login item after a real reboot |
| S | no `spctl --master-disable` or quarantine-strip step in any job or document; `.app` layout intact | PARTIAL: signature intact (ad hoc), no Gatekeeper bypass, no secret scan | |
| U | see row 9 | PASS on runner: 0.1.0 to 0.1.10, data kept (run 44391151264, main `dadf6de`) | |
| X | delete the `.app`; leftovers (login item, data folder) listed against the doc | PASS on runner: sign out alone removes the login item (#253), only `browser-profiles` kept (R-12), process gone | |

### 3. Device enrolment and approved company sign-in

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| A | code shown, approved on the CI Hub's `/device`, key issued once; wrong, expired and reused codes refused; a non-company email refused; `logout` revokes the key and the next call is refused | the happy path and logout are in the smoke; the refusals are covered by Hub unit tests, not through the packaged app | Google sign-in with a real Swangz account on the first-party address |
| R | revoke at the Hub; the app notices on its next sync, keeps local data and says what to do | unit-tested in the client, not through the binary | |
| S | the key appears in no log and not in `status`; record `key_storage` (keychain or file) per runner | not recorded | |
| X | `logout` leaves nothing but what the doc lists | smoke checks credentials removed | |

### 4. Server address set securely, no embedded secrets

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| I | a fresh install has no address; it is given by the person (`login --server`, the sign-in window) | not tested | |
| S | scan of the built binary, archive and installer for keys, tokens, `.env`, company hostnames and common secret patterns: zero hits; a non-https address is refused except 127.0.0.1 (the rule is in `swangz_client/core.py`: https only, except `localhost`, `127.0.0.1` and `::1`; checked in code 18 Nov, the packaged-app test is still to write) | PASS on both runners: Windows and macOS scans clean (see the acceptance table); `--min-archives` makes an empty or wrong folder fail (#266). The packaged app's address rule is not tested | the production address itself |
| R, U | the address survives restart and upgrade | not tested | |

### 5. Company-managed AI browser workspace, separate employee profiles

Needs #204 merged first. Today the only evidence is Linux, headless (#236).

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| I | Chrome found, or a clear refusal; one folder per person under the app data folder | Linux only | real Chrome on a real Windows PC and Mac |
| A | Open goes through the Hub and is recorded (Hub row) | Linux only | a real provider sign-in that persists |
| R | suspend closes the window and keeps the folder; retire removes it; reactivate makes a new generation | Linux only | |
| S | two enrolments give two folders, neither readable as the other (ACL on Windows, mode on macOS); the workspace never opens the Hub address or the default browser; policy-pack tamper is detected | policy pack proven on Linux Chrome CI | a second OS user cannot read the profile; policy applied by the real OS |
| U, X | profile folder and marker survive upgrade; uninstall behaviour matches the doc | not tested | |

### 6. Staff reporting, admin functions, existing functionality

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| A | after sign-in the packaged app lists only what the person is granted; revoke at the Hub removes it on the next sync | Hub tests plus smoke `sync` | |
| R | grants and the person's reports reappear after a restart | not tested | |
| S | **F-18:** with `store_bodies` at its default no prompt or reply text is stored, and a console role without the right cannot read one (Hub tests on CI, plus one packaged round trip). **Machine policy:** a tampered pack is reported. One person cannot see another's data; admins see metadata only | F-18 and policy integrity are open release blockers | admin judgement of the staff and admin screens inside the shell |

### 7. Safe reconnect after restart or network loss

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| R | (a) kill and relaunch: still signed in; (b) stop the CI Hub, wait past two heartbeats, restart it: the app is signed in again with no new code; (c) Hub down at app start: a clear message, no key deleted, no second code issued; (d) revoked while the Hub was away: refused on return, local data kept as documented | (a) and (b) PASS on both runners (Windows: relay cut then restored; macOS: #263, same address, next sync succeeds, the Hub records a new check-in). (c) Hub down at app start and (d) revoked while away: **not run in a packaged app** | real laptop sleep, Wi-Fi switch, VPN (O-4 below) |
| S | after an outage no log line exposes the key; offline never deletes a profile folder | not tested | |
| U | restart after upgrade still signed in | PASS on both runners: after the upgrade the device is still signed in and checks in (Windows: heartbeat after upgrade; macOS: window opens, same device). Reconnect after a Hub outage is Windows only | |

### 8. Versioned artifacts, checksums, reproducible builds, release notes

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| I | the name carries the version and `UNSIGNED`; the `sha256` file verifies on a clean runner | sidecar checksums exist and verify (Windows, macOS). The shipped version is `0.1.<patch + run number>`: two builds of one commit differ | |
| S | two builds of the same commit give the same SHA-256, or the differing bytes are listed and explained (timestamps, signatures); an SBOM is attached; pinned tool versions are listed | Windows: two builds of one tree identical (program and installer); SBOM read (67 components) and validated by `cyclonedx-cli`. macOS: SBOM read (53 components, validated); **no macOS reproducibility check**. Build tools: macOS pinned by version and SHA-256 (#253, `--require-hashes`); Windows PyInstaller pinned by version only, Inno Setup by SHA-256 | the approver reads the notes; they may not say production-ready |

### 9. Controlled update architecture, updates disabled until signing

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| S | `update status` says updates are off; with no pinned key an offered update is refused; a tampered or older package is refused | the updater exists and is disabled; its unit tests use `tests/fixtures/test_release_rsa4096.json` | enabling updates needs a signing key and Arnold's decision |
| U | build N and N+1 from two commits; install N, enrol, create a profile marker, install N+1 over it: still signed in, marker kept, version changed; then N over N+1 is refused or documented as unsupported | **PASS on both runners.** Windows 0.1.0 to 0.1.14 (key, device and sign-in kept, installer closed the running app); macOS 0.1.0 to 0.1.10 (person, device and data kept). **Not tested:** N over N+1 refused or documented, a genuinely older release (the "previous" build is the same source labelled 0.1.0) | |
| X | removing N+1 after an upgrade leaves what the doc lists | not tested | |

### 10. Evidence from install, auth, restart, security, upgrade and uninstall

One `release-evidence` workflow runs rows 1 to 9 on both runners and uploads logs, a JSON report and the checksums. It
writes a table keyed by commit and SHA-256. Today there is no single combined workflow: each platform's own workflow (`release-windows.yml`, `build-macos.yml`) uploads its logs, JSON report, checksums and SBOM, and the acceptance table below joins them. Every OWNER cell above is recorded by whoever ran it.

## Results read by Probe

### Deliverable 1, Windows installer: commit 43c92da, run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44170698656, artifact `Swangz-Windows-installer-evidence`

Runner: Windows Server 2025 10.0.26100 (`windows-latest`), Inno Setup 6.4.3, `Swangz-Setup-0.1.0-UNSIGNED.exe`. `report.json` says `ok: true`.

| Kind | Result | What the log shows | Not shown |
|---|---|---|---|
| I | PASS (runner) | silent install, no admin install mode (HKCU); files under `%LOCALAPPDATA%\Programs\Swangz`; Start-menu and desktop shortcuts created (installed with the desktop task selected); `Run` value `Swangz` with `--background`; Apps and features entry 0.1.0 | desktop shortcut left out when not chosen; Add or remove programs seen by a person; SmartScreen |
| A | PASS (runner) | device code approved against the CI Hub, first sync done, `key_storage: keychain` | wrong, expired, reused code refusals through the installed binary |
| R | PASS (runner) | program closed and started again, still signed in; Hub recorded sync and check-in; Hub unreachable: sync exited 1, credentials and state kept, next sync checked in with no new sign-in | revoked-while-down; reboot with start at sign-in (OWNER) |
| S | PARTIAL | `self_check`: frozen, updates off, 0 production keys | install-folder ACL listing; secret scan of the installer; checksum verified on a clean runner |
| U | PARTIAL | install over an existing install (same version): same device, still signed in | N+1 over N; profile folder marker kept; older build refused |
| X | PASS (runner) | silent uninstall ran `Swangz logout` first: device disconnected at the Hub, credentials removed; program, both shortcuts, Run value and uninstall entry deleted; install folder removed (first delete failed with code 145 and succeeded on retry, `Removed all? Yes`) | the person's data folder, if the doc keeps one; no Hub row read by Probe beyond the report's statement |

Deliverable 1 stands as: install, auth, restart, reconnect and uninstall PASS on the runner for the unsigned RC; security, upgrade and OWNER rows open. Not production.

### Deliverables 1 and 2, latest runs: PR #251 head 493dd07 (read 18 Nov 2026)

**Windows**, run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44355833898/job/134983572610. `Swangz-Setup-0.1.0-UNSIGNED.exe`, 13,955,689 bytes, SHA-256 `ba62076a2c7c17fe5dd38c120fa08494cc7819ed3580e89a304ac6f1c551d9bc`.
PASS: silent install without administrator rights (program, Start-menu and desktop shortcuts, start-at-sign-in value, Apps and features entry); launch (`--version`, Tk window, `--background`, updates off, no release keys); enrol against the CI Hub (key in the keychain); restart still signed in; Hub unreachable then back with no new sign-in; **reinstall over a running copy** (the installer closed it, same device); **silent uninstall while running** (program stopped, device disconnected at the Hub, credentials and Credential Manager entry removed, program, shortcuts, Run value and Apps and features entry gone). This closes the gap Probe raised on #243.
Not shown: uninstall while the Hub is unreachable, N+1 over N from a different build, a second Windows user, installer secret scan, SmartScreen.

**macOS**, run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44355833974/job/134983573486 (`macos-latest`, arm64). `Swangz-0.1.4-RC-UNSIGNED-macos-arm64.dmg`, 11,846,983 bytes, SHA-256 `dfccc8180a36f87681f39f4d393ee8994e678bcbe97c5dc1b3422df603af491e` (`shasum -c` OK, `hdiutil verify` VALID). Journey passed, 31 steps:
PASS: DMG holds the app, an Applications link and the RC notice; old build 0.1.0 installed from its DMG; self-check; `codesign --verify` intact (ad hoc); `spctl` rejects the unsigned RC (expected, recorded, not bypassed); window opens; code approved in the person's browser; sign-in exit 0; device connected at the Hub; start at login on; relaunch still signed in; **upgrade in place 0.1.0 to 0.1.4** keeping the same person and device and data (`browser-profiles`, `device.json`, `extension`, `manifest.json`, `state.json`, `workspace-state.json`); sign out tells the server and removes Swangz; device disconnected at the Hub; no key in the data folder; no Swangz item in the login keychain; only `browser-profiles` kept (R-12, by design); login item removed; app removed; no Swangz process left.
Not shown: Hub down then back (R), second macOS user, a real Gatekeeper first-open and Keychain prompt (OWNER), signing and notarization (OWNER), a tampered or older build refused.

Row 9 update: upgrade (U) now has runner evidence on macOS (0.1.0 to 0.1.4, data kept) and a same-version reinstall on Windows; an N+1 over N on Windows and the refusal of an older build remain open.


### Post-merge on main: #252 (Windows upgrade) and #253 (sign out turns off start at login), read 19 Nov 2026

Main at `e27ceb4` (#252 merged `0075869`, #253 merged `dadf6de`, this matrix merged `e27ceb4`).

- **Hub checks on `e27ceb4`** (run 44391323345): python 3.10 and 3.12, browser and app-window all success. The Hub checks runs on `dadf6de` and `0075869` show cancelled because a newer push replaced them (concurrency), not because a job failed.
- **Windows**, run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44397268970 (`workflow_dispatch` on main at `e27ceb4`, `windows-latest`, Windows Server 2025). The Windows workflow runs on pull requests only, so I started it by hand on main. `report.json` ok. `Swangz-Setup-0.1.14-UNSIGNED.exe`, 13,955,969 bytes, SHA-256 `46f0e00a72a1172a980d1d7d786cdac14e046900fc389c8868b293070e783220` (my `sha256sum` of the downloaded file equals the sidecar). 7 steps PASS: silent install; launch; enrol; restart; network interruption and return with no new sign-in; **upgrade 0.1.0 to 0.1.14 over a running copy** (same device and key, no new sign-in); silent uninstall while running. Artifacts: the 0.1.14 installer, its checksum and `RELEASE-LABEL.txt` ("RC — UNSIGNED — INTERNAL TEST ONLY"), plus the evidence logs; the previous installer is not uploaded.
- **macOS**, run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44391151264 (main `dadf6de`): journey success. `Swangz-0.1.10-RC-UNSIGNED-macos-arm64.dmg`; old 0.1.0 installed, upgraded in place to 0.1.10 with data kept; "start at login still on before sign out", then sign out, then "sign out removed the login item" (no `autostart off` beforehand); keychain item gone; only `browser-profiles` kept (R-12); no Swangz process left.
- **Not proven by a runner:** sign out removing the Windows `Run` value (#253's unit tests patch the platform to darwin and linux only, the Windows journey ends in uninstall, not sign out); an older build refused after N+1; the stored Credential Manager secret equal to the original (it is checked as present); the `key_id` value is asserted equal but not printed in `report.json`.

### Windows RC rows read on 19 Nov 2026: reproducibility, downgrade refusal, secret scan (run 44418629043, head 7907035 of PR #258)

Main `1a38664` (after #259 and #260): `Hub checks` and `macOS app (RC, unsigned)` both completed success (runs 44418358789 and 44418358776). The Windows installer workflow runs on PRs, not on main pushes, so the Windows rows below come from the #258 run, whose Windows tree equals main plus the scan. Artifact `Swangz-Windows-installer-evidence`; read by Probe.

| Row | Result | What the artifact shows | Not shown |
|---|---|---|---|
| 8 reproducible build (Windows) | PASS (runner) | two builds from the same tree give identical SHA-256: program `e90390864fd4...` (12426096 bytes) and installer `1330d627f682...` (13956394 bytes), `identical: true` | a macOS equivalent; a build on a second runner image |
| 9 / 1-U older build refused | PASS (runner) | after upgrading 0.1.0 to 0.1.25, installing 0.1.0 over it aborts: "Swangz 0.1.25 is already installed. This installer is an older version (0.1.0) and will not replace it." | that the sign-in and profile marker survive the refusal (the report's wording not re-read for this) |
| 1-S, 4-S secret scan | PASS (runner), PR #258 VERIFIED by Probe | 11 files, 1318 inner entries, `dist\Swangz.exe` opened as a PyInstaller archive, 0 hits, 0 unreadable. A planted fake key, API_KEY assignment, tunnel address and `.env` were all caught (exit 1) in Probe's own run; the report masks values | the setup .exe is scanned as raw bytes only (LZMA payload); macOS scan not wired |

SBOM (#260): read from the runs below (row 8).

## Acceptance table, main `46bdec1` (rows 5, 6 and 10 updated at `8013574`), read 19 Nov 2026 (runner scope; every build is an unsigned internal RC, not production)

Runs read by Probe: Windows https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44448432643 (`workflow_dispatch` on main; the Windows workflow runs on pull requests only), macOS https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44446670259 (push to main), Hub checks https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44446670258 (python 3.10 and 3.12 and app-window success; `browser` was still running when I read it, so the Hub suite is not yet green on this commit).
Artifacts: `Swangz-Setup-0.1.38-UNSIGNED.exe`, SHA-256 `61595534f526977a…` (sidecar and my `sha256sum` equal); `Swangz-0.1.41-RC-UNSIGNED-macos-arm64.dmg`, SHA-256 `e7dddf4e642d5d9c…`.

| # | Deliverable | Runner result | Open, not proven |
|---|---|---|---|
| 1 | Windows installer | **PASS**: silent install, launch, enrol, restart, network cut and return, upgrade over a running copy, older build refused, sign out, uninstall while running; secret scan clean (1,318 entries, 0 hits) | SmartScreen, reboot with start on login, second Windows user (OWNER); install-folder ACL not listed |
| 2 | macOS app and DMG | **PASS**: 41 journey steps; DMG and `.app` checks, `codesign` intact (ad hoc), Gatekeeper rejects the unsigned RC as documented; the mounted DMG's app equals the scanned build and the mounted volume is scanned (0 hits); upgrade in place; sign out removes the login item; only `browser-profiles` kept | Developer ID, notarization, a real first open, real Keychain (OWNER) |
| 3 | Enrolment and approved sign-in | **PASS** for code, approval, sign-in, sync, sign out and revoke on both runners | wrong, expired and reused codes and non-company emails through the packaged app (Hub unit tests only); real Google sign-in (OWNER) |
| 4 | Server address, no embedded secrets | **PARTIAL**: both scans clean; empty or wrong scan folders now fail (#266, tested here with synthetic folders: exit 1 for an empty folder, exit 1 for `--min-archives 1` on a plain folder, exit 2 for a missing path) | a fresh install has no address and a non-https address is refused: not tested in the packaged app; the production address (OWNER) |
| 5 | Company browser workspace, separate profiles | **PARTIAL (runner)** since #270: on both runners the installed app opens a granted tool in a real Google Chrome window on one per-person folder inside its own data folder; the folder's marker matches this person and this device; Chrome wrote `Local State` there; the Hub records the open. 6 steps on each OS | a second person getting a different folder; the profile and its marker surviving an upgrade (not asserted); ACLs and a second OS user (OWNER); a real provider sign-in (OWNER); proof of the Chrome command line (only `Local State` is checked) |
| 6 | Staff reporting and admin functions; F-18; machine policy | **PARTIAL**: F-18 (#249) and policy integrity (#248) merged with Hub tests; since #270 a **packaged F-18 round trip PASSES on both runners** (9 steps: storage off by default; request with the app's own credential recorded with no prompt or reply; owner turns storage on; trust role reads the prompt; viewer gets `content=withheld`; storage off again); staff and admin screens by the app-window and browser suites | the "off" check reads the console API only, not the database, WAL or logs; the packaged app's grants after restart; machine-policy tamper through the packaged app |
| 7 | Reconnect after restart or outage | **PASS** for relaunch and Hub unreachable then back, on both runners | Hub down at app start; revoked while away; key never in logs after an outage; sleep, Wi-Fi, VPN (OWNER) |
| 8 | Versioned artifacts, checksums, reproducibility, notes | **PASS** checksums both; **PASS** Windows reproducibility (program `3d7f9e40…`, installer `61595534…`, both `identical: true`); SBOM read on both (Windows 67 components, macOS 53, CycloneDX 1.5, tool-validated); RC notice and `RELEASE-NOTES-RC.md` exist | macOS reproducibility not checked; version is `0.1.<run>`, so two runs of one commit differ in name and hash |
| 9 | Updates off until signing | **PARTIAL**: `updates off, no release keys` in the self-check on both; Windows refuses an older build over a newer one; upgrade N+1 over N PASS on both | macOS older-build refusal; a tampered or older update package through the packaged app (unit tests only); enabling updates is Arnold's decision (OWNER) |
| 10 | Evidence from install, auth, restart, security, upgrade, uninstall | **PASS for what the runners can do** (Windows run 44455161915 and macOS run 44455029714, both on main `8013574`, both success): the two platform workflows produce the logs, reports, checksums and SBOMs listed above | OWNER-only checklist O-1 to O-7 has no results yet |

**Probe's reading of #263 and #266 (main):** both hold at the level stated, with limits from GPT-6.1 Sol (read-only; the author is Claude, so it is the independent vendor) that I confirmed in `packaging/macos_journey.py`:
- "Hub unreachable" cuts a relay in front of a running Hub; it does not stop the Hub process, so a Hub restart is not tested.
- "No new sign-in" is inferred from the next sync succeeding without `reconnect` set and the Hub's `last_used` changing. The journey does not compare the key itself or count sign-in codes.
- "Byte-for-byte" compares names, entry types, file SHA-256, symlink targets and executability, not other modes, ownership or extended attributes.
- The mounted-DMG compare and scan are skipped if `--new-app` is omitted (CI passes it).

### SBOM rows, artifacts read by Probe on 19 Nov 2026

Both files are CycloneDX 1.5 JSON, produced and checked by the official `cyclonedx-cli` 0.33.1 (pinned by SHA-256) in the job log: `BOM validated successfully.`

| Platform | Run, head | File | Result | What it lists | Not shown |
|---|---|---|---|---|---|
| Windows | run 44430620385, head 9fb391a (job green), artifact `Swangz-Windows-installer-RC-UNSIGNED` | `Swangz-0.1.26.cdx.json` | PASS (runner) | 67 components, 65 with SHA-256; the program `Swangz.exe` 0.1.26 with its hash; no secret-pattern text in the file (my own search for key, private-key and tunnel strings) | the SBOM's program hash was not compared with the installed program; the build ran on a pull-request head, not a tagged release |
| macOS | run 44430620376, head 9fb391a (job green), artifact `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` | `Swangz-0.1.28-macos.cdx.json` | PASS (runner) | 53 components (51 files, CPython 3.12.10, the swangz client 0.1.28), 51 with SHA-256; pinned build tools PyInstaller 6.22.3 and hooks 2026.10 with hashes; the subject hash `98254788d698...` equals the SHA-256 of the DMG in `SHA256SUMS` (I recomputed it) | no secret-pattern text found; the DMG's contents are not in the SBOM beyond the `.app` files |

The macOS secret scan in the same artifact (`evidence/secret-scan.json`): 771 files, 805 inner entries, 0 hits, nothing unreadable. The DMG's `READ ME FIRST.txt` is listed by the journey ("holds the app, an Applications link and the RC notice") but is not itself scanned or proven equal to the scanned `.app`; a follow-up PR for that was asked of Forge on 19 Nov and had not landed when I wrote this.

Row 8 SBOM: PASS on both runners for the unsigned RC; that the SBOM matches a tagged, reproducible release is still open. The Windows and macOS file versions differ (0.1.26 and 0.1.28) because each run built its own workflow's version; that is noted, not a defect I can judge.

### #270 post-merge, main `8013574`, read 19 Nov 2026 (deliverables 5 and 6)

Runs: Windows https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44455161915 (started by hand, `workflow_dispatch`; `report.json` ok, 0.1.45, 15 steps including the 6 workspace and 9 F-18 steps), macOS https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44455029714 (push to main, success, 56 PASS lines in the log, SBOM 53 components, secret scan CLEAN 772 files, 0 hits). The same steps passed on the PR runs 44451865923 (Windows) and 44451865888 (macOS). Hub checks on `46bdec1` were success (run 44446670258); the run on `8013574` was still going when I wrote this.

**Probe:** #270 does what it says at the level stated. **GPT-6.1 Sol** (read-only; Forge is Claude, so it is the independent vendor) found limits, which I confirmed in `packaging/hub_journey.py`:
- F-18 "off" proves only that the console API record has no prompt text. It does not scan the database, orphaned body blobs, the SQLite WAL or server logs, and does not assert the reply field is empty by a reply sentinel. (My own earlier DB-wide scan for D-023 covered cells of every table; this journey does not.)
- The workspace step shows one folder, one marker that matches the manifest, `Local State` present and one recorded open. It does not show a second person getting a separate folder, the Chrome command line, or that the profile survives an upgrade (macOS lists top-level names only; Windows checks device and key).
- Possible false passes: `newest()` turns an error into 0, `record()` can pick another request if two run at once (CI is serial), and the detail call's HTTP status is not checked, so an error body would satisfy "off".
- `close_chrome()` ends processes by matching the folder in the command line, with no check that they exited. The app's `open` output is kept in the evidence, so a leaked key would be kept there; the scan does cover the evidence folder.

Fix tasks: (1) in the F-18 step, also scan the fixture database and logs for the `off` marker and assert the reply is empty; check the detail call returns 200. (2) After the upgrade, assert the workspace folder and its marker are still there, and add a second person with their own folder.

## Owner-only checklist (never closed by a runner)

Record device, OS version, date, who, result, and a screenshot with no secret in it.

| Id | Check | Why a runner cannot do it |
|---|---|---|
| O-1 | Windows 11 PC: install the unsigned installer, note the SmartScreen prompt, sign in with a real Swangz account, open one AI site in the workspace, reboot, confirm start on login (if chosen), uninstall | real SmartScreen, Defender, reboot, real Google account |
| O-2 | Mac (Apple silicon): open the DMG, note first-open Gatekeeper behaviour (expected: blocked until signed), Keychain prompt, sign in, workspace, remove the app | real Gatekeeper and Keychain |
| O-3 | A second OS user on each machine cannot read the first user's profile folder or the app data | needs a second logged-in account |
| O-4 | Sleep, Wi-Fi off and on, VPN switch: the app reconnects, no new code | real network and power events |
| O-5 | Production server address, domain, Google OAuth redirect, company identity rules | Arnold's accounts |
| O-6 | Signing certificate, Apple Developer ID, notarization, and the decision to turn updates on | Arnold's purchase and approval |
| O-7 | Provider seat inventory: which person holds which real subscription | provider accounts |

## Who writes which part

| Work | Suggested owner | Rows |
|---|---|---|
| Windows installer, silent flags, uninstall | Forge | 1, 3 to 7, 9 |
| macOS `.app`, DMG, Gatekeeper and signing document | Anvil | 2 |
| Merge #204, then the workspace on Windows and macOS runners | Chief, Forge | 5 |
| F-18 default and role gate; machine-policy integrity | Sentinel with Forge | 6 |
| `release-evidence` workflow: install, enrol against a CI Hub, kill and relaunch, Hub outage, upgrade from the previous RC, uninstall, scans, checksums, SBOM | Probe (new CI tools need Sentinel's nod) | all |
| Release notes, checksum table, status post on 21 Nov 20:00 | Chief | 8, 10 |

## How a row is reported

`Deliverable N, <kind>: PASS | FAIL | BLOCKED | NOT TESTED | OWNER, commit <sha>, artifact <first 12 of sha256>, run <URL>, first failure <one line>`.
A missing line means NOT TESTED.

## Not covered here

Linux and phones (G7 and G8 of the acceptance gate), real provider terms, load, and anything that needs the production server.
