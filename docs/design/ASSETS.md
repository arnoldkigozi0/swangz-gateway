# Glass assets

The photographic layers reuse the existing owner-supplied Swangz artwork:
`gateway/static/admin-welcome.webp`, `home-welcome.webp` and `login-welcome.webp`.
No reference photograph, external image, or new image download is used.

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
