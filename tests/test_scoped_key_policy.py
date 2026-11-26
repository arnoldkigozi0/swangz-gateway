"""A tool-scoped key says which tool a request is for. Company policies, their monthly caps and the policy simulator
read it from the key, never from the user agent; keys without a tool are read from the user agent as before."""

import unittest

from gateway import policy
from tests.support import Rig

MESSAGE = {"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}
OTHER_AGENTS = ("codex_exec/0.155.0", "python-requests/2.32")


class ScopedKeyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db = self.rig.gw.db
        status, out = self.rig.api("POST", f"/people/{self.rig.person_id}/keys", {"label": "scoped", "tool_id": "claude-code"})
        self.assertEqual(status, 200, out)
        self.key = out["key"]

    def draft(self, tool_id, effect="deny", **params):
        return {"name": f"{effect} {tool_id}", "effect": effect, "subjects": {"everyone": True},
                "scope": {"tools": [tool_id]}, "params": params}

    def add(self, tool_id, effect="deny", **params):
        status, out = self.rig.api("POST", "/policies", self.draft(tool_id, effect, **params))
        self.assertEqual(status, 200, out)
        return out["id"]

    def ask(self, agent, key=None):
        return self.rig.anthropic(MESSAGE, key=key or self.key, extra={"user-agent": agent})[0]

    def test_a_deny_on_the_keys_tool_holds_under_any_user_agent(self):
        pid = self.add("claude-code")
        for agent in ("claude-cli/2.1.286",) + OTHER_AGENTS:
            with self.subTest(agent=agent):
                self.assertEqual(self.ask(agent), 403)
                record = self.rig.last_record()
                self.assertEqual((record["outcome"], record["rule"]), ("blocked", f"policy:{pid}"))

    def test_the_keys_housekeeping_requests_are_judged_the_same_way(self):
        pid = self.add("claude-code")
        status = self.rig.request("GET", "/anthropic/v1/models", None,
                                  {"x-api-key": self.key, "user-agent": OTHER_AGENTS[0]})[0]
        self.assertEqual((status, self.rig.last_record()["rule"]), (403, f"policy:{pid}"))

    def test_a_deny_on_the_user_agents_tool_does_not_reach_a_key_for_another_tool(self):
        self.add("codex")
        self.assertEqual(self.ask("codex_exec/0.155.0"), 200)

    def test_a_key_without_a_tool_is_read_from_the_user_agent_as_before(self):
        self.add("claude-code")
        self.assertEqual(self.ask("claude-cli/2.1.286", key=self.rig.key), 403)
        self.assertEqual(self.ask("python-requests/2.32", key=self.rig.key), 200)

    def test_a_monthly_cap_counts_the_keys_spend_under_any_user_agent(self):
        self.assertEqual(self.ask(OTHER_AGENTS[0]), 200)
        self.db.x("UPDATE requests SET cost = 10 WHERE id = ?", (self.rig.last_record()["id"],))
        spent = {tool: policy.scoped_spend(self.db, policy.validate(self.draft(tool, "cap", limit_usd=5)), 0, 4e9)
                 for tool in ("claude-code", "codex")}
        self.assertEqual(spent, {"claude-code": 10, "codex": 0})
        self.add("claude-code", "cap", limit_usd=5)
        self.assertEqual(self.ask(OTHER_AGENTS[1]), 403)

    def test_a_cap_still_counts_unscoped_spend_by_user_agent(self):
        self.assertEqual(self.ask("claude-cli/2.1.286", key=self.rig.key), 200)
        self.db.x("UPDATE requests SET cost = 10 WHERE id = ?", (self.rig.last_record()["id"],))
        self.add("claude-code", "cap", limit_usd=5)
        self.assertEqual(self.ask(OTHER_AGENTS[1]), 403)  # a scoped request shares the tool's cap
        self.assertEqual(self.ask("claude-cli/2.1.286", key=self.rig.key), 403)

    def test_the_simulator_replays_a_request_against_the_keys_tool(self):
        self.assertEqual(self.ask(OTHER_AGENTS[0]), 200)
        for tool_id, refused in (("claude-code", 1), ("codex", 0)):
            status, out = self.rig.api("POST", "/policies/simulate", {"policy": self.draft(tool_id), "days": 1})
            self.assertEqual((status, out["refused"]["request"]), (200, refused), tool_id)


if __name__ == "__main__":
    unittest.main()
