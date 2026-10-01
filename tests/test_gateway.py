import http.client
import json
import socket
import threading
import time
import unittest

from .support import Rig, sse_events


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    # ------------------------------------------------------------ the happy paths

    def test_claude_code_stream_is_passed_through_and_recorded(self):
        rig = self.rig
        body = {"model": "claude-opus-5-5", "stream": True, "max_tokens": 1000,
                "messages": [{"role": "user", "content": [{"type": "text", "text": "<system-reminder>ctx</system-reminder>"},
                                                          {"type": "text", "text": "run ls -la"}]}]}
        status, headers, payload = rig.anthropic(body, extra={"x-claude-code-session-id": "sess-1"})
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers["content-type"])
        names = [n for n, _ in sse_events(payload)]
        self.assertEqual(names[0], "message_start")
        self.assertEqual(names[-1], "message_stop")

        sent = rig.fake.seen[-1]
        self.assertEqual(sent["headers"]["x-api-key"], "sk-ant-provider-secret")  # the provider key went upstream
        self.assertNotIn("authorization", sent["headers"])
        self.assertNotIn(rig.key, json.dumps(sent))  # the person's gateway key did not
        self.assertEqual(sent["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(sent["body"], body)  # byte-for-byte the same request

        r = rig.last_record()
        self.assertEqual((r["person_id"], r["key_id"], r["client"], r["session"]), (rig.person_id, rig.key_id, "Claude Code", "sess-1"))
        self.assertEqual((r["outcome"], r["status"], r["model"], r["stream"]), ("ok", 200, "claude-opus-5-5", 1))
        self.assertEqual(r["prompt"], "run ls -la")
        self.assertEqual(json.loads(r["actions"]), [{"tool": "Bash", "kind": "command", "text": "$ ls -la"}])
        self.assertEqual((r["in_tok"], r["out_tok"], r["cache_write_tok"], r["cache_read_tok"]), (1000, 50, 200, 3000))
        self.assertAlmostEqual(r["cost"], (1000 * 4 + 50 * 20 + 200 * 5 + 3000 * 0.2) / 1e6)
        self.assertIsNotNone(r["ttft_ms"])

    def test_tool_result_turn_and_full_record_pull_back(self):
        rig = self.rig
        first = {"model": "claude-sonnet-5-5", "stream": False, "max_tokens": 100,
                 "messages": [{"role": "user", "content": "run cat secrets.txt"}]}
        status, _, payload = rig.anthropic(first)
        self.assertEqual(status, 200)
        tool_use = json.loads(payload)["content"][1]
        second = dict(first, messages=first["messages"] + [
            {"role": "assistant", "content": json.loads(payload)["content"]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use["id"],
                                          "content": "token ghp_" + "a" * 36}]}])
        status, _, payload = rig.anthropic(second)
        self.assertEqual(json.loads(payload)["content"][0]["text"], "done")
        r = rig.last_record()
        self.assertIsNone(r["prompt"])  # the agent was working on its own, nobody typed anything
        self.assertEqual(r["reply"], "done")
        self.assertEqual(r["flags"], "secret:GitHub token")

        status, record = rig.api("GET", f"/requests/{r['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(record["request"], second)  # the whole conversation comes back
        self.assertEqual(record["response"]["content"][0]["text"], "done")
        self.assertEqual(record["person"], "Nansubuga Grace")
        audit = rig.gw.db.one("SELECT * FROM audit ORDER BY id DESC LIMIT 1")
        self.assertEqual(audit["action"], "opened the full record")  # watching is itself on the record
        self.assertEqual(audit["actor"], "owner")

    def test_codex_responses_stream(self):
        rig = self.rig
        body = {"model": "gpt-6-astra", "stream": True, "input": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "run git status"}]}]}
        status, _, payload = rig.openai("/responses", body, extra={"session-id": "codex-thread-1"})
        self.assertEqual(status, 200)
        self.assertEqual(sse_events(payload)[-1][0], "response.completed")
        self.assertEqual(rig.fake.seen[-1]["headers"]["authorization"], "Bearer sk-openai-provider-secret")
        r = rig.last_record()
        self.assertEqual((r["client"], r["session"], r["prompt"]), ("Codex", "codex-thread-1", "run git status"))
        self.assertEqual(json.loads(r["actions"])[0]["text"], "$ git status")
        self.assertEqual((r["in_tok"], r["cache_read_tok"], r["out_tok"], r["reasoning_tok"]), (1000, 4000, 300, 120))
        self.assertIsNone(r["cost"])  # no price row for this model: shown as unpriced, never guessed

    def test_chat_stream_gets_usage_added(self):
        rig = self.rig
        body = {"model": "gpt-x", "stream": True, "messages": [{"role": "user", "content": "run make build"}]}
        status, _, payload = rig.openai("/chat/completions", body, extra={"user-agent": "OpenAI/Python 2.1"})
        self.assertEqual(status, 200)
        self.assertEqual(rig.fake.seen[-1]["body"]["stream_options"], {"include_usage": True})
        r = rig.last_record()
        self.assertEqual(json.loads(r["actions"])[0]["text"], "$ bash -lc make build")
        self.assertEqual((r["in_tok"], r["cache_read_tok"], r["out_tok"]), (200, 1000, 40))

    def test_keep_alive_reuses_the_connection(self):
        rig = self.rig
        conn = http.client.HTTPConnection("127.0.0.1", rig.port, timeout=10)
        headers = {"x-api-key": rig.key}
        for text in ("one", "two", "three"):
            body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": text}]}
            status, _, payload = rig.request("POST", "/anthropic/v1/messages", body, headers, conn=conn)
            self.assertEqual(status, 200)
            self.assertTrue(payload.endswith(b"\n\n"))
        conn.close()
        self.assertEqual(rig.gw.db.scalar("SELECT COUNT(*) FROM requests"), 3)

    def test_warm_up_probe_and_sub_agents(self):
        rig = self.rig
        status, _, _ = rig._request("HEAD", "/anthropic/api/hello")
        self.assertEqual(status, 200)
        self.assertEqual(rig.gw.db.scalar("SELECT COUNT(*) FROM requests"), 0)  # not noise in the log
        rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "look around"}]},
                      extra={"x-claude-code-agent-id": "ag-7", "x-claude-code-agent-type": "Explore",
                             "x-claude-code-request-class": "subagent", "x-claude-code-prompt-id": "prompt-3"})
        r = rig.last_record()
        self.assertEqual((r["agent"], r["request_class"], r["turn_id"]), ("Explore:ag-7", "subagent", "prompt-3"))
        self.assertEqual(rig.fake.seen[-1]["headers"]["x-claude-code-agent-id"], "ag-7")  # still forwarded

    def test_only_model_endpoints_go_through(self):
        rig = self.rig
        for method, path in (("GET", "/anthropic/v1/files"), ("POST", "/anthropic/v1/messages/batches"),
                             ("GET", "/openai/v1/responses/resp_123"), ("GET", "/anthropic/v1/organizations/users")):
            status, _, payload = rig.request(method, path, None, {"x-api-key": rig.key})
            self.assertEqual(status, 403, path)
            self.assertIn("is not available through the gateway", payload.decode())
        self.assertEqual(len(rig.fake.seen), 0)  # none of it reached the provider
        self.assertEqual(rig.last_record()["reason"], "endpoint not allowed")

    def test_refusals_tell_tools_not_to_retry(self):
        rig = self.rig
        rig.api("POST", f"/keys/{rig.key_id}/revoke")
        status, headers, _ = rig.anthropic({"model": "claude-opus-5-5", "messages": []})
        self.assertEqual((status, headers["x-should-retry"]), (403, "false"))

    def test_upstream_error_passes_through(self):
        status, _, payload = self.rig.anthropic({"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "fail please"}]})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(payload)["error"]["message"], "fake failure")
        r = self.rig.last_record()
        self.assertEqual((r["outcome"], r["reason"]), ("error", "fake failure"))

    def test_count_tokens_is_logged_but_hidden_by_default(self):
        rig = self.rig
        status, _, payload = rig.request("POST", "/anthropic/v1/messages/count_tokens",
                                         {"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "x"}]},
                                         {"x-api-key": rig.key})
        self.assertEqual((status, json.loads(payload)), (200, {"input_tokens": 42}))
        self.assertEqual(rig.api("GET", "/requests")[1]["items"], [])
        self.assertEqual(len(rig.api("GET", "/requests?all=1")[1]["items"]), 1)

    # ------------------------------------------------------------ refusals

    def test_wrong_keys_are_refused_and_noted(self):
        rig = self.rig
        status, _, payload = rig.anthropic({"model": "m", "messages": []}, key="sk-ant-someone-elses")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(payload)["error"]["type"], "authentication_error")
        forged = f"sgw_{rig.key_id}_not-the-secret"
        status, _, _ = rig.anthropic({"model": "m", "messages": []}, key=forged)
        self.assertEqual(status, 401)
        r = rig.last_record()
        self.assertEqual((r["outcome"], r["key_id"], r["person_id"]), ("denied", rig.key_id, None))
        self.assertEqual(len(rig.fake.seen), 0)  # nothing reached the provider

    def test_revoked_suspended_paused_and_model_rules(self):
        rig = self.rig
        body = {"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "hi"}]}

        rig.gw.db.x("UPDATE people SET allowed_models = 'claude-haiku-*, claude-sonnet-*' WHERE id = ?", (rig.person_id,))
        status, _, payload = rig.anthropic(body)
        self.assertEqual(status, 403)
        self.assertIn("not cleared to use the model 'claude-opus-5-5'", json.loads(payload)["error"]["message"])
        self.assertEqual(rig.anthropic(dict(body, model="claude-haiku-4-5"))[0], 200)
        rig.gw.db.x("UPDATE people SET allowed_models = '' WHERE id = ?", (rig.person_id,))

        self.assertEqual(rig.api("POST", "/pause", {"paused": True})[0], 200)
        status, _, payload = rig.openai("/responses", {"model": "gpt-6-astra", "input": "hi"})
        self.assertEqual(status, 403)
        self.assertIn("paused for everyone", json.loads(payload)["error"]["message"])  # OpenAI-shaped error
        rig.api("POST", "/pause", {"paused": False})

        rig.api("POST", f"/people/{rig.person_id}/suspend")
        self.assertEqual(rig.anthropic(body)[0], 403)
        rig.api("POST", f"/people/{rig.person_id}/resume")
        self.assertEqual(rig.anthropic(body)[0], 200)

        rig.api("POST", f"/keys/{rig.key_id}/revoke")
        status, _, payload = rig.anthropic(body)
        self.assertEqual(status, 403)
        self.assertIn("revoked", json.loads(payload)["error"]["message"])
        reasons = [r["reason"] for r in rig.gw.db.q("SELECT reason FROM requests WHERE outcome = 'blocked' ORDER BY id")]
        self.assertEqual(reasons, ["model not allowed", "paused", "suspended", "key revoked"])

    def test_budget_stops_spending(self):
        rig = self.rig
        rig.api("PATCH", f"/people/{rig.person_id}", {"daily_budget": "0.009"})
        body = {"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "hi"}]}
        self.assertEqual(rig.anthropic(body)[0], 200)  # costs $0.0066
        self.assertEqual(rig.anthropic(body)[0], 200)  # $0.0132 spent now — over
        status, _, payload = rig.anthropic(body)
        self.assertEqual(status, 403)
        self.assertIn("daily AI budget ($0.01) is used up", json.loads(payload)["error"]["message"])

    def test_secret_blocking_when_switched_on(self):
        rig = self.rig
        rig.api("PUT", "/settings", {"block_secrets": True})
        body = {"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "deploy with AKIAABCDEFGHIJKLMNOP"}]}
        status, _, payload = rig.anthropic(body)
        self.assertEqual(status, 403)
        self.assertIn("AWS access key", json.loads(payload)["error"]["message"])
        self.assertEqual(len(rig.fake.seen), 0)

    def test_provider_without_a_key(self):
        status, _, payload = self.rig.request("POST", "/nokey/v1/chat/completions", {"model": "x", "messages": []},
                                              {"authorization": f"Bearer {self.rig.key}"})
        self.assertEqual(status, 403)
        self.assertIn("has no API key on the gateway", json.loads(payload)["error"]["message"])

    # ------------------------------------------------------------ pulling access back mid-stream

    def _slow_stream(self, results, dialect="anthropic"):
        rig = self.rig
        conn = http.client.HTTPConnection("127.0.0.1", rig.port, timeout=30)
        if dialect == "anthropic":
            body = {"model": "claude-opus-5-5", "stream": True, "messages": [{"role": "user", "content": "slow story"}]}
            conn.request("POST", "/anthropic/v1/messages", json.dumps(body), {"x-api-key": rig.key, "content-type": "application/json"})
        else:
            body = {"model": "gpt-6-astra", "stream": True, "input": "slow story"}
            conn.request("POST", "/openai/v1/responses", json.dumps(body), {"authorization": f"Bearer {rig.key}", "content-type": "application/json"})
        resp = conn.getresponse()
        results["status"] = resp.status
        results["payload"] = resp.read()
        conn.close()

    def test_revoking_a_key_cuts_its_live_stream(self):
        rig = self.rig
        results = {}
        t = threading.Thread(target=self._slow_stream, args=(results,))
        t.start()
        live = rig.wait_for(lambda: [x for x in rig.gw.live.snapshot() if x["bytes"] > 800])  # some words are out
        self.assertEqual(live[0]["person"], "Nansubuga Grace")
        self.assertEqual(rig.api("GET", "/overview")[1]["live"][0]["key_id"], rig.key_id)
        status, out = rig.api("POST", f"/keys/{rig.key_id}/revoke")
        self.assertEqual(out["cut"], 1)
        t.join(10)
        self.assertFalse(t.is_alive())
        events = sse_events(results["payload"])
        self.assertEqual(events[-1][0], "error")
        self.assertIn("revoked", json.loads(events[-1][1])["error"]["message"])
        self.assertLess(len(events), 30)  # stopped long before the 40-piece story finished
        r = rig.wait_for(lambda: rig.gw.db.one("SELECT * FROM requests WHERE outcome = 'cut'"))
        self.assertIn("revoked", r["reason"])
        self.assertTrue(r["reply"].startswith("hello from the fake model"))  # what got through is on record
        self.assertEqual(rig.gw.live.snapshot(), [])

    def test_pausing_everyone_cuts_codex_too(self):
        rig = self.rig
        results = {}
        t = threading.Thread(target=self._slow_stream, args=(results, "openai"))
        t.start()
        rig.wait_for(lambda: [x for x in rig.gw.live.snapshot() if x["streaming"]])
        self.assertEqual(rig.api("POST", "/pause", {"paused": True})[1]["cut"], 1)
        t.join(10)
        events = sse_events(results["payload"])
        self.assertEqual(events[-1][0], "response.failed")

    def test_an_owner_can_stop_one_request(self):
        rig = self.rig
        results = {}
        t = threading.Thread(target=self._slow_stream, args=(results,))
        t.start()
        live = rig.wait_for(lambda: [x for x in rig.gw.live.snapshot() if x["streaming"]])
        status, _ = rig.api("POST", f"/live/{live[0]['id']}/cut", who="viewer")
        self.assertEqual(status, 403)  # viewers watch, they don't act
        self.assertEqual(rig.api("POST", f"/live/{live[0]['id']}/cut")[1]["cut"], 1)
        t.join(10)
        self.assertEqual(rig.wait_for(rig.last_record)["outcome"], "cut")  # written just after the reply ends
        self.assertEqual(rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]})[0], 200)

    def test_a_person_closing_their_tool_is_recorded(self):
        rig = self.rig
        sock = socket.create_connection(("127.0.0.1", rig.port))
        body = json.dumps({"model": "claude-opus-5-5", "stream": True, "messages": [{"role": "user", "content": "slow"}]})
        sock.sendall((f"POST /anthropic/v1/messages HTTP/1.1\r\nHost: x\r\nx-api-key: {rig.key}\r\n"
                      f"content-type: application/json\r\ncontent-length: {len(body)}\r\n\r\n{body}").encode())
        sock.recv(200)
        sock.close()
        r = rig.wait_for(lambda: rig.gw.db.one("SELECT * FROM requests WHERE outcome = 'aborted'"), timeout=15)
        self.assertEqual(r["reason"], "the person's tool disconnected")


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_sign_in(self):
        rig = self.rig
        status, _, _ = rig.request("POST", "/admin/api/login", {"username": "owner", "password": "nope"}, {"x-gateway-admin": "1"})
        self.assertEqual(status, 401)
        status, _, _ = rig.request("POST", "/admin/api/login", {"username": "owner", "password": "owner-password"})
        self.assertEqual(status, 403)  # no console header: a form on another site cannot sign anyone in
        self.assertEqual(rig.request("GET", "/admin/api/overview")[0], 401)
        cookie = rig.login()
        self.assertIn("HttpOnly", rig.request("POST", "/admin/api/login", {"username": "owner", "password": "owner-password"},
                                              {"x-gateway-admin": "1"})[1]["set-cookie"])
        self.assertEqual(rig.request("GET", "/admin/api/me", headers={"cookie": cookie})[0], 200)

    def test_sign_in_throttle(self):
        rig = self.rig
        for _ in range(8):
            rig.request("POST", "/admin/api/login", {"username": "owner", "password": "wrong"}, {"x-gateway-admin": "1"})
        status, _, payload = rig.request("POST", "/admin/api/login", {"username": "owner", "password": "owner-password"},
                                         {"x-gateway-admin": "1"})
        self.assertEqual(status, 429)

    def test_people_keys_and_setup(self):
        rig = self.rig
        status, out = rig.api("POST", "/people", {"name": "Kato Brian", "department": "Post-production", "monthly_budget": 40})
        self.assertEqual(status, 200)
        pid = out["id"]
        self.assertEqual(rig.api("POST", "/people", {"name": "x"}, who="viewer")[0], 403)
        status, key = rig.api("POST", f"/people/{pid}/keys", {"label": "edit suite"})
        self.assertTrue(key["key"].startswith("sgw_"))
        names = [t["name"] for t in key["tools"]]
        self.assertIn("Claude Code", names)
        self.assertIn("Codex", names)
        codex = next(t for t in key["tools"] if t["name"] == "Codex")
        self.assertIn('base_url = "https://ai.example.test/openai/v1"', codex["steps"][0]["code"])
        self.assertIn(key["key"], codex["steps"][1]["code"])
        stored = rig.gw.db.one("SELECT * FROM keys WHERE id = ?", (key["id"],))
        self.assertNotIn(key["key"].split("_", 2)[2], json.dumps(stored))  # only a hash is kept

        rig.anthropic({"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "hi"}]}, key=key["key"],
                      extra={"x-claude-code-session-id": "s-9"})
        status, people = rig.api("GET", "/people", who="viewer")
        brian = next(p for p in people["items"] if p["name"] == "Kato Brian")
        self.assertEqual((brian["active_keys"], brian["today"]["requests"]), (1, 1))
        status, person = rig.api("GET", f"/people/{pid}")
        self.assertEqual(person["sessions"][0]["session"], "s-9")
        self.assertEqual(person["sessions"][0]["first_prompt"], "hi")
        status, session = rig.api("GET", "/sessions/s-9")
        self.assertEqual(session["items"][0]["reply"], "hello from the fake model")

    def test_overview_search_and_export(self):
        rig = self.rig
        rig.anthropic({"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "=HYPERLINK(\"http://x\")"}]})
        rig.anthropic({"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "run rm -rf build"}]})
        status, ov = rig.api("GET", "/overview")
        self.assertEqual(ov["today"]["requests"], 2)
        self.assertEqual(ov["people_today"][0]["name"], "Nansubuga Grace")
        found = rig.api("GET", "/requests?q=rm%20-rf")[1]["items"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["actions"][0]["text"], "$ rm -rf build")
        status, csv_bytes = rig.api("GET", "/export.csv")
        text = csv_bytes.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", text)  # a prompt cannot become a spreadsheet formula
        self.assertIn("$ rm -rf build", text)

    def test_prices_and_settings(self):
        rig = self.rig
        rig.openai("/responses", {"model": "gpt-6-astra", "input": "hi"})
        status, prices = rig.api("GET", "/prices")
        self.assertEqual(prices["unpriced_models"], ["gpt-6-astra"])
        self.assertEqual(rig.api("PUT", "/prices/gpt-6-astra", {"input": 2, "output": 8, "cache_read": 0.2})[0], 200)
        rig.openai("/responses", {"model": "gpt-6-astra", "input": "hi"})
        self.assertAlmostEqual(rig.last_record()["cost"], (1000 * 2 + 4000 * 0.2 + 300 * 8) / 1e6)
        self.assertEqual(rig.api("PUT", "/settings", {"retention_days": -1})[0], 400)
        self.assertEqual(rig.api("PUT", "/settings", {"retention_days": 30, "store_bodies": False})[0], 200)
        rig.anthropic({"model": "claude-opus-5-5", "messages": [{"role": "user", "content": "private"}]})
        r = rig.last_record()
        self.assertEqual(r["prompt"], "private")  # the summary is kept…
        self.assertIsNone(r["req_head"])  # …but not the body

    def test_admins(self):
        rig = self.rig
        self.assertEqual(rig.api("POST", "/admins", {"username": "auditor", "password": "short", "role": "viewer"})[0], 400)
        self.assertEqual(rig.api("POST", "/admins", {"username": "auditor", "password": "long-enough-pw", "role": "viewer"})[0], 200)
        self.assertEqual(rig.api("GET", "/admins", who="viewer")[0], 403)
        owner_id = rig.gw.db.scalar("SELECT id FROM admins WHERE username = 'owner'")
        self.assertEqual(rig.api("DELETE", f"/admins/{owner_id}")[0], 400)
        self.assertEqual(rig.api("POST", "/password", {"current": "owner-password", "new": "a-new-password"})[0], 200)
        actions = [a["action"] for a in rig.api("GET", "/audit")[1]["items"]]
        self.assertIn("added a console user", actions)
        self.assertIn("changed own password", actions)

    def test_two_apps_are_served_with_a_strict_policy(self):
        rig = self.rig
        status, headers, payload = rig.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'self'", headers["content-security-policy"])
        self.assertIn(b"<title>Swangz AI</title>", payload)  # staff see the AI app, nothing about monitoring
        self.assertIn(b"portal.js", payload)
        status, _, payload = rig.request("GET", "/admin")
        self.assertIn(b"admin.js", payload)
        self.assertIn(b"admin.js", rig.request("GET", "/admin/people/3")[2])
        status, headers, _ = rig.request("GET", "/static/fonts/Archivo-latin.woff2")
        self.assertEqual((status, headers["content-type"]), (200, "font/woff2"))
        self.assertEqual(rig.request("GET", "/static/../gateway.db")[0], 400)
        self.assertEqual(rig.request("GET", "/static/nope.js")[0], 404)
        self.assertEqual(rig.request("GET", "/static/fonts/../admin.js")[0], 400)


if __name__ == "__main__":
    unittest.main()


class StaffBase(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.cookie = None

    def tearDown(self):
        self.rig.close()

    def staff(self, method, path, body=None, cookie=None, header=True):
        headers = {"x-swangz-app": "1"} if header else {}
        if cookie or self.cookie:
            headers["cookie"] = cookie or self.cookie
        status, h, payload = self.rig.request(method, "/api" + path, body, headers)
        if "set-cookie" in h and h["set-cookie"].startswith("sgw_staff="):
            self.cookie = h["set-cookie"].split(";")[0]
        return status, json.loads(payload) if payload else None

    def invite(self):
        rig = self.rig
        rig.api("PATCH", f"/people/{rig.person_id}", {"email": "Grace@Swangz.com", "monthly_budget": 50})
        status, out = rig.api("POST", f"/people/{rig.person_id}/invite")
        self.assertEqual(status, 200)
        return out["link"].rsplit("/", 1)[1]


class StaffAppTests(StaffBase):
    def test_invite_link_sets_a_password_once(self):
        rig = self.rig
        status, out = rig.api("POST", f"/people/{rig.person_id}/invite")
        self.assertEqual((status, out["error"]), (400, "add their email first — it is what they sign in with"))
        token = self.invite()
        self.assertEqual(self.staff("GET", f"/welcome/{token}")[1]["name"], "Nansubuga Grace")
        self.assertEqual(self.staff("POST", "/welcome", {"token": token, "password": "short"})[0], 400)
        self.assertEqual(self.staff("POST", "/welcome", {"token": token, "password": "a-long-password"})[0], 200)
        self.assertEqual(self.staff("GET", "/me")[1]["name"], "Nansubuga Grace")
        self.assertEqual(self.staff("POST", "/welcome", {"token": token, "password": "another-password"})[0], 404)  # used up
        stored = rig.gw.db.one("SELECT pw_hash, invite_hash FROM people WHERE id = ?", (rig.person_id,))
        self.assertTrue(stored["pw_hash"].startswith("pbkdf2_sha256$"))
        self.assertIsNone(stored["invite_hash"])

    def test_sign_in_and_own_devices(self):
        rig = self.rig
        token = self.invite()
        self.staff("POST", "/welcome", {"token": token, "password": "a-long-password"})
        self.cookie = None
        self.assertEqual(self.staff("POST", "/login", {"email": "grace@swangz.com", "password": "wrong-password"})[0], 401)
        self.assertEqual(self.staff("POST", "/login", {"email": "grace@swangz.com", "password": "a-long-password"}, header=False)[0], 403)
        self.assertEqual(self.staff("POST", "/login", {"email": " GRACE@swangz.com ", "password": "a-long-password"})[0], 200)

        status, me = self.staff("GET", "/me")
        self.assertEqual((me["budget"]["monthly"], len(me["keys"]), me["can_add_keys"]), (50, 1, True))
        self.assertIn("claude-code", [t["id"] for t in me["tools"]])
        for leak in ("prompt", "requests", "actions", "reply", "sessions", "pw_hash", "allowed_models"):
            self.assertNotIn(leak, me)  # the staff app never shows anyone's activity, not even their own

        status, key = self.staff("POST", "/keys", {"label": "Grace MacBook"})
        self.assertEqual(status, 200)
        self.assertEqual(rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]}, key=key["key"])[0], 200)
        self.assertEqual(rig.gw.db.one("SELECT created_by FROM keys WHERE id = ?", (key["id"],))["created_by"], "self")
        self.assertEqual(self.staff("POST", f"/keys/{key['id']}/revoke")[0], 200)
        self.assertEqual(rig.anthropic({"model": "claude-haiku-4-5", "messages": []}, key=key["key"])[0], 403)

        # someone else's key is out of reach
        other = rig.gw.db.x("INSERT INTO people(name, created) VALUES('Kato Brian', 0)").lastrowid
        rig.gw.db.x("INSERT INTO keys(id, person_id, label, secret_hash, hint, created) VALUES('abcdefabcdef', ?, 'x', 'h', 'h', 0)", (other,))
        self.assertEqual(self.staff("POST", "/keys/abcdefabcdef/revoke")[0], 404)
        # and a staff session opens nothing in the admin console
        self.assertEqual(rig.request("GET", "/admin/api/overview", headers={"cookie": self.cookie})[0], 401)

    def test_admin_controls_still_win(self):
        rig = self.rig
        token = self.invite()
        self.staff("POST", "/welcome", {"token": token, "password": "a-long-password"})
        rig.api("PUT", "/settings", {"staff_self_keys": False})
        self.assertEqual(self.staff("POST", "/keys", {"label": "x"})[0], 403)
        rig.api("POST", f"/people/{rig.person_id}/suspend")
        self.assertEqual(self.staff("GET", "/me")[0], 401)  # suspending signs them out of the app too
        actions = [a["action"] for a in rig.api("GET", "/audit")[1]["items"]]
        self.assertIn("set their Swangz AI password", actions)
        self.assertIn("created a sign-in link", actions)


class MediaTests(unittest.TestCase):
    """ElevenLabs and Higgsfield through the gateway: same keys, same rules, same record."""

    def setUp(self):
        self.rig = Rig()

    def tearDown(self):
        self.rig.close()

    def test_elevenlabs_voice_is_recorded_and_playable(self):
        rig = self.rig
        status, headers, audio = rig.request("POST", "/elevenlabs/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb?output_format=mp3_44100_128",
                                             {"text": "Karibu ku Swangz Avenue showcase.", "model_id": "eleven_multilingual_v2"},
                                             {"xi-api-key": rig.key, "user-agent": "elevenlabs-python/2.3.0"})
        self.assertEqual((status, headers["content-type"]), (200, "audio/mpeg"))
        sent = rig.fake.seen[-1]["headers"]
        self.assertEqual(sent["xi-api-key"], "eleven-provider-secret")  # the company key went upstream
        self.assertNotIn(rig.key, json.dumps(rig.fake.seen[-1]))
        r = rig.last_record()
        self.assertEqual((r["kind"], r["media_type"], r["model"], r["units"], r["unit"]),
                         ("media", "voice", "eleven_multilingual_v2", 33, "characters"))
        self.assertEqual(r["prompt"], "Karibu ku Swangz Avenue showcase.")
        self.assertEqual(json.loads(r["actions"])[0]["text"], "voice-over · voice JBFqnCBsd6RMkjVDRZzb · 33 characters")
        status, payload = rig.api("GET", f"/requests/{r['id']}/media")
        self.assertEqual(payload, audio)  # the admin can play back exactly what was generated
        self.assertEqual(rig.gw.db.one("SELECT action FROM audit ORDER BY id DESC LIMIT 1")["action"], "played back a generation")

    def test_higgsfield_job_result_lands_on_the_request(self):
        rig = self.rig
        status, _, payload = rig.request("POST", "/higgsfield/flux-pro/kontext/max/text-to-image",
                                         {"prompt": "Bebe Cool on a boda boda at golden hour, Kampala", "aspect_ratio": "16:9"},
                                         {"authorization": f"Key {rig.key}:anything", "user-agent": "higgsfield-server-js/2.0"})
        job = json.loads(payload)["request_id"]
        self.assertEqual(rig.fake.seen[-1]["headers"]["authorization"], "Key hf-id:hf-provider-secret")
        submit = rig.last_record()
        self.assertEqual((submit["media_type"], submit["turn_id"], submit["prompt"]),
                         ("image", job, "Bebe Cool on a boda boda at golden hour, Kampala"))
        for _ in range(2):
            rig.request("GET", f"/higgsfield/requests/{job}/status", None, {"authorization": f"Key {rig.key}:x"})
        submit = rig.gw.db.one("SELECT * FROM requests WHERE id = ?", (submit["id"],))
        self.assertEqual(json.loads(submit["result_urls"]), ["https://cdn.example.test/result.jpg"])
        self.assertEqual(submit["reply"], "completed · 1 result")
        listed = rig.api("GET", "/requests")[1]["items"]
        self.assertEqual([x["kind"] for x in listed], ["media"])  # status polling stays out of the feed

    def test_account_wide_endpoints_and_service_rules(self):
        rig = self.rig
        status, _, _ = rig.request("GET", "/elevenlabs/v1/history", None, {"xi-api-key": rig.key})
        self.assertEqual(status, 403)  # the company account's history would show everyone's work to everyone
        rig.api("PATCH", f"/people/{rig.person_id}", {"allowed_models": "claude-haiku-*"})
        status, _, _ = rig.request("POST", "/elevenlabs/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb",
                                   {"text": "hi", "model_id": "eleven_flash_v2_5"}, {"xi-api-key": rig.key})
        self.assertEqual(status, 200)  # model rules are for chat models; services have their own rule
        rig.api("PATCH", f"/people/{rig.person_id}", {"allowed_services": "anthropic, openai"})
        status, _, payload = rig.request("POST", "/elevenlabs/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb", {"text": "hi"},
                                         {"xi-api-key": rig.key})
        self.assertEqual(status, 403)
        self.assertIn("ElevenLabs isn't switched on for you", payload.decode())
        self.assertEqual(rig.anthropic({"model": "claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]})[0], 200)

    def test_internal_header_needs_the_secret(self):
        rig = self.rig
        status, _, _ = rig.request("POST", "/elevenlabs/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb", {"text": "hi"},
                                   {"x-sgw-internal": "guess", "x-sgw-person": str(rig.person_id)})
        self.assertEqual(status, 401)


class StudioTests(StaffBase):
    """The staff app's Studio: voice, image and video, checked and recorded like any other request."""

    def setUp(self):
        super().setUp()
        token = self.invite()
        self.staff("POST", "/welcome", {"token": token, "password": "a-long-password"})

    def test_voice(self):
        rig = self.rig
        status, studio = self.staff("GET", "/studio")
        self.assertEqual((status, studio["voice"], studio["image"]), (200, True, True))
        self.assertEqual(studio["voices"][0]["name"], "George")
        status, made = self.staff("POST", "/studio/voice", {"text": "Welcome to the showcase.", "voice_id": "JBFqnCBsd6RMkjVDRZzb"})
        self.assertEqual(status, 200)
        self.assertTrue(made["audio"].startswith("/api/studio/media/"))
        st, _, audio = rig.request("GET", made["audio"], headers={"cookie": self.cookie})
        self.assertEqual(st, 200)
        self.assertTrue(audio.startswith(b"ID3"))
        r = rig.gw.db.one("SELECT * FROM requests WHERE id = ?", (made["id"],))
        self.assertEqual((r["client"], r["person_id"], r["key_id"], r["prompt"]),
                         ("Swangz AI Studio", rig.person_id, None, "Welcome to the showcase."))
        self.assertEqual(self.staff("GET", "/studio")[1]["recent"][0]["id"], made["id"])
        self.assertEqual(self.staff("POST", "/studio/voice", {"text": "please fail", "voice_id": "JBFqnCBsd6RMkjVDRZzb"})[1]["error"],
                         "This request exceeds your quota.")

    def test_image_job(self):
        status, made = self.staff("POST", "/studio/generate", {"kind": "image", "prompt": "A poster for the showcase", "aspect_ratio": "9:16"})
        self.assertEqual(status, 200)
        self.assertTrue(made["job"])
        first = self.staff("GET", f"/studio/jobs/{made['job']}")[1]
        self.assertEqual((first["state"], first["urls"]), ("in_progress", []))
        done = self.staff("GET", f"/studio/jobs/{made['job']}")[1]
        self.assertEqual(done["urls"], ["https://cdn.example.test/result.jpg"])
        self.assertEqual(self.staff("POST", "/studio/generate", {"kind": "video", "prompt": "slow push in", "image_url": "ftp://x"})[0], 400)

    def test_the_rules_still_apply(self):
        rig = self.rig
        rig.api("PATCH", f"/people/{rig.person_id}", {"allowed_services": "anthropic"})
        self.assertEqual(self.staff("GET", "/studio")[1]["voice"], False)
        self.assertEqual(self.staff("POST", "/studio/voice", {"text": "hi", "voice_id": "JBFqnCBsd6RMkjVDRZzb"})[0], 403)
        rig.api("PATCH", f"/people/{rig.person_id}", {"allowed_services": ""})
        rig.api("POST", "/pause", {"paused": True})
        status, out = self.staff("POST", "/studio/voice", {"text": "hi", "voice_id": "JBFqnCBsd6RMkjVDRZzb"})
        self.assertEqual(status, 403)
        self.assertIn("paused for everyone", out["error"])
        self.assertEqual(rig.last_record()["outcome"], "blocked")  # refused, and on the record


class AddressTests(unittest.TestCase):
    def test_setup_follows_the_link_people_used(self):
        rig = Rig()
        try:
            rig.settings.public_url = ""
            rig.gw.trust_proxy = True
            rig.login()
            headers = {"cookie": rig.cookies["owner"], "x-gateway-admin": "1",
                       "x-forwarded-host": "abc123.lhr.life", "x-forwarded-proto": "https"}
            status, _, payload = rig.request("POST", f"/admin/api/people/{rig.person_id}/keys", {"label": "x"}, headers)
            codex = next(t for t in json.loads(payload)["tools"] if t["id"] == "codex")
            self.assertIn('base_url = "https://abc123.lhr.life/openai/v1"', codex["steps"][0]["code"])
            headers["x-forwarded-host"] = "evil.example/<script>"
            status, _, payload = rig.request("GET", "/admin/api/me", None, headers)
            self.assertNotIn("evil", json.loads(payload)["base_url"])  # a malformed host header is ignored
        finally:
            rig.close()
