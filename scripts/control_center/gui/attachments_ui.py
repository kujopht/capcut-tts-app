"""Widget đính kèm cho ô chat: dán, kéo-thả, chọn tệp, xem trước, bỏ ra.

MỘT ĐIỀU PHẢI NÓI TRƯỚC, vì nó là cổng nghiệm thu của V0.1.1 và bản này
không được phá nó: `OSoanThao` giờ **can thiệp vào việc dán**. Đó đúng là
chỗ dễ làm hỏng clipboard nhất trong toàn bộ ứng dụng.

Cách giữ an toàn, và nó chỉ có một cách đúng: `insertFromMimeData` chỉ xử
lý khi mime **thật sự** mang ảnh hoặc URL tệp, và MỌI trường hợp khác đi
thẳng xuống `super()`. Không bao giờ chặn `keyPressEvent` cho Ctrl+V, không
bao giờ đăng ký một `QShortcut("Ctrl+V")`. Dán văn bản thuần vẫn là đường
của Qt, y như trước.

Và một điều nữa: dán một ảnh **cùng lúc với** văn bản nhiều dòng phải giữ
được cả hai. Clipboard của Windows thường mang nhiều định dạng một lúc
(CF_DIB + CF_UNICODETEXT, hoặc CF_HDROP + text), nên xử lý phải là "lấy hết
những gì hiểu được", không phải "if/elif rồi bỏ phần còn lại".

ĐÍNH KÈM ĐƯỢC NHẬN VÀO KHO NGAY khi dán/thả, trước khi bấm Gửi. Nhờ vậy
thumbnail và `sha256` có thật ngay lúc đó, và người dùng thấy đúng thứ sẽ
được gửi. Bỏ một đính kèm trước khi gửi thì nó bị xoá khỏi kho luôn — không
để lại blob mồ côi.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from scripts.control_center.attachments import DinhKemLoi
from scripts.control_center.gui.widgets import HopThoai, VanBanChonDuoc

#: Kich co thumbnail. Du to de nhan ra mot anh chup man hinh, du nho de
#: nam duoc 5-6 cai tren mot dong.
O_ANH = QSize(84, 60)

#: Duoi tep -> nhan ngan hien trong chip. Chi de doc, khong phai allowlist
#: (allowlist that o `attachments.LOAI_THEO_DUOI`).
NHAN_LOAI = {
    "image": "ẢNH", "document": "TÀI LIỆU", "data": "DỮ LIỆU",
    "code": "MÃ", "config": "CẤU HÌNH", "log": "NHẬT KÝ",
    "archive": "NÉN",
}


class TheDinhKem(QFrame):
    """Một đính kèm đang chờ gửi: thumbnail hoặc chip, kèm nút bỏ ra."""

    bo_ra = Signal(str)          # attachment_id
    xem = Signal(str)

    def __init__(self, dk, duong_dan: Optional[Path],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.dk = dk
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "TheDinhKem{background:#ffffff; border:1px solid #dfe3ea;"
            "border-radius:8px;}")
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 5, 4, 5)
        h.setSpacing(8)

        if dk.la_anh and duong_dan is not None:
            self.hinh = QLabel()
            pm = QPixmap(str(duong_dan))
            if not pm.isNull():
                self.hinh.setPixmap(pm.scaled(
                    O_ANH, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.hinh.setFixedSize(O_ANH)
            self.hinh.setAlignment(Qt.AlignCenter)
            self.hinh.setStyleSheet(
                "background:#f2f4f8; border-radius:5px;")
            self.hinh.setCursor(Qt.PointingHandCursor)
            self.hinh.setToolTip("Bấm để xem ảnh đầy đủ")
            h.addWidget(self.hinh)
        else:
            nhan = QLabel(NHAN_LOAI.get(dk.media_type, "TỆP"))
            nhan.setFixedSize(QSize(58, 44))
            nhan.setAlignment(Qt.AlignCenter)
            nhan.setStyleSheet(
                "background:#eef1f6; color:#4a5270; border-radius:5px;"
                "font-size:10px; font-weight:700;")
            h.addWidget(nhan)

        cot = QVBoxLayout()
        cot.setSpacing(1)
        self.ten = QLabel(dk.filename)
        self.ten.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ten.setStyleSheet("font-size:11px; font-weight:600;"
                               "color:#1b2340;")
        self.ten.setMaximumWidth(190)
        cot.addWidget(self.ten)
        phu = QLabel(f"{dk.co_doc_duoc()} · {dk.sha256[:8]}")
        phu.setTextInteractionFlags(Qt.TextSelectableByMouse)
        phu.setStyleSheet("font-size:10px; color:#69708a;")
        cot.addWidget(phu)
        h.addLayout(cot)

        self.nut_xem = QPushButton("Xem")
        self.nut_xem.setCursor(Qt.PointingHandCursor)
        self.nut_xem.setToolTip("Mở xem trước tệp này")
        self.nut_xem.setFixedHeight(22)
        self.nut_xem.clicked.connect(
            lambda: self.xem.emit(self.dk.attachment_id))
        h.addWidget(self.nut_xem)

        self.nut_bo = QPushButton("×")
        self.nut_bo.setCursor(Qt.PointingHandCursor)
        self.nut_bo.setToolTip("Bỏ tệp này ra khỏi tin nhắn")
        self.nut_bo.setFixedSize(24, 24)
        self.nut_bo.setStyleSheet(
            "QPushButton{border:none; font-size:17px; color:#8a1c1c;}"
            "QPushButton:hover{background:#ffe0e0; border-radius:5px;}")
        self.nut_bo.clicked.connect(
            lambda: self.bo_ra.emit(self.dk.attachment_id))
        h.addWidget(self.nut_bo)

        self.setToolTip(
            f"{dk.filename}\n{dk.media_type} · {dk.co_doc_duoc()}\n"
            f"sha256 {dk.sha256}")

    def mousePressEvent(self, e):                           # noqa: N802
        if e.button() == Qt.LeftButton and self.dk.la_anh:
            self.xem.emit(self.dk.attachment_id)
        super().mousePressEvent(e)


class DaiDinhKem(QWidget):
    """Dải đính kèm đang chờ gửi, nằm ngay trên ô soạn.

    Ẩn hoàn toàn khi chưa có đính kèm nào: một dải trống thường trực chỉ
    ăn mất chỗ của ô soạn.
    """

    #: So luong/kich co doi -> cua so cap nhat nhan.
    doi = Signal()
    #: Nguoi dung bam `×` tren mot the.
    xin_bo_mot = Signal(str)
    #: Nguoi dung bam `Xem` hoac bam vao thumbnail.
    xin_xem_mot = Signal(str)

    def __init__(self, lay_duong_dan: Callable[[str], Optional[Path]],
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._lay = lay_duong_dan
        self._ds: List = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 6)
        v.setSpacing(4)

        dau = QHBoxLayout()
        self.nhan = QLabel("")
        self.nhan.setStyleSheet("color:#69708a; font-size:11px;"
                                "font-weight:600;")
        dau.addWidget(self.nhan)
        dau.addStretch(1)
        self.nut_bo_het = QPushButton("Bỏ hết")
        self.nut_bo_het.setCursor(Qt.PointingHandCursor)
        self.nut_bo_het.setToolTip("Bỏ toàn bộ tệp đính kèm")
        self.nut_bo_het.setFixedHeight(20)
        dau.addWidget(self.nut_bo_het)
        v.addLayout(dau)

        self.cuon = QScrollArea()
        self.cuon.setWidgetResizable(True)
        self.cuon.setFrameShape(QFrame.NoFrame)
        self.cuon.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.cuon.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cuon.setFixedHeight(84)
        self.trong = QWidget()
        self.hang = QHBoxLayout(self.trong)
        self.hang.setContentsMargins(0, 0, 0, 0)
        self.hang.setSpacing(8)
        self.hang.addStretch(1)
        self.cuon.setWidget(self.trong)
        v.addWidget(self.cuon)
        self.setVisible(False)

    # -- trang thai ----------------------------------------------------------

    def danh_sach(self) -> List:
        return list(self._ds)

    def cac_ma(self) -> List[str]:
        return [d.attachment_id for d in self._ds]

    def them(self, dk) -> None:
        if any(d.attachment_id == dk.attachment_id for d in self._ds):
            return                      # da co: dan lai dung tep do
        self._ds.append(dk)
        self._ve_lai()
        self.doi.emit()

    def bo(self, attachment_id: str) -> None:
        self._ds = [d for d in self._ds
                    if d.attachment_id != attachment_id]
        self._ve_lai()
        self.doi.emit()

    def xoa_het(self) -> None:
        self._ds = []
        self._ve_lai()
        self.doi.emit()

    def _ve_lai(self) -> None:
        while self.hang.count() > 1:
            it = self.hang.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
        for dk in self._ds:
            the = TheDinhKem(dk, self._lay(dk.attachment_id))
            the.bo_ra.connect(self._xin_bo)
            the.xem.connect(self._xin_xem)
            self.hang.insertWidget(self.hang.count() - 1, the)
        n = len(self._ds)
        tong = sum(d.size_bytes for d in self._ds)
        self.nhan.setText(
            f"{n} tệp đính kèm · {tong / 1048576:.1f} MB" if n else "")
        self.setVisible(n > 0)

    def _xin_bo(self, aid: str) -> None:
        self.xin_bo_mot.emit(aid)

    def _xin_xem(self, aid: str) -> None:
        self.xin_xem_mot.emit(aid)


def mo_xem(dk, duong_dan: Path, parent: Optional[QWidget] = None) -> None:
    """Xem trước một đính kèm — ẢNH thì xem TRONG APP, còn lại nhờ hệ điều hành.

    Ảnh xem trong app là lựa chọn có chủ đích: nó là loại được dán nhiều
    nhất, và mở nó bằng ứng dụng ngoài cho một việc chỉ cần "nhìn cho chắc"
    là quá nhiều ma sát.

    Các loại khác giao cho `QDesktopServices` — tức là ứng dụng mặc định của
    người dùng. Chỉ làm vậy với loại NẰM TRONG allowlist (kho đã chặn ở lúc
    nhận), nên không có `.exe`/`.lnk`/`.reg` nào tới được đây.
    """
    if dk.la_anh:
        h = HopThoai(dk.filename, parent)
        pm = QPixmap(str(duong_dan))
        if pm.isNull():
            o = VanBanChonDuoc()
            o.setPlainText(f"Không đọc được ảnh:\n{duong_dan}")
            h.than.addWidget(o)
        else:
            nhan = QLabel()
            nhan.setAlignment(Qt.AlignCenter)
            nhan.setPixmap(pm.scaled(QSize(940, 660), Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation))
            nhan.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            h.than.addWidget(nhan)
            phu = QLabel(f"{dk.filename} · {dk.co_doc_duoc()} · "
                         f"{pm.width()}×{pm.height()} · sha256 {dk.sha256}")
            phu.setTextInteractionFlags(Qt.TextSelectableByMouse)
            phu.setStyleSheet("color:#69708a; font-size:11px;")
            h.than.addWidget(phu)
        h.resize(1000, 760)
        h.exec()
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(duong_dan)))


def chon_tep(parent: Optional[QWidget] = None) -> List[str]:
    """Hộp chọn tệp — đường cho người không dán và không kéo-thả."""
    duong, _ = QFileDialog.getOpenFileNames(
        parent, "Chọn tệp đính kèm", "",
        "Tệp được hỗ trợ (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.pdf "
        "*.txt *.md *.docx *.csv *.json *.xlsx *.zip *.py *.js *.ts *.sql "
        "*.yaml *.yml *.toml *.ini *.log *.xml *.html *.css);;"
        "Tất cả tệp (*.*)")
    return list(duong or [])


def loi_doc_duoc(exc: Exception) -> str:
    """Thông điệp lỗi cho người dùng, không phải traceback."""
    if isinstance(exc, DinhKemLoi):
        return str(exc)
    return f"không nhận được tệp: {type(exc).__name__}: {exc}"
