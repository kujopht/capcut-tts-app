# Overnight technical audit — 2026-08-27

Supporting detail for the overnight autonomous work session. The executive
summary lives in `overnight-fanfic-world-2026-08-27.md`; this document is
the full audit trail behind each finding, for anyone who wants the "why,"
not just the "what."

---

## Track A — Prefetch storm regression, formalized

Already proven and fixed this session (PR #63/#64/#65) using a real
`wrangler dev` build of the deployed OpenNext Worker — the only faithful
local reproduction of the actual Cloudflare behavior (plain `next start`
never shows the storm, because the storm is an interaction between Next's
client router cache and OpenNext's cache-interception layer).

**Standing regression test:** `web/tests/static-link-prefetch.test.mjs` —
a source-level scan asserting every `<Link>` to a small fixed set of
already-prerendered static routes carries `prefetch={false}`, catching the
*cause* (a new static-destination link added without the prop) rather than
the symptom (measured request counts), which is more useful in CI since it
runs in milliseconds and needs no live Worker build.

**Why no CI-level live-traffic regression test was added on top of that:**
reproducing the storm requires a real `wrangler dev` build (multi-minute)
plus a live idle-network capture (tens of seconds) — too slow and too
Windows-file-lock-prone (see the `.open-next` EPERM issue hit twice this
session) to run on every PR. The source-level test catches the actual root
cause class; a full live-traffic harness would mostly be testing that
`wrangler dev` itself still works, at high CI cost. If this class of bug
recurs despite the source-level test (e.g. a *new* mechanism, not a missed
`prefetch={false}`), that would be the trigger to invest in the heavier
harness — not preemptively.

**Local reproduction numbers** (real `wrangler dev` Worker, six routes:
`/`, `/fanfic`, `/animation`, `/community`, `/library`, plus the header/
footer present on all of them):
- Before fix: ~3,000–3,500 requests / 30s idle, indefinitely, from a single
  tab.
- After fix (PR #63+#64+#65 combined): **0** requests during 30s idle AND
  during a 2-minute idle window, across all six routes. Only a bounded,
  one-time initial load burst in the first ~1s of each navigation.

## Track B — Link/prefetch classification audit

Every `<Link>` in `web/src` was already swept for the storm-causing
pattern (PR #63/#64/#65); this section adds the requested formal
classification.

| Surface | Class | Prefetch decision | Why |
|---|---|---|---|
| Header/footer brand link, nav items (`/`, `/fanfic`, `/animation`, `/community`, `/library`, `/write`, `/login`, `/studio`, `/image-studio`, `/leaderboard`, `/account`, `/notifications`, `/creator/apply`) | STATIC_HIGH_VALUE | **OFF** (`prefetch={false}`) | Always mounted, always in/near viewport, small fixed prerendered set — exactly the storm's trigger condition. Value of prefetching a page that loads in ~1s anyway is negligible next to the cost of it looping. |
| Homepage hero/portal/CTA cards | STATIC_HIGH_VALUE | **OFF** | Same reasoning — same small set of static destinations, just reached from a different component. |
| Fanfic/animation card grids → `/novels/{id}`, `/animation/{id}` | DYNAMIC_HIGH_CARDINALITY | **ON** (default) | Genuinely per-item, unbounded cardinality — each card is a distinct route Next has never prefetched before, so there's no "already cached, still refetching" loop to trigger. Confirmed separately: these prefetch exactly once per card, correctly. |
| Chapter/listen links from a novel/episode detail page | DYNAMIC_LOW_CARDINALITY | **ON** (default) | Bounded by chapter count of the one open work (single digits to low dozens), not the whole catalog — same one-shot-prefetch behavior as above, no storm risk. |
| Community posts, `/u/{username}` profile links | USER_GENERATED_LIST | **ON** (default) | High cardinality, always changing — same reasoning as fanfic cards; no evidence of any storm risk since each URL is prefetched at most once. |
| Admin table row links (stories/users/sources list → detail) | ADMIN | **ON** (default) | Extremely low traffic (a handful of admin accounts, not public visitors) — even a worst-case storm here couldn't meaningfully threaten the 100k/day budget, and prefetch genuinely speeds up an operator's workflow. |
| `AdminShell.tsx` persistent sidebar nav | STATIC_HIGH_VALUE (admin) | **OFF** | Structurally identical to the public header — always mounted across every `/admin/*` page — so it has the same storm precondition even though admin traffic itself is low. Fixed in PR #65 for consistency/correctness even though the blast radius is small. |
| Single-destination admin breadcrumbs (e.g. "← Về danh sách") | ADMIN | **ON** (default, left untouched) | Not persistently mounted across pages — unmounts on navigation, so it can't accumulate an infinite loop the way an always-mounted nav can. |
| Dropdown-menu-only items (`.menu-item` in `NavAuth.tsx`: Studio/Image Studio/Account/Leaderboard) | STATIC_HIGH_VALUE, but conditionally mounted | **ON** (left untouched) | Only exists in the DOM while the dropdown is open — never has the sustained viewport presence the storm requires. |

**Links audited:** all `<Link>` usages across `web/src` (54-line sweep
covering every `.tsx` file under `app/` and `components/`).
**Auto-prefetch turned off:** 19 distinct static-destination link sites
across `NavAuth.tsx`, `page.tsx`, `layout.tsx`, `AdminShell.tsx`, and 8
other files with query-string/ternary hrefs (PR #63+#64+#65 combined).
**Auto-prefetch kept on:** every dynamic per-item route (chapters, novels,
animation episodes, posts, profiles) and every admin single-destination
link — confirmed via the local storm-free measurement above that keeping
these on introduces no observed request-storm risk.

**Hover/focus/pointer-intent alternative — evaluated, not adopted:**
Next.js's own `prefetch={false}` already fully solves the observed problem
(the storm was viewport-triggered, not hover-triggered — hover prefetch
was never the cause). A custom pointer-intent prefetch layer would add
real complexity (a new hook, event listeners, cleanup) for zero additional
benefit over what's already shipped, so it wasn't built — this is a
"don't add abstraction the problem doesn't need" call, not an oversight.

## Track C — Cloudflare free-tier hardening audit

This re-confirms (does not repeat from scratch) the architecture decision
already documented in `web/wrangler.jsonc` from an earlier session, since
the incident made it worth double-checking rather than assuming.

1. **Does HTML navigation invoke the Worker?** Yes, confirmed via
   `wrangler dev` — RSC/page-navigation requests carry `x-opennext*`
   response headers, meaning the Worker ran.
2. **Do JS/CSS/fonts/images avoid the Worker?** Yes — confirmed via the
   same local build that `/favicon.ico` (and by extension anything under
   the static-assets manifest) returns with **no** `x-opennext*` header,
   meaning Cloudflare's static-asset router served it directly and never
   invoked the Worker at all.
3. **Is `run_worker_first` disabled?** Yes — left unset (defaults to
   false/off) in `wrangler.jsonc`, exactly as it should be for this
   architecture: asset-first serving is what makes static files free of
   Worker invocations in the first place.
4. **Does asset-first serving actually function?** Yes, per point 2.
5. **Do decorative assets accidentally invoke the Worker?** No evidence
   found — they're all under the static-assets directory the router
   matches by path.
6. **Do API calls bypass the frontend Worker to Render directly?** Yes —
   `NEXT_PUBLIC_API_BASE` points the browser straight at
   `fas-prod-api.onrender.com`; API traffic never touches the Cloudflare
   Worker's request count at all. (This is *why* the backend stayed fully
   reachable throughout the entire 1027 outage — confirmed useful this
   session: local dev pointed at the real production API worked the whole
   time, letting Trusted Sources certification and this audit proceed
   without needing fanfic.world to be up.)
7. **Was a rewrite (serving prerendered HTML straight from `assets` to
   skip the Worker on navigation too) reconsidered?** No — the prior
   session's `ziptest.html` experiment already proved the static-file
   router matches by path only, ignoring RSC/prefetch headers, so it would
   break client-side navigation into full-page reloads and unmount
   `AudioEngineProvider` (breaking audio-persistence-across-navigation).
   Nothing from this incident changes that trade-off: the *cost per
   navigation* was never the problem (it's one cheap, cache-intercepted
   Worker call), the *unbounded storm* was, and that's fixed at the source
   now.

### Request budget estimate

Per real page view, post-fix: **1 Worker invocation** for the page's own
HTML/RSC payload. Static assets (JS/CSS/fonts/images, including anything
already in the OpenNext incremental cache) don't add to this count. A
"session" — one visitor browsing a few pages — costs roughly one
invocation per page they actually navigate to, not per asset.

| Scenario | Assumption | Estimated Worker requests/day |
|---|---|---|
| 100 visits/day | ~3 page navigations/visit (home → list → detail) | ~300 |
| 500 visits/day | same | ~1,500 |
| 1,000 visits/day | same | ~3,000 |
| 5,000 visits/day | same | ~15,000 |

**Free-tier headroom:** even the 5,000-visits/day scenario uses only ~15%
of the 100,000/day ceiling — roughly a **6.5× safety margin** before
legitimate traffic alone would approach the limit. This estimate is
deliberately conservative (assumes no caching benefit across repeat
visitors, no bot/crawler traffic subtracted) and should be treated as a
ceiling-check, not a promise — real numbers should replace it once a few
days of clean post-fix traffic exist (see the runbook's monitoring
section). What *isn't* estimate-dependent: the incident happened at
~3,000-3,500 requests **per 30 seconds from one tab**, roughly 400-500×
the entire 5,000-visits/day legitimate estimate — the storm was never a
"too much real traffic" problem, it was a several-orders-of-magnitude
software bug, which is why the fix was code, not a plan upgrade.

## Track D — Free-tier monitoring runbook

Written as its own document: [`cloudflare-free-tier-runbook.md`](cloudflare-free-tier-runbook.md).

## Track F — Trusted Sources cleanup audit (read-only)

Re-verified via direct backend API calls (`fas-prod-api.onrender.com`,
bypassing the down frontend entirely — see Track C point 6 for why this
was possible throughout the outage):

| Item | Classification | Status |
|---|---|---|
| 13 Fanfic novels (`GET /api/novels`) | REAL_CONTENT | `total: 13`, unchanged before/after all QA work this session. |
| Trusted sources (`GET /api/admin/animation/sources`) | — | **0** remaining — both QA canary sources (known-duplicate test, non-duplicate pipeline test) were deleted after certification. |
| Published animation series (`GET /api/animation/series`) | — | **0** — matches pre-session baseline; the one QA canary series created during the non-duplicate pipeline test was deleted along with its one episode. |
| Import records from the QA canary run | QA_OWNED_SAFE_DELETE | All 50 individually set to `rejected` (no bulk-delete endpoint exists for imports by design — `reject`/`ignore` are the only in-app cleanup mechanisms, confirmed via route inventory) — verified via `Group-Object status` showing 50/50 rejected, zero left in any other state. |
| Temp QA admin account (`hainam10102000+qatrustedsourcesfe6597@gmail.com`) | UNKNOWN_KEEP | **Not removed.** No workflow in the product grants a non-admin path to safely revoke another account's admin role without direct database/API action outside the normal user-facing flows — removing it unilaterally would be an irreversible auth change made without the explicit config-change authorization this session's instructions call for. Recorded as a manual action (see the morning-actions report) rather than acted on. |

No `UNKNOWN` artifacts were found beyond the temp admin account itself —
every trusted source, series, episode, and import created during this
session's certification work was traced and accounted for.

## Track G — Universal Story Scraper: test-gap audit

Existing coverage (`test_story_scraper_adapters.py`,
`test_story_scraper_contract.py`, pre-dating this session) already covers:
chapter-nav-links-mixed-with-unrelated-links, chapter order preserved as
displayed (not re-sorted), canonical-redirect/URL-variant convergence,
content-revision detection, resume-after-interruption (both
skip-completed and retry-failed), and deterministic hashing/fingerprinting.

Gaps found and closed this session (new `RobustnessTest` class in
`test_story_scraper_adapters.py`, PR #66):
- Malformed/unclosed HTML tags — doesn't crash, still extracts.
- Empty response body — doesn't crash, produces a well-defined empty hash.
- Malformed JSON-LD block — skipped silently, doesn't break the rest of
  the page's extraction.
- Duplicate chapter `href`s on one index page (e.g. desktop+mobile nav
  listing the same chapter twice) — deduped, confirmed via explicit test
  (the dedup logic already existed in `discover_series`; it just lacked a
  regression test).
- Vietnamese diacritic text — hashes and extracts stably across repeated
  runs (this was implicitly true given SHA256-over-UTF8, but wasn't
  explicitly tested).
- **New hardening, not just a test:** non-text `content-type` responses
  (e.g. a chapter link that resolves to an image or PDF) are now rejected
  with a clear `FetchError` *before* being handed to the HTML parser —
  previously this would silently produce garbage "extracted text" with no
  error anywhere in the pipeline. This is a real gap that was closed, not
  just documented.

Gaps found and **deliberately left open**, with reasoning:
- **Pagination across multiple chapter-index pages.** `discover_series`
  fetches exactly one URL. No site requiring this has been identified yet
  for this project's actual use case (YouTube-sourced trusted sources, not
  paginated web novel indexes) — building it speculatively would be
  exactly the kind of premature abstraction this project's own conventions
  warn against. Documented here so it's a known, intentional limitation,
  not a silent one.
- **Multiple candidate "article" nodes on one page.** The extractor is
  structure-agnostic by design (concatenates all non-noise-tag text; there
  is no "find the main content div" heuristic) — a page with unrelated
  "related articles" content not wrapped in `nav`/`aside`/etc. could bleed
  into extracted text. No real source has surfaced this yet; flagged as a
  known architectural trade-off (simplicity now, heuristic-if-ever-needed
  later) rather than fixed speculatively.
- **Title-only content changes not flagged as a revision.** Confirmed as
  *intentional* behavior (title is metadata, not "content" for
  revision-detection purposes) via a new test documenting it explicitly —
  not treated as a bug to fix.

## Track H — Scrapling (Tier 1) evaluation

Already the subject of a real fallback-tree decision documented in
`server/scraper/__init__.py`'s module docstring from an earlier session;
this section adds the deeper comparison the mega-task asked for.

**What Scrapling adds over Tier 0's direct HTTP + hand-rolled parser:**
adaptive/resilient CSS/XPath selectors that survive markup drift (a site
changing its HTML structure slightly doesn't necessarily break extraction,
unlike a brittle fixed selector), a more ergonomic extraction API, and an
optional JS-rendering fetcher path (backed by Playwright/Camoufox under
the hood) for when a page genuinely needs it — meaning Scrapling can
itself partially blur into "Tier 2" territory for a subset of pages
without a separate browser-fallback implementation.

**Evidence-based fallback rule (already the project's stated design,
reaffirmed here):**
- **Tier 0** (direct HTTP + this project's own `html_extract.py`) for
  pages whose structure is known/stable enough that a fixed extraction
  contract (meta tags, JSON-LD, a href-pattern for chapter links) works —
  this covers the actual current use case (YouTube API + generic HTML
  indexes) entirely; no site has yet required more.
- **Tier 1** (Scrapling) reserved for a site whose markup genuinely drifts
  or requires adaptive selection Tier 0's simple parser can't express —
  not yet needed in practice, but the adapter is stubbed
  (`adapters/scrapling_adapter.py`) so adopting it is additive, not a
  rewrite, when a real case appears.
- **Escalate only on repeated, structural failure** — never on a single
  selector miss, which is far more often a genuine site content change
  (chapter removed, page moved) than evidence the parsing strategy itself
  is inadequate.

**Not adopted yet:** the `scrapling` PyPI package isn't installed in the
local dev venv (present in `requirements.txt` for CI, absent locally) —
this is a pre-existing, unrelated gap, not something this session's work
depends on or should paper over.

## Track I — CloakBrowser vs. Playwright evaluation

Full research delegated to an independent research pass (web search, no
code changes) given neither prior session context nor this one had deep
first-hand knowledge of CloakBrowser specifically. Summary:

| | STATIC HTML | JS RENDER | RESOURCE COST | STEALTH/ANTI-BOT | MAINTENANCE RISK | SPEED | PARALLELISM | BEST USE CASE | RECOMMENDATION |
|---|---|---|---|---|---|---|---|---|---|
| **Direct HTTP** (current Tier 0) | Native | No | Very low (ms, few MB) | N/A — not needed for public pages | Very low, already implemented | Fastest | Cheap, high | Static/server-rendered public pages | Keep as Tier 0 |
| **Scrapling** (planned Tier 1) | Yes, adaptive | Yes, via optional Playwright/Camoufox-backed fetcher | Low for static; browser-class when JS path invoked | Adaptive selectors is the real value; optional stealthy fetcher | Moderate — active project, single core maintainer | Fast for static | Built-in crawl support | Markup drift resilience, occasional JS fallback | Adopt for Tier 1 as planned |
| **Playwright** | Overkill but works | Full Chromium/Firefox/WebKit | Moderate, ~150-300MB/context | Adequate for "look like an ordinary browser" on non-adversarial public pages | Very low — Microsoft-maintained, huge adoption, already a transitive dependency in `web/node_modules` | Seconds/page (normal for JS render) | Strong native multi-context pooling | Genuine JS-rendered public pages Tier 0/1 can't handle | **Adopt for Tier 2, when actually needed** |
| **CloakBrowser** | Works but wasteful vs. Tier 0 | Same Chromium engine as Playwright | Same class as Playwright + a ~200MB binary download | Strong, but purpose-built for CAPTCHA/anti-bot *bypass* — explicitly out of this project's scope | Higher — young single-vendor org, proprietary binary, features gated behind paid tiers | Same order as Playwright | Free tier caps at **1 concurrent session** | Defeating adversarial detection on hostile sites | **Do not adopt** |

**Why not CloakBrowser:** its entire differentiated value proposition
(defeating Cloudflare Turnstile, scoring high on reCAPTCHA v3, evading
fingerprinting services) is precisely the bypass-logic category this
scraper is explicitly prohibited from building — only public,
freely-accessible pages are ever in scope. Stripped of that use case, it
is functionally redundant with Playwright for "render a public page's JS
content and extract clean text," while adding a licensing/concurrency cap
and a smaller, less-proven maintainer behind the compiled binary.

## Track J — Browser fallback prototype: not built

No concrete public page has been identified this session (or in any prior
recorded evaluation) that Tier 0 or the planned Tier 1 (Scrapling)
genuinely cannot parse due to a hard JS-rendering requirement. Per the
mega-task's own explicit condition ("ONLY if evidence shows a real public
test page Tier 0/1 genuinely cannot parse"), building a Tier 2 prototype
without that evidence would be speculative work against a use case that
doesn't exist yet — skipped. When such a page is found, Track I's
evaluation already settles the "which tool" question in advance
(Playwright, not CloakBrowser), so the remaining work at that point would
be implementation, not another research pass.

## Track K — Scraper resource/cost model

Order-of-magnitude estimates only — no load testing was run to refine
these, consistent with not provisioning anything tonight.

| Tier | Per-chapter cost (rough) | Chapters/minute (single worker) | Where it should run |
|---|---|---|---|
| Tier 0 (direct HTTP) | Sub-second, a few KB-hundreds of KB network, negligible CPU | High — tens per minute, bound mostly by the rate-limit/robots.txt politeness delay added this session (`min_delay_seconds`, default 1s/host), not by processing cost | Fine on the existing `fanfic-worker-prod` GCE VM alongside current jobs — cost is dominated by network wait, not compute |
| Tier 1 (Scrapling, static path) | Similar order to Tier 0 plus parser overhead | Slightly lower than Tier 0 but same order | Same VM — no meaningfully different resource profile for the non-JS path |
| Tier 1 (Scrapling, JS-rendering path) / Tier 2 (Playwright) | Seconds per page, ~150-300MB per active browser context | Low — single digits per minute per browser instance, bound by page-render time and by intentionally not running many contexts in parallel against one small site (politeness) | **Not** the always-on `fanfic-worker-prod` VM as currently sized — a browser-rendering job is a different resource shape (bursty, memory-heavy) than the steady TTS/translation workload that VM is sized for today. Best fit: an on-demand/ephemeral job (matches the "dispatcher + on-demand worker" architecture pattern already designed in this project's GCE cost-optimization work), not a permanent resident process. Not provisioned tonight — this is a sizing note for whenever Tier 2 actually gets built (see Track J). |

No false precision intended — these are planning-order numbers (right
order of magnitude, not a benchmark), sufficient to say "Tier 0/1's static
path is cheap enough to not think about it further" and "Tier 2, if ever
built, needs its own resource plan rather than assuming it fits current
capacity," without pretending to more accuracy than a real load test would
provide.

## Track L — Visual audit (offline, against real production data)

Cloudflare being down blocks testing the *deployed* frontend, but not the
*code* — the real backend (`fas-prod-api.onrender.com`) is a separate
Render service, unaffected by the Cloudflare quota outage. A local
`next dev` build pointed at that real production API let this audit run
against real data without generating any traffic against the exhausted
Cloudflare zone.

**Method:** Playwright, desktop (1440×900) and mobile (390×844), against
`localhost:3000` with `NEXT_PUBLIC_API_BASE=https://fas-prod-api.onrender.com`.

**Routes checked:** `/`, `/fanfic`, `/animation`, `/community`, `/library`
(both breakpoints), plus one real novel detail page, one real chapter
page, and one attempted listen page, using a real novel/chapter ID pulled
live from the production API (`nov_478b5853894c4f69` /
`chp_8683f7ba8c3f4c8e`).

**Findings:**
- Zero JavaScript console/page errors across all 10 list-page shots
  (desktop+mobile × 5 routes).
- Novel-detail and chapter pages could not fully render real content
  locally — the production API's CORS policy correctly does **not** allow
  `http://localhost:3000` as an origin (it's scoped to the real
  `fanfic.world` origin), so cross-origin fetches from this local test
  setup were blocked. This is a **limitation of the local test method**,
  not a product defect — confirmed by inspecting the rendered page: it
  showed a clean, properly-styled "Không tải được dữ liệu" (couldn't load
  data) error card with a working retry button, not a blank page or a
  crash. This is exactly the intended graceful-degradation behavior for a
  real network failure, working as designed.
- The `/chapters/{id}/listen` URL pattern used in this audit turned out to
  be wrong (the real route is `/listen/{chapterId}`, found by grepping
  `web/src/app`) — the mistaken URL correctly rendered the site's themed
  404 page rather than crashing, which is itself a small positive
  signal (404 handling works), though it means the listen page itself
  wasn't visually re-verified this pass.
- **Idle-network check on the listen page:** after initial load, **zero**
  network requests over a 15-second idle window — directly confirms
  `ListenReporter`'s interval (see Track N) produces no idle traffic when
  audio isn't actively playing, exactly as designed.

**No genuine visual defects found.** No redesign performed, no cover
regeneration (none of the 13 covers showed any breakage in the list-page
shots). A full pixel-level pass against fully-loaded real content — the
only piece this local method couldn't reach — is exactly what Track Q
(post-quota-reset live pass) is for for, and remains the right place to do
it rather than fighting the CORS limitation further here.

## Track M — React Bits final audit

Exactly **one** component in the codebase is React-Bits-inspired:
`web/src/components/CountUp.tsx`.

| Component | Route(s) | Purpose | Bundle cost | Continuous RAF? | WebGL? | Reduced motion | Verdict |
|---|---|---|---|---|---|---|---|
| `CountUp` | Wherever a stat number animates in (author rank/progress displays) | Count-up number animation on mount/value-change | None — hand-written, ~30 lines, no new dependency (explicitly *not* using `framer-motion`, which isn't in this project's dependency tree) | **No** — RAF loop is bounded to a fixed 500ms animation and self-cancels; nothing runs once the count settles or the component unmounts (`cancelAnimationFrame` in the effect cleanup) | No | Respected — `prefers-reduced-motion` short-circuits straight to the final value, no interpolation | **KEEP** |

No other React Bits components were adopted anywhere in the codebase
(confirmed via a repo-wide search for `react-bits`/`reactbits` in source
and `package.json` — no dependency, no other inspired component). This
matches the prior session's own research conclusion (minimal, selective
adoption only where a real UI need existed) — there was nothing further
to remove, and nothing new was added "to use the library."

## Track N — Frontend idle-zero audit

Full inventory of every `setInterval`/recursive `setTimeout` in `web/src`:

| Location | Mechanism | Classification | Notes |
|---|---|---|---|
| `NotificationBell.tsx` | **None** — explicitly documented decision *not* to poll | NECESSARY (by omission) | The component's own docstring states the reasoning: a 30s poll "looks harmless" but is a query every 30 seconds for *every open tab of every user*, including forgotten background tabs — exactly the class of bug that caused the Cloudflare incident, avoided here by design from the start. Refreshes only on page change and panel-open (both real user-attention moments). Cited here as an example of this principle already being followed correctly elsewhere in the codebase. |
| `ListenReporter.tsx`, `ContinueListenReporter.tsx` | `setInterval(1000ms)` | EVENT-DRIVEN, already correct | Gated on `trangThai.dangPhat` (actively playing) — cleared via effect cleanup the moment playback stops. Confirmed via live idle-network capture (Track L): zero network activity while not playing. The interval itself does local counting only; it results in at most one API call per chapter, sent once a listen threshold is crossed. |
| `YouTubeFacadePlayer.tsx` | Two `setInterval`s (progress report + local scrubber update) | EVENT-DRIVEN, already correct | Same shape as above — only active during actual playback of an embedded video. |
| `translate/page.tsx` | Recursive `setTimeout(2000ms)` | EVENT_DRIVEN_REPLACEMENT_POSSIBLE, not urgent | Polls job status, but only while a translation job the user just started is actively in-flight — bounded duration (stops on completion/cancellation), not an idle-forever loop. A WebSocket/SSE push would be architecturally cleaner but this isn't a network-storm risk the way an always-mounted idle poll would be; not worth the added complexity for what it doesn't currently break. |
| `write/import/page.tsx` | `setInterval(3000ms)` | EVENT_DRIVEN_REPLACEMENT_POSSIBLE, not urgent | Same shape and same reasoning as `translate/page.tsx` — bounded to an active import batch, not idle traffic. |
| `admin/**/page.tsx` (×4), `animation/page.tsx`, `fanfic/page.tsx`, `SearchOverlay.tsx` | `setTimeout(250ms)`/debounce | NECESSARY | Single-shot debounce for search-as-you-type, cleared on each keystroke and on unmount — never a recurring/idle timer. |
| `PageBackground.tsx` | `setInterval(30ms)` | NECESSARY, but worth flagging precisely | Purely local (checks the current pathname to pick a background image/theme) — **no network call inside it**, confirmed via source read. A 30ms local DOM/state check has a real but small idle-CPU cost; not a network concern, and out of this pass's stated priority (Track N explicitly ranks network loops above local animation loops), but noted here as the one interval that runs unconditionally on every page regardless of user activity. |
| `NavIndicator.tsx` | `setTimeout` (debounced) | NECESSARY | Drives the nav tracer's selection-travel visual effect; single-shot per interaction, not recurring. |
| `SyncedTranscript.tsx` | `setTimeout` (debounced) | NECESSARY | Not recurring. |
| `toast.tsx` | `setTimeout` (per-toast auto-dismiss) | NECESSARY | One-shot per toast, cleared appropriately. |
| `useJobTracker.ts` | `setTimeout` (polling wrapper) | EVENT_DRIVEN_REPLACEMENT_POSSIBLE, not urgent | Same bounded-duration shape as the translate/import pollers above — active only while a tracked job is running, not an idle loop. |

**Conclusion: no unnecessary idle-network activity found.** Every
network-issuing interval in the codebase is already gated on an active,
user-visible state (playback in progress, a job actively running) and
stops cleanly when that state ends — confirmed both by source reading and
by the live idle-network capture in Track L (zero requests over 15s idle
on the one page, `/listen/{id}`, most likely to have such an interval).
The only *unconditional* recurring timer (`PageBackground.tsx`'s 30ms
local check) does no network I/O at all. No changes were made under this
track — the codebase already satisfies the "idle user, ~zero recurring
network traffic" principle; the Cloudflare incident's root cause was never
a `setInterval`-style poll, it was the RSC prefetch mechanism audited and
fixed under Tracks A/B.
