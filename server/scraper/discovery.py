"""
Cong cu KHAM PHA site CHUA duoc cau hinh (`site_registry.lookup()` tra ve
`None`) — Phase 2 cua Story Harvester V3. TAT DINH, KHONG dung LLM: chi suy
luan tu cau truc HTML that su co tren trang (JSON-LD, OpenGraph, cum lien
ket lap lai, mau URL, vung noi dung van ban day dac) roi tra ve MOT de xuat
co cau truc kem CONFIDENCE ro rang — KHONG BAO GIO tu dung "doan" mot mau
URL/selector khi khong co du bang chung (xem `_MIN_CLUSTER_SIZE`).

Phan cap uu tien khi giai quyet mot URL (xem `server/scraper_ops_service.py`):
    SiteConfig da xac minh (`site_registry`) > SiteProfile da hoc (`site_profile`)
    > MOT lan kham pha moi (module nay) — module nay CHI chay khi ca hai
    tang tren khong co du lieu.

Toi da HAI lan fetch moi lan goi `discover()`: trang muc luc + MOT trang
chuong mau (de xac nhan vung noi dung truoc khi de xuat HIGH confidence) —
gioi han co tinh, tranh "con bao yeu cau" (xem AI_ROUTER.md, nguyen tac
Phase 9/10 cua Story Harvester V3: khong crawl hang loat chi de kham pha).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from server.scraper.contract import ScraperTier, canonicalize_url
from server.scraper.html_extract import extract
from server.scraper.http_fetcher import FetchError

#: So lien ket TOI THIEU cung "hinh dang" URL (xem `_shape_of`) de duoc coi
#: la MOT cum chuong that su, khong phai trung hop ngau nhien vai lien ket
#: giong nhau (vd menu "chia se len mang xa hoi" thuong co 2-4 lien ket cung
#: dang nhung KHONG phai danh sach chuong). Duoi nguong nay: KHONG de xuat
#: mau URL nao ca (tra ve `None`), thay vi doan bua — xem docstring module.
_MIN_CLUSTER_SIZE = 3
#: So ky tu van ban TOI THIEU trong mot ung vien vung noi dung tren trang
#: chuong mau de duoc coi la "vung noi dung that", khong phai mot doan gioi
#: thieu ngan/placeholder dang nhap.
_MIN_CONTAINER_CHARS = 200

_CHAPTER_WORD_RE = re.compile(
    r"(chương|chuong|chapter|ch\.|episode|phần|phan|tập|tap|hồi|hoi)",
    re.IGNORECASE,
)
_DIGIT_RUN_RE = re.compile(r"\d+")
_NEXT_WORD_RE = re.compile(
    r"(next|tiếp theo|tiep theo|trang sau|chương sau|chuong sau|»|›)",
    re.IGNORECASE,
)
_PAGINATION_HINT_RE = re.compile(r"(page|trang)", re.IGNORECASE)
_CANONICAL_LINK_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
_REL_NEXT_RE = re.compile(r'rel=["\']next["\']', re.IGNORECASE)

#: Tu khoa GOI Y mot the/id co the la vung noi dung chuong — CHI la goi y de
#: uu tien quet, KHONG phai danh sach dong cung (site nao dung ten khac hoan
#: toan se khong tim duoc ung vien nao, dan den confidence thap hon — dung
#: dan, khong phai loi).
_CONTAINER_HINT_RE = re.compile(
    r"(content|chapter|chuong|article|entry|post|story|truyen|reading|noi.?dung|main.?text)",
    re.IGNORECASE,
)
_NOISE_TAGS = {"script", "style", "noscript", "nav", "header", "footer", "aside"}
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class SourceConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PaginationStrategy(Enum):
    NONE = "none"
    NEXT_PREV = "next_prev"
    NUMBERED_PAGES = "numbered_pages"


@dataclass
class DiscoveryProposal:
    """Ket qua kham pha MOT site chua cau hinh — hien thi cho operator xem
    truoc khi cho phep bat dau quet that (xem admin UI "NEW SOURCE
    DETECTED"). KHONG phai mot `SiteConfig`/`SiteProfile` — chi la DE XUAT,
    can duoc operator xac nhan (MEDIUM) hoac co the tu dong dry-run (HIGH),
    khong bao gio tu dong ghi du lieu that."""

    source_url: str
    canonical_url: str
    work_title: Optional[str]
    author: Optional[str]
    description: Optional[str]
    index_url: str
    chapter_count_estimate: int
    #: Regex ap len href tho, sap dua thang cho `SiteConfig.chapter_href_pattern`
    #: neu operator chap nhan de xuat nay — `None` neu khong du bang chung
    #: (xem `_MIN_CLUSTER_SIZE`), KHONG BAO GIO mot pattern doan bua.
    chapter_url_pattern: Optional[str]
    #: Mo ta NGUOI DOC duoc cua vung noi dung tren trang chuong mau, vi du
    #: "div.chapter-content" — `None` neu chua xac dinh duoc (xem
    #: `_MIN_CONTAINER_CHARS`).
    content_container_candidate: Optional[str]
    pagination_strategy: PaginationStrategy
    #: LUON de xuat Tier 0 (DIRECT_HTTP) — engine nay KHONG BAO GIO tu dong
    #: de xuat Tier 2 (browser), du tin hieu co ve can JS render (xem
    #: `evidence` cho ghi chu do, quyet dinh nang cap la cua operator/ky su
    #: sau khi THAT SU xac nhan, dung theo Phase 10 cua Story Harvester V3).
    fetch_tier: ScraperTier
    confidence: SourceConfidence
    #: Danh sach ly do NGUOI DOC duoc, giai thich CHINH XAC tin hieu nao dan
    #: den confidence nay — bat buoc hien thi cho operator, khong duoc an di.
    evidence: List[str] = field(default_factory=list)
    #: MOT vai url chuong dau tien (theo dung thu tu tim thay tren trang muc
    #: luc) — dung de xem truoc, KHONG phai danh sach day du.
    sample_chapter_urls: List[str] = field(default_factory=list)


def _shape_of(path: str) -> str:
    """Thay moi day chu so lien tiep bang `#` — hai duong dan chi khac o so
    chuong (vd `/truyen/x/chuong-12` va `/truyen/x/chuong-345`) se ra CUNG
    mot "hinh dang", dung de gom cum."""
    return _DIGIT_RUN_RE.sub("#", path)


def _shape_to_regex(shape: str) -> str:
    escaped = re.escape(shape)
    return escaped.replace(re.escape("#"), r"\d+")


class _ContainerScanner(HTMLParser):
    """Quet MOT trang chuong mau, tim the (tag + class/id) co ten goi y
    "content/chapter/..." (xem `_CONTAINER_HINT_RE`) bao boc NHIEU van ban
    hien thi nhat — cung phong cach tag-stack O(1)/the voi
    `html_extract._Parser` (xem comment o do ve ly do khong khop ten khi
    pop, chi dem long nhau)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._stack: List[Optional[str]] = []
        self.totals: Dict[str, int] = {}
        self.body_total = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_d = {k: v for k, v in attrs if v is not None}
        if tag in _NOISE_TAGS:
            self._skip_depth += 1

        sig: Optional[str] = None
        for cls in attrs_d.get("class", "").split():
            if _CONTAINER_HINT_RE.search(cls):
                sig = f"{tag}.{cls}"
                break
        if sig is None:
            tag_id = attrs_d.get("id", "")
            if tag_id and _CONTAINER_HINT_RE.search(tag_id):
                sig = f"{tag}#{tag_id}"

        if tag not in _VOID_TAGS:
            self._stack.append(sig)

    def handle_endtag(self, tag: str) -> None:
        if tag in _NOISE_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag not in _VOID_TAGS and self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or not data.strip():
            return
        n = len(data)
        self.body_total += n
        for sig in set(s for s in self._stack if s is not None):
            self.totals[sig] = self.totals.get(sig, 0) + n


def _scan_content_container(sample_chapter_html: str) -> Tuple[Optional[str], float]:
    """Tra ve `(ten_ung_vien, ty_le_van_ban_trang)` — `ten_ung_vien` la
    `None` neu khong ung vien nao du `_MIN_CONTAINER_CHARS` ky tu."""
    scanner = _ContainerScanner()
    scanner.feed(sample_chapter_html)
    scanner.close()
    if not scanner.totals:
        return None, 0.0
    best_sig = max(scanner.totals, key=lambda s: scanner.totals[s])
    best_total = scanner.totals[best_sig]
    if best_total < _MIN_CONTAINER_CHARS:
        return None, 0.0
    ratio = best_total / scanner.body_total if scanner.body_total else 0.0
    return best_sig, ratio


def _find_link_clusters(links: List[Tuple[str, str]], base_url: str
                        ) -> Dict[str, List[Tuple[str, str]]]:
    """Gom `links` theo `_shape_of(path)` — moi nhom la `[(href_tuyet_doi,
    van_ban_lien_ket), ...]` THEO DUNG thu tu xuat hien, giu ca hai de goi
    sau con dung de tinh ty le "giong chuong" va de xuat pattern."""
    groups: Dict[str, List[Tuple[str, str]]] = {}
    seen_per_group: Dict[str, set] = {}
    for href, text in links:
        absolute = urljoin(base_url, href)
        path = urlsplit(absolute).path
        if not path or path == "/":
            continue
        shape = _shape_of(path)
        seen = seen_per_group.setdefault(shape, set())
        if absolute in seen:
            continue
        seen.add(absolute)
        groups.setdefault(shape, []).append((absolute, text))
    return groups


def _pick_chapter_cluster(groups: Dict[str, List[Tuple[str, str]]]
                          ) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """Chon nhom co kha nang la danh sach chuong nhat: uu tien SO LUONG lon
    hon, hoa thi uu tien ty le lien ket "giong chuong" (co tu khoa chuong
    hoac co so trong van ban lien ket) cao hon. Tra ve `(shape, nhom)` hoac
    `(None, [])` neu khong nhom nao du `_MIN_CLUSTER_SIZE`."""
    def chapterish_fraction(items: List[Tuple[str, str]]) -> float:
        if not items:
            return 0.0
        hits = sum(
            1 for _href, text in items
            if _CHAPTER_WORD_RE.search(text) or _DIGIT_RUN_RE.search(text)
        )
        return hits / len(items)

    candidates = [
        (shape, items) for shape, items in groups.items()
        if len(items) >= _MIN_CLUSTER_SIZE
    ]
    if not candidates:
        return None, []
    candidates.sort(key=lambda pair: (len(pair[1]), chapterish_fraction(pair[1])),
                    reverse=True)
    return candidates[0]


def _detect_pagination(groups: Dict[str, List[Tuple[str, str]]], chapter_shape: Optional[str],
                        raw_html: str) -> PaginationStrategy:
    for shape, items in groups.items():
        if shape == chapter_shape or len(items) < 2:
            continue
        if _PAGINATION_HINT_RE.search(shape):
            return PaginationStrategy.NUMBERED_PAGES
    if _REL_NEXT_RE.search(raw_html):
        return PaginationStrategy.NEXT_PREV
    for _shape, items in groups.items():
        if any(_NEXT_WORD_RE.search(text) for _href, text in items):
            return PaginationStrategy.NEXT_PREV
    return PaginationStrategy.NONE


def _extract_title_author_description(page, raw_html: str) -> Tuple[
        Optional[str], Optional[str], Optional[str], bool]:
    """Tra ve `(title, author, description, co_json_ld_co_cau_truc)`."""
    has_structured_json_ld = False
    title = page.meta.get("og:title")
    author = page.meta.get("author") or page.meta.get("article:author")
    description = page.meta.get("og:description") or page.meta.get("description")

    for block in page.json_ld:
        candidates = block if isinstance(block, list) else [block]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            if item_type in ("Book", "CreativeWork", "Article", "WebSite"):
                has_structured_json_ld = True
                title = title or item.get("name") or item.get("headline")
                desc = item.get("description")
                description = description or (str(desc) if desc else None)
                author_field = item.get("author")
                if not author and isinstance(author_field, dict):
                    author = author_field.get("name")
                elif not author and isinstance(author_field, str):
                    author = author_field

    title = title or page.title
    return title, author, description, has_structured_json_ld


def _canonical_url_of(raw_html: str, final_url: str) -> str:
    match = _CANONICAL_LINK_RE.search(raw_html)
    if match:
        return canonicalize_url(urljoin(final_url, match.group(1)))
    return canonicalize_url(final_url)


class UnknownSiteDiscoveryEngine:
    """Diem vao Phase 2 — goi khi `site_registry.lookup(url)` va SiteProfile
    da hoc (`site_profile.py`) DEU khong co cau hinh cho domain nay."""

    def __init__(self, fetcher) -> None:
        self._fetcher = fetcher

    def discover(self, url: str) -> DiscoveryProposal:
        result = self._fetcher.fetch(url)
        page = extract(result.text)
        canonical = _canonical_url_of(result.text, result.final_url)

        groups = _find_link_clusters(page.links, result.final_url)
        chapter_shape, chapter_items = _pick_chapter_cluster(groups)
        chapter_urls = [href for href, _text in chapter_items]
        pagination = _detect_pagination(groups, chapter_shape, result.text)

        title, author, description, has_json_ld = \
            _extract_title_author_description(page, result.text)

        evidence: List[str] = []
        score = 0

        if chapter_shape is None:
            evidence.append(
                "KHÔNG tìm thấy cụm liên kết lặp lại (>= "
                f"{_MIN_CLUSTER_SIZE}) cùng hình dạng URL trên trang mục "
                "lục — không thể đề xuất mẫu URL chương. Có thể trang này "
                "cần JavaScript để hiển thị danh sách chương, hoặc không "
                "phải trang mục lục thật.")
        else:
            evidence.append(
                f"Tìm thấy {len(chapter_items)} liên kết cùng hình dạng URL "
                f"({_shape_to_regex(chapter_shape)}) — đề xuất đây là danh "
                "sách chương.")
            score += 2 if len(chapter_items) >= 5 else 1
            frac = sum(
                1 for _h, t in chapter_items
                if _CHAPTER_WORD_RE.search(t) or _DIGIT_RUN_RE.search(t)
            ) / len(chapter_items)
            if frac >= 0.6:
                score += 1
                evidence.append(
                    f"{frac:.0%} liên kết trong cụm có từ khóa chương hoặc "
                    "số chương trong văn bản hiển thị.")

        if has_json_ld:
            score += 1
            evidence.append("Trang có JSON-LD có cấu trúc (schema.org).")
        if title:
            score += 1
            evidence.append(f"Tiêu đề tìm được: {title!r}.")

        sample_html: Optional[str] = None
        if chapter_urls:
            try:
                sample_result = self._fetcher.fetch(chapter_urls[0])
                sample_html = sample_result.text
            except FetchError as exc:
                evidence.append(f"Không tải được trang chương mẫu để xác nhận: {exc}.")

        container_candidate: Optional[str] = None
        if sample_html is not None:
            container_candidate, ratio = _scan_content_container(sample_html)
            if container_candidate:
                score += 1
                evidence.append(
                    f"Trang chương mẫu có vùng nội dung rõ ràng: "
                    f"{container_candidate} (~{ratio:.0%} văn bản trang).")
            else:
                evidence.append(
                    "Không xác định được vùng nội dung rõ ràng trên trang "
                    "chương mẫu (không thẻ nào có đủ "
                    f"{_MIN_CONTAINER_CHARS} ký tự văn bản với tên gợi ý "
                    "nội dung/chương) — cần operator kiểm tra thủ công "
                    "trước khi quét thật.")

        if chapter_shape is None:
            confidence = SourceConfidence.LOW
        elif score >= 4 and container_candidate:
            confidence = SourceConfidence.HIGH
        else:
            confidence = SourceConfidence.MEDIUM

        if len(page.visible_text()) < 100 and not chapter_urls:
            evidence.append(
                "Trang gần như không có văn bản hiển thị — có thể cần "
                "JavaScript để render. KHÔNG tự động chuyển sang trình "
                "duyệt (Tier 2); cần kỹ sư xác nhận thật trước khi thêm "
                "độ phức tạp đó (xem Phase 10, docs/AI_ROUTER.md).")

        return DiscoveryProposal(
            source_url=url,
            canonical_url=canonical,
            work_title=title,
            author=author,
            description=description,
            index_url=canonicalize_url(result.final_url),
            chapter_count_estimate=len(chapter_items),
            chapter_url_pattern=(
                _shape_to_regex(chapter_shape) if chapter_shape else None),
            content_container_candidate=container_candidate,
            pagination_strategy=pagination,
            fetch_tier=ScraperTier.DIRECT_HTTP,
            confidence=confidence,
            evidence=evidence,
            sample_chapter_urls=chapter_urls[:5],
        )
