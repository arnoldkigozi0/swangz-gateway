# R16: the Overview's KPI row (BRIEF 10.3 "KPI cards", 10.7)

Builder's capture, not an acceptance. System Chromium headless through Playwright, local synthetic fixture
(`tests/browser/demo.py`), owner role, 10 November 2026.

## Measured at 1440x852, dark and light (target in brackets)
- Row x 173 to 1349, y 140 to 292 [first card x 173, y 140 to 292]: 0px.
- Cards x 173-458, 470-755, 767-1052, 1064-1349: each 285 wide, 12px gaps [285, 12]: 0px. Radius 18.
- Label box starts (19, 19) inside the card [(18, 22)]; arrow circle 24x24, 15px from the top and right edges;
  value 24px weight 700, box y 232 to 260 [baseline y 255]; chip beside the value; caption 9px, y 261 to 273.
- The next block (tabs) starts y 310. No horizontal overflow at 1440 or 390; no page errors.
- 390x844: 2-up, cards 173 wide; the change chip sits under the value (beside it, it ran past the card).

Files: `overview-1440x852-dark.png`, `overview-1440x852-light.png`, `overview-390x844-dark.png`.

## What changed (`gateway/static/admin-monitor.js`, `gateway/static/admin.css`)
- The Overview's three joined cells are now four separate cards: AI spend (accent glass), AI requests, Active people,
  Security events. AI requests is new on the Overview and comes from the same `/trends` totals; each card opens the
  page that holds its detail.
- Card: radius 18, padding 18, 152px tall; label 11px top-left; arrow in a 24px circle top-right; value 24px weight
  700 bottom-left; change chip beside the value; one 9px caption under.
- The row ends at x 1349, 6px past the content column (x 1343), as the reference's four 285px cards do.

## Differences, tagged with BRIEF 10.1
- 10.1(1): our labels and numbers; each label names its period ("30 days", "today", "7 days").
- 10.1(3): no live blur on the cards; they sit on the page's backing plane from R15 piece 1, so the room shows around
  the row more than through it.
- 10.1(3): the change chip has its own backing so its colour keeps contrast on the accent card; the security card
  shows a status word in the chip, not a percentage.
- 10.1(3): at 1200px and below the cards are fluid, 2-up, with an 11px caption.
- 10.1(4): the spend sparkline left the card (the Trends tab below has the chart).

## Measured, 1440x852 (ours against dashboard-02, read off the still by eye, so within a few px)
| Block | Reference | Ours |
|---|---|---|
| AI usage panel | x180-752, y315-780 | x173-755, y310-780 |
| Count card 1 | x770-1047, y315-535 | x767-1052, y310-530 |
| Count card 2 | x1063-1342, y315-535 | x1064-1349, y310-530 |
| Uses by tool | x770-1342, y555-780 | x767-1349, y542-791 |

The two columns are equal, so the chart sits under KPI cards 1-2 and the count cards under 3-4, as in the still.
The chart is 350px tall above 1000px wide and 250px below it. `r17-overlay-overview-1440x852-dark.png` is the 50% overlay.

## Checks run
- **Layout shift on a cold load: 0** in all four cells (1440x852 and 390x844, dark and light). CI had found 0.025 from
  the chart being drawn a frame late; its height is now held in CSS.
- **axe (wcag2a, wcag2aa, wcag21aa): no violations** in the four cells. axe could not judge 55 runs over the photo,
  so those were sampled:
- **Sampled contrast** (every visible text run against the pixels behind it): worst 5.56:1 dark and 4.74:1 light at
  1440; nothing below 4.5:1. At 390 the sampler flagged two runs that sit *under* the bottom tab bar at that scroll
  position (the chart's value label, and the active tab's label, which the sampler reads against the wrong layer).
  Looked at by eye they are a dark label on the white pill and a hidden label; not counted as failures, not proven by measurement.
- No horizontal overflow at either width; no page errors.

## Still different from dashboard-02
- Uses by tool is a ranked bar list, not a donut (defect against 10.7, above).
- At 1440x852 the page is 871px tall, so it scrolls by 19px; the reference fits the screen.
- Our count cards have no round icon at the top left and the reference's wave line is not drawn.
- With one day of data the chart has one tube; the reference has eight. Not padded (10.9.2).
- Not run: motion, reduced-transparency and reduced-motion captures, the 4x CPU trace.

### Open colour difference on the first card (D1, from Probe's check of R16)
The reference's first KPI card samples near `#8A6540` (BRIEF 10.4, corrected for compression); ours renders darker.
This is a defect against 10.4, not one of the 10.1 allowed differences. It is not fixed here: the tint has to be
sampled in a browser over the same point of the room before it is changed.
