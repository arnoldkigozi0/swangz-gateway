# Glass R1 — foundation progress and verification

7 November 2026. Branch `feature/glass-r1`, based on freshly fetched main
`7356e067a70b425cd2420ecfe856f1c9e68af545` (PR #36). Isolated worktree
`.worktrees/glass-r1`. This is the shared visual foundation, before the separately
assigned sidebar, top bar, KPI, chart, sign-in and footer work.

## Changes

Warm smoked glass and a separately designed milky Porcelain theme share tokens
for surfaces, rims, inset highlights, shadows, blur, radii and motion. Legacy
radius/motion names alias these tokens. The fixed photographic layer reuses the
existing Swangz artwork and a contrast scrim; it adds no full-screen blur.

Opt-in classes: `u-glass`, `u-glass-strong`, `u-glass-accent`, `u-glass-pill`,
`u-glass-well` and `u-glass-lift`. Compose the pill/lift modifiers with a surface
class. Nested glass utilities become tint-only wells without a second blur.
Use strong glass for dense text; accent glass promotes supporting text to the
primary text colour to keep labels readable. Avoid overlapping blurred siblings
when adopting these primitives in later page work.

Unsupported blur and reduced transparency use solid `--ink-2` surfaces in both
themes. Reduced transparency also removes the scene image and existing backdrop
blurs. Reduced motion disables lift and translated entrances. Forced colours use
system colours. The newly added hover transition animates transform only.

Plus Jakarta Sans variable Latin is self-hosted with its complete OFL licence;
body text, headings and controls inherit it, with tabular figures. The two HTML
files change only their font preload URLs. Asset provenance and byte size are in
`docs/design/ASSETS.md`. No application data, route, authentication or policy changes.

## Actual checks

- `python3 -m unittest tests.test_portal tests.test_hub` (local socket access
  enabled, existing fake upstream only): `Ran 56 tests in 29.326s`, `OK`, exit 0.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`, exit 0.
- `node docs/screenshots/glass-r1/check.cjs`: `PASS 65 targeted checks;
  6 screenshots; 20 contrast bounds`, exit 0. Uses the existing pinned Playwright,
  Chromium and axe tooling plus `tests/browser/demo.py`; no new test dependency.
- `git diff --check`: exit 0. WOFF2 signature validated; 27,348 bytes.

The reproducible check logs in as synthetic owner and staff accounts. It checks
the real admin overview and staff catalogue at 1440×900 and 390×844, dark/light,
without horizontal overflow; the admin screenshots verify the loaded font and
tabular figures. Utility-only previews use explicitly synthetic content, exercise
focus, single nested blur, solid fallback and motion preferences, and have zero
axe WCAG 2.1 AA findings in both themes. No full-app accessibility conformance is
claimed from those utility scans.

The 20 analytical contrast bounds composite black/white photographs through the
scrim and ordinary/strong/accent surfaces. Supporting text passes ≥4.5:1:
minimum 4.63:1, maximum 15.36:1. This checks the selected text tokens, not every
semantic colour or future component. The unsupported-blur declaration block is
forced active in the test stylesheet; a native browser without blur support was
not available. Reduced transparency/motion use real Chromium media emulation.

Initial checks exposed a test calculation error (alpha was included as a colour
channel) and insufficient muted-label contrast on accent glass. Both were
corrected before the passing result. Screenshots wait for existing theme
transitions and disable screenshot animations to avoid transitional colours.

Not run: full local Python suite (Actions runs it on the PR), heavy browser
matrix, real phones, Safari/Firefox, screen readers, native OS transparency
settings, performance traces/60 fps measurement or CLS measurement. Chrome
DevTools and Motion MCP tools were not exposed; the existing supported headless
Playwright harness was used. No MotionScore audit is claimed.

## Screenshots and remaining reference differences

Required actual app screenshots: `admin-1440-dark.png`, `admin-1440-light.png`,
`admin-390-dark.png`, `admin-390-light.png`. The viewport sizes are exact;
these are viewport tests, not device checks. `utilities-390-*.png` are separate,
full-document synthetic previews of the opt-in materials and focus state.
`results.json` contains the assertion names and measured contrast bounds.

The matching dashboard and Porcelain reference stills are copied alongside the
screenshots. All three reference clips were inspected as sequential one-second
contact sheets, with full-size dashboard/footer stills for material detail.

- Existing Swangz architecture replaces the reference's living-room photography.
- The stronger scene scrim protects supporting text over bright imagery; the reference is more transparent.
- The app still has the labelled, edge-to-edge sidebar; R2 owns the floating icon rail.
- The current overview still has its original joined KPI strip and opaque data panels; later page PRs adopt the opt-in glass utilities and new KPI layout.
- Existing charts, top bar and small hardcoded control shapes remain until their assigned visual passes.
- Sign-in panel swapping, page cross-fades and the liquid footer are outside R1 and remain absent.

No production service, real provider, deployment or merge was used. Browser and
fixture processes terminate in the check's cleanup handler.

## Independent review corrections

Probe rejected initial head `1e0a319` after reproducing the CI browser failure:
Jakarta's font metrics exceed the KPI value's former 1.12 line height. Probe also
found mobile catalogue metadata clipping and the scene printing behind black
text. The initial focused checks above passed but did not cover these defects.

The correction raises KPI value line height to 1.3, wraps catalogue metadata,
and hides the decorative scene when printing. The CI harness now checks catalogue
metadata overflow; the focused check also measures KPI fit, catalogue metadata
and the print scene/paper/text styles. The font and its licence stay unchanged.
Chief confirmed Forge's R3 shared-style work has not started and reserved these
bounded corrections for R1.

Corrected-tree results, all exit 0:

- `UI_WIDTH=<1440|390> UI_THEME=<dark|light> UI_PAGES_ONLY=1
  UI_OUTPUT=/tmp/prism-glass-r1-<theme><width> node tests/browser/check.cjs`,
  executed separately for each of the four combinations: `PASS principal pages
  27 interaction assertions; 25 screen checks` each. Total 108 assertions and
  100 screen checks, zero browser exceptions or axe findings, no KPI or metadata
  overflow. Each run includes the deliberately rejected Studio voice request;
  no unexpected API failures. The role matrix remains on Actions, so these are
  bounded selections of the CI harness, not a complete local CI job.
- `node docs/screenshots/glass-r1/check.cjs`: `PASS 81 targeted checks;
  8 screenshots; 20 contrast bounds`. Print media emulation hides the scene and
  preserves white paper/black body text in both themes/viewports. This is not a
  physical printer or full report PDF check. Contrast bounds remain ≥4.63:1.
- `python3 -m unittest tests.test_portal tests.test_hub`:
  `Ran 56 tests in 30.576s`, `OK`.
- `python3 tests/browser/syntax.py`: `Checked 23 JavaScript files`.
- `git diff --check`: exit 0.

`regression-results.json` records the four CI-harness selections and counts.
The four required admin screenshots were refreshed and visually inspected;
`staff-tools-390-dark.png` and `staff-tools-390-light.png` show the full labels
in the Adobe Premiere and CapCut rows. The wrapping makes those rows taller;
the page layout and other reference differences listed above remain intentional.
Independent re-verification and corrected-head Actions results are pending.
