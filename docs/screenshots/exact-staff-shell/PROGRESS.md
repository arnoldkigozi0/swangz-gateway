# Staff shell exact-match pass — 8 November 2026

Branch: feature/exact-staff-shell. Seed: PR #53, design/exact-match-brief at 9ceae8faea223337b8fc4ee66d936d5f3812a9b6. Draft only; visual acceptance is blocked.

Product changes are confined to portal.js, portal.css and new exact-staff.css. The CSS is imported by portal.css, so no shared HTML, ui.js or exact.css wiring change is needed. source-identity.json records unchanged shared blobs. The new appearance requires #53's approved font/image assets and tokens; #53 is an unreviewed prerequisite, not a claimed approval.

The reference rail and floating workspace, breadcrumb, search, New, clock, bell and account controls replace the wide staff sidebar. Existing staff routes remain available through All pages and Ctrl/Command+K search. Studio visibility still uses the existing server-derived availability. Icon links have accessible names and focus tooltips; Up/Down/Home/End move through the rail. Account and New menus support arrow keys, Home/End, Escape, natural Tab dismissal and focus return. Menu capture closes before profile/password actions create a dialog, preserving its native focus. Profile, password, theme, usage policy, help and sign-out remain available. Staff receive no emergency authority: admin Stop all AI/Resume, command menu and Settings routes are byte-identical to #53.

## Actual checks

- `python3 -m unittest tests.test_portal tests.test_hub`: **Ran 56 tests in 35.051s, OK**. Real local HTTP with synthetic gateway/FakeUpstream, no production or provider traffic.
- `node tests/browser/exact-staff-shell-model.cjs`: **18 checks, PASS** using the shipped ui.js and portal.js in a minimal synthetic DOM. Navigation names/current state, rail arrows and wrapping, account menu arrows/Home/End/Escape/focus return, primitive theme switch, literal untrusted name text, all ten destinations, search and empty state, Escape close, Ctrl+K, unavailable Studio and signed-out shortcut guard. This is behavior coverage only. The initial harness run failed because its focusout event lacked target; the fixture was corrected, then passed. No browser result is implied.
- `python3 tests/browser/syntax.py`: **Checked 27 JavaScript files**, exit 0 (includes both new harnesses).
- `git diff --check`: passed.
- Shared source identity: ui.js, index.html, admin.html, exact.css and admin.js unchanged from seed.

## Not run / remaining acceptance gates

OpenMausBot browser/Chrome DevTools tools are not exposed in this conversation. Tool discovery found neither agent_browser actions nor chrome-devtools. No alternate shell-launched browser was used. Therefore **no screenshots, 50% overlays, rendered position/radius/colour measurements, axe scans, browser focus/overflow/zoom checks, real screen-reader checks or performance traces were produced**. No visual or WCAG sign-off, CLS 0 or 60 fps claim.

`tests/browser/exact-staff-shell.cjs` is provided for the authorized browser-test surface. It starts/stops tests/browser/demo.py, uses synthetic staff login, checks four viewport/theme cells (1440×852 and 390×844, dark/light), five measured desktop shell bounds, account/search keys, overflow and axe; saves screenshots, results, matching still, side-by-side and 50% overlay with existing ffmpeg. It is **syntax-checked only**, not executed. A failed check saves partial results and must be resolved before acceptance. Full suite and fresh CI are pending GitHub Actions; no concurrent local full suite was started.

## Remaining differences, tagged to BRIEF §10.1

- §10.1.1: Swangz branding, staff page names, account initials and real notification counts replace CRM words/data; the rail has nine staff routes only when Studio is available. No invented activity or KPI numbers.
- §10.1.1: No green avatar presence dot: the staff endpoint supplies no online-presence evidence.
- §10.1.2: The approved room-warm.webp replaces the reference room; local scrim is .32 dark / approved light .42. Photo colour samples still need actual rendering.
- §10.1.3: Light theme uses dark text and milky surfaces; phone hides the rail, clock and New pill and exposes all destinations through the workspace drawer. Phone controls have 44px minimum targets. Detailed phone polish remains the separately queued task; no second build started.
- §10.1.3: Pill/menu surfaces are provisionally more opaque for readability, with solid reduced-transparency/unsupported-blur fallbacks and visible focus rings. Contrast has not been measured; this tag does not waive verification.
- §10.1.4: Staff launchpad content remains the existing real-data workflow; this scoped PR changes the shell only. It does not claim the staff Home body matches dashboard-02's administrator metrics. Body appearance requires its own review.
- §10.1.4: The old simple footer's help/policy actions move into account/help routes; the separate liquid-footer work is pending.
- §10.1.4: New offers existing access, procurement and adoption-report routes; no unsupported create action or endpoint is introduced. Help and settings open existing staff privacy/profile destinations.

Every listed difference requires Probe review. Missing browser measurements are an evidence gap, not an allowed design difference. Untagged rendered differences must fail acceptance.

## Exact next step

Probe: run the focused real-browser harness on the authorized browser-test surface at this PR's exact head, inspect all four images and reference overlays, measure remaining shell colour/radius/motion values, and return any defects. Keep draft until #53 prerequisites, section 10 evidence, CI and independent verification pass. The workspace trigger retains the existing “Open navigation” accessible name so the shared mobile harness selector remains valid. No shared harness edits were made here.

#44 remains on HOLD; #50 and other old appearance drafts were not changed. No merge, deployment, Netlify configuration change, new font/library, production sign-in or data mutation.
