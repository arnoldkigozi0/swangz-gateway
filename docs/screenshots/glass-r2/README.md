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

## Main refresh — 7 November, 16:38 handoff

Merged main `f898ebfe5f56eb95a70f98481d3e0fa5996bd924` normally, without resolution
edits. Navigation CSS/JS are byte-identical to prior PR head `ca834fc`; no shared
admin source edits were made during this refresh. The browser harness regenerated
its eight synthetic screenshots.

Fresh checks: the focused invocation above again passed `75 navigation checks;
8 screenshots; 6 axe scans`, exit 0. `python3 -m unittest tests.test_browser_profiles
tests.test_portal tests.test_hub` reported `Ran 99 tests in 39.773s`, `OK`, exit 0.
The fake-fixture run emitted socket ResourceWarnings; there were no test failures.
Both working and merge-index `git diff --check` passed. Full CI and renewed
independent QA must cover the refreshed head; old verdicts do not transfer.

R4 remains at `8cdc8ea` and its `ui.css` ownership is explicitly released to
Chief/Forge. R4 integration is not verified while corrected dependency #40 is
pending. This refresh did not change or merge the R4 worktree.

## Probe review corrections — 7 November, 17:08 task

Probe's BLOCKED findings on `ca834fc` apply to unchanged navigation at `dcb058e`.
This correction does not transfer or imply independent approval.

- Compact navigation moves search/bell/theme/sign-out into the full navigator,
  reached through an explicit **All pages** control. It summarises Trust indicators
  even while their destination is offscreen. Labelled/phone navigation has five
  pinned area shortcuts with aggregate server-derived indicator badges. All
  destinations remain in the scroll region, with a visible More cue and scrollbar.
  Indicator sums are not unique incident/person counts.
- Focus restoration matches a toggle's stable `aria-controls` before its label;
  an unlabeled toggle can no longer match another unlabeled button.
- White selection discs have a dark inset state ring. The measured ring-to-disc
  contrast is **16.7404:1**. Red incident severity is retained rather than recoloured
  amber. Labels-toggle tooltips sit beyond the rail instead of covering the brand.
- Phone navigation labels are 11px. Emergency actions have at least 44px height.
  The navigator closes before invoking the existing confirmation/resume behavior;
  this prevents its focus trap competing with the confirmation dialog. No endpoint,
  authorization, backend pause semantics or confirmation wording changed.
- Live backdrop blur is removed from navigation. The side rail keeps its warm
  tint/rim/shadow over imagery; drawer and fixed phone bar are opaque so underlying
  text cannot bleed through. This is a deliberate performance/readability difference
  from the reference's live frosted overlay.

### Fresh targeted evidence

With `UI_TOOLING` set to the same existing pinned tooling directory above:

- `node docs/screenshots/glass-r2/check.cjs`: `PASS 75 navigation checks;
  8 screenshots; 6 axe scans`, exit 0. Four required viewport/theme screenshots
  were regenerated; mobile drawer/bar screenshots inspected for opacity/readability.
- `node docs/screenshots/glass-r2/review.cjs`: `PASS 23 review regression checks`,
  exit 0. Covers 1366×768 pinned area access, offscreen incident summary/red severity,
  Trust focus after 16.5s, tooltip placement, ring contrast, no rail blur, 44px phone
  action and real fake-gateway cancel → unchanged state, confirm → paused,
  resume → active. The incident indicator is explicit synthetic client test state;
  pause state is verified through the fake gateway API. No real accounts/providers.
- `UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r2-correction-desktop node tests/browser/check.cjs` and a separate `UI_WIDTH=390 UI_THEME=dark UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r2-correction-phone` run (existing `NODE_PATH` tooling): each passed 27 interaction assertions and 25 screens, exit 0. Total 54 assertions/50 screens, no exceptions or axe findings; only the deliberate Studio 400. Results: `correction-regression-results.json`.
- `python3 -m unittest tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 99 tests in 32.166s`, `OK`, exit 0. Fake-fixture socket ResourceWarnings appeared without failures.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `git diff --check` and a SHA-256 comparison of final CSS/JS against the performance snapshot passed.

### Comparative performance (bounded and mixed)

`node docs/screenshots/glass-r2/performance.cjs` runs the same six-route rAF workload
at 1366×768 against main `f898ebf`, reviewed R2 `dcb058e` and snapshotted corrected
CSS/JS. Three interleaved rounds share the same synthetic fixture and browser;
`performance-results.json` includes samples and corrected-source SHA-256 hashes.

| Variant | Median number of frames >50ms | Median longest frame |
| --- | ---: | ---: |
| Main | 3 | 100.1ms |
| Reviewed R2 | 9 | 100.1ms |
| Corrected R2 | 4 | 116.6ms |

The count improves; the longest-frame median does not. These measurements are
not Probe's original unavailable script, do not reproduce its original absolute
numbers, and do not establish 60fps or eliminate scheduling noise/other builders.
No MotionScore or device-performance claim. Renewed independent judgment of the
performance gate is required; no extra sampling is used to hide the mixed result.

### Final documentation-baseline integration

Normally merged main `9f326992bbd63a6beefb2d1acbce297c9917b511` after the correction.
Only `docs/design/BRIEF.md` arrived from main; no wording-nit edits or conflict
resolutions were made. Product, test and workflow files match `4a0a68f` exactly.
SHA-256 checks confirm the performance comparison still describes these files;
it was not rerun to seek a better outcome. Its mixed result and independent gate
remain unchanged.

Fresh retest: focused harness `PASS 75 navigation checks; 8 screenshots; 6 axe
scans`, exit 0; `python3 -m unittest tests.test_browser_profiles tests.test_portal
tests.test_hub`: `Ran 99 tests in 32.501s`, `OK`, exit 0. Fake-fixture socket
ResourceWarnings remain non-failing. Both working/merge-index whitespace checks
passed. QA and CI must cover this final refreshed head, not an earlier head.


### Browser CI theme-transition diagnosis — 8 November

Inspected actual failed run `42382080869`, browser job `128431709285`, at
head `4f6cf7e`. Downloaded its synthetic artifact; the failing first
`light-1440-_` scan named staff Home launch links for Canva, ChatGPT and Claude.
Summary retained in `ci-failure.json`. Staff portal/shared UI source is identical
to main and unaffected by R2. The job changes theme immediately before axe.

`ci-contrast.cjs` reproduces the same three links at their native 30ms text
transition state, freezing time only so axe can inspect independently of CPU
speed: foreground `#979391` on white measured 3.04:1. The fully settled page
has zero findings. This is not an authorization/product regression or evidence
that all transient theme colours meet AA. No product theme styling changed.

The existing browser harness now waits for fonts and real finite theme
transitions before scans; it neither disables transitions nor excludes rules,
removes assertions, retries axe, or changes contrast thresholds. Infinite
animations are excluded from the wait only, not from accessibility scans. The
initial edit guard detected multiple matching theme setters and aborted without
writing; a shared helper now covers all four theme-setting call sites.

Normally merged current main `7ce5407` without conflicts. Admin CSS/JS are
byte-identical to `4f6cf7e`; earlier performance evidence and limitations stand.
Fresh targeted Python: 99 tests in 60.789s, OK, exit 0; fixture socket
ResourceWarnings were non-failing. Syntax: 23 JavaScript files checked, exit 0.
Focused navigation: 75 checks, eight screenshots, six axe scans, exit 0.
`NODE_PATH=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_WIDTH=1440 UI_THEME=light UI_PAGES_ONLY=1 UI_OUTPUT=/tmp/prism-r42-corrected node tests/browser/check.cjs`: `PASS principal pages 27 interaction assertions; 25 screen checks`, exit0, no browser/axe/unexpected API findings. `ci-regression-results.json` retains the summary. Updated `UI_TOOLING=<same existing R1 tooling> node docs/screenshots/glass-r2/ci-contrast.cjs`: `PASS 3 CI contrast diagnosis checks; native 30ms state fails, settled state passes`, exit0; after reproduction it resumes and awaits real transitions rather than force-finishing them. `git diff --check`: exit0. All local processes finished. Independent exact-head QA and final-head CI pending.


### New-main integration before final QA — 8 November 2026

Normally merged main `2b30af5f0c47c6bf447671a8de2f91742fec6ff6` into
`feature/glass-r2` without conflicts. Main delta from7ce5407 is limited to
docs/CLIENT.md, gateway/enroll.py and tests/test_browser_contract.py: negotiated
`browser_contract=1` adds an inert authenticated person/device browser block to
the manifest; non-negotiating clients retain their original manifest shape.
No hand edits to inherited implementation or tests.

Own-source verification against `d31bfe81ba28736cc70d00b27accda4e9307f1d5`:
admin.css, admin.js and tests/browser/check.cjs are byte-identical. Shared
ui.css/ui.js also unchanged. Five exact comparisons, baseline Git blob IDs and
current SHA256s recorded in `docs/screenshots/glass-r2/main-refresh-identity.json`.
Earlier transition diagnosis, all assertions, reference differences and mixed
performance evidence remain unchanged; no CI diagnosis repeated.

Fresh results: `python3 -m unittest tests.test_browser_contract tests.test_browser_profiles tests.test_portal tests.test_hub`: `Ran 119 tests in 95.128s`, `OK`, exit0; a non-failing fixture socket ResourceWarning appeared. `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r2/check.cjs`: `PASS 75 navigation checks; 8 screenshots; 6 axe scans`, exit0. `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit0. Five byte-identity comparisons and working/staged whitespace checks passed. Local checks finished. Full local
suite/role matrix, new performance/CLS/MotionScore, real devices, other engines
and screen readers: Not run. Fresh final-head Actions and independent Probe QA
remain required. No new build/PR, shared UI edits, merge to main or deployment.
