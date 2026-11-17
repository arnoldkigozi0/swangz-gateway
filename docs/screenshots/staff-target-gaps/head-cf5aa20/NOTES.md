# Probe notes — PR #234, head cf5aa20d3111ec879c1b159bdda36ff25ef03f6b (2026-11-14)
Synthetic local demo (HUB_STAFF_PHONE_FIXTURE), Chrome, one browser at a time. No reference overlay (touch targets, not a reference screen).
## Result: PASS (390/640, light+dark); desktop 1440 unchanged
- Committed tests/browser/staff-phone.cjs: "staff phone: 156 checks passed", all assertions green. The shell's `timeout 280` then reported exit 124 (the five-cell run is slow on this laptop; the pass line prints at the very end). Not a failed check. See staff-phone-run.txt.
- Re-measure (o13, targets-cf5aa20.json), 390 and 640, light and dark:
  - Tools drawer: top Close 44x44, footer Close 62.3x44, Open <tool> 86.6x44.
  - Page tabs Requests (4), Devices (2), Weekly (3): all min height 44 (Weekly 390 wraps to 65.4); width >= 157. No sideways scroll.
  - Privacy summaries (6, including "Weekly reporting and your declarations"): 44 tall. Click opens and closes (and Enter, per suite). Not covered by the fixed nav after scrollIntoView.
  - Skip link focused: 139.1x44, 2px outline, fully on screen at top 12; Enter moves focus into main.
  - Top bar/bottom nav (8 controls): all >= 44. Pairwise overlaps in all changed groups and bars: none.
  - Drawer focus: Tab stays in the drawer; focus ring 2px solid (dark rgb(229,190,120), light rgb(120,86,15)); Escape closes it (the exit animation takes ~1s: 1 element at 300ms, 0 at 1.3s, repeated 3x at light 390) and focus returns to the opener row.
- Desktop 1440 light/dark: unchanged by design (drawer buttons 36, tabs 42, top bar 36-38, skip link 39.3, Privacy summaries 20-23). Not a phone-scope miss.
Not run: full Python suite, real device.
