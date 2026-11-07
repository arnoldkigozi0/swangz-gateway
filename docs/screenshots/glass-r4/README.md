# Glass R4 — Overview header and KPI cards

Dependency: PR #40, exact `42ce9b7e98c1152878cf094dbf588c3d75684db6`.
Branch `feature/glass-r4` starts there; relative product changes are limited to
`gateway/static/ui.css` header/KPI selectors and `admin-monitor.js`. The PR is
against main and includes inherited R5 chart changes until #40 merges. R2 and
R3 are separate and are not present in these screenshots.

Overview keeps its title, navigation, price context, source periods, security
posture and existing links. The existing trends API supplies a fourth card,
AI requests over 30 days, linked to the matching Activity view/range. Its volume
delta is neutral: increased use alone is not judged good or bad. Missing earlier
activity stays “no earlier data”; missing security stays unknown. No new endpoint,
provider, dependency, authentication or administrative behavior was added.

Four separated glass cards use shared material/radius/motion tokens; the spend
card uses accent glass, with high-contrast supporting text. Arrow affordances
belong to the existing full-card links; information buttons remain separate.
The title/icon and ghost/primary actions share the header. Phone layouts use two
columns and stack header actions. Only transform animates on card hover; reduced
motion disables lift. Shared unsupported-blur/reduced-transparency token fallbacks
apply to the new material consumers. Forced colours replace card materials.

## Actual checks

- `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r4/check.cjs`:
  `PASS 44 focused checks; 4 screenshots`, exit 0. All four main-content axe
  scans have zero findings. Checks cover data fidelity, responsive columns,
  value clipping, API-failure presentation, zero activity, absent prior data,
  font loading, request-link target and transform/reduced-motion behavior.
- `NODE_PATH=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r4-desktop node tests/browser/check.cjs` and a separate `UI_WIDTH=390 UI_THEME=dark UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r4-phone` selection: each `PASS principal pages 27 interaction assertions; 25 screen checks`, exit 0. Total 54 assertions/50 screens, no browser exceptions or axe findings; the intentionally rejected Studio request is the only API 400. Bounded selection, not a complete local role matrix. Summaries: `regression-results.json`.
- `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 29.501s`, `OK`, exit 0.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `git diff --check`: exit 0.

Only synthetic local gateway/fake-upstream fixtures were used. Error/zero cases
use explicit test response interception; these values are never product data.
`results.json` records the assertions and scoped accessibility results.

## Reference comparison

The four exact viewport screenshots are `admin-1440-dark.png`,
`admin-1440-light.png`, `admin-390-dark.png`, `admin-390-light.png` (1440×900 and
390×844). All were visually inspected alongside the included reference stills.

- Real Hub metrics and mixed reporting periods replace reference CRM revenue/customer values.
- Known changes use existing percentage chips; unknown prior activity is labelled instead of inventing a delta.
- Approved Swangz architecture replaces the reference room photograph; stronger material protects contrast.
- Porcelain retains the existing dark primary-action token while dark mode uses gold.
- Phones use two columns and wrapped period labels; the reference has no phone layout.
- Sidebar/top bar and non-KPI data panels remain as on dependency #40; their redesigns are separate.
- No count-up, page cross-fade or new chart behavior is included in this bounded treatment.

Not run: full local suite/role matrix (Actions), real devices, Safari/Firefox,
screen readers, native OS settings, performance traces/60fps/CLS/MotionScore,
native unsupported-blur browsers or renewed R4-specific contrast bounds over
arbitrary photographs. Shared R1 tokens were previously bounded analytically;
current axe scans cover these synthetic screens, not all future content.
Chrome DevTools/Motion/mounted browser actions and peer coordination tools were
not exposed; the existing supported browser harness was used. Independent QA and
new-head CI remain pending. Nothing deployed or merged.
