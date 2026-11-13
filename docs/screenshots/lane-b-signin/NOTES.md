# Lane B sign-in forced colours: Probe captures

Head under test: 5ea4a642a61b6d43ef0fe8a2f23b719599e7e1d7 (local; remote was ceea4db at the time).
Captured with Chromium (forcedColors active, colorScheme light/dark) on the demo fixture, synthetic data. Eye focused in each shot.

- forcedColorChecks run alone: 32 of 32 pass (both apps, light and dark, 390x844). Earlier result on ceea4db, kept separate: 24 of 24.
- Eye toggle, forced colours, both apps, light and dark, 390 and 1440: 305-349 (390) / 569-613 (1440), field right edge 349 / 613, 44x44, margin-right 0, border 1px: contained, target kept. On ceea4db it overhung by 10px.
- Normal mode: unchanged (margin-right -10px, no border, 315-359 at 390). Not part of this PR.

Allowed difference, BRIEF 10.1.3: system palette and no photo/blur in forced colours; the eye border stays within the field while preserving its 44px target. No 50% reference overlay was produced for this fallback. Normal-mode overlays remain open. The historical light focus-ring contrast finding (2.39:1) was on the People page, not a current sign-in measurement; current-page verification remains open.
