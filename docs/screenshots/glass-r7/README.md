# R7: glass list (table, filter pills, search pill, progress, favourite)

Reference: `docs/design/references/stills/dashboard-04.jpg` (and dashboard-03.jpg), BRIEF "Lists/tables" and item 7.
Check script: `tests/browser/lists.cjs` (91 checks, dark and light, 1440x900 and 390x844; `SHOTS=<dir>` re-saves these images).

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
hairline rows and a translucent head. **No live backdrop blur** on the panel, rows, pills or search pill (see Corrections).

## Measured (pixels actually painted behind the glyphs; in the check output)
Text 7.45 to 18.19 against the 4.5 limit in both themes (lowest: light panel subtitle 7.45, light status word 5.28).
Icons 6.36 to 10.86 against 3. Progress fill against its track: dark 4.86, light 3.43 (limit 3).
Reduced motion: no bar animation, transitions at the global .001s. Reduced transparency (emulated in Chrome): the panel goes solid. Touch (390px, touch emulation): pills at least 36px, stars 44px. No horizontal page scroll at 390px.

## Differences from the reference still left
- The reference has a coloured segment chip per row (VIP / Loyal / New) and a loyalty ring; here status keeps the existing word-with-dot
  `SUI.status` (always carries a word) and progress is a bar.
- The reference's pressed pill is a bright solid fill; here it is a light tint with a stronger rim, because a bright fill failed the
  4.5:1 text check over the brightest part of the photo (3.44 and 4.37 measured while tuning).
- Row hover is a tint, not the reference's lifted row.
- Column heading is not sticky inside `.u-list` (the head stays with the panel); the plain table keeps its sticky head.
- No existing screen adopts `listPanel` yet: that touches admin/portal files owned elsewhere. Adopting it is the next step.
- Not measured here: CLS on a real page load; frame rate on real GPU hardware (see Corrections for the software-render numbers).

## Corrections after Probe's exact-head review (BLOCKED on focus and performance)
1. **Focus.** `segmented` and the time-range pills were rebuilt (`replaceChildren`) on every selection, so a keyboard user's focus fell to the body. The buttons are now built once and only `aria-pressed` changes. `lists.cjs` gained 14 checks: arrow then Enter, arrow then Space, Home then Enter all keep focus on the pressed pill; a search with zero rows keeps focus in the box; selecting a pill while zero rows show keeps focus; clearing the search restores the rows. The first of them fails on the previous `ui.js` (checked), so the regression is real.
2. **Performance.** The list panel was one large `backdrop-filter` layer repainted on every hover and filter. It now has none (`.u-list`, a denser tint: dark `rgba(22,19,17,.86)`, light `rgba(250,247,242,.94)`, solid under reduced transparency); rim, highlight and shadow still come from `.u-glass-strong`, so the glass look stays. Contrast rechecked: lowest measured 3.52 (non-text), text far above 4.5.
3. **Trace.** `perf.cjs` here: 1440x900, headless Chrome with `--disable-gpu` (software render), 3 hover sweeps over the rows plus 6 filter changes per run, 4 runs, same build with the blur forced back on (`BLUR=1`) versus off, frame intervals from `requestAnimationFrame`:

| Theme | Blur (old) p95 | No blur (now) p95 | Slow frames (>33 ms) per run, old | now |
|---|---|---|---|---|
| dark | 433-517 ms | 50 ms | 48, 51, 48, 48 | 18, 23, 20, 20 |
| light | 333-383 ms | 33-50 ms | 47, 48, 45, 44 | 17, 17, 13, 10 |

Limits: software rendering on a weak laptop, so absolute numbers say little; the comparison is the point. The harness drives the pointer through Playwright, so a share of the remaining 50 ms frames is input overhead. Not run: a real GPU, a main-branch baseline on the same fixture (main has no list panel), a Chrome performance-trace file.
