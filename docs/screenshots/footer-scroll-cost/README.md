# Footer scroll cost (fix/footer-scroll-cost)

The staff footer from #65 makes a desktop page 733px taller than the screen. Probe measured 26–39 fps scrolling
`/#/tools` at 1440×852 against the BRIEF §10.9 gate of 55; with the footer hidden the same page gave 52–55.
The room photo is not the cause.

## Result: no CSS change kept
Measured 10 November 2026, headless Chromium (software rendering), local fixture, `/#/tools` at 1440x852, a scripted
1.5s scroll down and up, variants interleaved in one session, laptop load 6 to 8. Frames per second per run:

| Variant | Scroll | Runs |
|---|---|---|
| main (base) | 733px | 31.3, 32.3, 32.6, 30.0, 34.0 · 32.2, 31.3, 28.9 |
| `contain: layout paint` on the footer + `will-change: transform` on the glass | 733px | 27.9, 31.6, 28.4, 29.0, 29.0 |
| footer `display: none` | **22px** | 53.0, 52.7, 56.0, 53.7, 56.0 |
| footer `visibility: hidden` (same height, nothing drawn) | 733px | 37.3, 36.4, 38.2 |
| glass fill removed | 733px | 36.6, 35.9, 36.9 |
| mask removed (no cut-out word) | 733px | 31.6, 32.1, 36.1 |
| plain background instead of the SVG glass | 733px | 28.2, 33.4, 36.1 |
| room photo removed | 733px | 34.5, 34.1, 37.3 |

- The candidate (own paint box + kept layer) was **not** an improvement, so it is not in this branch.
- "Footer hidden gives 52 to 55" is not a like-for-like control: with the footer gone the page scrolls 22px, so
  almost nothing moves. With the footer's height kept but nothing drawn, the same page gives 36 to 38.
- So drawing the footer costs about 5 fps here; the rest of the gap to 55 is the cost of scrolling this page 733px
  at all on this machine. No footer-only CSS change can reach the gate in this harness.
- Only removing the glass fill recovered those 5 fps, and that removes the footer's look. Not done.
- Not measured: a real GPU, a quiet machine, other pages, the fill animation.

## Tagged difference, BRIEF §10.1(4): footer panel width
The panel is x 173–1343 (1170 wide); the footer reference is x 30–1410 (1380 wide). The reference is a page of its
own with no rail; in the staff shell the footer sits in the content column beside the 143px rail, with the same
30px gutter the pages use. This is the layout exception of §10.1(4) and is unchanged by this branch (first recorded
in `docs/screenshots/exact-footer/README.md`).
