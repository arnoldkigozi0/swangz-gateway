"""Entry point for the packaged Swangz app (PyInstaller). Opens the window; `Swangz run claude` etc. also work."""
import json
import os
from pathlib import Path
import sys

from swangz_client.cli import main


def self_check(destination):
    """Bounded, offline check of the frozen imports, state and actual Tk window.

    A report file also works for Windows' windowed executable, which has no stdout.
    It contains no credential or device metadata and never acknowledges an update.
    """
    import tkinter as tk
    from swangz_client import __version__, core, gui, release_keys, updater  # noqa: F401

    client = core.Client()
    client.store.state()
    root = tk.Tk()
    root.withdraw()
    try:
        app = gui.App(client, root=root, inline=True)
        root.update_idletasks()
        report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
                  "window": app.page, "tk": root.tk.call("info", "patchlevel"),
                  "updates_enabled": release_keys.ENABLED, "production_keys": len(release_keys.KEYS)}
    finally:
        root.destroy()
    Path(destination).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    # PyInstaller --windowed leaves these as None on Windows. Do not create a log
    # file: the credential helper's output must never be persisted there.
    for stream in ("stdout", "stderr"):
        if getattr(sys, stream) is None:
            setattr(sys, stream, open(os.devnull, "w", encoding="utf-8"))
    if len(sys.argv) == 3 and sys.argv[1] == "--self-check":
        sys.exit(self_check(sys.argv[2]))
    sys.exit(main())
