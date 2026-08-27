"""
Kieu du lieu chuan hoa + giao dien trung lap nha cung cap cho Universal Story
Scraper. Xem `server/scraper/__init__.py` cho tong quan kien truc phan tang.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


class ScraperTier(Enum):
    """Tang xu ly — CANG THAP CANG RE, luon thu tang thap truoc."""

    DIRECT_HTTP = 0
    HTML_PARSER = 1
    BROWSER = 2
    UNSUPPORTED = 3


#: CHI tien to thuc su AN TOAN (khong param that nao bat dau bang no) duoc
#: khop THEO TIEN TO — `utm_source`/`utm_medium`/... co hau to doi nhung
#: luon bat dau dung `utm_`. Moi ten khac phai khop CHINH XAC (xem
#: `_TRACKING_PARAM_NAMES`): `startswith("ref")`/`startswith("si")` tung bi
#: phat hien xoa nham `referral_code`, `refund`, `sid`, `size`, `since` —
#: nhung tham so THAT, khong phai theo doi.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_NAMES = {
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "igshid", "mc_cid",
    "mc_eid", "ref", "referrer", "spm", "si",
}


def _la_tham_so_theo_doi(key: str) -> bool:
    ha = key.lower()
    return ha in _TRACKING_PARAM_NAMES or any(
        ha.startswith(p) for p in _TRACKING_PARAM_PREFIXES)


def canonicalize_url(url: str) -> str:
    """
    Chuan hoa MOT url ve dang so sanh duoc: scheme/host thuong, bo cong
    (default port), bo dau `/` cuoi (tru root), bo query tracking, sap query
    con lai theo thu tu bang chu cai (thu tu tham so KHAC nhau nhung CUNG gia
    tri phai ra CUNG mot canonical_url), bo fragment (`#...`).

    KHONG theo redirect — day la chuan hoa CHUOI, khong phai giai quyet
    mang. Giai quyet redirect that su la viec cua `http_fetcher.resolve()`.
    """
    da_strip = url.strip()
    # `urlsplit` doc mot url KHONG co scheme/`//` (vd "example.com/x") nhu
    # MOT duong dan tuong doi thuan tuy — toan bo chuoi roi vao `path`,
    # `netloc` rong, va `urlunsplit` sau do ra mot chuoi hong dang
    # "https:example.com/x". Them scheme truoc neu chua co ca hai dau hieu.
    if "://" not in da_strip and not da_strip.startswith("//"):
        da_strip = f"https://{da_strip}"

    parts = urlsplit(da_strip)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    # Bo cong mac dinh (`:80` cho http, `:443` cho https) — cung mot dich chi
    # khac nhau o cho nay khong duoc phep tao ra hai canonical_url khac nhau.
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[: -len(":443")]
    elif scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[: -len(":80")]

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _la_tham_so_theo_doi(k)
    ]
    query = urlencode(sorted(query_pairs))

    return urlunsplit((scheme, netloc, path, query, ""))


def domain_of(url: str) -> str:
    """Host cua `url`, bo `www.` va vien thuong — dinh nghia DUY NHAT dung
    CHUNG (`site_registry.lookup`, `scraper_ops_service._adapter_for_url`,
    `site_profile.profile_from_proposal`) de tranh mot bien the "quen bo
    www." o MOT noi lam SiteProfile vua xac nhan xong khong tim lai duoc o
    noi khac (khoa luu voi "www.example.com" nhung tra cuu voi
    "example.com", hoac nguoc lai) — phat hien qua review doc lap (Codex)."""
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def same_registrable_host(url_a: str, url_b: str) -> bool:
    """`True` neu hai url CUNG host (sau khi bo `www.`/vien thuong) — dung
    de chan tin tuong mot gia tri LAY TU NOI DUNG TRANG (vd href chuong
    mau, `<link rel=canonical>`) tro sang MOT DOMAIN KHAC domain dang xet:
    dung cho ca ngan SSRF khi tu dong tai "trang chuong mau" (Phase 2,
    `discovery.py`) LAN ngan "dau doc" SiteProfile qua canonical link tro
    cheo domain (phat hien qua review doc lap, Codex). KHONG xu ly quan he
    subdomain-cua-domain-goc (vd `cdn.example.com` != `example.com`) — co
    y BAO THU, mot nguon can subdomain rieng phai duoc them qua
    `site_registry` (ky su xac minh tay), khong qua discovery tu dong."""
    return domain_of(url_a) == domain_of(url_b)


@dataclass
class SeriesInfo:
    """Ket qua `discover_series()` — thong tin muc luc, CHUA phai danh sach
    chuong day du (xem `list_chapters()`)."""

    canonical_url: str
    title: str
    source_domain: str
    author: Optional[str] = None
    description: Optional[str] = None
    #: URL (CHUA chuan hoa) cua tung chuong, THEO THU TU DOC da xac dinh —
    #: Phase 3 Story Harvester V3: adapter co the da SAP XEP LAI thu tu
    #: xuat hien tho tren trang muc luc (vd phat hien "reverse chronological
    #: TOC", uu tien so chuong ro rang hon thu tu HTML tho) — xem
    #: `ordering_evidence` cho LY DO cu the, `chapter_ordering.py` cho phan
    #: cap uu tien day du. KHONG BAO GIO bia dat so chuong con thieu.
    chapter_urls: List[str] = field(default_factory=list)
    #: Giai thich NGUOI DOC duoc ve tang uu tien nao da quyet dinh thu tu
    #: o tren (xem `chapter_ordering.OrderingResult.evidence`) — rong neu
    #: adapter khong tinh toan thu tu (VD chua nang cap len Phase 3).
    ordering_evidence: str = ""


@dataclass
class NormalizedChapter:
    """Mot chuong DA chuan hoa — dinh dang trung lap nha cung cap, san sang
    dua vao pipeline nhap truyen."""

    source_url: str
    canonical_url: str
    source_domain: str
    series_title: str
    chapter_title: str
    raw_text: str
    clean_text: str
    #: sha256(clean_text) — xem `dedupe.content_hash`. Dung de phat hien
    #: NOI DUNG doi (khong phai chi de dinh danh chuong).
    content_hash: str
    #: sha256(canonical_url) — DINH DANH ON DINH cua chinh vi tri nguon nay,
    #: KHONG doi ngay ca khi noi dung doi. Xem `dedupe.source_fingerprint`.
    source_fingerprint: str
    chapter_number: Optional[int] = None
    author: Optional[str] = None
    published_at: Optional[str] = None
    language: str = "vi"
    #: "high"/"medium"/"low" tu `content_extraction.extract_content_v3`
    #: (Phase 6 Story Harvester V3) — CHI duoc dien khi trang KHONG co
    #: boundary da xac minh tay (xem `html_extract.ExtractedPage.
    #: boundary_matched`). RONG ("") nghia la da dung boundary xac minh
    #: (Wikisource/Royal Road) — KHONG can diem tin cay, da CHUNG MINH dung.
    extraction_confidence: str = ""


class StoryProvider(ABC):
    """Giao dien trung lap nha cung cap. Moi adapter cu the (xem
    `adapters/`) trien khai giao dien nay cho MOT dang trang/nguon nhat
    dinh — KHONG duoc bien thanh mot bo giai ma HTML da nang."""

    tier: ScraperTier = ScraperTier.DIRECT_HTTP

    @abstractmethod
    def resolve(self, url: str) -> str:
        """Tra ve canonical_url that su cua `url` — vi du theo redirect
        that (khong chi chuan hoa chuoi), hoac xac nhan adapter nay xu ly
        duoc url nay. Nem `ValueError` neu khong xu ly duoc."""

    @abstractmethod
    def discover_series(self, url: str) -> SeriesInfo:
        """`url` la trang muc luc (hoac mot chuong — adapter tu suy ra muc
        luc cha neu co the). Tra ve thong tin series + danh sach url chuong
        THEO DUNG THU TU hien thi."""

    def list_chapters(self, series: SeriesInfo) -> List[str]:
        """Mac dinh: chinh la `series.chapter_urls` — adapter chi override
        khi can phan trang qua nhieu lan goi (danh sach qua dai cho MOT
        `discover_series` lay het)."""
        return list(series.chapter_urls)

    @abstractmethod
    def fetch_chapter(self, url: str) -> str:
        """Tai VE HTML tho cua MOT chuong. KHONG lam sach o day — tach rieng
        khoi `normalize_chapter` de co the luu HTML tho lam fixture kiem thu
        (xem `server/tests/fixtures/scraper/`)."""

    @abstractmethod
    def normalize_chapter(self, url: str, raw_html: str,
                           series: SeriesInfo) -> NormalizedChapter:
        """Bien HTML tho thanh `NormalizedChapter` sach — day la buoc DUY
        NHAT duoc phep trich xuat/lam sach van ban."""

    def fingerprint(self, chapter: NormalizedChapter) -> str:
        """Dinh danh ON DINH cua VI TRI nguon nay — mac dinh chinh la
        `source_fingerprint` da tinh san trong `normalize_chapter`. Tach
        thanh phuong thuc rieng de test/goi ngoai co the doi chien luoc dinh
        danh (vd theo series+so chuong) ma khong doi contract."""
        return chapter.source_fingerprint

    def resume(self, state: "ScrapeState", chapter_urls: List[str]) -> List[str]:
        """Loc `chapter_urls` con lai CAN xu ly, dua tren `state` da luu tu
        lan chay truoc (xem `dedupe.ScrapeState`) — mac dinh: bo qua url da
        co canonical_url trong state VA chua danh dau la loi/can thu lai."""
        con_lai = []
        for url in chapter_urls:
            canon = canonicalize_url(url)
            rec = state.get(canon)
            if rec is None or rec.get("status") == "failed":
                con_lai.append(url)
        return con_lai
