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
