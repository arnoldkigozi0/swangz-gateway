# Rendered Hub interface review

These are actual screenshots from isolated synthetic databases, not mock-ups or production staff exports. Baseline code: `5c6a3d0b937249d3e6640b6ca878e4bbf1a34673`. The after images show the native Tracker parity branch. Both applications retain the existing Obsidian & Gold / Porcelain tokens and owner-supplied raster backgrounds.

## Before and after

| Screen | Before | After | Deliberate change |
|---|---|---|---|
| Staff Home, 1440px dark | [Before](screenshots/hub-parity/before-home-desktop.png) | [After](screenshots/hub-parity/after-home-desktop.png) | Three recent tool rows, compact reporting action and Updates; the complete catalogue remains under My tools. Document height 1255→1022px. |
| Admin weekly workspace, 1440px dark | [Before](screenshots/hub-parity/before-weekly-desktop.png) | [After](screenshots/hub-parity/after-weekly-desktop.png) | Four focused work areas; records, groups, reconciliation, management and policy open deliberately. Both examples fit the 900px viewport. |
| Admin Settings, 390px light | [Before](screenshots/hub-parity/before-settings-mobile.png) | [After](screenshots/hub-parity/after-settings-mobile.png) | Native category selector replaces the tall category grid; advanced retention is disclosed on demand. Document height 2354→1396px. |

Heights describe these fixture screenshots, not a performance benchmark. Essential tool and reporting actions stay near the start of Home; optional details remain available through real controls.

## Native business workspaces

- [Business overview, desktop](screenshots/hub-parity/after-business-desktop.png): three compact counts and ranked reported productivity; analytics, inbox, projects and management remain separate views.
- [Financial comparisons, desktop](screenshots/hub-parity/after-finance-desktop.png): working period, currency, comparable costs, ROI, missing revenue and estimate basis are visible. Values are synthetic declarations, not production results.
- [Project detail, mobile](screenshots/hub-parity/after-project-mobile.png): before/AI workflow, reported benefit, explicit media link and source report. No per-project financial allocation is invented.
- [Report review, mobile](screenshots/hub-parity/after-review-mobile.png): focused section selector, readable decisions and deliberate attribution disclosure. Original versions remain separate from later decisions.

## Actual inspection and corrections

The browser matrix covers 31 staff/admin views at 1440, 1280, 1024, 768 and 390px in both themes. Manual inspection included Home, business overview/finance, weekly records, Settings, identity administration, project and procurement drawers, report review, and mobile layouts. Inspection corrected the narrow business workspace, oversized media-link icon, clipped review actions, mobile Settings navigation and financial table headings. A drawer-focus race and Settings discard/confirmation timing were also corrected without reducing permissions or validation.

The harness now checks horizontal overflow, clipped ordinary actions, oversized project icons, WCAG accessibility findings, JavaScript errors and unexpected API failures. End-to-end checks cover both wizards, projects, working units, saved drafts, immutable corrections, department approvals, viewer restrictions, deep links, history and unsaved navigation. Real test results and external limitations are in [HUB-COMPLETION.md](HUB-COMPLETION.md); GitHub job results remain attached to PR #6.
