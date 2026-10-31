"""Build the Swangz app into a standalone program for the computer you run this on.

    python3 packaging/build.py            # -> dist/Swangz (Linux), dist/Swangz.exe (Windows), dist/Swangz.app (macOS)

Needs Python with Tk (python.org's installers and Homebrew's python-tk have it; on Debian/Ubuntu:
apt install python3-tk) and PyInstaller (pip install pyinstaller). The program carries its own Python, so
the people who install it need nothing. Signing and notarising (so Windows and macOS don't warn) are a
separate step with certificates only Swangz holds: see packaging/README.md.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def command(dist, work, onedir=False):
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "Swangz",
           "--paths", str(ROOT), "--hidden-import", "swangz_client.gui", "--hidden-import", "swangz_client.cli",
           "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work)]
    if sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", "com.swangzavenue.swangz"]
        onedir = True  # a .app is already one thing; one-file inside it only slows every start
    cmd.append("--onedir" if onedir else "--onefile")
    cmd.append(str(ROOT / "packaging" / "swangz_app.py"))
    return cmd


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dist", default=str(ROOT / "dist"))
    p.add_argument("--work", default=str(ROOT / "build" / "packaging"))
    args = p.parse_args(argv)
    try:
        import PyInstaller  # noqa: F401
        import tkinter  # noqa: F401
    except ImportError as exc:
        sys.exit(f"missing {exc.name}: see the notes at the top of this file")
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    code = subprocess.run(command(args.dist, args.work), env=env).returncode
    if code == 0:
        print(f"built into {args.dist}")
    return code


if __name__ == "__main__":
    sys.exit(main())
