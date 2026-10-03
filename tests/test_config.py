"""Settings from a .env file: comments, quotes, and the example file itself."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from gateway.config import Settings, load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))


class DotenvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sgw-env-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def load(self, text):
        path = os.path.join(self.tmp, ".env")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        with mock.patch.dict(os.environ, {}, clear=True):
            load_dotenv(path)
            return dict(os.environ)

    def test_a_comment_after_a_value_is_not_part_of_it(self):
        env = self.load("GATEWAY_DATA=data   # the record\nEMPTY=    # nothing here\nURL=https://a.example/x#top\n"
                        "QUOTED=\"pass # word\"\n# GATEWAY_PORT=1\nexport PLAIN=yes\n")
        self.assertEqual(env, {"GATEWAY_DATA": "data", "EMPTY": "", "URL": "https://a.example/x#top",
                               "QUOTED": "pass # word", "PLAIN": "yes"})

    def test_the_example_file_gives_clean_settings(self):
        """Copying .env.example as it is must never give a setting a comment for a value."""
        with open(os.path.join(HERE, "..", ".env.example"), encoding="utf-8") as f:
            env = self.load(f.read())
        self.assertTrue(all("#" not in v for v in env.values()), {k: v for k, v in env.items() if "#" in v})
        settings = Settings.from_env(env)
        self.assertEqual((settings.data_dir, settings.tz_offset_minutes), ("data", 180))
        self.assertEqual((settings.workspace_agent_url, settings.workspace_agent_token), ("", ""))


if __name__ == "__main__":
    unittest.main()
