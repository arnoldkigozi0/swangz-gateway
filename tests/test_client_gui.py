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


class FakeClient:
    def __init__(self, signed_in=False):
        self.signed = signed_in
        self.calls = []
        self.paths = SimpleNamespace(home="/tmp", data="/tmp")
        self.login_error = None
        self.cleanup_pending = False
        self.cleanup_error = None
        self.open_error = None

    def signed_in(self):
        return self.signed

    def status(self):
        return {"signed_in": self.signed, "server": "https://ai.swangzavenue.com", "person": {"name": "Nansubuga Grace", "email": "grace@swangzavenue.com"},
                "device": {"name": "Grace's laptop", "owner_kind": "personal"}, "installed": {"claude-code": {"version": "1"}, "codex": {"version": "1"}},
                "last_sync": time.time(), "update_available": True, "client_version": "0.1.0", "autostart": False,
                "recording": "Swangz AI Hub records this device's name... It never reads your files, screen, keystrokes or other programs.",
                "cleanup_pending": self.cleanup_pending}

    def packages(self):
        return MANIFEST_PACKAGES

    def apps(self):
        return [{"id": "canva", "name": "Canva", "category": "Design", "signin": "seat", "company_browser": False, "open": "https://x/go/canva"},
                {"id": "midjourney", "name": "Midjourney", "category": "Image", "signin": "shared", "company_browser": True, "open": "https://x/go/midjourney"}]

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
        if isinstance(w, tk.Button):
            found[str(w.cget("text"))] = w
        found.update(buttons(w))
    return found


@unittest.skipUnless(HAVE_DISPLAY, "needs Tk and a display (run under xvfb-run)")
class WindowTests(unittest.TestCase):
    def make(self, signed_in=True, **kw):
        self.client = FakeClient(signed_in)
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

    def refuse(self, error, page="Apps"):
        app = self.make()
        if page != "Home":
            buttons(app.dock)[page].invoke()
        self.client.open_error = error
        with mock.patch.object(gui.shell, "open_url") as opened:
            buttons(app.content)["Open" if page == "Apps" else "Canva"].invoke()
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
        self.assertEqual(app.statusbar.cget("text"), "Opened in the Swangz workspace window.")

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
        # the only buttons left are the list's own Open buttons, which refuse again, and Dismiss
        self.assertEqual(set(found), {"Open", "Dismiss"})

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
        self.assertEqual(sorted(buttons(app.dock)), ["Apps", "Home", "Packages", "Reports & Hub", "This device"])
        for name, expect in (("Apps", "Opens in a company browser of your own"), ("Reports & Hub", "Open weekly reports"), ("Packages", "Update ready (1.0.0)"), ("This device", "What Swangz records")):
            buttons(app.dock)[name].invoke()
            app.root.update()
            self.assertIn(expect, " ".join(self.everything()), name)

    def test_packages_say_where_each_one_stands_and_what_you_can_do(self):
        app = self.make()
        buttons(app.dock)["Packages"].invoke()
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
        buttons(app.dock)["This device"].invoke()
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
        with mock.patch.object(gui.messagebox, "askyesno", return_value=True):
            buttons(app.content)["Sign out and disconnect this device"].invoke()
        self.assertIn(("logout",), self.client.calls)
        self.assertEqual(app.page, "signin")

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
        buttons(app.dock)["Reports & Hub"].invoke()
        text = " ".join(self.everything())
        self.assertIn("grace@swangzavenue.com", text)
        self.assertIn("open in your browser", text)
        self.assertIn("own browser profile", text)
        self.assertNotIn("Open tools", buttons(app.content))
        with mock.patch.object(gui.shell, "open_hub") as opened:
            for label, page in (("Open weekly reports", "weekly"),
                                ("Open my devices", "devices"), ("Open control room", "admin")):
                buttons(app.content)[label].invoke()
                opened.assert_called_with(self.client, page)
        with mock.patch.object(gui.shell, "open_hub", side_effect=OSError("Browser unavailable")):
            buttons(app.content)["Open weekly reports"].invoke()
        self.assertIn("Browser unavailable", app.statusbar.cget("text"))

    def test_hub_actions_fit_smallest_supported_window(self):
        app = self.make()
        app.root.geometry("780x540")
        app.show("hub")
        app.root.update()
        bottom = app.statusbar.winfo_rooty()
        for label, button in buttons(app.content).items():
            self.assertGreaterEqual(button.winfo_rootx(), app.content.winfo_rootx(), label)
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                 app.content.winfo_rootx() + app.content.winfo_width(), label)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom, label)

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
