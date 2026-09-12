# -*- coding: utf-8 -*-
"""VAI TRÒ ổn định, MODEL thay được — V1.0 (B4), và cổng review chéo (B5).

VÌ SAO KHÔNG GẮN CHẾT MODEL VÀO VAI: model đổi hàng tháng; vai thì không.
`CHIEF_STRATEGIST` hôm nay là Fable 5.1, mai có thể là thứ khác — mà mọi chỗ
gọi nó vẫn phải chạy. Nên vai là DANH TÍNH, model là MỘT LỰA CHỌN ƯU TIÊN, và
ưu tiên chỉ có hiệu lực khi model đó THẬT SỰ phơi ra ở fabric.

BA ĐIỀU FILE NÀY CỐ Ý KHÔNG LÀM:

1. **Không bịa model.** Ưu tiên không có trong fabric thì rơi xuống lựa chọn
   kế tiếp và GHI LẠI là đã rơi. Không bao giờ trả về một `model_id` mà
   fabric không biết — đó là cách một lượt dispatch chết ở tận nơi.
2. **Không tự nới `qd_0001`.** GPT-6 Astra là bậc thang NGOẠI LỆ cho việc
   suy luận cực khó, KHÔNG phải "chế độ MAX thì dùng Astra". Luật đó đọc từ
   ký ức dự án, và ở đây chỉ được THI HÀNH chứ không được định nghĩa lại.
3. **Không cho tự review.** Một thay đổi mã sản phẩm do họ Gemini viết thì
   người phản biện phải KHÁC HỌ. Cùng một phiên tự chấm mình là không có
   thông tin mới nào cả.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple


class Vai(str, Enum):
    """Vai trò trong đội. Tên ỔN ĐỊNH — mã khác tham chiếu bằng tên này."""

    PROJECT_LEADER = "PROJECT_LEADER"
    CHIEF_STRATEGIST = "CHIEF_STRATEGIST"
    PRINCIPAL_ARCHITECT = "PRINCIPAL_ARCHITECT"
    CTO_INTEGRATION = "CTO_INTEGRATION"
    SENIOR_ENGINEER = "SENIOR_ENGINEER"
    RAPID_ENGINEER = "RAPID_ENGINEER"
    CODE_REVIEWER = "CODE_REVIEWER"


#: Ưu tiên model cho từng vai — CHỈ là ưu tiên, theo thứ tự.
#:
#: Danh sách xếp từ "hợp nhất" xuống "chấp nhận được". Mục đầu không có trong
#: fabric thì thử mục sau; hết thì vai đó KHÔNG khả dụng (và nói ra), chứ
#: không im lặng lấy bừa một model.
UU_TIEN: Dict[Vai, Tuple[str, ...]] = {
    Vai.PROJECT_LEADER: ("claude-opus-5", "claude-code-session",
                         "claude-sonnet-4-6"),
    Vai.CHIEF_STRATEGIST: ("fable-5-1", "claude-opus-5", "gemini-3.1-pro-low"),
    Vai.PRINCIPAL_ARCHITECT: ("gpt-6-astra", "claude-opus-5"),
    Vai.CTO_INTEGRATION: ("gpt-5.6-sol", "codex-default", "claude-opus-5"),
    Vai.SENIOR_ENGINEER: ("claude-sonnet-4-6", "claude-sonnet-5",
                          "gemini-3.1-pro-low"),
    Vai.CODE_REVIEWER: ("claude-sonnet-4-6", "claude-sonnet-5",
                        "codex-default"),
    Vai.RAPID_ENGINEER: ("gemini-3.8-flash-high", "gemini-3.8-flash-medium"),
}

#: Model thuộc bậc NGOẠI LỆ — `qd_0001`. Không bao giờ là mặc định.
#:
#: Đây là THI HÀNH một quyết định đã ghi trong ký ức dự án, không phải một
#: chính sách mới đặt ra ở đây. Tra không được thì HẠN CHẾ (fail closed).
CAO_CAP: FrozenSet[str] = frozenset({"gpt-6-astra", "fable-5-1"})

#: Họ model — dùng cho luật ĐỘC LẬP của người phản biện.
def ho_model(model_id: str) -> str:
    m = (model_id or "").lower()
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith("claude"):
        return "claude"
    if m.startswith(("gpt", "codex")):
        return "openai"
    if m.startswith("fable"):
        return "fable"
    return "khac"


@dataclass(frozen=True)
class ChonVai:
    """Kết quả chọn model cho một vai — kèm VÌ SAO."""

    vai: Vai
    model_id: str = ""
    ho: str = ""
    la_uu_tien_dau: bool = False
    da_roi_xuong: Tuple[str, ...] = ()      # những ưu tiên đã thử mà không có
    ly_do: str = ""

    @property
    def co(self) -> bool:
        return bool(self.model_id)

    def to_dict(self) -> Dict:
        return {"vai": self.vai.value, "model_id": self.model_id,
                "ho": self.ho, "uu_tien_dau": self.la_uu_tien_dau,
                "da_roi_xuong": list(self.da_roi_xuong), "ly_do": self.ly_do}


def chon_model(vai: Vai, co_san: Sequence[str], *,
               cho_phep_cao_cap: bool = False) -> ChonVai:
    """Chọn model cho `vai` trong số `co_san` (model fabric THẬT SỰ phơi ra).

    `cho_phep_cao_cap=False` là MẶC ĐỊNH và là phần quan trọng: model bậc
    ngoại lệ bị bỏ qua trừ khi người gọi nói rõ đây là lượt leo thang. Nên
    "chế độ MAX" một mình KHÔNG kéo được Astra vào — phải có một quyết định
    leo thang tường minh.
    """
    co = [str(m) for m in co_san]
    bo_qua: List[str] = []
    for i, m in enumerate(UU_TIEN.get(vai, ())):
        if m in CAO_CAP and not cho_phep_cao_cap:
            bo_qua.append(f"{m} (bậc ngoại lệ — cần leo thang tường minh)")
            continue
        if m in co:
            return ChonVai(
                vai=vai, model_id=m, ho=ho_model(m),
                la_uu_tien_dau=(i == 0 and not bo_qua),
                da_roi_xuong=tuple(bo_qua),
                ly_do=("ưu tiên đầu của vai" if i == 0 and not bo_qua
                       else f"rơi xuống sau {len(bo_qua)} lựa chọn không dùng được"))
        bo_qua.append(f"{m} (không có ở fabric)")
    return ChonVai(vai=vai, da_roi_xuong=tuple(bo_qua),
                   ly_do=("không model nào của vai này khả dụng — KHÔNG lấy "
                          "bừa một model khác"))


# ==========================================================================
# B5 — CỔNG REVIEW CHÉO HỌ MODEL
# ==========================================================================

#: Loại việc mà kết quả là MÃ SẢN PHẨM. Review chéo là BẮT BUỘC.
VIEC_SUA_MA: FrozenSet[str] = frozenset({"implementation", "testing",
                                         "refactor", "migration"})

#: Loại việc DỮ LIỆU: cạo web, theo dõi tin, trích metadata, phân loại,
#: nghiên cứu. Kiểm bằng SCHEMA tất định là đủ — không cần một model thứ hai
#: đọc lại, và bắt nó đọc chỉ tốn quota mà không thêm tín hiệu.
VIEC_DU_LIEU: FrozenSet[str] = frozenset({"scrape", "monitor", "metadata",
                                          "classification", "research",
                                          "recon"})


@dataclass(frozen=True)
class YeuCauReview:
    bat_buoc: bool = False
    ly_do: str = ""
    ho_bi_cam: Tuple[str, ...] = ()          # họ KHÔNG được làm reviewer
    reviewer_de_xuat: Optional[ChonVai] = None

    def to_dict(self) -> Dict:
        return {"bat_buoc": self.bat_buoc, "ly_do": self.ly_do,
                "ho_bi_cam": list(self.ho_bi_cam),
                "reviewer": (self.reviewer_de_xuat.to_dict()
                             if self.reviewer_de_xuat else None)}


def can_review_doc_lap(*, loai_viec: str, model_da_lam: str,
                       co_kiem_schema: bool = False) -> YeuCauReview:
    """Việc này có BẮT BUỘC review độc lập trước khi chấp nhận không?

    Luật (B5), và nó hẹp có chủ đích:

    * họ **Gemini** + việc **sửa mã sản phẩm** -> BẮT BUỘC, reviewer phải
      khác họ;
    * việc **dữ liệu** (cạo/tin/metadata/phân loại/nghiên cứu) mà đã có
      **kiểm schema tất định** -> KHÔNG bắt buộc. Bắt một model thứ hai đọc
      lại một tệp JSON đã validate là tốn quota để mua một ý kiến;
    * mọi trường hợp khác -> không bắt buộc ở tầng này (tầng khác vẫn có thể
      yêu cầu).

    KHÔNG BAO GIỜ cho reviewer cùng họ với người viết: một phiên tự chấm
    mình không thêm thông tin nào.
    """
    ho = ho_model(model_da_lam)
    loai = (loai_viec or "").strip().lower()

    if loai in VIEC_DU_LIEU and co_kiem_schema:
        return YeuCauReview(
            bat_buoc=False,
            ly_do=(f"việc dữ liệu ({loai}) đã có kiểm schema tất định — "
                   f"một model thứ hai đọc lại không thêm tín hiệu"))

    if ho == "gemini" and loai in VIEC_SUA_MA:
        return YeuCauReview(
            bat_buoc=True, ho_bi_cam=("gemini",),
            ly_do=(f"mã sản phẩm do họ gemini viết ({model_da_lam}) — "
                   f"phản biện phải KHÁC họ trước khi chấp nhận"))

    return YeuCauReview(
        bat_buoc=False,
        ly_do=f"không thuộc diện bắt buộc ({ho}/{loai or 'không rõ'})")


def chon_reviewer(co_san: Sequence[str], *, ho_bi_cam: Sequence[str] = (),
                  vai: Vai = Vai.CODE_REVIEWER) -> ChonVai:
    """Chọn người phản biện, LOẠI những họ bị cấm.

    Lọc TRƯỚC khi chọn, không phải chọn xong rồi kiểm: chọn xong mới phát
    hiện trùng họ thì hoặc phải chọn lại (tốn một vòng), hoặc — tệ hơn — có
    người sẽ chấp nhận nó "cho xong".
    """
    cam = {str(h).lower() for h in ho_bi_cam}
    loc = [m for m in co_san if ho_model(m) not in cam]
    kq = chon_model(vai, loc)
    if not kq.co:
        return ChonVai(vai=vai, da_roi_xuong=kq.da_roi_xuong,
                       ly_do=(f"không có reviewer ĐỘC LẬP nào (đã loại họ "
                              f"{sorted(cam)}) — báo SUY GIẢM thay vì để một "
                              f"model tự chấm mình"))
    return kq
