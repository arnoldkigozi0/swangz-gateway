# Glass R4 — Overview header and KPI cards

Parent PR #40 is merged. Normally integrated main
`6ee3ed3aeaa5244cb88df8302b1435546112d524` without conflicts. R4 overview code,
CSS (including the phone focus/wrapping fix) and focused harness remain byte-
identical to previous head `75d80bc`. The product diff against current main is
R4's admin-monitor.js and scoped header/KPI/phone styles. Fresh final-head CI
and independent exact-head Probe QA are still required before readiness.

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


## Final bottom-up refresh after40 merged — 8 November 09:30

Normally merged main `6ee3ed3aeaa5244cb88df8302b1435546112d524` as
`031b58bb690931008192e8c48d6a306a8c66f2f6`, no conflicts. Incoming delta from
previous75d80bc is main's two-line empty-chart fix and chart tests. Own
admin-monitor.js, ui.css including phone scroll clearance/wrapping, focused R4
harness and tokens are byte-identical to75d80bc. Shared ui.js matches main and
main's whole CSS is an exact prefix. Proof: `parent40-merged-identity.json`.

Fresh checks: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r4/check.cjs`: `PASS 58 focused checks; 6 screenshots`, exit0, four main-content axe scans without findings, no browser exceptions. All phone tab/native Arrow-key focus bounds and KPI content bounds pass. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 46.351s`, `OK`, exit0. Source identities and working/staged whitespace checks pass. All local checks finished. Parent40 gate is
released; previous unmerged-dependency statements above are historical. No new
source changes, PR/build or repeated diagnosis. Fresh CI/exact-head Probe QA
remain required. Full local suite/matrix, real devices, other engines/screen
readers and new hardware performance/CLS/MotionScore: Not run.


## Exact-head Chrome traces and legacy Netlify diagnosis — 8 November 09:50

Captured actual Chrome DevTools Protocol performance traces of requested
head d89f3e778d350bbf8148cb734d3b92109a6ce569 versus main6ee3ed3.
`UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r4/performance-trace.cjs`: exit0, two traces saved, no browser exceptions.
Exact source comparison overrides only main/candidate ui.css and admin-monitor.js
on the same synthetic fixture; all other product source is shared. One run each,
1440x900 dark, unthrottled, six KPI hovers plus scroll down/back twice.
Renderer: ANGLE Vulkan SwiftShader (software), no GPU/device/60fps claim.
Raw Chrome traceEvents JSON is gzip-compressed in trace-main.json.gz and
trace-r4.json.gz; hashes, event counts and provenance in performance-trace-results.json.
Decompress before importing into DevTools if compressed import is unsupported.
The script guards product/fixture blob identity so evidence-only commits can rerun it.

Observed rAF frames>50ms/max: main0/33.3ms, R4 22/416.7ms. Main TaskDuration
0.534785s vs R4 1.191918s; RecalcStyleDuration0.020671s vs0.281196s.
This single trace pair exposes a performance concern and DOES NOT clear the
performance gate. Shared-laptop scheduling, tracing overhead, source/UI count
differences and software rendering limit inference; no extra sampling or product
fix attempted in the bounded window. Probe must assess/route bounded follow-up.

Read-only GitHub check/status inspection: all four Hub checks SUCCESS on d89f3e7.
Legacy swangz-ai Header/Pages/Redirect checks all say Deploy failed for deploy
6af017fc8610934220af7902, annotations0; they do not report independent rule errors.
Old-site same-head header succeeded (1 rule), redirects succeeded (9 rules),
pages neutral (already uploaded), preview success. Public Netlify deploy API
HTTP200 reports state error/summary unavailable; exact build6af017fc8610934220af7900
API returns Access Denied. App/log web reads unavailable. No credential-store
inspection, Netlify execution, deploy/configuration or spending action.
Verified underlying layer: one failed preview fans out to all three checks.
Exact build trigger remains UNKNOWN; next step is authorized read-only build-log
access, not a rerun. Do not infer missing SWANGZ_GATEWAY or credits from history.
Details: netlify-diagnosis.json. Performance comparison and authenticated Netlify
log diagnosis remain open gates. Product source is unchanged; local processes stopped.
