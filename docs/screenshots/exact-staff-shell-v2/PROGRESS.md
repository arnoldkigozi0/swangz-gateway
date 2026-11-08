# Isolated staff shell — 8 November 2026

Base: main a3ff895ad5854d583ef8d7abf1b31ec61d6bc60d. Branch feature/exact-staff-shell-v2 supersedes the seed-based #55. Only staff-frame code was transplanted. Main showSignIn, signOut, startup and every byte outside that frame section are unchanged (source-identity.json). No inherited console, Overview, splitGate or authentication bundle. No HTML/ui.js/admin changes.

The offending #53 global `.shell` console grid is excluded: exact.css is neither present nor loaded. The staff CSS scopes Home grid columns to .staff-exact and preserves main’s normal desktop/phone columns, so a generic staff .shell never receives a 129px console column. The focused browser harness additionally checks 1440px Home grid width/columns and visible, fitting metadata in both themes.

Actual checks: `python3 -m unittest tests.test_portal tests.test_hub`: Ran 56 tests in 34.802s, OK. `node tests/browser/exact-staff-shell-model.cjs`: 18 checks PASS against actual main ui.js + transplanted portal.js in a synthetic DOM. `python3 tests/browser/syntax.py`: Checked 28 JavaScript files. `git diff --check`: passed. Source identity checks passed for main auth/outside-frame and ui.js, HTML, admin.js, admin-monitor.js; no generic console grid rule.

Not run: browser/Chrome DevTools actions are not exposed in this conversation; no shell-launched replacement browser was used. No light-1440 rendered metadata result, full browser-job success, screenshots, overlays, axe, contrast, CLS or performance result is claimed. Existing GitHub full browser job must pass; provided focused harness is syntax-checked only. Full Python suite delegated to existing CI to avoid concurrent heavy local runs.

Dependencies and tagged differences against BRIEF 10:
- §10.1.1: Swangz staff words/routes/real counts replace CRM data; no invented presence dot or emergency authority. Admin Stop all AI/Resume routes are untouched.
- §10.1.2 / §10.5 DEPENDENCY: current main lacks #53 room-warm.webp and Poppins files. This bounded branch uses main’s home-welcome.webp and existing font; approved room/font assets need a separate scoped delivery or explicit ownership expansion. It does not depend on the seed’s auth/console bundle. Exact-match acceptance remains blocked by these visible differences.
- §10.1.3: light surfaces, keyboard focus/menu keys, reduced-motion/transparency fallbacks, basic phone drawer and 44px phone targets. Opacity and contrast still need browser measurements.
- §10.1.4: Staff launchpad body remains the real existing workflow, not the admin Overview; help/policy remain in account routes and liquid footer work remains separate. Studio still depends on server availability. New links to existing request/adoption workflows only.

Any untagged rendered difference is a defect. Missing browser evidence is not an allowed visual difference.

Next: run full browser CI and focused exact-staff-shell.cjs on this exact head, especially light 1440 Home metadata and both theme/size cells; inspect overlays and fix any measured defects. Keep draft until independent verification and asset dependencies are resolved. portal.js is released to Forge at the pushed commit; Prism must not edit it during Forge sign-in work. CSS-only phone follow-up is separately queued. No merge/deploy, production sign-in, new dependencies, #44/#50 edits or shared-file changes.

## Approved asset correction — local review checkpoint, 12:25 Kampala

Chief authorized copying #53's existing approved fonts and room photo without inheriting its bundle. Five Poppins latin weights (400–800), Poppins-OFL.txt and room-warm.webp were copied byte-identically from 9ceae8f; asset-identity.json records all seven blobs and byte sizes (69,629 bytes total). exact-staff.css registers a staff-specific font-family and sets --font only on .staff-exact, then uses the room photo in both themes. The asset dependency described above is resolved locally; it is not yet pushed.

Recheck: 56 Python tests in 34.679s, OK; 18 synthetic-DOM checks PASS; git diff --check passes. portal.js remains byte-identical to the released e6f13f0 version. No auth/shared files changed. The baseline CI browser failure remains “Choose a tool” clipped at light 1440; Probe's rendered bounds/styles are pending. No speculative clipping fix, browser workaround or weakened test was introduced. These assets will be batched with the evidence-based CSS correction, respecting at least 30 minutes since the previous branch push. Fresh full browser CI and independent overlays/axe/trace remain required after that batch.

Correction to whitespace result: the earlier unstaged CSS diff check passed, but the staged asset check reports pre-existing trailing whitespace at Poppins-OFL.txt:21. The licence is deliberately preserved byte-for-byte as authorized; no whitespace cleanup was applied. Excluding that unchanged upstream licence, the correction diff check passes. A fresh GitHub status read failed with an API connection error; no additional CI result is claimed.

## Main #51 integration — 12:28 Kampala

Normal conflict-free merge of origin/main 91a1a086c828b262bfc58b2cd074a2bf5083f3d0 created 3381074ec1a553f00740f21c4abee7857927c37c. Only the two-line chart browser CI addition arrived. Workflow matches main byte-for-byte and retains both lists.cjs and charts.cjs. portal.js remains byte-identical to released e6f13f0; no sign-in or other portal edits. Approved asset commit 4f18777 is preserved. main51-identity.json records checks.

Targeted integration retest: Ran 56 tests in 49.281s, OK (`tests.test_portal tests.test_hub`); 18 synthetic-DOM behavior checks PASS; diff check passes excluding the preserved upstream licence whitespace already recorded above. No full local suite or duplicate browser QA. Probe clipping bounds still pending; CSS clipping correction, fresh full browser CI and overlays/axe/trace remain open. Integration and assets stay local for the existing batched push, at least 30 minutes after the previous branch push. No new PR/build/phone task or portal ownership change.

## Diagnosed CSS correction — 12:36 Kampala

Chief relayed Probe’s real-browser diagnostic on old remote e6f13f0: later hub.css `.hub-staff-app` won over equally specific `.staff-exact`, retaining the 216px grid. Probe’s injected compound selector restored desktop main x173/1170px and phone main358px with no horizontal overflow; desktop four-cell clipping checks passed. These are **Probe-reported** bounds, not Prism reruns; provenance is in probe-diagnosis.json. Prism inspected Probe’s fixed-light-1440 screenshot and confirmed the visibly unreadable heading/lede over the dark inherited hero art.

The source now uses `.hub-staff-app.staff-exact { display:block; grid-template-columns:none }`. No button widths, hub.css, assertions or portal.js changed. A second cascade issue required a more specific local hero ::before selector so later `.hero.art::before` cannot replace its readability scrim. The staff lede override now correctly targets `.home-lede` rather than `.lede`. The old staff doorway ::after is removed, leaving the approved room scene behind the local scrim.

**Forced accessibility difference §10.1(3):** only the Home hero receives rgba(28,24,22,.88) dark / rgba(252,248,242,.94) light scrim, behind its existing text and controls. No box dimensions, font sizes, surrounding room scrim or global room appearance are changed. It adds no blur layer. hero-contrast-bound.json calculates WCAG specified-colour lower bounds for any sRGB underlying photo: dark heading11.7695/lede8.6818; light heading14.5856/lede9.4577, each >=4.5. These are mathematical guarantees for the declared colours/compositing, **not fresh rendered-pixel or computed-style measurements**. Probe must still confirm the final cascade and pixels with approved Poppins/room assets.

Actual correction checks: Ran56 Python tests in33.348s, OK;18 synthetic-DOM checks PASS; released portal.js byte-identical; whitespace check passes excluding the unchanged upstream OFL whitespace. No new browser run, overlay, axe, CLS or performance clearance. Fresh browser CI and Probe QA must cover1440×852/900 both themes and390×844. All pending changes will be pushed together after12:46:43 Kampala (30min after previous branch push recorded by remote-tracking reflog). The existing PR stays draft.
