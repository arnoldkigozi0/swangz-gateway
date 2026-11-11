# Design brief — "Glass" redesign of Swangz AI Hub

Arnold, 7 Nov 2026: *"This is the exact design I want. They can improve where necessary."*
Arnold, 8 Nov 2026: *"My boss said it needs an interface exactly like that."*
The four reference videos are the target look and motion. **Match them exactly** — same layout, sizes,
spacing, radii, colours, transparency, type scale and motion. The only allowed differences are the ones listed
in **§10 Exact match** (our words/data/brand, our licensed photos, and the accessibility, performance and phone
rules in §7). §10 holds the measured values and the acceptance check every UI PR must pass; where §10 and an
earlier section disagree, §10 wins.

| Reference | Video | Stills | Becomes |
|---|---|---|---|
| Glassy Dashboard V7 + CRM | `references/video/glass-dashboard-crm.mp4` | `references/stills/dashboard-01…07.jpg` | The control room (`admin.html`, `admin.css`, `admin-*.js`) and the staff app shell (`index.html`, `portal.css`) |
| Glassy login form V2 | `references/video/glass-login.mp4` | `references/stills/login-01…07.jpg` | Staff and admin sign-in |
| Glassy liquid footer | `references/video/liquid-glass-footer.mp4` | `references/stills/footer-01…06.jpg` | The footer of the staff app and the sign-in page |
| Glassy Navigation tabs V7 (added 9 Nov) | `references/video/glassy-nav-tabs.mp4` | `references/stills/nav-01…05.jpg` | Every tab strip inside a page (both themes) and the phone bottom tab bar of both apps — see **§10.8** |

Watch the videos, don't only read the stills: the motion is half of the design. Stills are 1-per-second crops
at 2x. The videos are Instagram posts by @code.xr. We copy the *design language*, never their assets, logos,
names ("Lumen CRM", "Vertix"), copy or background photos.

## 0. What this replaces
This brief supersedes two older visual rules in `CLAUDE.md`: the Oct 7 "Swangz Avenue Bookings" finish (tight
radii, outline-by-default buttons) and "keep imagery separate from controls and data". Glass over imagery *is*
the design now. Everything structural in `docs/UI.md` stays: one home per kind of information, tabs vs pages,
URL state, fewer tiles (the 4-up KPI row is the page's one `.kpis` strip), honest evidence labels.

## 1. The look in one paragraph
Frosted, smoked glass panels floating over a softly blurred photographic room. Panels are dark, translucent
and warm-tinted, with a 1px light rim and a faint top highlight. Generous radius (20–24px cards, full pills
for controls). One warm accent (amber/gold) used sparingly: the primary button, the selected bar, the first
KPI card. Big confident numbers, small quiet labels. Everything moves gently: cards lift on hover, pages
cross-fade with a blur, the footer fills like liquid.

## 2. Design tokens (define once in `tokens.css`, use everywhere)
Keep the Hub's brand: the reference's warm amber maps onto our existing `--primary` gold (#F5B32B) and
`--accent` champagne. Use the approved self-hosted Plus Jakarta Sans for UI text and headings (see §9). Add:

```css
--glass-bg:        rgba(28, 24, 22, .52);   /* smoked warm glass, dark theme */
--glass-bg-strong: rgba(22, 19, 17, .68);   /* tables, dense text */
--glass-bg-accent: linear-gradient(160deg, rgba(245,179,43,.38), rgba(120,72,24,.30)); /* first KPI card */
--glass-rim:       rgba(255, 255, 255, .10);
--glass-highlight: inset 0 1px 0 rgba(255, 255, 255, .08);
--glass-shadow:    0 20px 50px -20px rgba(0, 0, 0, .55);
--glass-blur:      blur(22px) saturate(140%);
--radius-card: 22px;  --radius-pill: 999px;
--lift: translateY(-5px);                    /* hover lift, from the reference code (whileHover y:-5) */
--ease-out: cubic-bezier(.22, 1, .36, 1);  --dur-1: 160ms; --dur-2: 280ms; --dur-3: 520ms;
```
The light "Porcelain" theme uses the footer reference: milky, warm, lighter glass (`rgba(245,240,234,.55)`)
with dark text. Both themes must be designed, not one auto-inverted.

## 3. Background layer
One fixed full-screen layer behind everything: our own `admin-welcome.webp` / `home-welcome.webp` /
`login-welcome.webp` (dark architecture with warm gold light), scaled to cover and darkened with a scrim so
glass text always passes contrast. Arnold may later supply real Swangz studio photos — the layer must take any
image. Never use the reference's photos.

## 4. Control room and staff shell (dashboard reference)
- **Icon rail sidebar:** a floating, rounded, dark-glass vertical pill on the left (not full height edge-to-edge).
  Brand mark at top in an accent rounded square. Icons only; the active item is a solid white circle with a dark
  icon; hover shows a small dark tooltip with the page name; count badges are small accent dots with numbers.
  Help and Settings pinned at the bottom. Keyboard: arrow keys move, Enter opens, tooltips also show on focus.
  Our sidebar has four groups — show them as spaced clusters in the rail; the full names live in the tooltip
  and in a "expand" state for people who prefer labels (keep the existing remembered preference).
- **Top bar (floating, no bar background):** workspace pill (avatar + name + chevron) → breadcrumb → centred
  search pill with ⌘K hint → right side: accent "New" pill, clock pill, bell with red count, avatar with green
  presence dot.
- **Page header:** big greeting or page title + one emoji/icon, one-line subtitle, actions right-aligned on the
  same line (ghost glass pill + accent pill). This matches `docs/UI.md` ("main action on the title's line").
- **KPI cards:** 4-up row. Small label top-left, arrow-in-circle button top-right, large value, delta chip
  (green up / red down, with the word, never colour alone), "vs last" caption. The first card uses
  `--glass-bg-accent`.
- **Charts (vanilla SVG/CSS, no chart library):** revenue/usage as rounded "glass tube" bars with a soft top
  glow; the selected/current bar is accent-gradient with a floating value label. Donut with a thick ring, gaps
  between segments and the total in the middle. Semi-circle gauge (CSAT-style) for a single health %. Line chart
  with gradient area fill and dot markers. Use `--viz-*` tokens; keep every value readable as text too.
- **Lists/tables:** inside a strong-glass panel; segmented filter pills top-right (All / VIP …) with a search
  pill; rows with avatar circle, status chips, slim progress bars and a star/favourite column.
- **Profile card (CRM "Sophia Reynolds" card):** use for the Person profile header: tier chip, active dot,
  avatar initials, mini sparkline in an inset glass well, tag chips, two buttons (solid white + ghost).
- **Motion:** card hover = `--lift` + slightly brighter rim (`--dur-2`); page change = old content fades and
  blurs out, new content fades/blurs in and rises 8px (`--dur-3`, see dashboard-06); numbers count up once on
  first load; bars grow from 0 on first view.

## 5. Sign-in (login reference)
- One large glass card split into two panels by a **slanted seam**. One panel holds the form, the other a big
  bold heading ("WELCOME BACK!" style, uppercase, heavy weight) with a line of text and a ghost pill button.
  The panels **swap sides with a slide** when you switch mode (see login-03/04 mid-transition).
- Underline inputs with a leading icon; the focused field's underline brightens to white. Full-width pill
  primary button. Small text links underneath.
- **Improve for the Hub:** there are no passwords and no self sign-up. Modes are (a) *Continue with Google*
  (company account) and (b) *Email me a sign-in code* → code entry. The panel swap animates between those two
  modes. Keep every existing security behaviour of sign-in exactly as it is (this is critical work: @Sentinel
  reviews it); the redesign is visual only.
- Background: graphite, angular 3D shapes, blurred — use `login-welcome.webp` darkened.

## 6. Liquid glass footer (footer reference)
- A wide, light, milky glass panel. Left: logo + one bold line + one input pill with a dark button. Right: a
  nested, lighter glass card with link columns. Bottom row: © line + green "All systems normal" status, a
  pill group of icon links, and a theme switch ("Evening" ⇄ "Daylight").
- Signature move: as the footer scrolls into view, it **fills up like liquid** — a wavy top edge rises and
  settles (footer-01 → 03), then content fades in. Then a **giant cut-out wordmark** ("Swangz") across the
  bottom shows the background through the letters.
- **Improve for the Hub:** the status dot shows the real gateway health; the input becomes "Ask for a tool"
  (creates an access request) instead of a newsletter; links go to Privacy, Devices, Requests, Help.

## 7. Where we improve on the reference (required)
1. **Contrast:** every text on glass ≥ 4.5:1 (≥ 3:1 for large numbers) in both themes, measured over the
   brightest part of the background. Add scrim or raise opacity, never thin the text.
2. **Performance on weak devices:** at most one blur layer under any pixel (no glass on glass except the
   footer link card); no blur on scrolling lists' rows; `@supports not (backdrop-filter: blur(1px))` and
   `prefers-reduced-transparency` fall back to solid `--ink-2` surfaces. Animate transform and opacity only.
   Target 60 fps on this laptop and CLS 0.
3. **Reduced motion:** `prefers-reduced-motion` turns lift, liquid fill, count-up and blur transitions into
   simple fades.
4. **Phones (the references are desktop-only):** at ≤ 700px the rail becomes a bottom tab bar (exactly the §10.8 bar C),
   KPI cards 2-up, charts full width, tables become cards, the sign-in card stacks (heading panel on top, small),
   the footer stacks and the wordmark scales to width.
5. **Real data only:** every number, chart and list comes from existing endpoints. Never fake data client-side;
   ask @Forge for an endpoint.
6. **Accessibility:** keyboard reachable everything, visible focus rings (accent, 2px, offset), tooltips on
   focus, ARIA for tabs/segmented controls as in `docs/UI.md`.

## 8. Suggested PR-sized order (30–60 min each)
1. Tokens + background layer + glass utility classes + fallbacks (`tokens.css`, `ui.css`).
2. Icon rail sidebar (control room).  3. Floating top bar + search pill + clock + bell + avatar.
4. Page header + KPI glass cards + hover lift.  5. Glass tube bar chart.  6. Donut + gauge + line chart.
7. Glass table + segmented filters + progress bars.  8. Person profile glass header card.
9. Page transition (blur cross-fade) + count-up + reduced motion.  10. Sign-in split card + panel swap (critical).
11. Liquid footer + cut-out wordmark + theme switch.  12. Staff app shell adopts the same system.
13. Phone layouts pass.  14. Light "Porcelain" glass theme pass.

Each UI PR: screenshots at 390×844 and 1440×900, light and dark, in `docs/screenshots/<task>/`, next to the
matching reference still, with one line per difference that remains.

## 9. Decisions (Arnold, 7 Nov 2026)
- **Font: Plus Jakarta Sans** (SIL Open Font License) for all UI text and headings, replacing Archivo. Self-host
  the variable woff2, latin subset only, with its `OFL.txt`, in `gateway/static/fonts/` (strict CSP: no Google Fonts
  link). Weights 400–800. Numbers in KPIs, tables and charts use `font-variant-numeric: tabular-nums`. Done in R1.
- **Photos:** Swangz's own artwork and photos first (`*-welcome.webp`, and any photos Arnold adds later). Where a
  screen needs a closer match to the references, use freely licensed photos (Unsplash or Pexels licence) of warm,
  softly lit interiors like the dashboard and footer references, or dark angular 3D surfaces like the login
  reference. Optimise to WebP ≤ 200 KB, and record each in `docs/design/ASSETS.md` (file, source URL, author,
  licence, date). Never use the reference creator's photos, logos, names or copy.

## 10. Exact match (Arnold, 8 Nov 2026) — this section wins over everything above

"Like the reference" is no longer enough: a reviewer puts the Hub screenshot next to the reference still and
any difference that is not on the allowed list below is a defect. Rounds already merged (R1–R3, R5, R7) are
re-checked against this section in **R15** (below), not re-opened one by one.

### 10.1 Allowed differences (the only ones)
1. **Words, data and brand:** Hub page names, real numbers from real endpoints, the Swangz "S" mark instead of
   their logo, our names instead of "Lumen CRM" / "Vertix" / "Barbara". Same *positions, sizes and styles* though.
2. **Photos:** ours, never theirs (§9). The control room and staff app use `static/room-warm.webp`; sign-in keeps
   `login-welcome.webp` (dark angular, matches the login reference).
3. **§7 improvements:** contrast ≥ 4.5:1, one blur layer, reduced motion/transparency fallbacks, phone layouts,
   keyboard and ARIA. When one of these forces a change, the PR says which rule and by how much.
4. **Features the reference has no room for** (more pages than its 10 rail icons, the Hub's sign-in modes):
   solved in the reference's visual language, listed in the PR.
5. **The §10.9 additions** (Swangz signatures, honest low-data states, compact density, quality gates) — they sit on
   top of the matched layout and never move or resize a measured element.
6. **§10.10 (boss review, 10 Nov):** box-shaped controls, the layered page structure, the new background, and the
   side bar and scrollbar design. Where §10.10 and a reference still disagree, §10.10 wins.
7. **Overview background below the panels (reason: photo).** The reference reads 119,105,98 at (700,810); no part of
   `room-warm.webp` is bright enough to land within ±16 there at any crop, zoom, flip or scrim in the .30–.40 range
   (analysis in `docs/screenshots/console-room/README.md`). Allowed until a different photo is chosen.
   The console photo was replaced on 11 Nov (§10.10.3, `room-suite`); this point has not been re-measured with it.

### 10.2 Acceptance check (every UI PR)
- Screenshot at **1440×852** (the stills' frame) dark theme, next to the matching still, plus a **50% overlay**
  (`docs/screenshots/<task>/overlay-*.png`). Positions and sizes within **±4px**, radii within ±2px.
- Colour: sample the same points the table below lists; each channel within **±16** of the reference sample
  (video compression darkens the stills, so the targets below are already corrected — use those, not the jpg).
- Motion: step the reference video frame by frame (`ffmpeg -ss <t> -i references/video/<file>.mp4 -vf fps=30
  frames/%03d.png`) and match start, duration and easing of each transition within ±2 frames.
- One line per remaining difference, each tagged with its §10.1 number. No tag = not mergeable.

### 10.3 Measured layout, 1440×852 (from `dashboard-01/03/05`, `login-02/05`, `footer-04`)
| Element | Exact values |
|---|---|
| **Scene** | Warm, mid-tone room filling the screen (`room-warm.webp`), scrim **rgba(12,10,9,.30–.40)** — not .78. Visible room around and through every panel is the point of the design; the background must read as a room, not as black. |
| **Rail** | Floating pill x **67–129** (62 wide), y **22–832** (inset 22 top / 20 bottom), radius 31, `rgba(30,26,24,.80)`, 1px rim. Brand square 36×36 at y 30, radius 10. **Icons only, 18px, centres 45px apart** starting y 112; active = solid white circle **36px** with dark icon; badges 14px accent circles at the icon's top-right. Help + Settings at y 758 and 805. No visible words in the collapsed rail ("All pages", "More" become icons with tooltips — §10.1.4). Tooltip: dark pill right of the icon, 11px. |
| **Top bar** | No bar background. All pills **38px tall**, centre y **38**. Workspace pill x 175–310 (avatar 24px + 2 text lines + chevron) → breadcrumb text x 325 → search pill x **588–933** (345 wide, ⌘K chip at its right) → accent **New** pill x 1082–1165 → clock pill x 1176–1252 (time + date, 2 lines) → bell x 1280 (red count dot) → avatar 36px x 1327 with green presence dot. |
| **Page header** | Title x **178**, cap height ≈ 18px (24px, weight 600, white) + one emoji; subtitle 11px muted at y 117. Page actions right-aligned, right edge **1343**, centre y 101, pills 34px tall (ghost glass + accent). |
| **KPI cards** | Row y **140–292** (152 tall), four cards 285 wide, 12px gaps, first at x 173. Radius **18**. Label 11px at (18, 22); arrow-in-circle 24px top-right; value 24px weight 700 bottom-left (baseline y 255); delta chip right of value; "vs last" caption 9px under. First card accent glass, others dark glass `rgba(28,24,22,.52)` — the room must stay visible through them. |
| **Big panels** | Radius 22, padding 18; eyebrow 9px caps letter-spaced accent; title 15px weight 600; inner KPI groups separated by space, not lines. Segmented pill group (Q1–Q4) with a white selected pill. |
| **Login card** | Centred, **1150 × ~640**, radius 24. Two panels split by a **slanted seam** (top x ≈ 595 → bottom x ≈ 665, ~6°). Form panel darker (`rgba(20,20,24,.55)`), heading panel lighter (`rgba(70,74,78,.35)`). Heading **40px, weight 800, uppercase, 2 lines**; body 16px. Underline inputs: 1px `rgba(255,255,255,.14)`, focused 2px white; leading 18px icon. Primary button full-width pill **56px**, translucent grey glass, white 16px weight 600; ghost pill 230×54 with 1px rim and "→". Panels swap by sliding (see video), ≈ 600ms ease-in-out. |
| **Footer** | Milky warm glass panel x 30–1410, radius 28 (`rgba(235,220,205,.55)` over the room). Left: logo + 32px weight 600 two-line heading in near-black, input pill 380×46 with a dark button inside. Right: nested lighter card x 590–1375, y 157–378, radius 20 (`rgba(255,255,255,.30)`), 4 link columns (12px muted heading, 14px links, 28px rows). Bottom row y 434: © + green status dot · icon pill group · Evening switch. Giant cut-out wordmark ≈ 240px tall spanning the width. |

### 10.4 Colour targets (corrected for video compression)
| Token | Value | Use |
|---|---|---|
| `--accent-pill` | `linear-gradient(180deg, #F7AE62, #EE8F3E)`, text `#2A170A` | New, primary page action, selected bar, first KPI card tint — the reference's amber-orange. Keep `--primary` gold for the brand mark only. |
| `--glass-bg` (dark) | `rgba(28,24,22,.52)` (unchanged) — correct **only** over the room at scrim .30–.40 | KPI cards, panels |
| Active rail item | `#F2EEEC` circle, icon `#1C1816` | |
| Delta up / down | `#7BC47F` on `rgba(123,196,127,.16)` / `#F07A7A` on `rgba(240,122,122,.16)` | always with the word |
| Presence / status | `#3DDC84` | avatar dot, "All systems normal" |

### 10.5 Typography — DECIDED (Arnold, 8 Nov: "make everything exact")
**Poppins** (OFL) for the console and staff app, **Inter** (OFL) for sign-in, replacing Plus Jakarta Sans. Self-hosted
latin woff2 files are already in `gateway/static/fonts/` on the WIP branch (see 10.7) with their `*-OFL.txt`.

### 10.6 New round
**R15 — exact-match pass** (after the open drafts merge): switch the scene to `room-warm.webp` with the §10.3 scrim,
re-balance contrast for it (raise panel opacity locally where text fails, never the scrim back to .78), bring the
rail and top bar to §10.3, and re-shoot R1–R7 against the stills with overlays. Then R10 (sign-in) and R11
(footer) are reviewed against 10.3 before they merge.

### 10.7 Decisions, 8 Nov 2026 (later) — Arnold: "make everything exact, drop the un-required"
- **Who builds:** the OpenMaus team builds all of it. Claude only writes this brief and reviews against §10.
- **Deadline: 20 November 2026.** This brief is on main from 8 Nov so every branch has it; branch from main, not from #53.
- **Accent:** the reference's amber-orange everywhere the reference uses it (`--accent-pill`, §10.4). Gold only for
  warnings. **Fonts:** §10.5.
- **Drop the un-required:** anything on a screen that the reference does not have is removed *from that screen* —
  not from the product. It stays reachable through the "All pages" drawer, the ⌘K menu or the avatar menu. Concretely:
  - Rail: brand square + **9 page icons** (Overview, Live, Needs attention, Activity, People, Access requests, Tools,
    Licences & spend, Security) + an **All pages** icon; Help + Settings at the foot. No labels toggle, no search/bell in
    the rail, no "All pages"/"More" words, no group buttons, no emergency block, no account block in the rail.
  - Theme switch, Sign out and **Stop all AI / Resume** move to the **avatar menu** in the top bar (emergency also stays in
    ⌘K and Settings → Emergency — it must never become unreachable).
  - Page header: no eyebrow/area crumb line; title + emoji, one 11px line, actions right. Breadcrumb lives in the top bar.
  - Overview = dashboard-02 exactly: "Hello, <name>! 👋", 4 KPI cards (AI spend [amber], AI requests, Active people,
    Security events), tube chart "AI usage" (8 days) left, two count cards (need attention · live requests), donut
    "Uses by tool" with legend. The old Right now / Trends / Top tools / Licences tabs leave the Overview (each already
    has its own page).
  - Sign-in (both apps) = the split card only: no side art, no feature bullets, no "Swangz Avenue · Company access only"
    footer. Mode A "Login" (underline fields with icons, eye toggle, Login pill, Google button when configured) ↔ mode B
    "Get access" (no self sign-up exists: explains admin-made accounts); greeting panel "HELLO, FRIEND!" ↔ "WELCOME BACK!".
  - Background: control room + staff app on `room-warm.webp`, scrim ≈ .16–.34; sign-in on `login-welcome.webp`.
- **Starting point (WIP, not reviewed, not tested):** branch `design/exact-match-brief` (PR #53, draft) carries a first pass
  by Claude: `static/exact.css` (tokens, rail, top bar, header, KPI/stat/donut, pop menus), `exactRail()` + top bar +
  `popMenu/newMenu/accountMenu` in `admin.js`, the rebuilt Overview in `admin-monitor.js`, `SUI.splitGate/xfield/eyeToggle`
  in `ui.js`, and both sign-ins switched to it — **the sign-in CSS is not written yet** and the browser suites have not
  been re-run. Take it, finish it, or replace it; it must pass the full test suites and the §10.2 check before merge.

### 10.8 Navigation tabs — reference 4 (Arnold, 9 Nov 2026: "if it has a place, use it, and exact")
Video `references/video/glassy-nav-tabs.mp4` (9.3 s, 720×1280, 30 fps, @code.xr), stills `nav-01…05.jpg`
(720×430 crops: 01 start, 02 rest, 03/04 lens mid-drag, 05 settled on "Saved"). It shows three bars over the same kind
of warm room, so it drops straight into our scene. **Where each bar goes:**

| Bar (still nav-02) | Becomes | Shape (H = bar height; values measured on the 720-wide stills, verify with §10.2) |
|---|---|---|
| **A** — smoky glass, light labels, **white raised pill** on the active tab, soft warm glow under it (Home · Discover · Library · Messages · Profile) | Every in-page tab strip (`role="tablist"`: page tabs, Settings sections, profile tabs, report tabs) in the **Evening (dark)** theme | Full-pill bar, H ≈ 52 (x 127–620 on the still → 9.5 H wide for 5 tabs; tabs share the width evenly). Active pill inset ≈ 0.1 H, height ≈ 0.82 H, full radius, `#F4F1EE`, text `#1E1A18`, warm glow `0 0.15H 0.35H rgba(238,143,62,.35)` under it. Inactive labels ≈ `#ECE7E2`. Icon ≈ 0.27 H + label ≈ 0.28 H font, gap ≈ 0.17 H. 1px light rim. |
| **B** — milky white glass, dark labels, **black pill** on the active tab (User · Overview · Projects · Alerts · Settings) | The same tab strips in the **Daylight (light)** theme — B is A inverted, so one component with two theme skins | Same geometry as A, gap between A and B in the video ≈ 0.85 H. Bar `rgba(240,236,232,.55)` + 1px `rgba(255,255,255,.6)` rim; active pill `#141210` (≈ .92), text white; inactive `#2E2A27`. |
| **C** — milky icon bar + separate round button with a red count badge; the active item is a soft grey pill with a **filled** icon + its label (Home → Search → Saved) | The **phone bottom tab bar** (≤ 700px, §7.4) of both apps. Control room: Overview · Live · Needs attention · People, round button = All pages (badge = items needing attention). Staff app: Home · Search tools · Saved tools · Alerts, round button = Access requests (badge = pending). | Bar x 211–473 on the still (≈ 5 H wide, H ≈ 52) + round button H×H, 10 px apart (≈ 0.19 H). Active pill ≈ 2 H × 0.8 H `rgba(60,50,44,.10)`, icon filled, label weight 600. Inactive = outline icons only, no labels. Badge ≈ 0.3 H `#E5383B` circle, white number, at the button's top-right. Sits 12 px above the safe-area inset, centred. |

**Motion (the signature — step the video at 30 fps and match within ±2 frames, §10.2):**
- **A/B:** the active pill **slides** to the new tab (transform + width only, no layout animation) with a small
  overshoot; the labels cross-fade colour as it passes. Measure start/duration in the video (≈ 0.8–1.6 s, Home → Library).
- **C, the liquid lens (≈ 2.6–5.3 s):** on pointer-down a clear **liquid-glass lens** appears over the pressed item:
  ≈ 2.1 H wide × 1.15 H tall (it overflows the bar top and bottom), 1px light rim, the background seen through it is
  magnified/refracted and slightly darkened. While the pointer is held it **follows the pointer** across the bar;
  on release it shrinks into the grey active pill on the item under it (≈ 6–8 frames), the icon fills and the label
  slides out; the previous item collapses back to an outline icon. A tap without drag does the same in place.
- Implementation hints (not requirements): Chromium supports `backdrop-filter: url(#lens)` with an SVG
  `feDisplacementMap` for the refraction; elsewhere use `backdrop-filter: blur(2px) brightness(.9)` + `scale(1.08)`.
  The lens exists only during the gesture, so it is the one allowed glass-on-glass besides the footer card (§7.2).
**§7 still applies:** `role="tablist"`/`tab`, `aria-selected`, arrow keys move and Enter/Space select (the lens is
pointer-only decoration; keyboard shows the accent focus ring), every label ≥ 4.5:1 on its bar, reduced motion =
the pill cross-fades and no lens, reduced transparency = solid bars. Hub names, icons and counts replace theirs
(§10.1.1); the cart becomes our button above, never a shopping cart.
**New round R16 — navigation tabs** (after the v18 backlog lands): one `SUI.tabs` component with the A/B skins replacing
the current tab strips, then the C bottom bar for both apps at ≤ 700px; screenshots at 390×844 and 1440×852 in both themes
plus a frame-stepped comparison of the slide and the lens against the video.

### 10.9 Beyond the reference (Arnold, 10 Nov 2026) — what lifts the finished Hub from ~7.5 to ~8.5 against the market
Matching the references makes the Hub the best-looking product in its category, but leaves four weaknesses: it is a
copy of public Instagram designs, it is built for big demo numbers while ours are small, it shows few numbers per
screen for daily admins, and glass designs fail when contrast and smoothness are not policed. These four fixes are
required. They are §10.1.5 allowed differences: they never move or resize anything measured in §10.3/§10.8.

**1. Two Swangz signatures (originality).** Everything else stays exact; these two make it ours:
- **Liquid "S" loader:** every loading state (page load, panel refresh, Live connecting) is the Swangz "S" mark filling
  with the amber liquid from the footer's wave motion (same wave curve and easing as `footer-01→03`), never a generic
  spinner or skeleton shimmer. 24px in panels, 48px for a full page. Reduced motion = a static S at 60% opacity.
- **Amber live pulse:** the one value on a screen that is changing *right now* (live requests, a seat in use, the
  "Needs attention" count) gets a slow amber ring pulse (2.4 s, opacity .0→.35→.0, transform only) — the Hub's
  "this is alive" mark. At most one pulse per screen; none under reduced motion.
- The footer's giant cut-out **"Swangz" wordmark** (§6) stays and is also the sign-in page's only background mark.

**2. Honest low-data states (our numbers are small).** Glass cards built for "$99,560" look broken with "$0.0054":
- Money: below $0.01 show **"< $0.01"**, below $1 show 2 decimals, never more than 2 decimals anywhere. Counts of 0
  show "0" with a one-line reason ("No requests in 7 days").
- A card or chart with no data shows a **purposeful empty state** inside the same card size: one 15px line on what
  will appear, one 11px line on why it is empty, and one action pill (e.g. "Grant a tool" → Access, "Connect a
  provider" → AI providers). Same glass, same position — the layout never collapses.
- Charts with fewer than 3 data points show the truthful empty state from `SUI.line` (#45) plus "Collecting since
  <date>". Never fake, pad or demo-fill data (§7.5).
- Review each Overview card with today's real laptop data and with a fresh empty database; both screenshots go in the PR.

**3. Compact density for daily admins.** A **Comfortable / Compact** switch in the avatar menu (remembered per admin,
default Comfortable). Compact applies to list/table pages only (People, Activity, Tools, Licences & spend, Access
requests, Security, Devices): rows 32px, 12px text, table body on `--glass-bg-strong` (no see-through behind dense
text), sticky header, column sorting kept, 2× the rows per screen. Cards, Overview, sign-in and footer never change.
The reference look is Comfortable; Compact must still pass §7 contrast and keyboard rules.

**4. Quality gates that block merging (so the build cannot cut corners).** Every UI PR, checked by Probe — FAIL if
any is missing:
- **Contrast:** automated axe run in the browser CI job in both themes **plus** a sampled check of every text style
  over the brightest point of `room-warm.webp` behind it: ≥ 4.5:1 (≥ 3:1 for ≥ 24px numbers). Report the worst value.
- **Smoothness:** a Chrome performance trace on this 7 GB Celeron laptop (or CI with 4× CPU throttling) scrolling
  the Overview and opening a tab with the lens: no long frames > 50 ms, ≥ 55 fps, CLS 0. One blur layer per pixel (§7.2).
- **Fallbacks:** screenshots with `prefers-reduced-transparency`, `prefers-reduced-motion` and no `backdrop-filter`
  support — the page must still read clearly.
- **Low data:** the empty-database screenshot from point 2.

**Round R17 — "beyond the reference"** (after R15 and R16): the S loader + live pulse, the low-data pass over every
Overview card and chart, and the Compact switch. Points 2 and 4 apply to every UI PR **from now on**, not only R17.

### 10.10 Boss review, 10 Nov 2026 (late) — structure, box controls, background, side bar and scrollbars

Arnold's boss: "the design is good", but (1) too many things sit on one page — the app must be directive and
layered, data chained from one level to the next like a professional product; (2) buttons must be boxes, not ovals
or pills; (3) the background is below standard; (4) the side bar and scroll bars must be properly designed.
**This section wins over §10.1–§10.9 wherever they disagree** (it is §10.1 allowed difference 6). The glass
material, colours, type, card sizes and the measured positions of §10.3 stay.

**1. Layered structure — one page answers one question.** Every screen in both apps is exactly one of four levels:

| Level | What it is | What may be on it |
|---|---|---|
| **L1 Summary** (area landing: Overview, Money, Security…) | "How is this area doing?" | Title, ≤ 4 number cards, **one** chart or **one** short list (≤ 5 rows, "See all" link). Nothing below the fold at 1440×852. |
| **L2 List** (People, Tools, Activity, Requests…) | "Which ones?" | One table or card list, one filter row (search + ≤ 3 filters), one primary action. No charts, no second table. |
| **L3 Record** (one person, one tool, one request, one device) | "What about this one?" | Header (name, state, primary action) + tabs; each tab holds one block. |
| **L4 Action** (add, edit, grant, revoke, approve) | "Do it." | A side sheet or dialog over the page it came from: ≤ 6 fields per step; longer forms become numbered steps. |

- **The chain:** every number on an L1 card is a link to the L2 list already filtered to exactly those items (the card
  "3 need attention" opens the list showing those 3). Every L2 row opens its L3 record. Every L3 record links to its
  related records (person → their tools → tool → its licence → its spend → the requests behind that spend), so a
  reader can walk the data without using the menu. No dead ends: every record has a way on and a way back.
- **The trail:** the top-bar breadcrumb shows the whole chain (`Overview › Needs attention › Nansubuga Grace`), each
  crumb is a link, Back returns to the same filter and scroll position, and the address carries the level and filter.
- **Directive:** one primary (amber) button per screen. Each L1 and L3 has one "Next step" line under the title that
  names the most useful thing to do now and links to it; when nothing needs doing it says so in one line.
- **Limits a reviewer counts:** at 1440×852 an L1 shows ≤ 7 blocks and does not scroll; no page mixes a table with
  charts; no tab strip has more than 6 tabs; no page has two tab strips; nothing is repeated on two pages — the
  second place links to the first (`docs/UI.md` "Canonical homes").
- **Before building:** one table in `docs/UI.md` ("Page levels") listing **every** page of the console and the staff
  app with: level, the one question it answers, its parent, its children, what leaves it and where that goes.
  Content that leaves a page is never deleted from the product (§10.7 rule); it moves down a level.
- Order: Overview → People chain (list → person → their tools) → Tools chain → Money chain → Security chain →
  Settings → staff app (Home → tool → request access).

**2. Box controls, not pills.** New tokens in `tokens.css`; no control uses `--radius-pill` any more:

| Token | Value | Used by |
|---|---|---|
| `--radius-control` | **10px** | Buttons (38px and 34px tall), inputs, search field, selects, workspace switcher, clock, "New", page actions, sign-in Login button and its fields' focus frame, footer input and its button |
| `--radius-control-sm` | **8px** | Small buttons (≤ 30px tall), the active marker inside a tab strip, menu rows, table row hover |
| `--radius-chip` | **6px** | Status chips, count badges with text, filter tags, keyboard hints (⌘K) |
| unchanged | 18 / 22 / 24 / 28 | Cards, panels, sign-in card, footer panel |

- Still round, because they are not buttons: avatars, status dots, the bell's number dot, the donut, the arrow-in-
  circle on KPI cards.
- Tab strips (§10.8 A and B): the bar is radius **12**, the active marker is a raised box radius **8**; it still
  slides and keeps the same timing. Phone bar C: bar radius **16**, active item radius **10**; the lens becomes a
  rounded box of the same radius and keeps its motion.
- Buttons: 38px tall (34px in page headers), padding 0 16px, 13px weight 600, icon 16px with 8px gap. Three kinds
  only — primary (amber fill), secondary (glass, 1px rim), quiet (no fill until hover). Destructive = secondary with
  the danger colour, never a red fill except in the confirming dialog. Hover lifts brightness, pressed moves 1px,
  focus is a 2px ring 2px outside the box; disabled is 45% opacity and not clickable.
- Acceptance: a search of `gateway/static/*.css` and `*.js` finds `999px` / `--radius-pill` / `border-radius: 50%`
  only on the round items listed above. Probe lists every remaining use.

**3. Background to a professional standard.** `room-warm.webp` is 1600×947 at 26 KB: it is soft, blocky in the
dark areas and its composition fights the cards. Replace it; the scrim and glass values are then re-tuned once.
- Source ≥ **3840×2160**, shipped as WebP at 2560, 1920 and 960 wide (`image-set`), quality ≥ 82, the 1920 file
  between 180 and 420 KB. No visible banding or blocks in the dark gradients at 100% zoom on a 1440×852 window.
- Content: a calm warm interior or architectural space, out of focus or shallow depth, **one** soft light source,
  mid-tone (average brightness 30–45%), no people, faces, text, screens, logos or strong lines crossing the card
  area. The busy part of the picture sits behind the rail or the page margin, not behind the numbers.
- Licence: CC0, Unsplash or Pexels licence only, logged in `docs/design/ASSETS.md` with source address, author,
  licence and the edits made. Never a reference photo, never an AI-generated picture of a real place.
- Deliver **three** candidates as 1440×852 Overview screenshots in dark and light in the PR; ship the one with the
  best worst-case text contrast (§10.9.4) and keep the other two in `docs/design/backgrounds/` so Arnold can swap
  with a one-line change. Sign-in gets the same quality pass (`login-welcome.webp` is 47 KB).
- Fallback when the photo cannot load or transparency is reduced: a designed gradient (two warm radial lights on
  near-black, with 2% noise so it does not band) — never a flat black page.

**4. Side bar, scrollbars and sliders.**
- **Side bar (rail):** radius **16** (was a full pill), same position and width. Icon buttons 40×40, radius 10,
  centred; active = raised glass box + amber 3px marker on its left edge + filled icon; hover = faint box. A label
  tooltip appears to the right after 300 ms and immediately on keyboard focus. Groups are separated by 12px of
  space, not lines. The "All pages" drawer opens as a second layer beside the rail with the same L1 areas as
  headings and their L2 pages under them — it is the map of §10.10.1, in the same order as the breadcrumb.
- **Scrollbars:** one style everywhere (page, panels, tables, drawers, menus): 8px wide, thumb radius 4,
  thumb `rgba(255,255,255,.22)` (dark) / `rgba(0,0,0,.25)` (light), hover .40, transparent track, 2px inset from
  the panel edge; `scrollbar-width: thin` + `scrollbar-color` for Firefox, `::-webkit-scrollbar` for Chrome. A
  panel never shows two scrollbars; tables scroll inside their panel with a sticky header; no horizontal page
  scroll at any width. `scrollbar-gutter: stable` so pages do not shift when a bar appears.
  **Ruling (Chief, 11 Nov):** `scrollbar-gutter: stable` is set on boxes that scroll inside a page (the rail's list,
  scrolling lists), not on `html`; the page itself is left as it is.
- **Range sliders and progress bars:** track 4px, radius 2; filled part amber; slider thumb a 16×16 box, radius 5,
  white with a 1px rim, 2px focus ring; the value is shown as text beside it.

**5. The control kit — use the right control, built once, used everywhere.** Pages are structured by choosing
controls that hide what is not needed now. All of these live in `ui.js` / `ui.css` as one shared kit (`SUI.*`) used by
both apps; no page builds its own. Vanilla JS and CSS, no new dependencies.

| Control | Use it for | Rules |
|---|---|---|
| **Dropdown select** | Choosing 1 of 5+ options (team, tool, role, period, sort) | Box trigger with the current value + chevron; menu opens under it, 8px radius rows, tick on the current one, type to jump, a search field inside when > 8 options. Fewer than 5 options and space allows → segmented control instead. |
| **Menu button ("More ⋯")** | Secondary actions on a page, card or table row | Every table row ends in one `⋯` button; a page header shows the primary button + at most one secondary + `⋯`. Destructive items last, separated, danger colour. |
| **Split button** | A primary action with close variants ("Add person ▾" → Add one · Import list · Invite by email) | Main part does the common action; the chevron part opens the variants. |
| **Segmented control** | Switching the view of the same data (Day · Week · Month; Cards · Table) | 2–4 options, box style of §10.10.2; remembered in the address. |
| **Tabs** | The parts of one record (L3) | ≤ 6; the rest go under a "More ▾" tab dropdown. |
| **Filter bar** | Narrowing an L2 list | Search + ≤ 3 dropdown filters + "More filters ▾"; each active filter shows as a removable chip under the bar with "Clear all"; filters live in the address so a link reproduces the list. |
| **Date range picker** | Any period choice | Dropdown with presets (Today, 7 days, 30 days, This month, Custom) + a two-month calendar for Custom; always shows the chosen range as text. |
| **Disclosure / accordion** | Detail most readers do not need ("Advanced", raw record, history) | Closed by default, chevron + one-line summary of what is inside; state remembered per page. |
| **Side sheet** | L4 add / edit / grant, and row preview | Slides from the right, 480px (full width on phones), title + one-line purpose, sticky footer with Cancel (quiet) and the primary button, Esc closes, unsaved changes are confirmed. |
| **Stepper** | Any form over 6 fields | Numbered steps along the top of the sheet, Back / Next, a final review step before saving. |
| **Dialog** | Confirming something destructive or irreversible only | Says what will happen and to whom, in plain words; the confirm button names the action ("Remove access"), never "OK". |
| **Tooltip / popover** | Explaining an icon, a number or a term | Tooltip = one line on hover/focus; popover = a small card on click (how a number was calculated, with a link to the list behind it). |
| **Pagination** | Lists over 25 rows | 25 / 50 / 100 per page dropdown, "1–25 of 312", previous/next; sticky table header; bulk-select bar appears only when rows are ticked. |
| **Toast** | Result of an action | Bottom-right, one line + Undo where the action can be undone; errors stay until dismissed and say what to do next. |
| **Breadcrumb with dropdown** | The trail of §10.10.1 | Each crumb is a link; the last-but-one crumb has a chevron listing its sibling pages, so a reader can move sideways without the menu. |
| **Command menu (⌘K)** | Jumping anywhere | Already exists: must list every L1/L2 page and every primary action, grouped by area. |

- **Every control has every state designed:** default, hover, focus (2px ring), pressed, open, selected, disabled,
  loading (the S loader inside the box, width does not jump), error (message under the field, never colour alone),
  and empty. One screenshot sheet per control in dark and light goes in `docs/design/kit/`.
- **Keyboard and screen readers (required, not optional):** every menu and dropdown opens with Enter/Space/↓, moves
  with arrows, closes with Esc and returns focus to its trigger; correct roles (`menu`, `listbox`, `tablist`,
  `dialog` with focus trap); touch targets ≥ 44px on phones; menus flip when they would leave the screen and become
  a bottom sheet on phones.
- **Forms, international grade:** label above the field, hint under it, required marked in words, validation on
  leaving the field, the first error focused on submit; dates as "10 Nov 2026", times with the zone, money with the
  currency code, numbers with thousands separators; every table column sortable with a visible arrow, numbers
  right-aligned, long text cut with an ellipsis and shown in full in a tooltip.
- **Consistency a reviewer checks:** one name per thing across the whole product (never "Remove" on one page and
  "Delete" on another for the same act); the primary button is always in the same place (page header right; sheet
  footer right); spacing only from the 4 / 8 / 12 / 16 / 24 / 32 scale; icons from one set at one stroke width.
- **Build order:** the kit page first (`/admin#kit`, visible to owners only: every control in every state), then
  pages adopt it chain by chain in the order of §10.10.1. A page is not "restructured" until it uses only kit controls.

**6. Bookings-grade buttons and layering (Arnold, 11 Nov 2026: "so slick, just like we did in the Swangz Bookings
app, and the layering — but here improve everything").** The source is the live Bookings app
(`swangz-bookings.netlify.app`; its `public/ui.css` §1–2, `tokens.css`, `admin.css` `.ftabs` / `.modal--drawer`).
The values below are read from that code. **This point replaces the radii in point 2**: controls are crisp
rectangles, not soft boxes. Glass, colours and card radii stay.

| Token | Value (was) | Used by |
|---|---|---|
| `--radius-control` | **4px** (10) | Buttons, inputs, selects, search, dropdown triggers, split buttons, top-bar items |
| `--radius-control-sm` | **3px** (8) | Small buttons, menu rows, table row hover, icon buttons, the slider thumb |
| `--radius-chip` | **3px** (6) | Chips, badges with text, filter tags, keyboard hints |
| tab strip | bar **14px**, tab **9px** (12 / 8) | Every tab strip — the Bookings floating tab bar |
| rail | bar **14px**, icon box **4px** (16 / 10) | Side bar |
| motion | `--d-fast:120ms; --d-base:200ms; --d-slow:320ms; --e-out:cubic-bezier(.2,.7,.3,1); --e-in-out:cubic-bezier(.4,0,.2,1)` | Every control transition |

**Buttons — five kinds, one base.** Base: inline-flex, **36px** tall (30px small, 42px large), padding 0 14px
(11 / 20), gap 6px, 13px weight 600, letter-spacing −.002em, 1px border, icon 15px, never wraps. Pressed =
`translateY(1px)`. Disabled = 40% opacity, no pointer. On touch screens the visible size stays and the hit area
grows to 44px.
- **Primary — the accent sweep (the Bookings signature).** Rest: solid near-white `#F2F2F2`, text `#0D0D0D`. On
  hover and on keyboard focus the amber (`--accent-pill`) **sweeps in from the left** behind the label:
  a `::after` layer, `transform: scaleX(0→1)`, origin left, 200ms `--e-out`; it sweeps back out on leave. One
  primary per screen. This replaces the resting amber fill on buttons (amber stays on the first KPI card, the
  selected bar and the live pulse).
- **Secondary** (the default for a plain button): transparent, 1px rim `rgba(255,255,255,.22)`, hover fills
  `rgba(255,255,255,.08)` and brightens the rim.
- **Quiet:** text only, muted; hover brightens the text and adds a faint fill.
- **Danger:** outlined in the danger colour, **never filled**; hover adds a faint danger tint.
- **On glass / over the photo:** `rgba(13,13,13,.55)` + the panel's existing blur (no second blur layer, §7.2),
  rim `rgba(242,242,242,.28)`; hover `.8` and rim `.55`.
- **Icon button — the stage light.** 34×34, radius 3. Hover and focus: the icon lifts 1px and a soft radial
  light fades up behind it (`radial-gradient(circle at 50% 55%, rgba(255,255,255,.16), transparent 68%)`, from
  `scale(.7)` opacity 0 to `scale(1)` opacity 1, 200ms). Pressed-on state = amber icon. Its label appears under it.
- **Loading:** the label goes transparent and the S loader (14px) sits centred; the width does not change.

**Improved over Bookings (required):** a 2px focus ring 2px outside every control (Bookings relies on the sweep
alone); under reduced motion the sweep and the stage light become an instant colour change; the split button's two
halves sweep together and are divided by a 1px line; the sweep is transform-only (no layout, no repaint of the
glass behind it) and must hold ≥ 55 fps on the laptop; light theme inverts it (rest `#0D0D0D`, amber sweeps in,
label stays readable at ≥ 4.5:1 at every point of the sweep — Probe samples the half-way frame).

**Layering — the Bookings dashboard pattern, made the rule for every area** (it is how points 1 and 5 look in
practice):
1. **Band:** each area opens with a compact title band (title, one-line purpose, the Next-step line, the primary
   button right) — 96px, no photo of its own; the room is the background.
2. **Floating tab bar:** directly under the band, sticky under the top bar while the page scrolls, as wide as its
   tabs (not full width), strong glass, radius 14 with 9px tabs and 6px padding. It is the area's L2 pages. The
   address carries the tab (`#people/active`), so every tab is a link and Back works.
3. **One panel:** under the bar exactly one panel — one table, or one card list, or one chart. Never two.
4. **Action column:** every table's last column is one button — **"Take action"** when the row needs a decision,
   otherwise **"Open"** — plus the `⋯` menu. The row click does the same as Open.
5. **Drawer for the record (L3):** Open slides a drawer from the right, **560px**, full height, 320ms
   `--e-in-out`, with its own tabs; each tab loads only when first opened. The list stays visible behind it and
   keeps its filter and scroll. The address carries the record (`#people/active/<id>/tools`).
6. **Decision sheet (L4):** "Take action" opens **one** sheet that shows everything needed to decide — the
   request, who, what it costs, what else that person already has — and the two answers (Approve / Decline) plus
   "Full details" (opens the drawer). Nobody should have to leave the sheet to make the decision.
7. **Search everywhere:** `/` or Ctrl+K from any layer finds people, tools, requests, dates and pages.

**Improved over Bookings (required):** the breadcrumb chain of point 1 runs through all layers; Esc closes one
layer at a time and focus returns to the row it came from; on phones the tab bar scrolls sideways with a fade
edge, the drawer and the sheet are full-screen with a sticky action footer; a drawer never opens over a drawer —
a link inside a drawer replaces its content and adds a crumb.

**7. Little on each page, and the app leads the way (Arnold, 11 Nov 2026, clarifying "layering").** What the boss
means by layered: **a page shows only a little, in the order a person needs it, so that even a very basic user
always knows what they are looking at and what to do next.** The test reader is someone who has never used an admin
tool. Points 1, 5 and 6 are the means; this point is the measure, and it wins when they disagree.

- **One sentence first.** Under every page title, one plain sentence states the answer the page exists to give,
  with the real number in it ("3 people are waiting for a tool." / "Nothing needs you right now."). A reader who
  reads only that sentence has got the page.
- **Then at most three things.** A screen at 1440×852 shows the sentence plus **at most three blocks** (this
  tightens the "≤ 7 blocks" of point 1 for the default view). On a phone: the sentence plus **one** block per
  screen height. Everything else is one deliberate step away — never further down the same page.
- **Show the few, offer the rest.** Summary lists show 5 rows and "See all 42"; tables show **5 columns and 10
  rows** by default (others under "Columns ▾", more rows by paging); a record shows its 4 most important facts and
  keeps the rest under closed sections ("History", "Devices", "Advanced"); long text is cut to two lines with "More".
- **Simple and Detailed.** Every list and record has a **Simple / Detailed** switch (segmented control, top right,
  remembered per person, **Simple by default for everyone**). Simple is the rules above. Detailed is the full
  table for people who work in it daily (with Compact from §10.9.3). Nothing exists only in Detailed that a task
  needs — Simple must be enough to finish every common job.
- **The app asks, the user answers.** Home (staff) and Overview (console) start with **"What do you want to do?"**
  — at most six large task tiles in plain words (Add a person · Give someone a tool · Answer a request · See what
  we spent · Check who is using what · Stop all AI). Each tile starts a guided flow: one question per step, the
  safe answer pre-selected, a progress line ("Step 2 of 3"), Back always available, a final "Here is what will
  happen" screen, then a clear result with the next suggested task. The full menus stay for people who know the way.
- **Always a next step.** Every page, drawer, sheet, empty state, success message and error ends with one
  suggested action as a button. A dead end — a screen with nothing to press but the menu — is a defect.
- **First visit.** A new admin sees a "Set up in 4 steps" checklist on Overview (add people → add tools → give
  access → check the first report) that ticks itself off from real data and disappears when done. A new member of
  staff sees three steps (sign in → open a tool → ask for one you do not have).
- **Plain words.** No internal or technical terms on a default screen (not "entitlement", "grant", "seat",
  "policy", "provenance", "L2"): say "access", "give", "licence", "rule", "where this number comes from". A term
  that must stay gets a dotted underline and a one-line popover. Buttons are verb + thing ("Give access", never
  "Submit" or "OK"). Sentences of 12 words or fewer. Numbers always carry their unit and period ("$4.20 this week").
- **Use every arranging tool before adding to a page:** tabs, the floating tab bar, dropdowns, accordions,
  drawers, sheets, steppers, popovers, "See all" links, Simple/Detailed, paging, grouping with headings, and empty
  space (≥ 24px between blocks). When something new must be shown, it goes down a level — a page never grows.
- **Signposts.** The trail shows where you are; the active rail icon and tab are unmistakable; every drawer and
  sheet says in its title what it is about and for whom ("Give Nansubuga Grace a tool").

**The basic-user test (Probe runs it on every restructured area; merge-blocking).** With a fresh browser and no
help, each of these is done from the landing page in **≤ 3 clicks to start, no scrolling to find the way, no
jargon read**: add a person; give that person a tool; answer a waiting request; find what was spent this week;
see what one person used; stop all AI. Probe records the click path and a screenshot of each step at 1440×852 and
390×844, counts the blocks on each screen (> 3 in Simple = fail), and lists every word a new user would not know.

**Round R18 — "structure and boxes"** goes **ahead of** the unfinished R15–R17 items, in this order: (a) tokens +
box controls + scrollbars + rail in one PR (CSS only, both apps, both themes); (b) the background; (c) the
"Page levels" table and the control kit page of point 5; (d) Overview as L1 with every card chained to its filtered list; (e) one chain per PR in the
order above. §10.2 overlays compare layout and colour only from now on — control radii follow this section.
