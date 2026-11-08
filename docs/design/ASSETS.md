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
