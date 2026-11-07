# R7: glass list (table, filter pills, search pill, progress, favourite)

Reference: `docs/design/references/stills/dashboard-04.jpg` (and dashboard-03.jpg), BRIEF "Lists/tables" and item 7.
Check script: `tests/browser/lists.cjs` (77 checks, dark and light, 1440x900 and 390x844; `SHOTS=<dir>` re-saves these images).

| File | View |
|---|---|
| list-desktop-dark.png / list-desktop-light.png | 1440x900 |
| list-mobile-dark.png / list-mobile-light.png | 390x844 (table turns into cards) |

## What the screenshots show (and do not)
The page is the real console (`/admin`, test database via `tests/browser/demo.py`) with a list mounted by `SUI` in `main`.
**No existing page uses the new list yet.** The first row is the demo database's real person; the other four rows are
placeholders (example.test addresses, invented budget percentages and favourites). They exist to show the states.

## New in ui.js / ui.css
`SUI.listPanel` (strong-glass panel, title left, filter pills and search pill right), `SUI.segmented` (filter pills, one pressed,
arrow keys/Home/End), `SUI.searchPill`, `SUI.progress` (slim bar plus its number, `role=progressbar`), `SUI.star` (favourite toggle).
`.u-seg` (also used by the time-range control) is now a glass pill track. The table itself is unchanged; inside `.u-list` it gets
hairline rows and a translucent head. One blur layer: the panel. Rows, pills and the search pill have none.

## Measured (pixels actually painted behind the glyphs; in the check output)
Text 7.45 to 18.19 against the 4.5 limit in both themes (lowest: light panel subtitle 7.45, light status word 5.28).
Icons 6.36 to 10.86 against 3. Progress fill against its track: dark 4.86, light 3.43 (limit 3).
Reduced motion: no bar animation, transitions at the global .001s. Reduced transparency (emulated in Chrome): the panel drops its blur and
goes solid. Touch (390px, touch emulation): pills at least 36px, stars 44px. No horizontal page scroll at 390px.

## Differences from the reference still left
- The reference has a coloured segment chip per row (VIP / Loyal / New) and a loyalty ring; here status keeps the existing word-with-dot
  `SUI.status` (always carries a word) and progress is a bar.
- The reference's pressed pill is a bright solid fill; here it is a light tint with a stronger rim, because a bright fill failed the
  4.5:1 text check over the brightest part of the photo (3.44 and 4.37 measured while tuning).
- Row hover is a tint, not the reference's lifted row.
- Column heading is not sticky inside `.u-list` (the head stays with the panel); the plain table keeps its sticky head.
- No existing screen adopts `listPanel` yet: that touches admin/portal files owned elsewhere. Adopting it is the next step.
- Not measured here: frame rate on this software-rendered laptop (the panel is one blur layer over a static page); CLS on a real page load.
