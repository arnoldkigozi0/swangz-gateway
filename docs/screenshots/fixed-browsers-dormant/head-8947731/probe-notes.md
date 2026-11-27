# Probe notes — PR #374 LOCAL head 89477314104a88ad42b9509bb71ce15fca82509f (28 Nov 2026, 01:30–01:34 EAT; remote still fdadd35)
Synthetic local demo only; Midjourney set to a shared login locally; 1440x900 and 390x844, light and dark. Off-site requests: none.
Saved-agent states "empty", "error" and "listed" are browser-side stubs of GET /admin/api/workspace; "not-configured" is the demo's real reply.

## Result: VERIFIED for the corrections (1335548 label regression fixed; saved-agent panel copy corrected)
- p374d: 251 passed, 2 failed, exit 1 (probe-results.json, probe-run.txt). Both failures are the pre-existing item below.
- Label: plain text, style equal to "Saved browser configuration" (12px/620/normal), name exactly
  "Fixed browsers (dormant)", description only the help (4 cells).
- Both selector modes: copy exact, keyboard switch, hidden field skipped, no clipping, axe clean.
- Value preserved/editable; keyboard clear+save PATCH {"workspace_mode":"","workspace_url":""} 200; reload empty.
- Saved-agent panel, 4 states x 4 cells: title and final hint exact; status lines exact; old setup/sign-in phrases absent
  in the three states without browsers; field hidden and value kept; Tab from Save reaches the link / browser button; axe clean.

## Follow-ups (existing code, not changed by this PR)
- 390x844, "listed" state (both themes): in browserRow, "owner@swangzavenue.com is signing it in" overflows its column
  and runs under the "Open again" button (the 2 failures). Screenshot account-saved-agent-listed-390x844-light.png.
- Listed browsers keep "Sign in to the tool", "Open again", "Done", "is signing it in" (and, source read, the toast
  "Ready. Sign in to the tool inside it, then press Done.") inside a panel marked dormant.
- 390: the not-configured notice lays text, link and final "." in separate columns.

## Not run
- Open routing / provider launch (#373 open); real workspace agent; browser button actions; role permissions (unchanged,
  checked at fdadd35); full suite; CI for this unpushed head; BRIEF 10.9 motion/fallback/empty-database/contrast checks;
  reference overlay (no still; BRIEF 10.1.1/10.1.4).
