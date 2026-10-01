"""Read what a person sent and what came back, in each provider's own dialect.

Everything here is pure: dicts and bytes in, plain dicts out. The proxy forwards bytes untouched;
this module only reads a copy, so a parsing gap can never break anyone's work — it can only leave
a summary thinner than it should be (and the full body is still kept).
"""

import json
import re

# Tags that coding tools wrap around context they inject into a "user" message. What is left
# after removing them is what the person actually typed.
_INJECTED = re.compile(
    r"<(system-reminder|environment_context|user_instructions|INSTRUCTIONS|skills_instructions)>.*?</\1>",
    re.S,
)

SECRET_PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-)?[A-Za-z0-9_\-]{32,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("Private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Gateway key", re.compile(r"\bsgw_[0-9a-f]{12}_[A-Za-z0-9_\-]{20,}")),
]

MAX_TEXT = 4000
MAX_ACTION = 400


# ---------------------------------------------------------------- what kind of call is this


def endpoint_kind(dialect, path, method="POST"):
    """'messages' | 'chat' | 'responses' for chat models; 'media' for a voice/image/video job;
    'media-status' for polling a job; 'other' for everything else."""
    p = path.split("?", 1)[0].rstrip("/")
    if dialect in ("elevenlabs", "higgsfield", "media"):
        if method == "POST" and not re.search(r"/requests/[^/]+/cancel$", p):
            return "media"
        if dialect == "higgsfield" and re.search(r"/requests/[^/]+/status$", p):
            return "media-status"
        if dialect == "media" and method == "GET":
            return "media-status"
        return "other"
    if dialect == "anthropic":
        return "messages" if p.endswith("/v1/messages") else "other"
    if p.endswith("/chat/completions"):
        return "chat"
    if p.endswith("/responses"):
        return "responses"
    return "other"


def list_field(kind, body):
    """Which top-level field holds the growing conversation (stored message by message)."""
    if kind in ("messages", "chat") and isinstance(body.get("messages"), list):
        return "messages"
    if kind == "responses" and isinstance(body.get("input"), list):
        return "input"
    return None


def _header(headers, name):
    """Header lookup that ignores case, for real header objects and plain dicts alike."""
    value = headers.get(name)
    if value is None and isinstance(headers, dict):
        for k, v in headers.items():
            if k.lower() == name:
                return v
    return value


def client_name(headers):
    ua = _header(headers, "user-agent") or ""
    low = ua.lower()
    if low.startswith("claude-cli") or "claude-code" in low:
        return "Claude Code"
    if "claude-agent-sdk" in low:
        return "Claude Agent SDK"
    if low.startswith("codex") or "codex_" in low or (_header(headers, "originator") or "").startswith("codex"):
        return "Codex"
    if "cursor" in low:
        return "Cursor"
    if "opencode" in low:
        return "OpenCode"
    if "aider" in low:
        return "Aider"
    if low.startswith("anthropic/"):
        return "Anthropic SDK"
    if "elevenlabs" in low:
        return "ElevenLabs SDK"
    if "higgsfield" in low:
        return "Higgsfield SDK"
    if low.startswith("openai/") or "openai-python" in low or "openai-node" in low:
        return "OpenAI SDK"
    if low.startswith("curl/"):
        return "curl"
    if low.startswith("mozilla/"):
        return "Browser"
    return ua.split("/", 1)[0][:40] if ua else "unknown"


def session_of(headers, body):
    for name in ("x-claude-code-session-id", "session-id", "session_id", "thread-id", "x-session-id"):
        value = _header(headers, name)
        if value:
            return value.strip()[:120]
    if isinstance(body, dict):
        meta = body.get("metadata")
        if isinstance(meta, dict):
            uid = meta.get("user_id")
            if isinstance(uid, str):
                m = re.search(r'"session_id"\s*:\s*"([^"]+)"', uid) or re.search(r"session_([0-9a-f\-]{36})", uid)
                if m:
                    return m.group(1)
        cm = body.get("client_metadata")
        if isinstance(cm, dict) and isinstance(cm.get("session_id"), str):
            return cm["session_id"][:120]
        if isinstance(body.get("prompt_cache_key"), str):
            return body["prompt_cache_key"][:120]
    return None


def request_meta(headers, body):
    """What the tool says about this request: its class, the agent inside the tool, the prompt it serves.

    Claude Code sends x-claude-code-agent-id on sub-agent requests always, and the request class and
    prompt id when CLAUDE_CODE_GATEWAY_HINT_HEADERS=1 is set (the setup snippet sets it). Codex sends a
    turn-metadata JSON header on every request.
    -> {request_class, agent, turn_id}
    """
    meta = {"request_class": None, "agent": None, "turn_id": None}
    rclass = _header(headers, "x-claude-code-request-class")
    agent_id = _header(headers, "x-claude-code-agent-id")
    agent_type = _header(headers, "x-claude-code-agent-type")
    if rclass:
        meta["request_class"] = rclass.strip()[:40]
    if agent_id or agent_type:
        meta["agent"] = ((agent_type or "sub-agent").strip() + (":" + agent_id.strip() if agent_id else ""))[:120]
    if _header(headers, "x-claude-code-compaction"):
        meta["request_class"] = "compaction"
    prompt_id = _header(headers, "x-claude-code-prompt-id")
    if prompt_id:
        meta["turn_id"] = prompt_id.strip()[:80]

    raw = _header(headers, "x-codex-turn-metadata")
    if not raw and isinstance(body, dict) and isinstance(body.get("client_metadata"), dict):
        raw = body["client_metadata"].get("x-codex-turn-metadata")
    if raw:
        try:
            codex = json.loads(raw)
        except (TypeError, ValueError):
            codex = None
        if isinstance(codex, dict):
            name = codex.get("agent_name")
            if isinstance(name, str) and name and name != "/root":
                meta["agent"] = ("sub-agent:" + name)[:120]
            kind = codex.get("request_kind")
            if isinstance(kind, str) and kind:
                meta["request_class"] = ("subagent" if meta["agent"] else "main") if kind == "turn" else kind[:40]
            turn = codex.get("root_turn_id") or codex.get("turn_id")
            if isinstance(turn, str):
                meta["turn_id"] = turn[:80]
    return meta


# ---------------------------------------------------------------- what the person asked


def human_text(content):
    """The words a person typed in one message, without the context their tool wrapped around it."""
    parts = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("text", "input_text") and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
    text = _INJECTED.sub("", "\n".join(parts))
    if text.lstrip().startswith("# AGENTS.md instructions"):
        return ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _attachments(content):
    n = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("image", "document", "input_image", "input_file", "image_url", "file"):
                n += 1
    return n


def _is_person_turn(item):
    """A message from the person (or a system/developer note between turns)."""
    if not isinstance(item, dict):
        return False
    role = item.get("role")
    kind = item.get("type", "message")
    return kind == "message" and role in ("user", "system", "developer")


def summarize_request(kind, body):
    """-> {model, stream, prompt, attachments, tail}

    `prompt` is what the person typed since the model last spoke — None when this request only
    carries tool results back (the agent working on its own). `tail` is everything new since the
    model last spoke, used for the secret scan.
    """
    out = {"model": None, "stream": False, "prompt": None, "attachments": 0, "tail": []}
    if not isinstance(body, dict):
        return out
    out["model"] = body.get("model") if isinstance(body.get("model"), str) else None
    out["stream"] = bool(body.get("stream"))
    if kind in ("messages", "chat"):
        items = body.get("messages") if isinstance(body.get("messages"), list) else []
    elif kind == "responses":
        raw = body.get("input")
        if isinstance(raw, str):
            out["prompt"] = _clip(raw.strip()) or None
            out["tail"] = [raw]
            return out
        items = raw if isinstance(raw, list) else []
    else:
        return out

    tail, texts, attachments = [], [], 0
    for item in reversed(items):
        if not isinstance(item, dict):
            break
        role = item.get("role")
        is_user_side = (
            role in ("user", "system", "developer", "tool")
            if kind != "responses"
            else (_is_person_turn(item) or item.get("type", "").endswith("_output"))
        )
        if not is_user_side:
            break
        tail.append(item)
        if role == "user" and (kind != "responses" or item.get("type", "message") == "message"):
            text = human_text(item.get("content"))
            if text:
                texts.append(text)
            attachments += _attachments(item.get("content"))
    texts.reverse()
    tail.reverse()
    out["prompt"] = _clip("\n\n".join(texts)) or None
    out["attachments"] = attachments
    out["tail"] = tail
    return out


def find_secrets(obj):
    """Names of credential formats that appear anywhere in obj."""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return sorted({name for name, rx in SECRET_PATTERNS if rx.search(text)})


# ---------------------------------------------------------------- what the model did


def summarize_response(kind, dialect, resp):
    """-> {model, reply, actions, stop, usage} from a final response object (streamed or not)."""
    out = {"model": None, "reply": "", "actions": [], "stop": None, "usage": empty_usage(), "error": None}
    if not isinstance(resp, dict):
        return out
    if isinstance(resp.get("error"), dict):
        out["error"] = resp["error"].get("message") or resp["error"].get("type")
    if kind == "messages":
        out["model"] = resp.get("model")
        out["stop"] = resp.get("stop_reason")
        texts = []
        for block in resp.get("content") or []:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                texts.append(block.get("text") or "")
            elif t in ("tool_use", "server_tool_use", "mcp_tool_use"):
                out["actions"] += describe_tool(block.get("name"), block.get("input"))
        out["reply"] = _clip("\n\n".join(x for x in texts if x).strip())
        out["usage"] = anthropic_usage(resp.get("usage"))
    elif kind == "chat":
        out["model"] = resp.get("model")
        choice = (resp.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        out["stop"] = choice.get("finish_reason")
        content = msg.get("content")
        if isinstance(content, list):
            content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
        out["reply"] = _clip((content or "").strip())
        for call in msg.get("tool_calls") or []:
            fn = (call or {}).get("function") or {}
            out["actions"] += describe_tool(fn.get("name"), fn.get("arguments"))
        out["usage"] = openai_usage(resp.get("usage"))
    elif kind == "responses":
        out["model"] = resp.get("model")
        out["stop"] = resp.get("status")
        texts = []
        for item in resp.get("output") or []:
            if not isinstance(item, dict):
                continue
            t = item.get("type")
            if t == "message":
                for part in item.get("content") or []:
                    if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                        texts.append(part.get("text") or "")
            elif t == "function_call":
                out["actions"] += describe_tool(item.get("name"), item.get("arguments"))
            elif t == "custom_tool_call":
                out["actions"] += describe_tool(item.get("name"), item.get("input"))
            elif t == "local_shell_call":
                action = item.get("action") or {}
                out["actions"] += describe_tool("shell", {"command": action.get("command")})
            elif t == "web_search_call":
                out["actions"] += describe_tool("web_search", item.get("action") or {})
            elif t in ("reasoning",):
                continue
            elif t:
                out["actions"].append({"tool": t, "kind": "other", "text": _short(t)})
        out["reply"] = _clip("\n\n".join(x for x in texts if x).strip())
        out["usage"] = openai_usage(resp.get("usage"))
    elif isinstance(resp.get("usage"), dict):
        out["usage"] = anthropic_usage(resp["usage"]) if dialect == "anthropic" else openai_usage(resp["usage"])
    return out


def empty_usage():
    return {"input": 0, "output": 0, "cache_write": 0, "cache_write_1h": 0, "cache_read": 0, "reasoning": 0, "speed": None}


def anthropic_usage(u):
    usage = empty_usage()
    if not isinstance(u, dict):
        return usage
    usage["input"] = _int(u.get("input_tokens"))
    usage["output"] = _int(u.get("output_tokens"))
    usage["cache_read"] = _int(u.get("cache_read_input_tokens"))
    total_write = _int(u.get("cache_creation_input_tokens"))
    split = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
    w5, w1h = _int(split.get("ephemeral_5m_input_tokens")), _int(split.get("ephemeral_1h_input_tokens"))
    if w5 + w1h == 0:
        w5 = total_write
    usage["cache_write"], usage["cache_write_1h"] = w5, w1h
    usage["speed"] = u.get("speed")
    return usage


def openai_usage(u):
    """OpenAI counts cached tokens inside the input total; split them out so both dialects mean the same."""
    usage = empty_usage()
    if not isinstance(u, dict):
        return usage
    total_in = _int(u.get("input_tokens", u.get("prompt_tokens")))
    details_in = u.get("input_tokens_details") or u.get("prompt_tokens_details") or {}
    details_out = u.get("output_tokens_details") or u.get("completion_tokens_details") or {}
    cached = _int(details_in.get("cached_tokens")) if isinstance(details_in, dict) else 0
    usage["input"] = max(total_in - cached, 0)
    usage["cache_read"] = cached
    usage["output"] = _int(u.get("output_tokens", u.get("completion_tokens")))
    usage["reasoning"] = _int(details_out.get("reasoning_tokens")) if isinstance(details_out, dict) else 0
    return usage


# ---------------------------------------------------------------- one tool call, in plain words

_EDIT_VERBS = {"write": "wrote", "edit": "edited", "multiedit": "edited", "notebookedit": "edited notebook",
               "create_file": "created", "str_replace_based_edit_tool": "edited"}


def describe_tool(name, raw_input):
    """-> list of {tool, kind, text}. kind is command | edit | read | web | agent | other."""
    name = name or "tool"
    inp = raw_input
    if isinstance(inp, str):
        stripped = inp.strip()
        if stripped.startswith("{"):
            try:
                inp = json.loads(stripped)
            except ValueError:
                pass
    low = name.lower()
    d = inp if isinstance(inp, dict) else {}

    def first(*keys):
        for k in keys:
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                return " ".join(v)
        return ""

    if low in ("bash", "shell", "exec_command", "local_shell", "run_command", "terminal", "powershell", "container.exec"):
        return [_act(name, "command", "$ " + (first("command", "cmd") or _short(inp)))]
    if low == "exec" and isinstance(inp, str):
        return _codex_exec(name, inp)
    if low == "apply_patch":
        patch = inp if isinstance(inp, str) else first("input", "patch")
        files = _patch_files(patch)
        return [_act(name, "edit", "patched " + (", ".join(files) if files else "files"))]
    if low in _EDIT_VERBS:
        return [_act(name, "edit", f"{_EDIT_VERBS[low]} {first('file_path', 'path', 'notebook_path') or '?'}")]
    if low in ("read", "view", "view_image", "read_file"):
        return [_act(name, "read", "read " + (first("file_path", "path") or "?"))]
    if low in ("glob", "grep", "ls", "list_dir", "search", "find"):
        where = first("path")
        return [_act(name, "read", f"searched {first('pattern', 'query') or '?'}" + (f" in {where}" if where else ""))]
    if low in ("webfetch", "web_fetch", "fetch"):
        return [_act(name, "web", "fetched " + (first("url") or "?"))]
    if low in ("websearch", "web_search"):
        return [_act(name, "web", "searched the web: " + (first("query", "q") or _short(inp)))]
    if low in ("agent", "task", "spawn_agent"):
        return [_act(name, "agent", "started a sub-agent: " + (first("description", "prompt", "task", "message") or "?"))]
    if low in ("todowrite", "update_plan"):
        return [_act(name, "other", "updated the plan")]
    return [_act(name, "other", f"{name} {_short(inp)}".strip())]


def _codex_exec(name, code):
    """Codex runs its tools from a small JavaScript program; read the tool calls out of it."""
    actions = []
    for m in re.finditer(r"tools\.(\w+)\s*\(", code):
        tool = m.group(1)
        window = code[m.end(): m.end() + 2000]
        if tool in ("exec_command", "shell", "run_command"):
            cmd = re.search(r"""\b(?:cmd|command)\s*:\s*(["'`])((?:\\.|(?!\1).)*)\1""", window, re.S)
            if not cmd:
                cmd = re.search(r"""^\s*(["'`])((?:\\.|(?!\1).)*)\1""", window, re.S)
            text = "$ " + (_unescape(cmd.group(2)) if cmd else "(command)")
            actions.append(_act(tool, "command", text))
        elif tool == "apply_patch":
            files = _patch_files(window)
            actions.append(_act(tool, "edit", "patched " + (", ".join(files) if files else "files")))
        elif tool in ("view_image", "read_file"):
            actions.append(_act(tool, "read", "read a file"))
        elif tool in ("web_search", "web_fetch"):
            actions.append(_act(tool, "web", tool.replace("_", " ")))
        else:
            actions.append(_act(tool, "other", tool))
    if not actions:
        first_line = next((ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("//")), "")
        actions.append(_act(name, "other", "ran code: " + first_line))
    return actions


def _patch_files(patch):
    if not isinstance(patch, str):
        return []
    files = re.findall(r"\*\*\* (?:Update|Add|Delete) File: ([^\n\\]+)", patch)
    seen = []
    for f in files:
        f = f.strip()
        if f not in seen:
            seen.append(f)
    return seen


def _unescape(s):
    try:
        return json.loads('"' + s.replace('"', '\\"') + '"')
    except ValueError:
        return s


def _act(tool, kind, text):
    return {"tool": tool, "kind": kind, "text": _clip(" ".join(text.split()), MAX_ACTION)}


def _short(obj, limit=160):
    if obj is None:
        return ""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _clip(text, limit=MAX_TEXT):
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- streams


class SSEParser:
    """Server-sent events, fed in arbitrary byte chunks."""

    def __init__(self):
        self.buf = b""
        self.event = None
        self.data = []

    def feed(self, chunk):
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        out = []
        for line in lines:
            self._line(line.rstrip(b"\r"), out)
        return out

    def close(self):
        out = []
        if self.buf:
            self._line(self.buf.rstrip(b"\r"), out)
            self.buf = b""
        self._line(b"", out)
        return out

    def _line(self, line, out):
        if not line:
            if self.data or self.event:
                out.append((self.event, "\n".join(self.data)))
            self.event, self.data = None, []
            return
        if line.startswith(b":"):
            return
        name, _, value = line.partition(b":")
        if value.startswith(b" "):
            value = value[1:]
        name = name.decode("utf-8", "replace")
        if name == "event":
            self.event = value.decode("utf-8", "replace")
        elif name == "data":
            self.data.append(value.decode("utf-8", "replace"))


class StreamReader:
    """Rebuilds the final response object from a stream, as if it had not been streamed."""

    def __init__(self, kind):
        self.kind = kind
        self.sse = SSEParser()
        self.error = None
        self.events = 0
        # messages
        self.message = None
        self.blocks = {}
        self.partial = {}
        # chat
        self.chat = {"model": None, "content": [], "tools": {}, "finish": None, "usage": None, "id": None}
        # responses
        self.response = None
        self.items = {}
        self.item_text = {}

    def feed(self, chunk):
        for name, data in self.sse.feed(chunk):
            self._event(name, data)

    def finish(self):
        for name, data in self.sse.close():
            self._event(name, data)
        return self.result()

    def _event(self, name, data):
        self.events += 1
        if data.strip() == "[DONE]":
            return
        try:
            d = json.loads(data)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        if self.kind == "messages":
            self._anthropic(name, d)
        elif self.kind == "chat":
            self._chat(d)
        elif self.kind == "responses":
            self._responses(name, d)

    def _anthropic(self, name, d):
        t = d.get("type") or name
        if t == "message_start":
            self.message = dict(d.get("message") or {})
            self.message["usage"] = dict(self.message.get("usage") or {})
        elif t == "content_block_start":
            self.blocks[d.get("index", len(self.blocks))] = dict(d.get("content_block") or {})
        elif t == "content_block_delta":
            idx = d.get("index", 0)
            block = self.blocks.setdefault(idx, {})
            delta = d.get("delta") or {}
            dt = delta.get("type")
            if dt == "text_delta":
                block["text"] = block.get("text", "") + (delta.get("text") or "")
            elif dt == "input_json_delta":
                self.partial[idx] = self.partial.get(idx, "") + (delta.get("partial_json") or "")
            elif dt == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + (delta.get("thinking") or "")
        elif t == "content_block_stop":
            self._close_block(d.get("index", 0))
        elif t == "message_delta":
            if self.message is None:
                self.message = {"usage": {}}
            delta = d.get("delta") or {}
            for k in ("stop_reason", "stop_sequence", "stop_details"):
                if delta.get(k) is not None:
                    self.message[k] = delta[k]
            for k, v in (d.get("usage") or {}).items():
                if v is not None:
                    self.message["usage"][k] = v
        elif t == "error":
            self.error = d.get("error") or d

    def _close_block(self, idx):
        if idx in self.partial:
            raw = self.partial.pop(idx)
            block = self.blocks.setdefault(idx, {})
            if raw.strip():
                try:
                    block["input"] = json.loads(raw)
                except ValueError:
                    block["input"] = raw

    def _chat(self, d):
        if d.get("error"):
            self.error = d["error"]
        self.chat["model"] = d.get("model") or self.chat["model"]
        self.chat["id"] = d.get("id") or self.chat["id"]
        for choice in d.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                self.chat["content"].append(delta["content"])
            for call in delta.get("tool_calls") or []:
                entry = self.chat["tools"].setdefault(call.get("index", 0), {"id": None, "name": "", "arguments": ""})
                entry["id"] = call.get("id") or entry["id"]
                fn = call.get("function") or {}
                if fn.get("name"):
                    entry["name"] += fn["name"]
                if fn.get("arguments"):
                    entry["arguments"] += fn["arguments"]
            if choice.get("finish_reason"):
                self.chat["finish"] = choice["finish_reason"]
        if d.get("usage"):
            self.chat["usage"] = d["usage"]

    def _responses(self, name, d):
        t = d.get("type") or name
        if t in ("response.created", "response.in_progress", "response.completed", "response.incomplete", "response.failed"):
            if isinstance(d.get("response"), dict):
                self.response = d["response"]
        elif t == "response.output_item.added":
            self.items.setdefault(d.get("output_index", len(self.items)), d.get("item") or {})
        elif t == "response.output_item.done":
            self.items[d.get("output_index", len(self.items))] = d.get("item") or {}
        elif t == "response.output_text.delta":
            idx = d.get("output_index", 0)
            self.item_text[idx] = self.item_text.get(idx, "") + (d.get("delta") or "")
        elif t == "error":
            self.error = d.get("error") or d
        if t == "response.failed" and isinstance(self.response, dict) and self.response.get("error"):
            self.error = self.response["error"]

    def result(self):
        if self.kind == "messages":
            msg = dict(self.message or {})
            for idx in list(self.partial):
                self._close_block(idx)
            msg["content"] = [self.blocks[i] for i in sorted(self.blocks)]
            if self.error:
                msg["error"] = self.error
            return msg
        if self.kind == "chat":
            message = {"role": "assistant", "content": "".join(self.chat["content"])}
            if self.chat["tools"]:
                message["tool_calls"] = [
                    {"id": e["id"], "type": "function", "function": {"name": e["name"], "arguments": e["arguments"]}}
                    for _, e in sorted(self.chat["tools"].items())
                ]
            out = {"id": self.chat["id"], "model": self.chat["model"],
                   "choices": [{"index": 0, "message": message, "finish_reason": self.chat["finish"]}],
                   "usage": self.chat["usage"]}
            if self.error:
                out["error"] = self.error
            return out
        if self.kind == "responses":
            r = dict(self.response or {})
            if not r.get("output"):
                output = []
                for idx in sorted(set(self.items) | set(self.item_text)):
                    item = dict(self.items.get(idx) or {})
                    if idx in self.item_text and not item.get("content"):
                        item.setdefault("type", "message")
                        item["content"] = [{"type": "output_text", "text": self.item_text[idx]}]
                    output.append(item)
                r["output"] = output
            if self.error:
                r["error"] = self.error
            return r
        return {}


# ---------------------------------------------------------------- voice, image and video services

_PROMPT_KEYS = ("text", "prompt", "promptText", "prompt_text", "description", "lyrics")


def _find_prompt(body):
    if not isinstance(body, dict):
        return None
    for key in _PROMPT_KEYS:
        if isinstance(body.get(key), str) and body[key].strip():
            return body[key].strip()
    for nest in ("input", "params", "inputs"):
        inner = body.get(nest)
        if isinstance(inner, dict):
            found = _find_prompt(inner)
            if found:
                return found
    if isinstance(body.get("inputs"), list):  # ElevenLabs text-to-dialogue
        lines = [i.get("text") for i in body["inputs"] if isinstance(i, dict) and isinstance(i.get("text"), str)]
        if lines:
            return "\n".join(lines)
    return None


def media_type(dialect, path):
    p = path.split("?", 1)[0].lower()
    if dialect == "elevenlabs":
        if "speech-to-text" in p:
            return "transcription"
        if "sound-generation" in p:
            return "sound"
        if "music" in p:
            return "music"
        return "voice"
    if "video" in p or "image2video" in p or "/dop" in p or "kling" in p or "veo" in p or "seedance" in p:
        return "video"
    if "image" in p or "soul" in p or "flux" in p:
        return "image"
    if "speech" in p or "audio" in p or "voice" in p:
        return "voice"
    if "music" in p:
        return "music"
    return "generation"


def summarize_media_request(dialect, path, body, content_type=""):
    """-> {model, prompt, media_type, units, unit, action} for a voice/image/video request."""
    p = path.split("?", 1)[0]
    mtype = media_type(dialect, p)
    model = None
    detail = ""
    if isinstance(body, dict):
        model = body.get("model_id") or body.get("model")
        if not isinstance(model, str):
            model = None
    if dialect == "higgsfield" or (dialect == "media" and not model):
        endpoint = p.strip("/")
        model = f"{endpoint}" + (f" · {body['model']}" if isinstance(body, dict) and isinstance(body.get("model"), str) else "")
    voice = re.search(r"/(?:text-to-speech|speech-to-speech)/([^/]+)", p)
    if voice:
        detail = f" · voice {voice.group(1)}"
    prompt = _find_prompt(body)
    if prompt is None and "multipart/" in (content_type or ""):
        prompt = None
        detail += " · uploaded a file"
    units, unit = 1, "request"
    if dialect == "elevenlabs" and mtype == "voice" and prompt:
        units, unit = len(prompt), "characters"
    elif mtype in ("image", "video"):
        count = 1
        if isinstance(body, dict):
            for k in ("num_images", "batch_size", "num_outputs"):
                if isinstance(body.get(k), int):
                    count = body[k]
        units, unit = count, mtype + ("s" if count != 1 else "")
    noun = {"voice": "voice-over", "sound": "sound effect", "music": "music", "transcription": "transcription",
            "image": "image", "video": "video"}.get(mtype, "generation")
    if isinstance(body, dict) and isinstance(body.get("aspect_ratio"), str):
        detail += f" · {body['aspect_ratio']}"
    text = noun + detail + (f" · {units} {unit}" if unit == "characters" else "")
    return {"model": model[:120] if model else None, "prompt": _clip(prompt) if prompt else None, "media_type": mtype,
            "units": units, "unit": unit,
            "action": {"tool": dialect, "kind": mtype if mtype in ("voice", "image", "video") else "media", "text": text}}


def _urls(d):
    found = []

    def add(u):
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in found:
            found.append(u)

    if not isinstance(d, dict):
        return found
    for img in d.get("images") or []:
        add(img.get("url") if isinstance(img, dict) else img)
    for key in ("video", "audio", "image", "result"):
        v = d.get(key)
        add(v.get("url") if isinstance(v, dict) else v)
    for key in ("url", "audio_url", "video_url", "image_url", "output_url"):
        add(d.get(key))
    out = d.get("output")
    if isinstance(out, str):
        add(out)
    elif isinstance(out, list):
        for o in out:
            add(o.get("url") if isinstance(o, dict) else o)
    for job in d.get("jobs") or []:
        if isinstance(job, dict):
            raw = ((job.get("results") or {}).get("raw") or {})
            add(raw.get("url"))
    return found[:20]


def summarize_media_response(content_type, final, size):
    """-> {status, job_id, urls, reply} from a voice/image/video response (JSON, or audio bytes)."""
    ctype = (content_type or "").lower()
    if final is None:
        kind = ctype.split(";")[0] or "binary"
        return {"status": None, "job_id": None, "urls": [], "reply": f"{kind} · {size / 1024:.0f} KB" if size else None}
    if not isinstance(final, dict):
        return {"status": None, "job_id": None, "urls": [], "reply": None}
    status = final.get("status") if isinstance(final.get("status"), str) else None
    job = final.get("request_id") or final.get("id")
    urls = _urls(final)
    reply = None
    if isinstance(final.get("text"), str):  # a transcription
        reply = _clip(final["text"])
    elif urls:
        reply = (f"{status} · " if status else "") + f"{len(urls)} result{'s' if len(urls) != 1 else ''}"
    elif status:
        reply = status
    err = final.get("detail") or final.get("error")
    if isinstance(err, dict):
        err = err.get("message") or err.get("status")
    return {"status": status, "job_id": job if isinstance(job, str) else None, "urls": urls, "reply": reply,
            "error": err if isinstance(err, str) else None}
