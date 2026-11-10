# Glass assets

The photographic layers reuse the existing owner-supplied Swangz artwork:
`gateway/static/admin-welcome.webp`, `home-welcome.webp` and `login-welcome.webp`.
No reference photograph is used.

**`gateway/static/room-warm.webp`** (8 Nov 2026, BRIEF §10) — the warm room behind the control room and staff app.
- Source: "Free cozy living room image", rawpixel, <https://www.rawpixel.com/image/5925845/photo-image-public-domain-house-living-room>
  (found via Openverse, id `7a92e95b-a898-470f-87bb-d5e41f919e13`). Author not credited by the source.
- Licence: **CC0 1.0 / public domain** — no attribution required, commercial use and modification allowed.
- Edits: cropped to the shelves/sofa/table (no window or tripod), resized to 1600×947, Gaussian blur 3px,
  evening grade (brightness .62, contrast 1.12, warm multiply #FFC48C, vignette). WebP q78, **25,972 bytes**.
- SHA-256 of the source download (1024×683 jpg): `76d16ea7bb57e7c699bbe2f76dbfd35fa1214a4b04b3492fef39a040539f6386`;
  of the WebP: `8553a2fa375bc0284bdf6db63285c9009096cce6ace450fb5c1d310413a32ef6`.
- **Provisional:** the mood matches the reference, the composition does not (the reference is a render with a
  centred TV wall). Replace with Swangz's own studio photo, or a closer licensed image, when one exists.

UI and headings use **Plus Jakarta Sans**, a geometric face selected after Arnold's
7 November instruction to choose the best font. Normal Latin, variable weight
200–800, WOFF2, **27,348 bytes**; no external font requests at runtime.

- Distribution: [Google Fonts family](https://fonts.google.com/specimen/Plus+Jakarta+Sans).
- File: [Google Fonts Latin WOFF2 v12](https://fonts.gstatic.com/s/plusjakartasans/v12/LDIoaomQNQcsA88c7O9yZ4KMCoOg4Ko20yw.woff2).
- Copyright 2020 The Plus Jakarta Sans Project Authors ([Tokotype](https://github.com/tokotype/PlusJakartaSans)).
- Licence: SIL Open Font License 1.1; full text stored alongside the font in
  `gateway/static/fonts/PlusJakartaSans-OFL.txt`, copied from the
  [Google Fonts licence](https://github.com/google/fonts/blob/main/ofl/plusjakartasans/OFL.txt).
- WOFF2 SHA-256: `153fc85b70298beeb1d61a5f723331649e7f23bb77302a66e61cb3e2fbdb5e79`.

The two HTML preload links follow the replacement font. Archivo's existing file
is retained for older cached pages. No library or font-loading script is added.

**Poppins** (console + staff app) and **Inter** (sign-in), 8 Nov 2026, BRIEF §10.5 — replacing Plus Jakarta Sans.
- Poppins 400/500/600/700/800, latin WOFF2 from Google Fonts v24 (`Poppins-<weight>-latin.woff2`, ~8 KB each). Copyright 2020
  The Poppins Project Authors (Indian Type Foundry). Licence SIL OFL 1.1, text in `fonts/Poppins-OFL.txt`.
- Inter variable 400–800, latin WOFF2 from Google Fonts v20 (`Inter-latin.woff2`, 48,256 bytes). Copyright 2020 The Inter
  Project Authors (Rasmus Andersson). Licence SIL OFL 1.1, text in `fonts/Inter-OFL.txt`.
- Self-hosted (strict CSP, no font requests to Google at runtime).

**`gateway/static/room-warm-tile.webp`** (10 Nov 2026) — `room-warm.webp` followed by its vertical mirror image
(1600×1894), so the staff app's room continues without a seam on desktop pages that scroll. Derived from
`room-warm.webp` only; same CC0 source and edits. WebP q80, **51,422 bytes**.

**Console room, 10 Nov 2026 (late), BRIEF §10.10.3** — three candidates, all CC0 from Wikimedia Commons (photos first
published on Unsplash under CC0, or uploaded to Commons as CC0). Unsplash, Pexels and StockSnap refused automated
visits, so nothing was taken from them directly.

| Candidate | Source | Author | Original | SHA-256 of the original |
|---|---|---|---|---|
| `room-hall-*` (in use, `gateway/static/`) | [Ornate office space (Unsplash)](https://commons.wikimedia.org/wiki/File:Ornate_office_space_(Unsplash).jpg) | Crew | 4000×2662 | `338b2064ac92ee6f243a9b0a79fe43fe048abd47463098b3a621cb75614cc1c5` |
| `room-lamp-*` (`docs/design/backgrounds/`) | [Books in stack with lamps (Unsplash)](https://commons.wikimedia.org/wiki/File:Books_in_stack_with_lamps_(Unsplash).jpg) | chuttersnap | 6016×4016 | `f36259cbc0d89fd9e2e739db30687ef4f7cfd72a243533f992662942ce9ad5cc` |
| `room-suite-*` (`docs/design/backgrounds/`) | [Hotel room bedroom … Salford, 5 October 2025](https://commons.wikimedia.org/wiki/File:Hotel_room_bedroom_in_building_on_Chapel_Street,_Salford,_Greater_Manchester,_England,_on_5_October_2025.jpg) | MatthewHoobin | 4080×2296 | `5708c346927df45ea6d00bde26a0184e1678ea261dc59a561534fd3eacc6b0cc` |

Edits, the same for all three (`docs/design/backgrounds/build.py`): centre crop to 16:9, resize to 3840×2160, Gaussian
blur radius 26 (so the room is out of focus and no text, logo or hard line survives), brightness set to an average of
34–36%, fine grain added so the soft gradients do not band, WebP quality 86 at 2560, 1920 and 960 wide. The lamp and
suite candidates are also warmed (red ×1.08, blue ×0.80–0.82); the hall is not. After the 16:9 crop every source is still larger than
3840×2160 (the smallest is the hall at 4000×2250), so nothing is upscaled.

