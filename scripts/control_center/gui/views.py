"""Bốn khung còn lại: Tasks / Agents / Logs / Usage.

Một quyết định chung cho cả bốn: dùng `QTableWidget` với ô CHỈ-ĐỌC thay vì
widget tự vẽ. Bảng của Qt cho sẵn chọn hàng bằng chuột, Ctrl+A, menu chuột
phải và cuộn bằng bánh xe. Tự vẽ thẻ trông đẹp hơn nhưng sẽ phải dựng lại
toàn bộ những thứ đó — và đó đúng là chỗ các app hay làm hỏng clipboard.

MỘT ĐÍNH CHÍNH đáng ghi lại: bản trước tệp này viết rằng Qt "cho sẵn Ctrl+C
copy hàng đang chọn". **Không đúng.** Qt6 copy `DisplayRole` của MỘT ô hiện
tại; chọn ba hàng rồi Ctrl+C vẫn ra một ô. Không bài kiểm nào bơm Ctrl+C
vào bảng nên câu sai đó sống sót tới lượt review đối kháng. Giờ có
`_BangCopyDuoc` cài `keyPressEvent` để Ctrl+C copy cả hàng, và có bài kiểm
bơm phím thật.

`Tasks` vẫn có phần "thẻ" theo yêu cầu: mỗi hàng mang huy hiệu trạng thái
có màu, và bấm vào hàng mở một panel chi tiết bên phải.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from scripts.control_center.gui.bridge import mo_ta_thoi_luong
from scripts.control_center.gui.widgets import (HuyHieu, KhoiMa, KhungNhatKy,
                                                VanBanChonDuoc, dat_clipboard,
                                                dat_van_ban_giu_chon,
                                                menu_copy)


def _bang(cot: List[str]) -> QTableWidget:
    """Bảng chỉ-đọc, chọn theo hàng, Ctrl+C copy CẢ HÀNG (xem `_BangCopyDuoc`)."""
    b = _BangCopyDuoc(0, len(cot))
    b.setHorizontalHeaderLabels(cot)
    b.setEditTriggers(QAbstractItemView.NoEditTriggers)   # chi doc...
    b.setSelectionBehavior(QAbstractItemView.SelectRows)  # ...nhung VAN chon duoc
    b.setSelectionMode(QAbstractItemView.ExtendedSelection)
    b.setAlternatingRowColors(True)
    b.verticalHeader().setVisible(False)
    b.setShowGrid(False)
    b.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    b.horizontalHeader().setStretchLastSection(True)
    b.setStyleSheet(
        "QTableWidget{border:1px solid #e2e6ee; border-radius:8px;}"
        "QTableWidget::item{padding:5px 8px;}"
        "QHeaderView::section{background:#f4f6fa; border:none;"
        "border-bottom:1px solid #e2e6ee; padding:6px 8px;"
        "font-weight:600; color:#4a5270;}")
    return b


def _o(text: str, *, tooltip: str = "") -> QTableWidgetItem:
    it = QTableWidgetItem(text or "")
    it.setToolTip(tooltip or text or "")
    return it


def _o_text(b: QTableWidget, r: int, c: int) -> str:
    """Chữ của một ô, KỂ CẢ khi ô đó là một widget chứ không phải item.

    Cột "Trạng thái" và cột "Usage" dùng `setCellWidget(HuyHieu)` để có màu,
    nên `b.item(r, c)` trả `None` ở đó. Bản trước chỉ đọc `item()`, nên
    "Copy hàng đang chọn" và "Copy All" dán ra một bảng **thiếu đúng cột
    quan trọng nhất** — state ở bảng Tasks, và mức tin cậy ở bảng Agents,
    tức là cột mà bất biến "không bịa số usage" đang bảo vệ. Mất dữ liệu
    âm thầm: header vẫn ghi tên cột, giá trị thì rỗng.
    """
    it = b.item(r, c)
    if it is not None:
        return it.text()
    w = b.cellWidget(r, c)
    if w is not None:
        # `HuyHieu` la mot QLabel; lay `text()` neu co.
        lay = getattr(w, "text", None)
        if callable(lay):
            return lay() or ""
    return ""


def _copy_bang(b: QTableWidget) -> str:
    """Văn bản của các hàng đang chọn, dạng TSV — dán được vào Excel."""
    hang = sorted({i.row() for i in b.selectedIndexes()})
    if not hang:
        hang = list(range(b.rowCount()))
    dong = ["\t".join(b.horizontalHeaderItem(c).text()
                      for c in range(b.columnCount()))]
    for r in hang:
        dong.append("\t".join(_o_text(b, r, c)
                              for c in range(b.columnCount())))
    return "\n".join(dong)


class _BangCopyDuoc(QTableWidget):
    """Bảng mà **Ctrl+C copy CẢ HÀNG**, không phải một ô.

    Qt6 mặc định cho Ctrl+C trên `QTableWidget` copy đúng `DisplayRole` của
    MỘT ô hiện tại — chọn ba hàng rồi Ctrl+C vẫn ra một ô. Tài liệu của bản
    trước nói ngược lại, và không bài kiểm nào bơm Ctrl+C vào bảng nên
    khoảng cách đó không bị bắt.

    Cài ở `keyPressEvent` chứ KHÔNG bằng `QShortcut`: một shortcut Ctrl+C
    (dù ở phạm vi cửa sổ) sẽ giành mất Ctrl+C của mọi ô văn bản chỉ-đọc
    khác trong cùng cửa sổ. Xử lý tại widget thì chỉ tác dụng khi chính
    bảng đang có focus, và mọi phím khác vẫn xuống `super()`.
    """

    def keyPressEvent(self, e):                             # noqa: N802
        if (e.key() == Qt.Key_C and (e.modifiers() & Qt.ControlModifier)
                and not (e.modifiers() & Qt.ShiftModifier)):
            dat_clipboard(_copy_bang(self))
            e.accept()
            return
        super().keyPressEvent(e)


def _thanh_copy(b: QTableWidget, nhan: str) -> QWidget:
    """Thanh nút Copy cho một bảng — đường cho người không dùng lối tắt."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    t = QLabel(nhan)
    t.setStyleSheet("color:#4a5270; font-weight:600;")
    h.addWidget(t)
    h.addStretch(1)
    n1 = QPushButton("Copy hàng đang chọn")
    n1.setCursor(Qt.PointingHandCursor)
    n1.setToolTip("Sao chép các hàng đang chọn (dạng TSV, dán được vào Excel)")
    n1.clicked.connect(lambda: dat_clipboard(_copy_bang(b)))
    h.addWidget(n1)
    n2 = QPushButton("Copy All")
    n2.setCursor(Qt.PointingHandCursor)
    n2.setToolTip("Sao chép toàn bộ bảng")
    n2.clicked.connect(lambda: (b.selectAll(), dat_clipboard(_copy_bang(b)),
                                b.clearSelection()))
    h.addWidget(n2)
    menu_copy(b, lambda: _copy_bang(b))
    return w


class KhungViec(QWidget):
    """Tasks: bảng + panel chi tiết. Bấm một hàng để mở chi tiết."""

    mo_log = Signal(str)

    COT = ["Việc", "Trạng thái", "Agent", "Thời lượng", "Ưu tiên",
           "Phụ thuộc", "Worktree", "Cập nhật"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._viec: Dict[str, Dict] = {}
        self._dang_chon = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        self.bang = _bang(self.COT)
        # Be rong ban dau: cot "Viec" phai du rong de KHONG cat ten viec.
        # Mac dinh cua Qt chia deu, nen "Backend wiring" ra "Backend ..." —
        # ten viec la thu nguoi dung quet mat de tim, cat no la lam mat
        # chinh cong nang cua bang. Nguoi dung van keo lai duoc (Interactive).
        for cot, rong in ((0, 210), (1, 96), (2, 110), (3, 92), (4, 62),
                          (5, 78), (6, 120)):
            self.bang.setColumnWidth(cot, rong)
        self.bang.itemSelectionChanged.connect(self._doi_chon)
        v.addWidget(_thanh_copy(self.bang, "Việc trong dự án"))

        chia = QSplitter(Qt.Horizontal)
        chia.addWidget(self.bang)
        self.chi_tiet = _PanelChiTietViec()
        self.chi_tiet.mo_log.connect(self.mo_log.emit)
        chia.addWidget(self.chi_tiet)
        chia.setSizes([680, 380])
        v.addWidget(chia, 1)

    def cap_nhat(self, d: Dict) -> None:
        ds = d.get("tasks") or []
        self._viec = {t.get("task_id"): t for t in ds}
        gio = time.time()
        # Giu lai hang dang chon qua moi lan ve lai.
        self.bang.setRowCount(len(ds))
        for r, t in enumerate(ds):
            self.bang.setItem(r, 0, _o(t.get("title") or t.get("task_id"),
                                       tooltip=t.get("objective") or ""))
            hh = HuyHieu(t.get("state", "?"))
            self.bang.setCellWidget(r, 1, hh)
            self.bang.setItem(r, 2, _o(t.get("owner_session") or "—"))
            self.bang.setItem(r, 3, _o(mo_ta_thoi_luong(
                t.get("started_at"), t.get("ended_at"), bay_gio=gio) or "—"))
            self.bang.setItem(r, 4, _o(str(t.get("priority", ""))))
            dep = t.get("dependencies") or []
            self.bang.setItem(r, 5, _o(f"{len(dep)}" if dep else "—",
                                       tooltip="\n".join(dep)))
            wt = t.get("worktree") or ""
            self.bang.setItem(r, 6, _o(wt.rsplit("\\", 1)[-1] if wt else "—",
                                       tooltip=wt))
            self.bang.setItem(r, 7, _o(_gio(t.get("updated_at"))))
            self.bang.item(r, 0).setData(Qt.UserRole, t.get("task_id"))
        if self._dang_chon in self._viec:
            self.chi_tiet.dat(self._viec[self._dang_chon])

    def _doi_chon(self) -> None:
        hang = self.bang.currentRow()
        if hang < 0 or self.bang.item(hang, 0) is None:
            return
        tid = self.bang.item(hang, 0).data(Qt.UserRole)
        self._dang_chon = tid or ""
        if self._dang_chon in self._viec:
            self.chi_tiet.dat(self._viec[self._dang_chon])


def _gio(ts) -> str:
    if not ts:
        return "—"
    return time.strftime("%H:%M:%S", time.localtime(float(ts)))


class _PanelChiTietViec(QFrame):
    """Panel chi tiết một việc, kèm nút điều khiển và nút mở nhật ký."""

    mo_log = Signal(str)
    tam_dung = Signal(str)
    tiep_tuc = Signal(str)
    dung_lai = Signal(str)
    duyet = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tid = ""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "_PanelChiTietViec{background:#fbfbfd;"
            "border:1px solid #e2e6ee; border-radius:8px;}")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 12, 12, 12)
        self.v.setSpacing(8)

        self.ten = QLabel("Chọn một việc để xem chi tiết")
        self.ten.setWordWrap(True)
        self.ten.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ten.setStyleSheet("font-size:13px; font-weight:700; color:#1b2340;")
        self.v.addWidget(self.ten)

        self.hh = HuyHieu("")
        self.hh.setVisible(False)
        self.v.addWidget(self.hh, 0, Qt.AlignLeft)

        self.o = VanBanChonDuoc()
        self.o.setMinimumHeight(160)
        self.v.addWidget(self.o, 1)

        thanh = QHBoxLayout()
        for nhan, sig, tip in (
                ("Tạm dừng", self.tam_dung, "Dừng việc sau lượt hiện tại"),
                ("Tiếp tục", self.tiep_tuc, "Cho việc chạy lại"),
                ("Dừng", self.dung_lai, "Dừng hẳn việc này"),
                ("Nhật ký", None, "Mở nhật ký đầy đủ của việc")):
            n = QPushButton(nhan)
            n.setCursor(Qt.PointingHandCursor)
            n.setToolTip(tip)
            if sig is None:
                n.clicked.connect(lambda: self.mo_log.emit(self._tid))
            else:
                n.clicked.connect(
                    lambda _=False, s=sig: s.emit(self._tid))
            thanh.addWidget(n)
        self.v.addLayout(thanh)

        self.nut_duyet = QPushButton("Duyệt cổng GATED…")
        self.nut_duyet.setVisible(False)
        self.nut_duyet.setCursor(Qt.PointingHandCursor)
        self.nut_duyet.setStyleSheet(
            "QPushButton{background:#8a1c1c; color:white; border:none;"
            "border-radius:6px; padding:7px 12px; font-weight:600;}")
        self.nut_duyet.clicked.connect(lambda: self.duyet.emit(self._tid))
        self.v.addWidget(self.nut_duyet)

    def dat(self, t: Dict) -> None:
        self._tid = t.get("task_id") or ""
        self.ten.setText(t.get("title") or self._tid)
        self.hh.setVisible(True)
        self.hh.dat(t.get("state", "?"))
        dong = [
            f"mã việc   : {self._tid}",
            f"trạng thái: {t.get('state')}",
            f"quyền     : {t.get('permission') or '—'}",
            f"ưu tiên   : {t.get('priority')}",
            f"phiên     : {t.get('owner_session') or '—'}",
            f"worktree  : {t.get('worktree') or '—'}",
            f"nhánh     : {t.get('branch') or '—'}",
            f"lượt thử  : {t.get('attempts')}",
            f"phụ thuộc : {', '.join(t.get('dependencies') or []) or '—'}",
            "",
            "MỤC TIÊU",
            (t.get("objective") or "—"),
        ]
        if t.get("gate_reason"):
            dong += ["", "CỔNG", t["gate_reason"]]
        if t.get("blocked_reason"):
            dong += ["", "ĐANG CHỜ BẠN", t["blocked_reason"]]
        # GIU vung dang boi den: panel nay ve lai moi giay, va ghi tho
        # bang `setPlainText` xoa vung chon nguoi dung vua boi de bam
        # Ctrl+C. Do la mot loi CLIPBOARD, du trong nhu loi hieu nang.
        dat_van_ban_giu_chon(self.o, "\n".join(dong))
        self.nut_duyet.setVisible(t.get("state") == "BLOCKED")


class KhungAgent(QWidget):
    """Agents: phiên thật, kèm mức tin cậy usage — không bịa số."""

    COT = ["Provider", "Phiên", "Trạng thái", "Việc hiện tại",
           "Thời lượng", "Hoạt động cuối", "Worktree", "Usage"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        self.bang = _bang(self.COT)
        v.addWidget(_thanh_copy(self.bang, "Phiên agent"))
        v.addWidget(self.bang, 1)
        self.ghi_chu = QLabel(
            "Usage chỉ hiện ACTUAL khi nhà cung cấp trả số đọc được bằng "
            "máy. Không đo được thì ghi UNAVAILABLE — không suy ra 0.")
        self.ghi_chu.setWordWrap(True)
        self.ghi_chu.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ghi_chu.setStyleSheet("color:#69708a; font-size:11px;")
        v.addWidget(self.ghi_chu)

    def cap_nhat(self, d: Dict, *, usage_theo_runtime: Optional[Dict] = None) -> None:
        ds = d.get("sessions") or []
        gio = time.time()
        self.bang.setRowCount(len(ds))
        for r, s in enumerate(ds):
            nha = s.get("provider") or "—"
            rt = s.get("runtime_id") or ""
            self.bang.setItem(r, 0, _o(f"{nha}" + (f" · {rt}" if rt else "")))
            self.bang.setItem(r, 1, _o(s.get("session_id") or "—",
                                       tooltip=f"pid={s.get('pid') or '—'}"))
            self.bang.setCellWidget(r, 2, HuyHieu(s.get("state", "?")))
            self.bang.setItem(r, 3, _o(s.get("current_task") or "—"))
            self.bang.setItem(r, 4, _o(mo_ta_thoi_luong(
                s.get("created_at"), bay_gio=gio) or "—"))
            self.bang.setItem(r, 5, _o(_gio(s.get("last_activity"))))
            wt = s.get("worktree") or ""
            self.bang.setItem(r, 6, _o(wt.rsplit("\\", 1)[-1] if wt else "—",
                                       tooltip=wt))
            u = (usage_theo_runtime or {}).get(rt)
            self.bang.setCellWidget(
                r, 7, HuyHieu(u if u else "UNAVAILABLE"))


class KhungLog(QWidget):
    """Logs: văn bản chọn được, Copy / Copy All, lọc, theo dõi."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tid = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        dau = QHBoxLayout()
        self.nhan = QLabel("Nhật ký — chọn một việc ở khung Tasks")
        self.nhan.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.nhan.setStyleSheet("color:#4a5270; font-weight:600;")
        dau.addWidget(self.nhan)
        dau.addStretch(1)
        v.addLayout(dau)

        self.nk = KhungNhatKy()
        v.addWidget(self.nk, 1)

    def dat_viec(self, task_id: str, tho: str) -> None:
        self._tid = task_id
        self.nhan.setText(f"Nhật ký · {task_id}" if task_id
                          else "Nhật ký — chọn một việc ở khung Tasks")
        self.nk.dat_van_ban(tho)

    def task_id(self) -> str:
        return self._tid


class KhungUsage(QWidget):
    """Usage: đọc được cho người, và KHÔNG bịa độ chính xác."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        self.tom = QLabel("")
        self.tom.setWordWrap(True)
        self.tom.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.tom.setStyleSheet("color:#2b3350; font-size:12px;")
        v.addWidget(self.tom)

        self.bang = _bang(["Hạng mục", "Giá trị", "Đơn vị", "Mức tin cậy",
                           "Ghi chú"])
        v.addWidget(_thanh_copy(self.bang, "Usage"))
        v.addWidget(self.bang, 1)

        self.giai_thich = QLabel(
            "ACTUAL = số nhà cung cấp trả về, đọc được bằng máy.  "
            "ESTIMATED = suy ra từ hoạt động cục bộ, có thể lệch.  "
            "UNAVAILABLE = không có cách đọc — cố ý để trống, không ghi 0.")
        self.giai_thich.setWordWrap(True)
        self.giai_thich.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.giai_thich.setStyleSheet("color:#69708a; font-size:11px;")
        v.addWidget(self.giai_thich)

    def cap_nhat(self, bc: Dict) -> None:
        if bc.get("error"):
            self.tom.setText(f"Không đọc được usage: {bc['error']}")
        ms = bc.get("metrics") or []
        self.bang.setRowCount(len(ms))
        dem = {"ACTUAL": 0, "ESTIMATED": 0, "UNAVAILABLE": 0}
        for r, m in enumerate(ms):
            tin = (m.get("confidence") or "UNAVAILABLE").upper()
            dem[tin] = dem.get(tin, 0) + 1
            self.bang.setItem(r, 0, _o(m.get("label") or "—"))
            gt = m.get("value")
            self.bang.setItem(r, 1, _o("—" if gt is None else str(gt)))
            self.bang.setItem(r, 2, _o(m.get("unit") or ""))
            self.bang.setCellWidget(r, 3, HuyHieu(tin))
            self.bang.setItem(r, 4, _o(m.get("note") or ""))
        if not bc.get("error"):
            self.tom.setText(
                f"{len(ms)} hạng mục — {dem.get('ACTUAL', 0)} ACTUAL, "
                f"{dem.get('ESTIMATED', 0)} ESTIMATED, "
                f"{dem.get('UNAVAILABLE', 0)} UNAVAILABLE.")


class HopTroGiup(QWidget):
    """Nội dung trợ giúp. Đặt trong `HopThoai` nên có X + Esc sẵn."""

    NOI_DUNG = """Router Control Center — dùng bằng CHUỘT

Bạn không cần nhớ phím nào. Mọi việc đều có nút.

  Chat     Gõ mục tiêu vào ô dưới, bấm Gửi. Router tự phân rã thành
           việc, chọn agent, dựng worktree, chạy, báo cáo.
           "Thêm ngữ cảnh…" chèn đường dẫn tệp vào yêu cầu.
  Tasks    Bảng mọi việc. Bấm một hàng để xem chi tiết bên phải, kèm
           nút Tạm dừng / Tiếp tục / Dừng / Nhật ký.
  Agents   Phiên agent thật đang chạy, provider, việc, thời lượng.
  Logs     Nhật ký đầy đủ. Bôi đen bằng chuột rồi Ctrl+C, hoặc bấm
           Copy / Copy All. Có ô lọc và nút Theo dõi.
  Usage    Số usage kèm mức tin cậy ACTUAL / ESTIMATED / UNAVAILABLE.

Việc chạm lớp GATED (deploy production, đổi quyền, chạm bí mật) KHÔNG
tự chạy. Nó dừng ở BLOCKED và chờ bạn bấm Duyệt — đúng như vậy là cố ý.

Clipboard hoạt động như mọi app Windows khác: bôi đen bằng chuột,
Ctrl+C để copy, Ctrl+V để dán vào ô soạn, chuột phải có Copy/Paste.
Ứng dụng này KHÔNG chiếm các tổ hợp đó.

Lối tắt (tuỳ chọn, không bắt buộc):
  Ctrl+Enter   gửi tin trong ô soạn
  Esc          đóng hộp thoại đang mở
"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        km = KhoiMa(self.NOI_DUNG, tieu_de="hướng dẫn")
        # `KhoiMa` gioi han cao 220px cho khoi ma trong chat. Trong hop thoai
        # tro giup thi gioi han do de lai mot dai trong lon o tren, nen noi
        # ra cho het hop.
        km.o.setMaximumHeight(16777215)
        v.addWidget(km)
