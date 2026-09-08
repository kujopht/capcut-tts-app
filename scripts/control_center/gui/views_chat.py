"""Khung Chat — trung tâm của sản phẩm.

YÊU CẦU KHÓ NHẤT Ở ĐÂY không phải vẽ bong bóng chat, mà là: *cho thấy
Router đã phân rã mục tiêu thành gì, mà KHÔNG trút nội tạng điều phối vào
cuộc hội thoại.* Nên mỗi câu trả lời của Router hiện dạng cây gọn:

    Đã nhận mục tiêu
    ├─ Backend wiring        RUNNING · AG01/claude-opus
    ├─ Artwork integration   QUEUED
    ├─ Tests                 WAITING
    └─ Production proof      BLOCKED — chờ bạn duyệt

Chi tiết (hợp đồng, phạm vi, phiên, worktree, nhật ký thô) nằm sau các mục
GẤP LẠI được. Mặc định đóng.

PHÂN BIỆT NĂM LOẠI TIN, bằng màu VÀ bằng chữ — không chỉ bằng màu, vì màu
một mình thì người mù màu không đọc được:

    bạn            viền xanh đậm, nhãn "Bạn"
    Router quyết   viền tím, nhãn "Router"
    việc được tạo  hàng cây trong thẻ Router, có huy hiệu trạng thái
    báo cáo agent  nền xám nhạt, nhãn "Agent"
    chặn           viền đỏ, nhãn "Cần bạn duyệt" + nút duyệt ngay trên thẻ
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from scripts.control_center.gui.bridge import gop_ke_hoach
from scripts.control_center.gui.attachments_ui import (DaiDinhKem,
                                                       chon_tep)
from scripts.control_center.gui.widgets import (HuyHieu, KhoiMa, OSoanThao,
                                                VanBanChonDuoc, menu_copy)

CAY_GIUA = "├─"
CAY_CUOI = "└─"


class MucGapLai(QWidget):
    """Một mục gấp lại được, mở/đóng bằng CHUỘT. Mặc định đóng.

    Dùng cho "chi tiết" mà người dùng thường không cần: hợp đồng, phạm vi,
    nhật ký thô. Đây là cách giữ đúng luật "đừng trút nội tạng vào chat".
    """

    def __init__(self, tieu_de: str, than: QWidget,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 0)
        v.setSpacing(2)
        self.nut = QToolButton()
        self.nut.setText(f"  {tieu_de}")
        self.nut.setCheckable(True)
        self.nut.setChecked(False)
        self.nut.setCursor(Qt.PointingHandCursor)
        self.nut.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.nut.setArrowType(Qt.RightArrow)
        self.nut.setStyleSheet(
            "QToolButton{border:none; color:#4a5270; font-size:11px;"
            "font-weight:600; padding:2px;}"
            "QToolButton:hover{color:#1b2340;}")
        self.nut.toggled.connect(self._doi)
        v.addWidget(self.nut, 0, Qt.AlignLeft)
        self.than = than
        self.than.setVisible(False)
        v.addWidget(self.than)

    def _doi(self, mo: bool) -> None:
        self.nut.setArrowType(Qt.DownArrow if mo else Qt.RightArrow)
        self.than.setVisible(mo)


class TheTin(QFrame):
    """Một bong bóng tin. Văn bản luôn CHỌN/COPY được."""

    def __init__(self, *, nhan: str, text: str, mau_vien: str,
                 mau_nen: str = "#ffffff",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"TheTin{{background:{mau_nen}; border:1px solid #e2e6ee;"
            f"border-left:3px solid {mau_vien}; border-radius:8px;}}")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 8, 12, 10)
        self.v.setSpacing(4)

        dau = QLabel(nhan)
        dau.setStyleSheet(
            f"color:{mau_vien}; font-size:11px; font-weight:700;"
            f"letter-spacing:.4px;")
        self.v.addWidget(dau)

        self._text = text or ""
        if self._text:
            self.o = VanBanChonDuoc()
            self.o.setPlainText(self._text)
            self.o.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            self._co_lai(self.o)
            self.v.addWidget(self.o)
        menu_copy(self, lambda: self._text)

    @staticmethod
    def _co_lai(o: VanBanChonDuoc) -> None:
        """Cho ô cao đúng bằng nội dung — không để một dải trống dài.

        `QTextBrowser` mặc định muốn cao
        cả khung; trong một danh sách tin
        nhắn thì phải co theo văn bản.
        """
        o.document().setTextWidth(o.viewport().width() or 560)
        cao = int(o.document().size().height()) + 8
        o.setFixedHeight(max(22, min(cao, 480)))


class TheRouter(TheTin):
    """Thẻ trả lời của Router: cây phân rã + chi tiết gấp lại."""

    def __init__(self, *, text: str, hang: List[Dict],
                 khi_duyet: Callable[[str], None],
                 khi_mo_viec: Callable[[str], None],
                 parent: Optional[QWidget] = None):
        super().__init__(nhan="ROUTER", text="", mau_vien="#6b46c1",
                         parent=parent)
        #: `task_id -> _HangViec`, de cap nhat trang thai TAI CHO.
        self.hang_viec: Dict[str, "_HangViec"] = {}
        if hang:
            tom = QLabel("Đã nhận mục tiêu — phân rã thành "
                         f"{len(hang)} việc:")
            tom.setStyleSheet("color:#2b3350; font-size:12px;")
            self.v.addWidget(tom)
            for h in hang:
                hv = _HangViec(h, khi_duyet=khi_duyet,
                               khi_mo_viec=khi_mo_viec)
                self.hang_viec[h.get("task_id", "")] = hv
                self.v.addWidget(hv)
        else:
            # Khong co viec nao: van phai hien loi cua Router, khong im lang.
            o = VanBanChonDuoc()
            o.setPlainText(text or "(Router không tạo việc nào)")
            self._co_lai(o)
            self.v.addWidget(o)

        if text:
            than = KhoiMa(text, tieu_de="nguyên văn trả lời của Router")
            self.v.addWidget(MucGapLai("Chi tiết quyết định", than))
        self._text = text or ""


class _HangViec(QFrame):
    """Một hàng trong cây phân rã. Bấm để mở chi tiết việc."""

    def __init__(self, h: Dict, *, khi_duyet: Callable[[str], None],
                 khi_mo_viec: Callable[[str], None],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.h = h
        bi_chan = (h.get("state") == "BLOCKED")
        self.setStyleSheet(
            ("_HangViec{background:#fff7f7; border-radius:6px;}"
             if bi_chan else ""))
        r = QHBoxLayout(self)
        r.setContentsMargins(2, 2, 2, 2)
        r.setSpacing(8)

        nhanh = QLabel(CAY_CUOI if h.get("cuoi") else CAY_GIUA)
        nhanh.setStyleSheet("color:#9aa2b8; font-family:Consolas;")
        r.addWidget(nhanh)

        ten = QPushButton(h.get("title") or h.get("task_id", ""))
        ten.setFlat(True)
        ten.setCursor(Qt.PointingHandCursor)
        ten.setToolTip("Mở chi tiết việc này")
        ten.setStyleSheet(
            "QPushButton{border:none; text-align:left; color:#1b2340;"
            "font-size:12px; padding:1px 2px;}"
            "QPushButton:hover{color:#0b4a80; text-decoration:underline;}")
        ten.clicked.connect(lambda: khi_mo_viec(h.get("task_id", "")))
        r.addWidget(ten, 1)

        hh = HuyHieu(h.get("state", "?"))
        r.addWidget(hh)

        agent = h.get("agent") or ""
        if agent:
            a = QLabel(agent)
            a.setTextInteractionFlags(Qt.TextSelectableByMouse)
            a.setStyleSheet("color:#69708a; font-size:11px;")
            r.addWidget(a)

        if bi_chan:
            # Nut duyet nam NGAY tren the, khong bat nguoi dung di tim menu.
            nut = QPushButton("Duyệt…")
            nut.setCursor(Qt.PointingHandCursor)
            nut.setToolTip(h.get("blocked_reason")
                           or "Việc này chạm lớp GATED — cần bạn duyệt")
            nut.setStyleSheet(
                "QPushButton{background:#8a1c1c; color:white; border:none;"
                "border-radius:5px; padding:3px 10px; font-size:11px;"
                "font-weight:600;}"
                "QPushButton:hover{background:#a52222;}")
            nut.clicked.connect(lambda: khi_duyet(h.get("task_id", "")))
            r.addWidget(nut)

        self.hh, self.nhan_agent = hh, None
        if agent:
            self.nhan_agent = a
        menu_copy(self, self._van_ban)

    def cap_nhat(self, h: Dict) -> None:
        """Cập nhật TẠI CHỖ, không dựng lại thẻ.

        Dựng lại cả danh sách tin mỗi lần một việc đổi trạng thái sẽ huỷ
        thẻ người dùng đang đọc và huỷ luôn vùng họ đang bôi đen. Trạng
        thái việc đổi liên tục, nên đây là đường nóng.
        """
        self.h = h
        self.hh.dat(h.get("state", "?"))
        if self.nhan_agent is not None:
            self.nhan_agent.setText(h.get("agent") or "")

    def _van_ban(self) -> str:
        h = self.h
        return (f"{h.get('task_id')}  {h.get('state')}  "
                f"{h.get('title')}  {h.get('agent') or ''}").strip()


class KhungChat(QWidget):
    """Khung Chat đầy đủ: danh sách tin + ô soạn dính ở dưới."""

    #: Yeu cau mo chi tiet mot viec (cua so chinh xu ly).
    mo_viec = Signal(str)
    #: Nguoi dung bam Duyet tren mot the bi chan.
    duyet_viec = Signal(str)
    #: Nguoi dung gui mot muc tieu. (van_ban, danh_sach_ma_dinh_kem)
    gui = Signal(str, list)
    #: Nguoi dung dan/tha tep -> cua so nhan vao kho.
    xin_nhan_tep = Signal(list)
    #: Nguoi dung dan mot anh tho tu clipboard.
    xin_nhan_anh = Signal(object)
    #: Nguoi dung bo mot dinh kem ra khoi tin nhan CHUA gui.
    xin_bo_dinh_kem = Signal(str)
    #: Nguoi dung muon xem truoc mot dinh kem.
    xin_xem_dinh_kem = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        #: `attachment_id -> Path`. Giu o day de `TheDinhKem` ve duoc
        #: thumbnail ma khong phai tu hoi so.
        self._duong_dan: Dict[str, object] = {}
        self._dau_tin = ""
        self._dau_viec = ""
        self._the_router: List["TheRouter"] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.cuon = QScrollArea()
        self.cuon.setWidgetResizable(True)
        self.cuon.setFrameShape(QFrame.NoFrame)
        self.trong = QWidget()
        self.ds = QVBoxLayout(self.trong)
        self.ds.setContentsMargins(16, 14, 16, 14)
        self.ds.setSpacing(10)
        self.ds.addStretch(1)
        self.cuon.setWidget(self.trong)
        v.addWidget(self.cuon, 1)

        v.addWidget(self._dung_o_soan())

    def _dung_o_soan(self) -> QWidget:
        khung = QFrame()
        khung.setStyleSheet(
            "QFrame{background:#fbfbfd; border-top:1px solid #e2e6ee;}")
        ngoai = QVBoxLayout(khung)
        ngoai.setContentsMargins(14, 10, 14, 12)
        ngoai.setSpacing(6)

        # Dai dinh kem nam TREN o soan: nguoi dung thay thu sap gui
        # ngay canh cho dang go, khong o mot panel khac.
        self.dai = DaiDinhKem(self._lay_duong_dan)
        self.dai.xin_bo_mot.connect(self.xin_bo_dinh_kem.emit)
        self.dai.xin_xem_mot.connect(self.xin_xem_dinh_kem.emit)
        self.dai.nut_bo_het.clicked.connect(self._bo_het)
        self.dai.doi.connect(self._cap_nhat_nhan_gui)
        ngoai.addWidget(self.dai)

        self.o_soan = OSoanThao()
        self.o_soan.yeu_cau_gui.connect(self._bam_gui)
        self.o_soan.co_tep.connect(self.xin_nhan_tep.emit)
        self.o_soan.co_anh.connect(self.xin_nhan_anh.emit)
        ngoai.addWidget(self.o_soan)

        thanh = QHBoxLayout()
        self.nut_dinh_kem = QPushButton("Đính kèm tệp…")
        self.nut_dinh_kem.setCursor(Qt.PointingHandCursor)
        self.nut_dinh_kem.setToolTip(
            "Chọn tệp để gửi kèm tin nhắn." + chr(10) +
            "Hoặc: dán bằng Ctrl+V (ảnh chụp Win+Shift+S cũng được), "
            "hoặc kéo-thả tệp từ Explorer vào ô soạn.")
        self.nut_dinh_kem.clicked.connect(self._chon_tep)
        thanh.addWidget(self.nut_dinh_kem)
        thanh.addStretch(1)

        self.nhan_trang_thai = QLabel("")
        self.nhan_trang_thai.setStyleSheet("color:#69708a; font-size:11px;")
        thanh.addWidget(self.nhan_trang_thai)

        self.nut_gui = QPushButton("Gửi")
        self.nut_gui.setCursor(Qt.PointingHandCursor)
        self.nut_gui.setToolTip("Gửi mục tiêu này cho Router (Ctrl+Enter)")
        self.nut_gui.setMinimumWidth(96)
        self.nut_gui.setStyleSheet(
            "QPushButton{background:#0b4a80; color:white; border:none;"
            "border-radius:6px; padding:7px 16px; font-weight:600;}"
            "QPushButton:hover{background:#0d5c9e;}"
            "QPushButton:disabled{background:#b8c0d0;}")
        self.nut_gui.clicked.connect(self._bam_gui)
        thanh.addWidget(self.nut_gui)
        ngoai.addLayout(thanh)
        return khung

    # -- hanh dong -----------------------------------------------------------

    def _chon_tep(self) -> None:
        duong = chon_tep(self)
        if duong:
            self.xin_nhan_tep.emit(duong)
        self.o_soan.setFocus()

    def _bo_het(self) -> None:
        for aid in list(self.dai.cac_ma()):
            self.xin_bo_dinh_kem.emit(aid)

    def them_dinh_kem(self, dk, duong_dan) -> None:
        """Cua so goi vao day SAU KHI kho da nhan tep."""
        self._duong_dan[dk.attachment_id] = duong_dan
        self.dai.them(dk)

    def bo_dinh_kem(self, attachment_id: str) -> None:
        self._duong_dan.pop(attachment_id, None)
        self.dai.bo(attachment_id)

    def _lay_duong_dan(self, attachment_id: str):
        return self._duong_dan.get(attachment_id)

    def cac_ma_dinh_kem(self):
        return self.dai.cac_ma()

    def _cap_nhat_nhan_gui(self) -> None:
        n = len(self.dai.cac_ma())
        self.nut_gui.setText("Gửi" if not n else f"Gửi ({n} tệp)")

    def _bam_gui(self) -> None:
        text = self.o_soan.toPlainText().strip()
        ma = self.dai.cac_ma()
        # Cho phep gui khi CHI co dinh kem: keo mot anh vao roi bam Gui
        # la mot y dinh hop le ("xem cai nay").
        if not text and not ma:
            return
        self.gui.emit(text, ma)
        self.o_soan.clear()
        self._duong_dan.clear()
        self.dai.xoa_het()

    def dat_dang_lam(self, dang: bool) -> None:
        self.nut_gui.setEnabled(not dang)
        self.nhan_trang_thai.setText("Router đang phân rã…" if dang else "")

    # -- ve lai --------------------------------------------------------------

    def cap_nhat(self, d: Dict) -> None:
        """Vẽ lại danh sách tin — DỰNG LẠI CÀNG ÍT CÀNG TỐT.

        Có HAI loại thay đổi, và gộp chúng lại là một lỗi thật:

        * **tin mới** (bảng `chat` chỉ INSERT, text không bao giờ đổi) —
          phải dựng thêm thẻ;
        * **việc đổi trạng thái** — chỉ ảnh hưởng vài huy hiệu bên trong
          các thẻ ĐÃ CÓ.

        Bản đầu dùng MỘT dấu vân tay cho cả hai, nên mỗi lần một việc đổi
        `RUNNING→DONE` là **toàn bộ** danh sách tin bị dựng lại: thẻ người
        dùng đang đọc biến mất, vùng đang bôi đen mất theo (⇒ Ctrl+C ra
        rỗng), và màn hình nhảy về cuối. Review đối kháng đo được: 19 thẻ,
        người dùng cuộn ở đầu (scroll 0/2452), một việc đổi trạng thái ⇒
        toàn bộ 19 thẻ mới và scroll 2452/2452.

        Nên tách: tin mới thì dựng thêm; trạng thái đổi thì cập nhật TẠI
        CHỖ. Và chỉ tự cuộn xuống khi người dùng vốn ĐANG ở cuối — ai đang
        đọc lại tin cũ thì không bị kéo đi.
        """
        chat = d.get("chat") or []
        viec = {t.get("task_id"): t for t in (d.get("tasks") or [])}

        dau_tin = repr([(m.get("message_id"), m.get("role")) for m in chat])
        dau_viec = repr(sorted((k, v.get("state"), v.get("owner_session"))
                               for k, v in viec.items()))

        if dau_tin != self._dau_tin:
            sb = self.cuon.verticalScrollBar()
            o_cuoi = sb.maximum() == 0 or sb.value() >= sb.maximum() - 4
            while self.ds.count() > 1:
                it = self.ds.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
            self._the_router = []
            for m in chat:
                w = self._the(m, viec)
                if isinstance(w, TheRouter):
                    self._the_router.append(w)
                self.ds.insertWidget(self.ds.count() - 1, w)
            self._dau_tin, self._dau_viec = dau_tin, dau_viec
            if o_cuoi:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self._cuoi_trang)
            return

        if dau_viec != self._dau_viec:
            # KHONG dung lai gi ca — chi doi huy hieu trong cac the da co.
            for tr in self._the_router:
                for tid, hv in tr.hang_viec.items():
                    t = viec.get(tid)
                    if t:
                        moi_h = dict(hv.h)
                        moi_h["state"] = t.get("state", "?")
                        moi_h["agent"] = t.get("owner_session") or ""
                        hv.cap_nhat(moi_h)
            self._dau_viec = dau_viec

    def _the(self, m: Dict, viec: Dict[str, Dict]) -> QWidget:
        vai = (m.get("role") or "").lower()
        text = m.get("text") or ""
        if vai == "user":
            return TheTin(nhan="BẠN", text=text, mau_vien="#0b4a80",
                          mau_nen="#f4f9ff")
        if vai == "router":
            hang = gop_ke_hoach(m.get("meta") or {}, viec)
            return TheRouter(text=text, hang=hang,
                             khi_duyet=self.duyet_viec.emit,
                             khi_mo_viec=self.mo_viec.emit)
        # Bao cao agent / tin he thong.
        return TheTin(nhan=(vai or "hệ thống").upper(), text=text,
                      mau_vien="#69708a", mau_nen="#f7f8fa")

    def _cuoi_trang(self) -> None:
        sb = self.cuon.verticalScrollBar()
        sb.setValue(sb.maximum())
