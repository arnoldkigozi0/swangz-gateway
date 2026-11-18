"""Compare two builds of the same commit and say, honestly, whether they are byte-for-byte identical.

    python packaging/reproducible.py --a build-a/Swangz.exe --b build-b/Swangz.exe --label program --report evidence/repro.json

It never fails the build because of a difference: it records the result (identical or not, the SHA-256 of each, how many
bytes differ and where) so the release notes can state it. It exits 2 only when an input is missing. For Windows programs
it also reads the PE header's link timestamp and checksum, and for a PyInstaller one-file program it lists the archive
entries whose contents differ, which says where the difference comes from.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def differing_ranges(a, b, limit=20):
    """[start, end) byte ranges where a and b differ (a length difference is one range at the end)."""
    ranges, start = [], None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if start is None:
                start = i
        elif start is not None:
            ranges.append([start, i])
            start = None
            if len(ranges) >= limit:
                return ranges, True
    if start is not None:
        ranges.append([start, min(len(a), len(b))])
    if len(a) != len(b):
        ranges.append([min(len(a), len(b)), max(len(a), len(b))])
    return ranges[:limit], len(ranges) > limit


def pe_header(data):
    """The COFF link timestamp and the optional header's checksum of a Windows program, or None."""
    if data[:2] != b"MZ" or len(data) < 0x40:
        return None
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[offset:offset + 4] != b"PE\0\0":
        return None
    timestamp = struct.unpack_from("<I", data, offset + 8)[0]
    checksum = struct.unpack_from("<I", data, offset + 24 + 64)[0]
    return {"timestamp": timestamp, "checksum": checksum}


def archive_differences(path_a, path_b):
    """Names of PyInstaller archive entries whose contents differ, or None when PyInstaller cannot read them."""
    try:
        from PyInstaller.archive.readers import CArchiveReader
        ra, rb = CArchiveReader(str(path_a)), CArchiveReader(str(path_b))
        names = sorted(set(ra.toc) | set(rb.toc))
        return [n for n in names if n not in ra.toc or n not in rb.toc or ra.extract(n) != rb.extract(n)]
    except Exception as exc:  # not a PyInstaller program, or a reader API change: say so rather than guess
        return {"unavailable": f"{type(exc).__name__}: {exc}"[:300]}


def compare(path_a, path_b, label):
    a, b = Path(path_a).read_bytes(), Path(path_b).read_bytes()
    result = {"label": label, "a": {"file": str(path_a), "size": len(a), "sha256": hashlib.sha256(a).hexdigest()},
              "b": {"file": str(path_b), "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}}
    result["identical"] = a == b
    if not result["identical"]:
        ranges, more = differing_ranges(a, b)
        result["differing_ranges"] = ranges
        result["more_ranges"] = more
        result["differing_bytes_in_listed_ranges"] = sum(e - s for s, e in ranges)
        pa, pb = pe_header(a), pe_header(b)
        if pa or pb:
            result["pe"] = {"a": pa, "b": pb}
        result["archive_entries_differing"] = archive_differences(path_a, path_b)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--a", type=Path, required=True)
    p.add_argument("--b", type=Path, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--summary", type=Path, help="append one Markdown line (e.g. $GITHUB_STEP_SUMMARY)")
    args = p.parse_args(argv)
    for path in (args.a, args.b):
        if not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            return 2
    result = compare(args.a, args.b, args.label)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    verdict = "IDENTICAL" if result["identical"] else "DIFFERENT"
    print(f"{verdict} {args.label}: {result['a']['sha256']} vs {result['b']['sha256']}")
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(f"- Reproducible-build check, {args.label}: **{verdict}** "
                    f"(`{result['a']['sha256'][:16]}` vs `{result['b']['sha256'][:16]}`)\n")
    if not result["identical"]:
        print(json.dumps({k: result[k] for k in ("differing_ranges", "pe", "archive_entries_differing") if k in result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
