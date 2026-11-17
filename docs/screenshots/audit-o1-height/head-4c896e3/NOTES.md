# Probe notes — PR #233, head 4c896e306a7ac81bc991b5b348e9a9b4cb395ce3 (2026-11-14)
Synthetic local demo (tests/browser/demo.py, HUB_UI_FIXTURE=1), Chrome, 1440x852. No reference overlay: Audit has no reference still (BRIEF 10.1 reason: not in the reference videos). ../before.json is incomplete-review "before" data, not acceptance evidence.

Result: FAIL (one defect). Shipped tests/browser/audit.cjs fails at this head locally (audit-cjs-run.txt) and in CI (browser job, run 43555999840): "dark 1440: and the page itself does not scroll" (view simple).

Measured (o1-results.json, o1-pager-results.json):
- Detailed: panel bottom 732, footer 756, page overflow 0 — OK, unchanged.
- Simple, no pager yet (first 10 rows or fewer): panel bottom 742, overflow 0 — OK.
- Simple, with the 54px pager under the table (any log with more than one page): wrap 462 + pager 54, panel bottom 796, footer top 820, page overflow 24px => the page scrolls. Expected 796 was met but the footer is pushed below 852.
- Capping the wrap at 438/432/400px inline changed nothing: the wrap is content-sized at 462 (10 rows), so the 462px max-height is not what binds; the pager is outside the wrap.
- 390 and 640: no sideways overflow; wrap max-height none. Models cap not re-run here (352 measured earlier on #188).
Fix direction (owner): reserve the pager's 54px (and the 24px) in the Audit max-height calc, or make the wrap max-height 100dvh - (chrome + pager).
Staff touch targets (staff-phone.cjs, 390 dark/light + 1440): 52 checks passed; 640 dark/light copy: 36 passed (staff640.txt).
