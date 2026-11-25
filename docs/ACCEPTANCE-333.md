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
| For Mac, Google recommends the universal PKG; Chrome installs into the system Applications folder. | https://support.google.com/chrome/a/answer/9020580 | Documented | D-026 uses the DMG. Both work; the PKG is Google's recommendation for managed rollout. |
| The consumer download is https://www.google.com/chrome ; Windows asks "Do you want to allow this app to make changes to your device?"; a Mac may ask for an administrator password. | https://support.google.com/chrome/answer/95346 | Documented | A safe manual repair page. Consent comes from the operating system. |
| `https://dl.google.com/dl/chrome/install/googlechromestandaloneenterprise64.msi` returns 200, 175,624,192 bytes, last modified 23 Nov 2026. | Request to Google's server | Observed; **unverified** in documentation | Used by D-026. It can change without notice, so a failure needs the manual page as repair. It is the x64 build; the ARM64 address is unverified. |
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

Read from the code at `main` `9977c2a` on 25 Nov. **Done** = code and a named test on `main`. **Partial** = part of
the criterion is built or proven. **Missing** = not on `main`. Test files are under `tests/`. Nothing below was run on
a physical Windows computer or Mac. Two open changes are noted where they would move a line; they are not on `main`:
#336 (repair steps after a refused Open) and #337 (default Hub address).

### Known gaps to read first

1. **A provider can still open in the person's own browser.** The app refuses shared company accounts and sends the
   person to the Hub. The website's Open (`/go/<tool>`, `gateway/staff.py` `launch`) redirects whatever browser is
   signed in to the Hub, shared accounts and company browsers included. `managed.launch_refusal` refuses only when the
   link carries a device id. Pinned by `test_managed_workspace.py` `test_the_device_claim_can_only_refuse_never_open`
   and `test_enforce_never_blocks_a_request_that_makes_no_device_claim`. "Every authorised web tool opens only in the
   dedicated Chrome" is therefore **not true** for Opens made on the website.
2. **Setup does not install or verify Chrome.** The app looks for Chrome at fixed paths and offers Google's page.
3. **Sign-out, revocation and uninstall leave the browser folder, with its provider sessions, on the disk.** On
   Windows a retired workspace cannot delete it either.
4. **`enforce` must stay off.** D-025 requires an admin way to confirm or change whether a device is company-owned
   first. No such route is on `main`; the person approving the device chooses.

### 1. Guided setup

| Part | State | Evidence or gap |
|---|---|---|
| Detect Chrome | Partial | `workspace_launcher.find_browser`: fixed paths and "is a file"; no signature check. `test_workspace_launcher.py` `test_fixed_candidates`, `test_first_usable_wins_and_none_means_no_browser`. |
| Install it from Google if missing | Missing | No test. The window offers https://www.google.com/chrome/; the command line prints it. Neither installer has a Chrome step. |
| Verify publisher and signature | Missing | No test. Facts to build on are in section 1. |
| Respect elevation and consent | Missing | There is no install step that could ask. |
| Dedicated folder per employee | Done | `browser_profiles`. `test_browser_profiles.py` `test_different_owners_do_not_reuse`; `test_browser_contract.py` `test_two_people_get_their_own_ids`. |
| Retire an earlier person's folder when a second person uses the same OS account | Missing | The second person gets a different folder; the first one stays (`test_workspace_revocation.py` `test_9_another_owners_folder_survives_a_retired`). |
| No redistribution of Chrome | Holds | Nothing bundles it. No test. |

### 2. Launch only in that Chrome

| Part | State | Evidence or gap |
|---|---|---|
| App Open goes to explicit Chrome with the dedicated folder | Done | `core.open_app`. `test_workspace_launcher.py` `test_default_browser_is_never_used`. |
| No default-browser fallback in the app | Done | `test_no_refusal_falls_back_to_the_default_browser`, `test_without_a_workspace_nothing_opens`, `test_no_tool_ever_reaches_open_url_on_a_contract_2_device`. |
| No provider link in the default browser anywhere | Missing | Gap 1 above. |
| Repair UI when it fails closed | Partial | On `main`: a message, and an install prompt when Chrome is missing. #336 adds steps and buttons for each refusal. |
| Native and command-line tools kept separate | Done | They do not use the browser launcher. |

### 3. Sessions

| Part | State | Evidence or gap |
|---|---|---|
| Provider sign-in survives restart | Partial | `test_browser_profiles.py` `test_prepare_reuses_exact_owner`; `packaging/hub_journey.py` `kept()`. No real provider session and no computer restart tested. |
| No copying of cookies, passwords or tokens between employees | Partial | No code reads or uploads folder content; `test_only_the_workspace_launcher_imports_it` limits who can reach it. No test states "nothing is uploaded". |
| Interactive Google sign-in, no Chrome sync | Partial | The pack allows the two Google sign-in hosts and disables sync. Country Google hosts are **unverified**. The pack cannot stop a person typing a personal Google account. |

### 4. Policy, conflicts and revocation

| Part | State | Evidence or gap |
|---|---|---|
| Extension and policy provisioned by setup | Missing | By hand: `deploy/chrome-policy/prepare.py`, which needs the Hub host, the extension id and its update address. The extension is not published, so two of the three do not exist yet. Force-installing from outside the Web Store works only on managed computers. |
| Read policy without changing personal settings | Done | `test_machine_policy.py`, `test_policy_integrity.py`. The app writes no policy. |
| Detect conflicts (#194) | Partial | Required values are checked. Extra policy names, per-user (HKCU) and Recommended policies are not reported. |
| Report unenforced controls | Missing | The report says whether the pack's values are present, not whether Chrome applied them. |
| Company/personal decided by an admin | Missing | Gap 4. `test_chrome_policy.py` checks only the pack's shape. |
| Revocation: the Hub refuses launches | Done | `test_device_open.py`, `test_workspace_revocation.py`, `test_managed_workspace.py`. |
| Revocation: the open workspace closes | Partial | `test_5_revoked_closes_before_the_wipe_and_keeps_the_folder`. Waits for the next sync (up to 15 minutes) or for the computer to be online. A window left from an earlier app run cannot be closed. |
| Revocation: local data removed | Partial | Disconnecting keeps the folder by design. Retiring a workspace purges it, except on Windows (`test_15_retired_on_windows_closes_refuses_and_reports_the_purge_not_done`, `test_mock_windows_retirement_refuses_without_mutation`). |
| Suspend or retire from the console | Partial | API only (`POST /admin/api/devices/<id>/workspace`); no console button. |
| Local cleanup told apart from provider revocation | Partial | Said in documents only. The console does not say that the provider seat or session stays. |

### 5. Tests and release evidence

| Part | State | Evidence or gap |
|---|---|---|
| Missing Chrome, profile isolation, denied tool, no fallback | Done | Named above; `test_device_open.py` for denials. |
| Install failure | Missing | There is no install step. |
| Paths with spaces | Partial | On `main` only the fixed `C:\Program Files` candidates. #336 adds a real start from folders with spaces and accents. |
| Restart | Partial | App restart in tests; no computer restart. |
| Revocation | Partial | Windows folder deletion is not done. |
| Both installers from one tested commit | Partial | `release-windows.yml` runs on pull requests and by hand only; `build-macos.yml` also on pushes to `main` that touch app files. A pull-request run builds a merge commit. Start both by hand on the chosen `main` commit. Both are **unsigned**. |
| Physical acceptance | Missing | Section 3. |

### 6. Server, limits, rollback

| Part | State | Evidence or gap |
|---|---|---|
| Same server and domain, no cloud browser needed | Done | Nothing in this work changes them. |
| Limitations and rollback written down | Partial | The #333 design is in open pull request #334. No step removes an installed Chrome policy. Personal computers get no site allow list. |

## 3. Physical checklist for Arnold

Use test staff accounts and Swangz test computers. Write **Pass**, **Fail** or **Not run** with a reason for every
row. Never capture a password, one-time code, key or cookie; cut web addresses before the `?`.

### Before the computers

| # | Do | Expect and keep |
|---|---|---|
| S1 | On the server, back up and check: `cd /opt/swangz-gateway`, then `sudo -u swangz python3 -m gateway backup` and `sudo -u swangz python3 -m gateway backup-verify --latest`. | `restore check ok`. Keep both lines. |
| S2 | In the server's git clone: `git fetch`, `git checkout <commit Chief names>`, `sudo bash deploy/setup-gateway-server.sh hub.ictconnect.org`. In `/opt/swangz-gateway/.env` both address values must be `https://hub.ictconnect.org`. | The script restarts the service. Rollback: `docs/SERVER-DAY.md` section 11 (restore the backup; never old code on a newer database). |
| S3 | `curl -s https://hub.ictconnect.org/healthz` | `"ok": true` and the chosen commit. On 25 Nov it showed `7c2071125a54`, 39 commits behind `9977c2a`, at address `13.63.32.73`. The earlier name `51-21-160-193.sslip.io` did not answer. Confirm this is the intended AWS server and that its address is fixed. |
| S4 | The team starts both installer workflows on that commit; download `Swangz-Windows-installer-RC-UNSIGNED` and `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` (kept 14 days). Check each file: `Get-FileHash <file>` / `shasum -a 256 <file>`. | Hash equals the one beside the file. Keep the run link, commit and hashes. |
| S5 | In the console: two test people, A and B. Give A one website tool with an active subscription that is not a shared account (for example Gemini). Give B none. Leave policy mode on `warn`. | Screenshot of each person's access. |

### Windows (W) and macOS (M): run every row on both

| # | Do | Expect and keep |
|---|---|---|
| 1 Fresh install | On a user account that never had Swangz, ideally without Chrome. Run the installer (Mac: drag from the DMG to Applications). It is unsigned: note the exact SmartScreen or Gatekeeper warning and how you passed it. | Sign-in opens. With #337 in the build the address is already `https://hub.ictconnect.org`; otherwise type it. Sign in as A and approve in the browser. Choose "company-owned" only on a Swangz computer: it also points coding agents at the gateway. Screenshots. |
| 1a Chrome missing | Press Open on A's tool before installing Chrome. | A message that Chrome is needed and Google's download page offered. The tool opens in **no** browser. Screenshot. |
| 2 Chrome is Google's | Install from https://www.google.com/chrome/. **W2:** PowerShell `Get-AuthenticodeSignature "C:\Program Files\Google\Chrome\Application\chrome.exe" \| Format-List Status,SignerCertificate` (per-user install: under `$env:LOCALAPPDATA\Google\Chrome\Application`). **M2:** `codesign --verify --deep --strict --verbose=2 "/Applications/Google Chrome.app"`, `codesign -dv --verbose=4 "/Applications/Google Chrome.app"`, `spctl --assess --type execute -vv "/Applications/Google Chrome.app"`. | W: `Valid`, organisation `Google LLC`. M: verification passes, `Identifier=com.google.Chrome`, `TeamIdentifier=EQHXZ8M8AV`, accepted. Copy the text. |
| 3 Open | Press Try again or Open. **W:** `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" \| Where-Object CommandLine -like '*browser-profiles*' \| Select-Object -First 1 -ExpandProperty CommandLine`. **M:** `ps -axww -o command \| grep -m1 browser-profiles`. | A Chrome window; the command has `--user-data-dir=` inside `Swangz/browser-profiles`. Your normal Chrome profile is unchanged. Console, Activity: one launch. |
| 4 Google and provider sign-in | Sign in by hand in that window with A's test account, including two-step. | The tool is usable. Note any blocked or country-specific Google address, and any prompt to sign in to Chrome. |
| 5 Restart | Quit the app and the window, restart the computer, Open again. | Still signed in; same folder name. List it: `Get-ChildItem $env:LOCALAPPDATA\Swangz\browser-profiles` / `ls -l "$HOME/Library/Application Support/Swangz/browser-profiles"`. |
| 6a Two users, two OS accounts | Second OS account, sign in as B (give B the tool for this row, then remove it). | B is not signed in to A's provider account and cannot open A's folder. |
| 6b Two users, one OS account | In A's OS account: This device, sign out; sign in as B. | A second folder; B sees none of A's sessions. Expected gap: A's folder is still there. List it. |
| 7 Denied tool | As B without the tool, or after removing it from A, press Sync now, then Open if it is still listed. If it is no longer listed, record that. | Refused with a reason; no window opens. Console, Activity shows the refusal when the Hub made it. |
| 8 Blocked sites | Only where the company policy pack is installed (`deploy/chrome-policy/README.md`; it blocks every Chrome window and OS user on that computer, so use a test computer). Read it: `reg query HKLM\Software\Policies\Google\Chrome /s /reg:64` / `defaults read "/Library/Managed Preferences/com.google.Chrome"`. Try Gmail and an unlisted site in the workspace window, then A's tool. | Gmail and the unlisted site blocked; the tool loads. Without the extension id and update address the extension is not installed: record that. No pack: **Not run**. |
| 8a Known gap | In your normal browser, signed in to the Hub as A, press Open. | It opens in that browser (gap 1). Record what happens, with and without the pack. |
| 9 Revoke | With the window open, disconnect the device (console, Devices; or A's Devices page). Press Sync now or wait 15 minutes. Try Open. | Window closes; app returns to sign-in; Open refused. Expected gap: the folder remains. The provider session is **not** revoked: remove the seat or sign out at the provider and note it. Repeat once with the computer offline and note the delay. |
| 10 Uninstall | Reconnect first. **W:** Settings, Apps, Swangz, Uninstall. **M:** sign out in the app, quit, move Swangz to the Bin. | Device shows disconnected; Swangz no longer starts at login. List what is left in the Swangz folder; browser folders are expected to remain. Chrome and personal profiles are untouched. |

Release is not accepted while any row is Fail or Not run without a decision from Arnold, or while gaps 1 to 4 have no
decision. Passing this list does not make the unsigned installers production-ready.
