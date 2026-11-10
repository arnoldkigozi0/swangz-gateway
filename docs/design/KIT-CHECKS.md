# Control kit: how each control is verified (BRIEF §10.10 point 5)

The acceptance checks Probe runs on every merged kit PR, written down so builders can run them first. A control
passes only when every row for it passes at 1440×852 and 390×844, dark and light. Nothing here is built yet
on main (10 Nov, c429f93): a row is "Not run" until the PR for that control has been checked on its merged head.

## Checks that apply to every control

| # | Check | How it is run |
|---|---|---|
| 1 | Radius from the tokens (`--radius-control` 10, `-sm` 8, `--radius-chip` 6), none from `--radius-pill` | `grep -nE "999px|--radius-pill|border-radius: ?50%" gateway/static/*.css gateway/static/*.js`; each remaining hit must be an avatar, status dot, bell dot, donut or KPI arrow circle (§10.10.2) |
| 2 | Keyboard only | Tab reaches it; Enter/Space/↓ opens; arrows move; Esc closes and focus returns to the trigger. Played with Playwright `keyboard`, asserting `document.activeElement` |
| 3 | Roles and names | axe wcag2a/2aa/21aa clean; `role` as listed below; every icon-only trigger has an `aria-label`; open state in `aria-expanded` |
| 4 | Focus ring | 2px ring 2px outside the box, visible on the page background in both themes, ≥ 3:1 |
| 5 | Text contrast | Pixel method: blank the text, screenshot, sample behind each run at the 5th percentile; ≥ 4.5:1 (≥ 3:1 large text and non-text) |
| 6 | States | default, hover, focus, pressed, open, selected, disabled (45%, not clickable), loading (width does not jump: bounding box equal before/after), error (message under the field, never colour alone), empty |
| 7 | No layout shift | CLS 0 opening and closing it; no horizontal page scroll |
| 8 | Touch size | At 390 wide every interactive target ≥ 44px in its short side |
| 9 | Phone behaviour | Menus and dropdowns that would leave the screen flip, and become a bottom sheet at 390 |
| 10 | One kit | The control comes from `SUI.*`; a page that builds its own markup for the same job fails |

## Per control

| Control | Role / extra checks |
|---|---|
| Dropdown select | `button[aria-haspopup=listbox]` + `role=listbox`/`option`; tick on the current option; type-to-jump; a search field inside when > 8 options; < 5 options on a page with room must be a segmented control |
| More menu (⋯) | `role=menu`/`menuitem`; every table row ends in exactly one; destructive items last, separated, danger colour |
| Split button | Main part acts; chevron part opens variants; two separate tab stops |
| Segmented | 2–4 options, `role=radiogroup` or tabs semantics, choice in the address |
| Tabs | `role=tablist`; ≤ 6 visible, the rest under "More ▾"; one strip per page |
| Filter bar | Search + ≤ 3 dropdowns + "More filters"; each active filter a removable chip with "Clear all"; the address reproduces the list (reload and compare rows) |
| Date range | Presets + Custom calendar; chosen range always shown as text; format "10 Nov 2026" |
| Accordion | Closed by default, one-line summary, `aria-expanded`, state remembered per page |
| Side sheet | 480px (full width at 390), `role=dialog` with focus trap, Esc closes, sticky footer with Cancel before the primary, unsaved changes confirmed |
| Stepper | Numbered steps, Back/Next, a review step, ≤ 6 fields per step |
| Dialog | Only for destructive or irreversible acts; confirm button names the action, never "OK" |
| Popover / tooltip | Tooltip on hover and on keyboard focus; popover on click with a link to the list behind the number |
| Pagination | Only over 25 rows; 25/50/100; "1–25 of 312"; sticky header; bulk bar only with ticked rows |
| Toast | Bottom-right, one line + Undo where undoable; errors stay until dismissed; `role=status` / `alert` |
| Breadcrumb | Each crumb a link; last-but-one crumb has a sibling dropdown; Back returns to the same filter and scroll |
| Scrollbars | 8px, thumb radius 4, one style everywhere; no panel shows two scrollbars (count `scrollHeight > clientHeight` on nested overflow elements); `scrollbar-gutter: stable` (no width change when a bar appears) |
| Rail | radius 16; icon boxes 40×40 radius 10; tooltip after 300 ms and at once on focus; All pages drawer matches the Page levels table |

## The kit page (`/admin#kit`)

Owner-only. It shows every control in every state above, in dark and light, in one scroll; it is the page Probe
screenshots per control. It is a development reference, so it is not part of the Page levels chain and carries no data.
Verified-when: each control appears with all ten states of check 6, and the page itself passes checks 3, 5 and 7.

## Report format

One line per control: PASS / FAIL + exact element + the failing check number. Anything not run says "Not run: <reason>".
