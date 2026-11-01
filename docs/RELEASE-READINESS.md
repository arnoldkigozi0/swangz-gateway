# Swangz AI Hub — release readiness

**Status:** not ready for internal beta distribution yet. This is the initial release checkpoint for
the 2–16 November 2026 execution window, based on main `ba82a2a`.

## Evidence present

- PR #6 native business workflows, PR #7 VPS hardening and PR #8 installed desktop client are merged.
- Latest main GitHub Actions **Hub checks** run 13 succeeded on 31 October 2026.
- GitHub's available 13-run history contains only `Hub checks`; `.github/workflows/build-app.yml` has
  not been run in that history, so no current Windows/macOS/Linux artifacts were verified here.
- Local Python baseline: **426 tests passed, 13 skipped, 503.976s** on Python 3.14. The first run was
blocked by sandbox loopback restrictions; the successful run used fake local services.
- Linux standalone desktop app had previously passed a smoke and end-to-end gateway journey, per
`docs/STATE.md` and `packaging/README.md`.
- Hub PWA manifest/install support and synthetic browser workflow coverage exist.

## Release gates not yet passed

- G2 Sentinel architecture/security approval for credential storage, update trust, client installation
and continuity.
- G3 OS keychain storage on Linux, Windows and macOS, with safe migration from `device.key`.
- G4 signed update integrity, rollback and recovery verified across supported platforms.
- G5 current Windows/macOS/Linux CI package artifacts and install smoke checks; production signing is
unavailable until required account/certificate access is verified.
- G6 current cited provider compatibility/seat/SSO/billing matrix and independent QA. Live tests are
not evidenced; do not treat fake-provider success as vendor verification.
- G7 current mobile PWA install/device checks and written native packaging decision.
- G8 independent security review, all required regression/browser/platform checks and actual results.
- G9 exact candidate commit/artifact inventory, operations/recovery, known issues and Arnold review.

## Distribution boundaries and decisions

- Unsigned packages, if CI produces them, are **test-only** and must be labelled as such. A checksum by
  itself does not establish Swangz publisher identity. Do not call any installer signed until the target
  operating system verifies its signature and (macOS) notarization.
- Windows Authenticode and macOS Developer ID/notarization account access remain unverified. Arnold
  must confirm existing authorized credentials are available before the team prepares signing. No
  purchase or account change is authorized here.
- Native Android/iOS app stores are not in scope for this beta. The current mobile product is the PWA;
  no app-store-readiness claim is supported.
- No provider cost, new subscription or live-provider test has been authorized by this checkpoint.
- No production deploy, DNS/callback change, production migration/import, merge or release publication
  is part of this work without Arnold's separate explicit approval.

## Remaining risks

1. App credential compromise risk remains higher than desired while the device key is a local file.
2. No app-binary signature verification or self-update currently protects installed clients.
3. Cross-platform support is still an implementation claim for Windows/macOS until real CI artifacts
   and target-OS smoke/installation results exist.
4. Swangz authentication is not provider authentication. Provider sign-in, company-seat terms and spend
   attribution must be explicit per tool.
5. The local Python 3.14 baseline emitted resource cleanup warnings. They did not fail tests; triage
   separately if Sentinel/Probe judges them security- or reliability-relevant.

Update this checklist with exact commits, links and raw test outcomes at each G8/G9 checkpoint.
