"""The macOS RC evidence as Markdown (the workflow's job summary, also written to EVIDENCE/SUMMARY.md).

    python3 packaging/macos_summary.py --dist dist --evidence evidence --pyinstaller 6.22.3
"""

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path

LABEL = "RC — UNSIGNED — INTERNAL TEST ONLY"


def sw_vers():
    try:
        return subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip() or "?"
    except OSError:
        return "not macOS"


def render(dist, evidence, pyinstaller, env=os.environ, macos=None):
    sums = Path(dist) / "SHA256SUMS"
    steps_file = Path(evidence) / "journey.json"
    steps = json.loads(steps_file.read_text(encoding="utf-8")) if steps_file.exists() else []
    failed = [s for s in steps if s["result"] != "pass"]
    verdict = "no journey ran" if not steps else (f"FAILED at: {failed[0]['step']}" if failed else f"passed, {len(steps)} steps")
    lines = [f"# Swangz for macOS — {LABEL}", "",
             "Not signed with a Developer ID, not notarized: Gatekeeper refuses it, as it should. "
             "Not production-ready. See docs/MACOS-SIGNING.md.", "",
             "| | |", "|---|---|",
             f"| Commit | `{env.get('GITHUB_SHA', '?')[:12]}` |",
             f"| Run | {env.get('GITHUB_SERVER_URL', '')}/{env.get('GITHUB_REPOSITORY', '')}/actions/runs/{env.get('GITHUB_RUN_ID', '?')} |",
             f"| Runner | macOS {macos or sw_vers()}, {platform.machine()} |",
             f"| PyInstaller | {pyinstaller} (pinned) |",
             f"| Journey | {verdict} |", "",
             "## SHA-256", "", "```", sums.read_text(encoding="utf-8").strip() if sums.exists() else "no SHA256SUMS (build failed)", "```", "",
             "## Journey (install, launch, enrol, restart, upgrade, uninstall)", "", "| Result | Step | Detail |", "|---|---|---|"]
    for s in steps:
        detail = str(s.get("detail") or "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(f"| {s['result']} | {s['step']} | {detail} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dist", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--pyinstaller", default="?")
    a = p.parse_args(argv)
    text = render(a.dist, a.evidence, a.pyinstaller)
    Path(a.evidence).mkdir(parents=True, exist_ok=True)
    (Path(a.evidence) / "SUMMARY.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
