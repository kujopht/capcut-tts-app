"""
T1 Structured Data — embedded-JSON-blob extraction, RSS/Atom feed parsing,
sitemap.xml parsing for the Universal Acquisition Engine.

All functions take already-fetched text (HTML or XML) as input and return
structured data. They do NOT do any network fetching — that is the job of
HttpFetcher, reused by callers.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

import defusedxml.ElementTree as ET  # noqa: N812 — same import shape as youtube_websub.py

# --- Safety constants ---

#: Max size (bytes) for a single embedded JSON script block before we skip it.
_EMBEDDED_JSON_MAX_SIZE = 5 * 1024 * 1024  # 5 MB

#: Max nesting depth for recursive content search (matches defensive spirit
#: of _JSON_LD_MAX_NESTING_DEPTH in html_extract.py but kept separate since
#: this is a search, not a parse — 12 levels covers realistic Next.js/
#: Nuxt pageProps trees without allowing adversarial depth bombs).
_CONTENT_SEARCH_MAX_DEPTH = 12

#: Min length for a content string to be considered real (not a placeholder
#: like "" or "n/a").
_CONTENT_MIN_LENGTH = 200

#: Hard cap on URLs returned from sitemap parsing — a real sitemap can be
#: huge; this prevents a caller from accidentally pulling 100K URLs without
#: pagination. Callers doing real bounded crawling must apply their OWN
#: much smaller per-run limit on top of this.
_SITEMAP_MAX_URLS = 50_000

# ---------------------------------------------------------------------------
# 1. Embedded JSON blob extraction
# ---------------------------------------------------------------------------

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)
_NUXT_RE = re.compile(
    r'<script>\s*window\.__NUXT__\s*=\s*(.*?)\s*;?\s*</script>',
    re.DOTALL,
)
_GENERIC_JSON_SCRIPT_RE = re.compile(
    r'<script\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)


def _is_valid_json(s: str) -> bool:
    """Return True if s looks like it starts with { or [ (heuristic pre-check)."""
    stripped = s.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def _extract_nested_json_depth(raw: str, limit: int) -> bool:
    """Check if JSON nesting depth exceeds *limit* (iterative, no recursion).

    Mirrors the defensive spirit of html_extract._do_sau_json_vuot_qua:
    checked BEFORE json.loads, not via try/except RecursionError after.
    """
    depth = 0
    in_string = False
    escaping = False
    for ch in raw:
        if in_string:
            if escaping:
                escaping = False
            elif ch == "\\":
                escaping = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
            if depth > limit:
                return True
        elif ch in "]}":
            depth -= 1
    return False


def extract_embedded_json_blobs(html: str) -> List[Dict[str, Any]]:
    """Find and parse every embedded JSON blob in *html*.

    Search order:
    1. ``<script id="__NEXT_DATA__" type="application/json">`` (Next.js)
    2. ``<script>window.__NUXT__=(...)</script>`` (Nuxt.js — JS expression,
       not always strict JSON; silently skipped on json.loads failure)
    3. Any other ``<script type="application/json">`` that is NOT
       ``application/ld+json`` (JSON-LD is handled elsewhere).

    Safety:
    - Blocks over ``_EMBEDDED_JSON_MAX_SIZE`` bytes are skipped.
    - Nesting depth > ``_JSON_LD_MAX_NESTING_DEPTH`` (64) is skipped before
      ``json.loads`` to avoid platform-dependent RecursionError behaviour.
    - Returns ``[]`` on anything malformed — never raises.
    """
    results: List[Dict[str, Any]] = []

    for m in _NEXT_DATA_RE.finditer(html):
        raw = m.group(1)
        if len(raw.encode("utf-8", errors="replace")) > _EMBEDDED_JSON_MAX_SIZE:
            continue
        if _extract_nested_json_depth(raw, 64):
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                results.append(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    for m in _NUXT_RE.finditer(html):
        raw = m.group(1)
        if len(raw.encode("utf-8", errors="replace")) > _EMBEDDED_JSON_MAX_SIZE:
            continue
        if _extract_nested_json_depth(raw, 64):
            continue
        if not _is_valid_json(raw):
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                results.append(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    for m in _GENERIC_JSON_SCRIPT_RE.finditer(html):
        raw = m.group(1)
        if len(raw.encode("utf-8", errors="replace")) > _EMBEDDED_JSON_MAX_SIZE:
            continue
        if _extract_nested_json_depth(raw, 64):
            continue
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                results.append(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    return results


# ---------------------------------------------------------------------------
# 2. Content search inside a JSON blob
# ---------------------------------------------------------------------------


def find_content_in_json_blob(
    blob: Dict[str, Any],
    *,
    hint_keys: Sequence[str] = ("content", "body", "text", "articleBody", "html"),
) -> Optional[str]:
    """Bounded recursive search for a long content string inside *blob*.

    Walks the dict/list tree up to ``_CONTENT_SEARCH_MAX_DEPTH`` levels deep,
    looking for a string value whose key (case-insensitive) matches one of
    ``hint_keys`` and whose length >= ``_CONTENT_MIN_LENGTH``.

    This is a **heuristic best-effort** helper, not a schema-aware parser.
    It will miss content stored under unexpected key names or split across
    multiple fields. That is by design — callers should treat ``None`` as
    "no content found via this heuristic", not as an error.
    """
    hint_keys_lower = {k.lower() for k in hint_keys}

    def _search(obj: Any, depth: int) -> Optional[str]:
        if depth > _CONTENT_SEARCH_MAX_DEPTH:
            return None
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, str) and key.lower() in hint_keys_lower:
                    if len(val) >= _CONTENT_MIN_LENGTH:
                        return val
                found = _search(val, depth + 1)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _search(item, depth + 1)
                if found is not None:
                    return found
        return None

    return _search(blob, 0)


# ---------------------------------------------------------------------------
# 3. RSS / Atom feed parsing
# ---------------------------------------------------------------------------


def _text_or_none(el: Optional[ET.Element]) -> Optional[str]:
    """Return element text or None."""
    if el is None:
        return None
    return el.text


def _localname(tag: str) -> str:
    """Strip an XML namespace: ``{ns}localname`` -> ``localname``."""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def _find_local(parent: ET.Element, localname: str) -> Optional[ET.Element]:
    """Find the first direct child whose local (namespace-free) name matches."""
    for child in parent:
        if _localname(child.tag) == localname:
            return child
    return None


def parse_feed(xml_text: str) -> List[Dict[str, str]]:
    """Parse an RSS 2.0 or Atom feed and return a list of item dicts.

    Each dict has keys: ``title``, ``link``, ``description_or_summary``,
    ``published``, ``guid_or_id`` — all strings, raw (no date parsing).
    Missing fields are empty strings.

    Returns ``[]`` on malformed XML, non-feed XML, or anything that doesn't
    match RSS/Atom structure — never raises.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    root_name = _localname(root.tag)

    # Detect Atom feed
    if root_name == "feed":
        results: List[Dict[str, str]] = []
        for entry in root:
            if _localname(entry.tag) != "entry":
                continue
            title_el = _find_local(entry, "title")
            link_el = _find_local(entry, "link")
            summary_el = _find_local(entry, "summary")
            content_el = _find_local(entry, "content")
            published_el = _find_local(entry, "published")
            if published_el is None:
                published_el = _find_local(entry, "updated")
            id_el = _find_local(entry, "id")

            link_href = ""
            if link_el is not None:
                link_href = link_el.get("href") or (link_el.text or "")

            results.append({
                "title": _text_or_none(title_el) or "",
                "link": link_href,
                "description_or_summary": (
                    _text_or_none(summary_el) or _text_or_none(content_el) or ""
                ),
                "published": _text_or_none(published_el) or "",
                "guid_or_id": _text_or_none(id_el) or "",
            })
        return results

    # Detect RSS
    channel = _find_local(root, "channel")
    if channel is not None:
        items = []
        for child in channel:
            if _localname(child.tag) == "item":
                items.append(child)
        results = []
        for item in items:
            title_el = _find_local(item, "title")
            link_el = _find_local(item, "link")
            desc_el = _find_local(item, "description")
            pub_el = _find_local(item, "pubDate")
            guid_el = _find_local(item, "guid")
            results.append({
                "title": _text_or_none(title_el) or "",
                "link": _text_or_none(link_el) or "",
                "description_or_summary": _text_or_none(desc_el) or "",
                "published": _text_or_none(pub_el) or "",
                "guid_or_id": _text_or_none(guid_el) or "",
            })
        return results

    return []


# ---------------------------------------------------------------------------
# 4. Sitemap parsing
# ---------------------------------------------------------------------------


def parse_sitemap(xml_text: str) -> List[str]:
    """Parse a sitemap.xml or sitemap index and return all ``<loc>`` URLs.

    Handles both ``<urlset>`` (standard sitemap) and ``<sitemapindex>``
    (sitemap index pointing to sub-sitemaps). Returns a flat list of every
    ``<loc>`` URL string found, capped at ``_SITEMAP_MAX_URLS``.

    **Crawl-scope policy note:** This function's only job is honest parsing.
    A caller doing real bounded crawling must apply its OWN much smaller
    per-run limit on top of this — 50K is a "don't return an absurd amount
    of data" safety bound, not a crawl policy.

    Returns ``[]`` on malformed XML or non-sitemap XML — never raises.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    urls: List[str] = []

    root_name = _localname(root.tag)

    # urlset
    if root_name == "urlset":
        for url_el in root.iter():
            if _localname(url_el.tag) != "url":
                continue
            loc_el = _find_local(url_el, "loc")
            if loc_el is not None and loc_el.text:
                urls.append(loc_el.text)
                if len(urls) >= _SITEMAP_MAX_URLS:
                    break
        return urls

    # sitemapindex
    if root_name == "sitemapindex":
        for sm_el in root.iter():
            if _localname(sm_el.tag) != "sitemap":
                continue
            loc_el = _find_local(sm_el, "loc")
            if loc_el is not None and loc_el.text:
                urls.append(loc_el.text)
                if len(urls) >= _SITEMAP_MAX_URLS:
                    break
        return urls

    return []
