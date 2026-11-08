# Design brief — "Glass" redesign of Swangz AI Hub

Arnold, 7 Nov 2026: *"This is the exact design I want. They can improve where necessary."*
The three reference videos are the target look and motion. Match them closely; improve only where this
brief says so (accessibility, performance, phone layouts, the Hub's real features and data).

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
