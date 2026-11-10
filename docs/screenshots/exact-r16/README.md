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

## Not done / not verified
The 50% overlay against `dashboard-01.jpg`, measured contrast of the 9px caption and the chip, axe, hover motion,
a card with a real percentage in the chip (the fixture has no earlier period), roles other than owner.
Other pages' `.kpis` strips are unchanged.

# R17: the Overview under the cards (BRIEF 10.7 "Overview = dashboard-02")

Builder's note. **Written without a browser**: nothing in this section is measured or captured yet.

## What changed (`admin-monitor.js`, one appended block in `admin.css`, `docs/UI.md`)
- Title is "Hello, <name>!" (the part of the console username before the first `@ . _ -`, capitalised).
- The four tabs (Right now, Trends, Top tools & people, Licences) leave the Overview. In their place: **AI usage**
  (tube chart, eight days) on the left; on the right two count cards, **Need attention** and **Live requests**, and
  **Uses by tool** (top five, 30 days).
- Nothing leaves the product: the top-three urgent list is Needs attention, the live preview is Live, trends and
  leaders are Activity → Who used what, licence opportunities and renewals are Licences & spend.

## Differences, tagged with BRIEF 10.1
- 10.1(1): no emoji in the title; our names and numbers.
- 10.1(3): Uses by tool is a ranked bar list with numbers, not a donut with a legend. The shared kit has no donut
  yet; **this is a defect against 10.7 to close in a later piece, not a permanent difference.**
- 10.1(4): each block's header carries one link to the page that owns the detail.

## Not done / not verified
Positions against dashboard-02, overlay, contrast, axe, phones, the look of the tube chart at this width.
