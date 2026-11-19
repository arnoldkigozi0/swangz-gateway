# Swangz app: release candidate notes (Windows and macOS)

**RC — UNSIGNED — INTERNAL TEST ONLY.** This is a release candidate for internal testing. It is not a production
release, and nothing here may be described as production-ready. Arnold approves any distribution beyond internal
testing.

Facts here come from [RELEASE-EVIDENCE.md](RELEASE-EVIDENCE.md) and merged pull requests only. Where the evidence
says NOT TESTED, PARTIAL or OWNER, so do these notes. Windows build details: `packaging/RELEASE-NOTES-RC.md`.

- **Release commit:** `<filled in by Chief>`
- **CI runs:** Windows `<run URL>` · macOS `<run URL>`

## What is in it

| Piece | What it does | Evidence |
|---|---|---|
| **Windows installer** | Per-person install with no administrator rights. It adds a Start-menu entry, plus two optional tasks that are off by default: a desktop shortcut and starting at sign-in. It also adds an uninstaller in Apps & features. An older installer run over a newer install is refused | #243, #250. Install, sign-in, restart, network cut and restore, upgrade over a running copy and uninstall all pass on `windows-latest` (RELEASE-EVIDENCE rows 1, 7 and 9) |
| **macOS app and DMG** | `Swangz.app` in a DMG for Apple silicon. You drag it into Applications. An older copy put over a newer one refuses to run (exit 5) | #244, #253, #263, #271, #275. The 31-step journey passes on `macos-latest`. Gatekeeper rejects the unsigned app as expected (row 2) |
| **Device sign-in** | The device is approved with a code in the person's own browser (`/device`). The key is stored in the system keychain (Credential Manager on Windows, Keychain on macOS). No Hub address, key or secret is built in: the person enters the address at first run, and it must be https, except `localhost`, `127.0.0.1` and `::1` | Rows 3 and 4. The macOS app refuses `http://` addresses (#271) |
| **Managed AI browser workspace** | A company-managed browser profile per person for approved AI sites, kept apart from personal browsing. Company devices check the machine policy before Open and report it if it has been tampered with (D-024, #248) | #204, #248. Linux headless only (#236) and Linux Chrome CI (`w6-step5`). No real-Chrome run on Windows or macOS yet (row 5) |
| **Prompt and reply privacy (F-18)** | `store_bodies` is **off by default**: no prompt or reply text is stored. If an admin turns it on, only console roles with the `trust` area (owner, security) can read the content. Every other role sees "withheld" | #249, D-023. Probe verified at `58da416`. Content already stored stays until retention removes it. Not yet checked as a round trip through the packaged app |
| **Updates** | Off. The app reports "Updates unavailable: no pinned release key". A newer RC is installed by hand | `release_keys.ENABLED = False` |

## Version rules

- **Test builds:** CI numbers RC builds as the tree's version with PATCH raised by the run number: `0.1.0` becomes
  `0.1.<run>`, for example `0.1.400`. Two runs of the same commit therefore differ in name and hash.
- **No going back:** an older build never replaces a newer one. On Windows the installer refuses it. On macOS the
  app refuses to run (exit 5) while the device is signed in, and its dialog offers **Sign out** (#275). A version the
  updater rolled back from does not count.
- **The first real release is `0.2.0`.** It raises MINOR so that it sorts above every `0.1.<run>` test build. Any
  tester who ran an RC can then install it without being refused (`docs/CLIENT.md`).
- **The server sets a minimum client version.** That is what controls agent use. The local "no going back" check
  deliberately does not apply to the credential helper.

## Known limits

- **Unsigned:**
  - **Windows:** SmartScreen warns "unknown publisher". This is expected until Swangz signs the installer with its
    own code-signing certificate.
  - **macOS:** Gatekeeper blocks the app on first open. This is expected until the app has a Developer ID and is
    notarized. The team gives no instructions for bypassing Gatekeeper, and no job turns it off or strips the
    quarantine flag.
- **Auto-update is OFF** until signed builds exist, the app checks signatures against a pinned release key, and
  Arnold decides to turn it on.
- **Windows has fewer packaged-app checks than macOS.** These run in the macOS packaged app but not yet in the
  Windows one, and are waiting on Prism's Windows parity PR:
  - a fresh install has no saved address;
  - the https-only address rule;
  - the Hub being down when the app starts;
  - a device revoked while the Hub was away;
  - the key appearing in no log after an outage.
- **The managed workspace has not run with real Chrome on Windows or macOS.** There is no evidence yet that the
  profile folder survives an upgrade, or of what uninstall does to it.
- **macOS reproducibility is not checked.** Windows builds are byte-identical only for two builds in one job on one
  runner image.
- **Runners are not company devices.** They show no real SmartScreen or Gatekeeper prompt, no Keychain dialog, no
  sleep or Wi-Fi change, and no second person. A program restart stands in for a reboot.
- **Owner-only checks O-1 to O-7 are open.** None has a result yet: the physical Windows PC and Mac, a second OS
  user, sleep/Wi-Fi/VPN, the production address and Google sign-in, signing and the decision on updates, and the
  provider-seat inventory. See [RELEASE-OWNER-CHECKLIST.md](RELEASE-OWNER-CHECKLIST.md).

## Install

### Windows 11

1. Download `Swangz-Setup-<version>-UNSIGNED.exe` and its `.sha256` from the `Swangz-Windows-installer-RC-UNSIGNED`
   artifact.
2. Check the hash in PowerShell: `Get-FileHash -Algorithm SHA256 .\Swangz-Setup-<version>-UNSIGNED.exe`. It must
   match the `.sha256` file and the table below.
3. Run the installer. No administrator rights are needed. SmartScreen's "unknown publisher" warning is expected:
   record it for O-1.
4. Open Swangz, enter the Hub address you were given, and approve the code in your own browser.

### macOS (Apple silicon)

1. Download `Swangz-<version>-RC-UNSIGNED-macos-arm64.dmg` and its `.sha256` from the
   `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` artifact.
2. Check the hash in Terminal: `shasum -a 256 Swangz-<version>-RC-UNSIGNED-macos-arm64.dmg`.
3. Open the DMG and drag Swangz into Applications.
4. Open it. Gatekeeper blocking the unsigned app is the expected result: record it for O-2. Do not turn Gatekeeper
   off. Testing beyond this point on a real Mac waits for a signed build, or for Arnold's decision on how the owner
   test runs.
5. Once it opens: enter the Hub address, approve the code in your browser, and allow the Keychain prompt.

## Sign out and uninstall

Signing out tells the Hub first, so the device's key stops working everywhere. It then removes what Swangz added
to the computer, even when offline. If the Hub could not be reached, ask an admin to disconnect the device in the
control room.

| | Sign out | Uninstall |
|---|---|---|
| **Windows** | In the app: This device → **Sign out and remove Swangz from this device** | Settings → Apps → Installed apps → Swangz → Uninstall. The uninstaller stops a running Swangz, runs `Swangz.exe logout`, and then removes the program, the shortcuts, the start-at-sign-in entry and the Apps & features entry |
| **macOS** | In the app: This device → **Sign out and remove Swangz from this device**. In Terminal: `/Applications/Swangz.app/Contents/MacOS/Swangz logout` (`swangz` is not on PATH on a Mac) | Sign out first, then drag Swangz from Applications to the Bin. Signing out removes the login item |
| **Older copy refused (macOS, exit 5)** | Choose **Sign out** in the refusal dialog, or run the Terminal command above | Then install the newer build |

After sign-out the data folder keeps only `browser-profiles`. This is by design (R-12): each company-browser
profile stays bound to its owner.

## Artifacts and checksums

CI or Chief fills in this table from the release run's `SHA256SUMS` and `.sha256` files. Use only the run for the
exact release commit above.

| Artifact | CI artifact | SHA-256 |
|---|---|---|
| `Swangz-Setup-<version>-UNSIGNED.exe` | `Swangz-Windows-installer-RC-UNSIGNED` | `<sha256>` |
| `Swangz-<version>.cdx.json` (Windows SBOM, CycloneDX 1.5) | `Swangz-Windows-installer-RC-UNSIGNED` | `<sha256>` |
| `RELEASE-LABEL.txt` | `Swangz-Windows-installer-RC-UNSIGNED` | `<sha256>` |
| `Swangz-<version>-RC-UNSIGNED-macos-arm64.dmg` | `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` | `<sha256>` |
| `Swangz-<version>-macos.cdx.json` (macOS SBOM, CycloneDX 1.5) | `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY` | `<sha256>` |

The acceptance evidence is in separate artifacts: `Swangz-Windows-installer-evidence`, and the `evidence/` folder
inside the macOS artifact. CI artifacts are kept for 14 days.
