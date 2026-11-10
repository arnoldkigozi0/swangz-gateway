# R16 piece 2: the staff app's phone bottom bar, bar C (BRIEF 10.8) — 10 November 2026

Builder's captures, not an acceptance. Bundled Chromium headless at 390x844, synthetic fixture. Staff app only:
`portal.js` (`phoneBar`, `phoneLens`), new `exact-staff-bar.css`, one line in `index.html`. Shown at 700px and under.

Measured, same in both themes: bar 260x52 (5H x H) at x 34, round button 52x52 at x 304, 10px apart, the pair
centred, 12px above the bottom edge; active item a 104x42 pill (2H x .81H) with its label, the other three 44x44
icon-only; the last page content ends 28px above the bar when scrolled to the end. No sideways overflow, CLS 0,
bar hidden at 1440. Keyboard Enter on an item navigates; tapping the round button opens Access requests.
Lens: 109x60 (2.1H x 1.15H), follows a held pointer, and on release the item under it opens and the lens is removed.

axe (wcag2a/2aa/21aa): 0 on Home, Tools, My tools, Alerts, Access requests in both themes when the page is settled.
In two earlier runs that scrolled to the page end and back just before axe, `color-contrast` was reported on the
footer's "Name a tool" input (#65) on one or two cells; it did not reproduce on a settled page with or without the
bar, so it is not attributed here and is not cleared either.

Differences, tagged with BRIEF 10.1:
- 10.1(1)/(4): the third item is **My tools** (`#/tools?show=mine`), not "Saved tools": the Hub has no saved-tools
  feature and none is invented. Round button = Access requests, badge = tools you have asked for and are waiting on.
- 10.1(3): the bar is solid `#F4F0EC`, not see-through glass: page content was readable through it. Same bar in both themes.
- 10.1(3): badge `#B51E33` (white text 4.5:1) instead of `#E5383B`.
- 10.1(3): the items are links in a `nav` with `aria-current`, not a tablist: they change page.
- 10.1(3): reduced motion = no lens. The lens is `blur(2px) brightness(.9)`, not the SVG refraction, and it does not
  animate into the pill on release (the page re-renders with the new active item).
- 10.1(1): the magnifier is drawn heavier when active instead of filled.

Not done: frame-stepped comparison with `glassy-nav-tabs.mp4`, the lens's shrink-into-pill motion, a real phone or
touch-device run (the lens was driven with a mouse pointer), the control room's bar C, sizes between 391 and 700px
other than CI's matrix, rendered contrast sampling beyond axe.

Checks: `business.cjs` at 390 both themes (62 screens, 11 workflows, no errors), `paused.cjs` 80, `syntax.py` 35 files.
