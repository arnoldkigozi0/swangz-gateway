"""#333: the apps start sign-in on the company's Hub, the person can still choose another, and nothing else changes."""
import sys
import unittest
from pathlib import Path
from unittest import mock

from swangz_client import cli, core

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
import secret_scan  # noqa: E402

HUB = "https://hub.ictconnect.org"


class DefaultAddressTests(unittest.TestCase):
    def test_the_default_is_a_plain_https_address(self):
        self.assertEqual(core.DEFAULT_SERVER, HUB)
        self.assertEqual(core.normalise_server(core.DEFAULT_SERVER), HUB)

    def login(self, argv, typed=""):
        client = mock.Mock()
        client.login.side_effect = core.ApiFailure(0, "offline", "stop here")
        with mock.patch("builtins.input", return_value=typed) as asked, mock.patch.object(cli, "say"):
            try:
                cli.main(argv, client=client)
            except core.ApiFailure:
                pass
        return client.login.call_args.args[0], asked

    def test_the_command_line_takes_the_default_on_enter(self):
        for typed in ("", "   "):
            server, asked = self.login(["login"], typed)
            self.assertEqual(server, HUB)
            self.assertIn(HUB, asked.call_args.args[0])

    def test_the_command_line_still_takes_another_address(self):
        self.assertEqual(self.login(["login"], " other.example.org ")[0], "other.example.org")
        server, asked = self.login(["login", "--server", "https://other.example.org"])
        self.assertEqual(server, "https://other.example.org")
        asked.assert_not_called()

    def test_the_extension_starts_on_the_same_address_and_keeps_a_chosen_one(self):
        popup = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")
        self.assertIn(f'value: st && st.base ? st.base : "{HUB}"', popup)

    def test_the_release_scan_allows_only_the_default_hub_name(self):
        def hits(data):
            found = []
            secret_scan.scan_bytes(data, "build", found)
            return [h["sample"] for h in found]
        self.assertEqual(hits(HUB.encode()), [])
        for other in (b"https://staging.ictconnect.org", b"ictconnect.org", b"https://hub.swangzavenue.com"):
            self.assertEqual(len(hits(other)), 1, other)


if __name__ == "__main__":
    unittest.main()
