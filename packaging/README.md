# Packaging the Swangz app

`python3 packaging/build.py` makes a standalone program for the computer you run it on (PyInstaller; Python
with Tk needed to *build*, nothing to *run*). Verified on Linux (a single ~7 MB `dist/Swangz`: `--version`,
`status`, a full sign-in / sync / sign-out against a real gateway, and the window). Windows and macOS builds use
the same script but have **not** been built or run yet — they need those operating systems (a runner or a
machine) and, to avoid "unknown publisher" warnings, certificates only Swangz can hold:

| | Needs | Produces |
|---|---|---|
| Windows | a Windows runner/machine; a code-signing certificate (an EV certificate avoids the SmartScreen warning) | `Swangz.exe` → wrap in an installer (Inno Setup or WiX) and sign both |
| macOS | a Mac runner/machine; an Apple Developer ID and notarization | `Swangz.app` → `.dmg`, signed and notarized (`codesign`, `notarytool`) |
| Linux | any Linux with `python3-tk` | `Swangz` → AppImage or `.deb` |

`.github/workflows/build-app.yml` builds all three on GitHub's runners and attaches the unsigned results to a
manual run, so the Windows and macOS builds can be tried without a machine of each. Signing steps are left as
comments, to be filled in with the certificates as repository secrets.
