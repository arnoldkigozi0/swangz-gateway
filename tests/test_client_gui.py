"""The Swangz app window, driven for real (Tk) against a stand-in client. Skipped where there is no Tk or no display:

    xvfb-run -a python3 -m unittest tests.test_client_gui
"""

import os
from pathlib import Path
import time
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    import tkinter as tk

    root = tk.Tk()
    root.destroy()
    HAVE_DISPLAY = True
except Exception:  # noqa: BLE001 — no tkinter, or no display
    HAVE_DISPLAY = False

if HAVE_DISPLAY:
    from swangz_client import core, gui
    from swangz_client import workspace_launcher as wl

MANIFEST_PACKAGES = [
    {"id": "claude-code", "name": "Claude Code", "kind": "agent", "description": "Anthropic's coding agent.", "version": "1", "state": "installed", "installed_version": "1", "detail": "", "mode": "scoped"},
    {"id": "brand-prompts", "name": "Brand prompts", "kind": "tool", "description": "Shared prompts.", "version": "1.1.0", "state": "update", "installed_version": "1.0.0", "detail": "", "mode": None},
    {"id": "access-gate", "name": "Browser access gate", "kind": "extension", "description": "Keeps AI websites governed.", "version": "abc", "state": "available", "installed_version": None, "detail": "", "mode": None},
]


class FakeNative:
    """Stands in for native_apps.Manager: records what the window asked for, installs and starts nothing."""

    def __init__(self):
        self.calls = []
        self.states = {}
        self.chrome_state = "installed"

    def detect(self, tool_id, fresh=False):
        return dict(self.states.get(tool_id, {"state": "missing", "version": "", "path": "", "via": ""}))

    def chrome(self):
        return {"state": self.chrome_state, "version": "", "path": ""}

    def plan(self, tool_id, action="install"):
        from swangz_client import native_apps
        return native_apps.Plan(tool_id, action, "winget", "Claude", "Anthropic", "winget, Microsoft's app installer",
                                ("winget.exe", "install"), "")

    def consent_text(self, plan):
        return f"Install {plan.name}?\nPublisher: {plan.publisher}\nFrom: {plan.where}"

    def execute(self, plan):
        self.calls.append(("execute", plan.tool, plan.action))
        self.states[plan.tool] = {"state": "installed", "version": "1.2", "path": "C:\\x\\Claude.exe", "via": "fixed path"}
        return {"state": "installed", "message": f"{plan.name} is installed."}

    def launch(self, tool_id):
        self.calls.append(("launch", tool_id))
        return "Opened Claude."

    def forget(self, tool_id=None):
        self.calls.append(("forget", tool_id))


class FakeClient:
    def __init__(self, signed_in=False):
        import tempfile
        self.signed = signed_in
        self.calls = []
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = SimpleNamespace(home=self._tmp.name, data=self._tmp.name)
        self.native = FakeNative()
        self.launcher = None
        self.chrome = {"ok": True, "path": "/opt/google/chrome/chrome", "why": ""}
        self.extra_tools = [{"id": "claude", "name": "Claude", "kind": "api", "category": "Assistant"}]
        self.login_error = None
        self.cleanup_pending = False
        self.cleanup_error = None
        self.open_error = None
        self.account_error = None
        self.account_removal = {"told": True, "left": [], "problems": []}
        self.company = False
        self.browser = {"contract": 2, "workspace": {"state": "active", "generation": 1}}
        self.store = SimpleNamespace(manifest=lambda: {"browser": self.browser}, device=lambda: {})
        self.workspace = SimpleNamespace(latch=lambda: {})

    def signed_in(self):
        return self.signed

    google_opened = None

    def google_signin_opened(self):
        return self.google_opened

    def sign_in_google(self):
        self.calls.append(("google",))
        if self.open_error:
            raise self.open_error
        self.google_opened = time.time()
        return "workspace"

    def status(self):
        return {"signed_in": self.signed, "server": "https://ai.swangzavenue.com", "person": {"name": "Nansubuga Grace", "email": "grace@swangzavenue.com"},
                "device": {"name": "Grace's laptop", "owner_kind": "personal"}, "installed": {"claude-code": {"version": "1"}, "codex": {"version": "1"}},
                "last_sync": time.time(), "update_available": True, "client_version": "0.1.0", "autostart": False,
                "recording": "Swangz AI Hub records this device's name... It never reads your files, screen, keystrokes or other programs.",
                "cleanup_pending": self.cleanup_pending}

    def packages(self):
        return MANIFEST_PACKAGES

    def apps(self):
        return [{"id": "canva", "name": "Canva", "category": "Design", "signin": "seat", "company_browser": False, "workspace": True, "open": "https://x/go/canva"},
                {"id": "midjourney", "name": "Midjourney", "category": "Image", "signin": "shared", "company_browser": True, "open": "https://x/go/midjourney"}]

    def tools(self):
        return [{"id": a["id"], "name": a["name"], "kind": "site", "category": a["category"]} for a in self.apps()] \
            + self.extra_tools

    def chrome_status(self):
        self.calls.append(("chrome",))
        return dict(self.chrome)

    def policy_report(self):
        return None

    def workspace_app(self, app):
        return app.get("workspace") is True

    def company_device(self):
        return self.company

    def login(self, server, name, on_code=None, cancelled=lambda: False, timeout=None):
        self.calls.append(("login", server, name))
        if on_code:
            on_code("BCDF-GH23", server + "/device?code=BCDF-GH23")
        if self.login_error:
            raise self.login_error
        self.signed = True
        return {"server": server}

    def sync(self, force=False):
        self.calls.append(("sync",))
        return {"results": [("claude-code", "current", "")], "manifest": {}}

    def remove_package(self, pid):
        self.calls.append(("remove", pid))

    def logout(self):
        self.calls.append(("logout",))
        self.signed = False
        return True

    def remove_everything(self):
        self.calls.append(("cleanup",))
        if self.cleanup_error:
            raise self.cleanup_error
        self.cleanup_pending = False

    def cleanup(self):
        self.calls.append(("remove account",))
        if self.account_error:
            raise self.account_error
        self.signed = False
        return self.account_removal

    def open_app(self, tool_id):
        self.calls.append(("open", tool_id))
        if self.open_error:
            raise self.open_error

    def refresh(self):
        self.calls.append(("refresh",))


def texts(widget):
    out = []
    for w in widget.winfo_children():
        try:
            out.append(str(w.cget("text")))
        except tk.TclError:
            pass
        out += texts(w)
    return out


def buttons(widget):
    found = {}
    for w in widget.winfo_children():
        if isinstance(w, (tk.Button, gui.LabelButton)):
            found[str(w.cget("text"))] = w
        found.update(buttons(w))
    return found


@unittest.skipUnless(HAVE_DISPLAY, "needs Tk and a display (run under xvfb-run)")
class WindowTests(unittest.TestCase):
    def make(self, signed_in=True, **kw):
        self.client = FakeClient(signed_in)
        self.addCleanup(self.client._tmp.cleanup)
        self.app = gui.App(self.client, inline=True, **kw)
        self.addCleanup(self.app.root.destroy)
        self.app.root.update()
        return self.app

    def everything(self):
        return texts(self.app.root)

    def test_signed_out_it_asks_you_to_connect_the_device(self):
        self.make(False)
        text = " ".join(self.everything())
        self.assertIn("Connect this device", text)
        self.assertIn("Swangz AI Hub address", text)
        self.assertNotIn("Home", buttons(self.app.dock))  # no dock until you are in

    def test_sign_in_starts_on_the_company_hub_unless_the_environment_names_another(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SWANGZ_SERVER", None)
            app = self.make(False)
            self.assertEqual(app.server_var.get(), "https://hub.ictconnect.org")
            self.assertEqual(self.client.calls, [])  # nothing is sent before Sign in
            os.environ["SWANGZ_SERVER"] = ""
            app.show("signin")
            self.assertEqual(app.server_var.get(), "https://hub.ictconnect.org")
            os.environ["SWANGZ_SERVER"] = "https://other.example.org"
            app.show("signin")
            self.assertEqual(app.server_var.get(), "https://other.example.org")

    def test_signing_in_shows_the_code_then_lands_on_home(self):
        app = self.make(False)
        app.server_var.set("ai.swangzavenue.com")
        app.name_var.set("Grace's laptop")
        app.sign_in()
        app.root.update()
        self.assertEqual(self.client.calls[0], ("login", "https://ai.swangzavenue.com", "Grace's laptop"))
        self.assertEqual(app.page, "home")
        self.assertIn("Good", " ".join(self.everything()))
        self.assertIn(("sync",), self.client.calls)  # it syncs straight away

    def test_incomplete_cleanup_is_retried_through_the_client_interface(self):
        app = self.make(False)
        self.client.cleanup_pending = True
        app.show("signin")
        self.assertIn("Credential removal is incomplete.", " ".join(self.everything()))
        self.client.cleanup_error = core.keystore.KeyStoreError("Keychain is locked; retry removal.")
        buttons(app.content)["Retry local removal"].invoke()
        self.assertTrue(self.client.cleanup_pending)
        self.assertIn("Keychain is locked; retry removal.", self.everything())
        self.assertIn("Retry local removal", buttons(app.content))
        self.client.cleanup_error = None
        buttons(app.content)["Retry local removal"].invoke()
        self.assertEqual(self.client.calls, [("cleanup",), ("cleanup",)])
        self.assertFalse(self.client.cleanup_pending)
        self.assertNotIn("Retry local removal", buttons(app.content))
        self.assertEqual(app.page, "signin")

    def test_the_code_is_big_and_there_is_a_way_to_cancel(self):
        app = self.make(False)
        app._show_code("BCDF-GH23", "https://x/device?code=BCDF-GH23")
        app.root.update()
        self.assertIn("BCDF-GH23", self.everything())
        self.assertIn("Cancel", buttons(app.content))
        self.assertIn("Open the page again", buttons(app.content))

    def test_a_bad_address_is_explained_without_calling_the_server(self):
        app = self.make(False)
        app.server_var.set("ftp://nope")
        app.sign_in()
        app.root.update()
        self.assertEqual(self.client.calls, [])
        self.assertIn("doesn't look like", " ".join(self.everything()))

    def test_a_failed_sign_in_says_why_and_stays_on_the_sign_in_page(self):
        app = self.make(False)
        self.client.login_error = core.ApiFailure(400, "access_denied", "The sign-in was refused.")
        app.server_var.set("ai.swangzavenue.com")
        app.sign_in()
        app.root.update()
        self.assertEqual(app.page, "signin")
        self.assertIn("The sign-in was refused.", self.everything())

    def test_home_offers_the_agents_and_apps_you_have(self):
        app = self.make()
        found = buttons(app.content)
        for name in ("Open Claude Code", "Open Codex", "Canva", "Midjourney", "Sync now"):
            self.assertIn(name, found)
        self.assertIn("A newer version of Swangz is available.", " ".join(self.everything()))
        found["Canva"].invoke()
        self.assertIn(("open", "canva"), self.client.calls)

    def test_on_macos_every_button_is_a_label_that_keeps_its_colours_and_still_works(self):
        # Aqua ignores tk.Button colours (white boxes, pale text in the 27 Nov CI screenshot), so macOS gets LabelButtons
        with mock.patch.object(gui, "LABEL_BUTTONS", True):
            app = self.make()
            dock, found = buttons(app.dock), buttons(app.content)
            self.assertTrue(dock and all(isinstance(b, gui.LabelButton) for b in dock.values()))
            self.assertTrue(found and all(isinstance(b, gui.LabelButton) for b in found.values()))
            home = dock["Home"]
            self.assertEqual((str(home.cget("bg")), str(home.cget("fg"))), (gui.C["raised"], gui.C["gold_hi"]))
            self.assertEqual(str(dock["Apps"].cget("fg")), gui.C["text"])  # readable on the dark sidebar
            found["Canva"].invoke()
            self.assertIn(("open", "canva"), self.client.calls)
            dock["Apps"].event_generate("<Enter>")
            dock["Apps"].event_generate("<Leave>")
            self.assertEqual(str(dock["Apps"].cget("fg")), gui.C["text"])  # hover returns to its own colours
            dock["Apps"].invoke()
            app.root.update()
            self.assertEqual(app.page, "apps")
            b = buttons(app.content)["Open in Swangz Chrome"]
            b.configure(state="disabled")
            before = list(self.client.calls)
            b.invoke()
            self.assertEqual(self.client.calls, before)  # a disabled button does nothing

    def test_home_asks_once_to_sign_in_to_google_with_the_persons_own_swangz_account(self):
        app = self.make()
        text = " ".join(self.everything())
        self.assertIn("Sign in to Google once", text)
        self.assertIn("grace@swangzavenue.com", text)
        buttons(app.content)["Sign in to Google in Swangz Chrome"].invoke()
        app.root.update()
        self.assertIn(("google",), self.client.calls)
        self.assertNotIn("Sign in to Google once", " ".join(self.everything()))  # asked once, then it stays on Workspace

    def test_workspace_shows_the_account_and_signs_in_again(self):
        app = self.make()
        buttons(app.dock)["Workspace"].invoke()
        app.root.update()
        text = " ".join(self.everything())
        self.assertIn("Your Swangz Google account", text)
        self.assertIn("Swangz never sees it", text)
        buttons(app.content)["Sign in to Google in Swangz Chrome"].invoke()
        app.root.update()
        self.assertIn("Sign in again", buttons(app.content))
        self.assertIn("Google's sign-in was opened here", " ".join(self.everything()))

    def test_a_refused_google_sign_in_says_why(self):
        app = self.make()
        self.client.open_error = wl.LaunchError("no_browser")
        buttons(app.content)["Sign in to Google in Swangz Chrome"].invoke()
        app.root.update()
        self.assertIn("Google's sign-in wasn't opened.", self.everything())
        self.assertIsNone(self.client.google_opened)

    def refuse(self, error, page="Apps"):
        app = self.make()
        if page != "Home":
            buttons(app.dock)[page].invoke()
        self.client.open_error = error
        with mock.patch.object(gui.shell, "open_url") as opened:
            buttons(app.content)["Open in Swangz Chrome" if page == "Apps" else "Canva"].invoke()
        opened.assert_not_called()  # a refusal opens nothing by itself
        app.root.update()
        return app

    def test_a_refused_open_says_why_what_to_do_and_offers_the_way_out(self):
        for page in ("Home", "Apps"):
            app = self.refuse(wl.LaunchError("no_browser"), page)
            text = " ".join(self.everything())
            self.assertIn("Google Chrome is needed", text, page)
            self.assertIn(wl.MESSAGES["no_browser"], text)
            self.assertIn("1. Get Google Chrome", text)
            self.assertIn("wasn't opened", app.statusbar.cget("text"))
            found = buttons(app.content)
            for name in ("Get Google Chrome", "Try again", "Dismiss"):
                self.assertIn(name, found)
            with mock.patch.object(gui.shell, "open_url") as opened:
                found["Get Google Chrome"].invoke()
            opened.assert_called_once_with("https://www.google.com/chrome/")

    def test_try_again_asks_the_hub_first_and_clears_the_panel_when_it_opens(self):
        app = self.refuse(wl.LaunchError("launch_failed"), "Home")
        self.client.calls.clear()
        buttons(app.content)["Try again"].invoke()  # still refused: the panel stays
        self.assertEqual(self.client.calls, [("refresh",), ("open", "canva")])
        self.assertIn("Try again", buttons(app.content))
        self.client.open_error, self.client.calls = None, []
        buttons(app.content)["Try again"].invoke()
        self.assertEqual(self.client.calls, [("refresh",), ("open", "canva")])
        self.assertNotIn("Try again", buttons(app.content))
        self.assertEqual(app.statusbar.cget("text"), "Opened in your Swangz Chrome.")

    def test_a_hub_refusal_shows_the_hubs_words_and_the_weekly_report_button(self):
        app = self.refuse(core.ApiFailure(403, "weekly_report_required", "Send last week's report to open Canva."))
        self.assertIn("Send last week's report to open Canva.", self.everything())
        with mock.patch.object(gui.shell, "open_hub") as hub:
            buttons(app.content)["Open weekly reports"].invoke()
        hub.assert_called_once_with(self.client, "weekly")

    def test_a_shared_account_on_a_company_computer_offers_no_way_to_open_it(self):
        with mock.patch.object(gui.shell, "open_hub") as hub:
            app = self.refuse(wl.LaunchError("shared_account_company"))
        hub.assert_not_called()
        self.assertIn(wl.MESSAGES["shared_account_company"], self.everything())
        found = buttons(app.content)
        self.assertIn("Dismiss", found)
        # the only buttons left are the list's own Open buttons, which refuse again, Re-check, Pin and Dismiss:
        # nothing that opens the Hub, a /go/ link or another browser
        self.assertEqual(set(found), {"Open in Swangz Chrome", "Re-check", "Pin to Home", "Dismiss"})

    def test_the_panel_survives_a_redraw_and_goes_on_dismiss_or_page_change(self):
        app = self.refuse(core.ApiFailure(403, "not_assigned", "Canva isn't assigned to you."))
        app.sync_now()
        app.root.update()
        self.assertIn("Dismiss", buttons(app.content))
        buttons(app.content)["Dismiss"].invoke()
        self.assertNotIn("Dismiss", buttons(app.content))
        app = self.refuse(wl.LaunchError("folder"))
        buttons(app.dock)["Home"].invoke()
        buttons(app.dock)["Apps"].invoke()
        self.assertNotIn("Dismiss", buttons(app.content))

    def test_a_revoked_device_on_open_goes_to_sign_in_not_a_repair_panel(self):
        app = self.make()
        self.client.open_error = core.Revoked(401, "device_revoked", "x")
        self.client.signed = False
        buttons(app.content)["Canva"].invoke()
        app.root.update()
        self.assertEqual(app.page, "signin")
        self.assertIsNone(app.refusal)
        self.assertNotIn("Try again", buttons(app.content))

    def test_the_dock_moves_between_pages(self):
        app = self.make()
        self.assertEqual([name for key, name in gui.PAGES], ["Home", "Apps", "Workspace", "Automations", "Usage", "Settings"])
        self.assertEqual(sorted(buttons(app.dock)), sorted(name for _, name in gui.PAGES))
        for name, expect in (("Apps", "Opens in your Swangz Chrome"), ("Workspace", "Your profile folder"),
                             ("Automations", "Update ready (1.0.0)"), ("Usage", "Open weekly reports"),
                             ("Settings", "What Swangz records"), ("Home", "Quick launch")):
            buttons(app.dock)[name].invoke()
            app.root.update()
            self.assertIn(expect, " ".join(self.everything()), name)

    def test_the_apps_page_says_what_open_really_does_on_this_computer(self):
        """#333 D-026 D4: a shared account opens in no browser of the app's; the row says so for each kind of computer."""
        for company, expect in ((False, "Shared company account. Open it from Swangz AI Hub"),
                                (True, "Shared company account. Doesn't open on this company computer yet; ask your administrator")):
            app = self.make()
            app.client.company = company
            buttons(app.dock)["Apps"].invoke()
            app.root.update()
            text = " ".join(self.everything())
            self.assertIn(expect, text, company)
            self.assertIn("Opens in your Swangz Chrome", text)
            self.assertNotIn("company browser of your own", text)
            self.assertNotIn("turn", text)

    def test_packages_say_where_each_one_stands_and_what_you_can_do(self):
        app = self.make()
        buttons(app.dock)["Automations"].invoke()
        found = buttons(app.content)
        self.assertEqual({k for k in found if k in ("Remove", "Update", "Install")}, {"Remove", "Update", "Install"})
        self.client.calls.clear()
        found["Install"].invoke()
        self.assertIn(("sync",), self.client.calls)
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            buttons(app.content)["Remove"].invoke()
        self.assertIn(("remove", "claude-code"), self.client.calls)
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False):
            self.client.calls.clear()
            buttons(app.content)["Remove"].invoke()
        self.assertEqual(self.client.calls, [])

    def test_the_device_page_says_what_is_recorded_and_signing_out_removes_swangz(self):
        app = self.make()
        buttons(app.dock)["Settings"].invoke()
        text = " ".join(self.everything())
        self.assertIn("never reads your files", text)
        self.assertIn("Personal", text)
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as asked:
            buttons(app.content)["Sign out and disconnect this device"].invoke()
        self.assertNotIn(("logout",), self.client.calls)
        question = asked.call_args.args[1]
        # Until deletion is built, the question must not promise the browser folders go too.
        self.assertNotIn("remove Swangz from this device", question)
        self.assertIn("provider and Google sign-ins are not removed", question)
        self.assertIn(str(Path(self.client.paths.data) / "browser-profiles"), question)
        self.assertIn(gui.REMOVE, question)  # where the person goes to delete them
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            buttons(app.content)["Sign out and disconnect this device"].invoke()
        self.assertIn(("logout",), self.client.calls)
        self.assertEqual(app.page, "signin")

    def remove_account(self, app, answer=True):
        with mock.patch.object(gui.messagebox, "askyesno", return_value=answer) as asked:
            buttons(app.content)[gui.REMOVE].invoke()
        app.root.update()
        return asked.call_args.args[1]

    def test_the_device_page_can_remove_swangz_from_this_account(self):
        app = self.make()
        buttons(app.dock)["Settings"].invoke()
        question = self.remove_account(app, answer=False)
        self.assertNotIn(("remove account",), self.client.calls)
        for said in ("signs you out", "deletes the browser sign-ins (provider and Google)", "app itself stays installed"):
            self.assertIn(said, question)
        self.remove_account(app)
        self.assertEqual(self.client.calls.count(("remove account",)), 1)
        self.assertEqual(app.page, "signin")
        self.assertIn("removed from this account", app.statusbar.cget("text"))
        self.assertNotIn(gui.REMOVE, buttons(app.content))

    def test_an_incomplete_removal_names_what_is_left_and_can_be_tried_again(self):
        app = self.make()
        buttons(app.dock)["Settings"].invoke()
        self.client.account_removal = {"told": False, "left": [("/data/browser-profiles/stuck", "cleanup_failed")],
                                       "problems": ["start at login (PermissionError)"]}
        self.remove_account(app)
        shown = " ".join(self.everything())
        for said in ("not completely removed", "/data/browser-profiles/stuck", "start at login (PermissionError)"):
            self.assertIn(said, shown)
        self.assertNotIn("removed from this account.", app.statusbar.cget("text"))
        self.assertIn("ask an admin to disconnect", app.statusbar.cget("text"))
        self.client.account_removal = {"told": True, "left": [], "problems": []}
        self.remove_account(app)
        self.assertNotIn("not completely removed", " ".join(self.everything()))
        self.assertNotIn(gui.REMOVE, buttons(app.content))

    def test_a_refused_removal_says_why_and_stays_where_it_was(self):
        app = self.make()
        buttons(app.dock)["Settings"].invoke()
        self.client.account_error = core.CleanupRefused("elevated_refused")
        self.remove_account(app)
        self.assertEqual(app.page, "settings")
        self.assertIn("elevated_refused", app.statusbar.cget("text"))

    def test_a_disconnected_device_goes_back_to_sign_in_with_the_reason(self):
        app = self.make()
        self.client.signed = False
        app.failed(core.Revoked(401, "device_revoked", "x"))
        app.root.update()
        self.assertEqual(app.page, "signin")
        shown = " ".join(self.everything())
        self.assertIn("was disconnected", shown)
        self.assertNotIn("has been removed", shown)  # the browser folders stay until deletion is built
        self.assertIn("provider and Google sign-ins are not removed", shown)

    def test_opening_a_coding_agent_starts_a_terminal_running_it_through_swangz(self):
        app = self.make()
        with mock.patch.object(gui.shell, "open_terminal", return_value=True) as opened:
            buttons(app.content)["Open Claude Code"].invoke()
        cmd = opened.call_args[0][0]
        self.assertEqual(cmd[-2:], ["run", "claude"])

    def test_hub_actions_explain_separate_browser_signin_and_dispatch(self):
        app = self.make()
        buttons(app.dock)["Settings"].invoke()
        text = " ".join(self.everything())
        self.assertIn("grace@swangzavenue.com", text)
        self.assertIn("open in your usual browser", text)
        self.assertIn("own browser profile", text)
        self.assertNotIn("Open tools", buttons(app.content))
        with mock.patch.object(gui.shell, "open_hub") as opened:
            for page_name, label, page in (("Settings", "Open my devices", "devices"),
                                           ("Settings", "Open control room", "admin"),
                                           ("Usage", "Open weekly reports", "weekly"),
                                           ("Workspace", "Open Swangz AI Hub", "devices")):
                buttons(app.dock)[page_name].invoke()
                buttons(app.content)[label].invoke()
                opened.assert_called_with(self.client, page)
        with mock.patch.object(gui.shell, "open_hub", side_effect=OSError("Browser unavailable")):
            buttons(app.dock)["Usage"].invoke()
            buttons(app.content)["Open weekly reports"].invoke()
        self.assertIn("Browser unavailable", app.statusbar.cget("text"))

    def test_every_page_fits_the_smallest_supported_window_across(self):
        app = self.make()
        app.root.geometry("780x540")
        for page, _ in gui.PAGES:
            app.show(page)
            app.root.update()
            right = app.canvas.winfo_rootx() + app.canvas.winfo_width()
            for label, button in buttons(app.content).items():
                self.assertGreaterEqual(button.winfo_rootx(), app.canvas.winfo_rootx(), (page, label))
                self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), right, (page, label))
        app.show("usage")
        app.root.update()
        button = buttons(app.content)["Open weekly reports"]  # the page's one action is above the fold
        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), app.statusbar.winfo_rooty())

    # ------------------------------------------------------------ the workstation (27 Nov 2026)

    def on(self, system):
        """Draw as if on `system` (the table's per-OS entries); the fake native manager installs nothing."""
        patcher = mock.patch.object(gui.native_apps, "os_key", return_value=system)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_home_greets_by_the_whole_name_and_shows_chrome_sync_and_device(self):
        app = self.make()
        text = " ".join(self.everything())
        self.assertIn(", Nansubuga Grace", text)  # never a guessed "first name"
        for said in ("Google Chrome", "Found on this computer", "Last synced", "Personal · connected",
                     "Quick launch", "Running now", "No Swangz Chrome window is open."):
            self.assertIn(said, text)
        self.client.native.chrome_state = "missing"
        app.show("home")
        self.assertIn("Not installed", " ".join(self.everything()))
        buttons(app.content)["Set up"].invoke()
        self.assertEqual(app.page, "workspace")

    def test_cards_carry_badges_and_the_quiet_account_note(self):
        self.on("windows")
        app = self.make()
        apps = FakeClient.apps(self.client)
        apps[0]["account_note"] = "Company account: sign in with design@swangzavenue.com"
        self.client.apps = lambda: apps
        buttons(app.dock)["Apps"].invoke()
        text = self.everything()
        for word in ("Web", "Desktop", "Desktop app not installed", "Company account: sign in with design@swangzavenue.com"):
            self.assertIn(word, text)
        found = buttons(app.content)
        for name in ("Open in Swangz Chrome", "Install", "Pin to Home", "Re-check"):
            self.assertIn(name, found)
        self.assertNotIn("Open desktop app", found)

    def test_install_asks_first_and_declining_runs_nothing(self):
        self.on("windows")
        app = self.make()
        buttons(app.dock)["Apps"].invoke()
        with mock.patch.object(gui.messagebox, "askyesno", return_value=False) as asked:
            buttons(app.content)["Install"].invoke()
        title, text = asked.call_args.args
        self.assertEqual(title, "Install Claude")
        for said in ("Claude", "Publisher: Anthropic", "From: winget"):
            self.assertIn(said, text)
        self.assertNotIn(("execute", "claude", "install"), self.client.native.calls)
        self.assertEqual(app.statusbar.cget("text"), "Nothing was changed.")
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            buttons(app.content)["Install"].invoke()
        app.root.update()
        self.assertIn(("execute", "claude", "install"), self.client.native.calls)
        self.assertEqual(app.statusbar.cget("text"), "Claude is installed.")
        found = buttons(app.content)
        self.assertIn("Open desktop app", found)
        self.assertIn("Repair", found)
        self.assertIn("Desktop app installed 1.2", self.everything())
        found["Open desktop app"].invoke()
        self.assertIn(("launch", "claude"), self.client.native.calls)
        self.assertEqual(app.statusbar.cget("text"), "Opened Claude.")
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True) as asked:
            buttons(app.content)["Repair"].invoke()
        self.assertEqual(asked.call_args.args[0], "Repair Claude")
        self.assertIn(("execute", "claude", "repair"), self.client.native.calls)

    def test_on_linux_desktop_apps_are_not_offered(self):
        self.on("linux")
        app = self.make()
        buttons(app.dock)["Apps"].invoke()
        found = buttons(app.content)
        self.assertNotIn("Install", found)
        self.assertNotIn("Open desktop app", found)
        self.assertIn("Swangz installs and opens this one on Windows and macOS.", self.everything())

    def test_coding_agents_open_from_their_cards_through_swangz(self):
        app = self.make()
        self.client.extra_tools = [{"id": "claude-code", "name": "Claude Code", "kind": "dev", "category": "Coding"}]
        buttons(app.dock)["Apps"].invoke()
        with mock.patch.object(gui.shell, "open_terminal", return_value=True) as opened:
            buttons(app.content)["Open Claude Code"].invoke()
        self.assertEqual(opened.call_args[0][0][-2:], ["run", "claude"])

    def test_pinning_puts_a_tool_first_on_home_and_survives_a_restart(self):
        self.on("windows")
        app = self.make()
        buttons(app.dock)["Apps"].invoke()
        cards = [w for w in app.content.winfo_children() if isinstance(w, tk.Frame)]
        claude_card = next(c for c in cards if "Claude" in texts(c))
        buttons(claude_card)["Pin to Home"].invoke()
        self.assertIn("Unpin", buttons(app.content))
        buttons(app.dock)["Home"].invoke()
        home = texts(app.content)
        self.assertLess(home.index("Claude"), home.index("Canva"))
        again = gui.App(self.client, inline=True)
        self.addCleanup(again.root.destroy)
        self.assertEqual(again.pinned(), ["claude"])

    def test_workspace_checks_chrome_off_the_window_and_guides_the_install(self):
        app = self.make()
        self.client.chrome = {"ok": False, "path": "", "why": "an unsigned chrome.exe"}
        buttons(app.dock)["Workspace"].invoke()
        app.root.update()  # the check runs after the page is drawn
        self.assertIn(("chrome",), self.client.calls)
        text = " ".join(self.everything())
        self.assertIn("isn't set up on this computer yet", text)
        self.assertIn("Why: an unsigned chrome.exe", text)
        self.assertIn(str(Path(self.client.paths.data) / "browser-profiles"), text)
        with mock.patch.object(gui.sys, "platform", "darwin"), mock.patch.object(gui.shell, "open_url") as opened:
            buttons(app.content)["Install Google Chrome"].invoke()
        opened.assert_called_once_with("https://www.google.com/chrome/")  # Google's own page, nothing else
        self.client.chrome = {"ok": True, "path": "/opt/google/chrome/chrome", "why": ""}
        buttons(app.content)["Re-check"].invoke()
        self.assertIn("Installed, and checked: published by Google.", " ".join(self.everything()))
        self.assertNotIn("Install Google Chrome", buttons(app.content))

    def test_windows_chrome_install_asks_on_the_window_and_uses_the_company_build_step(self):
        app = self.make()
        self.client.chrome = {"ok": False, "path": "", "why": ""}
        buttons(app.dock)["Workspace"].invoke()
        app.root.update()
        seen = {}

        def request_install(consent=None, **kw):
            seen["asked"] = consent("Install Google Chrome for everyone on this computer.")
            return ("declined", "Nothing was changed.")

        from swangz_client import chrome_install
        with mock.patch.object(gui.sys, "platform", "win32"), \
                mock.patch.object(chrome_install, "request_install", side_effect=request_install), \
                mock.patch.object(gui.messagebox, "askyesno", return_value=False) as asked, \
                mock.patch.object(gui.shell, "open_url") as opened:
            buttons(app.content)["Install Google Chrome"].invoke()
        self.assertEqual(asked.call_args.args, ("Install Google Chrome", "Install Google Chrome for everyone on this computer."))
        self.assertFalse(seen["asked"])
        opened.assert_not_called()
        self.assertEqual(app.statusbar.cget("text"), "Nothing was changed.")

    def test_usage_lists_this_devices_recent_opens(self):
        app = self.make()
        now = int(time.time())
        data = Path(self.client.paths.data)
        (data / "workspace-open.log").write_text(f"{now - 60} open canva\n{now - 30} open canva\n", encoding="utf-8")
        (data / "apps-open.log").write_text(f"{now - 10} desktop claude\n", encoding="utf-8")
        buttons(app.dock)["Usage"].invoke()
        text = " ".join(self.everything())
        self.assertIn("opened 2 times", text)
        self.assertIn("Claude  ·  desktop app", text)
        self.assertIn("Canva  ·  Swangz Chrome", text)

    def test_it_can_start_minimised_for_start_at_login(self):
        with mock.patch.object(tk.Tk, "iconify") as iconify:  # a bare display has no window manager to honour it
            self.make(background=True)
        iconify.assert_called_once()
        with mock.patch.object(tk.Tk, "iconify") as iconify:
            self.make(False, background=True)  # signed out, it has to ask for the code: never hidden
        iconify.assert_not_called()

    def test_a_real_screenshot_can_be_taken(self):
        """Not a check of looks: it makes sure the whole window draws at its normal size without errors."""
        app = self.make()
        app.root.update_idletasks()
        self.assertGreaterEqual(app.root.winfo_width(), 780)


if __name__ == "__main__":
    unittest.main()
