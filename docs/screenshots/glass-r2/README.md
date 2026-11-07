# Glass R2 — unfinished shift-end handoff

7 November 2026, 14:01 EAT. Branch `feature/glass-r2`, isolated worktree
`.worktrees/glass-r2`, based on merged R1 `3cdb8ec`. Parked as WIP at shift end.
Not ready for a draft PR: the targeted browser check has not completed successfully.

## Implemented so far

- Floating glass rail, white active circle, existing five navigation groups and
  real count badges, pinned Help and Settings.
- Labelled view preference alongside the existing group-fold preference.
- Arrow/Home/End navigation and existing shared focus/hover tooltips.
- Phone quick bar with five shortcuts plus More and a labelled navigation drawer.
- Navigation refresh preserves scroll/focus; drawer closes before focus returns.
- Existing emergency/theme/sign-out controls retained, with print, reduced
  motion/transparency and forced-colour navigation styles.

Only `admin.css` and navigation portions of `admin.js` changed in product code.
No tokens, shared UI, portal, auth, dependencies, providers or deployment changes.

## Actual partial verification

Existing tooling invocation (no dependency install):

```sh
UI_TOOLING=/home/inquiline/swangz-team/swangz-gateway/.worktrees/glass-r1/tests/browser/node_modules node docs/screenshots/glass-r2/check.cjs
```

The latest run exited 1 after 52 assertions. It passed dark desktop/phone/drawer
checks and the early light desktop checks; it then timed out clicking the hidden
Tools link after the test toggled the already-open Govern group closed. The
group preference persisted from the dark pass. Correct the harness to open a
group only when `aria-expanded` is false; Reporting has the same assumption.
Do not treat these partial results as a passing final-tree check. The last run
also crossed a small navigation tooltip-position edit; rerun the complete check
on the finished source after resuming. Raw partial results are in `results.json`.

Earlier iterations found and corrected two implementation defects: group folding
affected the labelled preference override, and the drawer tried returning focus
while More was still hidden. The latest dark pass covers these fixes, but final
verification is still pending. Earlier `node --check gateway/static/admin.js`
invocations passed; no new tests were started at shift end.

Five partial screenshots are present: dark desktop, labelled desktop, phone and
drawer, plus light desktop. The required light 390×844 screenshot is missing.
These are synthetic Chromium viewport checks, not real-device checks.

## Exact next step

1. Correct the two group-opening assumptions in `check.cjs`, finish the bounded
   navigation/fallback checks, then rerun it against an unchanged final tree.
2. Inspect all four required screenshots and document remaining reference
   differences. Check mobile keyboard focus, long labels and refresh behavior.
3. Run appropriate targeted Python tests, syntax/whitespace checks and bounded
   existing CI browser selections. Full matrices stay on Actions.
4. Commit/push the finished correction, open one draft R2 PR, and hand it to Probe
   and Chief. Only after that clean handoff, refresh existing PR #37 on its own
   branch and correct the stale Archivo sentence. R4 has not started.

Remaining visual differences: the Hub has five groups and more destinations than
the reference, so its middle rail scrolls; existing search, notification, emergency
and account controls remain until their assigned passes. Other page content is
unchanged. Detailed final visual comparison is pending.

Not run: final passing navigation check, targeted Python tests, CI browser
regressions, full suite/matrices, real devices, Safari/Firefox, screen readers,
60fps/CLS/MotionScore. Chrome DevTools, Motion and mounted browser actions were
not exposed; the task uses the existing supported Playwright harness. Peer
coordination tools were also unavailable in this resumed build session.
