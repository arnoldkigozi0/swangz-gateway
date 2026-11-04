# Packaging the Swangz app

`python packaging/build.py` uses the existing PyInstaller dependency and Python with Tk.
It builds for the host OS only; the output carries its own Python. Heavy builds run on
GitHub Actions, not the team laptop.

| Runner | Standalone app | Download archive |
|---|---|---|
| Linux | `dist/Swangz` | `Swangz-UNSIGNED-TEST-Linux-<arch>.tar.gz` |
| Windows | `dist/Swangz.exe` | `Swangz-UNSIGNED-TEST-Windows-<arch>.zip` |
| macOS | `dist/Swangz.app` | `Swangz-UNSIGNED-TEST-Darwin-<arch>.tar.gz` |

These are **UNSIGNED-TEST** artifacts for internal verification, not production installers.
No publisher certificate, Developer ID, notarization, production release key or signing secret
is used. PyInstaller may apply the ad-hoc signature required by macOS; that is not a trusted
publisher signature. OS warnings are expected. Updates remain disabled (`ENABLED=False`,
empty pinned release keys). The archives include SHA-256 sidecars for transfer integrity;
these are not authenticated update signatures. Tar preserves executable modes and `.app`
symlinks inside GitHub's artifact download ZIP. Extract the inner archive before running.

## Actions build and smoke

Dispatch **Build the Swangz app** (`build-app.yml`) with the desired feature branch as its
ref, for example:

```sh
gh workflow run build-app.yml --ref feature/desktop-distribution
```

Each Linux, Windows and macOS runner builds with Python 3.12 and PyInstaller, recording
their actual versions. `packaging/smoke.py` starts the built executable from a temporary
working directory without source Python paths. It uses the existing isolated gateway and
`tests/fake_upstream.py`; all identities, credentials and provider keys are test fixtures.
No external provider is contacted, and no credential backend is mocked in the executable.
The browser launch is redirected to a no-op process; the driver approves the code using
the real local gateway's authenticated device page.

The smoke checks:

- `--version` exits successfully; fresh `status` exits 2.
- `--self-check REPORT.json` imports the frozen client, reads state, renders and destroys
  the actual sign-in window, and reports the bundled version/Tk and disabled update gates.
  Linux uses the existing Xvfb tool. This bounded offline command does not install or
  acknowledge an update. Its report contains no credential or device metadata.
- Packaged `login` requests a device code, receives real fixture-page approval and syncs.
- A second packaged `sync` advances state, installs the local access extension and records
  a gateway heartbeat. Signed-in `status` succeeds, including a credential read.
- Packaged `logout` revokes the server key and removes local credentials and the extension;
  subsequent `status` exits 2. Keychain mode or explicit file fallback is recorded honestly.

Windows' windowed app has no console streams; absent streams go to the null device, never
a persistent log (especially the credential helper pipe). Exit codes, gateway records and
the self-check file provide evidence there. This is a bounded headless smoke, not exhaustive
GUI, native credential-service, SmartScreen/Gatekeeper or installer verification.

Only a passing smoke produces an app artifact. Each OS also uploads its safe JSON smoke
report, including failures when available. All artifacts expire after seven days. This
manual workflow does not publish a release, deploy anything or run the Python suite.

Local suite/build checks are intentionally not run under Codex: fake servers cannot bind
ports there and the laptop is reserved for light work. Actions is the cross-platform
execution authority; Probe provides independent verification of exact commits.

## Decisions for Arnold before production distribution

Installer formats and their additional tools remain undecided: Windows installer (for
example NSIS/WiX/Inno Setup), Linux `.deb`/AppImage, and macOS `.dmg`. None is added by
this workflow. Approve the tool choice and pinned PyInstaller dependency hashes before
production packaging. Publisher certificates, Apple Developer ID/notarization, the release
signing ceremony and enabling updates are separate approval gates. Do not bypass OS
security controls to distribute these test builds.
