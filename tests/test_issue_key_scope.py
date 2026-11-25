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

MESSAGE = {"model": "claude-sonnet-4-6", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}


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

    def test_an_unassigned_tool_gets_no_key(self):
        self.db.x("DELETE FROM entitlements")
        before = self.keys()
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("issue-key", str(self.pid), "--tool", "claude-code")
        self.assertIn("not assigned", str(caught.exception))
        self.assertEqual(self.keys(), before)


if __name__ == "__main__":
    unittest.main()
