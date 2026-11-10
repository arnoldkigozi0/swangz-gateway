# Overview: Uses by tool as a donut (BRIEF 10.7, dashboard-02)

The reference's third block is a ring with the total in the middle and a legend at its right. Uses by tool was a
ranked bar list; it is now `SUI.donut`. The panel stays where it was (x 767-1349, y 542-792; 791 before).

- The ring's shares are of the true 30-day total (requests + opens + visits from the daily series). Up to five tools
  are named; anything they do not account for is one muted arc named "Other tools". Nothing is padded.
- The legend carries every name and count as text, in the ring's order clockwise from the top, and each name still
  opens the tool. The ring itself is hidden from screen readers.
- With no use at all the panel keeps its existing empty state.

## Checks run (1440x852 and 390x844, dark and light)
- Layout shift on a cold load: 0 in the four cells. axe (wcag2a, wcag2aa, wcag21aa): no violations.
  No horizontal overflow, no page errors. The page still fits 1440x852 without scrolling.
- Sampled text contrast at 1440: worst 4.87:1 dark, 4.74:1 light; nothing under 4.5:1. At 390 the sampler flags the
  same two runs under the bottom tab bar as before (known artefacts, see `exact-r16`).

## Still different, or not checked
- The demo data has three tools and five uses; the reference shows five segments. Not padded (10.9.2).
- Segment colours are read from the still by eye, not sampled channel by channel.
- In light the yellow arc on the white panel is likely under 3:1 against its background (not measured). The count
  is in the legend as text, so no information depends on it, but it is a known weak point.
- No 50% overlay was made. Motion, reduced-transparency and the 4x CPU trace were not run.

## Follow-up (architect review, Nov 10)

- `overlay-50-dashboard-02-dark.png`: this page at 1440×852 dark blended 50% with `stills/dashboard-02.jpg`. The ring
  sits on the reference ring; the legend is centred on the ring and its rows are at the reference's 29px pitch.
- The fixture has three tools with uses, so three legend rows are drawn. Up to five are named when the data has five
  (`donutParts`, tested); rows are never invented to fill the legend.
- Light theme: the reference arcs were under 3:1 on porcelain `#FCF8F2` (yellow 1.44, green 1.96, blue 2.20, orange
  2.62; pink 3.07). Light now uses darker arcs of the same hues, computed against `#FCF8F2`: orange `#DB5F1F` 3.50,
  blue `#1C8FCF` 3.38, yellow `#A88200` 3.39, pink `#E0456A` 3.80, green `#1A9A62` 3.40, other `#8A8378` about 3.5.
  A test holds each at 3:1 or more. These are computed ratios on the flat panel colour, not sampled from a capture.
- Dark colours are unchanged and were read from the still by eye.
