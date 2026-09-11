"""NỐI "ok làm đi" VỀ ĐÚNG ĐỀ XUẤT TRƯỚC ĐÓ — V0.9, §1.

BẤT BIẾN §2 CỦA V0.8 GIỮ NGUYÊN, và tệp này tồn tại để giữ nó chứ không phải
để nới nó: một đề xuất của Strategist KHÔNG tự thành việc. Chỉ câu NGƯỜI DÙNG
xin làm mới mở cửa. Thứ v0.9 thêm là: người dùng không phải nhắc lại cả kế
hoạch. "ok làm đi" phải nối được về đúng lời khuyên vừa rồi.

TẤT ĐỊNH, KHÔNG LLM. Hai lý do, và cả hai đã trả giá trong kho này:

* Hỏi model "câu này có phải xin làm không?" là thêm một lượt model vào MỌI
  tin nhắn — đúng thứ `phan_loai.py` của v0.8 tồn tại để tránh.
* Một model có thể trả lời "có" cho một câu không phải xin làm, và lúc đó ta
  tự tạo ra đúng đường mà §1 cấm. Một biểu thức chính quy sai thì sai theo
  cách đọc được và sửa được.

VÀ MỘT ĐIỀU NỮA, quan trọng hơn cả hai: **văn bản đi vào ngữ cảnh Leader
không hoàn toàn do người dùng viết** (tóm tắt worker, câu commit — xem
`leader.HANH_DONG_TU_CHAY`). Nên bộ dò này chỉ được chạy trên ĐÚNG chuỗi
người dùng gõ, và `giai_quyet()` đòi `nguon="user"`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


def _c(*mau: str) -> Tuple[re.Pattern, ...]:
    return tuple(re.compile(m, re.I) for m in mau)


#: XIN LÀM — câu mở cửa thực thi. Cố ý ngắn và cụ thể.
#:
#: `\bok\b` một mình KHÔNG đủ: "ok mình hiểu rồi" không phải một lệnh. Nên
#: mọi mẫu đều đòi một ĐỘNG TỪ hành động, hoặc "ok" đi kèm động từ đó.
_XIN_LAM = _c(
    r"\b(?:ok|okay|oke|uk|ừ|u)\b[\s,]*(?:thì\s+)?(?:m(?:ày)?\s+|bro\s+)?"
    r"(?:cứ\s+)?(?:làm|lam|triển|trien|chạy|chay|bắt tay|bat tay|tiến hành|"
    r"tien hanh|làm luôn|go)\b",
    r"\b(?:làm|lam)\s+(?:đi|di|luôn|luon|ngay|thử|thu)\b",
    r"\b(?:triển khai|trien khai|triển|trien)\b(?!\s+khai\s+nào)",
    r"\b(?:tiến hành|tien hanh|bắt tay vào|bat tay vao)\b",
    r"\b(?:fix|sửa|sua)\s+(?:cái\s+này|cai\s+nay|nó|no|luôn|luon|giúp|giup)\b",
    r"\b(?:build|dựng|dung)\s+(?:feature|tính năng|tinh nang)\b",
    r"\b(?:implement|thực thi|thuc thi)\s+(?:it|that|nó|no|cái đó|cai do)\b",
    r"\b(?:go ahead|do it|let'?s do it|make it so|ship it)\b",
    r"\bcho\s+(?:chạy|chay|làm|lam)\s+(?:đi|di|luôn|luon)\b",
)

#: THAM CHIẾU về một đề xuất trước đó. Không bắt buộc — "ok làm đi" trống
#: vẫn nối về đề xuất mới nhất — nhưng khi có thì nó thu hẹp phạm vi.
_THAM_CHIEU = _c(
    r"\b(?:hướng|huong|cách|cach|phương án|phuong an|đề xuất|de xuat|"
    r"kế hoạch|ke hoach|ý|y)\s+(?:đó|do|này|nay|trên|tren|vừa rồi|vua roi)\b",
    r"\b(?:như|nhu)\s+(?:m|mày|may|bro|bạn|ban)\s+(?:nói|noi|bảo|bao|đề xuất|de xuat)\b",
    r"\b(?:that|the)\s+(?:plan|approach|recommendation|option)\b",
    r"\b(?:cái|cai)\s+(?:đó|do|vừa nói|vua noi)\b",
)

#: THU HẸP PHẠM VI — "chỉ phần repo-local thôi", "phần X đó". Bắt được thì ý
#: định mang `pham_vi_noi_ro` và kế hoạch bị cắt theo. Bỏ lọt thì không sao:
#: kế hoạch đầy đủ vẫn đi qua cổng thẩm quyền như thường.
_PHAM_VI = _c(
    r"\b(?:phần|phan)\s+([a-z0-9 \-_/\.]{2,40}?)\s*(?:đó|do|này|nay|thôi|thoi|đi|di)\b",
    r"\b(?:chỉ|chi|only)\s+(?:phần|phan|the)?\s*([a-z0-9 \-_/\.]{2,40}?)\s*"
    r"(?:thôi|thoi|đi|di|part)\b",
    r"\b(repo[\s-]?local|read[\s-]?only|chỉ đọc|chi doc)\b",
)

#: HOÃN / TỪ CHỐI. Kiểm TRƯỚC `_XIN_LAM`: "khoan làm đã" chứa "làm đ…" và sẽ
#: khớp mẫu xin làm nếu không chặn trước. Đây là một lỗi thật dễ mắc, và hậu
#: quả của nó là khởi động một lần thực thi mà người dùng vừa bảo đừng.
_HOAN = _c(
    # Cho phép tối đa 2 từ chen giữa: "khoan LÀM đã", "đợi MỘT CHÚT đã". Đòi
    # hai từ dính nhau thì "khoan làm đã" — đúng dạng người ta gõ — lọt qua
    # và rơi thẳng vào `_XIN_LAM` vì nó chứa "làm đ…". Đã vấp thật ở bài kiểm.
    r"\b(?:khoan|đợi|doi|chờ)\b(?:\s+\w+){0,2}\s+(?:đã|da|chút|chut|tí|ti)\b",
    r"^\s*(?:khoan|đợi|chờ)\b",
    r"\b(?:chưa|chua|đừng|dung|không|khong|kg|ko)\s+(?:làm|lam|triển|trien|"
    r"chạy|chay|vội|voi)\b",
    r"\b(?:hold on|not yet|wait|don'?t)\b",
    r"\bđể\s+(?:sau|lát|lat)\b",
)


@dataclass(frozen=True)
class TinHieuTiepNoi:
    """Kết quả dò trên MỘT câu người dùng."""

    la_tiep_noi: bool = False
    dau_hieu: Tuple[str, ...] = ()
    co_tham_chieu: bool = False
    pham_vi_noi_ro: str = ""
    bi_hoan: bool = False

    def to_dict(self) -> Dict:
        return {"la_tiep_noi": self.la_tiep_noi,
                "dau_hieu": list(self.dau_hieu),
                "co_tham_chieu": self.co_tham_chieu,
                "pham_vi_noi_ro": self.pham_vi_noi_ro,
                "bi_hoan": self.bi_hoan}


def _bat(mau: Tuple[re.Pattern, ...], van: str) -> List[str]:
    ra: List[str] = []
    for m in mau:
        x = m.search(van)
        if x:
            ra.append(x.group(0).strip()[:60])
    return ra


def xet_tiep_noi(cau: str) -> TinHieuTiepNoi:
    """Câu người dùng -> tín hiệu. Tất định, vài chục micro-giây."""
    van = str(cau or "").strip()
    if not van:
        return TinHieuTiepNoi()
    hoan = _bat(_HOAN, van)
    if hoan:
        # HOAN THANG. Xem chu thich cua `_HOAN`.
        return TinHieuTiepNoi(la_tiep_noi=False, dau_hieu=tuple(hoan),
                              bi_hoan=True)
    lam = _bat(_XIN_LAM, van)
    if not lam:
        return TinHieuTiepNoi()
    tc = bool(_bat(_THAM_CHIEU, van))
    pv = ""
    for m in _PHAM_VI:
        x = m.search(van)
        if x:
            pv = (x.group(x.lastindex or 0) or "").strip()
            if pv:
                break
    return TinHieuTiepNoi(la_tiep_noi=True, dau_hieu=tuple(lam),
                          co_tham_chieu=tc, pham_vi_noi_ro=pv[:60])


# ------------------------------------------------------------- de xuat ----

@dataclass
class DeXuat:
    """Một ĐỀ XUẤT đã nói ra trong hội thoại — thứ "ok làm đi" trỏ về.

    Lưu vì §1: người dùng không phải nhắc lại kế hoạch. Không lưu thì câu
    tiếp nối chỉ còn hai chữ và Leader phải đoán — đúng thứ vòng kín tồn tại
    để bỏ đi.

    `tu_vai` phân biệt lời khuyên của Strategist với câu Leader tự nói. Nó đi
    vào nguồn gốc của ý định, nên câu hỏi "ai đề xuất việc này?" trả lời
    được sau nhiều tuần.
    """

    ma: str
    project_id: str
    message_id: int
    tom_tat: str
    cac_buoc: Tuple[str, ...] = ()
    rui_ro: str = "LOW"
    tac_dong_production: bool = False
    tu_vai: str = "strategist"
    execution_id: str = ""
    ts: float = field(default_factory=time.time)

    @property
    def da_dung(self) -> bool:
        return bool(self.execution_id)

    def to_dict(self) -> Dict:
        return {"ma": self.ma, "project_id": self.project_id,
                "message_id": self.message_id, "tom_tat": self.tom_tat,
                "cac_buoc": list(self.cac_buoc), "rui_ro": self.rui_ro,
                "tac_dong_production": self.tac_dong_production,
                "tu_vai": self.tu_vai, "execution_id": self.execution_id,
                "da_dung": self.da_dung, "ts": self.ts}


@dataclass(frozen=True)
class KetNoi:
    """Kết quả nối: đề xuất nào, vì sao, và mục tiêu rút ra được."""

    de_xuat: Optional[DeXuat]
    muc_tieu: str
    ly_do: str
    tin_hieu: TinHieuTiepNoi

    @property
    def noi_duoc(self) -> bool:
        return self.de_xuat is not None

    def to_dict(self) -> Dict:
        return {"noi_duoc": self.noi_duoc,
                "de_xuat": (self.de_xuat.to_dict() if self.de_xuat else None),
                "muc_tieu": self.muc_tieu, "ly_do": self.ly_do,
                "tin_hieu": self.tin_hieu.to_dict()}


#: Đề xuất cũ hơn ngần này thì KHÔNG nối nữa. Một "ok làm đi" gõ ba ngày sau
#: một lời khuyên gần như chắc chắn nói về chuyện khác.
HAN_NOI_GIAY = 24 * 3600.0


def giai_quyet(cau: str, de_xuat: Sequence[DeXuat], *,
               nguon: str = "user", now: Optional[float] = None) -> KetNoi:
    """Nối câu tiếp nối về đề xuất MỚI NHẤT còn hạn và CHƯA được dùng.

    `nguon` phải là `"user"`. Gọi với nguồn khác trả về không-nối-được, và
    đó là rào chính của tệp này: một tóm tắt worker có chữ "ok làm đi" trong
    đó KHÔNG được khởi động gì.

    "Chưa được dùng" (`execution_id` rỗng) chặn một lớp lỗi thật: người dùng
    gõ "ok làm đi" hai lần vì lần đầu chậm, và ta tạo hai lần thực thi cho
    cùng một lời khuyên. Bản thứ hai nối về đề xuất KẾ TIẾP nếu có, hoặc
    không nối — chứ không nhân đôi.
    """
    th = xet_tiep_noi(cau)
    if nguon != "user":
        return KetNoi(None, "", "văn bản không do người dùng gõ — không nối",
                      TinHieuTiepNoi())
    if not th.la_tiep_noi:
        return KetNoi(None, "", ("người dùng hoãn" if th.bi_hoan
                                 else "không phải câu tiếp nối"), th)
    t = time.time() if now is None else now
    ung = [d for d in de_xuat
           if not d.da_dung and (t - d.ts) <= HAN_NOI_GIAY]
    if not ung:
        return KetNoi(None, "", ("không có đề xuất nào chưa dùng trong "
                                 f"{int(HAN_NOI_GIAY // 3600)} giờ qua"), th)
    d = max(ung, key=lambda x: x.ts)
    muc = d.tom_tat
    if th.pham_vi_noi_ro:
        muc = f"{d.tom_tat} — giới hạn ở: {th.pham_vi_noi_ro}"
    return KetNoi(d, muc,
                  (f"nối về đề xuất {d.ma} (tin nhắn #{d.message_id}, "
                   f"{d.tu_vai})"), th)
