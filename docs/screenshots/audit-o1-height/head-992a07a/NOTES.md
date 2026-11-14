# Probe notes — LOCAL head 992a07a1373ad89f4dafdbcce0643ea8921790f3 (PR #233 remote is still the failed 4c896e3; nothing here is a check of the remote head)
Synthetic local demo, Chrome, one browser at a time. No reference overlay (Audit is not in the reference videos).
## Result: PASS (Audit O1)
- Shipped tests/browser/audit.cjs: 164 checks passed (audit-cjs-run.txt).
- Matrix 1440x852, dark+light, default and +80 rows, with and without the 54px pager (o1-matrix-results.json, screenshots):
  - Simple, no pager: wrapper cap/height 492, panel bottom 772, footer rect 796-812, page overflow 0, scroll attempt moved 0.
  - Simple, with pager: cap/height 438 (+54 pager), panel bottom 772, footer 796-812, overflow 0, scroll moved 0. +80 rows: identical, scrolls inside the wrapper.
  - Detailed: 462 cap, panel bottom 732, footer 756-772, overflow 0 (unchanged, both states, both themes).
  - Models 1440x852: cap 352, bottom 686, overflow 0 (unchanged).
  - 1100x800 (tablet rule): cap 300, overflow 0. 640x900 and 390x844: wrapper max-height none, no sideways overflow (the page scrolls vertically as before; unchanged).
- My earlier "inline max-height stays 462" experiments: not reproducible. On this head an inline max-height of 400/300 binds immediately (computed and rect agree; one .u-table-wrap, no important rule). Most likely my old script measured a re-rendered wrapper; I cannot prove it. The new caps do bind (492/438 computed = rect).
## Staff targets, 390/640 light/dark (o12; staff-targets-summary.json / -raw.json)
Pages: Home, Tools, Requests, Devices, Weekly, Privacy, Tools drawer. Every visible a/button/input/summary measured (top bar, search, New, bell, avatar, bottom nav, tabs, rows, drawer, footer).
Below 44px:
- Page tab buttons 43.7px tall (0.3px short): Requests (Updates, Access requests; at 640 also Tool & subscription purchases, Department reports), Devices (Connected, Connect a tool), Weekly at 640 (Pending & returned, Submitted, Adoption & impact).
- Tools drawer at 390 and 640: top Close icon 36x36, footer Close 62x36, "Open <tool> (opens in a new tab)" 87x36. These are real misses.
- Privacy at 640 (not 390): <summary> rows 23.3px tall (e.g. "Weekly reporting and your declaration").
- Skip link 39.3 tall (off-screen until focused; minor).
Top bar, search, New, bell, avatar, bottom nav, footer links and theme switch: all >= 44 in the scan. No horizontal clipping anywhere. Controls "covered" were only content under the fixed bottom bar at scroll 0 (Tools: Connect, Codex details) and everything behind the open drawer (expected). Not run: focus-ring check, pairwise overlap test, keyboard path.
