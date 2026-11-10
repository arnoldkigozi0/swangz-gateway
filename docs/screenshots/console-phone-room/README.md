# Console at 390: the room around the page

Each sheet is four 390x844 captures: Overview old, Overview new, People old, People new (10 Nov 2026, local fixture,
headless Chromium). The "new" captures were taken by injecting this branch's one rule into a build of the Overview
branch, not from a build of this branch alone.

- Below 900px the page's backing plane now stops 8px short of the left, right and bottom edges, with 18px corners.
- Leftmost text is at x16 and rightmost at x374 on Overview, People and Settings, before and after: nothing moved,
  no text sits in the 8px strips, no horizontal overflow.
- Sampled contrast of every text run in the page is identical before and after, in both themes. The readings below
  4.5:1 are the same in both columns and are sampler artefacts, not visible text: "Person" on People in light (4.41:1)
  is the table's column header, which is clipped to 1px in card mode (`.u-table.cards thead` in `ui.css`) and only
  read by screen readers; the other two runs sit under the bottom tab bar at that scroll position.
- Not run: axe, 768px (the rule also applies there), reduced transparency.
