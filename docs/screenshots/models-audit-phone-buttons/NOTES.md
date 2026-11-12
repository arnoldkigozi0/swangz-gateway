# PR 189 (D3b) Probe captures. Head fa6fab499c1ea8c5268de46472025d1648ff3d71
Real Chromium, demo fixture, synthetic data.
- audit.cjs unmodified: 162 checks passed (390 and 640, light and dark).
- models.cjs unmodified: FAILS at "dark 390: See all shows the rest" (test defect, see below).
- models.cjs with one-line patch (scrollIntoViewIfNeeded before boundingBox), run from a /tmp copy: 164 checks passed, all six cells.
- Focus ring on See all: 2px, offset 2, ring bottom 682.9 vs panel bottom 687.9, not clipped (390 and 640, light and dark). seeall-focus-*.png.
- Visible heights: See all 36px, pager Previous/Next 30px (small). Hit area 44px, reaches 3px below the box.
