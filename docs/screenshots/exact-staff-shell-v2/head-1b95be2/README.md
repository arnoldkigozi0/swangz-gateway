# Staff shell at product head 1b95be2 (10 November 2026, 07:31 Kampala)

Captured by the builder, not an acceptance. System Chrome headless through Playwright, local synthetic fixture
(`tests/browser/demo.py`, `HUB_UI_FIXTURE=1`), Poppins latched. Probe's verdict is separate.

## Files
- `<page>-1440x852-dark.png` for Home, Tools, Requests, Weekly, Projects; Home and Tools also at 1440x852 light and 390x844 dark/light.
- `overlay-<page>-1440x852-dark.png`: 50% blend with the reference still. Home against `dashboard-01.jpg`, the four
  section pages against `dashboard-03.jpg` (the builder's choice of still; both are 1440x852).
- `contrast-summary.json`: text contrast from rendered pixels, 20 cells (5 pages, 1440x852 and 390x844, dark and light).

## Measured at 1440x852 dark (BRIEF 10.3 target in brackets)
- Search pill x 588, width 345, height 38, y 19 to 57 [x 588 to 933, 38 tall, centre y 38]: 0px.
- Page title text x 179 [178]: +1px. Title centre y 91.5 on Tools, Requests, Weekly, Projects [about 93]: -1.5px.
- Home title centre y 154.5: +61.5px. Tagged 10.1(1)/(4) below, not a match.
- Tools, Requests, Weekly and Projects each sit on one glass panel: `rgba(28,24,22,.82)`, radius 22px. Home's hero the same.

## Contrast (rendered pixels, worst pixel behind each text run, whole staff shell)
- Dark: worst enabled text 6.57:1 in all ten cells.
- Light: worst enabled text 4.98:1 (Home, 390), 4.99:1 (Home, 1440); other cells 5.55:1 or more.
- Below 4.5: only the DOM-disabled "Previous" pager (3.6 dark, 2.47 light; disabled controls are outside WCAG 1.4.3).
- One measurement artifact, not a failure: "Observed activity" on Weekly at 390 light reads 2.97, but that header is
  the screen-reader-only `thead` of the card table (`clip: rect(0 0 0 0)`, ui.css) and is not painted.
- Not measured: icon and control (non-text) 3:1 contrast.

## Remaining differences, each tagged with its BRIEF 10.1 number
- 10.1(1): Hub words, page names, real counts and the Swangz mark replace the CRM's; no decorative title emoji.
- 10.1(1)/(4): Home keeps its real launchpad (greeting, status line, hero action, report notice, Your tools, Updates) where
  the reference has four KPI cards, so its title is 61.5px lower. This is a content difference, not within 4px.
- 10.1(1)/(4): the reference's Export / New customer page actions are absent; these pages have no such actions and none are invented.
- 10.1(2): `room-warm.webp` replaces the reference photo.
- 10.1(3): panel opacity .82 dark / .94 light (reference .52) to hold 4.5:1 over the photo.
- 10.1(3): no backdrop blur and a scroll-attached room, for scroll performance (f0608ee). Not yet re-measured for frame rate.
- 10.1(3): if Poppins is not loaded 1.2s after the shell mounts, the session keeps Helvetica Neue/Arial (`tests/browser/staff-font.cjs`).
- 10.1(3): phone and light layouts have no reference still.

## Not run or not claimed
Radii and colour samples against 10.4, motion frame-stepping, scroll frame rate, 430px and the six-width Tools check,
axe on this head beyond `exact-staff-shell.cjs` (4 cells, 0 violations, run on the same product code).
