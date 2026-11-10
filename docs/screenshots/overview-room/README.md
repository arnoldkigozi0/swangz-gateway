# Overview: the room is the ground (architect review item 1, Nov 10)

Dark, 1201px and wider, Overview only. The page-wide backing plane is gone, the "AI usage" and "Uses by tool" panels are
glass over the room (one blur, glass rim, radius 22, no header band, no header divider).

## Sample points at 1440×852 against `stills/dashboard-02.jpg` (7×7 average, target ±16 per channel)

| Point | Reference | Before | Now | Difference | Within ±16 |
|---|---|---|---|---|---|
| KPI gap (464,220) | 102,85,71 | 37,30,24 | 81,59,39 | −21,−26,−32 | no |
| Chart panel (300,420) | 106,89,81 | 20,20,23 | 97,80,73 | −9,−9,−8 | yes |
| Below panels (700,810) | 119,105,98 | 27,23,19 | 24,16,9 | −95,−89,−89 | no |

Two of three points are not met. Both are bare room, so what they read is the photo itself under the .35 scrim:
`room-warm.webp` is more orange than the reference room at the first point and is a dark sofa at the third, where the
reference has a pale floor. No scrim inside the brief's .30 to .40 range moves 24,16,9 to 119,105,98; that needs a
different photo or crop, which is not in this change.

The panel tint is `rgba(129,117,120,.60)`, not `--glass-bg`: with `--glass-bg` the chart point read 49,35,22.

## Text contrast (sampled from the capture, every text run)

- Dark 1440: worst 4.66:1 (axis label "5"), no run under 4.5:1. Muted text and axis labels are lifted on this page to
  hold that; the amber card keeps its #92 colour (average `#835D38`) with a dark layer under its tint.
- Light 1440: unchanged, worst 4.74:1. Light keeps the plane: no reference still, bare text over the room unmeasured.
- axe: no violations in the four cells (1440 and 390, dark and light). Layout shift 0, no horizontal overflow.

## Not done

- Other console pages still have the plane.
- Phones and 1200px and below still have the plane in dark.
- Reduced transparency falls back to the opaque panel; not captured.
