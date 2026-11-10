# Overview: round icons on the two count cards (dashboard-02)

The reference's two count cards open with a 34px round icon at the top left. Ours had none. Need attention and
Live requests now carry one; our label sits beside it (the reference has no label there, the Hub keeps its words).

## Checks run (1440x852 and 390x844, dark and light)
- Layout shift 0, axe no violations, no horizontal overflow, no page errors.
- At 1440 the cards did not move (x 767-1052 and 1064-1349, y 310-530). At 390 each card is 11px taller (132 to 143).
- Sampled contrast at 1440: worst 4.87:1 dark, 4.74:1 light.

## Still different
- The reference's wave line on the second card is not drawn. No 50% overlay was made.
