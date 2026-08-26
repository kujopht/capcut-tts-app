# Overnight report, continuation — Fanfic World, 2026-08-26 (phase 2)

Continuation of `overnight-fanfic-world-2026-08-26.md` after the user completed
the 3 morning actions from that report (FAS_ADMIN_USER_IDS live, schema key
revoked, fas-prod-api redeployed). Covers: closing Trusted Sources
certification, the Cloudflare frontend deploy + an incident during it, live
production visual QA, and the scraper's first Tier 1.

## PHASE 1 — Trusted Sources: BLOCKED_MANUAL, but the real root cause is now known

Live admin auth reverified first: QA account (`6a8dd1115b1ef86a585a`) now
logs in with `is_admin: true`, `/api/health` shows `admin_count` including
it. Confirmed via the normal API, not assumed.

**Known-duplicate certification**: created a single-video Trusted Source for
`XtJqhxbd1pY` (the same real overlap with novel `nov_6b42f7954f914227` proven
correct at the algorithm level in the previous session), scanned it. The scan
succeeded (`detected: 1`), but the resulting `VideoImport` document, read
directly from Appwrite, had **no `possible_duplicate_novel_id` attribute at
all** — not `null`, genuinely absent from the document's field list.

Investigated further: `curl`'d the `video_imports` collection's attribute
list directly from Appwrite. Confirmed: **the attribute does not exist on
the live collection.** It's been defined in `scripts/setup_appwrite.py`
since PR #55 (weeks ago), but that specific attribute was never actually
migrated onto production. Appwrite silently drops writes to attributes that
aren't in the collection schema rather than erroring, which is exactly why
this went unnoticed: the scan reports success, the algorithm computes the
right value, but it never lands anywhere.

Confirmed this needs schema-key access (tried the runtime key first — got
`401 missing scopes ["collections.write"]`, as expected given the
established security model). The temporary schema key from the previous
session was already revoked by the time this was discovered, so **this one
piece is now BLOCKED_MANUAL** — see `MORNING_ACTIONS_2026-08-26.md`.

**This supersedes the previous session's conclusion.** The algorithm was
correctly proven correct in isolation (calling `_phat_hien_novel_trung`
directly, bypassing the write path). What was never exercised until tonight
was the actual write-and-persist step through the real HTTP pipeline — and
that's where the gap actually is. No code fix is needed; this is a pure
one-attribute additive schema migration.

**Non-overlapping source certification: full PASS.** Created a Trusted
Source for the Library of Congress channel (same safe public-domain source
used in earlier canaries), then verified the complete pipeline for real:
URL resolution → historical scan (50 videos detected) → manual series
assignment → approved import (episode created) → **rescan idempotency**
(`already_tracked: 1`, same episode_id, no duplicate) → WebSub subscribe
(`pending` → `active` with a real 5-day lease from Google's hub, verified
after the actual wait) → unsubscribe → reconciliation (`sources_checked: 1,
sources_failed: 0`). All QA artifacts (1 source, 50 imports, 1 draft series,
1 episode) were verified as QA-owned by their `owner_id`/`created_by` before
deletion, then deleted. Final check: all 4 Trusted Sources collections at
`total: 0`, `novels` unchanged at `total: 18` (13 real works + 5 pre-existing
unrelated drafts, untouched).

**Verdict: YOUTUBE TRUSTED SOURCES PRODUCTION: BLOCKED_MANUAL** (one missing
schema attribute — algorithm and pipeline both proven correct otherwise).

## PHASE 2 — Frontend production release: deployed, with one self-caused incident

Confirmed the deployed frontend did **not** have PR #59/#60 live: fetched the
production CSS bundle directly and it still showed the old broken
`-webkit-backdrop-filter`-only declaration. No auto-deploy exists for this
Cloudflare Worker.

Found `npm run cf:deploy:production` already available and `wrangler`
already OAuth-authenticated locally with write scopes — an existing
authorized mechanism, used it as instructed.

**Incident**: the first deploy ran without `NEXT_PUBLIC_API_BASE` set, which
Next.js bakes in at build time (default `http://localhost:8000`). This
silently broke every page that fetches backend data — the homepage's static
hero content looked fine, but chapter/listen/detail pages showed "Không kết
nối được máy chủ." Caught this within minutes via live Playwright QA
(inspecting actual network requests, not just page load success), traced it
to the missing env var (confirmed correct value from
`docs/reports/production-deploy-portal-v7-2026-08-24.md`, which documented
the correct invocation from a prior deploy), and redeployed correctly:
`NEXT_PUBLIC_API_BASE=https://fas-prod-api.onrender.com npm run
cf:deploy:production`. Reverified — zero failed requests, correct content
everywhere tested. Production was in the broken state for several minutes
during active testing; no evidence of real user impact, but flagging
transparently rather than omitting it.

**Lesson recorded in `MORNING_ACTIONS_2026-08-26.md`** so this exact mistake
isn't repeated: `cf:deploy:production` must always be invoked with
`NEXT_PUBLIC_API_BASE` set explicitly.

## PHASE 3 — Live production visual QA (real Playwright, real screenshots)

Local Playwright (already installed as a transitive dependency in
`web/node_modules`, Chromium already downloaded) was available and used
directly against `https://fanfic.world` — no MCP browser tool was available,
so this was done via ad hoc Node scripts rather than a dedicated agent.

- **Header/glass**: `getComputedStyle` on `.site-header` returns
  `backdrop-filter: blur(18px) saturate(1.2)` live in the browser (not just
  present in the CSS text) — the fix genuinely renders. 73px header height,
  no horizontal overflow at 1920/1440/1280/390.
- **Nav tracer/selection travel**: measured `.nav-vach`'s computed
  `transform` every ~60ms while clicking `/` → `/fanfic`. Real interpolation
  observed (`translateX`: 0 → 36 → 68 → 82px), not a disappear/respawn.
  Active nav item: text color `rgb(236,239,247)` (readable) on a fully
  transparent background (`rgba(0,0,0,0)`) — confirms the selected state
  does not overpower the text.
- **Chapter audio-only state**: confirmed live, correct text and button,
  after the deploy fix above.
- **Novel detail page**: renders correctly with full cover art, glass-panel
  header treatment, clean typography.
- **13 covers**: the new art is genuinely deployed and loading (all 13 R2
  requests returned `200`, confirmed via network inspection) — but on the
  `/fanfic` grid specifically, a pre-existing decorative circular icon
  overlay (moon/star/rune motifs, from the existing `Ornaments` system,
  **not something added tonight**) sits on top of each card's cover art,
  partially obscuring it and making fandom differentiation harder at a
  glance in the grid view specifically. On the novel detail page, where this
  overlay isn't present, the cover art is fully visible and reads clearly.
  This is a real, pre-existing design tension worth a follow-up look, but is
  out of scope to change without more context on why the overlay exists.
- **`/admin/trusted-sources`** as an unauthenticated visitor: shows a clean
  404 ("Không tìm thấy trang này"), no crash.
- **`/animation`, `/community`**: load without visible breakage.

## PHASE 4 — Universal Scraper: Tier 1 added (Scrapling)

See PR #61. Evaluated Scrapling for real (installed in an isolated venv
first, tested its adaptive `.save()`/`.relocate()` API directly against
hand-built before/after HTML before writing any adapter code). Confirmed:
base package has no browser dependency, and its relocate capability
genuinely survives a full DOM restructure (class names, wrapper elements,
**and** the chapter URL scheme all changed) where an exact-selector
approach returns nothing. Implemented `ScraplingAdapter`, added `scrapling`
to `server/requirements.txt`, 7 new tests (parity with Tier 0, the
DOM-restructure justification case, no-fingerprint-yet safety, malformed
HTML, pagination, chapter reorder, source revision detection). CloakBrowser
and Playwright (Tier 2/3) evaluated in the fallback decision tree
(documented in `server/scraper/__init__.py`) but not implemented — no real
source has been identified yet that Tier 0/1 can't handle.

## PRs this phase

- #61 — Scrapling Tier 1 (merged). Independent review found one latent
  defensive gap (None-title guard, fixed) and CI caught a genuine
  Linux-vs-Windows libxml2 tag-soup-recovery divergence in the malformed-
  HTML test fixture (an unclosed `<title>` was swallowing everything after
  it differently across platforms) — fixed by keeping `<title>` well-formed
  so the fixture tests what it actually intends (unclosed `<p>` tags)
  without depending on ambiguous cross-platform recovery behavior.

No production data mutations this phase beyond the QA-cleanup already
described (all QA-owned, all deleted, verified). No real content published.
The 13 real Fanfic novels were touched only via read-only duplicate-check
verification, as required.
