import json
import unittest

from gateway import parse
from gateway.proxy import endpoint_allowed

CLAUDE_CODE_FIRST_TURN = {
    "model": "claude-opus-5-5", "stream": True,
    "metadata": {"user_id": json.dumps({"device_id": "abc", "account_uuid": "", "session_id": "8bb244f3-9cb8-4176-a164-9191fb02ceda"})},
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "<system-reminder>\nAttribution rules...\n</system-reminder>"},
        {"type": "text", "text": "<system-reminder>more context</system-reminder>"},
        {"type": "text", "text": "fix the login bug"}]}],
}

CLAUDE_CODE_TOOL_TURN = {
    "model": "claude-opus-5-5", "stream": True,
    "messages": CLAUDE_CODE_FIRST_TURN["messages"] + [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "AKIAABCDEFGHIJKLMNOP in .env"},
                                     {"type": "text", "text": "<system-reminder>todo list</system-reminder>"}]}],
}

CODEX_FIRST_TURN = {
    "model": "gpt-6-astra", "stream": True, "prompt_cache_key": "01a0f89f-831e",
    "input": [
        {"type": "additional_tools", "role": "developer", "tools": []},
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "You are Codex"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>\n<cwd>/x</cwd>\n</environment_context>"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "add a test for the parser"}]},
    ],
}


class RequestTests(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(parse.endpoint_kind("anthropic", "/v1/messages?beta=true"), "messages")
        self.assertEqual(parse.endpoint_kind("anthropic", "/v1/messages/count_tokens"), "other")
        self.assertEqual(parse.endpoint_kind("openai", "/v1/chat/completions"), "chat")
        self.assertEqual(parse.endpoint_kind("openai", "/v1/responses"), "responses")
        self.assertEqual(parse.endpoint_kind("openai", "/v1/responses/compact"), "other")
        self.assertEqual(parse.endpoint_kind("openai", "/v1/models"), "other")

    def test_claude_code_prompt_is_what_was_typed(self):
        s = parse.summarize_request("messages", CLAUDE_CODE_FIRST_TURN)
        self.assertEqual(s["prompt"], "fix the login bug")
        self.assertEqual(s["model"], "claude-opus-5-5")
        self.assertTrue(s["stream"])

    def test_tool_turn_has_no_prompt_but_a_tail(self):
        s = parse.summarize_request("messages", CLAUDE_CODE_TOOL_TURN)
        self.assertIsNone(s["prompt"])
        self.assertEqual(len(s["tail"]), 1)
        self.assertEqual(parse.find_secrets(s["tail"]), ["AWS access key"])

    def test_codex_prompt(self):
        s = parse.summarize_request("responses", CODEX_FIRST_TURN)
        self.assertEqual(s["prompt"], "add a test for the parser")

    def test_codex_tool_turn(self):
        body = dict(CODEX_FIRST_TURN, input=CODEX_FIRST_TURN["input"] + [
            {"type": "reasoning", "summary": []},
            {"type": "custom_tool_call", "name": "exec", "input": "await tools.exec_command({cmd: 'ls'})", "call_id": "c1"},
            {"type": "custom_tool_call_output", "call_id": "c1", "output": "a.txt"}])
        s = parse.summarize_request("responses", body)
        self.assertIsNone(s["prompt"])
        self.assertEqual(len(s["tail"]), 1)

    def test_chat_prompt_and_images(self):
        body = {"model": "gpt-x", "messages": [
            {"role": "system", "content": "be nice"},
            {"role": "user", "content": [{"type": "text", "text": "what is in this picture?"},
                                         {"type": "image_url", "image_url": {"url": "data:..."}}]}]}
        s = parse.summarize_request("chat", body)
        self.assertEqual(s["prompt"], "what is in this picture?")
        self.assertEqual(s["attachments"], 1)

    def test_sessions(self):
        self.assertEqual(parse.session_of({}, CLAUDE_CODE_FIRST_TURN), "8bb244f3-9cb8-4176-a164-9191fb02ceda")
        self.assertEqual(parse.session_of({"X-Claude-Code-Session-Id": "abc"}, {}), "abc")
        self.assertEqual(parse.session_of({}, CODEX_FIRST_TURN), "01a0f89f-831e")
        self.assertIsNone(parse.session_of({}, {"model": "x"}))

    def test_request_meta(self):
        meta = parse.request_meta({"X-Claude-Code-Agent-Id": "a1", "x-claude-code-agent-type": "Explore",
                                   "x-claude-code-request-class": "subagent", "x-claude-code-prompt-id": "p-1"}, {})
        self.assertEqual(meta, {"request_class": "subagent", "agent": "Explore:a1", "turn_id": "p-1"})
        self.assertEqual(parse.request_meta({"x-claude-code-compaction": "auto"}, {})["request_class"], "compaction")
        codex = json.dumps({"agent_name": "/root/tester", "request_kind": "turn", "root_turn_id": "t-9"})
        self.assertEqual(parse.request_meta({"x-codex-turn-metadata": codex}, {}),
                         {"request_class": "subagent", "agent": "sub-agent:/root/tester", "turn_id": "t-9"})
        root = {"client_metadata": {"x-codex-turn-metadata": json.dumps({"agent_name": "/root", "request_kind": "turn"})}}
        self.assertEqual(parse.request_meta({}, root)["request_class"], "main")
        self.assertEqual(parse.request_meta({}, {}), {"request_class": None, "agent": None, "turn_id": None})

    def test_endpoint_rules(self):
        self.assertTrue(endpoint_allowed("anthropic", "POST", "/v1/messages?beta=true"))
        self.assertTrue(endpoint_allowed("anthropic", "GET", "/v1/models/claude-opus-5-5"))
        self.assertFalse(endpoint_allowed("anthropic", "GET", "/v1/files"))
        self.assertFalse(endpoint_allowed("anthropic", "GET", "/v1/messages"))
        self.assertTrue(endpoint_allowed("openai", "POST", "/v1/responses/compact"))
        self.assertFalse(endpoint_allowed("openai", "GET", "/v1/responses/resp_1"))
        self.assertTrue(endpoint_allowed("openai", "POST", "/v1/images/generations", "POST /v1/images/generations"))

    def test_clients(self):
        self.assertEqual(parse.client_name({"user-agent": "claude-cli/2.1.286 (external, sdk-cli)"}), "Claude Code")
        self.assertEqual(parse.client_name({"user-agent": "codex_exec/0.155.0 (Ubuntu)"}), "Codex")
        self.assertEqual(parse.client_name({"user-agent": "codex_cli_rs/0.150.0"}), "Codex")
        self.assertEqual(parse.client_name({"user-agent": "OpenAI/Python 2.1.0"}), "OpenAI SDK")
        self.assertEqual(parse.client_name({}), "unknown")

    def test_secrets(self):
        self.assertEqual(parse.find_secrets("key sk-ant-api03-abcdefghijklmnopqrstuvwxyz"), ["Anthropic API key"])
        self.assertEqual(parse.find_secrets("-----BEGIN OPENSSH PRIVATE KEY-----"), ["Private key"])
        self.assertEqual(parse.find_secrets("nothing to see"), [])


class ToolTests(unittest.TestCase):
    def one(self, name, inp):
        acts = parse.describe_tool(name, inp)
        self.assertEqual(len(acts), 1)
        return acts[0]

    def test_claude_code_tools(self):
        self.assertEqual(self.one("Bash", {"command": "npm test"})["text"], "$ npm test")
        self.assertEqual(self.one("Edit", {"file_path": "/app/login.ts", "old_string": "a", "new_string": "b"})["text"], "edited /app/login.ts")
        self.assertEqual(self.one("Write", {"file_path": "/app/new.ts", "content": "x"})["kind"], "edit")
        self.assertEqual(self.one("Read", {"file_path": "/etc/hosts"})["text"], "read /etc/hosts")
        self.assertEqual(self.one("Grep", {"pattern": "TODO", "path": "src"})["text"], "searched TODO in src")
        self.assertEqual(self.one("WebFetch", {"url": "https://swangz.com", "prompt": "x"})["text"], "fetched https://swangz.com")
        self.assertEqual(self.one("Agent", {"description": "review the diff", "prompt": "..."})["kind"], "agent")

    def test_arguments_given_as_json_text(self):
        self.assertEqual(self.one("shell", json.dumps({"command": ["bash", "-lc", "ls -la"]}))["text"], "$ bash -lc ls -la")

    def test_apply_patch(self):
        patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Add File: src/b.py\n+z\n*** End Patch"
        self.assertEqual(self.one("apply_patch", patch)["text"], "patched src/a.py, src/b.py")

    def test_codex_exec_program(self):
        code = ("const a = await tools.exec_command({cmd: \"git status --short\", yield_time_ms: 1000});\n"
                "await tools.apply_patch(`*** Begin Patch\n*** Update File: app.js\n@@\n-a\n+b\n*** End Patch`);\n"
                "text(a.output);")
        acts = parse.describe_tool("exec", code)
        self.assertEqual([a["text"] for a in acts], ["$ git status --short", "patched app.js"])
        self.assertEqual([a["kind"] for a in acts], ["command", "edit"])

    def test_codex_exec_without_tools(self):
        acts = parse.describe_tool("exec", "// @exec: {}\ntext(1 + 1);")
        self.assertEqual(acts[0]["text"], "ran code: text(1 + 1);")

    def test_unknown_tool(self):
        act = self.one("mcp__drive__search", {"q": "budget"})
        self.assertEqual(act["kind"], "other")
        self.assertIn("budget", act["text"])


class StreamTests(unittest.TestCase):
    def feed_split(self, reader, payload):
        for i in range(0, len(payload), 13):  # deliberately awkward chunk boundaries
            reader.feed(payload[i:i + 13])
        return reader.finish()

    def test_anthropic_stream(self):
        events = [
            ("message_start", {"type": "message_start", "message": {"model": "claude-opus-5-5", "content": [],
                                                                  "usage": {"input_tokens": 10, "cache_read_input_tokens": 500, "output_tokens": 1}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Running ünïcode "}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "t", "name": "Bash", "input": {}}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"comma'}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": 'nd": "ls"}'}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 1}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 77}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        payload = "".join(f"event: {n}\r\ndata: {json.dumps(d, ensure_ascii=False)}\r\n\r\n" for n, d in events).encode()
        final = self.feed_split(parse.StreamReader("messages"), payload)
        s = parse.summarize_response("messages", "anthropic", final)
        self.assertEqual(s["reply"], "Running ünïcode")
        self.assertEqual(s["actions"], [{"tool": "Bash", "kind": "command", "text": "$ ls"}])
        self.assertEqual(s["usage"]["output"], 77)
        self.assertEqual(s["usage"]["cache_read"], 500)
        self.assertEqual(s["stop"], "tool_use")

    def test_chat_stream(self):
        chunks = [
            {"model": "gpt-x", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "c", "function": {"name": "shell", "arguments": ""}}]}}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"command": "make'}}]}}]},
            {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": ' build"}'}}]}, "finish_reason": "tool_calls"}]},
            {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 9, "prompt_tokens_details": {"cached_tokens": 60}}},
        ]
        payload = ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
        final = self.feed_split(parse.StreamReader("chat"), payload)
        s = parse.summarize_response("chat", "openai", final)
        self.assertEqual(s["actions"][0]["text"], "$ make build")
        self.assertEqual((s["usage"]["input"], s["usage"]["cache_read"], s["usage"]["output"]), (40, 60, 9))

    def test_responses_stream_cut_before_completion(self):
        events = [
            ("response.created", {"type": "response.created", "response": {"model": "gpt-6-astra", "output": []}}),
            ("response.output_text.delta", {"type": "response.output_text.delta", "output_index": 0, "delta": "half an ans"}),
        ]
        payload = "".join(f"event: {n}\ndata: {json.dumps(d)}\n\n" for n, d in events).encode()
        final = self.feed_split(parse.StreamReader("responses"), payload)
        s = parse.summarize_response("responses", "openai", final)
        self.assertEqual(s["reply"], "half an ans")

    def test_sse_parser_keeps_partial_lines(self):
        p = parse.SSEParser()
        self.assertEqual(p.feed(b"event: a\ndata: {\"x\""), [])
        self.assertEqual(p.feed(b": 1}\n\n"), [("a", '{"x": 1}')])
        self.assertEqual(p.feed(b"data: tail"), [])
        self.assertEqual(p.close(), [(None, "tail")])

    def test_openai_usage_does_not_double_count_cache(self):
        u = parse.openai_usage({"input_tokens": 5000, "output_tokens": 300, "input_tokens_details": {"cached_tokens": 4000},
                                "output_tokens_details": {"reasoning_tokens": 120}})
        self.assertEqual((u["input"], u["cache_read"], u["output"], u["reasoning"]), (1000, 4000, 300, 120))


if __name__ == "__main__":
    unittest.main()
