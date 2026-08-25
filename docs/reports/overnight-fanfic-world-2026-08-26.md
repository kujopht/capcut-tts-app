# Overnight report — Fanfic World, 2026-08-26

Mega-task covering Trusted Sources final certification, a visual audit,
cover regeneration, and a Universal Story Scraper foundation. This report
is deliberately honest about what was verified/built vs. what was found
to already be fine vs. what was not attempted — no track is claimed
complete without evidence below.

## TRACK A — Trusted Sources final certification: BLOCKED_MANUAL

Verified: the QA account (`user_id 6a8dd1115b1ef86a585a`, registered last
session) still logs in with `is_admin: false`, and the live `/api/health`
`admin_count` is unchanged. Whatever was set in `FAS_ADMIN_USER_IDS` /
however it was redeployed, the live `fas-prod-api` process does not see
it. This blocks live HTTP-level certification (the actual
`/api/admin/animation/sources/*` endpoints).

What's still true without needing that access: the duplicate-advisor
algorithm itself was already proven correct directly against real
production Appwrite data in the prior session (novel
`nov_6b42f7954f914227` / video `XtJqhxbd1pY`), and the candidate-window
hardening (PR #58) can only ever find MORE true matches, never fewer — so
there is no plausible way the merged code regressed this. What's
unverified is only whether the live binary is actually running that code
and whether the HTTP/admin-auth layer is wired correctly end-to-end.

See `docs/reports/trusted-sources-duplicate-advisor-2026-08-26.md` for
the full prior investigation. **Action needed — see MORNING_ACTIONS.**

## TRACK B — Visual Renaissance: PARTIAL, one real bug found and fixed

A dedicated audit (live Playwright verification against the dev server at
1440/768/390px on `/`, `/fanfic`, `/animation`, plus a full production
build inspection) found the Nav V7 tracer, selection-travel animation,
compact single-row desktop layout, and mobile horizontal-scroll nav are
all **already correct** — no regression exists in the restored
navigation. The premise that the nav "has repeatedly regressed" did not
hold up under direct inspection.

What the audit did find, real and unrelated to the nav: **Next.js 16's
Lightning CSS minifier silently drops the `backdrop-filter` declaration
from every hand-authored `backdrop-filter` + `-webkit-backdrop-filter`
pair where the standard property was written first** — keeping only the
`-webkit-` form, which Chrome/Edge/Firefox don't honor. This affected
every "glass" surface site-wide: the header, the shared `.kinh` glass
group (`.listen-hero`/`.account-hero`/`.novel-head`/`.cta-band`/cards),
`.surface-primary`, the search overlay, the mini player, and the mobile
notification panel override. **All of these have been rendering flat and
unblurred on every non-Safari browser** since this pattern was introduced
(pre-dates the nav work by two weeks). Fixed in PR #59 (merged) —
reordered every instance, verified via `npm run build` + inspecting the
compiled CSS chunk before/after. A second instance was missed on the
first pass and caught by independent review before merge.

Also in PR #59: the 13 audio-only Fanfic chapters now show an intentional
"Chương này chỉ có bản audio" state with a clear path to `/listen/[id]`,
instead of a generic message that read as a data error.

**Not done tonight** (found to already be well-implemented on inspection,
or deferred as too large for the remaining time):
- Premium glass system extraction — already exists as the shared `.kinh`
  class group with token-based blur/border/shadow; `/novels/[id]` already
  uses it. No new abstraction was needed.
- PageHero/`.page-head` contrast — already redesigned in a prior pass
  (`.hero-copy`'s soft localized mist, replacing an earlier full-width
  flat strip); found to already satisfy the "no giant opaque block, no
  flat grey box" requirement. Not touched further.
- Full homepage / fanfic-grid / Listen-page visual polish passes —
  **not attempted**. These are real, valid tracks but too large to do
  with real rigor in the time remaining after the above.

## TRACK C — React Bits research: DONE (research only, nothing implemented)

Full candidate matrix produced against the real `react-bits` catalog
(~165 components across Animations/Backgrounds/Components/TextAnimations,
fetched from source, not guessed from names). Published as an artifact.
Recommendation: adopt a small set of cheap, dependency-free, copy-
localized patterns — `SpotlightCard`/`GlareHover` for card hover depth,
`BorderGlow` for input focus, one `StarBorder` accent, a blur-only
`GlassSurface` for the search overlay, `BlurText` for hero entrances, and
`Folder` for empty states. Reject the entire WebGL/Backgrounds category
and all custom-cursor components outright (redundant with the existing
live-wallpaper system; real accessibility cost; competes with the nav
tracer). **None of this was implemented tonight** — it's a decision, not
code.

## TRACK D — 13 cover regeneration: DONE, verified in production

All 13 covers regenerated using the free Pollinations endpoint (no key,
no cost), portrait 768×1152, one story-specific prompt per work (read
each real title/fandom/description rather than a shared template — see
prompts in `upload_covers.py`'s companion generation script, not
committed to the repo since it's an operator one-off, not app code).

QA was genuine visual inspection of every image, not a heuristic: 3 of 13
were regenerated after failing on first attempt (single ambiguous
silhouette instead of the intended two-character scene; abstract
landscape instead of a visible character; distant unreadable figure) —
each fixed with a revised prompt and re-reviewed. Final set has real
fandom differentiation (basketball court, courtroom confrontation,
detective noir, ninja fire chakra, sake tavern, pirate ship, sci-fi
tower, Sharingan/ocean fusion) — no repeated central rune, no two
interchangeable images.

Uploaded to R2 under a new object key per novel
(`covers/{owner}/{novel_id}/anh-v2.jpg`); the original `anh.webp` was
**not deleted** and remains as a rollback reference. Verified end-to-end:
fetched the live novel via the real public API, confirmed `cover_url`
resolves, downloaded the signed URL, confirmed byte-for-byte match with
the uploaded file. Title/audio/source/ownership/publication state were
not touched. Contact sheet: see MORNING_ACTIONS or ask for the artifact
link.

## TRACK E/F — UI/performance/accessibility audit: PARTIAL

Bounded, not exhaustive. Done: live nav/header verification (see Track
B) across 3 routes × 3 viewports with real DOM measurement, not
guesswork; a direct code check of every `requestAnimationFrame` user in
`web/src/components/` (`NavIndicator`, `CountUp`, `YouTubeFacadePlayer`,
`ui.tsx`'s modal focus effect) confirmed every one cancels its frame on
unmount — no leaks found; confirmed 7 separate `prefers-reduced-motion`
blocks exist in `globals.css`. **Not done**: the full route-by-route walk
across every public/auth/author/admin page listed in the original scope,
design-token drift audit, typography audit, or a formal desktop/mobile
screenshot set for every route. This is real, valid remaining work.

## TRACK G — Universal Story Scraper foundation: DONE

Provider-neutral contract (`resolve`/`discover_series`/`list_chapters`/
`fetch_chapter`/`normalize_chapter`/`fingerprint`/`resume`) plus a Tier 0
(direct HTTP + stdlib `html.parser`, zero new dependencies) implementation
in `server/scraper/`. 28 tests against local fixtures (no live network in
CI) prove series discovery, chapter ordering, clean-text extraction,
idempotent reruns, resume-after-interruption (skips completed chapters,
retries failed ones, flags content revisions instead of silently
overwriting), and JSON-LD-over-scraped-text preference. Manually verified
`HttpFetcher` against one real public page (Project Gutenberg, a single
respectful GET). Scrapling and Playwright (Tier 1/2) were evaluated but
not added — nothing yet requires them.

Independent review caught two real bugs before merge: `canonicalize_url`
mishandled scheme-less input (`"example.com/x"` → malformed output), and
tracking-param stripping matched too broadly by prefix (`"ref"`/`"si"`
would have silently dropped real params like `size`/`sid`/`referral_code`).
Both fixed with regression tests. PR #60, merged.

**Foundation only** — not wired into any ingestion pipeline, no crawling
scheduler, no admin UI, no auto-publish. That's the next phase, not
tonight's.

## TRACK H — Engineering process

Three PRs tonight, each with its own tests/typecheck/build/independent
review/CI before merge:
- **#59** — backdrop-filter fix + chapter audio-only state (merged)
- **#60** — Universal Story Scraper foundation (merged)
- (Trusted Sources work from the prior session — #57, #58 — already
  merged before this session started)

No half-finished branches left behind; `main` is synced; every feature
branch was deleted after merge.

## Production state

- **Deployed to Cloudflare (web)**: not verified — this session did not
  check whether the Cloudflare Pages frontend deploy is on autoDeploy or
  requires a manual trigger; assume it needs the same verification as
  `fas-prod-api`.
- **Deployed to Render (fas-prod-api)**: blocked, see Track A and
  MORNING_ACTIONS. `autoDeploy: false`, no deploy hook available to this
  session.
- **Production data mutated**: 13 novels' `cover_key` updated (old key
  preserved, reversible); nothing else. The 13 real Fanfic novels'
  title/audio/source/ownership/publication state were not touched.
- **Real content published**: none new.
