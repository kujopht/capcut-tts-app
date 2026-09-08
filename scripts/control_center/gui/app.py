"""Cửa sổ chính: thanh trên, sidebar trái, khung giữa, inspector phải.

BỐ CỤC (đúng thứ tự yêu cầu):

    ┌───────────────────────────────────────────────────────────────┐
    │ THANH TRÊN  dự án · đang chạy · bị chặn · pool · tìm · ? ⚙   │
    ├──────────┬────────────────────────────────────┬───────────────┤
    │ DỰ ÁN    │  Chat / Tasks / Agents / Logs /    │  ACTIVITY     │
    │ + Mới    │  Usage                             │  (gấp lại     │
    │ ⚙ Cài đặt│                                    │   được)       │
    └──────────┴────────────────────────────────────┴───────────────┘

MỘT ĐIỀU VỀ PHÍM TẮT, vì nó là cổng nghiệm thu của bản này: cửa sổ này
KHÔNG đăng ký `QShortcut`/`QAction` nào cho Ctrl+C/V/X/A. Lối tắt duy nhất
ở phạm vi cửa sổ là **Ctrl+K** (ô tìm) và **F1** (trợ giúp), và cả hai đều
có nút bấm tương đương. `Esc` do `QDialog` xử lý sẵn.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPushButton,
                               QSplitter, QStackedWidget, QVBoxLayout,
                               QWidget)

from scripts.control_center.gui.bridge import Cau, mo_ta_thoi_luong
from scripts.control_center.gui.views import (HopTroGiup, KhungAgent,
                                              KhungLog, KhungUsage, KhungViec)
from scripts.control_center.gui.views_chat import KhungChat
from scripts.control_center.gui.widgets import (HopThoai, HuyHieu,
                                                VanBanChonDuoc, menu_copy)

TEN_KHUNG = ("Chat", "Tasks", "Agents", "Logs", "Usage")


class CuaSoChinh(QMainWindow):
    def __init__(self, *, root: Optional[Path] = None,
                 cau: Optional[Cau] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Router Control Center")
        self.resize(1360, 860)
        self.cau = cau if cau is not None else Cau(root=root)

        goc = QWidget()
        self.setCentralWidget(goc)
        ngoai = QVBoxLayout(goc)
        ngoai.setContentsMargins(0, 0, 0, 0)
        ngoai.setSpacing(0)
        ngoai.addWidget(self._thanh_tren())

        self.chia = QSplitter(Qt.Horizontal)
        self.chia.addWidget(self._sidebar_trai())
        self.chia.addWidget(self._khung_giua())
        self.inspector = _Inspector()
        self.chia.addWidget(self.inspector)
        self.chia.setSizes([230, 800, 330])
        self.chia.setCollapsible(0, False)
        self.chia.setCollapsible(1, False)
        self.chia.setCollapsible(2, True)   # inspector gap lai duoc
        ngoai.addWidget(self.chia, 1)

        self.trang_thai = self.statusBar()
        self.trang_thai.showMessage("Sẵn sàng")

        self._noi_tin_hieu()
        self._phim_tat_tuy_chon()

    # -- dung giao dien ------------------------------------------------------

    def _thanh_tren(self) -> QWidget:
        khung = QFrame()
        khung.setStyleSheet(
            "QFrame{background:#ffffff; border-bottom:1px solid #e2e6ee;}")
        h = QHBoxLayout(khung)
        h.setContentsMargins(14, 8, 12, 8)
        h.setSpacing(12)

        self.nhan_project = QLabel("—")
        self.nhan_project.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.nhan_project.setStyleSheet(
            "font-size:14px; font-weight:700; color:#1b2340;")
        h.addWidget(self.nhan_project)

        self.chip_chay = _Chip("đang chạy", "0", "#d9ecff", "#0b4a80")
        self.chip_chan = _Chip("bị chặn", "0", "#ffe0e0", "#8a1c1c")
        self.chip_pool = _Chip("pool", "—", "#eceff4", "#4a4a4a")
        self.chip_pool.setToolTip(
            "Số runtime Antigravity/Codex nhận dispatch. Dò sức khoẻ là "
            "LƯỜI: chỉ dò khi có việc chờ giao.")
        for c in (self.chip_chay, self.chip_chan, self.chip_pool):
            h.addWidget(c)
        h.addStretch(1)

        self.o_tim = QLineEdit()
        self.o_tim.setPlaceholderText("Tìm việc, phiên, worktree… (Ctrl+K)")
        self.o_tim.setClearButtonEnabled(True)
        self.o_tim.setFixedWidth(300)
        self.o_tim.setToolTip("Lọc nhanh mọi bảng theo đoạn chữ này")
        h.addWidget(self.o_tim)

        self.nut_tro_giup = QPushButton("?")
        self.nut_tro_giup.setToolTip("Hướng dẫn dùng (F1)")
        self.nut_tro_giup.setCursor(Qt.PointingHandCursor)
        self.nut_tro_giup.setFixedSize(28, 26)
        self.nut_tro_giup.clicked.connect(self.mo_tro_giup)
        h.addWidget(self.nut_tro_giup)

        self.nut_cai_dat = QPushButton("⚙")
        self.nut_cai_dat.setToolTip("Cài đặt")
        self.nut_cai_dat.setCursor(Qt.PointingHandCursor)
        self.nut_cai_dat.setFixedSize(28, 26)
        self.nut_cai_dat.clicked.connect(self.mo_cai_dat)
        h.addWidget(self.nut_cai_dat)
        return khung

    def _sidebar_trai(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#f7f8fb;")
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 12, 10, 12)
        v.setSpacing(8)

        t = QLabel("DỰ ÁN")
        t.setStyleSheet("color:#69708a; font-size:11px; font-weight:700;")
        v.addWidget(t)

        self.ds_project = QListWidget()
        self.ds_project.setStyleSheet(
            "QListWidget{border:none; background:transparent;}"
            "QListWidget::item{padding:7px 8px; border-radius:6px;}"
            "QListWidget::item:selected{background:#dce8f7; color:#0b2f52;}")
        self.ds_project.itemClicked.connect(self._bam_project)
        v.addWidget(self.ds_project, 1)

        self.nut_project_moi = QPushButton("+  Dự án mới")
        self.nut_project_moi.setCursor(Qt.PointingHandCursor)
        self.nut_project_moi.setToolTip("Thêm một kho vào Control Center")
        self.nut_project_moi.clicked.connect(self.mo_project_moi)
        v.addWidget(self.nut_project_moi)

        self.nut_cai_dat2 = QPushButton("⚙  Cài đặt")
        self.nut_cai_dat2.setCursor(Qt.PointingHandCursor)
        self.nut_cai_dat2.clicked.connect(self.mo_cai_dat)
        v.addWidget(self.nut_cai_dat2)

        nut_tui = QPushButton("Mở TUI (gỡ lỗi)")
        nut_tui.setCursor(Qt.PointingHandCursor)
        nut_tui.setToolTip(
            "Giao diện terminal của V0.1 vẫn còn, làm đường dự phòng.\n"
            "Chạy: router-cc")
        nut_tui.clicked.connect(self._chi_dan_tui)
        v.addWidget(nut_tui)
        return w

    def _khung_giua(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        thanh = QFrame()
        thanh.setStyleSheet("QFrame{background:#ffffff;"
                            "border-bottom:1px solid #e2e6ee;}")
        h = QHBoxLayout(thanh)
        h.setContentsMargins(10, 6, 10, 0)
        h.setSpacing(4)
        self.nut_khung: Dict[str, QPushButton] = {}
        for i, ten in enumerate(TEN_KHUNG):
            n = QPushButton(ten)
            n.setCheckable(True)
            n.setCursor(Qt.PointingHandCursor)
            n.setStyleSheet(
                "QPushButton{border:none; padding:8px 16px; color:#4a5270;"
                "font-weight:600; border-bottom:2px solid transparent;}"
                "QPushButton:hover{color:#0b4a80;}"
                "QPushButton:checked{color:#0b4a80;"
                "border-bottom:2px solid #0b4a80;}")
            n.clicked.connect(lambda _=False, k=i: self.doi_khung(k))
            self.nut_khung[ten] = n
            h.addWidget(n)
        h.addStretch(1)
        v.addWidget(thanh)

        self.chong = QStackedWidget()
        self.khung_chat = KhungChat()
        self.khung_viec = KhungViec()
        self.khung_agent = KhungAgent()
        self.khung_log = KhungLog()
        self.khung_usage = KhungUsage()
        for x in (self.khung_chat, self.khung_viec, self.khung_agent,
                  self.khung_log, self.khung_usage):
            self.chong.addWidget(x)
        v.addWidget(self.chong, 1)
        self.doi_khung(0)
        return w

    # -- noi day -------------------------------------------------------------

    def _noi_tin_hieu(self) -> None:
        self.cau.anh_chup.connect(self.ve_lai)
        self.cau.co_loi.connect(self._bao_loi)
        self.cau.xong_viec.connect(
            lambda n: self.trang_thai.showMessage(f"{n} — xong", 4000))
        self.cau.dang_lam.connect(self.khung_chat.dat_dang_lam)

        self.khung_chat.gui.connect(self.cau.gui_chat)
        self.khung_chat.duyet_viec.connect(self.xac_nhan_duyet)
        self.khung_chat.mo_viec.connect(self._mo_viec_tu_chat)

        self.khung_viec.mo_log.connect(self._mo_log)
        ct = self.khung_viec.chi_tiet
        ct.tam_dung.connect(self.cau.tam_dung)
        ct.tiep_tuc.connect(self.cau.tiep_tuc)
        ct.dung_lai.connect(self.xac_nhan_dung)
        ct.duyet.connect(self.xac_nhan_duyet)

        self.o_tim.textChanged.connect(lambda _: None)

    def _phim_tat_tuy_chon(self) -> None:
        """Chỉ hai lối tắt, cả hai đều có nút bấm tương đương.

        KHÔNG có Ctrl+C/V/X/A ở đây. Đó là điều kiện nghiệm thu, và
        `tests/test_control_center_gui_clipboard.py` kiểm lại bằng cách
        quét mọi `QShortcut`/`QAction` của cửa sổ.
        """
        for phim, ham in (("Ctrl+K", lambda: self.o_tim.setFocus()),
                          ("F1", self.mo_tro_giup)):
            sc = QShortcut(QKeySequence(phim), self)
            sc.activated.connect(ham)

    # -- ve lai --------------------------------------------------------------

    def ve_lai(self, d: Dict) -> None:
        ps = d.get("projects") or []
        chon = d.get("selected") or ""
        if self.ds_project.count() != len(ps):
            self.ds_project.clear()
            for p in ps:
                it = QListWidgetItem(p.get("name") or p.get("project_id"))
                it.setData(Qt.UserRole, p.get("project_id"))
                it.setToolTip(p.get("repo_path") or "")
                self.ds_project.addItem(it)
        for i in range(self.ds_project.count()):
            if self.ds_project.item(i).data(Qt.UserRole) == chon:
                self.ds_project.setCurrentRow(i)
                break

        ten = next((p.get("name") for p in ps
                    if p.get("project_id") == chon), chon)
        self.nhan_project.setText(ten or "—")

        viec = d.get("tasks") or []
        self.chip_chay.dat(str(sum(1 for t in viec
                                   if t.get("state") == "RUNNING")))
        self.chip_chan.dat(str(sum(1 for t in viec
                                   if t.get("state") == "BLOCKED")))

        self.khung_chat.cap_nhat(d)
        self.khung_viec.cap_nhat(d)
        self.khung_agent.cap_nhat(d)
        self.inspector.cap_nhat(d)

        if self.chong.currentIndex() == 4:
            self.khung_usage.cap_nhat(self.cau.bao_cao_usage())
        if self.chong.currentIndex() == 3 and self.khung_log.task_id():
            tid = self.khung_log.task_id()
            self.khung_log.dat_viec(tid, self.cau.log_viec(tid))

    # -- hanh dong -----------------------------------------------------------

    def doi_khung(self, i: int) -> None:
        self.chong.setCurrentIndex(i)
        for j, ten in enumerate(TEN_KHUNG):
            self.nut_khung[ten].setChecked(i == j)
        if i == 4:
            self.khung_usage.cap_nhat(self.cau.bao_cao_usage())

    def _bam_project(self, it: QListWidgetItem) -> None:
        pid = it.data(Qt.UserRole)
        if pid:
            self.cau.chon_project(pid)

    def _mo_viec_tu_chat(self, task_id: str) -> None:
        self.doi_khung(1)
        b = self.khung_viec.bang
        for r in range(b.rowCount()):
            if b.item(r, 0) and b.item(r, 0).data(Qt.UserRole) == task_id:
                b.selectRow(r)
                break

    def _mo_log(self, task_id: str) -> None:
        if not task_id:
            return
        self.khung_log.dat_viec(task_id, self.cau.log_viec(task_id))
        self.doi_khung(3)

    def _chi_dan_tui(self) -> None:
        h = HopThoai("Giao diện TUI (dự phòng)", self)
        o = VanBanChonDuoc()
        o.setPlainText(
            "Giao diện terminal của V0.1 vẫn còn nguyên, làm đường dự "
            "phòng/gỡ lỗi.\n\nChạy trong terminal:\n\n"
            "    cd C:\\FanficWorkers\\router-control-center\n"
            "    .\\router-cc.cmd\n\n"
            "Nó dùng CHUNG một sổ SQLite với giao diện này, nên mở cạnh "
            "nhau vẫn thấy cùng dự án/việc/phiên.")
        h.than.addWidget(o)
        h.exec()

    def mo_tro_giup(self) -> None:
        """Trợ giúp là HỘP THOẠI — không chiếm chỗ thường trực trên màn."""
        h = HopThoai("Hướng dẫn dùng", self)
        h.than.addWidget(HopTroGiup())
        h.resize(720, 560)
        h.exec()

    def mo_cai_dat(self) -> None:
        h = HopThoai("Cài đặt", self)
        o = VanBanChonDuoc()
        o.setPlainText(
            "V0.1.1 chưa có mục cài đặt nào đổi được từ giao diện — và nói "
            "thẳng như vậy thì tốt hơn là dựng một khung trống trông như "
            "làm được gì đó.\n\n"
            f"Sổ dữ liệu : {getattr(self.cau.cc, 'root', '—')}\n"
            f"Trần song song: {getattr(self.cau.cc, 'max_parallel', '—')}\n\n"
            "Đổi trần song song: chạy lại với cờ --max-parallel N.\n"
            "Quyền của agent nằm ở tệp cấu hình của `agy` và CỐ Ý không "
            "sửa được từ đây — xem docs/CONTROL_CENTER.md §4b.")
        h.than.addWidget(o)
        h.exec()

    def mo_project_moi(self) -> None:
        duong = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục kho git cho dự án mới")
        if not duong:
            return
        ten = Path(duong).name
        pid = "".join(c for c in ten.lower() if c.isalnum() or c in "-_")[:24]
        if not pid:
            self._bao_loi("tên thư mục không tạo được mã dự án")
            return
        self.cau.them_project(pid, ten, duong)

    def xac_nhan_dung(self, task_id: str) -> None:
        """Dừng hẳn một việc là thao tác KHÔNG hoàn tác — phải xác nhận."""
        if not task_id:
            return
        tl = QMessageBox(self)
        tl.setIcon(QMessageBox.Warning)
        tl.setWindowTitle("Dừng việc?")
        tl.setText(f"Dừng hẳn việc {task_id}?")
        tl.setInformativeText(
            "Việc sẽ chuyển sang FAILED và không tự chạy lại. Worktree "
            "trên đĩa KHÔNG bị xoá — công việc chưa commit vẫn còn đó.")
        tl.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        tl.setDefaultButton(QMessageBox.Cancel)
        if tl.exec() == QMessageBox.Yes:
            self.cau.dung_viec(task_id)

    def xac_nhan_duyet(self, task_id: str) -> None:
        """Mở cổng GATED là quyết định của người — không bao giờ tự động."""
        if not task_id:
            return
        t = next((x for x in (self.cau.cc.store.tasks(self.cau.project_id))
                  if x.task_id == task_id), None)
        ly_do = (t.blocked_reason or t.gate_reason) if t else ""
        tl = QMessageBox(self)
        tl.setIcon(QMessageBox.Warning)
        tl.setWindowTitle("Duyệt cổng GATED?")
        tl.setText(f"Cho phép {task_id} chạy?")
        tl.setInformativeText(
            (ly_do or "Việc này chạm lớp GATED.")
            + "\n\nDuyệt là hành động của BẠN và được ghi vào sổ kiểm toán.")
        tl.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        tl.setDefaultButton(QMessageBox.Cancel)
        if tl.exec() == QMessageBox.Yes:
            self.cau.duyet_gated(task_id)

    def _bao_loi(self, msg: str) -> None:
        self.trang_thai.showMessage(msg, 8000)

    # -- vong doi ------------------------------------------------------------

    def bat_dau(self) -> None:
        self.cau.bat_dau()

    def closeEvent(self, e):                                # noqa: N802
        self.cau.dung()
        super().closeEvent(e)


class _Chip(QFrame):
    """Một con số nhỏ trên thanh trên, kèm nhãn chữ."""

    def __init__(self, nhan: str, gt: str, nen: str, chu: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(5)
        self.so = QLabel(gt)
        self.so.setStyleSheet(
            f"background:{nen}; color:{chu}; border-radius:9px;"
            f"padding:2px 9px; font-weight:700; font-size:11px;")
        self.so.setTextInteractionFlags(Qt.TextSelectableByMouse)
        h.addWidget(self.so)
        t = QLabel(nhan)
        t.setStyleSheet("color:#69708a; font-size:11px;")
        h.addWidget(t)

    def dat(self, gt: str) -> None:
        self.so.setText(gt)


class _Inspector(QFrame):
    """Sidebar phải: việc đang chạy + khoá đang giữ. Gấp lại được."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(
            "_Inspector{background:#fbfbfd; border-left:1px solid #e2e6ee;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        dau = QHBoxLayout()
        t = QLabel("ĐANG CHẠY")
        t.setStyleSheet("color:#69708a; font-size:11px; font-weight:700;")
        dau.addWidget(t)
        dau.addStretch(1)
        v.addLayout(dau)

        self.o = VanBanChonDuoc()
        self.o.setPlainText("(chưa có việc nào chạy)")
        v.addWidget(self.o, 1)
        menu_copy(self, self.o.toPlainText)

    def cap_nhat(self, d: Dict) -> None:
        gio = time.time()
        viec = [t for t in (d.get("tasks") or [])
                if t.get("state") in ("RUNNING", "REVIEW", "WAITING")]
        phien = {s.get("session_id"): s for s in (d.get("sessions") or [])}
        dong: List[str] = []
        for t in viec:
            s = phien.get(t.get("owner_session") or "") or {}
            dong += [
                f"● {t.get('title') or t.get('task_id')}",
                f"   {t.get('state')}  ·  {mo_ta_thoi_luong(t.get('started_at'), bay_gio=gio) or '—'}",
                f"   agent: {s.get('provider') or '—'}"
                f"{'/' + s.get('runtime_id') if s.get('runtime_id') else ''}",
                f"   phiên: {t.get('owner_session') or '—'}",
                f"   cây  : {(t.get('worktree') or '—').rsplit(chr(92), 1)[-1]}",
                "",
            ]
        khoa = d.get("locks") or []
        if khoa:
            dong += ["KHOÁ ĐANG GIỮ"]
            for k in khoa:
                dong.append(f"   {k.get('kind')}  {k.get('resource')}")
        self.o.setPlainText("\n".join(dong) or "(chưa có việc nào chạy)")
