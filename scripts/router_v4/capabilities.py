"""Từ vựng NĂNG LỰC — Router V4, nền của mọi quyết định định tuyến.

QUY TẮC KIẾN TRÚC TRUNG TÂM CỦA V4:

    ĐỊNH TUYẾN THEO YÊU CẦU CỦA VIỆC.
    KHÔNG ĐỊNH TUYẾN THEO VAI TRÒ MODEL ĐÓNG CỨNG.

Router V3 định tuyến bằng những nhãn như `"implement" -> GEMINI_FLASH_HIGH`.
Nó chạy được, nhưng nó gắn chặt *cái tên nhà cung cấp* vào *loại việc*: đổi
model, thêm tài khoản, hay một việc cần đọc video đều phải sửa bảng định
tuyến. Tệ hơn, nó khoá Gemini vào vai "worker code" trong khi cùng model đó
đọc được ảnh/video — năng lực KHAN HIẾM nhất của cả bể.

Ở V4, bên gọi mô tả **nhu cầu**:

    "cần: repo_write + coding, reasoning cao, không cần multimodal"

và bộ lập lịch tự tìm ra (runtime, model) nào thoả. Không chỗ nào trong mã
được viết `if task == "coding": dùng Gemini`.

HAI LOẠI YÊU CẦU, tách bạch có chủ đích:

    RÀO CỨNG (`bool` trong `Requirements`) — không thoả thì LOẠI. Một việc
        cần đọc video mà model không đọc được video thì không có điểm số nào
        cứu được; nó sẽ thất bại một cách khó hiểu.
    THANG ĐO (`reasoning_level`, `latency_priority`, `quality_priority`) —
        cho điểm, đánh đổi được.

Trộn hai loại này là lỗi thiết kế hay gặp: nó cho phép một worker "rẻ và
rảnh" thắng một việc mà nó CHẲNG LÀM ĐƯỢC.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Optional, Set

#: Nang luc NHI PHAN — mot model co hoac khong. Day la RAO CUNG.
#:
#: Co y giu nho va cu the. Mot tu vung phinh to ("smart", "fast", "good at
#: python") khong kiem duoc bang may va se bien thanh vai tro dong cung
#: duoi mot cai ten khac.
HARD_CAPABILITIES: FrozenSet[str] = frozenset({
    "coding",             # sinh/sua ma nguon
    "repo_read",          # doc duoc tep trong kho
    "repo_write",         # ghi duoc tep (can workspace co lap)
    "shell",              # chay duoc lenh he thong
    "multimodal",         # hieu duoc dau vao khong phai van ban (bao trum)
    "image",              # doc anh
    "video",              # doc video
    "audio",              # doc am thanh
    "long_context",       # cua so ngu canh lon
    "structured_output",  # tra ve JSON dung luoc do mot cach dang tin
})

#: Muc suy luan. Thang do CO THU TU — so sanh duoc, khong phai nhan tu do.
class Reasoning(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}[self.value]

    def __ge__(self, other) -> bool:                      # type: ignore[override]
        if isinstance(other, Reasoning):
            return self.rank >= other.rank
        return NotImplemented

    def __gt__(self, other) -> bool:                      # type: ignore[override]
        if isinstance(other, Reasoning):
            return self.rank > other.rank
        return NotImplemented

    def __le__(self, other) -> bool:                      # type: ignore[override]
        if isinstance(other, Reasoning):
            return self.rank <= other.rank
        return NotImplemented

    def __lt__(self, other) -> bool:                      # type: ignore[override]
        if isinstance(other, Reasoning):
            return self.rank < other.rank
        return NotImplemented


class Priority(str, Enum):
    """Đánh đổi. `BALANCED` là mặc định và có nghĩa "không ưu tiên gì đặc
    biệt" — KHÔNG phải "ưu tiên trung bình cả hai"."""

    LOW = "low"
    BALANCED = "balanced"
    HIGH = "high"

    @property
    def weight(self) -> float:
        return {"low": 0.0, "balanced": 0.5, "high": 1.0}[self.value]


class CapabilityError(ValueError):
    pass


def validate_capabilities(caps: Iterable[str]) -> FrozenSet[str]:
    la = set(caps) - HARD_CAPABILITIES
    if la:
        raise CapabilityError(
            f"năng lực lạ {sorted(la)} — chỉ chấp nhận {sorted(HARD_CAPABILITIES)}. "
            f"Thêm một năng lực mới phải là quyết định có ý thức ở đây, không "
            f"phải một chuỗi gõ nhầm lặng lẽ tạo ra một rào cứng không ai thoả.")
    return frozenset(caps)


#: Nang luc BAO TRUM nang luc khac. `multimodal` la nhan chung; mot model
#: doc duoc video thi hien nhien la multimodal. Khai bao quan he nay MOT
#: LAN o day thay vi bat moi cau hinh phai liet ke ca hai — thieu mot dong
#: trong cau hinh se thanh mot rao cung khong ai thoa.
_BAO_TRUM: Dict[str, FrozenSet[str]] = {
    "video": frozenset({"multimodal"}),
    "image": frozenset({"multimodal"}),
    "audio": frozenset({"multimodal"}),
    "repo_write": frozenset({"repo_read"}),
}


def expand(caps: Iterable[str]) -> FrozenSet[str]:
    """Mở rộng theo quan hệ bao trùm. `{"video"}` -> `{"video","multimodal"}`."""
    ra: Set[str] = set(caps)
    doi = True
    while doi:
        doi = False
        for c in list(ra):
            them = _BAO_TRUM.get(c, frozenset()) - ra
            if them:
                ra |= them
                doi = True
    return frozenset(ra)


@dataclass(frozen=True)
class Requirements:
    """NHU CẦU của một việc. Bên gọi mô tả cái này, không mô tả worker.

    Mọi cờ `bool` mặc định `False`: một việc chỉ đòi thứ nó THẬT SỰ cần.
    Đòi thừa (vd bật `multimodal` cho một việc sửa CSS) làm cạn đúng thứ
    khan hiếm nhất — xem `scheduler.py` mục khan hiếm.
    """

    coding: bool = False
    repo_read: bool = False
    repo_write: bool = False
    shell: bool = False
    multimodal: bool = False
    image: bool = False
    video: bool = False
    audio: bool = False
    long_context: bool = False
    structured_output: bool = False

    reasoning_level: Reasoning = Reasoning.MEDIUM
    latency_priority: Priority = Priority.BALANCED
    quality_priority: Priority = Priority.BALANCED

    #: Ghim nhà cung cấp/runtime/model — CHỈ cho ràng buộc năng lực thật sự
    #: hoặc để người vận hành gỡ lỗi. Không phải đường tắt để "chọn con tôi
    #: thích"; `scheduler.explain()` luôn ghi rõ một lượt bị ghim.
    pin_provider: Optional[str] = None
    pin_runtime: Optional[str] = None
    pin_model: Optional[str] = None
    #: Loại trừ một họ model — dùng cho review độc lập khác họ.
    exclude_families: tuple = ()

    @property
    def hard(self) -> FrozenSet[str]:
        """Tập năng lực BẮT BUỘC, đã mở rộng bao trùm."""
        co = {f.name for f in fields(self)
              if f.name in HARD_CAPABILITIES and getattr(self, f.name)}
        return expand(co)

    def to_dict(self) -> Dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)
             if f.name in HARD_CAPABILITIES}
        d.update({
            "reasoning_level": self.reasoning_level.value,
            "latency_priority": self.latency_priority.value,
            "quality_priority": self.quality_priority.value,
        })
        for ten in ("pin_provider", "pin_runtime", "pin_model"):
            if getattr(self, ten):
                d[ten] = getattr(self, ten)
        if self.exclude_families:
            d["exclude_families"] = list(self.exclude_families)
        return d

    @staticmethod
    def from_dict(d: Optional[Dict]) -> "Requirements":
        d = dict(d or {})
        return Requirements(
            **{k: bool(d.get(k, False)) for k in HARD_CAPABILITIES},
            reasoning_level=Reasoning(str(d.get("reasoning_level") or "medium")),
            latency_priority=Priority(str(d.get("latency_priority") or "balanced")),
            quality_priority=Priority(str(d.get("quality_priority") or "balanced")),
            pin_provider=d.get("pin_provider") or None,
            pin_runtime=d.get("pin_runtime") or None,
            pin_model=d.get("pin_model") or None,
            exclude_families=tuple(d.get("exclude_families") or ()))


def satisfies(model_caps: Iterable[str], req: Requirements) -> bool:
    """Model có thoả MỌI rào cứng của việc không. Không có điểm số ở đây —
    đây là bộ lọc nhị phân chạy TRƯỚC mọi phép cho điểm."""
    return req.hard <= expand(model_caps)


def missing(model_caps: Iterable[str], req: Requirements) -> List[str]:
    """Năng lực còn THIẾU — để `explain()` nói được VÌ SAO một ứng viên bị
    loại, thay vì chỉ nói nó bị loại."""
    return sorted(req.hard - expand(model_caps))
