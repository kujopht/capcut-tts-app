"""Nối giao diện với `ControlCenter` đã phát hành. KHÔNG có logic điều phối.

Đây là toàn bộ bề mặt mà giao diện được phép chạm tới backend. Giữ nó hẹp
là có chủ đích: nếu widget nào cũng gọi thẳng `engine`, thì logic điều phối
sẽ từ từ rỉ vào tầng vẽ, và bản V0.1 đã chứng minh (bằng 6 lỗi review đối
kháng) rằng điều phối là chỗ sai đắt nhất.

HAI THỨ TẦNG NÀY THẬT SỰ GIẢI QUYẾT:

1. **Không chặn luồng giao diện.** `chat()` gọi bộ phân rã, và bộ phân rã
   có thể gọi ra model thật. Chạy nó trên luồng UI thì cửa sổ đóng băng
   giữa lúc người dùng vừa bấm Send. Nên nó đi qua `QThreadPool`.
2. **Một nguồn sự thật.** Giao diện KHÔNG giữ trạng thái riêng; nó vẽ lại
   từ `snapshot()`. Sổ SQLite của V0.1 vẫn là nguồn duy nhất, nên mở app
   hai lần, hay mở TUI cạnh GUI, đều thấy cùng một thứ.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import (QObject, QRunnable, QThreadPool, QTimer, Signal,
                            Slot)

from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project

#: Nhip lam moi giao dien. 1s la du: sổ nằm trên đĩa cục bộ và `snapshot()`
#: chỉ đọc, không gọi mạng (xem docstring của nó). Nhanh hơn nữa chỉ đốt
#: CPU mà mắt người không thấy khác.
NHIP_MS = 1000


class _Viec(QRunnable):
    """Chạy một hàm trên luồng nền, trả kết quả/lỗi qua callback."""

    def __init__(self, ham: Callable, xong: Callable, hong: Callable):
        super().__init__()
        self._ham, self._xong, self._hong = ham, xong, hong

    @Slot()
    def run(self) -> None:                                  # pragma: no cover
        try:
            kq = self._ham()
        except Exception as exc:                            # noqa: BLE001
            # KHONG de ngoai le chet lang: mot loi backend phai hien ra o
            # giao dien, khong phai chi in ra stderr roi mat.
            self._hong(exc)
            return
        self._xong(kq)


class Cau(QObject):
    """Cầu nối giữa cửa sổ và `ControlCenter`.

    Tín hiệu là cách duy nhất giao diện biết có gì mới; không widget nào
    được tự gọi `store` để đọc thêm.
    """

    #: Ảnh chụp mới của dự án đang mở.
    anh_chup = Signal(dict)
    #: Một thao tác nền đã xong (`chat`, `pause`, ...) — kèm mô tả ngắn.
    xong_viec = Signal(str)
    #: Một thao tác nền hỏng — kèm thông điệp đọc được cho người dùng.
    co_loi = Signal(str)
    #: Đang chạy một thao tác nền hay không (để bật/tắt nút Send).
    dang_lam = Signal(bool)

    def __init__(self, *, root: Optional[Path] = None,
                 cc: Optional[ControlCenter] = None,
                 max_parallel: int = 3, parent: Optional[QObject] = None):
        super().__init__(parent)
        # Cho phép tiêm `cc` để bài kiểm dùng một backend giả/tạm mà không
        # phải dựng thư mục thật.
        self.cc = cc if cc is not None else ControlCenter(
            root=root, max_parallel=max_parallel)
        self._pool = QThreadPool.globalInstance()
        self._dang = 0
        self._pid = ""
        self._dong_ho = QTimer(self)
        self._dong_ho.setInterval(NHIP_MS)
        self._dong_ho.timeout.connect(self.lam_moi)

    # -- vong doi ------------------------------------------------------------

    def bat_dau(self) -> None:
        """Chạy vòng điều phối của backend + bắt đầu làm mới giao diện."""
        self.cc.start()
        self._dong_ho.start()
        self.lam_moi()

    def dung(self) -> None:
        self._dong_ho.stop()
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass

    # -- doc -----------------------------------------------------------------

    @property
    def project_id(self) -> str:
        return self._dam_bao_pid()

    def cac_project(self) -> List[Project]:
        return self.cc.projects()

    def chon_project(self, project_id: str) -> None:
        self._pid = project_id
        self.lam_moi()

    def _dam_bao_pid(self) -> str:
        """Mã dự án đang mở, tự phân giải nếu chưa có.

        Phải là MỘT chỗ duy nhất. Bản đầu chỉ phân giải trong `lam_moi()`,
        nên `gui_chat()` đọc `self._pid` khi nó còn rỗng và gửi tin vào dự
        án `""` — tin nhắn ghi vào một dự án không tồn tại, im lặng. Bài
        kiểm giao diện bắt được vì nó vẽ cửa sổ mà không chạy đồng hồ làm
        mới, đúng như một lần khởi động chậm ngoài đời.
        """
        if not self._pid:
            ps = self.cc.projects()
            self._pid = ps[0].project_id if ps else ""
        return self._pid

    @Slot()
    def lam_moi(self) -> None:
        """Đọc sổ và phát ảnh chụp. Chỉ đọc — không gọi mạng."""
        try:
            self._dam_bao_pid()
            d = self.cc.snapshot(self._pid)
        except Exception as exc:                            # noqa: BLE001
            self.co_loi.emit(f"không đọc được sổ: {exc}")
            return
        self.anh_chup.emit(d)

    def log_viec(self, task_id: str) -> str:
        try:
            return self.cc.log_cua_viec(task_id)
        except Exception as exc:                            # noqa: BLE001
            return f"không đọc được nhật ký: {exc}"

    def bao_cao_usage(self) -> Dict:
        """Usage cho khung Usage. Không bịa số: nhãn đi kèm giá trị."""
        try:
            return self.cc.usage.report(self._pid)
        except Exception as exc:                            # noqa: BLE001
            return {"error": str(exc), "metrics": []}

    # -- ghi (chay tren luong nen) -------------------------------------------

    def _nen(self, ham: Callable, nhan: str) -> None:
        self._dang += 1
        self.dang_lam.emit(True)

        def xong(_kq):
            self._giam()
            self.xong_viec.emit(nhan)

        def hong(exc):
            self._giam()
            self.co_loi.emit(f"{nhan} hỏng: {type(exc).__name__}: {exc}")

        self._pool.start(_Viec(ham, xong, hong))

    def _giam(self) -> None:
        self._dang = max(0, self._dang - 1)
        if self._dang == 0:
            self.dang_lam.emit(False)
        # Lam moi ngay sau khi mot thao tac xong, dung cho het nhip 1s:
        # nguoi vua bam nut thi phai thay ket qua ngay.
        QTimer.singleShot(0, self.lam_moi)

    def gui_chat(self, text: str) -> None:
        pid = self._dam_bao_pid()
        if not pid:
            # FAIL CLOSED: khong co du an thi KHONG ghi tin vao du an "".
            self.co_loi.emit("chưa có dự án nào — thêm một dự án trước khi gửi")
            return
        self._nen(lambda: self.cc.chat(pid, text), "gửi yêu cầu")

    def tam_dung(self, task_id: str) -> None:
        self._nen(lambda: self.cc.pause(task_id), f"tạm dừng {task_id}")

    def tiep_tuc(self, task_id: str) -> None:
        self._nen(lambda: self.cc.resume(task_id), f"tiếp tục {task_id}")

    def dung_viec(self, task_id: str) -> None:
        self._nen(lambda: self.cc.stop(task_id), f"dừng {task_id}")

    def duyet_gated(self, task_id: str) -> None:
        self._nen(lambda: self.cc.mo_khoa_gated(task_id),
                  f"duyệt cổng {task_id}")

    def them_project(self, project_id: str, name: str, repo_path: str) -> None:
        p = Project(project_id=project_id, name=name, repo_path=repo_path)
        self._nen(lambda: self.cc.them_project(p), f"thêm dự án {project_id}")


def gop_ke_hoach(chat_meta: Dict, viec_theo_id: Dict[str, Dict]) -> List[Dict]:
    """Ghép kế hoạch trong tin nhắn router với TRẠNG THÁI SỐNG của việc.

    Tin nhắn chat là ảnh chụp lúc phân rã: nó biết cây việc nhưng không biết
    bây giờ việc nào đang chạy. Trạng thái sống nằm ở bảng `tasks`. Hàm này
    nối hai thứ đó bằng `task_ids` để vẽ được đúng cái người dùng muốn thấy:

        Đã nhận mục tiêu
        ├─ Backend wiring        RUNNING · AG01/claude
        ├─ Artwork integration   QUEUED
        └─ Production proof      BLOCKED — chờ bạn duyệt

    Trả danh sách hàng đã sẵn sàng để vẽ; không chạm Qt để bài kiểm gọi
    được trực tiếp.
    """
    ids = list((chat_meta or {}).get("task_ids") or [])
    ke = (chat_meta or {}).get("plan") or {}
    tieu_de = {t.get("task_id"): t.get("title", "")
               for t in (ke.get("tasks") or [])}
    hang: List[Dict] = []
    for i, tid in enumerate(ids):
        t = viec_theo_id.get(tid) or {}
        # Tieu de: uu tien ban SONG (nguoi dung co the da doi), roi den ban
        # trong ke hoach, cuoi cung la chinh id.
        nhan = t.get("title") or tieu_de.get(tid) or tieu_de.get(
            tid.split(".", 1)[-1]) or tid
        hang.append({
            "task_id": tid,
            "title": nhan,
            "state": t.get("state") or "?",
            "agent": t.get("owner_session") or "",
            "permission": t.get("permission") or "",
            "blocked_reason": t.get("blocked_reason") or "",
            "cuoi": i == len(ids) - 1,
        })
    return hang


def mo_ta_thoi_luong(bat_dau: Optional[float], ket_thuc: Optional[float] = None,
                     *, bay_gio: Optional[float] = None) -> str:
    """`1m 12s` — thời lượng đọc được, không phải dấu thời gian thô.

    Trả `""` khi chưa bắt đầu: một việc chưa chạy thì không có thời lượng,
    và in `0s` sẽ nói sai rằng nó vừa chạy xong tức thì.
    """
    if not bat_dau:
        return ""
    het = ket_thuc or bay_gio or time.time()
    giay = max(0, int(het - bat_dau))
    if giay < 60:
        return f"{giay}s"
    phut, giay = divmod(giay, 60)
    if phut < 60:
        return f"{phut}m {giay:02d}s"
    gio, phut = divmod(phut, 60)
    return f"{gio}h {phut:02d}m"
