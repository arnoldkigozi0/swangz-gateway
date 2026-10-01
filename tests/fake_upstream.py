"""A stand-in for api.anthropic.com and api.openai.com, speaking both dialects, streamed or not.

What it answers depends on the last thing the person said:
  "run <cmd>"   -> the model asks to run <cmd> with its Bash/shell tool
  "slow"        -> a stream that trickles for ~10 s (for cut/revoke tests)
  "fail"        -> HTTP 400 with an error body
  anything else -> a short text reply
Tool results coming back get a final text reply ("done").
Every request it sees is kept in .seen for assertions.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _last_user_text(body, kind):
    items = body.get("messages") if kind != "responses" else body.get("input")
    if isinstance(items, str):
        return items, False
    for item in reversed(items or []):
        content = item.get("content")
        if item.get("role") == "tool" or str(item.get("type", "")).endswith("_output"):
            return "", True
        if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return "", True
        if item.get("role") == "user":
            if isinstance(content, str):
                return content, False
            texts = [b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") in ("text", "input_text")]
            return texts[-1] if texts else "", False
    return "", False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(n)
        body = json.loads(raw) if raw else {}
        self.server.fake.seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
        path = self.path.split("?")[0]
        if path.endswith("/v1/messages/count_tokens"):
            return self._json(200, {"input_tokens": 42})
        kind = "messages" if path.endswith("/v1/messages") else "chat" if path.endswith("/chat/completions") else "responses" if path.endswith("/responses") else None
        if kind is None:
            return self._json(404, {"error": {"message": "unknown path"}})
        text, tool_turn = _last_user_text(body, kind)
        if text.startswith("fail"):
            if kind == "messages":
                return self._json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "fake failure"}})
            return self._json(400, {"error": {"message": "fake failure", "type": "invalid_request_error"}})
        command = text[4:].strip() if text.startswith("run ") and not tool_turn else None
        reply = "done" if tool_turn else ("hello from the fake model" if not command else None)
        slow = text.startswith("slow")
        model = body.get("model") or "fake-model"
        stream = bool(body.get("stream"))
        getattr(self, f"_{kind}")(model, stream, reply, command, slow, body)

    do_GET = do_POST

    # ------------------------------------------------------------ transport

    def _json(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _sse(self, events, slow=False):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()
        try:
            for i, (name, data) in enumerate(events):
                chunk = (f"event: {name}\n" if name else "") + "data: " + (data if isinstance(data, str) else json.dumps(data)) + "\n\n"
                raw = chunk.encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(raw), raw))
                self.wfile.flush()
                if slow:
                    time.sleep(0.25)
            self.wfile.write(b"0\r\n\r\n")
        except OSError:
            pass

    # ------------------------------------------------------------ dialects

    def _messages(self, model, stream, reply, command, slow, body):
        usage = {"input_tokens": 1000, "output_tokens": 50, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 3000}
        content = [{"type": "text", "text": reply}] if reply else [
            {"type": "text", "text": "I'll run it."},
            {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": command, "description": "run it"}}]
        stop = "end_turn" if reply else "tool_use"
        if not stream:
            return self._json(200, {"id": "msg_1", "type": "message", "role": "assistant", "model": model,
                                    "content": content, "stop_reason": stop, "usage": usage})
        events = [("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": model, "content": [],
            "usage": {**usage, "output_tokens": 1}}})]
        for i, block in enumerate(content):
            if block["type"] == "text":
                events.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}))
                pieces = [block["text"]] if not slow else [block["text"]] * 160
                for piece in pieces:
                    events.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": piece}}))
            else:
                events.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {
                    "type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}))
                js = json.dumps(block["input"])
                for j in range(0, len(js), 7):
                    events.append(("content_block_delta", {"type": "content_block_delta", "index": i,
                                                           "delta": {"type": "input_json_delta", "partial_json": js[j:j + 7]}}))
            events.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
        events.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 50}}))
        events.append(("message_stop", {"type": "message_stop"}))
        self._sse(events, slow)

    def _chat(self, model, stream, reply, command, slow, body):
        usage = {"prompt_tokens": 1200, "completion_tokens": 40, "prompt_tokens_details": {"cached_tokens": 1000}}
        call = {"id": "call_1", "type": "function", "function": {"name": "shell", "arguments": json.dumps({"command": ["bash", "-lc", command or ""]})}}
        if not stream:
            message = {"role": "assistant", "content": reply}
            if command:
                message["tool_calls"] = [call]
            return self._json(200, {"id": "chatcmpl-1", "model": model, "choices": [
                {"index": 0, "message": message, "finish_reason": "stop" if reply else "tool_calls"}], "usage": usage})
        events = []
        if reply:
            for piece in ([reply] if not slow else [reply] * 160):
                events.append((None, {"id": "chatcmpl-1", "model": model, "choices": [{"index": 0, "delta": {"content": piece}}]}))
        else:
            args = call["function"]["arguments"]
            events.append((None, {"id": "chatcmpl-1", "model": model, "choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "type": "function", "function": {"name": "shell", "arguments": ""}}]}}]}))
            for j in range(0, len(args), 5):
                events.append((None, {"id": "chatcmpl-1", "model": model, "choices": [{"index": 0, "delta": {"tool_calls": [
                    {"index": 0, "function": {"arguments": args[j:j + 5]}}]}}]}))
        events.append((None, {"id": "chatcmpl-1", "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop" if reply else "tool_calls"}]}))
        if (body.get("stream_options") or {}).get("include_usage"):
            events.append((None, {"id": "chatcmpl-1", "model": model, "choices": [], "usage": usage}))
        events.append((None, "[DONE]"))
        self._sse(events, slow)

    def _responses(self, model, stream, reply, command, slow, body):
        usage = {"input_tokens": 5000, "output_tokens": 300, "total_tokens": 5300, "input_tokens_details": {"cached_tokens": 4000},
                 "output_tokens_details": {"reasoning_tokens": 120}}
        if reply:
            item = {"type": "message", "id": "msg_1", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": reply, "annotations": []}]}
        else:
            code = "const r = await tools.exec_command({cmd: " + json.dumps(command) + "});\ntext(r.output);"
            item = {"type": "custom_tool_call", "id": "ctc_1", "call_id": "call_1", "name": "exec", "input": code, "status": "completed"}
        response = {"id": "resp_1", "object": "response", "model": model, "status": "completed", "output": [item], "usage": usage}
        if not stream:
            return self._json(200, response)
        events = [("response.created", {"type": "response.created", "response": {**response, "status": "in_progress", "output": [], "usage": None}})]
        events.append(("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": {**item, "status": "in_progress"}}))
        if reply:
            for piece in ([reply] if not slow else [reply] * 160):
                events.append(("response.output_text.delta", {"type": "response.output_text.delta", "output_index": 0, "content_index": 0, "delta": piece}))
        events.append(("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}))
        events.append(("response.completed", {"type": "response.completed", "response": response}))
        self._sse(events, slow)


class FakeUpstream:
    def __init__(self):
        self.seen = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.fake = self
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


if __name__ == "__main__":  # run standalone for manual tests: python3 tests/fake_upstream.py 18902
    import sys

    fake = FakeUpstream.__new__(FakeUpstream)
    fake.seen = []
    fake.server = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 18902), Handler)
    fake.server.fake = fake
    print("fake upstream on", fake.server.server_address)
    fake.server.serve_forever()
