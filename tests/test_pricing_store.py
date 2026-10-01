import json
import os
import shutil
import tempfile
import time
import unittest

from gateway import pricing, store
from gateway.db import DB
from gateway.parse import empty_usage


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = DB(os.path.join(self.tmp, "g.db"))
        pricing.seed(self.db)
        self.prices = pricing.load(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp)

    def test_lookup(self):
        self.assertEqual(pricing.find_price(self.prices, "claude-opus-5-5")["input"], 4.0)
        self.assertEqual(pricing.find_price(self.prices, "claude-opus-5")["input"], 5.0)
        self.assertEqual(pricing.find_price(self.prices, "claude-haiku-4-5-20251001")["input"], 1.0)
        self.assertIsNone(pricing.find_price(self.prices, "gpt-6-astra"))
        self.assertIsNone(pricing.find_price(self.prices, None))

    def test_cost_counts_every_meter(self):
        usage = dict(empty_usage(), input=1000, output=50, cache_write=200, cache_read=3000)
        expected = (1000 * 4 + 50 * 20 + 200 * 5 + 3000 * 0.2) / 1e6
        self.assertAlmostEqual(pricing.cost(self.prices["claude-opus-5-5"], usage), expected)
        self.assertAlmostEqual(pricing.cost(self.prices["claude-opus-5-5"], dict(usage, speed="fast")), expected * 2)
        self.assertIsNone(pricing.cost(None, usage))

    def test_seed_does_not_overwrite_edits(self):
        self.db.x("UPDATE prices SET input = 99 WHERE model = 'claude-opus-5-5'")
        pricing.seed(self.db)
        self.assertEqual(pricing.load(self.db)["claude-opus-5-5"]["input"], 99)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = DB(os.path.join(self.tmp, "g.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp)

    def save(self, body, ts):
        head, items = store.store_request_body(self.db, body, b"", "messages")
        self.db.x("INSERT INTO requests(ts, provider, method, path, kind, outcome, req_list_field, req_head, req_items)"
                  " VALUES(?,?,?,?,?,?,?,?,?)", (ts, "anthropic", "POST", "/v1/messages", "messages", "ok", "messages", head, items))
        return self.db.one("SELECT * FROM requests ORDER BY id DESC LIMIT 1")

    def test_a_growing_conversation_is_stored_once(self):
        tools = [{"name": "Bash", "description": "x" * 5000}]
        messages = []
        for turn in range(30):
            messages = messages + [{"role": "user", "content": f"step {turn}", "cache_control": {"type": "ephemeral"}},
                                   {"role": "assistant", "content": f"ok {turn}"}]
            # tools move the cache marker every turn; that must not defeat the de-duplication
            for m in messages[:-2]:
                m.pop("cache_control", None)
            self.save({"model": "m", "tools": tools, "messages": messages}, time.time())
        blobs = self.db.scalar("SELECT COUNT(*) FROM blobs")
        self.assertEqual(blobs, 30 * 2 + 1)  # every message once, plus one head (model + tools)

    def test_rebuild(self):
        body = {"model": "m", "system": "s", "messages": [{"role": "user", "content": [{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}]}]}
        row = self.save(body, time.time())
        rebuilt = store.load_request_body(self.db, row)
        self.assertEqual(rebuilt, {"model": "m", "system": "s", "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]})

    def test_purge_keeps_shared_bodies(self):
        shared = [{"role": "user", "content": "shared"}]
        self.save({"model": "m", "messages": shared}, time.time() - 100 * 86400)
        keep = self.save({"model": "m", "messages": shared + [{"role": "user", "content": "new"}]}, time.time())
        removed, orphans = store.purge(self.db, 90)
        self.assertEqual(removed, 1)
        self.assertEqual(orphans, 0)  # the old head and message are still used by the newer request
        self.assertEqual(store.load_request_body(self.db, keep)["messages"][1]["content"], "new")
        self.db.x("DELETE FROM requests")
        removed, orphans = store.purge(self.db, 90)
        self.assertEqual(orphans, 3)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM blobs"), 0)

    def test_raw_bodies(self):
        head, items = store.store_request_body(self.db, None, b"--multipart--", None)
        self.assertIsNone(items)
        self.assertEqual(store.get_blob(self.db, head), b"--multipart--")
        self.assertEqual(json.loads(store.canonical({"b": 1, "a": {"cache_control": 1, "x": 2}})), {"a": {"x": 2}, "b": 1})


if __name__ == "__main__":
    unittest.main()
