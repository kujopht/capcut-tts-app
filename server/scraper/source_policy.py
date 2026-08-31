"""
Chinh sach nguon fanfic anime/manga — ket qua NGHIEN CUU THAT (Anime Fanfic
Production Canary, xac minh 2026-08-31), khong phai suy doan.

MO HINH HAI TRUC (Owner Policy Update, 2026-08-31) — thay cho mot
`SourcePolicyClass` gop chung truoc do:

  `TechnicalAccess`  — nguon co TAI DUOC hay khong. La CONG THAT: mot domain
                       AUTH_REQUIRED/PAYWALLED/CAPTCHA_OR_BOT_CHALLENGE/
                       ACCESS_DENIED bi tu choi truoc ca khi fetch.
  `RightsRisk`       — quyen tai xuat ban noi dung co ro rang hay khong.
                       CHI LA SIEU DU LIEU tu quyet dinh 2026-08-31: "khong
                       dung quyen chua ro lam ly do chan nhap ky thuat nua".
                       KHONG BAO GIO la cong chan trong `assert_source_not_
                       blocked()`.

CO MOT CONG THU BA, DOC LAP VOI CA HAI TRUC TREN VA KHONG THAY DOI BOI
QUYET DINH 2026-08-31: `tos_prohibits_automation`. Quyet dinh do noi ro
"khong uy quyen: bo qua dang nhap/paywall/CAPTCHA/token/xoay vong danh
tinh de tranh chan" — mot dieu khoan dich vu CAM RO RANG viec truy cap tu
dong (spider/crawl/scrape, bat ke thu cong hay tu dong) la mot RANH GIOI
KY THUAT-TRUY-CAP cua BEN THU BA (nen tang luu tru), khong phai mot cau hoi
VE QUYEN NOI DUNG — chu so huu san pham khong co tham quyen chap nhan rui
ro thay cho quyen cua mot nen tang khac quyet dinh ai duoc phep goi vao no
bang may. Vi vay co ba nay VAN chan, du RightsRisk la gi.

VI SAO FILE NAY TON TAI: moi domain o day da duoc kiem tra TOAN VEN — doc
robots.txt/ToS THAT (khong chi tra loi tu tri nho huan luyen) VA thu fetch
THAT qua `server/scraper/http_fetcher.py::HttpFetcher` (chinh fetcher san
xuat, khong phai mot cong cu doc trang rieng biet co User-Agent/TLS khac).
Ket luan o day la MOT LAN, tranh cho agent/operator sau nay lap lai dung
nghien cuu da lam.

`check_source_policy()` duoc goi TRUOC bat ky discovery/fetch nao trong
`ScraperOpsService.discover()`/`start_or_continue()`/`confirm_unknown_
source()` — domain bi chan (ToS-cam-tu-dong-hoa HOAC TechnicalAccess
khong the vuot qua) bi tu choi NGAY, khong chay heuristic, khong gui mot
request nao ve domain do.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
from urllib.parse import urlsplit


class TechnicalAccess(str, Enum):
    PUBLIC_DIRECT = "public_direct"
    PUBLIC_API = "public_api"
    PUBLIC_BROWSER_RENDERED = "public_browser_rendered"
    AUTH_REQUIRED = "auth_required"
    PAYWALLED = "paywalled"
    CAPTCHA_OR_BOT_CHALLENGE = "captcha_or_bot_challenge"
    ACCESS_DENIED = "access_denied"


class RightsRisk(str, Enum):
    """SIEU DU LIEU — khong bao gio la dieu kien trong `assert_source_not_
    blocked()`. Ghi lai trung thuc de kiem duyet/doi soat sau nay, KHONG
    xoa/nguy trang de "cho qua"."""

    LOW = "low"
    UNKNOWN = "unknown"
    OWNER_ACCEPTED_UNVERIFIED = "owner_accepted_unverified"
    TAKEDOWN_REQUESTED = "takedown_requested"


#: TechnicalAccess KHONG the vuot qua duoc BAY GIO (can dang nhap/tra phi/
#: CAPTCHA that su, hoac da xac nhan bi tu choi thang). `PUBLIC_BROWSER_
#: RENDERED` CO CHU Y khong nam trong tap nay: trinh duyet thuong render
#: mot trang JS-only cong khai la hop le (khong phai "vuot qua" gi ca) —
#: xem docstring `TechnicalAccess`.
_BLOCKED_TECHNICAL_ACCESS = frozenset({
    TechnicalAccess.AUTH_REQUIRED,
    TechnicalAccess.PAYWALLED,
    TechnicalAccess.CAPTCHA_OR_BOT_CHALLENGE,
    TechnicalAccess.ACCESS_DENIED,
})


@dataclass(frozen=True)
class SourcePolicyRecord:
    domain: str
    technical_access: TechnicalAccess
    rights_risk: RightsRisk
    #: `True` = Dieu khoan dich vu (hoac dieu khoan API chinh thuc) CUA
    #: CHINH nen tang do CAM RO RANG truy cap tu dong — cong nay KHONG bi
    #: go boi quyet dinh "chu so huu chap nhan rui ro ban quyen", vi day la
    #: ranh gioi truy cap cua MOT BEN THU BA khac, khong phai cau hoi ve
    #: quyen so huu noi dung.
    tos_prohibits_automation: bool
    #: Bang chung THAT (trich dan ToS/robots.txt, ma HTTP that quan sat
    #: duoc) — khong phai "co ve nguy hiem".
    evidence: str
    verified_at: str  # ISO date, vd "2026-08-31"


class SourcePolicyBlockedError(Exception):
    """Domain da duoc XAC MINH khong the/khong duoc tu dong hoa BAY GIO —
    xem `SourcePolicyRecord.evidence` trong thong diep loi."""


#: HAT GIONG tu khao sat nguon anime/manga fanfic that (khong phai vi du) —
#: dang ky them qua registry nay khi co nghien cuu moi, KHONG hardcode ranh
#: gioi o noi khac.
_KNOWN_SOURCE_POLICIES: Dict[str, SourcePolicyRecord] = {
    "archiveofourown.org": SourcePolicyRecord(
        domain="archiveofourown.org",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "ToS/OTW cong khai: 'khong ngoai le... cho nguoi muon tao "
            "dataset', chu dong gioi han toc do/giam sat, da yeu cau Common "
            "Crawl ngung quet 2022 — cam tu dong hoa RO RANG, doc lap voi "
            "cau hoi quyen tac gia. THEM: `HttpFetcher` that (User-Agent tu "
            "nhan dang minh bach) nhan HTTP 403 tren ca trang ToS lan trang "
            "/tags/{fandom}/works — tu choi ky thuat THAT, khong chi ToS."),
        verified_at="2026-08-31",
    ),
    "fanfiction.net": SourcePolicyRecord(
        domain="fanfiction.net",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence=(
            "ToS THAT cho phep automation TOC DO NGUOI (khong cam tuyet "
            "doi), robots.txt Content-Signal=search=yes,ai-train=no,use="
            "reference. NHUNG `HttpFetcher` that nhan HTTP 403 tren mot "
            "trang truyen that (Ninja's Hero Academia, /s/13530962/...) — "
            "ha tang tu choi bot du ToS/robots.txt nghe co ve chap nhan, "
            "nen van khong the ke ca khi RightsRisk duoc chap nhan."),
        verified_at="2026-08-31",
    ),
    "wattpad.com": SourcePolicyRecord(
        domain="wattpad.com",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "ToS cam RO RANG, khong dieu kien: \"Don't use any kind of "
            "software, device or method (whether it's manual or automated) "
            "to 'crawl', 'spider' or otherwise remove any content\" — ap "
            "dung cho CA metadata, khong chi full-text."),
        verified_at="2026-08-31",
    ),
    "scribblehub.com": SourcePolicyRecord(
        domain="scribblehub.com",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence=("HTTP 403 tren CA robots.txt lan trang ToS — khong doc "
                  "duoc chinh sach that su, va ha tang tu choi fetch tu dong."),
        verified_at="2026-08-31",
    ),
    "royalroad.com": SourcePolicyRecord(
        domain="royalroad.com",
        technical_access=TechnicalAccess.PUBLIC_DIRECT,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "Domain nay DA nam san trong `site_registry.py` tu mot mission "
            "truoc (robots.txt cho phep tai lien ket chuong, nen da them "
            "vao) — nhung ToS (cap nhat 2025-03-03) cam RO RANG: 'use or "
            "launch any manual or automated system or software, devices, "
            "scripts robots, other means or processes to access, scrape, "
            "crawl, cache, spider any web page or other service contained "
            "in our Services'. robots.txt cho phep KHONG co nghia ToS cho "
            "phep. Van chan du sau Owner Policy Update 2026-08-31: day la "
            "ranh gioi truy cap CUA HO, khong phai cau hoi quyen noi dung."),
        verified_at="2026-08-31",
    ),
    "quotev.com": SourcePolicyRecord(
        domain="quotev.com",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence=("robots.txt cho phep, nhung `HttpFetcher` that nhan HTTP "
                  "200 voi than trang RONG (1 ky tu) tren trang chu VA trang "
                  "muc fanfiction — nghi la chan bot bang trang gia (than "
                  "trang rong khong phai loi tam thoi), coi la tu choi THAT."),
        verified_at="2026-08-31",
    ),
    "docln.net": SourcePolicyRecord(
        domain="docln.net",
        technical_access=TechnicalAccess.PUBLIC_BROWSER_RENDERED,
        rights_risk=RightsRisk.OWNER_ACCEPTED_UNVERIFIED,
        tos_prohibits_automation=False,
        evidence=(
            "SUA LAI LAN HAI sau khi thuc hien dung yeu cau kiem tra that "
            "cua chu san pham: mot phien trinh duyet that (mcp__claude-in- "
            "chrome__*), duong di nguoi doc thong thuong KHONG dang nhap, "
            "KHONG chen ma giai ma/trich khoa/bo qua CAPTCHA. Ket qua: JS "
            "GOC cua chinh docln.net tu giai ma chuoi XOR-shuffle va dat "
            "van ban that vao DOM cho MOI khach vang lai, KHONG co bat ky "
            "thu thach/CAPTCHA nao xuat hien — xac nhan qua "
            "docln_chuong_100.txt (van ban chuong that, tieng Viet, doc "
            "duoc hoan toan). KET LUAN TRUOC DO (CAPTCHA_OR_BOT_CHALLENGE, "
            "coi XOR-shuffle tuong duong bo bao ve ky thuat) la MOT LOI "
            "PHAN LOAI THAT: da nham lan 'noi dung bi bien doi trong HTML "
            "ban dau' voi 'kiem soat truy cap/thu thach bot' — day la Case "
            "1 (trinh duyet thuong render JS cong khai, hop le), khong "
            "phai Case 2. Day KHONG PHAI giai ma/tai hien co che ma hoa "
            "cua site — chi la doc lai DOM ma trinh duyet cua NGUOI DUNG "
            "THUONG da tu hien thi san, khong khac gi View Page Source sau "
            "khi JS chay xong. Vi vay dung T2 (browser-rendered) lam tang "
            "acquisition, KHONG tu giai ma XOR-shuffle trong ma nguon cua "
            "chung ta."),
        verified_at="2026-08-31",
    ),
    "forums.spacebattles.com": SourcePolicyRecord(
        domain="forums.spacebattles.com",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "Dien dan XenForo — ToS mac dinh cua XenForo (xac nhan nguyen "
            "van tren Questionable Questing, dien dan XenForo cung ho, xem "
            "muc rieng ben duoi) cam ro rang 'spidering, crawling, or "
            "scraping'; rat co the la CUNG mot dieu khoan boilerplate tu "
            "nha cung cap phan mem, chua xac minh truc tiep tung chu nhung "
            "suy luan hop ly tu cung nen tang. THEM: robots.txt cho phep "
            "(Content-Signal: search=yes,ai-train=no,use=reference — giong "
            "FFN/docln), nhung `HttpFetcher` that nhan HTTP 403 tren mot "
            "forum that (/forums/creative-writing.20/) — chan CA hai truc."),
        verified_at="2026-08-31",
    ),
    "syosetu.org": SourcePolicyRecord(
        domain="syosetu.org",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence=(
            "Hameln — HTTP 403 (khong phai 200-voi-than-rong nhu Quotev) "
            "tren ca robots.txt lan trang chu qua HttpFetcher that — day la "
            "tu choi RO RANG o tang HTTP (Case 2: ha tang chu dong tu choi "
            "truy cap tu dong), khong phai 'chi can trinh duyet render JS' "
            "(Case 1) — khong thu render trinh duyet vi 403 khong phai dau "
            "hieu cua noi dung JS-only, ma la tu choi thang."),
        verified_at="2026-08-31",
    ),
    "forums.sufficientvelocity.com": SourcePolicyRecord(
        domain="forums.sufficientvelocity.com",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "Dien dan XenForo cung ho voi SpaceBattles/Questionable "
            "Questing — cung suy luan ve ToS boilerplate 'spidering, "
            "crawling, or scraping'. THEM: robots.txt cho phep (cung "
            "Content-Signal voi SpaceBattles/FFN), nhung HttpFetcher that "
            "nhan HTTP 403 tren forum that (/forums/creative-writing.2/)."),
        verified_at="2026-08-31",
    ),
    "forum.questionablequesting.com": SourcePolicyRecord(
        domain="forum.questionablequesting.com",
        technical_access=TechnicalAccess.PUBLIC_DIRECT,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "KY THUAT tai duoc that (HttpFetcher nhan HTTP 200 tren "
            "/forums/creative-writing.5/) — nguon XenForo DUY NHAT khong bi "
            "403. NHUNG Terms and rules (forum.questionablequesting.com/"
            "help/terms/) cam RO RANG 'spamming, phishing, pharming, "
            "pretexting, spidering, crawling, or scraping' — dieu khoan "
            "truy cap cua ben thu ba, KHONG duoc go boi Owner Policy Update "
            "vi day khong phai cau hoi ve quyen noi dung. Van chan du "
            "TechnicalAccess la PUBLIC_DIRECT."),
        verified_at="2026-08-31",
    ),
    "metruyenchu.com": SourcePolicyRecord(
        domain="metruyenchu.com",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence="robots.txt cho phep hau het duong dan, nhung HttpFetcher that nhan HTTP 403 tren trang chu.",
        verified_at="2026-08-31",
    ),
    "truyenfull.today": SourcePolicyRecord(
        domain="truyenfull.today",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence=("Loi SSL handshake (UNEXPECTED_EOF_WHILE_READING) LAP LAI "
                  "qua hai lan thu that (khong phai loi tam thoi mot lan) — "
                  "nghi la chan o tang TLS/CDN, khong doc duoc noi dung."),
        verified_at="2026-08-31",
    ),
    "truyen.tangthuvien.vn": SourcePolicyRecord(
        domain="truyen.tangthuvien.vn",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence="HttpFetcher that: het thoi gian ket noi (timeout) lap lai — khong phan biet duoc la chan hay chi cham, coi la khong dung duoc BAY GIO.",
        verified_at="2026-08-31",
    ),
    "syosetu.com": SourcePolicyRecord(
        domain="syosetu.com",
        technical_access=TechnicalAccess.PUBLIC_DIRECT,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=True,
        evidence=(
            "Narou (syosetu.com) — trang chu HttpFetcher that tai duoc "
            "(HTTP 200), NHUNG chinh API chinh thuc cua ho (\"なろうデベロッパー"
            "\", dev.syosetu.com) cong khai liet ke hanh vi BI CAM: 'lay noi "
            "dung tieu thuyet mot cach may moc roi hien thi/tai xuong trong "
            "app hoac website'. Day la dieu khoan API CHINH THUC, ro rang "
            "hon ca mot dieu khoan ToS chung chung — chinh chu so huu tu "
            "noi qua kenh duoc uy quyen rang khong duoc tai xuat ban toan "
            "van. Van chan du TechnicalAccess la PUBLIC_DIRECT."),
        verified_at="2026-08-31",
    ),
    "kakuyomu.jp": SourcePolicyRecord(
        domain="kakuyomu.jp",
        technical_access=TechnicalAccess.ACCESS_DENIED,
        rights_risk=RightsRisk.UNKNOWN,
        tos_prohibits_automation=False,
        evidence=(
            "Trang chu tai duoc that (HTTP 200), nhung robots.txt CHAN "
            "DUNG duong dan doc chuong that: '/works/*/episodes/*/read$' — "
            "chinh trang can nhat (noi dung chuong) bi chan rieng bang "
            "robots.txt, du cac duong khac cho phep. Bo qua robots.txt "
            "tren dung duong dan nay la 'vuot qua kiem soat truy cap ky "
            "thuat ro rang' — khong lam."),
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
    """Nem `SourcePolicyBlockedError` NEU domain khong the/khong duoc tu
    dong hoa BAY GIO — goi o dau `discover()`/`start_or_continue()`/
    `confirm_unknown_source()`, TRUOC fetch/heuristic nao.

    HAI dieu kien chan, ca hai DOC LAP voi `rights_risk` (Owner Policy
    Update 2026-08-31: rui ro quyen la sieu du lieu, khong bao gio la dieu
    kien o day):
      1. `tos_prohibits_automation` — ranh gioi truy cap cua BEN THU BA,
         chu so huu san pham khong co tham quyen go bo.
      2. `technical_access` nam trong `_BLOCKED_TECHNICAL_ACCESS` — chua
         vuot qua duoc BAY GIO (dang nhap/tra phi/CAPTCHA that, hoac da xac
         nhan bi tu choi thang).

    Domain chua biet hoac vuot qua ca hai dieu kien tren di qua binh
    thuong."""
    record = check_source_policy(url)
    if record is None:
        return
    if record.tos_prohibits_automation:
        raise SourcePolicyBlockedError(
            f"{record.domain}: điều khoản dịch vụ/API chính thức cấm rõ "
            f"ràng truy cập tự động — đây là ranh giới truy cập của bên "
            f"thứ ba, không phải câu hỏi về quyền nội dung, nên không được "
            f"gỡ bởi chính sách chấp nhận rủi ro bản quyền ({record.verified_at}) "
            f"— {record.evidence}")
    if record.technical_access in _BLOCKED_TECHNICAL_ACCESS:
        raise SourcePolicyBlockedError(
            f"{record.domain}: technical_access={record.technical_access.value} "
            f"({record.verified_at}) — {record.evidence}")
