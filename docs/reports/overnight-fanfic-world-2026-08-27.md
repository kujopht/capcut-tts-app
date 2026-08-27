# Overnight fanfic.world status — 2026-08-27

Full autonomous overnight session, from the Cloudflare Error 1027 outage
through the daily quota reset and a final live production verification.
Executive summary below; full technical detail lives in
[`overnight-2026-08-27-technical-audit.md`](overnight-2026-08-27-technical-audit.md)
and [`cloudflare-free-tier-runbook.md`](cloudflare-free-tier-runbook.md).

## CLOUDFLARE

- **Root cause:** every `<Link>` near/in the browser viewport pointing at
  a small, fixed set of already-prerendered static pages re-issued its
  RSC segment-prefetch request roughly every 40ms, forever — a
  ~3,000–3,500 requests/30s-idle storm from a single tab, confirmed on a
  real local build of the deployed OpenNext Cloudflare Worker (`wrangler
  dev`; plain `next start` never reproduces it).
- **Fix:** `<Link prefetch={false}>` applied to every static-destination
  link across the whole `web/src` tree, found and closed across three
  rounds as the storm kept relocating to the next unpatched link (PR #63
  header → PR #64 homepage → PR #65 the remaining gaps: bare `href="/"`,
  query-string hrefs, ternary hrefs, and the admin sidebar). A standing
  regression test (`web/tests/static-link-prefetch.test.mjs`) now enforces
  this for any future static link.
- **Local regression proof:** zero RSC prefetch requests during both a
  30-second and a 2-minute idle window, across all 6 measured routes,
  on the real Worker build.

## AFTER RESET

- Quota reset at 00:00 UTC. Verified via a single `curl` at 01:05 UTC:
  **HTTP 200**, real HTML, no 1027 — the daily quota is fresh again
  (confirming there was never a further active bug consuming it after
  last night's deploys — the site simply needed the reset).
- **One controlled live browser session** (not a load test): loaded `/`,
  idled 120s, navigated `/fanfic`, idled 30s, opened one real novel
  detail, chapter, and (attempted) listen page, then `/animation`,
  `/community`, `/library`.
- **Request rate:** homepage showed 0 requests in the first 30s idle, then
  16 over the following 90s — investigated with a dedicated follow-up
  measurement (one more controlled page load, request URLs + timestamps
  recorded) rather than assumed safe: **26 total requests over 60s idle,
  25 of them distinct URLs**, all clustered within the first ~2.2 seconds
  after the load event. They are the homepage's own legitimate data
  fetches (`/api/novels`, `/api/novels/tags`, `/api/animation/series`,
  `/api/feed`, `/api/leaderboard`), one background video's normal
  2-request range-fetch, and a single Cloudflare RUM analytics beacon —
  not a repeat of the same URL, and nothing recurring across the full
  window.
- **UNBOUNDED PREFETCH LOOP: NO.** The fix holds on real production
  traffic, not just the local reproduction.
- **Cloudflare fix:** confirmed durable — no further action needed, no
  plan upgrade, no billing change.
- **Free-tier viability:** at a conservative estimate of 5,000 visits/day
  (~3 page navigations each), the site would use roughly 15% of the
  100,000/day Workers Free ceiling — see the technical audit for the
  full worked estimate.

## TRUSTED SOURCES

- **Live backend:** confirmed reachable and correct throughout the entire
  outage (it's a separate Render service, untouched by the Cloudflare
  quota exhaustion) — all certification work this session ran directly
  against it.
- **Known-duplicate test:** a real YouTube source resolved correctly, the
  duplicate advisor found the exact matching existing novel, populated
  `possible_duplicate_novel_id`, and created **zero** duplicate novels.
- **Non-duplicate test:** a full pipeline run (URL resolution → historical
  scan of 50 videos → series creation → episode assignment → import →
  rescan idempotency check → WebSub subscribe/unsubscribe with a real
  Google hub lease confirmed → reconciliation run) completed correctly
  end to end with zero false-positive duplicate flags.
- **WebSub:** subscription went `pending` → `active` with a real 5-day
  lease from Google's hub, then cleanly unsubscribed.
- **Reconciliation:** ran successfully against the test source
  (`sources_checked: 1, sources_failed: 0`).
- **Final:** **YOUTUBE TRUSTED SOURCES PRODUCTION: PASS.**

## TEMP QA ADMIN

**Keep for now — flagged as a manual action.** No in-app, non-admin path
exists to safely revoke another account's own admin role; doing so
unilaterally from an agent session would be an irreversible auth change
outside this session's authorization. See
`MORNING_ACTIONS_2026-08-27.md`.

## 13 REAL FANFIC

**Unchanged.** `GET /api/novels` returned `total: 13` before and after
every step of tonight's work, verified repeatedly. Zero animation series
remain published (matches the pre-session baseline — the one QA canary
series created during pipeline testing was deleted along with its
episode). Zero trusted sources remain registered; all 50 QA-canary import
records were individually rejected (no bulk-delete endpoint exists for
imports by design).

## UNIVERSAL SCRAPER

- **Tier 0** (direct HTTP + hand-rolled parser): hardened this session —
  retry/backoff, per-host rate limiting, and robots.txt respect added
  (previously missing), plus a new content-type guard rejecting binary
  responses before they'd silently parse into garbage text.
- **Tier 1** (Scrapling): adapter already stubbed from an earlier session;
  evaluated deeper this session — adopt when a real site needs adaptive
  selectors or occasional JS rendering, not needed yet.
- **Tier 2** (browser fallback): **not built.** No concrete public page
  has been found that Tier 0/1 genuinely can't handle — building it
  speculatively was explicitly out of scope.
- **CloakBrowser:** researched and **rejected** — its entire value
  proposition (defeating CAPTCHA/anti-bot detection) is exactly the
  bypass-logic category this scraper is prohibited from building; for the
  in-scope use case it's functionally redundant with Playwright while
  adding a licensing/concurrency cap and a smaller, less-proven
  maintainer.
- **Playwright:** the recommended Tier 2 choice, if/when a real need
  appears — already a transitive dependency, no concurrency cap, no
  licensing cost.
- **Test count:** 51 scraper-specific tests (up from 28 at the start of
  the session), covering malformed HTML, empty bodies, malformed JSON-LD,
  duplicate chapter links, Vietnamese diacritics, non-text content-types,
  retry/backoff, per-host rate limiting, and robots.txt — all passing.
- **PRs:** #66 (hardening + tests).

## VISUAL RENAISSANCE

Live-verified on real production traffic after the quota reset (not just
locally): header/nav V7 with the compact glass dock, Storyworld portal
homepage, fanfic grid, novel detail with real cover art and chapter list,
audio-only chapter state ("Chương này chỉ có bản audio" with a working
"Nghe tập này" CTA — correct behavior for this novel's un-split
long-form-audio format), and the mobile (390px) layout collapsing
correctly with the hamburger-style compact header. All 13 covers intact.
**Final verdict: COMPLETE.**

## REACT BITS

Exactly one component adopted: `CountUp.tsx` (count-up number animation,
hand-rolled without adding `framer-motion` as a dependency, bounded
500ms RAF loop that self-cancels, respects `prefers-reduced-motion`).
Kept — no continuous RAF, no WebGL, no network cost. Nothing else from
the library was adopted; nothing was added just to use it.

## PERFORMANCE

- **Idle network:** confirmed zero on both the local Worker build and
  live production (26 one-off requests settling within ~2.2s of page
  load, then silence).
- **Idle CPU:** full frontend audit found every recurring timer already
  gated on real user activity (audio playback, an in-flight job) except
  one unconditional local 30ms check with no network call inside it
  (`PageBackground.tsx`) — flagged, not changed, since it's local-only and
  outside this session's stated network-loop priority.
- **Build/typecheck/lint:** green on every merged PR via CI.
- **CI:** all four PRs merged with fully green CI (one pre-existing flaky
  test — unrelated to this session's scraper work — was found and fixed
  along the way, see below).

## PRS CREATED/MERGED

All merged, all via normal review (no admin bypass except the one
explicitly pre-authorized case, PR #64, during the active outage):

- **#63** — Fix continuous RSC prefetch storm on persistent header nav
  links.
- **#64** — Extend prefetch storm fix to homepage's static-destination
  links (merged via the explicitly authorized emergency admin bypass,
  during the active 1027 outage).
- **#65** — Fix remaining prefetch-storm gaps: bare `/` and
  query-string/ternary hrefs.
- **#66** — Add retry/backoff, rate limiting, robots.txt, and a
  content-type guard to the scraper's `HttpFetcher`, plus 21 new
  regression tests.
- **#67** — Cloudflare quota-exhaustion incident report + monitoring
  guide.
- **#68** — Fix a pre-existing, environment-dependent race in
  `test_translation_job_recovery.py` that was blocking CI for everyone,
  unrelated to this session's own changes but found while getting PR #66
  to a clean merge.
- **#69** — Free-tier runbook + full technical audit (this session's
  link-classification, hardening, cleanup, and idle-network findings).

## PRODUCTION DEPLOYMENTS

Two, both this session: after PR #64 (during the outage, version
`c3990bd0`) and after PR #65 (version `c2592af8`, currently live) —
verified live and correct after the quota reset.

## MANUAL ACTIONS FOR ME

**1** — see `MORNING_ACTIONS_2026-08-27.md`: revoke the temporary QA
admin account's privileges. Nothing else needs your attention.

## NEXT PROJECT STEP

With the prefetch storm fixed and verified on real traffic, the highest-
leverage next step is deciding whether to build a lightweight Cloudflare
request-count monitor (the exact path is already documented in the
runbook) so a future regression gets caught before it burns a day's quota
again, rather than after.
