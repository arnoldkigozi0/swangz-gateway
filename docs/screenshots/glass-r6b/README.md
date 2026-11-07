# R6b glass line chart

Reference: `docs/design/BRIEF.md` §4 (line chart with gradient area fill and dot markers), still `dashboard-04` (Cohort Growth Trajectory: smooth curve, soft area, dots on the curve, lit end point).
Shots: `line-{dark,light}-{1440x900,390x844}.png` (admin Overview, Trends tab, "Spend per day"), `line-hover-{dark,light}-1440x900.png` (crosshair, lit dot and tooltip on a day), `line-drawing-dark-1440x900.png` (about 400 ms into the draw-in).
Regenerate: `node docs/screenshots/glass-r6b/check.cjs` (Playwright and Chrome; starts `demo_spend.py`).

The spend in the shots is synthetic: `demo_spend.py` adds 30 days of invented priced requests to a throwaway test database. The chart reads the real `/trends` series; nothing is faked client-side.

## What changed
Only the `SUI.line` renderer in `gateway/static/ui.js` (plus a small `smoothPath` helper beside it). Same call signature, same data, same tooltip, arrow-key reading, table view and end label. The `aria-label` now also states the latest and highest values.
Callers (unchanged): admin Overview "Spend per day" (`admin-monitor.js`), Licences & spend "Spend per day" (`admin-money.js`), staff "Declarations filed over time" (`business-ui.js`).
- Curve: monotone cubic through the real points, so it never dips below zero or above a day's value.
- Area: a vertical gradient from the series colour to transparent (`--viz-1`, or `--viz-2` for `tone: 2`), so the light theme follows the tokens.
- Glow: a wider, faint copy of the stroke under the line (no SVG filter, so no per-frame cost).
- Dots: markers on the days the axis names; the latest point is a lit dot with a halo that follows the crosshair.
- Motion: the curve opens left to right once, the first time it is in view (a clip rect animated with transform, then the end dot fades in); reduced motion draws everything at once.
- No `ui.css` change: styling uses the tokens through CSSOM and SVG attributes. The old flat `.area` rule is simply no longer used by this chart (the sparkline still uses it).

## Differences still left versus the reference
- The reference plots two series with a legend and a shaded band between them; `SUI.line` is one series, so there is one curve.
- The reference area is a dark glass slab behind the plot; here the plot sits directly on the panel's glass.
- The reference has dots only at a few points; here they follow the axis labels (3 to 6 depending on width).
- The glow is a faint stroke copy, not a blurred bloom.
- Gauge and donut are not part of R6b.
