"""Scan built release artifacts for embedded secrets and server addresses.

    python packaging/secret_scan.py --report evidence/secret-scan.json [--summary FILE] [--min-archives N] PATH [PATH ...]

Each PATH is a file or a folder. Every file is searched as raw bytes. A PyInstaller program is also opened and every
entry is searched after decompression, including each module inside its PYZ archive; zip files are searched entry by
entry. Archives that cannot be opened are listed under "unreadable" rather than silently skipped.

A scan that saw nothing is not clean: a folder given as PATH that holds no files fails, and with --min-archives N the
scan fails unless at least N PyInstaller programs were actually opened (so a build that moved or broke cannot pass
by being skipped). Both are listed under "problems" in the report.

Exit codes: 0 no hits and no problems, 1 at least one hit or problem, 2 an input is missing.
"""
import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

PATTERNS = {
    "private key": rb"-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----",
    "Anthropic key": rb"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI key": rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{40,}",
    "GitHub token": rb"(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,})",
    # Not inside a base64 run: a DMG's block table is base64 full of A's and once read "...AAKIAAAAAAAQAACAAAAF".
    # Only a run of 8+ base64 characters hides a match: one character is not enough, because compiled Python
    # stores a short string's length as one byte that can be a letter, digit, "+" or "/" (and "\\n" or "%3D" end in one).
    "AWS access key": rb"(?<![A-Za-z0-9+/]{8})(?:AKIA|ASIA)[0-9A-Z]{16}",
    "Google API key": rb"AIza[0-9A-Za-z_\-]{35}",
    "Google OAuth client secret": rb"GOCSPX-[A-Za-z0-9_\-]{20,}",
    "Slack token": rb"xox[abprs]-[A-Za-z0-9\-]{10,}",
    "secret assignment": rb"(?:API_KEY|_SECRET|_TOKEN|PASSWORD|CREDENTIALS)\s*=\s*['\"]?[A-Za-z0-9_\-/+]{16,}",
    "Swangz Hub key": rb"sgw_[0-9a-f]{12}_[A-Za-z0-9_\-]{40,}",
    "deployment address": rb"[a-z0-9\-]+\.(?:trycloudflare\.com|netlify\.app|up\.railway\.app|ngrok(?:-free)?\.app)",
    "company address": rb"[a-z0-9\-.]*(?:swangzavenue\.com|ictconnect\.org)",
}
# Text that matches a pattern but is not a secret or an embedded address. Each entry says why it is allowed.
ALLOWED = {
    b"hub.ictconnect.org": "the address sign-in starts with (core.DEFAULT_SERVER); the person can change it, and nothing is sent "
                           "to it before they press Sign in",
    b"ai.swangzavenue.com": "the example address in builds made before the default address",
    b"swangzavenue.com": "the company email domain named in sign-in help text",
}
ENV_NAMES = re.compile(r"(^|[\\/])\.env(\.[A-Za-z0-9_-]+)?$")
COMPILED = {name: re.compile(p) for name, p in PATTERNS.items()}


SCANNED = {"inner entries": 0}


def scan_bytes(data, where, hits):
    if "!" in where:
        SCANNED["inner entries"] += 1
    for name, rx in COMPILED.items():
        for m in rx.finditer(data):
            text = m.group(0)
            if text in ALLOWED or text.lstrip(b"@.") in ALLOWED:
                continue
            # never write a found secret into the evidence: keep only a short, masked prefix
            hits.append({"where": where, "pattern": name, "offset": m.start(),
                         "sample": text[:6].decode("latin-1") + "…" if name not in ("deployment address", "company address")
                         else text.decode("latin-1")})


def scan_name(name, where, hits):
    if ENV_NAMES.search(name):
        hits.append({"where": where, "pattern": ".env file", "offset": 0, "sample": name[-40:]})


def scan_pyinstaller(path, hits, unreadable):
    try:
        from PyInstaller.archive.readers import CArchiveReader
        reader = CArchiveReader(str(path))
    except Exception as exc:  # not a PyInstaller program, or PyInstaller is not installed here
        return f"{type(exc).__name__}: {exc}"[:200]
    for name in reader.toc:
        where = f"{path}!{name}"
        scan_name(name, where, hits)
        try:
            if name.endswith(".pyz") or name == "PYZ-00.pyz" or name.startswith("PYZ"):
                pyz = reader.open_embedded_archive(name)
                for mod in pyz.toc:
                    try:
                        scan_bytes(_code_bytes(pyz, mod), f"{where}!{mod}", hits)
                    except Exception as exc:
                        unreadable.append({"where": f"{where}!{mod}", "error": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            data = reader.extract(name)
        except Exception as exc:
            unreadable.append({"where": where, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        scan_bytes(data, where, hits)
        if data[:4] == b"PK\x03\x04":
            scan_zip(io.BytesIO(data), where, hits, unreadable)
    return None


def _code_bytes(pyz, mod):
    """A module's compiled code as bytes: string constants sit in it uncompressed."""
    import marshal
    try:
        code = pyz.extract(mod, raw=True)  # PyInstaller 6: the decompressed, still-marshalled bytes
    except TypeError:
        code = pyz.extract(mod)
    if isinstance(code, tuple):  # older readers return (is_package, code)
        code = code[-1]
    if isinstance(code, (bytes, bytearray)):
        return bytes(code)
    return marshal.dumps(code) if code is not None else b""


def scan_zip(fileobj, where, hits, unreadable):
    try:
        with zipfile.ZipFile(fileobj) as z:
            for info in z.infolist():
                scan_name(info.filename, f"{where}!{info.filename}", hits)
                scan_bytes(z.read(info), f"{where}!{info.filename}", hits)
    except Exception as exc:
        unreadable.append({"where": where, "error": f"{type(exc).__name__}: {exc}"[:200]})


def scan(paths):
    hits, unreadable, files, archives = [], [], [], []
    SCANNED["inner entries"] = 0
    for root in paths:
        root = Path(root)
        for f in ([root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())):
            files.append(str(f))
            scan_name(f.name, str(f), hits)
            data = f.read_bytes()
            scan_bytes(data, str(f), hits)
            if data[:4] == b"PK\x03\x04":
                scan_zip(f, str(f), hits, unreadable)
            elif data[:2] == b"MZ" or data[:4] in (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
                why_not = scan_pyinstaller(f, hits, unreadable)
                archives.append({"file": str(f), "pyinstaller": why_not is None, "note": why_not})
    return {"files": files, "inner_entries_scanned": SCANNED["inner entries"], "archives": archives, "patterns": sorted(PATTERNS),
            "allowed": {k.decode(): v for k, v in ALLOWED.items()}, "hits": hits, "unreadable": unreadable}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--report", required=True)
    ap.add_argument("--summary")
    ap.add_argument("--min-archives", type=int, default=0, metavar="N",
                    help="fail unless at least N PyInstaller programs were opened and searched entry by entry")
    args = ap.parse_args(argv)
    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print("missing input: " + ", ".join(missing), file=sys.stderr)
        return 2
    result = scan(args.paths)
    opened = sum(a["pyinstaller"] for a in result["archives"])
    problems = [f"{p}: no files to scan" for p in args.paths
                if Path(p).is_dir() and not any(f.is_file() for f in Path(p).rglob("*"))]
    if opened < args.min_archives:
        problems.append(f"{opened} PyInstaller archives opened, at least {args.min_archives} expected")
    result["problems"] = problems
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(result, indent=2))
    n = len(result["hits"])
    ok = n == 0 and not problems
    line = (f"Secret scan: {len(result['files'])} files, {opened} PyInstaller archives opened, "
            f"{result['inner_entries_scanned']} archive entries and modules searched, "
            f"{len(result['unreadable'])} unreadable, {n} hits")
    print(("CLEAN " if ok else "HITS " if n else "FAILED ") + line)
    for problem in problems:
        print("  " + problem)
    for h in result["hits"][:50]:
        print(f"  {h['pattern']}: {h['where']} @{h['offset']} {h['sample']}")
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as fh:
            fh.write(f"- {'CLEAN' if ok else '**HITS**' if n else '**FAILED**'}: {line}"
                     + "".join(f"; **{problem}**" for problem in problems) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
