"""
Network intelligence — Story Harvester V5 Phase 3.

Discovers candidate JSON/API endpoints from ALREADY-ACQUIRED page content
and validates them before anything downstream is allowed to trust them.

Honest scope boundary: real live XHR/fetch/GraphQL interception requires a
headless browser (Playwright or similar) intercepting network traffic while
a page renders. This repo has NO browser-automation dependency installed
(confirmed: only `scrapling`'s HTML-only adaptive relocation exists, not
`DynamicFetcher`/`StealthyFetcher` - see `adapters/scrapling_adapter.py`).
This module therefore implements the DETERMINISTIC discovery path (scanning
already-fetched HTML for embedded JSON blobs that reference API-shaped
URLs - no browser needed) plus the FULL validation gate, which is the part
that matters most for safety. Live browser-based network capture is a
Tier-2 `AcquisitionPlugin` hook (see `router.py`) - not faked here.

Never automatically trust a discovered endpoint. `validate_endpoint_candidate`
is the only gate allowed to mark one trusted, and even then it is the
CALLER's decision whether to act on that - this module never calls back
into the acquisition pipeline itself.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Sequence
from urllib.parse import urljoin

from server.scraper.contract import domain_of
from server.scraper.http_fetcher import FetchError
from server.scraper.universal.acquisition import NetworkEndpointCandidate

#: Bounded response size for a CANDIDATE endpoint validation fetch - much
#: smaller than `http_fetcher.MAX_RESPONSE_BYTES` (20MB, sized for a full
#: chapter) because a legitimate JSON/API endpoint answering one page's
#: worth of structured data has no business being large; a large response
#: here is itself a signal something is wrong (misidentified endpoint,
#: or a deliberately oversized decoy).
MAX_CANDIDATE_RESPONSE_BYTES = 2 * 1024 * 1024

_JSON_LIKE_CONTENT_TYPES = ("application/json", "application/ld+json",
                            "application/graphql+json", "text/json")

#: Loose heuristic for "this string looks like an API endpoint", scanning
#: embedded JSON blobs (e.g. `__NEXT_DATA__`, other inline `<script
#: type="application/json">` payloads) already present in fetched HTML -
#: no network request is made during discovery itself.
_API_SHAPED_URL = re.compile(
    r"https?://[^\s\"'<>]+?(?:/api/|/graphql|\.json(?:\?|$)|/v\d+/)[^\s\"'<>]*",
    re.IGNORECASE)

_SCRIPT_JSON_BLOCK = re.compile(
    r'<script[^>]+type=["\']application/(?:json|ld\+json)["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)


def discover_embedded_json_endpoints(
        html: str, page_url: str) -> List[NetworkEndpointCandidate]:
    """Browser-free discovery: scan `<script type="application/json">`/
    `<script type="application/ld+json">` blocks in already-fetched HTML
    for URL strings that look API-shaped. Pure string/regex scan, no
    network call - candidates only, not validated."""
    seen = set()
    candidates: List[NetworkEndpointCandidate] = []
    for block in _SCRIPT_JSON_BLOCK.findall(html):
        for match in _API_SHAPED_URL.findall(block):
            resolved = urljoin(page_url, match)
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(NetworkEndpointCandidate(
                url=resolved, discovered_via="embedded_json_script"))
    return candidates


@dataclass(frozen=True)
class EndpointValidationResult:
    candidate: NetworkEndpointCandidate
    trusted: bool
    reasons: List[str] = field(default_factory=list)


def _content_type_is_json_or_text(content_type: str) -> bool:
    base = content_type.split(";", 1)[0].strip().lower()
    return base in _JSON_LIKE_CONTENT_TYPES or base.startswith("text/")


def _json_shape_key(text: str):
    """Structural fingerprint of a JSON response, IGNORING values - two
    fetches of a legitimately dynamic endpoint (a view counter, a
    timestamp) should still count as "stable" if the same KEYS/TYPES
    come back both times; only a genuinely different SHAPE is treated as
    an unstable identifier."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return _shape_of(parsed)


def _shape_of(value):
    if isinstance(value, dict):
        return {k: _shape_of(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_shape_of(v) for v in value[:1]]
    return type(value).__name__


def validate_endpoint_candidate(
        candidate: NetworkEndpointCandidate, *, page_url: str, fetcher,
        check_reproducibility: bool = True) -> EndpointValidationResult:
    """The ONE gate allowed to mark a discovered candidate trusted. Checks,
    in order: same-origin (never trust a cross-origin candidate scraped out
    of page content - it could point anywhere), reachable via the SAME
    `fetcher` used for real acquisition (so SSRF/robots/redirect-safety
    protections in `HttpFetcher` apply here too, not a separate unguarded
    request path), JSON/text content type, bounded response size, and
    (optional) reproducibility - fetched twice, same structural shape."""
    reasons: List[str] = []

    if domain_of(candidate.url) != domain_of(page_url):
        reasons.append(
            f"khac origin voi trang goc: {domain_of(candidate.url)} != {domain_of(page_url)}")
        return EndpointValidationResult(candidate, False, reasons)

    try:
        first = fetcher.fetch(candidate.url)
    except FetchError as exc:
        return EndpointValidationResult(candidate, False, [f"khong tai duoc: {exc}"])

    if not _content_type_is_json_or_text(first.content_type):
        reasons.append(f"content-type khong phai JSON/text: {first.content_type!r}")

    if len(first.text.encode("utf-8")) > MAX_CANDIDATE_RESPONSE_BYTES:
        reasons.append("vuot gioi han kich thuoc phan hoi cho phep voi mot endpoint ung vien")

    if check_reproducibility and not reasons:
        try:
            second = fetcher.fetch(candidate.url)
        except FetchError as exc:
            reasons.append(f"khong tai lai duoc lan hai: {exc}")
        else:
            shape1, shape2 = _json_shape_key(first.text), _json_shape_key(second.text)
            if shape1 is None or shape2 is None:
                reasons.append("khong phan tich duoc JSON de kiem tra on dinh cau truc")
            elif shape1 != shape2:
                reasons.append("cau truc JSON khong on dinh giua hai lan goi")

    return EndpointValidationResult(candidate, trusted=not reasons, reasons=reasons)


def validate_candidates(
        candidates: Sequence[NetworkEndpointCandidate], *, page_url: str,
        fetcher, check_reproducibility: bool = True) -> List[EndpointValidationResult]:
    return [validate_endpoint_candidate(c, page_url=page_url, fetcher=fetcher,
                                        check_reproducibility=check_reproducibility)
           for c in candidates]
