# Glass R4 — Overview header and KPI cards

Dependency: PR #40 at corrected `4698dcc06a2fceca2d5204ca5c0b399d8e57ad4c`.
Composed with current main `a0dbcfe140dfcde4e7d1e4e1904b75c014abd222` after
Forge's explicit shared-file release. Both normal merges were conflict-free.
R5 is not yet merged: keep this PR draft until its dependency lands, bottom-up
fresh CI and independent exact-head QA clear. Product changes against that
parent remain admin-monitor.js and the R4 header/KPI/Overview-phone CSS block.
Shared ui.js exactly matches R5; R5's complete ui.css is an unchanged prefix.
R2/R3 from main are present in current screenshots.

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
- Sidebar/top bar now come from refreshed main; non-KPI panels retain their existing presentation.
- No count-up, page cross-fade or new chart behavior is included in this bounded treatment.

Not run: full local suite/role matrix (Actions), real devices, Safari/Firefox,
screen readers, native OS settings, performance traces/60fps/CLS/MotionScore,
native unsupported-blur browsers or renewed R4-specific contrast bounds over
arbitrary photographs. Shared R1 tokens were previously bounded analytically;
current axe scans cover these synthetic screens, not all future content.
Chrome DevTools/Motion/mounted browser actions and peer coordination tools were
not exposed; the existing supported browser harness was used. Independent QA and
new-head CI remain pending. Nothing deployed or merged.


## Current-main refresh while shared files remain reserved — 8 November

Normally merged main `a0f7dad941f44f79e87b1439cff0ddbcbbc426d1` without
conflicts as `2d57ae95b0c0c3ea26cca73e82e2e6bf5509a11b`. Before merging,
confirmed main had no ui.css/ui.js changes relative to the common ancestor.
After merging, exact comparisons prove both shared files, admin-monitor.js and
the focused R4 harness are byte-identical to old R4 head
`8cdc8eaae29a1229bb79c4ae6faef9d8d472ea76`. The inherited shared browser
harness matches main; no hand edits to it or workflows. Identity evidence:
`main-refresh-identity.json`. No product source edits or conflict resolutions.

`UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r4/check.cjs`:
`PASS 44 focused checks; 4 screenshots`, exit0; four main-content axe scans
with zero findings, no browser exceptions. `python3 -m unittest tests.test_portal
tests.test_hub`: `Ran 56 tests in 51.811s`, `OK`, exit0. `git diff --check`:
exit0. Inspected all four regenerated exact desktop/phone light/dark screenshots.

Dependency integration remains BLOCKED: R4 still contains old R5 base42ce9b7;
PR40 is open at corrected `f25b65c7366a6cba0001b5f0e6a3a9810dcb4df2`, whose
ui.css/ui.js differ. Those files remain Forge-reserved, so no corrected-R5 merge
was performed. Existing R4 phone spacing gaps remain untouched in shared CSS.
Keep draft until corrected dependency integration, renewed targeted checks, fresh
CI and independent exact-head QA clear. Bell badge Low is separately addressed
by PR50, not included in this branch. R8 not started: dependency and three-new-
build cap remain constraints. Full local suite/matrix, real devices/other engines,
screen readers and hardware performance/CLS/MotionScore: Not run. All local
checks finished. No new draft/build for R4, deployment or merge to main.


## Corrected R5 composition and phone tab visibility — 8 November

Integrated maina0dbcfe, then released corrected R5 `4698dcc` normally, no
conflicts. Dependency merge commit `f5833a8c32a4da882c97fdfc4db7c2af5dfbb450`.
No hand resolution of shared code. R5 ui.js is byte-identical; its whole ui.css
is an exact prefix of the composed file. Removing only the three new phone-
scoped lines leaves the previous R4 CSS block byte-identical; admin-monitor.js
also matches previous R4 head09c27e1. Proof/hashes: `composition-identity.json`.
The earlier ownership/dependency blocker is now resolved as a composition;
parent PR40 still must land before this PR can be ready.

New geometry checks reproduced a phone tab visibility failure. Native focus
placed Right now at y778.375–821.625 behind navigation starting y774; recorded
in `composition-before-fix.json/png`. Arrow-key selection also exposed the
last Licences tab/count beyond the right edge; `phone-tabs-before-fix.png`
records that intermediate horizontal failure. Initial direct-focus probes were
replaced with native focus/real Arrow-key selection before final validation.

Added Overview-only phone scroll clearance using existing rail tokens/safe-area
inset, and responsive tab wrapping/gaps using --s1/--s2. No shared pageTabs JS
behavior changed. All four selected tabs now fit horizontally and sit above
fixed navigation in both themes. KPI labels/values/context fit every card;
existing KPI size/material/spacing remain unchanged.

`UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r4/check.cjs`:
`PASS 58 focused checks; 6 screenshots`, exit0; four main-content axe scans,
zero findings/browser exceptions. Four exact1440x900/390x844 dark/light main
screens plus tabs-390-dark/light.png were regenerated and inspected alongside
existing references. Required visible difference: phone tab gaps are tighter
and labels may wrap on narrow widths; focused tabs clear fixed navigation.
Desktop and KPI presentation stay as in the composed reference treatment.

`python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 43.712s`,
`OK`, exit0. `node --check docs/screenshots/glass-r4/check.cjs` and working/staged
whitespace checks pass. Tests retain API-summary error/zero/missing-prior-data
assertions, reduced-motion/hover checks and real API KPI comparison. Full local
suite/matrix, real devices/other engines/screen readers, new hardware
performance/CLS/MotionScore: Not run. Fresh final-head Actions, parent40 gates
and independent exact-head Probe QA remain required; no approval waiver.
All local processes finished. No new PR/build, merge to main or deployment.
