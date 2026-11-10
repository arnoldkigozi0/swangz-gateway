# R5 glass tube bars

Reference: `docs/design/BRIEF.md` §4 (charts), still `dashboard-02` (Revenue tubes with the amber current bar and floating label).
Shots: `tubes-{dark,light}-{1440x900,390x844}.png` (admin Overview, Trends tab, "Usage per day"), `tubes-hover-{dark,light}-1440x900.png` (hover moves the current bar), `tubes-growing-dark-1440x900.png` (about 40 ms into the grow).
Regenerate: `node docs/screenshots/glass-r5/check.cjs` (Playwright and Chrome; starts `demo_history.py`).

The history in the shots is synthetic: `demo_history.py` adds 30 days of invented tool opens to a throwaway test database. The chart itself reads the real `/trends` series; nothing is faked client-side.

## Fixes after Probe's review of 42ce9b7
- Empty data: `SUI.columns` with no rows now returns the shared empty state ("No data yet") instead of throwing.
- Height is exactly proportional to the value (a 1px floor only so a non-zero day is visible); the cap radius is `min(width, height) / 2`, so a short bar is a small rounded stub, not a taller one. The check compares every bar to the table view's values (max error 0.00 px).
- Tubes are wider (about 66% of the day's slot, up to 24 px) and the chart is taller (210 px by default). At 1440 wide the 30-day chart in a half-width panel gives 10 px tubes.
- The hover tooltip is anchored above the floating value label, so the two no longer overlap (checked by bounding boxes).
- The harness now measures a real CLS (layout-shift entries from the first frame) instead of `null`; it reads 0 on every run.
- Contrast (`ui.css`, tube block only): the 1px rim and the current bar's edge now reach 3:1 against what is really behind the chart (WCAG 1.4.11). Measured by `check.cjs` at both sizes: dark rim 6.2:1, current 11.42:1; light rim 3.9:1, current 4.44:1 (see `results.json`). Light selected colour is #A86A06, not the suggested #B8780A, which measures only 3.3-3.7:1. The tube fill itself stays translucent by design; the rim carries the boundary. While a tube is hovered its opacity drops to .78, which lowers its rim slightly; the resting and current states are what is asserted.

## Differences still left versus the reference
- The reference tubes are wider and taller still (a full-width revenue panel); the 30-day usage chart lives in a half-width panel.
- Tube fill is a plain translucent gradient plus a thin highlight; there is no blurred top glow (a filter per bar would cost frames on this laptop).
- The light theme tubes are warm grey rather than frosted white.
- Only `SUI.columns` changed; `SUI.line` and the ranked bars keep their look (the donut and gauge are not part of R5).
