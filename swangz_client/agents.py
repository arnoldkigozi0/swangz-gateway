"""Pointing Claude Code and Codex at the company gateway.

Two modes, chosen by the server from what the person said about the device when they approved it:

  * scoped (a personal device): nothing outside the Swangz folder is written. `swangz run claude|codex`
    sets what is needed for that one command, so the person's own use of those tools is untouched.
  * managed (a company device): the tool's own settings are pointed at the gateway for good, so plain
    `claude` and `codex` are governed and recorded. What we add is marked, a copy of the original is kept
    once, and removing it later leaves anything the person changed since.

Managed configuration contains helper commands, never a credential. Scoped execution uses child environments.
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

from . import keystore, shell

BEGIN = "# >>> swangz (managed by the Swangz app; removed when you sign out) >>>"
END = "# <<< swangz <<<"
CLAUDE_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_GATEWAY_HINT_HEADERS")
# Enable only after the deployed Claude CLI preserves /anthropic against the fake gateway.
# Official helper documentation and SDK concatenation alone do not prove that CLI behavior.
CLAUDE_PREFIX_VERIFIED = False


class AgentConfigError(Exception):
    """A tool's settings are in a state we won't guess about. Nothing was changed."""


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def write_atomic(path, text, private=False):
    if private:
        return keystore.write_private(path, text)
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
        keystore.write_private(dest, Path(source).read_text(encoding="utf-8"))


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


def block_digest(text):
    found = re.search(re.escape(BEGIN) + r"\n.*?" + re.escape(END), text, re.S)
    return digest(found.group()) if found else None


# ---------------------------------------------------------------- Claude Code


def claude_settings(paths):
    return Path(paths.home) / ".claude" / "settings.json"


def validate_base_url(base_url):
    if not isinstance(base_url, str) or not re.fullmatch(r'https?://[A-Za-z0-9.\[\]:-]+/[a-z0-9-]+(?:/v1)?', base_url):
        raise AgentConfigError("Unsafe coding-agent base URL.")
    return base_url


def helper_command(paths, tool):
    if sys.platform == "win32":
        raise AgentConfigError("Managed Windows helpers require native vendor/version verification. Use swangz run.")
    args = ["/usr/bin/env", "SWANGZ_HOME=" + str(paths.data)]
    if not getattr(sys, "frozen", False):
        args += ["PYTHONPATH=" + str(Path(__file__).resolve().parent.parent)]
    return shlex.join(args + shell.app_command() + ["key", "--for", tool])


def scoped_record(base_url, tool, gated=False):
    short = "claude" if tool == "claude-code" else tool
    return {"mode": "scoped", "base_url": base_url, "credential_config": 2, "gated": gated,
            "detail": f"Run it with: swangz run {short}" + (". Managed configuration awaits native vendor/version verification." if gated else "")}


def install_claude(paths, base_url, key, mode):
    """-> the record to remember. A managed device gets its settings file's "env" block pointed at the gateway."""
    validate_base_url(base_url)
    if mode != "managed" or sys.platform == "win32":
        return scoped_record(base_url, "claude-code", mode == "managed")
    if not CLAUDE_PREFIX_VERIFIED:
        record = scoped_record(base_url, "claude-code", True)
        record["detail"] = "Managed Claude setup is gated until the deployed CLI verifies the /anthropic path. Existing scoped runs remain available: swangz run claude."
        return record
    path = claude_settings(paths)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError:
            raise AgentConfigError(f"{path} isn't valid JSON, so the Swangz app left it alone. Fix or remove it, then sync again.")
        if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
            raise AgentConfigError(f"{path} has an unexpected shape, so the Swangz app left it alone.")
    env = data.setdefault("env", {})
    helper = helper_command(paths, "claude-code")
    wrote = {"ANTHROPIC_BASE_URL": base_url, "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1"}
    resuming = data.get("apiKeyHelper") == helper and all(k not in env or env[k] == v for k, v in wrote.items())
    if (any(k in env for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"))
            or not resuming and (any(k in env for k in CLAUDE_ENV) or "apiKeyHelper" in data)):
        raise AgentConfigError(f"{path} already has authentication or gateway settings, so the Swangz app left it alone. Use swangz run claude.")
    keep_original(paths, path, "claude-settings.json.orig")
    env.update(wrote)
    data["apiKeyHelper"] = helper
    write_atomic(path, json.dumps(data, indent=2) + "\n", private=True)
    return {"mode": "managed", "base_url": base_url, "file": str(path), "credential_config": 2,
            "helper": digest(helper), "wrote": {k: digest(v) for k, v in wrote.items()},
            "detail": "Claude Code now goes through the company gateway."}


def remove_claude(paths, record):
    path = Path(record.get("file") or "")
    if record.get("mode") != "managed" or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except ValueError:
        return  # theirs now; not ours to repair
    if not isinstance(data, dict):
        return
    env = data.get("env", {})
    if not isinstance(env, dict):
        env = {}
    for name, fingerprint in (record.get("wrote") or {}).items():
        if name in env and digest(str(env[name])) == fingerprint:  # only what we wrote, and only if still ours
            del env[name]
    if not env:
        data.pop("env", None)
    if record.get("helper") and digest(str(data.get("apiKeyHelper", ""))) == record["helper"]:
        data.pop("apiKeyHelper", None)
    write_atomic(path, json.dumps(data, indent=2) + "\n", private=True)


# ---------------------------------------------------------------- Codex


def codex_config(paths):
    return Path(paths.home) / ".codex" / "config.toml"


def codex_block(base_url):
    validate_base_url(base_url)
    return ('model_provider = "swangz"\n\n[model_providers.swangz]\nname = "Swangz AI Hub"\n'
            f'base_url = {json.dumps(base_url)}\nenv_key = "SWANGZ_AI_KEY"\nwire_api = "responses"')


def codex_overrides(base_url):
    """The same settings as command-line overrides, for a scoped run that writes nothing."""
    validate_base_url(base_url)
    pairs = ['model_provider="swangz"', 'model_providers.swangz.name="Swangz AI Hub"',
             f'model_providers.swangz.base_url={json.dumps(base_url)}', 'model_providers.swangz.env_key="SWANGZ_AI_KEY"',
             'model_providers.swangz.wire_api="responses"']
    return [x for pair in pairs for x in ("-c", pair)]


def install_codex(paths, base_url, key, mode):
    validate_base_url(base_url)
    if mode != "managed" or sys.platform == "win32" or sys.version_info < (3, 11):
        return scoped_record(base_url, "codex", mode == "managed")
    path = codex_config(paths)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    import tomllib
    try:
        tomllib.loads(text)
    except ValueError:
        raise AgentConfigError(f"{path} isn't valid TOML, so the Swangz app left it alone.") from None
    outside = without_block(text)
    parsed_outside = tomllib.loads(outside)
    if "model_provider" in parsed_outside or "swangz" in parsed_outside.get("model_providers", {}):
        raise AgentConfigError(f"{path} already chooses a provider of its own, so the Swangz app left it alone. "
                               "Remove that, or use `swangz run codex` instead.")
    keep_original(paths, path, "codex-config.toml.orig")
    candidate = with_block(text, codex_block(base_url), at_start=True)
    tomllib.loads(candidate)
    persisted = persist_env(paths, "SWANGZ_AI_KEY")
    write_atomic(path, candidate)
    return {"mode": "managed", "base_url": base_url, "file": str(path), "env": persisted,
            "credential_config": 2, "block": block_digest(candidate),
            "detail": "Codex now goes through the company gateway. Open a new terminal for it to take effect."}


def remove_codex(paths, record, key=None):
    path = Path(record.get("file") or "")
    if record.get("mode") != "managed":
        return
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if has_block(text) and (not record.get("block") or block_digest(text) == record["block"]):
            write_atomic(path, without_block(text))
    forget_env(paths, "SWANGZ_AI_KEY", record.get("env"), key=key)


# ---------------------------------------------------------------- an environment variable that survives a restart


def profiles(paths):
    home = Path(paths.home)
    out = [home / ".profile"]
    if sys.platform == "darwin" or "zsh" in os.environ.get("SHELL", ""):
        out.append(home / ".zprofile")
    return out


def persist_env(paths, name, value=None, run=subprocess.run):
    """Unix only: marked login-profile helper. No persistent Windows credential environment."""
    if sys.platform == "win32":
        raise AgentConfigError("Use swangz run codex on Windows.")
    if name != "SWANGZ_AI_KEY":
        raise AgentConfigError("Unknown managed environment variable.")
    line = f'export {name}="$({helper_command(paths, "codex")})"'
    done, fingerprints = [], {}
    for profile in profiles(paths):
        text = profile.read_text(encoding="utf-8") if profile.exists() else ""
        candidate = with_block(text, line)
        write_atomic(profile, candidate)
        done.append(str(profile))
        fingerprints[str(profile)] = block_digest(candidate)
    return {"kind": "profile", "files": done, "fingerprints": fingerprints}


def forget_env(paths, name, record, run=subprocess.run, key=None, registry=None):
    record = record or {}
    if record.get("kind") == "windows-user-env":
        if registry is None:
            import winreg as registry
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, "Environment", 0,
                                  registry.KEY_QUERY_VALUE | registry.KEY_SET_VALUE) as handle:
                current, _ = registry.QueryValueEx(handle, name)
                fingerprint = record.get("fingerprint") or (digest(key) if key else None)
                if not fingerprint:
                    raise AgentConfigError("The old Windows credential environment needs keychain access before safe removal. Retry signing out.")
                if digest(str(current)) == fingerprint:
                    registry.DeleteValue(handle, name)
        except FileNotFoundError:
            pass
    for f in record.get("files") or []:
        profile = Path(f)
        if profile.exists():
            text = profile.read_text(encoding="utf-8")
            expected = (record.get("fingerprints") or {}).get(str(profile))
            if has_block(text) and (not expected or block_digest(text) == expected):
                write_atomic(profile, without_block(text))


def scrub_backup(paths, key):
    """Remove only an exact known managed credential from the app's own old settings backup."""
    path = Path(paths.data) / "backups" / "claude-settings.json.orig"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        if key in path.read_text(encoding="utf-8"):
            raise AgentConfigError("An old settings backup needs manual recovery before credential migration can finish.")
        return
    if isinstance(data, dict) and isinstance(data.get("env"), dict):
        changed = False
        for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            if data["env"].get(name) == key:
                del data["env"][name]
                changed = True
        if changed:
            write_atomic(path, json.dumps(data, indent=2) + "\n", private=True)
