"""Downloading and unpacking packages Swangz publishes — only what checks out, only inside Swangz's own folder.

A package arrives as a zip with a checksum from the manifest. Before anything is written it is checked
against that checksum; while it is unpacked every file is checked to land inside the package's own folder
(no `..`, no absolute or drive paths, no links), and the size and number of files are capped so a small
download can't fill the disk. It is unpacked beside its final place and moved into it in one step, so a
failed install never leaves a half-package behind.
"""

import hashlib
import io
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path

MAX_FILES = 20000
MAX_UNPACKED = 1 << 30  # 1 GB
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,59}")
SAFE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,31}")


class BundleError(Exception):
    pass


def check_name(name):
    if (not name or name.startswith(("/", "\\")) or "\\" in name or "\x00" in name or re.match(r"[A-Za-z]:", name)
            or ".." in name.split("/")):
        raise BundleError(f"the package has an unsafe file name: {name!r}")


def extract(data, dest):
    """Unpack zip `data` into the (new, empty) folder `dest`. -> number of files."""
    dest = Path(dest)
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BundleError("the download is not a zip file")
    with z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise BundleError("the package has too many files")
        if sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise BundleError("the package is too large once unpacked")
        root = dest.resolve()
        count = 0
        for info in infos:
            check_name(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise BundleError(f"the package contains a link: {info.filename!r}")
            target = (dest / info.filename).resolve()
            if target != root and root not in target.parents:
                raise BundleError(f"the package would write outside its folder: {info.filename!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with z.open(info) as src, open(target, "wb") as out:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    written += len(chunk)
                    if written > info.file_size or written > MAX_UNPACKED:  # the header lied
                        raise BundleError(f"{info.filename!r} is larger than it says")
                    out.write(chunk)
            if os.name == "posix":
                os.chmod(target, 0o755 if mode & 0o111 else 0o644)
            count += 1
    return count


def install(paths, pid, version, data, sha256, base=None):
    """Verify, unpack beside the final place, then swap in; older versions of this package are removed.
    -> the folder."""
    if not SAFE_ID.fullmatch(pid or "") or not SAFE_VERSION.fullmatch(version or ""):
        raise BundleError("the package has an unsafe name or version")
    if hashlib.sha256(data).hexdigest() != sha256:
        raise BundleError("the download doesn't match its checksum, so it was not installed")
    base = Path(base or Path(paths.data) / "packages")
    final = base / pid / version
    staging = base / (".incoming-" + pid)
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        extract(data, staging)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(final, ignore_errors=True)
        os.replace(staging, final)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    for old in final.parent.iterdir():
        if old.name != version:
            shutil.rmtree(old, ignore_errors=True)
    return final


def remove(paths, pid, base=None):
    base = Path(base or Path(paths.data) / "packages")
    if SAFE_ID.fullmatch(pid or ""):
        shutil.rmtree(base / pid, ignore_errors=True)
