"""The Control Room's Workstations page (owner directive, 27 Nov 2026): one read that answers the owner's list —
employees, devices and their apps, who has what, seats against single company logins, what Swangz observed, and the
weekly reports — with metadata only. Suspend and revoke on the page use the existing device and key routes."""

import json
import pathlib
import re
import shutil
import subprocess
import time
import unittest

from gateway import workstations

from .test_devices import DeviceBase

STATIC = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"


def ensure_apps_columns(db):
    """Schema v31 (the desktop app's heartbeat) adds these; add them here only if this branch does not have it yet."""
    have = {r["name"] for r in db.q("PRAGMA table_info(devices)")}
    if "apps_json" not in have:
        db.x("ALTER TABLE devices ADD COLUMN apps_json TEXT NOT NULL DEFAULT '[]'")
    if "apps_reported" not in have:
        db.x("ALTER TABLE devices ADD COLUMN apps_reported REAL")


class WorkstationsBase(DeviceBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db

    def read(self, who="owner"):
        status, out = self.rig.api("GET", "/workstations", who=who)
        self.assertEqual(status, 200, out)
        return out

    def raw(self, who="owner"):
        if who not in self.rig.cookies:
            self.rig.login(who)
        return self.rig.request("GET", "/admin/api/workstations", None, {"cookie": self.rig.cookies[who], "x-gateway-admin": "1"})

    def person(self, name, department="", status="active"):
        return self.db.x("INSERT INTO people(name, email, department, status, created) VALUES(?,?,?,?,?)",
                         (name, name.split()[0].lower() + "@swangzavenue.com", department, status, time.time())).lastrowid

    def device_row(self, did):
        return next(d for d in self.read()["devices"]["items"] if d["device_id"] == did)


class ReadTests(WorkstationsBase):
    def test_every_console_user_may_read_it_and_nobody_signed_out_may(self):
        self.assertEqual(self.read("viewer")["online_minutes"], 20)
        status, _, _ = self.rig.request("GET", "/admin/api/workstations", None, {"x-gateway-admin": "1"})
        self.assertEqual(status, 401)

    def test_employees_and_departments_are_counted_from_people(self):
        self.person("Okello Brian", "Creative")
        self.person("Atim Sarah", "Finance")
        self.person("Mugisha Paul", "", status="suspended")
        e = self.read()["employees"]
        self.assertEqual((e["total"], e["active"], e["suspended"]), (4, 3, 1))
        self.assertEqual(e["departments"], [{"name": "Creative", "people": 2}, {"name": "Finance", "people": 1}])
        self.assertEqual((e["with_device"], e["without_device"]), (0, 3))

    def test_the_turns_retirement_date_is_stated(self):
        self.assertEqual(self.read()["turns_retired"], "2026-11-27")


class DeviceTests(WorkstationsBase):
    def test_an_enrolled_device_is_online_for_twenty_minutes_then_offline(self):
        did = self.enrol("company")["device_id"]
        d = self.device_row(did)
        self.assertTrue(d["connected"])
        self.assertTrue(d["online"])
        self.assertEqual((d["person"], d["app_version"], d["owner_kind"], d["workspace"]), ("Nansubuga Grace", "0.1.0", "company", "active"))
        self.db.x("UPDATE devices SET last_seen = ? WHERE device_id = ?", (time.time() - 21 * 60, did))
        out = self.read()
        self.assertFalse(self.device_row(did)["online"])
        self.assertEqual((out["devices"]["summary"]["online"], out["devices"]["summary"]["offline"]), (0, 1))
        self.assertEqual(out["employees"]["with_device"], 1)

    def test_without_the_apps_columns_the_device_simply_reports_no_apps(self):
        did = self.enrol()["device_id"]
        if "apps_json" in {r["name"] for r in self.db.q("PRAGMA table_info(devices)")}:
            self.skipTest("schema v31 is on this branch")
        d = self.device_row(did)
        self.assertEqual((d["apps"], d["chrome"], d["apps_reported"]), ([], None, None))

    def test_chrome_and_ai_apps_come_from_the_apps_the_app_reported(self):
        did = self.enrol()["device_id"]
        ensure_apps_columns(self.db)
        apps = [{"id": "chrome", "state": "installed", "version": "131.0"}, {"id": "claude-code", "state": "installed", "version": "2.1"},
                {"id": "chatgpt", "state": "web", "version": ""}, {"id": "codex", "state": "missing", "version": ""},
                {"id": "midjourney", "state": "exploded"}, {"state": "installed"}, "nonsense"]
        self.db.x("UPDATE devices SET apps_json = ?, apps_reported = ? WHERE device_id = ?", (json.dumps(apps), time.time(), did))
        d = self.device_row(did)
        self.assertEqual((d["chrome"], d["chrome_version"]), ("installed", "131.0"))
        self.assertEqual([(a["id"], a["state"]) for a in d["apps"]],
                         [("claude-code", "installed"), ("chatgpt", "web"), ("codex", "missing"), ("midjourney", "unknown")])
        self.assertEqual(d["apps"][0]["name"], "Claude Code")  # named from the catalogue

    def test_unreadable_apps_are_left_out_never_guessed(self):
        did = self.enrol()["device_id"]
        ensure_apps_columns(self.db)
        for raw in ("{not json", '{"id": "chrome"}', "null"):
            self.db.x("UPDATE devices SET apps_json = ? WHERE device_id = ?", (raw, did))
            self.assertEqual((self.device_row(did)["apps"], self.device_row(did)["chrome"]), ([], None), raw)

    def test_suspend_and_revoke_work_with_the_ids_the_page_is_given(self):
        did = self.enrol()["device_id"]
        d = self.device_row(did)
        status, out = self.rig.api("POST", f"/devices/{d['device_id']}/workspace", {"action": "suspend", "reason": "lost laptop"})
        self.assertEqual(status, 200, out)
        self.assertEqual(self.device_row(did)["workspace"], "suspended")
        audit = self.db.one("SELECT reason FROM audit WHERE action = 'suspend the workspace on a device' ORDER BY id DESC")
        self.assertEqual(audit["reason"], "lost laptop")
        status, out = self.rig.api("POST", f"/keys/{d['key_id']}/revoke", {"reason": "left the company"})
        self.assertEqual(status, 200, out)
        after = self.device_row(did)
        self.assertEqual((after["connected"], after["online"], after["key_id"]), (False, False, None))
        self.assertEqual(self.read()["devices"]["summary"]["disconnected"], 1)

    def test_a_viewer_reads_the_page_but_cannot_suspend_or_revoke(self):
        did = self.enrol()["device_id"]
        d = self.device_row(did)
        self.assertEqual(self.rig.api("POST", f"/devices/{did}/workspace", {"action": "suspend"}, who="viewer")[0], 403)
        self.assertEqual(self.rig.api("POST", f"/keys/{d['key_id']}/revoke", {}, who="viewer")[0], 403)

    def test_no_key_secret_hash_or_address_leaves_the_server(self):
        enrolled = self.enrol()
        status, _, payload = self.raw()
        text = payload.decode()
        self.assertEqual(status, 200)
        for row in self.db.q("SELECT secret_hash FROM keys"):
            self.assertNotIn(row["secret_hash"], text)
        self.assertNotIn(enrolled["key"], text)
        self.assertNotIn(enrolled["key"].split("_")[-1], text)
        for word in ("secret_hash", "last_ip", "user_agent", "prompt", "password", "cookie", "@swangzavenue.com"):
            self.assertNotIn(word, text)


class AppsAndAccountsTests(WorkstationsBase):
    def test_who_has_what_counts_direct_and_department_grants(self):
        brian = self.person("Okello Brian", "Creative")
        self.person("Atim Sarah", "Finance")
        self.assertEqual(self.rig.api("POST", "/teams/Creative/tools/canva")[0], 200)
        self.assertEqual(self.rig.api("POST", f"/people/{brian}/tools/midjourney")[0], 200)
        items = {x["tool_id"]: x for x in self.read()["assigned"]["items"]}
        self.assertEqual((items["canva"]["people"], items["canva"]["teams"]), (2, ["Creative"]))
        self.assertEqual(items["canva"]["names"], ["Nansubuga Grace", "Okello Brian"])
        self.assertEqual((items["midjourney"]["people"], items["midjourney"]["names"]), (1, ["Okello Brian"]))
        self.assertEqual(items["claude-code"]["signin"], "api")

    def test_a_single_company_login_is_named_as_an_account_limitation_with_no_timer(self):
        brian = self.person("Okello Brian", "Creative")
        self.assertEqual(self.rig.api("PATCH", "/tools/midjourney", {"signin": "shared"})[0], 200)
        self.rig.api("PUT", "/subscriptions/midjourney", {"state": "active", "monthly_cost": 30})
        self.rig.api("PUT", "/subscriptions/canva", {"state": "active", "monthly_cost": 30, "seats": 1})
        for pid in (brian, self.rig.person_id):
            self.rig.api("POST", f"/people/{pid}/tools/midjourney")
            self.rig.api("POST", f"/people/{pid}/tools/canva")
        out = self.read()["accounts"]
        items = {x["tool_id"]: x for x in out["items"]}
        mj = items["midjourney"]
        self.assertEqual((mj["signin"], mj["assigned"]), ("shared", 2))
        self.assertIn("one person per login", mj["limitation"]["text"])
        self.assertIn("seat of their own", mj["limitation"]["recommendation"])
        self.assertIsNone(items["canva"]["limitation"])
        self.assertTrue(items["canva"]["over_seats"])
        self.assertEqual((out["summary"]["single_logins"], out["summary"]["over_seats"]), (1, 1))
        self.assertEqual(out["items"][0]["tool_id"], "midjourney")  # limitations first
        for word in ("turn", "minutes", "queue", "seats_at_once"):
            self.assertNotIn(word, json.dumps(mj))

    def test_coding_agents_are_not_listed_as_accounts(self):
        self.assertNotIn("claude-code", [x["tool_id"] for x in self.read()["accounts"]["items"]])


class ActivityAndReportsTests(WorkstationsBase):
    def test_activity_is_observed_in_swangz_and_provider_reports_are_said_to_be_missing(self):
        now = time.time()
        pid = self.rig.person_id
        self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome, ip) VALUES('canva', ?, ?, 'opened', '203.0.113.9')", (pid, now - 60))
        self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('canva', ?, ?, 'refused')", (pid, now - 50))
        self.db.x("INSERT INTO site_usage(tool_id, person_id, host, outcome, started, seconds) VALUES('chatgpt', ?, 'chatgpt.com', 'allowed', ?, 300)", (pid, now - 30))
        self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('canva', ?, ?, 'opened')", (pid, now - 8 * 86400))
        a = self.read()["activity"]
        self.assertEqual((a["label"], a["source"], a["days"]), ("Observed in Swangz", "observed", 7))
        self.assertEqual((a["opens"], a["opens_refused"], a["visits"], a["visits_blocked"], a["people"]), (1, 1, 1, 0, 1))
        self.assertEqual([(r["kind"], r["tool_id"]) for r in a["recent"]], [("visit", "chatgpt"), ("open", "canva"), ("open", "canva")])
        self.assertEqual(a["provider"]["label"], "Provider-reported usage and billing")
        self.assertFalse(a["provider"]["available"])
        status, _, payload = self.raw()
        self.assertNotIn("203.0.113.9", payload.decode())

    def test_weekly_reports_name_the_last_closed_week(self):
        w = self.read()["weekly"]
        self.assertEqual(time.strptime(w["week_start"], "%Y-%m-%d").tm_wday, 0)  # a Monday
        for k in ("submitted", "missing", "outstanding_all"):
            self.assertIsInstance(w[k], int)

    def test_the_apps_reader_ignores_what_is_not_a_list_of_apps(self):
        self.assertEqual(workstations._apps('[{"id": " x ", "state": "web"}]', {}), [{"id": "x", "name": "x", "state": "web", "version": ""}])
        self.assertEqual(workstations._apps(None, {}), [])
        self.assertEqual(workstations._apps("[1, 2]", {}), [])


def lead(cases):
    source = (STATIC / "admin-workstations.js").read_text(encoding="utf-8")
    many = re.search(r"\n  (const many = .*?;)\n", source).group(1)
    fn = re.search(r"\n  (function workstationsLead\(n\) \{\n.*?\n  \})\n", source, re.S).group(1)
    script = many + fn + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(workstationsLead)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class PageLeadTests(unittest.TestCase):
    """BRIEF 10.10.7: one plain sentence with the real number, then one next step that is never a dead end."""
    BASE = {"loaded": True, "people": 8, "connected": 5, "online": 5, "offline": 0, "withoutDevice": 0, "singleLogins": 0, "missing": 0}

    def one(self, **n):
        return lead([{**self.BASE, **n}])[0]

    def test_a_single_company_login_is_named_first_and_opens_the_accounts(self):
        out = self.one(singleLogins=2, offline=3, missing=4)
        self.assertEqual(out["sentence"], "2 tools use one company login.")
        self.assertEqual(out["action"]["href"], "#/workstations?view=detailed&focus=accounts")

    def test_then_people_without_a_workstation_then_missing_reports_then_offline(self):
        self.assertEqual(self.one(withoutDevice=1, missing=2)["sentence"], "1 person has no workstation yet.")
        self.assertEqual(self.one(missing=2, offline=1)["sentence"], "2 weekly reports are missing.")
        self.assertEqual(self.one(offline=2)["sentence"], "2 of 5 computers are offline.")
        self.assertEqual(self.one()["sentence"], "All 5 computers are online.")

    def test_empty_and_failed_are_never_a_dead_end(self):
        self.assertEqual(self.one(people=0)["action"]["href"], "#/people?add=1")
        self.assertEqual(self.one(connected=0)["sentence"], "No computer has the Swangz app yet.")
        self.assertTrue(lead([{"loaded": False}])[0]["action"]["retry"])

    def test_no_sentence_speaks_of_turns_or_waiting(self):
        cases = [{**self.BASE, **x} for x in ({"singleLogins": 1}, {"withoutDevice": 3}, {"missing": 1}, {"offline": 1}, {}, {"connected": 1, "online": 1})]
        for out in lead(cases):
            self.assertNotRegex(out["sentence"].lower(), r"\bturns?\b|queue|wait|hand back")
            self.assertLessEqual(len(out["sentence"].split()), 12)


class ConsoleWiringTests(unittest.TestCase):
    def test_workstations_is_first_in_the_rail_the_menu_and_the_landing(self):
        admin = (STATIC / "admin.js").read_text(encoding="utf-8")
        self.assertIn('const RAIL = ["#/workstations", "#/",', admin)
        self.assertIn('["Monitor", [["#/workstations", "Workstations", "monitor"], ["#/", "Overview", "overview"]', admin)
        self.assertIn('"#/workstations");', admin[admin.index("function landing()"):])
        html = (STATIC / "admin.html").read_text(encoding="utf-8")
        self.assertLess(html.index("/static/admin.js"), html.index("/static/admin-workstations.js"))
        self.assertIn('href="/static/workstations.css"', html)

    def test_suspend_and_revoke_ask_why_in_a_dialog_never_a_browser_alert(self):
        page = (STATIC / "admin-workstations.js").read_text(encoding="utf-8")
        self.assertNotRegex(page, r"\b(alert|confirm|prompt)\(")
        self.assertIn('`/devices/${encodeURIComponent(d.device_id)}/workspace`, { action: "suspend", reason }', page)
        self.assertIn('`/keys/${encodeURIComponent(d.key_id)}/revoke`, { reason }', page)
        self.assertIn('"Observed in Swangz"', page)


class TurnsRetiredInTheUiTests(unittest.TestCase):
    """27 Nov 2026: no turns, queues, countdowns or hand-backs on any screen; a single company login names its limitation;
    past turns stay readable as history."""

    def read(self, name):
        return (STATIC / name).read_text(encoding="utf-8")

    def test_the_staff_app_has_no_turn_controls_and_names_the_company_login(self):
        portal = self.read("portal.js")
        # "Yours until <date>" stays: that is a grant's end date, not a turn's clock time
        for gone in ("Take your turn", "Hand back", "takes turns", "your turn", ".turn", "turn/end", "In use — free at", '"Yours until " + fmt.clock'):
            self.assertFalse(gone in portal, gone)
        self.assertIn("One login the company pays for. The provider may not let several people use it at once", portal)
        self.assertIn("t.account_note", portal)

    def test_the_console_edits_no_turn_settings_and_keeps_history_read_only(self):
        govern = self.read("admin-govern.js")
        for gone in ("seats_at_once", "turn_minutes", '"/turns"', "Take it back", "How long a turn lasts", "workspaceTab"):
            self.assertFalse(gone in govern, gone)
        self.assertIn('A.panel("Account limitation"', govern)
        self.assertIn("History — turns were retired on 27 Nov 2026", govern)
        self.assertIn('if (params.get("tab") === "workspace") params.set("tab", "account");', govern)
        self.assertNotIn('"/turns"', self.read("admin-monitor.js"))
        self.assertNotIn("Take back a shared turn", self.read("admin-money.js"))


if __name__ == "__main__":
    unittest.main()
