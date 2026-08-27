# Story Harvester V3 — Phase 11 real multi-site canary matrix

Four structurally different, small, public sources (A–D below), each hit
with the real `HttpFetcher` (default `respect_robots=True`, honest
User-Agent, default rate limiting — no test-mode speedups) and bounded
`chapter_limit`/`max_chapters` — no mass crawl. Neither of the two
already-production-verified sources (`vi.wikisource.org`, `royalroad.com`)
was touched again; these are four *new* sources chosen specifically to be
structurally unlike those two and unlike each other.

robots.txt was hand-checked for all four before any request (recorded
below), on top of `HttpFetcher`'s own default enforcement. One additional
candidate, `standardebooks.org`, was ruled out during that check — its
robots.txt explicitly disallows `/ebooks/*/text*` (the exact ebook-text
path) and separately names `claude-web`/`claude-user` under a blanket
`Disallow: /honeypot` block — excluded outright, no request made.

## A — en.wikisource.org (MediaWiki, different language/work than production)

`https://en.wikisource.org/wiki/The_War_of_the_Worlds_(1898)`. robots.txt:
general crawlers allowed on `/wiki/` article pages (same shape as the
verified `vi.wikisource.org` config).

- Discovery: **MEDIUM** confidence, 33 chapter-shaped links found
  (`/wiki/The_War_of_the_Worlds/Book_\d+/Chapter_\d+`), correctly *not*
  HIGH because none of the discovered anchor texts contained a literal
  chapter keyword (`_word_fraction` = 0%) even though the actual work
  does use "Chapter N." headings — this particular TOC's link text
  formatting doesn't carry the word into every anchor. Container
  detection and JSON-LD both fired correctly.
- Full pipeline run (via `GenericIndexAdapter`, `chapter_limit=2`,
  manually-configured pattern): fetched Book 1/Chapter 1 successfully,
  13,100 characters of clean text, `boundary_matched` (Wikisource's
  existing CSS-boundary detection) fired correctly on this different-
  language edition — good generalization signal, since that boundary
  logic was tuned against `vi.wikisource.org` specifically.

## B — en.wikibooks.org (MediaWiki, different project conventions)

`https://en.wikibooks.org/wiki/Python_Programming`. robots.txt: general
crawlers allowed on `/wiki/` pages; `/w/` is disallowed.

- Discovery: **MEDIUM** confidence, but the discovered "chapter cluster"
  (`/w/index.php?title=Python_Programming&veaction=edit&section=\d+`) is
  actually the page's **"[edit section]" links**, not real chapter
  subpages — this particular Wikibooks page is a single long page with
  numbered sections, not a subpage-per-chapter book (contrary to this
  canary's initial assumption about how Wikibooks organizes content).
  When discovery tried to fetch a sample "chapter" from that bogus
  pattern, `HttpFetcher`'s default `respect_robots=True` correctly
  **refused** the request (`/w/` is disallowed) — the robots.txt safety
  layer caught a real discovery-engine limitation before it could do
  anything with the misleading pattern. No code changed here: this is a
  case where an existing safety layer already did its job; the
  discovery engine's own heuristic limitation (getting fooled by
  same-shaped non-chapter links) is noted for awareness, not fixed, since
  it never gets more than MEDIUM (safe: MEDIUM already requires operator
  review) and no consequence beyond a lower-quality proposal.

## C — www.gutenberg.org (real bug found and fixed)

`https://www.gutenberg.org/files/11/11-h/11-h.htm` ("Alice's Adventures
in Wonderland"). robots.txt: general crawlers only disallowed from
`/ebooks/search`; this path is unaffected.

- Discovery initially returned **HIGH** confidence — but on inspection
  this was a **real bug**: the page navigates its 12 chapters via
  in-page anchors (`#chap01`..`#chap12`) on one single server-side page,
  not 12 separate pages. `_find_link_clusters` grouped by path+query
  only (fragments ignored), so the 12 distinct anchor hrefs collapsed
  into one "shape" and cleared the minimum-cluster-size check, producing
  a confident `chapter_url_pattern` that would have re-fetched the exact
  same page 12 times instead of 12 real chapters.
- **Fixed** in `server/scraper/discovery.py::_pick_chapter_cluster`: a
  candidate cluster is now rejected if its members collapse to fewer
  than `_MIN_CLUSTER_SIZE` distinct URLs once fragments are stripped.
  Verified live against this exact URL post-fix: confidence correctly
  drops to LOW / `chapter_url_pattern=None` (no other valid cluster
  exists on this single-page book). Regression test + a control test
  (real multi-page clusters unaffected) added in
  `test_scraper_discovery.py::FragmentOnlyClusterTest`. Shipped as its
  own commit (`efcc2b2`) with full suite green (3141 passed).

## D — doc.rust-lang.org/book (mdBook static site, no index page)

`https://doc.rust-lang.org/book/`. robots.txt: only old book editions
and `/0.`/`/1.` paths disallowed; the current book is unaffected.

- Discovery on the book root: correctly **LOW** / no pattern — this
  mdBook version renders its full sidebar TOC via JavaScript, so the
  static HTML genuinely has no discoverable chapter list. Evidence
  correctly notes "may need JavaScript," and per Phase 10 policy does
  **not** suggest escalating to Tier 2 automatically.
- `NavigationOnlyAdapter` against the same book, started at
  `ch01-00-getting-started.html`: succeeded, `extraction_confidence=high`
  on the first chapter, `ordering_evidence` correctly labeled as
  navigation-sequence (no invented chapter numbers) — this is exactly
  the scenario `NavigationOnlyAdapter` exists for (confirmed on a real
  site, not just fixtures).
- **Canary-configuration lesson, not a code defect**: this run's
  `next_href_pattern` was a bare filename shape
  (`^ch\d+-\d+-[a-z0-9-]+\.html$`), which matches mdBook's "previous
  chapter" link just as well as its "next chapter" link — and since the
  previous chapter (the introduction) hadn't been visited yet, the
  adapter followed it, walking backward one step before the existing
  already-visited guard could help. This is the documented, expected
  behavior of `NavigationOnlyAdapter`'s `next_href_pattern` contract
  (bare regex on href shape — the operator is responsible for scoping it
  to the actual "next" element, e.g. via `rel="next"` or a distinguishing
  class, same as `SiteConfig.chapter_href_pattern` requires elsewhere in
  this codebase). No fix applied; noted here as real-world confirmation
  of why that contract matters when a site is added for real.

## Summary

| Source | Structure | Confidence | Real finding |
|---|---|---|---|
| A: en.wikisource.org | MediaWiki, different language/naming | MEDIUM (correctly, honest) | none — generalizes correctly |
| B: en.wikibooks.org | MediaWiki, single-page-with-sections | MEDIUM | discovery heuristic limitation; robots.txt safety net caught it |
| C: www.gutenberg.org | Static HTML, anchor-nav single page | was HIGH (wrong) → now LOW (correct) | **real bug, fixed** (fragment-collapse false positive) |
| D: doc.rust-lang.org | mdBook, JS-rendered TOC + static next-links | LOW (index) / works (nav-only) | confirms NavigationOnlyAdapter's reason for existing; canary misconfiguration lesson, not a defect |

One genuine production-code bug found and fixed via real-world testing
(C). No destructive actions taken; no site was crawled beyond a handful
of bounded requests; no content was written to any data store.
