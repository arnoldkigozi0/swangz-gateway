# Swangz AI Hub — interface map

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

## Page levels (BRIEF §10.10.1)

The plan for the layered structure. It lists every page of the console and the staff app, in the order the
chain PRs will touch them. It changes no code; each row is the target, and "Today" says where the page stands
against it. **Nothing leaves the product**: content that leaves a page moves down a level and stays reachable
(the All pages drawer, Ctrl+K, the avatar menu). Stop all AI stays one step away from every page.

Levels: **L1 Summary** (how is this area doing: title, ≤ 4 number cards, one chart or one ≤ 5-row list, no scroll
at 1440×852) · **L2 List** (which ones: one table or card list, one filter row, one primary action, no charts) ·
**L3 Record** (what about this one: header + tabs, one block per tab) · **L4 Action** (do it: side sheet or dialog,
≤ 6 fields per step). Counting rules a reviewer applies: an L1 has ≤ 7 blocks; no page mixes a table with charts;
a tab strip has ≤ 6 tabs; a page has one tab strip; a number on an L1 card links to the L2 list already filtered to
those items; nothing appears on two pages, the second page links to the first (Canonical homes, below).

### Console (`/admin`)

| Page (address) | Level | The one question | Parent | Children | What leaves the page, and where it goes |
|---|---|---|---|---|---|
| **Overview** (`#/`) | L1 | Is anything wrong, and what is the next step? | — (root of Monitor) | Needs attention, Live, Activity, Licences & spend, Security | Simple (default, remembered per console user): one sentence with the real number, a next-step button, and at most 3 blocks (*What do you want to do?* tiles, numbers, then setup or the waiting list). Each tile is a guided task in `admin-guide.js`: one question a step, the safe answer chosen, a review, then a next task. Detailed (`?view=detailed`): Converted (11 Nov): 7 blocks (4 KPI cards, the AI usage chart, two count cards). *Uses by tool* now shows on Activity → Who used what when grouped by tool. Each card opens its list filtered to what it counts (spend 30 days, requests 30 days, today's people, security 7 days, the attention queue, live). One "Next step" line under the title; the trail is in the top bar. Not yet measured in a browser at 1440×852 |
| **Needs attention** (`#/attention`) | L2 | Which items need someone now? | Overview | Person, Tool, Device, Record, Incident (each row's L3) | Nothing. Canonical home of the queue |
| **Live** (`#/live`) | L2 | Which requests are running right now? | Overview | Record (Inspect) | Cut-request action is L4 (confirm dialog) |
| **Activity** (`#/activity?tab=`) | L2 | What did people do? | Overview | Record, Person, Tool | Five tabs (Timeline · Who used what · AI requests · Tools opened · Websites visited), within the limit. *Who used what* has charts, so it moves to its own L1-style summary under Reports when the Money chain lands; the table tabs stay |
| **Request record** (`#/records/<id>`) | L3 | What happened in this one request? | Activity (or the list it came from) | Person, Tool, Device, the session | Nothing. Canonical home of a request in full |
| **Session** (`#/sessions/<id>`) | L3 | What was in this session? | Request record | Request records, Person | Nothing |
| **Health** (`#/health`) | L2 | Which checks pass? | Overview | Settings (the fix), Audit log | Not measured for this table (UNVERIFIED which blocks it holds today); the chain PR that reaches it measures it first |
| **People** (`#/people`) | L2 | Which person? | Govern (L1, new) | Person | Status filter + search + one primary (Add person). Budgets stay on the person |
| **Person** (`#/people/<id>`) | L3 | What about this person? | People | Their Tools (Access tab), Devices, Activity rows, Incidents | Six tabs: Overview · Access · Activity · Devices · Security · Account. Overview shrinks to facts + one next step; the live-now block and the recent-activity preview leave for the Activity tab |
| **Access requests** (`#/requests`) | L2 | Which requests wait for a decision? | Govern (L1, new) | Person, Tool | Built on the kit: one table, one filter row (Status with counts, defaulting to Open, plus a search), a pager and a row menu (their record, the tool). No tab strip and no primary button; Decline (asks for an optional note) and Grant sit at the row's edge (L4), and a Next step line names the oldest request still waiting. `?state=any` shows every decision |
| **Tools** (`#/tools`) | L2 | Which tool? | Govern (L1, new) | Tool | Catalogue as one table, one filter row (search, Show, Category; counts sit in the Show options), one primary (Add a tool), a More menu ending each row, 25/50/100 pages over 25 rows, all in the address |
| **Tool** (`#/tools?open=<id>` side sheet) | L3 | What about this tool? | Tools | Licence (Subscription tab), Person (Access tab), Usage rows | Six tabs: Overview · Usage · Access · Subscription · Configuration · Workspace (shared accounts only). Usage keeps the one chart and the refusals; the people and devices tables are on Access. The header holds the state, a Next step line, Manage access and a More menu to Activity, Licences and Access requests |
| **Models** (`#/models`) | L2 | Which model, and is it allowed? | Govern (L1, new) | Model sheet (L4 edit) | Nothing |
| **Policies** (`#/policies?tab=`) | L2 | Which rules apply? | Govern (L1, new) | Policy editor (L4, grouped steps) | Three tabs: Policies · Simulate · Explain a decision. Simulate and Explain are tools, so they stay as tabs but never share a page with the list |
| **Weekly reporting** (`#/weekly?tab=`) | L2 | Which weekly reports need review? | Reporting (L1, new) | Weekly report (L3 sheet), Person, Tool | Five tabs (Weekly trends · Staff estimates · Adoption value · Licence opportunities · Procurement) mix charts and tables: trends and value move to the Reporting L1; each tab keeps one block |
| **Business value** (`#/business?tab=`) | L2 | Which tool pays back? | Reporting (L1, new) | Project, Department, Tool | Tabs Overview · Departments · Projects · Analytics; the allowance form fields (≤ 6) become an L4 sheet |
| **Tool & subscription requests** (`#/procurement`) | L2 | Which purchase requests wait? | Reporting (L1, new) | Procurement request (L3) | Decision is L4 |
| **Licences & spend** (`#/licences?tab=`) | L1 (Money) | How is spend and licence use? | — (root of Money) | Licences, What cost us money?, Renewals, Spend reports | Money L1 = 4 number cards + one chart; *Licences*, *What cost us money?* and *Renewals* are L2 pages under it (`?tab=`), one table each. Rising fast and How spend is worked out open as L4 sheets |
| **Spend reports** (`#/reports`, `#/reports/<id>`) | L2 → L3 | Which standard question do I need answered? | Money | One report (range + CSV download) | Nothing; each report is its own page |
| **Security** (`#/security`) | L1 (Trust) | Is anything unsafe? | — (root of Trust) | All signals, Incidents, Devices, Audit log | Built: four cards (Signals, Open incidents, Failed sign-ins, Credentials), each opening its list already filtered; one list of the first five signals; posture and the three safeguards moved to a Safeguards side sheet |
| **All signals** (`#/security?view=signals`) | L2 | Which signals? | Security | Record, Person, Device, Audit log (each signal's evidence) | Built: Period, Kind and Severity filters plus search; details and Open incident in each row's More menu. Failed sign-ins are the Kind filter, one row per address |
| **Incidents** (`#/incidents`) | L2 | Which incident is open? | Security | Incident | Built: State (Active by default) and Severity filters plus search |
| **Incident** (`#/incidents/<id>`) | L3 | What happened and what was done? | Incidents | Records, Person, Device, Audit log | Built: tabs Overview · Evidence · Notes · Audit trail and a Next step line; Resolve and Dismiss are L4 dialogs |
| **Devices** (`#/devices?tab=`) | L2 | Which key or browser? | Trust (Security) | Device | Tabs Gateway keys · Browsers (the one strip). Kit filter bar (Status + search), pager, a row menu (record, their activity, revoke). No primary button. Trail: Devices |
| **Device** (`#/devices/<id>`) | L3 | What did this device do? | Devices | Person, Records | Trail Devices › name, one Next step line (flagged requests first, then an owner suspended, a key never used or idle). Six tabs: Overview (the key's facts, replacing the stat tiles and the Gateway key tab) · Usage (chart, apps, models) · Activity · Flagged · Sessions · Addresses. Revoke is the only danger action (L4 confirm) |
| **Audit log** (`#/audit`) | L2 | Who changed what? | Security | Record or target the change names | Built: trail Security › Audit log; kit filter bar (search, Period, Who, Outcome, Area, and an About chip from a link), pager over the 100 loaded entries, Load older for the next 100. Typing `person:7` in the search finds what a change names. Canonical home of admin changes |
| **Settings** (`#/settings?section=`) | L1 → L4 | What do I configure? | Trust (Security) | Seven categories: Access & privacy · Purpose & location · Providers & pricing · Company browsers · Emergency · Console users · Your account | The rail is the L1 list. A section is an L4 form: ≤ 6 fields per step, longer sections become numbered steps. Access & privacy (Records · Safeguards · Staff controls) and Purpose & location (Purposes · Locations · Connections) each split so no section shows two tab strips |
| **Notifications** (bell sheet) | L2 | What did the system tell me? | Any page | The thing each note names | Sheet, not a page |
| **Sign-in** (`/admin` signed out) | — | — | — | Overview | Not part of the chain |

*New L1 landings* (Govern, Reporting, Money, Security) do not exist as pages today: the area's first page is an L2.
They are built in the chain PRs below, each with ≤ 4 cards and one list or chart, and each card links to a filtered L2.

### Staff app (`/`)

| Page (address) | Level | The one question | Parent | Children | What leaves the page, and where it goes |
|---|---|---|---|---|---|
| **Home** (`#/`) | L1 | What do I open now? | — | Tools, a tool's Open (`/go/`), Requests, Weekly reports | One hero action + three recent rows + one of Updates / allowance. Today the page can also show Updates and allowance together; target is one of them, the other links to Requests → Updates |
| **Tools** (`#/tools`) | L2 | Which tool is mine? | Home | Tool drawer (L3), Open, Request access (L4) | Search + category + sort is one filter row. Yours as cards, the rest as rows: one list with a "Mine" filter |
| **Tool drawer** | L3 | Why do I have this, how does sign-in work, what is recorded? | Tools | Privacy (the "recorded" link), Request access | Ends with the single link to Privacy |
| **Request access** | L4 | — | Tool drawer | Requests → Access requests | ≤ 6 fields |
| **Studio** (`#/studio?view=`) | L2 | What can I make, what have I made? | Home | A creation | Two views: Create · Your creations |
| **Devices** (`#/devices?view=`) | L2 | Which devices are connected? | Home | Connect flow (L4), a device | Views Connected · Connect a tool; "Disconnected" becomes a filter on Connected |
| **Requests** (`#/requests?view=`) | L2 | What is waiting for me? | Home | Update, Access request | Views Updates · Access requests; Procurement and Department reports leave for Weekly reports |
| **Weekly reports** (`#/weekly?view=`) | L2 | Which report do I owe? | Home | Weekly report (L3 sheet) | Views Pending & returned · Submitted · Adoption & impact; Adoption & impact is its own L2 (below) |
| **Adoption & impact** (`#/activity`, `#/business`) | L2 | How is my area adopting AI? | Weekly reports | Project | Declarations, department views, analytics: one block per tab |
| **Project** (`#/projects`) | L3 | What is this deliverable? | Adoption & impact | — | Focused detail only |
| **Privacy** (`#/privacy`) | L3 | What is recorded about me? | Any tool drawer, Home footer | — | Six sections with an index; this is reference reading, linked from the drawer, not from Home |
| **Device approval** (`/device`) | L4 | Approve this device? | The app's sign-in code | — | One code, one decision |
| **Sign-in** (`/`) signed out | — | — | — | Home | Not part of the chain |

### Build order (BRIEF §10.10, round R18)

(d) Overview as the L1 with its cards linked → (e) one chain per PR: People (list → person → their tools) → Tools
→ Money (new L1) → Security (new L1) → Settings → staff app (Home → tool → request access). Each chain PR changes
this table in the same commit, so the document stays the truth.

### What this table does not decide (UNVERIFIED / open)

- The exact ≤ 4 cards for Govern, Reporting, Money and Security landings are not chosen; each chain PR proposes them and Arnold's boss reviews.
- Block counts "today" were read from the code and the Overview screenshot on 10 Nov (main c429f93), not measured on every page; each chain PR measures its own page at 1440×852 before and after.
- Tab counts were read from `pageTabs()` / `viewTabs()` calls; pages that build tabs dynamically (Reporting detail sheets) are not counted.

## Audit (before this pass) and what each page is now for

| Area | Primary job | Problems found | Overlap | Structure now |
|---|---|---|---|---|
| Sidebar | Find any page | PR draft opened with three of four groups collapsed; a collapsed group could hide the active page; group labels looked like links | — | Four groups, all open by default, collapsible, the active page's group always open; remembered per browser |
| Page tabs | Switch views | PR draft: a syntax error (the whole console failed to load); `aria-controls` pointed at nothing; nested Settings tabs shared one query string; tab changes weren't in history; switching tabs could drop unsaved settings | — | One `pageTabs()` with its own query parameter, real ARIA wiring, history entries, an unsaved-changes guard, and tab switches that don't refetch the page |
| Overview | Is anything wrong, is anyone working, what's changing, what costs money | "Right now" listed up to six attention items — the queue's job; four tabs repeated other pages | Attention queue; licence table; trends; leaders | Since R16/R17 (BRIEF §10.7): a greeting, four cards (AI spend, AI requests, Active people, Security events), then AI usage over eight days, two counts (Need attention · Live requests) and Uses by tool. No tabs: each block links to the page that owns the detail (Licences & spend, Activity, Needs attention, Live, Security) |
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
| Settings | Configure the gateway | Ten flat tabs; PR draft nested tabs shared `?tab=` and lost the section on refresh. V2.2: the category list was plain text with no grouping, the content had no header, Emergency looked like any preference, and phones got a cramped scrolling strip | — | A workspace (V2.2): a grouped rail — *Gateway* (Access & privacy · Purpose & location · Providers & pricing · Company browsers), *Emergency*, *Console access* (Console users · Your account) — with icons, a view-only lock per category for the role, and the stop state on Emergency. Each category opens with a header (what it is, "View only" or "Some of these need another role") that holds its sections (Purposes, Locations; Connections, Model prices, Media rates). Rows a role can't change say which access they need. Emergency is a status board with the one big stop, then one provider at a time and the company browsers, then links to the smaller stops. Below 1100px the rail becomes a grid of tiles. Choosing a category opens its first section; old `?tab=` links still land in the right place |
| Staff Home | Open your tools | Every approved tool repeated from the catalogue; cards for devices and privacy competed with the tools. V2.2: no action in the hero, a "used this week" figure, every module full width and equal | Tools, Requests | A launchpad (V2.2): the hero says where you stand and holds one action — back to the tool you opened last (through `/go/`), or "Choose a tool", or "Browse the catalogue" when nothing is on; paused and suspended say so and offer nothing to open. Your other tools (up to five more, never the one in the hero) are the main column; beside them Updates (up to three, link to Updates), your allowance only when it's visible to you, Studio only when you have it, and quiet links to devices, requests and privacy |
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
| A tool's use | Tool → Usage | Tool → Overview (one line of facts), Activity → Who used what → Tool (Uses by tool) |
| Who can use a tool and why | Tool → Access (per tool) · Person → Access (per person) | Licences (seats), staff drawer ("why it's available to you") |
| The attention queue | Needs attention | Overview (a count), the bell |
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
  Settings-style category list (a grid of tiles on narrow screens); `opts.split` returns `{ bar, body }` for a
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
accent, tight radii, sentence-case outline buttons with one primary per place. Owner-supplied artwork from
`Oct 09 - 13_57.zip` supplies the self-hosted architectural artwork: `static/home-welcome.webp` sits behind
the staff Home hero and fades into the page surface; `static/login-welcome.webp` gives staff sign-in its own
soft-edged photographic panel; `static/admin-welcome.webp` gives admin sign-in a distinct, warmer doorway view.
The artwork remains behind page headings and cards, never behind tables, lists, charts or numbers. Entrance
fades respect reduced motion. Interface and tool icons remain vectors.

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

## Settings and Home (V2.2)

- **Settings rail.** `pageTabs(…, { vertical: true, groups, icons, marks })`: `groups` are `[label | null, [ids]]` (no
  label = a divider), `icons` an icon per tab, `marks` a node after a label (the view-only lock, Emergency's "AI paused"
  / "2 off"). The rail answers all four arrows, Home and End, because below 1100px it folds into a grid of tiles.
- **Category header.** Every category starts with `set-head`: icon, title, one line on what it covers, and — when the
  role can change none of it or only some of it — "View only" or "Some of these need another role". Categories with
  sections carry them in the header (`pageTabs(…, { param: "section", split: true })`), so the sections read as part of
  the category, smaller than the rail. Choosing a category by hand opens its first section; Back, Forward and links
  restore the exact section in the address.
- **Rows.** `A.settingRow(label, hint, control, { lock: area })` marks a row this role can't change with the access it
  needs. On phones a switch stays beside its label; numbers and text take the line below.
- **Emergency.** A status board (what is running now, the one big stop or resume, its consequence), then switches for
  one provider at a time and the company browsers, then links to the stops that live elsewhere. Every stop still asks
  first. Text on a solid red fill uses `--on-bad`.
- **Home.** Only real values: the lead tool is the one opened most recently from here (or the only one), never a guess;
  no figure appears that doesn't help (no "0 used this week"); a tool is never shown twice; the allowance appears only
  when the person's budget is visible to them; Studio only when their services include it and they're active.

## Interface elevation after V2.2

The existing information architecture now has stronger page headings, calmer selection accents,
readable sentence-case panels/tables and aligned phone table fields. Staff catalogue filters
(`q`, `cat`, `show`, `sort`) live in the URL and have a reset action. Studio keeps separate media
forms while switching kinds/views, announces submission states and offers a read-only retry when
progress cannot be checked. The staff mobile bar includes Studio when it is available. Review notes,
limitations and repeatable optional browser checks are in [UI-ELEVATION.md](UI-ELEVATION.md).

## October 9 artwork and Settings refinement

Settings' Access & privacy category uses `?section=records|safeguards|staff`; older access links open
Records. Purpose & location and Providers & pricing retain their existing section URLs. Every section
begins with an explanation of its task and a compact saved-state summary. Forms still enforce role
permissions and guard unsaved changes before switching. See `docs/ART-SETTINGS.md` for supplied-art
selection and verification.

## Native Hub business workspaces (schema20)

Staff Adoption & impact is the home of longer-term declarations, scoped department views, business comparisons and export. Projects opens a focused source-linked deliverable sheet. Weekly reports remains a distinct per-tool accountability task. Requests separates operational tool access, procurement and department-report permissions; purchasing uses its own saved four-step wizard. The shared six-step adoption/report wizard preserves projects, conditional finances and eight-hour working days/forty-hour working weeks.

Admin Business value contains Overview, Reports inbox, Projects, Analytics and Management. Individual reports use a labelled section selector to reveal declaration, evidence, immutable history, review and authorised corrections; mobile decisions wrap without clipping. Weekly reporting retains its compact Overview, Records/review, Management and Policy views. Operational catalogue/licences remain authoritative and have their existing profiles.

Settings retain the category rail on desktop; a native labelled selector replaces the tall grid on narrow screens. Both drive the same URL-state tabs, child-section reset, history and dirty guard. Advanced retention is a disclosure; Discard restores controls in place without an asynchronous redraw that could overwrite a later edit. Staff Home shows three recent tool rows and a compact reporting reminder; the full catalogue is bounded/paginated. See HUB-UI-REVIEW.md for actual screenshots and inspected corrections.

On phones, tool categories use a labelled selector with preserved focus, filters, URL state, Back and refresh. Request tabs form readable labelled buttons; segmented filters wrap rather than hiding off-screen actions. Desktop category chips and page tabs retain their existing interactions.
