# Production Release — 2026-08-24 morning

Deployed last night's website-completion work (PRs #43-#49) plus one
production-visible bug found during smoke testing (PR #50, redeployed).

## Phase 0 correction (mid-task)

The user's initial framing assumed `staging.fanfic.world` showed a
meaningfully different, better nav/homepage design than current `main`
("too bright" selected background, missing tracer, missing travel
animation). Direct forensic verification found this did not hold:

- Cloudflare's deployment log shows `fanfic-web-staging` was deployed
  **exactly once**, from commit `d959dbd` (2026-08-21T16:44:59Z) — the
  same commit deployed to production 6 minutes later. Staging and
  production were byte-identical at that point.
- `staging.fanfic.world` is still live (never actually torn down).
  Direct inspection (screenshots + DOM/computed-style checks) showed a
  subtle `rgba(255,255,255,0.06)` selected-nav background, fully
  legible text, no tracer SVG at all (`data-dung-yen` = "static"), and
  a homepage visually indistinguishable from current production.
- The actual source of the "bright background" memory was identified:
  a self-documented, already-fixed bug in an intermediate commit of
  the unmerged `feature/fanfic-visual-renaissance-v1` branch's own
  development history (a `sheen` streak animation missing
  `animation-fill-mode: forwards`, causing a background gradient to
  get stuck fully visible) — never deployed anywhere. What was
  restored into `main` last night already matches that branch's later,
  fixed architecture (pure SVG stroke, `dasharray 14/86` on
  `pathLength=100`, real-height-measured `rx`/`ry`).

User confirmed: treat this as resolved, resume production verification.

```
FINAL REPORT
------------
MAIN SHA:                  085bb68f9d574d19341532c21bfea4a9a151cdd2
PRODUCTION FRONTEND SHA:   085bb68f9d574d19341532c21bfea4a9a151cdd2
                            (Cloudflare Version ID 22f70b07-37e4-4201-a2ac-9c3b24bb5bc1)
PRODUCTION API SHA:        unchanged — no server/ changes in any PR tonight/this
                            morning, so no API redeploy was needed or performed
                            (health check confirms environment=production, healthy)

FRONTEND DEPLOY: YES — deployed twice: once for PRs #43-#49 (visual parity,
  route sweep, motion audit, admin moderation confirm dialogs, docs), once
  more for PR #50 (featured-authors fix found during smoke test)
API DEPLOY: NOT NEEDED (no backend changes)

FANFIC.WORLD:
NAV CONTINUOUS TRACER: PASS — live-verified genuinely animating
  (strokeDashoffset changing over time, animationName: nav-tracer-dash,
  playState: running), correctly follows selection across / -> /fanfic ->
  /community, unselected items show no tracer
ROUTE TRANSITIONS: PASS — Aether Rift idle->revealing->idle cycle confirmed,
  no stuck overlay, destination clickable within ~370ms
LIVE WALLPAPER: PASS — distinct per-route background video confirmed
  (01-home.mp4 / 06-library.mp4 etc.), no load errors, no flash-to-blank
PAGE HERO: PASS — motion confirmed live-animating (computed transform changed
  across two samples 500ms apart)
ANIMATION PLAYER: dim-on-pause verified via code read only — no real episode
  content exists to test live against (pre-existing sandbox/production data
  limitation, not a product gap)
MOBILE: PASS — 390x844 checked on homepage + one other route, no horizontal
  overflow, no overlapping elements
REDUCED MOTION: PASS — with prefers-reduced-motion emulated, tracer's
  strokeDashoffset stays frozen, selected item still shows a static
  indicator, navigation remains fully functional

TRUSTED SOURCES ADMIN: loads correctly, no console errors, correctly shows
  the admin-login gate for anonymous access (real admin credentials for
  actual production are not available in this environment — deep functional
  behavior was already live-verified last night against a seeded local mock
  backend with a real admin session; today's check on real production
  confirms the page loads/gates correctly, not full functional re-verification)
AUTHOR APPLICATIONS: loads correctly, correctly gated
USER MANAGEMENT: loads correctly, correctly gated
CONTENT MODERATION: loads correctly, correctly gated

CLOUDFLARE 1102: none observed across 35 burst requests (20x on
  /admin/authors/applications, 15x on /) — cache headers (x-opennext-cache:
  HIT, x-nextjs-prerender: 1) unchanged from before tonight's changes, no new
  SSR/runtime overhead introduced, no paid Cloudflare features touched
  (confirmed empty diff on wrangler.jsonc/package.json/open-next.config.ts)
PRODUCTION HEALTH: healthy

PRODUCTION DATA MUTATED: NO
REAL CONTENT INGESTED: NO
PRODUCTION INFRA CHANGED: NO

KNOWN P1: none
KNOWN P2:
  - Import Queue approve/reject path remains test-verified only, not
    live-verified against real queue data (needs a YouTube API key
    unavailable in any sandbox used so far) — pre-existing, not new.
  - Admin routes on REAL production were verified as correctly gated but not
    deep-functionally re-tested live (no real production admin credentials
    in this environment) — functional correctness already established last
    night against a local mock backend with equivalent code.
KNOWN P3:
  - `server/tests/test_translation_job_recovery.py::test_worker_chet_giua_truyen_worker_moi_hoan_tat_dung_mot_lan`
    failed identically (10 != 12) 3 times today in CI, across 2 unrelated
    frontend-only PRs, always passing on a fresh workflow run — looks like a
    wall-clock/thread-scheduling-timing-dependent flake in a worker-crash
    recovery simulation, not a real regression (passed cleanly in a full
    2710-test local run last night). Recommend a dedicated follow-up to make
    it deterministic; explicitly not fixed tonight per "do not begin
    unrelated work."
  - Mobile nav-pill bar has no scroll-affordance gradient (from last night's
    report, still applies, not touched this morning).
  - Admin data tables show ~2/6 columns on mobile without a scroll-shadow
    hint (from last night's report, still applies).

FINAL VERDICT:
PRODUCTION WEBSITE RELEASE: PASS
READY FOR MANUAL VISUAL REVIEW: YES
READY FOR REAL CONTENT PILOT: NO — this decision is explicitly reserved for
  the user's own judgment after manual review, not something to declare from
  automated verification.
```

## Bug found and fixed during smoke test

`/community`'s "Tác giả nổi bật" (Featured Authors) sidebar was showing a
seeded test account (`author_status=approved`, empty `username`) publicly,
with a dead profile link (`/u/` → 404, confirmed via network trace). Fixed
in `web/src/components/CommunitySidebar.tsx` by filtering out any profile
with a missing or whitespace-only username before ranking/slicing to the
top 5 shown — a frontend defensive fix, not a mutation of the underlying
production account (PR #50). Verified live after redeploy: the account no
longer appears, no 404s, and the section correctly falls back to its
documented empty state (hidden entirely) since it was apparently the only
account with ranking data.
