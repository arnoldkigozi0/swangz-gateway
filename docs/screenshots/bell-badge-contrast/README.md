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
