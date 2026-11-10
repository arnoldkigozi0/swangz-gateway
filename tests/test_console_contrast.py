"""The console's pop menus: the danger item (Stop all AI) must be readable in both themes.

Reads the design tokens straight from the CSS, so it needs no server and no browser."""
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "gateway" / "static"


def _luminance(hex_colour):
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def tokens():
    """{'dark': {name: value}, 'light': {...}} for the #RRGGBB tokens."""
    css = (STATIC / "tokens.css").read_text(encoding="utf-8")
    cut = css.index(':root[data-theme="light"]')
    read = lambda text: dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\s*;", text))
    return {"dark": read(css[:cut]), "light": read(css[cut:])}


class ConsoleMenuContrast(unittest.TestCase):
    def test_danger_item_uses_the_readable_red(self):
        css = (STATIC / "admin.css").read_text(encoding="utf-8")
        rule = re.search(r"\.console-pop button\.danger\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule)
        self.assertIn("color: var(--bad-hi)", rule.group(1))

    def test_danger_text_is_readable_on_the_menu_in_both_themes(self):
        for theme, t in tokens().items():
            with self.subTest(theme=theme):
                self.assertGreaterEqual(contrast(t["--bad-hi"], t["--ink-2"]), 4.5)

    def test_the_old_light_red_was_the_failure(self):
        # #CE4136 on the light menu is 4.49:1: keeps this check honest about what it guards.
        t = tokens()["light"]
        self.assertLess(contrast(t["--bad"], t["--ink-2"]), 4.5)


if __name__ == "__main__":
    unittest.main()
