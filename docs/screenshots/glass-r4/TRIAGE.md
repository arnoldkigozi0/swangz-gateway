# Overview #44 triage — 10 November 2026

**Recommendation: close #44 as superseded by BRIEF §10.7 and the immediate §10.9 gates.** A plain rebase or isolated header/KPI adjustment cannot make this old tabbed Overview the specified dashboard. Preserve the branch, its phone-focus diagnosis and raw traces. This record recommends closure; it does not close or merge the PR.

Inspected source: `972aaeeba88dfd1d89ddd119e7742fefc5401f23`, identical to remote and clean on entry. Canonical brief: fetched main `5196617f45590b919f5cbd38cf71cf9aad1941a4`, §10–10.9. Viewed the canonical `dashboard-02.jpg` (its blob matches main), plus the saved desktop-dark and phone-light R4 screenshots. #56 remains frozen and untouched. No local test/browser/build was launched during Probe's exclusive slot.

## Source and reference conflicts

| Area | #44 source / preserved evidence | Current requirement |
| --- | --- | --- |
| Page structure | `pageOverview()` keeps Right now, Trends, Top tools & people and Licences tabs. The first view is Most urgent + Live activity. | §10.7 explicitly removes these tabs from Overview. The default layout must show the eight-day AI usage tube chart, two count cards and Uses by tool donut/legend in the reference positions. This is a body-layout replacement, not a header-only patch. |
| Header | Title “Overview”, a42px icon disc, area eyebrow, up to41.6px heading and44px actions. Saved desktop subtitle is near y193 and cards start near y228. | §10.3/10.7 require Hello/name greeting,24px/600 heading at x178, subtitle y117, no area eyebrow,34px actions and cards starting y140. These visual changes exceed the allowed4px tolerance. |
| KPI geometry | CSS: minimum204px height,16px gaps,20px padding,22px radius. Saved results record301×240.15625px desktop cards. | §10.3 specifies285×152px,12px gaps,18px radius. Actual saved height differs by about88px; the CSS minimum alone exceeds target by52px. |
| KPI type and order | Labels10px; values up to36px;28px arrow discs. Order is spend, active today, requests, security. | §10.3 specifies11px labels,24px values,24px arrows. §10.7 order is spend, requests, active people, security. |
| Scene/material | Inherits `admin-welcome.webp`, dark scrim.78/light.88, Plus Jakarta Sans, gold primary and old rail. | §10.3–10.5 require the approved room, approximately.30–.40 dark scrim, Poppins and amber accent. The saved screenshot visibly retains the old shell. Rebasing does not supply the new console shell, and old font/contrast results cannot validate a changed scene. |
| Acceptance harness | `check.cjs` explicitly expects Jakarta, `admin-welcome.webp`, four Overview tabs and the old chart placement. | Updating appearance while retaining those assertions would fail; weakening them would conceal a mismatch. A replacement implementation needs assertions for the canonical layout instead. |

Real data/wording can use §10.1(1); the approved photo uses §10.1(2); phone/accessibility changes can use §10.1(3). Those exceptions do not permit the desktop card dimensions or the tabs expressly removed by §10.7. Deferred R16/R17 components are not started by this triage.

## Immediate §10.9 gates

- **Low data is visibly noncompliant:** `fmt.money()` in inherited `ui.js` emits four decimals below one cent. The actual saved R4 screenshots/results show `$0.0054`, whereas §10.9 requires `< $0.01`. Zero counts have existing contextual text, but the required one-line zero reason and same-size empty-card explanation/action have not been implemented or demonstrated for every Overview card. The harness's intercepted zero response is not a fresh empty-database screenshot. No production/laptop data was read for this triage.
- **Smoothness remains blocked:** preserved Chrome traces capture source `d89f3e7` versus baseline `6ee3ed3`; product code has not changed since that capture. R4 recorded22 frames over50ms, maximum416.7ms; baseline0, maximum33.3ms. Both compressed-file SHA-256 hashes match the recorded provenance. One unthrottled dark/software-render sample is limited evidence and cannot identify a cause or prove the new4×-CPU/≥55fps/CLS0 gate. It nevertheless gives no basis to clear performance.
- **Contrast/fallback evidence is incomplete:** old main-content axe scans cover four theme/size cells, but `results.json` has no sampled contrast entries. Required brightest-room samples and reduced-transparency/no-backdrop-filter screenshots are absent. Reduced-motion hover assertions exist; they are not the complete fallback screenshot set.
- **Reference evidence is incomplete:** saved desktop screenshots are1440×900, not1440×852; there are no50% overlays, measured reference colour samples or frame-stepped motion comparison. The existing phone screenshots remain390×844. No current-reference acceptance is inferred from historical PASS results.

The S loader, live pulse and Compact switch are deferred R17 work. The low-data and quality gates above apply immediately under the final paragraph of §10.9 and cannot be deferred with R17.

## Preserved useful work and next step

Keep the neutral AI-request delta, real endpoint/range mapping, phone focus/wrapping reproduction, API-error checks and trace history for the eventual canonical Overview implementation. The four-tab phone fix may cease to apply when those tabs leave Overview; do not reintroduce them merely to preserve this patch. There is also a small Live “Search everything” range-link change in the diff; it remains preserved on this branch rather than being silently deleted or spun into a new PR during the WIP limit.

Chief can close #44 with: “Superseded by BRIEF §10.7: old tabbed Overview/KPI geometry conflicts with the canonical dashboard; immediate §10.9 low-data and performance gates are unmet.” If Chief retains it, rework the existing draft as the canonical Overview after console-shell ownership is scheduled, using real endpoints and the required low-data/quality evidence. Do not merge the old design as an intermediate step. #47 remains queued until the #44 decision.

Actual checks this shift: read-only source/reference inspection; local/remote identity; saved screenshot dimensions; inspection of58 historical checks/four axe scans; both trace hashes match; no product diff after captured source; `git diff --check origin/main...HEAD` passed. Not run: new Python/DOM/browser tests, screenshots, overlays, contrast, fallback, CLS or performance capture; Probe owns the exclusive slot. Historical56 Python tests/46.351s and58 focused checks remain historical. No product, shared sign-in/client/backend, root/WIP or #56 file changed; no dependency, new draft, closure, merge or deployment.
