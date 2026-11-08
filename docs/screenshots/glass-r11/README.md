# R11 liquid glass staff footer

Reference: `docs/design/BRIEF.md` §6–7, stills `footer-01`, `footer-03`, `footer-06`.
Shots: `footer-{dark,light}-{1440x900,390x844}.png`, `footer-reveal-mid-dark-1440x900.png` (about 230 ms into the reveal).
Regenerate: `node docs/screenshots/glass-r11/check.cjs` (needs Playwright and Chrome; starts `tests/browser/demo.py`). Results in `results.json`.

Real data only: health is the public `/healthz` (cached 60 s), "Ask" reuses the existing request dialog (`POST /tools/{id}/request`), links are existing routes.

## Differences still left versus the reference
- The panel's top edge settles straight; the reference keeps a wavy liquid edge. The reveal wave was removed with the panel animation (below).
- (Superseded by the last correction below: the letters show the scene photo again, placed by layout.) In dark theme the wordmark was the fixed scene lifted by a warm light layer, so "Swa" reads as soft grey while "ngz" shows more of the photo; the reference letters are brighter still. The rim is a drop-shadow, not a text stroke (a stroke drew the variable font's overlapping inner contours).
- The "g" descender runs into the panel's bottom edge on purpose (cut-off wordmark); the reference shows the full letter.
- Light theme panel is a flatter cream than the reference's frosted white; the panel is a layered translucent gradient with no backdrop blur (see below), so it is flatter than frosted glass.
- Gateway status has three wordings (running; up with the database not responding; not answering). No other health data is available to show.

## Corrections after Probe's review of 172c77a (portal.css, portal.js, this folder only)
Reveal jank, measured with `/tmp`-style frame sampler (140 requestAnimationFrame frames while the footer scrolls into view, 1440x900, headless Chrome with **software rendering**, so absolute numbers are pessimistic; same script for every row):
| Variant | Frames over 50 ms (per run) | Worst frame |
|---|---|---|
| 172c77a (blur panel, animated panel) | 6 to 9 | 300 to 880 ms |
| Panel kept static, content-only reveal, blur kept | 6 to 9 (no gain) | 350 to 880 ms |
| Same, backdrop blur off (isolated by an injected rule) | 1 to 8 (noisy) | 67 to 200 ms |
| **This head: no backdrop blur, content-only reveal** | **1 to 4** | **117 to 183 ms** |
| This head with the wordmark hidden (experiment only) | 1 | 67 to 117 ms |

Findings: the live backdrop blur was the main cost (a blur radius of 8 px cost the same as 22 px, so it is the layer, not its size); moving the panel was not. The remaining stalls come from the wordmark, a 300px text clip painted from a fixed full-size photo. Trying a separate layer and a non-fixed background did not help. Main (no footer) is 0 to 1 over 50 ms, so **this is better but not at parity**; the wordmark is the next step and I stopped there rather than flatten the reference's signature element. On a machine with a GPU the original blur may be fine; I could not measure one.
- Panel: layered gradient instead of backdrop blur; still reads as milky glass (screenshots). The panel no longer moves or fades; only the content rises and fades in (opacity and transform), the wordmark fades in place. The wave crest is removed.
- Reduced motion: hover lift off as well (checked). Reveal is not armed at all when reduced motion is requested at load.
- Controls hidden before the reveal: focusing any footer control reveals the footer at once (checked), so nothing focusable stays invisible.
- Footer link targets 40px (44px on coarse pointers); were 32px.
- Ask field border: white at .42 on dark, brown at .6 on light, so the field edge shows. Not measured numerically (estimated above 3:1 from the panel colours).
- `/healthz` 503 with a body now reads "Gateway up, database not responding" (checked with a mocked 503); unreachable stays "Gateway not answering".
- Typing a tool that does not exist keeps the message on the footer with a "Search every tool for it" link instead of jumping to Tools and losing the message (checked).

## Correction after Probe's exact-head review (performance BLOCKED)
- **Removed the wordmark's repaint layer.** `.gf-word` was the scene photo (`cover fixed`) clipped to 300px letters with a `drop-shadow` filter: a fixed background repaints on every scroll step and the filter adds a layer. It is now one translucent gradient clipped to the letters (`background-clip: text`), with no photo, no fixed attachment and no filter. Kept: the cut-off "Swangz" letters at the panel's foot, the milky panel, the reveal (content rises, wordmark fades in place). Dropped: the photo showing through the letters and the 1px light rim, which needed the filter. The wordmark stays decorative (`aria-hidden`).
- `check.cjs` now asserts the wordmark has no text stroke, no filter, no fixed attachment and no image (`url()`), in both themes and sizes. Screenshots regenerated on the head merged with current main.
- **Trace** (`perf.cjs`, same page and harness, `OLDWORD=1` puts the previous wordmark back with an injected rule): 1440x900, headless Chrome `--disable-gpu` (software render), 4 runs; each loads Tools, scrolls to the footer in 24 steps and records `requestAnimationFrame` intervals until 1.6 s after arrival.

| Theme | Old wordmark: p95 per run | Gradient wordmark: p95 per run | Frames over 50 ms, old | now |
|---|---|---|---|---|
| dark | 100, 83, 83, 83 ms | 67, 67, 67, 67 ms | 10, 9, 7, 7 | 10, 11, 9, 6 |
| light | 83, 83, 67, 67 ms | 83, 67, 83, 67 ms | 11, 11, 10, 10 | 11, 10, 10, 9 |

Honest reading: dark shows a modest, repeatable gain in p95 and worst frame (max 117-183 ms before, 83-100 ms now); the count of slow frames and the light theme are within noise. **I do not claim parity with main.** Not run: a same-harness main baseline (main has no footer), a real GPU, a Chrome performance-trace file. The scroll loop is driven through Playwright, so some of the slow frames are harness overhead. The earlier experiment with the wordmark hidden (67-117 ms) suggests the remaining cost is the page, not the wordmark.

## Correction after Probe's Medium finding on the flat wordmark (scene through the letters, no repaint cost)
Probe measured the flat-gradient letters at about 1.76:1 (dark) and 1.2:1 (light) against the panel, and the reference (`footer-03`) shows the letters as clear windows onto the sharp scene behind the frosted panel.
- **Letters show the scene photo again, without a fixed background or a filter.** `.gf-word` paints the same `--scene-image` through the letters (`background-clip: text`, normal scroll-attached background, painted once and moved by the compositor). `wordmarkScene()` in `portal.js` sets four custom properties (`--gf-bw/-bh/-bx/-by`: the photo's cover size and offset) so the photo lines up with the fixed scene where the footer comes to rest at the bottom of the page. It runs on load, on window resize and when the body resizes, never on scroll. Until the image size is known (or if it fails) the flat gradient from the previous correction is the fallback. A light "lift" layer (`--gf-lift`) sits over the photo so the letters read as bright frosted windows in dark and as deep ones in light.
- Honest limit: the scene photo is fixed to the viewport, the letters scroll. They line up when the footer is at rest (page scrolled to the end, which is where it is seen); while the page is still scrolling the photo in the letters is a fixed picture inside moving letters, not the scene behind them. The page is not re-measured on scroll on purpose.
- **Contrast, measured** (screenshot with and without the wordmark; luminance of the letters against the panel around them, WCAG ratio, left third "Swa" and right two thirds "ngz"):

| Theme / size | Swa | ngz |
|---|---|---|
| dark 1440x900 | 3.7 | 4.9 |
| dark 390x844 | 3.7 | 4.6 |
| light 1440x900 | 10.7 | 8.1 |
| light 390x844 | 8.1 | 6.8 |

  The wordmark is decorative (`aria-hidden`), so 3:1 is a target, not a requirement; it is met in all four.
- `check.cjs`: the wordmark has no text stroke, no filter, no fixed attachment, a `url()` image clipped to text once `gf-photo` is set, and its offsets do not change while scrolling (both themes, both sizes).

### Same-distance trace, branch versus main
Earlier traces compared scroll distances of 845 px (branch) and 256 px (main); that comparison is withdrawn. Now every arm scrolls exactly 845 px: `DISTANCE=845` adds a spacer above main's plain footer so main's page is as long, then the same 24 steps 30 ms apart and 1.6 s of rest. `perf.cjs`, 1440x900, dark, headless Chrome `--disable-gpu` (software render, one weak laptop, other work running), rounds interleaved, 4 runs per arm per round. Frames over 50 ms per run:

| Arm | Runs | Mean | Range |
|---|---|---|---|
| main (plain footer, no reveal) | 16 | 8.2 | 2 to 11 |
| this branch | 16 | 10.3 | 5 to 14 |
| branch, reveal switched off by injected CSS | 8 | 8.0 | 4 to 11 |
| branch, flat-gradient wordmark by injected CSS | 8 | 10.1 | 9 to 12 |
| branch, previous fixed-photo wordmark with filter | 8 | 10.4 | 7 to 14 |

Reading: the arms overlap a lot and the p95 swings from 50 to 180 ms between rounds even on main, so this is noise-limited. What it supports: the photo in the letters costs nothing measurable over the flat gradient (10.3 against 10.1); the branch is about two slow frames per run above main, and that gap closes when the reveal is switched off (8.0 against 8.2), so the extra frames belong to the reveal animation main does not have (opacity and transform only). It does not show the old wordmark was worse, so the earlier "gain" claim is also not repeated here. **No parity with main is claimed.** Not run: a real GPU, a Chrome performance-trace file, light theme (not repeated), a reveal-free variant on a device. Reproduce: `DISTANCE=845 node docs/screenshots/glass-r11/perf.cjs`, `ROOT=<main checkout> DISTANCE=845 ...`, `EXTRACSS='...'`, `OLDWORD=1`.

## Raster correction: the wordmark gets its own layer (`will-change: opacity` while armed)
Probe's remaining finding: dark slow frames 11.2 against main 6.3, light 11.3 against 11, with raster time 500-1014 ms against main's 9-21 ms and hiding the wordmark taking it to 236-315 ms. Tried, one at a time, as injected CSS on the same page (`EXTRACSS`), every arm scrolling exactly 860 px (`DISTANCE=860`: the branch page is now 847 px long, so all arms, main included, are padded to the same distance), 3 runs per arm per round, arms interleaved, headless Chrome `--disable-gpu`. Raw runs are saved in `trace-variants.ndjson` (every arm) and `trace-final.ndjson` (the shipped head against main); summarise with the per-run fields `over50`, `p95`, `max`, `taskMs` (main-thread task time over the run, from CDP `Performance.getMetrics`).

| Arm (mean per run) | Dark: slow frames / p95 / task ms | Light: slow frames / p95 / task ms |
|---|---|---|
| branch before this change | 9.5 / 72 / 263 (n=15) | 8.7 / 80 / 268 (n=9) |
| `.gf-word { will-change: opacity }` (kept) | 6.5 / 61 / 229 (n=15) | 7.8 / 63 / 240 (n=9) |
| `.gf-word { contain: paint }` | 6.3 / 59 / 248 (n=15) | 7.4 / 65 / 242 (n=9) |
| both together | 8.2 / 69 / 268 (n=6, dark only) | not run |
| `.glass-foot { content-visibility: auto }` | 10.0 / 83 / 333 (n=3; a second run failed the equal-distance guard because the height changes) | not run |
| main (plain footer, no reveal) | 5.4 / 54 / 145 (n=9) | 4.6 / 54 / 123 (n=9) |

Shipped head, final interleaved trace (`trace-final.ndjson`, n=6 per cell): dark 6.5 slow frames, p95 64, task 229 ms against main 4.3, 56, 134; light 6.7, 56, 221 against main 4.5, 56, 123.

Decision: keep `will-change: opacity` on the armed wordmark only (so reduced motion, which never arms, gets no layer): the clipped photo is rasterised once and the 900 ms fade runs on the compositor. It cuts slow frames by about a third in dark and about one in ten in light, with no clipping risk. `contain: paint` measured the same but clips ink that overflows the box (the "g" descender and the first and last letters' side bearings), so it is not shipped. `content-visibility: auto` is not shipped: no gain, and it moves the page height (a CLS risk). Both together were no better than either.

Honest reading: **still not at parity with main.** Main-thread task time is about 1.7 times main's and about two extra slow frames per run remain in both themes; those are the footer's own painting (the milky panel gradients, the clipped photo and the reveal), which main does not have. Software render, noisy (n = 6 to 15 per cell), not a GPU: I make no GPU claim and no waiver claim. I did not get a Chrome trace file or separate raster-thread numbers; `taskMs` is main-thread only.

Checks on this head (`check.cjs`, exit 0, both themes at 1440x900 and 390x844): no clipping or CLS (CLS 0), the existing focus reveal, a new real-keyboard Tab into the footer (revealed, opacity 1, on screen), axe wcag2a/aa on the settled footer (no violations), reduced motion (reveal not armed, footer opaque, hover lift off), the four theme/size cells for the wordmark assertions and no console errors.
