# Staff shell: top bar in the console's system (BRIEF §4 item 12)

Builder's capture, not an acceptance. Headless Chromium through Playwright, local synthetic fixture
(`tests/browser/demo.py`), staff person Grace, 12 November 2026. Produced by `tests/browser/exact-staff-shell.cjs`
with `UI_OUTPUT` set to this folder.

## What changed (`gateway/static/exact-staff.css` only)
- **New** is the amber accent pill (`--accent-pill`, the same gradient as the console's New), in both themes. It was
  off-white in dark and black in light, so the staff app's top bar did not match the console's or the reference's.
- **The bell** sits in a pill (rim and fill of the other top-bar controls), as the console's bell does. It was a bare icon.
- **Phones (≤ 900px):** the search keeps its label "Search pages…" (it was an icon centred in a 110px empty box); to
  make room, the workspace pill shows only its mark and chevron. The button's accessible name is unchanged
  ("Open navigation").
- No markup, script or page content changed.

## Measured at 1440×852 against dashboard-02 (`overlay-dark.png`, `beside-dark.png`)
Geometry checks in the harness, within 4px of the reference: rail x 67, y 22, 62×810; workspace x 175, y 19, 135×38;
search x 588, y 19, 345×38; New x 1082, y 19, 83×38; account x 1327, y 19, 36×38. All passed.
axe: 0 violations in all four cells (1440×852 and 390×844, dark and light). No horizontal overflow, no page errors.

## Remaining differences, tagged with BRIEF 10.1
- 10.1(1): our labels ("Swangz AI Hub · Your workspace", "Home", "Search pages…"), our page content below the bar.
- 10.1(1): the avatar shows initials, not a photo; no presence dot (the staff endpoint has no presence evidence).
- 10.1(3): on phones the workspace pill drops its two text lines so the search label fits; the console instead moves
  search to a second row. The staff phone already has the bottom bar (§10.8 bar C) for page navigation.
- 10.1(3): New brightens slightly on hover/focus instead of the gold sweep the other staff buttons use, because a
  gold sweep over amber has no visible change.

## Other checks run on this head
`touch.cjs` 250 checks, `kit.cjs` 263 checks, `staff-font.cjs` 30 cells: all exit 0.
`python3 -m unittest tests.test_static_css tests.test_portal tests.test_hub`: 81 OK.
Not run: the full Python suite (CI runs it), Probe's real-browser check.
- Before (main): `before-1440-852-dark.png`, `before-390-844-light.png`.
