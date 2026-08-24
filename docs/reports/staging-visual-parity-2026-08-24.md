# Staging Visual Parity — 2026-08-24

## Canonical staging identification

**CANONICAL_STAGING_SHA:** `4053e95` ("V7: sửa tracer hình elip, nav-right nằm
ngang, bỏ hộp chữ nhật sau hero")
**CANONICAL_STAGING_BRANCH:** `feature/fanfic-visual-renaissance-v1` (never
merged, never deployed anywhere)
**CURRENT MAIN SHA (before this restoration):** `f0d32f0`

### Evidence this is the correct candidate, not a guess

- Cloudflare's own deployment log shows the ONE real `fanfic-web-staging`
  deployment ever made (2026-08-21T16:44:59Z) was from commit `d959dbd` — a
  **strict ancestor** of `4053e95` (confirmed via `git merge-base
  --is-ancestor`). The real deployed staging predates this work by ~4 days
  and never had it.
- `d959dbd` was also deployed to production 6 minutes later — staging and
  production were byte-identical at that point, and neither ever had the
  Portal, the leaderboard shelf, or the V7 nav tracer.
- `feature/fanfic-visual-renaissance-v1`'s own commit history (all same
  author, same session, 2026-08-17 through 2026-08-20) documents an explicit
  V1→V7 iteration sequence for the nav tracer, each commit fixing a specific
  named defect in the previous one (conic-gradient masking bug → SVG stroke
  rewrite → elliptical-tracer bug → this fix). `4053e95` is the LAST commit
  in that sequence that touches `NavIndicator.tsx`/`globals.css` before the
  branch moves on to unrelated backend ingestion work — i.e. the final,
  most-refined state, not an intermediate one.
- The branch's own docstrings self-diagnose the exact bug the user
  remembered ("selected background too bright/obscuring text"): an earlier
  iteration (V1/V3) had a one-shot arrival animation missing
  `animation-fill-mode: forwards`, which left a solid gradient "stuck"
  filling the pill's interior. That bug was already fixed by later commits
  on the SAME branch — `4053e95` does not have it.
- `docs/design/FANFIC_WORLD_VISUAL_BIBLE_V1.md` and
  `docs/design/fanfic-world-modern-anime-fantasy-aesthetic.md` (both exist
  only on this branch) independently corroborate the intended final
  aesthetic ("Moonlit Storyworld") matching what `4053e95` renders.

No second/third candidate was built — the archaeology found exactly one
coherent lineage where the Portal, the leaderboard shelf, and the final nav
tracer design coexist. There was no competing candidate to weigh against.

## Route / component parity table

| Route / Component | Staging reference (4053e95) | Current result (this restoration) | Parity | Difference | Why different |
|---|---|---|---|---|---|
| Homepage — hero | Simple `.hero-copy`-free hero: pill, title, lead, 2 CTAs, no motif, no secondary pill row | `.hero-copy` wrapper kept, no motif, no secondary pill row | MATCH (adapted) | Wraps content in `.hero-copy` | `.hero-copy` is shared `PageHero` mist/glow infrastructure added to `main` AFTER 4053e95, used consistently across every other themed route on the site today. Dropping it would be a real regression relative to current main, not a restoration. Kept per explicit instruction #4 ("preserve current-main functionality... where newer/better"). |
| Homepage — Storyworld Portal | `TheGioiCong`: 2/3-width Truyện card (real illustrated art) + Animation/Audio stack + 3-satellite row | Ported verbatim (component, CSS, art assets byte-identical from git history) | MATCH | None | — |
| Homepage — weekly leaderboard | "Bảng vàng tuần" shelf, `HangBangVang`, `/api/leaderboard?mode=weekly` | Ported verbatim | MATCH | None | The backend endpoint and `.lb-*` CSS already existed on main (built later, for the standalone `/leaderboard` page) — reused directly, no new backend work needed. |
| Homepage — Animation shelf | Single-item featured treatment (`TheAnimNoiBat`) alongside multi-item grid | Ported verbatim | MATCH | None | — |
| Homepage — CTA band | Full-bleed illustrated background (`creator-worldbuilding.webp`) + overlay | Ported verbatim, art recovered byte-exact | MATCH | None | — |
| Homepage — empty state ("Đang nổi bật") | `.portal-empty-noibat`, shares Portal's class prefix | `.empty-noibat` (own class names) | MATCH (functionally/visually), diverges only in class naming | Different CSS class names, identical rendered result (same motif, same layout, same CSS properties) | Restored the previous night under independent, non-`portal-`-prefixed names specifically to avoid coupling to the Portal system before it was known whether Portal would ever be restored. Now that Portal IS restored, kept the existing names rather than rename a working, tested, already-reviewed component purely for naming purity — reversible, zero visual difference, avoids needless churn. |
| Nav — selected background | `color-mix(in srgb, var(--bg) 82%, transparent)` | Identical | MATCH | None | — |
| Nav — tracer | Two-layer SVG stroke: static base (muted blend) + animated dashed tracer (solid accent) | Identical, live-verified via computed styles across all 5 routes | MATCH | None | — |
| Nav — selected label color | `var(--text)` (near-white) | Identical | MATCH | None | — |
| Nav — border-radius / elliptical-tracer fix | JS-clamped `Math.min(targetRadius, w/2, h/2)` from real computed style | Identical | MATCH | None | — |
| Nav — CTA leave-grace | `data-nav-leaving="write"` on `<body>`, 560ms | Identical, live-verified via real click-based navigation | MATCH | None | — |
| Nav — arrival "streak" effect | **Not present** (removed by staging's own later commits as the root cause of a "stuck bright background" bug) | Not present (removed) | MATCH | Previous night's independent restoration had added a one-shot streak effect based on an earlier, already-superseded iteration — removed in this pass to match the actual final design | The user's memory and this restoration both point to `4053e95`, which has no streak effect. Keeping one would not be "recovering the actual staging implementation." |
| Route transitions (Aether Rift) | Present, working | Unchanged, already on main | MATCH (pre-existing) | None | Confirmed already-correct in tonight's Phase 3 motion audit; not part of `4053e95`'s diff against current main. |
| Live Wallpaper | Present, working | Unchanged, already on main | MATCH (pre-existing) | None | Same as above — added to main after `4053e95` in a later, more complete form. |
| PageHero (non-homepage routes) | N/A on this branch (added later) | Unchanged, already on main | N/A | — | `4053e95` predates PageHero entirely; nothing to port. |
| Explore (`/fanfic`) | Same hub-model shelf layout as main | Unchanged | MATCH | None | Not touched by this restoration — confirmed structurally equivalent in tonight's earlier live audits. |
| Novel/reader, Audio Studio, Animation watch | Not part of `4053e95`'s diff against main | Unchanged | N/A | — | These routes were not part of the Visual Renaissance homepage/nav work — no staging-vs-main difference exists to restore. |
| Trusted Sources admin | Not part of `4053e95`'s diff against main; built later, entirely independently | Unchanged | N/A | — | Already confirmed fully operational in tonight's Phase 4 audit; out of scope for this visual restoration. |
| Mobile (Portal, nav) | Portal: Truyện full-width, Animation/Audio side-by-side, satellites become horizontal scroll-snap rail. Nav: unchanged mobile behavior (horizontal scroll) | Ported verbatim, live-verified at 390×844 (no horizontal overflow) | MATCH | None | — |
| Reduced motion | Tracer (Layer B) animation stopped; static base (Layer A) remains fully visible | Identical | MATCH | None | — |

No unexplained differences remain. The two documented differences (hero
wrapper, empty-state class names) are both justified preservations of
already-working current-main infrastructure, not gaps.
