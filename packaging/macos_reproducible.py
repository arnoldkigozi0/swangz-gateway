"""Compare two macOS builds of the same commit (the .app trees and the DMGs) and say honestly whether they match.

    python packaging/macos_reproducible.py --app-a dist/Swangz.app --app-b dist-b/Swangz.app \
        --dmg-a dist/X.dmg --dmg-b dist-b/X.dmg --report evidence/reproducible-macos.json --summary "$GITHUB_STEP_SUMMARY"

Like packaging/reproducible.py (Windows) it never fails the build because of a difference: it records each side's
SHA-256, whether the two are identical, and for the app which files differ (with the PyInstaller archive entries
that differ where PyInstaller can read the file), so the release notes can state the result. Exit 2 only when an
input is missing.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reproducible  # noqa: E402  packaging/reproducible.py: sha256 and PyInstaller archive comparison

LIMIT = 25


def tree(root):
    """relative path -> ("dir",) | ("link", target) | ("file", sha256, executable). Links are never followed."""
    root, out = Path(root), {}
    for here, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(here) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                out[rel] = ("link", os.readlink(p))
            elif p.is_dir():
                out[rel] = ("dir",)
            else:
                out[rel] = ("file", reproducible.sha256(p), os.access(p, os.X_OK))
    return out


def tree_sha(entries):
    return hashlib.sha256(json.dumps(sorted(entries.items()), separators=(",", ":")).encode()).hexdigest()


def compare_apps(a, b):
    ta, tb = tree(a), tree(b)
    differing = [k for k in sorted(set(ta) | set(tb)) if ta.get(k) != tb.get(k)]
    out = {"label": "app", "a": {"path": str(a), "entries": len(ta), "tree_sha256": tree_sha(ta)},
           "b": {"path": str(b), "entries": len(tb), "tree_sha256": tree_sha(tb)},
           "identical": not differing, "differing_count": len(differing), "differing": []}
    for rel in differing[:LIMIT]:
        item = {"path": rel, "a": "missing" if rel not in ta else ta[rel][0], "b": "missing" if rel not in tb else tb[rel][0]}
        if item["a"] == item["b"] == "file":
            item["archive_entries_differing"] = reproducible.archive_differences(Path(a) / rel, Path(b) / rel)
        out["differing"].append(item)
    return out


def compare_files(a, b, label):
    sa, sb = reproducible.sha256(a), reproducible.sha256(b)
    return {"label": label, "a": {"file": str(a), "size": Path(a).stat().st_size, "sha256": sa},
            "b": {"file": str(b), "size": Path(b).stat().st_size, "sha256": sb}, "identical": sa == sb}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--app-a", type=Path, required=True)
    p.add_argument("--app-b", type=Path, required=True)
    p.add_argument("--dmg-a", type=Path, required=True)
    p.add_argument("--dmg-b", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--summary", type=Path, help="append Markdown lines (e.g. $GITHUB_STEP_SUMMARY)")
    args = p.parse_args(argv)
    for path, kind in ((args.app_a, "dir"), (args.app_b, "dir"), (args.dmg_a, "file"), (args.dmg_b, "file")):
        if not (path.is_dir() if kind == "dir" else path.is_file()):
            print(f"missing: {path}", file=sys.stderr)
            return 2
    result = {"app": compare_apps(args.app_a, args.app_b), "dmg": compare_files(args.dmg_a, args.dmg_b, "dmg")}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = []
    for key in ("app", "dmg"):
        r = result[key]
        verdict = "IDENTICAL" if r["identical"] else "DIFFERENT"
        sa = r["a"].get("tree_sha256") or r["a"]["sha256"]
        sb = r["b"].get("tree_sha256") or r["b"]["sha256"]
        extra = f", {r['differing_count']} entries differ" if key == "app" and not r["identical"] else ""
        print(f"{verdict} macOS {key}: {sa} vs {sb}{extra}")
        lines.append(f"- Reproducible-build check, macOS {key}: **{verdict}** (`{sa[:16]}` vs `{sb[:16]}`{extra})\n")
    if not result["app"]["identical"]:
        print(json.dumps(result["app"]["differing"][:10]))
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.writelines(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
