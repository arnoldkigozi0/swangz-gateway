# Probe notes — PR #231, head 9acb44241ee284cab281bcf3e31d4190ca78a089 (2026-11-14)
Synthetic local demo (HUB_UI_FIXTURE=1), Chrome. Method: hide the text, screenshot under each crumb part, WCAG contrast of worst/mean pixel vs text colour. No reference overlay (BRIEF 10.1: trail not in the reference videos).
Result: PASS on measurements.
- 1440 desktop trail (.console-trail): light Money 5.75, separator 5.89, current page 4.74 (worst pixel; mean ~6.2); dark Money 9.36, separator 4.76, current 6.23. Spend/Licences trails >= 4.74 both themes. No backing: transparent, shadow none, ancestors transparent; not clipped.
- 390 and 640 (.top .crumbs.in-bar, the trail is hidden <=1200): all parts >= 7.5 light and dark (one "1" dark reading is a measurement artifact; the 4x crop shows a uniform dark background).
- Focus on the "..." link: light 2px #78560F inset, dark 3px #F6F6F4; whole outline inside the 38px trail box.
- Full current-page trail shown; links clickable (o2/o3/o4-results-head.json).
- Nit: the "..." link is 23.9px wide (WCAG 2.5.8 wants 24).
Settings header icon "nick": cannot reproduce — 7 icons x 2 themes all 42x42 badge, 20px SVG at 11,11, not clipped (o6-settings-icons.json).
Not run: CI (Python/browser IN_PROGRESS at check time), full Python suite.
