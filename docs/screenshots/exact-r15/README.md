# R15, piece 1: the console scene (BRIEF 10.3 "Scene", 10.6)

Builder's capture, not an acceptance. System Chrome headless through Playwright, local synthetic fixture
(`tests/browser/demo.py`), 10 November 2026.

## What changed (`gateway/static/admin.css` only)
- The signed-in console now sits in `room-warm.webp` with a `rgba(12,10,9,.35)` scrim (10.3: .30 to .40, not .78).
  Sign-in keeps `login-welcome.webp` and its own scrim.
- One backing plane behind the page column, painted behind the content so nothing moves.

## Files
`overview-<size>-<theme>.png` at 1440x852 and 390x844, dark and light; `people-1440x852-dark.png`;
`overlay-overview-1440x852-dark.png` (50% blend with `dashboard-01.jpg`); `contrast-summary.json`.

## Contrast (rendered pixels, worst pixel behind each text run, 8 console pages x 2 sizes x 2 themes = 32 cells)
Pages: Overview, People, Activity, Tools, Licences & spend, Security, Settings, Health.
- With the scene change alone, text outside a card failed: as low as 3.18 dark (hints) and 1.27 light.
- With the backing plane: every enabled text run that the scene affects is at 4.5:1 or more.
- Still below 4.5 and **not caused by this change** (same values before it): the white letter on a tool's own
  colour chip (`.logo.mono`, 3.79 to 4.2). Disabled pagers are below too and are outside WCAG 1.4.3.
- Measurement artifact: the selected phone-nav label reads 1.0 because the capture hides text colour and the pill
  is drawn with it; on screen it is dark text on a white pill.
- Not measured: icon and control (non-text) 3:1 contrast.

## Remaining differences, tagged with BRIEF 10.1
- 10.1(2): `room-warm.webp`, not the reference's photo.
- 10.1(3): the backing plane is `rgba(28,24,22,.82)` dark, radius 22. The reference has no such plane: its title and
  page actions sit straight on the room. It is here because bare text over the brighter room measured below 4.5:1.
  The room is visible around the plane, behind the rail and the top bar, less so through the page than in the reference.
- 10.1(3): light theme (no reference still) uses a `rgba(250,244,236,.42)` veil and a `.94` porcelain plane; the top
  bar's area label gets a porcelain backing in light only.
- **Not tagged, still to do in later R15 pieces (defects against 10.3, not allowed differences):** the rail is at
  x 17 to 91 with "All pages" and "More" words (target x 67 to 129, icons only, 9 page icons); the top bar has no
  accent New pill and its pills are 44px (target 38px); the page header keeps its eyebrow line; KPI cards are not
  four 285px cards. This PR does not claim the 4px overlay acceptance for the Overview.

## Not run
Any reference colour sampling (10.4), motion, scroll frame rate, axe, and the repo's browser suites locally (CI runs them).

# R15, piece 2: top-bar pill height and the page eyebrow (BRIEF 10.3 "Top bar", 10.7 "Page header")

Builder's capture, not an acceptance. Same tooling as piece 1. `gateway/static/admin.css` only, above 1200px wide.

## Measured at 1440x852 dark, Overview and People (target in brackets)
- Workspace pill, search, clock, bell and avatar: all 38px tall, centre y 38 [38px, centre y 38]: 0px.
- Bell and avatar 38px wide; avatar image 36px [36px]; workspace mark 24px [24px].
- The "MONITOR" eyebrow is no longer on the page [10.7: no eyebrow line]; the area is the text beside the workspace
  pill. It stays in the accessibility tree as the "You are here" landmark.
- No horizontal overflow at 1440, 1100 or 390.

## Unchanged on purpose, tagged
- 10.1(3): at 1200px and below the pills stay 44px and the eyebrow stays visible. Phones need 44px targets, and
  there the top bar has no room for the area text, so the eyebrow is the only place it shows.
- 10.1(4): a page with a real breadcrumb trail (links) keeps it above the title.

## Still defects against 10.3, not fixed here
Search pill is x 564 to 984, 420 wide [588 to 933, 345]; workspace pill x 148 to 314 [175 to 310]; no accent New pill;
clock x 1200 [1176 to 1252]; title x 148, centre y 108, about 38px tall [x 178, about y 93, 24px weight 600];
the rail (x 17 to 91, with "All pages" and "More" words) and the KPI row. These all hang off the rail's position
and width, which is the next piece.

Files: `piece2-overview-1440x852-dark.png`, `piece2-overview-390x844-dark.png`, `piece2-overlay-overview-1440x852-dark.png`.
Not run: axe, contrast re-measure (no colour or background changed), the repo's browser suites locally.

# R15, piece 3: the rail, the top bar's positions and the page header (BRIEF 10.3, 10.7)

Builder's capture, not an acceptance. Same tooling. `gateway/static/admin.js` and `admin.css`; the measured frame applies above 1200px.

## Measured at 1440x852, dark and light, on Overview, People and Health (target in brackets)
- Rail x 67 to 129, y 22 to 832 [67 to 129, 22 to 832]; brand 36x36 at (80, 30) [36x36 at y 30]; no words in the rail.
- Icon centres y 112, 157, 202 ... 517, 45px apart [from 112, 45 apart]; active is a 36px circle; Help y 758, Settings y 805 [758, 805].
- Workspace pill x 175 to 310 [175 to 310], two text lines; area text x 325 [325]; search x 588 to 933 [588 to 933];
  New x 1082 to 1165 [1082 to 1165]; clock x 1176 to 1252, time and date [1176 to 1252]; avatar 36px at x 1327 [1327].
  All 38px tall, centre y 38.
- Title text x 178, centre y 93, 24px weight 600 [178, about 93]; subtitle 11px, box y 111 to 129 [y 117];
  page actions right edge 1343, centre y 101, 34px tall [1343, 101, 34].
- Content column x 173 to 1343. No horizontal overflow at 1440, 1100 or 390; no page errors.

## What moved, and where it went (10.7 "drop the un-required", nothing removed from the product)
- The rail shows nine pages (Overview, Live, Needs attention, Activity, People, Access requests, Tools, Licences & spend,
  Security) and an All pages icon. The other ten pages, the emergency stop, theme and sign-out are in the All pages
  drawer (checked: 21 links, the stop button and the account block are there). Stop all AI is also in the command
  menu and Settings. When the page you are on has no rail icon, the All pages icon carries the selected circle (10.1(4)).
- The labels toggle, rail search, rail bell, group buttons and "More" scroll button are gone from the rail.
- New pill: Person, Tool, Policy, each opening the existing add form (`?add=1`); shown only to roles with `govern`.
  Keyboard: arrows, Home, End, Escape returns focus (checked by hand in the capture script, not in a committed test).

## Remaining differences
- 10.1(1): Hub names, counts and mark; no title emoji.
- 10.1(3): bell box is 38px at x 1261 to 1299 (centre 1280); the reference gives "x 1280" without saying which edge.
- 10.1(3): no presence dot on the avatar: the console has no presence evidence.
- 10.1(3): at 1200px and below the earlier rail (76px, 44px targets) and top bar stay; no New pill there.
- 10.1(3): 8px second lines in the workspace and clock pills are the reference's size; they are below a comfortable
  reading size and should be looked at in the accessibility review.
- **Still defects:** the KPI row is three joined cards, not four 285px cards with 12px gaps at y 140 to 292; theme, sign-out
  and Stop all AI are not yet in an avatar menu (10.7), only in the drawer; the backing plane from piece 1 remains.

## Contrast
Re-measured, 32 cells as in piece 1: every text run this piece touches is at 4.5:1 or more. The same pre-existing
items remain below (tool colour chips, disabled pagers). One new reading, "90 days" on Settings at 390 light (1.09),
is on a screen this piece does not restyle; not investigated, so treat it as open.

Files: `piece3-overview-1440x852-dark.png`, `-light.png`, `piece3-overview-390x844-dark.png`, `piece3-people-1440x852-dark.png`,
`piece3-overlay-overview-1440x852-dark.png`. Not run: axe, colour sampling, motion, the repo's browser suites locally.
