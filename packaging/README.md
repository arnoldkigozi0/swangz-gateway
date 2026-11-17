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
When the runner has no IANA timezone database (Windows), the driver supplies a
temporary fixed EAT/UTC+03:00 TZif fixture for the gateway. It is not shipped in the
client and does not verify historical timezone rules or require a tzdata dependency.

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

Execution record (4 November 2026): [initial Actions run 41814355423](https://github.com/arnoldkigozi0/swangz-gateway/actions/runs/41814355423)
at `c47a874` built all three apps. Linux x86_64 and macOS arm64 passed all seven
smoke steps and uploaded test artifacts; storage was `file` and `keychain`, respectively.
Windows failed before starting the app because the gateway fixture lacked IANA timezone
data. The fixed EAT fixture corrects that setup issue; its format decoded locally as
UTC+03:00. A follow-up Actions run is required for Windows and the corrected head.
The full Python suite and exhaustive browser/manual desktop checks were not run here.

## Decisions for Arnold before production distribution

Installer formats and their additional tools remain undecided: Windows installer (for
example NSIS/WiX/Inno Setup), Linux `.deb`/AppImage, and macOS `.dmg`. None is added by
this workflow. Approve the tool choice and pinned PyInstaller dependency hashes before
production packaging. Publisher certificates, Apple Developer ID/notarization, the release
signing ceremony and enabling updates are separate approval gates. Do not bypass OS
security controls to distribute these test builds.

## Windows installer (RC — UNSIGNED — INTERNAL TEST ONLY)

`packaging/windows/swangz.iss` (Inno Setup) wraps `dist\Swangz.exe`; `.github/workflows/windows-installer.yml`
builds it on `windows-latest` with pinned build tools (PyInstaller, Inno Setup via Chocolatey) on every pull request
that touches `packaging/`, `swangz_client/` or the workflow, and on manual dispatch.

The installer:
- installs per person, with no administrator rights, into `%LOCALAPPDATA%\Programs\Swangz`. Nothing machine-wide is
  changed and no Windows security setting is touched;
- adds a Start-menu entry. Two optional tasks are off by default: a desktop shortcut, and starting Swangz at sign-in
  (the HKCU `Run` value `Swangz`, the same one the app's own switch uses);
- carries no Hub address, key or secret: the person types the Hub address at first run;
- installs no updater and schedules nothing. In-app updates stay off (`release_keys.ENABLED = False`) until signed
  releases exist;
- uninstalls by first running `Swangz.exe logout`, which tells the Hub to disconnect the device and removes what Swangz
  put on the computer, even offline. It then removes the program, the shortcuts, the `Run` value and the Apps & features
  entry. Installing again over an existing install keeps the person's device and settings.

The artifact is `Swangz-Setup-<version>-UNSIGNED.exe` plus a `.sha256` file and `RELEASE-LABEL.txt`.

`packaging/windows/installer_e2e.py` is the acceptance run on the runner. It does: silent install, launch (self-check
window, `--background` start), enrol against the test suite's local Hub, restart, network interruption and recovery
(through a local relay the script cuts and restores), install over the top, then silent uninstall. Its `report.json`
and the installer's and uninstaller's logs are uploaded as the `Swangz-Windows-installer-evidence` artifact.

Not covered by CI: SmartScreen (the installer is unsigned, so Windows warns "unknown publisher" until Swangz signs it
with its own certificate), a real reboot (a restart of the program stands in for one), and Windows on physical devices.
These stay on the owner checklist.
