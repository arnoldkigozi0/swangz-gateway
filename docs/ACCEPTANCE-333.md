# Issue #333: acceptance map and physical checklist

Release blocker: managed Chrome setup and tool launch on Windows and macOS. This page records what is proven, what is
not, and how to check it on real computers. Nothing here is a claim that the release is ready.

## 1. Chrome: where to get it and how to know it is Google's

Checked 25 Nov 2026 (Africa/Kampala). "Documented" means a Google page or Google-published source says it.
"Observed" means we read it from a file downloaded from `dl.google.com` that day, without running it and without
cryptographically verifying the signature. "Unverified" means we could not confirm it.

### Download

| Fact | Source | Status | Impact on our code |
|---|---|---|---|
| Google's enterprise download page offers a Windows MSI bundle (64-bit, ARM64, 32-bit) and Mac PKG and DMG universal installers. Downloading accepts the Chrome terms. | https://chromeenterprise.google/download/ | Documented (the page prints no file addresses) | Google is the only source; the person or admin accepts the terms. |
| The Windows enterprise bundle is linked from Google's help page as `dl.google.com/tag/s/...` ZIP files that contain the MSI and policy templates. | https://support.google.com/chrome/a/answer/7650032 | Documented | The ZIP links are the documented ones, not the direct MSI address below. |
| For Mac, Google recommends the universal PKG; Chrome installs into the system Applications folder. | https://support.google.com/chrome/a/answer/9020580 | Documented | D-026 (#338) has Swangz download nothing on macOS: an administrator installs the PKG; on a personal Mac the person may use Google's DMG. |
| The consumer download is https://www.google.com/chrome ; Windows asks "Do you want to allow this app to make changes to your device?"; a Mac may ask for an administrator password. | https://support.google.com/chrome/answer/95346 | Documented | A safe manual repair page. Consent comes from the operating system. |
| `https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi` returns 200, 175,624,192 bytes, last modified 23 Nov 2026. | Request to Google's server | Observed; **unverified** in documentation | Used by D-026 (#338). It can change without notice, so a failure needs the manual page as repair. It is the x64 build; the ARM64 address is unverified. |
| `https://dl.google.com/chrome/mac/universal/stable/GGRO/googlechrome.dmg` returns 200, 289,260,301 bytes. | Request to Google's server | Observed; **unverified** in documentation | As above. |
| `https://dl.google.com/chrome/mac/universal/stable/gcem/GoogleChrome.pkg` returns 200. | Request to Google's server | Observed; **unverified** in documentation | Alternative for admins. |
| `https://dl.google.com/chrome/install/latest/chrome_installer.exe` redirects to the small online installer `ChromeSetup.exe`. | Request to Google's server | Observed; **unverified** in documentation | Not the offline MSI. |
| Size of the download: both full installers are under 300 MB. | As above | Observed | D-026's 500 MB cap holds today. |

### Publisher and signature

| Fact | Source | Status | Impact on our code |
|---|---|---|---|
| Windows: Google's updater source accepts installer signers named `Google LLC` (and the older `Google Inc`). | https://raw.githubusercontent.com/google/omaha/main/omaha/base/const_code_signing.h | Documented in Google source; **not** in Chrome product documentation | Require a valid Authenticode signature **and** the signer organisation `Google LLC`. |
| Windows: the enterprise MSI (SHA-256 `aa958c31c82a744eba52e1354bf2d97ae3b413d5ecd14125bdf7db1b1f44c99b`) and `ChromeSetup.exe` (SHA-256 `25c001df7621d67921602e1ba9733a4c947224e1487abd9e7349eeef251ab2ca`) carry a signer certificate with `CN=Google LLC, O=Google LLC`, serial number field `3582691`, issued by `DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1`, valid 8 Apr 2024 to 10 Apr 2027. | Certificates read from the downloaded files | Observed; signature validity **unverified** until `Get-AuthenticodeSignature` reports `Valid` on Windows | Compare the organisation exactly, not as a substring. Do not pin the certificate thumbprint: it expires. |
| Windows: the signer of an installed `chrome.exe`. | None | **Unverified** | Checklist step W2 records it. |
| macOS: Chromium source expects Team ID `EQHXZ8M8AV`, identifier `com.google.Chrome`, and the requirement `anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] and certificate leaf[field.1.2.840.113635.100.6.1.13] and certificate leaf[subject.OU] = "EQHXZ8M8AV"`. | https://chromium.googlesource.com/chromium/src/+/main/chrome/browser/safe_browsing/incident_reporting/binary_integrity_analyzer_mac.cc | Documented in Google source; **not** in product documentation | Verify the installed app against this requirement plus the identifier. |
| macOS: the DMG is signed by `Developer ID Application: Google LLC (EQHXZ8M8AV)`. Its own signing identifier is `GoogleChrome-<version>-GGRO` (158.0.8127.89 that day), **not** `com.google.Chrome`. | Signature block read from the DMG | Observed; signature validity **unverified** until `codesign` passes on a Mac | If the DMG itself is checked, require the Team ID only. The identifier rule belongs to the app inside. |
| macOS: the PKG is signed by `Developer ID Installer: Google LLC (EQHXZ8M8AV)`; that certificate expires 1 Feb 2027. | Signature block read from the PKG | Observed; validity **unverified** (`pkgutil --check-signature`) | Pin the Team ID, never the certificate. |

### Distribution terms

| Fact | Source | Status | Impact on our code |
|---|---|---|---|
| "You may not copy, modify, distribute, sell, or lease any part of our services or software." (effective 30 Jul 2026) | https://policies.google.com/terms | Documented | Never bundle, mirror or host a Chrome installer. Download from Google at setup, with consent. |
| The Chrome additional terms (modified 30 Sep 2025) contain no clause letting an organisation redistribute Chrome. | https://www.google.com/chrome/terms/ | Documented (absence) | Permission to redistribute is **unverified**; assume none. |
| Google publishes a hash for each installer. | None found | **Unverified** | Rely on the signature. Log the hash as evidence only. |
| Exact silent-install commands for the MSI and PKG. | Not on the pages read | **Unverified** | Prove them on the real computers before relying on them. |

## 2. Acceptance map against `main`

Checked 26 Nov 2026 at `main` `8b025a5` (merges #351, #353, #354, #356 and #357; app version 0.1.100, database schema 30).
**Done** = code and a named test on `main` that passed. **Partial** = part of the criterion is built or proven.
**Missing** = not on `main`. Test files are under `tests/`. **Nothing was run on a physical Windows computer or Mac.**
D-026 (`docs/DECISIONS.md`) records the design; a decision there is not evidence that its code is built.

### CI evidence for this tree

| Run | Commit | Result on 26 Nov | What it shows |
|---|---|---|---|
| [Hub checks](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/45700455025) (Linux) | `8b025a5` | Python 3.10, 3.12 and app window: pass. Browser job **still running** at 00:19 EAT (extension in Chrome and Hub workflow steps had passed; from the Tracker parity step on, not finished) | Full Python suite, app window, browser journeys (console, staff, extension in Chrome). |
| [Inert browser profiles](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/45700455281) | `8b025a5` | Pass: Linux, Windows, macOS; Python 3.10 and 3.12 | Folder ownership and deletion, launcher, policy check and report. |
| [macOS installer](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/45700454990) (hosted Mac) | `8b025a5` | Pass | Installed app with that runner's Chrome: workspace open, second person, two copies at once, policy refusals. No `cleanup` or uninstall step. |
| [Windows installer](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/45674518861) (hosted Windows) | `a9276d5`, same Git tree as `8b025a5` | Pass | The same journeys, plus uninstall: workspace folders, key and local data removed. The workflow also runs the company installer test. |
| [Chrome publisher](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/45672223240) | `801f37d` (its files are unchanged in `8b025a5`) | Pass: Linux, Windows, macOS | Publisher and signature rules. |

Both installers are **unsigned**. The Windows one has no run on `8b025a5` itself, and `gh release list` showed no release
newer than `aac71ac` (25 Nov). The release commit needs new runs of both workflows.

### Known gaps to read first

1. **A provider can still open in the person's own browser.** The website's Open (`/go/<tool>`) redirects whatever
   browser is signed in to the Hub, company computers included; `managed.launch_refusal` refuses only when the link
   carries a device id (`test_managed_workspace.py` `test_the_device_claim_can_only_refuse_never_open`). Seen again in
   the local journey below (step 5). "Every authorised web tool opens only in the dedicated Chrome" is **not true** for
   Opens made on the website. The app does not open shared company accounts; D-027 records the design and none of it is
   built.
2. **Setup does not install Chrome.** The app now verifies Chrome's publisher before starting it (#351). The Windows
   install step is an open draft (#358), not on `main`. On macOS Swangz installs nothing by design.
3. **Revocation leaves the browser folders, with provider and Google sessions, on the disk.** Disconnecting the device
   and signing out of the app keep them; the app names the folder and says to run `cleanup`. They are deleted by
   `cleanup`, by the Windows uninstaller (which runs it), when a different person signs in on the same OS account
   (#354), and by an authenticated workspace `retired` or higher generation. macOS has no uninstaller: dragging the app
   to the Bin without removing Swangz first leaves them. D-026 F1 (delete on revocation) is not built.
4. **`enforce` must stay off.** An admin can now mark a device company or personal (#357), through the API only. A mark
   of "personal" does not disarm the app's own policy check until the app restarts (and not if the device was declared
   company), and signing in again starts a new, unmarked enrolment. (Probe review of #357, 25 Nov.)

### 1. Guided setup

| Part | State | Proven on | Evidence or gap |
|---|---|---|---|
| Detect Chrome | Done | CI: Windows, macOS, Linux | `workspace_launcher.find_browser`, fixed places only; `test_workspace_launcher.py`, `test_chrome_verify.py`. |
| Verify publisher and signature | Done in code and CI | CI: Windows, macOS | `test_chrome_verify.py`; both installer journeys started the runner's Chrome through the default launcher, which checks it first. A refused publisher on a real computer: not seen. |
| Install it from Google if missing | Missing | - | #358 (draft, Windows company build only) is not merged. The repair panel links to Google's page. |
| Respect elevation and consent | Missing | - | No install or policy-write step on `main`. A company (all-users) installer exists (#342). |
| Dedicated folder per employee | Done | CI: Windows, macOS (installed app) | `browser_profiles`; journey step "the folder belongs to this person on this device". |
| Retire an earlier person's folder on the same OS account | Done | CI: Windows, macOS (installed app) | #354; `test_browser_profiles.py` `test_every_folder_of_every_other_person_is_deleted_and_their_own_are_kept`; journey step "the first person's folder is deleted from this account". Happens at the second person's first authenticated contact or open, not at approval. |
| No redistribution of Chrome | Holds | - | Nothing bundles it. No test. |

### 2. Launch only in that Chrome

| Part | State | Proven on | Evidence or gap |
|---|---|---|---|
| App Open goes to explicit Chrome with the dedicated folder | Done | CI: Windows, macOS (installed app) | "Google Chrome started on that folder (not the default browser)"; `test_default_browser_is_never_used`. |
| No default-browser fallback in the app | Done | CI | `test_workspace_launcher.py`, `test_no_fallback.py`. The default browser is still used for the Hub's own pages and Google's Chrome page. |
| No provider link in the default browser anywhere | **Missing** | - | Gap 1. |
| Repair screen when it fails closed | Done | CI | `test_open_repair.py`, `test_client_gui.py`; policy refusals seen in both installer journeys. Not seen by a person on a real computer. |
| Native and command-line tools kept separate | Done | CI | They do not use the browser launcher. |

### 3. Sessions

| Part | State | Proven on | Evidence or gap |
|---|---|---|---|
| Provider sign-in survives restart | Partial | CI: Windows, macOS | The folder and its marker survive upgrade and sign-out. No real provider session and no computer restart. |
| No copying of cookies, passwords or tokens between employees | Partial | CI: Windows, macOS | Separate folders for two people and two running copies. No test states "nothing is uploaded". |
| Interactive Google sign-in, no Chrome sync | Partial | Not run | The pack allows the Google sign-in hosts and disables sync. Country Google hosts are **unverified**. |

### 4. Policy, conflicts and revocation

| Part | State | Proven on | Evidence or gap |
|---|---|---|---|
| Extension and policy provisioned by setup | Missing | - | By hand (`deploy/chrome-policy/prepare.py`). The CI packs use placeholder values. |
| Read the policy, refuse a missing or changed one (`enforce`) | Done in CI | CI: Windows, macOS (installed app) | Intact: opens. Tampered, wrong pack or removed: refused, no open recorded. On real computers `enforce` stays off (gap 4). |
| Detect conflicts (#194) | Done in code | CI: Windows, macOS, Linux | #352; `test_policy_report.py` (extra names, per-user, Recommended). Not tried against a real GPO or MDM. |
| Report unenforced controls | Partial | CI | `machine_policy.setup_report()` is tested, but no screen or Hub page calls it. |
| Company/personal decided by an admin | Partial | CI: Linux | #357, API only; see gap 4. |
| Revocation: the Hub refuses launches and AI requests | Done | Local Linux and CI | Local journey steps 11 and 12. |
| Revocation: the open workspace closes | Partial | CI | `test_5_revoked_closes_before_the_wipe_and_keeps_the_folder`. Waits for the next sync or for the computer to be online. |
| Revocation: local browser data removed | **Missing** | Seen kept: Local Linux, Windows, macOS | Gap 3. |
| `cleanup` / uninstall removes the folders | Done (macOS: command or button only) | Local Linux; CI Windows uninstall; unit tests on all three | #353; `test_profile_delete.py`. A folder held by a running browser is kept and named. The company uninstaller removes no person's folders. |
| Suspend or retire a workspace from the console | Partial | CI | API only (`POST /admin/api/devices/<id>/workspace`). |
| Local cleanup told apart from provider revocation | Partial | - | Said in documents. No console text saying the provider seat or session stays was found. |

### 5. Tests and release evidence

| Part | State | Evidence or gap |
|---|---|---|
| Missing Chrome, profile isolation, denied tool, no fallback | Done | Named above; `test_device_open.py` for denials. |
| Install failure | Missing | The Chrome install step is not on `main`. |
| Paths with spaces | Partial | `test_open_repair.py` starts a stand-in script. Real Chrome from a path with spaces is not asserted by name. |
| Restart | Partial | App restart in tests; no computer restart. |
| Both installers from one tested commit | Partial | Same tree today, not the same commit (table above). Unsigned. |
| Physical acceptance | **Missing** | Section 3. |

### 6. Server, limits, rollback

| Part | State | Evidence or gap |
|---|---|---|
| Same server and domain, no cloud browser needed | Done | Nothing in this work changes them. `https://hub.ictconnect.org/healthz` answered on 26 Nov with commit `7c2071125a54`, 120 commits behind `8b025a5`. |
| Limitations and rollback written down | Partial | D-026 lists the limits. No step removes an installed Chrome policy. Personal computers get no site allow list. |

### Local end-to-end journey, 26 Nov, `8b025a5`

Linux, Python 3.14.4, on the team laptop: a real `python3 -m gateway serve` on a new database, the stand-in provider
`tests/fake_upstream.py`, plain HTTP requests as the console, staff browser and extension would send them, and the app's
command line. No real key, account or provider. The driving script is Probe's and is not in the repository.
Result of the final run: **52 checks, 50 passed, 2 failed** (both in step 9). `/healthz` reported `8b025a580ce5`.

| # | Step | Result | Observed |
|---|---|---|---|
| 1 | First owner, health, admin sign-in | PASS | 200. |
| 2 | Admin adds two people, a tool, an active subscription, a grant to one | PASS | All 200. |
| 3 | Each sets a password from the one-time link and signs in | PASS | Set 200; link reused 404; sign-in 200. |
| 4 | Staff sees the tool | PASS | Granted: `enabled`; other person: `not_assigned`. |
| 5 | Open via `/go/` | PASS | Granted: 302 to the tool, in the browser that asked (gap 1). Other person: 403. |
| 6 | Launch recorded; admin sees it | PASS | Activity timeline: 1 launch. Tools opened: `opened` and `refused`. |
| 7 | Extension gate (its API calls) | PASS | Granted: allowed, 42 s recorded. Ungoverned site: answered `known: false`. Other person: blocked with a reason. Websites visited shows both. |
| 8 | Device enrol | PASS | Code shown, approved in the person's session, app signed in and synced; admin lists the device. Keychain here is a stand-in `secret-tool`. |
| 9 | Issue a key **naming a tool** | **FAIL** | `POST /admin/api/people/1/keys` with `tool_id`: 500. `python3 -m gateway issue-key 1 --tool claude-code`: exit 1. Both `TypeError: 'int' object is not subscriptable` (`entitle.py` `person_grants`, reached from `reporting.key_scope`, which is passed the person's id, not the row). The console's own request, with no tool, works. |
| 10 | AI request through the gateway; admin sees it in Live and AI requests | PASS | 1 in flight under the person, then recorded `ok`. Website opens appear in Activity, not Live. |
| 11 | App Open, then grant removed | PASS | Open started a stand-in script (not Chrome) on the person's folder. After removal: web Open 403, extension blocked, app Open refused with no start, tool `not_assigned`. |
| 12 | API grant removed | PASS | The very next AI request: 403. |
| 13 | Device revoked from the console | PASS, folder kept | Next sync exit 3, app signed out, `status` exit 2, no key file left. The browser folder stayed (gap 3). |
| 14 | `swangz cleanup` | PASS | Exit 0, no browser folder left. |
| 15 | Weekly report | PASS | Job run directly with the clock 8 days on: 2 reports compiled; due report showed 2 launches; submitted; admin sees it; another person gets 404. |
| 16 | Staff sign-out and suspension | PASS | After sign-out `/api/me` 401 and `/go/` goes to sign-in. Suspended: the old extension session 401, a new extension sign-in 403; the web sign-in still answers 200, but `/go/` is refused (403), even after a new grant. |
| 17 | Audit log, admin sign-out, server log scan | PASS | Expected entries present; old cookie 401; the server log holds no admin or staff password, API key or extension token from the run (its one traceback is step 9). |

**Not run locally:** clicking through the console and staff pages, and the extension inside a browser (covered by the CI
browser journeys above, not by this journey); real Chrome; Google sign-in; a real provider; Windows; macOS.

**Also seen**

- The extension's session stays valid after the staff web sign-out (it is a separate sign-in). Suspension ends it.
- Linux only, first run: with `secret-tool` installed but no reachable keyring, the app kept the key in its protected
  file, then `sync` after revocation exited 1 and `cleanup` exited 1 ("Secret Service could not delete the device
  credential."), leaving `device.key` and the device record. The Hub had already refused the key. Linux is outside
  #333; not tried on Windows or macOS.

## 3. Physical checklist for Arnold

Use test staff accounts and Swangz test computers. Write **Pass**, **Fail** or **Not run** with a reason for every
row. Never capture a password, one-time code, key or cookie; cut web addresses before the `?`.

### Before the computers

| # | Do | Expect and keep |
|---|---|---|
| S1 | On the server, back up and check: `cd /opt/swangz-gateway`, then `sudo -u swangz python3 -m gateway backup` and `sudo -u swangz python3 -m gateway backup-verify --latest`. | `restore check ok`. Keep both lines. |
| S2 | In the server's git clone: `git fetch`, `git checkout <commit Chief names>`, `sudo bash deploy/setup-gateway-server.sh hub.ictconnect.org`. In `/opt/swangz-gateway/.env` both address values must be `https://hub.ictconnect.org`. | The script restarts the service. Rollback: `docs/SERVER-DAY.md` section 11 (restore the backup; never old code on a newer database). |
| S3 | `curl -s https://hub.ictconnect.org/healthz` | `"ok": true` and the chosen commit. On 26 Nov it showed `7c2071125a54`, 120 commits behind `8b025a5`. Confirm this is the intended AWS server and that its address is fixed (on 25 Nov: `13.63.32.73`; the earlier name `51-21-160-193.sslip.io` did not answer). |
| S4 | Use both installer runs for the commit Chief names; the team starts both workflows on it. Download `Swangz-Windows-installer-RC-UNSIGNED` and `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` from the runs (kept 14 days). Do not take an installer from the older pre-releases. Check each file: `Get-FileHash <file>` / `shasum -a 256 <file>`. | Hash equals the one beside the file; the app version is the chosen build's. Keep the run link, commit and hashes. |
| S5 | In the console: two test people, A and B. Give A one website tool with an active subscription that is not a shared account (for example Gemini). Give B none. Leave policy mode on `warn`. | Screenshot of each person's access. |

### Windows (W) and macOS (M): run every row on both

| # | Do | Expect and keep |
|---|---|---|
| 1 Fresh install | On a user account that never had Swangz, ideally without Chrome. Run the installer (Mac: drag from the DMG to Applications). It is unsigned: note the exact SmartScreen or Gatekeeper warning and how you passed it. | Sign-in opens. The address is already `https://hub.ictconnect.org`; nothing is saved until sign-in. Sign in as A and approve in the browser. Choose "company-owned" only on a Swangz computer: it also points coding agents at the gateway. Screenshots. |
| 1a Chrome missing | Press Open on A's tool before installing Chrome. | A panel "Google Chrome is needed" with **Get Google Chrome** (Google's download page) and **Try again**. The tool opens in **no** browser. Screenshot. |
| 2 Chrome is Google's | Install from https://www.google.com/chrome/. **W2:** PowerShell `Get-AuthenticodeSignature "C:\Program Files\Google\Chrome\Application\chrome.exe" \| Format-List Status,SignerCertificate` (per-user install: under `$env:LOCALAPPDATA\Google\Chrome\Application`). **M2:** `codesign --verify --deep --strict --verbose=2 "/Applications/Google Chrome.app"`, `codesign -dv --verbose=4 "/Applications/Google Chrome.app"`, `spctl --assess --type execute -vv "/Applications/Google Chrome.app"`. | W: `Valid`, organisation `Google LLC`. M: verification passes, `Identifier=com.google.Chrome`, `TeamIdentifier=EQHXZ8M8AV`, accepted. Copy the text. |
| 3 Open | Press Try again or Open. **W:** `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" \| Where-Object CommandLine -like '*browser-profiles*' \| Select-Object -First 1 -ExpandProperty CommandLine`. **M:** `ps -axww -o command \| grep -m1 browser-profiles`. | A Chrome window; the command has `--user-data-dir=` inside `Swangz/browser-profiles`. Your normal Chrome profile is unchanged. Console, Activity: one launch. |
| 4 Google and provider sign-in | Sign in by hand in that window with A's test account, including two-step. | The tool is usable. Note any blocked or country-specific Google address, and any prompt to sign in to Chrome. |
| 5 Restart | Quit the app and the window, restart the computer, Open again. | Still signed in; same folder name. List it: `Get-ChildItem $env:LOCALAPPDATA\Swangz\browser-profiles` / `ls -l "$HOME/Library/Application Support/Swangz/browser-profiles"`. |
| 6a Two users, two OS accounts | Second OS account, sign in as B (give B the tool for this row, then remove it). | B is not signed in to A's provider account and cannot open A's folder. |
| 6b Two users, one OS account | In A's OS account, close the workspace window: This device, sign out; sign in as B, Sync now, then Open B's tool. | B gets a new folder and sees none of A's sessions; **A's folder is gone**. List the folders. |
| 7 Denied tool | As B without the tool, or after removing it from A, press Sync now, then Open if it is still listed. If it is no longer listed, record that. | Refused with a reason; no window opens. Console, Activity shows the refusal when the Hub made it. |
| 8 Blocked sites | Only where the company policy pack is installed (`deploy/chrome-policy/README.md`; it blocks every Chrome window and OS user on that computer, so use a test computer). Read it: `reg query HKLM\Software\Policies\Google\Chrome /s /reg:64` / `defaults read "/Library/Managed Preferences/com.google.Chrome"`. Try Gmail and an unlisted site in the workspace window, then A's tool. | Gmail and the unlisted site blocked; the tool loads. Without the extension id and update address the extension is not installed: record that. No pack: **Not run**. |
| 8a Known gap | In your normal browser, signed in to the Hub as A, press Open. | It opens in that browser (gap 1). Record what happens, with and without the pack. |
| 8b Shared account | On a company-owned test computer, give A a shared-account tool for this row, press Sync now, then Open it in the app. | Panel "This shared account doesn't open here yet", advice to ask the Swangz admin, only **Dismiss**. Nothing opens. Remove the grant afterwards. Not company-owned: **Not run**. |
| 9 Revoke | With the window open, disconnect the device (console, Devices; or A's Devices page). Press Sync now or wait 15 minutes. Try Open. | Window closes; app returns to sign-in and names the browser folder it did not remove; Open refused. Expected gap: the folder remains (gap 3). The provider session is **not** revoked: remove the seat or sign out at the provider and note it. Repeat once with the computer offline and note the delay. |
| 10 Uninstall | Reconnect first and open a tool. Close the workspace window. **W:** Settings, Apps, Swangz, Uninstall. **M:** This device, **Remove Swangz from this account**, then move Swangz to the Bin. | Device shows disconnected; Swangz no longer starts at login; no folder is left under `browser-profiles` (a folder that could not be deleted is named). Chrome and personal profiles are untouched. The provider session at the provider's side is not ended. |

Release is not accepted while any row is Fail or Not run without a decision from Arnold, or while gaps 1 to 4 have no
decision. Passing this list does not make the unsigned installers production-ready.
