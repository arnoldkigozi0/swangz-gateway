"""Build the Swangz app into a standalone program for the computer you run this on.

    python3 packaging/build.py            # -> dist/Swangz (Linux), dist/Swangz.exe (Windows), dist/Swangz.app (macOS)
    python packaging/build.py --company   # Windows only -> dist-company/Swangz/ (Swangz.exe and _internal)

Needs Python with Tk (python.org's installers and Homebrew's python-tk have it; on Debian/Ubuntu:
apt install python3-tk) and PyInstaller (pip install pyinstaller). The program carries its own Python, so
the people who install it need nothing. Signing and notarising (so Windows and macOS don't warn) are a
separate step with certificates only Swangz holds: see packaging/README.md.

`--company` is the Windows build that the company installer (packaging/windows/swangz-company.iss) puts under
Program Files: one folder instead of one file, so the program never unpacks itself into a person's %TEMP%, where
that person's other programs could replace what it loads (docs/DECISIONS.md D-026 B5).
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
           "--hidden-import", "swangz_client.chrome_install",
           "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work)]
    if sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", "com.swangzavenue.swangz"]
        onedir = True  # a .app is already one thing; one-file inside it only slows every start
    cmd.append("--onedir" if onedir else "--onefile")
    cmd.append(str(ROOT / "packaging" / "swangz_app.py"))
    return cmd


def normalize_windows_program(path, epoch):
    """Make a Windows build depend on the source only: PyInstaller stamps the build time into the PE header (and the
    resource directory) when it writes the icon and manifest. Set those to the source date, then recompute the PE
    checksum. The appended archive is untouched. Returns the stamps that were replaced."""
    import pefile  # one of PyInstaller's own Windows dependencies (packaging/requirements-windows-build.txt)

    pe = pefile.PE(str(path))
    replaced = {"file_header": pe.FILE_HEADER.TimeDateStamp}
    pe.FILE_HEADER.TimeDateStamp = epoch

    def directories(directory):
        yield directory
        for entry in getattr(directory, "entries", []):
            if hasattr(entry, "directory"):
                yield from directories(entry.directory)

    if hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
        stamps = set()
        for directory in directories(pe.DIRECTORY_ENTRY_RESOURCE):
            stamps.add(directory.struct.TimeDateStamp)
            directory.struct.TimeDateStamp = epoch
        replaced["resources"] = sorted(stamps)
    pe.OPTIONAL_HEADER.CheckSum = pe.generate_checksum()
    data = pe.write()
    pe.close()
    Path(path).write_bytes(data)
    os.utime(path, (epoch, epoch))  # the installer stores the file's time too
    return replaced


def date_files(folder, epoch):
    """Give every file of a one-folder build the source date: the installer stores each file's time."""
    for f in Path(folder).rglob("*"):
        if f.is_file():
            os.utime(f, (epoch, epoch))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dist")
    p.add_argument("--work")
    p.add_argument("--company", action="store_true", help="Windows: the one-folder build for the company installer")
    args = p.parse_args(argv)
    if args.company and sys.platform != "win32":
        p.error("--company is the Windows company build; macOS and Linux have one build")
    # Separate folders, so one build never overwrites the other.
    args.dist = args.dist or str(ROOT / ("dist-company" if args.company else "dist"))
    args.work = args.work or str(ROOT / "build" / ("packaging-company" if args.company else "packaging"))
    try:
        import PyInstaller  # noqa: F401
        import tkinter  # noqa: F401
    except ImportError as exc:
        sys.exit(f"missing {exc.name}: see the notes at the top of this file")
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    code = subprocess.run(command(args.dist, args.work, onedir=args.company), env=env).returncode
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if code == 0 and epoch and sys.platform == "win32":
        folder = Path(args.dist) / "Swangz" if args.company else Path(args.dist)
        program = folder / "Swangz.exe"
        print(f"normalized {program} to SOURCE_DATE_EPOCH {epoch}: replaced {normalize_windows_program(program, int(epoch))}")
        if args.company:
            date_files(folder, int(epoch))
    if code == 0:
        print(f"built into {args.dist}")
    return code


if __name__ == "__main__":
    sys.exit(main())
