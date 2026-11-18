# The Swangz app on macOS: building, signing, notarization and Gatekeeper

**Status (17 Nov 2026): the macOS build is an UNSIGNED release candidate, `RC — UNSIGNED — INTERNAL TEST ONLY`.**
It is built, installed, launched, enrolled, restarted, upgraded and uninstalled on GitHub's `macos-latest` runner
(`.github/workflows/build-macos.yml`). It is **not** signed with a Swangz Developer ID and **not** notarized by
Apple, so it must not be given to staff, and it must not be called production-ready.

## What is built today

| Step | Where | Result |
|---|---|---|
| `Swangz.app` | `packaging/macos_dmg.py` → `packaging/build.py` (PyInstaller, pinned in the workflow) | a one-folder app bundle, `com.swangzavenue.swangz`, version from `swangz_client/__init__.py`, macOS 11 or later |
| Signature | `codesign --sign -` | **ad hoc only** — what Apple silicon needs to run any program. It identifies nobody and Gatekeeper refuses it |
| DMG | `hdiutil create -format UDZO` (built into macOS; no third-party DMG tool) | `Swangz-<version>-RC-UNSIGNED-macos-<arch>.dmg`: the app, an Applications link and `READ ME FIRST.txt` with the RC notice |
| Checksum | `shasum -a 256` | `<dmg>.sha256` and `SHA256SUMS`, checked in the workflow |
| Journey | `packaging/macos_journey.py` | install from the DMG, launch, enrol (code approved in the person's browser), restart, upgrade from the previous build, sign out (server shows the device disconnected, keychain item and data removed), remove the app. Log, step table and screenshots are uploaded as evidence |

The journey also runs `spctl --assess` and **expects it to refuse** the build. That refusal is the correct
behaviour for an unsigned app; it is recorded, never worked around.

## CI evidence

The workflow runs on every pull request that touches the app or packaging, on every push to `main` with the same
paths, and by hand (`workflow_dispatch`). Each run uploads the artifact `swangz-macos-RC-UNSIGNED-INTERNAL-TEST-ONLY`
(kept 14 days): the DMGs, `<dmg>.sha256`, `SHA256SUMS`, and `evidence/` (`journey.log`, `journey.json`, the three
screenshots, both self-check reports and `SUMMARY.md`). The same summary — label, commit, runner, PyInstaller
version, verdict, checksums and the step table — is written to the run's page (`packaging/macos_summary.py`), so the
SHA-256 can be read without downloading anything. Nothing is published as a GitHub release by this workflow.

Last recorded pass (run `44178445822`, PR #244): 29 journey steps passed, from install from the DMG to the app being
removed. `Swangz-0.1.3-RC-UNSIGNED-macos-arm64.dmg`, SHA-256
`2c866b3845e392f2581a31a1fb5352cb85fb12b923955b566324baaeefdd6014`. Re-check any copy with
`shasum -a 256 -c SHA256SUMS` before installing it.

What the journey shows, and what it does not:

- After sign out only `browser-profiles` may remain in `~/Library/Application Support/Swangz/`. That is deliberate
  (R-12): each company-browser profile is bound to its owner and wiped when it is reassigned, not on sign out. The
  journey fails if anything else is left, or if a Swangz process is still running after the app is removed.
- Sign out turns start at login off: `Swangz logout` removes `com.swangzavenue.swangz.plist`, and the journey
  checks it exists before sign out and is gone after it (no `autostart off` first).
- The runner is a fresh virtual Mac (Apple silicon). It does not show a downloaded, quarantined copy opening, an
  Intel Mac, or a person's real keychain prompts; those need item 6 below.

## What is never done

- No `xattr -d com.apple.quarantine`, no `spctl --master-disable` / `--add`, no instructions telling staff to
  right-click → Open or use *Open Anyway*, no MDM profile that turns Gatekeeper off. The CI journey installs a
  DMG built on the same runner, which carries no quarantine flag because it was never downloaded; that is a
  property of the test, not a workaround, and it does not show that a downloaded copy would open.
- No signing identity, certificate, Apple ID or password in the repository, a log or an artifact.

## What signing and notarization need (all Arnold's)

These are owner-only items for `docs/RELEASE-OWNER-CHECKLIST.md`. Nothing below can be faked or substituted.

1. **Apple Developer Program membership for Swangz Avenue as an organization** (not a personal account), so the
   certificate reads "Swangz Avenue". Enrolment needs the company's D-U-N-S number and someone with legal
   authority to sign for it. Apple charges a yearly fee (spending money: Arnold's decision).
2. **A Developer ID Application certificate** created in that account, exported as a `.p12` with a strong
   password. Keep the private key off shared machines. (A *Developer ID Installer* certificate is only needed if
   we ship a `.pkg`; the DMG does not.)
3. **Notarization credentials**, one of:
   - an App Store Connect API key (`.p8` file, key ID, issuer ID) with the Developer role — preferred for CI; or
   - the Apple ID, an app-specific password and the Team ID.
4. **Repository secrets** holding them, added by Arnold in GitHub → Settings → Secrets:
   `MACOS_CERT_P12_BASE64`, `MACOS_CERT_PASSWORD`, `MACOS_KEYCHAIN_PASSWORD` (any random value for the temporary
   keychain), `MACOS_NOTARY_KEY_P8_BASE64`, `MACOS_NOTARY_KEY_ID`, `MACOS_NOTARY_ISSUER_ID`, `MACOS_TEAM_ID`.
5. **Confirmation of the bundle identifier** `com.swangzavenue.swangz` (it cannot change after people install it
   without macOS treating it as a different app and its keychain item as someone else's).
6. **A physical-Mac acceptance run** on a signed, notarized build (Apple silicon, and Intel if Swangz still has
   Intel Macs): download the DMG through a browser so it is quarantined, open it, drag to Applications, open it
   with no warning beyond the normal "downloaded from the internet" prompt, enrol, restart, upgrade, sign out.

## The signed pipeline (to add once the secrets exist)

Replace the ad hoc step in `packaging/macos_dmg.py` with these, in this order, in a job that runs only when the
secrets are present (pull requests from forks never see them):

```bash
# 1. a temporary keychain holding the certificate, removed at the end of the job
security create-keychain -p "$MACOS_KEYCHAIN_PASSWORD" build.keychain
security set-keychain-settings -lut 21600 build.keychain
security unlock-keychain -p "$MACOS_KEYCHAIN_PASSWORD" build.keychain
echo "$MACOS_CERT_P12_BASE64" | base64 --decode > cert.p12
security import cert.p12 -k build.keychain -P "$MACOS_CERT_PASSWORD" -T /usr/bin/codesign
security set-key-partition-list -S apple-tool:,apple: -s -k "$MACOS_KEYCHAIN_PASSWORD" build.keychain
rm cert.p12

# 2. sign every binary inside the bundle, then the bundle: hardened runtime, secure timestamp
codesign --force --options runtime --timestamp --entitlements packaging/macos.entitlements \
         --sign "Developer ID Application: Swangz Avenue (TEAMID)" Swangz.app/Contents/Frameworks/... Swangz.app
codesign --verify --deep --strict --verbose=2 Swangz.app

# 3. build the DMG from the signed app, sign the DMG
hdiutil create ... Swangz-<version>-macos-<arch>.dmg
codesign --timestamp --sign "Developer ID Application: Swangz Avenue (TEAMID)" Swangz-<version>-macos-<arch>.dmg

# 4. notarize and staple (the ticket travels with the DMG, so it opens offline too)
xcrun notarytool submit Swangz-<version>-macos-<arch>.dmg --key AuthKey.p8 --key-id "$MACOS_NOTARY_KEY_ID" \
      --issuer "$MACOS_NOTARY_ISSUER_ID" --wait
xcrun stapler staple Swangz-<version>-macos-<arch>.dmg

# 5. prove it: these must PASS (today they are expected to fail)
xcrun stapler validate Swangz-<version>-macos-<arch>.dmg
spctl --assess --type open --context context:primary-signature --verbose=2 Swangz-<version>-macos-<arch>.dmg
spctl --assess --type execute --verbose=2 /Applications/Swangz.app   # after installing from the DMG
```

Notes for whoever does this:

- PyInstaller's one-folder bundle contains many `.so`/`.dylib` files and the Python framework; each must be
  signed with the same identity, hardened runtime and timestamp, inside-out. `codesign --deep` is not enough for
  notarization; sign the nested code explicitly (PyInstaller's own `--codesign-identity` and
  `--osx-entitlements-file` options do this when given the identity).
- The entitlements file is not in the repo yet. Start with **none**; add only what a signed build is shown to
  need on a real Mac (for embedded Python this is sometimes `com.apple.security.cs.allow-unsigned-executable-memory`),
  and record why in the PR. Every entitlement weakens the hardened runtime; Sentinel reviews each one.
- If notarization is refused, `xcrun notarytool log <id>` says which file and why. Fix the build; never ship the
  refused artifact.
- Remove the temporary keychain at the end of the job (`security delete-keychain build.keychain`), also on failure.
- Once signed, drop "UNSIGNED" from the file names in `packaging/macos_dmg.py` and the "expected refusal" check in
  `packaging/macos_journey.py` becomes an expected **pass**. Keep the RC label until the physical-Mac acceptance
  (item 6) has passed.

## Updates

Desktop auto-update stays **off** until builds are signed and the app verifies the signature of what it
downloads (the status line "Updates unavailable: no pinned release key" says so). An unsigned RC never updates
itself; a newer RC is installed by hand from its DMG, which the journey's upgrade step covers. A person's data
(`~/Library/Application Support/Swangz`) and keychain item live outside the bundle, so replacing the app keeps
the sign-in.

## Where the app keeps things on a Mac

| What | Where | Removed by Sign out |
|---|---|---|
| Device key | login keychain, service "Swangz AI Hub" (a protected file only if the keychain does not work) | yes |
| Device record, state, manifest, packages | `~/Library/Application Support/Swangz/` | yes |
| Start at login | `~/Library/LaunchAgents/com.swangzavenue.swangz.plist` (only when turned on) | yes (sign out turns start at login off; the journey checks the file is gone) |
| The app | `/Applications/Swangz.app` | dragged to the Bin by the person |
