# Release evidence matrix: Windows and macOS apps (sprint 17 to 21 Nov 2026)

Status: **draft. Nothing in this file is a pass.** Written by Probe on 17 Nov 2026 against `main` `8ad23d1`; the
candidate-PR rows below were updated at 23:45 EAT.
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
| Windows installer (Start menu, desktop shortcut option, uninstaller) | **draft PR #243 at 43c92da, not merged.** `windows-latest` job (Inno Setup pinned by SHA-256, build, then the journey) passed: silent install without administrator rights, launch, enrol against a CI Hub (key in the keychain), restart still signed in, Hub unreachable then back with no new sign-in, install over an existing install, silent uninstall (device disconnected at the Hub, credentials, program, shortcuts, Run value and Apps & features entry gone). Run https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44170698656/job/134348675999 ; installer `Swangz-Setup-0.1.0-UNSIGNED.exe`, SHA-256 `3e91b88131e947f2d57740eead32c89b294fa1d83986576d6309d1bd8899b95d`. All PR checks green. **Not covered:** uninstall while the Hub is unreachable (the uninstaller runs `logout`, which cannot disconnect the device at the Hub then), an upgrade from a different earlier build, a second Windows user, SmartScreen | deliverable 1 |
| macOS DMG, signing and Gatekeeper document | **draft PR #244 (a57f150), not merged.** Its `macos-latest` journey job **FAILED** at `app finishes signing in`: install, first launch, sign-in code and approval passed, then the app said `This version of Swangz (0.0.9) is too old. Please update it.` (exit 1). The built version string is below the Hub's minimum client version. Run: https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44166501723/job/134333865171. Defect for Anvil. `docs/MACOS-SIGNING.md` is in the PR and unread by Probe | deliverable 2 |
| Updates | disabled by design (`ENABLED=False`, no pinned release key) | `packaging/README.md` |
| Managed workspace | in PR #204, **not merged**. Demo record is PR #236, steps 1 to 4 on Linux, headless | `docs/W-DEMO-RESULT-20261114.md` |
| Prompt and reply privacy exposure (F-18, `store_bodies`) | open, release blocker; decision doc PR #160 | sprint brief |
| Machine-policy integrity (W6 / R-8) | in #204; proven only on Linux Chrome CI (`w6-step5`) | `.github/workflows/w6-step5.yml` |

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
| I | silent install exits 0; Start-menu entry present; desktop shortcut present only when chosen; uninstaller listed in Add or remove programs | no installer, only the unsigned archive | SmartScreen prompt on a real PC; how the shortcut looks |
| A | the installed binary completes the smoke login | smoke runs on the archive, not an installed copy | |
| R | kill and relaunch the installed app, still signed in | not tested | start on login after a real reboot and sign-in (`swangz autostart on` writes the entry; a runner can only check the entry exists) |
| S | install folder ACL listed; no secret inside the installer; log shows no Defender or policy command | not tested | |
| U | see row 9 | | |
| X | silent uninstall removes folder, shortcuts, startup entry and uninstaller entry; leftover list matches the doc | not tested | |

### 2. macOS `.app` and DMG, with signing and Gatekeeper documented

| Kind | Runner evidence (M) | TODAY | OWNER-only |
|---|---|---|---|
| I | mount the DMG, copy the `.app`, record `codesign -dv` and `spctl -a -vv` output as it is (unsigned is expected to be rejected; the document must say so) | no DMG, no signing document; the zip holds a `.app` | Developer ID signing, notarization, `spctl` accepted, the first-open Gatekeeper dialog on a real Mac |
| A | smoke login from the copied `.app` | not tested | Keychain prompt on a real Mac |
| R | kill and relaunch | not tested | login item after a real reboot |
| S | no `spctl --master-disable` or quarantine-strip step in any job or document; `.app` layout intact | not tested | |
| U | see row 9 | | |
| X | delete the `.app`; leftovers (login item, data folder) listed against the doc | not tested | |

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
| S | scan of the built binary, archive and installer for keys, tokens, `.env`, company hostnames and common secret patterns: zero hits; a non-https address is refused except 127.0.0.1 (the rule is in `swangz_client/core.py`: https only, except `localhost`, `127.0.0.1` and `::1`; checked in code 18 Nov, the packaged-app test is still to write) | no scan exists | the production address itself |
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
| R | (a) kill and relaunch: still signed in; (b) stop the CI Hub, wait past two heartbeats, restart it: the app is signed in again with no new code; (c) Hub down at app start: a clear message, no key deleted, no second code issued; (d) revoked while the Hub was away: refused on return, local data kept as documented | client logic and unit tests only; **no packaged-app run** | real laptop sleep, Wi-Fi switch, VPN (O-4 below) |
| S | after an outage no log line exposes the key; offline never deletes a profile folder | not tested | |
| U | restart after upgrade still signed in | not tested | |

### 8. Versioned artifacts, checksums, reproducible builds, release notes

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| I | the name carries the version and `UNSIGNED`; the `sha256` file verifies on a clean runner | sidecar checksums exist | |
| S | two builds of the same commit give the same SHA-256, or the differing bytes are listed and explained (timestamps, signatures); an SBOM is attached; pinned tool versions are listed | no reproducibility check, no SBOM | the approver reads the notes; they may not say production-ready |

### 9. Controlled update architecture, updates disabled until signing

| Kind | Runner evidence (W and M) | TODAY | OWNER-only |
|---|---|---|---|
| S | `update status` says updates are off; with no pinned key an offered update is refused; a tampered or older package is refused | the updater exists and is disabled; its unit tests use `tests/fixtures/test_release_rsa4096.json` | enabling updates needs a signing key and Arnold's decision |
| U | build N and N+1 from two commits; install N, enrol, create a profile marker, install N+1 over it: still signed in, marker kept, version changed; then N over N+1 is refused or documented as unsupported | no installer to upgrade through | |
| X | removing N+1 after an upgrade leaves what the doc lists | not tested | |

### 10. Evidence from install, auth, restart, security, upgrade and uninstall

One `release-evidence` workflow runs rows 1 to 9 on both runners and uploads logs, a JSON report and the checksums. It
writes a table keyed by commit and SHA-256. Today: **none exists**. Every OWNER cell above is recorded by whoever ran it.

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
