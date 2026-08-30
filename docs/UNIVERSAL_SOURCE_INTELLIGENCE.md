# Universal Source Intelligence (Story Harvester V5)

Provider-neutral acquisition/adapter/identity layer in
`server/scraper/universal/`, sitting **alongside** the existing V4
fiction-only pipeline (`server/scraper/contract.py`,
`server/scraper/adapters/`) — nothing in V4 was modified or removed.

## Source plugin contract (Phase 4)

Every source-class adapter — a known site (fiction, YouTube, Bilibili) or a
generic/unknown source — implements `universal.adapter.SourceAdapter`:

```
probe(url) -> bool
capabilities() -> SourceCapabilities
canonicalize(url) -> str
extract_metadata(url) -> dict
list_units(url) -> list[str]
fetch_unit(unit_ref) -> AcquisitionResult
normalize(unit_ref, acquisition) -> <normalized unit>
stable_identity(normalized_unit) -> str
```

`universal.adapter.StoryProviderAdapter` bridges every existing
`contract.StoryProvider` (`GenericIndexAdapter`, `ScraplingAdapter`) into
this contract with **zero changes** to those adapters.

## Acquisition tiers (Phase 2)

`universal.router.AcquisitionRouter`:

- **Tier 1 — direct HTTP.** Real, always available. Reuses the existing
  `HttpFetcher` — every SSRF/robots.txt/response-size/redirect protection
  already proven in `http_fetcher.py` applies here, not reimplemented.
- **Tier 2 — browser rendering.** Plugin hook (`AcquisitionPlugin`,
  `tier=TIER2_BROWSER`). **Not implemented** — no browser-automation
  dependency exists in this repo.
- **Tier 3 — structured/network intelligence.** Plugin hook
  (`tier=TIER3_STRUCTURED`). Firecrawl/Bright Data/Crawl4AI/provider APIs
  are all expected to be one of these. **None implemented** — no paid
  service is mandatory; a router with zero plugins is Tier-1-only, which
  is this repo's actual current, fully-supported configuration.

Tier selection is history-driven: the last tier that succeeded for a host
is preferred next time (in-memory only — persistence, if wanted, is the
caller's job, mirroring `harvest_scheduler.py`'s own "foundation-only, no
I/O" boundary).

## Known-source support

| Source class | Adapter | Metadata source | Notes |
|---|---|---|---|
| Web fiction | `StoryProviderAdapter` (wraps existing V4 adapters) | existing V4 fetch paths | incremental updates supported |
| YouTube | `adapters_v5.youtube_adapter.YouTubeAdapter` | public oEmbed endpoint | no video/audio download; `fetch_transcript()` always raises `NotImplementedError` by design |
| Video platform (generic) | `adapters_v5.generic_video_platform.VideoPlatformAdapter` (marker base) | — | future platforms extend this |
| Bilibili | `adapters_v5.bilibili_adapter.BilibiliAdapter` | public unauthenticated view-info API | no login/cookie handling, no download |

## Unknown-source onboarding (Phase 8)

```
unknown source
  -> evidence collection      universal.fingerprint.build_fingerprint(html, url)
  -> LLM proposal             universal.schema_proposal.propose_extraction_schema(fp, llm_fn=...)
  -> deterministic validation propose_extraction_schema's own field/hint checks
  -> fixture generation       caller supplies >=2 real fixture pages
  -> multi-page validation    universal.schema_proposal.validate_schema_against_fixtures
  -> candidate adapter        (caller builds one once trusted)
  -> explicit promotion       universal.schema_proposal.promote_to_trusted_adapter
```

`propose_extraction_schema`'s `llm_fn` is an injected seam
(`Callable[[str], str]`) — this module never calls a specific LLM
provider; wiring a real one (e.g. via the AI Router) is a follow-up
integration. **LLM output never becomes a production parser directly**:
every field name/hint is validated against a strict character class
before it becomes part of a `ProposedSchema`, and `promote_to_trusted_adapter`
is the one explicit gate — it requires the schema to work on **at least 2**
independently-validated fixture pages, not one lucky match.

See `server/scraper/universal/e2e_unknown_source.py` for the full flow
proven end to end on fixtures.

## Network intelligence (Phase 3)

`universal.network_intelligence`:

- `discover_embedded_json_endpoints(html, url)` — browser-free discovery,
  scans `<script type="application/json">`/`application/ld+json"` blocks
  already present in acquired HTML for API-shaped URLs. **Live XHR/fetch
  interception requires a headless browser and is not implemented** (see
  Tier 2 above) — this is the honest, deterministic subset that doesn't
  need one.
- `validate_endpoint_candidate(candidate, page_url, fetcher)` — the **one**
  gate allowed to mark a candidate trusted: same-origin check, fetched
  through the same guarded `fetcher` (SSRF/robots/redirect protections
  apply), JSON/text content-type, bounded response size
  (`MAX_CANDIDATE_RESPONSE_BYTES`, tighter than the general 20MB body
  cap), and an optional reproducibility check (fetched twice, same
  structural shape). **Never automatically trusted** — this function
  returns a verdict, it never acts on it.

## Canonical identity (Phase 9)

`universal.identity.CanonicalIdentity.identity_key()` prefers a
platform's own native ID (YouTube video ID, Bilibili bvid) over a
URL-based fingerprint when one exists — a platform's own ID essentially
never aliases across mobile/desktop/embed/tracking-parameter URL variants,
which a pure URL-canonicalization approach cannot fully collapse on its
own. Falls back to `dedupe.source_fingerprint(canonical_url)` (existing,
already-solved URL-alias/tracking-parameter layer) for sources with no
native ID concept.

## Change detection V2 (Phase 11)

`universal.change_detection.UnitChangeKind` — the same 7 states as the
existing fiction-only `change_detection.ChangeKind`, generalized past
"chapter": `UNCHANGED / NEW_UNIT / NEEDS_BASELINE / UPDATED_UNIT /
REMOVED_OR_UNAVAILABLE / SOURCE_METADATA_CHANGED / TRANSIENT_FAILURE`.
`to_fiction_change_kind()`/`from_fiction_change_kind()` translate to/from
the existing fiction enum.

## Security model (Phase 13)

- Every real network fetch — Tier 1 acquisition, endpoint-candidate
  validation, the (optional, not-CI) live smoke test — goes through the
  **same** `HttpFetcher`/injected fetcher. There is no second, unguarded
  request path anywhere in `universal/`.
- SSRF/robots.txt/redirect-loop/response-size protections are **inherited
  from `http_fetcher.py`**, not reimplemented — see
  `test_story_scraper_http_fetcher.py` for that layer's own coverage.
  `server/tests/test_universal_security_adversarial.py` proves the NEW
  code around them (the router, the endpoint validator) surfaces those
  failures as ordinary `FAILED`/`untrusted` results, never an uncaught
  exception, and never retries beyond what the underlying fetcher already
  does.
- Discovered network endpoints are **never auto-trusted** — see Network
  Intelligence above.
- Scraped content is untrusted data: `schema_proposal.build_llm_prompt`
  only ever sends an LLM a `SourceFingerprint` (already-bounded metadata),
  never raw HTML, with an explicit instruction to treat it as data, not
  commands. `fingerprint._clip()` strips control characters, bounds
  length, and redacts URL-embedded credentials (`user:pass@host`) from
  every field before it can reach a prompt or a log.
- Known, inherited, **not newly introduced** gap: DNS-rebinding is
  resolve-then-connect (documented already in `http_fetcher.SsrfBlockedError`),
  not a pinned-connection transport — closing it fully needs a custom
  transport, tracked as future work at the `http_fetcher.py` layer, not
  something `universal/` can fix independently.

## Rights boundary for media

Video adapters (`YouTubeAdapter`, `BilibiliAdapter`) acquire **metadata
only** — title, description, duration, thumbnails, counters. Neither
implements video/audio download. `YouTubeAdapter.fetch_transcript()`
always raises `NotImplementedError` — transcript acquisition is
deliberately deferred behind a future, separate, explicitly-authorized
access path, not attempted opportunistically.

## How to add another source

1. Decide its `SourceClass` (add a new one to `acquisition.py` only if it
   genuinely doesn't fit an existing class).
2. Implement `SourceAdapter` — for a known site, prefer a small,
   conservative adapter using a real public API/endpoint (see
   `BilibiliAdapter`); for an existing V4 fiction site, use
   `StoryProviderAdapter` to bridge it for free.
3. Register the adapter's own `SourceCapabilities` — declare
   `requires_browser=True` honestly if Tier 1 genuinely cannot handle it
   (nothing in this repo currently sets that to `True` for a real reason).
4. Write tests against `FixtureFetcher`, not live network — see any
   `test_universal_*_adapter.py` for the pattern. A single, clearly
   separate, non-CI live smoke script is fine for one-time verification
   (see `docs/HANDOFF.md`'s V5 section for the pattern used to verify
   `AcquisitionRouter` against a real public page).
