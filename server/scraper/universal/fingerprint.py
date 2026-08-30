"""
Unknown-source reconnaissance, deterministic half — Story Harvester V5
Phase 8.

Builds a `SourceFingerprint` from HTML the caller ALREADY acquired (via
`AcquisitionRouter`) - DOM structure, JSON-LD types, embedded-JSON top-level
keys, a bounded sample of internal links, and network endpoint candidates
(reusing `network_intelligence.discover_embedded_json_endpoints`, not
duplicating it). Pure, no network, no LLM call - the LLM-proposal half
lives in `schema_proposal.py`, kept separate on purpose: this module's
output is what gets shown to an LLM, and everything in it is already
bounded/summarized metadata, never verbatim scraped prose, precisely
because scraped content is untrusted data that must never be handed to an
LLM (or a human operator's log) unbounded.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List
from urllib.parse import urljoin

from server.scraper.contract import domain_of
from server.scraper.universal.acquisition import NetworkEndpointCandidate
from server.scraper.universal.network_intelligence import (
    discover_embedded_json_endpoints,
)

#: Bound on any single string field copied from scraped content into a
#: fingerprint - a fingerprint is METADATA, not a content mirror.
_MAX_FIELD_LEN = 200
#: Bound on how many sample links a fingerprint keeps - enough to see the
#: site's link shape, not a full site crawl.
_MAX_LINK_SAMPLE = 20

_JSON_LD_SCRIPT = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)
_EMBEDDED_JSON_SCRIPT = re.compile(
    r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL)


def _clip(text: str) -> str:
    """Same discipline as `change_detection._an_toan`: strip control
    characters, bound length - a fingerprint field is metadata about
    scraped content, not a place to mirror it verbatim."""
    printable = "".join(c for c in str(text) if c.isprintable())
    return printable[:_MAX_FIELD_LEN]


class _TagHistogramParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tag_counts: Dict[str, int] = {}
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)
                    break


def _dom_tag_histogram_and_links(html: str) -> tuple:
    parser = _TagHistogramParser()
    try:
        parser.feed(html)
    except Exception:                                      # noqa: BLE001
        # Malformed HTML must never crash reconnaissance - a partial/best-
        # effort histogram from whatever HTMLParser managed to consume
        # before choking is still useful signal.
        pass
    return parser.tag_counts, parser.links


def _json_ld_types(html: str) -> List[str]:
    types: List[str] = []
    for block in _JSON_LD_SCRIPT.findall(html):
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for item in candidates:
            if isinstance(item, dict) and isinstance(item.get("@type"), str):
                types.append(_clip(item["@type"]))
    return types


def _embedded_json_top_level_keys(html: str) -> List[str]:
    keys: List[str] = []
    for block in _EMBEDDED_JSON_SCRIPT.findall(html):
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            keys.extend(_clip(k) for k in parsed.keys())
    return keys


@dataclass(frozen=True)
class SourceFingerprint:
    canonical_url: str
    dom_tag_histogram: Dict[str, int] = field(default_factory=dict)
    json_ld_types: List[str] = field(default_factory=list)
    embedded_json_top_level_keys: List[str] = field(default_factory=list)
    #: Bounded sample of internal links found on the page - SAME ORIGIN
    #: only, to keep this a fingerprint of the source itself, not a crawl
    #: frontier into arbitrary other domains.
    link_graph_sample: List[str] = field(default_factory=list)
    network_endpoint_candidates: List[NetworkEndpointCandidate] = field(default_factory=list)

    def content_signature(self) -> str:
        """A stable hash of the STRUCTURAL shape (tag histogram keys,
        JSON-LD types, embedded JSON keys) - two pages with the same
        template but different prose content hash to the SAME signature,
        which is exactly the point: this identifies "this looks like the
        same kind of page", not "this is the same page"."""
        shape = {
            "tags": sorted(self.dom_tag_histogram.keys()),
            "json_ld_types": sorted(set(self.json_ld_types)),
            "embedded_json_keys": sorted(set(self.embedded_json_top_level_keys)),
        }
        raw = json.dumps(shape, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_fingerprint(html: str, url: str) -> SourceFingerprint:
    """Pure, no network, no LLM - just structural analysis of HTML the
    caller already acquired through the normal acquisition path."""
    histogram, raw_links = _dom_tag_histogram_and_links(html)
    own_domain = domain_of(url)
    internal_links = []
    for href in raw_links:
        resolved = urljoin(url, href)
        if domain_of(resolved) == own_domain:
            internal_links.append(_clip(resolved))
        if len(internal_links) >= _MAX_LINK_SAMPLE:
            break

    return SourceFingerprint(
        canonical_url=url,
        dom_tag_histogram=histogram,
        json_ld_types=_json_ld_types(html),
        embedded_json_top_level_keys=_embedded_json_top_level_keys(html),
        link_graph_sample=internal_links,
        network_endpoint_candidates=discover_embedded_json_endpoints(html, url),
    )
