"""V2: authority, the audit fabric, location, purpose, policies and the rest of the control plane."""

import json
import os
import sqlite3
import tempfile
import time
import unittest

from gateway import authz, geo, security
from gateway.db import DB, SCHEMA

from .support import Rig
from .test_insight import add_request


def add_admin(db, username, role):
    stored_role, areas = authz.stored(role)
    db.x("INSERT INTO admins(username, pw_hash, role, areas, created) VALUES(?,?,?,?,?)",
         (username, security.hash_password(f"{username}-password", 1000), stored_role, areas, time.time()))


class V2Base(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.db = self.rig.gw.db
        for name in ("billing", "security", "operations"):
            add_admin(self.db, name, name)

    def tearDown(self):
        self.rig.close()


class MigrationTests(unittest.TestCase):
    def test_a_v12_database_upgrades_with_its_data(self):
        tmp = tempfile.mkdtemp(prefix="sgw-mig-")
        path = os.path.join(tmp, "old.db")
        conn = sqlite3.connect(path, isolation_level=None)
        for script in SCHEMA[:12]:
            for stmt in script.split(";"):
                if stmt.strip():
                    conn.execute(stmt)
        conn.execute("INSERT INTO meta(k, v) VALUES('schema', '12')")
        conn.execute("INSERT INTO admins(username, pw_hash, role, created) VALUES('o', 'x', 'owner', 1)")
        conn.execute("INSERT INTO requests(ts, provider, method, path, kind, outcome, cost) VALUES(1, 'anthropic', 'POST', '/v1/messages', 'messages', 'ok', 0.5)")
        conn.execute("INSERT INTO audit(ts, actor, action) VALUES(1, 'o', 'signed in')")
        conn.close()
        db = DB(path)
        self.assertEqual(int(db.scalar("SELECT v FROM meta WHERE k = 'schema'")), len(SCHEMA))
        self.assertEqual(db.one("SELECT role, areas FROM admins"), {"role": "owner", "areas": ""})
        self.assertEqual(db.one("SELECT cost, purpose FROM requests"), {"cost": 0.5, "purpose": None})
        self.assertEqual(db.one("SELECT action, outcome FROM audit"), {"action": "signed in", "outcome": "ok"})
        db.close()


class AuthorityTests(V2Base):
    def test_each_role_changes_only_its_areas(self):
        rig = self.rig
        pid = rig.person_id
        # billing: prices and budgets, not people or the emergency stop
        self.assertEqual(rig.api("PUT", "/prices/test-model", {"input": 1, "output": 2}, who="billing")[0], 200)
        self.assertEqual(rig.api("PATCH", f"/people/{pid}", {"monthly_budget": 50}, who="billing")[0], 200)
        self.assertEqual(rig.api("PATCH", f"/people/{pid}", {"name": "Someone Else"}, who="billing")[0], 403)
        self.assertEqual(rig.api("POST", "/pause", {"paused": True}, who="billing")[0], 403)
        # security: emergency controls and trust settings, not prices or tools
        self.assertEqual(rig.api("POST", f"/people/{pid}/suspend", who="security")[0], 200)
        self.assertEqual(rig.api("POST", f"/people/{pid}/resume", who="security")[0], 200)
        self.assertEqual(rig.api("PUT", "/settings", {"rate_per_min": 30}, who="security")[0], 200)
        self.assertEqual(rig.api("PUT", "/settings", {"retention_days": 30}, who="security")[0], 403)
        self.assertEqual(rig.api("PUT", "/prices/test-model", {"input": 1, "output": 2}, who="security")[0], 403)
        # operations: tools and access
        self.assertEqual(rig.api("POST", f"/people/{pid}/tools/canva", who="operations")[0], 200)
        self.assertEqual(rig.api("PUT", "/subscriptions/canva", {"state": "active"}, who="operations")[0], 403)
        # only an owner manages console users; the viewer changes nothing
        self.assertEqual(rig.api("GET", "/admins", who="operations")[0], 403)
        self.assertEqual(rig.api("POST", "/pause", {"paused": False}, who="viewer")[0], 403)
        self.assertEqual(rig.api("GET", "/admins")[0], 200)

    def test_refusals_are_audited_and_me_says_what_you_can_do(self):
        rig = self.rig
        self.assertEqual(rig.api("POST", "/pause", {"paused": True}, who="billing")[0], 403)
        row = self.db.one("SELECT * FROM audit WHERE outcome = 'denied' ORDER BY id DESC LIMIT 1")
        self.assertEqual((row["actor"], row["action"]), ("billing", "was refused a change"))
        status, me = rig.api("GET", "/me", who="security")
        self.assertEqual((me["role"], me["role_label"], me["can"]), ("security", "Security admin", ["emergency", "trust"]))
        self.assertFalse(me["owner"])
        self.assertEqual(rig.api("GET", "/me")[1]["can"], sorted(authz.AREAS))

    def test_roles_can_be_given_and_changed_but_one_owner_always_stays(self):
        rig = self.rig
        self.assertEqual(rig.api("POST", "/admins", {"username": "finance", "password": "a-long-password", "role": "billing"})[0], 200)
        status, admins = rig.api("GET", "/admins")
        finance = next(a for a in admins["items"] if a["username"] == "finance")
        self.assertEqual((finance["role"], finance["can"]), ("billing", ["money"]))
        self.assertEqual(rig.api("PATCH", f"/admins/{finance['id']}", {"role": "custom", "areas": ["money", "trust"]})[0], 200)
        self.assertEqual(authz.role_of(self.db.one("SELECT * FROM admins WHERE username = 'finance'")), "custom")
        owner = self.db.one("SELECT id FROM admins WHERE username = 'owner'")
        self.assertEqual(rig.api("PATCH", f"/admins/{owner['id']}", {"role": "viewer"})[0], 400)
        self.assertEqual(rig.api("POST", "/admins", {"username": "x1", "password": "a-long-password", "role": "god"})[0], 400)
        change = self.db.one("SELECT * FROM audit WHERE action = \"changed a console user's role\"")
        self.assertEqual(json.loads(change["after_json"])["role"], "Custom")


class AuditFabricTests(V2Base):
    def test_changes_record_before_after_reason_and_correlation(self):
        rig = self.rig
        pid = rig.person_id
        rig.api("PATCH", f"/people/{pid}", {"monthly_budget": 40, "reason": "agreed in the budget meeting"})
        row = self.db.one("SELECT * FROM audit WHERE action = 'changed a person' ORDER BY id DESC LIMIT 1")
        self.assertEqual(json.loads(row["before_json"]), {"monthly_budget": None})
        self.assertEqual(json.loads(row["after_json"]), {"monthly_budget": 40.0})
        self.assertEqual((row["reason"], row["correlation"], row["area"]), ("agreed in the budget meeting", f"person:{pid}", "money"))
        # the console gets the change back as data, and can filter on it
        status, audit = rig.api("GET", f"/audit?correlation=person:{pid}")
        entry = audit["items"][0]
        self.assertEqual((entry["before"], entry["after"]), ({"monthly_budget": None}, {"monthly_budget": 40.0}))

    def test_settings_changes_name_their_area_and_keep_the_old_value(self):
        rig = self.rig
        self.assertEqual(rig.api("PUT", "/settings", {"rate_per_min": 12, "block_secrets": True})[0], 200)
        row = self.db.one("SELECT * FROM audit WHERE action = 'changed settings' ORDER BY id DESC LIMIT 1")
        self.assertEqual(json.loads(row["after_json"]), {"block_secrets": "1", "rate_per_min": "12"})
        self.assertEqual(row["area"], "trust")
        self.assertEqual(rig.api("PUT", "/settings", {"retention_audit_days": 30})[0], 400)  # an audit log is kept a year at least

    def test_sign_out_is_recorded(self):
        rig = self.rig
        rig.login("viewer")
        rig.request("POST", "/admin/api/logout", {}, {"cookie": rig.cookies["viewer"], "x-gateway-admin": "1"})
        self.assertTrue(self.db.one("SELECT 1 FROM audit WHERE actor = 'viewer' AND action = 'signed out'"))


class EmergencyTests(V2Base):
    def test_switching_a_provider_off_refuses_its_requests(self):
        rig = self.rig
        self.assertEqual(rig.api("PUT", "/settings", {"disabled_providers": ["anthropic"]}, who="security")[0], 200)
        status, _, _ = rig.anthropic({"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(status, 403)
        self.assertEqual(rig.last_record()["reason"], "provider switched off")
        self.assertEqual(rig.api("PUT", "/settings", {"disabled_providers": ["nope"]})[0], 400)
        rig.api("PUT", "/settings", {"disabled_providers": []})
        self.assertEqual(rig.anthropic({"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]})[0], 200)


class LocationTests(V2Base):
    def setUp(self):
        super().setUp()
        self.csv = os.path.join(self.rig.tmp, "geo.csv")
        with open(self.csv, "w") as f:
            f.write("ip_start,ip_end,continent,country,stateprov,city,lat,lon\n")
            f.write("41.210.0.0,41.210.255.255,AF,UG,Central Region,Kampala,0.3,32.5\n")
            f.write("102.85.0.0,102.85.255.255,AF,KE,Nairobi,Nairobi,-1.2,36.8\n")
            f.write("2c0f:f000::,2c0f:ffff:ffff:ffff:ffff:ffff:ffff:ffff,AF,UG,Central Region,Entebbe,0,0\n")

    def test_address_types_need_no_table(self):
        self.assertEqual(geo.label("127.0.0.1", self.db), "this computer")
        self.assertEqual(geo.label("192.168.1.20", self.db), "private network")
        self.assertEqual(geo.label("100.64.3.4", self.db), "carrier network (shared address)")
        self.assertEqual(geo.label("8.8.8.8", self.db), "public internet")
        self.assertEqual(geo.label("not an ip", self.db), "unknown")

    def test_an_imported_table_gives_an_approximate_place_with_its_source(self):
        self.assertEqual(geo.import_csv(self.db, self.csv, "DB-IP Lite test"), 3)
        d = geo.describe("41.210.145.3", self.db)
        self.assertEqual((d["label"], d["approximate"], d["source"], d["country_code"]), ("Kampala, Uganda · approximate", True, "DB-IP Lite test", "UG"))
        self.assertEqual(geo.label("2c0f:f001::1", self.db), "Entebbe, Uganda · approximate")
        self.assertEqual(geo.label("8.8.8.8", self.db), "public internet")
        self.assertIn("not in the location table", geo.describe("8.8.8.8", self.db)["evidence"])
        with self.assertRaises(ValueError):
            geo.import_csv(self.db, self.csv, "")

    def test_known_networks_name_an_address_exactly_and_win_over_the_table(self):
        rig = self.rig
        geo.import_csv(self.db, self.csv, "DB-IP Lite test")
        status, out = rig.api("POST", "/networks", {"cidr": "41.210.145.0/24", "label": "Swangz office", "place": "Kampala", "kind": "office"},
                              who="security")
        self.assertEqual(status, 200, out)
        self.assertEqual(geo.label("41.210.145.3", self.db), "Swangz office · Kampala")
        self.assertEqual(geo.describe("41.210.145.3", self.db)["approximate"], False)
        self.assertEqual(rig.api("POST", "/networks", {"cidr": "not/a/net", "label": "x"}, who="security")[0], 400)
        self.assertEqual(rig.api("POST", "/networks", {"cidr": "10.0.0.0/8", "label": "x"}, who="billing")[0], 403)
        status, g = rig.api("GET", "/geo", who="viewer")
        self.assertEqual((g["table"]["source"], len(g["networks"])), ("DB-IP Lite test", 1))
        rig.api("DELETE", f"/networks/{g['networks'][0]['id']}", who="security")
        self.assertEqual(geo.label("41.210.145.3", self.db), "Kampala, Uganda · approximate")

    def test_the_cli_import_is_audited(self):
        from gateway.__main__ import main

        data = tempfile.mkdtemp(prefix="sgw-cli-")
        os.environ["GATEWAY_DATA"] = data
        try:
            main(["geoip-import", self.csv, "--source", "DB-IP Lite cli"])
        finally:
            os.environ.pop("GATEWAY_DATA", None)
            geo.bind(self.db)  # the CLI bound its own database; put the test's back
        db = DB(os.path.join(data, "gateway.db"))
        self.assertEqual(db.get_setting("geoip_source"), "DB-IP Lite cli")
        self.assertTrue(db.one("SELECT 1 FROM audit WHERE action = 'imported a location table'"))
        db.close()


CHAT = {"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}


def ask(text, model="claude-sonnet-4-6"):
    return {"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": text}]}


class PurposeTests(V2Base):
    SDK = {"user-agent": "anthropic-python/0.60.0"}

    def test_a_declared_purpose_is_taken_as_given_and_the_header_never_reaches_the_provider(self):
        rig = self.rig
        rig.anthropic(ask("hello there"), extra={"x-swangz-purpose": "Marketing", "x-swangz-project": "Showcase 2026", **self.SDK})
        r = rig.last_record()
        self.assertEqual((r["purpose"], r["purpose_source"], r["purpose_confidence"], r["project"]),
                         ("marketing", "declared", 1.0, "Showcase 2026"))
        sent = {k.lower() for k in rig.fake.seen[-1]["headers"]}
        self.assertFalse({"x-swangz-purpose", "x-swangz-project"} & sent)

    def test_a_coding_agent_is_derived_and_keywords_are_inferred_with_their_evidence(self):
        rig = self.rig
        rig.anthropic(ask("hello there"))  # Claude Code, nothing in the text
        r = rig.last_record()
        self.assertEqual((r["purpose"], r["purpose_source"], r["purpose_evidence"]), ("software-development", "derived", "Coding agent: Claude Code"))
        rig.anthropic(ask("Write an Instagram caption and hashtags for our campaign launch"), extra=self.SDK)
        r = rig.last_record()
        self.assertEqual((r["purpose"], r["purpose_source"]), ("marketing", "inferred"))
        self.assertGreaterEqual(r["purpose_confidence"], 0.6)
        self.assertIn("instagram", r["purpose_evidence"])
        status, rec = rig.api("GET", f"/requests/{r['id']}", who="viewer")
        self.assertEqual((rec["purpose_name"], rec["location"]["label"], rec["location"]["kind"]), ("Marketing", "this computer", "loopback"))
        self.assertEqual(rec["cost_basis"]["basis"], "estimated" if r["cost"] is not None else "unpriced")
        rig.anthropic(ask("hello there"), extra=self.SDK)
        self.assertEqual((rig.last_record()["purpose"], rig.last_record()["purpose_source"]), (None, None))  # unknown is an answer

    def test_inference_can_be_switched_off_and_the_taxonomy_edited(self):
        rig = self.rig
        self.assertEqual(rig.api("PUT", "/settings", {"purpose_inference": False})[0], 200)
        rig.anthropic(ask("Write an Instagram caption and hashtags for our campaign launch"), extra=self.SDK)
        self.assertIsNone(rig.last_record()["purpose"])
        rig.api("PUT", "/settings", {"purpose_inference": True})
        status, out = rig.api("POST", "/purposes", {"name": "Event planning", "keywords": "venue, guest list, rsvp, stage"}, who="operations")
        self.assertEqual((status, out["id"]), (200, "event-planning"))
        self.assertEqual(rig.api("POST", "/purposes", {"name": "x"}, who="billing")[0], 403)
        status, t = rig.api("POST", "/purposes/test", {"text": "Draft the guest list and RSVP note for the venue"}, who="viewer")
        self.assertEqual((t["purpose"], t["evidence"]), ("event-planning", ["guest list", "rsvp", "venue"]))
        rig.anthropic(ask("Draft the guest list and RSVP note for the venue"), extra=self.SDK)
        self.assertEqual(rig.last_record()["purpose"], "event-planning")
        status, listed = rig.api("GET", "/purposes", who="viewer")
        self.assertEqual(next(p for p in listed["items"] if p["id"] == "event-planning")["requests"], 1)
        # built-ins are archived, not deleted; a used purpose can't be deleted either
        self.assertEqual(rig.api("DELETE", "/purposes/marketing")[0], 400)
        self.assertEqual(rig.api("DELETE", "/purposes/event-planning")[0], 400)
        self.assertEqual(rig.api("PUT", "/purposes/marketing", {"archived": True})[0], 200)
        audit = self.db.one("SELECT * FROM audit WHERE action = 'changed a purpose'")
        self.assertEqual((json.loads(audit["before_json"]), json.loads(audit["after_json"])), ({"archived": 0}, {"archived": 1}))

    def test_an_agent_turn_without_a_prompt_continues_its_session(self):
        rig = self.rig
        sess = {"x-claude-code-session-id": "sess-42", **self.SDK}
        rig.anthropic(ask("Fix the failing pytest in the repo and refactor the function"), extra=sess)
        first = rig.last_record()
        self.assertEqual((first["purpose"], first["purpose_source"]), ("software-development", "inferred"))
        tool_result = {"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [
            {"role": "user", "content": "Fix the failing pytest in the repo and refactor the function"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "bash", "input": {"cmd": "pytest"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}]}
        rig.anthropic(tool_result, extra=sess)
        r = rig.last_record()
        if r["prompt"]:
            self.skipTest("this dialect reports the tool result as a prompt")
        self.assertEqual((r["purpose"], r["purpose_evidence"]), ("software-development", f"Continues request #{first['id']} in the same session"))


class ModelRegistryTests(V2Base):
    def test_disabled_and_restricted_models_are_refused_with_the_rule_recorded(self):
        rig = self.rig
        self.assertEqual(rig.api("PUT", "/models/claude-opus-4", {"status": "disabled", "provider": "anthropic"}, who="billing")[0], 403)
        self.assertEqual(rig.api("PUT", "/models/claude-opus-4", {"status": "disabled", "provider": "anthropic"}, who="operations")[0], 200)
        status, _, body = rig.anthropic(ask("hi", "claude-opus-4-1-20250805"))
        self.assertEqual(status, 403)
        self.assertIn("switched off", json.loads(body)["error"]["message"])
        r = rig.last_record()
        self.assertEqual((r["reason"], r["rule"]), ("model disabled", "model:claude-opus-4"))
        # restricted: only the named departments
        self.assertEqual(rig.api("PUT", "/models/claude-opus-4", {"status": "restricted"})[0], 400)  # needs departments
        rig.api("PUT", "/models/claude-opus-4", {"status": "restricted", "allowed_departments": ["Engineering"]})
        self.assertEqual(rig.anthropic(ask("hi", "claude-opus-4-1"))[0], 403)
        self.assertEqual(rig.last_record()["reason"], "model restricted")
        rig.api("PUT", "/models/claude-opus-4", {"allowed_departments": ["Engineering", "Creative"]})
        self.assertEqual(rig.anthropic(ask("hi", "claude-opus-4-1"))[0], 200)
        # other models are untouched; removing the entry makes it unlisted (allowed) again
        self.assertEqual(rig.anthropic(ask("hi"))[0], 200)
        status, models = rig.api("GET", "/models", who="viewer")
        opus = next(m for m in models["items"] if m["id"] == "claude-opus-4-1")
        self.assertEqual((opus["status"], opus["governed_by"], opus["refused"]), ("restricted", "claude-opus-4", 1))
        self.assertEqual(rig.api("DELETE", "/models/claude-opus-4")[0], 200)
        self.assertEqual(next(m for m in rig.api("GET", "/models")[1]["items"] if m["id"] == "claude-opus-4-1")["status"], "unlisted")
        self.assertEqual([a["action"] for a in self.db.q("SELECT action FROM audit WHERE correlation = 'model:claude-opus-4' ORDER BY id")],
                         ["registered a model", "changed a model's rules", "changed a model's rules", "removed a model from the registry"])


class PolicyTests(V2Base):
    def policy(self, body, who="operations"):
        status, out = self.rig.api("POST", "/policies", body, who=who)
        self.assertEqual(status, 200, out)
        return out["id"]

    def test_a_deny_policy_refuses_requests_and_says_which_rule(self):
        rig = self.rig
        pid = self.policy({"name": "No Codex for Creative", "effect": "deny", "subjects": {"departments": ["creative"]},
                           "scope": {"tools": ["codex"]}, "params": {"message": "Creative doesn't use Codex."}})
        status, _, body = rig.openai("/responses", {"model": "gpt-5", "input": "hi"})
        self.assertEqual(status, 403)
        self.assertIn("Creative doesn't use Codex.", json.loads(body)["error"]["message"])
        r = rig.last_record()
        self.assertEqual((r["outcome"], r["reason"], r["rule"]), ("blocked", "policy: No Codex for Creative", f"policy:{pid}"))
        self.assertEqual(rig.anthropic(CHAT)[0], 200)  # Claude Code isn't covered
        status, listed = rig.api("GET", "/policies", who="viewer")
        item = listed["items"][0]
        self.assertEqual(item["refused_30d"], 1)
        self.assertIn("Refuses Codex for the creative department", item["summary"])
        # switched off, it stops applying; the change is audited with before and after
        self.assertEqual(rig.api("PATCH", f"/policies/{pid}", {"enabled": False})[0], 200)
        self.assertEqual(rig.openai("/responses", {"model": "gpt-5", "input": "hi"})[0], 200)
        row = self.db.one("SELECT * FROM audit WHERE action = 'switched a policy off'")
        self.assertEqual((json.loads(row["before_json"]), json.loads(row["after_json"]), row["area"]), ({"enabled": 1}, {"enabled": 0}, "govern"))

    def test_permitted_hours_follow_gateway_time(self):
        from gateway import policy

        p = policy.parse_row({"id": 1, "name": "Office hours", "effect": "hours", "subjects": {"everyone": True}, "scope": {},
                              "params": {"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "19:00"}})
        who, what = {"person_id": 1, "department": ""}, {"channel": "request"}
        monday_10 = 1760346000  # Mon 13 Oct 2025 09:00 UTC = 12:00 in Kampala (UTC+3)
        self.rig.settings.tz_offset_minutes = 180
        self.assertTrue(policy.evaluate(self.db, self.rig.settings, who, what, [p], now=monday_10).allowed)
        late = policy.evaluate(self.db, self.rig.settings, who, what, [p], now=monday_10 + 9 * 3600)  # 21:00 Kampala
        self.assertFalse(late.allowed)
        self.assertIn("outside permitted hours (Mon, Tue, Wed, Thu, Fri 08:00–19:00)", late.message)
        saturday = policy.evaluate(self.db, self.rig.settings, who, what, [p], now=monday_10 + 5 * 86400)
        self.assertFalse(saturday.allowed)
        overnight = dict(p, params={"days": [0], "start": "22:00", "end": "06:00"})
        self.assertTrue(policy.evaluate(self.db, self.rig.settings, who, what, [overnight], now=monday_10 + 11 * 3600).allowed)  # 23:00
        with self.assertRaises(ValueError):
            policy.validate({"name": "x", "effect": "hours", "subjects": {"everyone": True}, "params": {"days": [0], "start": "9", "end": "17:00"}})

    def test_a_cap_counts_only_what_it_covers(self):
        rig = self.rig
        add_request(self.db, person_id=rig.person_id, model="claude-opus-4-1", cost=4.0)
        add_request(self.db, person_id=rig.person_id, model="claude-sonnet-4-6", cost=9.0)
        self.policy({"name": "Opus cap", "effect": "cap", "subjects": {"departments": ["Creative"]},
                     "scope": {"models": ["claude-opus-*"]}, "params": {"limit_usd": 5}})
        self.assertEqual(rig.anthropic(ask("hi", "claude-opus-4-1"))[0], 200)  # $4 of $5
        add_request(self.db, person_id=rig.person_id, model="claude-opus-4-1", cost=1.5)
        status, _, body = rig.anthropic(ask("hi", "claude-opus-4-1"))
        self.assertEqual(status, 403)
        self.assertIn("$5.50 of $5.00 used this month", json.loads(body)["error"]["message"])
        self.assertEqual(rig.anthropic(ask("hi"))[0], 200)  # sonnet spend isn't capped

    def test_a_policy_governs_opening_and_visiting_a_tool_too(self):
        from .test_portal import PortalBase

        rig = self.rig
        portal = PortalBase("run")
        portal.rig, portal.cookie = rig, None
        rig.api("PATCH", f"/people/{rig.person_id}", {"email": "grace@swangzavenue.com"})
        self.db.x("UPDATE people SET pw_hash = ? WHERE id = ?", (security.hash_password("a-long-password", 1000), rig.person_id))
        portal.staff("POST", "/login", {"email": "grace@swangzavenue.com", "password": "a-long-password"})
        portal.enable("canva")
        pid = self.policy({"name": "No design tools", "effect": "deny", "subjects": {"people": [rig.person_id]},
                           "scope": {"tools": ["canva"], "channels": ["launch", "site"]}})
        status, _, page = portal.go("canva")
        self.assertEqual(status, 403)
        self.assertIn("No design tools", page)
        row = self.db.one("SELECT * FROM launches ORDER BY id DESC LIMIT 1")
        self.assertEqual((row["outcome"], row["rule"]), ("refused", f"policy:{pid}"))
        self.assertIn("No design tools", row["reason"])
        token = portal.staff("POST", "/extension/login", {"email": "grace@swangzavenue.com", "password": "a-long-password"})[1]["token"]
        status, h, payload = rig.request("POST", "/api/gate/open", {"host": "www.canva.com"}, {"x-swangz-app": "1", "authorization": "Bearer " + token})
        out = json.loads(payload)
        self.assertEqual((out["allowed"], out["state"]), (False, "policy"))
        self.assertEqual(self.db.one("SELECT rule FROM site_usage ORDER BY id DESC LIMIT 1")["rule"], f"policy:{pid}")
        self.assertEqual(rig.api("GET", "/policies")[1]["items"][0]["refused_30d"], 2)

    def test_bad_policies_are_refused_with_what_to_fix(self):
        rig = self.rig
        for body, words in (({"effect": "deny", "subjects": {"everyone": True}}, "name"),
                            ({"name": "x", "effect": "maybe", "subjects": {"everyone": True}}, "effect"),
                            ({"name": "x", "effect": "deny", "subjects": {}}, "who"),
                            ({"name": "x", "effect": "deny", "subjects": {"people": [99999]}}, "exist"),
                            ({"name": "x", "effect": "deny", "subjects": {"everyone": True}, "scope": {"tools": ["nope"]}}, "catalogue"),
                            ({"name": "x", "effect": "cap", "subjects": {"everyone": True}, "params": {}}, "limit_usd")):
            status, out = rig.api("POST", "/policies", body)
            self.assertEqual(status, 400, body)
            self.assertIn(words, out["error"])
        self.assertEqual(rig.api("POST", "/policies", {"name": "x", "effect": "deny", "subjects": {"everyone": True}}, who="viewer")[0], 403)


class SimulatorTests(V2Base):
    def test_the_simulator_replays_history_without_changing_anything(self):
        rig, now = self.rig, time.time()
        other = self.db.x("INSERT INTO people(name, department, created) VALUES('Okello Brian', 'Engineering', 1)").lastrowid
        for i in range(3):
            add_request(self.db, person_id=rig.person_id, key_id=rig.key_id, client="Codex", provider="openai", model="gpt-5",
                        cost=0.5, ts=now - 3600 * (i + 1))
        add_request(self.db, person_id=other, client="Codex", provider="openai", model="gpt-5", cost=2.0, ts=now - 600)
        add_request(self.db, person_id=rig.person_id, cost=0.25, ts=now - 300)  # Claude Code: not covered
        rig.login("viewer")
        before = (self.db.scalar("SELECT COUNT(*) FROM policies"), self.db.scalar("SELECT COUNT(*) FROM audit"))
        draft = {"name": "No Codex for Creative", "effect": "deny", "subjects": {"departments": ["Creative"]}, "scope": {"tools": ["codex"]}}
        status, sim = rig.api("POST", "/policies/simulate", draft, who="viewer")
        self.assertEqual(status, 200, sim)
        self.assertEqual((sim["refused"]["request"], sim["refused"]["total"], sim["devices"], sim["spend"]), (3, 3, 1, 1.5))
        self.assertEqual([(p["person"], p["refused"]) for p in sim["people"]], [("Nansubuga Grace", 3)])
        self.assertEqual(sim["tools"][0]["tool_id"], "codex")
        self.assertIn("Read-only", sim["notes"][0])
        self.assertEqual((self.db.scalar("SELECT COUNT(*) FROM policies"), self.db.scalar("SELECT COUNT(*) FROM audit")), before)
        # an existing rule that already refuses the same thing is named, and an identical one is a duplicate
        status, out = rig.api("POST", "/policies", {**draft, "name": "Existing"})
        status, sim = rig.api("POST", "/policies/simulate", draft)
        self.assertEqual(sim["already_refused"], [{"id": out["id"], "name": "Existing", "events": 3}])
        self.assertEqual(sim["conflicts"][0]["kind"], "duplicate")
        status, sim = rig.api("POST", "/policies/simulate", {"policy": draft, "replacing": out["id"]})
        self.assertEqual((sim["already_refused"], sim["conflicts"]), ([], []))

    def test_a_simulated_cap_stops_counting_what_it_refused(self):
        rig, now = self.rig, time.time()
        for i in range(5):
            add_request(self.db, person_id=rig.person_id, cost=1.0, ts=now - 60 * (5 - i))
        draft = {"name": "Small cap", "effect": "cap", "subjects": {"people": [rig.person_id]}, "params": {"limit_usd": 2}}
        sim = rig.api("POST", "/policies/simulate", {"policy": draft, "days": 1})[1]
        # spend earlier this month (before the window) counts toward the cap; the window itself starts at $0 here
        self.assertEqual(sim["refused"]["request"], 3)

    def test_revoke_and_seat_simulators(self):
        rig, now = self.rig, time.time()
        status, sim = rig.api("POST", "/simulate/revoke", {"person_id": rig.person_id, "tool_id": "codex"}, who="viewer")
        self.assertEqual((sim["grants"]["direct"], sim["after"]["enabled"], sim["now"]["enabled"]), (True, False, True))
        rig.api("POST", "/teams/Creative/tools/codex")
        sim = rig.api("POST", "/simulate/revoke", {"person_id": rig.person_id, "tool_id": "codex"})[1]
        self.assertEqual((sim["grants"]["department"], sim["after"]["enabled"]), ("Creative", True))
        self.assertIn("department's grant", sim["effects"][0])
        self.assertEqual(rig.api("POST", "/simulate/revoke", {"person_id": 9999, "tool_id": "codex"})[0], 404)
        rig.api("PUT", "/subscriptions/canva", {"state": "active", "monthly_cost": 60, "seats": 3})
        rig.api("POST", f"/people/{rig.person_id}/tools/canva")
        other = self.db.x("INSERT INTO people(name, department, created) VALUES('Okello Brian', 'Ops', 1)").lastrowid
        rig.api("POST", f"/people/{other}/tools/canva")
        self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('canva', ?, ?, 'opened')", (other, now - 100))
        status, seats = rig.api("POST", "/simulate/seats", {"tool_id": "canva", "seats": 1})
        self.assertEqual((seats["assigned"], seats["active_30d"]), (2, 1))
        self.assertEqual(([k["person"] for k in seats["keep"]], [w["person"] for w in seats["without"]]), (["Okello Brian"], ["Nansubuga Grace"]))
        self.assertEqual(seats["cost"], {"per_seat": 20.0, "monthly": 20.0, "change": -40.0, "basis": "allocated"})
        self.assertEqual(rig.api("POST", "/simulate/seats", {"tool_id": "canva", "seats": -1})[0], 400)

    def test_explain_walks_every_check_in_order(self):
        rig = self.rig
        status, ex = rig.api("GET", f"/policies/explain?person={rig.person_id}&tool=claude-code&model=claude-sonnet-4-6", who="viewer")
        self.assertEqual(status, 200, ex)
        self.assertTrue(ex["allowed"])
        self.assertEqual([s["check"] for s in ex["steps"]],
                         ["Everyone's AI access", "Their account", "Service", "Their services", "Their model rules", "Model registry",
                          "Developer tool", "Their budget", "Company policies"])
        rig.api("PUT", "/models/claude-sonnet-4", {"status": "disabled"})
        ex = rig.api("GET", f"/policies/explain?person={rig.person_id}&tool=claude-code&model=claude-sonnet-4-6")[1]
        self.assertEqual((ex["allowed"], ex["decided_by"]), (False, "Model registry"))
        ex = rig.api("GET", f"/policies/explain?person={rig.person_id}&tool=midjourney")[1]
        self.assertEqual((ex["channel"], ex["allowed"], ex["decided_by"]), ("launch", False, "Assignment and subscription"))
        self.assertEqual(rig.api("GET", "/policies/explain?tool=midjourney")[0], 400)


class MediaCostTests(V2Base):
    def speak(self, text):
        return self.rig.request("POST", "/elevenlabs/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb", {"text": text, "model_id": "eleven_multilingual_v2"},
                                {"xi-api-key": self.rig.key})

    def test_media_is_unpriced_until_a_rate_exists_and_old_costs_never_change(self):
        rig = self.rig
        self.speak("Karibu")
        first = rig.last_record()
        self.assertEqual((first["cost"], first["cost_source"]), (None, None))
        self.assertEqual(rig.api("POST", "/media-rates", {"provider": "elevenlabs", "unit": "characters", "usd_per_unit": 0.0003},
                                 who="operations")[0], 403)
        status, out = rig.api("POST", "/media-rates", {"provider": "elevenlabs", "unit": "characters", "usd_per_unit": 0.0003,
                                                       "effective": "2020-01-01"}, who="billing")
        self.assertEqual(status, 200, out)
        self.speak("Karibu ku Swangz")  # 16 characters
        second = rig.last_record()
        self.assertAlmostEqual(second["cost"], 16 * 0.0003)
        self.assertEqual(second["cost_source"], f"rate:{out['id']}@{int(time.mktime(time.strptime('2020-01-01', '%Y-%m-%d')) - time.timezone)}")
        rig.api("POST", "/media-rates", {"provider": "elevenlabs", "unit": "character", "usd_per_unit": 0.001, "effective": "2021-01-01"}, who="billing")
        self.assertAlmostEqual(self.db.one("SELECT cost FROM requests WHERE id = ?", (second["id"],))["cost"], 16 * 0.0003)
        self.assertIsNone(self.db.one("SELECT cost FROM requests WHERE id = ?", (first["id"],))["cost"])
        self.speak("Karibu")
        self.assertAlmostEqual(rig.last_record()["cost"], 6 * 0.001)
        self.assertEqual(rig.api("DELETE", f"/media-rates/{out['id']}", who="billing")[0], 400)  # it priced a request
        listed = rig.api("GET", "/media-rates", who="viewer")[1]
        self.assertEqual([r["current"] for r in listed["items"]], [True, False])
        self.assertEqual(listed["unpriced"][0]["requests"], 1)


class ReportTests(V2Base):
    def test_reports_read_as_json_and_export_as_audited_csv(self):
        rig = self.rig
        add_request(self.db, person_id=rig.person_id, cost=1.25, purpose="marketing", purpose_source="inferred")
        add_request(self.db, person_id=rig.person_id, cost=None, model="claude-unpriced")
        status, listing = rig.api("GET", "/reports", who="viewer")
        self.assertIn("purposes", [r["kind"] for r in listing["items"]])
        for kind in [r["kind"] for r in listing["items"]]:
            self.assertEqual(rig.api("GET", f"/reports/{kind}", who="viewer")[0], 200, kind)
        status, rep = rig.api("GET", "/reports/spend")
        row = rep["rows"][0]
        self.assertEqual((row["person"], row["cost"], row["unpriced"]), ("Nansubuga Grace", 1.25, 1))
        self.assertIn("estimated", rep["notes"][0])
        status, purposes = rig.api("GET", "/reports/purposes")
        self.assertEqual({r["purpose"]: r["inferred"] for r in purposes["rows"]}, {"Marketing": 1, "Unknown": 0})
        status, h, csv_bytes = rig.request("GET", "/admin/api/reports/spend?format=csv", None, {"cookie": rig.cookies["owner"]})
        self.assertEqual((status, h["content-type"]), (200, "text/csv; charset=utf-8"))
        text = csv_bytes.decode("utf-8-sig")
        self.assertIn("Swangz AI report: Spend by person", text)
        self.assertIn("Nansubuga Grace", text)
        self.assertTrue(self.db.one("SELECT 1 FROM audit WHERE action = 'exported a report' AND correlation = 'report:spend'"))
        self.assertEqual(rig.api("GET", "/reports/nope")[0], 404)
        self.assertEqual(rig.api("GET", "/reports/usage?since=200&until=100")[0], 400)



class IncidentTests(V2Base):
    def test_an_incident_runs_from_open_to_resolved_with_its_evidence_and_trail(self):
        rig = self.rig
        rid = add_request(self.db, person_id=rig.person_id, key_id=rig.key_id)
        body = {"title": "Key shared in a public repo", "severity": "high", "source": "security:credential",
                "links": [{"kind": "person", "ref": str(rig.person_id)}, {"kind": "request", "ref": str(rid)},
                          {"kind": "device", "ref": rig.key_id}]}
        self.assertEqual(rig.api("POST", "/incidents", body, who="billing")[0], 403)
        self.assertEqual(rig.api("POST", "/incidents", {**body, "links": [{"kind": "person", "ref": "9999"}]}, who="security")[0], 400)
        status, out = rig.api("POST", "/incidents", body, who="security")
        self.assertEqual(status, 200, out)
        iid = out["id"]
        status, inc = rig.api("GET", f"/incidents/{iid}", who="viewer")
        self.assertEqual([l["label"] for l in inc["links_list"]], ["Nansubuga Grace", f"Request #{rid} · Nansubuga Grace", "laptop (Nansubuga Grace)"])
        self.assertEqual(inc["next"], ["investigating", "contained", "resolved", "dismissed"])
        self.assertEqual(rig.api("PATCH", f"/incidents/{iid}", {"status": "resolved"}, who="security")[1]["error"],
                         "say how it ended: a resolution is needed to close an incident")
        rig.api("PATCH", f"/incidents/{iid}", {"status": "investigating"}, who="security")
        rig.api("POST", f"/incidents/{iid}/notes", {"text": "Asked Grace; it was a test key."}, who="security")
        self.assertEqual(rig.api("PATCH", f"/incidents/{iid}", {"status": "open"}, who="security")[0], 400)  # not a valid step
        rig.api("PATCH", f"/incidents/{iid}", {"status": "resolved", "resolution": "Key revoked and rotated."}, who="security")
        inc = rig.api("GET", f"/incidents/{iid}")[1]
        self.assertEqual((inc["status"], inc["closed_by"], inc["next"]), ("resolved", "security", ["open"]))
        self.assertEqual([n["kind"] for n in inc["notes_list"]], ["status", "status", "note", "status"])
        self.assertEqual([t["action"] for t in inc["trail"]],
                         ["opened an incident", "changed an incident", "added a note to an incident", "changed an incident"])
        self.assertEqual(rig.api("GET", "/incidents")[1]["items"], [])  # active only by default
        self.assertEqual(len(rig.api("GET", "/incidents?status=closed")[1]["items"]), 1)


class NotificationTests(V2Base):
    def test_conditions_become_notifications_that_resolve_and_are_read_per_admin(self):
        from gateway import notify

        rig = self.rig
        rig.api("POST", "/pause", {"paused": True})
        rig.api("PUT", "/settings", {"disabled_providers": ["openai"]})
        notify.refresh(rig.gw)
        status, out = rig.api("GET", "/notifications", who="viewer")
        keys = {n["key"]: n for n in out["items"]}
        self.assertEqual(keys["att:paused"]["severity"], "high")
        self.assertEqual(keys["provider-off:openai"]["severity"], "warning")
        self.assertEqual(out["unread"], len(out["items"]))
        rig.api("POST", "/notifications/read", {"ids": [keys["att:paused"]["id"]]}, who="viewer")
        self.assertEqual(rig.api("GET", "/notifications", who="viewer")[1]["unread"], len(out["items"]) - 1)
        self.assertEqual(rig.api("GET", "/notifications")[1]["unread"], len(out["items"]))  # the owner hasn't read it
        rig.api("POST", "/pause", {"paused": False})
        notify.refresh(rig.gw)
        self.assertNotIn("att:paused", {n["key"] for n in rig.api("GET", "/notifications", who="viewer")[1]["items"]})
        everything = rig.api("GET", "/notifications?all=1", who="viewer")[1]["items"]
        self.assertTrue(next(n for n in everything if n["key"] == "att:paused")["resolved"])
        # it comes back as new, unread again
        rig.api("POST", "/pause", {"paused": True})
        notify.refresh(rig.gw)
        again = next(n for n in rig.api("GET", "/notifications", who="viewer")[1]["items"] if n["key"] == "att:paused")
        self.assertIsNone(again["read"])

    def test_high_notifications_are_emailed_once_and_only_when_set_up(self):
        from gateway import notify

        rig = self.rig
        rig.api("POST", "/pause", {"paused": True})
        self.assertIsNone(notify.smtp_settings())
        notify.refresh(rig.gw)  # no SMTP: nothing is sent, nothing is marked
        self.assertIsNone(self.db.one("SELECT emailed FROM notifications WHERE key = 'att:paused'")["emailed"])
        sent = []
        self.assertEqual(notify.email_new(rig.gw, send=lambda cfg, msg: sent.append(msg)), 1)
        self.assertIn("AI access is paused for everyone", sent[0]["Subject"])
        self.assertIn("https://ai.example.test/admin#/settings", sent[0].get_content())
        self.assertEqual(notify.email_new(rig.gw, send=lambda cfg, msg: sent.append(msg)), 0)


class RetentionTests(V2Base):
    def test_each_category_keeps_its_own_window_and_every_purge_is_audited(self):
        rig, now = self.rig, time.time()
        old = now - 400 * 86400
        rig.anthropic(CHAT)
        rid = rig.last_record()["id"]
        self.db.x("UPDATE requests SET ts = ? WHERE id = ?", (now - 40 * 86400, rid))
        self.db.x("INSERT INTO site_usage(tool_id, person_id, host, outcome, started) VALUES('canva', ?, 'canva.com', 'allowed', ?)",
                  (rig.person_id, old))
        self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('canva', ?, ?, 'opened')", (rig.person_id, old))
        self.db.x("INSERT INTO audit(ts, actor, action) VALUES(?, 'someone', 'an old change')", (old,))
        self.db.x("INSERT INTO audit(ts, actor, action) VALUES(?, 'someone', 'a recent change')", (now - 200 * 86400,))
        rig.api("PUT", "/settings", {"retention_days": 0, "retention_bodies_days": 30, "retention_site_days": 90,
                                     "retention_launch_days": 90, "retention_audit_days": 365})
        self.assertTrue(self.db.one("SELECT req_head FROM requests WHERE id = ?", (rid,))["req_head"])
        rig.gw.maintain()
        r = self.db.one("SELECT * FROM requests WHERE id = ?", (rid,))
        self.assertEqual((r["req_head"], r["resp_blob"], r["model"]), (None, None, "claude-sonnet-4-6"))  # the record stays
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM site_usage"), 0)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM launches"), 0)
        self.assertFalse(self.db.one("SELECT 1 FROM audit WHERE action = 'an old change'"))
        self.assertTrue(self.db.one("SELECT 1 FROM audit WHERE action = 'a recent change'"))
        purge = self.db.one("SELECT * FROM audit WHERE action = 'purged old records'")
        after = json.loads(purge["after_json"])
        self.assertEqual((after["retention_bodies_days"], after["retention_site_days"], after["retention_launch_days"],
                          after["retention_audit_days"]), (1, 1, 1, 1))
        self.assertGreater(after["bodies_unreferenced"], 0)
        self.assertTrue(self.db.get_setting("maintenance_last"))
        from gateway import store

        self.assertEqual(store.purge_categories(self.db, {"retention_audit_days": 30}, now=now + 100 * 86400), {})  # never under a year


class RiskTests(V2Base):
    def test_a_new_place_and_a_new_device_are_compared_with_the_persons_own_history(self):
        from gateway import insight

        rig, now = self.rig, time.time()
        self.db.x("INSERT INTO networks(cidr, label, place, kind, created) VALUES('41.210.145.0/24', 'Swangz office', 'Kampala', 'office', 1)")
        from gateway import geo

        geo.invalidate()
        for d in (20, 15, 10):
            add_request(self.db, person_id=rig.person_id, key_id=rig.key_id, client_ip="41.210.145.9", ts=now - d * 86400)
        kid2, _, h, hint = security.new_key()
        self.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES(?,?,?,?,?,?)",
                  (kid2, rig.person_id, "new phone", h, hint, now))
        add_request(self.db, person_id=rig.person_id, key_id=kid2, client_ip="102.85.4.4", ts=now - 3600)
        ctx = type("C", (), {"db": self.db, "gw": rig.gw})()
        events = {e["type"]: e for e in insight.security_events(ctx, 7)}
        place = events["new_place"]
        self.assertIn("from public internet for the first time in 30 days; before that, from Swangz office · Kampala", place["text"])
        self.assertEqual(place["location"]["kind"], "public")
        self.assertIn("approximate", place["evidence"])
        self.assertEqual(events["new_device"]["device"], "new phone")
        self.assertNotIn("off_hours", events)  # too little history to say what is usual

    def test_repeated_refusals_across_channels_are_one_signal(self):
        from gateway import insight

        rig, now = self.rig, time.time()
        for _ in range(6):
            add_request(self.db, person_id=rig.person_id, outcome="blocked", reason="model not allowed", ts=now - 60)
        for _ in range(5):
            self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES('canva', ?, ?, 'refused')", (rig.person_id, now - 30))
        ctx = type("C", (), {"db": self.db, "gw": rig.gw})()
        e = next(e for e in insight.security_events(ctx, 1) if e["type"] == "denials")
        self.assertEqual(e["text"], "Nansubuga Grace was refused 11 times in 24 hours (6 requests, 5 opens, 0 website visits).")
        self.assertIn("Worth a word, not a conclusion.", e["evidence"])


class TimelineAndExportTests(V2Base):
    def test_sign_ins_access_changes_and_turns_join_the_timeline(self):
        rig = self.rig
        rig.api("PATCH", f"/people/{rig.person_id}", {"email": "grace@swangzavenue.com"})
        self.db.x("UPDATE people SET pw_hash = ? WHERE id = ?", (security.hash_password("a-long-password", 1000), rig.person_id))
        rig.request("POST", "/api/login", {"email": "grace@swangzavenue.com", "password": "a-long-password"}, {"x-swangz-app": "1"})
        rig.api("POST", f"/people/{rig.person_id}/suspend")
        self.db.x("INSERT INTO tool_turns(tool_id, person_id, started, expires) VALUES('chatgpt', ?, ?, ?)",
                  (rig.person_id, time.time() - 60, time.time() + 600))
        status, tl = rig.api("GET", f"/timeline?person={rig.person_id}", who="viewer")
        self.assertEqual(status, 200, tl)
        kinds = [(e["type"], e.get("action")) for e in tl["items"]]
        self.assertIn(("access", "signed in to Swangz AI"), kinds)
        self.assertIn(("access", "suspended a person"), kinds)
        self.assertIn(("turn", None), kinds)
        signin = next(e for e in tl["items"] if e.get("action") == "signed in to Swangz AI")
        self.assertTrue(signin["self"])
        self.assertEqual(rig.api("GET", "/timeline?type=turn", who="viewer")[1]["items"][0]["tool"], "ChatGPT")

    def test_the_export_carries_purpose_cost_basis_and_place_and_withholds_prompts_without_the_trust_area(self):
        rig = self.rig
        rig.anthropic(ask("Write an Instagram caption and hashtags for our campaign launch"), extra={"user-agent": "anthropic-python/0.6"})
        status, h, payload = rig.request("GET", "/admin/api/export.csv", None, {"cookie": rig.login("security")})
        rows = list(__import__("csv").DictReader(payload.decode("utf-8-sig").splitlines()))
        self.assertEqual((rows[0]["purpose"], rows[0]["purpose_source"], rows[0]["place"]), ("marketing", "inferred", "this computer"))
        self.assertIn(rows[0]["cost_basis"], ("estimated", "unpriced"))
        self.assertIn("Instagram", rows[0]["prompt"])
        status, h, payload = rig.request("GET", "/admin/api/export.csv", None, {"cookie": rig.login("billing")})
        rows = list(__import__("csv").DictReader(payload.decode("utf-8-sig").splitlines()))
        self.assertEqual((rows[0]["prompt"], rows[0]["purpose"]), ("", "marketing"))
        audit = self.db.one("SELECT * FROM audit WHERE action = 'exported records' AND actor = 'billing'")
        self.assertIn("without prompts", audit["detail"])



class V2PermissionTests(V2Base):
    READS = ["/purposes", "/models", "/policies", "/media-rates", "/reports", "/reports/usage", "/geo", "/geo/lookup?ip=8.8.8.8",
             "/incidents", "/notifications", "/health"]
    CHANGES = [("POST", "/purposes"), ("PUT", "/purposes/marketing"), ("DELETE", "/purposes/x"), ("PUT", "/models/x"),
               ("DELETE", "/models/x"), ("POST", "/policies"), ("PUT", "/policies/1"), ("PATCH", "/policies/1"),
               ("DELETE", "/policies/1"), ("POST", "/media-rates"), ("DELETE", "/media-rates/1"), ("POST", "/networks"),
               ("PATCH", "/networks/1"), ("DELETE", "/networks/1"), ("POST", "/incidents"), ("PATCH", "/incidents/1"),
               ("POST", "/incidents/1/notes"), ("POST", "/incidents/1/links"), ("DELETE", "/incidents/1/links/1")]

    def test_viewers_read_every_v2_page_change_nothing_and_strangers_get_nothing(self):
        rig = self.rig
        for path in self.READS + [f"/policies/explain?person={rig.person_id}&tool=canva"]:
            self.assertEqual(rig.api("GET", path, who="viewer")[0], 200, path)
            self.assertEqual(rig.request("GET", "/admin/api" + path)[0], 401, path)
        for method, path in self.CHANGES:
            self.assertEqual(rig.api(method, path, {}, who="viewer")[0], 403, f"{method} {path}")
            self.assertEqual(rig.request(method, "/admin/api" + path, {}, {"x-gateway-admin": "1"})[0], 401, f"{method} {path}")
        # what-ifs and the keyword tester change nothing, so any console user may run them
        for path, body in (("/policies/simulate", {"name": "x", "effect": "deny", "subjects": {"everyone": True}}),
                           ("/simulate/revoke", {"person_id": rig.person_id, "tool_id": "codex"}),
                           ("/simulate/seats", {"tool_id": "canva", "seats": 2}), ("/purposes/test", {"text": "a logo"}),
                           ("/notifications/read", {"all": True})):
            self.assertEqual(rig.api("POST", path, body, who="viewer")[0], 200, path)
        denied = self.db.scalar("SELECT COUNT(*) FROM audit WHERE actor = 'viewer' AND outcome = 'denied'")
        self.assertEqual(denied, len(self.CHANGES))


if __name__ == "__main__":
    unittest.main()
