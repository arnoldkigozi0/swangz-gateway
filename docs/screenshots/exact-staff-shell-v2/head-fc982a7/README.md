# Staff shell at product head fc982a7 (10 November 2026, 09:45 Kampala) — desktop scroll

Builder's measurements, not an acceptance. Only the room behind the shell changed since f10a78a; that folder's
screenshots, overlays, tagged differences and "not run" list still apply except as stated here.

## Change
Above 900px the fixed full-screen photo layer is gone. The room is painted on the page itself: sized to cover the
viewport, so at the top of a page it is the same picture in the same place (Requests 1440x852 dark, photo area:
at most 9 per channel from f10a78a); `room-warm-tile.webp` (the approved photo followed by its mirror image)
continues it without a seam on pages that scroll; it is drawn with nearest-neighbour sampling. Phones are unchanged.

- **10.1(3), new:** on desktop the room moves with the page instead of staying put as in the reference, and on a
  page longer than one screen the mirrored room appears below the first screen.
- 10.1(2)/(3): `room-warm-tile.webp` is derived from `room-warm.webp` only (docs/design/ASSETS.md).

## Desktop Tools scroll, Probe's `perf.cjs` method, 1440x852 (gate: 55fps, no frame over 50ms)
The laptop's load average was 6–8.5 from other sessions for every run, so no run here is a clean reading.
- Five runs (dark / light fps): 55.7/54.6, 40.3/42.6, 54.0/50.1, 57.7/54.0, 56.0/50.4. Raw: `scroll-5-runs-and-captures.log`.
- Six further runs interleaved with a no-photo control under the same load: this head averaged **53.1fps** (46.2–56.4),
  the page with no photo at all **54.4fps** (48.1–57.0). f10a78a's fixed layer measured 39–48 against the same control.
- So the photo now costs about 1fps where it cost about 12, but **the gate was not met on this machine during these
  runs: not even the no-photo page held 55.** It needs Probe's re-run in the quieter slot where no-photo read 58–59.7.
- One 20-cell run: the 18 non-desktop-Tools cells 59–60fps (one 50ms frame on 390 Projects dark); desktop Tools 43.2 / 43.5 in that run.

## Still true on this head
axe 0 and CLS 0 with no layout-shift entries in all 20 cells and five cold loads; text contrast over the real photo
worst 6.57:1 dark, 4.99:1 light (unchanged; text sits on panels). Brightest-point contrast was not re-run on desktop
(the harness swaps `room-warm.webp`, not the tile). Reduced-transparency: flat scene, no photo.
Checks: `staff-font.cjs` 30 cells OK, `exact-staff-shell.cjs` exit 0, model 18 PASS, `syntax.py` 29 files, 56 Python tests OK.

## Noted by Probe, not changed
The Tools panel runs to y 842 at 1440x852 (the page is 874px tall, so it scrolls 22px). Minor; 10.1(1)/(4) content length.
