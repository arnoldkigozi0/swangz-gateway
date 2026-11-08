# Glass R3 — floating control-room toolbar

Dependency: draft PR #42, exact `4f6cf7e5cb5fae63b1642e9e30f5766ecbb6e5f5`.
Branch `feature/glass-r3` starts there. Against that dependency, product edits are
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
