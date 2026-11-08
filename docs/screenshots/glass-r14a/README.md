# R14a: Porcelain (light) chart and list contrast

Check script: `tests/browser/porcelain.cjs` (`SHOTS=<dir>` re-saves these images; `REPORT_ONLY=1` prints without failing).
Each number is the element's own colour against the worst pixel actually painted behind it (element hidden, background photographed), in the real console.

| File | View |
|---|---|
| charts-desktop-light.png / charts-desktop-dark.png | 1440x900 |
| charts-mobile-light.png / charts-mobile-dark.png | 390x844 |

**Fixture:** the charts, bars, sparklines and list are mounted by `SUI` into the real console with invented values and example.test names. Nothing here is real usage data. Colour is what is being checked.

## Light theme, measured after the change (limits: 4.5 text, 3 non-text)
| Part | Ratio | Limit |
|---|---|---|
| axis label text | 6.14 | 4.5 |
| column fill (spend tone) | 4.32 | 3 |
| column fill (tone 2) | 4.72 | 3 |
| line stroke | 3.59 | 3 |
| line stroke tone 2 | 3.87 | 3 |
| end label text | 16.04 | 4.5 |
| show-as-table link | 6.14 | 4.5 |
| sparkline stroke | 4.49 | 3 |
| bar list name | 16.17 | 4.5 |
| bar list value | 16.07 | 4.5 |
| bar list note | 6.1 | 4.5 |
| bar list fill | 3.39 | 3 |
| list title | 16.04 | 4.5 |
| filter pill text | 7.78 | 4.5 |
| progress value | 16.51 | 4.5 |
| panel heading | 16.18 | 4.5 |

Before: spend line 2.74 (fail), sparkline 1.22 (fail), spend columns 3.22 and bar fill 3.10 (pass, thin), tone-2 line 3.19.
Change: light-theme-only block in `ui.css` (`--pc-1` #96690C, `--pc-2` #1A70AC, `--pc-spark` #6F675D) for lines, columns, areas, end dots and bar fills, plus a visible bar track. Dark theme and `tokens.css` untouched.

Decorative, not asserted (a number or table repeats them):
- grid line (decorative, not asserted): 1.07
- bar list track (decorative, not asserted): 1.27

## Left over
- **Dark sparkline stroke is 1.40:1** (limit 3). Out of this task's light-theme scope; not changed. Fix is a one-line dark override of `.u-spark .line`.
- Light gridlines are 1.07:1 by design (decorative; axis labels carry the values).
- The end-dot ring colour and glass tube columns (PR #40) are not covered here; the check mounts `SUI.columns` as it exists on this branch (no tube).
- Frame rate not measured.
