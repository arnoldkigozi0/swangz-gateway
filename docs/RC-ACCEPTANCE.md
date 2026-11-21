# RC acceptance matrix: deliverables 1 to 10 against the new unsigned RC

Status: **draft, written 21 Nov 2026 against `main` `13966ba` (code identical to `4c451fe`).** The new RC tag has not been
given to Probe yet, so every "New RC" cell below says **Not run: awaiting RC tag**. Nothing here is production-ready:
every build is `RC — UNSIGNED — INTERNAL TEST ONLY`, and no row is closed by a real device.

Companion to `docs/RELEASE-EVIDENCE.md` (the dated record, how each row was proven and what each run does not show),
`docs/RELEASE-OWNER-CHECKLIST.md` and `docs/ARNOLD-ONLY.md` (what only Arnold can do). The deliverables are numbered as in
`/home/inquiline/swangz-team/mission/release-sprint-17nov.md`.

## 1. What changed since the old RC, and what that means for re-running

Old RC: pre-release `rc-unsigned-20261120-ec02d96` (target `ec02d96`; Windows 0.1.71, macOS 0.1.89).
New RC: cut by Anvil from `4c451fe` or later. Main's tree today is `13966ba` (a docs-only merge on top of `4c451fe`).

Changes between `ec02d96` and `13966ba` that touch what the journeys exercise (23 code and test files, read from `git diff`):

| Area | Change | PR | Why it forces a re-run |
|---|---|---|---|
| Packaged app journeys | Windows wrong-code step posts a real CSRF token | #302 | new journey step, not in the old RC's run |
| Packaged app journeys | Row 5 level B: two installed copies at once, each with its own data folder, plus disconnect of one while the other carries on (Windows steps 70 to 82, macOS 120 to 132) | #303 | new steps, not in the old RC's run |
| Hub, schema | **v29**: four new `tools` columns (`info_url`, `modes`, `oauth_hosts`, `last_verified`), defaults empty | #304 | the journeys start a Hub from the tree under test and migrate it; the RC's Hub changes |
| Hub, catalogue and `/go/` | settle app URLs and hosts at start-up, `inside_other_tool` refusal (Seedance inside Higgsfield AI), Adobe sign-in hosts, gate-host ownership rules | #305 to #315, #317, #318 | changes what Open and the extension gate do |
| Company Chrome pack | `ims-na1.adobelogin.com` allowed as an exact host; typed-flake fix in the policy harness | #316, #317 | the pack's hash changes, and row 5 policy steps pin that hash |
| Client app (`swangz_client/`) | **none** since `ec02d96` | | the installed program's code is unchanged; its version label still comes from the CI run counter |
| Workflows (`.github/`) | **none** since `ec02d96` | | `build-app.yml` and `checks.yml` unchanged |

Version in the tree is still `0.1.0` (`swangz_client/__init__.py`); the shipped number is `0.1.<run number>`.

## 2. Which rows already have evidence, which must be re-run on the new tag

"Latest on main's tree" means a run whose tree is main after the last journey change (`046f6e5`, #303 merged); Hub-side
changes after it are not in those runs. A pull-request run tests GitHub's merge of the branch with main, which is why
the Windows PR run on `fb089eb` already contains #302's real-token step.

| # | Deliverable | Evidence in the old RC (`ec02d96`) | Latest journey run (tree `046f6e5`) | Must re-run on the new tag? |
|---|---|---|---|---|
| 1 | Windows installer | Windows run [44724106592](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44724106592): PASS, 71 steps | Windows PR run [44740743244](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44740743244): ok, **84 steps**, `Swangz-Setup-0.1.74-UNSIGNED.exe` | **Yes.** The artifact to ship is new; the journey and checksums must be of the shipped file |
| 2 | macOS app and DMG | macOS run [44724112936](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44724112936): PASS, 152 steps | macOS push run [44759014007](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44759014007) on `046f6e5`: PASS, **168 steps**, `Swangz-0.1.94-RC-UNSIGNED-macos-arm64.dmg` | **Yes**, same reason |
| 3 | Enrolment and sign-in | PASS on both; Windows used a made-up CSRF token | PASS on both; Windows now posts a real token (report step 4) | **Yes** (journey is the evidence); no new gap |
| 4 | Server address, no secrets | PASS on both; scans 0 hits | scans 0 hits: macOS 777 files, DMG 386 files, Windows 13 files, 1,318 inner entries | **Yes**: scan the new artifacts, a scan of an older build proves nothing about the new one |
| 5 | Company browser workspace | PARTIAL: separate folders for two people on one device; Hub and fake-agent level A (#298) | **level B now PASS on both runners** (see §3); policy tamper steps PASS | **Yes**: the pack changed, so the policy steps run against a new baseline hash |
| 6 | Staff reporting, admin functions | PARTIAL | unchanged; Hub checks on `4c451fe`: 1533 tests, browser job green | **Yes** for the packaged F-18 and grant steps; Hub tests re-run on the new tag's commit |
| 7 | Reconnect after restart or outage | PASS on both | PASS on both (same steps) | **Yes** |
| 8 | Versioned artifacts, checksums, reproducibility | PARTIAL: DMG not reproducible | Windows program and installer identical; macOS `.app` identical, **DMG still not identical** | **Yes**: checksums and SBOM of the new files |
| 9 | Updates off until signing | PARTIAL | unchanged; tree still `0.1.0` | **Yes** (self-check says updates off); `0.2.0` is still never built |
| 10 | Evidence from the runs | PASS for what runners can do | same | **Yes**: the evidence zips must be the new RC's |

The Hub checks on the RC commit are a separate re-run: the 1533-test suite and the browser job must be green on the exact
commit the RC is cut from (see §4).

## 3. What the latest journeys show that the old RC's did not

Read by Probe from the downloaded artifacts of the two runs above (21 Nov).

| Claim | Result | What the journey shows | Not shown |
|---|---|---|---|
| Windows wrong-code refusal is not a CSRF refusal | PASS (Windows runner) | report step 4: the token is fetched from the waiting code's own `/device` form and compared with the Hub's own token for that session; the POST with it answers 400 with the "Open the link from your device again and retry" text and approves nothing | the expiry steps still set `expires` in the fixture database instead of waiting |
| Two people signed in at once, two app copies, one machine (row 5 level B) | PASS (both runners) | each copy has its own data folder; two device ids, two key ids, two stored keys, each found under its own key id and different (compared in memory, never printed); two Chrome windows on two different folders in two different data folders; the first person's folder is not in the second copy's data folder; the Hub records each open under its own person; the admin's Devices list shows both; with both windows closed neither data folder holds the other's key; the admin disconnects one, that copy's next sync is refused and removes only its own data, the other stays signed in with the same key and folder (Windows steps 70 to 82, macOS 120 to 132) | both copies run under **one** OS user and one runner; a second OS user is OWNER (O-3). Two real machines and a real provider sign-in (level C) are OWNER (O-7) |
| macOS DMG reproducibility | **FAIL (recorded, not a build failure)** | `reproducible-macos.json`: `app.identical true`, `dmg.identical false` | the cause of the differing bytes is not explained |

## 4. Matrix on the new RC tag

Fill this table when Anvil gives the tag. A cell may say PASS only with a run URL for that exact commit and a SHA-256 read
from the uploaded sidecar, and **Not run** otherwise. The old RC's results do not carry over.

RC tag: **Not run: awaiting RC tag from Anvil.** Release commit: pending. Hub checks run: pending. Windows run: pending.
macOS run: pending.

| # | Deliverable | Runner result on the new tag | Run URL | Artifact SHA-256 (first 12) | First failure | Blockers that stay |
|---|---|---|---|---|---|---|
| 1 | Windows installer | **Not run: awaiting RC tag** | | | | SmartScreen on a real PC, reboot with start on login, install-folder ACL not listed, second Windows user (O-1, O-3); Authenticode signing (O-6) |
| 2 | macOS app and DMG | **Not run: awaiting RC tag** | | | | real Gatekeeper first-open and Keychain prompt (O-2); Developer ID and notarization (O-6); the DMG is not reproducible |
| 3 | Enrolment and sign-in | **Not run: awaiting RC tag** | | | | Google sign-in on the first-party address (O-5); expiry forced through the database, not waited |
| 4 | Server address, no secrets | **Not run: awaiting RC tag** | | | | real https address, domain, TLS (O-5); runners use `127.0.0.1`; the setup `.exe` is scanned as raw bytes |
| 5 | Company browser workspace | **Not run: awaiting RC tag** | | | | two real machines and a real provider sign-in (level C, O-7); a second OS user (O-3); Chrome's own enforcement of the pack and Group Policy or MDM delivery on a company machine |
| 6 | Staff reporting, admin functions | **Not run: awaiting RC tag** | | | | the packaged app shows no staff reports or admin screens (Hub tests and the browser job cover them); admin judgement inside the shell is OWNER |
| 7 | Reconnect after restart or outage | **Not run: awaiting RC tag** | | | | sleep, Wi-Fi and VPN on a real device (O-4) |
| 8 | Versioned artifacts, checksums, reproducible builds, notes | **Not run: awaiting RC tag** | | | | macOS DMG not reproducible; version is `0.1.<run>` not a release number; SBOM hash not compared with the installed program |
| 9 | Updates off until signing | **Not run: awaiting RC tag** | | | | `0.2.0` never built or upgraded to; "older build" is the same source relabelled; refusal dialog's Sign out button unit-tested only; enabling updates needs a signing key and Arnold (O-6) |
| 10 | Evidence from the runs | **Not run: awaiting RC tag** | | | | no combined workflow; Windows workflow does not run on pushes to main (started by hand); O-1 to O-7 have no results |

## 5. Hub-side checks on the RC commit

| Check | Latest on `4c451fe` (read 21 Nov) | New RC commit |
|---|---|---|
| Hub checks, run [44854832588](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44854832588) | python 3.10 and 3.12: **1533 tests each, OK (skipped=20)**; app-window 16 tests OK; browser job success | Not run: awaiting RC tag (if the tag is `4c451fe` itself, this row stands) |
| Chrome policy pack checks, run [44854832597](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44854832597) | success (job names and result only; Probe did not read its log) | Not run: awaiting RC tag |
| Hub checks on `13966ba` (this docs-only merge), run [44867206566](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/44867206566) | was in progress when written | |

## 6. Honest blockers for the Saturday 20:00 status (all of them, whatever the new run says)

1. **No signing.** Windows Authenticode and Apple Developer ID plus notarization are not in place (O-6). Gatekeeper refuses
   the macOS RC as documented, and SmartScreen warns. Updates stay off.
2. **No real-device acceptance.** Nobody has run O-1 to O-4 on a real Windows PC and a real Mac, including a second OS user,
   reboot, sleep, Wi-Fi and VPN.
3. **No production server.** Address, domain, TLS, Google OAuth and company identity are Arnold's (O-5); every runner test
   uses `127.0.0.1`.
4. **No real provider sign-in persisting in the company browser, no provider-seat inventory** (O-7); row 5 level C is open.
5. **Chrome policy enforcement is not proven by Chrome.** The runners write the pack where Chrome reads policy and the app
   reads it back; Chrome's own enforcement and GPO or MDM delivery on a company machine are not shown.
6. **The tree is `0.1.0`.** A real `0.2.0` has never been built, upgraded to or downgrade-refused; CI's "older" build is the
   same source relabelled.
7. **The macOS DMG is not reproducible** (the `.app` is). The cause is not explained.
8. **Scope of "PASS".** Every PASS is a GitHub-hosted runner with test data, one OS user, no human at a desktop. It is not a
   company device and not a staff pilot (G12 of `RELEASE-ACCEPTANCE-GATE.md`).
9. **Not covered:** Linux packaged app and phones (G7, G8). A PWA test on a real Android phone and iPhone is still to be done.

Final verdict for the status post, until the above changes: **NOT READY FOR PRODUCTION. Unsigned release candidate for
internal testing only.** Whether it is ready for a staff pilot is Arnold's call once O-1 to O-5 have results.

## 7. How this file is updated

When Anvil gives the tag: read the release's `SHA256SUMS`, the Hub checks run, and both journey artifacts (`journey.json`,
`report.json`, scans, SBOMs, reproducibility files), fill §4 and §5, then move any row whose new run fails to FAIL with its
first failure. Rows are written as in `RELEASE-EVIDENCE.md`: `Deliverable N: PASS | FAIL | BLOCKED | NOT TESTED | OWNER, commit,
artifact SHA-256, run URL, first failure`. No secret, key, cookie or password goes in this file.
