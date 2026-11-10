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


def donut_parts(calls):
    source = (STATIC / "ui.js").read_text(encoding="utf-8")
    fn = re.search(r"\n  (function donutParts\(rows, total, max\) \{\n.*?\n  \})\n", source, re.S).group(1)
    script = (fn + "\nconsole.log(JSON.stringify(" + json.dumps(calls) + ".map((c) => { const o = donutParts(c[0], c[1], c[2]);"
              " return [o.whole, o.parts.map((p) => [p.row ? p.row.label : null, p.value, Math.round(p.share * 1000) / 1000, p.tone])]; })));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class DonutShareTests(unittest.TestCase):
    def test_shares_are_of_the_true_total_and_the_rest_is_named_other(self):
        rows = [{"label": "A", "value": 6}, {"label": "B", "value": 3}, {"label": "C", "value": 0}]
        self.assertEqual(donut_parts([[rows, 12, 5], [rows, 9, 5], [rows, 0, 5], [rows, 9, 1], [[], 0, 5]]), [
            [12, [["A", 6, 0.5, 1], ["B", 3, 0.25, 2], [None, 3, 0.25, 0]]],
            [9, [["A", 6, 0.667, 1], ["B", 3, 0.333, 2]]],
            [9, [["A", 6, 0.667, 1], ["B", 3, 0.333, 2]]],      # a total smaller than the rows is not believed
            [9, [["A", 6, 0.667, 1], [None, 3, 0.333, 0]]],
            [0, []]])

    def test_light_theme_arcs_reach_three_to_one_on_porcelain(self):
        css = (STATIC / "ui.css").read_text(encoding="utf-8")

        def lum(h):
            c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]

        found = re.findall(r'html\[data-theme="light"\] \.u-donut \.t(\d) \{ stroke: (#[0-9A-F]{6}); color: \2; \}', css)
        self.assertEqual(sorted(t for t, _ in found), ["0", "1", "2", "3", "4", "5"])
        for tone, colour in found:
            ratio = (lum("#FCF8F2") + .05) / (lum(colour) + .05)
            self.assertGreaterEqual(ratio, 3.0, "tone %s %s is %.2f:1" % (tone, colour, ratio))

    def test_dark_orange_reaches_three_to_one_on_room_glass(self):
        css = (STATIC / "ui.css").read_text(encoding="utf-8")
        colour = re.search(r'\.u-donut \{ --donut-orange: (#[0-9A-F]{6});', css).group(1)
        self.assertIn('.u-donut .t1 { stroke: var(--donut-orange); color: var(--donut-orange); }', css)

        def lum(rgb):
            c = [v / 255 for v in rgb]
            c = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in c]
            return sum(v * w for v, w in zip(c, (.2126, .7152, .0722)))

        # Brightest ring-adjacent pixel in the saved #103 dark capture, at (845, 626).
        # Also check the brief's panel target and the opaque reduced-transparency fallback.
        fg = lum(tuple(bytes.fromhex(colour[1:])))
        for bg in ((111, 92, 84), (106, 89, 81), (18, 18, 20)):
            ratio = (fg + .05) / (lum(bg) + .05)
            self.assertGreaterEqual(ratio, 3.0, "%s on %s is %.2f:1" % (colour, bg, ratio))

    def test_uses_by_tool_lives_on_who_used_what_and_overview_is_an_l1(self):
        source = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
        overview = source.split("async function pageOverview(")[1].split("async function pageAttention(")[0]
        usage = source.split("async function usageTab(")[1].split("async function aiTab(")[0]
        # BRIEF 10.10.1: the donut left Overview for Activity > Who used what, grouped by tool. Nothing was deleted.
        self.assertNotIn("SUI.donut(", overview)
        self.assertIn('st.by === "tool" && rows.length', usage)
        self.assertIn('SUI.donut({ label: "Uses by tool in this period"', usage)
        self.assertIn('title: "No AI activity in this period"', usage)
        # Seven blocks: six number cards and the one chart. One primary button, one Next step line, the trail.
        self.assertEqual(overview.count("A.kpi({"), 6)
        self.assertEqual(overview.count("A.panel("), 1)
        self.assertEqual(overview.count('class: "btn primary"'), 1)
        self.assertIn('trail: [["Overview"]], next,', overview)
        self.assertIn('"Nothing needs doing right now."', overview)
        # Every card opens its list already filtered to the items it counts.
        for href in ('"#/licences?tab=spend&range=30d"', '"#/activity?tab=ai&range=30d"', '"#/activity?tab=usage&range=today&by=person"',
                     '"#/security?days=7"', '"#/attention"', '"#/live"'):
            self.assertIn("href: " + href, overview)

    def test_trail_puts_the_chain_in_the_top_bar_with_the_current_page_marked(self):
        source = (STATIC / "admin.js").read_text(encoding="utf-8")
        self.assertIn('el("span", { class: "crumb-here", "aria-current": "page" }, label)', source)
        self.assertIn('const barTrail = o.trail ? chain("console-area console-trail") : null;', source)
        self.assertIn('o.next ? el("p", { class: "lede next-step" }, el("strong", { class: "next-label" }, "Next step"), o.next) : null,', source)
        monitor = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
        for page in ("Needs attention", "Live", "Activity"):
            self.assertIn('title: "%s", trail: [["Overview", "#/"], ["%s"]]' % (page, page), monitor)

if __name__ == "__main__":
    unittest.main()
