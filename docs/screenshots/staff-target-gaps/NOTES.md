# Staff target gaps

Before data: independent fixture scan on product `992a07a` at 390/640 light/dark,
with unchanged staff code from main `9407c10`. The JSON is before-fix evidence,
not acceptance of this branch. The real misses are the Tools drawer controls
(36px), native Privacy summaries (23.3px at 640), page tabs (43.7px) and the
focused skip link (39.3px). Top bar, bottom nav and footer already reach 44px.

This branch gives these controls visible 44px targets below 641px. The drawer
and skip link sit outside `.staff-exact`, so their rules use the containing
body's signed-in-shell state. Native summaries retain their disclosure markers.

BRIEF 10.1.3 allows the accessibility difference. Desktop geometry is retained.
Fresh 390/640 light/dark and 1440 screenshots, focus/overlap checks and browser
verification are pending; no current-head acceptance is claimed.

## Independent review of cf5aa20

390/640 light/dark PASS: drawer Close icon 44×44, footer Close 62.3×44, Open
86.6×44; page tabs at least 44px tall; six Privacy summaries 44px; focused
skip link 139.1×44. No sideways clipping or pairwise overlap in changed groups.
Keyboard focus stays in the drawer, Escape returns it to the row, disclosures
activate with click/Enter, and the skip link focuses main. Drawer close was
rechecked three times: it completes by 1.3s on the slow laptop. Desktop 1440
light/dark retains its prior dimensions.

The committed staff-phone.cjs printed 156 checks passed; the 280s shell timeout
then returned exit 124 during shutdown. No assertion failed, but this is not an
exit-zero suite result. Full CI remains required. No local process remains.
Actual captures and JSON: head-cf5aa20/. Not run: full local Python suite or a
real device. The shared AGENT-PROGRESS checkpoint is carried by #231 to avoid
competing appended logs; this PR keeps its own detailed review evidence here.
