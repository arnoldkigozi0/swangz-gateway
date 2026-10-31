"""Pointing Claude Code and Codex at the company gateway.

Two modes, chosen by the server from what the person said about the device when they approved it:

  * scoped (a personal device): nothing outside the Swangz folder is written. `swangz run claude|codex`
    sets what is needed for that one command, so the person's own use of those tools is untouched.
  * managed (a company device): the tool's own settings are pointed at the gateway for good, so plain
    `claude` and `codex` are governed and recorded. What we add is marked, a copy of the original is kept
    once, and removing it later leaves anything the person changed since.

The key is never put in a file we did not already own: Claude Code's settings (a managed device) hold it as
its own docs describe, Codex reads it from the environment, which on Unix is read from our 0600 key file.
"""

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

BEGIN = "# >>> swangz (managed by the Swangz app; removed when you sign out) >>>"
END = "# <<< swangz <<<"
CLAUDE_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_GATEWAY_HINT_HEADERS")


class AgentConfigError(Exception):
    """A tool's settings are in a state we won't guess about. Nothing was changed."""


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def write_atomic(path, text, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".swangz-tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if private and os.name == "posix":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def keep_original(paths, source, name):
    """Copy a settings file aside once, before the first time we touch it."""
    dest = Path(paths.data) / "backups" / name
    if Path(source).exists() and not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


# ---------------------------------------------------------------- marked blocks in text files


def with_block(text, block, at_start=False):
    """`text` with our marked block replaced, or added: at the start for TOML (top-level keys must come before
    any table), at the end elsewhere. `without_block` takes back exactly what this added."""
    marked = f"{BEGIN}\n{block.rstrip()}\n{END}\n"
    text = without_block(text)
    if at_start:
        return marked + ("\n" + text if text else "")
    if not text:
        return marked
    return text + "\n" + marked


def without_block(text):
    if BEGIN not in text:
        return text
    text = re.sub(r"(?s)\A" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n\n?", "", text, count=1)  # added at the start
    return re.sub(r"(?s)\n" + re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n", "", text, count=1)  # added at the end


def has_block(text):
    return BEGIN in text and END in text


# ---------------------------------------------------------------- Claude Code


def claude_settings(paths):
    return Path(paths.home) / ".claude" / "settings.json"


def install_claude(paths, base_url, key, mode):
    """-> the record to remember. A managed device gets its settings file's "env" block pointed at the gateway."""
    if mode != "managed":
        return {"mode": "scoped", "base_url": base_url, "detail": "Run it with: swangz run claude"}
    path = claude_settings(paths)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError:
            raise AgentConfigError(f"{path} isn't valid JSON, so the Swangz app left it alone. Fix or remove it, then sync again.")
        if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
            raise AgentConfigError(f"{path} has an unexpected shape, so the Swangz app left it alone.")
    keep_original(paths, path, "claude-settings.json.orig")
    env = data.setdefault("env", {})
    wrote = {"ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_AUTH_TOKEN": key, "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1"}
    env.update(wrote)
    write_atomic(path, json.dumps(data, indent=2) + "\n", private=True)
    return {"mode": "managed", "base_url": base_url, "file": str(path), "wrote": {k: digest(v) for k, v in wrote.items()},
            "detail": "Claude Code now goes through the company gateway."}


def remove_claude(paths, record):
    path = Path(record.get("file") or "")
    if record.get("mode") != "managed" or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except ValueError:
        return  # theirs now; not ours to repair
    env = data.get("env")
    if not isinstance(env, dict):
        return
    for name, fingerprint in (record.get("wrote") or {}).items():
        if name in env and digest(str(env[name])) == fingerprint:  # only what we wrote, and only if still ours
            del env[name]
    if not env:
        data.pop("env", None)
    write_atomic(path, json.dumps(data, indent=2) + "\n", private=True)


# ---------------------------------------------------------------- Codex


def codex_config(paths):
    return Path(paths.home) / ".codex" / "config.toml"


def codex_block(base_url):
    return ('model_provider = "swangz"\n\n[model_providers.swangz]\nname = "Swangz AI Hub"\n'
            f'base_url = "{base_url}"\nenv_key = "SWANGZ_AI_KEY"\nwire_api = "responses"')


def codex_overrides(base_url):
    """The same settings as command-line overrides, for a scoped run that writes nothing."""
    pairs = ['model_provider="swangz"', 'model_providers.swangz.name="Swangz AI Hub"',
             f'model_providers.swangz.base_url="{base_url}"', 'model_providers.swangz.env_key="SWANGZ_AI_KEY"',
             'model_providers.swangz.wire_api="responses"']
    return [x for pair in pairs for x in ("-c", pair)]


def install_codex(paths, base_url, key, mode):
    if mode != "managed":
        return {"mode": "scoped", "base_url": base_url, "detail": "Run it with: swangz run codex"}
    path = codex_config(paths)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    outside = without_block(text)
    if re.search(r"(?m)^\s*model_provider\s*=", outside) or re.search(r"(?m)^\s*\[model_providers\.swangz\]", outside):
        raise AgentConfigError(f"{path} already chooses a provider of its own, so the Swangz app left it alone. "
                               "Remove that, or use `swangz run codex` instead.")
    keep_original(paths, path, "codex-config.toml.orig")
    write_atomic(path, with_block(text, codex_block(base_url), at_start=True))
    persisted = persist_env(paths, "SWANGZ_AI_KEY", key)
    return {"mode": "managed", "base_url": base_url, "file": str(path), "env": persisted,
            "detail": "Codex now goes through the company gateway. Open a new terminal for it to take effect."}


def remove_codex(paths, record):
    path = Path(record.get("file") or "")
    if record.get("mode") != "managed":
        return
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if has_block(text):
            write_atomic(path, without_block(text))
    forget_env(paths, "SWANGZ_AI_KEY", record.get("env"))


# ---------------------------------------------------------------- an environment variable that survives a restart


def profiles(paths):
    home = Path(paths.home)
    out = [home / ".profile"]
    if sys.platform == "darwin" or "zsh" in os.environ.get("SHELL", ""):
        out.append(home / ".zprofile")
    return out


def persist_env(paths, name, value, run=subprocess.run):
    """Windows: the user's own environment (setx). Elsewhere: a marked line in the login profile that reads the
    key from our private key file, so the key itself is not copied into a new place."""
    if sys.platform == "win32":
        run(["setx", name, value], capture_output=True, check=False)
        return {"kind": "windows-user-env"}
    line = f'export {name}="$(cat {shlex.quote(str(Path(paths.data) / "device.key"))} 2>/dev/null)"'
    done = []
    for profile in profiles(paths):
        text = profile.read_text(encoding="utf-8") if profile.exists() else ""
        write_atomic(profile, with_block(text, line))
        done.append(str(profile))
    return {"kind": "profile", "files": done}


def forget_env(paths, name, record, run=subprocess.run):
    record = record or {}
    if record.get("kind") == "windows-user-env":
        run(["reg", "delete", r"HKCU\Environment", "/v", name, "/f"], capture_output=True, check=False)
    for f in record.get("files") or []:
        profile = Path(f)
        if profile.exists():
            text = profile.read_text(encoding="utf-8")
            if has_block(text):
                write_atomic(profile, without_block(text))
