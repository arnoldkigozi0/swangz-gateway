"""The Swangz app window: an AI workstation. A sidebar down the left (Home, Apps, Workspace, Automations, Usage, Settings)
and the page you are on. Tk, so it is a real window on Windows, macOS and Linux with nothing to install beyond Python.

All the work is done by `core.Client` (and its `native` app manager); this file only draws it. Network calls, installs
and Chrome's publisher check run on a worker thread and hand their results back through a queue, so the window never
freezes. Tests drive it with `inline=True`.
"""

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__, core, native_apps, repair, shell
from .workspace_launcher import INSTALL_PAGE, profiles_folder

REMOVE = "Remove Swangz from this account"
PREFS = "workstation.json"  # this window's own preferences on this computer (pinned apps); nothing secret


def browser_folders_stay(data):
    """Sign out and revocation leave the company-browser folders on disk; say so rather than promise more. The folder
    is named by browser_profiles alone, reached through the launcher (inventory and import guards)."""
    return ("Browser folders that hold your provider and Google sign-ins are not removed. They stay on this device at "
            f"{profiles_folder(data)}. To delete them, choose “{REMOVE}” in Settings, or run swangz cleanup.")


# One calm palette: near-black neutrals, a darker sidebar, champagne gold as the one accent, mint and coral for states.
C = dict(bg="#0f0f11", side="#0a0a0b", panel="#17171a", raised="#202024", line="#2b2b30", text="#ece9e2",
         muted="#9a978f", gold="#c8a96a", gold_hi="#e2c88d", bad="#e07a6b", ok="#7bd3a7")
FONT = ("Segoe UI" if os.name == "nt" else "Helvetica", 11)

# macOS draws tk.Button with Aqua, which ignores bg/fg: the CI screenshot of 27 Nov 2026 showed white boxes with pale,
# unreadable text in the sidebar and on every button. A Label paints its colours everywhere, so on macOS each button is
# a LabelButton: same options, same command, keyboard and hover behaviour. Windows and Linux keep tk.Button.
LABEL_BUTTONS = sys.platform == "darwin"


class LabelButton(tk.Label):
    """A tk.Label that behaves like the buttons this file makes: command, invoke(), state, hover, Return and space."""

    def __init__(self, parent, command=None, **kw):
        for unused in ("relief", "overrelief", "default", "repeatdelay", "repeatinterval"):
            kw.pop(unused, None)
        self._command = command
        self._rest = (kw.get("bg"), kw.get("fg"))
        self._hover = (kw.get("activebackground") or kw.get("bg"), kw.get("activeforeground") or kw.get("fg"))
        kw.setdefault("disabledforeground", C["muted"])
        super().__init__(parent, takefocus=1, **kw)
        self.bind("<Button-1>", lambda e: self.invoke())
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<Enter>", lambda e: self._paint(True))
        self.bind("<Leave>", lambda e: self._paint(False))

    def _paint(self, hover):
        if str(self.cget("state")) == "disabled":
            return
        bg, fg = self._hover if hover else self._rest
        super().configure(bg=bg, fg=fg)

    def invoke(self):
        if str(self.cget("state")) != "disabled" and self._command:
            return self._command()
        return None

    def configure(self, cnf=None, **kw):
        if "command" in kw:
            self._command = kw.pop("command")
        if "bg" in kw or "fg" in kw:
            self._rest = (kw.get("bg", self._rest[0]), kw.get("fg", self._rest[1]))
        for unused in ("relief", "overrelief", "default"):
            kw.pop(unused, None)
        return super().configure(cnf, **kw)

    config = configure


def make_button(parent, **kw):
    return LabelButton(parent, **kw) if LABEL_BUTTONS else tk.Button(parent, **kw)
SYNC_EVERY_MS = 15 * 60 * 1000
PAGES = (("home", "Home"), ("apps", "Apps"), ("workspace", "Workspace"), ("automations", "Automations"),
         ("usage", "Usage"), ("settings", "Settings"))
STATE_WORDS = {"installed": "Installed", "update": "Update ready", "available": "Not installed"}
AGENTS = {"claude-code": "Claude Code", "codex": "Codex"}
GAP = 14


def clock(ts):
    return time.strftime("%H:%M", time.localtime(ts)) if ts else "never"


def when(ts):
    return time.strftime("%a %d %b, %H:%M", time.localtime(ts)) if ts else "never"


def app_note(client, app):
    """The web line on an Apps card: what Open in Swangz Chrome does for `app` on this computer, checked in
    core.Client.open_app's own order: the contract-2 workspace, its state, a refusal held by the workspace latch (read
    only: drawing a row never retries a purge), then the workspace tool, then whose computer it is (D-026 D4)."""
    manifest = client.store.manifest() or {}
    browser = manifest.get("browser") or {}
    if not isinstance(browser, dict) or browser.get("contract") != 2:
        return "Doesn't open until this device has a Swangz workspace window. Update Swangz, or ask your admin"
    state = (browser.get("workspace") or {}).get("state")
    if state == "retired":
        return "Doesn't open: your admin removed the Swangz workspace from this device"
    if state != "active":
        return "Doesn't open while this device's workspace is paused. Ask your admin"
    held = client.workspace.latch()
    if held.get("purge_pending") or held.get("refused"):
        return "Doesn't open right now. Press Open to see why"
    if client.workspace_app(app):
        return "Opens in your Swangz Chrome"
    shared = "Shared company account. " if app.get("signin") == "shared" else ""
    if client.company_device():
        return shared + "Doesn't open on this company computer yet; ask your administrator"
    return shared + "Open it from Swangz AI Hub"


def native_words(tool_id, found):
    """The desktop / command-line line on an Apps card, from native_apps.Manager.detect."""
    w = native_apps.way(tool_id, native_apps.os_key())
    what = "Command-line tool" if w.method == native_apps.CLI else "Desktop app"
    state = found.get("state")
    if state == "installed":
        version = f" {found['version']}" if found.get("version") else ""
        how = {"store": " from the Microsoft Store", "winget": " (listed by winget)",
               "PATH (fallback)": " (found on PATH)"}.get(found.get("via"), "")
        return f"{what} installed{version}{how}"
    if state == "unknown":
        return f"{what}: Swangz can't check whether it is installed on this computer"
    if state == "installing":
        return f"{what}: installing…"
    if state == "failed":
        return found.get("message") or f"{what}: the last install didn't finish"
    return f"{what} not installed"


class App:
    def __init__(self, client, root=None, inline=False, background=False):
        self.client, self.inline = client, inline
        self.root = root or tk.Tk()
        self.q = queue.Queue()
        self.cancel = False
        self.page = None
        self.error = ""
        self.removal_incomplete = False
        self.refusal = None  # (page, tool id, tool name, repair.Repair) while an Open stays refused
        self.opened = []     # (time, tool name, how) opened from this window since it started
        self.pending = set()  # tool ids with an install running from this window
        self.chrome_seen = None  # the last publisher check: {"ok", "path", "why"} or None while not checked
        self._chrome_checked_at = 0.0
        self._apps_checked_at = 0.0
        self.root.title("Swangz AI Hub")
        self.root.geometry("1040x700")
        self.root.minsize(780, 540)
        self.root.configure(bg=C["bg"])
        self._styles()
        self.dock = tk.Frame(self.root, bg=C["side"], width=212)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        self.body = tk.Frame(self.root, bg=C["bg"])
        self.body.pack(side="left", fill="both", expand=True)
        self.statusbar = tk.Label(self.body, text="", anchor="w", bg=C["bg"], fg=C["muted"], font=(FONT[0], 9), padx=24, pady=8)
        self.statusbar.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(self.body, bg=C["bg"], highlightthickness=0, bd=0)
        # The scrollbar lives in a fixed-width holder: a ttk scrollbar's own size request can change as it is set, and
        # packed straight beside the canvas that would resize the canvas, re-set the scrollbar, and never settle.
        rail = tk.Frame(self.body, bg=C["bg"], width=14)
        rail.pack_propagate(False)
        rail.pack(side="right", fill="y")
        self.scrollbar = ttk.Scrollbar(rail, orient="vertical", command=self.canvas.yview)
        self.scrollbar.pack(fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.canvas, bg=C["bg"])
        self._window = self.canvas.create_window((32, 26), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=(0, 0, e.width + 64, e.height + 52)))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=max(e.width - 64, 300)))
        self.root.bind_all("<MouseWheel>", self._wheel)
        self.root.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.root.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))
        self.root.bind("<FocusIn>", self._focused)
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
        s.map("TCheckbutton", background=[("active", C["bg"])])
        s.configure("TEntry", fieldbackground=C["raised"], foreground=C["text"], insertcolor=C["text"], bordercolor=C["line"],
                    lightcolor=C["line"], darkcolor=C["line"], padding=4)
        s.map("TEntry", bordercolor=[("focus", C["gold"])], lightcolor=[("focus", C["gold"])], darkcolor=[("focus", C["gold"])])
        s.configure("Vertical.TScrollbar", background=C["raised"], troughcolor=C["bg"], bordercolor=C["bg"], arrowcolor=C["muted"])

    def _wheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-event.delta / (120 if os.name == "nt" else 1)), "units")

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

    def ask(self, title, text):
        """From a worker: ask a yes/no question on the window's thread and wait for the answer."""
        answer, done = {}, threading.Event()

        def question():
            try:
                answer["yes"] = messagebox.askyesno(title, text)
            finally:
                done.set()

        self.later(question)
        done.wait()
        return answer.get("yes") is True

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

    def _focused(self, event=None):
        """Back in the window after installing Chrome or an app elsewhere: look again (at most every few seconds)."""
        if event is not None and event.widget is not self.root:
            return
        if self.page in ("workspace", "home") and self.chrome_seen is not None and not self.chrome_seen.get("ok") \
                and time.monotonic() - self._chrome_checked_at > 3:
            self.check_chrome()
        elif self.page == "apps" and self.pending and time.monotonic() - self._apps_checked_at > 5:
            self.recheck_apps(quiet=True, max_age=30)  # winget's list at most every 30 s, however often focus returns

    def say(self, text, bad=False):
        self.statusbar.configure(text=text, fg=C["bad"] if bad else C["muted"])

    def failed(self, exc):
        if isinstance(exc, core.Revoked):
            self.error = ("This device was disconnected from Swangz AI Hub, so the coding agents and packages Swangz "
                          "installed were taken off it. " + browser_folders_stay(self.client.paths.data))
            self.show("signin")
        elif isinstance(exc, core.NeedsReconnect):
            self.say(str(exc), bad=True)  # nothing was removed
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
        surface = kw.pop("bg", C["bg"])  # what the button sits on; a primary button is always gold
        bg = C["gold"] if primary else surface
        b = make_button(parent, text=text, command=command, font=(FONT[0], 10), bg=bg, fg=fg,
                      activebackground=C["gold_hi"] if primary else C["raised"],
                      activeforeground=C["bg"] if primary else fg, relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                      highlightthickness=1, highlightbackground=C["bad"] if danger else (C["gold"] if primary else C["line"]), **kw)
        return b

    def card(self, parent, **kw):
        return tk.Frame(parent, bg=C["panel"], highlightthickness=1, highlightbackground=C["line"], padx=18, pady=14, **kw)

    def heading(self, parent, title, note=None):
        self.label(parent, title, 22, bold=True).pack(anchor="w")
        if note:
            self.label(parent, note, 10, color="muted", wrap=680).pack(anchor="w", pady=(6, 16))

    def section(self, parent, title, note=None):
        card = self.card(parent)
        card.pack(fill="x", pady=(0, GAP))
        self.label(card, title, 13, bold=True, bg=C["panel"]).pack(anchor="w")
        if note:
            self.label(card, note, 10, color="muted", bg=C["panel"], wrap=640).pack(anchor="w", pady=(2, 8))
        return card

    def row(self, parent, bg=None):
        r = tk.Frame(parent, bg=bg or C["panel"])
        r.pack(anchor="w", fill="x", pady=(8, 0))
        return r

    def badge(self, parent, text):
        return tk.Label(parent, text=text, bg=C["raised"], fg=C["gold_hi"], font=(FONT[0], 8, "bold"), padx=6, pady=1)

    def fact(self, parent, key, value):
        r = tk.Frame(parent, bg=C["panel"])
        r.pack(fill="x", pady=2)
        self.label(r, key, 10, color="muted", bg=C["panel"], width=18).pack(side="left")
        self.label(r, str(value if value not in (None, "") else "—"), 10, bg=C["panel"], wrap=480).pack(side="left")

    def clear(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    # ------------------------------------------------------------ pages

    def show(self, page):
        self.page = page
        if self.refusal and self.refusal[0] != page:
            self.refusal = None
        self.say("")
        self.clear(self.dock)
        self.clear(self.content)
        self.canvas.yview_moveto(0)
        self.nav = {}
        brand = tk.Frame(self.dock, bg=C["side"])
        brand.pack(fill="x", padx=22, pady=(24, 22))
        tk.Label(brand, text="SWANGZ", bg=C["side"], fg=C["gold"], font=(FONT[0], 14, "bold"), anchor="w").pack(fill="x")
        tk.Label(brand, text="AI workstation", bg=C["side"], fg=C["muted"], font=(FONT[0], 9), anchor="w").pack(fill="x")
        if page != "signin":
            for key, name in PAGES:
                here = key == page
                item = tk.Frame(self.dock, bg=C["raised"] if here else C["side"])
                item.pack(fill="x")
                tk.Frame(item, bg=C["gold"] if here else C["side"], width=3).pack(side="left", fill="y")
                b = make_button(item, text=name, anchor="w", command=lambda k=key: self.show(k), relief="flat", bd=0, padx=19,
                              pady=10, font=FONT, bg=C["raised"] if here else C["side"], fg=C["gold_hi"] if here else C["text"],
                              activebackground=C["raised"], activeforeground=C["gold_hi"], cursor="hand2", highlightthickness=0)
                b.pack(side="left", fill="x", expand=True)
                self.nav[key] = b
            st = self.client.status()
            person = st.get("person") or {}
            tk.Label(self.dock, text=f"{person.get('name', '')}\n{(st.get('device') or {}).get('name') or ''}",
                     bg=C["side"], fg=C["muted"], font=(FONT[0], 9), anchor="w", padx=22, wraplength=170,
                     justify="left").pack(side="bottom", fill="x", pady=(0, 18))
        getattr(self, "page_" + page)()

    def page_signin(self):
        f = self.content
        self.label(f, "Connect this device", 22, bold=True).pack(anchor="w")
        self.label(f, "Swangz brings your company's AI tools to this computer, in one place, under the company's rules. "
                      "Sign in with your Swangz account to get started.", color="muted", wrap=560).pack(anchor="w", pady=(8, 20))
        if self.error:
            self.label(f, self.error, color="bad", wrap=560).pack(anchor="w", pady=(0, 14))
        if self.client.status().get("cleanup_pending"):
            self.label(f, "Credential removal is incomplete. Retry while the keychain is available.", color="bad", wrap=560).pack(anchor="w")
            self.button(f, "Retry local removal", lambda: self.work(self.client.remove_everything,
                        lambda ok, value: self.show("signin") if ok else self.failed(value))).pack(anchor="w", pady=12)
        if self.removal_incomplete:
            self.button(f, REMOVE, self.remove_account, danger=True).pack(anchor="w", pady=(0, 14))
        self.server_var = tk.StringVar(value=os.environ.get("SWANGZ_SERVER") or core.DEFAULT_SERVER)
        self.name_var = tk.StringVar(value=core.device_name())
        for text, var in (("Swangz AI Hub address", self.server_var), ("Name for this device", self.name_var)):
            self.label(f, text, 10, color="muted").pack(anchor="w")
            ttk.Entry(f, textvariable=var, width=46, font=FONT).pack(anchor="w", pady=(2, 14), ipady=4)
        self.signin_button = self.button(f, "Sign in", self.sign_in, primary=True)
        self.signin_button.pack(anchor="w", pady=(4, 0))
        self.code_box = tk.Frame(f, bg=C["bg"])
        self.code_box.pack(anchor="w", fill="x", pady=(24, 0))
        self.say("Nothing is recorded until you sign in. What Swangz records is shown in Settings.")

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

    # ---- Home: the dashboard

    def page_home(self):
        f, st = self.content, self.client.status()
        name = (st.get("person") or {}).get("name") or ""  # the whole name: which part is the "first" one is not ours to guess
        hour = time.localtime().tm_hour
        self.label(f, f"Good {'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'}{', ' + name if name else ''}",
                   24, bold=True).pack(anchor="w")
        self.label(f, f"Your AI workstation  ·  signed in to {st.get('server') or ''}", 10, color="muted").pack(anchor="w", pady=(2, 18))
        if st.get("reconnect"):
            self.label(f, core.RECONNECT, 10, color="bad", wrap=700).pack(anchor="w", pady=(0, 10))
            self.button(f, "Reconnect this device", self.sign_out).pack(anchor="w", pady=(0, GAP))
        self.repair_panel(f)
        email = (st.get("person") or {}).get("email") or ""
        if email and not self.google_signin_opened():
            card = self.section(f, "Sign in to Google once", f"Sign in with your Swangz account ({email}) in your Swangz "
                                "Chrome. Then every AI tool's \"Continue with Google\" signs you in with one click.")
            self.button(card, "Sign in to Google in Swangz Chrome", self.sign_in_google, primary=True,
                        bg=C["panel"]).pack(anchor="w", pady=(8, 0))
        tiles = tk.Frame(f, bg=C["bg"])
        tiles.pack(fill="x", pady=(0, GAP))
        chrome = self.chrome_line()
        device = st.get("device") or {}
        for i, (title, value, good, action) in enumerate((
                ("Google Chrome", chrome[0], chrome[1], ("Set up", lambda: self.show("workspace")) if not chrome[1] else None),
                ("Sync", f"Last synced {clock(st.get('last_sync'))}", bool(st.get("last_sync")), ("Sync now", self.sync_now)),
                ("This device", ("Company-owned" if device.get("owner_kind") == "company" else "Personal") + " · connected",
                 not st.get("reconnect"), None))):
            tile = self.card(tiles)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
            tiles.grid_columnconfigure(i, weight=1, uniform="tiles")
            self.label(tile, title, 9, color="muted", bg=C["panel"]).pack(anchor="w")
            self.label(tile, ("● " if good else "○ ") + value, 11, color="ok" if good else "gold_hi",
                       bg=C["panel"], wrap=220).pack(anchor="w", pady=(4, 0))
            if action:
                self.button(tile, action[0], action[1], bg=C["panel"]).pack(anchor="w", pady=(8, 0))
        quick = self.quick_tools()
        card = self.section(f, "Quick launch", "Pinned and recent tools. Web tools open in your own Swangz Chrome." if quick
                            else None)
        if quick:
            r = self.row(card)
            for t in quick:
                self.button(r, t["name"], lambda i=t["id"]: self.launch(i), bg=C["panel"]).pack(side="left", padx=(0, 8))
        else:
            self.label(card, "No tools are turned on for you yet. Ask your admin, or press Sync now.", 10, color="muted",
                       bg=C["panel"]).pack(anchor="w", pady=(2, 0))
        agents = [(k, n) for k, n in AGENTS.items() if k in st["installed"]]
        if agents:
            r = self.row(card)
            self.label(r, "Coding agents:", 10, color="muted", bg=C["panel"]).pack(side="left", padx=(0, 10))
            for key, label in agents:
                self.button(r, f"Open {label}", lambda k=key: self.open_agent(k), bg=C["panel"]).pack(side="left", padx=(0, 8))
        card = self.section(f, "Running now")
        launcher = getattr(self.client, "launcher", None)
        window = bool(launcher is not None and launcher.running())
        self.label(card, "Your Swangz Chrome window is open." if window else "No Swangz Chrome window is open.", 10,
                   bg=C["panel"]).pack(anchor="w")
        if self.opened:
            names = ", ".join(dict.fromkeys(n for _, n, _ in reversed(self.opened)))
            self.label(card, f"Opened from Swangz since it started: {names}", 10, color="muted", bg=C["panel"],
                       wrap=640).pack(anchor="w", pady=(4, 0))
        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(anchor="w", pady=(2, 0))
        if st.get("update_available"):
            self.label(bar, "A newer version of Swangz is available.", color="gold_hi").pack(side="left")

    def chrome_line(self):
        """(words, good) for Google Chrome: the last publisher check if there was one, else presence at its fixed place."""
        seen = self.chrome_seen
        if seen is not None:
            return ("Installed and checked", True) if seen.get("ok") else ("Not set up yet", False)
        try:
            found = self.client.native.chrome()
        except Exception:  # noqa: BLE001
            found = {"state": "missing"}
        return ("Found on this computer", True) if found.get("state") == "installed" else ("Not installed", False)

    # ---- Apps: the library

    def prefs(self):
        try:
            data = json.loads((self._data() / PREFS).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _data(self):
        from pathlib import Path
        return Path(self.client.paths.data)

    def pinned(self):
        pins = self.prefs().get("pinned")
        return [p for p in pins if isinstance(p, str)] if isinstance(pins, list) else []

    def toggle_pin(self, tool_id):
        pins = self.pinned()
        pins = [p for p in pins if p != tool_id] if tool_id in pins else (pins + [tool_id])[-12:]
        try:
            core.write_private(self._data() / PREFS, json.dumps({**self.prefs(), "pinned": pins}))
        except OSError as exc:
            return self.say(f"Couldn't save that: {exc}", bad=True)
        self.show(self.page)

    def tools(self):
        try:
            return self.client.tools()
        except Exception:  # noqa: BLE001
            return [{"id": a["id"], "name": a["name"], "kind": "site", "category": a.get("category", "")}
                    for a in self.client.apps()]

    def quick_tools(self, limit=6):
        tools = {t["id"]: t for t in self.tools()}
        order = list(self.pinned())
        try:
            order += [tool for _, tool, _ in native_apps.recent_opens(self.client.paths.data, 30)]
        except Exception:  # noqa: BLE001
            pass
        order += list(tools)
        return [tools[i] for i in dict.fromkeys(order) if i in tools][:limit]

    def web_app(self, tool_id):
        return next((a for a in self.client.apps() if a["id"] == tool_id), None)

    def page_apps(self):
        f = self.content
        head = tk.Frame(f, bg=C["bg"])
        head.pack(fill="x")
        self.label(head, "Apps", 22, bold=True).pack(side="left")
        self.button(head, "Re-check", self.recheck_apps).pack(side="right")
        self.label(f, "Every AI tool your company has given you. Web tools open in your own Swangz Chrome. Desktop and "
                      "command-line apps install from their publisher, and only when you say so.", 10, color="muted",
                   wrap=680).pack(anchor="w", pady=(6, 16))
        self.repair_panel(f)
        tools = self.tools()
        if not tools:
            self.label(f, "Nothing here yet. Press Sync now in Settings, or ask your admin.", color="muted").pack(anchor="w")
        system, pins = native_apps.os_key(), self.pinned()
        agents = set(self.client.status()["installed"]) & set(AGENTS)
        for t in tools:
            self.app_card(f, t, system, pins, agents)

    def app_card(self, parent, tool, system, pins, agents=()):
        tool_id, app = tool["id"], self.web_app(tool["id"])
        w = native_apps.way(tool_id, system)
        card = self.card(parent)
        card.pack(fill="x", pady=(0, 8))
        top = tk.Frame(card, bg=C["panel"])
        top.pack(fill="x")
        self.label(top, tool["name"], 12, bold=True, bg=C["panel"]).pack(side="left")
        for word in native_apps.badges(tool_id, system, app is not None):
            self.badge(top, word).pack(side="left", padx=(8, 0))
        if app is not None:
            self.label(card, app_note(self.client, app), 9, color="muted", bg=C["panel"], wrap=640).pack(anchor="w", pady=(4, 0))
        found = None
        if w.method != native_apps.WEB:
            found = self.client.native.detect(tool_id)
            if tool_id in self.pending and found.get("state") != "installed":
                found = dict(found, state="installing")
            self.label(card, native_words(tool_id, found), 9, color="ok" if found.get("state") == "installed" else "muted",
                       bg=C["panel"], wrap=640).pack(anchor="w", pady=(2, 0))
        elif app is None and tool_id not in agents:
            self.label(card, "Swangz installs and opens this one on Windows and macOS." if system == "linux" else
                       "Opens outside Swangz. Ask your admin how your company uses it.", 9, color="muted",
                       bg=C["panel"], wrap=640).pack(anchor="w", pady=(4, 0))
        note = (app or {}).get("account_note")
        if isinstance(note, str) and note.strip():
            self.label(card, note.strip()[:300], 9, color="muted", bg=C["panel"], wrap=640).pack(anchor="w", pady=(2, 0))
        r = self.row(card)
        if app is not None:
            self.button(r, "Open in Swangz Chrome", lambda i=tool_id: self.open_app(i), bg=C["panel"]).pack(side="left", padx=(0, 8))
        if tool_id in agents:  # Claude Code / Codex set up by Swangz: run through the company gateway (agents.py)
            self.button(r, f"Open {AGENTS[tool_id]}", lambda k=tool_id: self.open_agent(k), bg=C["panel"]).pack(side="left", padx=(0, 8))
        if found is not None:
            state = found.get("state")
            if state == "installed" and w.method == native_apps.NATIVE:
                self.button(r, "Open desktop app", lambda i=tool_id: self.launch_native(i), bg=C["panel"]).pack(side="left", padx=(0, 8))
            if state in ("missing", "failed", "unknown") and self.client.native.plan(tool_id) is not None:
                self.button(r, "Install", lambda i=tool_id: self.install_native(i), bg=C["panel"]).pack(side="left", padx=(0, 8))
            if state in ("installed", "failed"):
                self.button(r, "Repair", lambda i=tool_id: self.install_native(i, "repair"), bg=C["panel"]).pack(side="left", padx=(0, 8))
        self.button(r, "Unpin" if tool_id in pins else "Pin to Home", lambda i=tool_id: self.toggle_pin(i),
                    bg=C["panel"]).pack(side="right")

    # ---- Workspace: the Swangz Chrome profile

    def page_workspace(self):
        f = self.content
        self.heading(f, "Workspace", "Your own Swangz Chrome: a separate Chrome folder that only you use on this computer. "
                                     "Your sign-ins to AI tools stay in it between sessions. Open several tools at once: "
                                     "each one joins the same Swangz Chrome.")
        self.repair_panel(f)
        card = self.section(f, "Google Chrome")
        seen = self.chrome_seen
        if seen is None:
            self.label(card, "Checking Google Chrome on this computer…", 10, color="muted", bg=C["panel"]).pack(anchor="w")
            if time.monotonic() - self._chrome_checked_at > 1:
                self._chrome_checked_at = time.monotonic()
                self.root.after_idle(self.check_chrome)  # after this page is drawn: its answer redraws the page
        elif seen.get("ok"):
            self.label(card, "● Installed, and checked: published by Google.", 10, color="ok", bg=C["panel"]).pack(anchor="w")
            self.label(card, seen.get("path") or "", 9, color="muted", bg=C["panel"], wrap=640).pack(anchor="w", pady=(2, 0))
        else:
            self.label(card, "Swangz opens web AI tools in Google Chrome, which isn't set up on this computer yet.", 10,
                       bg=C["panel"], wrap=640).pack(anchor="w")
            if seen.get("why"):
                self.label(card, f"Why: {seen['why']}", 9, color="muted", bg=C["panel"], wrap=640).pack(anchor="w", pady=(2, 0))
            for n, step in enumerate(("Press Install Google Chrome. It uses Google's own installer or download page.",
                                      "Finish the install, then come back to this window.",
                                      "Swangz checks Chrome again by itself, or press Re-check."), 1):
                self.label(card, f"{n}. {step}", 10, color="muted", bg=C["panel"], wrap=640).pack(anchor="w")
            r = self.row(card)
            self.button(r, "Install Google Chrome", self.install_chrome, primary=True).pack(side="left", padx=(0, 8))
            self.button(r, "Re-check", self.check_chrome, bg=C["panel"]).pack(side="left")
        email = (self.client.status().get("person") or {}).get("email") or ""
        card = self.section(f, "Your Swangz Google account", "Sign in to Google once in your Swangz Chrome with the same "
                            "Swangz account you use for the Hub. Every AI tool's \"Continue with Google\" then uses it, "
                            "and it stays signed in after a restart. Type your password only on Google's page; Swangz "
                            "never sees it.")
        if email:
            self.label(card, email, 11, bold=True, bg=C["panel"]).pack(anchor="w", pady=(6, 0))
            done = self.google_signin_opened()
            self.button(card, "Sign in again" if done else "Sign in to Google in Swangz Chrome", self.sign_in_google,
                        primary=not done, bg=C["panel"]).pack(anchor="w", pady=(8, 0))
            if done:
                self.label(card, f"Google's sign-in was opened here on {clock(done)}.", 9, color="muted",
                           bg=C["panel"]).pack(anchor="w", pady=(4, 0))
                card = self.section(f, "Your profile folder", "Provider and Google sign-ins you make in Swangz Chrome are kept here, "
                                                      "only for you. Swangz never copies or uploads them.")
        self.label(card, str(profiles_folder(self.client.paths.data)), 10, bg=C["panel"], wrap=640).pack(anchor="w")
        card = self.section(f, "Open windows")
        launcher = getattr(self.client, "launcher", None)
        window = bool(launcher is not None and launcher.running())
        self.label(card, "Your Swangz Chrome window is open." if window else "No Swangz Chrome window is open. Open a "
                   "tool from Apps or Home to start one.", 10, bg=C["panel"], wrap=640).pack(anchor="w")
        # Only the Hub's account pages (shell.HUB_PAGES): its tool pages would open tools outside Swangz Chrome.
        card = self.section(f, "Swangz AI Hub", "Your devices and reports in the Hub. It opens in your usual browser; "
                                                "sign in there with your company account. Open AI tools from here, not "
                                                "from the Hub, so they stay in your Swangz Chrome.")
        r = self.row(card)
        self.button(r, "Open Swangz AI Hub", lambda: self.open_hub("devices"), bg=C["panel"]).pack(side="left")

    def check_chrome(self):
        """Google Chrome at its fixed place, and its publisher (D-026 A2-A4), off the window's thread."""
        self._chrome_checked_at = time.monotonic()

        def done(ok, value):
            self.chrome_seen = value if ok and isinstance(value, dict) else {"ok": False, "path": "", "why": ""}
            if self.page in ("workspace", "home"):
                said, color = self.statusbar.cget("text"), self.statusbar.cget("fg")
                self.show(self.page)  # the redraw clears the status line: keep what it said (an install's outcome)
                self.statusbar.configure(text=said, fg=color)

        self.work(self.client.chrome_status, done)

    def install_chrome(self):
        """Windows company build: the elevated, Google-only install (D-026 B5) after the person agrees. Anywhere else:
        Google's own Chrome page; the window checks again when the person comes back."""
        from . import chrome_install
        if sys.platform not in ("win32", "cygwin"):
            self.repair_action(repair.CHROME, None)
            self.say(chrome_install.MESSAGES["mac_page" if sys.platform == "darwin" else "linux"])
            self.chrome_seen = {"ok": False, "path": "", "why": ""}
            return
        self.say("Setting up Google Chrome…")

        def done(ok, value):
            code, message = value if ok else ("failed", chrome_install.MESSAGES["failed"])
            if code == "ask_admin" and not self.client.company_device():
                self.repair_action(repair.CHROME, None)  # a personal computer may use Chrome from Google's page (A4)
                message = "Opened Google's Chrome page. Install Chrome from there, then come back here."
            self.say(message, bad=code not in ("installed",))
            self.check_chrome()

        self.work(lambda: chrome_install.request_install(consent=lambda text: self.ask("Install Google Chrome", text)), done)

    # ---- Automations: packages and coding agents

    def page_automations(self):
        f, st = self.content, self.client.status()
        head = tk.Frame(f, bg=C["bg"])
        head.pack(fill="x")
        self.label(head, "Automations", 22, bold=True).pack(side="left")
        self.button(head, "Sync all", self.sync_now, primary=True).pack(side="right")
        self.label(f, "Coding agents and packages your company has made available. The company decides this list; it "
                      "updates here by itself.", 10, color="muted", wrap=680).pack(anchor="w", pady=(6, 16))
        agents = [(k, n) for k, n in AGENTS.items() if k in st["installed"]]
        card = self.section(f, "Coding agents", "They run in a terminal window. Everything they send to AI goes through "
                                                "the company gateway." if agents else None)
        if agents:
            r = self.row(card)
            for key, name in agents:
                self.button(r, f"Open {name}", lambda k=key: self.open_agent(k), bg=C["panel"]).pack(side="left", padx=(0, 8))
        else:
            self.label(card, "None have been set up for you. Ask your admin, or press Sync all.", 10, color="muted",
                       bg=C["panel"]).pack(anchor="w")
        self.label(f, "Packages", 13, bold=True).pack(anchor="w", pady=(4, 8))
        rows = self.client.packages()
        if not rows:
            self.label(f, "Nothing has been offered to you yet.", color="muted").pack(anchor="w")
        for r in rows:
            row = self.card(f)
            row.pack(fill="x", pady=(0, 8))
            text = tk.Frame(row, bg=C["panel"])
            text.pack(side="left", fill="x", expand=True)
            self.label(text, f"{r['name']}   {r['version']}", 12, bold=True, bg=C["panel"]).pack(anchor="w")
            self.label(text, r["description"], 9, color="muted", bg=C["panel"], wrap=520).pack(anchor="w")
            self.label(text, STATE_WORDS.get(r["state"], r["state"]) + (f" ({r['installed_version']})" if r["state"] == "update" else ""), 9,
                       color="ok" if r["state"] == "installed" else "gold_hi", bg=C["panel"]).pack(anchor="w")
            if r["state"] == "installed":
                self.button(row, "Remove", lambda i=r["id"]: self.remove_package(i), bg=C["panel"]).pack(side="right")
            else:
                self.button(row, "Update" if r["state"] == "update" else "Install", self.sync_now, bg=C["panel"]).pack(side="right")

    # ---- Usage: this device's recent opens

    def page_usage(self):
        f = self.content
        self.heading(f, "Usage", "What you opened from Swangz on this computer. This list stays on this computer; "
                                 "Swangz AI Hub keeps the company's own record of opens.")
        card = self.section(f, "Weekly report", "Tell the company what you used each tool for this week.")
        r = self.row(card)
        self.button(r, "Open weekly reports", lambda: self.open_hub("weekly"), bg=C["panel"]).pack(side="left")
        names = {t["id"]: t["name"] for t in self.tools()}
        try:
            recent = native_apps.recent_opens(self.client.paths.data, 200)
        except Exception:  # noqa: BLE001
            recent = []
        week = time.time() - 7 * 86400
        counts = {}
        for ts, tool, _ in recent:
            if ts >= week:
                counts[tool] = counts.get(tool, 0) + 1
        card = self.section(f, "This week")
        if counts:
            for tool, n in sorted(counts.items(), key=lambda kv: -kv[1])[:10]:
                self.fact(card, names.get(tool, tool), f"opened {n} time{'s' if n != 1 else ''}")
        else:
            self.label(card, "Nothing opened from Swangz on this computer this week.", 10, color="muted", bg=C["panel"]).pack(anchor="w")
        card = self.section(f, "Recent")
        if recent:
            for ts, tool, how in recent[:15]:
                self.fact(card, when(ts), f"{names.get(tool, tool)}  ·  {'Swangz Chrome' if how == 'web' else 'desktop app'}")
        else:
            self.label(card, "Nothing yet.", 10, color="muted", bg=C["panel"]).pack(anchor="w")

    # ---- Settings

    def page_settings(self):
        f, st = self.content, self.client.status()
        d = st.get("device") or {}
        person = st.get("person") or {}
        self.heading(f, "Settings")
        card = self.section(f, "This computer")
        self.auto_var = tk.BooleanVar(value=st.get("autostart", False))
        tk.Checkbutton(card, text="Start Swangz when I sign in to this computer", variable=self.auto_var,
                       command=self.toggle_autostart, bg=C["panel"], fg=C["text"], selectcolor=C["raised"],
                       activebackground=C["panel"], activeforeground=C["text"], font=(FONT[0], 10), anchor="w",
                       highlightthickness=0, bd=0).pack(anchor="w")
        r = self.row(card)
        self.label(r, f"Last synced {clock(st.get('last_sync'))}", 10, color="muted", bg=C["panel"]).pack(side="left", padx=(0, 12))
        self.button(r, "Sync now", self.sync_now, bg=C["panel"]).pack(side="left")
        card = self.section(f, "This device")
        for k, v in (("Name", d.get("name")), ("Kind", "Company-owned" if d.get("owner_kind") == "company" else "Personal"),
                     ("Signed in as", f"{person.get('name', '')}  ({person.get('email', '')})"),
                     ("Server", st.get("server")), ("Swangz version", st.get("client_version") or __version__),
                     ("Updates", (st.get("updates") or {}).get("message", "Updates unavailable")),
                     ("Platform signature", (st.get("updates") or {}).get("platform_signature", "not checked")),
                     ("Key storage", st.get("key_storage")), ("Last synced", clock(st.get("last_sync"))),
                     ("Company browser settings", self.policy_words())):
            self.fact(card, k, v)
        if st.get("credential_warning"):
            self.label(f, st["credential_warning"], 10, color="bad", wrap=700).pack(anchor="w", pady=(0, GAP))
        card = self.section(f, "What Swangz records")
        self.label(card, st.get("recording") or "", 10, color="muted", bg=C["panel"], wrap=640).pack(anchor="w")
        card = self.section(f, "Swangz AI Hub", "These pages open in your usual browser. Sign in there as "
                            f"{person.get('email') or 'your company account'}. Connecting this device does not sign you "
                            "into the website. Use your own browser profile and sign out of the Hub when finished.")
        for page, title, note in (
            ("devices", "Open my devices", "Review devices connected to your account."),
            ("admin", "Open control room", "Sign in with an authorized administrator account to manage the Hub."),
        ):
            r = self.row(card)
            self.button(r, title, lambda p=page: self.open_hub(p), bg=C["panel"]).pack(side="left")
            self.label(r, note, 9, color="muted", bg=C["panel"], wrap=420).pack(side="left", padx=(12, 0))
        card = self.section(f, "Sign out")
        r = self.row(card)
        self.button(r, "Sign out and disconnect this device", self.sign_out, danger=True, bg=C["panel"]).pack(side="left")
        self.button(r, REMOVE, self.remove_account, danger=True, bg=C["panel"]).pack(side="left", padx=(12, 0))

    def policy_words(self):
        """Company computers check Chrome's machine policy (D-024); personal ones never do."""
        try:
            report = self.client.policy_report() if hasattr(self.client, "policy_report") else None
        except Exception:  # noqa: BLE001
            report = None
        if report is None:
            return "Not used on this computer" if not self.client.company_device() else "Not checked yet"
        return "In force" if report.get("ok") else "Not in force. Ask your admin"

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
            if self.page in ("home", "apps", "workspace", "automations", "settings", "usage"):
                self.show(self.page)  # redraw first: it clears the status line
            self.say(f"Synced at {clock(time.time())}." if not bad else f"Synced, but {bad[0][0]} needs attention: {bad[0][1]}", bad=bool(bad))

        self.work(self.client.sync, done)

    def remove_package(self, pid):
        if not messagebox.askyesno("Remove", "Remove this from the device? It stays available, and Sync will put it back."):
            return
        self.client.remove_package(pid)
        self.show(self.page)
        self.say("Removed. Sync puts it back if it is still offered to you.")

    def open_agent(self, key):
        short = {"claude-code": "claude", "codex": "codex"}[key]
        if not shell.open_terminal(shell.app_command() + ["run", short]):
            self.say(f"Couldn't open a terminal. In one, run:  swangz run {short}", bad=True)
        else:
            self.opened.append((time.time(), AGENTS[key], "terminal"))
            self.say(f"Opened {short} in a terminal.")

    def launch(self, tool_id):
        """Quick launch: the web tool in Swangz Chrome if it has one, else its desktop app or coding agent."""
        if self.web_app(tool_id) is not None:
            return self.open_app(tool_id)
        w = native_apps.way(tool_id, native_apps.os_key())
        if w.method == native_apps.CLI and tool_id in AGENTS and tool_id in self.client.status()["installed"]:
            return self.open_agent(tool_id)
        if w.method == native_apps.NATIVE and self.client.native.detect(tool_id).get("state") == "installed":
            return self.launch_native(tool_id)
        self.show("apps")
        self.say("Install it here first, then open it.")

    def launch_native(self, tool_id):
        try:
            words = self.client.native.launch(tool_id)
        except LookupError as exc:
            return self.say(str(exc), bad=True)
        name = next((t["name"] for t in self.tools() if t["id"] == tool_id), tool_id)
        self.opened.append((time.time(), name, "desktop"))
        self.say(words)

    def install_native(self, tool_id, action="install"):
        """Install or repair a desktop / command-line app: say exactly what will happen, and only on Yes do it."""
        native = self.client.native
        plan = native.plan(tool_id, action)
        if plan is None:
            return self.say("Nothing to install on this computer: this one opens in Swangz Chrome.")
        if not messagebox.askyesno(f"{'Repair' if action == 'repair' else 'Install'} {plan.name}", native.consent_text(plan)):
            return self.say("Nothing was changed.")
        self.pending.add(tool_id)
        self.say(f"Working on {plan.name}…")
        if self.page == "apps":
            self.show("apps")

        def done(ok, value):
            if plan.kind != "terminal":
                self.pending.discard(tool_id)
            native.forget(tool_id)
            if self.page == "apps":
                self.show("apps")
            if not ok:
                return self.say(f"{plan.name}: {value}", bad=True)
            self.say(value.get("message", ""), bad=value.get("state") == "failed")

        self.work(lambda: native.execute(plan), done)

    def recheck_apps(self, quiet=False, max_age=0):
        """Look again for every desktop and command-line app (after an install outside Swangz, for example)."""
        native = self.client.native
        self._apps_checked_at = time.monotonic()

        def look():  # winget's own list can take seconds: off the window's thread
            native.forget()
            refresh = getattr(native, "refresh_winget", None)
            if refresh is not None:
                refresh(max_age=max_age)

        def done(ok, value):
            for tool_id in list(self.pending):
                if native.detect(tool_id, fresh=True).get("state") == "installed":
                    self.pending.discard(tool_id)
            if self.page == "apps":
                self.show("apps")
            if not quiet:
                self.say(f"Checked again at {clock(time.time())}." if ok else f"Couldn't check: {value}", bad=not ok)

        self.work(look, done)

    def open_app(self, tool_id, check_first=False):
        """Open in the Swangz Chrome window, or say why not and what to do. Never anywhere else. `check_first` (Try
        again) asks the Hub for the current list and workspace state before opening."""
        try:
            if check_first:
                self.client.refresh()
            self.client.open_app(tool_id)
        except Exception as exc:  # noqa: BLE001
            fix = repair.explain(exc)
            if fix is None:
                self.refusal = None
                return self.failed(exc)
            name = next((a["name"] for a in self.client.apps() if a["id"] == tool_id), "This tool")
            self.refusal = (self.page, tool_id, name, fix)
            self.show(self.page)
            return self.say(f"{name} wasn't opened.", bad=True)
        name = next((a["name"] for a in self.client.apps() if a["id"] == tool_id), tool_id)
        self.opened.append((time.time(), name, "web"))
        if self.refusal:
            self.refusal = None
            self.show(self.page)
        self.say("Opened in your Swangz Chrome.")

    def google_signin_opened(self):
        reader = getattr(self.client, "google_signin_opened", None)
        return reader() if callable(reader) else None

    def sign_in_google(self):
        """Google's own sign-in page in the person's Swangz Chrome, their Swangz address filled in (D-029)."""
        try:
            self.client.sign_in_google()
        except Exception as exc:  # noqa: BLE001
            fix = repair.explain(exc)
            if fix is None:
                self.refusal = None
                return self.failed(exc)
            self.refusal = (self.page, "google-signin", "Google sign-in", fix)
            self.show(self.page)
            return self.say("Google's sign-in wasn't opened.", bad=True)
        self.refusal = None
        self.show(self.page)
        self.say("Google's sign-in is open in your Swangz Chrome. Sign in there with your Swangz account.")

    def repair_panel(self, parent):
        """Why the last Open was refused, what to do about it, and the buttons that help."""
        if not self.refusal:
            return
        _, tool_id, name, fix = self.refusal
        card = self.card(parent)
        card.configure(highlightbackground=C["bad"])
        card.pack(fill="x", pady=(0, GAP))
        bg = C["panel"]
        self.label(card, f"{name}: {fix.title}", 13, bold=True, bg=bg, wrap=640).pack(anchor="w")
        self.label(card, fix.message, 10, bg=bg, wrap=640).pack(anchor="w", pady=(4, 6))
        for n, step in enumerate(fix.steps, 1):
            self.label(card, f"{n}. {step}", 10, color="muted", bg=bg, wrap=640).pack(anchor="w")
        row = tk.Frame(card, bg=bg)
        row.pack(anchor="w", pady=(10, 0))
        for i, action in enumerate(fix.actions):
            self.button(row, repair.LABELS[action], lambda a=action, t=tool_id: self.repair_action(a, t),
                        primary=i == 0, bg=bg).pack(side="left", padx=(0, 10))
        self.button(row, "Dismiss", self.dismiss_repair, bg=bg).pack(side="left")

    def repair_action(self, action, tool_id):
        if action == repair.RETRY:
            self.open_app(tool_id, check_first=True)
        elif action == repair.CHROME:  # Google's own download page: a fixed address, never a tool's
            shell.open_url(INSTALL_PAGE)
        elif action == repair.WEEKLY:
            self.open_hub("weekly")

    def dismiss_repair(self):
        self.refusal = None
        self.show(self.page)

    def open_hub(self, page):
        try:
            shell.open_hub(self.client, page)
            self.say("Opened in your browser. Sign in to the Hub there if asked.")
        except Exception as exc:
            self.failed(exc)

    def toggle_autostart(self):
        try:
            shell.set_autostart(self.client.paths, self.auto_var.get())
        except OSError as exc:
            self.say(f"Couldn't change that: {exc}", bad=True)

    def sign_out(self):
        if not messagebox.askyesno("Sign out", "Sign out and disconnect this device?\n\nThe coding agents and packages Swangz "
                                                "installed will be taken off, and the device disconnected.\n\n"
                                                + browser_folders_stay(self.client.paths.data)):
            return
        self.work(self.client.logout, lambda ok, value: (setattr(self, "error", ""), self.show("signin")) if ok else self.failed(value))

    def remove_account(self):
        if not messagebox.askyesno(REMOVE, f"{REMOVE}?\n\nThis signs you out, takes off the coding agents and packages "
                                           "Swangz installed, deletes the browser sign-ins (provider and Google) saved by "
                                           "Swangz on this computer, and stops Swangz starting when you sign in. The app "
                                           "itself stays installed."):
            return
        self.say("Removing…")
        self.work(self.client.cleanup, self._removed)

    def _removed(self, ok, value):
        if not ok:
            return self.failed(value)
        left = [path for path, _ in value["left"]] + value["problems"]
        self.removal_incomplete = bool(left)
        self.error = ""
        if left:
            self.error = ("Swangz was not completely removed. Close any workspace window, then try again. Still here:\n"
                          + "\n".join(left))
        self.show("signin")
        told = "" if value["told"] else " The server couldn't be reached, so ask an admin to disconnect this device."
        if not left:
            self.say("Swangz was removed from this account. You can now uninstall the app, or drag it to the Bin." + told)
        elif told:
            self.say(told.strip(), bad=True)


def main(client=None, background=False):
    client = client or core.Client()
    app = App(client, background=background)
    app.root.mainloop()
    return 0
