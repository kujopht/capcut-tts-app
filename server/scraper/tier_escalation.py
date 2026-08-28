"""
Phase 10 cua Story Harvester V3 — CHINH THUC HOA chinh sach nang tang xu
ly (Tier 0/1/2). Cay quyet dinh da duoc mo ta bang prose truoc do o
`server/scraper/__init__.py` (docstring module) va nhac lai trong
`discovery.py` (dong "KHONG tu dong chuyen sang trinh duyet (Tier 2)...
xem Phase 10") — module nay bien no thanh CODE THAT SU CO THE KIEM THU,
khong chi ghi chu cho nguoi doc.

HAI TRACH NHIEM RIENG BIET:

1. `classify_page_signal()` — doc MOT trang HTML, phan biet RO 5 ly do
   khac nhau khien Tier 0 khong trich duoc cau truc/noi dung mong doi:
   AUTH_REQUIRED, CAPTCHA, PAYWALL (BA thu nay la RANH GIOI AN TOAN
   CUNG — tuyet doi KHONG BAO GIO duoc dung lam ly do de nang tang, du
   Tier 1/2 co the ky thuat "vuot qua" duoc), NOT_FOUND (trang khong
   ton tai — nang tang khong giai quyet duoc van de nay), JS_REQUIRED
   (co the can Tier 2 trong tuong lai — CHUA TRIEN KHAI, xem
   `server/scraper/__init__.py`), va NO_STRUCTURE_MATCH (mau/selector
   khong khop du trang la cong khai/tinh — day la TRUONG HOP DUY NHAT
   nang tang THAT SU co the giup, vi du Tier 1 Scrapling adaptive
   relocation).

2. `decide_escalation()` — tu ly do phan loai o tren, tra ve MOT quyet
   dinh RO RANG: nang tang (va len tang nao), hay TU CHOI han (bao cao
   Tier 3 — thu cong, cho operator). KHONG BAO GIO co nhanh "thu
   CloakBrowser"/nguy trang chong phat hien trong tu vung quyet dinh
   cua module nay — CloakBrowser hoan toan khong duoc nhac toi o day
   co chu dich (xem `server/scraper/__init__.py` ve ly do van CHUA cai:
   can bang chung THAT tu MOT nguon cong khai cu the ma Playwright
   thuong khong vuot qua duoc, chua co nguon nao nhu vay duoc xac dinh).

CAP NHAT (P2, overnight hardening): `scrapling` GIO DA duoc cai that (xem
`server/requirements.txt`, `adapters/scrapling_relocation.is_scrapling_available()`
— tham do THAT qua try/import, KHONG gia dinh). LUU Y RANH GIOI: cac ham
CUA MODULE NAY (`classify_page_signal`/`decide_escalation`) VAN CHUA duoc
mot duong that nao goi truc tiep (van la chinh sach da CHINH THUC HOA
thanh code kiem thu duoc, chua noi day vao pipeline fetch-chuong that su
— xem docstring goc o tren). Rieng `scraper_ops_service.confirm_unknown_source`
(nhanh DEGRADED) dung MOT co che nang tang RIENG, cu the hon
(`scrapling_relocation.attempt_adaptive_relocation`, tu kiem tra
`is_scrapling_available()` truc tiep) KHONG di qua `decide_escalation()` —
hai co che nay giai quyet hai van de khac nhau (danh sach chuong/muc luc
vs vung noi dung mot chuong), xem docstring `scrapling_relocation.py`.
Nguyen tac KHONG DOI cho CHINH module nay: bat cu noi nao trong TUONG LAI
goi `decide_escalation` VOI `tier1_available=True` PHAI tu kiem tra kha
nang that truoc (khong hardcode `True`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List

from server.scraper.html_extract import extract

#: Cum tu THUONG GAP tren trang yeu cau dang nhap — TACH RIENG khoi
#: CAPTCHA/paywall (xem docstring module: ba pham tru nay deu la RANH
#: GIOI AN TOAN CUNG nhung duoc bao cao RIENG cho operator de ho biet
#: CHINH XAC dang gap loai chan nao, khong chi mot nhan "bi chan" chung
#: chung).
_AUTH_HINT_RE = re.compile(
    r"(đăng nhập để (đọc|xem)|vui lòng đăng nhập|please\s?log\s?in|"
    r"you must be logged in|sign in to continue|đăng nhập tài khoản)",
    re.IGNORECASE,
)
_CAPTCHA_HINT_RE = re.compile(
    r"(captcha|are you (a )?human|verify you are human|"
    r"checking your browser|cloudflare.{0,20}challenge|"
    r"xác minh bạn không phải (là )?robot)",
    re.IGNORECASE,
)
_PAYWALL_HINT_RE = re.compile(
    r"(subscribe to (read|continue)|trở thành hội viên|"
    r"nâng cấp (tài khoản|thành viên) để đọc|premium (content|chapter)|"
    r"mua (chương|gói) để đọc|unlock this chapter|upgrade to (read|premium)|"
    r"nội dung dành cho (hội viên|thành viên) vip)",
    re.IGNORECASE,
)
_NOT_FOUND_HINT_RE = re.compile(
    r"(trang không tồn tại|page not found|404 not found|"
    r"không tìm thấy (trang|nội dung)|content (has been )?removed)",
    re.IGNORECASE,
)
_JS_REQUIRED_HINT_RE = re.compile(
    r"(please enable javascript|enable javascript to continue|"
    r"requires javascript|javascript is required|"
    r"bật javascript để (xem|tiếp tục))",
    re.IGNORECASE,
)

#: Duoi nguong nay (ky tu van ban hien thi), MOT trang gan nhu trong duoc
#: coi la ung vien "can JavaScript de render" NEU CO them cum tu goi y
#: (xem `classify_page_signal`) — chi rieng it van ban KHONG DU, vi mot
#: trang loi/tam thoi trong cung co the ngan nhu vay ma khong lien quan
#: JavaScript.
_NGUONG_VAN_BAN_QUA_NGAN_CHO_JS = 100


class TierFailureReason(Enum):
    #: Mau href/CSS khong khop URL/vung noi dung nao tren mot trang CONG
    #: KHAI, tinh — day la TRUONG HOP DUY NHAT nang tang THAT SU giup ich.
    NO_STRUCTURE_MATCH = "no_structure_match"
    AUTH_REQUIRED = "auth_required"
    CAPTCHA = "captcha"
    PAYWALL = "paywall"
    NOT_FOUND = "not_found"
    JS_REQUIRED = "js_required"


class EscalationDecision(Enum):
    #: Thu nang len Tier 1 (Scrapling adaptive relocation) — CHI khi
    #: `tier1_available=True` VA ly do la NO_STRUCTURE_MATCH.
    ESCALATE_TIER_1 = "escalate_tier_1"
    #: BAO CAO cho operator la co the can Tier 2 (trinh duyet render) —
    #: KHONG tu dong thuc hien gi (Tier 2 CHUA TRIEN KHAI, xem docstring
    #: module `server/scraper/__init__.py`).
    REPORT_NEEDS_TIER_2 = "report_needs_tier_2"
    #: TU CHOI han — bao Tier 3 (thu cong) cho operator, KHONG nang tang
    #: nao ca. Dung cho CA hai truong hop: (a) RANH GIOI AN TOAN CUNG
    #: (auth/captcha/paywall — nang tang se KHONG BAO GIO duoc dung de
    #: "vuot qua" nhung thu nay), (b) khong con lua chon nao khac (trang
    #: khong ton tai, hoac Tier 1 khong san sang trong moi truong nay).
    REFUSE_MANUAL_REQUIRED = "refuse_manual_required"


@dataclass(frozen=True)
class EscalationResult:
    decision: EscalationDecision
    reason: TierFailureReason
    evidence: str


#: BA ly do nay la RANH GIOI AN TOAN CUNG — `decide_escalation` PHAI tra
#: ve `REFUSE_MANUAL_REQUIRED` cho CA BA, KHONG co truong hop ngoai le
#: nao (khong co tham so nao "bat qua" duoc kiem tra nay).
_BLOCKED_REASONS = frozenset({
    TierFailureReason.AUTH_REQUIRED,
    TierFailureReason.CAPTCHA,
    TierFailureReason.PAYWALL,
})


def classify_page_signal(raw_html: str) -> TierFailureReason:
    """Phan loai LY DO Tier 0 khong trich duoc cau truc/noi dung mong doi
    tu MOT trang HTML — xem thu tu uu tien trong docstring module (CAPTCHA/
    AUTH/PAYWALL/NOT_FOUND kiem truoc, vi cum tu cua chung CU THE hon va
    it co kha nang trung voi noi dung chuong that su hop phap so voi cum
    tu JS_REQUIRED chung chung hon). Mac dinh `NO_STRUCTURE_MATCH` neu
    khong tin hieu nao khop — day la GIA DINH AN TOAN nhat trong so cac
    nhan: no dan den escalate (co the giup) thay vi tu choi oan mot nguon
    cong khai binh thuong chi vi mau href chua duoc cau hinh dung."""
    text = extract(raw_html).visible_text()
    if _CAPTCHA_HINT_RE.search(text):
        return TierFailureReason.CAPTCHA
    if _AUTH_HINT_RE.search(text):
        return TierFailureReason.AUTH_REQUIRED
    if _PAYWALL_HINT_RE.search(text):
        return TierFailureReason.PAYWALL
    if _NOT_FOUND_HINT_RE.search(text):
        return TierFailureReason.NOT_FOUND
    if (len(text.strip()) < _NGUONG_VAN_BAN_QUA_NGAN_CHO_JS
            and _JS_REQUIRED_HINT_RE.search(text)):
        return TierFailureReason.JS_REQUIRED
    return TierFailureReason.NO_STRUCTURE_MATCH


def decide_escalation(reason: TierFailureReason, *,
                       tier1_available: bool = False) -> EscalationResult:
    """Tu MOT ly do da phan loai, tra ve quyet dinh nang tang RO RANG.
    `tier1_available` PHAI duoc noi goi tu kiem tra (vd `try/except
    ImportError` tren `scrapling`) — KHONG BAO GIO gia dinh True, mac
    dinh tham so la False dung theo trang thai THAT cua moi truong nay."""
    if reason in _BLOCKED_REASONS:
        return EscalationResult(
            decision=EscalationDecision.REFUSE_MANUAL_REQUIRED,
            reason=reason,
            evidence=(
                f"Phát hiện dấu hiệu {reason.value} — KHÔNG BAO GIỜ nâng "
                "tầng xử lý để vượt qua đăng nhập/CAPTCHA/paywall, dù về "
                "mặt kỹ thuật Tier 1/2 có thể làm được. Đây là ranh giới "
                "an toàn cứng, báo Tier 3 (thủ công) cho kỹ sư."),
        )
    if reason == TierFailureReason.NOT_FOUND:
        return EscalationResult(
            decision=EscalationDecision.REFUSE_MANUAL_REQUIRED,
            reason=reason,
            evidence=(
                "Trang không tồn tại (404/đã gỡ) — nâng tầng xử lý không "
                "giải quyết được vấn đề này, đây không phải lỗi trích "
                "xuất. Báo Tier 3 (thủ công) cho kỹ sư."),
        )
    if reason == TierFailureReason.JS_REQUIRED:
        return EscalationResult(
            decision=EscalationDecision.REPORT_NEEDS_TIER_2,
            reason=reason,
            evidence=(
                "Nội dung dường như cần JavaScript để render — Tier 1 "
                "(Scrapling bản phân tích HTML tĩnh) cũng không giải "
                "quyết được vấn đề này. Cần Tier 2 (trình duyệt render, "
                "CHƯA TRIỂN KHAI) — chỉ báo cáo cho kỹ sư, KHÔNG tự động "
                "thử bất kỳ điều gì thêm (xem Phase 10, "
                "server/scraper/__init__.py)."),
        )
    # NO_STRUCTURE_MATCH — TRUONG HOP DUY NHAT nang tang THAT SU giup ich.
    if tier1_available:
        return EscalationResult(
            decision=EscalationDecision.ESCALATE_TIER_1,
            reason=reason,
            evidence=(
                "Mẫu href/CSS không khớp trên một trang công khai, tĩnh — "
                "có thể site đã đổi cấu trúc. Tier 1 (Scrapling adaptive "
                "relocation) khả dụng trong môi trường này, thử định vị "
                "lại trước khi báo thất bại."),
        )
    return EscalationResult(
        decision=EscalationDecision.REFUSE_MANUAL_REQUIRED,
        reason=reason,
        evidence=(
            "Mẫu href/CSS không khớp, và Tier 1 (Scrapling) KHÔNG khả "
            "dụng trong môi trường này (gói package chưa được cài) — báo "
            "Tier 3 (thủ công, cần kỹ sư cấu hình lại site_registry) cho "
            "kỹ sư."),
    )
