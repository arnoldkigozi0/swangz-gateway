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


def overview_lead(cases):
    source = (STATIC / "admin-guide.js").read_text(encoding="utf-8")
    many = re.search(r"\n  (const many = .*?;)\n", source).group(1)
    fn = re.search(r"\n  (function overviewLead\(n\) \{\n.*?\n  \})\n", source, re.S).group(1)
    script = many + fn + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map(overviewLead)));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class OverviewLeadTests(unittest.TestCase):
    BASE = {"loaded": True, "canStop": True, "canAnswer": True}

    def lead(self, **n):
        return overview_lead([{**self.BASE, **n}])[0]

    def test_the_sentence_carries_the_real_number(self):
        # BRIEF 10.10.7: one plain sentence with the real number
        self.assertEqual(self.lead(urgent=2)["sentence"], "2 things need you now.")
        self.assertEqual(self.lead(urgent=1)["sentence"], "1 thing needs you now.")
        self.assertEqual(self.lead(waiting=3)["sentence"], "3 people are waiting for a tool.")
        self.assertEqual(self.lead(waiting=1)["sentence"], "1 person is waiting for a tool.")
        self.assertEqual(self.lead(secOpen=True, secEvents=4)["sentence"], "4 security warnings in the last 7 days.")
        self.assertEqual(self.lead(items=5)["sentence"], "5 small things to look at.")

    def test_the_most_pressing_thing_wins(self):
        self.assertEqual(self.lead(paused=True, urgent=2, waiting=3)["sentence"], "AI is stopped for everyone.")
        self.assertEqual(self.lead(urgent=2, waiting=3)["action"]["href"], "#/attention")
        self.assertEqual(self.lead(waiting=3, items=9)["action"]["task"], "answer-request")

    def test_a_failed_check_is_not_reported_as_nothing_to_do(self):
        out = self.lead(loaded=False)
        self.assertEqual(out["sentence"], "We could not check what needs you.")
        self.assertTrue(out["action"]["retry"])

    def test_a_role_is_only_offered_what_it_can_do(self):
        self.assertEqual(self.lead(waiting=1, canAnswer=False)["action"]["href"], "#/requests")
        self.assertEqual(self.lead(paused=True, canStop=False)["action"]["href"], "#/live")

    def test_setup_then_calm(self):
        step = {"label": "Add your tools", "href": "#/tools"}
        self.assertEqual(self.lead(setupLeft=3, setupNext=step), {"sentence": "3 setup steps left.", "action": step})
        self.assertEqual(self.lead()["sentence"], "Nothing needs you right now.")


class GuidedTaskTests(unittest.TestCase):
    def test_the_console_loads_the_guide(self):
        html = (STATIC / "admin.html").read_text(encoding="utf-8")
        self.assertIn('src="/static/admin-guide.js"', html)
        self.assertIn('href="/static/guide.css"', html)

    def test_every_tile_has_a_task_and_no_task_guesses_a_route(self):
        source = (STATIC / "admin-guide.js").read_text(encoding="utf-8")
        tasks = set(re.findall(r'"([a-z-]+)": ', re.search(r"const TASKS = \{(.*?)\n  \};", source, re.S).group(1)))
        tasks |= set(re.findall(r"\b([a-z]+-[a-z]+)\": async", source))
        tiles = re.findall(r'\["([a-z]+-[a-z]+)", "[A-Z]', source)
        self.assertGreaterEqual(len(tiles), 6)
        self.assertLessEqual(set(tiles), tasks)

    def test_stopping_all_ai_starts_on_the_safe_answer(self):
        source = (STATIC / "admin-guide.js").read_text(encoding="utf-8")
        self.assertIn('state: { go: "no" }', source)


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
        self.assertEqual(overview.count('class: "btn primary"'), 1)  # Detailed's; Simple's one primary is the next-step button
        self.assertIn('next: view === "simple" ? A.leadButton(lead.action)', overview)
        # Every card opens its list already filtered to the items it counts.
        for href in ('"#/licences?tab=spend&range=30d"', '"#/activity?tab=ai&range=30d"', '"#/activity?tab=usage&range=today&by=person"',
                     '"#/security?view=signals&days=7&severity=warnings"', '"#/attention"', '"#/live"'):
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


class ToolsChainTests(unittest.TestCase):
    """Tools on the control kit (BRIEF 10.10). The browser behaviour is in tests/browser/tools.cjs."""
    source = (STATIC / "admin-govern.js").read_text(encoding="utf-8")

    def test_remove_restore_and_delete_have_their_functions(self):
        # They were called for five weeks after their definitions went, so every press threw a ReferenceError.
        for name in ("toolAction", "deleteTool"):
            self.assertIn("async function %s(" % name, self.source)

    def test_list_uses_the_kit_filter_bar(self):
        body = self.source[self.source.index("async function pageTools("):self.source.index("async function toolAction(")]
        self.assertIn("SUI.filterBar(", body)
        self.assertNotIn("A.seg(", body)
        self.assertNotIn("fb-select", body)

    def test_usage_tab_leaves_people_and_devices_to_access(self):
        usage = self.source[self.source.index("async function usageTab("):self.source.index("async function accessTab(")]
        access = self.source[self.source.index("async function accessTab("):self.source.index("async function billingTab(")]
        for title in ("Who uses it", "Devices that ran it"):
            self.assertNotIn(title, usage)
            self.assertIn(title, access)


class MoneyChainTests(unittest.TestCase):
    """Money on the control kit (BRIEF 10.10). The browser behaviour is in tests/browser/money.cjs."""
    source = (STATIC / "admin-money.js").read_text(encoding="utf-8")

    def section(self, start, end):
        return self.source[self.source.index(start):self.source.index(end)]

    def test_summary_is_four_cards_one_chart_and_each_card_opens_its_filtered_list(self):
        summary = self.section("async function moneySummary(", "async function licencesList(")
        self.assertEqual(summary.count("A.kpi({"), 4)
        self.assertEqual(summary.count("A.panel("), 1)
        self.assertEqual(summary.count("SUI.line("), 1)
        self.assertNotIn("SUI.table(", summary)
        self.assertNotIn('class: "btn primary"', summary)
        self.assertIn('"Nothing needs doing right now."', summary)
        for href in ('"#/licences?tab=spend&range=30d"', '"#/licences?tab=licences&show=paid"',
                     '"#/licences?tab=licences&show=idle"', '"#/licences?tab=renewals&show=soon"'):
            self.assertIn("href: " + href, summary)

    def test_each_list_is_one_table_on_the_kit_filter_bar(self):
        for start, end in (("async function licencesList(", "function utilBar("),
                           ("async function spendList(", "async function renewalsList("),
                           ("async function renewalsList(", "// ------------------------------------------------------------------ Settings")):
            body = self.section(start, end)
            self.assertEqual(body.count("SUI.filterBar("), 1, start)
            self.assertEqual(body.count("SUI.table("), 1, start)
            self.assertIn("pager", body, start)
            self.assertNotIn("SUI.line(", body, start)
            self.assertNotIn("A.seg(", body, start)

    def test_no_page_of_the_chain_goes_back_to_tabs(self):
        self.assertNotIn('A.pageTabs("#/licences"', self.source)

    def test_reports_sit_under_money_in_the_trail(self):
        self.assertIn('trail: [MONEY_ROOT, ["Spend reports"]]', self.source)
        self.assertIn('trail: [MONEY_ROOT, ["Spend reports", "#/reports"], [meta.title]]', self.source)


class ControlKitPageTests(unittest.TestCase):
    """The #/kit page: loaded by the console, owners only, out of the navigation, and it never calls the API."""
    source = (STATIC / "admin-kit.js").read_text(encoding="utf-8")

    def test_console_loads_the_page_after_the_core(self):
        html = (STATIC / "admin.html").read_text(encoding="utf-8")
        self.assertIn('<script src="/static/admin-kit.js"></script>', html)
        self.assertLess(html.index("/static/admin.js"), html.index("/static/admin-kit.js"))

    def test_owner_check_comes_before_any_control(self):
        body = self.source[self.source.index("function pageKit()"):]
        self.assertLess(body.index("A.isOwner()"), body.index("SUI.menuButton("))

    def test_page_reads_and_changes_nothing(self):
        for call in ("api(", "fetch(", "localStorage", "location.hash ="):
            self.assertNotIn(call, self.source)

    def test_every_kit_control_is_shown(self):
        for control in ("SUI.menuButton(", "SUI.splitButton(", "SUI.select(", "SUI.filterBar(", "SUI.sheet(",
                        "SUI.segmented(", "SUI.searchPill(", "A.switchInput(", "SUI.status(", "SUI.badge(",
                        "SUI.progress(", "SUI.skeleton(", "SUI.stateBox(", "SUI.errorBox("):
            self.assertIn(control, self.source)

    def test_page_is_not_in_the_navigation(self):
        self.assertNotIn("#/kit", (STATIC / "admin.js").read_text(encoding="utf-8"))
