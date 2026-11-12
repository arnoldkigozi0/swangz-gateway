# Real-browser QA, 12 Nov 2026 (main aab785a; #157 re-checked on 6909f01)

Method: `tests/browser/demo.py` (fake upstream, no real keys), Chromium, owner console, 13 people added by API, dark and light,
1280x720 and a 390 px window. Screenshots in `docs/screenshots/probe-qa-20261112/aab785a-*`.

## Verdicts

| PR | Verdict |
|---|---|
| #141 Bookings buttons | VERIFIED with 3 defects (D1 to D3) |
| #151 People Simple | VERIFIED, no defect (one observation, O1) |
| #152 Tools Simple | VERIFIED, no defect |
| #157 cancelled renewal (main 6909f01) | VERIFIED |
| #158, #159 | still draft, not checked |

## What was seen

- **#141:** all five kinds on the Kit page measure to BRIEF 10.10.6: 36 / 30 / 42 px tall, 4 / 3 px radius, 13 px 600, gap 6, padding 14,
  secondary rim .22, danger outlined and never filled, primary rest `#F2F2F2`, sweep layer `scaleX(0 > .5 > 1)` from the left over 200 ms, 2 px focus ring.
  Light half-way frame: label `#F2F2F2` on the sweep colours is 4.82 and 5.91 : 1 (rest 17.4 : 1), so AA holds. `controls.css` is linked from `/`, `/admin`, `/device`.
- **#151:** sentence carries the real count ("12 of 13 people have not signed in yet."), the next step opens `#/people?status=invite` with exactly those 12,
  5 columns, 10 rows and a pager ("1-10 of 13", Next gives 3), Detailed gives the 7-column table, the choice is remembered per console user and in `?view=`.
- **#152:** "2 tools were given but never opened." opens `#/tools?show=idle` with exactly Canva and Midjourney, 5 columns in Simple, Sign-in column in Detailed,
  empty search ends in "See all tools". At 390 px both pages are cards with one primary.
- **#157:** a cancelled plan renewing in 5 days is not listed on Needs attention; an active plan renewing in 5 days is.

## Fix list

| # | Page / element | Expected | Seen | Smallest fix |
|---|---|---|---|---|
| D1 | Any `.btn` in the loading state on a touch device (`hover: none`), e.g. Kit page "Loading" | The S spins in place, centred, 14 px | `controls.css:103` (`@media (hover: none)`, `.btn:not(.link)::before`, 44 px tall, `translateY(-50%)`) has the same specificity as the loading rule at line 58 and comes later. It overrides the loader's box and the rotation animates from `translateY(-50%)`, so the S jumps up and down by about 10 px and is off-centre (three screenshots of the same button show it at different heights) | Exclude the loading states from the hit-area rule: `.btn:not(.link):not(.loading):not([data-loading="true"]):not([aria-busy="true"])::before` |
| D2 | Every console page header action at 1201 px and wider (Add a tool, Add a policy, Register a model, Open an incident, Export CSV, Refresh, Spend reports, Review changes, Safeguards) | 36 px (BRIEF 10.10.6) | 34 px (`admin.css:1356`). On People the header's Add person is 36 px, so the same header row has two heights | Change `min-height` and `height` to 36px on that line |
| D3 | People and Tools at 640 px and narrower: every `.btn` (Open, Add a tool, next step) | Visible size stays 36 / 30; only the hit area grows to 44 | Visible button is 44 px (`admin.css:1474`; the same pattern at lines 1466, 1482, 1504 and 1514 for other routes) | Drop the `min-height: 44px` rules and rely on the shared hit-area layer, after D1 is fixed. Low priority: phones get bigger buttons, nothing breaks |

Observation O1 (no fix asked): on a filtered People view the sentence keeps "12 of 13 ..." but the next step turns into "Give someone a tool". That reads as intended (the link would point at the page you are on).

Second opinion: GPT-6.1 Sol (a different vendor from the Claude-authored PRs) confirmed D1, D2 and D3 by reading the CSS.
