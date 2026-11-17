"""Turn dist/Swangz.app into a versioned, UNSIGNED release candidate: an .app and a DMG with SHA-256 sums.

    python3 packaging/build.py              # on macOS: dist/Swangz.app
    python3 packaging/macos.py stamp        # version + bundle metadata into Info.plist, ad-hoc re-seal
    python3 packaging/macos.py dmg          # artifacts/Swangz-<version>-macOS-<arch>-UNSIGNED.dmg (+ .zip of the .app)
    python3 packaging/macos.py verify-dmg   # mount read-only, copy the app out, run its self-check, unmount

Uses only tools that ship with macOS (hdiutil, codesign, ditto, spctl). No Developer ID, no notarization and
no signing secret: the only signature is the ad-hoc seal Apple Silicon needs to run any binary at all. Gatekeeper
will refuse the app on a normal Mac until it is signed and notarized (docs/MACOS-SIGNING.md); this script never
removes quarantine, never disables Gatekeeper and never tells anyone to.
"""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BUNDLE_ID = "com.swangzavenue.swangz"
LABEL = "RC — UNSIGNED — INTERNAL TEST ONLY"
MIN_MACOS = "11.0"


def version():
    from swangz_client import __version__
    return __version__


def artifact_name(ver, arch, ext):
    return f"Swangz-{ver}-macOS-{arch}-UNSIGNED.{ext}"


def stamp_plist(info, ver, build):
    """The Info.plist keys the release depends on. Pure: returns a new dict."""
    out = dict(info)
    out.update({
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": "Swangz",
        "CFBundleDisplayName": "Swangz",
        "CFBundleShortVersionString": ver,
        "CFBundleVersion": build,
        "LSMinimumSystemVersion": MIN_MACOS,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Swangz Avenue. " + LABEL,
    })
    # The app opens a window; it is not a background-only agent.
    out.pop("LSBackgroundOnly", None)
    out.pop("LSUIElement", None)
    return out


def dmg_command(staging, out, volname, epoch=None):
    """hdiutil call for a compressed, read-only image. Pure: returns argv."""
    return ["hdiutil", "create", "-volname", volname, "-srcfolder", str(staging), "-fs", "HFS+",
            "-format", "UDZO", "-imagekey", "zlib-level=9", "-ov", str(out)]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sum(path):
    digest = sha256(path)
    Path(str(path) + ".sha256").write_text(f"{digest}  {Path(path).name}\n", encoding="utf-8")
    return digest


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def build_number():
    # Same source tree -> same build number: the commit count, or 0 outside git.
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-list", "--count", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip() or "0"
    except (OSError, subprocess.CalledProcessError):
        return "0"


def cmd_stamp(app):
    plist = app / "Contents" / "Info.plist"
    with plist.open("rb") as f:
        info = plistlib.load(f)
    info = stamp_plist(info, version(), build_number())
    with plist.open("wb") as f:
        plistlib.dump(info, f, sort_keys=True)
    # Editing Info.plist breaks PyInstaller's ad-hoc seal; re-seal ad-hoc ("-"). Not a Developer ID signature.
    run(["codesign", "--force", "--deep", "--sign", "-", "--identifier", BUNDLE_ID, str(app)])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    print(f"stamped {app.name}: {info['CFBundleShortVersionString']} ({info['CFBundleVersion']})")
    return 0


def cmd_dmg(app, out_dir):
    ver, arch = version(), platform.machine()
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"label": LABEL, "version": ver, "arch": arch, "files": {}}
    with tempfile.TemporaryDirectory(prefix="swangz-dmg-") as tmp:
        staging = Path(tmp) / "Swangz"
        staging.mkdir()
        run(["ditto", str(app), str(staging / app.name)])           # keeps symlinks, modes and the seal
        os.symlink("/Applications", staging / "Applications")       # drag-to-install
        (staging / "READ ME FIRST.txt").write_text(
            f"Swangz {ver} for macOS ({arch})\n{LABEL}\n\n"
            "This build is not signed with a Developer ID and not notarized by Apple.\n"
            "macOS will refuse to open it. Do not work around that warning: wait for the signed build,\n"
            "or ask Swangz IT. See docs/MACOS-SIGNING.md in the repository.\n", encoding="utf-8")
        dmg = out_dir / artifact_name(ver, arch, "dmg")
        run(dmg_command(staging, dmg, f"Swangz {ver}"))
    run(["hdiutil", "verify", str(dmg)])
    report["files"][dmg.name] = write_sum(dmg)
    zipped = out_dir / artifact_name(ver, arch, "app.zip")
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(zipped)])
    report["files"][zipped.name] = write_sum(zipped)
    (out_dir / "SHA256SUMS").write_text("".join(f"{d}  {n}\n" for n, d in sorted(report["files"].items())),
                                        encoding="utf-8")
    (out_dir / "release-macos.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for n, d in sorted(report["files"].items()):
        print(f"{d}  {n}")
    return 0


def cmd_verify_dmg(dmg, report_path):
    """Install from the DMG the way a person would (copy out of the mounted image) and launch the copy."""
    report = {"dmg": dmg.name, "steps": [], "ok": False}

    def step(msg):
        report["steps"].append(msg)
        print("PASS", msg, flush=True)

    mount = Path(tempfile.mkdtemp(prefix="swangz-mnt-"))
    target = Path(tempfile.mkdtemp(prefix="swangz-apps-"))
    attached = False
    try:
        if sha256(dmg) != Path(str(dmg) + ".sha256").read_text(encoding="utf-8").split()[0]:
            raise RuntimeError("DMG does not match its SHA-256")
        step("DMG matches its SHA-256")
        run(["hdiutil", "attach", "-readonly", "-nobrowse", "-noautoopen", "-mountpoint", str(mount), str(dmg)])
        attached = True
        names = sorted(p.name for p in mount.iterdir() if not p.name.startswith("."))
        if names != ["Applications", "READ ME FIRST.txt", "Swangz.app"] or os.readlink(mount / "Applications") != "/Applications":
            raise RuntimeError(f"unexpected DMG contents: {names}")
        step("mounted read-only: Swangz.app, Applications link, READ ME FIRST.txt")
        app = target / "Swangz.app"
        run(["ditto", str(mount / "Swangz.app"), str(app)])
        step("copied Swangz.app out of the image (drag-to-Applications equivalent)")
        with (app / "Contents" / "Info.plist").open("rb") as f:
            info = plistlib.load(f)
        if info.get("CFBundleShortVersionString") != version() or info.get("CFBundleIdentifier") != BUNDLE_ID:
            raise RuntimeError("Info.plist version or identifier is wrong")
        step(f"Info.plist: {BUNDLE_ID} {info['CFBundleShortVersionString']} ({info.get('CFBundleVersion')})")
        run(["codesign", "--verify", "--deep", "--strict", str(app)])
        sig = subprocess.run(["codesign", "-dv", str(app)], capture_output=True, text=True).stderr
        report["signature"] = "adhoc" if "Signature=adhoc" in sig else "other"
        step(f"code seal intact (signature: {report['signature']}, not a Developer ID)")
        # Gatekeeper's verdict is recorded, never bypassed. Unsigned + not notarized must be rejected.
        gk = subprocess.run(["spctl", "--assess", "--type", "execute", "-vv", str(app)], capture_output=True, text=True)
        report["gatekeeper"] = {"exit": gk.returncode, "output": (gk.stdout + gk.stderr).strip()[-400:]}
        if gk.returncode == 0:
            raise RuntimeError("Gatekeeper accepted an unsigned build: check what signed it")
        step("Gatekeeper rejects it (expected for an unsigned, un-notarized build; not bypassed)")
        binary = app / "Contents" / "MacOS" / "Swangz"
        out = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=120)
        if out.returncode != 0 or version() not in out.stdout + out.stderr:
            raise RuntimeError(f"--version failed: {out.returncode} {out.stdout} {out.stderr}")
        step(f"installed copy runs: {(out.stdout + out.stderr).strip()}")
        check = target / "self-check.json"
        out = subprocess.run([str(binary), "--self-check", str(check)], capture_output=True, text=True, timeout=180)
        data = json.loads(check.read_text(encoding="utf-8")) if check.exists() else {}
        if out.returncode != 0 or not data.get("frozen") or data.get("updates_enabled") or data.get("production_keys"):
            raise RuntimeError(f"self-check failed: {out.returncode} {data} {out.stderr[-2000:]}")
        report["self_check"] = data
        step(f"installed copy opens its window (Tk {data['tk']}, page {data['window']}); updates disabled")
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        if attached:
            subprocess.run(["hdiutil", "detach", str(mount), "-force"], capture_output=True)
        shutil.rmtree(target, ignore_errors=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["stamp", "dmg", "verify-dmg"])
    p.add_argument("--app", type=Path, default=ROOT / "dist" / "Swangz.app")
    p.add_argument("--out", type=Path, default=ROOT / "artifacts")
    p.add_argument("--dmg", type=Path)
    p.add_argument("--report", type=Path, default=ROOT / "smoke-results" / "macOS-dmg.json")
    args = p.parse_args(argv)
    if sys.platform != "darwin":
        sys.exit("macOS only: run this on a macOS runner (.github/workflows/release-macos.yml)")
    if args.action == "stamp":
        return cmd_stamp(args.app)
    if args.action == "dmg":
        return cmd_dmg(args.app, args.out)
    dmg = args.dmg or args.out / artifact_name(version(), platform.machine(), "dmg")
    return cmd_verify_dmg(dmg, args.report)


if __name__ == "__main__":
    sys.exit(main())
