"""Exercise the Workstation repair-button handlers even where a Tk display is unavailable."""
import unittest
from unittest.mock import Mock, patch

try:
    from swangz_client import gui
except ImportError:
    gui = None


@unittest.skipUnless(gui, "needs tkinter, but not a display")
class ChromeRepairHandlers(unittest.TestCase):
    def test_google_retry_resyncs_and_reopens_only_google(self):
        app = Mock()
        app.sign_in_google.side_effect = lambda **kw: gui.App.sign_in_google(app, **kw)
        with patch.object(gui.shell, "open_url") as outside:
            gui.App.repair_action(app, gui.repair.RETRY, None)
        outside.assert_not_called()
        app.open_app.assert_not_called()
        self.assertEqual([call[0] for call in app.client.mock_calls], ["refresh", "sign_in_google"])
        self.assertIsNone(app.refusal)

    def test_provider_retry_uses_the_managed_tool_entry_point(self):
        app = Mock()
        with patch.object(gui.shell, "open_url") as outside:
            gui.App.repair_action(app, gui.repair.RETRY, "chatgpt")
        outside.assert_not_called()
        app.open_app.assert_called_once_with("chatgpt", check_first=True)
        app.sign_in_google.assert_not_called()

    def test_windows_repair_offers_the_existing_guided_setup(self):
        app = Mock()
        with patch.object(gui.sys, "platform", "win32"), patch.object(gui.shell, "open_url") as outside:
            gui.App.repair_action(app, gui.repair.CHROME, "chatgpt")
        outside.assert_not_called()
        app.install_chrome.assert_called_once_with()

    def test_macos_repair_opens_only_the_official_chrome_download(self):
        app = Mock()
        with patch.object(gui.sys, "platform", "darwin"), patch.object(gui.shell, "open_url") as outside:
            gui.App.repair_action(app, gui.repair.CHROME, "chatgpt")
        outside.assert_called_once_with(gui.INSTALL_PAGE)
        app.install_chrome.assert_not_called()
        app.open_app.assert_not_called()
