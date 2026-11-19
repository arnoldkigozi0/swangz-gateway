# Swangz app release status: template for Saturday 21 Nov 2026, 20:00

**RC — UNSIGNED — INTERNAL TEST ONLY.** This status describes a release candidate for internal testing. It is not a
production release. Never describe it as ready for production. Arnold approves any distribution beyond internal
testing.

Chief copies this file into the status message and fills in every `<...>`. Results come from
[RELEASE-EVIDENCE.md](RELEASE-EVIDENCE.md) on main and from the release runs below. Nothing else counts. A row
with no run read by Probe stays as the evidence file says (PASS, PARTIAL, NOT TESTED or OWNER).

## 1. What the workflows publish today (read from main, 19 Nov 2026)

Neither workflow creates a GitHub release, a tag or a download page. Both have `permissions: contents: read`
and upload **Actions artifacts only**. These are kept for 14 days.

| | Windows: `.github/workflows/release-windows.yml` | macOS: `.github/workflows/build-macos.yml` |
|---|---|---|
| Runs on | pull requests touching `packaging/`, `swangz_client/` or the workflow; `workflow_dispatch`. **Not** on push to main, **not** on tags | pull requests (same paths plus `gateway/enroll.py`); push to main **only when those paths change**; `workflow_dispatch`. **Not** on tags |
| Version | tree version with PATCH raised by the run number (`0.1.0` becomes `0.1.<run>`) | the same scheme, with its own run number. So the Windows and macOS numbers differ |
| RC artifact | `Swangz-Windows-installer-RC-UNSIGNED` | `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` |
| Files in it | `Swangz-Setup-<v>-UNSIGNED.exe`, `Swangz-Setup-<v>-UNSIGNED.exe.sha256`, `RELEASE-LABEL.txt` (`RC — UNSIGNED — INTERNAL TEST ONLY`), `Swangz-<v>.cdx.json` | in a `dist/` folder: `Swangz-<v>-RC-UNSIGNED-macos-arm64.dmg`, `.dmg.sha256`, `SHA256SUMS`, `Swangz-<v>-macos.cdx.json`; beside it `evidence/` (journey log, `journey.json`, screenshots) |
| Evidence artifact | `Swangz-Windows-installer-evidence` (`report.json`, installer and uninstaller logs, `reproducible-program.json`, `reproducible-installer.json`) | inside the RC artifact (`evidence/`) |
| Checks before upload | acceptance run on the installer, secret scan, CycloneDX validation; the reproducibility check runs after the upload | journey, `shasum -c`, secret scan, CycloneDX validation |

## 2. Release commit and runs

- **Release commit (main):** `<full sha>`
- **Windows run:** `<run URL>` (`workflow_dispatch` on main), conclusion `<success/failure>`, `report.json` `ok: <true/false>`, `<n>` steps
- **macOS run:** `<run URL>`, conclusion `<...>`, `journey.json` `<n>` steps, `<n>` `pass`
- **Hub checks on the same commit:** `<run URL>`: python 3.10 `<...>`, python 3.12 `<...>`, browser `<...>`, app-window `<...>`
- **GitHub pre-release:** `<release URL>` (tag `<tag>`), marked pre-release, titled with the RC label

## 3. Artifacts and SHA-256

Copy each hash from the run's sidecar file: `Swangz-Setup-<v>-UNSIGNED.exe.sha256` for Windows, and `SHA256SUMS`
or `.dmg.sha256` for macOS. Then recompute it from the downloaded file (`sha256sum`) and tick the last column only
if the two are equal. The SBOM and label files have no sidecar, so their hashes are computed after download. Say
so in the row.

| File | Artifact | Size (bytes) | SHA-256 (sidecar) | Recomputed equal |
|---|---|---|---|---|
| `Swangz-Setup-<v>-UNSIGNED.exe` | `Swangz-Windows-installer-RC-UNSIGNED` | `<...>` | `<...>` | `<yes/no>` |
| `Swangz-<v>.cdx.json` | `Swangz-Windows-installer-RC-UNSIGNED` | `<...>` | computed after download: `<...>` | n/a |
| `RELEASE-LABEL.txt` | `Swangz-Windows-installer-RC-UNSIGNED` | `<...>` | computed after download: `<...>` | n/a |
| `Swangz-<v>-RC-UNSIGNED-macos-arm64.dmg` | `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` | `<...>` | `<...>` | `<yes/no>` |
| `Swangz-<v>-macos.cdx.json` | `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` | `<...>` | computed after download: `<...>` | n/a |

## 4. Deliverables 1-10

The baseline below is the acceptance table in RELEASE-EVIDENCE.md and its post-merge sections as of main
`5005b37` (19 Nov 2026). On Saturday, replace each run ID with the release runs once Probe has read them. Do not
upgrade a result that Probe has not read.

| # | Deliverable | Result | Runs (baseline) | Open, not proven |
|---|---|---|---|---|
| 1 | Windows installer | **PASS (runner)** | Windows 44500938493 (47 steps, #287 head); reproducibility 44418629043 | SmartScreen, a real reboot with start at sign-in, a second Windows user (OWNER) |
| 2 | macOS app and DMG | **PASS (runner)** | macOS 44506182423 (114 steps, all `pass`, main `13e22b2`) | Developer ID, notarization, a real first open, a real Keychain prompt (OWNER) |
| 3 | Enrolment and approved sign-in | **PASS (runner)** | both journeys above | wrong, expired and reused codes and non-company emails through the packaged app (Hub unit tests only); real Google sign-in (OWNER) |
| 4 | Server address, no embedded secrets | **PARTIAL** | secret scans on both; fresh install and https-only rule on macOS (#271) and Windows (#276, 44471096830); address kept across an upgrade on both (macOS #277, Windows #287 step 31) | the production address (OWNER) |
| 5 | Company browser workspace | **PARTIAL (runner)** | Windows 44455161915, macOS 44455029714 (#270); #272 runs 44463794008 (Windows), 44467560442 (macOS) | two people signed in at once; ACLs and a second OS user (OWNER); a real provider sign-in (OWNER); the Chrome command line |
| 6 | Staff reporting, admin, F-18, machine policy | **PARTIAL** | F-18 packaged round trip on both (#270, #272: same runs as row 5); Hub checks 44488549742 | the production Hub; the packaged app's grants after restart; machine-policy tamper through the packaged app |
| 7 | Reconnect after restart or outage | **PASS (runner)**, with gaps | Windows 44500938493 (key in no file step 8, Hub process restart step 9, Run entry removed step 36); macOS 44506182423 (login item removed on revoke, step 110, #286) | Linux: start-at-login removal on revoke (unit tests only); sleep, Wi-Fi, VPN (OWNER) |
| 8 | Versioned artifacts, checksums, reproducibility, notes | **PASS** checksums and Windows reproducibility | Windows 44418629043; SBOM rows read on 19 Nov 2026 | macOS reproducibility not checked; two runs of one commit differ in version, so they also differ in hash |
| 9 | Updates off until signing | **PARTIAL** | self-check on both; older build refused on both (macOS #271, Windows #258) | the "older" build is the same source relabelled; tampered update packages are covered by unit tests only; turning updates on is Arnold's decision (OWNER) |
| 10 | Evidence from the runs | **PASS for what runners can do** | the release runs in section 2 | O-1 to O-7 have no results |

## 5. Blockers (exact)

Fill in on Saturday. Each line names the thing, its evidence row and who clears it. Known on 19 Nov 2026:

- **Unsigned builds.** SmartScreen warns on Windows and Gatekeeper blocks the app on macOS. Clearing this needs code-signing certificates and Apple notarization: Arnold, O-6.
- **No physical-device acceptance.** Arnold, O-1 to O-4.
- **No production address, DNS or Google OAuth redirect.** Arnold, O-5.
- **No provider-seat inventory.** Arnold, O-7.
- **Updates are off** (`release_keys.ENABLED = False`) until signed builds and a pinned release key exist.
- RELEASE-EVIDENCE.md does not yet record #287 (Windows key in no log, Hub process restart, address across upgrade). Probe reads run 44500938493 before Saturday.
- `<any red run, open PR or new defect at the release commit>`

## 6. Owner actions left

See [RELEASE-OWNER-CHECKLIST.md](RELEASE-OWNER-CHECKLIST.md) (items 1-7) and the owner rows O-1 to O-7 in
[RELEASE-EVIDENCE.md](RELEASE-EVIDENCE.md). List only the items whose status changed since the checklist's last
update.

## 7. How the UNSIGNED RC pre-release is made (Chief, Saturday)

Dry run on 19 Nov 2026 against existing runs (Windows 44475955390, macOS 44499097781): every file name in sections
1 and 3 matched, both sidecars passed `sha256sum -c`, and `RELEASE-LABEL.txt` reads `RC — UNSIGNED — INTERNAL TEST ONLY`
(Windows line ending). The release step itself was not run.

Pre-approved in the sprint brief: a GitHub pre-release or draft release marked exactly
`RC — UNSIGNED — INTERNAL TEST ONLY`. No workflow does this. It takes these manual steps from a clean shell, with
`R=arnoldkigozi0/swangz-gateway`:

1. Pick the release commit: `SHA=$(gh api repos/$R/commits/main -q .sha)`. Hub checks on `$SHA` must be green.
2. Build both from that commit. Neither workflow runs by itself on a docs-only merge, so start both by hand:
   `gh workflow run release-windows.yml -R $R --ref main` and `gh workflow run build-macos.yml -R $R --ref main`.
3. Find the two runs and confirm that each ran on `$SHA`:
   `gh run list -R $R --workflow release-windows.yml --event workflow_dispatch -L 1 --json databaseId,headSha,conclusion`.
   Repeat for `build-macos.yml`. Wait until both conclude `success`. If main moved, start again from step 1.
4. Download into an empty folder:
   `gh run download <win-run> -R $R -n Swangz-Windows-installer-RC-UNSIGNED -D rc/win` and
   `gh run download <mac-run> -R $R -n swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY -D rc/mac`.
   The macOS files land in `rc/mac/dist/` (the artifact keeps its `dist/` and `evidence/` folders); the Windows files
   land directly in `rc/win/`. Check them: `(cd rc/win && sha256sum -c *.exe.sha256)` and
   `(cd rc/mac/dist && sha256sum -c SHA256SUMS)`. Both must print `OK`.
5. Fill in [RELEASE-NOTES-RC.md](RELEASE-NOTES-RC.md) (release commit, run URLs, the hash table) into
   `rc/notes.md`. Do not commit secrets or production values.
6. Create the pre-release, pinned to the commit (the tag is new and RC-only, never `v0.2.0`):

   ```sh
   gh release create "rc-2026-11-21-${SHA:0:7}" -R $R --target "$SHA" --prerelease \
     --title "Swangz RC ${SHA:0:7} — RC — UNSIGNED — INTERNAL TEST ONLY" --notes-file rc/notes.md \
     rc/win/*.exe rc/win/*.exe.sha256 rc/win/RELEASE-LABEL.txt rc/win/*.cdx.json \
     rc/mac/dist/*.dmg rc/mac/dist/*.dmg.sha256 rc/mac/dist/SHA256SUMS rc/mac/dist/*.cdx.json
   ```

   To review it before anyone sees it, add `--draft`, then publish it with `gh release edit <tag> -R $R --draft=false`.
7. Check it: `gh release view <tag> -R $R --json isPrerelease,assets` must show `isPrerelease: true` and the eight
   files. Download one asset again and compare its SHA-256 with the table in section 3.

Never mark it latest or non-prerelease, never attach the evidence or the previous-version builds, and never use
"production" in its title or notes.
