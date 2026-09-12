"""MÁY TRẠNG THÁI của một lần thực thi — V0.9, §5.

VÌ SAO KHÔNG DÙNG LẠI `TaskState`: `TaskState` là vòng đời của MỘT việc mà
một agent chạy. Một lần thực thi sống lâu hơn thế — nó có kế hoạch, có nhiều
việc con, có một cổng thẩm quyền, có một pha kiểm định, và có thể lập lại kế
hoạch rồi chạy tiếp. Nhồi `VERIFYING`/`REPLANNING`/`WAITING_AUTHORITY` vào
enum của việc sẽ làm hỏng đúng thứ `model.TaskState` đang làm tốt (trả lời
"có việc nào đang chờ TÔI không?").

MỘT LUẬT KHÔNG ĐƯỢC PHÁ, và nó là lý do tệp này tồn tại:

    KHÔNG CÓ `RUNNING -> DONE`.

Mọi đường tới `DONE` đi qua `VERIFYING`. Yêu cầu §5 viết thẳng: *"No task may
silently jump RUNNING -> DONE without result/evidence."* Khoá điều đó bằng
bảng chuyển thay vì bằng quy ước — một quy ước sẽ bị một `doi_trang_thai(...,
force=True)` lúc 2 giờ sáng đi vòng qua, còn một bảng thì ném.

TRẠNG THÁI KẾT THÚC PHẢI NHẢ TÀI NGUYÊN. `KET_THUC` ở đây là danh sách mà
`dieu_phoi.py` dùng để gọi `LockManager.tra`; thêm một trạng thái kết thúc mà
quên thêm vào đây là để lại một khoá treo tới hết TTL.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class TrangThaiThucThi(str, Enum):
    """Mười một trạng thái. Giá trị là thứ đi vào sổ, API và giao diện."""

    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    WAITING_AUTHORITY = "WAITING_AUTHORITY"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    REPLANNING = "REPLANNING"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def ket_thuc(self) -> bool:
        return self in KET_THUC

    @property
    def dang_chay(self) -> bool:
        """Đang CHIẾM tài nguyên (việc con đang bay, hoặc đang kiểm định)."""
        return self in (TrangThaiThucThi.RUNNING, TrangThaiThucThi.VERIFYING)

    @property
    def can_nguoi(self) -> bool:
        return self in (TrangThaiThucThi.WAITING_AUTHORITY,
                        TrangThaiThucThi.BLOCKED)

    @property
    def nhan(self) -> str:
        return _NHAN[self]


#: Trạng thái KẾT THÚC. `dieu_phoi.nha_tai_nguyen` đọc đúng tập này.
KET_THUC: FrozenSet[TrangThaiThucThi] = frozenset({
    TrangThaiThucThi.DONE, TrangThaiThucThi.FAILED,
    TrangThaiThucThi.CANCELLED})

_NHAN: Dict[TrangThaiThucThi, str] = {
    TrangThaiThucThi.DRAFT: "nháp",
    TrangThaiThucThi.PLANNED: "đã lập kế hoạch",
    TrangThaiThucThi.WAITING_AUTHORITY: "chờ bạn cho phép",
    TrangThaiThucThi.READY: "sẵn sàng chạy",
    TrangThaiThucThi.RUNNING: "đang chạy",
    TrangThaiThucThi.VERIFYING: "đang kiểm định",
    TrangThaiThucThi.REPLANNING: "đang lập lại kế hoạch",
    TrangThaiThucThi.BLOCKED: "bị chặn — cần người",
    TrangThaiThucThi.PAUSED: "tạm dừng",
    TrangThaiThucThi.DONE: "xong",
    TrangThaiThucThi.FAILED: "hỏng",
    TrangThaiThucThi.CANCELLED: "đã huỷ",
}

T = TrangThaiThucThi

#: Bảng chuyển HỢP LỆ. Đọc theo dòng: "từ X đi được tới…".
#:
#: `DRAFT` không đi thẳng `READY` được: một lần thực thi không có kế hoạch
#: thì không có gì để chạy, và `PLANNED` là chỗ duy nhất DAG được kiểm.
#:
#: `FAILED -> REPLANNING` có, và nó KHÔNG phải sự rộng rãi: nó là đường thử
#: lại THỦ CÔNG (người bấm), cùng khuôn `TaskState.FAILED -> QUEUED`. Tự
#: động thì không đi đường này — `phuc_hoi.py` đi `VERIFYING -> REPLANNING`
#: và có trần.
_CHUYEN: Dict[TrangThaiThucThi, FrozenSet[TrangThaiThucThi]] = {
    T.DRAFT: frozenset({T.PLANNED, T.CANCELLED, T.FAILED}),
    T.PLANNED: frozenset({T.WAITING_AUTHORITY, T.READY, T.REPLANNING,
                          T.BLOCKED, T.CANCELLED, T.FAILED}),
    T.WAITING_AUTHORITY: frozenset({T.READY, T.BLOCKED, T.REPLANNING,
                                    T.CANCELLED, T.FAILED}),
    T.READY: frozenset({T.RUNNING, T.WAITING_AUTHORITY, T.PAUSED, T.BLOCKED,
                        T.REPLANNING, T.CANCELLED, T.FAILED}),
    # KHONG CO `RUNNING -> DONE`. Xem docstring module.
    #
    # `RUNNING -> REPLANNING` thi CO, va no khong mau thuan: mot buoc hong
    # giua chung co the chung minh KE HOACH sai chu khong phai buoc sai, va
    # bat no di vong qua VERIFYING truoc se bao "kiem dinh" mot thu chua
    # chay xong. Nhung buoc con dang bay duoc doi soat o nhip sau.
    T.RUNNING: frozenset({T.VERIFYING, T.REPLANNING, T.WAITING_AUTHORITY,
                          T.PAUSED, T.BLOCKED, T.CANCELLED, T.FAILED}),
    T.VERIFYING: frozenset({T.DONE, T.REPLANNING, T.BLOCKED,
                            T.WAITING_AUTHORITY, T.CANCELLED, T.FAILED}),
    T.REPLANNING: frozenset({T.PLANNED, T.READY, T.WAITING_AUTHORITY,
                             T.BLOCKED, T.CANCELLED, T.FAILED}),
    T.BLOCKED: frozenset({T.READY, T.WAITING_AUTHORITY, T.REPLANNING,
                          T.PAUSED, T.CANCELLED, T.FAILED}),
    T.PAUSED: frozenset({T.READY, T.RUNNING, T.BLOCKED, T.CANCELLED,
                         T.FAILED}),
    T.DONE: frozenset(),
    T.FAILED: frozenset({T.REPLANNING}),
    T.CANCELLED: frozenset(),
}


class ChuyenTrangThaiLoi(ValueError):
    """Chuyển trạng thái không hợp lệ. Ném NGAY, không âm thầm bỏ qua."""


def co_the_chuyen(cu: TrangThaiThucThi, moi: TrangThaiThucThi) -> bool:
    return moi is cu or moi in _CHUYEN.get(cu, frozenset())


def kiem_chuyen(execution_id: str, cu: TrangThaiThucThi,
                moi: TrangThaiThucThi) -> None:
    if co_the_chuyen(cu, moi):
        return
    di_duoc = sorted(x.value for x in _CHUYEN.get(cu, frozenset()))
    them = ""
    if cu is T.RUNNING and moi is T.DONE:
        them = (" — `RUNNING -> DONE` bị CẤM CỨNG: mọi đường tới DONE phải "
                "đi qua VERIFYING, vì mã thoát 0 không phải bằng chứng.")
    raise ChuyenTrangThaiLoi(
        f"{execution_id}: {cu.value} -> {moi.value} không hợp lệ. Từ "
        f"{cu.value} chỉ đi được tới {di_duoc}.{them}")


def cac_chuyen_hop_le(cu: TrangThaiThucThi) -> FrozenSet[TrangThaiThucThi]:
    return _CHUYEN.get(cu, frozenset())
