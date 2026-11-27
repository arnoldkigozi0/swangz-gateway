"""Issuing a key for one tool, from the console and from the command line: the key is scoped to that tool, and only a
tool the person may use now can be chosen."""

import contextlib
import io
import os
import re
import time
import unittest
from unittest.mock import patch

from gateway import parse, reporting
from tests.support import Rig
from tests.test_gateway import StaffBase

MESSAGE = {"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}
# every value that names no tool; only leaving tool_id out asks for an unscoped key
NO_TOOL = ("", " ", " \t\n", None, 0, False, [], {})


class IssueKeyScopeBase(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db, self.pid = self.rig.gw.db, self.rig.person_id

    def keys(self):
        return self.db.scalar("SELECT COUNT(*) FROM keys")

    def scope(self, key_id):
        return self.db.scalar("SELECT hub_tool_id FROM keys WHERE id = ?", (key_id,))


class ConsoleIssueKeyTests(IssueKeyScopeBase):
    def issue(self, tool_id, who="owner"):
        return self.rig.api("POST", f"/people/{self.pid}/keys", {"label": "tool key", "tool_id": tool_id}, who=who)

    def test_a_key_for_an_assigned_tool_is_scoped_to_it(self):
        status, out = self.issue("claude-code")
        self.assertEqual(status, 200, out)
        self.assertEqual(self.scope(out["id"]), "claude-code")
        self.assertEqual(self.rig.anthropic(MESSAGE, key=out["key"])[0], 200)
        self.assertEqual(self.rig.openai("/chat/completions", {**MESSAGE, "model": "gpt-5"}, key=out["key"])[0], 403)
        detail = self.db.scalar("SELECT detail FROM audit WHERE action = 'issued a key' ORDER BY id DESC LIMIT 1")
        self.assertIn("tool: claude-code", detail)

    def test_a_department_grant_counts(self):
        self.db.x("DELETE FROM entitlements")
        self.db.x("INSERT INTO entitlements(tool_id, department, granted) VALUES('claude-code', 'Creative', ?)",
                  (time.time(),))
        status, out = self.issue("claude-code")
        self.assertEqual(status, 200, out)
        self.assertEqual(self.scope(out["id"]), "claude-code")

    def test_a_tool_the_person_may_not_use_gets_no_key(self):
        before = self.keys()
        cases = (("UPDATE people SET status = 'suspended'", "UPDATE people SET status = 'active'"),
                 ("UPDATE people SET access_until = 1", "UPDATE people SET access_until = NULL"),
                 ("UPDATE entitlements SET expires = 1", "UPDATE entitlements SET expires = NULL"))
        for take_away, give_back in cases:
            with self.subTest(case=take_away):
                self.db.x(take_away)
                status, out = self.issue("claude-code")
                self.assertEqual(status, 403, out)
                self.db.x(give_back)
        for tool_id in ("gemini", "no-such-tool"):  # a website tool, and one that does not exist
            self.assertEqual(self.issue(tool_id)[0], 400, tool_id)
        self.assertEqual(self.issue("claude-code", who="viewer")[0], 403)
        self.assertEqual(self.keys(), before)


    def test_only_a_left_out_tool_makes_an_unscoped_key(self):
        before = self.keys()
        for value in NO_TOOL:
            with self.subTest(tool_id=value):
                status, out = self.issue(value)
                self.assertEqual(status, 400, out)
        self.assertEqual(self.keys(), before)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM audit WHERE action = 'issued a key'"), 0)
        status, out = self.rig.api("POST", f"/people/{self.pid}/keys", {"label": "no tool"})
        self.assertEqual(status, 200, out)
        self.assertIsNone(self.scope(out["id"]))


class StaffIssueKeyScopeTests(StaffBase):
    def test_only_a_left_out_tool_makes_an_unscoped_key(self):
        self.assertEqual(self.staff("POST", "/welcome", {"token": self.invite(), "password": "a-long-password"})[0], 200)
        db = self.rig.gw.db
        before = db.scalar("SELECT COUNT(*) FROM keys")
        for value in NO_TOOL:
            with self.subTest(tool_id=value):
                status, out = self.staff("POST", "/keys", {"label": "tool key", "tool_id": value})
                self.assertEqual(status, 400, out)
        self.assertEqual(db.scalar("SELECT COUNT(*) FROM keys"), before)
        for body, scope in (({"label": "tool key", "tool_id": "claude-code"}, "claude-code"),
                            ({"label": "no tool"}, None)):
            status, out = self.staff("POST", "/keys", body)
            self.assertEqual(status, 200, out)
            self.assertEqual(db.scalar("SELECT hub_tool_id FROM keys WHERE id = ?", (out["id"],)), scope)


JOB = "job0001-0000-4000-8000-000000000000"
# every request besides model and media ones that a scoped key may make, by the tool it is scoped to
LISTED = {
    "claude-code": (("GET", "/anthropic/v1/models"), ("GET", "/anthropic/v1/models/claude-sonnet-4-6"),
                    ("POST", "/anthropic/v1/messages/count_tokens")),
    "codex": (("GET", "/openai/v1/models"), ("GET", "/openai/v1/models/gpt-5"),
              ("POST", "/openai/v1/responses/compact")),
    "elevenlabs": (("GET", "/elevenlabs/v1/voices"), ("GET", "/elevenlabs/v1/voices/JBFqnCBsd6RMkjVDRZzb"),
                   ("GET", "/elevenlabs/v1/models")),
    "higgsfield-ai": (("POST", f"/higgsfield/requests/{JOB}/cancel"),),
}
# reachable through the gateway, but on no scoped key's list
UNLISTED = {
    "claude-code": (("GET", "/anthropic/v1/models/claude-sonnet-4-6/more"), ("GET", "/anthropic/v1/models/%2e%2e")),
    "codex": (("POST", "/openai/v1/embeddings"), ("POST", "/openai/v1/completions")),
    "elevenlabs": (("GET", "/elevenlabs/v2/voices"), ("GET", "/elevenlabs/v1/voices/abc/settings")),
    "higgsfield-ai": (("GET", "/higgsfield/v1/motions"), ("GET", "/higgsfield/v1/job-sets/abc")),
}
STATUS = ("GET", f"/higgsfield/requests/{JOB}/status")


class ScopedKeyListTests(unittest.TestCase):
    def test_the_list_matches_whole_paths_only(self):
        for dialect, method, path in (("anthropic", "GET", "/v1/models/.."), ("anthropic", "GET", "/v1/models/."),
                                      ("anthropic", "GET", "/x/v1/models"), ("anthropic", "HEAD", "/v1/models"),
                                      ("anthropic", "POST", "/v1/models"), ("openai", "GET", "/v1/modelsx"),
                                      ("openai", "POST", "/v1/responses/compact/x"),
                                      ("higgsfield", "POST", "/requests/a/../b/cancel"),
                                      ("higgsfield", "POST", "/v1/requests-a/cancel"), ("media", "GET", "/v1/models")):
            with self.subTest(dialect=dialect, method=method, path=path):
                self.assertFalse(parse.scoped_key_may(dialect, method, path))
        for dialect, method, path in (("openai", "GET", "/v1/models/ft:gpt-4o:org::abc/?limit=1"),
                                      ("higgsfield", "POST", "/requests/job-1/cancel"),
                                      ("higgsfield", "POST", "/v1/requests/job-1/cancel")):
            with self.subTest(dialect=dialect, method=method, path=path):
                self.assertTrue(parse.scoped_key_may(dialect, method, path))


class ScopedKeyRequestBase(IssueKeyScopeBase):
    def setUp(self):
        super().setUp()
        for tool_id in ("elevenlabs", "higgsfield-ai"):
            self.db.x("INSERT INTO entitlements(tool_id, person_id, granted) VALUES(?,?,?)",
                      (tool_id, self.pid, time.time()))
        # JOB is this person's, started under the video tool, so only the key scope rules below decide
        self.db.x("INSERT INTO requests(ts, person_id, provider, method, path, kind, client, outcome, turn_id, hub_tool_id)"
                  " VALUES(?,?,'higgsfield','POST','/x','media','python-urllib','ok',?,'higgsfield-ai')", (time.time(), self.pid, JOB))

    def scoped_key(self, tool_id):
        status, out = self.rig.api("POST", f"/people/{self.pid}/keys", {"label": "tool key", "tool_id": tool_id})
        self.assertEqual(status, 200, out)
        return out

    def call(self, method, path, key, agent="python-urllib"):
        """-> (status, body, the request's record)"""
        before = self.db.scalar("SELECT COUNT(*) FROM requests")
        status, _, body = self.rig.request(method, path, MESSAGE if method == "POST" else None,
                                           {"authorization": f"Bearer {key}", "user-agent": agent})
        self.rig.wait_for(lambda: self.db.scalar("SELECT COUNT(*) FROM requests") > before)
        return status, body, self.rig.last_record()

    def refused(self, method, path, key, reason="key tool scope"):
        sent = len(self.rig.fake.seen)
        status, body, row = self.call(method, path, key)
        self.assertEqual(status, 403, body)
        self.assertEqual((row["person_id"], row["status"], row["outcome"], row["reason"]),
                         (self.pid, 403, "blocked", reason))
        self.assertEqual(len(self.rig.fake.seen), sent)  # nothing reached a provider

    def passed(self, method, path, key, tool_id):
        sent = len(self.rig.fake.seen)
        status, body, row = self.call(method, path, key)
        self.assertNotEqual(status, 403, body)
        self.assertEqual(len(self.rig.fake.seen), sent + 1)
        self.assertEqual(row["hub_tool_id"], tool_id)
        self.assertNotEqual(row["outcome"], "blocked", row["reason"])


class ScopedKeyRequestTests(ScopedKeyRequestBase):
    def test_a_listed_request_passes_on_a_key_for_that_provider(self):
        for tool_id, cases in LISTED.items():
            key = self.scoped_key(tool_id)["key"]
            for method, path in cases:
                with self.subTest(tool=tool_id, path=path):
                    self.passed(method, path, key, tool_id)

    def test_a_listed_request_is_refused_on_a_key_for_another_provider(self):
        keys = {tool_id: self.scoped_key(tool_id)["key"] for tool_id in LISTED}
        for tool_id, cases in LISTED.items():
            for other in (t for t in LISTED if t != tool_id):
                for method, path in cases:
                    with self.subTest(key=other, path=path):
                        self.refused(method, path, keys[other])

    def test_an_unlisted_request_is_refused(self):
        for tool_id, cases in UNLISTED.items():
            key = self.scoped_key(tool_id)["key"]
            for method, path in cases:
                with self.subTest(tool=tool_id, path=path):
                    self.refused(method, path, key)

    def test_an_unscoped_key_still_makes_them(self):
        for method, path in LISTED["codex"] + UNLISTED["codex"]:
            with self.subTest(path=path):
                self.assertNotEqual(self.call(method, path, self.rig.key)[0], 403)

    def test_job_polling_is_for_the_keys_own_provider(self):
        for tool_id in ("elevenlabs", "claude-code"):
            with self.subTest(key=tool_id):
                self.refused(*STATUS, self.scoped_key(tool_id)["key"])
        self.passed(*STATUS, self.scoped_key("higgsfield-ai")["key"], "higgsfield-ai")

    def test_an_archived_tools_key_is_refused(self):
        cases = (("claude-code", LISTED["claude-code"] + (("POST", "/anthropic/v1/messages"),)),
                 ("higgsfield-ai", LISTED["higgsfield-ai"] + (STATUS,)))
        for tool_id, requests in cases:
            key = self.scoped_key(tool_id)["key"]
            self.assertEqual(self.rig.api("POST", f"/tools/{tool_id}/archive")[0], 200)
            for method, path in requests:
                with self.subTest(tool=tool_id, path=path):
                    self.refused(method, path, key)

    def test_a_tool_no_longer_assigned_stops_them_too(self):
        keys = [(self.scoped_key(t)["key"], c) for t, c in (("codex", LISTED["codex"][0]), ("higgsfield-ai", STATUS))]
        self.db.x("DELETE FROM entitlements")
        for key, (method, path) in keys:
            with self.subTest(path=path):
                self.refused(method, path, key, "tool entitlement")

    def test_an_overdue_weekly_report_stops_them_too(self):
        keys = [(self.scoped_key(t)["key"], c) for t, c in (("codex", LISTED["codex"][2]), ("higgsfield-ai", STATUS))]
        last_week = reporting.week(self.rig.gw)["starts"] - 7 * 86400
        for tool_id in ("codex", "higgsfield-ai"):
            self.db.x("INSERT INTO launches(tool_id, person_id, ts, outcome) VALUES(?,?,?, 'opened')",
                      (tool_id, self.pid, last_week + 100))
        for key, (method, path) in keys:
            with self.subTest(path=path):
                self.refused(method, path, key, "weekly_report_required")

    def test_a_company_policy_applies_to_the_listed_requests(self):
        key = self.scoped_key("codex")["key"]
        status, out = self.rig.api("POST", "/policies", {"name": "No Codex", "effect": "deny",
                                                         "subjects": {"everyone": True}, "scope": {"tools": ["codex"]}})
        self.assertEqual(status, 200, out)
        for method, path in LISTED["codex"]:
            with self.subTest(path=path):
                status, _, row = self.call(method, path, key, "codex_exec/0.155.0")
                self.assertEqual((status, row["reason"], row["rule"]), (403, "policy: No Codex", f"policy:{out['id']}"))
        self.assertEqual(self.rig.fake.seen, [])


class CommandLineIssueKeyTests(IssueKeyScopeBase):
    def run_cli(self, *argv):
        from gateway.__main__ import main

        out = io.StringIO()
        env = {"GATEWAY_DATA": self.rig.tmp, "GATEWAY_ENV_FILE": os.path.join(self.rig.tmp, "no.env")}
        with patch.dict(os.environ, env), contextlib.redirect_stdout(out):
            main(list(argv))
        return out.getvalue()

    def test_a_key_for_an_assigned_tool_is_scoped_to_it(self):
        text = self.run_cli("issue-key", str(self.pid), "--tool", "claude-code")
        key = re.search(r"^  (sgw_\S+)$", text, re.M).group(1)
        row = self.db.one("SELECT * FROM keys ORDER BY rowid DESC LIMIT 1")
        self.assertEqual((row["person_id"], row["hub_tool_id"], row["created_by"]),
                         (self.pid, "claude-code", "command line"))
        self.assertEqual(self.rig.anthropic(MESSAGE, key=key)[0], 200)

    def test_an_empty_tool_gets_no_key(self):
        before = self.keys()
        for value in ("", "   "):
            with self.subTest(tool=value):
                with self.assertRaises(SystemExit) as caught:
                    self.run_cli("issue-key", str(self.pid), "--tool", value)
                self.assertIn("Choose an API or developer tool", str(caught.exception))
        self.assertEqual(self.keys(), before)

    def test_leaving_the_tool_out_makes_an_unscoped_key(self):
        self.run_cli("issue-key", str(self.pid))
        self.assertIsNone(self.db.scalar("SELECT hub_tool_id FROM keys ORDER BY rowid DESC LIMIT 1"))

    def test_an_unassigned_tool_gets_no_key(self):
        self.db.x("DELETE FROM entitlements")
        before = self.keys()
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("issue-key", str(self.pid), "--tool", "claude-code")
        self.assertIn("not assigned", str(caught.exception))
        self.assertEqual(self.keys(), before)


if __name__ == "__main__":
    unittest.main()
