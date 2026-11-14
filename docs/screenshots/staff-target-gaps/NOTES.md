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
