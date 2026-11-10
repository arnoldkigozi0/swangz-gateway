# exact-footer — the staff app's liquid glass footer (feature/exact-footer)

Reference: `docs/design/references/stills/footer-04.jpg` (settled) and `footer-01…03` (the fill), video
`liquid-glass-footer.mp4`. BRIEF §6 and the Footer row of §10.3. Builder's captures, not an acceptance.
Playwright's bundled Chromium, headless, local synthetic fixture (`tests/browser/demo.py`), Poppins latched.

## Files
- `footer-1440x852-{dark,light}.png`, `footer-390x844-{dark,light}.png`: Tools scrolled to the end.
- `overlay-footer-1440x852-dark.png`: 50% blend with `footer-04.jpg`, **panel top-left corners aligned** (the still is
  1440×760 with the panel at x30/y125; ours is at x173/y165, so the capture is shifted by −143/−40).
  `beside-footer-1440x852-dark.png`: the still above ours.
- `footer-reduced-motion-…png`, `footer-reduced-transparency-…png` (solid `#EBDCCD` glass, flat scene),
  `footer-w1024-1024x768-dark.png` (one column from 1250px down).
- `results.json`: geometry, axe and layout-shift entries for nine cells. `scroll-footer-vs-22px-control.log`: see Scroll.

## Measured at 1440×852, panel-relative (footer-04 in brackets)
- Lead inset 37 [37]; brand mark 36px, top 38 [≈ 32]; heading 32px/600, two lines, box top 92 [ink ≈ 97].
- Ask pill 380×46 at y 185 [380×46, y 183]; dark button inside; note under it.
- Link card: top 32 [32], right inset 35 [35], height 221 [221], radius 20; 4 columns, 12px headings, 14px links, 28px rows.
- Bottom row centre y 309 [309]: © · status dot + word · icon pill group (38 tall) · Evening switch 46×26 at the right inset.
- Panel radius 28, 1px light rim.

## Remaining differences, each tagged with its BRIEF §10.1 number
- **10.1(4):** the panel is x 173–1343 (1170 wide), not x 30–1410 (1380). The footer reference is a page of its own; the
  staff app has the fixed rail at x 67–129 and its content column at 173–1343, and a panel at x 30 would run under the
  rail. Insets, the 380px pill and the card's top/right/height are kept, so the card is 662 wide (reference 785).
- **10.1(3):** glass is `rgba(235,220,205,.86)`, reference `.55`. The staff shell has no live blur (scroll performance,
  #56), and near-black text over the unblurred room needs the opacity. Calculated bounds with black / white / the
  photo's brightest pixel behind the glass: ink 9.41 / 13.43 / 11.41, muted 5.56 / 7.93 / 6.74, on the card 11.45 and
  6.76 at worst, icon-pill icons 6.80, placeholder 7.43. Non-text: status dot `#0A6B38` ≥ 3:1 (always with its word);
  the Daylight (off) switch track is 3.36:1 at worst. These are calculations from declared colours, not pixel samples.
- **10.1(3):** no backdrop blur and no refraction in the letters: they are true holes onto the room.
- **10.1(1):** our words and links; the "S" mark; "Swangz" for the wordmark. "Swangz" has a descender, so the word sits
  higher than "Vertix" to keep the whole "g" inside the panel, and it is sized to span the panel (font 280px, capital
  height ≈ 196px; reference ≈ 240px on a panel 210px wider). The panel is 655 tall (reference 615).
- **10.1(1)/(4):** "Ask for a tool" instead of the newsletter: it opens the existing access-request dialog and sends
  nothing until the person confirms. With nothing left to ask for it is a link to Access requests. The status word is
  the real `/healthz` answer ("Gateway running", "Gateway up, database not responding", "Gateway not answering"),
  never a fixed "All systems normal". The icon group links to Updates, My tools, Weekly reports and Privacy (no
  social accounts). No "Hiring" chip.
- **10.1(3):** one look in both themes (the reference has one); the switch says Evening / Daylight and is a real
  `role="switch"`. Phones (no still): the footer stacks, link rows are 44px, the card is two columns, the word scales.
- **10.1(3):** reduced motion shows the footer at once with no fill; reduced transparency makes the glass solid.
- **Motion, not accepted against ±2 frames:** read from a 30fps contact sheet of the video (thumbnails): the glass rises
  with a wavy edge over ≈ 18 frames (ours 600ms), the edge settles by ≈ frame 30 (ours 1000ms), the words fade in from
  ≈ frame 20 (ours 650ms + 500ms). The wave's exact curve and the cursor ripple in footer-04 are not reproduced.
- **10.1(5), not in this PR:** the §10.9 liquid "S" loader and amber pulse. Sign-in does not get the footer here.

## Gates (§10.9.4)
- **axe** (wcag2a/2aa/21aa) on the footer: 0 violations in nine cells (1440, 1280, 1024, 768, 390; both themes at 1440 and 390).
- **CLS:** zero layout-shift entries in all nine cells and in `staff-font.cjs` (30 cold-load cells). `main` now has a
  minimum height of one screen less the top bar, so the footer always starts below the first screen (882 at 852 tall).
- **Scroll: the 55fps gate is NOT met on this laptop, and was not cleanly measurable** (load average 7.3–8.6 from other
  sessions throughout). The footer makes desktop Tools scroll 738px instead of 22px. Three runs each, 1440×852 dark,
  same page length: with the footer 30.2–32.2fps, footer present but `visibility: hidden` 34.2–36.2, without the word
  mask 30.1–35.4, without the reveal 34.1–36.3, with no room photo 32.6–35.1. So the long Tools page itself scrolls
  at about 35fps under this load and the footer costs about 3fps of it. Phone (390×844): 55.4–58.8fps with the footer,
  one or two frames over 50ms. In `scroll-footer-vs-22px-control.log` the "no-footer" rows scroll only 22px, so they
  are not a like-for-like control. Needs a run on an idle machine.
- **Fallbacks:** the two shots above. **Low data:** the footer shows no numbers; its one data-dependent state (nothing to
  ask for) is the link variant.

## Not run
Colour samples against the still, pixel-sampled contrast, frame-stepped motion, an idle or 4×-throttled trace,
430px, Firefox/Safari (the wordmark uses an SVG mask inside one SVG, no CSS mask), a screen reader.

## Checks
`tests/browser/exact-footer.cjs`: 7 cells PASS (geometry, reveal and reduced motion, health word, ask flow opens the
dialog and sends nothing, switch, touch heights, no overflow, no shift, focus reveal). `staff-font.cjs` 30 cells OK,
`exact-staff-shell.cjs` exit 0, shell model PASS, `syntax.py` 35 files. Full Python and browser suites: CI.
