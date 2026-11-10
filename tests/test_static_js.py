"""Checks of the shared front-end kit that need no browser: the function is read out of ui.js and run in Node."""
import json
import pathlib
import re
import shutil
import subprocess
import unittest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"


def money(values):
    source = (STATIC / "ui.js").read_text(encoding="utf-8")
    body = re.search(r"\n    money\(v\) \{\n(.*?)\n    \},\n", source, re.S).group(1)
    script = ("const money = function (v) {\n" + body + "\n};\n"
              "console.log(JSON.stringify(" + json.dumps(values) + ".map((v) => money(v))));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class MoneyFormatTests(unittest.TestCase):
    def test_an_amount_under_a_cent_says_so_and_nothing_shows_more_than_two_decimals(self):
        # BRIEF 10.9(2): "$0.0054" looked broken on a card; zero stays zero, and a missing price stays "unpriced"
        self.assertEqual(money([0.0054, 0.0099, 0, None, 0.01, 0.5, 12.345, 1234.5, -0.004]),
                         ["< $0.01", "< $0.01", "$0.00", "unpriced", "$0.01", "$0.50", "$12.35", "$1,234.50", "> -$0.01"])

    def test_no_money_text_is_built_with_more_than_two_decimals(self):
        body = re.search(r"\n  const fmt = \{\n(.*?)\n    num\(n\)", (STATIC / "ui.js").read_text(encoding="utf-8"), re.S).group(1)
        self.assertEqual(re.findall(r"toFixed\(([3-9])\)", body), [])


if __name__ == "__main__":
    unittest.main()
