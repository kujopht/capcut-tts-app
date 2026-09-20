"""
Discovery UI — Content Factory v2.

Desktop UI components for candidate discovery, deterministic filtering,
Gemini evaluation, and candidate inspection dialog.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scripts.content_factory.discovery_engine import DiscoveryEngine
from scripts.content_factory.discovery_models import (
    CandidateState,
    DeterministicFilterConfig,
    DiscoveredCandidate,
    GeminiCandidateEvaluation,
)
from scripts.content_factory.discovery_store import DiscoveryStore


class SampleChapterDialog(QDialog):
    """Displays a read-only preview of a single chapter for quality review."""

    def __init__(self, sample_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📖 Đọc Thử Chương Mẫu (READ-ONLY) — {sample_data.get('chapter_title', 'Chương 1')}")
        self.resize(780, 600)
        self.setStyleSheet("background-color: #0f172a; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info_lbl = QLabel(
            f"<b>Chương:</b> {sample_data.get('chapter_title')} | "
            f"<b>Độ dài:</b> {sample_data.get('word_count', 0):,} từ "
            f"({sample_data.get('character_count', 0):,} ký tự)<br>"
            "<span style='color: #38bdf8;'>Chế độ Đọc Thử Nguồn thuần túy (READ-ONLY). Hoàn toàn không dịch hay sinh TTS.</span>"
        )
        info_lbl.setStyleSheet("background-color: #1e293b; padding: 10px; border-radius: 6px; font-size: 11px;")
        layout.addWidget(info_lbl)

        txt_view = QTextEdit()
        txt_view.setReadOnly(True)
        txt_view.setStyleSheet("""
            QTextEdit {
                background-color: #111827; color: #e2e8f0; font-family: 'Segoe UI', sans-serif;
                font-size: 12px; line-height: 1.6; border: 1px solid #374151; border-radius: 6px; padding: 10px;
            }
        """)

        paragraphs = sample_data.get("sample_paragraphs", [])
        if paragraphs:
            txt_view.setPlainText("\n\n".join(paragraphs))
        else:
            txt_view.setPlainText(sample_data.get("full_text_snippet", "Không có nội dung mẫu."))

        layout.addWidget(txt_view, stretch=1)

        btn_close = QPushButton("Đóng")
        btn_close.setStyleSheet("""
            QPushButton { background-color: #334155; color: #ffffff; padding: 8px 20px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #475569; }
        """)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


class CandidateDetailDialog(QDialog):
    """Detailed candidate inspection dialog with metadata, Gemini scores, and economics."""

    def __init__(self, candidate: DiscoveredCandidate, engine: DiscoveryEngine, parent=None):
        super().__init__(parent)
        self.candidate = candidate
        self.engine = engine
        self.setWindowTitle(f"🔍 Chi Tiết Ứng Viên: {candidate.title}")
        self.resize(920, 720)
        self.setStyleSheet("background-color: #0f172a; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 1. Header Card
        header = QFrame()
        header.setStyleSheet("background-color: #1e293b; border-radius: 8px; padding: 12px; border: 1px solid #334155;")
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(10, 10, 10, 10)

        title_lbl = QLabel(f"📖 {candidate.title}")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 900; color: #38bdf8;")
        h_layout.addWidget(title_lbl)

        meta_sub = QLabel(
            f"Tác giả: <b>{candidate.author}</b> | Fandom: <b>{candidate.fandom}</b> | "
            f"Trạng thái: <b>{candidate.status.upper()}</b> | ID: <code>{candidate.source_work_id}</code> | "
            f"URL: <a style='color: #60a5fa;' href='{candidate.url}'>{candidate.url}</a>"
        )
        meta_sub.setOpenExternalLinks(True)
        meta_sub.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        h_layout.addWidget(meta_sub)

        layout.addWidget(header)

        # 2. Main Tabbed or Split Details
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Column: Synopsis & Metadata
        left_col = QFrame()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        lbl_syn_title = QLabel("📝 TÓM TẮT TÁC PHẨM (SYNOPSIS)")
        lbl_syn_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #a7f3d0;")
        left_layout.addWidget(lbl_syn_title)

        txt_synopsis = QTextEdit()
        txt_synopsis.setReadOnly(True)
        txt_synopsis.setPlainText(candidate.description or "Không có tóm tắt chi tiết.")
        txt_synopsis.setStyleSheet("""
            QTextEdit {
                background-color: #111827; color: #e2e8f0; font-size: 11.5px; line-height: 1.5;
                border: 1px solid #374151; border-radius: 6px; padding: 8px;
            }
        """)
        left_layout.addWidget(txt_synopsis, stretch=1)

        # Stats Card
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 10px; border: 1px solid #334155;")
        sf_layout = QGridLayout(stats_frame)
        sf_layout.setContentsMargins(6, 6, 6, 6)
        sf_layout.setSpacing(6)

        sf_layout.addWidget(QLabel(f"📚 Số chương: <b>{candidate.chapter_count}</b>"), 0, 0)
        sf_layout.addWidget(QLabel(f"📄 Ước lượng từ: <b>~{candidate.estimated_word_count:,}</b>"), 0, 1)
        sf_layout.addWidget(QLabel(f"⭐ Đánh giá: <b>{candidate.rating:.2f}/5</b>"), 1, 0)
        sf_layout.addWidget(QLabel(f"👥 Followers: <b>{candidate.followers:,}</b>"), 1, 1)
        sf_layout.addWidget(QLabel(f"👁 Lượt đọc: <b>{candidate.views:,}</b>"), 2, 0)
        sf_layout.addWidget(QLabel(f"🕒 Cập nhật cuối: <b>{candidate.last_update[:19] if candidate.last_update else 'N/A'}</b>"), 2, 1)

        left_layout.addWidget(stats_frame)
        splitter.addWidget(left_col)

        # Right Column: Gemini Evaluation & Economics
        right_col = QFrame()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        lbl_gem_title = QLabel("🤖 ĐÁNH GIÁ TIỀM NĂNG (GEMINI 3.8 FLASH)")
        lbl_gem_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #facc15;")
        right_layout.addWidget(lbl_gem_title)

        eval_card = QFrame()
        eval_card.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 12px; border: 1px solid #334155;")
        ec_layout = QVBoxLayout(eval_card)
        ec_layout.setContentsMargins(8, 8, 8, 8)
        ec_layout.setSpacing(6)

        ev = candidate.gemini_eval
        score_val = candidate.overall_score
        score_color = "#4ade80" if score_val >= 8.0 else ("#facc15" if score_val >= 6.0 else "#ef4444")

        score_banner = QLabel(f"Điểm Tổng Hợp: <span style='font-size: 18px; font-weight: 900; color: {score_color};'>{score_val:.1f} / 10</span>")
        ec_layout.addWidget(score_banner)

        if ev:
            scores_grid = QGridLayout()
            scores_grid.addWidget(QLabel(f"Cốt truyện: <b>{ev.story_quality:.1f}</b>"), 0, 0)
            scores_grid.addWidget(QLabel(f"Hợp Fandom: <b>{ev.fandom_fit:.1f}</b>"), 0, 1)
            scores_grid.addWidget(QLabel(f"Giá trị dịch: <b>{ev.translation_value:.1f}</b>"), 1, 0)
            scores_grid.addWidget(QLabel(f"Tính độc đáo: <b>{ev.catalog_uniqueness:.1f}</b>"), 1, 1)
            scores_grid.addWidget(QLabel(f"Tiến độ nguồn: <b>{ev.update_health:.1f}</b>"), 2, 0)
            scores_grid.addWidget(QLabel(f"Thu thập: <b>{ev.crawlability:.1f}</b>"), 2, 1)
            ec_layout.addLayout(scores_grid)

            ec_layout.addWidget(QLabel(f"<b>Lý do chọn:</b> {ev.reasons}"))
            if ev.risks:
                ec_layout.addWidget(QLabel(f"<span style='color: #f87171;'><b>Rủi ro:</b> {ev.risks}</span>"))

            if ev.recommended_for_owner_review:
                rec_lbl = QLabel("⭐ <b>ĐƯỢC ĐỀ XUẤT CHO OWNER REVIEW</b>")
                rec_lbl.setStyleSheet("color: #4ade80; background-color: #064e3b; padding: 6px; border-radius: 4px; font-weight: bold; text-align: center;")
                ec_layout.addWidget(rec_lbl)
        else:
            ec_layout.addWidget(QLabel("Chưa thực hiện đánh giá ngữ nghĩa với Gemini. Bấm 'Đánh Giá Gemini' để chấm điểm."))

        right_layout.addWidget(eval_card)

        # Economics Card
        econ_card = QFrame()
        econ_card.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 10px; border: 1px solid #334155;")
        econ_layout = QVBoxLayout(econ_card)
        econ_layout.setContentsMargins(8, 8, 8, 8)
        econ_layout.setSpacing(4)

        lbl_econ_title = QLabel("💰 ƯỚC LƯỢNG QUY MÔ & CHI PHÍ SẢN XUẤT")
        lbl_econ_title.setStyleSheet("font-size: 10.5px; font-weight: bold; color: #38bdf8;")
        econ_layout.addWidget(lbl_econ_title)

        econ_layout.addWidget(QLabel(f"Ước lượng thời lượng Audio TTS: <b>~{candidate.estimated_tts_hours:.1f} giờ</b> (tại 150 từ/phút)"))
        econ_layout.addWidget(QLabel(f"Ước tính chi phí LLM (Flash): <b>~${candidate.estimated_translation_cost_usd:.2f} USD</b> (nếu dịch toàn bộ)"))
        right_layout.addWidget(econ_card)

        splitter.addWidget(right_col)
        splitter.setSizes([450, 450])
        layout.addWidget(splitter, stretch=1)

        # 3. Action Bar
        action_bar = QHBoxLayout()
        action_bar.setContentsMargins(0, 4, 0, 0)
        action_bar.setSpacing(10)

        self.btn_sample = QPushButton("📖 Xem Thử Chương 1 (Sample Chapter)")
        self.btn_sample.setStyleSheet("""
            QPushButton { background-color: #1e3a8a; color: #93c5fd; border: 1px solid #3b82f6; padding: 8px 16px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #1d4ed8; color: #ffffff; }
        """)
        self.btn_sample.clicked.connect(self._fetch_sample)
        action_bar.addWidget(self.btn_sample)

        self.btn_eval = QPushButton("🤖 Đánh Giá Lại Bằng Gemini")
        self.btn_eval.setStyleSheet("""
            QPushButton { background-color: #854d0e; color: #fef08a; border: 1px solid #eab308; padding: 8px 16px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #a16207; color: #ffffff; }
        """)
        self.btn_eval.clicked.connect(self._run_eval)
        action_bar.addWidget(self.btn_eval)

        action_bar.addStretch()

        btn_close = QPushButton("Đóng")
        btn_close.setStyleSheet("""
            QPushButton { background-color: #334155; color: #ffffff; padding: 8px 24px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #475569; }
        """)
        btn_close.clicked.connect(self.accept)
        action_bar.addWidget(btn_close)

        layout.addLayout(action_bar)

    def _fetch_sample(self):
        self.btn_sample.setEnabled(False)
        self.btn_sample.setText("Đang tải chương 1...")
        QApplication.processEvents()
        try:
            res = self.engine.fetch_sample_chapter(self.candidate, 1)
            dlg = SampleChapterDialog(res, self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể lấy chương mẫu: {e}")
        finally:
            self.btn_sample.setEnabled(True)
            self.btn_sample.setText("📖 Xem Thử Chương 1 (Sample Chapter)")

    def _run_eval(self):
        self.btn_eval.setEnabled(False)
        self.btn_eval.setText("Đang đánh giá...")
        QApplication.processEvents()
        try:
            self.engine.evaluate_candidate_with_gemini(self.candidate)
            self.engine.store.upsert_candidate(self.candidate)
            QMessageBox.information(self, "Hoàn tất", f"Đánh giá thành công! Điểm tổng hợp: {self.candidate.overall_score:.1f}/10")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể đánh giá: {e}")
        finally:
            self.btn_eval.setEnabled(True)
            self.btn_eval.setText("🤖 Đánh Giá Lại Bằng Gemini")


class FilterConfigDialog(QDialog):
    """Configuration dialog for cheap deterministic discovery filters."""

    def __init__(self, current_config: DeterministicFilterConfig, parent=None):
        super().__init__(parent)
        self.config = current_config
        self.setWindowTitle("⚙️ Cấu Hình Bộ Lọc Tiêu Chuẩn (Deterministic Filters)")
        self.resize(460, 360)
        self.setStyleSheet("background-color: #0f172a; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        info = QLabel(
            "<b>Bộ Lọc Quyết Định Trước Khi Đánh Giá LLM:</b><br>"
            "<span style='color: #94a3b8; font-size: 11px;'>Tự động loại bỏ các tác phẩm không đạt tiêu chuẩn tối thiểu mà không tiêu tốn tài nguyên Gemini.</span>"
        )
        layout.addWidget(info)

        form = QGridLayout()
        form.setSpacing(10)

        form.addWidget(QLabel("Số chương tối thiểu (Min chapters):"), 0, 0)
        self.spn_chapters = QSpinBox()
        self.spn_chapters.setRange(1, 1000)
        self.spn_chapters.setValue(self.config.min_chapters)
        self.spn_chapters.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 4px;")
        form.addWidget(self.spn_chapters, 0, 1)

        form.addWidget(QLabel("Số từ tối thiểu (Min words):"), 1, 0)
        self.spn_words = QSpinBox()
        self.spn_words.setRange(1000, 500000)
        self.spn_words.setSingleStep(5000)
        self.spn_words.setValue(self.config.min_words)
        self.spn_words.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 4px;")
        form.addWidget(self.spn_words, 1, 1)

        form.addWidget(QLabel("Tối đa ngày bỏ dở (Max days abandoned):"), 2, 0)
        self.spn_abandoned = QSpinBox()
        self.spn_abandoned.setRange(0, 3650)
        self.spn_abandoned.setSingleStep(30)
        self.spn_abandoned.setValue(self.config.max_days_abandoned)
        self.spn_abandoned.setStyleSheet("background-color: #1e293b; color: #ffffff; padding: 4px;")
        form.addWidget(self.spn_abandoned, 2, 1)

        layout.addLayout(form)

        self.chk_prod = QCheckBox("Loại trừ tác phẩm đã tồn tại trên Production")
        self.chk_prod.setChecked(self.config.reject_already_in_production)
        layout.addWidget(self.chk_prod)

        self.chk_prev_rej = QCheckBox("Loại trừ tác phẩm đã bị Reject từ trước")
        self.chk_prev_rej.setChecked(self.config.reject_previously_rejected)
        layout.addWidget(self.chk_prev_rej)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()

        btn_save = QPushButton("Lưu Cấu Hình")
        btn_save.setStyleSheet("background-color: #059669; color: #ffffff; padding: 6px 18px; font-weight: bold; border-radius: 4px;")
        btn_save.clicked.connect(self._save)
        btns.addWidget(btn_save)

        btn_cancel = QPushButton("Hủy")
        btn_cancel.setStyleSheet("background-color: #334155; color: #ffffff; padding: 6px 14px; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)

        layout.addLayout(btns)

    def _save(self):
        self.config.min_chapters = self.spn_chapters.value()
        self.config.min_words = self.spn_words.value()
        self.config.max_days_abandoned = self.spn_abandoned.value()
        self.config.reject_already_in_production = self.chk_prod.isChecked()
        self.config.reject_previously_rejected = self.chk_prev_rej.isChecked()
        self.accept()


class DiscoveryWidget(QWidget):
    """
    Discovery Mode Tab (Tab 1) in Content Factory v2.
    Purely read-only candidate discovery, evaluation, and pipeline intake staging.
    """

    candidate_accepted = Signal(DiscoveredCandidate)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = DiscoveryStore()
        self.engine = DiscoveryEngine(store=self.store)
        self.current_candidates: List[DiscoveredCandidate] = []
        self._init_ui()
        self._load_cached_candidates()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 1. Search & Controls Card
        ctrl_card = QFrame()
        ctrl_card.setStyleSheet("background-color: #1e293b; border-radius: 8px; padding: 10px; border: 1px solid #334155;")
        c_layout = QVBoxLayout(ctrl_card)
        c_layout.setContentsMargins(8, 8, 8, 8)
        c_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        lbl_src = QLabel("🔍 TÌM KIẾM:")
        lbl_src.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 11px;")
        row1.addWidget(lbl_src)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Nhập từ khóa tìm kiếm (vd: Naruto, One Piece, Harry Potter, Reincarnation, SI)...")
        self.txt_search.setText("Naruto")
        self.txt_search.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 6px 10px; border: 1px solid #475569; border-radius: 4px; font-size: 12px;")
        self.txt_search.returnPressed.connect(self.action_discover)
        row1.addWidget(self.txt_search, stretch=2)

        self.combo_fandom = QComboBox()
        self.combo_fandom.addItems(["Tất Cả Fandom", "Naruto", "One Piece", "Harry Potter", "Bleach", "Genshin Impact", "Dragon Ball", "Fanfiction", "Original"])
        self.combo_fandom.setStyleSheet("background-color: #0f172a; color: #ffffff; padding: 6px; border: 1px solid #475569; border-radius: 4px;")
        row1.addWidget(self.combo_fandom)

        self.btn_search = QPushButton("🔍 Khám Phá (Read-Only)")
        self.btn_search.setStyleSheet("""
            QPushButton { background-color: #2563eb; color: #ffffff; padding: 6px 16px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        self.btn_search.clicked.connect(self.action_discover)
        row1.addWidget(self.btn_search)

        self.btn_direct_url = QPushButton("🔗 Thêm Từ URL")
        self.btn_direct_url.setStyleSheet("""
            QPushButton { background-color: #475569; color: #ffffff; padding: 6px 12px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #64748b; }
        """)
        self.btn_direct_url.clicked.connect(self.action_add_from_url)
        row1.addWidget(self.btn_direct_url)

        self.btn_config = QPushButton("⚙️ Cấu Hình Lọc")
        self.btn_config.setStyleSheet("""
            QPushButton { background-color: #334155; color: #ffffff; padding: 6px 12px; font-weight: bold; border-radius: 4px; }
            QPushButton:hover { background-color: #475569; }
        """)
        self.btn_config.clicked.connect(self.action_open_config)
        row1.addWidget(self.btn_config)

        c_layout.addLayout(row1)

        # Row 2: Quick Topic Chips & Batch Evaluation
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_chips = QLabel("Gợi ý nhanh:")
        lbl_chips.setStyleSheet("color: #94a3b8; font-size: 10px;")
        row2.addWidget(lbl_chips)

        for topic in ["Naruto", "One Piece", "Harry Potter", "Reincarnation", "SI", "Bleach"]:
            btn_chip = QPushButton(topic)
            btn_chip.setStyleSheet("""
                QPushButton { background-color: #0f172a; color: #cbd5e1; border: 1px solid #475569; border-radius: 12px; padding: 2px 10px; font-size: 10px; }
                QPushButton:hover { background-color: #1e293b; color: #38bdf8; border-color: #38bdf8; }
            """)
            btn_chip.clicked.connect(lambda ch=False, t=topic: self._apply_chip(t))
            row2.addWidget(btn_chip)

        row2.addStretch()

        self.chk_show_rejected = QCheckBox("Hiện tác phẩm đã từ chối (Rejected)")
        self.chk_show_rejected.setStyleSheet("color: #94a3b8; font-size: 10.5px;")
        self.chk_show_rejected.toggled.connect(self._refresh_table)
        row2.addWidget(self.chk_show_rejected)

        self.btn_batch_eval = QPushButton("🤖 Đánh Giá Gemini Hàng Loạt")
        self.btn_batch_eval.setStyleSheet("""
            QPushButton { background-color: #854d0e; color: #fef08a; padding: 4px 14px; font-weight: bold; border-radius: 4px; font-size: 11px; }
            QPushButton:hover { background-color: #a16207; }
        """)
        self.btn_batch_eval.clicked.connect(self.action_batch_eval)
        row2.addWidget(self.btn_batch_eval)

        c_layout.addLayout(row2)
        layout.addWidget(ctrl_card)

        # 2. KPI Summary Bar
        kpi_bar = QHBoxLayout()
        kpi_bar.setSpacing(8)

        self.card_total = self._create_kpi_card("TỔNG TÌM THẤY", "0", "#38bdf8")
        self.card_passed = self._create_kpi_card("VƯỢT BỘ LỌC", "0", "#4ade80")
        self.card_evaluated = self._create_kpi_card("ĐÃ CHẤM GEMINI", "0", "#facc15")
        self.card_recommended = self._create_kpi_card("ĐƯỢC ĐỀ XUẤT", "0", "#c084fc")
        self.card_rejected = self._create_kpi_card("ĐÃ TỪ CHỐI", "0", "#f87171")

        kpi_bar.addWidget(self.card_total)
        kpi_bar.addWidget(self.card_passed)
        kpi_bar.addWidget(self.card_evaluated)
        kpi_bar.addWidget(self.card_recommended)
        kpi_bar.addWidget(self.card_rejected)
        layout.addLayout(kpi_bar)

        # 3. Candidates Table
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Điểm", "Tiêu Đề Tác Phẩm", "Fandom", "Trạng Thái", "Số Chương",
            "Ước Lượng Từ", "Cập Nhật Cuối", "Đánh Giá / Rủi Ro", "Thao Tác"
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setStyleSheet("QHeaderView::section { background-color: #1e293b; color: #94a3b8; font-weight: bold; padding: 6px; border: 1px solid #334155; }")
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a; color: #ffffff; gridline-color: #1e293b;
                border: 1px solid #334155; border-radius: 6px; selection-background-color: #1e293b;
            }
            QTableWidget::item { padding: 4px; }
        """)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, stretch=1)

        # 4. Status Bar
        status_bar = QHBoxLayout()
        self.lbl_status = QLabel("Trạng thái: Sẵn sàng khám phá tác phẩm mới (READ-ONLY). Hoàn toàn không ghi đè production.")
        self.lbl_status.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
        status_bar.addWidget(self.lbl_status)
        status_bar.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e293b; border-radius: 3px; max-height: 10px; width: 160px; text-align: center; font-size: 8px; } QProgressBar::chunk { background-color: #38bdf8; }")
        status_bar.addWidget(self.progress_bar)

        layout.addLayout(status_bar)

    def _create_kpi_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"background-color: #1e293b; border-radius: 6px; padding: 6px 12px; border-left: 3px solid {color};")
        l = QVBoxLayout(card)
        l.setContentsMargins(4, 4, 4, 4)
        l.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 9px; color: #94a3b8; font-weight: bold;")
        l.addWidget(lbl_t)

        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"font-size: 16px; font-weight: 900; color: {color};")
        lbl_v.setObjectName("val")
        l.addWidget(lbl_v)
        return card

    def _set_kpi_value(self, card: QFrame, val: str):
        lbl = card.findChild(QLabel, "val")
        if lbl:
            lbl.setText(val)

    def _apply_chip(self, topic: str):
        self.txt_search.setText(topic)
        self.action_discover()

    def action_open_config(self):
        cfg = self.store.load_filter_config()
        dlg = FilterConfigDialog(cfg, self)
        if dlg.exec():
            self.store.save_filter_config(dlg.config)
            QMessageBox.information(self, "Đã lưu", "Đã cập nhật cấu hình bộ lọc tiêu chuẩn!")
            # Re-apply filters to current candidates
            for c in self.current_candidates:
                self.engine.apply_deterministic_filters(c, config=dlg.config)
                self.store.upsert_candidate(c)
            self._refresh_table()

    def action_add_from_url(self):
        url, ok = QInputDialog.getText(self, "Thêm Từ URL", "Nhập RoyalRoad Fiction URL hoặc ID:")
        if ok and url.strip():
            self.lbl_status.setText("Đang phân tích URL...")
            QApplication.processEvents()
            cand = self.engine.discover_from_url(url.strip())
            if cand:
                self.engine.apply_deterministic_filters(cand)
                self.store.upsert_candidate(cand)
                self.current_candidates.insert(0, cand)
                self._refresh_table()
                QMessageBox.information(self, "Thành công", f"Đã thêm: {cand.title}")
            else:
                QMessageBox.warning(self, "Lỗi", "Không thể lấy thông tin tác phẩm từ URL này.")

    def action_discover(self):
        query = self.txt_search.text().strip()
        if not query:
            return

        self.btn_search.setEnabled(False)
        self.lbl_status.setText(f"Đang tìm kiếm RoyalRoad: '{query}' (READ-ONLY)...")
        self.lbl_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        QApplication.processEvents()

        try:
            f_filter = self.combo_fandom.currentText()
            if f_filter == "Tất Cả Fandom":
                f_filter = None

            cands = self.engine.search_royalroad(query, fandom_filter=f_filter, max_results=20)
            cfg = self.store.load_filter_config()
            prod_ids = self.engine.get_production_work_ids()

            for c in cands:
                self.engine.apply_deterministic_filters(c, config=cfg, prod_work_ids=prod_ids)
                self.store.upsert_candidate(c)

            self.current_candidates = cands
            self._refresh_table()
            self.lbl_status.setText(f"✅ Tìm thấy {len(cands)} ứng viên cho '{query}'. Đã áp dụng bộ lọc tiêu chuẩn.")
            self.lbl_status.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
        except Exception as e:
            self.lbl_status.setText(f"❌ Lỗi tìm kiếm: {e}")
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")
        finally:
            self.btn_search.setEnabled(True)

    def action_batch_eval(self):
        """Runs Gemini semantic evaluation for candidates that passed deterministic filtering."""
        eligible = [c for c in self.current_candidates if c.deterministic_passed and not c.gemini_eval]
        if not eligible:
            QMessageBox.information(self, "Thông báo", "Tất cả ứng viên hợp lệ đều đã được đánh giá hoặc bị loại bởi bộ lọc.")
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận đánh giá hàng loạt",
            f"Chấm điểm {len(eligible)} ứng viên bằng Gemini Flash?\n"
            "(Chỉ gửi tóm tắt & metadata — hoàn toàn KHÔNG cào hay dịch chương)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.btn_batch_eval.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        for idx, c in enumerate(eligible):
            self.lbl_status.setText(f"🤖 Đang đánh giá {idx+1}/{len(eligible)}: {c.title[:30]}...")
            self.progress_bar.setValue(int(((idx) / len(eligible)) * 100))
            QApplication.processEvents()

            self.engine.evaluate_candidate_with_gemini(c)
            self.store.upsert_candidate(c)

        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.btn_batch_eval.setEnabled(True)
        self.lbl_status.setText(f"✅ Đã hoàn tất đánh giá {len(eligible)} ứng viên!")
        self._refresh_table()

    def _load_cached_candidates(self):
        stored = self.store.list_candidates(limit=50)
        if stored:
            self.current_candidates = stored
            self._refresh_table()

    def _refresh_table(self):
        show_rej = self.chk_show_rejected.isChecked()
        displayed = [c for c in self.current_candidates if show_rej or c.state != CandidateState.REJECTED]

        # Update KPIs
        tot = len(self.current_candidates)
        passed = sum(1 for c in self.current_candidates if c.deterministic_passed)
        ev_count = sum(1 for c in self.current_candidates if c.gemini_eval is not None)
        rec_count = sum(1 for c in self.current_candidates if c.gemini_eval and c.gemini_eval.recommended_for_owner_review)
        rej_count = sum(1 for c in self.current_candidates if c.state == CandidateState.REJECTED)

        self._set_kpi_value(self.card_total, str(tot))
        self._set_kpi_value(self.card_passed, str(passed))
        self._set_kpi_value(self.card_evaluated, str(ev_count))
        self._set_kpi_value(self.card_recommended, str(rec_count))
        self._set_kpi_value(self.card_rejected, str(rej_count))

        self.table.setRowCount(len(displayed))

        for row, c in enumerate(displayed):
            # 0. Score Badge
            score_val = c.overall_score
            score_txt = f"{score_val:.1f}" if score_val > 0 else "—"
            it_score = QTableWidgetItem(score_txt)
            it_score.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font = it_score.font()
            font.setBold(True)
            it_score.setFont(font)
            if score_val >= 8.0:
                it_score.setForeground(QColor("#4ade80"))
            elif score_val >= 6.0:
                it_score.setForeground(QColor("#facc15"))
            elif c.state == CandidateState.REJECTED:
                it_score.setForeground(QColor("#64748b"))
            else:
                it_score.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 0, it_score)

            # 1. Title
            title_prefix = "⭐ " if (c.gemini_eval and c.gemini_eval.recommended_for_owner_review) else ""
            it_title = QTableWidgetItem(f"{title_prefix}{c.title}")
            it_title.setToolTip(f"URL: {c.url}\nTác giả: {c.author}")
            self.table.setItem(row, 1, it_title)

            # 2. Fandom
            it_fandom = QTableWidgetItem(c.fandom)
            it_fandom.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_fandom.setForeground(QColor("#c084fc"))
            self.table.setItem(row, 2, it_fandom)

            # 3. Status
            it_st = QTableWidgetItem(c.status.upper())
            it_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_st.setForeground(QColor("#4ade80" if c.status == "ongoing" else ("#38bdf8" if c.status == "completed" else "#f87171")))
            self.table.setItem(row, 3, it_st)

            # 4. Chapters
            it_ch = QTableWidgetItem(f"{c.chapter_count:,}")
            it_ch.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, it_ch)

            # 5. Estimated Words
            it_w = QTableWidgetItem(f"~{c.estimated_word_count:,}")
            it_w.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_w.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 5, it_w)

            # 6. Last Update
            up_str = str(c.last_update)[:10] if c.last_update else "—"
            it_up = QTableWidgetItem(up_str)
            it_up.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, it_up)

            # 7. Risk / Reason
            if c.rejection_reasons:
                risk_txt = f"⛔ {'; '.join(c.rejection_reasons)}"
            elif c.gemini_eval and c.gemini_eval.risks:
                risk_txt = f"⚠️ {c.gemini_eval.risks}"
            elif c.gemini_eval and c.gemini_eval.reasons:
                risk_txt = f"✅ {c.gemini_eval.reasons}"
            else:
                risk_txt = "Chờ đánh giá ngữ nghĩa"
            it_risk = QTableWidgetItem(risk_txt[:80] + ("..." if len(risk_txt) > 80 else ""))
            it_risk.setToolTip(risk_txt)
            self.table.setItem(row, 7, it_risk)

            # 8. Action Buttons Container
            action_widget = QWidget()
            aw_layout = QHBoxLayout(action_widget)
            aw_layout.setContentsMargins(4, 2, 4, 2)
            aw_layout.setSpacing(4)

            btn_insp = QPushButton("Chi Tiết")
            btn_insp.setStyleSheet("background-color: #1e3a8a; color: #93c5fd; border-radius: 3px; font-size: 10px; padding: 2px 6px;")
            btn_insp.clicked.connect(lambda ch=False, cand=c: self._inspect_candidate(cand))
            aw_layout.addWidget(btn_insp)

            if c.state == CandidateState.REJECTED:
                btn_restore = QPushButton("Phục Hồi")
                btn_restore.setStyleSheet("background-color: #334155; color: #cbd5e1; border-radius: 3px; font-size: 10px; padding: 2px 6px;")
                btn_restore.clicked.connect(lambda ch=False, cand=c: self._restore_candidate(cand))
                aw_layout.addWidget(btn_restore)
            else:
                btn_rej = QPushButton("Từ Chối")
                btn_rej.setStyleSheet("background-color: #7f1d1d; color: #fca5a5; border-radius: 3px; font-size: 10px; padding: 2px 6px;")
                btn_rej.clicked.connect(lambda ch=False, cand=c: self._reject_candidate(cand))
                aw_layout.addWidget(btn_rej)

                btn_pipe = QPushButton("Đưa Vào Pipeline")
                btn_pipe.setStyleSheet("background-color: #065f46; color: #a7f3d0; border-radius: 3px; font-size: 10px; font-weight: bold; padding: 2px 6px;")
                btn_pipe.setToolTip("Tạo hồ sơ tiếp nhận cục bộ (LOCAL INTAKE). Hoàn toàn KHÔNG xuất bản hay cào toàn bộ.")
                btn_pipe.clicked.connect(lambda ch=False, cand=c: self._accept_to_pipeline(cand))
                aw_layout.addWidget(btn_pipe)

            self.table.setCellWidget(row, 8, action_widget)

    def _inspect_candidate(self, candidate: DiscoveredCandidate):
        dlg = CandidateDetailDialog(candidate, self.engine, self)
        dlg.exec()
        self._refresh_table()

    def _reject_candidate(self, candidate: DiscoveredCandidate):
        candidate.state = CandidateState.REJECTED
        candidate.rejection_reasons = ["Bị từ chối thủ công bởi người vận hành (Owner Rejected)."]
        self.store.update_candidate_state(candidate.source_platform, candidate.source_work_id, CandidateState.REJECTED, candidate.rejection_reasons)
        self._refresh_table()

    def _restore_candidate(self, candidate: DiscoveredCandidate):
        candidate.state = CandidateState.DISCOVERED
        candidate.rejection_reasons = []
        candidate.deterministic_passed = True
        self.store.update_candidate_state(candidate.source_platform, candidate.source_work_id, CandidateState.DISCOVERED, [])
        self._refresh_table()

    def _accept_to_pipeline(self, candidate: DiscoveredCandidate):
        """Creates a local intake job for this candidate. Never publishes anything."""
        candidate.state = CandidateState.ACCEPTED
        self.store.update_candidate_state(candidate.source_platform, candidate.source_work_id, CandidateState.ACCEPTED)
        self.candidate_accepted.emit(candidate)
        QMessageBox.information(
            self,
            "Đã Đưa Vào Hàng Đợi Pipeline",
            f"Tác phẩm '{candidate.title}' đã được tiếp nhận vào Intake Queue Cục Bộ.\n\n"
            "LƯU Ý BẢO MẬT:\n"
            "Chế độ này chỉ chuẩn bị metadata cục bộ. Chưa có bất kỳ chương nào bị cào, dịch, hay đưa lên production.",
        )
        self._refresh_table()
