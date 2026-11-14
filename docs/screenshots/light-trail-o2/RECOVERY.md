# O2 interrupted-review recovery

These are before-fix fixture measurements from head `89e25eb`, recovered after
the reviewer process was interrupted. There is no completed reviewer verdict.
`recovered-before-contrast.json` preserves the measurements, not acceptance.
The area crumb measured 2.18:1 in desktop light and 3.12:1 in phone light;
phone dark area/separator measured 3.31:1. The nested `.crumb-area` colour
overrode the primary ink on the parent. The subsequent CSS correction assigns
primary ink to that crumb and to the phone separators in both themes.

The Spend focus capture also shows a clipped left edge of the trail link's
focus outline. That finding remains open for the resumed rendered review.
Fresh pixel contrast, keyboard focus and screenshots are required.
