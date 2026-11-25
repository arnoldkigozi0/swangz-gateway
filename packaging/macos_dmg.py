"""Build the Swangz app for macOS into Swangz.app and a distributable .dmg, with a SHA-256 checksum.

    python3 packaging/macos_dmg.py                 # on a Mac: dist/Swangz.app, dist/Swangz-<v>-RC-UNSIGNED-macos-<arch>.dmg
    python3 packaging/macos_dmg.py --dry-run       # anywhere: print the steps without running them

UNSIGNED. The bundle carries only an ad-hoc signature (what Apple silicon needs to run any program at all), which
identifies nobody: Gatekeeper refuses it on a computer that downloaded it, and that is correct. Nothing here
bypasses or weakens Gatekeeper (no quarantine removal, no spctl changes). Developer ID signing and notarization
need Swangz's Apple Developer account: docs/MACOS-SIGNING.md says exactly what, and where the steps go.

Tools: PyInstaller (pip, pinned in the workflow) and what every Mac has — plutil, codesign, ditto, hdiutil, shasum.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def _load_build():
    """packaging/build.py by path: the folder name clashes with pip's own `packaging`, so it is not imported by name."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("swangz_packaging_build", Path(__file__).resolve().parent / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = _load_build()

LABEL = "RC — UNSIGNED — INTERNAL TEST ONLY"
BUNDLE_ID = "com.swangzavenue.swangz"
MIN_MACOS = "11.0"
README = f"""Swangz — {LABEL}

This is a release candidate for testing inside Swangz Avenue. It is NOT signed with a Swangz Developer ID and
NOT notarized by Apple, so macOS will refuse to open it when it was downloaded. Do not work around that on
staff computers. The signed build will open normally; see docs/MACOS-SIGNING.md in the project.

To install a signed build: drag Swangz onto Applications. To remove it: in Swangz choose "Remove Swangz from
this account" (or run `Swangz.app/Contents/MacOS/Swangz cleanup`, which signs out first), then drag Swangz from
Applications to the Bin. Each account on this Mac that used Swangz does this itself. Dragging it to the Bin alone
leaves the sign-in key and the saved browser sign-ins on the Mac.
"""


def app_version():
    ns = {}
    exec((ROOT / "swangz_client" / "__init__.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def arch():
    return {"arm64": "arm64", "x86_64": "x86_64"}.get(platform.machine(), platform.machine() or "unknown")


def dmg_name(version, machine):
    return f"Swangz-{version}-RC-UNSIGNED-macos-{machine}.dmg"


def volume_name(version):
    return f"Swangz {version} RC UNSIGNED"


def plist_values(version):
    """What Info.plist must say beyond PyInstaller's defaults (it writes 0.0.0 and no minimum system)."""
    return {"CFBundleShortVersionString": version, "CFBundleVersion": version, "CFBundleDisplayName": "Swangz",
            "CFBundleName": "Swangz", "CFBundleIdentifier": BUNDLE_ID, "LSMinimumSystemVersion": MIN_MACOS,
            "NSHighResolutionCapable": True, "LSApplicationCategoryType": "public.app-category.business",
            "NSHumanReadableCopyright": "Swangz Avenue. " + LABEL}


def steps(dist, work, version, machine):
    """The commands, in order. Each is a list run without a shell."""
    app = dist / "Swangz.app"
    plist = app / "Contents" / "Info.plist"
    stage = work / "dmg"
    dmg = dist / dmg_name(version, machine)
    out = [build.command(dist, work / "pyinstaller")]
    for key, value in plist_values(version).items():
        kind = "-bool" if isinstance(value, bool) else "-string"
        out.append(["plutil", "-replace", key, kind, ("YES" if value else "NO") if isinstance(value, bool) else value, str(plist)])
    out += [
        # The plist changed after PyInstaller's ad-hoc signature, so sign ad hoc again ("-" = no identity). This is
        # not Developer ID signing and does not satisfy Gatekeeper; docs/MACOS-SIGNING.md replaces it.
        ["codesign", "--force", "--deep", "--sign", "-", "--identifier", BUNDLE_ID, str(app)],
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
        ["ditto", str(app), str(stage / "Swangz.app")],
        ["ln", "-s", "/Applications", str(stage / "Applications")],
        ["hdiutil", "create", "-volname", volume_name(version), "-srcfolder", str(stage), "-fs", "HFS+",
         "-format", "UDZO", "-imagekey", "zlib-level=9", "-ov", str(dmg)],
        ["hdiutil", "verify", str(dmg)],
    ]
    return out, dmg


def sha256_line(path):
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"{h.hexdigest()}  {Path(path).name}\n"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dist", default=str(ROOT / "dist"))
    p.add_argument("--work", default=str(ROOT / "build" / "macos"))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    dist, work, version, machine = Path(args.dist), Path(args.work), app_version(), arch()
    commands, dmg = steps(dist, work, version, machine)
    if args.dry_run:
        for c in commands:
            print(" ".join(c))
        print(f"write {dmg.name}.sha256")
        return 0
    if sys.platform != "darwin":
        sys.exit("macos_dmg.py builds on a Mac (or a macos-latest runner); use --dry-run to see the steps")
    for leftover in (dist / "Swangz.app", work / "dmg"):
        shutil.rmtree(leftover, ignore_errors=True)
    (work / "dmg").mkdir(parents=True)
    (work / "dmg" / "READ ME FIRST.txt").write_text(README, encoding="utf-8")
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    for c in commands:
        print("+ " + " ".join(c), flush=True)
        subprocess.run(c, check=True, env=env)
    Path(str(dmg) + ".sha256").write_text(sha256_line(dmg), encoding="utf-8")
    print(f"built {dmg} ({LABEL})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
