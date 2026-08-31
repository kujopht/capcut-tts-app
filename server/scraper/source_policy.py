"""
Chinh sach nguon fanfic anime/manga — ket qua NGHIEN CUU THAT (Anime Fanfic
Production Canary, xac minh 2026-08-31), khong phai suy doan.

VI SAO FILE NAY TON TAI: moi domain o day da duoc kiem tra TOAN VEN — doc
robots.txt/ToS THAT (khong chi tra loi tu tri nho huan luyen) VA thu fetch
THAT qua `server/scraper/http_fetcher.py::HttpFetcher` (chinh fetcher san
xuat, khong phai mot cong cu doc trang rieng biet co User-Agent/TLS khac).
Ket luan o day la MOT LAN, tranh cho agent/operator sau nay lap lai dung
nghien cuu da lam, hoac te hon — vo tinh thu goi mot domain da biet ro la
chan quyen tac gia/ToS/ky thuat.

`check_source_policy()` duoc goi TRUOC bat ky discovery/fetch nao trong
`ScraperOpsService.discover()`/`confirm_unknown_source()` — domain nam
trong `BLOCKED_CLASSES` bi tu choi NGAY, khong chay heuristic, khong gui
mot request nao ve domain do.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
from urllib.parse import urlsplit


class SourcePolicyClass(str, Enum):
    FULL_TEXT_ALLOWED = "full_text_allowed"
    METADATA_AND_LINK_ONLY = "metadata_and_link_only"
    AUTHOR_OPT_IN_REQUIRED = "author_opt_in_required"
    POLICY_BLOCKED = "policy_blocked"
    AUTH_REQUIRED = "auth_required"
    TECHNICALLY_UNSTABLE = "technically_unstable"


#: Cac lop KHONG duoc phep di qua discovery/scrape tu dong — domain khop
#: mot trong so nay bi `check_source_policy()` tu choi truoc ca khi fetch.
#: `AUTH_REQUIRED` CO CHU Y khong nam trong tap nay: mot nguon can dang
#: nhap co the van hop le qua mot luong rieng (chua xay dung) sau nay,
#: khac han POLICY_BLOCKED/TECHNICALLY_UNSTABLE/AUTHOR_OPT_IN_REQUIRED —
#: ca ba deu la "khong the/khong duoc tu dong hoa BAY GIO", khong phai
#: "can them mot buoc ky thuat".
_BLOCKED_CLASSES = frozenset({
    SourcePolicyClass.POLICY_BLOCKED,
    SourcePolicyClass.AUTHOR_OPT_IN_REQUIRED,
    SourcePolicyClass.TECHNICALLY_UNSTABLE,
})


@dataclass(frozen=True)
class SourcePolicyRecord:
    domain: str
    policy_class: SourcePolicyClass
    #: Bang chung THAT (trich dan ToS/robots.txt, ma HTTP that quan sat
    #: duoc) — khong phai "co ve nguy hiem".
    evidence: str
    verified_at: str  # ISO date, vd "2026-08-31"


class SourcePolicyBlockedError(Exception):
    """Domain da duoc XAC MINH thuoc mot lop khong tu dong hoa duoc BAY
    GIO — xem `SourcePolicyRecord.evidence` trong thong diep loi."""


#: HAT GIONG tu khao sat nguon anime/manga fanfic that (khong phai vi du) —
#: dang ky them qua registry nay khi co nghien cuu moi, KHONG hardcode ranh
#: gioi o noi khac.
_KNOWN_SOURCE_POLICIES: Dict[str, SourcePolicyRecord] = {
    "archiveofourown.org": SourcePolicyRecord(
        domain="archiveofourown.org",
        policy_class=SourcePolicyClass.AUTHOR_OPT_IN_REQUIRED,
        evidence=(
            "Moi fanwork la ban quyen CUA TAC GIA, khong phai cua AO3/OTW — "
            "AO3 khong the cap quyen tai xuat ban thay tac gia du muon. OTW "
            "cong khai: 'khong ngoai le... cho nguoi muon tao dataset', chu "
            "dong gioi han toc do/giam sat, va da yeu cau Common Crawl ngung "
            "quet nam 2022. THEM: `HttpFetcher` that (User-Agent tu nhan "
            "dang minh bach) nhan HTTP 403 tren ca trang ToS lan trang "
            "/tags/{fandom}/works that."),
        verified_at="2026-08-31",
    ),
    "fanfiction.net": SourcePolicyRecord(
        domain="fanfiction.net",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=(
            "robots.txt cho phep tai (Content-Signal: search=yes,ai-train=no,"
            "use=reference) va ToS cho phep automation TOC DO NGUOI, nhung "
            "loai tru 'caches or archives' khoi ngoai le search-engine. "
            "THEM (quyet dinh hon): `HttpFetcher` that nhan HTTP 403 tren "
            "mot trang truyen that (Ninja's Hero Academia, /s/13530962/...) "
            "— ha tang chan bot du ToS/robots.txt nghe co ve chap nhan."),
        verified_at="2026-08-31",
    ),
    "wattpad.com": SourcePolicyRecord(
        domain="wattpad.com",
        policy_class=SourcePolicyClass.POLICY_BLOCKED,
        evidence=(
            "ToS cam RO RANG, khong dieu kien: \"Don't use any kind of "
            "software, device or method (whether it's manual or automated) "
            "to 'crawl', 'spider' or otherwise remove any content\" — ap "
            "dung cho CA metadata, khong chi full-text."),
        verified_at="2026-08-31",
    ),
    "scribblehub.com": SourcePolicyRecord(
        domain="scribblehub.com",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=("HTTP 403 tren CA robots.txt lan trang ToS — khong doc "
                  "duoc chinh sach that su, va ha tang tu choi fetch tu dong."),
        verified_at="2026-08-31",
    ),
    "royalroad.com": SourcePolicyRecord(
        domain="royalroad.com",
        policy_class=SourcePolicyClass.POLICY_BLOCKED,
        evidence=(
            "Domain nay DA nam san trong `site_registry.py` tu mot mission "
            "truoc (robots.txt cho phep tai lien ket chuong, nen da them "
            "vao) — nhung ToS (cap nhat 2025-03-03) cam RO RANG: 'use or "
            "launch any manual or automated system or software, devices, "
            "scripts robots, other means or processes to access, scrape, "
            "crawl, cache, spider any web page or other service contained "
            "in our Services'. robots.txt cho phep KHONG co nghia ToS cho "
            "phep — hai thu khac nhau, va ToS la rang buoc phap ly that su. "
            "site_registry.py CO CHU Y khong bi xoa cau hinh (lich su ky "
            "thuat) nhung moi lan `discover`/`start_or_continue`/`confirm_"
            "unknown_source` goi domain nay deu bi chan o day TRUOC KHI "
            "cham toi site_registry."),
        verified_at="2026-08-31",
    ),
    "quotev.com": SourcePolicyRecord(
        domain="quotev.com",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=("robots.txt cho phep, nhung `HttpFetcher` that nhan HTTP "
                  "200 voi than trang RONG (1 ky tu) tren trang chu VA trang "
                  "muc fanfiction — nghi la chan bot bang trang gia, khong "
                  "phai loi tam thoi."),
        verified_at="2026-08-31",
    ),
    "docln.net": SourcePolicyRecord(
        domain="docln.net",
        policy_class=SourcePolicyClass.AUTHOR_OPT_IN_REQUIRED,
        evidence=(
            "KY THUAT co the tai duoc that (`HttpFetcher` nhan HTTP 200, "
            "~170KB noi dung that tren trang chu — nguon DUY NHAT trong dot "
            "khao sat nay khong bi 403/rong) — nhung KHONG rights-clear: "
            "khu 'Truyen Sang Tac' (sang tac/fanfic goc) la noi dung CUA "
            "TUNG TAC GIA, giong nguyen tac AO3 (can dong y tung nguoi, "
            "khong the tong quat hoa). RIENG khu Light Novel dich (phan "
            "lon noi dung site) TE HON: chinh site tu nhan 'Truyen co chu "
            "so huu ban quyen se bi xoa' — nghia la phan lon la ban dich "
            "KHONG duoc cap phep, dang cho tac gia/nha xuat ban khieu nai. "
            "KHONG dung khu do lam nguon du reachable ve mat ky thuat."),
        verified_at="2026-08-31",
    ),
    "forums.spacebattles.com": SourcePolicyRecord(
        domain="forums.spacebattles.com",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=("robots.txt cho phep (Content-Signal: search=yes,ai-"
                  "train=no,use=reference — giong FFN/docln), nhung "
                  "`HttpFetcher` that nhan HTTP 403 tren mot forum that "
                  "(/forums/creative-writing.20/)."),
        verified_at="2026-08-31",
    ),
    "syosetu.org": SourcePolicyRecord(
        domain="syosetu.org",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence="Hameln — HTTP 403 tren ca robots.txt lan trang chu qua HttpFetcher that.",
        verified_at="2026-08-31",
    ),
    "forums.sufficientvelocity.com": SourcePolicyRecord(
        domain="forums.sufficientvelocity.com",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=("robots.txt cho phep (cung Content-Signal voi SpaceBattles/"
                  "FFN), nhung HttpFetcher that nhan HTTP 403 tren forum "
                  "that (/forums/creative-writing.2/)."),
        verified_at="2026-08-31",
    ),
    "metruyenchu.com": SourcePolicyRecord(
        domain="metruyenchu.com",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence="robots.txt cho phep hau het duong dan, nhung HttpFetcher that nhan HTTP 403 tren trang chu.",
        verified_at="2026-08-31",
    ),
    "truyenfull.today": SourcePolicyRecord(
        domain="truyenfull.today",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=("Loi SSL handshake (UNEXPECTED_EOF_WHILE_READING) LAP LAI "
                  "qua hai lan thu that (khong phai loi tam thoi mot lan) — "
                  "nghi la chan o tang TLS/CDN, khong doc duoc noi dung."),
        verified_at="2026-08-31",
    ),
    "truyen.tangthuvien.vn": SourcePolicyRecord(
        domain="truyen.tangthuvien.vn",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence="HttpFetcher that: het thoi gian ket noi (timeout) — khong xac dinh duoc la chan hay chi cham.",
        verified_at="2026-08-31",
    ),
    "syosetu.com": SourcePolicyRecord(
        domain="syosetu.com",
        policy_class=SourcePolicyClass.POLICY_BLOCKED,
        evidence=(
            "Narou (syosetu.com) — trang chu HttpFetcher that tai duoc "
            "(HTTP 200), NHUNG chinh API chinh thuc cua ho (\"なろうデベロッパー"
            "\", dev.syosetu.com) cong khai liet ke hanh vi BI CAM: 'lay noi "
            "dung tieu thuyet mot cach may moc roi hien thi/tai xuong trong "
            "app hoac website'. Day la nguon RO RANG NHAT trong toan bo khao "
            "sat: chinh chu so huu tu noi qua API chinh thuc rang khong "
            "duoc tai xuat ban toan van, khong phai suy doan tu ToS chung "
            "chung."),
        verified_at="2026-08-31",
    ),
    "kakuyomu.jp": SourcePolicyRecord(
        domain="kakuyomu.jp",
        policy_class=SourcePolicyClass.TECHNICALLY_UNSTABLE,
        evidence=(
            "Trang chu tai duoc that (HTTP 200), nhung robots.txt CHAN "
            "DUNG duong dan doc chuong that: "
            "'/works/*/episodes/*/read$' — nghia la trang chu cho phep "
            "nhung noi dung chuong (thu that su can) bi chan rieng."),
        verified_at="2026-08-31",
    ),
}


def check_source_policy(url: str) -> Optional[SourcePolicyRecord]:
    """Tra ve `SourcePolicyRecord` neu domain cua `url` da duoc khao sat,
    `None` neu chua biet (KHONG suy doan — domain chua khao sat di qua
    duong discovery binh thuong nhu truoc)."""
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return _KNOWN_SOURCE_POLICIES.get(host)


def assert_source_not_blocked(url: str) -> None:
    """Nem `SourcePolicyBlockedError` NEU domain thuoc mot lop bi chan —
    goi o dau `discover()`/`confirm_unknown_source()`, TRUOC fetch/heuristic
    nao. Domain chua biet hoac hop le (FULL_TEXT_ALLOWED/METADATA_AND_
    LINK_ONLY/AUTH_REQUIRED) di qua binh thuong."""
    record = check_source_policy(url)
    if record is not None and record.policy_class in _BLOCKED_CLASSES:
        raise SourcePolicyBlockedError(
            f"{record.domain} đã được xác minh là {record.policy_class.value} "
            f"({record.verified_at}) — {record.evidence}")
