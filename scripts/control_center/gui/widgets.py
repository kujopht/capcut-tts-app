"""Widget dùng lại. Đây là nơi CỔNG NGHIỆM THU CLIPBOARD được đáp ứng.

Nguyên tắc xuyên suốt tệp này: **để Qt làm việc của Qt.** `QPlainTextEdit`
và `QTextEdit` đã mang sẵn clipboard thật của hệ điều hành — chọn bằng
chuột, Ctrl+C/V/X/A, menu chuột phải, dán nhiều dòng, dán Unicode, dán văn
bản dài. Mọi lỗi clipboard trong một app Qt gần như luôn là do tác giả
GIÀNH lấy các tổ hợp đó hoặc chặn `keyPressEvent`. Nên tệp này cố ý KHÔNG
làm hai điều đó, và `tests/test_control_center_gui_clipboard.py` khoá lại.

Cụ thể, ba luật:

1. Không `QShortcut`/`QAction` nào ở đây đăng ký Ctrl+C, Ctrl+V, Ctrl+X hay
   Ctrl+A. Lối tắt duy nhất gắn vào ô soạn là **Ctrl+Return** và nó ở phạm
   vi widget, không phải phạm vi ứng dụng.
2. `keyPressEvent` chỉ được ghi đè cho ĐÚNG một phím (Return), và luôn gọi
   `super()` cho mọi phím khác — kể cả khi có modifier.
3. Ô đọc-chỉ vẫn phải CHỌN được. `setReadOnly(True)` giữ được chọn/copy;
   `setEnabled(False)` thì không. Không bao giờ dùng `setEnabled(False)` để
   làm một ô văn bản thành chỉ-đọc.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (QFont, QGuiApplication, QKeySequence,
                           QShortcut, QTextCursor)
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPlainTextEdit, QPushButton,
                               QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

#: Mau theo trang thai viec. Dung ca o huy hieu va vien the.
MAU_TRANG_THAI = {
    "QUEUED":  ("#e8eaf0", "#3a4256"),
    "WAITING": ("#fff4d6", "#7a5a00"),
    "RUNNING": ("#d9ecff", "#0b4a80"),
    "BLOCKED": ("#ffe0e0", "#8a1c1c"),
    "REVIEW":  ("#eadcff", "#4a2a80"),
    "DONE":    ("#dcf5e2", "#1c6b33"),
    "FAILED":  ("#ffd9d9", "#8a1010"),
    "PAUSED":  ("#eceff4", "#4a4a4a"),
    "STARTING": ("#e8eaf0", "#3a4256"),
    "IDLE":    ("#eceff4", "#4a4a4a"),
    "BUSY":    ("#d9ecff", "#0b4a80"),
    "DRAINING": ("#fff4d6", "#7a5a00"),
    "STOPPED": ("#eceff4", "#4a4a4a"),
    "DEAD":    ("#ffd9d9", "#8a1010"),
    "ACTUAL":  ("#dcf5e2", "#1c6b33"),
    "ESTIMATED": ("#fff4d6", "#7a5a00"),
    "UNAVAILABLE": ("#eceff4", "#4a4a4a"),
}

#: U+2029 — ky tu ma `QTextCursor.selectedText()` dung thay cho
#: ngat dong. Khai bang escape de no NHIN THAY DUOC trong ma nguon.
NGAT_DOAN = "\u2029"

_MONO = "Consolas, 'Cascadia Mono', 'Courier New', monospace"


def dat_clipboard(text: str) -> None:
    """Đặt clipboard hệ thống. Một chỗ duy nhất để bài kiểm chặn được."""
    cb = QGuiApplication.clipboard()
    if cb is not None:
        cb.setText(text or "")


def dat_van_ban_giu_chon(o, text: str) -> bool:
    """Đặt văn bản mà KHÔNG giết vùng đang bôi đen và chỗ đang cuộn.

    ĐÂY LÀ MỘT LỖI CLIPBOARD, dù trông như lỗi hiệu năng. Giao diện làm mới
    mỗi giây; nếu mỗi nhịp gọi `setPlainText()` vô điều kiện thì vùng người
    dùng vừa bôi đen bị xoá sau tối đa 1 giây. Người ta bôi đen rồi mới với
    tay bấm Ctrl+C — quá 1 giây là chuyện thường — nên Ctrl+C copy ra rỗng
    (hoặc nội dung cũ). Đúng triệu chứng "clipboard không đáng tin" mà bản
    V0.1.1 tồn tại để sửa.

    Review đối kháng trước phát hành đo được ba chỗ mắc lỗi này: pane
    "đang chạy" của Inspector, panel chi tiết việc, và nhật ký của một việc
    ĐANG mọc log (217 ký tự đang chọn → 0 sau một nhịp).

    Trả `True` nếu có ghi thật.
    """
    if o.toPlainText() == (text or ""):
        return False                    # khong doi thi KHONG ghi lai
    cur = o.textCursor()
    neo, vi = cur.anchor(), cur.position()
    thanh = o.verticalScrollBar()
    cho = thanh.value()
    o.setPlainText(text or "")
    # Khoi phuc vung chon neu no con nam trong van ban moi. Neu van ban da
    # ngan di, kep vao cuoi thay vi nem ngoai le.
    het = len(o.toPlainText())
    if neo != vi:
        cur = o.textCursor()
        cur.setPosition(min(neo, het))
        cur.setPosition(min(vi, het), QTextCursor.MoveMode.KeepAnchor)
        o.setTextCursor(cur)
    thanh.setValue(min(cho, thanh.maximum()))
    return True


class HuyHieu(QLabel):
    """Nhãn trạng thái có màu. Chỉ để đọc, nhưng vẫn chọn được bằng chuột."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text or "", parent)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setAlignment(Qt.AlignCenter)
        self.dat(text)

    def dat(self, text: str) -> None:
        t = (text or "?").upper()
        self.setText(t)
        nen, chu = MAU_TRANG_THAI.get(t, ("#eceff4", "#333333"))
        self.setStyleSheet(
            f"background:{nen}; color:{chu}; border-radius:9px;"
            f"padding:2px 9px; font-weight:600; font-size:11px;")


class VanBanChonDuoc(QTextBrowser):
    """Ô văn bản CHỈ ĐỌC nhưng chọn/copy được như bình thường.

    Dùng cho khung chat và mọi chỗ hiển thị văn bản dài. `QTextBrowser` giữ
    nguyên chọn bằng chuột, Ctrl+C, Ctrl+A và menu chuột phải mặc định của
    Qt — nên ở đây không cần (và không được) tự dựng lại.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setReadOnly(True)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
            | Qt.LinksAccessibleByMouse)
        self.setStyleSheet("QTextBrowser{border:none; background:transparent;}")


class OSoanThao(QPlainTextEdit):
    """Ô soạn tin của khung chat. Nhiều dòng, dán nguyên vẹn.

    HAI QUYẾT ĐỊNH UX Ở ĐÂY, và cả hai đều theo luật "bàn phím chỉ là lối
    tắt":

    * **Enter xuống dòng, KHÔNG gửi.** Ngược với thói quen của nhiều app
      chat, nhưng ở đây gõ nhiều dòng là việc thường ngày, và một cú Enter
      vô tình gửi mất bản nháp là mất công người dùng. Nút **Gửi** là đường
      chính; **Ctrl+Enter** là lối tắt tuỳ chọn.
    * **`QPlainTextEdit`, không phải `QLineEdit`.** `QLineEdit` một dòng sẽ
      biến một đoạn văn dán vào thành một dòng dài — đúng lỗi
      "prompt nhiều dòng không dán nguyên vẹn" mà bản này phải sửa.

    KHÔNG ghi đè Ctrl+C/V/X/A. `keyPressEvent` chỉ bắt Return kèm Ctrl và
    chuyển mọi thứ còn lại cho `super()`.
    """

    yeu_cau_gui = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setPlaceholderText(
            "Gõ mục tiêu cho Router… (Enter xuống dòng · nút Gửi hoặc "
            "Ctrl+Enter để gửi)")
        self.setTabChangesFocus(True)
        self.setMinimumHeight(76)
        self.setMaximumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # Pham vi WIDGET, khong phai ung dung: mot phim tat pham vi ung dung
        # se ban ca khi con tro dang o o khac.
        sc = QShortcut(QKeySequence("Ctrl+Return"), self)
        sc.setContext(Qt.WidgetWithChildrenShortcut)
        sc.activated.connect(self.yeu_cau_gui.emit)
        sc2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        sc2.setContext(Qt.WidgetWithChildrenShortcut)
        sc2.activated.connect(self.yeu_cau_gui.emit)

    #: V0.2: nguoi dung dan/tha tep vao o soan. Mang duong dan tep cuc bo.
    co_tep = Signal(list)
    #: V0.2: nguoi dung dan mot ANH tho tu clipboard (Win+Shift+S).
    #: Mang `QImage` — khong phai duong dan, vi anh chup khong co tep nao.
    co_anh = Signal(object)

    def keyPressEvent(self, e):                             # noqa: N802
        # CHI Return + Ctrl duoc bat o day. Moi phim khac — dac biet la
        # Ctrl+C/V/X/A — phai di tiep xuong `super()`, neu khong ta vua tu
        # tay pha chinh cong nghiem thu cua ban phat hanh nay.
        if (e.key() in (Qt.Key_Return, Qt.Key_Enter)
                and (e.modifiers() & Qt.ControlModifier)):
            self.yeu_cau_gui.emit()
            e.accept()
            return
        super().keyPressEvent(e)

    # -- V0.2: dan va keo-tha tep -------------------------------------------
    #
    # LAM O `insertFromMimeData`, KHONG o `keyPressEvent`. Day la khac biet
    # quan trong nhat cua ca tinh nang nay: Qt goi `insertFromMimeData` cho
    # MOI duong dan (Ctrl+V, chuot phai > Paste, chuot giua tren X11), nen
    # xu ly o day thi ca ba duong deu chay. Con chan `keyPressEvent` cho
    # Ctrl+V thi vua bo sot hai duong kia, vua co nguy co an mat phim dan.

    @staticmethod
    def _duong_dan_cuc_bo(mime) -> list:
        """Đường dẫn tệp CỤC BỘ trong mime, hoặc rỗng.

        Chỉ nhận `file://` trỏ tới tệp thật trên máy. Một URL `http://`
        kéo từ trình duyệt vào KHÔNG được biến thành lệnh tải về — tầng
        này không gọi mạng, và im lặng tải một URL là đúng thứ người dùng
        không yêu cầu.
        """
        if not mime.hasUrls():
            return []
        ra = []
        for u in mime.urls():
            if u.isLocalFile():
                ra.append(u.toLocalFile())
        return ra

    def canInsertFromMimeData(self, mime) -> bool:          # noqa: N802
        if self._duong_dan_cuc_bo(mime) or mime.hasImage():
            return True
        return super().canInsertFromMimeData(mime)

    def insertFromMimeData(self, mime) -> None:             # noqa: N802
        """Lấy HẾT những gì hiểu được, không phải if/elif rồi bỏ phần còn lại.

        Clipboard Windows thường mang nhiều định dạng một lúc: một cú copy
        trong Explorer đặt CF_HDROP *và* text; Win+Shift+S đặt CF_DIB *và*
        có thể cả text. Nên tệp/ảnh và VĂN BẢN được xử lý ĐỘC LẬP — dán
        một ảnh cùng lúc với một đoạn nhiều dòng phải giữ được cả hai.
        """
        tep = self._duong_dan_cuc_bo(mime)
        if tep:
            self.co_tep.emit(tep)
        elif mime.hasImage():
            # `elif`: mot cu copy tep ANH trong Explorer mang CA HDROP va
            # anh. Uu tien tep vi no giu duoc ten that va dinh dang goc;
            # di qua duong anh se doi ten thanh `dan-....png` va tai ma
            # hoa lai.
            anh = mime.imageData()
            if anh is not None:
                self.co_anh.emit(anh)
        # VAN BAN: luon de Qt lam viec cua Qt. Neu mime khong co text thi
        # `super()` khong chen gi — dung nhu mong doi.
        if mime.hasText():
            super().insertFromMimeData(mime)
        elif not tep and not mime.hasImage():
            super().insertFromMimeData(mime)

    # Keo-tha: `QPlainTextEdit` mac dinh nhan tha VAN BAN. Phai nhan ca tep.

    def dragEnterEvent(self, e):                            # noqa: N802
        if self._duong_dan_cuc_bo(e.mimeData()) or e.mimeData().hasImage():
            e.acceptProposedAction()
            return
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):                             # noqa: N802
        if self._duong_dan_cuc_bo(e.mimeData()) or e.mimeData().hasImage():
            e.acceptProposedAction()
            return
        super().dragMoveEvent(e)

    def dropEvent(self, e):                                 # noqa: N802
        tep = self._duong_dan_cuc_bo(e.mimeData())
        if tep:
            self.co_tep.emit(tep)
            e.acceptProposedAction()
            return
        if e.mimeData().hasImage():
            anh = e.mimeData().imageData()
            if anh is not None:
                self.co_anh.emit(anh)
                e.acceptProposedAction()
                return
        super().dropEvent(e)


class KhoiMa(QFrame):
    """Khối mã/nhật ký kèm nút **Copy** NHÌN THẤY ĐƯỢC.

    Nút này không thay cho Ctrl+C — nó là đường cho người không dùng lối
    tắt, đúng yêu cầu "dùng được mà không cần nhớ phím nào".
    """

    def __init__(self, text: str, *, tieu_de: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._text = text or ""
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "KhoiMa{background:#f6f7f9; border:1px solid #dfe3ea;"
            "border-radius:6px;}")
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(4)

        thanh = QHBoxLayout()
        nhan = QLabel(tieu_de or "mã")
        nhan.setStyleSheet("color:#69708a; font-size:11px; font-weight:600;")
        thanh.addWidget(nhan)
        thanh.addStretch(1)
        self.nut_copy = QPushButton("Copy")
        self.nut_copy.setToolTip("Sao chép khối này vào clipboard")
        self.nut_copy.setCursor(Qt.PointingHandCursor)
        self.nut_copy.setFixedHeight(22)
        self.nut_copy.clicked.connect(self._copy)
        thanh.addWidget(self.nut_copy)
        v.addLayout(thanh)

        self.o = QPlainTextEdit(self._text)
        self.o.setReadOnly(True)            # van chon duoc; KHONG setEnabled(False)
        self.o.setFont(QFont(_MONO.split(",")[0].strip(), 9))
        self.o.setStyleSheet("QPlainTextEdit{border:none; background:transparent;}")
        self.o.setMaximumHeight(220)
        v.addWidget(self.o)

    def _copy(self) -> None:
        dat_clipboard(self._text)
        self.nut_copy.setText("Đã copy")
        self.nut_copy.setEnabled(False)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, self._reset_nut)

    def _reset_nut(self) -> None:
        self.nut_copy.setText("Copy")
        self.nut_copy.setEnabled(True)

    def van_ban(self) -> str:
        return self._text


class KhungNhatKy(QWidget):
    """Khung Logs: chọn được bằng chuột, Copy / Copy All, tìm, theo dõi.

    Cố ý KHÔNG dùng widget terminal: yêu cầu là "không có hành vi chọn kiểu
    terminal khó hiểu". Một `QPlainTextEdit` chỉ-đọc cho đúng hành vi chọn
    mà người dùng Windows đã quen.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tho = ""
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        thanh = QHBoxLayout()
        self.tim = QLineEdit()
        self.tim.setPlaceholderText("Lọc theo chữ… (để trống = hiện tất cả)")
        self.tim.setClearButtonEnabled(True)
        self.tim.setToolTip("Chỉ hiện những dòng chứa đoạn chữ này")
        self.tim.textChanged.connect(self._ve_lai)
        thanh.addWidget(self.tim, 1)

        self.nut_theo = QPushButton("Theo dõi: BẬT")
        self.nut_theo.setCheckable(True)
        self.nut_theo.setChecked(True)
        self.nut_theo.setToolTip(
            "Bật: tự cuộn xuống dòng mới nhất. Tắt: giữ nguyên chỗ đang đọc")
        self.nut_theo.setCursor(Qt.PointingHandCursor)
        self.nut_theo.toggled.connect(self._doi_nhan_theo)
        thanh.addWidget(self.nut_theo)

        self.nut_copy = QPushButton("Copy")
        self.nut_copy.setToolTip("Sao chép phần đang chọn (hoặc tất cả nếu "
                                 "chưa chọn gì)")
        self.nut_copy.setCursor(Qt.PointingHandCursor)
        self.nut_copy.clicked.connect(self.copy_chon)
        thanh.addWidget(self.nut_copy)

        self.nut_copy_all = QPushButton("Copy All")
        self.nut_copy_all.setToolTip("Sao chép toàn bộ nhật ký đang hiện")
        self.nut_copy_all.setCursor(Qt.PointingHandCursor)
        self.nut_copy_all.clicked.connect(self.copy_tat_ca)
        thanh.addWidget(self.nut_copy_all)
        v.addLayout(thanh)

        self.o = QPlainTextEdit()
        self.o.setReadOnly(True)
        self.o.setFont(QFont(_MONO.split(",")[0].strip(), 9))
        self.o.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.o.setMaximumBlockCount(20000)
        v.addWidget(self.o, 1)

    def _doi_nhan_theo(self, bat: bool) -> None:
        self.nut_theo.setText(f"Theo dõi: {'BẬT' if bat else 'TẮT'}")
        if bat:
            self._cuoi_trang()

    def dat_van_ban(self, tho: str) -> None:
        if tho == self._tho:
            return
        self._tho = tho or ""
        self._ve_lai()

    def _ve_lai(self) -> None:
        loc = self.tim.text().strip().lower()
        dong = self._tho.splitlines()
        if loc:
            dong = [d for d in dong if loc in d.lower()]
        # `dat_van_ban_giu_chon` giu VUNG DANG BOI DEN. Ban truoc goi
        # `setPlainText()` tho, nen nhat ky cua mot viec DANG mọc log xoa
        # vung chon moi lan co dong moi — nguoi dung boi den 3 dong roi bam
        # Ctrl+C thi duoc rong, hoac nut Copy roi ve nhanh "copy tat ca" va
        # dan ra CA nhat ky thay vi 3 dong ho chon. Sai am tham.
        theo = self.nut_theo.isChecked()
        co_doi = dat_van_ban_giu_chon(self.o, "\n".join(dong))
        if theo and co_doi:
            self._cuoi_trang()

    def _cuoi_trang(self) -> None:
        sb = self.o.verticalScrollBar()
        sb.setValue(sb.maximum())

    def van_ban_dang_hien(self) -> str:
        return self.o.toPlainText()

    def copy_chon(self) -> None:
        chon = self.o.textCursor().selectedText()
        if chon:
            # `selectedText()` tra ve U+2029 (PARAGRAPH SEPARATOR)
            # thay cho MOI ngat dong, nen dan nguyen van vao Notepad
            # se ra mot dong dai. Phai doi lai thanh newline.
            #
            # Dung HANG SO co ten, khong viet ky tu tho vao day: ky
            # tu tho vo hinh trong dif, va `str.splitlines()` cua
            # Python coi U+2029 la mot ngat dong — moi cong cu doc
            # tep deu thay dong nay bi cat lam hai.
            dat_clipboard(chon.replace(NGAT_DOAN, "\n"))
        else:
            self.copy_tat_ca()

    def copy_tat_ca(self) -> None:
        dat_clipboard(self.o.toPlainText())


class HopThoai(QDialog):
    """Hộp thoại nền: có nút **X** nhìn thấy được, và Escape đóng được.

    `QDialog` đã đóng bằng Escape sẵn (`reject`), nhưng nút X thì phải tự
    thêm: cửa sổ con trong Qt không chắc có nút đóng của hệ điều hành ở mọi
    kiểu cửa sổ. Yêu cầu là "mọi modal/panel phải có nút X nhìn thấy được",
    nên nút đó được dựng ở đây, một lần, cho mọi hộp thoại.
    """

    def __init__(self, tieu_de: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(tieu_de)
        self.setModal(True)
        self.setMinimumSize(560, 380)
        ngoai = QVBoxLayout(self)
        ngoai.setContentsMargins(0, 0, 0, 0)

        thanh = QHBoxLayout()
        thanh.setContentsMargins(12, 10, 8, 6)
        nhan = QLabel(tieu_de)
        nhan.setStyleSheet("font-size:14px; font-weight:700;")
        thanh.addWidget(nhan)
        thanh.addStretch(1)
        # `×` (U+00D7 MULTIPLICATION SIGN), KHONG dung `✕`
        # (U+2715 MULTIPLICATION X): Segoe UI khong co glyph cho
        # U+2715 nen no ra HINH O VUONG. Mot o vuong tofu khong phai
        # "nut X nhin thay duoc" — do la yeu cau nghiem thu so 4, nen
        # day khong phai chuyen tham my.
        self.nut_x = QPushButton("×")
        self.nut_x.setToolTip("Đóng (Esc)")
        self.nut_x.setCursor(Qt.PointingHandCursor)
        self.nut_x.setFixedSize(30, 26)
        self.nut_x.setStyleSheet(
            "QPushButton{border:none; font-size:19px; color:#5a6070;}"
            "QPushButton:hover{background:#e8eaf0; border-radius:5px;}")
        self.nut_x.clicked.connect(self.reject)
        thanh.addWidget(self.nut_x)
        ngoai.addLayout(thanh)

        self.than = QVBoxLayout()
        self.than.setContentsMargins(12, 0, 12, 12)
        ngoai.addLayout(self.than, 1)


def menu_copy(widget: QWidget, lay_text: Callable[[], str]) -> None:
    """Gắn menu chuột phải có **Copy** cho một widget KHÔNG phải ô văn bản.

    Ô văn bản của Qt đã có menu này sẵn. Thẻ việc, hàng bảng, huy hiệu thì
    không — và yêu cầu là "chuột phải có Copy/Paste ở nơi hợp lý".
    """
    widget.setContextMenuPolicy(Qt.CustomContextMenu)

    def _mo(diem):
        m = QMenu(widget)
        m.addAction("Copy", lambda: dat_clipboard(lay_text()))
        m.exec(widget.mapToGlobal(diem))

    widget.customContextMenuRequested.connect(_mo)


def cac_phim_tat_bi_cam() -> List[str]:
    """Những tổ hợp KHÔNG được đăng ký ở phạm vi ứng dụng, ở bất kỳ đâu.

    Trả về dạng chuẩn hoá để bài kiểm so sánh. Giành một trong các tổ hợp
    này là cách chắc chắn nhất làm hỏng clipboard của mọi ô văn bản.
    """
    return [QKeySequence(s).toString() for s in
            ("Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A", "Ctrl+Z", "Ctrl+Y")]
