"""Entry point for the packaged Swangz app (PyInstaller). Opens the window; `Swangz run claude` etc. also work."""
import json
import os
from pathlib import Path
import sys


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
        bundle = getattr(sys, "_MEIPASS", None)  # where the frozen program's own files are loaded from
        beside = Path(sys.executable).resolve().parent / "_internal"
        report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
                  "one_folder": bool(bundle) and Path(bundle).resolve() == beside,
                  "window": app.page, "hub_address": app.server_var.get() if app.page == "signin" else None, "tk": root.tk.call("info", "patchlevel"),
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
    if len(sys.argv) > 1 and sys.argv[1] == "admin":
        # D-026 B3: the elevated step, `Swangz.exe admin <action>` and nothing else. Dispatched before the app's own
        # code (its state, settings and the person's folders) is loaded.
        from swangz_client.chrome_install import admin_main
        sys.exit(admin_main(sys.argv[1:]))
    if len(sys.argv) == 3 and sys.argv[1] == "--self-check":
        sys.exit(self_check(sys.argv[2]))
    from swangz_client.cli import main
    sys.exit(main())
