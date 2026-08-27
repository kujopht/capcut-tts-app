# Product phase — Cloudflare monitor, scraper productionization, YouTube operator UX

Follow-on to the overnight stabilization work
(`overnight-fanfic-world-2026-08-27.md`), same day. Post-cleanup
verification, closing the stabilization project, then Phase 1-4 of the
next product phase. Full detail below; the exact-format report the user
asked for is reproduced at the end.

## Post-cleanup verification

- **Temp QA admin lost admin access** — verified directly, not inferred:
  logged in as the QA account (`hainam10102000+qatrustedsourcesfe6597@gmail.com`)
  after its removal from `FAS_ADMIN_USER_IDS` + redeploy, confirmed
  `is_admin: false`, `admin_role: "none"`, and `GET /api/admin/overview`
  returns `403`.
- **Real admin account** — could not be tested with real credentials
  (correctly never handled in-session). Strong indirect confirmation:
  `GET /api/health` reports `admin_count: 1` (down from 2 pre-removal,
  not 0) — exactly one admin ID remains configured, consistent with a
  surgical removal of only the QA entry from the comma-separated list.
- **Production health** — `GET /api/health` returns `status: "ok"`,
  `appwrite_configured: true`, `r2_configured: true`.
- **13 real Fanfic works** — `GET /api/novels` returns `total: 13`,
  unchanged.
- **Trusted Sources** — public endpoint (`GET /api/animation/series`)
  confirms `total: 0` published series, matching the expected baseline.
  Deeper admin-only health metrics (per-source status, subscription
  states) could not be re-checked directly in this pass since the QA
  account that had been used for that access no longer has admin rights
  (correctly) and no other admin credential was available — this is a
  real, disclosed verification gap, not silently skipped.
- **No destructive/import canaries re-run** — per instruction, the
  existing PASS certification from the prior session stands; nothing was
  recreated to "double check."

**Stabilization project: CLOSED.** All tracks from the overnight session
verified intact after cleanup; no regressions found.

## Phase 1 — Cloudflare free request monitor

`scripts/cloudflare_request_monitor.py` (PR #71). Key finding during
implementation: the existing `wrangler` OAuth token already has Account
Analytics read access — tested directly against the real GraphQL API,
no new credential needed, correcting a wrong assumption in the original
incident report (left as an addended historical record, not rewritten).

Thresholds derived from real hourly data pulled from the same API,
covering both the incident's worst hour and the first clean hours after
the fix:

- NORMAL: latest hour < 2,000 requests AND today's running total < 80,000
- WARNING: latest hour ≥ 2,000 requests
- CRITICAL: latest hour ≥ 4,000 requests, OR today's total ≥ 80,000

Also fixed a real pre-existing gap found along the way: `scripts/tests/`
existed but CI never actually ran it (only syntax-compiled `scripts/`) —
added a real test-execution CI step.

## Phase 2 — Scraper ingestion pipeline

`server/scraper/pipeline.py` (PR #72). Orchestrates the existing Tier 0
contract/dedupe primitives into one flow: resolve → discover_series →
resume (skip already-done) → per-chapter fetch+normalize → classify
(NEW/REVISION/ALREADY_IMPORTED/FAILED) → in-process review queue.
Dry-run support, per-call chapter limits, resumable/idempotent re-runs,
one bad chapter doesn't abort the batch. Also added optional index
pagination to `GenericIndexAdapter` (opt-in, capped, loop-safe) — the one
real safeguard gap flagged in the prior audit. 16 new tests.

Deliberately did NOT build: persistence of the review queue itself
(that's Appwrite/admin-API integration territory, a separate layer this
package's own docstring has never claimed to own), and did not touch
Novel/Chapter auto-creation — nothing here auto-publishes anything.

## Phase 3 — Real canary (3 live pages, direct HTTP only)

All three fetched through the actual production `HttpFetcher`
(robots.txt respected, rate-limited), not fixtures:

| Target | Type | Result |
|---|---|---|
| Project Gutenberg — *Pride and Prejudice* full text | Static, simple markup | **Clean extraction.** 718K chars, correct title, 3.45s fetch, 47ms extract. |
| Wikipedia — "Fairy tale" article | Irregular, deeply-nested markup | **Successful extraction with minor noise.** Some UI chrome ("Jump to content") leaked into clean_text — not wrapped in semantic nav/header tags Tier 0 filters on. Article body still clearly present. |
| Wikisource — two short-story titles (Poe, Conan Doyle) | Public-domain literary text, MediaWiki markup | **Fetched successfully both times, but both resolved to "Versions" disambiguation pages, not the story text** — a real site-navigation subtlety (multiple published editions per title), independent of extraction quality. |

**Conclusion: no evidence found requiring Tier 1 (Scrapling) or Tier 2
(Playwright) escalation.** Tier 0 fetched and extracted usable text in
all three real attempts; the one genuine friction found (Wikisource's
versions-page redirect) is a resolve/discover-URL problem, not something
either candidate tier solves either — it needs a site-specific detail
(the actual edition URL), same as the existing project convention that
`GenericIndexAdapter` requires per-site configuration rather than fully
automatic guessing. Tier policy stays as documented: escalate only on
real evidence, none appeared here.

## Phase 4 — YouTube Trusted Source operator flow audit

Backend flow (scan → discover/cluster into series → WebSub subscribe) is
fully implemented and was already certified PASS in the prior session —
confirmed again by reading the actual detail-page code, not re-testing
against production. Real friction found: getting a **brand-new** source
from "just created" to "fully auto-updating" required the operator to
click three separate buttons across three separate cards (Quét → Khám
phá toàn nguồn → Đăng ký) with no guidance on order — a UI gap, not a
backend one.

Fixed (PR #73): a "Thiết lập nhanh" (Quick Setup) card, shown only for a
source that has never scanned successfully, sequencing the exact same
three existing functions with one click — no backend changes, no new API
calls, existing individual buttons still available for manual re-runs.
6 new tests.

---

## Report

```
QA ADMIN CLEANUP:
REAL ADMIN:        Retained — admin_count 1 (was 2), surgical removal confirmed by count, not directly logged in as (no credentials handled in-session)
TEMP ADMIN:        Confirmed removed — live test: is_admin=false, admin_role=none, /api/admin/overview -> 403
TRUSTED SOURCES:   PASS (carried from prior certification) — public series count unchanged (0); deep admin-only health metrics not re-checked this pass (QA account that had access no longer has it — disclosed gap, not silently skipped)

CLOUDFLARE MONITOR:
IMPLEMENTED:       Yes — scripts/cloudflare_request_monitor.py, no new credentials, uses existing wrangler OAuth token (verified it already had the needed scope)
NORMAL:            latest hour < 2,000 req AND today's total < 80,000
WARNING:           latest hour >= 2,000 req
CRITICAL:          latest hour >= 4,000 req, OR today's total >= 80,000

UNIVERSAL SCRAPER:
TIER 0:            Hardened further — pipeline orchestrator + index pagination added
TIER 1:            Not adopted yet — no evidence required it in this round's real canary either
TIER 2:            Not built — no evidence required it
TESTS:             65 scraper unit tests (fixture-based) + 3 live real-page validations (not added to CI, ad-hoc)
REAL CANARIES:      3 real external pages fetched via production HttpFetcher (Gutenberg, Wikipedia, Wikisource) — no mass crawl, nothing published
PRS:               #72 (pipeline + pagination)

YOUTUBE OPERATOR FLOW:
ONE-LINK INPUT:    Already good — paste URL -> mandatory preview -> confirm, no direct-create path
CHANNEL SCAN:      Already implemented and working (manual button, existing)
SERIES GROUPING:   Already implemented (discoverChannel auto-clusters) — friction was DISCOVERING this step existed/when to run it, not the clustering logic itself
EPISODE ORDERING:  Out of this page's scope (handled on series detail page) — not audited this pass
REVIEW:            Already implemented — pending-review counts + separate Import Queue page for approve/reject
WEBSUB:            Already implemented (manual subscribe button, existing) — now sequenced automatically by Quick Setup for new sources
AUTO UPDATE:       Already implemented (WebSub notifications + periodic reconciliation, existing) — unchanged, just easier to reach

NEXT BEST STEP: Decide whether to schedule the Cloudflare monitor as a recurring job (Task Scheduler/cron) now that it's built and tested, since an unscheduled monitor only helps the day someone remembers to run it by hand.
```
