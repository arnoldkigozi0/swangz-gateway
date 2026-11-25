# Swangz app: Windows release candidate notes

**RC — UNSIGNED — INTERNAL TEST ONLY.** This is not a production release. Nothing here may be described as
production-ready. Arnold approves any distribution beyond internal testing.

## What is built

| Artifact | Where | Notes |
|---|---|---|
| `Swangz-Setup-<version>-UNSIGNED.exe` | Actions artifact of `release-windows.yml` | per-person install, no administrator rights |
| `Swangz-Setup-<version>-UNSIGNED.exe.sha256` | same artifact | verify with `Get-FileHash -Algorithm SHA256` |
| `RELEASE-LABEL.txt` | same artifact | the label above, word for word |
| `Swangz-<version>.cdx.json` | same artifact | CycloneDX 1.5 SBOM: program hash, Python runtime, client modules, every bundled native file with its SHA-256, the hash-pinned build tools; validated by `cyclonedx-cli` |
| `Swangz-Windows-installer-evidence` | separate artifact | `report.json`, installer/uninstaller logs, `reproducible-program.json`, `reproducible-installer.json` |

The version is the tree's version with PATCH raised by the run number (0.1.100 becomes 0.1.<100 + run>).
Sign-in starts with `https://hub.ictconnect.org`, which the person can change. No key or secret is embedded.
In-app updates are off (`release_keys.ENABLED = False`) until signed builds exist.

## Build tools (pinned)

- Python 3.12 (`actions/setup-python`), PyInstaller 6.11.1. PR #255 installs PyInstaller and its dependencies
  from `packaging/requirements-windows-build.txt` with `--require-hashes --only-binary :all:`.
- Inno Setup 6.4.3 from its official GitHub release, checked against a SHA-256 pin before it runs.

## Reproducible builds: measured result

The job sets `SOURCE_DATE_EPOCH` to the commit time, builds the program and the installer, then builds both again from
the same tree in the same job and compares them byte for byte (`packaging/reproducible.py`).

- Before the fix (run 44397423996): the program differed only in the PE header time stamp, the PE checksum and the
  resource directory time stamp; every file inside the PyInstaller archive was identical. The installer differed
  because Inno Setup stamped each file with the compile time.
- The fix: `packaging/build.py` sets the PE header and resource time stamps to `SOURCE_DATE_EPOCH` and recomputes the PE
  checksum; `swangz.iss` sets `TouchDate=none` and `TouchTime=none` so files keep their own time.
- After the fix (run 44398806882): **program IDENTICAL**
  (`d7247778bc9f9b9b60f735d0ea32807f14f380e01d577b5bf1998e9b7d309e62`, both builds); **installer IDENTICAL**
  (`ad3ff2c53d631a3d0b10672b3fda19cadd1ccd44ede4404a84d250b7013cef58`, both builds).

Scope, honestly: proven for two builds in one job on one runner image. Not proven across different runners, runner
image updates or days; a future difference will show in the job summary and the JSON reports with its byte ranges.
Signing, when it comes, will change the bytes by design; compare unsigned builds.

## Acceptance evidence on the runner

`installer_e2e.py` installs the previous build (the tree's version), launches it, enrols against a local test Hub, restarts it,
cuts and restores the network, upgrades to this build while it runs (device, key and Credential Manager entry kept,
no new sign-in, new version in Apps & features and in the Hub's check-in), then uninstalls while it runs and checks the
device key is gone.

## Not verified

- SmartScreen and code signing: the installer is unsigned, so Windows warns "unknown publisher".
- Windows on physical devices, and a real reboot (a program restart stands in for one).
- The SBOM is generated from the program's own archive and checked against the CycloneDX 1.5 schema by the official
  `cyclonedx-cli` (pinned by SHA-256) in both the Windows and macOS jobs. That proves its shape, not that it is complete.
- macOS is covered by its own workflow and notes in `packaging/README.md`.

## Owner actions (Arnold)

- Buy a Windows code-signing certificate before any distribution beyond internal testing.
- Run the owner checklist in `docs/RELEASE-EVIDENCE.md` on a physical Windows PC.
