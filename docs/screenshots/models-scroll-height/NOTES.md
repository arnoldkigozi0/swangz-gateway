# PR 188 (M1) Probe captures. Head d4eff958c79af3a5b520addd4387750743c00fa0
Real Chromium, demo fixture (HUB_UI_FIXTURE=1), synthetic data. models.cjs: 100 checks passed. Own measurement in m1.json (80 cloned rows).
Models Simple 1440x852: document overflow 0 (light and dark, default and long); wrap max-height 352px, scrolls inside, scrollTop moves 0 to 400 with no page scroll.
Before (no M1 CSS, PR 189 head): document overflow 24px, wrap max-height 462px.
Detailed unaffected: max-height 462px, overflow 0 (default and long).
No reference overlay: Models has no reference still; BRIEF 10.10.2 (page does not scroll at 1440x852) is the criterion.
