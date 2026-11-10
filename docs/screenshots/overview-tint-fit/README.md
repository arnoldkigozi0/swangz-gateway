# Overview: first card tint and fitting the frame (BRIEF 10.4, 10.3)

Two differences left open by R17, measured at 1440x852 in dark against `dashboard-02`.

| | Before | After | Reference |
|---|---|---|---|
| First card, average colour over the card | `#5D4623` | `#835C38` | target `#8A6540` (10.4); each channel within 16 |
| Page height | 871 (scrolls 19px) | 852 (no scroll) | fits the screen |

- The tint is the accent amber (`#F7AE62` to `#EE8F3E`) at .50 to .40, dark theme only. Light is unchanged.
- The page keeps 56px under the blocks instead of 80, above 1200px wide, on Overview only.

## Checks run (dark, 1440x852 and 390x844)
- Layout shift on a cold load: 0. axe (wcag2a, wcag2aa, wcag21aa): no violations. No horizontal overflow, no page errors.
- Sampled contrast at 1440: worst 4.87:1 (the first card's 11px label, on the new tint); nothing under 4.5:1.
  At 390 the sampler again flags the two runs under the bottom tab bar (known artefacts, see `exact-r16`).

## Not run
- Light theme checks (its rules are untouched; the capture is here for the record). Motion and reduced-transparency captures.
- No 50% overlay: the block positions did not move.
