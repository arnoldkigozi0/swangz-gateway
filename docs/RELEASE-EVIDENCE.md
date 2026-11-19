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
| Machine-policy integrity (W6 / R-8) | **merged** (#248, D-024). Company devices report and verify before Open. A tampered pack through the packaged app is PASS on the macOS runner (#293) and the Windows runner (#296, read on its head `0ef0676`, not yet merged when written); Chrome's own enforcement is Linux Chrome CI only (`w6-step5`) | `.github/workflows/w6-step5.yml` |

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
| I | a fresh install has no address; it is given by the person (`login --server`, the sign-in window) | **PASS on both** (macOS #271 steps 3–5; Windows #276 report step 2: sign-in window has no Hub address, `status` exits 2) | |
| S | scan of the built binary, archive and installer for keys, tokens, `.env`, company hostnames and common secret patterns: zero hits; a non-https address is refused except 127.0.0.1 (the rule is in `swangz_client/core.py`: https only, except `localhost`, `127.0.0.1` and `::1`; checked in code 18 Nov) | PASS on both runners: Windows and macOS scans clean (see the acceptance table); `--min-archives` makes an empty or wrong folder fail (#266). macOS packaged app (#271, steps 6–8): `http://hub.example.com` and `http://192.0.2.10:8787` both refused (exit 1) and the Hub issued no sign-in code. Windows packaged app (#276, step 2): non-https addresses exit 1 without saving a device or issuing a sign-in code | the production address itself |
| R, U | the address survives restart and upgrade | **PARTIAL on macOS:** the same address is used after relaunch and after the Hub returns (#271, steps 22, 28–29). **PASS on macOS for upgrade too since #277** (step 70: address unchanged after the upgrade, and the new build syncs to it); a real Hub process restart also keeps it (steps 36–37). **Windows since #287:** address unchanged after the upgrade (report step 31) and the same key after a real Hub process restart (step 9) | |

### 5. Company-managed AI browser workspace, separate employee profiles

Needs #204 merged first. Today the only evidence is Linux, headless (#236).

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| I | Chrome found, or a clear refusal; one folder per person under the app data folder | Linux only | real Chrome on a real Windows PC and Mac |
| A | Open goes through the Hub and is recorded (Hub row) | Linux only | a real provider sign-in that persists |
| R | suspend closes the window and keeps the folder; retire removes it; reactivate makes a new generation | Linux only | |
| S | two enrolments give two folders, neither readable as the other (ACL on Windows, mode on macOS); the workspace never opens the Hub address or the default browser; policy-pack tamper is detected | two enrolments give two folders, each marked for its own person and device, **PASS on both runners since #272** (the second person signs in after the first signs out, on the same device; macOS steps 85–88, Windows the `second person:` lines); what neither runner checks is that one folder cannot be *read* as the other (ACL or mode). Policy pack proven on Linux Chrome CI | a second OS user cannot read the profile; policy applied by the real OS |
| U, X | profile folder and marker survive upgrade; uninstall behaviour matches the doc | **PARTIAL since #272, both runners:** the person's folder and marker are unchanged after the upgrade, after sign out, and while a second person is signed in (macOS steps 62, 77, 89; Windows report steps of the same names). Sign out keeps only `browser-profiles`, as documented (R-12; macOS step 74). Windows uninstall: the report line does not say what happens to the folder, so it is not asserted | |

### 6. Staff reporting, admin functions, existing functionality

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| A | after sign-in the packaged app lists only what the person is granted; revoke at the Hub removes it on the next sync | Hub tests plus smoke `sync` | |
| R | grants and the person's reports reappear after a restart | not tested | |
| S | **F-18:** with `store_bodies` at its default no prompt or reply text is stored, and a console role without the right cannot read one (Hub tests on CI, plus one packaged round trip). **Machine policy:** a tampered pack is reported. One person cannot see another's data; admins see metadata only | F-18 and policy integrity are open release blockers | admin judgement of the staff and admin screens inside the shell |

### 7. Safe reconnect after restart or network loss

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| R | (a) kill and relaunch: still signed in; (b) stop the CI Hub, wait past two heartbeats, restart it: the app is signed in again with no new code; (c) Hub down at app start: a clear message, no key deleted, no second code issued; (d) revoked while the Hub was away: refused on return, local data kept as documented | (a) and (b) PASS on both runners (Windows: relay cut then restored; macOS: #263, same address, next sync succeeds, the Hub records a new check-in). (c) Hub down at app start and (d) revoked while away: **PASS on both** (macOS #271; Windows #276, steps 6, 31, 32; see the #276, #277 and #281 section below). Hub process restart: **PASS on macOS** (#277), not on Windows | real laptop sleep, Wi-Fi switch, VPN (O-4 below) |
| S | after an outage no log line exposes the key; offline never deletes a profile folder | **PASS on macOS for the key** (#271 step 32: the key is in no log or file in the app's data folder or the journey evidence). **PASS on Windows since #287** (report step 8: the key is in no file of the app's data folder or the journey evidence, the fixture Hub log included; the key's own file is skipped, and on the runner the key is in Credential Manager). Profile folder after an outage: not asserted on either | |
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
| U | build N and N+1 from two commits; install N, enrol, create a profile marker, install N+1 over it: still signed in, marker kept, version changed; then N over N+1 is refused or documented as unsupported | **PASS on both runners; older build refused on both** (Windows installer abort; macOS exit 5, #271). Windows 0.1.0 to 0.1.14 (key, device and sign-in kept, installer closed the running app); macOS 0.1.0 to 0.1.10 (person, device and data kept). **Not tested:** a genuinely older release (the "previous" build is the same source labelled 0.1.0, so the refusal is real but tested against a relabelled build) | |
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
Not shown: Hub down then back (R), second macOS user, a real Gatekeeper first-open and Keychain prompt (OWNER), signing and notarization (OWNER), a tampered build refused (an older one is covered by #271 below).

Row 9 update: upgrade (U) now has runner evidence on macOS (0.1.0 to 0.1.4, data kept) and a same-version reinstall on Windows; N+1 over N on Windows has runner evidence (row 9 above); older-build refusal: Windows in the #258 section below, macOS in the #271 section.


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

## Acceptance table, main `46bdec1` (rows 5, 6 and 10 updated at `8013574`; rows 2, 4, 7 and 9 at `20151cb`), read 19 Nov 2026 (runner scope; every build is an unsigned internal RC, not production)

Runs read by Probe: Windows https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44448432643 (`workflow_dispatch` on main; the Windows workflow runs on pull requests only), macOS https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44446670259 (push to main), Hub checks https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44446670258 (python 3.10 and 3.12 and app-window success; `browser` was still running when I read it, so the Hub suite is not yet green on this commit).
Artifacts: `Swangz-Setup-0.1.38-UNSIGNED.exe`, SHA-256 `61595534f526977a…` (sidecar and my `sha256sum` equal); `Swangz-0.1.41-RC-UNSIGNED-macos-arm64.dmg`, SHA-256 `e7dddf4e642d5d9c…`.

| # | Deliverable | Runner result | Open, not proven |
|---|---|---|---|
| 1 | Windows installer | **PASS**: silent install, launch, enrol, restart, network cut and return, upgrade over a running copy, older build refused, sign out, uninstall while running; secret scan clean (1,318 entries, 0 hits) | SmartScreen, reboot with start on login, second Windows user (OWNER); install-folder ACL not listed |
| 2 | macOS app and DMG | **PASS**: 114 journey steps (run 44506182423 on main `13e22b2`, all `pass`; was 41, then 83); DMG and `.app` checks, `codesign` intact (ad hoc), Gatekeeper rejects the unsigned RC as documented; the mounted DMG's app equals the scanned build and the mounted volume is scanned (0 hits); upgrade in place; sign out removes the login item; only `browser-profiles` kept | Developer ID, notarization, a real first open, real Keychain (OWNER) |
| 3 | Enrolment and approved sign-in | **PASS** for code, approval, sign-in, sync, sign out and revoke on both runners | **Windows only, #292 (merged `809dd9e`):** wrong, expired and used codes through the installed program (see the #292 section). macOS: wrong, expired and reused codes still Hub unit tests only. Non-company emails through the packaged app: Hub unit tests only on both. Real Google sign-in (OWNER) |
| 4 | Server address, no embedded secrets | **PARTIAL**: both scans clean; empty or wrong scan folders now fail (#266, tested here with synthetic folders: exit 1 for an empty folder, exit 1 for `--min-archives 1` on a plain folder, exit 2 for a missing path) | fresh install with no address and the non-https refusal are **PASS on both** (macOS #271, Windows #276); the address across an upgrade is **PASS on both** (macOS #277, Windows #287); the production address (OWNER) |
| 5 | Company browser workspace, separate profiles | **PARTIAL (runner)** since #270: on both runners the installed app opens a granted tool in a real Google Chrome window on one per-person folder inside its own data folder; the folder's marker matches this person and this device; Chrome wrote `Local State` there; the Hub records the open. 6 steps on each OS | **closed by #272 on both runners:** a second person gets a different folder, and the profile and marker survive an upgrade (see the #272 section). Still open: two people signed in at the same time (the second signs in after the first signs out), ACLs and a second OS user (OWNER); a real provider sign-in (OWNER); proof of the Chrome command line (only `Local State` is checked) |
| 6 | Staff reporting and admin functions; F-18; machine policy | **PARTIAL**: F-18 (#249) and policy integrity (#248) merged with Hub tests; since #270 a **packaged F-18 round trip PASSES on both runners** (9 steps in #270, 11 since #272: storage off by default; request with the app's own credential recorded with no prompt or reply; owner turns storage on; trust role reads the prompt; viewer gets `content=withheld`; storage off again); staff and admin screens by the app-window and browser suites | the "off" check now also scans the fixture Hub's data folder, WAL, stored bodies and log (#272); it is a fixture Hub on the runner, not the production Hub; the packaged app's grants after restart: **Windows only, #292** (macOS not covered); machine-policy tamper through the packaged app: **macOS runner, #293** and **Windows runner, #296** (see the #293 and #296 sections; Chrome's own enforcement of the pack is not shown on either, and #296 was read on its head before merge) |
| 7 | Reconnect after restart or outage | **PASS** for relaunch, Hub unreachable then back, Hub down at app start, same key and no new sign-in code on return, and revoked while away, on both runners (macOS #271; Windows #276); **PASS on both** for key in no log or file (macOS #271, Windows #287) and a real Hub process restart (macOS #277, Windows #287); start at login removed on revoke on both (#281, #286) | Linux start-at-login removal (unit tests only); a refused Windows registry change (unit test only); a Hub restart on the real server; sleep, Wi-Fi, VPN (OWNER) |
| 8 | Versioned artifacts, checksums, reproducibility, notes | **PASS** checksums both; **PASS** Windows reproducibility (program `3d7f9e40…`, installer `61595534…`, both `identical: true`); SBOM read on both (Windows 67 components, macOS 53, CycloneDX 1.5, tool-validated); RC notice and `RELEASE-NOTES-RC.md` exist | macOS, #293 (merged `14b753c`, run read on its head `8703249`): the `.app` is reproducible (two builds, 420 entries each, identical tree hash); the **DMG is not** (two SHA-256 differ, sizes 11853646 and 11853563). Same runner and run only. Version is `0.1.<run>`, so two runs of one commit differ in name and hash |
| 9 | Updates off until signing | **PARTIAL**: `updates off, no release keys` in the self-check on both; Windows and macOS both refuse an older build over a newer one (macOS: #271, exit 5); upgrade N+1 over N PASS on both | `packaging/bump_version.py` (#293) makes the 0.2.0 bump one reviewed commit, covered by unit tests only; the tree is still 0.1.0 and nothing has been bumped; the "older" build is the same source relabelled 0.1.0 (see the caveat in the #271 section); a tampered or older update package through the packaged app (unit tests only); enabling updates is Arnold's decision (OWNER) |
| 10 | Evidence from install, auth, restart, security, upgrade, uninstall | **PASS for what the runners can do** (Windows run 44455161915 and macOS run 44455029714, both on main `8013574`, both success): the two platform workflows produce the logs, reports, checksums and SBOMs listed above | OWNER-only checklist O-1 to O-7 has no results yet |

**Probe's reading of #263 and #266 (main):** both hold at the level stated, with limits from GPT-6.1 Sol (read-only; the author is Claude, so it is the independent vendor) that I confirmed in `packaging/macos_journey.py`:
- "Hub unreachable" cuts a relay in front of a running Hub; it does not stop the Hub process, so a Hub restart is not tested.
- "No new sign-in" was inferred from the next sync succeeding without `reconnect` set and the Hub's `last_used` changing. **Closed on macOS by #271 (steps 30 and 31):** the journey now compares the keychain key id and secret hash before and after, and counts sign-in codes. Still open on Windows.
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

### #271 post-merge, main `20151cb`, read 19 Nov 2026 (rows 4, 7 and 9, macOS)

Run read: https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44458636155 (the pull request run at `606e06e`, macOS 26.7.2 arm64, `Swangz-0.1.49-RC-UNSIGNED-macos-arm64.dmg`). I downloaded `evidence/journey.json` and read every step: **83 steps, 83 `pass`** (`SUMMARY.md` also says 83; the "68/68" quoted in the task was wrong). The merged head `5728b2d` came after this run. The push run on main `20151cb` (https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44462236684, success) also has 83 steps, all `pass`; I read its `journey.json` too, and steps 5, 6, 8, 24, 30, 31, 60–62, 78 and 79 are the same.

| Row | Result | What the journey shows (step numbers in `journey.json`) | Not shown |
|---|---|---|---|
| 4 / I, S address rule | PASS (macOS) | 3–5 fresh install: no device record, `status` exit 2, the window opens on sign-in with an empty address. 6–8 `http://hub.example.com` and `http://192.0.2.10:8787` refused (exit 1), and the Hub's sign-in code count stayed (0, 0) | Windows packaged app; the address surviving an upgrade is not asserted as its own step |
| 9 / U older build refused | PASS (macOS) | 60–61 after upgrade, installing 0.1.0 over 0.1.49, `status` and `sync` both exit 5 with "Swangz 0.1.49 is already in use". 62 the refused build changed nothing: same device record and keychain key | see the caveat below |
| 7 / R Hub down at app start | PASS (macOS) | 23 key in the keychain before the outage. 24 the window still opens with the Hub down. 25–27 sync fails and says so, no sync is claimed, the device record is kept, `status` still names the person | Windows packaged app |
| 7 / R reconnect: same key, no new code | PASS (macOS) | 28 Hub back on the same address. 29 next sync exit 0. 30 same keychain key (`dc95f2329682` before and after, secret hash `db1151cdf333` unchanged). 31 sign-in codes (count, newest id) = (1, 1) before and after. 33 the Hub records a new check-in | a Hub process restart: the journey cuts a relay in front of a running Hub |
| 7 / S key not in logs | PASS (macOS) | 32 the key is in no log or file in the app's data folder or this journey's evidence | offline never deleting a profile folder is not asserted |
| 7 / R revoked while away | PASS (macOS) | 73–75 sign in again. 76 the person disconnects the device at the Hub while the app cannot reach it. 77 Hub still away: sync exit 1, device record kept. 78 Hub back: next sync refused (exit 3) and says so. 79 Swangz removed itself, only `browser-profiles` kept (R-12, by design). 80 no Swangz item left in the keychain. 81 `status` says not signed in | Windows packaged app |

**Caveat (Chief; confirmed in `packaging/macos_journey.py` step 5b and `.github/workflows/build-macos.yml`, where the previous build is the version in the tree):** the "older" build in CI is the same source relabelled 0.1.0, not a genuine earlier release. The refusal is therefore real but tested against a relabelled build. If the workflow is later pointed at a genuine pre-#271 RC that lacks the refusal, steps 60–62 will fail, and they should: they are the test.

**Still open after #271:** Windows has none of these packaged-app steps (address rule, Hub down at start, revoked while away, same-key comparison); real sleep, Wi-Fi and VPN are OWNER checks.

### #272 and #275 post-merge, main `64f05cf` and `63e3251`, read 19 Nov 2026 (rows 5, 6 and 9)

Runs read: macOS push to main at `64f05cf` https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44467560442 (success; 103 steps, all `pass`) and at `63e3251` https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44470485409 (success; 104 steps, all `pass`; Hub checks and Inert browser profile checks on `63e3251` also success). The Hub checks run on `64f05cf` was cancelled when the next merge came, and the one on `63e3251` covers it. Windows does not run on push to main, so its evidence is the pull request run of #272's merged head `21b8287` https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44463794008 (success, `report.json` ok, 0.1.48, 38 steps); the diff from `21b8287` to `64f05cf` is two docs files only. For #275 the Windows PR run on `c00e4ec` (https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44466762644, success) predates #272, so it has 24 steps. I read every step of both `journey.json` files and both `report.json` files. Step numbers: the #272 rows and the matrix rows above use the run at `64f05cf` (103 steps); the #275 rows use the run at `63e3251` (104 steps, one more because #275 added step 66, so later numbers are one higher).

| PR | Claim | Result | What the runs show | Not shown |
|---|---|---|---|---|
| #272 | F-18 "off" is checked against the Hub's own storage | PASS (both) | macOS steps 43–45, Windows the same three lines: the record lookup answers 200; the request is recorded with no prompt and an empty reply; the prompt marker (random per run) is in no file of the fixture Hub's data folder (database, WAL, shared memory), in no stored body (compressed blobs checked, orphans too) and in the Hub log. Step 49: with storage on, the same scan finds the prompt, so the scan can see what it looks for. 48 and 50: the trust role reads it, the viewer gets `content=withheld` in the record and in the list | the Hub is a fixture on the runner. Only the prompt marker is searched, not every possible form of it (an encoded or truncated copy would not match). A provider's own copy of the prompt is by definition outside this test |
| #272 | the workspace folder survives the upgrade | PASS (both) | macOS step 62; Windows the `after the upgrade` line: same folder name, marker unchanged. Also kept after sign out (macOS 77) | Windows uninstall and the folder |
| #272 | a second person gets their own folder | PASS (both) | macOS steps 78–91: the admin adds person 2 and grants the tool, they sign in with their own code, open the tool, get a second folder beside the first, marked for person 2 and their device, Chrome starts on it, the Hub records the open under their name; the first person's folder is unchanged (89). Person 2 signs out and only `browser-profiles` is kept (91) | two people at once; one folder not being readable as the other (ACL or mode); a second OS user |
| #275 | the refusal message gives the full sign-out command | PASS (macOS) | macOS step 66: the text printed for exit 5 ends "To sign out, run: <path>/Swangz.app/Contents/MacOS/Swangz logout". Steps 64–65 still exit 5 for `status` and `sync`, and 67 shows the refused build changed nothing; 68–69 the newer build is back and signed in; 71–74 sign out works | |
| #275 | **the refusal dialog has a Sign out button that signs out** | **UNIT TESTS ONLY** | `tests/test_client_newest_app.py` mocks `offer_sign_out` (Yes then `logout` is called and the app says it was removed; No leaves the sign-in alone) | the runner never opens the dialog, so a real Tk dialog from the packaged app, a click on it, and the logout after a refusal are not run. Windows has no such dialog (its installer refuses the older build) |
| #275 | the first real release is 0.2.0 | **RULE AND UNIT TEST ONLY** | `core.check_newest_app` accepts 0.2.0 after a 0.1.400 floor and refuses 0.1.5 and 0.1.0 (a unit test); `docs/CLIENT.md` states the rule | the tree is still `0.1.0` (`swangz_client/__init__.py`), so nothing in CI builds or checks a 0.2.0 yet; raising MINOR is a manual step before the first real release |

**Result:** #272 VERIFIED on both runners, with the limits above. #275 VERIFIED for the terminal message and the exit-5 behaviour; the Sign out button and the 0.2.0 rule are not proven by a runner. A tester who ran a CI test build (0.1.<run>) and then a lower-numbered copy still has to use the command or the button to get out; the button is untested in the packaged app.

**Probe (no second opinion):** I did not ask GPT-6.1 Sol: the Windows and macOS checks above are read directly from the runs, and its earlier call on this repo timed out.

### #276, #277 and #281 post-merge, main `31c3d0e`, `dd9237b` and `35008b8`, read 19 Nov 2026 (rows 1, 4, 7 and 9)

Runs read. Windows does not run on push to main, so Windows evidence is the pull request run of each merged head: #276 https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44471096830 (head `cbc6b8e`, success, `report.json` ok, 0.1.52, **43 steps**) and #281 https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44475955390 (head `10cb307`, success, ok, 0.1.53, 43 steps). I checked that the source between each head and its main merge differs only by the other merged PRs (no Windows journey or client change in between for #281: `git diff 10cb307 35008b8 -- packaging swangz_client` touches `packaging/macos_journey.py` only). macOS push runs on main: https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44475096711 at `31c3d0e` (success), https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44477625072 at `dd9237b` (success; **112 steps, all `pass`**) and https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44480358944 at `35008b8` (success; 112 steps, all `pass`). I read the `journey.json` of the last two and the Windows `report.json` of both PR runs. The Hub checks runs on these three commits were cancelled by the next merge; the last full Hub checks success on main I read is `63e3251` (run 44470485377), and the run on `750253d` (44483276017) was still going when I wrote this.

| PR | Claim | Result | What the runs show | Not shown |
|---|---|---|---|---|
| #276 | Windows packaged-app parity | PASS (Windows runner) | report steps: 2 fresh install, no address, `status` exit 2, non-https exit 1 with no device saved and no sign-in code issued; 6 Hub down at app start: the Home window opens and the background process keeps running; 7 network interruption: sync exit 1, credentials kept, on return the same key SHA-256 and unchanged sign-in-code count; 31 revoked while away: offline sync exit 1, credential kept; 32 revoked on return: exit 3, data and stored key removed, `status` exit 2, only `browser-profiles` may remain (R-12), folder and marker kept (33) | **the key in no log or file after an outage is not a Windows step**; the Hub-down-at-start step does not say that no key was deleted or no code issued (step 7 covers the outage); a Hub process restart; the address across an upgrade |
| #277 | real Hub process restart, address across upgrade (macOS) | PASS (macOS) | steps 34 Hub process stopped (pid 4306 in the `dd9237b` run), 36 restarted as a new process on the same data, 37 next sync exit 0 with no new sign-in, 38 same keychain key id and secret hash, 39 sign-in codes (1, 1) unchanged, 40 the Hub records a new check-in. Step 70: the address is identical before and after the upgrade and the new build syncs to it | Windows has neither: its journey cuts a relay. A Hub restart on the real server is not run (fixture Hub) |
| #281 | Windows Run entry removed on revoke, sign out and uninstall | PASS (Windows runner) | report step 32 is now "startup-enabled revocation: sync exits 3, Run value, device data and stored key removed, status exits 2": start-at-sign-in was on when the device was revoked, and the Run value is gone on return. Step 29 sign out: start-at-sign-in value gone. Step 43 uninstall while running: Run value gone | after a reboot nothing was started (O-1, owner); that Windows removes the value on every path is shown for revoke, sign out and uninstall only |
| #281 | the same on macOS and Linux (fixed by #283, next section) | **UNIT TESTS ONLY** | macOS step 84 shows sign out removes the login item; steps 108–110 (revoked) check the data folder, the keychain and `status`, **not the login item**; `swangz_client/core.py` calls `shell.set_autostart(..., False)` on every removal path, so this is expected, but only unit tests show it for revoke | startup-removal on macOS and Linux after revocation: see #283 below |

**Result:** #276, #277 and #281 VERIFIED at the level stated. #281 is proven on Windows only. The key not appearing in any log after an outage is shown on macOS only. The #283 fix (Forge's `65cb7a81`) is in the next section.

**Probe (no second opinion):** I did not ask GPT-6.1 Sol on this docs update; every claim is read from the runs above.

### #283 post-merge, main `4d8f4eb`, read 19 Nov 2026 (row 7, start at login)

Runs read: Windows PR run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44481269393 (head `32d466b`, success, `report.json` ok, 0.1.54, 43 steps; `git diff 32d466b 4d8f4eb -- packaging swangz_client` is empty, so main has the same client and journey code); macOS push run on main https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44485214286 (`4d8f4eb`, success, 112 steps, all `pass`). The change is `swangz_client/core.py` and `tests/test_client.py` only: every removal path (revoke, rotation, CLI cleanup, sign out) now calls `shell.set_autostart(..., False)` on every system (Run value, LaunchAgent, `.desktop`), not only Windows, and a failure prints one line instead of nothing.

| Claim | Result | What the runs show | Not shown |
|---|---|---|---|
| Windows Run value removed on revoke, sign out, uninstall | PASS (runner), unchanged | report steps 29, 32, 43 read the same as in #281 | |
| Start at login removed on revocation or cleanup on macOS (LaunchAgent) and Linux (`.desktop`) | **UNIT TESTS ONLY** | `test_revoke_and_cleanup_remove_the_launch_agent_and_the_desktop_file` and `test_an_absent_file_is_already_off_and_a_failure_never_blocks_removal` in `tests/test_client.py` (part of the full suite that passed in the Hub checks run on `31a60fe`, below) | **the macOS journey was not changed:** revoke steps 108–110 check the data folder, the keychain and `status`, not the login item, and the person signs in again for that check (steps 102–104) without turning start at login on, so there is nothing for revoke to remove. Step 84 (sign out removes the login item) is the only macOS runner evidence. Linux has no runner at all |
| A refused removal prints one line on Windows | UNIT TEST ONLY | the test asserts exactly one line naming the error type and the retry command, with no path or value | the Windows journey never makes the registry refuse |

**Fix task for Forge/Anvil:** in `packaging/macos_journey.py`, turn start at login on before the revocation check (after step 104) and assert the LaunchAgent plist is gone after step 107, next to steps 108–110. The Windows journey already does this (report step 32).

**Fix task closed by #286 (macOS, row 7):** run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44499097781 (PR head `85f5f13`, macOS journey success, 114 steps, all `pass`; read from `evidence/journey.json`). Step 105 turns start at login on after the person signs in again for the revocation check (the LaunchAgent plist exists); after the revoked sync (108, exit 3), step 110 "revoked: the login item is removed" passes, next to 109 (only `browser-profiles` kept), 111 (keychain) and 112 (`status` exit 2). So start-at-login removal on revoke is now **PASS (runner) on macOS and Windows**; **Linux stays unit-test only** (no Linux runner journey), and **no runner makes the Windows registry refuse** (the one-line message is a unit test only).

**Hub checks on main `31a60fe`, run 44488549742 (read 19 Nov 2026):** success. python 3.10 and 3.12 each ran 1440 tests, OK (skipped=20); app-window ran 16 tests, OK; the browser job passed all 34 steps. Earlier Hub checks runs on main were cancelled by the next merge; it is the first full success I have read since `63e3251` (run 44470485377).

**Probe (no second opinion):** I did not ask GPT-6.1 Sol; the claims are read from the runs and the diff.

### #286 and #287 post-merge, main `5005b37`, read 19 Nov 2026 (rows 1, 2, 4 and 7)

Merges: #286 `939d585`, #287 `13e22b2`, then #288 `5005b37` (a docs file only, `docs/RELEASE-STATUS-TEMPLATE.md`). Runs read:
- **macOS, push to main at `13e22b2`**, https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44506182423, success, `journey.json` **114 steps, all `pass`**. This is the merged state of #286 and #287 together. (The run at `939d585`, 44504601068, also succeeded; I did not read it.) The macOS workflow did not run at `5005b37` because only a docs file changed.
- **Windows, pull request run of #287's merged head `d023e6c`**, https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44500938493, success, `report.json` ok, 0.1.58, **47 steps**. Windows does not run on push to main. Between `d023e6c` and `13e22b2` the only changed file under `packaging/`, `swangz_client/` or `gateway/` is `packaging/macos_journey.py` (#286), so the Windows code on main is the code that ran. An earlier run of #287 at `ff0314a` (44499390232) failed; `d023e6c` fixed the restarted Hub's time zone search path, and I did not read the failed run.
- **Hub checks on `13e22b2`**, https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44506182434, success: python 3.10 and 3.12 each 1444 tests OK (skipped=20), app-window 16 tests OK, browser all steps pass. The run on `5005b37` (44529233222) was still going when I wrote this (app-window success); a docs-only change.

| PR | Claim | Result | What the runs show | Not shown |
|---|---|---|---|---|
| #286 | revoke removes the start-at-login LaunchAgent (macOS) | PASS (macOS runner) | steps 102–104 sign in again; **105 start at login turned on before the revocation**; 106 device disconnected at the Hub while away; 107 offline sync exit 1; 108 next sync exit 3; 109 only `browser-profiles` kept; **110 "revoked: the login item is removed"**; 111 keychain empty; 112 `status` exit 2 | Linux (unit tests only) |
| #287 | the device key is in no log or file after an outage (Windows) | PASS (Windows runner) | step 7 outage (sync exit 1, credentials kept, same key SHA-256, unchanged code count); **step 8** a search of the app's data folder and the journey evidence (the Hub fixture log included) finds no copy of the key | the search runs once, after the outage and before the Hub restart; it skips the key's own file (`device.key`, `device.key.next`); on the runner the key is in Credential Manager, so there is no such file |
| #287 | a real Hub process restart (Windows) | PASS (Windows runner) | **step 9** sync exits 1 while the Hub is stopped, a new Hub process (pid 6344, a different process from the journey) serves the same port and data, the next sync checks in with the same key SHA-256, no `reconnect` and no new sign-in code; the journey's own Hub then returns and the next sync checks in again | a fixture Hub, not the production service; the restart is a hard stop (`TerminateProcess`), not a service manager |
| #287 | the Hub address is kept across an upgrade (Windows) | PASS (Windows runner) | step 31: `http://127.0.0.1:50472` before and after the upgrade, and the new build syncs to it | the address in the packaged app is a local fixture, not an https production address (OWNER) |

**Result:** #286 and #287 VERIFIED at the level stated. Rows 4 and 7 no longer have a Windows gap for the key in logs, the Hub process restart, or the address across an upgrade. `docs/RELEASE-STATUS-TEMPLATE.md` (#288) still lists these as open in its baseline; I updated its rows 1, 2, 4 and 7 to match.

**Probe (no second opinion):** I did not ask GPT-6.1 Sol on this docs update; every claim is read from the runs above.

### #292 and #293 post-merge, main `14b753c` (#292 `809dd9e`, #293 `14b753c`), read 19 Nov 2026 (rows 3, 5, 6, 8 and 9)

Both merged. The runs below are from each PR's head, read before the merge. #293 merged at `979de18`, which differs from the head I read (`8703249`) by three files only, all Hub-side: a comment in `gateway/device_open.py`, one more audit line in `gateway/managed.py` ("device reported its browser policy is in force again", written when a failing device reports passing) and one test in `tests/test_policy_integrity.py`. Nothing under `packaging/`, `swangz_client/` or `.github/` changed, so the macOS journey that ran is the journey on main. I did not read a macOS run at `979de18` or `14b753c`.

**#292 (`feature/pkg-enrol-negative`, head `282a248`, Windows)**: Windows run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44552262351, success, `report.json` ok, 0.1.62, **52 steps**. All PR checks on that head are green (python 3.10 and 3.12, browser, app-window, macos, Windows installer).

| Claim | Result | What the report shows | Not shown |
|---|---|---|---|
| A wrong code approves nothing and the program keeps waiting | PASS (Windows runner) | step 4: while the installed program's `login` waits, `/device` answers "That code isn't right" with no approve form, and the waiting code stays `pending` | the extra POST that answers 400 carries a made-up CSRF token, so that 400 alone would also come from the CSRF check; the proof is the "isn't right" page and the unchanged waiting code |
| An expired code ends the login | PASS (Windows runner) | step 5: `login` exits 1 saying it expired, no `device.json`, no key issued, `/device` refuses that code | the expiry is made by setting `expires` in the fixture Hub's database, not by waiting the real time |
| A used code is not reusable | PASS (Windows runner) | step 7: `/device` refuses the used code; a second `login` on the signed-in program exits 1, asks for no new code, keeps the same device and key | the page cannot tell "used" from "expired" (one message: "already used or has expired") |
| A grant made while the app is closed is offered after it starts; one taken away is no longer offered | PASS (Windows runner) | steps 32 and 33: the app's saved offer (`manifest.json`) shows `perplexity` only after `--background` starts again, and drops it only after the next start, while closed it stays as it was | the check that nothing changes while closed is immediate, not over a period; the 15-minute timer cannot explain it (the wait is 60 s and the app syncs 500 ms after start); macOS is not covered; the app is started with `--background` and terminated, not shown as a window |

**#293 (`feature/mac-policy-tamper`, head `8703249`, macOS)**: macOS run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44553974716, success, `journey.json` **134 steps, all `pass`** (was 114). All PR checks on that head are green (python 3.10 and 3.12, browser, app-window, macos, Windows installer, inert profiles).

| Claim | Result | What the journey shows | Not shown |
|---|---|---|---|
| Machine-policy tamper is detected on a company device (macOS) | PASS (macOS runner) | steps 102 to 121: the pack is installed device-wide under `/Library/Managed Preferences/com.google.Chrome.plist`, owned by root; the Hub pins its hash in `enforce`. Intact: sync records `policy_ok 1` and the baseline hash, Open starts Chrome and the Hub records 1 open. Default-deny removed: Open exits 1 with the policy message and 0 opens, sync records `policy_ok 0` and a different hash, the audit log gains one line. Valid but not the pinned pack: Open refused and 0 opens, sync records `policy_ok 1` with a hash that is not the baseline. Restored: Open works again at once. Removed: Open refused, `policy_ok 0`, no hash | the pack is made by `prepare.py` with CI placeholders; the journey proves the app's hash check and the Hub's records, not that Chrome itself enforces the pack; the refusals are the app's own, so the new Hub-side check on `/device/open` is proved by the unit tests only; Windows: see the #296 section |
| The rows after it still pass | PASS | steps 122 to 134 repeat the revoke journey (login item removed, step 130) | |
| The `.app` builds reproducibly; the DMG does not | PASS for the app, **FAIL for the DMG** (recorded, not a build failure) | `evidence/reproducible-macos.json`: both `Swangz.app` trees have 420 entries and the same tree SHA-256 `afc3855e…`; the DMGs differ (`0f89c296…` and `625cde84…`, 83 bytes apart) | same runner, same run; the DMG differs from the disk image tool, a cause I did not investigate |
| `bump_version.py` | not run in CI against a real bump | unit tests (`test_the_real_tree_has_each_value_once`, `test_bump_changes_the_app_and_latest_but_not_the_minimum`, `test_minimum_only_when_asked_and_refusals`) passed in python 3.10 and 3.12 | the tree is still 0.1.0 (`__version__`, `CLIENT_LATEST` and `CLIENT_MINIMUM`); no version has been bumped |

Code read on #293: `gateway/device_open.py` now records the `policy` result an app sends with `/device/open` before it decides, and `swangz_client/core.py` sends it. This is the same unverified claim the heartbeat already carries (`managed.record_policy_report`), so a hostile app could report `ok` and the baseline hash; for Sentinel: the Hub cannot tell a true report from a copied one, as before, and the machine policy is the thing that actually stops a tampered browser.

**Result:** #292 VERIFIED at `282a248` (merged unchanged as `809dd9e`); #293 VERIFIED at `8703249`, Sentinel APPROVED the merged head `979de18`. The Hub-side delta between the two is not covered by a journey run I read; it is covered by the Hub unit tests only.

**Probe (no second opinion):** I did not ask GPT-6.1 Sol on these two; every claim is read from the runs and the diffs above.

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
### #296 Windows machine-policy tamper, head `0ef0676`, read 19 Nov 2026 (rows 5 and 6; read before merge)

Windows run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44572431807 (pull_request, success, version 0.1.67), evidence artifact `Swangz-Windows-installer-evidence`: `report.json` **70 steps, all pass** (was 52), plus `policy-tamper.json`. The head Chief quoted (`34b5a1e`) is not the PR's head (`0ef0676`); I read `0ef0676`. At the last read python 3.10 and 3.12, app-window, macos and the Windows installer were green; browser was still running.

| Claim | Result | What the journey shows | Not shown |
|---|---|---|---|
| Machine-policy tamper is detected on a company device (Windows) | PASS (Windows runner) | steps 52 to 69 (18 lines beginning `policy`; Chief's "17" plus the last "runner restored" check): the pack is written under `HKLM\Software\Policies\Google\Chrome` (64-bit view) the way Chrome's ADMX would, and the app's own reader returns the baseline (`1fdfbd3c…`, no problems). Intact: sync `policy_ok 1` and baseline hash, Open starts Chrome, 1 open. Default-deny removed: Open exit 1 with the policy message and 0 opens, sync `policy_ok 0` (`ea0eba5d…`), audit log +1. Valid but not the pinned pack: Open refused, 0 opens, sync `policy_ok 1` with `7e4129a6…`. Restored: Open works at once, baseline hash. Removed: Open refused, `policy_ok 0`, empty hash. Last step: the registry key is gone. `policy-tamper.json`: 10 case records, `cleanup_errors: []` | the pack uses CI placeholders; the journey proves the app's hash check and the Hub's records, not that Chrome itself enforces the registry policy; the pack is written directly to the registry as an administrator would (Group Policy and MDM delivery are not covered); "key gone" is the journey's own `present()` call, I did not inspect the runner afterwards; the Hub's `policy_ok` is the app's own claim |
| Windows and macOS readers agree | PASS | the baseline and both tampered hashes equal the macOS run's (`1fdfbd3c…`, `ea0eba5d…`, `7e4129a6…`) | |
| Runner-only guard | PASS (read in code, not run) | `packaging/windows/policy.py` and `packaging/macos_policy.py` exit unless `GITHUB_ACTIONS` is `true` and `RUNNER_ENVIRONMENT` is `github-hosted`, so the journey cannot edit a person's own machine policy | not exercised on a non-runner |

GPT-6.1 Sol read the diff and found no defect in the five cases, only three false-pass risks, none of which makes a claim above wrong: (1) `refused()` checks exit code, message and Hub opens but not that no Chrome process exists, so a regression that started Chrome and then refused would pass; (2) `synced()` does not require the Hub's `policy_reported` to advance, so values left by the preceding Open's refresh could satisfy it (the Hub value is still the one the case asserts); (3) the journey now ends as the first person, so uninstall no longer exercises keeping a different person's folder. Probe agrees with all three as hardening, not blockers; they are for Forge.

**Result:** #296 VERIFIED at `0ef0676` for the Windows runner (browser job pending at the last read). Rows 5 and 6 stay PARTIAL: Chrome's own enforcement of the pack, Group Policy or MDM delivery, and a real company machine are OPEN or OWNER.

A missing line means NOT TESTED.

## Not covered here

Linux and phones (G7 and G8 of the acceptance gate), real provider terms, load, and anything that needs the production server.
