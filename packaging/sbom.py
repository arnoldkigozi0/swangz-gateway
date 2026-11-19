"""A CycloneDX 1.5 software bill of materials for the built Swangz program.

    python packaging/sbom.py --program dist/Swangz.exe --version 0.1.23 --requirements packaging/requirements-windows-build.txt --out artifacts/Swangz-0.1.23.cdx.json
    python packaging/sbom.py --program dist/Swangz.app --artifact dist/Swangz-0.1.23-RC-UNSIGNED-macos-arm64.dmg ...

The program is a one-file Windows .exe or a macOS .app folder. For a folder, the program hash is the --artifact file's
(the .dmg people download); without one, a hash over every file's path and SHA-256.

What it lists, and where each fact comes from:
- the program itself (SHA-256 of the file);
- the Python runtime it carries (the version of the interpreter that ran the build, which PyInstaller bundles);
- the Swangz client code (its version and the modules found inside the program's archive);
- every native file bundled in the program (DLLs, .pyd extension modules), each with its SHA-256, read from the
  PyInstaller archive;
- the pinned build tools (name, version, SHA-256 from the hash-pinned requirements file), as tools, not as
  components, because none of them ships in the program.

The Swangz client uses the Python standard library only, so there are no third-party Python packages to list; if one
appears in the archive it is listed under "unexpected" and the script exits 1.
"""
import argparse
import hashlib
import json
import platform
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

NATIVE = re.compile(r"\.(dll|pyd|so|dylib)$", re.I)
MACHO = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xcf")
OWN = ("swangz_client",)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_requirements(path):
    """[(name, version, [sha256, ...])] from a hash-pinned requirements file."""
    text = Path(path).read_text(encoding="utf-8")
    out = []
    for block in re.split(r"\n(?=[A-Za-z0-9])", re.sub(r"\\\n\s*", " ", text)):
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;]+)", block.strip())
        if m:
            out.append((m.group(1), m.group(2), re.findall(r"--hash=sha256:([0-9a-f]{64})", block)))
    return out


def _modules(reader):
    modules = []
    for name in reader.toc:
        if name.endswith(".pyz") or name.startswith("PYZ"):
            modules.extend(reader.open_embedded_archive(name).toc)
    return modules


def archive_contents(program):
    """(native files {name: sha256}, python modules [name]) from a PyInstaller program: a one-file .exe, or a .app
    folder whose native files sit beside the executable that carries the module archive."""
    from PyInstaller.archive.readers import CArchiveReader
    program = Path(program)
    if program.is_file():
        reader = CArchiveReader(str(program))
        native = {name: sha256(reader.extract(name)) for name in reader.toc if NATIVE.search(name)}
        return native, sorted(set(_modules(reader)))
    native, modules, opened = {}, [], 0
    for f in sorted(p for p in program.rglob("*") if p.is_file() and not p.is_symlink()):
        data = f.read_bytes()
        rel = f.relative_to(program).as_posix()
        if NATIVE.search(f.name) or data[:4] in MACHO:
            native[rel] = sha256(data)
        if data[:4] in MACHO or f.suffix == ".pkg":
            try:
                found = _modules(CArchiveReader(str(f)))
            except Exception:  # an ordinary library, not a PyInstaller archive
                continue
            modules.extend(found)
            opened += 1
    if not opened:
        raise SystemExit(f"no PyInstaller archive found in {program}")
    return native, sorted(set(modules))


def program_digest(program, artifact=None):
    """SHA-256 of the program file, of the --artifact (the .dmg), or over a folder's sorted (path, SHA-256) list."""
    if artifact:
        return sha256(Path(artifact).read_bytes())
    program = Path(program)
    if program.is_file():
        return sha256(program.read_bytes())
    lines = [f"{p.relative_to(program).as_posix()} {sha256(p.read_bytes())}\n"
             for p in sorted(program.rglob("*")) if p.is_file() and not p.is_symlink()]
    return sha256("".join(lines).encode())


def build(program, version, requirements, native, modules, python_version, epoch=None, artifact=None):
    program_hash = program_digest(program, artifact)
    stamp = datetime.fromtimestamp(epoch, timezone.utc) if epoch else datetime.now(timezone.utc)
    own = [m for m in modules if m.split(".")[0] in OWN]
    stdlib = set(getattr(sys, "stdlib_module_names", ())) | {"_pyi_rth_utils", "pyimod01_archive", "pyimod02_importers",
                                                              "pyimod03_ctypes", "pyimod04_pywin32"}
    unexpected = sorted({m.split(".")[0] for m in modules} - set(OWN) - stdlib) if stdlib else []
    components = [
        {"type": "application", "bom-ref": "swangz-client", "name": "swangz-client", "version": version,
         "description": f"Swangz client code ({len(own)} modules), standard library only",
         "properties": [{"name": "swangz:modules", "value": ",".join(own)}]},
        {"type": "platform", "bom-ref": "cpython", "name": "CPython", "version": python_version,
         "description": "the interpreter and standard library bundled by PyInstaller",
         "properties": [{"name": "swangz:stdlib-modules", "value": str(len(modules) - len(own))}]},
    ]
    for name, digest in sorted(native.items()):
        components.append({"type": "file", "bom-ref": f"file:{name}", "name": name,
                           "hashes": [{"alg": "SHA-256", "content": digest}]})
    tools = [{"type": "application", "name": n, "version": v,
              "hashes": [{"alg": "SHA-256", "content": h} for h in hs]} for n, v, hs in requirements]
    bom = {
        "bomFormat": "CycloneDX", "specVersion": "1.5",
        "serialNumber": "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "swangz:" + program_hash)),
        "version": 1,
        "metadata": {
            "timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": tools},
            "component": {"type": "application", "bom-ref": "program", "name": Path(artifact or program).name, "version": version,
                          "hashes": [{"alg": "SHA-256", "content": program_hash}]},
            "properties": [{"name": "swangz:label", "value": "RC — UNSIGNED — INTERNAL TEST ONLY"}],
        },
        "components": components,
        "dependencies": [{"ref": "program", "dependsOn": [c["bom-ref"] for c in components]}],
    }
    return bom, unexpected


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--program", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--requirements", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--artifact", help="the file people download (a .dmg), whose SHA-256 names the program")
    ap.add_argument("--epoch", type=int, help="timestamp to record (SOURCE_DATE_EPOCH), so the SBOM is reproducible")
    args = ap.parse_args(argv)
    for p in (args.program, args.requirements, args.artifact):
        if p and not Path(p).exists():
            print(f"missing input: {p}", file=sys.stderr)
            return 2
    native, modules = archive_contents(args.program)
    bom, unexpected = build(args.program, args.version, read_requirements(args.requirements), native, modules,
                            platform.python_version(), args.epoch, args.artifact)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(bom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"SBOM {args.out}: {len(bom['components'])} components ({len(native)} native files, {len(modules)} modules), "
          f"{len(bom['metadata']['tools']['components'])} build tools")
    if unexpected:
        print("unexpected third-party modules in the program: " + ", ".join(unexpected), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
