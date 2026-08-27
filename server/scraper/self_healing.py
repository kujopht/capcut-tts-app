"""
Tu-chua selector (self-healing) — Phase 5 cua Story Harvester V3.

LUONG (theo dung yeu cau Phase 5): fingerprint/selector CU (SiteProfile
da xac minh) ngung khop -> UNG VIEN thay the (adaptive relocation) ->
KIEM TRA CAU TRUC -> chap nhan (ghi revision) / can duyet / that bai an toan.

CO Y GIOI HAN MOI TRUONG (trung thuc, khong phong dai): `scrapling`
(package Tier 1) KHONG duoc cai trong moi truong nay (xem
`adapters/scrapling_adapter.py` — DEAD/UNUSED, xac nhan qua audit Phase 1
cua Story Harvester V3). Module nay xay dung + KIEM THU DAY DU phan
"KIEM TRA CAU TRUC" (buoc quyet dinh co CHAP NHAN mot ung vien thay the
hay khong) — day la phan CO THE xac minh doc lap voi Scrapling, vi no chi
can MOT chuoi HTML ung vien, khong can chinh Scrapling tim ra ung vien do
nhu the nao. Phan "TIM ung vien tu dong qua Scrapling" (adaptive
relocation THAT SU) KHONG duoc noi day trong PR nay — chua co bang chung
(Phase 12 chua chay) rang Scrapling can thiet, va khong the kiem thu that
neu khong cai duoc thu vien.

TAI SU DUNG `content_extraction.extract_content_v3` (Phase 6) lam tin
hieu CO SO (do dai/mat do doan van/lien quan tieu de deu da tinh o do) —
THEM HAI kiem tra rieng cua Phase 5 ma content_extraction.py KHONG co:
(1) khong duoc TRUNG HET voi chuong TRUOC DO trong series (dau hieu
selector dang lay lai noi dung CU/tinh thay vi chuong MOI), (2) khong
giong trang dang nhap/loi/tu choi truy cap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from server.scraper.content_extraction import ExtractionConfidence, extract_content_v3
from server.scraper.dedupe import content_hash

#: Cum tu THUONG GAP tren trang dang nhap/loi/tu choi truy cap — CO Y
#: NGAN, "chac chan la" hon la co gang doan MOI bien the co the co (cung
#: triet ly voi `quality._NAV_PHRASES`).
#:
#: THEM cum tu loi may chu/xin loi CHUNG CHUNG (Phase 3 "profile poisoning
#: red team", phat hien qua fixture "trang loi dai giong bai viet that" —
#: mot trang loi 500/bao tri duoc viet THAN THIEN, nhieu doan van, boc
#: trong <article> that su tung dat HIGH confidence o CA content_extraction_v3
#: LAN self_healing truoc ban sua nay, vi cac cum tu cu (dang nhap/404)
#: khong khop): cac cum tu nay CO Y mang giong "van ban ho tro ky thuat"
#: (vd "da xay ra su co", "internal server error", "lien he ho tro") —
#: it co kha nang xuat hien tu nhien trong doi thoai/van xuoi tieu thuyet
#: that su, khac voi cac tu dan chung "loi"/"su co" don le co the xuat
#: hien trong noi dung chuong hop phap.
_LOGIN_OR_ERROR_HINT_RE = re.compile(
    r"(đăng nhập để (đọc|xem)|vui lòng đăng nhập|please log ?in|"
    r"you must be logged in|access denied|forbidden|"
    r"trang không tồn tại|page not found|404 not found|"
    r"không có quyền truy cập|nội dung không khả dụng|"
    r"đã xảy ra (một )?(lỗi|sự cố)|something went wrong|"
    r"an error (has )?occurred|internal server error|"
    r"service (temporarily )?unavailable|503 service unavailable|"
    r"hệ thống (đang|tạm thời) (bảo trì|gặp sự cố|quá tải)|"
    r"(please |vui lòng )?(try again later|thử lại sau (vài|ít) phút)|"
    r"liên hệ (bộ phận )?hỗ trợ khách hàng|contact (customer )?support)",
    re.IGNORECASE,
)


class RelocationConfidence(Enum):
    #: Ung vien dang tin cay — chap nhan, ghi revision SiteProfile MOI.
    HIGH = "high"
    #: Khong chac chan — gui hang doi duyet, KHONG tu dong chap nhan.
    MEDIUM = "medium"
    #: That bai an toan — TU CHOI ung vien, KHONG ghi de SiteProfile.
    LOW = "low"


@dataclass
class RelocationValidationResult:
    confidence: RelocationConfidence
    evidence: List[str] = field(default_factory=list)
    clean_text: str = ""
    is_duplicate_of_previous_chapter: bool = False
    looks_like_login_or_error_page: bool = False


#: Anh xa tu confidence trich xuat noi dung (Phase 6) sang confidence tu-
#: chua (Phase 5) — CUNG thang do (HIGH/MEDIUM/LOW), tai su dung truc
#: tiep vi ca hai deu tra loi cung mot cau hoi cot loi: "day co phai vung
#: noi dung chuong THAT hay khong".
_ANH_XA_CONFIDENCE = {
    ExtractionConfidence.HIGH: RelocationConfidence.HIGH,
    ExtractionConfidence.MEDIUM: RelocationConfidence.MEDIUM,
    ExtractionConfidence.LOW: RelocationConfidence.LOW,
}


def validate_relocated_content(
        raw_html: str, *, chapter_title: Optional[str] = None,
        previous_chapter_content_hash: Optional[str] = None,
) -> RelocationValidationResult:
    """Kiem tra CAU TRUC mot ung vien thay the — xem docstring module.
    KHONG BAO GIO tang confidence len HIGH chi vi trich xuat duoc nhieu
    van ban; hai kiem tra THEM cua Phase 5 (trung chuong truoc/trang dang
    nhap) CHI co the HA confidence, khong bao gio nang len."""
    ket_qua_v3 = extract_content_v3(raw_html, chapter_title=chapter_title)
    confidence = _ANH_XA_CONFIDENCE[ket_qua_v3.confidence]
    evidence = [
        f"Điểm tin cậy trích xuất nội dung (Phase 6): {ket_qua_v3.confidence.value} "
        f"(vùng nội dung: {ket_qua_v3.container_signature or 'không xác định'})."
    ]

    is_dup = False
    if previous_chapter_content_hash and ket_qua_v3.clean_text:
        if content_hash(ket_qua_v3.clean_text) == previous_chapter_content_hash:
            is_dup = True
            confidence = RelocationConfidence.LOW
            evidence.append(
                "Nội dung TRÙNG HỆT với chương TRƯỚC ĐÓ trong series — dấu "
                "hiệu bộ chọn (selector) đang lấy lại nội dung cũ/tĩnh "
                "thay vì nội dung của chương mới. Từ chối an toàn.")

    looks_login = bool(_LOGIN_OR_ERROR_HINT_RE.search(ket_qua_v3.clean_text))
    if looks_login:
        confidence = RelocationConfidence.LOW
        evidence.append(
            "Nội dung trích xuất được giống trang đăng nhập/lỗi/từ chối "
            "truy cập — không phải nội dung chương thật. Từ chối an toàn.")

    return RelocationValidationResult(
        confidence=confidence, evidence=evidence, clean_text=ket_qua_v3.clean_text,
        is_duplicate_of_previous_chapter=is_dup, looks_like_login_or_error_page=looks_login)
