"""Probe: section 9.3 demo, steps 1-4: real headless Chrome 156 against the in-process fake Hub (tests.test_client.ClientBase).
import json, os, subprocess, sys, time, unittest
from pathlib import Path

REPO = os.environ["DEMO_REPO"]
sys.path.insert(0, REPO)
from tests.test_client import ClientBase  # noqa: E402
from swangz_client import workspace_launcher as wl  # noqa: E402

WRAP = str(Path(__file__).with_name("chrome-headless.sh"))
OUT = {}


def chrome_procs(folder):
    """Main chrome processes whose command line carries this --user-data-dir."""
    res = []
    for line in subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout.splitlines():
        if "--user-data-dir=" + str(folder) in line and "--type=" not in line:
            res.append(line.strip())
    return res


def tree(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*") if p.is_file())[:40] if Path(folder).exists() else None


class Demo(ClientBase):
    def setUp(self):
        super().setUp()
        for t, cost in (("gemini", 20), ("perplexity", 20), ("canva", 15)):
            self.rig.api("PUT", f"/subscriptions/{t}", {"state": "active", "monthly_cost": cost, "seats": 5})
            self.assertEqual(self.rig.api("POST", f"/people/{self.rig.person_id}/tools/{t}")[0], 200)
        self.sign_in()
        self.client.refresh()
        Path(self.data).mkdir(mode=0o700, exist_ok=True); os.chmod(self.data, 0o700)
        self.client.launcher = wl.Launcher(self.data, finder=lambda: WRAP)
        self.addCleanup(self.client.launcher.close)

    def device_id(self):
        return self.client.store.device()["device_id"] if "device_id" in (self.client.store.device() or {}) else \
            self.gw.db.scalar("SELECT device_id FROM devices ORDER BY rowid DESC LIMIT 1")

    def admin(self, action):
        return self.rig.api("POST", f"/devices/{self.device_id()}/workspace", {"action": action}, who="owner")

    def profiles(self):
        root = Path(self.data) / "browser-profiles"
        return sorted(p for p in root.iterdir() if not p.name.startswith(".")) if root.exists() else []

    def test_93(self):
        c, log = self.client, OUT.setdefault("steps", {})
        before = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout
        other = lambda: sorted(l.split()[0] for l in subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True).stdout.splitlines()[1:] if 'chrome' in l and 'browser-profiles' not in l and 'demo93' not in l and 'chrome-headless' not in l)
        others_before = other()
        apps = {a["id"]: a for a in c.apps()}
        log["manifest_apps"] = {k: {"workspace": apps[k].get("workspace"), "hosts": apps[k].get("hosts")} for k in ("gemini", "perplexity", "canva") if k in apps}
        # ---- step 1
        res1 = {}
        for t in ("gemini", "perplexity", "canva"):
            try:
                res1[t] = c.open_app(t)
            except Exception as exc:  # noqa
                res1[t] = f"ERR {type(exc).__name__}: {exc}"
            time.sleep(1.5)
        newp = sorted(set(other()) - set(others_before))
        rows = {l.split(None, 2)[0]: l.split(None, 2) for l in subprocess.run(['ps','-eo','pid,ppid,args'],capture_output=True,text=True).stdout.splitlines()[1:]}
        def under_ours(pid):
            while pid in rows:
                if 'browser-profiles' in rows[pid][2]: return True
                pid = rows[pid][1]
            return False
        log['other_chrome_new'] = [(p_, 'child of workspace chrome' if under_ours(p_) else 'NOT ours', rows.get(p_, ['','',''])[2][:90]) for p_ in newp]
        folders = self.profiles()
        log["step1"] = {"open_results": res1, "folders": [p.name for p in folders],
                        "procs": [chrome_procs(p) for p in folders],
                        "launches": [dict(r) for r in self.gw.db.q("SELECT tool_id, outcome, device_id FROM launches ORDER BY id")],
                        "log": (Path(self.data) / "workspace-open.log").read_text() if (Path(self.data) / "workspace-open.log").exists() else None}
        if len(folders) != 1:
            Path(os.environ.get('DEMO_OUT','/tmp/demo93.json')).write_text(json.dumps(OUT, indent=1, default=str))
        self.assertEqual(len(folders), 1)
        folder = folders[0]
        (folder / "Default").mkdir(exist_ok=True)
        (folder / "Default" / "probe-marker").write_text("m1")
        ino = folder.stat().st_ino
        # ---- step 2: reopen
        c.launcher.close()
        time.sleep(1)
        res2 = c.open_app("gemini")
        time.sleep(1.5)
        folders2 = self.profiles()
        log["step2"] = {"result": res2, "same_folder": [p.name for p in folders2] == [folder.name], "same_inode": folder.stat().st_ino == ino,
                        "marker_kept": (folder / "Default" / "probe-marker").read_text() == "m1", "procs": chrome_procs(folder), "files": tree(folder)}
        # ---- step 3: suspend
        log["step3_suspend_api"] = self.admin("suspend")[0]
        n0 = self.gw.db.scalar("SELECT COUNT(*) FROM launches")
        try:
            pre = c.open_app("canva")
        except Exception as exc:  # noqa
            pre = f"{type(exc).__name__}: {exc}"
        log["step3_open_before_heartbeat"] = {"result": pre, "new_launch_rows": [dict(r) for r in self.gw.db.q("SELECT tool_id, outcome, rule, reason FROM launches ORDER BY id")][n0:]}
        t0 = time.time()
        c.heartbeat()
        log["step3_heartbeat_seconds"] = round(time.time() - t0, 2)
        time.sleep(1)
        refusal = None
        try:
            c.open_app("gemini")
        except Exception as exc:  # noqa
            refusal = f"{type(exc).__name__}: {exc}"
        log["step3"] = {"procs_after_suspend": chrome_procs(folder), "refusal": refusal, "folder_kept": folder.exists(),
                        "launches": [dict(r) for r in self.gw.db.q("SELECT tool_id, outcome FROM launches ORDER BY id")][-2:]}
        log["step3_reactivate_api"] = self.admin("reactivate")[0]
        c.heartbeat()
        log["step3_reopen"] = c.open_app("gemini")
        time.sleep(1.5)
        log["step3_after_reactivate"] = {"procs": chrome_procs(folder), "marker_kept": (folder / "Default" / "probe-marker").exists()}
        # ---- step 4: retire
        c.launcher.close()
        log["step4_retire_api"] = self.admin("retire")[0]
        c.heartbeat()
        time.sleep(1)
        refusal4 = None
        try:
            c.open_app("gemini")
        except Exception as exc:  # noqa
            refusal4 = f"{type(exc).__name__}: {exc}"
        gen_row = self.gw.db.one("SELECT workspace_state s, workspace_generation g FROM devices WHERE device_id = ?", (self.device_id(),))
        log["step4"] = {"folder_exists": folder.exists(), "profiles_left": [p.name for p in self.profiles()], "refusal": refusal4,
                        "server": dict(gen_row), "procs": chrome_procs(folder)}
        log["step4_reactivate_api"] = self.admin("reactivate")[0]
        c.heartbeat()
        gen_row = self.gw.db.one("SELECT workspace_state s, workspace_generation g FROM devices WHERE device_id = ?", (self.device_id(),))
        r = None
        try:
            r = c.open_app("gemini")
        except Exception as exc:  # noqa
            r = f"{type(exc).__name__}: {exc}"
        time.sleep(1.5)
        new = self.profiles()
        log["step4_after_reactivate"] = {"server": dict(gen_row), "open": r, "new_folder_differs": [p.name for p in new] != [folder.name], "folders": [p.name for p in new],
                                         "marker_gone": not any((p / "Default" / "probe-marker").exists() for p in new)}
        log['audit'] = [dict(r) for r in self.gw.db.q("SELECT action, outcome FROM audit WHERE action LIKE '%workspace%' ORDER BY rowid")]
        c.launcher.close()
        time.sleep(1)
        log["leftover_chrome"] = [l for l in subprocess.run(["ps", "-eo", "pid,args"], capture_output=True, text=True).stdout.splitlines() if "browser-profiles" in l]
        Path(os.environ.get("DEMO_OUT", "/tmp/demo93.json")).write_text(json.dumps(OUT, indent=1, default=str))


if __name__ == "__main__":
    unittest.main()
