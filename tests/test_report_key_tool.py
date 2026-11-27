"""Usage reports count a tool-scoped key's requests under the key's tool, whatever the user agent says (the rule the
policies use). A request on a key without a tool is placed by its user agent, as before."""

import unittest

from tests.support import Rig

SECOND = "second-api"
MESSAGE = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}
CODEX = "codex_exec/0.155.0"
PLAIN = "python-requests/2.32"


class ReportKeyToolTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db, self.pid = self.rig.gw.db, self.rig.person_id
        # a second API tool on the same provider, listed after chatgpt
        row = dict(self.db.one("SELECT * FROM tools WHERE id = 'chatgpt'"), id=SECOND, name="Second API")
        self.db.x(f"INSERT INTO tools({', '.join(row)}) VALUES({', '.join('?' * len(row))})", tuple(row.values()))
        for tool_id in ("chatgpt", SECOND):
            self.db.x("DELETE FROM entitlements WHERE tool_id = ? AND person_id = ?", (tool_id, self.pid))
            self.db.x("INSERT INTO entitlements(tool_id, person_id, granted) VALUES(?, ?, 1)", (tool_id, self.pid))

    def scoped_key(self, tool_id):
        status, out = self.rig.api("POST", f"/people/{self.pid}/keys", {"label": tool_id, "tool_id": tool_id})
        self.assertEqual(status, 200, out)
        return out["id"], out["key"]

    def send(self, key, agent, expected=200):
        status = self.rig.openai("/chat/completions", MESSAGE, key=key, extra={"user-agent": agent})[0]
        self.assertEqual(status, expected)
        return self.rig.last_record()

    def get(self, path):
        status, out = self.rig.api("GET", path, who="viewer")
        self.assertEqual(status, 200, out)
        return out

    def usage(self, query=""):
        return {r["tool_id"]: r["requests"] for r in self.get(f"/usage?person={self.pid}{query}")["rows"]}

    def timeline(self, tool_id):
        items = self.get(f"/timeline?kind=request&tool={tool_id}")["items"]
        return sorted((e["id"], e["tool_id"]) for e in items)

    def spend(self):
        return {t["tool_id"]: t["requests"] for t in self.get("/spend")["tools"]}

    def test_a_scoped_keys_requests_count_under_its_tool_in_every_report(self):
        key_id, key = self.scoped_key(SECOND)
        sent = [self.send(key, agent) for agent in (CODEX, PLAIN)]
        ids = sorted(r["id"] for r in sent)

        self.assertEqual(self.usage(), {SECOND: 2})
        self.assertEqual(self.usage(f"&tool={SECOND}"), {SECOND: 2})
        self.assertEqual(self.usage("&tool=codex"), {})
        self.assertEqual(self.usage("&tool=chatgpt"), {})
        self.assertEqual(self.spend(), {SECOND: 2})
        self.assertEqual(self.timeline(SECOND), [(i, SECOND) for i in ids])
        self.assertEqual(self.timeline("codex"), [])
        self.assertEqual(self.timeline("chatgpt"), [])

        own = self.get(f"/tools/{SECOND}/usage")
        self.assertEqual([d["key_id"] for d in own["devices"]], [key_id])
        self.assertEqual(own["devices"][0]["requests"], 2)
        self.assertAlmostEqual(own["cost_30d"], sum(r["cost"] or 0 for r in sent))
        self.assertEqual(sum(d["uses"] for d in own["series"]), 2)
        for other in ("codex", "chatgpt"):
            with self.subTest(other=other):
                page = self.get(f"/tools/{other}/usage")
                self.assertEqual((page["devices"], page["cost_30d"], page["active_month"]), ([], 0, 0))

    def test_keys_without_a_tool_are_placed_by_user_agent_as_before(self):
        key_id, key = self.scoped_key(SECOND)
        scoped = self.send(key, CODEX)
        as_codex = self.send(self.rig.key, CODEX)
        as_api = self.send(self.rig.key, PLAIN)

        self.assertEqual(self.usage(), {SECOND: 1, "codex": 1, "chatgpt": 1})
        self.assertEqual(self.spend(), {SECOND: 1, "codex": 1, "chatgpt": 1})
        # as before, the filter by tool and the tool's page show an API request without a scoped key under every API
        # tool of its provider, labelled with the provider's first one
        shared = as_api["key_id"]
        for tool_id, events, keys in (
                (SECOND, [(scoped["id"], SECOND), (as_api["id"], "chatgpt")], {key_id, shared}),
                ("codex", [(as_codex["id"], "codex")], {shared}),
                ("chatgpt", [(as_api["id"], "chatgpt")], {shared})):
            with self.subTest(tool=tool_id):
                self.assertEqual(self.timeline(tool_id), sorted(events))
                self.assertEqual({d["key_id"] for d in self.get(f"/tools/{tool_id}/usage")["devices"]}, keys)

    def test_a_developer_tools_key_counts_under_that_tool(self):
        _, key = self.scoped_key("codex")
        record = self.send(key, PLAIN)
        self.assertEqual(self.usage(), {"codex": 1})
        self.assertEqual(self.timeline("codex"), [(record["id"], "codex")])
        self.assertEqual(self.timeline("chatgpt"), [])

    def test_a_refused_request_is_listed_under_the_keys_tool(self):
        _, key = self.scoped_key(SECOND)
        self.db.x("DELETE FROM entitlements WHERE tool_id = ?", (SECOND,))
        record = self.send(key, CODEX, expected=403)
        self.assertIn(record["id"], [d.get("id") for d in self.get(f"/tools/{SECOND}/usage")["denials"]])
        self.assertNotIn(record["id"], [d.get("id") for d in self.get("/tools/codex/usage")["denials"]])

    def test_the_revoke_simulator_counts_the_same_requests(self):
        key_id, key = self.scoped_key(SECOND)
        self.send(key, CODEX)
        answers = {}
        for tool_id in (SECOND, "codex"):
            status, out = self.rig.api("POST", "/simulate/revoke", {"person_id": self.pid, "tool_id": tool_id}, who="viewer")
            self.assertEqual(status, 200, out)
            answers[tool_id] = (out["usage_30d"]["requests"], [d["id"] for d in out["devices"]])
        self.assertEqual(answers, {SECOND: (1, [key_id]), "codex": (0, [])})


if __name__ == "__main__":
    unittest.main()
