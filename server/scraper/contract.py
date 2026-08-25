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


#: Cac tham so theo doi/quang cao pho bien, KHONG anh huong noi dung trang —
#: loai bo khoi URL chuan hoa de hai bien the (co/khong tracking) tro thanh
#: CUNG mot canonical_url (chong trung).
_TRACKING_PARAM_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "spm", "si")


def canonicalize_url(url: str) -> str:
    """
    Chuan hoa MOT url ve dang so sanh duoc: scheme/host thuong, bo cong
    (default port), bo dau `/` cuoi (tru root), bo query tracking, sap query
    con lai theo thu tu bang chu cai (thu tu tham so KHAC nhau nhung CUNG gia
    tri phai ra CUNG mot canonical_url), bo fragment (`#...`).

    KHONG theo redirect — day la chuan hoa CHUOI, khong phai giai quyet
    mang. Giai quyet redirect that su la viec cua `http_fetcher.resolve()`.
    """
    parts = urlsplit(url.strip())
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
        if not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(sorted(query_pairs))

    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass
class SeriesInfo:
    """Ket qua `discover_series()` — thong tin muc luc, CHUA phai danh sach
    chuong day du (xem `list_chapters()`)."""

    canonical_url: str
    title: str
    source_domain: str
    author: Optional[str] = None
    description: Optional[str] = None
    #: URL (CHUA chuan hoa) cua tung chuong, theo DUNG thu tu hien thi tren
    #: trang muc luc — thu tu la du lieu, khong duoc tu sap lai.
    chapter_urls: List[str] = field(default_factory=list)


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
