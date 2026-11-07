# R11 liquid glass staff footer

Reference: `docs/design/BRIEF.md` §6–7, stills `footer-01`, `footer-03`, `footer-06`.
Shots: `footer-{dark,light}-{1440x900,390x844}.png`, `footer-reveal-mid-dark-1440x900.png` (about 230 ms into the reveal).
Regenerate: `node docs/screenshots/glass-r11/check.cjs` (needs Playwright and Chrome; starts `tests/browser/demo.py`). Results in `results.json`.

Real data only: health is the public `/healthz` (cached 60 s), "Ask" reuses the existing request dialog (`POST /tools/{id}/request`), links are existing routes.

## Differences still left versus the reference
- The panel's top edge settles straight; the reference keeps a wavy liquid edge. The wave (`.gf-crest`) is visible only during the reveal.
- Wordmark letters over the dark part of the scene ("Swa" in dark theme) show the photo at low brightness, so they read faint. The cut-out follows the fixed scene, not a brighter picture.
- The "g" descender runs into the panel's bottom edge on purpose (cut-off wordmark); the reference shows the full letter.
- Light theme panel is a flatter cream than the reference's frosted white; there is only one blur layer by design.
- `background-attachment: fixed` is ignored on iOS Safari, so the cut-out falls back to the scene scaled to the wordmark box.
- No "Gateway status" detail beyond running / not answering: no other health data is available to show.
