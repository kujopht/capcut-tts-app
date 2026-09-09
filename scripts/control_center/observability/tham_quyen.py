"""BẬC THẨM QUYỀN — nguồn nào được quyền trả lời câu hỏi nào.

Đây là phần sửa lỗi đúng đắn của V0.5, viết thành mã thay vì thành lời
nhắc. Bốn bậc, cao xuống thấp:

    1. LIVE            — vừa đo từ hệ thống thật
    2. KHO/BỀN         — kho git + sổ SQLite ở hiện tại
    3. KÝ ỨC/LỊCH SỬ   — sự kiện đã ghi, ảnh chụp cũ
    4. SUY LUẬN LLM    — model tự đoán

LUẬT KHÔNG ĐƯỢC PHÁ: khi câu hỏi là về HIỆN TẠI và có một probe LIVE cho
thứ được hỏi, thì bậc 3 và bậc 4 KHÔNG được dùng để trả lời. Đó chính là
đường đã dẫn tới câu sai:

    "production farmer còn chạy không?"
    -> Router có 0 việc  (bậc 2, và là về MỘT THỨ KHÁC)
    -> model suy ra "không có gì chạy"  (bậc 4)
    -> sai, vì `fanfic-farmer` đang chạy trên AWS.

Chú ý cái bẫy ở giữa: bậc 2 KHÔNG sai — Router thật sự có 0 việc. Cái
sai là dùng nó để trả lời một câu hỏi về hệ thống khác. Nên bậc thẩm
quyền phải xét theo TỪNG THỨ ĐƯỢC HỎI, không phải theo độ tin của nguồn.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import List, Sequence


class Bac(IntEnum):
    LIVE = 1
    KHO = 2
    KY_UC = 3
    SUY_LUAN = 4


#: Dau hieu cau hoi ve HIEN TAI. Tieng Viet truoc, vi do la ngon ngu
#: nguoi dung dung; kem vai dang tieng Anh hay gap.
#:
#: KHONG dat mot mau rieng cho "farmer" hay "fanfic": lop nay phai dung
#: cho moi du an, va mot mau ghim ten mot du an la dung cai V0.5 phai
#: tranh. Nhung mau duoi day noi ve THI (dang/con/roi/chua) va ve
#: SUC KHOE (song/khoe/chay), khong ve mot he thong cu the nao.
_MAU_HIEN_TAI = (
    r"\bđang\b", r"\bcòn\b.*\b(chạy|sống|hoạt động|bật)\b",
    r"\b(chạy|sống|hoạt động)\b.*\b(không|ko)\b",
    r"\bhiện (tại|nay|giờ)\b", r"\bbây giờ\b", r"\blúc này\b",
    r"\btới đâu\b", r"\bđến đâu\b", r"\bbao nhiêu rồi\b",
    r"\bxong (chưa|rồi)\b", r"\b(chưa|rồi) xong\b",
    r"\bhealthy\b", r"\balive\b", r"\bstatus\b", r"\bup\b\?",
    r"\bis .* (running|alive|up|healthy)\b",
    r"\b(running|alive|healthy)\b.*\?",
    r"\bcòn\b.*\?", r"\bthế nào\b", r"\bra sao\b",
    r"\bkiểm tra\b", r"\bcheck\b",
)

#: Dau hieu cau hoi ve LICH SU — duoc phep dung ky uc/su kien da ghi.
_MAU_LICH_SU = (
    r"\bhôm qua\b", r"\btuần trước\b", r"\btháng trước\b",
    r"\bđã từng\b", r"\blần trước\b", r"\btrước đây\b",
    r"\blịch sử\b", r"\byesterday\b", r"\blast (week|month|time)\b",
    r"\bđêm qua\b",
)

_HIEN_TAI = [re.compile(m, re.I) for m in _MAU_HIEN_TAI]
_LICH_SU = [re.compile(m, re.I) for m in _MAU_LICH_SU]


@dataclass
class YeuCauBangChung:
    """Kết luận: câu hỏi này cần bằng chứng ở bậc nào."""

    can_live: bool
    la_lich_su: bool
    dau_hieu: List[str]

    @property
    def bac_toi_thieu(self) -> Bac:
        return Bac.LIVE if self.can_live else Bac.KY_UC

    def to_dict(self) -> dict:
        return {"can_live": self.can_live, "la_lich_su": self.la_lich_su,
                "dau_hieu": list(self.dau_hieu),
                "bac_toi_thieu": int(self.bac_toi_thieu)}


def xet_cau_hoi(van_ban: str) -> YeuCauBangChung:
    """Câu này có đòi trạng thái SỐNG không?

    Cố tình NGHIÊNG VỀ PHÍA ĐI ĐO. Một lần probe thừa tốn vài giây; một
    câu trả lời sai về việc production còn chạy hay không thì tốn niềm
    tin, và đó là cái giá đã phải trả một lần rồi.
    """
    van = (van_ban or "").strip()
    dau: List[str] = []
    for r in _HIEN_TAI:
        if r.search(van):
            dau.append(r.pattern)
    ls = [r.pattern for r in _LICH_SU if r.search(van)]
    # Cau vua co dau hieu hien tai vua co moc thoi gian qua khu ("hom qua
    # farm tới đâu") -> uu tien LICH SU: nguoi dung hoi ve mot moc da qua,
    # va mot phep do BAY GIO khong tra loi duoc cau do.
    can_live = bool(dau) and not ls
    return YeuCauBangChung(can_live=can_live, la_lich_su=bool(ls),
                           dau_hieu=dau + [f"(lịch sử) {x}" for x in ls])


def cau_tu_choi_bia(so_viec_router: int, ly_do: Sequence[str]) -> str:
    """Câu Leader PHẢI nói khi probe live không ra kết quả.

    Hình dạng của câu này là một yêu cầu, không phải một gợi ý: nó phải
    (a) nói rõ Router đang thấy gì, (b) nói rõ mình CHƯA xác minh được hệ
    thống bên ngoài, (c) nói lý do. Ba phần đó là thứ ngăn "Router = 0"
    biến thành "production đã dừng".
    """
    vi = "; ".join(x for x in ly_do if x) or "không rõ nguyên nhân"
    return (f"Router tasks hiện tại = {so_viec_router}, nhưng tôi CHƯA xác "
            f"minh được trạng thái dịch vụ bên ngoài vì live probe không "
            f"thành công: {vi}. Router rảnh KHÔNG có nghĩa là dịch vụ ngoài "
            f"đã dừng — hai thứ đó độc lập.")
