# Glass R3 — floating control-room toolbar

Dependency: draft PR #42, exact `1b8c8d913b7c7612abe67e122d0275e978415ed5`.
Branch `feature/glass-r3` originally started at `4f6cf7e`; the corrected dependency
and main `2b30af5` are now normally integrated. Against that dependency, product edits are
limited to the header construction in `admin.js` and header-only selectors in
`admin.css`. Against main, the PR also contains inherited R2 navigation until
#42 merges. No shared UI, portal, authentication, backend or dependency changes.

The transparent toolbar holds a workspace navigation pill, area context, centered
command-search pill and keyboard hint, actual clock, existing notifications and
an account avatar link. The workspace button opens the existing navigator; search
opens the existing command menu; bell opens existing server-backed notifications;
avatar goes to Settings → Your account and uses the signed-in user's initials/name.

The clock uses the existing selected gateway/local/UTC timezone formatter. It
updates its text/ISO timestamp every 15 seconds through the existing per-route
lifecycle, without an ARIA live region or animation. Phone layout uses two rows;
all interactive targets have a 44px minimum. No backdrop blur is added. Existing
page title/actions, routing and access controls remain in place.

## Actual checks

- `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`:
  `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit 0. Zero findings in
  scoped toolbar scans, zero browser exceptions. Tests cover keyboard opening and
  focus return, navigation drawer, real notifications/account destinations, live
  clock tick and UTC preference changes, viewer identity, fitting 44px controls,
  additional 320/768/1280 widths, reduced motion/no blur and print omission.
- `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 38.042s`, `OK`, exit 0. Local fake-upstream ports enabled.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `git diff --check`: exit 0.
- `NODE_PATH=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_WIDTH=<1440|390> UI_THEME=<dark|light> UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r3-<theme>-<width> node tests/browser/check.cjs`: four separate runs each `PASS principal pages 27 interaction assertions; 25 screen checks`, exit 0. Total 108 assertions/100 screens; zero browser errors, axe findings or unexpected API failures. The deliberately rejected Studio request is expected. Summaries: `regression-results.json`.
- `python3 docs/screenshots/glass-r3/contrast.py`: `PASS 8 text contrast bounds; minimum 5.64`, exit 0. Bounds composite the shipped scene scrim and strong pill material over fully black/white photos for primary pill text and secondary area context; they do not measure every inherited icon/badge. Initial ad-hoc token parsing matched the selector in a comment and failed; the saved script matches the actual root rule.

Rerun on 8 November 2026: the initial invocation without `UI_TOOLING` failed
with `MODULE_NOT_FOUND`; rerunning with the existing R1 tooling path above passed.
No packages were installed.

Only the existing pinned test tooling and synthetic gateway/fake-upstream fixture
were used. No real service sign-in or provider request. `results.json` stores the
assertion/scoped-accessibility results. Automated scans are not whole-app AA
certification or screen-reader evidence.

## Screenshots and visible differences

Four exact viewports were inspected: `admin-1440-dark.png`, `admin-1440-light.png`,
`admin-390-dark.png`, `admin-390-light.png` (1440×900 and 390×844). Dashboard and
Porcelain reference stills are included beside them.

- Real Swangz branding and existing architecture replace the reference CRM branding/photo.
- The workspace pill opens navigation; there is no invented workspace switcher.
- A global New action is omitted because the app has no universal creation behavior; real page actions remain with the page title.
- The avatar uses initials and the actual account link; no unbacked presence/health dot is shown.
- Clock format follows the user's existing timezone and locale rather than a fixed reference timestamp.
- The area context accompanies the workspace on desktop; the existing page breadcrumb remains the canonical location indicator and is visible on phones.
- Phones use two rows; the reference is desktop-only. Search copy ellipsizes while its accessible name remains intact.
- Pills reuse strong tint/rim/highlight without live blur; there is no new full-width bar background or sticky overlay.
- R4 header/KPI cards and other chart/footer passes are separate; these screens show the dependency's current page content.

Not run: full local suite/role matrix (Actions), real devices, Safari/Firefox,
screen readers, native OS settings, runtime performance/60fps/CLS/MotionScore,
notification delivery outside the fake fixture, or analytical contrast bounds
for inherited avatar/badge/icon styles. Chrome DevTools, Motion and mounted browser
actions were unavailable; the existing supported Playwright harness was used.
Independent QA and new-head CI remain pending. Nothing deployed or merged.


## Corrected dependency integration — 8 November

Integrated clean, pushed PR42 head `d31bfe8`, including main `7ce5407`. Only
`docs/AGENT-PROGRESS.md` had an append conflict; both full records were retained.
No product/test conflict resolution. Admin CSS/JS are byte-identical to R3
`b5986c6`; shared ui.css/ui.js were not edited. The inherited CI test correction
waits for real finite theme transitions/fonts before existing axe assertions.
No rules, thresholds or assertions were removed.

Integrated-tree results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit0. `NODE_PATH=<same tooling> UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r48-integrated node tests/browser/check.cjs`: `PASS principal pages 27 interaction assertions; 25 screen checks`, exit0; zero browser errors/axe/unexpected API findings, summary in `integration-regression-results.json`. `python3 -m unittest tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 99 tests in 62.813s`, `OK`, exit0 (non-failing fixture socket ResourceWarnings). Syntax:23 JavaScript files checked; eight text contrast bounds min5.64; working/staged whitespace checks passed. All local check processes finished. Full final-head
Actions/independent exact-head QA remain required; earlier screenshots and
performance evidence do not establish those gates.


## Main2b30af5 integration for final QA — 8 November

Normally integrated refreshed PR42 `1b8c8d913b7c7612abe67e122d0275e978415ed5`,
including main `2b30af5f0c47c6bf447671a8de2f91742fec6ff6`, into existing PR48.
Only append-only progress records conflicted; retained both complete records.
No product/test resolution edits. Main adds the reviewed negotiated browser
manifest contract in enroll.py plus its documentation and tests.

Five byte-identity comparisons against previous PR48 head
`1af8d0f9a828a8770ecdc62aca090d73329605a1` passed: admin.css, admin.js,
tests/browser/check.cjs and shared ui.css/ui.js. Baseline Git blob IDs/current
SHA256s recorded in `docs/screenshots/glass-r3/main-refresh-identity.json`.
Earlier transition-wait assertions, diagnosis and mixed R2 performance evidence
are unchanged; no repeated diagnosis/performance sampling.

Latest integrated-tree results: `python3 -m unittest tests.test_browser_contract tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 119 tests in 61.188s`, `OK`, exit0; non-failing fixture socket ResourceWarnings appeared. `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r3/check.cjs`: `PASS 63 header checks; 4 screenshots; 4 axe scans`, exit0. Five own/shared source byte-identity comparisons and working/staged whitespace checks passed. All local check processes finished. Full local
suite/role matrix, hardware performance/CLS/MotionScore, real devices/other
engines/screen readers: Not run. Final-head Actions and independent Probe QA
remain required. No new build/PR, shared UI edits, merge to main or deployment.
