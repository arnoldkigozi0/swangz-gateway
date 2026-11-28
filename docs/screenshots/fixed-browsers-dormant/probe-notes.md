# Probe notes — PR #374, head fdadd35e4908127760669a3553c52f5aef023629 (28 Nov 2026, 01:20–01:23 EAT)
Synthetic local demo only (tests/browser/demo.py, Chrome headless, off-site requests blocked: none attempted).
Local fixture: Midjourney was set to signin=shared; workspace_mode empty; two https://fixed-browser.example.test/ addresses seeded.
Route: /admin#/tools?open=midjourney&tab=account

## Result: VERIFIED for the dormant-field scope (one nearby copy defect below)
- p374 run: 117 passed, 0 failed, exit 0 (probe-run.txt, probe-results.json). Settled focus run exit 0 (probe-focus.json).
- 1440x900 and 390x844, light and dark: label "Fixed browsers (dormant)", help text exact, placeholder "Leave empty",
  old sign-in promises and example URLs absent, seeded value preserved and editable.
- Accessibility tree: description = the visible help. Name = label followed by the same help (nit: read twice;
  the hint sits inside the wrapping label).
- Keyboard: select -> Tab -> field -> Tab -> Save; Shift+Tab back. Settled focus: border + 3px halo
  (border vs field background 10.66:1 dark, 6.7:1 light). The dark 1440 "focus" entry in probe-results.json was read
  before the style settled; probe-focus.json is the valid reading.
- No sideways overflow (page, sheet, body, textarea, help); field and help inside the viewport and uncovered.
  At 390 long saved addresses wrap and the 3-row textarea scrolls vertically.
- Owner cleared with the keyboard and saved (4 cells): PATCH /admin/api/tools/midjourney
  {"workspace_mode":"","workspace_url":""} -> 200 {"ok":true}; server value empty; reload empty.
- Agent option hides the field; switching back shows it. Saved agent mode keeps the value, hidden.
- Roles: billing and security see it disabled, no Save, PATCH 403; operations (govern) editable, PATCH 200.
- axe (WCAG 2/2.1 A+AA) on the sheet body: no violations in 4 cells. No page or console errors.
- CI at this head (gh pr checks): app-window, browser, python 3.10, python 3.12 pass.

## Open copy defect (same panel, lines not changed by this PR)
- admin-govern.js ~1243: the select above the field is labelled "Where Open takes them" (options "Swangz's company
  browsers — started when needed" / "The browsers listed below, or none"), directly over "Open never sends anyone to them".
- admin-govern.js ~1203-1204 (agent option): "People get a company browser that is already signed in..." /
  "Until they are, Open can't give anyone a browser for this tool." catalog.uses_workspace() returns False.

## Not run / not covered
- Open routing and provider launch (#373 still open at 857a3903). Full suite and other local tests.
- BRIEF 10.9 smoothness trace, reduced-transparency/motion/no-backdrop captures, empty-database capture,
  sampled contrast over room-warm; no reference still for this field (BRIEF 10.1.1 / 10.1.4).
- First script attempt used GET /tools (404, my error; the list is /catalog); no product behaviour exercised.
