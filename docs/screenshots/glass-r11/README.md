# R11 liquid glass staff footer

Reference: `docs/design/BRIEF.md` §6–7, stills `footer-01`, `footer-03`, `footer-06`.
Shots: `footer-{dark,light}-{1440x900,390x844}.png`, `footer-reveal-mid-dark-1440x900.png` (about 230 ms into the reveal).
Regenerate: `node docs/screenshots/glass-r11/check.cjs` (needs Playwright and Chrome; starts `tests/browser/demo.py`). Results in `results.json`.

Real data only: health is the public `/healthz` (cached 60 s), "Ask" reuses the existing request dialog (`POST /tools/{id}/request`), links are existing routes.

## Differences still left versus the reference
- The panel's top edge settles straight; the reference keeps a wavy liquid edge. The reveal wave was removed with the panel animation (below).
- (Superseded by the corrections below: the wordmark is now a plain clipped gradient.) In dark theme the wordmark was the fixed scene lifted by a warm light layer, so "Swa" reads as soft grey while "ngz" shows more of the photo; the reference letters are brighter still. The rim is a drop-shadow, not a text stroke (a stroke drew the variable font's overlapping inner contours).
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
