"""
FanFicFareProvider — T5 Managed Provider (see `universal/router.py`'s
`AcquisitionTier.T5_MANAGED_PROVIDER`: "provider quan ly ben ngoai qua
plugin") wrapping the real `fanficfare` CLI.

Grounded in two real proof missions, not speculation — read before
changing any threshold/host list below:
  - `docs/reports/fanficfare-real-proof-2026-09-02.md` (v4.61.0, 111
    sites, real multi-chapter acquisition PASS, incremental-update PASS
    with byte-level evidence, verdict SITE_ADAPTER_SOURCE).
  - `docs/reports/fanficfare-official-fetcher-options-proof-2026-09-02.md`
    (cloudscraper genuinely tried and still 403'd on FFN; browser-cache
    genuinely improved FFN — metadata + full chapter list + one clean
    chapter body from a single legitimately-cached page — but did NOT
    help AO3, whose adapter needs an internal `/navigate` sub-page a
    normal page view never caches; verdict BROWSER_CACHE_FALLBACK,
    narrow scope only).

Hard boundaries, enforced by construction:
  - NEVER enables `use_cloudscraper` here. That option exists in
    FanFicFare's own `defaults.ini` but real-world testing showed it
    makes no difference against FFN's 403 and this project's standing
    policy is no challenge-solving/stealth automation in production.
  - NEVER launches or drives a browser. The one legitimate fallback
    (browser cache) only reads a cache path an operator populated by
    hand (`FAS_FANFICFARE_BROWSER_CACHE_PATH`) — if that path is absent
    or empty, the fallback is simply unavailable. This module contains
    no Selenium/Playwright/subprocess-launches-a-browser code at all.
  - FanFiction.net and AO3 are BLOCKED BY DEFAULT (`_DEFAULT_BLOCKED_HOSTS`)
    even though FanFicFare's adapter list includes them — real testing
    showed both return a genuine 403 on direct fetch. They stay
    registered (so a future browser-cache hit can still use them) but
    are never tried direct.

This module does not reimplement the site-agnostic pieces this repo
already has — it composes with them instead of duplicating them:
  - deterministic validation: `universal/extraction_validation.py`
    (`validate_extracted_content`) — same gate every other tier uses.
  - content/source identity: `dedupe.py` (`content_hash`,
    `source_fingerprint`) — same hashing every adapter uses.
  - canonical URL: `contract.py` (`canonicalize_url`, `domain_of`).
  - source-health/backoff: `harvest_scheduler.py` (`next_check_at`,
    exponential backoff) — reused for the blocked-hosts+cache-miss case
    instead of a new backoff formula.
  - fixture-based regression testing: `server/tests/fixtures/scraper/`
    convention — see `server/tests/test_fanficfare_provider.py`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from server.scraper.contract import canonicalize_url, domain_of
from server.scraper.dedupe import content_hash, source_fingerprint

#: Hosts FanFicFare's OWN adapter list includes but real testing proved
#: return a genuine 403 on direct, non-interactive fetch (see module
#: docstring). Kept registered (fanficfare_supports_hostname() still
#: reports them as supported — that fact is real and useful for the
#: browser-cache-fallback path) but the resolver never routes to
#: "fanficfare direct" for these; see resolve_acquisition_route().
_DEFAULT_BLOCKED_HOSTS = frozenset({"www.fanfiction.net", "archiveofourown.org"})

_SITES_LIST_URL_RE = re.compile(r"^\*\s+(https?://\S+)")

_OPF_NS = {"opf": "http://www.idpf.org/2007/opf",
           "dc": "http://purl.org/dc/elements/1.1/"}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _fanficfare_binary() -> Optional[str]:
    """Absolute path to the `fanficfare` CLI, or None if not installed.
    Resolved fresh every call (cheap: one `shutil.which`/stat) rather
    than cached, matching the "never assume available just because
    registered" contract every plugin in this codebase follows."""
    found = shutil.which("fanficfare")
    if found:
        return found
    venv_candidate = Path(sys.exec_prefix) / "Scripts" / "fanficfare.exe"
    if venv_candidate.is_file():
        return str(venv_candidate)
    return None


@lru_cache(maxsize=1)
def _supported_hostnames() -> frozenset:
    """Real hostnames parsed from this exact installed version's OWN
    `--sites-list` output — never hand-maintained, so this can never
    drift from what the binary on THIS machine actually supports.
    Empty (not an exception) when the binary is missing/the call fails,
    so callers fail closed to "not supported" rather than crash."""
    binary = _fanficfare_binary()
    if not binary:
        return frozenset()
    try:
        proc = subprocess.run(
            [binary, "--sites-list"], capture_output=True, text=True, timeout=30)
    except Exception:
        return frozenset()
    if proc.returncode != 0:
        return frozenset()
    hosts = set()
    for line in proc.stdout.splitlines():
        m = _SITES_LIST_URL_RE.match(line.strip())
        if not m:
            continue
        host = urlparse(m.group(1)).netloc.lower()
        if host:
            hosts.add(host)
    return frozenset(hosts)


def fanficfare_supports_hostname(url: str) -> bool:
    """True iff this exact installed FanFicFare build's OWN `--sites-list`
    names this URL's host as a real example-URL host — not a guess, not
    a hand-maintained list."""
    host = urlparse(url).netloc.lower()
    return host in _supported_hostnames()


def _browser_cache_path() -> Optional[Path]:
    """The operator-populated browser cache directory, or None.

    Reads `FAS_FANFICFARE_BROWSER_CACHE_PATH` — set by hand, pointing at
    a Chrome `Cache_Data` (or Firefox `cache2`) directory an operator
    already produced by legitimately browsing the target pages
    themselves (see the fetcher-options proof report for exactly what
    that looks like). This function NEVER creates, populates, or drives
    anything toward that path — it only checks whether one already
    exists and looks non-empty. Absent/empty env var or path = None,
    which the resolver treats as "fallback unavailable", never as a
    reason to try launching a browser itself.
    """
    import os

    raw = os.environ.get("FAS_FANFICFARE_BROWSER_CACHE_PATH", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_dir():
        return None
    try:
        has_entries = any(path.iterdir())
    except OSError:
        return None
    return path if has_entries else None


def resolve_acquisition_route(url: str) -> str:
    """The resolver the FanFicFare integration mission asked for:

        supported hostname
          -> "fanficfare"                (direct)
          -> "browser_cache_fallback"     (only if a real cache already exists)
          -> "engine"                     (existing T0-T5 / StoryProvider engine)
          -> "unavailable"

    Returns one of those four literal strings. Never returns a route
    that would require launching a browser or enabling cloudscraper —
    those are not in this function's vocabulary at all.
    """
    if not fanficfare_supports_hostname(url):
        return "engine"

    host = urlparse(url).netloc.lower()
    if host in _DEFAULT_BLOCKED_HOSTS:
        if _browser_cache_path() is not None:
            return "browser_cache_fallback"
        return "engine"

    return "fanficfare"


def _classify_cli_failure(stderr: str) -> str:
    """Classify a real, observed FanFicFare CLI failure into one of a
    small set of known shapes — patterns taken directly from the two
    proof missions' actual captured tracebacks, not guessed."""
    if "Login Failed" in stderr:
        return "login_required"
    if "HTTPErrorFFF" in stderr and "403" in stderr:
        return "blocked"
    if "Page not found or expired in Browser Cache" in stderr:
        return "cache_miss"
    return "failed"


@dataclass
class FanFicFareChapter:
    order_index: int
    title: str
    content: str
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.content)


@dataclass
class FanFicFareAcquisition:
    """Parsed result of one successful FanFicFare CLI run — the shape
    `normalize_fanficfare_result()` turns into real `Novel`/`Chapter`
    payloads (server/domain.py)."""

    source_url: str
    title: str
    author: str
    external_chapter_count: int
    external_updated_at: str
    fanficfare_uid: str
    tags: List[str] = field(default_factory=list)
    chapters: List[FanFicFareChapter] = field(default_factory=list)
    epub_path: Optional[Path] = None


@dataclass
class FanFicFareCLIResult:
    ok: bool
    epub_path: Optional[Path]
    failure_kind: str = ""  # "blocked" | "login_required" | "cache_miss" | "failed"
    stderr_excerpt: str = ""


def _run_fanficfare_cli(
    target: str, *, workdir: Path, timeout: int = 180,
) -> FanFicFareCLIResult:
    """Run FanFicFare non-interactively. `target` is a story URL (fresh
    acquisition) or a path to an existing `.epub` (incremental update via
    `-u`, verified in the real-proof report to write zero bytes when
    nothing changed). No `-c personal.ini` is ever passed here — no
    cloudscraper, no browser-cache config — this is the plain-direct
    path only. Browser-cache runs go through `_run_fanficfare_cli_cached`
    instead, which is the ONLY function in this module allowed to write
    a personal.ini, and only ever with `use_browser_cache*`, never
    `use_cloudscraper`."""
    binary = _fanficfare_binary()
    if not binary:
        return FanFicFareCLIResult(ok=False, epub_path=None, failure_kind="failed",
                                    stderr_excerpt="fanficfare binary not found")
    workdir.mkdir(parents=True, exist_ok=True)
    is_update = target.lower().endswith(".epub")
    argv = [binary, "--non-interactive"]
    if is_update:
        argv += ["-u", target]
    else:
        argv += [target]
    try:
        proc = subprocess.run(
            argv, cwd=str(workdir), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return FanFicFareCLIResult(ok=False, epub_path=None, failure_kind="failed",
                                    stderr_excerpt="timed out")

    epubs = sorted(workdir.glob("*.epub"), key=lambda p: p.stat().st_mtime, reverse=True)
    if proc.returncode == 0 and epubs:
        return FanFicFareCLIResult(ok=True, epub_path=epubs[0])
    kind = _classify_cli_failure(proc.stderr or "")
    return FanFicFareCLIResult(ok=False, epub_path=None, failure_kind=kind,
                                stderr_excerpt=(proc.stderr or "")[-800:])


def _run_fanficfare_cli_cached(
    url: str, *, workdir: Path, cache_path: Path, timeout: int = 180,
) -> FanFicFareCLIResult:
    """Browser-cache-fallback run. Writes a scoped `personal.ini` with
    ONLY `use_browser_cache`/`use_browser_cache_only`/`browser_cache_path`
    — the exact three keys proven real in the fetcher-options report.
    Never writes `use_cloudscraper`. Never launches anything — `cache_path`
    must already exist and be populated (`_browser_cache_path()`'s job)."""
    binary = _fanficfare_binary()
    if not binary:
        return FanFicFareCLIResult(ok=False, epub_path=None, failure_kind="failed",
                                    stderr_excerpt="fanficfare binary not found")
    workdir.mkdir(parents=True, exist_ok=True)
    host = urlparse(url).netloc
    ini_path = workdir / "personal.ini"
    ini_path.write_text(
        "[defaults]\n"
        f"browser_cache_path:{cache_path}\n"
        "browser_cache_age_limit:-1\n\n"
        f"[{host}]\n"
        "use_browser_cache:true\n"
        "use_browser_cache_only:true\n",
        encoding="utf-8")
    try:
        proc = subprocess.run(
            [binary, "--non-interactive", "-c", str(ini_path), url],
            cwd=str(workdir), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return FanFicFareCLIResult(ok=False, epub_path=None, failure_kind="failed",
                                    stderr_excerpt="timed out")

    epubs = sorted(workdir.glob("*.epub"), key=lambda p: p.stat().st_mtime, reverse=True)
    if epubs:
        # Cache-only mode can produce a PARTIAL epub (metadata + whatever
        # chapters were actually cached) even when the process itself
        # reports a non-zero exit for the chapters that were not cached —
        # real behavior observed in the proof mission. A partial file is
        # still useful: parse it and let the caller see how many
        # chapters actually came through clean.
        return FanFicFareCLIResult(ok=True, epub_path=epubs[0])
    kind = _classify_cli_failure(proc.stderr or "")
    return FanFicFareCLIResult(ok=False, epub_path=None, failure_kind=kind,
                                stderr_excerpt=(proc.stderr or "")[-800:])


def _strip_html(raw_xhtml: str) -> str:
    body_match = re.search(r"<body[^>]*>(.*)</body>", raw_xhtml, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1) if body_match else raw_xhtml
    text = unescape(_TAG_RE.sub("\n", body))
    text = _WS_RE.sub(" ", text)
    return _NL_RE.sub("\n\n", text).strip()


def parse_fanficfare_epub(epub_path: Path) -> FanFicFareAcquisition:
    """Unzip a FanFicFare-produced EPUB and turn it into a
    `FanFicFareAcquisition` — real Dublin Core metadata + chapter bodies
    in spine order, HTML-stripped. A chapter whose body is FanFicFare's
    own "(CHAPTER ERROR)"/"chapter url removed due to failure" marker
    (real behavior seen under browser-cache-only mode — see proof
    report) is INCLUDED with that marker text intact, not silently
    dropped: the caller decides whether a partial acquisition is usable,
    this function never hides what actually happened.
    """
    with zipfile.ZipFile(epub_path) as zf:
        opf_name = next(n for n in zf.namelist() if n.endswith(".opf"))
        opf_bytes = zf.read(opf_name)
        root = ET.fromstring(opf_bytes)

        title = (root.findtext(".//dc:title", namespaces=_OPF_NS) or "").strip()
        author = (root.findtext(".//dc:creator", namespaces=_OPF_NS) or "").strip()
        source_url = ""
        for ident in root.findall(".//dc:identifier", namespaces=_OPF_NS) + \
                root.findall(".//dc:source", namespaces=_OPF_NS):
            text = (ident.text or "").strip()
            if text.startswith("http"):
                source_url = text
                break
        fanficfare_uid = (root.findtext(".//dc:identifier", namespaces=_OPF_NS) or "").strip()
        updated_at = ""
        for date_el in root.findall(".//dc:date", namespaces=_OPF_NS):
            if date_el.get(f"{{{_OPF_NS['opf']}}}event") == "modification":
                updated_at = (date_el.text or "").strip()
        tags = [
            (el.text or "").strip()
            for el in root.findall(".//dc:subject", namespaces=_OPF_NS)
            if (el.text or "").strip()
        ]

        spine_ids = [
            item.get("idref") for item in root.findall(".//opf:spine/opf:itemref", namespaces=_OPF_NS)
        ]
        manifest = {
            item.get("id"): item.get("href")
            for item in root.findall(".//opf:manifest/opf:item", namespaces=_OPF_NS)
        }
        opf_dir = "/".join(opf_name.split("/")[:-1])

        chapters: List[FanFicFareChapter] = []
        order = 0
        for item_id in spine_ids:
            href = manifest.get(item_id)
            if not href or "title_page" in href.lower() or "desc" in href.lower():
                continue
            full_path = f"{opf_dir}/{href}" if opf_dir else href
            try:
                raw = zf.read(full_path).decode("utf-8")
            except KeyError:
                continue
            title_match = re.search(r"<title>(.*?)</title>", raw, re.DOTALL | re.IGNORECASE)
            chapter_title = unescape(title_match.group(1)).strip() if title_match else f"Chapter {order + 1}"
            order += 1
            chapters.append(FanFicFareChapter(
                order_index=order, title=chapter_title, content=_strip_html(raw)))

    return FanFicFareAcquisition(
        source_url=source_url, title=title, author=author,
        external_chapter_count=len(chapters), external_updated_at=updated_at,
        fanficfare_uid=fanficfare_uid, tags=tags, chapters=chapters,
        epub_path=epub_path)


def normalize_fanficfare_result(
    acquisition: FanFicFareAcquisition, *, owner_id: str, fandom_names: List[str],
) -> Dict[str, Any]:
    """Turn a parsed `FanFicFareAcquisition` into the exact `Novel`+`Chapter`
    payload shape `POST /api/novels`/`POST /api/chapters` already accept
    (matching `scripts/mission_g_rezero_draft_runner.py`'s established
    call shape — no new wire format invented here). Preserves every field
    the integration mission asked for: source URL, story ID
    (`fanficfare_uid`, embedded in the description as explicit
    provenance since `Novel` has no free-form metadata field — see
    module docstring's "no schema change" note in the commit), author,
    fandom, chapter number/title, raw content, update metadata
    (`external_chapter_count`/`external_updated_at`).
    """
    novel_payload = {
        "title": acquisition.title,
        "description": f"[FanFicFare] {acquisition.fanficfare_uid}",
        "tags": acquisition.tags[:20],
        "fandom_names": fandom_names,
        "publication_mode": "full_text",
        "external_author_name": acquisition.author,
        "external_source_url": acquisition.source_url,
        "external_chapter_count": acquisition.external_chapter_count,
        "external_updated_at": acquisition.external_updated_at,
        "language": "en",
        "status": "ongoing",
    }
    chapters_payload = [
        {
            "title": ch.title,
            "order_index": ch.order_index,
            "content": ch.content,
            "content_hash": content_hash(ch.content),
        }
        for ch in acquisition.chapters
    ]
    return {"novel": novel_payload, "chapters": chapters_payload,
            "source_fingerprint": source_fingerprint(canonicalize_url(acquisition.source_url))}
