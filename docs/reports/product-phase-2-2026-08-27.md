# Product phase 2 — router-driven — final report

Moving Fanfic World from technically-ready infrastructure toward an
actually usable content-ingestion operation, using the AI Engineering
Router built earlier the same day. Full task-by-task detail is in
`router-burn-in-2026-08-27.md`; this is the product-facing summary.

## CLOUDFLARE MONITOR

**Done and scheduling-ready, not yet switched on.** Systemd timer/service
for the GCE VM (mirrors the existing `fanfic-worker-prod-health` pattern),
plus a portable API-token path since the local wrangler OAuth token was
found to be short-lived (unsuitable for an unattended weekly/monthly
schedule) and the VM has never run `wrangler login`. Live-validated
against real production data (a real 932 req/hour spike observed, still
comfortably under the WARNING threshold). Not activated — documented as
a deliberate, ready-to-run manual step, same posture as the existing
`run_websub_reconciliation.py` scheduling.

## YOUTUBE ONE-LINK UX

**Structurally complete, confirmed by reading the real code — live
re-verification blocked.** Paste-one-URL → mandatory preview → confirm
already works for channel/@handle/playlist/video, with no direct-create
path that skips preview. Live end-to-end re-testing against a real
YouTube source needs admin access, which was intentionally revoked at
the end of the prior session and can't be self-granted — recorded as a
manual follow-up (see below), not silently skipped.

## CHANNEL SCAN

Backend-implemented and already certified PASS in the prior session
(`scanTrustedSource` → `TrustedSourceService.scan_source`). Unchanged
this session; re-confirmed present via code reading, not re-tested live
(same admin-access blocker).

## SERIES GROUPING

Backend clustering (`discoverChannel`/`_gom_nhom_ung_vien`) already
exists and was already certified PASS. This session adds a genuinely new
layer on top: `server/scraper/vn_title_parser.py`, a deterministic
structural parser (episode single/range/part/chapter/season/full-work/
side-story as independent signals) plus a HIGH/MEDIUM/LOW confidence
scorer comparing two raw titles. Deliberately standalone for now (not
yet wired into `trusted_source_service.py` — confirmed via reading the
real code that it's additive to `episode_parser.py`/`series_fingerprint.py`,
not a duplicate). An independent Codex review of exactly this file found
and this session fixed 5 real bugs, 2 of them genuine over-merge risks
(a bracket-stripping bug that would have merged two different fandoms
sharing an episode number; a filler-word-only match that could hit HIGH
confidence with zero real content overlap) — both verified fixed by
direct execution against the real function before merging, not just
trusting the fix report.

## EPISODE ORDERING

Backend-implemented (`server/episode_parser.py`, `chapter_number`/
`order_index` wiring with duplicate-episode conflict detection) and
already certified PASS. Confirmed present via code reading this session;
not re-tested live (same blocker).

## REVIEW QUEUE

Backend-implemented (pending-count + Import Queue admin page with
bulk approve/reject/ignore) and already certified PASS. Unchanged this
session. The scraper side's own review queue (`ReviewItem`s from
`StoryIngestionPipeline.run()`) is a separate, in-process concept — see
SCRAPER/QUALITY below.

## WEBSUB AUTO UPDATE

Backend-implemented and already certified PASS (subscribe, notification
handling, periodic reconciliation). Now reachable with one click for a
brand-new source via last session's "Thiết lập nhanh" addition — no
change to the underlying mechanism itself this session.

## SCRAPER

**TIER 0:** Hardened further — the ingestion pipeline (`server/scraper/
pipeline.py`) now attaches a deterministic quality report to every
successfully-normalized chapter and exposes a `state` accessor for
bulk-run orchestration. Index pagination and content-type/robots.txt/
rate-limit/retry hardening from the prior session are unchanged and
still covered by their own tests.

**TIER 1 (Scrapling):** Not adopted. No evidence from this session's real
canary required it.

**TIER 2 NEEDED:** No. The real canary (below) fetched and correctly
processed a genuinely irregular real-world multi-chapter site end to end
via Tier 0 alone.

**REAL CANARIES:** One real external multi-chapter site this session —
Wikisource's *The Wonderful Wizard of Oz* (public domain, robots.txt
confirmed permissive), fetched through the actual production
`HttpFetcher` (robots.txt respected, rate-limited), not a fixture.
`discover_series` correctly found all 24 real chapter URLs in the right
order; a `chapter_limit=3, dry_run=True` pipeline run correctly fetched,
normalized, and classified 3 real chapters as NEW with zero failures.
Combined with the prior session's 3-page canary (Gutenberg, Wikipedia,
Wikisource-versions-page), Tier 0 has now been validated against 4 real
external targets total, no auto-publish, no mass crawl at any point.

**QUALITY:** `server/scraper/quality.py` — deterministic (no AI/LLM)
BLOCK/WARN checks: title validity, chapter number/order plausibility,
encoding sanity (mojibake/control-character/surrogate detection),
Vietnamese diacritic integrity, navigation-text leakage, duplicated
paragraphs, truncation, text-size bounds (both too-short and
"probably grabbed a whole book, not a chapter" too-large), and source
URL/domain preservation. Directly grounded in this session's own real
canary evidence (the nav-leakage check exists because of a real
Wikipedia "Jump to content" bleed-through found last session; the
oversized-text check exists because of the real ~718,000-character
single-fetch result from Project Gutenberg). Wired into the pipeline's
`ReviewItem` — labels only, never auto-rejects.

## BULK IMPORT

Architecture decided by an independent Opus review that read the real
`server/bulk_import_service.py`/`bulk_import_domain.py` first and
correctly rejected reusing it directly (it's coupled to a known owner/
novel and writes real Chapters — wrong fit for a review-queue-only,
no-owner-yet scraper). Instead, `server/scraper/run_state.py` +
`server/scraper/bulk.py` (`ScrapeRunService`) copy that system's *proven
mechanism* — deterministic-id create-once, status-field cancellation,
phase-driven drive loop, counters recounted exactly once at finalization
— with zero shared code and zero changes to the existing write/import
flow.

**10 / 100 / 500:** The same `drive_once(run_id, max_chapters=N)` cycle
handles all three scales identically — it processes up to
`chapters_per_cycle` PENDING items per call regardless of how many
total items the run has, so a 500-chapter run is just more cycles of
the same bounded operation, not a different code path. Not yet
exercised at real 100/500 scale against a live site (would mean a much
larger real fetch than "do not mass crawl" allows for a validation
pass) — validated at the unit level with fixture-backed multi-item runs.

**RESUME:** `ScrapeState`'s existing `to_json()`/`from_json()`
persistence, unchanged, still the resumability mechanism; the new
`ScrapeRun`/`ScrapeRunItem` layer adds crash-window reconciliation on
top (`_reconcile_items_from_state`, covered by a dedicated test) so an
item stuck PENDING after a crash between the state write and the item
write is correctly picked up as done on the next `plan_run`, not
silently re-fetched or silently lost.

**IDEMPOTENCY:** Run identity is the series URL alone (not the chapter
list or `chapter_limit`), so a small canary and a later full run of the
same series share one run and only ever gain items, never duplicate or
lose them — verified by a dedicated growth test. Cancellation is the
other hard safety property: checked once per item, strictly before that
item's own fetch, so a cancelled run's untouched items are provably left
PENDING, never marked failed or half-written — the single most
rigorously tested behavior in this addition.

## PRS

`#76` Cloudflare monitor scheduling · `#78` Content quality scoring ·
`#79` Bulk-run service · `#77` Vietnamese title parser (including the
post-Codex-review bug-fix commit) — all merged, all via normal CI-gated
review, zero admin bypasses.

## TESTS

2928 backend tests on `main` (up from 2809 at the start of this phase),
31 `scripts/` tests, all green. New this phase: 47 quality-scorer tests,
16 bulk-run-service tests, 54 title-parser tests (49 original + 5
Codex-driven regression tests), plus the token-fallback tests from
Phase 1. Zero regressions in any pre-existing test at any point.

## CI

Green on every merge — no `--admin` bypass used anywhere this phase (the
one prior emergency-authorized bypass from an earlier incident does not
extend here, and wasn't needed).

## PRODUCTION CHANGES

None. Every change this phase is backend/scraper library code, test
code, or not-yet-activated deploy configuration (the Cloudflare monitor
timer/service exist on disk but were never installed on the live VM).
Nothing was deployed to `fanfic.world` or `fas-prod-api`.

## NEXT BEST STEP

Get the one remaining manual blocker — a temporary admin grant on
`FAS_ADMIN_USER_IDS` — so the YouTube one-link flow, channel scan, series
grouping, episode ordering, review queue, and WebSub auto-update can all
be re-verified live against a real source in one pass, closing the gap
between "structurally confirmed by reading the code" and "actually
watched it work."
