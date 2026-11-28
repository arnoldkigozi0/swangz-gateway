"""The Swangz app window: an AI workstation laid out like the web staff app (Swangz AI Hub). A sidebar down the left
(Home · My tools · Sign-ins, then This computer: Workspace · Automations · Activity, then In the Hub: links that open
the Hub's own pages in the person's browser, then Settings and the person) and the page you are on.

Tk, so it is a real window on Windows, macOS and Linux with nothing to install beyond Python. The colours are the web's
design tokens (gateway/static/tokens.css), the tool tiles carry the same logos (logos.py, from the Hub's /icons) and the
"how you sign in" words are the web's (portal.js HOW).

All the work is done by `core.Client` (and its `native` app manager); this file only draws it. Network calls, installs
and Chrome's publisher check run on a worker thread and hand their results back through a queue, so the window never
freezes. Tests drive it with `inline=True`.
"""

import json
import math
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
PREFS = "workstation.json"  # this window's own preferences on this computer (pins, sign-in ticks); nothing secret


def browser_folders_stay(data):
    """Sign out and revocation leave the company-browser folders on disk; say so rather than promise more. The folder
    is named by browser_profiles alone, reached through the launcher (inventory and import guards)."""
    return ("Browser folders that hold your provider and Google sign-ins are not removed. They stay on this device at "
            f"{profiles_folder(data)}. To delete them, choose “{REMOVE}” in Settings, or run swangz cleanup.")


# The web's tokens (gateway/static/tokens.css, dark): near-black neutral surfaces, champagne gold as the brand, an
# off-white solid primary button, mint / sky / coral for states. Every state also carries a word.
C = dict(bg="#0A0A0B", side="#111113", panel="#17171A", raised="#1F1F23", hover="#2B2B31", line="#2A2A2F",
         line_hi="#35353C", text="#F6F6F4", text2="#CEC6BD", muted="#B5ADA5", faint="#5E5E66", gold="#F5B32B",
         gold_hi="#FFC54D", accent="#E5C48C", on_gold="#1A1200", solid="#F2F2F2", on_solid="#0D0D0D", ok="#2FD99A",
         bad="#FF5D52", info="#43B9F5", tile="#FFFFFF")
FONT = ("Segoe UI" if os.name == "nt" else "Helvetica Neue" if sys.platform == "darwin" else "Helvetica", 11)

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
# The pages, in the sidebar's order: the web staff app's first three, then this computer's own.
PAGES = (("home", "Home"), ("apps", "My tools"), ("accounts", "Sign-ins"), ("workspace", "Workspace"),
         ("automations", "Automations"), ("usage", "Activity"), ("settings", "Settings"))
MAIN_PAGES = ("home", "apps", "accounts")
COMPUTER_PAGES = ("workspace", "automations", "usage")
# The sidebar's "In the Hub" links: the Hub's own pages (shell.HUB_PAGES), opened in the person's usual browser.
HUB_LINKS = (("weekly", "Weekly reports"), ("requests", "Requests"), ("devices", "My devices"))
STATE_WORDS = {"installed": "Installed", "update": "Update ready", "available": "Not installed"}
AGENTS = {"claude-code": "Claude Code", "codex": "Codex"}
GAP = 14
LOGO = 44  # the web's .logo tile; the picture inside is 70% of it

# How a tool lets you in (the web staff app's words, portal.js HOW), and what to do on this computer.
HOW = {
    "sso": ("Company sign-in", "Opens with your Swangz work account — no separate password."),
    "seat": ("Company seat", "Your own seat on the company plan. Sign in with your work email; Swangz pays one bill."),
    "own": ("Your own login", "You use your own account for this one. Swangz still controls access to it."),
    "api": ("Company key", "Runs on the company's key through Swangz AI Hub — nothing to sign in to."),
    "shared": ("Company account", "One login the company pays for. The provider may not let several people use it at "
                                  "once; if it's busy or asks you to sign in, ask your admin for a seat of your own."),
}
# The Sign-ins page groups, in order: (sign-in kind, heading, steps with {email} filled in).
SIGNIN_GROUPS = (
    ("sso", "Continue with Google", ("Press Sign in: the tool opens in your Swangz Chrome.",
                                     "On its page choose Continue with Google (or Sign in with Google).",
                                     "Pick {email}. There is no password to type.")),
    ("seat", "Your company seat", ("Your admin adds {email} to the company plan, and the provider emails you an "
                                   "invitation. Accept it.",
                                   "Press Sign in and sign in with {email}.",
                                   "No invitation yet? Press Ask for a seat.")),
    ("own", "Your own login", ("Press Sign in and use your own account for this tool.",)),
    ("shared", "Company account", ("Press Sign in. If the tool asks for the company login or says it's busy, ask your "
                                   "admin for a seat of your own.",)),
)
# Brand colours for monograms when the Hub sent none (tokens.css data palette).
MONO = ("#3F3027", "#1F4E79", "#5B3A8C", "#16695A", "#8C3A2B", "#2D5F2E", "#7A5A12", "#3A4A5C")


def clock(ts):
    return time.strftime("%H:%M", time.localtime(ts)) if ts else "never"


def when(ts):
    return time.strftime("%a %d %b, %H:%M", time.localtime(ts)) if ts else "never"


def initials(name):
    words = [w for w in str(name or "").replace("-", " ").split() if w[:1].isalnum()]
    if not words:
        return "?"
    return (words[0][0] + (words[1][0] if len(words) > 1 else words[0][1:2])).upper()


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
        self._images = {}  # (tool id, size) -> PhotoImage, kept so Tk doesn't drop them
        self._logos_fetched = False
        self.query = tk.StringVar(master=self.root, value="")
        self.category = "All"
        self.tool_list = None
        self.root.title("Swangz AI Hub")
        self.root.geometry("1120x740")
        self.root.minsize(780, 540)
        self.root.configure(bg=C["bg"])
        self._styles()
        self.dock = tk.Frame(self.root, bg=C["side"], width=236)
        self.dock.pack(side="left", fill="y")
        self.dock.pack_propagate(False)
        tk.Frame(self.root, bg=C["line"], width=1).pack(side="left", fill="y")
        self.body = tk.Frame(self.root, bg=C["bg"])
        self.body.pack(side="left", fill="both", expand=True)
        self.statusbar = tk.Label(self.body, text="", anchor="w", bg=C["bg"], fg=C["muted"], font=(FONT[0], 9), padx=28, pady=8)
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
        self._window = self.canvas.create_window((36, 28), window=self.content, anchor="nw")
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=(0, 0, e.width + 72, e.height + 56)))
        self.canvas.bind("<Configure>", self._resized)
        self._drawn_width = 0
        self._redraw_after = None
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
        s.configure("TEntry", fieldbackground=C["raised"], foreground=C["text"], insertcolor=C["text"], bordercolor=C["line_hi"],
                    lightcolor=C["line_hi"], darkcolor=C["line_hi"], padding=6)
        s.map("TEntry", bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent"])], darkcolor=[("focus", C["accent"])])
        s.configure("Vertical.TScrollbar", background=C["raised"], troughcolor=C["bg"], bordercolor=C["bg"], arrowcolor=C["muted"])

    def _resized(self, event):
        """The page follows the window: tile grids are laid out for a width, so a big change redraws them (once the
        window settles)."""
        self.canvas.itemconfigure(self._window, width=max(event.width - 72, 300))
        if self.page in ("home", "apps", "accounts") and abs(event.width - self._drawn_width) > 120 and self._drawn_width:
            if self._redraw_after is not None:
                self.root.after_cancel(self._redraw_after)
            self._redraw_after = self.root.after(250, self._redraw)

    def _redraw(self):
        self._redraw_after = None
        if self.page in ("home", "apps", "accounts"):
            said, color = self.statusbar.cget("text"), self.statusbar.cget("fg")
            self.show(self.page)
            self.statusbar.configure(text=said, fg=color)

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

    def width(self):
        """The page's usable width now (before the first draw: from the window's own size)."""
        w = self.canvas.winfo_width()
        if w <= 1:
            self.root.update_idletasks()
            w = self.canvas.winfo_width()
        if w <= 1:
            w = max(self.root.winfo_width(), 1120) - 236 - 14
        return max(w - 72, 300)

    def columns(self, tile=240, most=4):
        return max(1, min(most, self.width() // tile))

    # ------------------------------------------------------------ widgets

    def label(self, parent, text, size=11, color="text", bold=False, **kw):
        font = (FONT[0], size, "bold" if bold else "normal")
        return tk.Label(parent, text=text, bg=kw.pop("bg", C["bg"]), fg=C[color], font=font, anchor=kw.pop("anchor", "w"),
                        justify="left", wraplength=kw.pop("wrap", 0), **kw)

    def button(self, parent, text, command, primary=False, danger=False, **kw):
        """The web's buttons: an outline by default, one off-white solid primary per place, danger outlined in coral."""
        surface = kw.pop("bg", C["bg"])  # what the button sits on
        small = kw.pop("small", False)
        fg = C["on_solid"] if primary else (C["bad"] if danger else C["text"])
        bg = C["solid"] if primary else surface
        return make_button(parent, text=text, command=command, font=(FONT[0], 9 if small else 10, "bold" if primary else "normal"),
                           bg=bg, fg=fg, activebackground="#FFFFFF" if primary else C["hover"],
                           activeforeground=C["on_solid"] if primary else fg, relief="flat", bd=0,
                           padx=10 if small else 14, pady=4 if small else 7, cursor="hand2", highlightthickness=1,
                           highlightbackground=C["bad"] if danger else (C["solid"] if primary else C["line_hi"]), **kw)

    def link(self, parent, text, command, bg=None):
        """A quiet text action (the web's .tlink / .hero-link), in champagne."""
        return make_button(parent, text=text, command=command, font=(FONT[0], 10), bg=bg or C["bg"], fg=C["accent"],
                           activebackground=bg or C["bg"], activeforeground=C["gold_hi"], relief="flat", bd=0, padx=0,
                           pady=2, cursor="hand2", highlightthickness=0)

    def card(self, parent, bg=None, **kw):
        return tk.Frame(parent, bg=bg or C["panel"], highlightthickness=1, highlightbackground=C["line"], padx=20, pady=16, **kw)

    def heading(self, parent, title, note=None, actions=()):
        """A page's title line: the title at the left and the page's actions at the right (web rule), the note below."""
        top = tk.Frame(parent, bg=C["bg"])
        top.pack(fill="x")
        self.label(top, title, 24, bold=True).pack(side="left")
        for text, command, primary in reversed(actions):
            self.button(top, text, command, primary=primary).pack(side="right", padx=(8, 0))
        if note:
            self.label(parent, note, 10, color="muted", wrap=min(760, self.width())).pack(anchor="w", pady=(6, 18))
        else:
            tk.Frame(parent, bg=C["bg"], height=16).pack()
        return top

    def section(self, parent, title, note=None, bg=None):
        card = self.card(parent, bg=bg)
        card.pack(fill="x", pady=(0, GAP))
        surface = bg or C["panel"]
        self.label(card, title, 13, bold=True, bg=surface).pack(anchor="w")
        if note:
            self.label(card, note, 10, color="muted", bg=surface, wrap=min(700, self.width() - 60)).pack(anchor="w", pady=(2, 8))
        return card

    def eyebrow(self, parent, text, bg=None):
        """A small upper-case group title (the web's section eyebrows)."""
        return self.label(parent, text.upper(), 8, color="muted", bold=True, bg=bg or C["bg"])

    def row(self, parent, bg=None):
        r = tk.Frame(parent, bg=bg or C["panel"])
        r.pack(anchor="w", fill="x", pady=(10, 0))
        return r

    def badge(self, parent, text, tone="accent", bg=None):
        return tk.Label(parent, text=text, bg=bg or C["raised"], fg=C[tone], font=(FONT[0], 8, "bold"), padx=7, pady=2)

    def fact(self, parent, key, value):
        r = tk.Frame(parent, bg=C["panel"])
        r.pack(fill="x", pady=3)
        self.label(r, key, 10, color="muted", bg=C["panel"], width=20).pack(side="left")
        self.label(r, str(value if value not in (None, "") else "—"), 10, bg=C["panel"], wrap=480).pack(side="left")

    def bar(self, parent, done, total, bg=None, width=280):
        """A slim progress bar: `done` of `total`."""
        c = tk.Canvas(parent, width=width, height=8, bg=bg or C["panel"], highlightthickness=0, bd=0)
        c.create_line(4, 4, width - 4, 4, width=6, fill=C["hover"], capstyle="round")
        if total and done:
            c.create_line(4, 4, 4 + (width - 8) * min(done, total) / total, 4, width=6, fill=C["ok"], capstyle="round")
        return c

    def avatar(self, parent, name, bg, size=34):
        c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        c.create_oval(1, 1, size - 1, size - 1, fill=C["raised"], outline=C["line_hi"])
        c.create_text(size / 2, size / 2, text=initials(name), fill=C["accent"], font=(FONT[0], 10, "bold"))
        return c

    def logo(self, parent, tool, bg, size=LOGO, command=None):
        """The tool's logo on a white rounded tile (the web's .logo), or its monogram on its brand colour."""
        c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        image = self.logo_image(tool["id"], int(size * 0.7))
        r = max(6, size // 4)
        fill = C["tile"] if image else (tool.get("color") or MONO[sum(map(ord, tool["id"])) % len(MONO)])
        x0, y0, x1, y1 = 0, 0, size - 1, size - 1
        points = (x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
                  x0, y1 - r, x0, y0 + r, x0, y0)
        c.create_polygon(points, smooth=True, fill=fill, outline=C["line"] if image else fill)
        if image:
            c.create_image(size / 2, size / 2, image=image)
        else:
            c.create_text(size / 2, size / 2, text=initials(tool.get("name")), fill="#FFFFFF",
                          font=(FONT[0], max(8, size // 3), "bold"))
        if command:
            c.configure(cursor="hand2")
            c.bind("<Button-1>", lambda e: command())
        return c

    def logo_image(self, tool_id, side):
        """The cached logo scaled to about `side` pixels, or None (the window then draws the monogram)."""
        key = (tool_id, side)
        if key in self._images:
            return self._images[key]
        image = None
        logos = getattr(self.client, "logos", None)
        path = logos.path(tool_id) if logos is not None else None
        if path is not None:
            try:
                full = tk.PhotoImage(master=self.root, file=str(path))
                w, h = full.width(), full.height()
                biggest = max(w, h, 1)
                if biggest > side:
                    image = full.subsample(max(1, math.ceil(biggest / side)))
                elif biggest * 2 <= side:
                    image = full.zoom(max(1, side // biggest))
                else:
                    image = full
            except (tk.TclError, OSError):
                image = None
        self._images[key] = image
        return image

    def clear(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    # ------------------------------------------------------------ the sidebar

    def show(self, page):
        self.page = page
        if self.refusal and self.refusal[0] != page:
            self.refusal = None
        self.say("")
        self.clear(self.dock)
        self.clear(self.content)
        self.tool_list = None
        self.canvas.yview_moveto(0)
        self.nav = {}
        self._brand()
        if page != "signin":
            self._sidebar(page)
        getattr(self, "page_" + page)()
        self._drawn_width = max(self.canvas.winfo_width(), 1)

    def _brand(self):
        side = C["side"]
        brand = tk.Frame(self.dock, bg=side)
        brand.pack(fill="x", padx=20, pady=(22, 20))
        mark = tk.Canvas(brand, width=30, height=30, bg=side, highlightthickness=0, bd=0)
        mark.create_rectangle(0, 0, 29, 29, fill=C["gold"], outline=C["gold"])
        mark.create_text(15, 15, text="S", fill=C["on_gold"], font=(FONT[0], 14, "bold"))
        mark.pack(side="left")
        words = tk.Frame(brand, bg=side)
        words.pack(side="left", padx=(10, 0))
        line = tk.Frame(words, bg=side)
        line.pack(anchor="w")
        tk.Label(line, text="Swangz ", bg=side, fg=C["text2"], font=(FONT[0], 12)).pack(side="left")
        tk.Label(line, text="AI Hub", bg=side, fg=C["text"], font=(FONT[0], 12, "bold")).pack(side="left")
        tk.Label(words, text="AI workstation", bg=side, fg=C["faint"], font=(FONT[0], 8), anchor="w").pack(anchor="w")

    def _nav_item(self, key, name, here, count=None):
        side = C["side"]
        item = tk.Frame(self.dock, bg=C["raised"] if here else side)
        item.pack(fill="x", padx=12, pady=1)
        tk.Frame(item, bg=C["accent"] if here else (C["raised"] if here else side), width=3).pack(side="left", fill="y")
        b = make_button(item, text=name, anchor="w", command=lambda k=key: self.show(k), relief="flat", bd=0, padx=14,
                        pady=8, font=(FONT[0], 10, "bold" if here else "normal"), bg=C["raised"] if here else side,
                        fg=C["accent"] if here else C["text2"], activebackground=C["raised"],
                        activeforeground=C["accent"], cursor="hand2", highlightthickness=0)
        b.pack(side="left", fill="x", expand=True)
        if count:
            tk.Label(item, text=str(count), bg=C["gold"], fg=C["on_gold"], font=(FONT[0], 8, "bold"),
                     padx=6).pack(side="right", padx=(0, 10))
        self.nav[key] = b
        return b

    def _sidebar(self, page):
        side = C["side"]
        names = dict(PAGES)
        todo = self.signins_left()
        for key in MAIN_PAGES:
            self._nav_item(key, names[key], key == page, count=todo if key == "accounts" else None)
        self.eyebrow(self.dock, "This computer", bg=side).pack(fill="x", padx=28, pady=(18, 4))
        for key in COMPUTER_PAGES:
            self._nav_item(key, names[key], key == page)
        self.eyebrow(self.dock, "In the Hub · your browser", bg=side).pack(fill="x", padx=28, pady=(18, 4))
        for key, name in HUB_LINKS:
            item = tk.Frame(self.dock, bg=side)
            item.pack(fill="x", padx=12, pady=1)
            tk.Frame(item, bg=side, width=3).pack(side="left", fill="y")
            make_button(item, text=name, anchor="w", command=lambda k=key: self.open_hub(k), relief="flat", bd=0,
                        padx=14, pady=7, font=(FONT[0], 10), bg=side, fg=C["muted"], activebackground=C["raised"],
                        activeforeground=C["text"], cursor="hand2", highlightthickness=0).pack(side="left", fill="x", expand=True)
        st = self.client.status()
        person = st.get("person") or {}
        foot = tk.Frame(self.dock, bg=side)
        foot.pack(side="bottom", fill="x", padx=16, pady=(0, 18))
        who = tk.Frame(foot, bg=side)
        who.pack(side="bottom", fill="x", pady=(12, 0))
        self.avatar(who, person.get("name") or person.get("email"), side).pack(side="left")
        words = tk.Frame(who, bg=side)
        words.pack(side="left", padx=(10, 0), fill="x")
        tk.Label(words, text=person.get("name") or "", bg=side, fg=C["text"], font=(FONT[0], 9, "bold"), anchor="w",
                 wraplength=160, justify="left").pack(anchor="w")
        tk.Label(words, text=(st.get("device") or {}).get("name") or person.get("email") or "", bg=side, fg=C["faint"],
                 font=(FONT[0], 8), anchor="w", wraplength=160, justify="left").pack(anchor="w")
        tk.Frame(foot, bg=C["line"], height=1).pack(side="bottom", fill="x", pady=(10, 0))
        holder = tk.Frame(self.dock, bg=side)
        holder.pack(side="bottom", fill="x")
        self.dock_bottom = holder
        here = page == "settings"
        item = tk.Frame(holder, bg=C["raised"] if here else side)
        item.pack(fill="x", padx=12)
        tk.Frame(item, bg=C["accent"] if here else side, width=3).pack(side="left", fill="y")
        b = make_button(item, text=names["settings"], anchor="w", command=lambda: self.show("settings"), relief="flat",
                        bd=0, padx=14, pady=8, font=(FONT[0], 10, "bold" if here else "normal"),
                        bg=C["raised"] if here else side, fg=C["accent"] if here else C["text2"],
                        activebackground=C["raised"], activeforeground=C["accent"], cursor="hand2", highlightthickness=0)
        b.pack(side="left", fill="x", expand=True)
        self.nav["settings"] = b

    # ------------------------------------------------------------ sign in (to the Hub)

    def page_signin(self):
        f = self.content
        self.label(f, "Connect this device", 24, bold=True).pack(anchor="w")
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
        box = self.card(f)
        box.pack(anchor="w", fill="x")
        self.server_var = tk.StringVar(value=os.environ.get("SWANGZ_SERVER") or core.DEFAULT_SERVER)
        self.name_var = tk.StringVar(value=core.device_name())
        for text, var in (("Swangz AI Hub address", self.server_var), ("Name for this device", self.name_var)):
            self.label(box, text, 10, color="muted", bg=C["panel"]).pack(anchor="w")
            ttk.Entry(box, textvariable=var, width=46, font=FONT).pack(anchor="w", pady=(2, 14), ipady=4)
        self.signin_button = self.button(box, "Sign in", self.sign_in, primary=True)
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

    # ------------------------------------------------------------ Home: the launchpad

    def page_home(self):
        f, st = self.content, self.client.status()
        name = (st.get("person") or {}).get("name") or ""  # the whole name: which part is the "first" one is not ours to guess
        hour = time.localtime().tm_hour
        self.heading(f, f"Good {'morning' if hour < 12 else 'afternoon' if hour < 18 else 'evening'}{', ' + name if name else ''}",
                     f"Your AI workstation  ·  signed in to {st.get('server') or ''}", actions=(("Sync now", self.sync_now, False),))
        if st.get("reconnect"):
            self.label(f, core.RECONNECT, 10, color="bad", wrap=700).pack(anchor="w", pady=(0, 10))
            self.button(f, "Reconnect this device", self.sign_out).pack(anchor="w", pady=(0, GAP))
        self.repair_panel(f)
        self.hero(f, st)
        tiles = tk.Frame(f, bg=C["bg"])
        tiles.pack(fill="x", pady=(0, GAP))
        chrome = self.chrome_line()
        device = st.get("device") or {}
        google = self.google_signin_opened()
        stats = [("Google Chrome", chrome[0], chrome[1], ("Set up", lambda: self.show("workspace")) if not chrome[1] else None),
                 ("Your Google account", "Sign-in opened " + clock(google) if google else "Not signed in yet", bool(google),
                  None if google else ("Sign-ins", lambda: self.show("accounts"))),
                 ("Sync", f"Last synced {clock(st.get('last_sync'))}", bool(st.get("last_sync")), None),
                 ("This device", ("Company-owned" if device.get("owner_kind") == "company" else "Personal") + " · connected",
                  not st.get("reconnect"), None)]
        cols = 4 if self.width() >= 760 else 2
        for i, (title, value, good, action) in enumerate(stats):
            tile = self.card(tiles)
            tile.grid(row=i // cols, column=i % cols, sticky="nsew", padx=(0 if i % cols == 0 else 10, 0), pady=(0, 10))
            tiles.grid_columnconfigure(i % cols, weight=1, uniform="tiles")
            self.label(tile, title, 9, color="muted", bold=True, bg=C["panel"]).pack(anchor="w")
            self.label(tile, ("● " if good else "○ ") + value, 11, color="ok" if good else "gold_hi",
                       bg=C["panel"], wrap=200).pack(anchor="w", pady=(6, 0))
            if action:
                self.button(tile, action[0], action[1], bg=C["panel"], small=True).pack(anchor="w", pady=(10, 0))
        quick = self.quick_tools(8)
        card = self.section(f, "Quick launch", "Pinned and recent tools. Web tools open in your own Swangz Chrome." if quick else None)
        if quick:
            self.tile_grid(card, quick)
            self.link(card, "All your tools  ›", lambda: self.show("apps"), bg=C["panel"]).pack(anchor="w", pady=(12, 0))
        else:
            self.label(card, "No tools are turned on for you yet. Ask your admin, or press Sync now.", 10, color="muted",
                       bg=C["panel"]).pack(anchor="w", pady=(2, 0))
        agents = [(k, n) for k, n in AGENTS.items() if k in st["installed"]]
        if agents:
            r = self.row(card)
            self.label(r, "Coding agents:", 10, color="muted", bg=C["panel"]).pack(side="left", padx=(0, 10))
            for key, label in agents:
                self.button(r, f"Open {label}", lambda k=key: self.open_agent(k), bg=C["panel"]).pack(side="left", padx=(0, 8))
        two = tk.Frame(f, bg=C["bg"])
        two.pack(fill="x")
        two.grid_columnconfigure(0, weight=1, uniform="two")
        two.grid_columnconfigure(1, weight=1, uniform="two")
        left, right = self.card(two), self.card(two)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right.grid(row=0, column=1, sticky="nsew")
        self.label(left, "Running now", 13, bold=True, bg=C["panel"]).pack(anchor="w")
        launcher = getattr(self.client, "launcher", None)
        window = bool(launcher is not None and launcher.running())
        self.label(left, "Your Swangz Chrome window is open." if window else "No Swangz Chrome window is open.", 10,
                   bg=C["panel"], wrap=320).pack(anchor="w", pady=(6, 0))
        if self.opened:
            names = ", ".join(dict.fromkeys(n for _, n, _ in reversed(self.opened)))
            self.label(left, f"Opened from Swangz since it started: {names}", 10, color="muted", bg=C["panel"],
                       wrap=320).pack(anchor="w", pady=(4, 0))
        self.label(right, "In the Hub", 13, bold=True, bg=C["panel"]).pack(anchor="w")
        self.label(right, "These open in your usual browser.", 9, color="muted", bg=C["panel"]).pack(anchor="w", pady=(2, 6))
        for key, title in (("weekly", "Weekly reports"), ("requests", "Access requests"), ("devices", "My devices"),
                           ("privacy", "How Swangz AI Hub works")):
            self.link(right, title + "  ›", lambda k=key: self.open_hub(k), bg=C["panel"]).pack(anchor="w")
        if st.get("update_available"):
            self.label(f, "A newer version of Swangz is available.", color="gold_hi").pack(anchor="w", pady=(GAP, 0))

    def hero(self, f, st):
        """The web's state-aware hero: one thing to do next, with its one action."""
        email = (st.get("person") or {}).get("email") or ""
        hero = tk.Frame(f, bg=C["raised"], highlightthickness=1, highlightbackground=C["line_hi"], padx=24, pady=20)
        hero.pack(fill="x", pady=(0, GAP))
        tk.Frame(hero, bg=C["gold"], height=2).pack(fill="x", pady=(0, 14))
        bg = C["raised"]
        need = self.signin_rows()
        done = sum(1 for _, _, signed in need if signed)
        if email and not self.google_signin_opened():
            self.eyebrow(hero, "Step 1 of 2", bg=bg).pack(anchor="w")
            self.label(hero, "Sign in to Google once", 18, bold=True, bg=bg).pack(anchor="w", pady=(2, 4))
            self.label(hero, f"Sign in with your Swangz account ({email}) in your Swangz Chrome. Then every AI tool's "
                             "\"Continue with Google\" signs you in with one click.", 10, color="text2", bg=bg,
                       wrap=min(700, self.width() - 60)).pack(anchor="w")
            r = tk.Frame(hero, bg=bg)
            r.pack(anchor="w", pady=(14, 0))
            self.button(r, "Sign in to Google in Swangz Chrome", self.sign_in_google, primary=True, bg=bg).pack(side="left")
            self.link(r, "   How sign-in works  ›", lambda: self.show("accounts"), bg=bg).pack(side="left")
        elif need and done < len(need):
            self.eyebrow(hero, "Step 2 of 2", bg=bg).pack(anchor="w")
            self.label(hero, "Sign in to your paid tools", 18, bold=True, bg=bg).pack(anchor="w", pady=(2, 4))
            self.label(hero, f"{done} of {len(need)} tools signed in. Sign in once on each tool's own page in your Swangz "
                             "Chrome; it keeps you signed in.", 10, color="text2", bg=bg, wrap=min(700, self.width() - 60)).pack(anchor="w")
            self.bar(hero, done, len(need), bg=bg).pack(anchor="w", pady=(10, 0))
            self.button(hero, "Go to Sign-ins", lambda: self.show("accounts"), primary=True, bg=bg).pack(anchor="w", pady=(14, 0))
        else:
            tools = self.tools()
            last = self.quick_tools(1)
            self.eyebrow(hero, "Ready", bg=bg).pack(anchor="w")
            self.label(hero, f"{len(tools)} tool{'s' if len(tools) != 1 else ''} ready for you" if tools else
                       "No tools yet", 18, bold=True, bg=bg).pack(anchor="w", pady=(2, 4))
            self.label(hero, "Everything you open from here stays signed in, in your own Swangz Chrome." if tools else
                       "Ask your admin for the tools you need, then press Sync now.", 10, color="text2", bg=bg).pack(anchor="w")
            r = tk.Frame(hero, bg=bg)
            r.pack(anchor="w", pady=(14, 0))
            if last:
                self.button(r, f"Open {last[0]['name']}", lambda i=last[0]["id"]: self.launch(i), primary=True, bg=bg).pack(side="left")
            self.link(r, "   All your tools  ›", lambda: self.show("apps"), bg=bg).pack(side="left")

    def tile_grid(self, parent, tools):
        """Tool tiles in a grid: the logo, the name (the tile's button) and the category, like the web's launchpad."""
        grid = tk.Frame(parent, bg=C["panel"])
        grid.pack(fill="x", pady=(4, 0))
        cols = self.columns(190, 4)
        for i, t in enumerate(tools):
            tile = tk.Frame(grid, bg=C["raised"], highlightthickness=1, highlightbackground=C["line"], padx=12, pady=12)
            tile.grid(row=i // cols, column=i % cols, sticky="nsew", padx=(0 if i % cols == 0 else 8, 0), pady=(0, 8))
            grid.grid_columnconfigure(i % cols, weight=1, uniform="quick")
            self.logo(tile, t, C["raised"], 36, command=lambda i=t["id"]: self.launch(i)).pack(side="left")
            words = tk.Frame(tile, bg=C["raised"])
            words.pack(side="left", padx=(10, 0), fill="x", expand=True)
            make_button(words, text=t["name"], command=lambda i=t["id"]: self.launch(i), anchor="w", relief="flat", bd=0,
                        padx=0, pady=0, font=(FONT[0], 10, "bold"), bg=C["raised"], fg=C["text"],
                        activebackground=C["raised"], activeforeground=C["accent"], cursor="hand2",
                        highlightthickness=0).pack(anchor="w")
            self.label(words, t.get("category") or self.how(t)[0], 8, color="muted", bg=C["raised"]).pack(anchor="w")

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

    # ------------------------------------------------------------ preferences on this computer

    def prefs(self):
        try:
            data = json.loads((self._data() / PREFS).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _data(self):
        from pathlib import Path
        return Path(self.client.paths.data)

    def _save_prefs(self, **changes):
        try:
            core.write_private(self._data() / PREFS, json.dumps({**self.prefs(), **changes}))
        except OSError as exc:
            self.say(f"Couldn't save that: {exc}", bad=True)
            return False
        return True

    def pinned(self):
        pins = self.prefs().get("pinned")
        return [p for p in pins if isinstance(p, str)] if isinstance(pins, list) else []

    def toggle_pin(self, tool_id):
        pins = self.pinned()
        pins = [p for p in pins if p != tool_id] if tool_id in pins else (pins + [tool_id])[-12:]
        if self._save_prefs(pinned=pins):
            self.show(self.page)

    def signed_marks(self):
        """{tool id: when} the person ticked "I'm signed in". Their own note on this computer: Swangz never reads the
        browser folder's cookies to find out."""
        marks = self.prefs().get("signed_in")
        if not isinstance(marks, dict):
            return {}
        return {k: v for k, v in marks.items() if isinstance(k, str) and isinstance(v, (int, float))}

    def mark_signed(self, tool_id, on=True):
        marks = self.signed_marks()
        if on:
            marks[tool_id] = time.time()
        else:
            marks.pop(tool_id, None)
        if self._save_prefs(signed_in=marks):
            self.show(self.page)
            self.say("Marked as signed in." if on else "Marked as not signed in yet.")

    # ------------------------------------------------------------ tools

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

    def signin_kind(self, tool):
        """How the person gets into `tool`: the website entry's sign-in, else the tool's, else by its kind."""
        app = self.web_app(tool["id"]) or {}
        if tool.get("kind") == "dev":
            return "api"
        kind = app.get("signin") or tool.get("signin")
        if kind in HOW:
            return kind
        return "api" if tool.get("kind") == "api" and not app else "seat"

    def how(self, tool):
        return HOW[self.signin_kind(tool)]

    def signin_rows(self):
        """[(tool, kind, signed)] for every tool that needs a sign-in of its own (everything but Company key)."""
        marks = self.signed_marks()
        return [(t, k, t["id"] in marks) for t in self.tools() for k in (self.signin_kind(t),) if k != "api"]

    def signins_left(self):
        try:
            return sum(1 for _, _, signed in self.signin_rows() if not signed)
        except Exception:  # noqa: BLE001 — a count on the sidebar never breaks the window
            return 0

    # ---- My tools: the library

    def page_apps(self):
        f = self.content
        self.heading(f, "My tools", "Every AI tool your company has given you. Web tools open in your own Swangz Chrome. "
                                    "Desktop and command-line apps install from their publisher, and only when you say so.",
                     actions=(("Re-check", self.recheck_apps, False),))
        self.repair_panel(f)
        tools = self.tools()
        if not tools:
            self.label(f, "Nothing here yet. Press Sync now in Settings, or ask your admin.", color="muted").pack(anchor="w")
            return
        bar = tk.Frame(f, bg=C["bg"])
        bar.pack(fill="x", pady=(0, 10))
        self.label(bar, "Search", 9, color="muted").pack(side="left", padx=(0, 8))
        entry = ttk.Entry(bar, textvariable=self.query, width=30, font=FONT)
        entry.pack(side="left", ipady=2)
        entry.bind("<KeyRelease>", lambda e: self.draw_tool_list())
        self.label(bar, f"{len(tools)} tool{'s' if len(tools) != 1 else ''}", 9, color="muted").pack(side="right")
        chips = tk.Frame(f, bg=C["bg"])
        chips.pack(fill="x", pady=(0, 14))
        self.chips = chips
        cats = ["All", "Pinned"] + sorted({t.get("category") for t in tools if t.get("category")})
        if self.category not in cats:
            self.category = "All"
        line, used = tk.Frame(chips, bg=C["bg"]), 0
        line.pack(anchor="w")
        for cat in cats:
            width = len(cat) * 8 + 34
            if used + width > self.width() and used:
                line, used = tk.Frame(chips, bg=C["bg"]), 0
                line.pack(anchor="w", pady=(6, 0))
            here = cat == self.category
            make_button(line, text=cat, command=lambda c=cat: self.pick_category(c), relief="flat", bd=0, padx=12, pady=4,
                        font=(FONT[0], 9, "bold" if here else "normal"), bg=C["accent"] if here else C["panel"],
                        fg=C["on_gold"] if here else C["text2"], activebackground=C["gold_hi"] if here else C["hover"],
                        activeforeground=C["on_gold"] if here else C["text"], cursor="hand2", highlightthickness=1,
                        highlightbackground=C["accent"] if here else C["line_hi"]).pack(side="left", padx=(0, 6))
            used += width
        self.tool_list = tk.Frame(f, bg=C["bg"])
        self.tool_list.pack(fill="x")
        self.draw_tool_list()

    def pick_category(self, cat):
        self.category = cat
        self.show("apps")

    def draw_tool_list(self):
        if self.tool_list is None:
            return
        self.clear(self.tool_list)
        system, pins = native_apps.os_key(), self.pinned()
        agents = set(self.client.status()["installed"]) & set(AGENTS)
        q = self.query.get().strip().lower()
        shown = 0
        cols = 2 if self.width() >= 880 else 1
        for c in range(2):
            self.tool_list.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="tools" if c < cols else "")
        for t in self.tools():
            if self.category == "Pinned" and t["id"] not in pins:
                continue
            if self.category not in ("All", "Pinned") and t.get("category") != self.category:
                continue
            if q and q not in f"{t['name']} {t.get('category', '')} {t.get('description', '')}".lower():
                continue
            card = self.app_card(self.tool_list, t, system, pins, agents, cols=cols)
            card.grid(row=shown // cols, column=shown % cols, sticky="nsew", padx=(0 if shown % cols == 0 else 8, 0), pady=(0, 8))
            shown += 1
        if not shown:
            self.label(self.tool_list, "No tools match. Clear the search or pick All.", color="muted").grid(row=0, column=0, sticky="w")

    def app_card(self, parent, tool, system, pins, agents=(), cols=1):
        """One tool's card (the caller places it): logo, name, badges, how you sign in, what Open does here, actions."""
        tool_id, app = tool["id"], self.web_app(tool["id"])
        w = native_apps.way(tool_id, system)
        bg = C["panel"]
        card = self.card(parent)
        self.logo(card, tool, bg).pack(side="left", anchor="n")
        body = tk.Frame(card, bg=bg)
        body.pack(side="left", fill="x", expand=True, padx=(16, 0))
        top = tk.Frame(body, bg=bg)
        top.pack(fill="x")
        self.label(top, tool["name"], 12, bold=True, bg=bg).pack(side="left")
        for word in native_apps.badges(tool_id, system, app is not None):
            self.badge(top, word).pack(side="left", padx=(8, 0))
        self.make_pin(top, tool_id, pins).pack(side="right")
        kind, (how, how_text) = self.signin_kind(tool), self.how(tool)
        line = tk.Frame(body, bg=bg)
        line.pack(fill="x", pady=(3, 0))
        if tool.get("category"):
            self.label(line, tool["category"], 9, color="muted", bg=bg).pack(side="left")
            self.label(line, "  ·  ", 9, color="faint", bg=bg).pack(side="left")
        self.label(line, how, 9, color="info" if kind == "api" else "accent", bold=True, bg=bg).pack(side="left")
        if kind != "api" and tool_id in self.signed_marks():
            self.label(line, "  ·  ● Signed in", 9, color="ok", bg=bg).pack(side="left")
        wrap = max(260, (self.width() - 8 * (cols - 1)) // cols - 120)
        if tool.get("description"):
            self.label(body, tool["description"], 10, color="text2", bg=bg, wrap=wrap).pack(anchor="w", pady=(4, 0))
        # What Open does here and the desktop app's state: one line when both are short, else one under the other.
        notes = []
        if app is not None:
            notes.append((app_note(self.client, app), "muted"))
        found = None
        if w.method != native_apps.WEB:
            found = self.client.native.detect(tool_id)
            if tool_id in self.pending and found.get("state") != "installed":
                found = dict(found, state="installing")
            notes.append((native_words(tool_id, found), "ok" if found.get("state") == "installed" else "muted"))
        if notes and sum(len(n) for n, _ in notes) * 6 < wrap:
            line = tk.Frame(body, bg=bg)
            line.pack(anchor="w", pady=(4, 0))
            for i, (words, tone) in enumerate(notes):
                if i:
                    self.label(line, "  ·  ", 9, color="faint", bg=bg).pack(side="left")
                self.label(line, words, 9, color=tone, bg=bg).pack(side="left")
        else:
            for words, tone in notes:
                self.label(body, words, 9, color=tone, bg=bg, wrap=wrap).pack(anchor="w", pady=(3, 0))
        if w.method == native_apps.WEB and app is None and tool_id not in agents:
            self.label(body, "Swangz installs and opens this one on Windows and macOS." if system == "linux" else
                       "Opens outside Swangz. Ask your admin how your company uses it.", 9, color="muted",
                       bg=bg, wrap=wrap).pack(anchor="w", pady=(4, 0))
        note = (app or {}).get("account_note")
        if isinstance(note, str) and note.strip():
            self.label(body, note.strip()[:300], 9, color="muted", bg=bg, wrap=wrap).pack(anchor="w", pady=(2, 0))
        r = self.row(body)
        if app is not None:
            self.button(r, "Open in Swangz Chrome", lambda i=tool_id: self.open_app(i), bg=bg, small=True).pack(side="left", padx=(0, 8))
        if tool_id in agents:  # Claude Code / Codex set up by Swangz: run through the company gateway (agents.py)
            self.button(r, f"Open {AGENTS[tool_id]}", lambda k=tool_id: self.open_agent(k), bg=bg, small=True).pack(side="left", padx=(0, 8))
        if found is not None:
            state = found.get("state")
            if state == "installed" and w.method == native_apps.NATIVE:
                self.button(r, "Open desktop app", lambda i=tool_id: self.launch_native(i), bg=bg, small=True).pack(side="left", padx=(0, 8))
            if state in ("missing", "failed", "unknown") and self.client.native.plan(tool_id) is not None:
                self.button(r, "Install", lambda i=tool_id: self.install_native(i), bg=bg, small=True).pack(side="left", padx=(0, 8))
            if state in ("installed", "failed"):
                self.button(r, "Repair", lambda i=tool_id: self.install_native(i, "repair"), bg=bg, small=True).pack(side="left", padx=(0, 8))
        if kind != "api":
            self.link(r, "How to sign in  ›", lambda: self.show("accounts"), bg=bg).pack(side="left", padx=(4, 0))
        return card

    def make_pin(self, parent, tool_id, pins):
        on = tool_id in pins
        return make_button(parent, text="Unpin" if on else "Pin to Home", command=lambda: self.toggle_pin(tool_id),
                           relief="flat", bd=0, padx=8, pady=2, font=(FONT[0], 9), bg=C["panel"],
                           fg=C["accent"] if on else C["muted"], activebackground=C["hover"], activeforeground=C["text"],
                           cursor="hand2", highlightthickness=0)

    # ---- Sign-ins: where you sign in to each paid tool

    def page_accounts(self):
        f, st = self.content, self.client.status()
        email = (st.get("person") or {}).get("email") or ""
        self.heading(f, "Sign-ins", "Where you sign in to each AI tool the company pays for. You sign in once, on the "
                                    "tool's own page, inside your Swangz Chrome, and it keeps you signed in. Swangz never "
                                    "sees your passwords.")
        self.repair_panel(f)
        rows = self.signin_rows()
        done = sum(1 for _, _, signed in rows if signed)
        top = self.card(f)
        top.pack(fill="x", pady=(0, GAP))
        bg = C["panel"]
        self.label(top, f"{done} of {len(rows)} tools signed in" if rows else "No tools need a sign-in", 15, bold=True,
                   bg=bg).pack(anchor="w")
        if rows:
            self.bar(top, done, len(rows), bg=bg, width=min(420, self.width() - 60)).pack(anchor="w", pady=(10, 6))
            self.label(top, "Swangz can't see whether you're signed in: press I'm signed in on each tool once you are.",
                       9, color="muted", bg=bg, wrap=min(700, self.width() - 60)).pack(anchor="w")
        # 1. the Google account
        card = self.section(f, "1  ·  Your Swangz Google account", "Sign in to Google once in your Swangz Chrome with the "
                            "same Swangz account you use for the Hub. Every \"Continue with Google\" below then uses it.")
        if email:
            r = self.row(card)
            self.avatar(r, (st.get("person") or {}).get("name") or email, bg, 30).pack(side="left")
            self.label(r, email, 11, bold=True, bg=bg).pack(side="left", padx=(10, 0))
            opened = self.google_signin_opened()
            r = self.row(card)
            self.button(r, "Sign in again" if opened else "Sign in to Google in Swangz Chrome", self.sign_in_google,
                        primary=not opened, bg=bg).pack(side="left")
            if opened:
                self.label(r, f"   Google's sign-in was opened here on {when(opened)}.", 9, color="muted",
                           bg=bg).pack(side="left")
        # 2. each tool, grouped by how it signs in
        self.label(f, "2  ·  Your tools", 13, bold=True).pack(anchor="w", pady=(6, 10))
        for kind, title, steps in SIGNIN_GROUPS:
            group = [(t, signed) for t, k, signed in rows if k == kind]
            if not group:
                continue
            card = self.section(f, f"{title}  ({sum(1 for _, s in group if s)} of {len(group)})", HOW[kind][1])
            for n, step in enumerate(steps, 1):
                self.label(card, f"{n}. {step.format(email=email or 'your Swangz email')}", 10, color="text2", bg=bg,
                           wrap=min(700, self.width() - 60)).pack(anchor="w")
            if kind == "seat":
                r = self.row(card)
                self.button(r, "Ask for a seat", lambda: self.open_hub("requests"), bg=bg, small=True).pack(side="left")
                self.label(r, "   opens Requests in the Hub", 9, color="muted", bg=bg).pack(side="left")
            tk.Frame(card, bg=C["line"], height=1).pack(fill="x", pady=(14, 4))
            for t, signed in group:
                self.signin_row(card, t, signed)
        keyed = [t for t in self.tools() if self.signin_kind(t) == "api"]
        if keyed:
            card = self.section(f, "Nothing to sign in to", HOW["api"][1])
            self.label(card, ", ".join(t["name"] for t in keyed), 10, color="text2", bg=bg,
                       wrap=min(700, self.width() - 60)).pack(anchor="w")

    def signin_row(self, parent, tool, signed):
        bg = C["panel"]
        tool_id, app = tool["id"], self.web_app(tool["id"])
        r = tk.Frame(parent, bg=bg)
        r.pack(fill="x", pady=(8, 0))
        self.logo(r, tool, bg, 32).pack(side="left")
        words = tk.Frame(r, bg=bg)
        words.pack(side="left", padx=(12, 0), fill="x", expand=True)
        self.label(words, tool["name"], 11, bold=True, bg=bg).pack(anchor="w")
        opens = app is not None and self.client.workspace_app(app)
        if signed:
            state = ("● Signed in", "ok")
        elif opens:
            state = ("○ Not signed in yet", "gold_hi")
        elif app is not None:
            state = (app_note(self.client, app), "muted")
        else:
            w = native_apps.way(tool_id, native_apps.os_key())
            state = ("Sign in inside its desktop app" if w.method == native_apps.NATIVE else
                     "Sign in where your admin told you", "muted")
        self.label(words, state[0], 9, color=state[1], bg=bg, wrap=max(260, self.width() - 420)).pack(anchor="w")
        actions = tk.Frame(r, bg=bg)
        actions.pack(side="right")
        if signed:
            self.button(actions, "Undo", lambda: self.mark_signed(tool_id, False), bg=bg, small=True).pack(side="right")
        else:
            self.button(actions, "I'm signed in", lambda: self.mark_signed(tool_id, True), bg=bg, small=True).pack(side="right")
        if opens:
            self.button(actions, "Sign in", lambda: self.open_app(tool_id), primary=not signed, bg=bg,
                        small=True).pack(side="right", padx=(0, 8))
        elif app is None and native_apps.way(tool_id, native_apps.os_key()).method == native_apps.NATIVE \
                and self.client.native.detect(tool_id).get("state") == "installed":
            self.button(actions, "Open desktop app", lambda: self.launch_native(tool_id), bg=bg,
                        small=True).pack(side="right", padx=(0, 8))

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
            self.button(r, "Install Google Chrome", self.install_chrome, primary=True, bg=C["panel"]).pack(side="left", padx=(0, 8))
            self.button(r, "Re-check", self.check_chrome, bg=C["panel"]).pack(side="left")
        email = (self.client.status().get("person") or {}).get("email") or ""
        card = self.section(f, "Your Swangz Google account", "Sign in to Google once in your Swangz Chrome with the same "
                            "Swangz account you use for the Hub. Every AI tool's \"Continue with Google\" then uses it, "
                            "and it stays signed in after a restart. Type your password only on Google's page; Swangz "
                            "never sees it.")
        if email:
            self.label(card, email, 11, bold=True, bg=C["panel"]).pack(anchor="w", pady=(6, 0))
            done = self.google_signin_opened()
            r = self.row(card)
            self.button(r, "Sign in again" if done else "Sign in to Google in Swangz Chrome", self.sign_in_google,
                        primary=not done, bg=C["panel"]).pack(side="left")
            self.link(r, "   All sign-ins  ›", lambda: self.show("accounts"), bg=C["panel"]).pack(side="left")
            if done:
                self.label(card, f"Google's sign-in was opened here on {clock(done)}.", 9, color="muted",
                           bg=C["panel"]).pack(anchor="w", pady=(6, 0))
        card = self.section(f, "Your profile folder", "Provider and Google sign-ins you make in Swangz Chrome are kept here, "
                                                      "only for you. Swangz never copies or uploads them.")
        self.label(card, str(profiles_folder(self.client.paths.data)), 10, bg=C["panel"], wrap=640).pack(anchor="w")
        card = self.section(f, "Open windows")
        launcher = getattr(self.client, "launcher", None)
        window = bool(launcher is not None and launcher.running())
        self.label(card, "Your Swangz Chrome window is open." if window else "No Swangz Chrome window is open. Open a "
                   "tool from My tools or Home to start one.", 10, bg=C["panel"], wrap=640).pack(anchor="w")
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
        self.heading(f, "Automations", "Coding agents and packages your company has made available. The company decides "
                                       "this list; it updates here by itself.", actions=(("Sync all", self.sync_now, True),))
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
            top = tk.Frame(text, bg=C["panel"])
            top.pack(anchor="w")
            self.label(top, r["name"], 12, bold=True, bg=C["panel"]).pack(side="left")
            self.badge(top, f"v{r['version']}").pack(side="left", padx=(8, 0))
            self.label(text, r["description"], 9, color="text2", bg=C["panel"], wrap=520).pack(anchor="w", pady=(2, 0))
            self.label(text, ("● " if r["state"] == "installed" else "○ ") + STATE_WORDS.get(r["state"], r["state"])
                       + (f" ({r['installed_version']})" if r["state"] == "update" else ""), 9,
                       color="ok" if r["state"] == "installed" else "gold_hi", bg=C["panel"]).pack(anchor="w", pady=(4, 0))
            if r["state"] == "installed":
                self.button(row, "Remove", lambda i=r["id"]: self.remove_package(i), bg=C["panel"], small=True).pack(side="right")
            else:
                self.button(row, "Update" if r["state"] == "update" else "Install", self.sync_now, bg=C["panel"],
                            small=True).pack(side="right")

    # ---- Activity: this device's recent opens

    def page_usage(self):
        f = self.content
        self.heading(f, "Activity", "What you opened from Swangz on this computer. This list stays on this computer; "
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
            if self.page in ("home", "apps", "accounts", "workspace", "automations", "settings", "usage"):
                self.show(self.page)  # redraw first: it clears the status line
            self.say(f"Synced at {clock(time.time())}." if not bad else f"Synced, but {bad[0][0]} needs attention: {bad[0][1]}", bad=bool(bad))
            self.fetch_logos()

        self.work(self.client.sync, done)

    def fetch_logos(self):
        """After a sync: fetch the logos that are due (off the window's thread), then redraw once if any changed."""
        refresh = getattr(self.client, "refresh_logos", None)
        if refresh is None or self._logos_fetched:
            return
        self._logos_fetched = True

        def done(ok, value):
            self._logos_fetched = False
            if ok and value:
                self._images.clear()
                if self.page in ("home", "apps", "accounts"):
                    said, color = self.statusbar.cget("text"), self.statusbar.cget("fg")
                    self.show(self.page)
                    self.statusbar.configure(text=said, fg=color)

        self.work(refresh, done)

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
    if sys.platform.startswith("linux") and os.environ.get("SWANGZ_KEEP_INPUT_METHOD") != "1":
        # Tk talks to the desktop's input method (ibus) over XIM for every widget; on the Ubuntu test laptop a busy ibus
        # made each page take ~10 s to paint (0.4 s without). The window has two short text boxes, so it goes without.
        os.environ["XMODIFIERS"] = "@im=none"
    client = client or core.Client()
    app = App(client, background=background)
    app.root.mainloop()
    return 0
