# R16: the Overview's KPI row (BRIEF 10.3 "KPI cards", 10.7)

Builder's note. **Written without a browser** (the team's one browser slot was in use): nothing below is measured
yet. The positions are worked out from the R15 piece 3 measurements (content column x 173 to 1343, header ends y 147).
CI runs the browser suites. No screenshots or overlay yet.

## What changed (`gateway/static/admin-monitor.js`, `gateway/static/admin.css`)
- The Overview's three joined cells are now four separate cards: AI spend (accent glass), AI requests, Active people,
  Security events. AI requests is new on the Overview and comes from the same `/trends` totals; each card opens the
  page that holds its detail.
- Card: radius 18, padding 18, 152px tall; label 11px top-left; arrow in a 24px circle top-right; value 24px weight
  700 bottom-left; change chip beside the value; one 9px caption under.
- Intended at 1440: row y 140 to 292, cards 285 wide with 12px gaps from x 173 (so the row ends at x 1349, 6px past
  the content column, as in the reference).

## Differences, tagged with BRIEF 10.1
- 10.1(1): our labels and numbers; each label names its period ("30 days", "today", "7 days").
- 10.1(3): no live blur on the cards; they sit on the page's backing plane from R15 piece 1, so the room shows around
  the row more than through it.
- 10.1(3): the change chip has its own backing so its colour keeps contrast on the accent card; the security card
  shows a status word in the chip, not a percentage.
- 10.1(3): at 1200px and below the cards are fluid, 2-up, with an 11px caption.
- 10.1(4): the spend sparkline left the card (the Trends tab below has the chart).

## Not done / not verified
Pixel positions, the 4px overlay, contrast of the 9px caption and the chip (both themes), axe, hover motion, phones.
Other pages' `.kpis` strips are unchanged.
