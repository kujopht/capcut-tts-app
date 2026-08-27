# Story Harvester V3 — Phase 12 direct HTTP vs Scrapling benchmark

Empirical basis for `DEFAULT_FETCH`/`ESCALATION_CONDITION` (formalized in
Phase 10's `server/scraper/tier_escalation.py`), since `scrapling` is not
installed in the main project environment and Phase 5/Phase 1's audits
had only ever described its adaptive-relocation behavior from a prior
session's report, not re-verified in this one.

**Method**: created a disposable, isolated `venv` (outside the project,
in scratch space — no change to `requirements.txt` or the shared
environment) with `scrapling==0.4.15` and `httpx` installed, then ran the
project's own `server/scraper/html_extract.py` (Tier 0) side-by-side with
`scrapling.parser.Selector` (Tier 1) against a real page already fetched
during Phase 11 (`en.wikisource.org`, 69,048 characters of raw HTML).
Confirms the install itself: base `scrapling` pulls in only
`lxml`/`cssselect`/`orjson`/`w3lib`/`tld`/`typing_extensions` — no
Playwright, no browser binaries, matching what `adapters/scrapling_adapter.py`'s
docstring already claimed.

## (1) Raw parse speed

Average of 30 runs on the identical cached HTML (no repeated network
calls):

| | ms/page | chars extracted |
|---|---|---|
| Tier 0 (`html_extract.py`, stdlib `html.parser`) | 6.67 ms | 13,100 |
| Tier 1 (Scrapling / `lxml`) | 2.33 ms | 14,583 |

Scrapling's `lxml`-backed parser is genuinely ~2.9x faster at raw
parsing on this real page (the character-count difference is `lxml`'s
whitespace/entity handling, not a correctness gap). **This is real but
not operationally significant**: a single chapter fetch is dominated by
network I/O (typically 100s of ms to low seconds per request, per the
default `HttpFetcher` rate limiting), not by a few milliseconds of
parsing — so a 4ms-per-page difference does not justify taking on a new
runtime dependency as the default path.

## (2) The actual differentiator: selector-drift survival

Two scenarios, matching what `adapters/scrapling_adapter.py`'s docstring
already claims, tested directly rather than taken on faith:

- **Chapter-link discovery via a fixed href pattern** (what
  `GenericIndexAdapter` actually does — Tier 0 never depends on
  class/tag names for this): simulated a site renaming `<ul
  class="chapter-list">`/`<a class="chapter-link">` to `<div
  class="story-index">`/`<a class="story-chapter-item">` while keeping
  the same `href`s. Tier 0 found all 3 links in **both** versions —
  unaffected, because it was never looking at the class name in the
  first place. Scrapling's fingerprint mechanism isn't needed here at
  all.
- **Content-region relocation** (what Phase 6's `content_extraction.py`
  does instead — score the DOM fresh each time, no memory of a prior
  successful selector): simulated a chapter body moving from `<div
  class="chapter-content">` to `<article class="story-body">` around the
  identical text node. Scrapling's `.save()`/`.relocate()` **correctly
  found the same node** across the rename (verified: relocated node's
  text matches exactly). `content_extraction.py` has no equivalent
  "remember what worked before" step — it re-scores the current DOM
  from scratch every time, which is fine as long as the new structure
  still scores as a plausible content region, but has no fallback if a
  redesign makes the real content region score ambiguously.

## Conclusion — DEFAULT_FETCH / ESCALATION_CONDITION

```
DEFAULT_FETCH = Tier 0 (GenericIndexAdapter / JsonLdAwareAdapter, direct HTTP)
```
Confirmed correct as the default: no dependency to install, parse-speed
difference is real but dwarfed by network I/O, and Tier 0 is already
immune to pure cosmetic (class/tag) changes for the one thing it depends
on class hints for at all (`_CONTAINER_HINT_RE` in Phase 6, which is a
*hint* toward candidates, not a hard requirement — the scorer still
considers untagged candidates).

```
ESCALATION_CONDITION = NO_STRUCTURE_MATCH on a domain with a PRIOR
    successful scan whose saved fingerprint can be relocated
    (Phase 10's tier_escalation.classify_page_signal() returning
    NO_STRUCTURE_MATCH, decide_escalation(tier1_available=True))
```
This is exactly what `server/scraper/tier_escalation.py` (Phase 10)
already encodes — this benchmark is the empirical justification for that
policy rather than a reason to change it. Escalation is explicitly
**not** triggered by speed, by AUTH_REQUIRED/CAPTCHA/PAYWALL (hard
safety boundary, unconditional refusal), or by a first-ever scan of a
new domain (no prior fingerprint exists to relocate from — Tier 1 has
"nothing more than Tier 0" in that case, per the existing module
docstring).

**`tier1_available` stays `False` in the real `_adapter_from_config`
dispatch** (`scraper_ops_service.py`): `scrapling` is confirmed not
installed in the actual project environment (only in this throwaway
benchmark venv, which was not merged into `requirements.txt` and leaves
no trace in the repo). Wiring `ScraplingAdapter` into real production
dispatch remains future work gated on: (a) a real decision to add the
dependency, (b) building the actual "did a prior fingerprint exist"
plumbing between `SiteProfile` and `ScraplingAdapter.discover_series`'s
`storage_file`, neither of which this phase's benchmark scope required.
