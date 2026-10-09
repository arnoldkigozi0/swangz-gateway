# Swangz Gateway — interface map

How the two apps are organised, where each kind of information lives, and the rules for adding to them.
Written for the V2.1 clarity pass (Oct 9, 2026). Keep it current: when a page gains or loses a job, say so here.

## The rules

- **One canonical home per kind of information.** Other pages may show a short summary of it *for their own
  task*, with the same meaning and time range, and a link to the canonical home. They never re-list the whole
  dataset.
- **Tabs** are alternative views of one thing (a person, a tool, a page's subject). **Pages** are separate jobs
  with their own URL. **Drawers/sheets** keep you in a list while you look at one item. **Accordions** hold
  optional explanation. Settings categories are a secondary navigation list, not tabs of tabs.
- Every page says where you are (area and page, or a breadcrumb for sub-pages), what it's for (one line), and
  puts its main action on the title's line. Tabs carry a one-line explanation only where the job isn't obvious.
- Primary navigation (the sidebar), page tabs (underlined), segmented filters (boxed, with counts) and chips
  look different from each other on purpose.
- The URL is the state: `?tab=` for a page's view, `?section=` for a Settings sub-section, filters and ranges
  alongside. Back and Forward step through tab changes; deep links and refresh land on the same view.

## Audit (before this pass) and what each page is now for

| Area | Primary job | Problems found | Overlap | Structure now |
|---|---|---|---|---|
| Sidebar | Find any page | PR draft opened with three of four groups collapsed; a collapsed group could hide the active page; group labels looked like links | — | Four groups, all open by default, collapsible, the active page's group always open; remembered per browser |
| Page tabs | Switch views | PR draft: a syntax error (the whole console failed to load); `aria-controls` pointed at nothing; nested Settings tabs shared one query string; tab changes weren't in history; switching tabs could drop unsaved settings | — | One `pageTabs()` with its own query parameter, real ARIA wiring, history entries, an unsaved-changes guard, and tab switches that don't refetch the page |
| Overview | Is anything wrong, is anyone working, what's changing, what costs money | "Right now" listed up to six attention items — the queue's job | Attention queue; licence table | Summary strip + four views; "Right now" shows the top three urgent items and the live preview, with links to Needs attention and Live |
| Needs attention | The whole queue | — | — | Canonical home of the queue |
| Activity | What people did | — | Security and Audit read like other histories | Timeline (chronological) · Who used what (analysis) · AI requests (request detail) · Tools opened · Websites visited; the intro says what is *not* here |
| Security | Signals that may need investigating | Read like another activity list | Activity | Signals with severity, evidence, *Investigate* and *Open incident*; not a history |
| Audit log | What admins and the system changed or tried to | — | Activity | Actor, action, target, outcome, reason, before/after |
| People | Find a person | — | — | Table with status filters and search |
| Person profile | Everything about one person | Overview stacked activity, tools, sessions and notes; "Tools" and "Details" were vague | Activity, devices | Overview (facts, live now, a short recent-activity and tools preview) · Access (tools and why, other limits) · Activity (timeline + sessions) · Devices (keys, app sign-in, browsers) · Security · Account (details, budgets, notes) |
| Devices / device profile | Keys and what each device did | "not geolocated" text out of date since V2 | — | Index (keys, browsers); profile tabs Activity · Flagged · Sessions · Apps & models · Addresses & location (each place with how it is known: named network, approximate, or address type only) · Gateway key |
| Tools / tool profile | The catalogue and each tool | Tool Overview held usage facts, a chart, people, devices, refusals, sign-in and domains in one scroll | Usage, access, settings | Overview (what it is, status, key facts, links) · Usage (chart, people, devices, refusals) · Access (teams, people, end dates, turns now) · Subscription (site tools) · Configuration · Workspace (shared accounts only: turn rules and the company browsers) |
| Models | The registry | — | — | Table with status filters; edit in a dialog |
| Policies | Rules, trying them, explaining a decision | Editor showed every field at once | — | Policies · Simulate · Explain; the editor is grouped (basics, who, what, limits, message) with conditional fields shown only for their effect |
| Licences & spend | Licences, metered spend, renewals | Licences opened with a spend figure; "Renewals & budgets" repeated spend by person | Spend, People | Licences (seats, use, idle, reclaim) · What cost us money? (metered spend) · Renewals (commitments only); budgets per person live on People |
| Reports | Standard questions with CSV | A permanent nine-item vertical tab list | — | A catalogue that says what each report answers; each report on its own page with range and download |
| Settings | Configure the gateway | Ten flat tabs; PR draft nested tabs shared `?tab=` and lost the section on refresh | — | Categories (secondary list): Access & privacy · Emergency · Purpose & location (Purposes, Locations) · Providers & pricing (Connections, Model prices, Media rates) · Company browsers · Console users · Your account. Old `?tab=` links still land in the right place |
| Staff Home | Open your tools | Every approved tool repeated from the catalogue; cards for devices and privacy competed with the tools | Tools, Requests | A restrained hero, up to three notices (link to Updates), up to six of your tools (link to the catalogue), Studio and quick links |
| Staff Tools | Find and open tools | Drawer repeated what's recorded in two places | Privacy | Catalogue: yours as cards, the rest as rows; drawer sections in one order, ending with a link to Privacy |
| Staff Studio | Make media | Recent creations made the page long | — | Create · Your creations |
| Staff Devices | Connect and manage devices | Setup cards, devices and old devices on one page | — | Connected · Connect a tool · Disconnected |
| Staff Requests | Updates and access requests | Two jobs on one page | Home notices | Updates · Access requests (the bell opens Updates) |
| Staff Privacy | What is recorded | Long cards | — | Sections with an in-page index: recorded, not recorded, purpose and location, who can see, retention, help |

## Canonical homes

| Information | Canonical home | Summaries elsewhere (and why) |
|---|---|---|
| A request in full | Record page (`#/records/<id>`) | Activity rows, device and person activity, Security evidence links |
| What one person did | Person → Activity | Person → Overview (last few), Activity timeline filtered by person |
| A tool's use | Tool → Usage | Tool → Overview (one line of facts), Overview → Top tools |
| Who can use a tool and why | Tool → Access (per tool) · Person → Access (per person) | Licences (seats), staff drawer ("why it's available to you") |
| The attention queue | Needs attention | Overview → Right now (top three), the bell |
| Security signals | Security | Person → Security, device → Flagged, Overview strip |
| Admin changes | Audit log | Incident trail, timeline access events (about a person) |
| Metered spend | Licences & spend → What cost us money? | Overview strip and trend, People (per person vs budget), Reports |
| Seats and idle licences | Licences & spend → Licences | Overview → Licences (top opportunities), tool Subscription |
| Renewals | Licences & spend → Renewals | Overview → Licences (next 30 days) |
| Configuration | Settings | Operational pages show the resulting state and link to the setting |
| Staff notices | Staff → Requests → Updates | Staff Home (top three) |
| What is recorded about staff | Staff → Privacy | One line and a link in the tool drawer and Connect flow |

## Tabs, views and the address

- **Console:** `A.pageTabs(base, params, tabs, opts)`. `tabs` are `[id, label, build, count?, description?]`. Each tab
  builds once, on first view. `opts.param` names the query key (default `tab`); a nested set uses its own key and the
  parent lists it in `opts.clears`, so choosing another category starts its sections over. `opts.vertical` is the
  Settings-style category list (an underlined row on narrow screens); `opts.split` returns `{ bar, body }` for a
  side sheet. Every click is a history entry; Back and Forward switch the view in place. A form with unsaved changes
  calls `A.setDirty(() => changed)` so switching tabs, leaving the page or closing the window asks first; clear it
  with `A.setDirty(null)` after a save. Links from before a rename keep working: Settings maps old `?tab=` values,
  people map `tools → access` and `details → account`, and Reports maps `?tab=<kind>` to `#/reports/<kind>`.
- **Staff app:** `viewTabs(base, params, views, label, fallback)` in `portal.js`. `views` are
  `[id, label, build, count?, onShow?]` and live in `?view=`. Every view is built at once and kept, hidden, so work
  in progress (a Studio job) carries on.
- **Not tabs:** segmented filters (`A.seg`, `.u-seg`) are boxed and carry counts; filter chips are rounded and
  removable; the sidebar is navigation. None of them look like page tabs.

## Visual direction

Obsidian & Gold, finished after Swangz Avenue Bookings: near-black neutral surfaces, champagne gold as light and
accent (never a fill behind text), tight radii, sentence-case outline buttons with one primary per place. The only
artwork is `static/door.svg` — the doorway, for "every AI tool, one door" — drawn as SVG with presentation attributes
(no inline styles, so the CSP holds), about 2 KB. It appears on the admin sign-in, the staff sign-in panel (and the
welcome page that shares it) and the staff Home hero. Nothing sits behind tables, lists, charts or numbers. It fades
in once, and not at all with reduced motion.

## How this pass was checked

Headless Chromium against the demo gateway (`tests/fake_upstream.py --demo`):

- **Owner and staff:** every page at 1440, 1280, 1024, 768, 430 and 390 px, dark and light.
- **Viewer, operations, security and billing:** the role-sensitive pages at 1440, 768 and 390 px, both themes.
- **On every page:** horizontal overflow, buttons past the window edge or with clipped text, tab bars scrolled past
  the chosen tab, console errors, failed requests.
- **Navigation, scripted:** deep links, refresh, Back/Forward through tabs, sheets and views, arrow/Home/End keys,
  the unsaved-changes guard, and old links.
- **Roles, asserted page by page:** what each role is offered.
- **Unit tests:** the Python suite.
