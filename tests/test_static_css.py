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


class OverviewRoomTests(unittest.TestCase):
    def test_dark_desktop_overview_drops_the_plane_and_its_panels_are_glass(self):
        css = (pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static" / "admin.css").read_text(encoding="utf-8")
        self.assertIn('html:not([data-theme="light"]) .shell.route-overview #main::before { display: none; }', css)
        self.assertIn("background: rgba(129, 117, 120, .60); border-color: var(--glass-rim); -webkit-backdrop-filter: var(--glass-blur); backdrop-filter: var(--glass-blur); }", css)
        self.assertIn('html:not([data-theme="light"]) .route-overview .overview-exact .panel > header { border-bottom: 0; background: none; }', css)
        # every other page, and light, keep the plane
        self.assertIn(".shell #main::before {", css)
        self.assertIn("(prefers-reduced-transparency: reduce)", css.split("OverviewRoom")[0].split(".shell.route-overview #main::before")[1])


class OverviewCountIconTests(unittest.TestCase):
    def test_the_two_count_cards_open_with_a_round_icon(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"
        self.assertIn(".kpis-exact.two .kpi .label > svg:first-child { display: block; box-sizing: border-box; width: 34px; height: 34px;", (root / "admin.css").read_text(encoding="utf-8"))
        js = (root / "admin-monitor.js").read_text(encoding="utf-8")
        self.assertIn('label: "Need attention", icon: "attention"', js)
        self.assertIn('label: "Live requests", icon: "live"', js)


class ConsoleRoomTests(unittest.TestCase):
    def test_other_console_pages_back_only_bare_text_and_dark_panels_are_one_layer_of_glass(self):
        css = (pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static" / "admin.css").read_text(encoding="utf-8")
        self.assertIn(".shell:not(.route-overview) #main::before { display: none; }", css)
        self.assertIn(":where(.shell:not(.route-overview) .page) > :where(:not(.panel, .kpis)) { background: var(--plane);", css)
        glass = css.split('html:not([data-theme="light"]) .shell:not(.route-overview) .page .panel:not(.panel .panel) {')[1].split("}")[0]
        self.assertIn("background: var(--glass-bg-strong);", glass)
        self.assertEqual(glass.count("backdrop-filter: var(--glass-blur)"), 2)
        self.assertNotIn('html[data-theme="light"] .shell:not(.route-overview) .page .panel', css)

    def test_smoked_glass_keeps_every_dark_text_token_readable_over_the_brightest_room(self):
        # the blurred room's brightest point is 155,115,75 (docs/screenshots/console-room/README.md)
        def lum(c):
            c = [x / 255 for x in c]
            c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]

        scene = [155 * .65 + 12 * .35, 115 * .65 + 10 * .35, 75 * .65 + 9 * .35]
        ground = [t * .68 + r * .32 for t, r in zip((22, 19, 17), scene)]
        for name, colour in (("tx-3", "B5ADA5"), ("accent-tx", "E5C48C"), ("ok", "2FD99A"), ("info", "43B9F5"), ("warn", "F5B32B"), ("bad", "FF5D52")):
            rgb = [int(colour[i:i + 2], 16) for i in (0, 2, 4)]
            self.assertGreaterEqual((lum(rgb) + .05) / (lum(ground) + .05), 4.5, name)


class LightAreaLabelTests(unittest.TestCase):
    def test_the_light_area_backing_is_a_pill_the_height_of_its_line_not_a_taller_box(self):
        css = (pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static" / "admin.css").read_text(encoding="utf-8")
        rule = css.split('html[data-theme="light"] .console-bar .console-area {')[1].split("}")[0]
        self.assertIn("padding: 0 12px; margin: 0 -12px; border-radius: var(--radius-control);", rule)
        self.assertNotIn("box-shadow", rule)


class RoomPhotoTests(unittest.TestCase):
    """BRIEF 10.10.3: the console room ships at three widths with a gradient under it."""

    def setUp(self):
        import pathlib
        self.static = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"
        self.css = (self.static / "admin.css").read_text(encoding="utf-8")

    def test_three_widths_ship_and_the_1920_file_is_in_the_size_range(self):
        for width in (2560, 1920, 960):
            name = "room-hall-%d.webp" % width
            self.assertTrue((self.static / name).is_file(), name)
            self.assertIn('url("/static/%s")' % name, self.css)
        size = (self.static / "room-hall-1920.webp").stat().st_size
        self.assertTrue(180_000 <= size <= 420_000, size)

    def test_a_gradient_sits_under_the_photo(self):
        self.assertIn("--scene-fallback: radial-gradient(", self.css)
        self.assertIn("var(--scene-image) center / cover no-repeat, var(--scene-fallback)", self.css)


if __name__ == "__main__":
    unittest.main()
