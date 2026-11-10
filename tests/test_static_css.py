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


if __name__ == "__main__":
    unittest.main()
