# -*- coding: utf-8 -*-
"""PROJECT LEADER: danh tính theo dự án + phiên nối lại được — V1.0 (B2, B3).

╔══════════════════════════════════════════════════════════════════════════╗
║  NỀN MÓNG — **CHƯA ĐƯỢC CẮM**. Không tính là năng lực V1.0 đang chạy.    ║
╚══════════════════════════════════════════════════════════════════════════╝

Tệp này có bài kiểm và KHÔNG có một chỗ gọi nào trong mã sản phẩm. Nó được
giữ lại một cách CÓ Ý THỨC làm nền cho cột mốc "Leader Opus 5 bền" về sau,
và nó KHÔNG được kể là một tính năng của bản phát hành này.

Vì sao ghi thẳng ra đây thay vì chỉ ghi trong báo cáo: đúng câu chủ sở hữu
dùng cho vòng sự cố — *"tested but not wired"* — đã đúng HAI lần trong bản
này (`su_co.py`, rồi `vai_tro.py`). Một mô-đun có 100% bài kiểm xanh trông y
hệt một mô-đun đang chạy, nếu không ai nói ra sự khác biệt.

Và có một cái bẫy cụ thể ở đây: `scripts/control_center/leader.py` có sẵn một
lớp **CÙNG TÊN** `PhienLeader`, và lớp ấy THẬT SỰ được dùng
(`engine.py`). Một phép tìm theo tên lớp sẽ trả về kết quả và cho cảm giác
tệp này đã được cắm — nó chưa.

**Muốn cắm thì phải có một dặm đường thật kèm theo**, không phải chỉ thêm
một lời gọi: đó là bài học đắt nhất của V1.0.


Mỗi dự án có MỘT danh tính Leader logic. Model/runtime chạy nó là một lựa
chọn thay được — hôm nay Claude Opus 5, mai có thể khác — mà vai thì không
đổi.

PHIÊN LÀ BỘ NHỚ NÓNG, KHÔNG PHẢI SỰ THẬT. Sự thật bền nằm ở: Ký ức dự án,
Viên nang, git, quyết định, sổ thực thi, sự cố, trạng thái sống. Mất phiên
là mất tốc độ, KHÔNG mất kiến thức — nên `hydrate` luôn dựng lại được từ các
nguồn bền, và một phiên hỏng không bao giờ là lý do để hỏi lại người dùng
những thứ đã biết.

VÌ SAO CÓ TRỪU TƯỢNG RUNTIME: `claude` CLI khai TƯỜNG MINH `--session-id
<uuid>` / `-r <uuid>` / `--fork-session` (đo được, xem
`V10_RUNTIME_CAPABILITY_AUDIT.md`), và `codex exec` cũng có `resume`/`fork`.
Hình dạng giống nhau đủ để một giao diện chung là thật chứ không khiên
cưỡng. Nhưng gói này KHÔNG tự gọi tiến trình nào — nó chỉ mô tả và giữ
trạng thái. Ai muốn chạy thật thì cắm một `RuntimeLeader` vào.

BA ĐIỀU TUYỆT ĐỐI KHÔNG:

1. **Không đọc tệp phiên nội bộ của công cụ khác**, không cookie trình
   duyệt, không trạng thái riêng tư. Định danh phiên là UUID **Router sinh
   ra và Router giữ**.
2. **Không lưu bí mật vào Ký ức dự án.** `PhienLeader` chỉ giữ tham chiếu.
3. **Không giả vờ có runtime.** Không chứng minh được thì `UNVERIFIED` và
   Leader chạy bằng đường sẵn có — không bao giờ báo là đã nối.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence


class TrangThaiPhien(str, Enum):
    CHUA_CO = "CHUA_CO"
    DANG_SONG = "DANG_SONG"
    NGUOI = "NGUOI"              # còn tham chiếu nhưng lâu không dùng
    HET_HAN = "HET_HAN"
    HONG = "HONG"
    UNVERIFIED = "UNVERIFIED"    # runtime chưa chứng minh được ở máy này


class KetCucLeader(str, Enum):
    """Kết cục CUỐI của một mục tiêu Leader — cố ý CHỈ có bốn.

    "worker hỏng, nhờ người dùng debug" KHÔNG nằm trong danh sách này, và đó
    là toàn bộ ý nghĩa của nó.
    """

    DONE = "DONE"
    CANCELLED_BY_OWNER = "CANCELLED_BY_OWNER"
    WAITING_AUTHORITY = "WAITING_AUTHORITY"
    UNRECOVERABLE_AFTER_BOUNDED_INVESTIGATION = \
        "UNRECOVERABLE_AFTER_BOUNDED_INVESTIGATION"


#: Phiên nguội quá ngưỡng này thì nối lại là rủi ro (ngữ cảnh đã trôi).
NGUONG_NGUOI = 6 * 3600.0
#: Phiên quá nặng thì XOAY sang phiên mới + nạp lại điểm dừng.
TRAN_LUOT = 120


class RuntimeLeader(Protocol):
    """Thứ một runtime Leader phải làm được. Cắm được, thay được."""

    ten: str

    def san_sang(self) -> bool: ...
    def tao_phien(self, *, session_id: str, model: str) -> bool: ...
    def noi_lai(self, *, session_id: str) -> bool: ...
    def hoi(self, *, session_id: str, cau: str) -> str: ...


@dataclass
class PhienLeader:
    """Tham chiếu phiên Leader của MỘT dự án. Bền trong sổ, không bí mật."""

    project_id: str
    leader_runtime: str = ""
    preferred_model: str = ""
    session_ref: str = ""
    session_status: TrangThaiPhien = TrangThaiPhien.CHUA_CO
    last_seen: float = 0.0
    checkpoint_ref: str = ""
    so_luot: int = 0

    @property
    def giay_nguoi(self) -> float:
        return max(0.0, time.time() - self.last_seen) if self.last_seen else 0.0

    @property
    def noi_lai_duoc(self) -> bool:
        """Có nên NỐI LẠI phiên này không.

        Ba điều kiện, và thiếu một là dựng mới: có tham chiếu, trạng thái
        còn sống, và chưa nguội quá ngưỡng. Nối vào một phiên đã trôi ngữ
        cảnh tệ hơn dựng mới — nó trả lời tự tin bằng một bối cảnh sai.
        """
        return (bool(self.session_ref)
                and self.session_status in (TrangThaiPhien.DANG_SONG,
                                            TrangThaiPhien.NGUOI)
                and self.giay_nguoi <= NGUONG_NGUOI)

    @property
    def can_xoay(self) -> bool:
        """Phiên quá nặng -> xoay sang phiên mới, nạp lại từ điểm dừng."""
        return self.so_luot >= TRAN_LUOT

    def to_dict(self) -> Dict:
        return {"project_id": self.project_id,
                "leader_runtime": self.leader_runtime,
                "preferred_model": self.preferred_model,
                "session_ref": self.session_ref,
                "session_status": self.session_status.value,
                "last_seen": self.last_seen, "giay_nguoi": self.giay_nguoi,
                "checkpoint_ref": self.checkpoint_ref,
                "so_luot": self.so_luot, "noi_lai_duoc": self.noi_lai_duoc,
                "can_xoay": self.can_xoay}

    @classmethod
    def from_dict(cls, d: Dict) -> "PhienLeader":
        return cls(
            project_id=str(d.get("project_id") or ""),
            leader_runtime=str(d.get("leader_runtime") or ""),
            preferred_model=str(d.get("preferred_model") or ""),
            session_ref=str(d.get("session_ref") or ""),
            session_status=TrangThaiPhien(
                str(d.get("session_status") or "CHUA_CO")),
            last_seen=float(d.get("last_seen") or 0.0),
            checkpoint_ref=str(d.get("checkpoint_ref") or ""),
            so_luot=int(d.get("so_luot") or 0))


@dataclass
class KetQuaKichHoat:
    """Kết quả của một lần kích hoạt Leader — NÓI RÕ đã nối hay dựng mới."""

    phien: PhienLeader
    da_noi_lai: bool = False
    da_dung_moi: bool = False
    da_xoay: bool = False
    can_nap_boi_canh: bool = False
    ly_do: str = ""

    def to_dict(self) -> Dict:
        return {"phien": self.phien.to_dict(), "da_noi_lai": self.da_noi_lai,
                "da_dung_moi": self.da_dung_moi, "da_xoay": self.da_xoay,
                "can_nap_boi_canh": self.can_nap_boi_canh,
                "ly_do": self.ly_do}


def kich_hoat(phien: PhienLeader, *, runtime: Optional[RuntimeLeader] = None,
              model: str = "") -> KetQuaKichHoat:
    """Nối lại nếu nối được; không thì dựng phiên mới + nạp bối cảnh có trần.

        phiên nối lại được?
            CÓ    -> nối lại
            KHÔNG -> dựng mới + hydrate từ nguồn BỀN

    Không có runtime (hoặc runtime chưa chứng minh được ở máy này) thì đánh
    dấu `UNVERIFIED` và vẫn trả về một phiên dùng được ở mức khái niệm —
    KHÔNG báo là đã nối. Giả vờ đã nối là cách một tầng trên tin rằng nó có
    ngữ cảnh mà thực ra không.
    """
    if model:
        phien.preferred_model = model
    if runtime is not None:
        phien.leader_runtime = getattr(runtime, "ten", "") or phien.leader_runtime

    if runtime is None or not runtime.san_sang():
        phien.session_status = TrangThaiPhien.UNVERIFIED
        return KetQuaKichHoat(
            phien=phien, can_nap_boi_canh=True,
            ly_do=("runtime Leader chưa chứng minh được ở máy này — KHÔNG "
                   "báo là đã nối; chạy bằng đường sẵn có và nạp bối cảnh "
                   "từ nguồn bền"))

    if phien.can_xoay and phien.session_ref:
        cu = phien.session_ref
        phien.session_ref = str(uuid.uuid4())
        phien.so_luot = 0
        ok = runtime.tao_phien(session_id=phien.session_ref,
                               model=phien.preferred_model)
        phien.session_status = (TrangThaiPhien.DANG_SONG if ok
                                else TrangThaiPhien.HONG)
        phien.last_seen = time.time()
        return KetQuaKichHoat(
            phien=phien, da_xoay=True, da_dung_moi=True,
            can_nap_boi_canh=True,
            ly_do=(f"phiên {cu[:8]} đã quá {TRAN_LUOT} lượt — xoay sang phiên "
                   f"mới và nạp lại từ điểm dừng"))

    if phien.noi_lai_duoc and runtime.noi_lai(session_id=phien.session_ref):
        phien.session_status = TrangThaiPhien.DANG_SONG
        phien.last_seen = time.time()
        return KetQuaKichHoat(
            phien=phien, da_noi_lai=True,
            ly_do=f"nối lại phiên {phien.session_ref[:8]} (bộ nhớ nóng còn dùng được)")

    cu = phien.session_ref
    phien.session_ref = str(uuid.uuid4())
    phien.so_luot = 0
    ok = runtime.tao_phien(session_id=phien.session_ref,
                           model=phien.preferred_model)
    phien.session_status = (TrangThaiPhien.DANG_SONG if ok
                            else TrangThaiPhien.HONG)
    phien.last_seen = time.time()
    return KetQuaKichHoat(
        phien=phien, da_dung_moi=True, can_nap_boi_canh=True,
        ly_do=("không nối lại được" + (f" phiên {cu[:8]}" if cu else "")
               + " — dựng phiên mới và nạp bối cảnh dự án có trần"))
