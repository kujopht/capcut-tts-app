"""VAI suy luận, và nhu cầu NĂNG LỰC của từng vai — V0.8.

Ở đây một vai là một **hồ sơ nhu cầu**, không phải một cái tên model. Đó là
cùng quy tắc kiến trúc mà Router V4 đã chọn cho việc (`router_v4/
capabilities.py`): bên gọi mô tả *cần gì*, bộ lập lịch tìm ra *ai thoả*.

Nếu viết `STRATEGIST = "claude-opus-4-6-thinking"` thì v0.8 sẽ chỉ là V3 dưới
một cái tên mới: đổi model, thêm tài khoản, hay một hôm Opus hết hạn mức đều
phải sửa mã. Nên vai khai `reasoning_toi_thieu`, `structured_output`, trần
token — và `dinh_tuyen.py` ghép đôi.

BA NĂNG LỰC MÀ VAI SUY LUẬN **KHÔNG** ĐƯỢC ĐÒI, và lý do là một phép đo:

    `repo_read`, `repo_write`, `shell`.

`agy --print` (headless) TỰ CHỐI mọi công cụ cần duyệt quyền — `command`,
`read_file`, `read_url` — kể cả khi chính Leader gọi chúng, và lượt trả về
RỖNG (đo 2026-09-10, ghi trong `CLAUDE.md` mục "LUẬT CHUNG đã trả giá BỐN
lần"). Một vai suy luận đòi `repo_read` sẽ được xếp lên một chỗ chạy không
đọc nổi tệp, rồi chết rỗng.

Nên vai suy luận **không có công cụ**, và mọi thứ nó cần đã nằm trong gói ngữ
cảnh do Router dựng hộ (`ngu_canh.py`). Cùng khuôn với `nguon_git.
git_nhat_ky_doc`, `web_reader.doc_web` và ký ức dự án: Router làm phép đọc an
toàn rồi ĐÍNH bằng chứng, chứ không nới quyền cho agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from scripts.router_v4.capabilities import Priority, Reasoning


class VaiTro(str, Enum):
    """Bốn vai. Giá trị là thứ đi vào sổ, vào API và vào giao diện."""

    LEADER = "leader"
    STRATEGIST = "strategist"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"

    @property
    def nhan(self) -> str:
        return {"leader": "Leader", "strategist": "Strategist",
                "reviewer": "Reviewer", "executor": "Executor"}[self.value]


#: Vai SUY LUẬN — những vai gói này tự định tuyến và tự gọi.
#:
#: `EXECUTOR` cố ý KHÔNG có trong tập này: nó là Router V4, và nó đi qua
#: `Scheduler`/`Executor` với hợp đồng việc thật, worktree thật, khoá thật.
#: Gộp nó vào đây sẽ mời người ta gọi một "executor" không có worktree.
VAI_SUY_LUAN: Tuple[VaiTro, ...] = (VaiTro.LEADER, VaiTro.STRATEGIST,
                                    VaiTro.REVIEWER)


@dataclass(frozen=True)
class HoSoVai:
    """Nhu cầu của một vai. Dữ liệu thuần — `dinh_tuyen.py` biến nó thành
    `Requirements`, `ngu_canh.py` đọc trần token của nó."""

    vai: VaiTro
    #: Bậc suy luận TỐI THIỂU khi việc ở mức thường. Câu khó nâng bậc này
    #: lên `HIGH` trong `dinh_tuyen.py` — hồ sơ là sàn, không phải trần.
    reasoning_toi_thieu: Reasoning
    #: Ưu tiên khi cho điểm. Leader ưu tiên ĐỘ TRỄ (nó chạy mọi lượt, kể cả
    #: câu chào); Strategist/Reviewer ưu tiên CHẤT LƯỢNG.
    uu_tien_do_tre: Priority
    uu_tien_chat_luong: Priority
    #: Trần token cho gói ngữ cảnh của vai này. ĐỘC LẬP với kích thước lịch
    #: sử dự án — cùng nguyên tắc "ảo hoá ngữ cảnh" của V0.6.
    tran_token_ngu_canh: int
    #: Trần thời gian tường cho MỘT lượt của vai.
    han_giay: float
    mo_ta: str

    @property
    def can_structured_output(self) -> bool:
        """Mọi vai suy luận đều phải trả về đúng một lược đồ.

        Không phải để cho đẹp: `hop_dong.py` FAIL CLOSED khi không đọc được
        phán xử ACCEPT/REVISE/REJECT, và một bản phản biện không đọc được
        thì Leader sẽ tổng hợp từ văn xuôi — tức là mất chính cái tín hiệu
        mà Reviewer tồn tại để tạo ra.
        """
        return True

    def to_dict(self) -> Dict:
        return {"vai": self.vai.value,
                "reasoning_toi_thieu": self.reasoning_toi_thieu.value,
                "uu_tien_do_tre": self.uu_tien_do_tre.value,
                "uu_tien_chat_luong": self.uu_tien_chat_luong.value,
                "tran_token_ngu_canh": self.tran_token_ngu_canh,
                "han_giay": self.han_giay,
                "can_structured_output": self.can_structured_output,
                "mo_ta": self.mo_ta}


#: Trần token: Leader nhỏ nhất vì nó chạy MỌI lượt; Strategist lớn nhất vì
#: nó là vai duy nhất cần thấy cả viên nang + quyết định + ràng buộc cùng
#: lúc; Reviewer ở giữa và nhận THÊM bản chiến lược đang bị soi.
HO_SO_VAI: Dict[VaiTro, HoSoVai] = {
    VaiTro.LEADER: HoSoVai(
        vai=VaiTro.LEADER,
        reasoning_toi_thieu=Reasoning.MEDIUM,
        uu_tien_do_tre=Priority.HIGH,
        uu_tien_chat_luong=Priority.BALANCED,
        tran_token_ngu_canh=2500,
        han_giay=180.0,
        mo_ta="sở hữu hội thoại; tổng hợp; quyết có cần suy luận sâu hơn"),
    VaiTro.STRATEGIST: HoSoVai(
        vai=VaiTro.STRATEGIST,
        reasoning_toi_thieu=Reasoning.HIGH,
        uu_tien_do_tre=Priority.LOW,
        uu_tien_chat_luong=Priority.HIGH,
        tran_token_ngu_canh=4200,
        han_giay=420.0,
        mo_ta="kiến trúc, lộ trình, đánh đổi, chiến lược gỡ lỗi khó"),
    VaiTro.REVIEWER: HoSoVai(
        vai=VaiTro.REVIEWER,
        reasoning_toi_thieu=Reasoning.HIGH,
        uu_tien_do_tre=Priority.LOW,
        uu_tien_chat_luong=Priority.HIGH,
        tran_token_ngu_canh=3400,
        han_giay=360.0,
        mo_ta="phản biện độc lập: bằng chứng thiếu, ràng buộc vi phạm, rủi ro"),
}


def ho_so(vai: VaiTro) -> HoSoVai:
    """Hồ sơ của một vai. Ném cho `EXECUTOR` có chủ ý — nó không đi đường này.

    Trả về một hồ sơ mặc định cho `EXECUTOR` sẽ mời người ta gọi Router V4
    qua `dinh_tuyen.py`, bỏ qua worktree/khoá/kiểm định. Thà ném.
    """
    h = HO_SO_VAI.get(vai)
    if h is None:
        raise KeyError(
            f"vai {vai!r} không có hồ sơ suy luận. `EXECUTOR` đi qua Router "
            f"V4 (`Scheduler` + `Executor`) với hợp đồng việc thật — không "
            f"qua bộ định tuyến vai.")
    return h
