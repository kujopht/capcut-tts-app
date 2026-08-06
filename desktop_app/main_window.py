"""
Cua so chinh cua Fanfic Audio Studio.

4 trang: Tao TTS / Hang doi / Ket qua / Cai dat.
Moi thao tac cham deu chay trong thread rieng (xem workers.py) nen giao dien
khong bao gio bi treo khi goi API.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyleOptionProgressBar,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app import APP_NAME, APP_VERSION
from desktop_app.models import (
    JOB_COUNT_CONFIRM_THRESHOLD,
    MAX_CHUNK_CHARS,
    MAX_WORKERS,
    MIN_CHUNK_CHARS,
    ErrorKind,
    InputItem,
    InputKind,
    Job,
    JobState,
    QueueState,
    VoiceEntry,
    human_size,
)
from desktop_app.output_manager import FFMPEG_HELP, find_ffmpeg
from desktop_app.queue_manager import QueueManager, build_jobs, estimate_job_count
from desktop_app.resources import app_icon_png, load_app_icon
from desktop_app.settings_manager import (
    RATE_CHOICES,
    SettingsManager,
    default_output_dir,
    user_data_dir,
)
from desktop_app.text_chunker import estimate_part_count, normalize_chunk_size
from desktop_app.text_importer import FILE_DIALOG_FILTER, make_text_item
from desktop_app.theme import THEME_DARK, THEME_LIGHT, build_stylesheet, palette, state_color
from desktop_app.tts_service import TtsService
from desktop_app.voice_catalog import SORT_MODES, VoiceCatalog, VoiceCatalogError
from desktop_app.workers import (
    ImportWorker,
    LibraryWorker,
    MergeWorker,
    PreviewWorker,
    QueueBridge,
    ZipWorker,
    job_snapshot,
)

# Logo sidebar: du de nhan dien, du nho de khong lay khong gian lam viec.
SIDEBAR_LOGO_SIZE = 44

STATE_LABELS = {
    "pending": "Chờ",
    "running": "Đang chạy",
    "success": "Thành công",
    "partial": "Một phần",
    "failed": "Thất bại",
    "stopped": "Đã dừng",
    "skipped": "Bỏ qua",
    "unknown": "Không rõ",
}

QUEUE_STATE_LABELS = {
    "idle": "Chờ lệnh",
    "running": "Đang chạy",
    "paused": "Tạm dừng",
    "stopping": "Đang dừng...",
    "stopped": "Đã dừng",
    "blocked": "ĐÃ CHẶN",
    "finished": "Hoàn tất",
}


def open_in_explorer(path: Path | str) -> None:
    """Mo thu muc (hoac chon file) trong Windows Explorer."""
    target = Path(path)
    try:
        if os.name == "nt":
            if target.is_file():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                os.startfile(str(target))  # type: ignore[attr-defined]
            return
    except Exception:
        pass
    folder = target if target.is_dir() else target.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


# -----------------------------------------------------------------------------
# Delegate ve progress bar trong o bang (nhe hon la nhung QProgressBar that)
# -----------------------------------------------------------------------------


class ProgressDelegate(QStyledItemDelegate):
    """
    Ve progress bar cho cot tien trinh cua bang job.

    Chu % duoc ve tay bang mau chu cua theme: neu de Qt tu ve, chu lay mau tu
    palette mac dinh nen rat kho doc tren nen thanh tien trinh.
    """

    def __init__(self, parent=None, text_color: str = "#E9E9F2"):
        super().__init__(parent)
        self.text_color = text_color

    def paint(self, painter, option, index):
        value = index.data(Qt.ItemDataRole.UserRole)
        if value is None:
            super().paint(painter, option, index)
            return
        try:
            percent = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            super().paint(painter, option, index)
            return

        bar = QStyleOptionProgressBar()
        bar.rect = option.rect.adjusted(4, 5, -4, -5)
        bar.minimum = 0
        bar.maximum = 100
        bar.progress = percent
        bar.textVisible = False
        QApplication.style().drawControl(
            QStyle.ControlElement.CE_ProgressBar, bar, painter
        )

        painter.save()
        painter.setPen(QColor(self.text_color))
        painter.drawText(
            bar.rect,
            int(Qt.AlignmentFlag.AlignCenter),
            str(index.data(Qt.ItemDataRole.DisplayRole) or f"{percent}%"),
        )
        painter.restore()


# -----------------------------------------------------------------------------
# Vung keo tha file
# -----------------------------------------------------------------------------


class DropZone(QFrame):
    """Khung keo-tha nhieu file/thu muc."""

    pathsDropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(58)
        self.setMaximumHeight(78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)
        # Mot label duy nhat (2 dong) de khong bao gio bi chong chu khi khung hep
        label = QLabel(
            "⬇  <b>Kéo &amp; thả file hoặc thư mục vào đây</b><br>"
            "<span style='font-size:11px;'>Hỗ trợ .txt, .md, .docx — hoặc bấm để chọn file</span>"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

    def _set_active(self, active: bool) -> None:
        self.setObjectName("DropZoneActive" if active else "DropZone")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_active(False)

    def dropEvent(self, event) -> None:
        self._set_active(False)
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            self.pathsDropped.emit(paths)
            event.acceptProposedAction()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# -----------------------------------------------------------------------------
# Cua so chinh
# -----------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, app_icon: Optional[QIcon] = None):
        super().__init__()

        self.settings = SettingsManager()
        self.catalog = VoiceCatalog()
        self.catalog.set_favorites(self.settings.favorites)

        self.inputs: List[InputItem] = []
        self.jobs: List[Job] = []
        self._job_rows: Dict[str, int] = {}
        self._selected_voice_uids: set[str] = set()
        self._visible_voices: List[VoiceEntry] = []
        self._catalog_error: str = ""

        self.queue: Optional[QueueManager] = None
        self.bridge = QueueBridge()
        self._import_worker: Optional[ImportWorker] = None
        self._preview_worker: Optional[PreviewWorker] = None
        self._zip_worker: Optional[ZipWorker] = None
        self._merge_worker: Optional[MergeWorker] = None
        self._library_worker: Optional[LibraryWorker] = None
        self._library_runs: List[Dict[str, Any]] = []

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        # app.py da truyen icon vao; neu cua so duoc tao tu noi khac thi tu nap
        # lai tu assets de title bar / Alt+Tab / Taskbar luon co icon.
        if app_icon is None:
            app_icon = load_app_icon()
        if app_icon is not None:
            self.setWindowIcon(app_icon)
        self.setMinimumSize(QSize(1100, 660))
        self.resize(1320, 780)
        self.setAcceptDrops(True)

        self._build_ui()
        self._connect_bridge()
        self._apply_theme(self.settings.theme)
        self._restore_window()
        self._load_catalog(initial=True)
        self._refresh_all_summaries()
        self._update_api_status()
        self._update_queue_buttons()

    # =========================================================================
    # Dung giao dien
    # =========================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 12)
        right_layout.setSpacing(10)

        self.pages = QStackedWidget()
        self.page_create = self._build_create_page()
        self.page_queue = self._build_queue_page()
        self.page_results = self._build_results_page()
        self.page_settings = self._build_settings_page()
        for page in (self.page_create, self.page_queue, self.page_results, self.page_settings):
            self.pages.addWidget(page)

        right_layout.addWidget(self.pages, 1)
        root.addWidget(right, 1)
        self.setCentralWidget(central)

        # -- status bar: trang thai API luon nhin thay
        self.api_status_label = QLabel("API: đang kiểm tra...")
        self.api_status_label.setObjectName("StatusPill")
        self.queue_status_label = QLabel("Hàng đợi: chờ lệnh")
        self.queue_status_label.setObjectName("StatusPill")
        self.ffmpeg_status_label = QLabel("ffmpeg: —")
        self.ffmpeg_status_label.setObjectName("StatusPill")

        status = self.statusBar()
        status.addPermanentWidget(self.ffmpeg_status_label)
        status.addPermanentWidget(self.queue_status_label)
        status.addPermanentWidget(self.api_status_label)
        status.showMessage("Sẵn sàng.")

    def _build_sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(212)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        layout.addWidget(self._build_brand())
        tag = QLabel(f"v{APP_VERSION} · offline desktop")
        tag.setObjectName("SidebarTag")
        layout.addWidget(tag)
        layout.addSpacing(8)

        self.nav_buttons: List[QPushButton] = []
        for index, (icon, text) in enumerate(
            [("✍️", "Tạo TTS"), ("📋", "Hàng đợi"), ("🎵", "Kết quả"), ("⚙️", "Cài đặt")]
        ):
            button = QPushButton(f"  {icon}   {text}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.clicked.connect(lambda _checked, i=index: self._go_to_page(i))
            layout.addWidget(button)
            self.nav_buttons.append(button)

        layout.addStretch(1)

        self.sidebar_summary = QLabel("—")
        self.sidebar_summary.setObjectName("Hint")
        self.sidebar_summary.setWordWrap(True)
        layout.addWidget(self.sidebar_summary)
        return bar

    def _build_brand(self) -> QWidget:
        """
        Khu vuc thuong hieu gon o dau sidebar: logo + ten app + dong phu.

        Co y giu nho (logo 44px) de khong an vao khong gian lam viec.
        """
        brand = QWidget()
        brand.setObjectName("SidebarBrand")
        brand.setToolTip(f"{APP_NAME} v{APP_VERSION}")
        row = QHBoxLayout(brand)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(10)

        self.brand_logo = QLabel()
        self.brand_logo.setObjectName("SidebarLogo")
        self.brand_logo.setFixedSize(SIDEBAR_LOGO_SIZE, SIDEBAR_LOGO_SIZE)
        self.brand_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_brand_logo()
        row.addWidget(self.brand_logo, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        name = QLabel(APP_NAME)
        name.setObjectName("SidebarBrandName")
        name.setWordWrap(True)
        text_col.addWidget(name)

        subtitle = QLabel("Text to Speech")
        subtitle.setObjectName("SidebarBrandSub")
        text_col.addWidget(subtitle)

        row.addLayout(text_col, 1)
        return brand

    def _apply_brand_logo(self) -> None:
        """Nap assets/app_icon.png vao logo sidebar (co ho tro man hinh HiDPI)."""
        png = app_icon_png()
        if png is not None:
            pixmap = QPixmap(str(png))
            if not pixmap.isNull():
                ratio = self.devicePixelRatioF() or 1.0
                edge = max(1, int(round(SIDEBAR_LOGO_SIZE * ratio)))
                scaled = pixmap.scaled(
                    edge,
                    edge,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(ratio)
                self.brand_logo.setPixmap(scaled)
                return
        # Khong co file logo -> van hien thi duoc, khong lam vo giao dien
        self.brand_logo.setText("🎧")

    def _go_to_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        if index == 2:
            self._reload_library()

    @staticmethod
    def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            layout.addWidget(label)
        return card, layout

    # -------------------------------------------------------------------------
    # Trang 1: Tao TTS
    # -------------------------------------------------------------------------

    def _build_create_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Tạo TTS")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        hint = QLabel("Nhập văn bản hoặc thêm nhiều file, chọn giọng, rồi bấm Bắt đầu")
        hint.setObjectName("PageHint")
        header.addWidget(hint)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ---- ben trai: van ban + file
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        text_card, text_layout = self._card("Văn bản")
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "Gõ hoặc dán nội dung tại đây...\n\n"
            "Văn bản dài sẽ tự chia thành nhiều phần tại ranh giới đoạn/câu."
        )
        self.text_edit.setMinimumHeight(110)
        self.text_edit.textChanged.connect(self._on_text_changed)
        text_layout.addWidget(self.text_edit)

        self.char_label = QLabel("0 ký tự · 0 phần")
        self.char_label.setObjectName("Hint")
        text_layout.addWidget(self.char_label)

        text_row = QHBoxLayout()
        add_text_btn = QPushButton("➕ Thêm vào danh sách")
        add_text_btn.setToolTip("Thêm nội dung trong ô văn bản thành một nguồn mới")
        add_text_btn.clicked.connect(self._add_text_as_input)
        text_row.addWidget(add_text_btn, 1)
        clear_text_btn = QPushButton("Xoá ô văn bản")
        clear_text_btn.setObjectName("Ghost")
        clear_text_btn.clicked.connect(self.text_edit.clear)
        text_row.addWidget(clear_text_btn)
        text_layout.addLayout(text_row)
        left_layout.addWidget(text_card)

        files_card, files_layout = self._card("Danh sách nguồn (văn bản & file)")
        self.drop_zone = DropZone()
        self.drop_zone.pathsDropped.connect(self._import_paths)
        self.drop_zone.clicked.connect(self._choose_files)
        files_layout.addWidget(self.drop_zone)

        # Luoi 2 cot: khong bi cat chu khi cua so hep (1366x768)
        file_buttons = QGridLayout()
        file_buttons.setHorizontalSpacing(8)
        file_buttons.setVerticalSpacing(6)
        for column, (label, slot, ghost) in enumerate(
            (
                ("📄 Chọn nhiều file...", self._choose_files, False),
                ("📁 Nhập cả thư mục...", self._choose_directory, False),
            )
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            file_buttons.addWidget(button, 0, column)
        for column, (label, slot) in enumerate(
            (
                ("Xoá dòng đã chọn", self._remove_selected_inputs),
                ("Xoá tất cả", self._clear_inputs),
            )
        ):
            button = QPushButton(label)
            button.setObjectName("Ghost")
            button.clicked.connect(slot)
            file_buttons.addWidget(button, 1, column)
        files_layout.addLayout(file_buttons)

        self.input_table = QTableWidget(0, 6)
        self.input_table.setHorizontalHeaderLabels(
            ["Tên", "Đường dẫn", "Ký tự", "Phần", "Giọng được gán", "Trạng thái"]
        )
        self.input_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.input_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.input_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.input_table.setAlternatingRowColors(True)
        self.input_table.verticalHeader().setVisible(False)
        # 6 cot khong the vua trong mot khung hep, nen dat be ngang co dinh
        # (keo tay duoc) + cuon ngang, thay vi de cac cot bi bop thanh "...".
        header_view = self.input_table.horizontalHeader()
        for col, width in ((0, 150), (1, 150), (2, 66), (3, 54), (4, 132), (5, 116)):
            header_view.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self.input_table.setColumnWidth(col, width)
        header_view.setStretchLastSection(True)
        self.input_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.input_table.setWordWrap(False)
        self.input_table.setMinimumHeight(150)
        self.input_table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        files_layout.addWidget(self.input_table, 1)

        left_layout.addWidget(files_card, 1)

        splitter.addWidget(left)

        # ---- ben phai: catalog voice
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        voice_card, voice_layout = self._card("Thư viện giọng đọc (Voice.json)")

        search_row = QHBoxLayout()
        self.voice_search = QLineEdit()
        self.voice_search.setPlaceholderText("Tìm theo tên hoặc voice_type...")
        self.voice_search.setClearButtonEnabled(True)
        self.voice_search.textChanged.connect(self._refresh_voice_table)
        search_row.addWidget(self.voice_search, 1)
        voice_layout.addLayout(search_row)

        filter_row = QHBoxLayout()
        self.lang_filter = QComboBox()
        self.lang_filter.currentIndexChanged.connect(self._refresh_voice_table)
        filter_row.addWidget(QLabel("Ngôn ngữ:"))
        filter_row.addWidget(self.lang_filter, 1)

        self.sort_combo = QComboBox()
        for key, label in SORT_MODES:
            self.sort_combo.addItem(label, key)
        self.sort_combo.currentIndexChanged.connect(self._refresh_voice_table)
        filter_row.addWidget(QLabel("Sắp xếp:"))
        filter_row.addWidget(self.sort_combo, 1)
        voice_layout.addLayout(filter_row)

        fav_row = QHBoxLayout()
        self.fav_only_check = QCheckBox("Chỉ hiện ★ yêu thích")
        self.fav_only_check.stateChanged.connect(self._refresh_voice_table)
        fav_row.addWidget(self.fav_only_check)
        fav_row.addStretch(1)
        reload_btn = QPushButton("🔄 Tải lại catalog")
        reload_btn.setObjectName("Ghost")
        reload_btn.clicked.connect(lambda: self._load_catalog(initial=False))
        fav_row.addWidget(reload_btn)
        voice_layout.addLayout(fav_row)

        self.voice_table = QTableWidget(0, 6)
        self.voice_table.setHorizontalHeaderLabels(
            ["", "★", "Tên hiển thị", "Ngôn ngữ", "voice_type", "resource_id"]
        )
        self.voice_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.voice_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.voice_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.voice_table.setAlternatingRowColors(True)
        self.voice_table.verticalHeader().setVisible(False)
        vheader = self.voice_table.horizontalHeader()
        vheader.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.voice_table.setColumnWidth(0, 30)
        vheader.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.voice_table.setColumnWidth(1, 28)
        # Ten hien thi duoc uu tien khong gian; voice_type/resource_id dat rong
        # co dinh (co the keo tay) de ten dai khong "an" het cot ten.
        vheader.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        vheader.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        vheader.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.voice_table.setColumnWidth(4, 148)
        vheader.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.voice_table.setColumnWidth(5, 104)
        vheader.setMinimumSectionSize(28)
        self.voice_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.voice_table.setWordWrap(False)
        self.voice_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.voice_table.itemChanged.connect(self._on_voice_item_changed)
        self.voice_table.cellClicked.connect(self._on_voice_cell_clicked)
        voice_layout.addWidget(self.voice_table, 1)

        select_row = QGridLayout()
        select_row.setHorizontalSpacing(8)
        select_row.setVerticalSpacing(6)

        select_all = QPushButton("Chọn tất cả (đang lọc)")
        select_all.clicked.connect(self._select_all_filtered)
        select_row.addWidget(select_all, 0, 0)
        clear_all = QPushButton("Bỏ chọn tất cả")
        clear_all.setObjectName("Ghost")
        clear_all.clicked.connect(self._deselect_all_voices)
        select_row.addWidget(clear_all, 0, 1)

        # Gan giong cho nguon: dat canh phan chon giong cho cung mach thao tac
        assign_all = QPushButton("Gán cho TẤT CẢ nguồn")
        assign_all.setToolTip("Áp dụng các giọng đang chọn cho tất cả nguồn trong danh sách")
        assign_all.clicked.connect(self._assign_voices_to_all)
        select_row.addWidget(assign_all, 1, 0)
        assign_selected = QPushButton("Gán cho dòng đã chọn")
        assign_selected.setToolTip("Áp dụng các giọng đang chọn cho những dòng đang được chọn")
        assign_selected.clicked.connect(self._assign_voices_to_selected)
        select_row.addWidget(assign_selected, 1, 1)
        clear_assign = QPushButton("Bỏ gán riêng (dùng giọng chung cho mọi nguồn)")
        clear_assign.setObjectName("Ghost")
        clear_assign.setToolTip("Quay lại dùng nhóm giọng chung đang chọn ở thư viện")
        clear_assign.clicked.connect(self._clear_assignment_for_selected)
        select_row.addWidget(clear_assign, 2, 0, 1, 2)
        voice_layout.addLayout(select_row)

        self.preview_btn = QPushButton("🔊 Thử giọng đang chọn (1 câu ngắn)")
        self.preview_btn.clicked.connect(self._preview_voice)
        voice_layout.addWidget(self.preview_btn)

        self.preview_status = QLabel("Chỉ gọi API khi bạn bấm nút này.")
        self.preview_status.setObjectName("Hint")
        self.preview_status.setWordWrap(True)
        voice_layout.addWidget(self.preview_status)

        self.voice_count_label = QLabel("—")
        self.voice_count_label.setObjectName("Hint")
        self.voice_count_label.setWordWrap(True)
        voice_layout.addWidget(self.voice_count_label)

        right_layout.addWidget(voice_card, 1)
        splitter.addWidget(right)
        # Thu vien giong can nhieu cot nen duoc uu tien be ngang hon mot chut.
        # Nguoi dung keo lai duoc va vi tri se duoc luu lai.
        splitter.setSizes([560, 760])
        left.setMinimumWidth(360)
        right.setMinimumWidth(380)
        self.create_splitter = splitter
        outer.addWidget(splitter, 1)

        # ---- tom tat + nut bat dau
        summary_card, summary_layout = self._card()
        summary_row = QHBoxLayout()
        self.summary_label = QLabel("0 nguồn × 0 giọng = 0 job")
        self.summary_label.setObjectName("SummaryBig")
        summary_row.addWidget(self.summary_label)
        self.summary_detail = QLabel("")
        self.summary_detail.setObjectName("Hint")
        summary_row.addWidget(self.summary_detail, 1)
        summary_row.addStretch(1)

        self.start_btn = QPushButton("▶  BẮT ĐẦU TẠO AUDIO")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start_queue)
        summary_row.addWidget(self.start_btn)
        summary_layout.addLayout(summary_row)

        self.summary_warning = QLabel("")
        self.summary_warning.setObjectName("WarnLabel")
        self.summary_warning.setWordWrap(True)
        self.summary_warning.setVisible(False)
        summary_layout.addWidget(self.summary_warning)

        outer.addWidget(summary_card)
        return page

    # -------------------------------------------------------------------------
    # Trang 2: Hang doi
    # -------------------------------------------------------------------------

    def _build_queue_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Hàng đợi")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.queue_state_label = QLabel("Chờ lệnh")
        self.queue_state_label.setObjectName("StatusPill")
        header.addWidget(self.queue_state_label)
        outer.addLayout(header)

        control_card, control_layout = self._card()
        buttons = QHBoxLayout()
        self.btn_start = QPushButton("▶ Start")
        self.btn_start.setObjectName("Primary")
        self.btn_start.clicked.connect(self._start_queue)
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.clicked.connect(self._pause_queue)
        self.btn_resume = QPushButton("⏵ Resume")
        self.btn_resume.clicked.connect(self._resume_queue)
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setObjectName("Danger")
        self.btn_stop.clicked.connect(self._stop_queue)
        self.btn_retry_failed = QPushButton("↻ Retry failed")
        self.btn_retry_failed.clicked.connect(self._retry_failed)
        self.btn_retry_one = QPushButton("↻ Retry job đang chọn")
        self.btn_retry_one.clicked.connect(self._retry_selected_job)
        for button in (
            self.btn_start, self.btn_pause, self.btn_resume, self.btn_stop,
            self.btn_retry_failed, self.btn_retry_one,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.btn_open_run = QPushButton("📂 Mở thư mục lần chạy")
        self.btn_open_run.setObjectName("Ghost")
        self.btn_open_run.clicked.connect(self._open_run_dir)
        buttons.addWidget(self.btn_open_run)
        control_layout.addLayout(buttons)

        progress_row = QHBoxLayout()
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setFormat("Tổng: %p%")
        progress_row.addWidget(self.overall_progress, 1)
        self.queue_stats_label = QLabel("Chưa có job")
        self.queue_stats_label.setObjectName("Hint")
        progress_row.addWidget(self.queue_stats_label)
        control_layout.addLayout(progress_row)

        self.stop_note = QLabel(
            "ℹ️ Stop/Pause có hiệu lực sau khi request hiện tại kết thúc hoặc hết "
            "timeout — một HTTP request đang chạy không thể bị hủy giữa đường."
        )
        self.stop_note.setObjectName("Hint")
        self.stop_note.setWordWrap(True)
        control_layout.addWidget(self.stop_note)
        outer.addWidget(control_card)

        self.job_table = QTableWidget(0, 7)
        self.job_table.setHorizontalHeaderLabels(
            ["Nguồn", "Giọng", "Trạng thái", "Tiến trình", "Phần", "Thời gian", "Chi tiết"]
        )
        self.job_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.job_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.job_table.setAlternatingRowColors(True)
        self.job_table.verticalHeader().setVisible(False)
        self.progress_delegate = ProgressDelegate(
            self.job_table, text_color=palette(self.settings.theme)["text"]
        )
        self.job_table.setItemDelegateForColumn(3, self.progress_delegate)
        jheader = self.job_table.horizontalHeader()
        jheader.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        jheader.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        jheader.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        jheader.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.job_table.setColumnWidth(3, 130)
        jheader.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        jheader.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        jheader.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.job_table, 1)

        log_card, log_layout = self._card("Nhật ký & thông báo")
        self.log_panel = QPlainTextEdit()
        self.log_panel.setObjectName("LogPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setMaximumHeight(132)
        log_layout.addWidget(self.log_panel)
        outer.addWidget(log_card)
        return page

    # -------------------------------------------------------------------------
    # Trang 3: Ket qua
    # -------------------------------------------------------------------------

    def _build_results_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Kết quả")
        title.setObjectName("PageTitle")
        header.addWidget(title)
        header.addStretch(1)
        reload_btn = QPushButton("🔄 Tải lại thư viện")
        reload_btn.setObjectName("Ghost")
        reload_btn.clicked.connect(self._reload_library)
        header.addWidget(reload_btn)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        runs_card, runs_layout = self._card("Các lần chạy")
        self.runs_list = QListWidget()
        self.runs_list.currentRowChanged.connect(self._on_run_selected)
        runs_layout.addWidget(self.runs_list, 1)
        splitter.addWidget(runs_card)

        detail_card, detail_layout = self._card("Nội dung lần chạy")
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["Nguồn / Giọng / File", "Trạng thái", "Dung lượng"])
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.itemDoubleClicked.connect(lambda *_: self._play_selected_audio())
        rheader = self.result_tree.header()
        rheader.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rheader.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        rheader.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        detail_layout.addWidget(self.result_tree, 1)

        actions = QHBoxLayout()
        for label, slot in (
            ("▶ Nghe / Mở MP3", self._play_selected_audio),
            ("📂 Mở thư mục", self._open_selected_folder),
            ("🗜 Xuất ZIP lần chạy", self._zip_selected_run),
            ("📋 Sao chép đường dẫn", self._copy_selected_path),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        detail_layout.addLayout(actions)

        self.result_note = QLabel(
            "Mẹo: nháy đúp vào một file để mở bằng ứng dụng phát nhạc mặc định của Windows."
        )
        self.result_note.setObjectName("Hint")
        self.result_note.setWordWrap(True)
        detail_layout.addWidget(self.result_note)

        splitter.addWidget(detail_card)
        splitter.setSizes([300, 900])
        runs_card.setMinimumWidth(200)
        self.results_splitter = splitter
        outer.addWidget(splitter, 1)
        return page

    # -------------------------------------------------------------------------
    # Trang 4: Cai dat
    # -------------------------------------------------------------------------

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        title = QLabel("Cài đặt")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        # --- ket qua & xu ly
        out_card, out_layout = self._card("Kết quả & xử lý")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        row = 0

        grid.addWidget(QLabel("Thư mục kết quả:"), row, 0)
        self.output_dir_edit = QLineEdit(str(self.settings.output_dir))
        grid.addWidget(self.output_dir_edit, row, 1)
        browse_out = QPushButton("Chọn...")
        browse_out.clicked.connect(self._choose_output_dir)
        grid.addWidget(browse_out, row, 2)
        open_out = QPushButton("Mở")
        open_out.setObjectName("Ghost")
        open_out.clicked.connect(lambda: open_in_explorer(self.settings.output_dir))
        grid.addWidget(open_out, row, 3)
        row += 1

        grid.addWidget(QLabel("Kích thước mỗi phần (ký tự):"), row, 0)
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(MIN_CHUNK_CHARS, MAX_CHUNK_CHARS)
        self.chunk_spin.setSingleStep(100)
        self.chunk_spin.setValue(self.settings.chunk_chars)
        self.chunk_spin.valueChanged.connect(self._on_chunk_changed)
        grid.addWidget(self.chunk_spin, row, 1)
        grid.addWidget(
            QLabel(f"Mặc định 2000 · cho phép {MIN_CHUNK_CHARS}–{MAX_CHUNK_CHARS}"), row, 2, 1, 2
        )
        row += 1

        grid.addWidget(QLabel("Tốc độ đọc:"), row, 0)
        self.rate_combo = QComboBox()
        self.rate_combo.setEditable(True)
        for choice in RATE_CHOICES:
            self.rate_combo.addItem(choice)
        self.rate_combo.setCurrentText(self.settings.rate)
        grid.addWidget(self.rate_combo, row, 1)
        grid.addWidget(QLabel("1.0 = bình thường"), row, 2, 1, 2)
        row += 1

        grid.addWidget(QLabel("Số worker song song:"), row, 0)
        self.worker_spin = QSpinBox()
        self.worker_spin.setRange(1, MAX_WORKERS)
        self.worker_spin.setValue(self.settings.workers)
        grid.addWidget(self.worker_spin, row, 1)
        grid.addWidget(
            QLabel(f"Tối đa {MAX_WORKERS} để tránh bị API giới hạn tần suất"), row, 2, 1, 2
        )
        row += 1

        grid.addWidget(QLabel("Theme:"), row, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Tối (mặc định)", THEME_DARK)
        self.theme_combo.addItem("Sáng", THEME_LIGHT)
        self.theme_combo.setCurrentIndex(0 if self.settings.theme == THEME_DARK else 1)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        grid.addWidget(self.theme_combo, row, 1)
        row += 1

        grid.addWidget(QLabel("Đường dẫn ffmpeg:"), row, 0)
        self.ffmpeg_edit = QLineEdit(self.settings.ffmpeg_path)
        self.ffmpeg_edit.setPlaceholderText("Để trống = tự tìm trong PATH")
        grid.addWidget(self.ffmpeg_edit, row, 1)
        browse_ffmpeg = QPushButton("Chọn...")
        browse_ffmpeg.clicked.connect(self._choose_ffmpeg)
        grid.addWidget(browse_ffmpeg, row, 2)
        check_ffmpeg = QPushButton("Kiểm tra")
        check_ffmpeg.setObjectName("Ghost")
        check_ffmpeg.clicked.connect(self._check_ffmpeg)
        grid.addWidget(check_ffmpeg, row, 3)
        row += 1

        out_layout.addLayout(grid)
        self.ffmpeg_note = QLabel("")
        self.ffmpeg_note.setObjectName("Hint")
        self.ffmpeg_note.setWordWrap(True)
        out_layout.addWidget(self.ffmpeg_note)
        outer.addWidget(out_card)

        # --- API / device
        api_card, api_layout = self._card("Cấu hình API (device.json)")
        api_layout.addWidget(
            self._hint(
                "Ứng dụng dùng device mặc định của SDK. Nếu bị HTTP 403 hoặc shark "
                "block, hãy nhập device.json riêng của bạn.\n"
                "File được COPY vào thư mục dữ liệu người dùng, không nằm trong "
                "Program Files, không đóng gói vào EXE và không commit vào repo."
            )
        )
        device_row = QHBoxLayout()
        self.device_edit = QLineEdit(self.settings.device_json_path)
        self.device_edit.setReadOnly(True)
        self.device_edit.setPlaceholderText("(chưa cấu hình — đang dùng device mặc định)")
        device_row.addWidget(self.device_edit, 1)
        import_device = QPushButton("Nhập device.json...")
        import_device.clicked.connect(self._import_device_json)
        device_row.addWidget(import_device)
        clear_device = QPushButton("Xoá cấu hình")
        clear_device.setObjectName("Ghost")
        clear_device.clicked.connect(self._clear_device_json)
        device_row.addWidget(clear_device)
        api_layout.addLayout(device_row)
        self.device_note = QLabel("")
        self.device_note.setObjectName("Hint")
        self.device_note.setWordWrap(True)
        api_layout.addWidget(self.device_note)
        api_layout.addWidget(
            self._hint(f"Thư mục dữ liệu người dùng: {user_data_dir()}")
        )
        outer.addWidget(api_card)

        # --- catalog
        cat_card, cat_layout = self._card("Thư viện giọng (Voice.json)")
        cat_row = QHBoxLayout()
        self.catalog_edit = QLineEdit(self.settings.catalog_path)
        self.catalog_edit.setPlaceholderText("Để trống = dùng Voice.json cạnh ứng dụng")
        cat_row.addWidget(self.catalog_edit, 1)
        browse_cat = QPushButton("Chọn...")
        browse_cat.clicked.connect(self._choose_catalog)
        cat_row.addWidget(browse_cat)
        reload_cat = QPushButton("Tải lại")
        reload_cat.setObjectName("Ghost")
        reload_cat.clicked.connect(lambda: self._load_catalog(initial=False))
        cat_row.addWidget(reload_cat)
        cat_layout.addLayout(cat_row)
        self.catalog_note = QLabel("")
        self.catalog_note.setObjectName("Hint")
        self.catalog_note.setWordWrap(True)
        cat_layout.addWidget(self.catalog_note)
        outer.addWidget(cat_card)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_btn = QPushButton("💾 Lưu cài đặt")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save_settings)
        save_row.addWidget(save_btn)
        outer.addLayout(save_row)
        outer.addStretch(1)
        return page

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Hint")
        label.setWordWrap(True)
        return label

    # =========================================================================
    # Theme, cua so
    # =========================================================================

    def _apply_theme(self, theme: str) -> None:
        self._theme = theme if theme in (THEME_DARK, THEME_LIGHT) else THEME_DARK
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self._theme))
        self._restyle_tables()

    def _restyle_tables(self) -> None:
        """Ve lai mau trang thai va chu % sau khi doi theme."""
        if hasattr(self, "progress_delegate"):
            self.progress_delegate.text_color = palette(self._theme)["text"]
            self.job_table.viewport().update()
        for job_id in list(self._job_rows):
            job = self._find_job(job_id)
            if job is not None:
                self._update_job_row(job_snapshot(job))

    def _on_theme_changed(self) -> None:
        theme = self.theme_combo.currentData() or THEME_DARK
        self.settings.theme = theme
        self._apply_theme(theme)
        self._log("info", f"Đã đổi theme: {theme}")

    def _restore_window(self) -> None:
        geometry = self.settings.load_geometry()
        if geometry:
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass
        state = self.settings.load_window_state()
        if state:
            try:
                self.restoreState(state)
            except Exception:
                pass
        for name, splitter in (
            ("create", getattr(self, "create_splitter", None)),
            ("results", getattr(self, "results_splitter", None)),
        ):
            saved = self.settings.load_splitter(name)
            if saved is not None and splitter is not None:
                try:
                    splitter.restoreState(saved)
                except Exception:
                    pass

    def closeEvent(self, event) -> None:
        if self.queue is not None and self.queue.is_active:
            answer = QMessageBox.question(
                self,
                "Hàng đợi đang chạy",
                "Hàng đợi vẫn đang chạy. Dừng và thoát?\n\n"
                "Lưu ý: request đang gửi sẽ chạy đến khi xong hoặc hết timeout. "
                "Các phần đã tạo được giữ lại và lần sau có thể tiếp tục.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.queue.stop()

        try:
            self.settings.save_window(self.saveGeometry(), self.saveState())
            for name, splitter in (
                ("create", getattr(self, "create_splitter", None)),
                ("results", getattr(self, "results_splitter", None)),
            ):
                if splitter is not None:
                    self.settings.save_splitter(name, splitter.saveState())
            self.settings.favorites = self.catalog.favorites
            self.settings.last_selected_voices = sorted(self._selected_voice_uids)
            self.settings.sync()
        except Exception:
            pass
        event.accept()

    # Keo tha vao bat ky dau trong cua so
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            self._import_paths(paths)
            event.acceptProposedAction()

    # =========================================================================
    # Catalog giong
    # =========================================================================

    def _load_catalog(self, initial: bool = False) -> None:
        configured = ""
        if hasattr(self, "catalog_edit"):
            configured = self.catalog_edit.text().strip()
        elif self.settings.catalog_path:
            configured = self.settings.catalog_path

        try:
            self.catalog.load(Path(configured) if configured else None)
            self._catalog_error = ""
            removed = self.catalog.prune_favorites()
            note = f"Đã nạp {self.catalog.count} giọng từ {self.catalog.path}"
            if self.catalog.skipped_entries:
                note += f" (bỏ qua {self.catalog.skipped_entries} bản ghi không hợp lệ)"
            if removed:
                note += f" · bỏ {removed} mục yêu thích không còn tồn tại"
            if hasattr(self, "catalog_note"):
                self.catalog_note.setText(note)
            self._log("info", note)
        except VoiceCatalogError as exc:
            self._catalog_error = str(exc)
            self.catalog.voices = []
            if hasattr(self, "catalog_note"):
                self.catalog_note.setText(f"⚠️ {exc}")
            self._log("error", f"Voice.json: {exc}")
            if not initial:
                self.statusBar().showMessage(f"Lỗi Voice.json: {exc}", 8000)

        # Nap lai bo loc ngon ngu
        if hasattr(self, "lang_filter"):
            self.lang_filter.blockSignals(True)
            current = self.lang_filter.currentData()
            self.lang_filter.clear()
            self.lang_filter.addItem("Tất cả", "")
            for lang in self.catalog.languages():
                self.lang_filter.addItem(lang, lang)
            if current:
                index = self.lang_filter.findData(current)
                if index >= 0:
                    self.lang_filter.setCurrentIndex(index)
            self.lang_filter.blockSignals(False)

        if initial:
            remembered = set(self.settings.last_selected_voices)
            self._selected_voice_uids = {
                uid for uid in remembered if self.catalog.get(uid) is not None
            }
        else:
            self._selected_voice_uids = {
                uid for uid in self._selected_voice_uids if self.catalog.get(uid) is not None
            }

        self._refresh_voice_table()
        self._refresh_all_summaries()

    def _refresh_voice_table(self) -> None:
        if not hasattr(self, "voice_table"):
            return
        query = self.voice_search.text() if hasattr(self, "voice_search") else ""
        language = self.lang_filter.currentData() if hasattr(self, "lang_filter") else ""
        favorites_only = self.fav_only_check.isChecked() if hasattr(self, "fav_only_check") else False
        sort_mode = self.sort_combo.currentData() if hasattr(self, "sort_combo") else "name_asc"

        voices = self.catalog.filter(
            query=query or "",
            language=language or None,
            favorites_only=favorites_only,
            sort_mode=sort_mode or "name_asc",
        )
        self._visible_voices = voices

        self.voice_table.blockSignals(True)
        self.voice_table.setRowCount(len(voices))
        for row, voice in enumerate(voices):
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(
                Qt.CheckState.Checked
                if voice.uid in self._selected_voice_uids
                else Qt.CheckState.Unchecked
            )
            check.setData(Qt.ItemDataRole.UserRole, voice.uid)
            self.voice_table.setItem(row, 0, check)

            star = QTableWidgetItem("★" if self.catalog.is_favorite(voice.uid) else "☆")
            star.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            star.setToolTip("Bấm để bật/tắt yêu thích")
            self.voice_table.setItem(row, 1, star)

            name_item = QTableWidgetItem(voice.label)
            name_item.setToolTip(
                f"{voice.label}\nvoice_type: {voice.voice_type}\n"
                f"resource_id: {voice.resource_id or '(không có)'}\n"
                f"ngôn ngữ: {voice.language or '(không có)'}"
            )
            self.voice_table.setItem(row, 2, name_item)
            self.voice_table.setItem(row, 3, QTableWidgetItem(voice.language or "—"))
            self.voice_table.setItem(row, 4, QTableWidgetItem(voice.voice_type))
            self.voice_table.setItem(row, 5, QTableWidgetItem(voice.resource_id or "—"))
        self.voice_table.blockSignals(False)

        total = self.catalog.count
        selected = len(self._selected_voice_uids)
        favorites = len(self.catalog.favorites)
        if self._catalog_error:
            self.voice_count_label.setText(f"⚠️ {self._catalog_error}")
        else:
            self.voice_count_label.setText(
                f"Hiện {len(voices)}/{total} giọng · đã chọn {selected} · ★ {favorites}"
            )

    def _on_voice_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if not uid:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_voice_uids.add(uid)
        else:
            self._selected_voice_uids.discard(uid)
        self._refresh_all_summaries()
        self._update_voice_counter()

    def _update_voice_counter(self) -> None:
        if self._catalog_error:
            return
        self.voice_count_label.setText(
            f"Hiện {len(self._visible_voices)}/{self.catalog.count} giọng · "
            f"đã chọn {len(self._selected_voice_uids)} · ★ {len(self.catalog.favorites)}"
        )

    def _on_voice_cell_clicked(self, row: int, column: int) -> None:
        if column != 1 or row >= len(self._visible_voices):
            return
        voice = self._visible_voices[row]
        is_fav = self.catalog.toggle_favorite(voice.uid)
        self.settings.favorites = self.catalog.favorites
        item = self.voice_table.item(row, 1)
        if item is not None:
            item.setText("★" if is_fav else "☆")
        if self.fav_only_check.isChecked():
            self._refresh_voice_table()
        else:
            self._update_voice_counter()

    def _select_all_filtered(self) -> None:
        if not self._visible_voices:
            return
        count = len(self._visible_voices)
        if count > JOB_COUNT_CONFIRM_THRESHOLD:
            answer = QMessageBox.question(
                self,
                "Chọn nhiều giọng",
                f"Bạn đang chọn {count} giọng đang lọc.\n\n"
                "Số job sẽ là (số nguồn × số giọng) và có thể tạo rất nhiều request. "
                "Vẫn tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        for voice in self._visible_voices:
            self._selected_voice_uids.add(voice.uid)
        self._refresh_voice_table()
        self._refresh_all_summaries()

    def _deselect_all_voices(self) -> None:
        self._selected_voice_uids.clear()
        self._refresh_voice_table()
        self._refresh_all_summaries()

    def _selected_voices(self) -> List[VoiceEntry]:
        return self.catalog.resolve(sorted(self._selected_voice_uids))

    def _current_voice(self) -> Optional[VoiceEntry]:
        row = self.voice_table.currentRow()
        if 0 <= row < len(self._visible_voices):
            return self._visible_voices[row]
        selected = self._selected_voices()
        return selected[0] if selected else None

    # =========================================================================
    # Nhap van ban / file
    # =========================================================================

    def _on_text_changed(self) -> None:
        text = self.text_edit.toPlainText()
        parts = estimate_part_count(text, self.chunk_spin.value() if hasattr(self, "chunk_spin") else 2000)
        self.char_label.setText(f"{len(text):,} ký tự · {parts} phần".replace(",", "."))

    def _on_chunk_changed(self) -> None:
        self._on_text_changed()
        self._refresh_input_table()
        self._refresh_all_summaries()

    def _add_text_as_input(self) -> None:
        text = self.text_edit.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("Ô văn bản đang trống.", 4000)
            return
        name = f"van_ban_{datetime.now().strftime('%H-%M-%S')}"
        item = make_text_item(text, name=name)
        self.inputs.append(item)
        self.text_edit.clear()
        self._refresh_input_table()
        self._refresh_all_summaries()
        self._log("info", f"Đã thêm văn bản trực tiếp ({item.char_count} ký tự)")

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Chọn nhiều file văn bản", str(Path.home()), FILE_DIALOG_FILTER
        )
        if paths:
            self._import_paths(paths)

    def _choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục chứa file văn bản", str(Path.home())
        )
        if directory:
            self._import_paths([directory])

    def _import_paths(self, paths: List[str]) -> None:
        if self._import_worker is not None and self._import_worker.isRunning():
            self.statusBar().showMessage("Đang nhập file, vui lòng chờ...", 3000)
            return
        worker = ImportWorker(paths)
        worker.progress.connect(
            lambda done, total, name: self.statusBar().showMessage(
                f"Đang đọc {done}/{total}: {name}", 2000
            )
        )
        worker.finishedWithItems.connect(self._on_import_finished)
        worker.failed.connect(lambda msg: self._log("error", f"Nhập file thất bại: {msg}"))
        self._import_worker = worker
        worker.start()

    def _on_import_finished(self, items: List[InputItem]) -> None:
        if not items:
            self._log("warn", "Không tìm thấy file .txt/.md/.docx nào.")
            self.statusBar().showMessage("Không tìm thấy file được hỗ trợ.", 5000)
            return

        existing = {i.path for i in self.inputs if i.path}
        added = 0
        skipped = 0
        errors = 0
        for item in items:
            if item.path and item.path in existing:
                skipped += 1
                continue
            self.inputs.append(item)
            existing.add(item.path or "")
            added += 1
            if item.error:
                errors += 1

        self._refresh_input_table()
        self._refresh_all_summaries()
        message = f"Đã thêm {added} nguồn"
        if skipped:
            message += f" · bỏ qua {skipped} file trùng"
        if errors:
            message += f" · {errors} file lỗi (xem cột Trạng thái)"
        self._log("warn" if errors else "info", message)
        self.statusBar().showMessage(message, 6000)

    def _refresh_input_table(self) -> None:
        chunk = self.chunk_spin.value() if hasattr(self, "chunk_spin") else 2000
        colors = palette(getattr(self, "_theme", THEME_DARK))
        self.input_table.setRowCount(len(self.inputs))

        for row, item in enumerate(self.inputs):
            icon = "📝" if item.kind == InputKind.TEXT else "📄"
            name_item = QTableWidgetItem(f"{icon} {item.name}")
            self.input_table.setItem(row, 0, name_item)

            path_item = QTableWidgetItem(item.source_label())
            path_item.setToolTip(item.source_label())
            self.input_table.setItem(row, 1, path_item)

            self.input_table.setItem(row, 2, QTableWidgetItem(f"{item.char_count:,}".replace(",", ".")))

            parts = estimate_part_count(item.text, chunk) if item.is_valid else 0
            self.input_table.setItem(row, 3, QTableWidgetItem(str(parts)))

            if item.voice_uids:
                voices = self.catalog.resolve(item.voice_uids)
                assigned = f"{len(voices)} giọng riêng"
                tooltip = "\n".join(v.label for v in voices)
            else:
                assigned = "(dùng giọng chung)"
                tooltip = "Sẽ dùng các giọng đang chọn ở thư viện bên phải"
            voice_item = QTableWidgetItem(assigned)
            voice_item.setToolTip(tooltip)
            self.input_table.setItem(row, 4, voice_item)

            status_item = QTableWidgetItem(item.status_text)
            if item.error:
                status_item.setForeground(Qt.GlobalColor.red)
                status_item.setToolTip(item.error)
            self.input_table.setItem(row, 5, status_item)

    def _remove_selected_inputs(self) -> None:
        rows = sorted({index.row() for index in self.input_table.selectedIndexes()}, reverse=True)
        if not rows:
            self.statusBar().showMessage("Chưa chọn dòng nào.", 3000)
            return
        for row in rows:
            if 0 <= row < len(self.inputs):
                self.inputs.pop(row)
        self._refresh_input_table()
        self._refresh_all_summaries()
        self._log("info", f"Đã xoá {len(rows)} nguồn khỏi danh sách")

    def _clear_inputs(self) -> None:
        if not self.inputs:
            return
        self.inputs.clear()
        self._refresh_input_table()
        self._refresh_all_summaries()
        self._log("info", "Đã xoá toàn bộ danh sách nguồn")

    def _assign_voices_to_all(self) -> None:
        uids = sorted(self._selected_voice_uids)
        if not uids:
            self.statusBar().showMessage("Chưa chọn giọng nào để gán.", 4000)
            return
        for item in self.inputs:
            item.voice_uids = list(uids)
        self._refresh_input_table()
        self._refresh_all_summaries()
        self._log("info", f"Đã gán {len(uids)} giọng cho tất cả {len(self.inputs)} nguồn")

    def _assign_voices_to_selected(self) -> None:
        uids = sorted(self._selected_voice_uids)
        rows = sorted({index.row() for index in self.input_table.selectedIndexes()})
        if not uids:
            self.statusBar().showMessage("Chưa chọn giọng nào để gán.", 4000)
            return
        if not rows:
            self.statusBar().showMessage("Chưa chọn dòng nào trong bảng nguồn.", 4000)
            return
        for row in rows:
            if 0 <= row < len(self.inputs):
                self.inputs[row].voice_uids = list(uids)
        self._refresh_input_table()
        self._refresh_all_summaries()
        self._log("info", f"Đã gán {len(uids)} giọng cho {len(rows)} nguồn")

    def _clear_assignment_for_selected(self) -> None:
        rows = sorted({index.row() for index in self.input_table.selectedIndexes()})
        target = rows or range(len(self.inputs))
        for row in target:
            if 0 <= row < len(self.inputs):
                self.inputs[row].voice_uids = []
        self._refresh_input_table()
        self._refresh_all_summaries()

    # =========================================================================
    # Tom tat so job
    # =========================================================================

    def _plan_jobs(self) -> List[Job]:
        """Dung danh sach job theo trang thai hien tai cua giao dien."""
        chunk = self.chunk_spin.value()
        rate = self.rate_combo.currentText().strip() or "1.0"
        common = self._selected_voices()

        jobs: List[Job] = []
        for item in self.inputs:
            if not item.is_valid:
                continue
            voices = self.catalog.resolve(item.voice_uids) if item.voice_uids else common
            if not voices:
                continue
            jobs.extend(build_jobs([item], voices, chunk, rate))
        return jobs

    def _refresh_all_summaries(self) -> None:
        if not hasattr(self, "summary_label"):
            return

        valid_inputs = [i for i in self.inputs if i.is_valid]
        invalid = len(self.inputs) - len(valid_inputs)
        voices = self._selected_voices()
        jobs = self._plan_jobs()
        total_parts = sum(job.total_parts for job in jobs)

        simple_count = estimate_job_count(len(valid_inputs), len(voices))
        self.summary_label.setText(
            f"{len(valid_inputs)} nguồn × {len(voices)} giọng = {len(jobs)} job"
        )
        detail = f"{total_parts} phần audio sẽ được tạo"
        if invalid:
            detail += f" · {invalid} nguồn lỗi bị bỏ qua"
        if any(i.voice_uids for i in self.inputs):
            detail += f" · có gán giọng riêng (công thức chung sẽ là {simple_count})"
        self.summary_detail.setText(detail)

        warning = ""
        if len(jobs) > JOB_COUNT_CONFIRM_THRESHOLD:
            warning = (
                f"⚠️ {len(jobs)} job (> {JOB_COUNT_CONFIRM_THRESHOLD}) — sẽ cần xác nhận "
                "trước khi chạy vì số lượng request rất lớn."
            )
        elif not voices and not any(i.voice_uids for i in self.inputs):
            warning = "⚠️ Chưa chọn giọng nào. Hãy tick giọng ở thư viện bên phải."
        elif not valid_inputs:
            warning = "⚠️ Chưa có nguồn văn bản hợp lệ."
        self.summary_warning.setText(warning)
        self.summary_warning.setVisible(bool(warning))

        self.sidebar_summary.setText(
            f"{len(valid_inputs)} nguồn\n{len(voices)} giọng đã chọn\n{len(jobs)} job dự kiến"
        )
        self.start_btn.setEnabled(bool(jobs))
        if hasattr(self, "btn_start"):
            self.btn_start.setEnabled(
                bool(jobs) or (self.queue is not None and not self.queue.is_active
                               and any(j.state == JobState.PENDING for j in self.jobs))
            )
        self._update_voice_counter()

    # =========================================================================
    # Hang doi
    # =========================================================================

    def _connect_bridge(self) -> None:
        self.bridge.jobUpdated.connect(self._update_job_row)
        self.bridge.queueChanged.connect(self._on_queue_state)
        self.bridge.messagePosted.connect(self._log)
        self.bridge.queueFinished.connect(self._on_queue_finished)

    def _make_service(self) -> TtsService:
        return TtsService(device_path=self.settings.active_device_path())

    def _start_queue(self) -> None:
        if self.queue is not None and self.queue.is_active:
            self.statusBar().showMessage("Hàng đợi đang chạy.", 3000)
            return

        # Chay lai cac job dang cho (sau retry) neu nguoi dung khong doi input
        if (
            self.queue is not None
            and self.jobs
            and any(j.state == JobState.PENDING for j in self.jobs)
            and not self._plan_jobs_changed()
        ):
            self._launch_queue(reuse=True)
            return

        jobs = self._plan_jobs()
        if not jobs:
            QMessageBox.information(
                self,
                "Chưa đủ dữ liệu",
                "Cần ít nhất một nguồn văn bản hợp lệ và một giọng được chọn.",
            )
            return

        if len(jobs) > JOB_COUNT_CONFIRM_THRESHOLD:
            total_parts = sum(job.total_parts for job in jobs)
            answer = QMessageBox.warning(
                self,
                "Xác nhận số lượng job lớn",
                f"Bạn sắp chạy {len(jobs)} job "
                f"({len([i for i in self.inputs if i.is_valid])} nguồn × "
                f"{len(self._selected_voices())} giọng), tổng {total_parts} phần audio.\n\n"
                f"Con số này lớn hơn ngưỡng {JOB_COUNT_CONFIRM_THRESHOLD} và sẽ tạo rất "
                "nhiều request tới API — có thể bị giới hạn tần suất (HTTP 429) hoặc bị chặn.\n\n"
                "Bạn có chắc muốn tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self.jobs = jobs
        self._rebuild_job_table()
        self._launch_queue(reuse=False)

    def _plan_jobs_changed(self) -> bool:
        """True neu ke hoach job hien tai khac voi danh sach job dang giu."""
        planned = self._plan_jobs()
        if len(planned) != len(self.jobs):
            return True
        for new, old in zip(planned, self.jobs):
            if new.input_name != old.input_name or new.voice.uid != old.voice.uid:
                return True
        return False

    def _launch_queue(self, reuse: bool) -> None:
        try:
            outputs_root = self.settings.ensure_output_dir()
        except OSError as exc:
            QMessageBox.critical(
                self, "Không tạo được thư mục kết quả",
                f"{exc}\n\nHãy chọn thư mục khác trong Cài đặt.",
            )
            return

        if not reuse or self.queue is None:
            self.queue = QueueManager(
                outputs_root=outputs_root,
                service_factory=self._make_service,
                hooks=self.bridge.hooks(),
                workers=self.worker_spin.value(),
                ffmpeg_path=self.ffmpeg_edit.text().strip(),
            )
            self.queue.set_jobs(self.jobs)
            self.queue.output_manager.create_run()
        else:
            self.queue.workers = max(1, min(MAX_WORKERS, self.worker_spin.value()))
            self.queue.ffmpeg_path = self.ffmpeg_edit.text().strip()
            self.queue.output_manager.create_run()

        run_dir = self.queue.output_manager.run_dir
        self._log("info", f"Bắt đầu {len(self.jobs)} job · thư mục: {run_dir}")
        if not self.queue.start(run_dir=run_dir):
            self._log("warn", "Không có job nào ở trạng thái chờ.")
            return
        self._go_to_page(1)
        self._update_queue_buttons()

    def _rebuild_job_table(self) -> None:
        self.job_table.setRowCount(len(self.jobs))
        self._job_rows = {}
        for row, job in enumerate(self.jobs):
            self._job_rows[job.job_id] = row
            self.job_table.setItem(row, 0, QTableWidgetItem(job.input_name))
            self.job_table.setItem(row, 1, QTableWidgetItem(job.voice.label))
            self.job_table.setItem(row, 6, QTableWidgetItem(""))
            self._update_job_row(job_snapshot(job))

    def _find_job(self, job_id: str) -> Optional[Job]:
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    def _update_job_row(self, snapshot: Dict[str, Any]) -> None:
        row = self._job_rows.get(snapshot.get("job_id", ""))
        if row is None or row >= self.job_table.rowCount():
            return

        state = snapshot.get("state", "pending")
        theme = getattr(self, "_theme", THEME_DARK)

        status_item = QTableWidgetItem(STATE_LABELS.get(state, state))
        status_item.setForeground(QColor(state_color(theme, state)))
        self.job_table.setItem(row, 2, status_item)

        percent = int(snapshot.get("progress", 0) or 0)
        progress_item = QTableWidgetItem(f"{percent}%")
        progress_item.setData(Qt.ItemDataRole.UserRole, percent)
        self.job_table.setItem(row, 3, progress_item)

        self.job_table.setItem(
            row, 4,
            QTableWidgetItem(f"{snapshot.get('done_parts', 0)}/{snapshot.get('total_parts', 0)}"),
        )
        self.job_table.setItem(row, 5, QTableWidgetItem(str(snapshot.get("elapsed", "—"))))

        detail = str(snapshot.get("message", ""))
        error_kind = snapshot.get("error_kind") or ""
        if error_kind:
            detail = f"[{error_kind}] {detail}"
        detail_item = QTableWidgetItem(detail)
        detail_item.setToolTip(
            detail + (f"\n\n{snapshot.get('merge_note')}" if snapshot.get("merge_note") else "")
        )
        self.job_table.setItem(row, 6, detail_item)

        self._update_queue_progress()

    def _update_queue_progress(self) -> None:
        if self.queue is None:
            return
        stats = self.queue.stats()
        self.overall_progress.setValue(self.queue.overall_progress())
        self.queue_stats_label.setText(
            f"Tổng {stats['total']} · ✅ {stats['success']} · ⚠️ {stats['partial']} · "
            f"❌ {stats['failed']} · ⏹ {stats['stopped']} · ⏭ {stats['skipped']} · "
            f"⏳ {stats['pending']}"
        )

    def _on_queue_state(self, state: str) -> None:
        label = QUEUE_STATE_LABELS.get(state, state)
        self.queue_state_label.setText(f"Hàng đợi: {label}")
        self.queue_status_label.setText(f"Hàng đợi: {label}")
        self._update_queue_buttons()
        self._update_queue_progress()

    def _update_queue_buttons(self) -> None:
        state = self.queue.state.value if self.queue is not None else "idle"
        running = state == "running"
        paused = state == "paused"
        active = state in ("running", "paused", "stopping")

        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(paused)
        self.btn_stop.setEnabled(active)
        self.btn_retry_failed.setEnabled(
            not active and self.queue is not None
            and any(j.state.is_retryable for j in self.jobs)
        )
        self.btn_retry_one.setEnabled(not active and bool(self.jobs))
        self.btn_start.setEnabled(not active)
        self.start_btn.setEnabled(not active and bool(self._plan_jobs()))

    def _pause_queue(self) -> None:
        if self.queue is not None:
            self.queue.pause()

    def _resume_queue(self) -> None:
        if self.queue is not None:
            self.queue.resume()

    def _stop_queue(self) -> None:
        if self.queue is not None:
            self.queue.stop()

    def _retry_failed(self) -> None:
        if self.queue is None:
            return
        try:
            count = self.queue.retry_failed()
        except RuntimeError as exc:
            self.statusBar().showMessage(str(exc), 4000)
            return
        if not count:
            self.statusBar().showMessage("Không có job nào cần chạy lại.", 4000)
            return
        self._log("info", f"Đặt lại {count} job để chạy lại (giữ các phần đã xong)")
        self._launch_queue(reuse=True)

    def _retry_selected_job(self) -> None:
        if self.queue is None:
            return
        row = self.job_table.currentRow()
        if row < 0 or row >= len(self.jobs):
            self.statusBar().showMessage("Chưa chọn job nào.", 4000)
            return
        job = self.jobs[row]
        try:
            ok = self.queue.retry_job(job.job_id)
        except RuntimeError as exc:
            self.statusBar().showMessage(str(exc), 4000)
            return
        if not ok:
            self.statusBar().showMessage(
                "Job này không ở trạng thái có thể chạy lại.", 4000
            )
            return
        self._log("info", f"Chạy lại job: {job.label}")
        self._launch_queue(reuse=True)

    def _on_queue_finished(self, summary: Dict[str, Any]) -> None:
        blocked = summary.get("blocked_reason") or ""
        message = (
            f"Kết thúc: ✅ {summary.get('success', 0)} · ⚠️ {summary.get('partial', 0)} · "
            f"❌ {summary.get('failed', 0)} · ⏹ {summary.get('stopped', 0)} · "
            f"⏭ {summary.get('skipped', 0)}"
        )
        self._log("error" if blocked else "info", message)
        if summary.get("report"):
            self._log("info", f"report.json: {summary['report']}")
        if blocked:
            QMessageBox.critical(self, "Hàng đợi đã bị chặn", blocked)
        self._update_queue_buttons()
        self._update_queue_progress()
        self._reload_library()

    def _open_run_dir(self) -> None:
        if self.queue is not None and self.queue.output_manager.run_dir:
            open_in_explorer(self.queue.output_manager.run_dir)
        else:
            open_in_explorer(self.settings.output_dir)

    # =========================================================================
    # Thu giong
    # =========================================================================

    def _preview_voice(self) -> None:
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self.preview_status.setText("Đang thử giọng, vui lòng chờ...")
            return
        voice = self._current_voice()
        if voice is None:
            self.preview_status.setText("Hãy chọn một giọng trong bảng trước.")
            return

        worker = PreviewWorker(
            voice=voice,
            device_path=self.settings.active_device_path(),
            rate=self.rate_combo.currentText().strip() or "1.0",
        )
        worker.statusChanged.connect(self.preview_status.setText)
        worker.succeeded.connect(self._on_preview_ready)
        worker.failed.connect(self._on_preview_failed)
        worker.finished.connect(lambda: self.preview_btn.setEnabled(True))
        self._preview_worker = worker
        self.preview_btn.setEnabled(False)
        self.preview_status.setText(f"Đang gọi API để thử giọng {voice.label}...")
        worker.start()

    def _on_preview_ready(self, uid: str, path: str) -> None:
        voice = self.catalog.get(uid)
        name = voice.label if voice else uid
        self.preview_status.setText(f"✅ {name}: đã tạo file thử, đang mở...")
        self._log("info", f"Thử giọng thành công: {name} → {path}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_preview_failed(self, uid: str, kind: str, message: str) -> None:
        voice = self.catalog.get(uid)
        name = voice.label if voice else uid
        self.preview_status.setText(f"❌ {name}: [{kind}] {message}")
        self._log("error", f"Thử giọng thất bại ({name}) [{kind}]: {message}")

    # =========================================================================
    # Ket qua / thu vien
    # =========================================================================

    def _reload_library(self) -> None:
        if self._library_worker is not None and self._library_worker.isRunning():
            return
        worker = LibraryWorker(self.settings.output_dir)
        worker.loaded.connect(self._on_library_loaded)
        worker.failed.connect(lambda msg: self._log("error", msg))
        self._library_worker = worker
        worker.start()

    def _on_library_loaded(self, runs: List[Dict[str, Any]]) -> None:
        self._library_runs = runs
        self.runs_list.clear()
        for run in runs:
            summary = run.get("summary") or {}
            ok = summary.get("success", 0)
            label = f"{run.get('name')}  ·  {run.get('audio_count', 0)} file"
            if ok:
                label += f"  ·  ✅ {ok}"
            item = QListWidgetItem(label)
            item.setToolTip(str(run.get("run_dir")))
            self.runs_list.addItem(item)
        if runs:
            self.runs_list.setCurrentRow(0)
        else:
            placeholder = QListWidgetItem("(chưa có lần chạy nào)")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.runs_list.addItem(placeholder)
            self.result_tree.clear()
            self.result_note.setText(
                f"Chưa có kết quả nào trong {self.settings.output_dir}\n"
                "Hãy tạo audio ở trang “Tạo TTS”, kết quả sẽ xuất hiện tại đây."
            )

    def _on_run_selected(self, row: int) -> None:
        self.result_tree.clear()
        if row < 0 or row >= len(self._library_runs):
            return
        run = self._library_runs[row]

        by_input: Dict[str, List[Dict[str, Any]]] = {}
        for job in run.get("jobs") or []:
            by_input.setdefault(str(job.get("input_name") or "?"), []).append(job)

        for input_name, jobs in by_input.items():
            parent = QTreeWidgetItem([f"📁 {input_name}", "", ""])
            for job in jobs:
                state = str(job.get("state") or "unknown")
                job_node = QTreeWidgetItem(
                    [
                        f"🎙 {job.get('voice_label')}",
                        STATE_LABELS.get(state, state),
                        f"{job.get('done_parts', 0)}/{job.get('total_parts', 0)} phần",
                    ]
                )
                job_node.setData(0, Qt.ItemDataRole.UserRole, job.get("job_dir"))
                job_node.setToolTip(0, str(job.get("message") or ""))
                if job.get("merge_note"):
                    job_node.setToolTip(1, str(job.get("merge_note")))
                for audio in job.get("audios") or []:
                    icon = "⭐" if audio.get("is_full") else "🎵"
                    node = QTreeWidgetItem(
                        [f"{icon} {audio.get('name')}", "", human_size(int(audio.get("size") or 0))]
                    )
                    node.setData(0, Qt.ItemDataRole.UserRole, audio.get("path"))
                    job_node.addChild(node)
                parent.addChild(job_node)
            self.result_tree.addTopLevelItem(parent)
        self.result_tree.expandAll()

        note = f"Thư mục: {run.get('run_dir')}"
        if not run.get("has_report"):
            note += "  ·  (không có report.json)"
        self.result_note.setText(note)

    def _selected_result_path(self) -> Optional[Path]:
        item = self.result_tree.currentItem()
        while item is not None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                return Path(str(data))
            item = item.parent()
        row = self.runs_list.currentRow()
        if 0 <= row < len(self._library_runs):
            return Path(str(self._library_runs[row].get("run_dir")))
        return None

    def _play_selected_audio(self) -> None:
        path = self._selected_result_path()
        if path is None:
            self.statusBar().showMessage("Chưa chọn file nào.", 3000)
            return
        if path.is_dir():
            open_in_explorer(path)
            return
        if not path.is_file():
            self.statusBar().showMessage(f"Không tìm thấy: {path}", 5000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.statusBar().showMessage(f"Đang mở {path.name} bằng trình phát mặc định.", 5000)

    def _open_selected_folder(self) -> None:
        path = self._selected_result_path()
        if path is None:
            open_in_explorer(self.settings.output_dir)
            return
        open_in_explorer(path)

    def _copy_selected_path(self) -> None:
        path = self._selected_result_path()
        if path is None:
            self.statusBar().showMessage("Chưa chọn gì để sao chép.", 3000)
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(str(path))
        self.statusBar().showMessage(f"Đã sao chép: {path}", 5000)

    def _zip_selected_run(self) -> None:
        row = self.runs_list.currentRow()
        if row < 0 or row >= len(self._library_runs):
            self.statusBar().showMessage("Chưa chọn lần chạy nào.", 3000)
            return
        if self._zip_worker is not None and self._zip_worker.isRunning():
            self.statusBar().showMessage("Đang xuất ZIP...", 3000)
            return
        run_dir = self._library_runs[row].get("run_dir")
        worker = ZipWorker(str(run_dir))
        worker.succeeded.connect(self._on_zip_done)
        worker.failed.connect(lambda msg: self._log("error", msg))
        self._zip_worker = worker
        self.statusBar().showMessage("Đang nén ZIP...", 0)
        worker.start()

    def _on_zip_done(self, path: str) -> None:
        self._log("info", f"Đã xuất ZIP: {path}")
        self.statusBar().showMessage(f"Đã xuất ZIP: {path}", 8000)
        open_in_explorer(path)

    # =========================================================================
    # Cai dat
    # =========================================================================

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu kết quả", str(self.settings.output_dir)
        )
        if directory:
            self.output_dir_edit.setText(directory)

    def _choose_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ffmpeg.exe", "", "ffmpeg (ffmpeg.exe);;Tất cả file (*)"
        )
        if path:
            self.ffmpeg_edit.setText(path)
            self._check_ffmpeg()

    def _check_ffmpeg(self) -> None:
        found = find_ffmpeg(self.ffmpeg_edit.text().strip())
        if found:
            self.ffmpeg_note.setText(f"✅ Tìm thấy ffmpeg: {found}")
        else:
            self.ffmpeg_note.setText(f"⚠️ Chưa tìm thấy ffmpeg.\n\n{FFMPEG_HELP}")
        self._update_api_status()

    def _choose_catalog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn Voice.json", "", "JSON (*.json);;Tất cả file (*)"
        )
        if path:
            self.catalog_edit.setText(path)
            self._load_catalog(initial=False)

    def _import_device_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn device.json", str(Path.home()), "JSON (*.json);;Tất cả file (*)"
        )
        if not path:
            return
        try:
            target = self.settings.import_device_json(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Không nhập được device.json", str(exc))
            self.device_note.setText(f"⚠️ {exc}")
            return
        self.device_edit.setText(str(target))
        self.device_note.setText(
            f"✅ Đã lưu bản runtime tại: {target}\n"
            "Nội dung file không được hiển thị trong app và không ghi vào log."
        )
        self._log("info", "Đã nhập device.json (nội dung không được ghi vào log)")
        self._update_api_status()

    def _clear_device_json(self) -> None:
        self.settings.clear_device_json()
        self.device_edit.setText("")
        self.device_note.setText("Đã xoá cấu hình — quay lại dùng device mặc định của SDK.")
        self._update_api_status()

    def _save_settings(self) -> None:
        try:
            self.settings.output_dir = self.output_dir_edit.text().strip() or str(default_output_dir())
            self.settings.chunk_chars = self.chunk_spin.value()
            self.settings.rate = self.rate_combo.currentText().strip() or "1.0"
            self.settings.workers = self.worker_spin.value()
            self.settings.ffmpeg_path = self.ffmpeg_edit.text().strip()
            self.settings.catalog_path = self.catalog_edit.text().strip()
            self.settings.theme = self.theme_combo.currentData() or THEME_DARK
            self.settings.favorites = self.catalog.favorites
            self.settings.sync()
        except Exception as exc:
            QMessageBox.warning(self, "Không lưu được cài đặt", str(exc))
            return
        self.chunk_spin.setValue(normalize_chunk_size(self.chunk_spin.value()))
        self._refresh_input_table()
        self._refresh_all_summaries()
        self._update_api_status()
        self.statusBar().showMessage("Đã lưu cài đặt.", 5000)
        self._log("info", "Đã lưu cài đặt")

    # =========================================================================
    # Trang thai & log
    # =========================================================================

    def _update_api_status(self) -> None:
        device = self.settings.active_device_path()
        if device:
            self.api_status_label.setText("API: device.json riêng")
            self.api_status_label.setToolTip(f"Đang dùng: {device}")
        else:
            self.api_status_label.setText("API: device mặc định")
            self.api_status_label.setToolTip(
                "Đang dùng device mặc định của SDK. Nếu bị 403/shark block, "
                "hãy nhập device.json riêng trong Cài đặt."
            )

        ffmpeg = find_ffmpeg(
            self.ffmpeg_edit.text().strip() if hasattr(self, "ffmpeg_edit") else ""
        )
        self.ffmpeg_status_label.setText("ffmpeg: ✅" if ffmpeg else "ffmpeg: ⚠️ thiếu")
        self.ffmpeg_status_label.setToolTip(
            ffmpeg or "Chưa có ffmpeg — vẫn tạo được các part, chỉ chưa ghép file full."
        )

        if hasattr(self, "device_note") and not self.device_note.text():
            self.device_note.setText(
                f"Đang dùng: {'device.json riêng' if device else 'device mặc định của SDK'}"
            )

    def _log(self, level: str, text: str) -> None:
        if not hasattr(self, "log_panel"):
            return
        prefix = {"info": "•", "warn": "⚠", "error": "✖"}.get(level, "•")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_panel.appendPlainText(f"[{stamp}] {prefix} {text}")
        bar = self.log_panel.verticalScrollBar()
        bar.setValue(bar.maximum())
        if level in ("warn", "error"):
            self.statusBar().showMessage(text, 9000)
