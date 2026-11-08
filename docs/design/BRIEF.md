# Design brief — "Glass" redesign of Swangz AI Hub

Arnold, 7 Nov 2026: *"This is the exact design I want. They can improve where necessary."*
Arnold, 8 Nov 2026: *"My boss said it needs an interface exactly like that."*
The three reference videos are the target look and motion. **Match them exactly** — same layout, sizes,
spacing, radii, colours, transparency, type scale and motion. The only allowed differences are the ones listed
in **§10 Exact match** (our words/data/brand, our licensed photos, and the accessibility, performance and phone
rules in §7). §10 holds the measured values and the acceptance check every UI PR must pass; where §10 and an
earlier section disagree, §10 wins.

| Reference | Video | Stills | Becomes |
|---|---|---|---|
| Glassy Dashboard V7 + CRM | `references/video/glass-dashboard-crm.mp4` | `references/stills/dashboard-01…07.jpg` | The control room (`admin.html`, `admin.css`, `admin-*.js`) and the staff app shell (`index.html`, `portal.css`) |
| Glassy login form V2 | `references/video/glass-login.mp4` | `references/stills/login-01…07.jpg` | Staff and admin sign-in |
| Glassy liquid footer | `references/video/liquid-glass-footer.mp4` | `references/stills/footer-01…06.jpg` | The footer of the staff app and the sign-in page |

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
4. **Phones (the references are desktop-only):** at ≤ 700px the rail becomes a bottom tab bar (5 items + More),
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
