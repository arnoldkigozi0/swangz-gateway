"""Static stylesheet checks that need no browser."""
import pathlib
import re
import unittest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"


class FontShorthandTests(unittest.TestCase):
    def test_font_shorthand_never_mixes_inherit_with_other_values(self):
        # 'font: 700 9px/16px inherit' is invalid: the browser drops the whole declaration and the
        # element keeps its inherited size. 'inherit' is only valid as the entire value.
        bad = []
        for sheet in sorted(STATIC.glob("*.css")):
            for value in re.findall(r"(?<![-\w])font\s*:\s*([^;}]+)", sheet.read_text(encoding="utf-8")):
                words = value.replace("!important", "").split()
                if "inherit" in words and len(words) > 1:
                    bad.append(f"{sheet.name}: font: {value.strip()}")
        self.assertEqual(bad, [])

    def test_staff_bar_badge_sets_its_size(self):
        rule = re.search(r"\.stb-badge\s*\{([^}]*)\}", (STATIC / "exact-staff-bar.css").read_text(encoding="utf-8")).group(1)
        for part in ("font-size: 9px", "line-height: 16px", "font-weight: 700", "font-family: inherit"):
            self.assertIn(part, rule)



class ChartEmptyStateTests(unittest.TestCase):
    def test_an_empty_chart_keeps_its_height_and_uses_the_brief_sizes(self):
        # BRIEF 10.9(2): one 15px line on what will appear, one 11px line on why it is empty, same card size
        css = (STATIC / "ui.css").read_text(encoding="utf-8")
        self.assertIn("font-size: 15px", re.search(r"\.u-chart-empty \.what\s*\{([^}]*)\}", css).group(1))
        self.assertIn("font-size: 11px", re.search(r"\.u-chart-empty \.why\s*\{([^}]*)\}", css).group(1))
        js = (STATIC / "ui.js").read_text(encoding="utf-8")
        self.assertEqual(js.count("return chartEmpty(o);"), 2)          # the column chart and the line chart
        self.assertIn("box.style.minHeight = (o.height + 24)", js)
        self.assertNotIn('title: "No data yet"', js)                    # no chart falls back to the generic box


class OverviewExactFitTests(unittest.TestCase):
    def test_first_card_uses_the_reference_amber_in_dark_and_the_page_fits_the_frame(self):
        css = (pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static" / "admin.css").read_text(encoding="utf-8")
        self.assertIn('html:not([data-theme="light"]) .kpis-exact .kpi.gold.link:hover { background: linear-gradient(160deg, rgba(247, 174, 98, .50), rgba(238, 143, 62, .40)); }', css)
        self.assertIn("@media (min-width: 1201px) { .route-overview .page { padding-bottom: 56px; } }", css)


class OverviewCountIconTests(unittest.TestCase):
    def test_the_two_count_cards_open_with_a_round_icon(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"
        self.assertIn(".kpis-exact.two .kpi .label > svg:first-child { display: block; box-sizing: border-box; width: 34px; height: 34px;", (root / "admin.css").read_text(encoding="utf-8"))
        js = (root / "admin-monitor.js").read_text(encoding="utf-8")
        self.assertIn('label: "Need attention", icon: "attention"', js)
        self.assertIn('label: "Live requests", icon: "live"', js)


if __name__ == "__main__":
    unittest.main()
