# Swangz for macOS: signing, notarization and Gatekeeper

**Status: RC — UNSIGNED — INTERNAL TEST ONLY.** The CI builds an unsigned app. It is not a production installer.

## What CI builds

`.github/workflows/release-macos.yml` runs on `macos-latest` (Apple Silicon, arm64), on every PR that touches packaging, and on demand.

| File | What it is |
|---|---|
| `Swangz-<version>-macOS-arm64-UNSIGNED.dmg` | Compressed, read-only disk image. It holds `Swangz.app`, a link to `/Applications` and `READ ME FIRST.txt`. |
| `Swangz-<version>-macOS-arm64-UNSIGNED.app.zip` | The same app as a zip (`ditto`), which is the format notarization takes. |
| `*.sha256`, `SHA256SUMS` | SHA-256 of each file. These check that a copy arrived intact; they are not a signature. |
| `release-macos.json` | Version, architecture and checksums. |

The steps, all in `packaging/macos.py` and using only tools that ship with macOS:

1. `packaging/build.py` builds `Swangz.app` with PyInstaller 6.22.3 (pinned in the workflow) and Python 3.12.
2. `macos.py stamp` writes the version into `Info.plist`: `CFBundleShortVersionString` = `swangz_client.__version__`, `CFBundleVersion` = the commit count, plus identifier `com.swangzavenue.swangz`, minimum macOS 11 and an UNSIGNED label. It then re-applies the **ad-hoc** seal (`codesign -s -`). Apple Silicon will not run a binary without a seal; an ad-hoc seal identifies no publisher and Gatekeeper does not trust it.
3. `packaging/smoke.py` runs the built app against a gateway started in CI: device code, approval in the browser page, sync, extension install, status, sign-out and server-side revocation.
4. `macos.py dmg` makes the DMG and zip, verifies the image (`hdiutil verify`) and writes the checksums.
5. `macos.py verify-dmg` installs the way a person would:
   - checks the checksum;
   - mounts the image read-only and checks its contents;
   - copies the app out;
   - checks `Info.plist` and the seal (`codesign --verify --deep --strict`);
   - **records Gatekeeper's verdict (`spctl --assess`), which must be a refusal**;
   - runs the installed copy's `--version` and `--self-check`, which opens the real window and confirms updates are off.

   The evidence is `smoke-results/macOS-dmg.json` and the job summary.

**Not built:** an Intel (x86_64) or universal build. A universal build needs a universal Python and a second PyInstaller pass; it's left until Arnold confirms whether Intel Macs need supporting.

## What a person sees with this build

Downloaded through a browser, the app carries the quarantine flag. macOS then refuses it: *"Swangz" can't be opened because Apple cannot check it for malicious software* (macOS 15 and later: *"Swangz" Not Opened*). **That is correct, and nobody should work around it.** Not with right-click → Open, not with *Open Anyway* in System Settings, not with `xattr` or `spctl`, and not by switching Gatekeeper off. The build is for internal testing on CI runners and on test Macs that Swangz IT chooses, until the signed build exists.

## What a production build needs (Arnold's items)

Each item is on `docs/RELEASE-OWNER-CHECKLIST.md`. None of them can be done by the team.

1. **Apple Developer Program membership** for Swangz Avenue as an organisation (yearly fee, D-U-N-S number).
2. **A Developer ID Application certificate**, created by the Account Holder. Export it as a `.p12` and keep it only in GitHub Actions secrets (`MACOS_CERT_P12`, `MACOS_CERT_PASSWORD`) in a protected `release` environment that needs approval. Never commit it to the repo or put it on the laptop.
3. **Notarization credentials:** an App Store Connect API key (`.p8`, key ID, issuer ID) with the Developer role, kept in the same secrets.
4. **Approval to sign:** signing and publishing stay Arnold's decision.

## The signed pipeline (to add once the items exist)

Add these steps to `release-macos.yml` after `stamp`, in a job that runs only in the protected environment:

```sh
# temporary keychain on the runner, deleted at the end of the job
security create-keychain -p "$KC_PASS" build.keychain
security import cert.p12 -k build.keychain -P "$MACOS_CERT_PASSWORD" -T /usr/bin/codesign
codesign --force --deep --options runtime --timestamp \
  --entitlements packaging/macos-entitlements.plist \
  --sign "Developer ID Application: Swangz Avenue (TEAMID)" dist/Swangz.app
ditto -c -k --keepParent dist/Swangz.app Swangz.zip
xcrun notarytool submit Swangz.zip --key key.p8 --key-id "$ID" --issuer "$ISSUER" --wait
xcrun stapler staple dist/Swangz.app
# then build the DMG, sign the DMG, notarize and staple it as well
spctl --assess --type execute -vv dist/Swangz.app   # must now say: accepted, source=Notarized Developer ID
```

Notes:
- **Hardened runtime** (`--options runtime`) is required for notarization. PyInstaller apps usually need `com.apple.security.cs.allow-unsigned-executable-memory` and possibly `com.apple.security.cs.disable-library-validation`. Add only what the notarized build is proven to need, and record each entitlement in the PR.
- **When signing exists,** `verify-dmg` changes its Gatekeeper check from "must refuse" to "must accept as Notarized Developer ID". The unsigned and signed artifacts keep different names, so one is never mistaken for the other.
- **Updates stay disabled** (`release_keys.ENABLED = False`, no production keys) until signed builds and a verified update channel exist. Code-signing the app doesn't change that.

## Reproducibility

The build pins Python 3.12, PyInstaller 6.22.3, `PYTHONHASHSEED=0` and `SOURCE_DATE_EPOCH`, so the same commit produces the same app contents. The DMG and the seal are **not** byte-for-byte identical between builds, because HFS+ timestamps and signing time vary. So compare builds by the app's file list and the version in `Info.plist`, not by the DMG's checksum. The checksums say which file was shipped, not that two builds match.

## Not proven by CI

These still need a physical Mac, done by Arnold or Swangz IT:
- what a person sees on a real Mac with a quarantined download;
- the Keychain prompt for the device key;
- start at login;
- upgrading over an earlier RC;
- removing the app and its data folder.

The runner proves the build, the install from the image and the launch only.
