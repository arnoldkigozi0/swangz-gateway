"""The Swangz app window: a small desktop shell — a dock down the left (Home, Apps, Packages, This device) and
the page you are on. Tk, so it is a real window on Windows, macOS and Linux with nothing to install beyond Python.

All the work is done by `core.Client`; this file only draws it. Network calls run on a worker thread and hand
their results back through a queue, so the window never freezes. Tests drive it with `inline=True`.
"""

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__, core, shell

C = dict(bg="#0b0b0c", panel="#141416", raised="#1c1c1f", line="#2a2a2e", text="#ece9e2", muted="#9a978f",
         gold="#c8a96a", gold_hi="#e2c88d", bad="#e07a6b", ok="#7bd3a7")
FONT = ("Segoe UI" if os.name == "nt" else "Helvetica", 11)
SYNC_EVERY_MS = 15 * 60 * 1000
PAGES = (("home", "Home"), ("apps", "Apps"), ("packages", "Packages"), ("device", "This device"))
STATE_WORDS = {"installed": "Installed", "update": "Update ready", "available": "Not installed"}


def clock(ts):
    return time.strftime("%H:%M", time.localtime(ts)) if ts else "never"


class App:
    def __init__(self, client, root=None, inline=False, background=False):
        self.client, self.inline = client, inline
        self.root = root or tk.Tk()
        self.q = queue.Queue()
        self.cancel = False
        self.page = None
        self.error = ""
        self.root.title("Swangz")
        self.root.geometry("980x660")
        self.root.minsize(780, 540)
        self.root.configure(bg=C["bg"])
        self._styles()
        self.dock = tk.Frame(self.root, bg=C["panel"], width=200)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.body = tk.Frame(self.root, bg=C["bg"])
        self.body.pack(side="left", fill="both", expand=True)
        self.statusbar = tk.Label(self.body, text="", anchor="w", bg=C["bg"], fg=C["muted"], font=(FONT[0], 9), padx=24, pady=8)
        self.statusbar.pack(side="bottom", fill="x")
        self.content = tk.Frame(self.body, bg=C["bg"])
        self.content.pack(fill="both", expand=True, padx=32, pady=(28, 0))
        self.nav = {}
        self.show("home" if client.signed_in() else "signin")
        if not inline:
            self.root.after(120, self._drain)
            if client.signed_in():
                self.root.after(500, self.sync_now)
                self.root.after(SYNC_EVERY_MS, self._tick)
        if background and client.signed_in():
            self.root.iconify()

    # ------------------------------------------------------------ plumbing

    def _styles(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TCheckbutton", background=C["bg"], foreground=C["text"], font=FONT)
        s.configure("TEntry", fieldbackground=C["raised"], foreground=C["text"], insertcolor=C["text"], bordercolor=C["line"],
                    lightcolor=C["line"], darkcolor=C["line"], padding=4)
        s.map("TEntry", bordercolor=[("focus", C["gold"])], lightcolor=[("focus", C["gold"])], darkcolor=[("focus", C["gold"])])
        s.configure("Vertical.TScrollbar", background=C["raised"], troughcolor=C["bg"], bordercolor=C["bg"])

    def work(self, fn, done=None):
        """Run fn off the window's thread; done(ok, value) runs back on it."""
        def run():
            try:
                outcome = (True, fn())
            except Exception as exc:  # noqa: BLE001 — shown to the person, not lost
                outcome = (False, exc)
            self.q.put(lambda: done(*outcome) if done else None)

        if self.inline:
            run()
            self.pump()
        else:
            threading.Thread(target=run, daemon=True).start()

    def later(self, fn):
        """Call fn on the window's thread (from a worker)."""
        self.q.put(fn)
        if self.inline:
            self.pump()

    def pump(self):
        while True:
            try:
                self.q.get_nowait()()
            except queue.Empty:
                return

    def _drain(self):
        self.pump()
        self.root.after(120, self._drain)

    def _tick(self):
        if self.client.signed_in():
            self.sync_now(quiet=True)
        self.root.after(SYNC_EVERY_MS, self._tick)

    def say(self, text, bad=False):
        self.statusbar.configure(text=text, fg=C["bad"] if bad else C["muted"])

    def failed(self, exc):
        if isinstance(exc, core.Revoked):
            self.error = "This device was disconnected from Swangz AI Hub, so Swangz has been removed from it."
            self.show("signin")
        elif isinstance(exc, core.NotSignedIn):
            self.show("signin")
        else:
            self.say(getattr(exc, "message", None) or str(exc), bad=True)

    # ------------------------------------------------------------ widgets

    def label(self, parent, text, size=11, color="text", bold=False, **kw):
        font = (FONT[0], size, "bold" if bold else "normal")
        return tk.Label(parent, text=text, bg=kw.pop("bg", C["bg"]), fg=C[color], font=font, anchor=kw.pop("anchor", "w"),
                        justify="left", wraplength=kw.pop("wrap", 0), **kw)

    def button(self, parent, text, command, primary=False, danger=False, **kw):
        fg = C["bg"] if primary else (C["bad"] if danger else C["text"])
        bg = C["text"] if primary else C["bg"]
        b = tk.Button(parent, text=text, command=command, font=FONT, bg=bg, fg=fg, activebackground=C["gold"] if primary else C["raised"],
                      activeforeground=C["bg"] if primary else fg, relief="flat", bd=0, padx=16, pady=7, cursor="hand2",
                      highlightthickness=1, highlightbackground=C["bad"] if danger else (C["text"] if primary else C["line"]), **kw)
        return b

    def card(self, parent, **kw):
        return tk.Frame(parent, bg=C["panel"], highlightthickness=1, highlightbackground=C["line"], padx=18, pady=14, **kw)

    def clear(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    # ------------------------------------------------------------ pages

    def show(self, page):
        self.page = page
        self.say("")
        self.clear(self.dock)
        self.clear(self.content)
        self.nav = {}
        tk.Label(self.dock, text="SWANGZ", bg=C["panel"], fg=C["gold"], font=(FONT[0], 13, "bold"), anchor="w", padx=22, pady=24).pack(fill="x")
        if page != "signin":
            for key, name in PAGES:
                b = tk.Button(self.dock, text=name, anchor="w", command=lambda k=key: self.show(k), relief="flat", bd=0, padx=22, pady=11,
                              font=FONT, bg=C["raised"] if key == page else C["panel"], fg=C["gold_hi"] if key == page else C["text"],
                              activebackground=C["raised"], activeforeground=C["gold_hi"], cursor="hand2", highlightthickness=0)
                b.pack(fill="x")
                self.nav[key] = b
            st = self.client.status()
            tk.Label(self.dock, text=(st.get("person") or {}).get("name", ""), bg=C["panel"], fg=C["muted"], font=(FONT[0], 9),
                     anchor="w", padx=22, wraplength=170, justify="left").pack(side="bottom", fill="x", pady=(0, 18))
        getattr(self, "page_" + page)()

    def page_signin(self):
        f = self.content
        self.label(f, "Connect this device", 22, bold=True).pack(anchor="w")
        self.label(f, "Swangz brings your company's AI tools to this device, in one place, under the company's rules. "
                      "Sign in with your Swangz account to get started.", color="muted", wrap=560).pack(anchor="w", pady=(8, 20))
        if self.error:
            self.label(f, self.error, color="bad", wrap=560).pack(anchor="w", pady=(0, 14))
        if (self.client.store.device() or {}).get("cleanup_pending"):
            self.label(f, "Credential removal is incomplete. Retry while the keychain is available.", color="bad", wrap=560).pack(anchor="w")
            self.button(f, "Retry local removal", lambda: self.work(self.client.remove_everything,
                        lambda ok, value: self.show("signin") if ok else self.failed(value))).pack(anchor="w", pady=12)
        self.server_var = tk.StringVar(value=os.environ.get("SWANGZ_SERVER", ""))
        self.name_var = tk.StringVar(value=core.device_name())
        for text, var in (("Swangz AI Hub address", self.server_var), ("Name for this device", self.name_var)):
            self.label(f, text, 10, color="muted").pack(anchor="w")
            ttk.Entry(f, textvariable=var, width=46, font=FONT).pack(anchor="w", pady=(2, 14), ipady=4)
        self.signin_button = self.button(f, "Sign in", self.sign_in, primary=True)
        self.signin_button.pack(anchor="w", pady=(4, 0))
        self.code_box = tk.Frame(f, bg=C["bg"])
        self.code_box.pack(anchor="w", fill="x", pady=(24, 0))
        self.say("Nothing is recorded until you sign in. What Swangz records is shown on the 'This device' page.")

    def sign_in(self):
        try:
            server = core.normalise_server(self.server_var.get())
        except ValueError as exc:
            self.error = str(exc)
            return self.show("signin")
        self.error, self.cancel = "", False
        self.signin_button.configure(state="disabled", text="Waiting for approval…")
        self.clear(self.code_box)
        name = self.name_var.get().strip() or core.device_name()

        def show_code(code, url):
            self.later(lambda: self._show_code(code, url))

        self.work(lambda: self.client.login(server, name, on_code=show_code, cancelled=lambda: self.cancel), self._signed_in)

    def _show_code(self, code, url):
        if self.page != "signin":
            return
        self.clear(self.code_box)
        self.label(self.code_box, "Check that your browser shows this code, then press Approve:", color="muted").pack(anchor="w")
        self.label(self.code_box, code, 30, color="gold_hi", bold=True).pack(anchor="w", pady=6)
        row = tk.Frame(self.code_box, bg=C["bg"])
        row.pack(anchor="w")
        self.button(row, "Open the page again", lambda: shell.open_url(url)).pack(side="left")
        self.button(row, "Cancel", self._cancel_signin).pack(side="left", padx=10)

    def _cancel_signin(self):
        self.cancel = True
        self.show("signin")

    def _signed_in(self, ok, value):
        if not ok:
            if getattr(value, "code", "") == "cancelled":
                return
            self.error = getattr(value, "message", None) or str(value)
            return self.show("signin")
        self.error = ""
        self.show("home")
        self.sync_now()

    def page_home(self):
        f, st = self.content, self.client.status()
        name = (st.get("person") or {}).get("name") or ""  # the whole name: which part is the "first" one is not ours to guess
        hour = time.localtime().tm_hour
        self.label(f, f"Good {'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'}{', ' + name if name else ''}", 24, bold=True).pack(anchor="w")
        self.label(f, f"Signed in to {st.get('server') or ''}  ·  last synced {clock(st.get('last_sync'))}", 10, color="muted").pack(anchor="w", pady=(2, 20))
        installed = st["installed"]
        agents = [(k, n) for k, n in (("claude-code", "Claude Code"), ("codex", "Codex")) if k in installed]
        card = self.card(f)
        card.pack(fill="x", pady=(0, 14))
        self.label(card, "Coding agents", 13, bold=True, bg=C["panel"]).pack(anchor="w")
        if agents:
            self.label(card, "Run them in a terminal. Everything they do goes through the company gateway.", 10, color="muted", bg=C["panel"]).pack(anchor="w", pady=(2, 10))
            row = tk.Frame(card, bg=C["panel"])
            row.pack(anchor="w")
            for key, name in agents:
                self.button(row, f"Open {name}", lambda k=key: self.open_agent(k)).pack(side="left", padx=(0, 10))
        else:
            self.label(card, "None have been set up for you. Ask your admin, or press Sync now.", 10, color="muted", bg=C["panel"]).pack(anchor="w", pady=(2, 0))
        apps = self.client.apps()[:6]
        card = self.card(f)
        card.pack(fill="x", pady=(0, 14))
        self.label(card, "Your apps", 13, bold=True, bg=C["panel"]).pack(anchor="w")
        if apps:
            row = tk.Frame(card, bg=C["panel"])
            row.pack(anchor="w", pady=(10, 0))
            for a in apps:
                self.button(row, a["name"], lambda t=a["id"]: self.open_app(t)).pack(side="left", padx=(0, 10))
        else:
            self.label(card, "No website tools are turned on for you yet.", 10, color="muted", bg=C["panel"]).pack(anchor="w", pady=(2, 0))
        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(anchor="w", pady=(6, 0))
        self.button(bar, "Sync now", self.sync_now, primary=True).pack(side="left")
        if st.get("update_available"):
            self.label(bar, "  A newer version of Swangz is available.", color="gold_hi").pack(side="left")

    def page_apps(self):
        f = self.content
        self.label(f, "Apps", 22, bold=True).pack(anchor="w")
        self.label(f, "Website tools your company has turned on for you. They open through Swangz, which checks access and "
                      "records which tool and when.", color="muted", wrap=640).pack(anchor="w", pady=(6, 16))
        apps = self.client.apps()
        if not apps:
            self.label(f, "Nothing here yet.", color="muted").pack(anchor="w")
        for a in apps:
            row = self.card(f)
            row.pack(fill="x", pady=4)
            text = tk.Frame(row, bg=C["panel"])
            text.pack(side="left", fill="x", expand=True)
            self.label(text, a["name"], 12, bold=True, bg=C["panel"]).pack(anchor="w")
            note = "Opens in a company browser of your own" if a.get("company_browser") else ("Shared company account, one turn at a time" if a.get("signin") == "shared" else a.get("category", ""))
            self.label(text, note, 9, color="muted", bg=C["panel"]).pack(anchor="w")
            self.button(row, "Open", lambda t=a["id"]: self.open_app(t)).pack(side="right")

    def page_packages(self):
        f = self.content
        head = tk.Frame(f, bg=C["bg"])
        head.pack(fill="x")
        self.label(head, "Packages", 22, bold=True).pack(side="left")
        self.button(head, "Sync all", self.sync_now, primary=True).pack(side="right")
        self.label(f, "What Swangz has made available to you. The company decides this list; it updates here by itself.", color="muted", wrap=640).pack(anchor="w", pady=(6, 16))
        rows = self.client.packages()
        if not rows:
            self.label(f, "Nothing has been offered to you yet.", color="muted").pack(anchor="w")
        for r in rows:
            row = self.card(f)
            row.pack(fill="x", pady=4)
            text = tk.Frame(row, bg=C["panel"])
            text.pack(side="left", fill="x", expand=True)
            self.label(text, f"{r['name']}   {r['version']}", 12, bold=True, bg=C["panel"]).pack(anchor="w")
            self.label(text, r["description"], 9, color="muted", bg=C["panel"], wrap=520).pack(anchor="w")
            self.label(text, STATE_WORDS.get(r["state"], r["state"]) + (f" ({r['installed_version']})" if r["state"] == "update" else ""), 9,
                       color="ok" if r["state"] == "installed" else "gold_hi", bg=C["panel"]).pack(anchor="w")
            if r["state"] == "installed":
                self.button(row, "Remove", lambda i=r["id"]: self.remove_package(i)).pack(side="right")
            else:
                self.button(row, "Update" if r["state"] == "update" else "Install", self.sync_now).pack(side="right")

    def page_device(self):
        f, st = self.content, self.client.status()
        d = st.get("device") or {}
        self.label(f, "This device", 22, bold=True).pack(anchor="w")
        card = self.card(f)
        card.pack(fill="x", pady=(14, 14))
        for k, v in (("Name", d.get("name")), ("Kind", "Company-owned" if d.get("owner_kind") == "company" else "Personal"),
                     ("Signed in as", f"{(st.get('person') or {}).get('name', '')}  ({(st.get('person') or {}).get('email', '')})"),
                     ("Server", st.get("server")), ("Swangz version", st.get("client_version")),
                     ("Key storage", st.get("key_storage")), ("Last synced", clock(st.get("last_sync")))):
            row = tk.Frame(card, bg=C["panel"])
            row.pack(fill="x", pady=2)
            self.label(row, k, 10, color="muted", bg=C["panel"], width=16).pack(side="left")
            self.label(row, str(v or "—"), 10, bg=C["panel"]).pack(side="left")
        if st.get("credential_warning"):
            self.label(f, st["credential_warning"], 10, color="bad", wrap=700).pack(anchor="w", pady=(0, 14))
        self.label(f, "What Swangz records", 13, bold=True).pack(anchor="w")
        self.label(f, st.get("recording") or "", 10, color="muted", wrap=700).pack(anchor="w", pady=(4, 14))
        self.auto_var = tk.BooleanVar(value=st.get("autostart", False))
        ttk.Checkbutton(f, text="Start Swangz when I sign in to this computer", variable=self.auto_var, command=self.toggle_autostart).pack(anchor="w", pady=(0, 18))
        self.button(f, "Sign out and remove Swangz from this device", self.sign_out, danger=True).pack(anchor="w")

    # ------------------------------------------------------------ actions

    def sync_now(self, quiet=False):
        if not self.client.signed_in():
            return
        if not quiet:
            self.say("Syncing…")

        def done(ok, value):
            if not ok:
                return self.failed(value)
            bad = [(p, d) for p, o, d in value["results"] if o == "failed"]
            if self.page in ("home", "apps", "packages", "device"):
                self.show(self.page)  # redraw first: it clears the status line
            self.say(f"Synced at {clock(time.time())}." if not bad else f"Synced, but {bad[0][0]} needs attention: {bad[0][1]}", bad=bool(bad))

        self.work(self.client.sync, done)

    def remove_package(self, pid):
        if not messagebox.askyesno("Remove", "Remove this from the device? It stays available, and Sync will put it back."):
            return
        self.client.remove_package(pid)
        self.show("packages")
        self.say("Removed. Sync puts it back if it is still offered to you.")

    def open_agent(self, key):
        short = {"claude-code": "claude", "codex": "codex"}[key]
        if not shell.open_terminal(shell.app_command() + ["run", short]):
            self.say(f"Couldn't open a terminal. In one, run:  swangz run {short}", bad=True)
        else:
            self.say(f"Opened {short} in a terminal.")

    def open_app(self, tool_id):
        try:
            self.client.open_app(tool_id)
            self.say("Opened in your browser.")
        except Exception as exc:  # noqa: BLE001
            self.failed(exc)

    def toggle_autostart(self):
        try:
            shell.set_autostart(self.client.paths, self.auto_var.get())
        except OSError as exc:
            self.say(f"Couldn't change that: {exc}", bad=True)

    def sign_out(self):
        if not messagebox.askyesno("Sign out", "Sign out and remove Swangz from this device?\n\nThe coding agents and packages Swangz "
                                                "installed will be taken off, and the device disconnected."):
            return
        self.work(self.client.logout, lambda ok, value: (setattr(self, "error", ""), self.show("signin")) if ok else self.failed(value))


def main(client=None, background=False):
    client = client or core.Client()
    app = App(client, background=background)
    app.root.mainloop()
    return 0
