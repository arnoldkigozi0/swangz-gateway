# Footer #39 triage — 10 November 2026

Inspected source: `c8d048f2885beb5287f0d663b8d63a7f2b75a3f9` on `feature/glass-r11`, clean on entry and identical to remote. Canonical brief read from fetched main `83ac62f`, §6–7 and §10–10.7, including the measured footer in §10.3. Main's brief has no §10.8–10.9. Inspected the actual `footer-04.jpg` reference and the committed `footer-dark-1440x900.png`; reviewed the existing README and raw-trace descriptions. No browser/test/build was launched while Probe holds the exclusive slot.

**Recommendation: close #39 as superseded by the exact-match brief.** Preserve this branch and its measurements for a later, bounded footer implementation after the corrected staff shell is accepted. Do not merge this draft in its present form. This is a recommendation, not a closure or a product change.

## Concrete incompatibilities

| Area | Existing #39 | Canonical target / consequence |
| --- | --- | --- |
| Desktop geometry | `.foot.glass-foot` remains inside the old `.hub-staff-main`, with `--gutter` padding. The saved 1440×900 screenshot shows the panel starting around x272 rather than x30. | §10.3 requires x30–1410 at 1440×852. The saved screenshot is a different height and cannot prove the required geometry. #56 also changes the shell containing the footer, so the old result cannot establish compatibility. |
| Surface and ink | `.gf-panel` uses dark gradients `rgba(48,41,37,.78)` to `rgba(26,22,20,.84)` and inherits pale text in dark mode. | §10.3 specifies milky warm `rgba(235,220,205,.55)` glass with near-black text; the reference visibly uses that treatment. Current difference is not explained by an accessibility requirement. |
| Typography | Old Plus Jakarta Sans inheritance; `.gf-line` weight750, capped at36px. | §10.5 requires Poppins; §10.3 specifies32px/600. New font metrics invalidate old spacing and contrast captures. |
| Input and link layout | `.gf-ask` max-width440px; 40px controls plus 5px padding and borders make a52px field. `.gf-card` has two columns. | §10.3 specifies380×46 and four link columns. Existing content must be mapped to real routes without invented destinations (§10.1(1)/(4)); simply retaining the old two-column layout does not establish a match. |
| Wordmark | README acknowledges the clipped “g” descender; current wordmark is up to300px with800 weight. | Reference shows the complete descender; §10.3 specifies an approximately240px wordmark. No allowed-difference reason is recorded for cropping the letter. |
| Theme control | Unlabelled visual sun/moon icon button from the existing primitive. | The reference has an Evening/Daylight switch. Accessible naming may already exist, but the visual form remains different. |
| Scene sampling | `wordmarkScene()` reads `getComputedStyle(document.body, '::before').backgroundImage`; `.gf-photo .gf-word` paints `--scene-image`. | #56 paints `room-warm.webp` on `.staff-exact` while the inherited scene token still points to `admin-welcome.webp`. The body-scene sampler cannot be assumed to align with the staff room. It needs a source-level integration decision and rendered evidence, rather than copying the old screenshots. |
| Reveal | Existing source fades/rises content; the wavy liquid fill was removed. | §6 requires the liquid fill; §10.2 requires reference timing within two frames. A §10.1(3) performance adaptation needs measured justification. The old comparison is insufficient to claim acceptance. |
| Performance | Saved final interleaved software-render traces report task229ms vs134ms main (dark),221ms vs123ms (light), and roughly two additional >50ms frames/run. README explicitly disclaims parity. | §7 requires60fps on the laptop. Do not replace this measured limitation with an assumption about GPU performance. A bounded reference transition and fresh comparative trace are needed. |
| Acceptance artifacts | Old390×844/1440×900 screenshots, no1440×852 capture or50% reference overlays. | §10.2 acceptance cannot be met using these artifacts. Old checks intentionally assert no live blur and40px link targets; their PASS is not exact-match validation. |

The content differences (real request workflow, actual gateway-health wording and existing routes) can be tagged §10.1(1)/(4). Phone stacking, reduced motion and a measured performance fallback can be tagged §10.1(3). Those tags do not explain the current desktop geometry, dark surface, wrong typeface or cropped descender.

## Safe next step

Chief can close the existing draft with the reason “Superseded by BRIEF §10; old-shell geometry, surface/type and measured performance do not meet acceptance.” Keep its source and trace history. If Chief chooses to finish this existing PR instead, first wait for #56's accepted shell, then update this branch on main, confine staff frame/footer edits to one owner, fix the scene source and layout, and capture the required overlays/contrast/CLS/comparative trace in the scheduled test slot. No new draft is needed for this decision.

Actual checks this shift: read-only source and artifact inspection, local/remote identity, and `git diff --check origin/main...HEAD` (exit0). Not run: local Python/DOM/browser tests, new screenshots, overlays, contrast, CLS or performance; no product code changed and Probe owns the test slot. No backend/sign-in/shared-source edits, dependencies, merge, deployment or closure performed.
