# Packaging the Swangz app

`python packaging/build.py` uses the existing PyInstaller dependency and Python with Tk.
It builds for the host OS only; the output carries its own Python. Heavy builds run on
GitHub Actions, not the team laptop.

| Runner | Standalone app | Download archive |
|---|---|---|
| Linux | `dist/Swangz` | `Swangz-UNSIGNED-TEST-Linux-<arch>.tar.gz` |
| Windows | `dist/Swangz.exe` | `Swangz-UNSIGNED-TEST-Windows-<arch>.zip` |
| macOS | `dist/Swangz.app` | `Swangz-UNSIGNED-TEST-Darwin-<arch>.tar.gz`; the DMG below |

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

## macOS: Swangz.app and the DMG (release sprint, 17 Nov 2026)

`python3 packaging/macos_dmg.py` (on a Mac) builds `dist/Swangz.app` and
`dist/Swangz-<version>-RC-UNSIGNED-macos-<arch>.dmg` with a `.sha256` beside it, using only
PyInstaller (pinned in the workflow) and tools every Mac has (`plutil`, `codesign` ad hoc,
`ditto`, `hdiutil`, `shasum`). `.github/workflows/build-macos.yml` builds it on `macos-latest`
for every pull request touching the app, and `packaging/macos_journey.py` installs it from the
DMG, launches it, enrols it against a CI gateway, restarts, upgrades from a previous build and
uninstalls it, uploading the log, step table and screenshots. Everything is labelled
`RC — UNSIGNED — INTERNAL TEST ONLY`. Developer ID signing, notarization, Gatekeeper and what only
Arnold can provide: `docs/MACOS-SIGNING.md`.

## Decisions for Arnold before production distribution

Installer formats and their additional tools remain undecided: Windows installer (for
example NSIS/WiX/Inno Setup), Linux `.deb`/AppImage, and macOS `.dmg`. None is added by
this workflow. Approve the tool choice and pinned PyInstaller dependency hashes before
production packaging. Publisher certificates, Apple Developer ID/notarization, the release
signing ceremony and enabling updates are separate approval gates. Do not bypass OS
security controls to distribute these test builds.

## Windows installer (RC — UNSIGNED — INTERNAL TEST ONLY)

`packaging/windows/swangz.iss` (Inno Setup) wraps `dist\Swangz.exe`; `.github/workflows/release-windows.yml`
builds it on `windows-latest` with pinned build tools (PyInstaller, Inno Setup 6.4.3 from its official release, checked against a SHA-256 pin) on every pull request
that touches `packaging/`, `swangz_client/` or the workflow, and on manual dispatch.

The installer:
- installs per person, with no administrator rights, into `%LOCALAPPDATA%\Programs\Swangz`. Nothing machine-wide is
  changed and no Windows security setting is touched;
- adds a Start-menu entry. Two optional tasks are off by default: a desktop shortcut, and starting Swangz at sign-in
  (the HKCU `Run` value `Swangz`, the same one the app's own switch uses);
- carries no key or secret. Sign-in starts with `https://hub.ictconnect.org`, which the person can change;
- installs no updater and schedules nothing. In-app updates stay off (`release_keys.ENABLED = False`) until signed
  releases exist;
- uninstalls by first stopping the person's own running Swangz (started at sign-in, it would hold the program open),
  then running `Swangz.exe logout`, which tells the Hub to disconnect the device and removes what Swangz
  put on the computer, even offline. It then removes the program, the shortcuts, the `Run` value and the Apps & features
  entry. Installing again over an existing install closes a running copy and keeps the person's device and settings.

The artifact is `Swangz-Setup-<version>-UNSIGNED.exe` plus a `.sha256` file, `RELEASE-LABEL.txt` and a CycloneDX SBOM
(`Swangz-<version>.cdx.json`, `packaging/sbom.py`; the job fails if a third-party Python package is found in the program
or the official `cyclonedx-cli` rejects the file). The macOS job ships `Swangz-<version>-macos.cdx.json` beside the DMG and
runs the same secret scan over the app and its journey logs.

`packaging/windows/installer_e2e.py` is the acceptance run on the runner. It does: silent install, launch (self-check
window, `--background` start), enrol against the test suite's local Hub, restart, network interruption and recovery
(through a local relay the script cuts and restores), an upgrade to this build while the program runs, then silent
uninstall while it runs, checking the device key is gone from Windows Credential Manager. Steps 1-5 run on the previous
build: the version in the tree (never below the server's minimum client version), built first as a test input and never
uploaded. This build raises PATCH by the run number (0.1.100 -> 0.1.<100 + run>), the same scheme as the macOS journey. The
upgrade must keep the device, its key and its Credential Manager entry, need no new sign-in, and show the new version in
Apps & features and in the Hub's check-in record. The previous installer is then run over this build and must be refused (exit code 1, the reason in its log, nothing
changed): `swangz.iss` refuses to replace a newer installed version, while reinstalling the same version and upgrading still work. Without `--previous`, step 6 reinstalls the same version. Its `report.json`
and the installer's and uninstaller's logs are uploaded as the `Swangz-Windows-installer-evidence` artifact.

Not covered by CI: SmartScreen (the installer is unsigned, so Windows warns "unknown publisher" until Swangz signs it
with its own certificate), a real reboot (a restart of the program stands in for one), and Windows on physical devices.
These stay on the owner checklist.

Each run also builds the program and installer a second time from the same tree and compares them byte for byte
(`packaging/reproducible.py`, with `SOURCE_DATE_EPOCH` = the commit time). The measured result and its scope are in
`packaging/RELEASE-NOTES-RC.md`. The company build below is not part of that comparison.

## Company installer (company computers, RC — UNSIGNED — INTERNAL TEST ONLY)

The installer above is for a person's own computer and does not change. A company computer can have the company build
instead (`docs/DECISIONS.md` D-026 B4, B5, B7):

- `python packaging/build.py --company` (Windows only) builds a PyInstaller **one-folder** program,
  `dist-company\Swangz\` (`Swangz.exe` and `_internal`). A one-file program unpacks itself into the person's `%TEMP%`
  on every start, where that person's other programs can replace what it loads.
- `packaging/windows/swangz-company.iss` wraps that folder as `Swangz-Company-Setup-<version>-UNSIGNED.exe`. It has its
  own application identity, so it never overwrites or uninstalls a person's own install.

An administrator installs it from an elevated prompt:

```
Swangz-Company-Setup-<version>-UNSIGNED.exe /ALLUSERS /HUBHOST=<Hub host name> /EXTENSIONID=<32 letters a-p> /EXTENSIONUPDATEURL=<https update address>
```

- Without `/ALLUSERS` it refuses to run. It installs into `%ProgramFiles%\Swangz` and refuses any other folder, so only
  administrators can change the program.
- The three values are recorded in `HKLM\Software\Swangz\Pinned` (64-bit view) as `hub_host`, `extension_id` and
  `extension_update_url`. Pass all three or none: some of them is refused, and an upgrade without them keeps the
  recorded ones. The installer only checks that they were typed whole. `deploy/chrome-policy/prepare.py` decides
  whether they are acceptable, when the policy step that reads them exists.
- An older version never replaces a newer one. An upgrade removes the previous `_internal` folder first.
- It adds a Start-menu entry for everyone and an optional desktop shortcut. It does not start the app, add a start-up
  entry or a service, install a browser or write any Chrome policy.
- Uninstalling stops every running copy and removes the program, the shortcuts and the recorded values. **It does not
  sign anyone out**, because that would run the app with administrator rights over files a person can edit. Each person
  signs out in the app first, or an administrator disconnects the device in the console. Data under each person's
  profile, including the Swangz browser folders, stays on the computer, as does a person's own "Start with Windows"
  entry if they switched it on.

Not built yet: the app does not read the recorded values, does not offer any administrator step, and the per-person app
does not yet tell people to ask for the company build. A person's own install on the same computer is left in place;
remove it from that person's account before using the company one.

The same workflow builds both company files (the installer and its `.sha256`, with a CycloneDX SBOM
`Swangz-Company-<version>.cdx.json`) and runs `packaging/windows/company_e2e.py` on the runner: refused without
`/ALLUSERS`, with some of the values and into another folder; installed with the values; the owner and write
permissions of every installed item; the installed program's self-check; upgrade, refused downgrade and uninstall. The
runner is already an administrator, so the Windows consent prompt and a standard user's attempts to change the files
are not exercised. That needs a physical computer.
