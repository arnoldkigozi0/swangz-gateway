# Bell badge contrast correction

Base: main `4cf653b38bba5e04766704906423fed64e66a7fb`. Branch
`feature/bell-badge-contrast`, isolated worktree `.worktrees/bell-badge-contrast`.

The existing `.bell-n` used white text on both theme fills. Reusing `--on-bad`
for its foreground corrects dark mode without changing its fill, geometry,
typography, notification data, semantics or interactions. Light mode retains
white text. This is the only product change, in admin.css.

G2 scope check: read mission/gates.md and existing project/security guidance.
This reuses the existing notification component and approved semantic tokens;
no architecture/security boundary or critical behavior changes. This correction introduces no additional client/security feature; no new G2
approval is claimed.
No endpoint, sign-in/session, device contract, provider, permission or data change.

## Actual verification

Extended the existing focused admin/header harness at
`docs/screenshots/glass-r3/check.cjs`, adding computed solid-colour WCAG text
contrast assertions in all four theme/viewport combinations. `UI_OUTPUT` directs
new evidence here, preserving old R3 evidence. No shared browser check.cjs,
ui.css/ui.js or workflow edits and no new test tooling.

- Before CSS correction, `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs` exited1: `AssertionError: dark1440 notification badge text >=4.5:1 (3.026120)`. This is the expected negative control. Full measurement/failure is preserved in `baseline-results.json`.
- After correction, same command: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. Includes existing keyboard/focus, real notification/account destinations, clock/timezone, viewer, viewport fit, print and reduced-motion checks. No browser exceptions or scoped axe findings. Full measurements in `results.json`.
- `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 52.014s`, `OK`, exit0.
- `node --check docs/screenshots/glass-r3/check.cjs`: exit0.
- `git diff --check`: exit0.

| Theme | Foreground | Fill | Before | After (both widths) | Required |
|---|---|---|---|---|---|
| Dark | #1F0705 | #FF5D52 | 3.026119928029301, white text | 6.361659258042617 | 4.5 |
| Light | #FFFFFF | #CE4136 | Same white foreground/fill | 4.736397633724517 | 4.5 |

Measurements use actual Chromium computed colours and WCAG relative luminance,
not rounded token comments. The badge has solid fill/foreground and opacity 1;
the photograph does not enter the text/fill contrast calculation. The baseline
browser reproduction stopped on dark1440; light before/after colour identity is
established by the original white declaration and existing light --on-bad token.

## Reference and screenshots

Inspected `admin-1440-dark.png`, `admin-1440-light.png`, `admin-390-dark.png`,
`admin-390-light.png`, exactly 1440x900/390x844. Matching dashboard and Porcelain
reference stills are included beside them. Required visible difference: the
warm red badge keeps its reference shape/fill; dark mode uses a dark numeral to
meet text contrast. Light mode remains white. Existing architectural branding,
phone layout and other page content follow main and are outside this correction.

All tests use synthetic local gateway/fake-upstream data and already installed
pinned Playwright/axe tooling. Mounted browser, Chrome DevTools/Motion tools were
unavailable. Not run: full local suite/matrix (Actions), real devices, other
engines, screen readers, hardware performance/CLS/MotionScore. Four scoped axe
scans do not certify the whole app. Independent exact-head QA and new-head CI
remain required. All local processes finished. No merge/deployment.


## PR50 latest-main integration after46 — 8 November

Normally merged exact main `a0dbcfe140dfcde4e7d1e4e1904b75c014abd222` as
`68f23bdf2dbe415ede16b126ed3c27fc5c37249a`, no conflicts. Main contributes
reviewed shared list/UI code and browser-contract tests/docs. No hand edits to
shared source or any harness. Own admin.css and focused admin assertion harness
remain byte-identical to previous PR50 head
`1048e6f91b2540c2db9e308766a460d0f37d7b60`; tokens.css and shared browser
harness also identical. Shared ui.css/ui.js exactly match integrated main.
Baseline Git blob IDs/current SHA256s: `main-refresh-identity.json`.

Fresh commands/results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs`: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. Zero browser exceptions/scoped axe findings. Actual contrast at both widths: dark6.361659258042617:1, light4.736397633724517:1. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 38.514s`, `OK`, exit0. Four source identity comparisons, inherited shared UI/main equality and working/staged whitespace checks passed. All local check processes finished. No new PR/build or
repeated diagnosis. Full local suite/matrix, real devices, other engines/screen
readers and new hardware performance/CLS/MotionScore: Not run. Fresh final-head
CI and independent Probe QA remain required. PR44 stays queued; no shared-file
release assumed or corrected40 integration performed. Peer tools unavailable;
final exact-head handoff is returned to Chief for Probe routing.


## PR50 amendment after45 merge — 8 November

At clean PR44 checkpoint, normally merged exact main
`be81749aadb7b9b1eeb3e61f4839d02903a09cae` as
`3309f5c889a3cc3396cad51074d9f4c6a178f5a2`, no conflicts. Incoming product
delta is only main's two-line empty-line chart fix, plus its chart tests.
No own source/harness/style edits. Four byte-identity checks against previously
verified `c8dfcb10e1aa419c4cefc55f50b69ccdd134ab64` pass: admin.css, focused
admin harness, tokens.css and shared browser harness. Shared ui.css/ui.js match
requested main exactly. Baseline blob IDs/SHA256s: `after45-identity.json`.

Fresh commands/results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs`: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. No browser exceptions/scoped axe findings. Actual badge contrast remains dark6.361659258042617:1/light4.736397633724517:1 at both widths. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 50.038s`, `OK`, exit0. Source identity and working/staged whitespace checks passed. All local check processes finished. No repeated diagnosis or
new PR/build. PR44 was clean and remains untouched. Full local suite/matrix,
real devices, other engines/screen readers, new hardware performance/CLS/MotionScore:
Not run. Fresh final-head CI and independent exact-head Probe QA remain required;
previous verdict is not claimed as new-head approval.


## PR50 refresh at final44 clean checkpoint — 8 November 09:30

PR44 was tested/pushed/clean atd89f3e7 before starting this optional refresh.
PR50 remained open; normally merged latest main
`6ee3ed3aeaa5244cb88df8302b1435546112d524` without conflicts. Main brings
merged R5 chart code/evidence. Own badge CSS, focused admin harness, tokens and
shared browser harness remain byte-identical to previous c37571e; shared UI
exactly matches requested main. Blob/SHA256 proof: `parent40-identity.json`.
No source changes, repeated diagnosis or new build/PR.

Fresh commands/results: `UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules UI_OUTPUT=docs/screenshots/bell-badge-contrast node docs/screenshots/glass-r3/check.cjs`: `PASS 67 header checks; 4 screenshots; 4 axe scans`, exit0. No browser exceptions/scoped axe findings; actual badge contrast remains dark6.361659258042617:1/light4.736397633724517:1 at both widths. `python3 -m unittest tests.test_portal tests.test_hub`: `Ran 56 tests in 43.684s`, `OK`, exit0. Source identity/whitespace checks passed; all local checks finished. Full local
suite/matrix, real devices/other engines/screen readers and new hardware
performance/CLS/MotionScore: Not run. Fresh exact-head CI and independent Probe
QA remain required. No ready/merge/deploy action.

## Current brief and main refresh — 10 November 2026

**Retain this minimal fix; acceptance remains pending.** Unlike the obsolete layout drafts, this change corrects one foreground on an opaque badge without changing measured geometry. Read canonical main `5196617f45590b919f5cbd38cf71cf9aad1941a4` BRIEF §10–10.9 and the reference stills. Normally merged that main without conflicts as `c0d97df`; root/WIP and #56 were untouched. Main integration brings already-merged source; no client/backend/sign-in files were hand-edited. Product diff against main remains exactly `.bell-n { color: var(--on-bad) }` in admin.css. Badge CSS, tokens, focused harness, shared ui.css and ui.js remain byte-identical to previous remote4704674; see `current-main-identity.json`.

§10.1(3) tagged accessibility difference: dark badge numerals use the existing dark semantic foreground instead of white on the unchanged red fill. Historical computed-colour ratios are6.361659:1 dark and4.736398:1 light. Current source retains those same foreground/fill tokens. Since both are opaque, the room photograph is not part of the numeral/fill ratio. This source identity supports retaining the fix; it is not a new rendered measurement, reference overlay or Probe acceptance. No badge size, position, radius, font, count, animation or API change was added.

Actual old-head checks were inspected rather than called green overall: on4704674 all four GitHub jobs passed, while paid `swangz-ai` Deploy Preview and Header/Pages/Redirect checks failed. All three rule checks point to deploy `6af018f82962c86a4887a339` and have zero annotations. Public Netlify API reports state `error`, null error_message, build `6af018f82962c86a4887a337`, and no published_at. The approved read-only status helper returns the expected preview URL but no failure explanation. Exact build cause remains unavailable; no rule-specific defect, credit problem or environment cause is inferred. No build was manually retriggered and no Netlify configuration was changed.

This shift: source/artifact inspection, clean merge, byte identity and `git diff --check origin/main...HEAD` passed. Not run locally: Python, DOM/browser/syntax tests, new screenshots, overlays, contrast/axe, fallbacks, CLS or performance. Probe owns the exclusive local test/browser slot. Historical67 header checks/four axe scans/four screenshots and56 Python tests/43.684s remain historical; fresh GitHub CI is required on the pushed head. The focused badge assertion is not a dedicated CI step.

Immediate §10.9 evidence remains missing: current-room full text-style samples/axe, required1440×852 overlay, reduced-transparency/reduced-motion/no-backdrop-filter screenshots, empty-database/low-data screenshot and laptop or4×-CPU smoothness/CLS evidence. This one-line correction does not implement deferred R16/R17 or claim to repair inherited low-data formatting. Request Probe's acceptance when the slot is available; keep draft/HOLD until the applicable evidence and all required checks are resolved. New screenshot/performance results are explicitly **Not run**. Preview: https://deploy-preview-50--swangz-ai.netlify.app — signed-in checks use the synthetic local demo, not the preview's live Hub connection.
