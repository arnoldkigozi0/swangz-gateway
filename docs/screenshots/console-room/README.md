# Console pages: local backing instead of the page-wide plane (architect review item 1, Nov 10)

**Not captured in a browser yet.** This was written while another check held the one browser slot. Everything below is
computed from the room photo and the colour tokens; nothing here was sampled from a screenshot, and no page was looked
at. It must be measured before it is treated as done.

## What changes (every console page except Overview, all widths)

- The plane behind the whole page is gone. The page header keeps a backing of the same colour, and so does each block
  of the page that is not a card. Blocks that have their own surface keep it.
- Dark: panels are smoked glass (`--glass-bg-strong`, one blur, glass rim). A panel inside a panel stays opaque.
- Light: panels stay opaque white. Overview on phones and in light still has the plane.

## Computed contrast, worst case

The room photo blurred at 22px has its brightest point at 155,115,75 and its darkest at 29,17,10 (the `saturate(140%)`
in `--glass-blur` is not modelled).

| Ground | Colour there | tx-1 | tx-2 | tx-3 | accent | ok | info | warn | bad |
|---|---|---|---|---|---|---|---|---|---|
| Dark smoked glass .68 over the brightest room | 49,38,28 | 13.65 | 8.75 | 6.67 | 8.87 | 8.10 | 6.68 | 7.99 | 4.88 |
| Dark backing .82 (as the plane was) | 42,34,27 | 14.48 | 9.28 | 7.08 | 9.41 | 8.59 | 7.09 | 8.48 | 5.18 |
| Dark `--glass-bg` .52, not used | 65,50,36 | 11.37 | 7.29 | 5.56 | 7.38 | 6.74 | 5.56 | 6.66 | 4.06 |

Light glass (.82 over the darkest room, 227,223,217) would put ok at 2.65, warn at 2.54, info at 3.24 and bad at 3.56,
which is why light panels stay opaque.

## Known risks until captured

- A block with its own translucent surface (a tab bar, a filter row) now sits over the room, not over the plane.
- Text on a tinted chip inside a glass panel was not modelled.
- Frame rate with several blurred panels on a long page is unmeasured.

## The two missed sample points on Overview: a crop cannot fix the lower one

Checked offline against `room-warm.webp` in 8px blocks, for every scrim in the brief's .30 to .40 range:

| Point | Reference | Blocks of our photo that land within ±16 at .30 / .35 / .40 |
|---|---|---|
| KPI gap (464,220) | 102,85,71 | 6.0% / 1.5% / 0.8% |
| Below panels (700,810) | 119,105,98 | 0.0% / 0.0% / 0.0% |

No part of the photo is bright enough for the lower point at any position, zoom or flip: it needs about 165,146,136
before the scrim, and the photo's brightest wide area is about 107. The other three photos in `static/` reach it in
at most 0.5% of their blocks. Meeting it needs a different photo with a pale floor in the lower middle; that is an
asset decision and is not made here.
