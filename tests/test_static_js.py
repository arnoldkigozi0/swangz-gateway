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


def zero_reason(calls):
    source = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
    fn = re.search(r"\n  (function zeroReason\(card, n\) \{\n.*?\n  \})\n", source, re.S).group(1)
    script = fn + "\nconsole.log(JSON.stringify(" + json.dumps(calls) + ".map((c) => zeroReason(c[0], c[1]))));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class OverviewZeroReasonTests(unittest.TestCase):
    def test_a_zero_count_carries_one_line_on_why(self):
        # BRIEF 10.9(2): counts of 0 show "0" with a one-line reason
        self.assertEqual(zero_reason([
            ["spend", {"cost": 0, "requests": 0}], ["spend", {"cost": 0, "requests": 4}],
            ["requests", {"requests": 0, "before": 0}], ["requests", {"requests": 0, "before": 1200}],
            ["people", {"today": 0, "month": 0}], ["people", {"today": 0, "month": 7}],
            ["security", {"events": 0}], ["attention", {"items": 0}], ["live", {"live": 0}]]),
            ["No metered requests in 30 days", "Requests ran, none carried a cost",
             "No requests in 30 days", "No requests in 30 days · 1,200 in the 30 before",
             "Nobody has used AI in 30 days", "Nobody has used AI today · 7 in 30 days",
             "No warnings in 7 days", "Nothing is flagged right now", "No requests in flight"])

    def test_a_count_that_is_not_zero_keeps_the_cards_usual_note(self):
        self.assertEqual(zero_reason([
            ["spend", {"cost": 0.004, "requests": 1}], ["requests", {"requests": 3, "before": 0}],
            ["people", {"today": 1, "month": 1}], ["security", {"events": 2}],
            ["attention", {"items": 1}], ["live", {"live": 1}], ["unknown", {}]]), [None] * 7)

    def test_every_overview_card_asks_for_its_reason(self):
        source = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
        for card in ("spend", "requests", "people", "security", "attention", "live"):
            self.assertIn('zeroReason("' + card + '"', source)


if __name__ == "__main__":
    unittest.main()
