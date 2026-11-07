# Glass R2 — control-room navigation

Branch `feature/glass-r2`, isolated worktree `.worktrees/glass-r2`, based on merged
R1 `3cdb8ec`. Product changes are limited to `admin.css` and navigation in
`admin.js`. Existing Plus Jakarta Sans, imagery and shared glass tokens are reused.

The floating rail has a white active circle, real count badges, all five existing
navigation groups, pinned Help/Settings and a labelled view remembered alongside
existing group folds. Arrow keys, Home/End, focus tooltips and visible focus rings
support keyboard use. The middle rail scrolls to accommodate the real catalogue
of admin destinations. The existing emergency, theme and sign-out controls remain.

At phone width, five shortcuts and More lead to a labelled drawer, with unique
control IDs, focus trapping and focus restored after the drawer closes. Background
navigation is hidden while the drawer covers it. Print, forced colours, reduced
motion/transparency and the existing unsupported-blur token fallback are retained.

## Actual checks

- `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r2/check.cjs`:
  `PASS 75 navigation checks; 8 screenshots; 6 axe scans`, exit 0. Existing pinned
  tooling only; synthetic gateway/fake upstream. Zero browser exceptions or axe
  findings in the scoped navigation scans. These are not whole-app accessibility
  certification or real-device checks.
- `UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r2-desktop node tests/browser/check.cjs` and the separate `UI_WIDTH=390 UI_THEME=dark UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r2-phone` selection (with `NODE_PATH` pointing to the same existing tooling): each `PASS principal pages 27 interaction assertions; 25 screen checks`, exit 0. Total 54 assertions/50 screens; no exceptions or axe findings. Only the intentionally rejected Studio request returned 400. These are bounded selections, not the full role matrix.
- `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 30.169s`, `OK`, exit 0.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `git diff --check`: exit 0.

The bounded CI-harness summaries are in `regression-results.json`. Independent QA and Actions results are pending.

`results.json` contains the assertions, scoped axe results and measured reduced
transparency styles. The harness first needed corrections for persisted group
state, asynchronous route settling, the shared 1ms reduced-motion duration override
and background-transition settling. Earlier WIP partial results are superseded by
this complete final-tree run. No product changes were needed during this resumption.

## Screenshots and reference differences

All required exact viewport images were inspected: `admin-1440-dark.png`,
`admin-1440-light.png`, `admin-390-dark.png`, `admin-390-light.png`. Additional
labelled-view and mobile-drawer images cover both themes. Matching dashboard and
Porcelain reference stills are alongside them.

- The rail scrolls because the real Hub has five groups and more destinations than the reference.
- Existing search, notifications, emergency and account controls remain in the rail pending their separately assigned passes.
- The rail is 76px wide to preserve 44px control targets with internal spacing.
- Light mode uses the approved milky Porcelain material; the dashboard reference is dark only.
- Phone quick navigation is an accessible adaptation of the desktop reference.
- Page headers, KPI/data panels and charts retain their current composition; separate PRs own those changes.
- Existing Swangz architecture and the approved font replace the reference photograph and typography.

Not run: full local suite/role matrix (Actions), real devices, Safari/Firefox,
screen readers, native OS settings, performance traces/60fps/CLS/MotionScore.
Chrome DevTools, Motion, mounted browser actions and peer coordination tools were
not exposed in this build session; the existing supported browser harness was used.
No deployment, providers, new dependencies, auth logic or production data changed.
