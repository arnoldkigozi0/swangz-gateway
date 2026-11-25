"""D-025 point 2: an admin confirms or changes whether an enrolled device is the company's. The mark wins over the
person's own declaration in `enforce`, is audited, needs the govern area, and never lets the app edit the coding-agent
settings of a computer its person called personal."""

import os
import sqlite3
import tempfile
import unittest

from gateway import managed
from gateway.db import DB, SCHEMA

from .test_managed_workspace import SHA, Base
from .test_v2 import add_admin
from .test_workspace_state import device as stored_device

COLUMNS = ("owner_confirmed", "owner_confirmed_at", "owner_confirmed_by")


class KindBase(Base):
    def mark(self, kind="company", did=None, who="owner", **body):
        return self.rig.api("POST", f"/devices/{did or self.did}/kind", dict({"kind": kind}, **body), who=who)

    def stored(self, did=None):
        row = self.db.one("SELECT owner_kind, owner_confirmed FROM devices WHERE device_id = ?", (did or self.did,))
        return row["owner_kind"], row["owner_confirmed"]

    def audits(self):
        return [dict(r) for r in self.db.q("SELECT * FROM audit WHERE action LIKE 'marked a device as %' ORDER BY id")]

    def enforce(self):
        self.assertEqual(self.rig.api("PUT", "/settings", {"managed_policy_sha256": SHA, "managed_policy_mode": "enforce"})[0], 200)

    def device_open(self, policy=None):
        status, out, _ = self.api("POST", "/device/open", dict({"tool": "canva"}, **({"policy": policy} if policy else {})), key=self.key)
        return status, out

    def agent_mode(self):
        modes = [p["install"]["mode"] for p in self.manifest()["packages"] if p["id"] == "claude-code"]
        self.assertEqual(len(modes), 1, "the rig grants Claude Code")
        return modes[0]


class DeclaredPersonalTests(KindBase):
    def test_marked_company_it_is_refused_in_enforce_until_it_reports_the_baseline(self):
        self.enable_canva()
        self.enforce()
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)  # declared personal, unmarked: no pack, no refusal
        self.assertEqual(self.device_open()[0], 200)
        self.assertEqual(self.mark("company")[0], 200)
        status, _, body = self.go(f"?d={self.did}")
        self.assertEqual(status, 403)
        self.assertIn("has not reported its browser policy", body)
        status, out = self.device_open()
        self.assertEqual((status, out.get("code")), (409, "workspace_policy"), out)
        status, out = self.device_open({"ok": True, "sha256": "b" * 64})
        self.assertEqual((status, out.get("code")), (409, "workspace_policy"), out)
        status, out = self.device_open({"ok": True, "sha256": SHA})
        self.assertEqual(status, 200, out)
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)

    def test_the_manifest_tells_the_app_it_is_company_but_never_to_edit_the_persons_tools(self):
        before = self.manifest()["device"]
        self.assertEqual(before["owner_kind"], "personal")
        self.assertNotIn("owner_confirmed", before)  # an unmarked device gets the answer it always got
        self.assertEqual(self.agent_mode(), "scoped")
        self.mark("company")
        after = self.manifest()["device"]
        self.assertEqual((after["owner_kind"], after["owner_confirmed"]), ("company", "company"))
        self.assertEqual(self.agent_mode(), "scoped")
        self.assertEqual(self.stored(), ("personal", "company"))  # the declaration is kept

    def test_the_change_is_audited_with_before_after_and_the_device(self):
        status, out = self.mark("company", reason="asset register 14")
        self.assertEqual(status, 200, out)
        self.assertTrue(out["changed"])
        row = self.db.one("SELECT * FROM devices WHERE device_id = ?", (self.did,))
        self.assertEqual(out["device"], {"device_id": self.did, "owner_kind": "personal", "owner_confirmed": "company",
                                         "owner_confirmed_at": row["owner_confirmed_at"], "owner_confirmed_by": row["owner_confirmed_by"],
                                         "effective_kind": "company"})
        self.assertIsNotNone(row["owner_confirmed_at"])
        [entry] = self.audits()
        self.assertEqual((entry["action"], entry["correlation"], entry["area"], entry["outcome"], entry["reason"], entry["actor"]),
                         ("marked a device as company", f"device:{self.did}", "govern", "ok", "asset register 14", row["owner_confirmed_by"]))
        self.assertEqual(entry["before_json"], '{"confirmed": null, "declared": "personal"}')
        self.assertEqual(entry["after_json"], '{"confirmed": "company", "declared": "personal"}')

    def test_repeating_a_mark_changes_and_audits_nothing_and_it_can_be_changed_back(self):
        self.mark("company")
        at = self.db.scalar("SELECT owner_confirmed_at FROM devices WHERE device_id = ?", (self.did,))
        status, out = self.mark("company")
        self.assertEqual((status, out["changed"]), (200, False))
        self.assertEqual(len(self.audits()), 1)
        self.assertEqual(self.db.scalar("SELECT owner_confirmed_at FROM devices WHERE device_id = ?", (self.did,)), at)
        self.assertEqual(self.mark("personal")[1]["device"]["effective_kind"], "personal")
        self.assertEqual(self.audits()[-1]["before_json"], '{"confirmed": "company", "declared": "personal"}')

    def test_nothing_the_device_sends_sets_or_clears_the_mark(self):
        self.mark("company")
        claim = {"owner_kind": "personal", "owner_confirmed": "personal", "kind": "personal"}
        self.assertEqual(self.beat(dict(claim, browser_contract=2))[0], 200)
        self.manifest("?browser_contract=2&owner_kind=personal&owner_confirmed=personal")
        self.assertEqual(self.stored(), ("personal", "company"))
        status, _, _ = self.rig.request("POST", f"/admin/api/devices/{self.did}/kind", {"kind": "personal"},
                                        {"x-gateway-admin": "1", "authorization": "Bearer " + self.key})
        self.assertEqual(status, 401)
        self.assertEqual(self.stored(), ("personal", "company"))

    def test_a_new_enrolment_starts_unmarked(self):
        self.mark("company")
        again = self.enrol("personal", name="Grace's laptop again")
        self.assertEqual(self.stored(again["device_id"]), ("personal", None))


class DeclaredCompanyTests(KindBase):
    OWNER = "company"

    def test_marked_personal_it_is_exempt_and_the_app_is_told_to_stop_configuring_agents(self):
        self.enable_canva()
        self.enforce()
        self.assertEqual(self.agent_mode(), "managed")
        self.assertEqual(self.device_open()[0], 409)
        self.assertEqual(self.mark("personal")[0], 200)
        self.assertEqual(self.go(f"?d={self.did}")[0], 302)
        self.assertEqual(self.device_open()[0], 200)
        shown = self.manifest()["device"]
        self.assertEqual((shown["owner_kind"], shown["owner_confirmed"]), ("personal", "personal"))
        self.assertEqual(self.agent_mode(), "scoped")

    def test_confirming_it_keeps_managed_mode_and_enforcement(self):
        self.enable_canva()
        self.enforce()
        status, out = self.mark("company")
        self.assertEqual((status, out["changed"]), (200, True))  # a confirmation is recorded even when the kind is the same
        self.assertEqual(self.manifest()["device"]["owner_confirmed"], "company")
        self.assertEqual(self.agent_mode(), "managed")
        self.assertEqual(self.device_open()[0], 409)


class AccessTests(KindBase):
    def test_only_the_govern_area_may_mark_a_device(self):
        for name in ("security", "billing", "operations"):
            add_admin(self.db, name, name)
        for who in ("viewer", "billing", "security"):
            self.assertEqual(self.mark(who=who)[0], 403, who)
        self.assertEqual(self.stored(), ("personal", None))
        denied = self.db.scalar("SELECT COUNT(*) FROM audit WHERE outcome = 'denied' AND target LIKE '%/kind'")
        self.assertEqual(denied, 3)
        path = f"/admin/api/devices/{self.did}/kind"
        self.assertEqual(self.rig.request("POST", path, {"kind": "company"}, {"x-gateway-admin": "1"})[0], 401)
        self.assertEqual(self.rig.request("POST", path, {"kind": "company"}, {"cookie": self.person_cookie, "x-gateway-admin": "1"})[0], 401)
        self.assertEqual(self.rig.request("POST", path, {"kind": "company"}, {})[0], 403)  # no console header
        self.assertEqual(self.stored(), ("personal", None))
        self.assertEqual(self.mark(who="operations")[0], 200)

    def test_bad_values_and_unknown_devices_change_nothing(self):
        for bad in (None, "", "Company", "COMPANY", " company", "byod", 1, True, ["company"], {"kind": "company"}):
            self.assertEqual(self.mark(bad)[0], 400, repr(bad))
        self.assertEqual(self.rig.api("POST", f"/devices/{self.did}/kind", {})[0], 400)
        self.assertEqual(self.mark(did="dev-unknown-1")[0], 404)
        self.assertEqual(self.stored(), ("personal", None))
        self.assertEqual(self.audits(), [])

    def test_the_console_lists_and_shows_the_declaration_and_the_mark(self):
        def listed():
            status, out = self.rig.api("GET", "/devices", who="viewer")
            self.assertEqual(status, 200, out)
            return next(i for i in out["items"] if i["device_id"] == self.did)

        item = listed()
        self.assertEqual((item["owner_kind"], item["owner_confirmed"], item["owner_confirmed_by"], item["effective_kind"]),
                         ("personal", None, None, "personal"))
        self.mark("company")
        item = listed()
        self.assertEqual((item["owner_kind"], item["owner_confirmed"], item["effective_kind"]), ("personal", "company", "company"))
        status, one = self.rig.api("GET", f"/devices/{item['id']}", who="viewer")
        self.assertEqual(status, 200, one)
        for field in ("owner_kind", "owner_confirmed", "owner_confirmed_at", "owner_confirmed_by", "effective_kind"):
            self.assertEqual(one[field], item[field], field)


class RuleTests(unittest.TestCase):
    def test_an_unreadable_value_is_held_to_the_company_rules_and_never_configures_agents(self):
        for declared, mark in (("garbage", None), (None, None), ("personal", "garbage"), ("personal", ""), ("company", "x")):
            row = {"owner_kind": declared, "owner_confirmed": mark}
            self.assertEqual(managed.effective_kind(row), "company", row)
        for declared, mark in (("garbage", None), (None, "company"), ("personal", "company"), ("company", "personal")):
            self.assertFalse(managed.configures_agents({"owner_kind": declared, "owner_confirmed": mark}), (declared, mark))


class MigrationTests(unittest.TestCase):
    def test_a_v29_database_upgrades_in_place_with_every_device_unmarked(self):
        path = os.path.join(tempfile.mkdtemp(prefix="sgw-v30-"), "g.db")
        old = DB(path)
        stored_device(old)
        for column in COLUMNS:
            old.x(f"ALTER TABLE devices DROP COLUMN {column}")
        old.x("UPDATE meta SET v = '29' WHERE k = 'schema'")
        before = old.q("SELECT * FROM devices")
        old.close()
        new = DB(path)
        self.assertEqual(new.scalar("SELECT v FROM meta WHERE k = 'schema'"), str(len(SCHEMA)))
        row = new.one("SELECT * FROM devices")
        self.assertEqual({k: row[k] for k in before[0]}, before[0])
        self.assertEqual(tuple(row[c] for c in COLUMNS), (None, None, ""))
        for sql in ("UPDATE devices SET owner_confirmed = 'byod'", "UPDATE devices SET owner_confirmed = ''",
                    "UPDATE devices SET owner_confirmed_by = NULL"):
            with self.assertRaises(sqlite3.IntegrityError, msg=sql):
                new.x(sql)
        new.close()


if __name__ == "__main__":
    unittest.main()
