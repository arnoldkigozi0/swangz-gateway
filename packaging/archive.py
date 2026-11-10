"""Archive only the standalone app; preserve Unix executable modes and .app links."""

import hashlib
from pathlib import Path
import platform
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    system = platform.system()
    app = ROOT / "dist" / {"Windows": "Swangz.exe", "Darwin": "Swangz.app", "Linux": "Swangz"}[system]
    if not app.exists():
        raise SystemExit(f"missing build: {app}")
    out = ROOT / "artifacts"
    out.mkdir(exist_ok=True)
    name = f"Swangz-UNSIGNED-TEST-{system}-{platform.machine()}"
    if system == "Windows":
        archive = out / (name + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
            handle.write(app, app.name)
    else:
        archive = out / (name + ".tar.gz")
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(app, arcname=app.name)
    checksum = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    digest = checksum.hexdigest()
    (out / (archive.name + ".sha256")).write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"UNSIGNED-TEST archive: {archive.name}\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
