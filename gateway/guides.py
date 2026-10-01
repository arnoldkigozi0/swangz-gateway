"""Step-by-step connection guides for each tool, filled in with this gateway's address and a key.

Used by the staff app ("Connect a tool") and by the admin console's key dialog.
"""

import json

PLACEHOLDER = "YOUR_SWANGZ_AI_KEY"


def guides(gw, key=None):
    base = gw.settings.base_url()
    key = key or PLACEHOLDER
    providers = gw.settings.providers
    out = []
    anthropic = next((p for p in providers.values() if p.dialect == "anthropic"), None)
    openai = providers.get("openai") or next((p for p in providers.values() if p.dialect == "openai"), None)

    if anthropic:
        url = f"{base}/{anthropic.name}"
        settings = json.dumps({"env": {"ANTHROPIC_BASE_URL": url, "ANTHROPIC_AUTH_TOKEN": key,
                                       "CLAUDE_CODE_GATEWAY_HINT_HEADERS": "1"}}, indent=2)
        out.append({
            "id": "claude-code", "name": "Claude Code", "kind": "Coding agent",
            "blurb": "Anthropic's coding agent in your terminal or editor.",
            "steps": [
                {"title": "Open your Claude Code settings file",
                 "how": "Mac and Linux: ~/.claude/settings.json — Windows: %USERPROFILE%\\.claude\\settings.json. "
                        "Create it if it isn't there. If it already has an \"env\" block, add these three lines to it.",
                 "code": settings},
                {"title": "Restart Claude Code",
                 "how": "Close any running Claude Code and start it again. Type /status — the base URL shows the Swangz AI address.",
                 "code": "claude"},
            ],
        })
        out.append({
            "id": "anthropic-sdk", "name": "Anthropic SDK", "kind": "Scripts and apps",
            "blurb": "Your own scripts, notebooks and tools that use Claude.",
            "steps": [
                {"title": "Point the client at Swangz AI", "how": "Python:",
                 "code": f'from anthropic import Anthropic\n\nclient = Anthropic(base_url="{url}", api_key="{key}")'},
                {"title": "Or use environment variables", "how": "Most tools that use Claude read these:",
                 "code": f'export ANTHROPIC_BASE_URL="{url}"\nexport ANTHROPIC_API_KEY="{key}"'},
            ],
        })
    if openai:
        url = f"{base}/{openai.name}/v1"
        out.append({
            "id": "codex", "name": "Codex", "kind": "Coding agent",
            "blurb": "OpenAI's coding agent in your terminal or editor.",
            "steps": [
                {"title": "Add Swangz AI to Codex",
                 "how": "Open ~/.codex/config.toml (Windows: %USERPROFILE%\\.codex\\config.toml) and add:",
                 "code": ('model_provider = "swangz"\n\n[model_providers.swangz]\nname = "Swangz AI"\n'
                          f'base_url = "{url}"\nenv_key = "SWANGZ_AI_KEY"\nwire_api = "responses"')},
                {"title": "Save your key where Codex can find it",
                 "how": "Add this line to ~/.bashrc or ~/.zshrc (Windows: setx SWANGZ_AI_KEY \"…\"), then open a new terminal:",
                 "code": f'export SWANGZ_AI_KEY="{key}"'},
                {"title": "Start Codex", "how": "It now works through Swangz AI.", "code": "codex"},
            ],
        })
        out.append({
            "id": "openai-compatible", "name": "Other AI apps", "kind": "Cursor, OpenCode, SDKs…",
            "blurb": "Any app that asks for an OpenAI-compatible base URL and API key.",
            "steps": [
                {"title": "Use these two values", "how": "In the app's model or API settings:",
                 "code": f"Base URL   {url}\nAPI key    {key}"},
                {"title": "From code", "how": "Python:",
                 "code": f'from openai import OpenAI\n\nclient = OpenAI(base_url="{url}", api_key="{key}")'},
            ],
        })
    for p in providers.values():
        if p is anthropic or p is openai:
            continue
        url = f"{base}/{p.name}" + ("/v1" if p.dialect == "openai" else "")
        out.append({"id": p.name, "name": p.name.capitalize(), "kind": "Extra provider",
                    "blurb": f"Models from {p.name} through Swangz AI.",
                    "steps": [{"title": "Use these two values", "how": "Base URL and API key:",
                               "code": f"Base URL   {url}\nAPI key    {key}"}]})
    return out


def flat_snippets(gw, key):
    """The guides as a flat list of {title, how, code} — the admin console's key dialog."""
    out = []
    for g in guides(gw, key):
        for i, step in enumerate(g["steps"]):
            out.append({"title": g["name"] + (f" — {step['title'].lower()}" if len(g["steps"]) > 1 else ""),
                        "how": step["how"], "code": step["code"]})
    return out
