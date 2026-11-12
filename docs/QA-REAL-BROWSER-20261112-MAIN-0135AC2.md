# Real-browser re-test on main 0135ac2 (12 Nov 2026, 22:00 to 22:20 Kampala)

Method: `tests/browser/demo.py` from a detached checkout of main 0135ac2 (fake upstream, no real keys), headless Chromium, owner console and staff app
(grace). Pages: Overview, Licences & spend, Devices, Security, Models, Access requests, Audit log; 1440x852 and 390x844, dark and light (28 page loads),
axe wcag2a + wcag2aa on every load, horizontal overflow, scrollers, visible button heights. Plus the Detailed switch, buttons D1 to D3 and the staff top bar.
Screenshots kept: `docs/screenshots/probe-qa-20261112/main-0135ac2/` (8 of 28 + staff; all 28 rows are in `results.json`).
Data: the demo fixture (one person, 13 models, one coding device, 4 tools). Devices and Requests were seen with little data; not run with a large list.

## Verdicts

| Area | Verdict |
|---|---|
| Simple view on Licences, Devices, Security, Models, Access requests, Audit log | VERIFIED, 1 defect (M1) and 1 observation |
| Buttons D1 | VERIFIED fixed |
| Buttons D2 | VERIFIED fixed (every `.btn` at 1201 and 1440 px is 36 or 30; no 34) |
| Buttons D3 | PARTIAL: People and Tools fixed; Models and Audit still show 44 px at phone width (D3b) |
| Staff top bar | VERIFIED (1440 and 390, both themes, axe clean) |

## What was seen

- Every page opens in Simple with one sentence and one next step: "Nothing needs you right now.", "4 paid licences nobody opened in 30 days (about $90.00 a month).",
  "1 device is active; 3 AI requests in 30 days.", "Nothing needs checking right now.", "1 model is in use with no rule yet.", "Nothing is waiting for a decision.",
  "11 changes were recorded in the last 30 days." Detailed opens `?view=detailed`, is remembered after a reload, and gives the full table
  (Devices 8 columns, Models 8, Audit 6). Licences, Security and Requests have no table to show in Detailed.
- axe (wcag2a, wcag2aa): 0 violations on all 28 loads (both admin sizes and themes), and on the staff app in all four cases.
- No page overflows sideways at 390 or 1440. The only console error is the 401 the sign-in page gets before login.
- At 390 px Devices, Models and Audit are cards, not tables; the one wide element found sits inside the card list, not the page.
- Staff top bar: 76 px tall at 1440 (width 1170) and at 390; search, New, bell, avatar, no overflow; light theme reads correctly.
- D1: on a touch device the loading button's spinner box is 14x14 and rotates in place (`ctl-turn`); no 44 px box any more.

## Fix list

| # | Page / element | Expected | Seen | Smallest fix |
|---|---|---|---|---|
| M1 | Models at 1440x852 | One scroll area (10.10.7: no double scrollbar) | The page is 876 px tall in an 852 px window (24 px of page scroll) while the table also scrolls inside its panel (`.u-table-wrap` 705 over 462) | Size the Models panel to the free height as Audit log and Devices do (their pages are exactly 852 px) |
| D3b | Models "See all 13", Audit "Previous" and "Next" at 640 px and narrower | Visible 36 / 30 px, hit area 44 | Visible height is 44 px | The same fix as D3 on those routes (`admin.css` mobile `min-height: 44px`) |
| O1 | Audit log at 1440x852 | Panel fills the free height | The table panel stops at 686 px and leaves about 130 px empty beneath, while Models fills to 796 | Observation only |
| O2 | Light theme, Licences at 1440 | No white pill | The breadcrumb "Money › Licences & spend" sits in a white pill (the known light-theme item in lane B) | Lane B (light theme) |

Not run: the full Python suite (CI), a large-data run of Devices and Requests, real phones, the staff app Tools and Studio pages.
Second opinion: Probe (no second opinion).
