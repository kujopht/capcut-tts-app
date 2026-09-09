"""Bậc CAO CẤP (GPT-6 Astra) và bốn chế độ định tuyến — chính sách, có rào.

MỘT CÂU THÔI: Astra **không bao giờ** được chọn tự động.

VÌ SAO MODULE NÀY TỒN TẠI. `codex exec` không có `-m` thì chạy **model mặc
định của chính CLI**, và mặc định đó đổi được ở phía nhà cung cấp sau một
lần `codex update` — không ai bên này sửa một dòng nào. Đo 2026-09-09
(`codex doctor`, codex-cli 0.153.4): mặc định trên máy này là
`gpt-5.6-sol`, và **cùng bản CLI đó phơi ra `gpt-6-astra`**. Nghĩa là một
thay đổi ở phía họ có thể biến mọi việc vặt của Router thành một lần gọi
model đắt tiền, im lặng, không dấu vết.

Nên có HAI lớp rào, và chúng độc lập nhau:

    1. `CodexAdapter` FAIL CLOSED khi chưa ghim model — không bao giờ rơi
       về mặc định của nhà cung cấp. (Rào này chặn cả những model cao cấp
       chưa ai kịp đặt tên.)
    2. Module này: bậc 3 chỉ vào được bằng một lý do leo thang TƯỜNG MINH,
       và có trần song song, trần mỗi việc, cấm đệ quy.

BỐN BẬC

    T0  rẻ/đơn giản        tra cứu, tóm tắt, việc cơ học
    T1  code hằng ngày     mặc định của phần lớn việc
    T2  agentic/suy luận mạnh
    T3  CAO CẤP — Astra    chỉ leo thang, không bao giờ mặc định

BỐN CHẾ ĐỘ

    ECO     cấm Astra tuyệt đối
    AUTO    mặc định; Astra hiếm, chỉ leo thang  ← Fanfic dùng cái này
    STRONG  ưu tiên model mạnh; Astra leo thang với bằng chứng chặt hơn
    MAX     Astra được chọn ngay CHO VIỆC NÀY khi người yêu cầu tường minh

`MAX` không phải "bật Astra cho cả dự án" — nó là một lựa chọn cho MỘT
việc, và vẫn phải đi qua trần song song.

KHÔNG CÓ GIÁ Ở ĐÂY. Chưa có nguồn giá/usage chính thức nào đọc được từ
provider này, nên module không bịa một con số nào. Dùng bao nhiêu mà không
đo được thì ghi `UNAVAILABLE`, không ghi 0 — cùng luật với `usage.py`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

#: Tên model cao cấp. Một chỗ duy nhất, để không ai gõ lại sai.
MODEL_ASTRA = "gpt-6-astra"

#: Bậc được coi là CAO CẤP.
BAC_CAO_CAP = 3

#: Trần phiên Astra chạy SONG SONG trên toàn máy.
TRAN_ASTRA_SONG_SONG = 1

#: Trần số lần leo thang lên Astra cho MỘT việc.
TRAN_ASTRA_MOI_VIEC = 1


class CheDo(str, Enum):
    """Chế độ định tuyến. Giá trị là thứ đi vào sổ và vào API."""

    ECO = "ECO"
    AUTO = "AUTO"
    STRONG = "STRONG"
    MAX = "MAX"


#: Mặc định của mọi dự án, gồm cả Fanfic.
CHE_DO_MAC_DINH = CheDo.AUTO


class LyDoLeoThang(str, Enum):
    """Lý do HỢP LỆ để cân nhắc Astra. Không có lý do = không leo thang."""

    NGUOI_YEU_CAU = "nguoi_yeu_cau"
    MODEL_MANH_DA_HONG = "model_manh_da_hong"
    AGENT_BAT_DONG = "agent_bat_dong"
    LOI_DONG_THOI_KHO = "loi_dong_thoi_kho"
    SUY_LUAN_BAO_MAT = "suy_luan_bao_mat"
    PHAN_XU_KIEN_TRUC = "phan_xu_kien_truc"
    DI_TRU_PHUC_TAP = "di_tru_phuc_tap"
    TRONG_TAI_CUOI = "trong_tai_cuoi"


#: Loại việc TẦM THƯỜNG — Astra không bao giờ được dùng, kể cả khi có ai đó
#: gắn một lý do leo thang vào. Đây là danh sách trong yêu cầu vận hành,
#: chép nguyên ý chứ không diễn giải lại.
VIEC_TAM_THUONG = frozenset({
    "search", "grep", "docs", "documentation", "format", "formatting",
    "crud", "simple_bug", "test_writing", "tests", "dependency_update",
    "deps", "git", "git_ops", "frontend_simple", "summary", "summarize",
    "lookup", "rename", "lint",
})


@dataclass(frozen=True)
class BanGhiAstra:
    """Một lần dùng Astra. Ghi ĐỦ để sau này trả lời được 'vì sao'."""

    task_id: str
    provider: str
    model: str
    reason: str
    escalated_from: str
    timestamp: float = field(default_factory=time.time)
    #: Số lượt/lời gọi nếu nhà cung cấp có báo. `None` = KHÔNG ĐO ĐƯỢC.
    #: Không bao giờ điền 0 để cho đẹp — xem docstring module.
    turns: Optional[int] = None

    def to_dict(self) -> Dict:
        return {"task_id": self.task_id, "provider": self.provider,
                "model": self.model, "reason": self.reason,
                "escalated_from": self.escalated_from,
                "timestamp": self.timestamp, "turns": self.turns}


class NganSachCanKiet(RuntimeError):
    """Hết ngân sách cao cấp. FAIL CLOSED, không âm thầm hạ cấp."""


class GacAstra:
    """Rào cho bậc 3. Mọi con đường tới Astra phải đi qua đây.

    Trạng thái nằm trong bộ nhớ tiến trình có chủ ý: nó đếm phiên đang
    SỐNG, và một phiên không sống lâu hơn tiến trình đã sinh ra nó.
    """

    def __init__(self, *, tran_song_song: int = TRAN_ASTRA_SONG_SONG,
                 tran_moi_viec: int = TRAN_ASTRA_MOI_VIEC,
                 ngan_sach: Optional[int] = None):
        self.tran_song_song = int(tran_song_song)
        self.tran_moi_viec = int(tran_moi_viec)
        #: `None` = không đặt trần tổng. Một số = tổng lần gọi còn lại.
        self.ngan_sach = ngan_sach
        self._dang_chay: Dict[str, str] = {}       # session_id -> task_id
        self._da_dung: Dict[str, int] = {}         # task_id -> số lần
        self.nhat_ky: List[BanGhiAstra] = []

    # -- truy van -----------------------------------------------------------

    @property
    def dang_chay(self) -> int:
        return len(self._dang_chay)

    def so_lan_cua_viec(self, task_id: str) -> int:
        return self._da_dung.get(task_id, 0)

    @staticmethod
    def la_astra(model_id: str, premium_tier: int = 0) -> bool:
        """Có phải một model cao cấp không — theo BẬC, không theo tên.

        Kiểm cả tên lẫn bậc: một model cao cấp mới có thể mang tên khác,
        và một `premium_tier=3` phải bị chặn dù tên là gì.
        """
        return (model_id or "").strip().lower() == MODEL_ASTRA \
            or int(premium_tier or 0) >= BAC_CAO_CAP

    # -- quyet dinh ---------------------------------------------------------

    def xin_phep(self, *, task_id: str, che_do: CheDo,
                 ly_do: Optional[LyDoLeoThang] = None,
                 loai_viec: str = "",
                 tu_astra: bool = False) -> Tuple[bool, str]:
        """`(được phép, vì sao)`. Mặc định là KHÔNG.

        Thứ tự kiểm cố ý đi từ luật CỨNG nhất xuống: một việc tầm thường
        không được cứu bởi chế độ MAX, và đệ quy không được cứu bởi bất cứ
        thứ gì.
        """
        if tu_astra:
            return False, ("một phiên Astra KHÔNG được sinh ra một phiên "
                           "Astra khác — đệ quy cao cấp là cách một việc "
                           "biến thành một hoá đơn")

        if che_do is CheDo.ECO:
            return False, "chế độ ECO cấm Astra tuyệt đối"

        lv = (loai_viec or "").strip().lower()
        if lv in VIEC_TAM_THUONG:
            return False, (f"việc loại {lv!r} là việc thường — Astra không "
                           f"dùng cho loại này, kể cả khi có lý do leo thang")

        if self.ngan_sach is not None and self.ngan_sach <= 0:
            # FAIL CLOSED: khong am tham ha cap xuong model khac. Nguoi
            # goi phai thay ro rang la ngan sach het.
            return False, "ngân sách cao cấp đã cạn — FAIL CLOSED"

        if self.dang_chay >= self.tran_song_song:
            return False, (f"đã có {self.dang_chay} phiên Astra đang chạy "
                           f"(trần {self.tran_song_song})")

        da = self.so_lan_cua_viec(task_id)
        if da >= self.tran_moi_viec:
            return False, (f"việc {task_id} đã leo thang lên Astra {da} lần "
                           f"(trần {self.tran_moi_viec})")

        if che_do is CheDo.MAX:
            # MAX = nguoi dung da yeu cau TUONG MINH cho viec nay.
            return True, "chế độ MAX: người yêu cầu tường minh cho việc này"

        if ly_do is None:
            return False, ("không có lý do leo thang — Astra không bao giờ "
                           "là lựa chọn mặc định")

        if che_do is CheDo.STRONG:
            return True, f"chế độ STRONG + lý do {ly_do.value}"
        return True, f"chế độ AUTO + lý do leo thang {ly_do.value}"

    # -- vong doi -----------------------------------------------------------

    def mo(self, *, session_id: str, task_id: str, che_do: CheDo,
           ly_do: Optional[LyDoLeoThang], escalated_from: str,
           loai_viec: str = "", tu_astra: bool = False) -> BanGhiAstra:
        """Ghi nhận một phiên Astra. Ném `PermissionError` nếu không được.

        Đi qua `xin_phep` LẦN NỮA ở đây có chủ ý: bên gọi có thể đã hỏi
        phép từ lâu, và trạng thái đổi được giữa hai thời điểm.
        """
        ok, vi_sao = self.xin_phep(task_id=task_id, che_do=che_do,
                                   ly_do=ly_do, loai_viec=loai_viec,
                                   tu_astra=tu_astra)
        if not ok:
            raise PermissionError(vi_sao)
        self._dang_chay[session_id] = task_id
        self._da_dung[task_id] = self._da_dung.get(task_id, 0) + 1
        if self.ngan_sach is not None:
            self.ngan_sach -= 1
        bg = BanGhiAstra(task_id=task_id, provider="codex", model=MODEL_ASTRA,
                         reason=vi_sao, escalated_from=escalated_from)
        self.nhat_ky.append(bg)
        return bg

    def dong(self, session_id: str) -> None:
        self._dang_chay.pop(session_id, None)


def bac_cua(model_id: str, premium_tier: int = 0) -> int:
    """Bậc của một model, ưu tiên con số đã khai trong cấu hình."""
    if int(premium_tier or 0) > 0:
        return int(premium_tier)
    return BAC_CAO_CAP if GacAstra.la_astra(model_id) else 1


def loc_ung_vien(models, *, che_do: CheDo, duoc_astra: bool = False):
    """Bỏ model cao cấp khỏi danh sách ứng viên khi chưa được phép.

    Đây là chỗ nối vào bộ lập lịch: nó KHÔNG cần biết gì về Astra, nó chỉ
    nhận một danh sách đã được lọc. Ít thứ phải nhớ hơn = ít chỗ quên hơn.
    """
    ra = []
    for m in models:
        cao = GacAstra.la_astra(getattr(m, "model_id", ""),
                               getattr(m, "premium_tier", 0))
        if cao and not (duoc_astra and che_do is not CheDo.ECO):
            continue
        ra.append(m)
    return ra
