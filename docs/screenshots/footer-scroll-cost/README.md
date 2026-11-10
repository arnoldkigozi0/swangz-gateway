# Footer scroll cost (fix/footer-scroll-cost)

The staff footer from #65 makes a desktop page 733px taller than the screen. Probe measured 26–39 fps scrolling
`/#/tools` at 1440×852 against the BRIEF §10.9 gate of 55; with the footer hidden the same page gave 52–55.
The room photo is not the cause.

## The change (staff footer CSS only, 901px and wider)
- `.xfoot { contain: layout paint }` — the footer paints as a box of its own.
- `.xf-fill { will-change: transform }` — the glass (one SVG rect behind a mask that cuts out the 240px word) is
  drawn once and kept, so scrolling moves a finished picture.

No colour, size or position changes. Phones are untouched.

## Measurement
**Not measured yet.** The change is kept only if five interleaved A/B runs (Probe's `/tmp/probe-main-ev/ab*.cjs`,
same page, base against this branch against no footer) show an improvement. Results go here.

## Tagged difference, BRIEF §10.1(4): footer panel width
The panel is x 173–1343 (1170 wide); the footer reference is x 30–1410 (1380 wide). The reference is a page of its
own with no rail; in the staff shell the footer sits in the content column beside the 143px rail, with the same
30px gutter the pages use. This is the layout exception of §10.1(4) and is unchanged by this branch (first recorded
in `docs/screenshots/exact-footer/README.md`).
