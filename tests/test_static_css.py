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


class StaffTopBarTests(unittest.TestCase):
    """BRIEF 4 item 12: the staff top bar uses the console's system (amber New, boxed bell, a labelled search on phones)."""
    css = (STATIC / "exact-staff.css").read_text(encoding="utf-8")

    def rule(self, selector, text=None):
        return re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text or self.css).group(1)

    def test_new_is_the_amber_accent_in_both_themes(self):
        self.assertIn("background: var(--accent-pill)", self.rule(".staff-exact .staff-new"))
        self.assertIn("--accent-pill: linear-gradient(180deg,#F7AE62,#EE8F3E)", self.css)
        self.assertNotIn("--btn-sweep", self.css.split(".staff-exact .staff-new svg")[0].split(".staff-exact .staff-tools")[1])

    def test_new_label_keeps_contrast_on_the_amber(self):
        for stop in ("#F7AE62", "#EE8F3E"):
            self.assertGreaterEqual(_contrast("#2A170A", stop), 4.5)

    def test_bell_sits_in_a_pill(self):
        bell = self.rule(".staff-exact .staff-bell")
        self.assertIn("border: 1px solid var(--staff-rim)", bell)
        self.assertIn("background: var(--staff-pill-bg)", bell)

    def test_bell_turns_opaque_with_its_neighbours(self):
        # BRIEF 10.9: with reduced transparency the bell goes solid like the clock and search beside it.
        block = self.css.split("@media (prefers-reduced-transparency: reduce) {", 1)[1].split("\n}", 1)[0]
        lists = [line for line in block.splitlines() if ".staff-clock" in line]
        self.assertEqual(len(lists), 2)
        for line in lists:
            self.assertIn(".staff-bell", line)

    def test_phone_search_keeps_its_label(self):
        phone = self.css.split("@media (max-width: 900px)")[1]
        self.assertNotRegex(phone, r"\.staff-search :is\(span,kbd\) \{ display: none")
        self.assertIn(".staff-exact .staff-search span { flex: 1", phone)
        self.assertIn(".staff-exact .staff-workspace span { display: none; }", phone)


def _luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return .2126 * r + .7152 * g + .0722 * b


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + .05) / (lo + .05)


class FocusRingTests(unittest.TestCase):
    def test_light_focus_colour_reaches_three_to_one_on_the_light_page(self):
        # KIT-CHECKS check 4. The two colours are the ends of the measured light page background.
        css = (STATIC / "tokens.css").read_text(encoding="utf-8")
        light = css[css.index(':root[data-theme="light"]'):]
        self.assertIn("--focus: var(--accent-tx);", light)
        ring = re.search(r"--accent-tx:\s*(#[0-9A-Fa-f]{6})", light).group(1)
        for page in ("#F6F2ED", "#FAF7F4"):
            self.assertGreaterEqual(_contrast(ring, page), 3)

    def test_accent_stays_the_button_fill_in_light(self):
        css = (STATIC / "tokens.css").read_text(encoding="utf-8")
        self.assertIn("--accent: #C9962A;", css[css.index(':root[data-theme="light"]'):])

    def test_no_focus_indicator_uses_the_accent_directly(self):
        # --accent is 2.4:1 on the light page; a ring or focus border must use --focus.
        bad = []
        for sheet in sorted(STATIC.glob("*.css")):
            for selector, body in re.findall(r"([^{}]*:focus[^{}]*)\{([^{}]*)\}", sheet.read_text(encoding="utf-8")):
                if ":hover" in selector:
                    continue
                if re.search(r"(?:outline(?:-color)?|box-shadow|border-color|stroke)\s*:[^;}]*var\(--accent\)", body):
                    bad.append(f"{sheet.name}: {selector.strip()}")
        self.assertEqual(bad, [])


class FilterChipTextTests(unittest.TestCase):
    def test_chip_text_has_room_for_descenders(self):
        """The chip's font is line-height 1 and its label clips, which cut the tails off "Company"."""
        css = (STATIC / "ui.css").read_text(encoding="utf-8")
        rule = re.search(r"\.u-chip span \{([^}]*)\}", css).group(1)
        self.assertIn("overflow: hidden", rule)
        self.assertIn("line-height: 1.3", rule)


class ConsoleTrailTests(unittest.TestCase):
    def test_top_bar_trail_is_hidden_where_the_title_shows_it(self):
        """.console-trail sets display: flex after the rule hiding .console-area, so it needs its own later rule."""
        css = (STATIC / "admin.css").read_text(encoding="utf-8")
        shown = css.index(".console-trail { display: flex")
        hidden = css.index("@media (max-width: 1200px) { .console-trail { display: none; } }")
        self.assertGreater(hidden, shown)


class BoxRadiusTests(unittest.TestCase):
    def test_count_badges_and_info_icons_are_boxes(self):
        # BRIEF 10.10.2: count badges use the chip radius; only dots, avatars and the like stay round.
        for sheet, selector in (("admin.css", ".fb-count"), ("admin.css", ".seg-n"), ("admin.css", ".count"),
                                ("portal.css", ".cat-part-h h2 .n"), ("ui.css", ".u-info")):
            css = (STATIC / sheet).read_text(encoding="utf-8")
            rule = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css).group(1)
            self.assertIn("border-radius: var(--radius-chip)", rule, selector)


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


class CollectingSinceTests(unittest.TestCase):
    """BRIEF 10.9(2): the Overview chart with fewer than 3 days of use shows its empty state and "Collecting since"."""
    def test_the_usage_chart_gives_way_below_three_days_and_never_pads(self):
        js = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
        self.assertIn("const collecting = usedDays.length < 3;", js)
        self.assertIn('"Collecting since " + fmt.dayMonth(tr.first_use)', js)
        self.assertIn("data: collecting ? [] : week.map(", js)


class LiveWaveTests(unittest.TestCase):
    """dashboard-02's wave on the second count card plots real readings (requests in flight at each refresh), never ornament."""
    def test_the_live_card_draws_its_own_readings_in_amber_beside_the_arrow(self):
        js = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
        self.assertIn("liveReadings.push(live.length);", js)
        self.assertIn("if (liveReadings.length > 24) liveReadings.shift();", js)
        self.assertIn("SUI.sparkline(liveReadings)", js)
        css = (STATIC / "admin.css").read_text(encoding="utf-8")
        self.assertIn(".kpis-exact .kpi .spark:has(.live-wave) { position: absolute; top: 18px; right: 48px;", css)
        self.assertIn(".kpis-exact .live-wave .u-spark .line { stroke: var(--viz-1);", css)
        ui = (STATIC / "ui.js").read_text(encoding="utf-8")
        self.assertIn('preserveAspectRatio: "none", "aria-hidden": "true" });', ui)  # the card states the number


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
        # no outer spread that would make it taller than its 38px line; the rim is inset
        self.assertIn("box-shadow: inset 0 0 0 1px var(--glass-rim), var(--glass-highlight);", rule)
        self.assertNotIn("border:", rule)

    def test_the_light_area_backing_is_the_glass_of_the_pills_beside_it_not_a_flat_white_box(self):
        css = (pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static" / "admin.css").read_text(encoding="utf-8")
        rule = css.split('html[data-theme="light"] .console-bar .console-area {')[1].split("}")[0]
        pills = css.split(".console-workspace, .console-search, .console-clock, .console-account {")[1].split("}")[0]
        self.assertIn("background: var(--glass-bg-strong)", pills)
        self.assertIn("background: var(--glass-bg-strong);", rule)
        self.assertIn("var(--glass-rim)", rule)
        self.assertNotIn("rgba(252, 248, 242", rule)


class StickyTableHeaderTests(unittest.TestCase):
    def test_long_tables_scroll_in_their_panel_and_no_rule_turns_the_header_off(self):
        css = (STATIC / "ui.css").read_text(encoding="utf-8")
        self.assertIn(".u-table-wrap:not(.sheet *, .u-sheet *) { max-height:", css)
        self.assertNotIn(".u-list .u-table thead th { background: transparent; position: static;", css)
        self.assertRegex(css, r"\.u-table thead th \{ position: sticky; top: 0;")


class RoomPhotoTests(unittest.TestCase):
    """BRIEF 10.10.3: the console room ships at three widths with a gradient under it."""

    def setUp(self):
        import pathlib
        self.static = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"
        self.css = (self.static / "admin.css").read_text(encoding="utf-8")

    def test_three_widths_ship_and_the_1920_file_is_in_the_size_range(self):
        for width in (2560, 1920, 960):
            name = "room-suite-%d.webp" % width
            self.assertTrue((self.static / name).is_file(), name)
            self.assertIn('url("/static/%s")' % name, self.css)
        size = (self.static / "room-suite-1920.webp").stat().st_size
        self.assertTrue(180_000 <= size <= 420_000, size)

    def test_a_gradient_sits_under_the_photo(self):
        self.assertIn("--scene-fallback: radial-gradient(", self.css)
        self.assertIn("var(--scene-image) center / cover no-repeat, var(--scene-fallback)", self.css)


class ButtonDefectTests(unittest.TestCase):
    """Probe's real-browser QA of 12 Nov (D1, D2)."""
    root = pathlib.Path(__file__).resolve().parent.parent / "gateway" / "static"

    def test_touch_hit_area_leaves_the_loading_spinner_alone(self):
        css = (self.root / "controls.css").read_text(encoding="utf-8")
        self.assertIn('.btn:not(.link):not(.loading):not([data-loading="true"]):not([aria-busy="true"])::before { content: "";', css)
        self.assertNotIn(".btn:not(.link)::before {", css)

    def test_console_page_actions_are_36px_on_desktop(self):
        css = (self.root / "admin.css").read_text(encoding="utf-8")
        self.assertIn(".top > .top-actions .btn { min-height: 36px; height: 36px;", css)
        self.assertNotIn(".top > .top-actions .btn { min-height: 34px;", css)

    def test_phone_buttons_keep_their_size_and_grow_only_the_hit_area(self):
        """D3: at 640px and narrower a .btn stays 36 / 30 px tall; the shared ::before layer makes the 44px target."""
        controls = (self.root / "controls.css").read_text(encoding="utf-8")
        self.assertIn("@media (hover: none), (max-width: 640px) {\n  .btn:not(.link):not(.loading)", controls)
        admin = (self.root / "admin.css").read_text(encoding="utf-8")
        guide = (self.root / "guide.css").read_text(encoding="utf-8")
        for gone in (".route-people .btn:not(.link), .route-tools .btn:not(.link)", "  .top-actions .btn { min-height: 44px; }",
                     ".route-overview .top > .top-actions .btn, .route-overview .panel-actions .btn { min-height: 44px",
                     ".route-licences .top > .top-actions .btn, .route-reports", ".route-security .top > .top-actions .btn, .route-incidents"):
            self.assertNotIn(gone, admin)
        self.assertNotIn(".next-step .btn { min-height: 44px; }", guide)
        self.assertNotIn(".route-overview .panel-actions .btn { min-height: 44px; }", guide)


if __name__ == "__main__":
    unittest.main()


class NextStepInkTests(unittest.TestCase):
    """A next step that is a link sits inside .lede, whose link colour would paint the button's label (1.1:1 on primary)."""

    def test_a_next_step_link_keeps_the_button_ink(self):
        guide = (STATIC / "guide.css").read_text(encoding="utf-8")
        self.assertIn(".next-step .btn { text-decoration: none; color: var(--btn-ink); }", guide)
        admin = (STATIC / "admin.css").read_text(encoding="utf-8")
        self.assertIn(".lede a { color: var(--tx-1);", admin)  # the rule it has to beat: (0,2,0) > (0,1,1)


class ProbeShellDefectTests(unittest.TestCase):
    """Probe's 12 Nov list: Audit on a phone (C1, C2) and staff touch targets (S2, S3)."""

    def test_audit_email_breaks_after_the_at_sign_and_meta_line_stacks_without_orphan_dots(self):
        css = (STATIC / "admin.css").read_text(encoding="utf-8")
        self.assertIn(".route-audit .audit-who strong { min-width: 0; overflow-wrap: anywhere; }", css)
        phone = css.split(".route-audit .audit-who strong")[1]
        self.assertIn(".route-audit .list-meta { flex-direction: column; align-items: flex-start; }", phone)
        self.assertIn(".route-audit .list-meta > * + *::before { content: none; }", phone)
        js = (STATIC / "admin-monitor.js").read_text(encoding="utf-8")
        self.assertIn('[who.slice(0, at + 1), el("wbr"), who.slice(at + 1)]', js)

    def test_staff_phone_links_tabs_and_rows_get_a_44px_target(self):
        css = (STATIC / "exact-staff.css").read_text(encoding="utf-8")
        block = css.split("@media (hover: none), (max-width: 640px) {")[-1]
        for sel in (".home-h .tlink", ".u-seg button", ".tr-main", ".drawer .hub-staff-nav > a::before"):
            self.assertIn(sel, block)
        self.assertIn("height: 44px; transform: translateY(-50%);", block)

    def test_footer_ask_button_and_phone_bar_items_get_a_44px_target(self):
        """Probe S5/S6 (13 Nov): the bottom bar's items are 42px tall, the footer's Ask button 38px."""
        staff = (STATIC / "exact-staff.css").read_text(encoding="utf-8").split("@media (hover: none), (max-width: 640px) {")[-1]
        self.assertIn(".xf-ask button)::before", staff)
        bar = (STATIC / "exact-staff-bar.css").read_text(encoding="utf-8")
        self.assertIn(".stb-bar a { position: relative; }", bar)
        self.assertIn('.stb-bar a::before { content: ""; position: absolute; top: 50%; left: 0; right: 0; height: 44px; transform: translateY(-50%); }', bar)

    def test_rails_keep_the_10_10_4_radius_of_16(self):
        # BRIEF 10.10.4 (10 Nov review) replaced 10.3's full pill (31) with 16
        self.assertIn("border-radius: 16px; overflow: visible; }", (STATIC / "admin.css").read_text(encoding="utf-8"))
        self.assertIn("border: 1px solid var(--staff-rim); border-radius: 16px;", (STATIC / "exact-staff.css").read_text(encoding="utf-8"))


class StaffToolRowPhoneTests(unittest.TestCase):
    """Staff shell (13 Nov): on phones a tool row's status sits on its own line, so no "·" hangs at a line end."""
    css = (STATIC / "exact-staff.css").read_text(encoding="utf-8")

    def test_phone_rows_stack_status_and_hide_the_dot(self):
        block = self.css.split("so a wrap never leaves")[1].split("\n}\n")[0]
        self.assertIn("@media (max-width: 640px)", block)
        self.assertRegex(block, r"\.staff-exact \.tool-row \.tr-sub \{[^}]*flex-direction: column")
        self.assertRegex(block, r"\.staff-exact \.tool-row \.tr-sub > \.dot \{[^}]*display: none")


class StaffVisibleTouchTests(unittest.TestCase):
    """Probe's re-test of main (13 Nov): on phones the staff controls' visible boxes reach 44px (tests/browser/touch.cjs measures them)."""

    def test_phone_rules_size_the_boxes(self):
        css = (STATIC / "exact-staff.css").read_text(encoding="utf-8")
        block = css.split("Staff touch targets, visible size")[1]
        for part in (".staff-exact :is(main, .xf-panel) .btn, .staff-exact .u-seg button, .staff-exact .p-index button { min-height: 44px; }",
                     ".staff-exact main a.tlink { display: inline-flex; align-items: center; min-height: 44px; }",
                     ".staff-exact .p-more > summary { padding-block: 12px; }",
                     ".staff-exact .xf-ask:is(form, a) :is(input, button, b) { height: 44px; min-height: 44px; }",
                     ".staff-exact .sort .input { min-height: 44px; }"):
            self.assertIn(part, block)

    def test_footer_links_are_44_on_phones(self):
        footer = (STATIC / "exact-footer.css").read_text(encoding="utf-8").split("@media (max-width: 900px)")[1]
        self.assertIn(".staff-exact .xf-col :is(a,button) { height: 44px; white-space: normal; }", footer)
        self.assertIn(".staff-exact .xf-col li { height: 48px; }", footer)

    def test_phone_bar_items_are_44_tall(self):
        bar = (STATIC / "exact-staff-bar.css").read_text(encoding="utf-8")
        self.assertIn("width: 44px; height: 44px; border-radius: 10px;", bar)
