"""PHÂN LOẠI THẤT BẠI và THỬ LẠI CÓ TRẦN cho vai suy luận — V0.8, §13.

MỘT CÂU QUAN TRỌNG NHẤT Ở ĐÂY, và nó là một luật, không phải một lời khuyên:

    **BẤT ĐỒNG Ý KIẾN CỦA MODEL KHÔNG PHẢI MỘT LỖI VẬN CHUYỂN.**

Một Reviewer trả về `REJECT` đã làm ĐÚNG việc của nó. Định tuyến lại sang
một model khác để "xin một ý kiến dễ chịu hơn" là biến cơ chế phản biện
thành một vòng lặp tìm sự đồng thuận — và nó sẽ luôn tìm được, vì lúc nào
cũng còn một model nữa. Nên `LoaiThatBai.VIEC` **không bao giờ** được thử
lại, kể cả khi còn ngân sách.

BỐN LOẠI KHÁC, và mỗi loại có một cách xử lý KHÁC NHAU. Gộp chúng thành
"hỏng thì thử chỗ khác" là cách sinh ra đúng cái "infinite provider cascade"
mà §13 cấm:

    NANG_LUC  chỗ chạy này KHÔNG LÀM ĐƯỢC (từ chối theo hình dạng, thiếu
              năng lực). Thử lại cùng chỗ là vô nghĩa -> ĐỊNH TUYẾN LẠI.
    QUOTA     hết hạn mức / bị chặn nhịp. Cùng chỗ sẽ hỏng tiếp, và cùng BỂ
              cũng vậy -> ĐỊNH TUYẾN LẠI, và loại cả bể.
    XAC_THUC  chưa đăng nhập. KHÔNG có đường tự động nào sửa được, và thử
              chỗ khác chỉ che mất việc người vận hành cần đăng nhập lại
              -> DỪNG, báo người.
    RUNTIME   tiến trình chết/quá hạn/không sinh được. Đây là loại DUY NHẤT
              mà thử lại CÙNG CHỖ có nghĩa (một lần), vì nguyên nhân có thể
              là một phiên đã chết.

TRẦN LÀ HAI CON SỐ, không phải một. Trần MỖI VAI chặn một vai quay vòng;
trần TOÀN LƯỢT chặn ba vai cùng quay vòng rồi cộng lại thành mười lần gọi
cho một câu hỏi. Thiếu con số thứ hai là một lỗi thật hay gặp.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from scripts.control_center.reasoning.vai import VaiTro


class LoaiThatBai(str, Enum):
    NANG_LUC = "NANG_LUC"
    QUOTA = "QUOTA"
    XAC_THUC = "XAC_THUC"
    RUNTIME = "RUNTIME"
    VIEC = "VIEC"
    KHONG_RO = "KHONG_RO"

    @property
    def mo_ta(self) -> str:
        return {
            "NANG_LUC": "chỗ chạy không làm được việc này",
            "QUOTA": "hết hạn mức hoặc bị chặn nhịp",
            "XAC_THUC": "chưa đăng nhập / mất xác thực",
            "RUNTIME": "tiến trình chết, quá hạn, hoặc không sinh được",
            "VIEC": "vai đã chạy và trả về thứ không dùng được (hoặc bất đồng)",
            "KHONG_RO": "không phân loại được",
        }[self.value]


class HanhDong(str, Enum):
    """Việc phải làm sau một lần hỏng."""

    THU_LAI_CUNG_CHO = "THU_LAI_CUNG_CHO"
    DINH_TUYEN_LAI = "DINH_TUYEN_LAI"
    DUNG = "DUNG"


#: Mẫu nhận dạng, xếp theo thứ tự ƯU TIÊN KIỂM. Thứ tự quan trọng: một thông
#: báo "rate limit" thường cũng chứa chữ "error", nên QUOTA phải được kiểm
#: trước RUNTIME.
_MAU: Tuple[Tuple[LoaiThatBai, Tuple[str, ...]], ...] = (
    (LoaiThatBai.XAC_THUC, (
        r"\bnot logged in\b", r"\bunauthenti", r"\bunauthorized\b",
        r"\b401\b", r"\blogin (required|expired)\b", r"\bchưa đăng nhập\b",
        r"\bauth(entication)? (failed|required|error)\b",
        r"\bcredential(s)? (missing|invalid)\b", r"\bmất xác thực\b",
        r"\bchưa lưu profile\b",
    )),
    (LoaiThatBai.QUOTA, (
        r"\brate.?limit", r"\bquota\b", r"\b429\b", r"\btoo many requests\b",
        r"\bhết (hạn mức|quota|credit)\b", r"\bexceeded\b.{0,20}\blimit\b",
        r"\blimit reached\b", r"\bresource.?exhausted\b",
        r"\bngân sách .{0,15}cạn\b", r"\bcooldown\b", r"\bthrottl",
        r"\binsufficient (credits|quota)\b",
    )),
    (LoaiThatBai.NANG_LUC, (
        r"codex_security_shaped_refusal", r"\bflagged for possible cyber",
        r"\btrusted access for cyber", r"\bno_model_pinned\b",
        r"\btool_permission_denied\b", r"\bpermission (denied|prompt)\b",
        r"\brefus(e|ed|al)\b", r"\btừ chối\b", r"\bthiếu năng lực\b",
        r"\bunsupported\b", r"\bmodel not (found|available)\b",
        r"\bI (can'?t|cannot) (help|assist) with\b",
    )),
    (LoaiThatBai.RUNTIME, (
        r"\btimeout\b", r"\btimed out\b", r"\bquá hạn\b", r"\bexit_-?\d+\b",
        r"\bspawn_failed\b", r"\bbroken pipe\b", r"\bconnection (reset|refused)\b",
        r"\bprocess (died|exited)\b", r"\bkhông khởi động được\b",
        r"\bkhông mở được phiên\b", r"\btrả về rỗng\b", r"\bempty response\b",
        r"\b5\d\d\b", r"\bsegmentation fault\b", r"\bOSError\b",
    )),
)

_BIEN_DICH = tuple((l, tuple(re.compile(m, re.I) for m in ms)) for l, ms in _MAU)


def phan_loai_that_bai(*, loi: str = "", van_ban: str = "",
                       ma_thoat: Optional[int] = None,
                       rong: bool = False,
                       doc_duoc: bool = True) -> Tuple[LoaiThatBai, str]:
    """`(loại, vì sao)`. Tất định, không LLM.

    `rong=True` (lượt trả về rỗng) là dấu hiệu RUNTIME chứ không phải VIEC:
    đo thật 2026-09-10 — `agy --print` tự chối một công cụ cần quyền thì lượt
    kết thúc RỖNG. Một lượt rỗng nghĩa là tiến trình không nói được gì, khác
    hẳn một lượt nói được nhưng nói thứ ta không dùng được.

    `doc_duoc=False` với văn bản KHÔNG rỗng là VIEC: vai đã chạy, đã tiêu một
    lượt, và trả về thứ không khớp lược đồ. Định tuyến lại cho trường hợp này
    là đi mua một ý kiến khác — xem docstring module.
    """
    gop = " ".join(x for x in (loi, van_ban) if x)
    for loai, mau in _BIEN_DICH:
        for r in mau:
            if r.search(gop):
                return loai, f"khớp dấu hiệu {loai.value}: {r.pattern!r}"
    if rong:
        return LoaiThatBai.RUNTIME, ("lượt trả về RỖNG — tiến trình không nói "
                                     "được gì (thường là công cụ bị chối quyền "
                                     "trong phiên headless)")
    if not doc_duoc:
        return LoaiThatBai.VIEC, ("vai đã chạy và trả lời, nhưng đầu ra không "
                                  "khớp lược đồ — KHÔNG định tuyến lại")
    if ma_thoat not in (None, 0):
        return LoaiThatBai.RUNTIME, f"mã thoát {ma_thoat}"
    return LoaiThatBai.KHONG_RO, "không dấu hiệu nào khớp"


#: Trần số LƯỢT GỌI cho MỘT vai trong một lượt hội thoại (gồm cả lần đầu).
TRAN_MOI_VAI = 2
#: Trần số LƯỢT GỌI cho TOÀN BỘ lượt hội thoại, cộng mọi vai.
TRAN_TOAN_LUOT = 4


@dataclass
class ChinhSachThuLai:
    """Trần thử lại của MỘT lượt hội thoại. Trạng thái sống bằng lượt đó.

    Sống ngắn có chủ ý: một bộ đếm bền qua nhiều lượt sẽ làm lượt thứ hai
    của người dùng bị chặn vì lượt thứ nhất đã tiêu ngân sách — và người dùng
    không có cách nào biết vì sao.
    """

    tran_moi_vai: int = TRAN_MOI_VAI
    tran_toan_luot: int = TRAN_TOAN_LUOT
    _da_goi: Dict[VaiTro, int] = field(default_factory=dict)
    _da_thu_cung_cho: Dict[VaiTro, int] = field(default_factory=dict)
    #: Placement đã hỏng cho từng vai — đi vào `exclude` của `Scheduler`.
    _loai_tru: Dict[VaiTro, List[str]] = field(default_factory=dict)

    @property
    def tong_goi(self) -> int:
        return sum(self._da_goi.values())

    def so_lan(self, vai: VaiTro) -> int:
        return self._da_goi.get(vai, 0)

    def loai_tru(self, vai: VaiTro) -> Tuple[str, ...]:
        return tuple(self._loai_tru.get(vai, ()))

    def ghi_goi(self, vai: VaiTro) -> None:
        self._da_goi[vai] = self._da_goi.get(vai, 0) + 1

    def con_cho_goi(self, vai: VaiTro) -> Tuple[bool, str]:
        """Vai này còn được gọi (lần đầu hay lần thử lại) không."""
        if self.so_lan(vai) >= self.tran_moi_vai:
            return False, (f"vai {vai.value} đã gọi {self.so_lan(vai)} lần "
                           f"(trần mỗi vai {self.tran_moi_vai})")
        if self.tong_goi >= self.tran_toan_luot:
            return False, (f"lượt này đã gọi {self.tong_goi} lượt vai "
                           f"(trần toàn lượt {self.tran_toan_luot})")
        return True, ""

    def quyet_dinh(self, vai: VaiTro, loai: LoaiThatBai, *,
                   placement: str = "") -> Tuple[HanhDong, str]:
        """Sau một lần hỏng: làm gì tiếp. Mặc định nghiêng về DỪNG.

        Ghi `placement` vào danh sách loại trừ của vai TRƯỚC khi trả lời, trừ
        khi hành động là thử lại cùng chỗ — nhờ vậy bên gọi không phải nhớ
        tự làm việc đó, và một lần quên sẽ không biến thành vòng lặp trên
        cùng một chỗ hỏng.
        """
        if loai is LoaiThatBai.VIEC:
            return HanhDong.DUNG, (
                "đầu ra không dùng được / vai bất đồng — ĐÂY KHÔNG PHẢI LỖI "
                "VẬN CHUYỂN. Không định tuyến lại: đi tìm một model khác cho "
                "cùng câu hỏi là đi mua một ý kiến dễ chịu hơn.")
        if loai is LoaiThatBai.XAC_THUC:
            if placement:
                self._loai_tru.setdefault(vai, []).append(placement)
            return HanhDong.DUNG, (
                "mất xác thực — không có đường tự động nào sửa được; cần "
                "người đăng nhập lại. Thử chỗ khác sẽ che mất việc đó.")

        con, vi_sao = self.con_cho_goi(vai)
        if not con:
            if placement:
                self._loai_tru.setdefault(vai, []).append(placement)
            return HanhDong.DUNG, f"hết ngân sách thử lại: {vi_sao}"

        if loai is LoaiThatBai.RUNTIME:
            da = self._da_thu_cung_cho.get(vai, 0)
            if da < 1:
                self._da_thu_cung_cho[vai] = da + 1
                return HanhDong.THU_LAI_CUNG_CHO, (
                    "lỗi runtime có thể là một phiên đã chết — thử lại ĐÚNG "
                    "MỘT lần trên cùng chỗ trước khi đổi chỗ")
            if placement:
                self._loai_tru.setdefault(vai, []).append(placement)
            return HanhDong.DINH_TUYEN_LAI, ("đã thử lại cùng chỗ một lần và "
                                             "vẫn hỏng — đổi chỗ")

        # NANG_LUC / QUOTA / KHONG_RO: thu lai cung cho la vo nghia.
        if placement:
            self._loai_tru.setdefault(vai, []).append(placement)
        return HanhDong.DINH_TUYEN_LAI, (
            f"{loai.value} ({loai.mo_ta}) — cùng chỗ sẽ hỏng lại; loại "
            f"{placement or 'chỗ vừa hỏng'} rồi chọn lại")

    def to_dict(self) -> Dict:
        return {"tran_moi_vai": self.tran_moi_vai,
                "tran_toan_luot": self.tran_toan_luot,
                "tong_goi": self.tong_goi,
                "da_goi": {k.value: v for k, v in self._da_goi.items()},
                "loai_tru": {k.value: list(v)
                             for k, v in self._loai_tru.items()}}
