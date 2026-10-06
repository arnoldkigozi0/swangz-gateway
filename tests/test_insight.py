"""The control room's lenses: trends, attention, security, devices, the timeline, spend and search."""

import time
import unittest

from gateway import insight

from .test_portal import PortalBase

LENSES = ("/trends", "/usage", "/timeline", "/devices", "/spend", "/security", "/attention", "/search?q=grace",
          "/tools/canva/usage")


def add_request(db, **kw):
    row = {"ts": time.time(), "provider": "anthropic", "method": "POST", "path": "/v1/messages", "kind": "messages",
           "client": "Claude Code", "outcome": "ok", "model": "claude-sonnet-4-5", "cost": 0.0, "flags": ""}
    row.update(kw)
    cols = list(row)
    return db.x(f"INSERT INTO requests({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [row[c] for c in cols]).lastrowid


class LensBase(PortalBase):
    def setUp(self):
        super().setUp()
        self.db = self.rig.gw.db
        self.pid = self.rig.person_id
        self.kid = self.rig.key_id


class PermissionTests(LensBase):
    def test_viewers_read_every_lens_and_strangers_none(self):
        for path in LENSES:
            self.assertEqual(self.rig.api("GET", path, who="viewer")[0], 200, path)
            status, _, _ = self.rig.request("GET", "/admin/api" + path)
            self.assertEqual(status, 401, path)
        self.assertEqual(self.rig.api("GET", "/devices/000000000000")[0], 404)
        self.assertEqual(self.rig.api("GET", "/tools/nope/usage")[0], 404)
        self.assertEqual(self.rig.api("GET", "/usage?since=200&until=100")[0], 400)


class TimelineTests(LensBase):
    def test_one_stream_newest_first_across_every_record(self):
        rig, now = self.rig, time.time()
        self.enable("canva")
        add_request(self.db, ts=now - 300, person_id=self.pid, key_id=self.kid, prompt="tidy the deploy script",
                    client_ip="41.210.1.2", user_agent="codex_cli_rs/0.155.0 (Mac OS 15.5.0; arm64)", client="Codex",
                    provider="openai")
        self.assertEqual(self.go("canva")[0], 302)  # a launch, now
        self.db.x("INSERT INTO site_usage(tool_id, person_id, host, outcome, started, seconds) VALUES(?,?,?,?,?,?)",
                  ("canva", self.pid, "canva.com", "allowed", now - 120, 600))
        status, out = rig.api("GET", "/timeline", who="viewer")
        self.assertEqual(status, 200)
        self.assertEqual([e["type"] for e in out["items"]], ["launch", "site", "request"])
        req = out["items"][2]
        self.assertEqual((req["person"], req["tool"], req["device"], req["platform"], req["place"]),
                         ("Nansubuga Grace", "Codex", "laptop", "Codex on macOS", "public internet"))
        # paging, and narrowing by kind, person, tool and words
        page = rig.api("GET", "/timeline?limit=1")[1]
        self.assertTrue(page["more"])
        rest = rig.api("GET", f"/timeline?limit=5&before={page['next_before']}")[1]["items"]
        self.assertEqual([e["type"] for e in rest], ["site", "request"])
        self.assertEqual(len(rig.api("GET", "/timeline?type=site")[1]["items"]), 1)
        self.assertEqual(len(rig.api("GET", "/timeline?tool=canva")[1]["items"]), 2)
        self.assertEqual(len(rig.api("GET", "/timeline?q=deploy")[1]["items"]), 1)
        self.assertEqual(rig.api("GET", f"/timeline?person={self.pid + 99}")[1]["items"], [])

    def test_who_used_what_adds_up_per_person_and_tool(self):
        now = time.time()
        for cost in (0.25, 0.5):
            add_request(self.db, ts=now - 60, person_id=self.pid, key_id=self.kid, cost=cost)
        add_request(self.db, ts=now - 60, person_id=self.pid, key_id=self.kid, outcome="blocked", reason="budget")
        out = self.rig.api("GET", "/usage")[1]
        cc = next(r for r in out["rows"] if r["tool_id"] == "claude-code")
        self.assertEqual((cc["requests"], cc["refused"], cc["cost"], cc["apps"]), (2, 1, 0.75, ["Claude Code"]))
        self.assertEqual(out["people"][0]["person"], "Nansubuga Grace")
        trends = self.rig.api("GET", "/trends?days=7")[1]
        self.assertEqual(len(trends["days"]), 7)
        self.assertEqual(trends["days"][-1]["requests"], 3)
        self.assertEqual(trends["current"]["people"], 1)
        self.assertEqual(trends["top_tools"][0]["tool"], "Claude Code")


class DeviceTests(LensBase):
    def test_a_device_shows_what_it_ran_and_from_where(self):
        now = time.time()
        add_request(self.db, ts=now - 3 * 86400, person_id=self.pid, key_id=self.kid, client_ip="10.0.0.5",
                    user_agent="claude-cli/2.1.286 (external, cli)", session="s-1", prompt="first")
        add_request(self.db, ts=now - 60, person_id=self.pid, key_id=self.kid, client_ip="41.210.1.2", cost=0.4,
                    flags="secret:AWS access key")
        out = self.rig.api("GET", "/devices", who="viewer")[1]
        d = out["items"][0]
        self.assertEqual((d["label"], d["app"], d["last_ip"], d["place"], d["requests_30d"], d["ips_30d"]),
                         ("laptop", "Claude Code", "41.210.1.2", "public internet", 2, 2))
        self.assertEqual(d["state"], "unused")  # last_used is only set by the proxy; these rows were written directly
        one = self.rig.api("GET", f"/devices/{self.kid}")[1]
        self.assertEqual([ip["place"] for ip in one["ips"]], ["public internet", "private network"])
        self.assertEqual(one["sessions"][0]["first_prompt"], "first")
        self.assertEqual(len(one["flagged"]), 1)
        self.assertEqual(len(one["series"]), 30)
        self.rig.api("POST", f"/keys/{self.kid}/revoke")
        self.assertEqual(self.rig.api("GET", f"/devices/{self.kid}")[1]["state"], "revoked")

    def test_browsers_staff_opened_tools_from(self):
        self.enable("canva")
        self.rig.request("GET", "/go/canva", None, {"cookie": self.cookie, "user-agent":
                         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36"})
        b = self.rig.api("GET", "/devices")[1]["browsers"]
        self.assertEqual((b[0]["browser"], b[0]["os"], b[0]["opens"]), ("Chrome", "Windows", 1))

    def test_reading_user_agents_and_addresses(self):
        self.assertEqual(insight.platform("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1"), "Safari on iOS")
        self.assertEqual(insight.platform("Mozilla/5.0 (X11; Linux x86_64) Edg/150.0 Chrome/150"), "Edge on Linux")
        self.assertEqual(insight.platform("Mozilla/5.0 (Linux; Android 15) Chrome/150 Mobile"), "Chrome on Android")
        self.assertIsNone(insight.platform("claude-cli/2.1.286 (external, cli)"))
        self.assertEqual(insight.ip_kind("127.0.0.1"), "this computer")
        self.assertEqual(insight.ip_kind("192.168.1.4"), "private network")
        self.assertEqual(insight.ip_kind("not an ip"), "unknown")


class SecurityTests(LensBase):
    def test_signals_with_their_evidence(self):
        rig = self.rig
        rig.anthropic({"model": "claude-sonnet-4-5", "max_tokens": 5,
                       "messages": [{"role": "user", "content": "use AKIAABCDEFGHIJKLMNOP"}]})
        for _ in range(5):
            rig.anthropic({"model": "claude-sonnet-4-5", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}]},
                          key="sgw_000000000000_badbadbadbadbadbadbadbad")
        rig.request("POST", "/admin/api/login", {"username": "owner", "password": "wrong"}, {"x-gateway-admin": "1"})
        out = rig.api("GET", "/security", who="viewer")[1]
        by = {e["type"]: e for e in out["events"]}
        self.assertIn("an AWS access key", by["credential"]["text"])
        self.assertEqual(by["wrong_key"]["severity"], "medium")
        self.assertIn("5 requests", by["wrong_key"]["text"])
        self.assertIn("owner", by["signin"]["text"])
        self.assertEqual(out["posture"], "watch")
        for e in out["events"]:
            self.assertTrue(e["evidence"])

    def test_unusual_is_measured_against_their_own_normal(self):
        now = time.time()
        for h in range(5):  # five active hours with 4 requests each, two days ago
            for _ in range(4):
                add_request(self.db, ts=now - 2 * 86400 - h * 3600, person_id=self.pid, key_id=self.kid)
        for _ in range(40):
            add_request(self.db, ts=now - 600, person_id=self.pid, key_id=self.kid)
        hit = [e for e in self.rig.api("GET", "/security")[1]["events"] if e["type"] == "unusual"]
        self.assertEqual(len(hit), 1)
        self.assertIn("10× their usual", hit[0]["text"])


class AttentionTests(LensBase):
    def test_one_list_most_urgent_first(self):
        rig, now = self.rig, time.time()
        rig.api("PATCH", f"/people/{self.pid}", {"daily_budget": 1})
        add_request(self.db, ts=now - 60, person_id=self.pid, cost=1.5)
        rig.api("PUT", "/subscriptions/canva", {"state": "active", "monthly_cost": 30, "seats": 0})
        self.enable("midjourney")
        rig.api("PUT", "/subscriptions/midjourney", {"state": "active", "monthly_cost": 30, "seats": 1})
        other = self.db.x("INSERT INTO people(name, created) VALUES(?,?)", ("Okello Brian", now)).lastrowid
        rig.api("POST", f"/people/{other}/tools/midjourney")
        self.staff("POST", "/tools/canva/request", {"reason": "posters"})
        rig.api("POST", "/pause", {"paused": True})
        out = rig.api("GET", "/attention", who="viewer")[1]
        keys = [i["key"] for i in out["items"]]
        self.assertEqual(keys[0], "paused")
        for key in (f"budget-{self.pid}-daily", "seats-midjourney", "requests", "idle"):
            self.assertIn(key, keys)
        sev = [insight.SEVERITY[i["severity"]] for i in out["items"]]
        self.assertEqual(sev, sorted(sev, reverse=True))


    def test_an_offline_computer_running_the_company_browsers(self):
        rig = self.rig
        self.assertNotIn("ws-offline", [i["key"] for i in rig.api("GET", "/attention")[1]["items"]])
        rig.gw.db.x("UPDATE tools SET signin = 'shared', workspace_mode = 'agent' WHERE id = 'midjourney'")
        rig.gw.workspaces.new_key("windows")
        rig.gw.db.set_setting("workspace_host", "windows")
        items = {i["key"]: i for i in rig.api("GET", "/attention", who="viewer")[1]["items"]}
        self.assertEqual(items["ws-offline"]["severity"], "high")  # set up, never checked in
        self.assertIn("Windows PC", items["ws-offline"]["title"])
        self.assertEqual(items["ws-offline"]["href"], "#/settings?tab=browsers")


class SpendTests(LensBase):
    def test_against_the_window_before(self):
        now = time.time()
        since, until = now - 3600, now + 1
        add_request(self.db, ts=now - 600, person_id=self.pid, cost=6.0)
        add_request(self.db, ts=now - 600, person_id=self.pid, cost=None)
        add_request(self.db, ts=now - 5000, person_id=self.pid, cost=2.0)  # the hour before
        out = self.rig.api("GET", f"/spend?since={since}&until={until}")[1]
        self.assertEqual((out["total"], out["previous_total"], out["unpriced"]), (6.0, 2.0, 1))
        self.assertAlmostEqual(out["change"], 2.0)
        grace = out["people"][0]
        self.assertEqual((grace["label"], grace["cost"], grace["previous"]), ("Nansubuga Grace", 6.0, 2.0))
        self.assertEqual(out["tools"][0]["label"], "Claude Code")
        self.assertEqual({x["dimension"] for x in out["increases"]}, {"person", "tool", "model"})
        self.assertEqual(out["departments"][0]["label"], "Creative")


class SearchAndFilterTests(LensBase):
    def test_search_everything(self):
        rid = add_request(self.db, person_id=self.pid, key_id=self.kid, prompt="storyboard for the showcase")
        groups = {g["group"]: g["items"] for g in self.rig.api("GET", "/search?q=grace", who="viewer")[1]["groups"]}
        self.assertEqual(groups["People"][0]["href"], f"#/people/{self.pid}")
        groups = {g["group"]: g["items"] for g in self.rig.api("GET", f"/search?q=%23{rid}")[1]["groups"]}
        self.assertEqual(groups["Requests"][0]["href"], f"#/records/{rid}")
        groups = {g["group"]: g["items"] for g in self.rig.api("GET", "/search?q=showcase")[1]["groups"]}
        self.assertEqual(groups["Requests"][0]["title"], "storyboard for the showcase")
        groups = {g["group"]: g["items"] for g in self.rig.api("GET", "/search?q=lapt")[1]["groups"]}
        self.assertEqual(groups["Devices"][0]["href"], f"#/devices/{self.kid}")
        self.assertEqual(self.rig.api("GET", "/search?q=")[1]["groups"], [])

    def test_audit_and_requests_filters(self):
        rig = self.rig
        rig.api("POST", "/pause", {"paused": True})
        rig.api("GET", "/audit", who="viewer")
        out = rig.api("GET", "/audit?q=paused")[1]
        self.assertEqual([a["action"] for a in out["items"]], ["paused AI access for everyone"])
        self.assertEqual({a["actor"] for a in rig.api("GET", "/audit?actor=viewer")[1]["items"]}, {"viewer"})
        self.assertIn("owner", out["actors"])
        self.assertEqual(rig.api("GET", f"/audit?since={time.time() + 60}")[1]["items"], [])
        add_request(self.db, ts=time.time() - 7200, person_id=self.pid)
        self.assertEqual(len(rig.api("GET", "/requests?dept=Creative")[1]["items"]), 1)
        self.assertEqual(rig.api("GET", "/requests?dept=Finance")[1]["items"], [])
        self.assertEqual(rig.api("GET", f"/requests?until={time.time() - 9000}")[1]["items"], [])


class StaffViewTests(LensBase):
    def test_me_explains_access_requests_privacy_and_devices(self):
        rig = self.rig
        rig.api("PUT", "/settings", {"support_contact": "IT desk — it@swangzavenue.com", "retention_days": 30})
        self.assertEqual(rig.api("GET", "/settings")[1]["support_contact"], "IT desk — it@swangzavenue.com")
        self.enable("canva")
        rig.api("PUT", "/subscriptions/figma-ai", {"state": "active"})
        self.staff("POST", "/tools/figma-ai/request", {"reason": "mockups"})
        add_request(self.db, person_id=self.pid, key_id=self.kid, client="Codex", provider="openai")
        me = self.staff("GET", "/me")[1]
        self.assertEqual(me["privacy"]["support_contact"], "IT desk — it@swangzavenue.com")
        self.assertEqual(me["privacy"]["retention_days"], 30)
        self.assertEqual([(r["tool"], r["state"]) for r in me["access_requests"]], [("Figma AI", "open")])
        canva = next(t for t in me["catalog"] if t["id"] == "canva")
        self.assertEqual(canva["grant"], "direct")
        key = next(k for k in me["keys"] if k["id"] == self.kid)
        self.assertEqual(key["client"], "Codex")
        self.assertNotIn("requests_30d", key)  # which app a device runs, never how much it was used
        self.assertEqual(rig.api("PUT", "/settings", {"support_contact": "x"}, who="viewer")[0], 403)


if __name__ == "__main__":
    unittest.main()
