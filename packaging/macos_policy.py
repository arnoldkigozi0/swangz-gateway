"""Deliverable 6, machine-policy integrity through the PACKAGED app on a macOS runner (D-024, W5).

The installed Swangz.app is signed in as a company device. The company browser policy pack made by
`deploy/chrome-policy/prepare.py` (CI placeholders, no real host or key) is installed device-wide, root-owned, at
`/Library/Managed Preferences/com.google.Chrome.plist`, and the Hub pins its baseline SHA-256 in `enforce` mode. Then:

1. intact pack: `sync` reports `ok` with the baseline hash, and `open` starts the workspace window (the control case);
2. tampered pack, default-deny removed (`*` taken out of URLBlocklist): `open` is refused before anything starts and
   the Hub records no open; `sync` reports `ok: false`, and the Hub writes one audit line for the move to failing;
3. tampered pack that still passes every rule but is not the pinned one (an extra blocked host): `open` is refused,
   `sync` reports a hash that is not the baseline;
4. the original pack put back: `open` works again at once (it carries its fresh result, so the Hub does not wait for
   the next heartbeat) and the Hub has the baseline hash again;
5. the pack removed: `open` is refused and `sync` reports `ok: false`.

What this does NOT prove: that Chrome itself applies the plist (no MDM profile here; Chrome's own enforcement is the
Linux bypass suite, `.github/workflows/w6-step5.yml`); tampering by an administrator who also replaces the app; the
report is the app's own claim (`gateway/managed.py`), used only to take access away. Runner only: it uses `sudo`.
"""

import json
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREPARE = ROOT / "deploy" / "chrome-policy" / "prepare.py"
PLIST = Path("/Library/Managed Preferences/com.google.Chrome.plist")
CI = {"--hub-host": "hub.swangz-ci.com", "--extension-id": "abcdefghijklmnopabcdefghijklmnop",
      "--update-url": "https://ext.swangz-ci.com/update.xml"}  # the same placeholders as w6-step5.yml
REFUSED = "company browser settings on this computer aren't in force"  # workspace_launcher.MESSAGES["workspace_policy"]
AUDIT = "device reported its browser policy is not in force"  # gateway/managed.record_policy_report
EXTRA_BLOCK = "example.org"


def signed_out(code, out):
    """A sign-out worked: exit 0, the app's own success line, and the server was told. Matching "removed" alone also
    matched the "Not removed: browser folders ..." warning every sign-out prints, so a failed one could pass."""
    return code == 0 and "taken off this" in out and "couldn't" not in out


def prepare(work):
    """-> (policy dict, baseline SHA-256 prepare.py printed)."""
    out = Path(work) / "prepared.json"
    args = [sys.executable, str(PREPARE), *[x for kv in CI.items() for x in kv], "--output", str(out)]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    found = re.search(r"^Baseline SHA-256[^:]*: ([0-9a-f]{64})$", proc.stdout, re.M)
    if proc.returncode != 0 or not found:
        raise SystemExit("prepare.py failed: " + (proc.stdout + proc.stderr)[-400:])
    return json.loads(out.read_text(encoding="utf-8")), found.group(1)


def install(policy, plist=PLIST):
    """Write the pack device-wide, owned by root, as an admin (or MDM) would. Returns (uid, mode)."""
    with tempfile.NamedTemporaryFile("wb", suffix=".plist", delete=False) as f:
        f.write(plistlib.dumps(policy, fmt=plistlib.FMT_XML))
    try:
        subprocess.run(["sudo", "mkdir", "-p", str(plist.parent)], check=True, timeout=60)
        subprocess.run(["sudo", "install", "-o", "root", "-g", "wheel", "-m", "0644", f.name, str(plist)], check=True, timeout=60)
    finally:
        os.unlink(f.name)
    st = os.stat(plist)
    return st.st_uid, oct(st.st_mode & 0o777)


CHROME_APP = Path("/Applications/Google Chrome.app")


def chrome_root_owned(app=CHROME_APP):
    """D-026 A4: a company Mac runs only a root-owned Chrome in /Applications, as an admin's or MDM's install leaves
    it. The runner image's copy belongs to the runner account, so it is handed to root here. Returns the app's uid
    and its main executable's."""
    subprocess.run(["sudo", "chown", "-R", "root:wheel", str(app)], check=True, timeout=300)
    return os.stat(app).st_uid, os.stat(app / "Contents" / "MacOS" / "Google Chrome").st_uid


def remove(plist=PLIST):
    subprocess.run(["sudo", "rm", "-f", str(plist)], timeout=60)


def without_default_deny(policy):
    p = json.loads(json.dumps(policy))
    p["URLBlocklist"] = [e for e in p.get("URLBlocklist", []) if e != "*"]
    return p


def extra_block(policy):
    p = json.loads(json.dumps(policy))
    p["URLBlocklist"] = list(p.get("URLBlocklist", [])) + [EXTRA_BLOCK]
    return p


def chrome_running(folder, timeout=30):
    """A Chrome process whose command line names this workspace folder: this Open started a window (the folder and
    its Local State stay from an earlier open, so they alone prove nothing). The opens close it after every case."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if subprocess.run(["pgrep", "-f", "--", "--user-data-dir=" + str(folder)], capture_output=True).returncode == 0:
            return True
        time.sleep(0.5)
    return False


def device_row(db, device_id):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT owner_kind, policy_ok, policy_sha, policy_reported FROM devices WHERE device_id = ?",
                          (device_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        con.close()


def audit_lines(db, device_id):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM audit WHERE action = ? AND correlation = ?",
                           (AUDIT, f"device:{device_id}")).fetchone()[0]
    finally:
        con.close()


def opens(owner, person_id, since, tool):
    status, out = owner.call("GET", f"/launches?person={person_id}&since={since}")
    return len([r for r in out.get("items", []) if r.get("tool_id") == tool and r.get("outcome") == "opened"]) if status == 200 else -1


def run(check, run_app, enrol_company, owner, db, person_id, data, evidence, tool="canva"):
    """check(name, ok, detail) records a step; run_app(*args) -> (exit, output) runs the installed app;
    enrol_company() signs the installed app in as a company device and returns its device id."""
    import hub_journey  # packaging/, already on sys.path when the macOS journey runs

    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("runner only: this replaces and removes the device-wide Chrome policy; GitHub-hosted runners only")

    report = {"plist": str(PLIST), "cases": []}
    work = Path(tempfile.mkdtemp(prefix="swangz-policy-"))
    policy, baseline = prepare(work)
    report["baseline"] = baseline
    check("policy: pack prepared by deploy/chrome-policy/prepare.py (CI placeholders), baseline printed", bool(baseline), baseline)
    status, _ = owner.call("PUT", "/settings", {"managed_policy_sha256": baseline, "managed_policy_mode": "enforce"})
    check("policy: the admin pins the baseline in enforce mode", status == 200, f"HTTP {status}")
    try:
        uid, mode = install(policy)
        check("policy: the pack is installed device-wide, owned by root", uid == 0 and mode == "0o644", f"uid {uid}, {mode}")
        owners = chrome_root_owned()
        check("policy: Chrome in /Applications is root-owned, as on a company Mac (D-026 A4)", owners == (0, 0),
              f"app uid {owners[0]}, executable uid {owners[1]}")
        device_id = enrol_company()
        row = device_row(db, device_id)
        check("policy: the app is signed in as a company device", row.get("owner_kind") == "company", str(row.get("owner_kind")))

        def opened(label):
            before = time.time() - 1
            code, out = run_app("open", tool)
            folders = hub_journey.workspace_folders(data)
            started = code == 0 and any(chrome_running(f) for f in folders) and any(hub_journey.chrome_wrote(f) for f in folders)
            for f in folders:
                hub_journey.close_chrome(f)
            n = opens(owner, person_id, before, tool)
            check(f"policy {label}: Open starts the workspace window and the Hub records it",
                  code == 0 and started and n >= 1, f"exit {code}, Chrome started {started}, opens {n}")
            report["cases"].append({"case": label, "open_exit": code, "chrome_started": started, "hub_opens": n})

        def refused(label):
            before = time.time() - 1
            code, out = run_app("open", tool)
            n = opens(owner, person_id, before, tool)
            check(f"policy {label}: Open is refused with the policy message and the Hub records no open",
                  code == 1 and REFUSED in out and n == 0, f"exit {code}, opens {n}, {out.strip()[-160:]}")
            report["cases"].append({"case": label, "open_exit": code, "hub_opens": n, "message": REFUSED in out})

        def synced(label, ok, sha_is_baseline):
            code, _ = run_app("sync")
            row = device_row(db, device_id)
            want_sha = (row.get("policy_sha") == baseline) if sha_is_baseline else (row.get("policy_sha") != baseline)
            check(f"policy {label}: sync reports it and the Hub records policy_ok={int(ok)}"
                  + (", the baseline hash" if sha_is_baseline else ", a hash that is not the baseline"),
                  code == 0 and row.get("policy_ok") == int(ok) and want_sha,
                  f"exit {code}, policy_ok {row.get('policy_ok')}, sha {str(row.get('policy_sha'))[:16]}")
            report["cases"].append({"case": label + " (sync)", "sync_exit": code, "hub_policy_ok": row.get("policy_ok"),
                                    "hub_policy_sha": row.get("policy_sha")})

        synced("intact", True, True)
        opened("intact")

        install(without_default_deny(policy))
        before = audit_lines(db, device_id)  # Open refreshes first, so its check-in may already carry the report
        refused("tampered, default-deny removed")
        synced("tampered, default-deny removed", False, False)
        after = audit_lines(db, device_id)
        check("policy tampered: the Hub's audit log records the device reporting its policy is not in force",
              after == before + 1, f"{before} -> {after}")

        install(extra_block(policy))
        refused("tampered, valid but not the pinned pack")
        synced("tampered, valid but not the pinned pack", True, False)

        install(policy)
        opened("restored")
        synced("restored", True, True)

        remove()
        check("policy: pack removed", not PLIST.exists(), str(PLIST))
        refused("removed")
        synced("removed", False, False)

        code, out = run_app("logout")
        check("policy: the company device signs out", signed_out(code, out), out.strip()[-160:])
    finally:
        remove()
        owner.call("PUT", "/settings", {"managed_policy_sha256": "", "managed_policy_mode": "warn"})
        (Path(evidence) / "policy-tamper.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
