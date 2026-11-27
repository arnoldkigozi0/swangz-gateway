# Fixed browsers — dormant field

Current product source: `89477314104a88ad42b9509bb71ce15fca82509f`. Evidence is in [head-8947731](head-8947731/). Captured by Probe on the synthetic local demo, after 01:20 EAT, 28 Nov 2026; no off-site requests.

## Required captures

| Size | Light | Dark |
| --- | --- | --- |
| 390x844 | [saved value](head-8947731/account-saved-390x844-light.png) | [saved value](head-8947731/account-saved-390x844-dark.png) |
| 1440x900 | [saved value](head-8947731/account-saved-1440x900-light.png) | [saved value](head-8947731/account-saved-1440x900-dark.png) |

Empty-field and saved-agent not-configured captures at all four cells are also committed, together with the two failing 390px listed-browser captures. Other exploratory captures remain local, untouched.

## Actual result and limits

Probe VERIFIED the requested corrections: normal-case label/style; accessible name exactly the visible label; help as description; both mode labels and dormant-panel text; preserved editable saved values; keyboard clear/save/reload with HTTP 200; keyboard paths and clean axe. Prism inspected all four required saved-value images and verified PNG dimensions.

The extended run had **251 passes, 2 failures, exit 1**, not an all-green run. Both failures are existing browserRow status-text overlap at 390 in the stubbed listed-browser state (both themes); browserRow and CSS are unchanged. [Full results](head-8947731/probe-results.json), [run output](head-8947731/probe-run.txt), [review notes](head-8947731/probe-notes.md). Follow-ups: legacy sign-in controls still exist in listed rows, and the not-configured notice separates text/link/punctuation at 390. These are retained visibly in evidence; they were not silently fixed or removed from results.

Static syntax/whitespace checks pass. Initial source fdadd35 had a 117-pass/exit-0 scoped run and green CI; this does not establish CI for the corrected head. The intermediate 1335548 label regression had 125 passes/4 failures/exit 1 and is fixed in the current source. Original notes/results are retained as historical evidence; their images remain local rather than duplicated in this PR.

## Visible differences and unavailable checks

BRIEF §10.1.1: label, options and help now identify dormant saved configuration. §10.1.4: product-specific settings with no corresponding reference still. Existing CSS/controls are reused. No visual redesign or new motion. No reference overlay is claimed.

Not run: provider Open/routing (#373 is a required dependency); real agent/browser button actions; full local suite; §10.9 motion/fallback/empty-database/room-background contrast matrix. Roles were verified on initial source fdadd35; permission/save logic remains unchanged. All demo/browser processes were stopped by Probe. **No merge authorized; hold for #373 and final CI.**
