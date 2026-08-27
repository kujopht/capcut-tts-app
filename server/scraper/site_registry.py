"""
Danh sach TRANG cac site da duoc CAU HINH + XAC MINH THAT cho
`GenericIndexAdapter` (Tier 0) — tra cuu theo domain cua URL nguoi dung
dan vao.

VI SAO CAN FILE NAY: `GenericIndexAdapter` can `chapter_href_pattern`
(regex nhan dien lien ket chuong tren trang muc luc) — THAM SO NAY LA
DAC THU TUNG SITE, khong the doan tu dong tin cay duoc (da xac nhan qua
canary that: xem `docs/reports/product-phase-2026-08-27.md` Phase 3,
"GenericIndexAdapter requires per-site configuration rather than fully
automatic guessing"). File nay TAP TRUNG hoa cau hinh do — mot dict, KHONG
phai if/elif rai rac trong route handler — de sau nay them site moi chi la
THEM MOT DONG, khong sua logic dieu phoi.

CHI THEM domain vao day sau khi da XAC MINH THAT qua canary (khong doan) —
xem lich su them domain trong git blame tung dong cho bang chung.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional
from urllib.parse import urlsplit


class ScopeExtractionError(Exception):
    """URL khop domain da cau hinh, nhung khong khop hinh dang URL mong doi
    (vd thieu ID truyen trong duong dan) — loi RO RANG, khong am tham dung
    mot pattern KHONG duoc thu hep pham vi (xem `SiteConfig.scope_id_pattern`)."""


@dataclass(frozen=True)
class SiteConfig:
    domain: str
    #: Co the chua `{scope_id}` (xem `scope_id_pattern`) — neu co, PHAI
    #: duoc dien gia tri that truoc khi dua cho `GenericIndexAdapter`, KHONG
    #: BAO GIO dung nguyen chuoi co `{scope_id}` lam regex that.
    chapter_href_pattern: str
    title_suffix_to_strip: str = ""
    #: Regex VOI DUNG MOT capture group, ap len URL NGUOI DUNG dan vao, de
    #: lay ID rieng cua tung truyen tren site nay (vd ID truyen cua Royal
    #: Road trong `/fiction/{id}/...`). `None` = site khong can thu hep pham
    #: vi theo tung truyen (vd Wikisource: ten tac pham da nam san trong
    #: duong dan chuong, khong can them ID rieng).
    #:
    #: LY DO CAN: mot regex `chapter_href_pattern` dung chung KHONG thu hep
    #: theo truyen co the bat NHAM lien ket sang truyen KHAC xuat hien tren
    #: cung trang (vd khung "de xuat/tac gia khac") — phat hien qua review
    #: doc lap (Codex) tren Royal Road, noi ID truyen nam ngay trong duong
    #: dan nhung khong duoc dua vao pattern.
    scope_id_pattern: Optional[str] = None
    #: Ghi chu ngan: khi nao/qua canary nao domain nay duoc xac minh —
    #: dung cho nguoi doc code, khong dung trong logic.
    verified_via: str = ""
    #: "generic_index" (mac dinh, co trang muc luc) hoac "navigation_only"
    #: (Phase 3 Story Harvester V3: KHONG co trang muc luc, chi theo doi
    #: lien ket "chuong tiep theo" tuan tu — xem
    #: `adapters/navigation_only_adapter.py`). Khi la "navigation_only",
    #: `chapter_href_pattern` duoc HIEU LAI thanh `next_href_pattern` (mau
    #: khop lien ket "chuong tiep theo" tren MOT trang chuong, khong phai
    #: mau khop lien ket chuong tren trang muc luc — hai khai niem khac
    #: nhau nhung dung CHUNG mot truong de tranh them mot truong chi dung
    #: cho MOT nhanh hiem gap).
    adapter_kind: str = "generic_index"

    def resolved(self, url: str) -> "SiteConfig":
        """Tra ve MOT ban da dien `{scope_id}` bang gia tri that rut ra tu
        `url`, hoac chinh no khong doi neu `scope_id_pattern` la `None`.
        Nem `ScopeExtractionError` RO RANG neu can thu hep pham vi nhung
        `url` khong khop hinh dang mong doi — KHONG am tham lui ve pattern
        rong (se tai hien dung loi da phat hien)."""
        if self.scope_id_pattern is None:
            return self
        match = re.search(self.scope_id_pattern, url)
        if not match:
            raise ScopeExtractionError(
                f"URL không khớp hình dạng mong đợi cho {self.domain} "
                f"(cần rút ra ID riêng của truyện, ví dụ ID trong đường dẫn) — "
                f"kiểm tra lại URL đã dán, đây có thể không phải trang mục lục "
                f"thật của một truyện cụ thể.")
        return replace(self, chapter_href_pattern=self.chapter_href_pattern.format(
            scope_id=re.escape(match.group(1))))


#: KHOA la domain (khong `www.`, chu thuong) — xem `lookup()`.
_REGISTRY = {
    "vi.wikisource.org": SiteConfig(
        domain="vi.wikisource.org",
        chapter_href_pattern=r"/Ch%C6%B0%C6%A1ng_\d+$",
        title_suffix_to_strip=" – Wikisource tiếng Việt",
        verified_via=(
            "Router V2 content-ops phase, 2026-08-27 — canary that tren "
            "'Lều chõng' (Ngô Tất Tố, 21 chương), xac minh sau khi sua loi "
            "ro ri UI-chrome MediaWiki (server/scraper/html_extract.py)."),
    ),
    # Cau truc HTML HOAN TOAN khac vi.wikisource.org (khong phai MediaWiki) —
    # them de kiem tra Tier 0 tren mot dang site khac, khong chi mot ho.
    # robots.txt (kiem truoc khi them) cho phep bot chung o duong doc chuong
    # that (chi chan mot vai duong khong lien quan nhu /vote, cong voi cac
    # bot AI-training co ten rieng nhu GPTBot/CCBot — HttpFetcher trinh dien
    # nhu mot bot chung, khong bi cac dong chan rieng do ap dung).
    "royalroad.com": SiteConfig(
        domain="royalroad.com",
        # `{scope_id}` duoc dien = ID truyen that rut tu URL nguoi dung dan
        # vao (xem `scope_id_pattern`) — THU HEP CHINH XAC ve mot truyen,
        # khong bat nham lien ket chuong cua truyen khac tren cung trang
        # (vd khung "de xuat") — phat hien qua review doc lap (Codex).
        chapter_href_pattern=r"/fiction/{scope_id}/[^/\"]+/chapter/\d+/",
        scope_id_pattern=r"/fiction/(\d+)/",
        title_suffix_to_strip=" | Royal Road",
        verified_via=(
            "Router V2 content-ops phase, 2026-08-27 — canary that tren "
            "'Regis and Charlotte' (14 chương, truyện đã hoàn thành), "
            "robots.txt xac nhan cho phep truoc khi them."),
    ),
}


def lookup(url: str) -> Optional[SiteConfig]:
    """Tra ve `SiteConfig` DA GIAI QUYET (san sang dua thang cho
    `GenericIndexAdapter`) neu domain cua `url` da duoc XAC MINH cau hinh,
    `None` neu domain chua duoc ho tro — route goi ham nay PHAI bao loi ro
    rang cho operator khi `None`, KHONG doan mot pattern bat ky. Neu domain
    duoc ho tro nhung `url` khong khop hinh dang mong doi (thieu ID truyen
    o site can thu hep pham vi), nem `ScopeExtractionError` — de nguyen,
    KHONG bat va am tham lui ve pattern rong."""
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    cfg = _REGISTRY.get(host)
    return cfg.resolved(url) if cfg is not None else None


def supported_domains() -> list:
    return sorted(_REGISTRY)
