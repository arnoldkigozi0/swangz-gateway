"""The Swangz app: Swangz AI Hub on a person's own device (Windows, macOS, Linux). Standard library only.

    swangz_client/core.py     sign in with a code, what this device is offered, install / update / remove, run
    swangz_client/agents.py   pointing Claude Code and Codex at the company gateway (never overwriting what's there)
    swangz_client/bundles.py  downloading and unpacking published packages safely
    swangz_client/shell.py    the device itself: start at login, a terminal, the web browser
    swangz_client/cli.py      the same things from a terminal
    swangz_client/gui.py      the app window

See docs/CLIENT.md.
"""

__version__ = "0.1.0"
