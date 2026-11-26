""""Explain a decision" for a tool the person holds a scoped key for answers as the gateway does for that key: the
rules follow the key's tool, whatever the user agent says. Without such a key the answer is as before."""

import unittest

from tests.support import Rig

SECOND = "second-api"
MESSAGE = {"model": "gpt-5", "messages": [{"role": "user", "content": "hi"}]}
AGENTS = ("codex_exec/0.155.0", "python-requests/2.32")


class ExplainKeyToolTests(unittest.TestCase):
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

    def scoped_key(self):
        status, out = self.rig.api("POST", f"/people/{self.pid}/keys", {"label": "second", "tool_id": SECOND})
        self.assertEqual(status, 200, out)
        return out["id"], out["key"]

    def deny(self, tool_id):
        status, out = self.rig.api("POST", "/policies", {
            "name": f"deny {tool_id}", "effect": "deny", "subjects": {"everyone": True}, "scope": {"tools": [tool_id]},
            "params": {}})
        self.assertEqual(status, 200, out)

    def explain(self, query=f"tool={SECOND}"):
        status, out = self.rig.api("GET", f"/policies/explain?person={self.pid}&{query}&model=gpt-5", who="viewer")
        self.assertEqual(status, 200, out)
        return out

    def send(self, key, agent):
        return self.rig.openai("/chat/completions", MESSAGE, key=key, extra={"user-agent": agent})[0]

    def assert_both(self, key, allowed, decided_by=None):
        answer = self.explain()
        self.assertEqual((answer["allowed"], answer["decided_by"]), (allowed, decided_by), answer["steps"])
        for agent in AGENTS:
            with self.subTest(agent=agent):
                self.assertEqual(self.send(key, agent), 200 if allowed else 403)

    def test_a_deny_on_the_keys_tool(self):
        _, key = self.scoped_key()
        self.deny(SECOND)
        self.assert_both(key, False, "Company policies")

    def test_a_deny_on_the_providers_first_tool_does_not_reach_the_key(self):
        _, key = self.scoped_key()
        self.deny("chatgpt")
        self.assert_both(key, True)
        self.assertIn("their key for Second API", " ".join(self.explain()["notes"]))

    def test_the_keys_tool_must_still_be_assigned(self):
        _, key = self.scoped_key()
        self.db.x("DELETE FROM entitlements WHERE tool_id = ?", (SECOND,))
        self.assert_both(key, False, "Their key's tool")

    def test_the_keys_tool_must_not_be_removed(self):
        _, key = self.scoped_key()
        self.db.x("UPDATE tools SET archived = 1 WHERE id = ?", (SECOND,))
        self.assert_both(key, False, "Their key's tool")

    def test_without_a_key_for_the_tool_the_answer_is_as_before(self):
        self.deny(SECOND)
        before = self.explain()
        self.assertTrue(before["allowed"])  # a key without a tool is placed on the provider's first tool
        self.assertNotIn("Their key's tool", [s["check"] for s in before["steps"]])
        self.assertEqual(len(before["notes"]), 1)
        self.assertEqual(self.send(self.rig.key, "python-requests/2.32"), 200)

    def test_a_revoked_key_no_longer_counts(self):
        key_id, _ = self.scoped_key()
        self.deny(SECOND)
        self.db.x("UPDATE keys SET revoked = 1 WHERE id = ?", (key_id,))
        self.assertTrue(self.explain()["allowed"])

    def test_naming_only_the_provider_is_as_before(self):
        self.scoped_key()
        self.deny(SECOND)
        answer = self.explain("provider=openai")
        self.assertEqual((answer["allowed"], answer["tool"]["id"]), (True, "chatgpt"))
        self.assertEqual(len(answer["notes"]), 1)


if __name__ == "__main__":
    unittest.main()
