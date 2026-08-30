"""
End-to-end V5 Web Fiction pipeline scenario — proving acquire -> classify ->
adapter -> normalize -> identity -> change detection -> completion.
"""
from __future__ import annotations

from typing import Any, Dict

from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter
from server.scraper.dedupe import content_hash
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.universal.acquisition import SourceClass
from server.scraper.universal.adapter import StoryProviderAdapter
from server.scraper.universal.change_detection import (
    classify_index, classify_unit_content, UnitChangeKind,
)
from server.scraper.universal.identity import CanonicalIdentity
from server.scraper.universal.router import AcquisitionRouter


INDEX_URL = "https://example.com/truyen/test-story"

ROUND1_PAGES = {
    INDEX_URL: """
    <!DOCTYPE html>
    <html>
    <head><title>Test Story</title></head>
    <body>
        <h1>Test Story</h1>
        <div class="chapters">
            <a href="https://example.com/truyen/test-story/chuong-1">Chương 1: Khởi đầu</a>
            <a href="https://example.com/truyen/test-story/chuong-2">Chương 2: Diễn biến</a>
        </div>
    </body>
    </html>
    """,
    "https://example.com/truyen/test-story/chuong-1": """
    <!DOCTYPE html>
    <html>
    <head><title>Chương 1: Khởi đầu - Test Story</title></head>
    <body>
        <article class="chapter-content">
            <p>Nội dung chương 1 ban đầu rất chi tiết và hấp dẫn.</p>
        </article>
    </body>
    </html>
    """,
    "https://example.com/truyen/test-story/chuong-2": """
    <!DOCTYPE html>
    <html>
    <head><title>Chương 2: Diễn biến - Test Story</title></head>
    <body>
        <article class="chapter-content">
            <p>Nội dung chương 2 ban đầu với những thử thách mới.</p>
        </article>
    </body>
    </html>
    """,
}

ROUND2_PAGES = {
    INDEX_URL: """
    <!DOCTYPE html>
    <html>
    <head><title>Test Story</title></head>
    <body>
        <h1>Test Story</h1>
        <div class="chapters">
            <a href="https://example.com/truyen/test-story/chuong-1">Chương 1: Khởi đầu</a>
            <a href="https://example.com/truyen/test-story/chuong-2">Chương 2: Diễn biến</a>
            <a href="https://example.com/truyen/test-story/chuong-3">Chương 3: Cao trào mới</a>
        </div>
    </body>
    </html>
    """,
    "https://example.com/truyen/test-story/chuong-1": """
    <!DOCTYPE html>
    <html>
    <head><title>Chương 1: Khởi đầu - Test Story</title></head>
    <body>
        <article class="chapter-content">
            <p>Nội dung chương 1 ban đầu rất chi tiết và hấp dẫn.</p>
        </article>
    </body>
    </html>
    """,
    "https://example.com/truyen/test-story/chuong-2": """
    <!DOCTYPE html>
    <html>
    <head><title>Chương 2: Diễn biến - Test Story</title></head>
    <body>
        <article class="chapter-content">
            <p>Nội dung chương 2 đã được tác giả biên tập chỉnh sửa lại hoàn toàn.</p>
        </article>
    </body>
    </html>
    """,
    "https://example.com/truyen/test-story/chuong-3": """
    <!DOCTYPE html>
    <html>
    <head><title>Chương 3: Cao trào mới - Test Story</title></head>
    <body>
        <article class="chapter-content">
            <p>Nội dung chương 3 hoàn toàn mới vừa xuất bản.</p>
        </article>
    </body>
    </html>
    """,
}


def run_scenario() -> dict:
    """Two-round fixture scenario using the REAL existing pieces (no
    mocks of business logic):
    - Round 1: a fixture story with 2 chapters (chuong-1, chuong-2), built
      via server.scraper.http_fetcher.FixtureFetcher, wrapped in
      server.scraper.adapters.generic_index_adapter.GenericIndexAdapter,
      bridged through server.scraper.universal.adapter.StoryProviderAdapter.
      Acquire the index page through
      server.scraper.universal.router.AcquisitionRouter (Tier 1), then
      call bridge.extract_metadata()/list_units() to get chapter URLs.
      Build a server.scraper.universal.identity.CanonicalIdentity for each
      chapter (source_platform="generic_web",
      source_type=SourceClass.WEB_FICTION, canonical_url=<chapter url>).
      Fetch+normalize each chapter via bridge.fetch_unit()/normalize(),
      compute content_hash via server.scraper.dedupe.content_hash on
      chapter.clean_text. Classify against an EMPTY previous-keys list
      using server.scraper.universal.change_detection.classify_index -
      both chapters should be NEW_UNIT.
    - Round 2: build a SECOND FixtureFetcher/adapter/bridge with 3
      chapters (chuong-1 UNCHANGED text, chuong-2 with DIFFERENT text than
      round 1, chuong-3 newly added). Classify against round 1's identity
      keys using classify_index (chuong-3 should be NEW_UNIT, chuong-1/
      chuong-2 NEEDS_BASELINE from the index-only pass), then for
      chuong-1/chuong-2 call classify_unit_content with round 1's stored
      content_hash vs round 2's freshly computed content_hash - chuong-1
      should resolve to UNCHANGED, chuong-2 to UPDATED_UNIT.
    Return a dict: {"round1": {...counts/kinds...}, "round2": {...}} with
    enough detail for a test to assert on kind-per-chapter, not just
    counts.
    """
    # -------------------------------------------------------------
    # ROUND 1
    # -------------------------------------------------------------
    fetcher_r1 = FixtureFetcher(ROUND1_PAGES)
    raw_adapter_r1 = GenericIndexAdapter(
        fetcher_r1,
        chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Test Story",
    )
    bridge_r1 = StoryProviderAdapter(raw_adapter_r1)

    router_r1 = AcquisitionRouter(http_fetcher=fetcher_r1)
    acq_index_r1 = router_r1.acquire(INDEX_URL, source_hint=SourceClass.WEB_FICTION)
    assert acq_index_r1.ok

    meta_r1 = bridge_r1.extract_metadata(INDEX_URL)
    unit_urls_r1 = bridge_r1.list_units(INDEX_URL)

    identities_r1: Dict[str, CanonicalIdentity] = {}
    content_hashes_r1: Dict[str, str] = {}
    normalized_r1: Dict[str, Any] = {}

    for url in unit_urls_r1:
        ident = CanonicalIdentity(
            source_platform="generic_web",
            source_type=SourceClass.WEB_FICTION,
            canonical_url=url,
        )
        key = ident.identity_key()
        identities_r1[url] = ident

        unit_acq = bridge_r1.fetch_unit(url)
        norm = bridge_r1.normalize(url, unit_acq)
        normalized_r1[url] = norm
        chash = content_hash(norm.clean_text)
        content_hashes_r1[key] = chash

    r1_identity_keys = [identities_r1[u].identity_key() for u in unit_urls_r1]
    r1_index_plan = classify_index(previous_keys=[], current_keys=r1_identity_keys)

    r1_chapter_kinds = {c.unit_identity_key: c.kind.value for c in r1_index_plan.changes}
    r1_by_url = {u: r1_chapter_kinds[identities_r1[u].identity_key()] for u in unit_urls_r1}

    round1_result = {
        "metadata": meta_r1,
        "unit_urls": unit_urls_r1,
        "identity_keys": r1_identity_keys,
        "counts": r1_index_plan.counts(),
        "kinds_by_key": r1_chapter_kinds,
        "kinds_by_url": r1_by_url,
    }

    # -------------------------------------------------------------
    # ROUND 2
    # -------------------------------------------------------------
    fetcher_r2 = FixtureFetcher(ROUND2_PAGES)
    raw_adapter_r2 = GenericIndexAdapter(
        fetcher_r2,
        chapter_href_pattern=r"/chuong-\d+",
        title_suffix_to_strip=" - Test Story",
    )
    bridge_r2 = StoryProviderAdapter(raw_adapter_r2)

    router_r2 = AcquisitionRouter(http_fetcher=fetcher_r2)
    acq_index_r2 = router_r2.acquire(INDEX_URL, source_hint=SourceClass.WEB_FICTION)
    assert acq_index_r2.ok

    meta_r2 = bridge_r2.extract_metadata(INDEX_URL)
    unit_urls_r2 = bridge_r2.list_units(INDEX_URL)

    identities_r2: Dict[str, CanonicalIdentity] = {}
    content_hashes_r2: Dict[str, str] = {}
    normalized_r2: Dict[str, Any] = {}

    for url in unit_urls_r2:
        ident = CanonicalIdentity(
            source_platform="generic_web",
            source_type=SourceClass.WEB_FICTION,
            canonical_url=url,
        )
        identities_r2[url] = ident

        unit_acq = bridge_r2.fetch_unit(url)
        norm = bridge_r2.normalize(url, unit_acq)
        normalized_r2[url] = norm
        chash = content_hash(norm.clean_text)
        content_hashes_r2[ident.identity_key()] = chash

    r2_identity_keys = [identities_r2[u].identity_key() for u in unit_urls_r2]
    r2_index_plan = classify_index(previous_keys=r1_identity_keys, current_keys=r2_identity_keys)

    r2_final_changes: Dict[str, UnitChangeKind] = {}
    for change in r2_index_plan.changes:
        key = change.unit_identity_key
        if change.kind == UnitChangeKind.NEEDS_BASELINE:
            # Reclassify with content hash comparison
            prev_hash = content_hashes_r1.get(key)
            new_hash = content_hashes_r2.get(key)
            unit_change = classify_unit_content(
                key,
                previous_content_hash=prev_hash,
                new_content_hash=new_hash,
            )
            r2_final_changes[key] = unit_change.kind
        else:
            r2_final_changes[key] = change.kind

    r2_by_url = {u: r2_final_changes[identities_r2[u].identity_key()].value for u in unit_urls_r2}

    round2_counts = {k.value: 0 for k in UnitChangeKind}
    for k in r2_final_changes.values():
        round2_counts[k.value] += 1

    round2_result = {
        "metadata": meta_r2,
        "unit_urls": unit_urls_r2,
        "identity_keys": r2_identity_keys,
        "index_counts": r2_index_plan.counts(),
        "counts": round2_counts,
        "kinds_by_key": {k: v.value for k, v in r2_final_changes.items()},
        "kinds_by_url": r2_by_url,
    }

    return {
        "round1": round1_result,
        "round2": round2_result,
    }
