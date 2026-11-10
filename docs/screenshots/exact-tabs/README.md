# R16 piece 1: staff view tabs as bars A and B (BRIEF 10.8) — 10 November 2026

Builder's captures, not an acceptance. Bundled Chromium headless, synthetic fixture. The screenshots were taken one
small CSS step before the final commit (pill 42px, single weight, glow no longer clipped); the numbers below are final.

Measured at 1440x852, same in both themes: bar 52px tall, radius 26, 1px rim; pill 42px tall (.81H, target .82H),
inset 4px + rim (.1H), exactly on the selected tab before and after an arrow-key move; the bar keeps its width when
the selection changes. axe 0, CLS 0 and no sideways overflow in 8 cells (Requests, Weekly x 1440/390 x dark/light).

Differences, tagged with BRIEF 10.1:
- 10.1(1): Hub labels and counts; no tab icons (the views have none); tabs keep their own widths instead of sharing
  the bar evenly, because the labels are much longer than the reference's.
- 10.1(3): phones (640px and under) keep the two-column tab grid; the reference has no phone still for A/B.
- 10.1(3): no backdrop blur on the bar (staff shell rule, scroll performance); bar A is `rgba(46,38,33,.86)`.

Not done in this piece: the frame-stepped motion comparison against `glassy-nav-tabs.mp4` (the slide is .42s with a
small overshoot, unverified against the video), the control room's tabs (`admin.js`), a shared `SUI.tabs`, bar C
(phone bottom bar and lens), colour sampling against the still, rendered contrast sampling beyond axe.
