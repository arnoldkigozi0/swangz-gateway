"""Every request that may have reached a provider leaves a record: text that can't be written is refused before it
leaves, and when the full record can't be saved a minimal one is."""

import http.client
import json
import os
import sqlite3
import time
import unittest
from unittest.mock import patch

from gateway import parse, proxy, purpose, security, store
from gateway.config import Provider
from tests.support import Rig

REFUSAL = (400, "blocked", "body text not valid")
PATHS = ("/anthropic/v1/messages", "/openai/v1/chat/completions", "/openai/v1/responses",
         "/elevenlabs/v1/text-to-speech/v1", "/higgsfield/flux-pro/image", "/custom/v1/anything-new")
ASK = {"model": "claude-sonnet-5-5", "max_tokens": 20, "messages": [{"role": "user", "content": "private words"}]}


class RecordCase(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db = self.rig.gw.db
        self.db.set_setting("store_bodies", "1")
        os.environ["FAKE_CUSTOM_KEY"] = "custom-provider-secret"
        self.rig.settings.providers["custom"] = Provider("custom", self.rig.fake.url, "FAKE_CUSTOM_KEY", "media", label="Custom")
        self.logged = []
        self.rig.gw.log = self.logged.append

    def send(self, path, body, key=None, extra=None, method="POST"):
        """-> (status, body, the request's record)"""
        headers = {"authorization": f"Bearer {key or self.rig.key}", "user-agent": "python-requests/2.32", **(extra or {})}
        before = self.count()
        status, _, payload = self.rig.request(method, path, body, headers)
        self.assertEqual(self.count(), before + 1)
        return status, payload, self.rig.last_record()

    def count(self):
        return self.db.scalar("SELECT COUNT(*) FROM requests")


class UnwritableTextTests(RecordCase):
    BODIES = (
        b'{"prompt": "p", "messages": [{"role": "user", "content": "a \\ud800 b"}], "input": "x"}',
        b'{"prompt": "a \\udfff"}',
        b'{"model": "m\\ud800", "prompt": "p"}',
        b'{"prompt": "p", "x": [{"y": {"z\\udc00": 1}}]}',
        b'{"prompt": "p", "x": "\\ude00\\ud83d"}',  # a pair the wrong way round
        b'{"prompt": "a \xed\xa0\x80 b"}',  # the same thing written as bytes
        b'["\\ud800"]',
        '{"prompt": "a \\ud800"}'.encode("utf-16"),
    )

    def test_it_is_refused_and_recorded_on_every_provider(self):
        for path in PATHS:
            for body in self.BODIES:
                with self.subTest(path=path, body=body):
                    sent = len(self.rig.fake.seen)
                    status, payload, row = self.send(path, body)
                    self.assertEqual((status, row["outcome"], row["reason"]), REFUSAL, payload)
                    self.assertEqual((row["person_id"], row["key_id"], row["status"]),
                                     (self.rig.person_id, self.rig.key_id, 400))
                    self.assertEqual((row["req_head"], row["prompt"]), (None, None))
                    self.assertEqual(len(self.rig.fake.seen), sent)  # nothing reached the provider

    def test_a_bad_key_is_still_told_only_that(self):
        status, _, row = self.send(PATHS[0], self.BODIES[0], key="sgw-not-a-key")
        self.assertEqual((status, row["reason"], row["person_id"]), (401, "bad key", None))

    def test_whole_pairs_and_written_out_escapes_pass(self):
        for body in (b'{"model": "m", "messages": [{"role": "user", "content": "hi \\ud83d\\ude00"}]}',
                     b'{"model": "m", "messages": [{"role": "user", "content": "type \\\\ud800"}]}'):
            with self.subTest(body=body):
                status, payload, row = self.send(PATHS[0], body)
                self.assertEqual((status, row["outcome"], row["reason"]), (200, "ok", None), payload)
                self.assertTrue(row["req_head"])

    def test_a_tools_own_note_holding_such_text_is_ignored(self):
        note = '{"turn_id": "t\\ud800", "agent_name": "a", "request_kind": "turn"}'
        for body, extra in ((ASK, {"x-codex-turn-metadata": note}),
                            (dict(ASK, client_metadata={"x-codex-turn-metadata": note}), None)):
            with self.subTest(extra=bool(extra)):
                status, payload, row = self.send(PATHS[0], body, extra=extra)
                self.assertEqual((status, row["outcome"], row["reason"]), (200, "ok", None), payload)
                self.assertEqual((row["turn_id"], row["agent"]), (None, None))
                self.assertTrue(row["req_head"])


class MinimalRecordTests(RecordCase):
    def minimal(self, row, status, outcome, path="/v1/messages"):
        self.assertEqual((row["person_id"], row["key_id"], row["path"], row["status"], row["outcome"], row["reason"]),
                         (self.rig.person_id, self.rig.key_id, path, status, outcome, "record failed"))
        for column in ("prompt", "reply", "actions", "session", "req_head", "req_items", "resp_blob"):
            self.assertIsNone(row[column], column)

    def test_any_failure_while_saving_still_leaves_a_record(self):
        for target, name in ((store, "store_request_body"), (store, "store_response"), (purpose, "classify"),
                             (proxy.pricing, "find_price"), (proxy.Call, "_write_full")):
            with self.subTest(name=name), patch.object(target, name, side_effect=RuntimeError("broken")):
                status, _, row = self.send(PATHS[0], ASK)
                self.assertEqual(status, 200)
                self.minimal(row, 200, "ok")
                self.assertEqual(row["provider"], "anthropic")
        self.assertIn("could not record request", self.logged[0])

    def test_the_cost_and_tokens_are_kept(self):
        with patch.object(store, "store_response", side_effect=sqlite3.OperationalError("disk")):
            _, _, row = self.send(PATHS[0], ASK)
        self.assertEqual((row["model"], row["in_tok"], row["out_tok"], row["cache_read_tok"]),
                         ("claude-sonnet-5-5", 1000, 50, 3000))
        self.assertGreater(row["cost"], 0)
        # the body saved inside the failed attempt was undone, so the next record saves it again
        _, _, row = self.send(PATHS[0], ASK)
        self.assertIsNone(row["reason"])
        self.assertEqual(store.load_request_body(self.db, row)["messages"], ASK["messages"])

    def test_an_answer_that_cannot_be_written(self):
        real = parse.summarize_response
        with patch.object(parse, "summarize_response", lambda *a: dict(real(*a), reply="a \ud800", model="m\ud800")):
            status, _, row = self.send(PATHS[0], dict(ASK, model=None))
        self.assertEqual(status, 200)
        self.minimal(row, 200, "ok")
        self.assertEqual((row["model"], row["in_tok"]), ("m?", 1000))

    def test_a_number_too_big_for_the_database(self):
        status, payload, row = self.send("/higgsfield/flux-pro/image", {"prompt": "p", "num_images": 10 ** 30})
        self.assertEqual(status, 200, payload)
        self.minimal(row, 200, "ok", "/flux-pro/image")
        self.assertEqual(row["turn_id"], json.loads(payload)["request_id"])  # the job is still theirs to follow
        status, _, poll = self.send(f"/higgsfield/requests/{row['turn_id']}/status", None, method="GET")
        self.assertEqual((status, poll["outcome"]), (200, "ok"))

    def test_a_refusal_that_cannot_be_saved_in_full(self):
        with patch.object(proxy.Call, "_write_full", side_effect=RuntimeError("broken")):
            status, _, row = self.send("/nokey/v1/chat/completions", ASK)
        self.assertEqual(status, 403)
        self.minimal(row, 403, "blocked", "/v1/chat/completions")

    def test_a_failure_after_the_answer_arrived(self):
        with patch.object(parse, "summarize_response", side_effect=TypeError("unexpected shape")):
            status, _, row = self.send(PATHS[0], ASK)
        self.assertEqual(status, 200)
        self.minimal(row, 200, "ok")
        self.assertGreater(row["resp_bytes"], 0)

    def test_a_failure_while_sending(self):
        with patch.object(proxy.Call, "_send", side_effect=ValueError("could not send")):
            status, _, row = self.send(PATHS[0], ASK)
        self.assertEqual(status, 500)
        self.minimal(row, None, "error")
        self.assertEqual(self.rig.gw.live.snapshot(), [])

    def test_a_failure_in_the_middle_of_a_stream(self):
        with patch.object(parse.StreamReader, "feed", side_effect=AttributeError("unexpected event")):
            with self.assertRaises(http.client.IncompleteRead):
                self.rig.anthropic(dict(ASK, stream=True))
            self.rig.wait_for(self.count)
        self.minimal(self.rig.last_record(), 200, "error")
        self.assertEqual((self.count(), self.rig.gw.live.snapshot()), (1, []))

    def test_when_even_that_cannot_be_saved_the_answer_still_arrives(self):
        with patch.object(proxy.Call, "_insert", side_effect=sqlite3.OperationalError("disk is full")):
            status, _, payload = self.rig._request("POST", PATHS[0], ASK, {"x-api-key": self.rig.key})
            self.rig.wait_for(lambda: any("even minimally" in line for line in self.logged))
        self.assertEqual((status, self.count()), (200, 0), payload)


if __name__ == "__main__":
    unittest.main()
