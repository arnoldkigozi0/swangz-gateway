# Probe notes — PR #374 LOCAL head 1335548d3c4bb06f15d6a917917d8c93699b7fd9 (28 Nov 2026, 01:26–01:29 EAT; remote still fdadd35)
Synthetic local demo only, Midjourney set to a shared login locally; 1440x900 and 390x844, light and dark. Off-site requests: none.

## Result: REJECTED — one visual regression introduced by the accessible-name fix
- admin-govern.js: the new <span id="fixed-browsers-label"> is the label's first child, so admin.css:313
  `.field > span:first-child { 11px; uppercase; letter-spacing .06em; --tx-3; 700 }` restyles it.
  Visible label: "FIXED BROWSERS (DORMANT)", 11px/700/muted, next to "Saved browser configuration" at 12px/620.
  Chrome's computed accessible name is therefore also "FIXED BROWSERS (DORMANT)" (4/4 cells; the only 4 failures).
- Tried in the live page only (no product edit; probe-label-style.json): plain text node as before + 
  aria-label="Fixed browsers (dormant)" (drop the span and aria-labelledby) -> label style equals the sibling's,
  name exactly "Fixed browsers (dormant)", description = help only. Both themes at 1440.

## Passed (p374b: 125 passed, 4 failed, exit 1; probe-results.json, probe-run.txt)
- Panel title, intro, selector label, both "(saved setting)" options, agent hint exact; old phrases absent in list mode.
- Description is only the help. Seeded value preserved/editable; keyboard clear+save PATCH
  {"workspace_mode":"","workspace_url":""} 200 {"ok":true}, server empty, reload empty (4 cells).
- Keyboard: select->field->Save and back; ArrowUp/ArrowDown switches modes; hidden field skipped by Tab.
- Both modes: no sideways overflow or clipped text, option text fits the select (257.9px of 275px at 390);
  axe on the sheet body clean; no page/console errors.

## Residual, not changed by this head (saved agent mode only)
- Panel "Company browsers on the rented server" still says to sign in to each browser ("press Sign in to the tool...
  Nobody can be given that browser meanwhile"), and in other states "gets its browsers from here within a minute of
  saving this tool" (source read), under a panel saying Open does not use company browsers.

## Not run
- Open routing / provider launch (#373 open); full suite; CI for this head (not pushed); role permission re-check
  (code unchanged since fdadd35, checked there); BRIEF 10.9 motion trace, fallback/empty-database captures,
  sampled contrast over room-warm; reference overlay (no still for this field; BRIEF 10.1.1/10.1.4).
