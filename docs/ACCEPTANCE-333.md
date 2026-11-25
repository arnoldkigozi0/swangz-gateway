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
