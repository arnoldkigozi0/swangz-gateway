# Staff shell at product head f10a78a (10 November 2026, 08:30 Kampala)

Captured by the builder, not an acceptance; Probe's verdict is separate. Playwright's bundled Chromium 156 headless,
local synthetic fixture (`tests/browser/demo.py`, `HUB_UI_FIXTURE=1 HUB_BUSINESS_FIXTURE=1`), Poppins latched.
Supersedes `head-1b95be2/` for the product code; that folder is kept as the record of the previous head.

## Files
- `<page>-<size>-<theme>.png`: Home, Tools, Requests, Weekly, Projects at 1440x852 and 390x844, dark and light (20).
- `overlay-<page>-1440x852-dark.png`: 50% blend with the reference still. Home against `dashboard-01.jpg`, Tools
  `dashboard-03.jpg`, Requests `dashboard-04.jpg`, Weekly `dashboard-05.jpg`, Projects `dashboard-06.jpg`.
- `empty-<page>-…png`: a fresh database (one signed-in person, no grants, no usage, no subscriptions): 1440x852 dark
  and light, 390x844 dark. All 20 cells that were run (390 light too, not committed): axe 0, no sideways overflow, CLS 0.
- `fb-reduced-transparency-…png`, `fb-reduced-motion-…png`: Home, Tools, Weekly at both sizes, dark. Reduced
  transparency = flat `#241F1C` scene and solid panels; no running infinite animations in either mode.
- `summary-<size>.json`: geometry, axe, load timings and layout shift per cell. `layout-shift-sources.txt`: cold-load
  layout-shift entries with source nodes (none). `perf.json`: the scroll run. `contrast-*.txt`: see below.

## Measured at 1440x852 (BRIEF 10.3 target in brackets), same in dark and light
- Search pill x 588, width 345, y 19 to 57 [x 588 to 933, 38 tall, centre y 38]: 0px.
- Workspace x 175 w 135, New x 1082 w 83, clock x 1176 w 76, avatar x 1327 [175–310, 1082–1165, 1176–1252, 1327]: 0px.
  Bell box x 1264 w 38, icon centre x 1283 [1280]: +3px.
- Rail x 67 w 62, y 22 to 832, radius 31; icons 36px, 45px apart, first centre y 111 [112]: -1px.
- Page title text x 179 [178]: +1px; centre y 92 on Tools, Requests, Weekly, Projects [about 93]: -1px. Subtitle y 119 [117]: +2px.
- Tools, Requests, Weekly and Projects each sit on one glass panel x 173 to 1343, top y 66, radius 22. Home: hero,
  report notice, Your tools and Updates are glass panels sharing x 173 and the 1343 right edge.

## Gates (BRIEF 10.9.4)
- **axe** (wcag2a/2aa/21aa): 0 violations in all 20 cells, and in the 20 empty-database cells.
- **Contrast**, rendered pixels behind every text run, 20 cells. Over the real photo: worst 6.57:1 dark, 4.99:1 light
  ("Access active", Home). With the photo replaced by its brightest pixel (164,128,95) everywhere: worst 6.01:1 dark,
  5.07:1 light. The lines reported for this review: light Requests meta, Weekly "Pending / draft", dark Home
  "1 more in Tools" and tool initials are all at or above those worsts. Disabled pagers now pass too (were 3.6 / 2.47).
  The only entries under 4.5 in the txt files are "Observed activity" and "Report state" at 390: the card table's
  screen-reader-only `thead` (`clip: rect(0 0 0 0)`), not painted. Not measured: icon and control (non-text) 3:1.
- **CLS**: 0 with zero layout-shift entries in all 20 cells and on five cold loads with source capture. Before this
  head: 0.0000239 at 390 / 0.0000038 at 1440 from the workspace pill (label and chevron moved 3px when the mark loaded).
- **Scroll**: 19 of 20 cells 58.7–60fps with no frame over 50ms. **Desktop Tools is 46.4 / 46.5fps (dark / light), worst
  frame 50ms, none over 50ms: below the 55fps gate.** The laptop's load average was 6.5–7.4 from other test runs
  during the measurement, and repeated A/B runs of the same code swung between 33 and 48fps, so this number is not
  a clean reading; with the photo removed the same page ran 53–58fps. It needs a re-run on an idle machine.
- **Fallbacks**: reduced transparency and reduced motion shots above. No `backdrop-filter` is used in the staff shell
  at all, so the no-backdrop-filter case is the normal case.

## Remaining differences, each tagged with its BRIEF 10.1 number
- 10.1(1): Hub words, page names, real counts and the Swangz mark replace the CRM's; no decorative title emoji; no presence dot (no presence data).
- 10.1(1)/(4): Home keeps its real launchpad (greeting, status, hero action, report notice, Your tools, Updates) where
  the reference has four KPI cards; its title centre is y 155, +62px. A content difference, not within 4px.
- 10.1(1)/(4): the reference's Export / New customer page actions are absent; these pages have no such actions and none are invented.
- 10.1(4): ten rail page icons plus All pages, where the reference has nine; the Hub has more pages.
- 10.1(2): `room-warm.webp` replaces the reference photo.
- 10.1(3): panel opacity .82 dark / .94 light (reference .52) to hold 4.5:1 over the photo; the page header sits on
  the panel for the same reason, where the reference title is directly over the room.
- 10.1(3): no backdrop blur (scroll performance, f0608ee). The room is now a fixed layer again, as in the reference.
- 10.1(3): disabled pagers are full-strength muted text with a dashed rim instead of a faded button.
- 10.1(3): if Poppins is not loaded 1.2s after the shell mounts, the session keeps Helvetica Neue/Arial.
- 10.1(3): phone and light layouts have no reference still. On phones titles align with panel content (no x 178 inset).
- 10.1(5), not built in this PR: the liquid "S" loader, amber live pulse and Compact density of 10.9; the 10.8 tab bars.

## Not run or not claimed
Colour samples against 10.4, radii other than rail and panels, motion frame-stepping, 430px and the 1280/1024/768
widths on this head (CI's business matrix covers 1440/1280/1024/768/390), non-text contrast, an idle-machine or
4x-throttled performance trace, long-task attribution (load long tasks of 200–690ms are in `summary-*.json`).

## Checks run on this product code
`tests/browser/staff-font.cjs` 30 cells OK (zero shifts); `exact-staff-shell.cjs` exit 0; `exact-staff-shell-model.cjs`
18 PASS; `syntax.py` 29 files; `business.cjs` with `UI_FAST=1` (1440 and 390, both themes): 124 screens, 11 workflows,
no errors; `python3 -m unittest tests.test_portal tests.test_hub`: 56 tests OK. Full Python suite: left to CI.
