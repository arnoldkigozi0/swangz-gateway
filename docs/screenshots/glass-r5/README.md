# R5 glass tube bars

Reference: `docs/design/BRIEF.md` §4 (charts), still `dashboard-02` (Revenue tubes with the amber current bar and floating label).
Shots: `tubes-{dark,light}-{1440x900,390x844}.png` (admin Overview, Trends tab, "Usage per day"), `tubes-hover-{dark,light}-1440x900.png` (hover moves the current bar), `tubes-growing-dark-1440x900.png` (about 40 ms into the grow).
Regenerate: `node docs/screenshots/glass-r5/check.cjs` (Playwright and Chrome; starts `demo_history.py`).

The history in the shots is synthetic: `demo_history.py` adds 30 days of invented tool opens to a throwaway test database. The chart itself reads the real `/trends` series; nothing is faked client-side.

## Differences still left versus the reference
- The reference tubes are about 12 px wide and tall (a full-width revenue panel); the 30-day usage chart is 170 px high with thinner tubes, so it reads smaller.
- Tube fill is a plain translucent gradient plus a thin highlight; there is no blurred top glow (a filter per bar would cost frames on this laptop).
- The tooltip stays (it carries the date and the breakdown), so on hover it can cover the floating value label.
- The light theme tubes are warm grey rather than frosted white.
- Only `SUI.columns` changed; `SUI.line` and the ranked bars keep their look (the donut and gauge are not part of R5).
