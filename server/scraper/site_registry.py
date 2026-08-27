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

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SiteConfig:
    domain: str
    chapter_href_pattern: str
    title_suffix_to_strip: str = ""
    #: Ghi chu ngan: khi nao/qua canary nao domain nay duoc xac minh —
    #: dung cho nguoi doc code, khong dung trong logic.
    verified_via: str = ""


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
        # Ap dung cho BAT KY truyen nao tren royalroad.com, khong rieng mot
        # ID — da kiem tra khong bat nham lien ket sang truyen KHAC (vd o
        # khung "de xuat") tren cung trang muc luc.
        chapter_href_pattern=r"/fiction/\d+/[^/\"]+/chapter/\d+/",
        title_suffix_to_strip=" | Royal Road",
        verified_via=(
            "Router V2 content-ops phase, 2026-08-27 — canary that tren "
            "'Regis and Charlotte' (14 chương, truyện đã hoàn thành), "
            "robots.txt xac nhan cho phep truoc khi them."),
    ),
}


def lookup(url: str) -> Optional[SiteConfig]:
    """Tra ve `SiteConfig` neu domain cua `url` da duoc XAC MINH cau hinh,
    `None` neu chua — route goi ham nay PHAI bao loi ro rang cho operator
    khi `None` ("site nay chua duoc cau hinh"), KHONG doan mot pattern bat
    ky va am tham co the tra ve rac."""
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return _REGISTRY.get(host)


def supported_domains() -> list:
    return sorted(_REGISTRY)
