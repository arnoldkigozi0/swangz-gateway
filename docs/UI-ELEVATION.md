# Interface elevation review

The pass builds on V2.2 at `d437f4e`, preserving Obsidian & Gold, Archivo, the launchpad,
Settings categories and the existing plain-JavaScript architecture.

## What the rendered audit found

- Staff catalogue, Studio, Devices and Requests used section-sized headings for the whole page.
- Every approved tool carried a solid primary button, competing with Home's main action.
  Catalogue footers frequently wrapped their actions below metadata, wasting space.
- The catalogue read down newspaper-style columns, making visual scanning and keyboard order differ.
  Category and sort choices did not survive refresh; clearing a search could leave stale filters.
- Studio rebuilt its form on each media switch, losing the script, prompt and selections. Progress
  reads failed silently, leaving a creation looking indefinitely busy.
- The staff phone navigation omitted Studio even when it was available to that person.
- Overview's `.note` summary spans inherited notification-card borders, padding and backgrounds.
- Sidebar descriptions used a token intended for disabled marks: axe measured 2.91:1 in dark mode
  and 2.33:1 in light mode. Light licence actions also failed contrast on their warning surface.
- Uppercase panel and table headings competed with small supporting text. Phone table fields lacked
  consistent label/value alignment, and wide tables offered no keyboard focus for horizontal scrolling.
- The Licences phone summary truncated the actual monthly amount; the large hero-number rule
  overrode the phone type size. Numeric summaries now show the complete value and can wrap.

## Implemented decisions

**Foundations.** Champagne selection accents, clearer neutral boundaries and supporting copy;
sentence-case section, table and empty-state headings; balanced table spacing, hover feedback,
aligned phone label/value fields and a focusable, named table scroll region. Existing numeric
alignment, statuses, captions and sort behaviour remain.

**Staff.** Proper page titles and heading structure; a calmer Home without the background grid,
smaller doorway composition and quieter secondary launches; a row-major catalogue with compact
footers, URL-backed search/category/availability/sort, reset actions and retained filter focus.
Mobile navigation includes Studio only when the existing availability check permits it. Account
menus support arrows, Home/End, Escape and Tab. Privacy explanations use more readable headings
and line spacing; Home updates are no longer truncated to two lines. On phones, access-request
status moves below the details so a long reason keeps a readable line length.

**Studio.** A bounded creation workspace with its own task heading, clearer voice-model selection,
native required-field validation and live submission feedback. Switching media types or Studio
views retains each form, including an in-flight submission. Failed submissions retain input.
An interrupted progress read says the request may still be running and offers **Check again**,
which only reads the existing job. Creation previews fit the full image rather than cropping it.
Drafts are retained within this Studio visit; leaving the page or refreshing does not persist them.

**Control room.** Stronger page and panel hierarchy, readable sidebar group descriptions, cleaned
Overview summary notes, consistent control heights, wrapping permission labels, and bounded dialogs
with wrapping actions and stable sheet headers. Shared table and state improvements apply to People,
Tools, Models, Policies, commercial views, reports, investigation pages and profile tables.
The category/child-section structure and dedicated Emergency experience remain intact.

Only the existing self-hosted `gateway/static/door.svg` artwork was found. No new Home or login
image paths are referenced. For later owner-supplied artwork, the proposed filenames are
`gateway/static/home-welcome.webp` and `gateway/static/login-welcome.webp`. These are documentation
conventions only: evaluate the supplied files, contrast and responsive crop before adding references.

## Repeat the browser checks

The app itself still needs only Python's standard library. Browser tools are optional and installed
outside the project. The fixture starts a temporary database and the repository's `FakeUpstream`,
creates local test accounts and removes the database when it exits. It never uses company keys.

```bash
npm install --prefix /tmp/swangz-browser playwright @axe-core/playwright
# Use an installed Chrome, or install Playwright's Chromium outside the runtime:
/tmp/swangz-browser/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/swangz-browser/node_modules node tests/browser/check.cjs
# To use system Chrome:
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome node tests/browser/check.cjs
# Additional profile tabs, dialogs, reports, progress recovery and Home states:
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome UI_DETAILS_ONLY=1 UI_OUTPUT=/tmp/swangz-ui-details node tests/browser/check.cjs
# Isolated role checks (also included in the principal run):
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome UI_ROLES_ONLY=1 UI_OUTPUT=/tmp/swangz-ui-roles node tests/browser/check.cjs
# Populated staff/admin access requests, incident evidence and session details:
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome UI_RECORDS_ONLY=1 UI_OUTPUT=/tmp/swangz-ui-records node tests/browser/check.cjs
# Staff and console sign-in screens:
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome UI_AUTH_ONLY=1 UI_OUTPUT=/tmp/swangz-ui-auth node tests/browser/check.cjs
# All owner Settings categories:
NODE_PATH=/tmp/swangz-browser/node_modules CHROME=/usr/bin/google-chrome UI_SETTINGS_ONLY=1 UI_OUTPUT=/tmp/swangz-ui-settings node tests/browser/check.cjs
```

`UI_OUTPUT` selects the directory for screenshots and `results.json`. `PYTHON` and `CHROME` select
executables. The principal run checks every major page at 1440×900, 1280×800, 1024×768, 768×1024,
430×932 and 390×844 in both themes; axe WCAG 2/2.1 AA-tagged scans run on desktop and phone pages.
The deep-view pass adds page/profile tabs, all reports, nested Settings sections, dialogs and Home's
paused, no-tools, one-tool and ended-access states. Role checks cover viewer, operations, security
and billing at desktop, tablet and phone widths in both themes. Read-only simulators stay usable;
role assertions distinguish those inputs from controls that change settings.

`UI_THEME=dark|light` and `UI_WIDTH` can narrow the principal, record or sign-in matrix for a focused
recheck. `UI_PAGES_ONLY=1` runs the principal pages and interactions without repeating the role pass.

## Recorded verification — 9 October 2026

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -t .` | PASS: 258 tests, 318.560 seconds |
| Principal pages: 25 routes × six viewports × two themes | PASS: 300 screen checks; 21 focused interaction assertions |
| Profile/page tabs, nine reports, child Settings sections, dialogs, Home access states and progress recovery | PASS: 360 screen checks; 71 interaction assertions |
| Viewer, operations, security and billing | PASS: 168 screen checks; 156 read-only/action-permission assertions |
| Owner: all seven Settings categories at desktop, tablet and phone widths in both themes | PASS: 42 screen checks |
| Populated access requests, incident evidence and sessions | PASS: 48 screen checks; final phone request layout rechecked in eight additional checks |
| Staff and admin sign-in | PASS: 24 screen checks |
| JavaScript syntax and `git diff --check` | PASS |

Every principal route was checked at 1440×900, 1280×800, 1024×768, 768×1024, 430×932 and 390×844
in both themes. Staff checks cover Home, catalogue, Studio, Devices, Requests and Privacy. Console
checks cover Overview, Live, Needs attention, Activity, Health, People and profiles, Tools and profiles,
Models, Policies, Licences & spend, Reports, Security, Incidents and evidence, Devices and profiles,
Audit, Settings, full records and sessions. Tab checks include cost/renewal views and policy simulation
and explanation views; Settings checks also exercise refresh, history and the unsaved-change guard.

No page-level horizontal overflow, clipped controls/numeric summaries or JavaScript exceptions were
found in the completed checks. Desktop/phone axe scans reported no violations for the selected
WCAG 2/2.1 AA tags. The deliberate failed voice-generation fixture returns HTTP 400; no unexpected
API failures occurred. The final checks were resumed after an interrupted run; completed viewport
states were retained and the remaining light-phone matrix was rerun successfully.

## Changed files

- Shared system: `gateway/static/tokens.css`, `gateway/static/ui.css`, `gateway/static/ui.js`.
- Staff: `gateway/static/portal.css`, `gateway/static/portal.js`.
- Console: `gateway/static/admin.css`, `gateway/static/admin.js`.
- Documentation: `docs/UI.md`, `docs/STATE.md`, `docs/UI-ELEVATION.md`.
- Optional browser checks: `tests/browser/demo.py`, `tests/browser/check.cjs`.
- Review captures: the ten PNGs linked below under `docs/images/ui-elevation/`.

## Review the screenshots

The complete captures remain in the selected test output directory. Selected captures are committed
for review; all activity, prices and generation results are local fixtures, not production evidence.

| Capture | Review |
| --- | --- |
| [Home, dark](images/ui-elevation/home-dark-desktop.png), [Home, light](images/ui-elevation/home-light-desktop.png) | Artwork, title composition, primary and secondary launches |
| [Catalogue](images/ui-elevation/catalogue-dark-desktop.png) | Scanning order, filters, compact card actions |
| [Studio, phone](images/ui-elevation/studio-dark-phone.png) | Form hierarchy, control spacing and result presentation |
| [Overview](images/ui-elevation/overview-dark-desktop.png) | Summary strip and removal of notification styles from notes |
| [Settings, phone](images/ui-elevation/settings-light-phone.png) | Grouped rail, wrapping labels, readable control rows |
| [Licences, phone](images/ui-elevation/licences-dark-phone.png) | Complete monetary amounts and label/value alignment |
| [Requests, phone](images/ui-elevation/requests-dark-phone.png) | Readable reason and clearly labelled status |
| [Tool profile, phone](images/ui-elevation/profile-light-phone.png) | Stable sheet header and scrollable form |
| [Policy sheet, phone](images/ui-elevation/policy-dark-phone.png) | Task grouping and bounded actions |

## Limits

Browser verification uses local fake-provider fixtures, not a production account. Real Google sign-in,
company browser sessions, external vendor interfaces and production-sized datasets need their own
operational checks. Axe results are automated findings, not a declaration of WCAG compliance.
Safari, Firefox, physical mobile devices and screen-reader sessions were not tested.
