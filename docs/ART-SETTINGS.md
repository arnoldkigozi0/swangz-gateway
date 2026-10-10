# October 9 artwork and Settings

The supplied archive is `Downloads/Oct 09 - 13_57.zip` (16 JPEGs). The first design pass used the third image,
`Create_architectural_portal_3D_a…_20261009140153.jpg`, for Home. After visual review, Home now uses
the sixteenth image, `Architectural_gateway_for_AI_pla…_20261009140153_5.jpg`: the layered, warmly
lit entrance set in dark architecture. The fifteenth image,
`Architectural_gateway_for_AI_pla…_20261009140153_4.jpg`, for sign-in. Originals remain in Downloads.
Images with checkerboards baked into their pixels were excluded. No image generation or background
removal was needed. WebP conversion preserves the supplied composition at quality 86.

Home uses the sixteenth image in the ZIP, framed in a restrained matte panel beside the welcome text and moving below the action on phones. Its nested doorway and lighting carry the portal visual language without the detached circular badge. Staff
sign-in uses a shaded doorway image panel; admin sign-in places the form beside the doorway on desktop
and on an opaque card on phones. Both themes retain readable controls. Decorative `/static/door.svg`
references are replaced; interface icons and tool logos are unchanged.

Settings now has a descriptive category rail, focused section buttons, task introductions, saved-state
summaries and clearer form groups. Access & privacy separates Records, Safeguards and Staff controls;
section links, refresh, history and unsaved-change checks use the existing routing system. Pricing
includes searchable model/provider names, all cache rates (including one-hour writes) and complete
label/value records on phones. Provider configuration distinguishes missing keys and emergency stops;
Emergency counts only configured, enabled providers. Health remains the source of live availability.

## Verification

- Gateway suite: 258 tests passing; the static-asset check verifies both WebP signatures and MIME types.
- Sign-in: 24 screen checks across six sizes and both themes, with desktop/phone accessibility scans.
- Principal pages: 100 screen checks at desktop and phone widths, with 42 interaction assertions.
- Settings: 72 screen checks, covering all twelve sections/categories at desktop, tablet and phone
  widths in both themes; selected desktop/phone accessibility scans. Checks cover unsaved safeguard
  edits, complete cache pricing, model search/empty results and provider configuration counts.
- Roles: 264 screen checks, with 180 permission assertions for viewer, operations, security and billing.
- JavaScript syntax and whitespace checks pass. Automated browser checks use local stand-in providers;
  they do not call company services or change production settings.

## Review captures

- [Home, light desktop](images/oct9-art-settings/home-light.png)
- [Staff sign-in, dark desktop](images/oct9-art-settings/staff-signin-dark.png)
- [Admin sign-in, light desktop](images/oct9-art-settings/admin-signin-light.png)
- [Records, dark desktop](images/oct9-art-settings/records-dark.png)
- [Pricing, light phone](images/oct9-art-settings/prices-light-phone.png)

Full screenshots and machine-readable results remain in the corresponding `/tmp/swangz-*-final`
folders and `/tmp/swangz-art-auth`. Browser checks are optional tooling documented in UI-ELEVATION.md.
