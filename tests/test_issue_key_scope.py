"""Issuing a key for one tool, from the console and from the command line: the key is scoped to that tool, and only a
tool the person may use now can be chosen."""

import contextlib
import io
import os
import re
import time
import unittest
from unittest.mock import patch

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


class ScopedKeyOtherRequestTests(IssueKeyScopeBase):
    """The tool check knows model and media requests. Anything else on a scoped key is refused, never passed on."""

    CASES = (("GET", "/anthropic/v1/models"), ("POST", "/anthropic/v1/messages/count_tokens"),
             ("GET", "/openai/v1/models"), ("POST", "/openai/v1/embeddings"), ("POST", "/openai/v1/completions"),
             ("POST", "/openai/v1/responses/compact"), ("GET", "/elevenlabs/v1/voices"))

    def call(self, method, path, key):
        return self.rig.request(method, path, MESSAGE if method == "POST" else None,
                                {"authorization": f"Bearer {key}"})

    def test_a_scoped_key_is_refused_and_the_refusal_recorded(self):
        out = self.rig.api("POST", f"/people/{self.pid}/keys", {"label": "tool key", "tool_id": "claude-code"})[1]
        records = lambda: self.db.scalar("SELECT COUNT(*) FROM requests")
        for method, path in self.CASES:
            with self.subTest(path=path):
                before = records()
                status, _, body = self.call(method, path, out["key"])
                self.assertEqual(status, 403, body)
                self.assertIn(b"scoped to one tool", body)
                self.rig.wait_for(lambda: records() > before)
                row = self.rig.last_record()
                self.assertEqual((row["person_id"], row["key_id"], row["kind"], row["status"], row["outcome"],
                                  row["reason"]), (self.pid, out["id"], "other", 403, "blocked", "key tool scope"))
        self.assertEqual(self.rig.fake.seen, [])  # nothing reached a provider

    def test_an_unscoped_key_still_makes_them(self):
        for method, path in self.CASES:
            with self.subTest(path=path):
                self.assertNotEqual(self.call(method, path, self.rig.key)[0], 403)
        self.assertEqual(len(self.rig.fake.seen), len(self.CASES))


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
