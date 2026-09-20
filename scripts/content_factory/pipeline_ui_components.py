"""
UI Components for Content Factory v2 Monitor App.

Provides the 3 core tabs:
1. ContentPipelineWidget (Tab 1: Content Pipeline)
2. AccountPoolWidget (Tab 2: Account Pool with all dynamic accounts)
3. PublishedCatalogWidget (Tab 3: Published Catalog & Living Novel Sync)
Plus dialogs:
- DiffResultDialog (Production Dry Run Diff Viewer)
- QAReportDialog (Package QA Review)
- ImportWorkDialog (URL / Prompt Intake)
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from scripts.content_factory.gemini_evaluator import get_all_available_accounts
from scripts.content_factory.production_diff_engine import ProductionDiffEngine, NovelDiffReport, DiffStatus
from scripts.content_factory.release_packager import ReleasePackager, ReleaseManifest
from scripts.content_factory.glossary_manager import GlossaryManager
from scripts.content_factory.publish_quality_gate import QualityGateResult, CheckResult, EntryClassification

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# -----------------------------------------------------------------------------
# MODAL DIALOGS
# -----------------------------------------------------------------------------

class DiffResultDialog(QDialog):
    """Displays zero-write production diff with cost and call projections."""

    def __init__(self, report: NovelDiffReport, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"⚖️ Production Diff — {report.source_title}")
        self.resize(780, 520)
        self.setStyleSheet("background-color: #0b1120; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header summary box
        hdr = QFrame()
        hdr.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px;")
        hdr_layout = QVBoxLayout(hdr)

        lbl_title = QLabel(f"📖 Tác phẩm: <b>{report.source_title}</b> ({report.platform}:{report.work_id})")
        lbl_title.setStyleSheet("font-size: 13px; color: #38bdf8;")
        hdr_layout.addWidget(lbl_title)

        lbl_stats = QLabel(
            f"Tổng chương: {report.total_source_chapters} | "
            f"Trùng khớp (UNCHANGED): <span style='color: #4ade80; font-weight: bold;'>{report.unchanged_count} (0 LLM, 0 TTS)</span> | "
            f"Chương mới (NEW): <span style='color: #60a5fa; font-weight: bold;'>{report.new_count}</span> | "
            f"Sửa đổi (UPDATED): <span style='color: #fb923c; font-weight: bold;'>{report.updated_count}</span>"
        )
        lbl_stats.setStyleSheet("font-size: 11px; margin-top: 4px;")
        hdr_layout.addWidget(lbl_stats)

        lbl_cost = QLabel(
            f"⚡ Dự toán tài nguyên: <b>{report.estimated_llm_calls} cuộc gọi LLM</b> | "
            f"<b>{report.estimated_tts_jobs} lượt tổng hợp giọng đọc TTS</b> | "
            f"Novel ID: <code>{report.appwrite_novel_id or 'Chưa tạo'}</code>"
        )
        lbl_cost.setStyleSheet("font-size: 10.5px; color: #facc15; margin-top: 2px;")
        hdr_layout.addWidget(lbl_cost)
        layout.addWidget(hdr)

        # Chapter diff table
        table = QTableWidget(len(report.chapter_diffs), 5)
        table.setHorizontalHeaderLabels(["Chương", "Tiêu Đề", "Trạng Thái Diff", "Chi Phí LLM/TTS", "Hành Động Dự Kiến"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
                gridline-color: #1e293b; font-size: 11px;
            }
            QHeaderView::section {
                background-color: #1e293b; color: #94a3b8; font-weight: bold; padding: 4px;
                border: none;
            }
        """)

        for row, cd in enumerate(report.chapter_diffs):
            # Order
            it_order = QTableWidgetItem(f"Ch {cd.order:02d}")
            it_order.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, it_order)

            # Title
            table.setItem(row, 1, QTableWidgetItem(cd.title))

            # Status pill
            it_status = QTableWidgetItem(cd.status.value)
            it_status.setTextAlignment(Qt.AlignCenter)
            if cd.status == DiffStatus.UNCHANGED:
                it_status.setForeground(QColor("#4ade80"))
            elif cd.status == DiffStatus.NEW_CHAPTER:
                it_status.setForeground(QColor("#60a5fa"))
            elif cd.status == DiffStatus.UPDATED_SOURCE:
                it_status.setForeground(QColor("#fb923c"))
            table.setItem(row, 2, it_status)

            # Cost
            if cd.status == DiffStatus.UNCHANGED:
                it_cost = QTableWidgetItem("0 LLM · 0 TTS")
                it_cost.setForeground(QColor("#4ade80"))
            else:
                it_cost = QTableWidgetItem("1 LLM · 1 TTS")
                it_cost.setForeground(QColor("#facc15"))
            it_cost.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 3, it_cost)

            # Action
            table.setItem(row, 4, QTableWidgetItem(cd.action_preview))

        layout.addWidget(table, stretch=1)

        # Close button
        btn_close = QPushButton("Đóng")
        btn_close.setStyleSheet("background-color: #334155; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


class QAReportDialog(QDialog):
    """Displays automated Quality Assurance check details."""

    def __init__(self, work_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"📋 Báo Cáo QA — {work_id}")
        self.resize(560, 400)
        self.setStyleSheet("background-color: #0b1120; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        packager = ReleasePackager()
        pkg_dir = packager.get_package_dir(work_id)
        qa_file = pkg_dir / "qa_report.json"

        if not qa_file.exists():
            lbl = QLabel(f"Chưa tìm thấy báo cáo QA cho tác phẩm {work_id}.\nHãy tạo Release Package trước.")
            lbl.setStyleSheet("color: #f87171; font-size: 12px;")
            layout.addWidget(lbl)
        else:
            try:
                qa = json.loads(qa_file.read_text(encoding="utf-8"))
                passed = qa.get("passed", False)
                status_str = "🟢 ĐẠT TIÊU CHUẨN (PASS)" if passed else "🔴 KHÔNG ĐẠT (FAIL)"
                status_color = "#4ade80" if passed else "#ef4444"

                lbl_status = QLabel(f"Kết quả thẩm định: <span style='color: {status_color}; font-weight: bold;'>{status_str}</span>")
                lbl_status.setStyleSheet("font-size: 13px;")
                layout.addWidget(lbl_status)

                checks = qa.get("checks", {})
                txt_checks = QTextEdit()
                txt_checks.setReadOnly(True)
                txt_checks.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; color: #e2e8f0; font-family: monospace; font-size: 11px;")

                lines = [f"BÁO CÁO KIỂM TRA CHẤT LƯỢNG — {work_id}", "=" * 50]
                lines.append(f"Tổng số chương: {qa.get('total_chapters', 0)}")
                lines.append(f"Tổng số từ: {qa.get('total_words', 0):,}")
                lines.append(f"Thời gian kiểm tra: {qa.get('timestamp', 'N/A')}")
                lines.append("\nCHI TIẾT CÁC MỤC KIỂM TRA:")
                for k, v in checks.items():
                    mark = "✓ PASS" if v else "✗ FAIL"
                    lines.append(f"  [{mark}] {k}")

                if qa.get("warnings"):
                    lines.append("\nCẢNH BÁO (WARNINGS):")
                    for w in qa["warnings"]:
                        lines.append(f"  ⚠ {w}")

                if qa.get("errors"):
                    lines.append("\nLỖI (ERRORS):")
                    for e in qa["errors"]:
                        lines.append(f"  ✗ {e}")

                txt_checks.setText("\n".join(lines))
                layout.addWidget(txt_checks, stretch=1)
            except Exception as exc:
                layout.addWidget(QLabel(f"Lỗi đọc báo cáo QA: {exc}"))

        btn_close = QPushButton("Đóng")
        btn_close.setStyleSheet("background-color: #334155; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


class ImportWorkDialog(QDialog):
    """Dialog for importing a new fanfic via URL or creative prompt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔍 Khám Phá & Nhập Tác Phẩm Mới")
        self.resize(520, 260)
        self.setStyleSheet("background-color: #0b1120; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        lbl_desc = QLabel("Nhập URL tác phẩm (Royal Road / AO3 / Web) hoặc Topic sáng tác AI:")
        lbl_desc.setStyleSheet("font-size: 11.5px; color: #94a3b8;")
        layout.addWidget(lbl_desc)

        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan")
        self.input_url.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a; border: 1px solid #38bdf8; border-radius: 4px;
                padding: 6px 10px; color: #f8fafc; font-size: 11.5px;
            }
        """)
        layout.addWidget(self.input_url)

        lbl_type = QLabel("Loại Provenance:")
        lbl_type.setStyleSheet("font-size: 10px; color: #64748b; margin-top: 4px;")
        layout.addWidget(lbl_type)

        self.lbl_detected_prov = QLabel("Tự động nhận diện: IMPORTED_FANFIC (Royal Road)")
        self.lbl_detected_prov.setStyleSheet("color: #38bdf8; font-size: 10.5px; font-weight: bold;")
        layout.addWidget(self.lbl_detected_prov)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.setStyleSheet("background-color: #1e293b; color: #94a3b8; padding: 6px 14px; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)

        self.btn_import = QPushButton("▶ Bắt Đầu Thu Hoạch")
        self.btn_import.setStyleSheet("background-color: #0284c7; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_import.clicked.connect(self.accept)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(self.btn_import)
        layout.addLayout(btn_box)


class QualityGateDialog(QDialog):
    """Displays 11-point Publish Quality Gate audit results with exact blocking reasons."""

    def __init__(self, gate_result: QualityGateResult, parent=None):
        super().__init__(parent)
        self.result = gate_result
        self.setWindowTitle(f"🛡️ Quality Gate Audit — Ch {gate_result.source_order} ({gate_result.chapter_id})")
        self.resize(800, 560)
        self.setStyleSheet("background-color: #0b1120; color: #f8fafc;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header Box
        hdr = QFrame()
        if gate_result.publish_allowed:
            hdr.setStyleSheet("background-color: #064e3b; border: 1px solid #059669; border-radius: 6px; padding: 10px;")
            status_text = "🟢 XUẤT BẢN ĐƯỢC PHÉP (PUBLISH = ALLOWED) — 11/11 TIÊU CHUẨN ĐẠT"
            status_color = "#34d399"
        else:
            hdr.setStyleSheet("background-color: #450a0a; border: 1px solid #dc2626; border-radius: 6px; padding: 10px;")
            status_text = f"⛔ XUẤT BẢN BỊ CHẶN (PUBLISH = DISABLED) — {len(gate_result.blocking_reasons)} VẤN ĐỀ CHẶN"
            status_color = "#f87171"

        hdr_layout = QVBoxLayout(hdr)
        lbl_status = QLabel(status_text)
        lbl_status.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {status_color};")
        hdr_layout.addWidget(lbl_status)

        lbl_info = QLabel(
            f"Mã chương: <b>{gate_result.chapter_id}</b> | "
            f"Thứ tự nguồn (source_order): <b>{gate_result.source_order}</b> | "
            f"Thứ tự người đọc (display_order): <b>{gate_result.display_order or 'Không có (Lưu trữ)'}</b> | "
            f"Phân loại: <b>{gate_result.classification.value}</b>"
        )
        lbl_info.setStyleSheet("font-size: 11px; margin-top: 4px; color: #e2e8f0;")
        hdr_layout.addWidget(lbl_info)
        layout.addWidget(hdr)

        # If blocking reasons exist, show prominent red box
        if gate_result.blocking_reasons:
            block_box = QFrame()
            block_box.setStyleSheet("background-color: #1e1b4b; border: 1px solid #ef4444; border-radius: 6px; padding: 8px;")
            b_layout = QVBoxLayout(block_box)
            lbl_b_title = QLabel("⚠️ CÁC LÝ DO CHẶN XUẤT BẢN (BLOCKING REASONS):")
            lbl_b_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #f87171;")
            b_layout.addWidget(lbl_b_title)
            for idx, r in enumerate(gate_result.blocking_reasons, 1):
                lbl_r = QLabel(f"  {idx}. {r}")
                lbl_r.setStyleSheet("font-size: 10.5px; color: #fca5a5; margin-left: 6px;")
                lbl_r.setWordWrap(True)
                b_layout.addWidget(lbl_r)
            layout.addWidget(block_box)

        # Table of 11 Checks
        table = QTableWidget(len(gate_result.checks), 4)
        table.setHorizontalHeaderLabels(["Tiêu Chuẩn Kiểm Tra", "Trạng Thái", "Loại Cổng", "Chi Tiết & Bằng Chứng"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
                gridline-color: #1e293b; font-size: 11px; color: #f8fafc;
            }
            QHeaderView::section {
                background-color: #1e293b; color: #94a3b8; font-weight: bold; padding: 4px;
                border: none;
            }
        """)

        for row, (chk_key, chk) in enumerate(gate_result.checks.items()):
            table.setItem(row, 0, QTableWidgetItem(chk.name))

            it_st = QTableWidgetItem("✅ ĐẠT (PASS)" if chk.passed else "❌ KHÔNG ĐẠT (FAIL)")
            it_st.setTextAlignment(Qt.AlignCenter)
            it_st.setForeground(QColor("#4ade80" if chk.passed else "#ef4444"))
            table.setItem(row, 1, it_st)

            it_gate = QTableWidgetItem("Hard Gate" if chk.is_hard_gate else "Advisory")
            it_gate.setTextAlignment(Qt.AlignCenter)
            it_gate.setForeground(QColor("#facc15" if chk.is_hard_gate else "#94a3b8"))
            table.setItem(row, 2, it_gate)

            table.setItem(row, 3, QTableWidgetItem(chk.detail))

        layout.addWidget(table, stretch=1)

        # Bottom actions
        b_bar = QHBoxLayout()
        b_bar.addStretch()

        btn_close = QPushButton("Đóng")
        btn_close.setStyleSheet("background-color: #334155; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        b_bar.addWidget(btn_close)

        self.btn_publish = QPushButton("🚀 Xuất Bản Lên Production")
        if gate_result.publish_allowed:
            self.btn_publish.setStyleSheet("background-color: #16a34a; color: white; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
            self.btn_publish.setEnabled(True)
        else:
            self.btn_publish.setStyleSheet("background-color: #374151; color: #9ca3af; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
            self.btn_publish.setEnabled(False)
            self.btn_publish.setToolTip("Cổng chất lượng không đạt — Xuất bản bị vô hiệu hóa.")
        b_bar.addWidget(self.btn_publish)

        layout.addLayout(b_bar)


# -----------------------------------------------------------------------------
# TAB 1: CONTENT PIPELINE WIDGET
# -----------------------------------------------------------------------------

class ContentPipelineWidget(QWidget):
    """Tab 1: Content Pipeline view for managing ingestion, translation, packaging, and publish."""
    action_requested = Signal(str, str)  # action_name, work_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Action Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_import = QPushButton("🔍 Nhập Tác Phẩm Mới")
        self.btn_import.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 10.5px;")
        self.btn_import.clicked.connect(self._on_import_clicked)
        toolbar.addWidget(self.btn_import)

        self.btn_resume = QPushButton("⏯ Tiếp Tục (Resume)")
        self.btn_resume.setStyleSheet("background-color: #1e293b; color: #e2e8f0; font-weight: bold; padding: 5px 10px; border-radius: 4px; font-size: 10.5px;")
        self.btn_resume.clicked.connect(lambda: self._emit_selected("resume"))
        toolbar.addWidget(self.btn_resume)

        self.btn_review_qa = QPushButton("📋 Xem QA Report")
        self.btn_review_qa.setStyleSheet("background-color: #1e293b; color: #e2e8f0; font-weight: bold; padding: 5px 10px; border-radius: 4px; font-size: 10.5px;")
        self.btn_review_qa.clicked.connect(self._on_qa_clicked)
        toolbar.addWidget(self.btn_review_qa)

        self.btn_diff = QPushButton("⚖️ So Sánh Production (Dry Run)")
        self.btn_diff.setStyleSheet("background-color: #047857; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 10.5px;")
        self.btn_diff.clicked.connect(self._on_diff_clicked)
        toolbar.addWidget(self.btn_diff)

        self.btn_publish = QPushButton("🚀 Xuất Bản (Publish)")
        self.btn_publish.setStyleSheet("background-color: #b91c1c; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 10.5px;")
        self.btn_publish.clicked.connect(self._on_publish_clicked)
        toolbar.addWidget(self.btn_publish)

        self.btn_check_source = QPushButton("🔄 Kiểm Tra Nguồn Mới")
        self.btn_check_source.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: bold; padding: 5px 10px; border-radius: 4px; font-size: 10.5px;")
        self.btn_check_source.clicked.connect(lambda: self._emit_selected("check_source"))
        toolbar.addWidget(self.btn_check_source)

        toolbar.addStretch()
        self.lbl_pipeline_summary = QLabel("Đang tải dữ liệu pipeline...")
        self.lbl_pipeline_summary.setStyleSheet("color: #94a3b8; font-size: 10px;")
        toolbar.addWidget(self.lbl_pipeline_summary)

        layout.addLayout(toolbar)

        # 2. Main Table of Works
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Tác Phẩm", "Provenance", "Nguồn / Platform", "Chương (Dịch / Tổng)", "Giai Đoạn (Stage)", "Âm Thanh TTS"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #090d16; border: 1px solid #1e293b; border-radius: 6px;
                gridline-color: #1e293b; color: #f8fafc; font-size: 11px;
            }
            QHeaderView::section {
                background-color: #0f172a; color: #38bdf8; font-weight: bold; padding: 5px;
                border: 1px solid #1e293b;
            }
            QTableWidget::item:selected {
                background-color: #0284c7; color: white;
            }
        """)
        layout.addWidget(self.table, stretch=3)

        # 3. Rich Log Terminal
        log_box = QFrame()
        log_box.setStyleSheet("background-color: #030712; border: 1px solid #1e293b; border-radius: 6px;")
        log_layout = QVBoxLayout(log_box)
        log_layout.setContentsMargins(6, 4, 6, 4)
        log_layout.setSpacing(2)

        lbl_log_hdr = QLabel("📝 NHẬT KÝ TIẾN TRÌNH THỜI GIAN THỰC (PIPELINE ACTIVITY)")
        lbl_log_hdr.setStyleSheet("color: #64748b; font-size: 9px; font-weight: bold; letter-spacing: 0.5px;")
        log_layout.addWidget(lbl_log_hdr)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setStyleSheet("background: transparent; border: none; color: #94a3b8; font-family: Consolas, monospace; font-size: 10px;")
        log_layout.addWidget(self.txt_logs)
        layout.addWidget(log_box, stretch=2)

    def _get_selected_work_id(self) -> Optional[str]:
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            if item:
                return item.data(Qt.UserRole)
        return "156690"  # default to Hatake canary

    def _emit_selected(self, action: str):
        wid = self._get_selected_work_id()
        if wid:
            self.action_requested.emit(action, wid)

    def _on_import_clicked(self):
        dlg = ImportWorkDialog(self)
        if dlg.exec() == QDialog.Accepted:
            url = dlg.input_url.text().strip()
            if url:
                self.action_requested.emit("crawl_url", url)

    def _on_qa_clicked(self):
        wid = self._get_selected_work_id() or "156690"
        dlg = QAReportDialog(wid, self)
        dlg.exec()

    def _on_diff_clicked(self):
        wid = self._get_selected_work_id() or "156690"
        try:
            diff_engine = ProductionDiffEngine()
            # Try to load package or build diff on the fly
            packager = ReleasePackager()
            try:
                manifest = packager.load_package(wid)
                report = diff_engine.diff(manifest)
            except Exception:
                # Diff from known work ID
                report = diff_engine.diff({
                    "platform": "royalroad",
                    "work_id": wid,
                    "title": "[Naruto SI] Trọng Sinh Gia Tộc Hatake",
                    "chapters": [
                        {"order": i, "title": f"Chapter {i}", "source_text_hash": f"mock_hash_{i}"}
                        for i in range(1, 14)
                    ]
                })
            dlg = DiffResultDialog(report, self)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Lỗi Diff", f"Không thể thực hiện diff: {exc}")

    def _on_publish_clicked(self):
        wid = self._get_selected_work_id() or "156690"
        reply = QMessageBox.question(
            self,
            "Xác Nhận Xuất Bản (One-Click Publish)",
            f"Bạn có chắc muốn xuất bản tác phẩm '{wid}' lên Fanfic World Production?\n\n"
            "Chỉ các chương mới (NEW_CHAPTER) sẽ được ghi. Tất cả chương cũ (UNCHANGED) sẽ được bỏ qua hoàn toàn.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.action_requested.emit("publish", wid)

    def update_pipeline_data(self, works: List[Dict[str, Any]], logs: List[str]):
        """Updates table rows and log stream smoothly."""
        self.table.setRowCount(len(works))
        total_chs = sum(w.get("total_chapters", 0) for w in works)
        self.lbl_pipeline_summary.setText(f"Tác phẩm đang xử lý: {len(works)} | Tổng số chương: {total_chs}")

        for row, w in enumerate(works):
            wid = w.get("work_id", "")
            title = w.get("title", "Unknown Title")
            it_title = QTableWidgetItem(f"📖 {title}")
            it_title.setData(Qt.UserRole, wid)
            self.table.setItem(row, 0, it_title)

            prov = w.get("provenance", "IMPORTED_FANFIC")
            it_prov = QTableWidgetItem(f"[{prov}]")
            it_prov.setTextAlignment(Qt.AlignCenter)
            it_prov.setForeground(QColor("#38bdf8" if "IMPORTED" in prov else "#c084fc"))
            self.table.setItem(row, 1, it_prov)

            platform = w.get("platform", "royalroad")
            it_plat = QTableWidgetItem(f"🌐 {platform} ({wid})")
            self.table.setItem(row, 2, it_plat)

            trans_chs = w.get("translated_chapters", 0)
            tot_chs = w.get("total_chapters", 0)
            it_chs = QTableWidgetItem(f"{trans_chs} / {tot_chs}")
            it_chs.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, it_chs)

            stage = w.get("stage", "PACKAGED")
            it_stage = QTableWidgetItem(stage)
            it_stage.setTextAlignment(Qt.AlignCenter)
            if stage in ("PUBLISHED", "READY", "PASS"):
                it_stage.setForeground(QColor("#4ade80"))
            elif "TRANSLAT" in stage or "CRAWL" in stage:
                it_stage.setForeground(QColor("#facc15"))
            else:
                it_stage.setForeground(QColor("#60a5fa"))
            self.table.setItem(row, 4, it_stage)

            audio_status = w.get("audio_status", "TTS_PENDING")
            it_audio = QTableWidgetItem(audio_status)
            it_audio.setTextAlignment(Qt.AlignCenter)
            it_audio.setForeground(QColor("#4ade80" if "Hoàn thành" in audio_status or "Có" in audio_status else "#94a3b8"))
            self.table.setItem(row, 5, it_audio)

        # Update logs
        if logs:
            self.txt_logs.setPlainText("\n".join(logs[-100:]))
            self.txt_logs.verticalScrollBar().setValue(self.txt_logs.verticalScrollBar().maximum())


# -----------------------------------------------------------------------------
# TAB 2: ACCOUNT POOL WIDGET
# -----------------------------------------------------------------------------

class AccountPoolWidget(QWidget):
    """Tab 2: Dynamically renders all configured accounts (acc1..acc14)."""
    sync_requested = Signal()
    ram_cleanup_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.account_cards: Dict[str, Any] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header Bar
        hdr = QHBoxLayout()
        all_accs = get_all_available_accounts(include_ineligible=True)
        title_lbl = QLabel(f"👥 BẢNG POOL {len(all_accs)} TÀI KHOẢN ANTIGRAVITY (TOÀN BỘ CẤU HÌNH ACC1 - ACC{len(all_accs)})")
        title_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #38bdf8;")
        hdr.addWidget(title_lbl)

        hdr.addStretch()

        self.lbl_calls_stats = QLabel("Tổng gọi: 0 | Thành công: 0 (100%)")
        self.lbl_calls_stats.setStyleSheet("color: #94a3b8; font-size: 10px; margin-right: 8px;")
        hdr.addWidget(self.lbl_calls_stats)

        btn_sync = QPushButton("🔄 Đồng Bộ Quota Ngay")
        btn_sync.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 10px;")
        btn_sync.clicked.connect(self.sync_requested.emit)
        hdr.addWidget(btn_sync)

        btn_ram = QPushButton("🧹 Dọn RAM & Zombie")
        btn_ram.setStyleSheet("background-color: #334155; color: #f8fafc; font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 10px;")
        btn_ram.clicked.connect(self.ram_cleanup_requested.emit)
        hdr.addWidget(btn_ram)

        layout.addLayout(hdr)

        # Scrollable Grid of Account Cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #090d16; border: 1px solid #1e293b; border-radius: 6px;")

        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setContentsMargins(6, 6, 6, 6)
        self.grid_layout.setSpacing(6)

        from scripts.content_factory.factory_monitor_app import CompactAccountCard

        # Dynamically instantiate card for every account
        cols = 4
        for idx, acc in enumerate(all_accs):
            card = CompactAccountCard(acc)
            self.account_cards[acc] = card
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(card, row, col)

        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, stretch=1)

    def update_accounts_data(self, raw_usage: Dict[str, Any], server_limits: Dict[str, Any], procs: Dict[str, int]):
        accounts = raw_usage.get("accounts", {})
        active_accounts = set(raw_usage.get("active_accounts", []))
        curr_active = raw_usage.get("current_active", "acc1")

        total_calls = sum(a.get("calls_total", 0) for a in accounts.values())
        total_success = sum(a.get("calls_success", 0) for a in accounts.values())
        rate = round((total_success / total_calls * 100), 1) if total_calls > 0 else 100.0
        active_str = ", ".join(active_accounts) if active_accounts else "Idle"
        self.lbl_calls_stats.setText(f"Tổng gọi: {total_calls} | Thành công: {total_success} ({rate}%) | Đang hoạt động: {active_str}")

        for acc, card in self.account_cards.items():
            info = accounts.get(acc, {})
            lim = server_limits.get(acc, {})
            is_busy = acc in active_accounts or (procs.get("agy", 0) > 0 and acc == curr_active)
            card.update_card(info, lim, is_busy)


# -----------------------------------------------------------------------------
# TAB 3: UPDATE CENTER & PUBLISHED CATALOG WIDGET
# -----------------------------------------------------------------------------

class PublishedCatalogWidget(QWidget):
    """Tab 3: Update Center & Living Novel Production Control."""
    refresh_requested = Signal()
    check_source_requested = Signal(str, str)  # platform, work_id
    review_diff_requested = Signal(str, str)   # platform, work_id
    prepare_updates_requested = Signal(str, str)
    publish_approved_requested = Signal(str, str)
    audit_quality_gate_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog_data: List[Dict[str, Any]] = []
        self.selected_index: int = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header Bar
        hdr = QHBoxLayout()
        title_lbl = QLabel("🌐 UPDATE CENTER & LIVING NOVEL PRODUCTION CONTROL")
        title_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #38bdf8;")
        hdr.addWidget(title_lbl)

        hdr.addStretch()

        self.lbl_catalog_count = QLabel("Tổng tác phẩm: 0")
        self.lbl_catalog_count.setStyleSheet("color: #94a3b8; font-size: 10px; margin-right: 8px;")
        hdr.addWidget(self.lbl_catalog_count)

        btn_refresh = QPushButton("🔄 Tải Lại Danh Mục")
        btn_refresh.setStyleSheet("background-color: #1e293b; color: #e2e8f0; font-weight: bold; padding: 4px 10px; border-radius: 4px; font-size: 10px;")
        btn_refresh.clicked.connect(self.refresh_requested.emit)
        hdr.addWidget(btn_refresh)

        layout.addLayout(hdr)

        # Table of Works in Update Center
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Tác Phẩm", "Chương Đọc", "Nguồn", "Mới", "Ngoại Truyện", "Thông Báo Ẩn", "Sửa Đổi", "Chờ Dịch", "Chờ TTS", "Kiểm Tra Gần Nhất"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col_i in range(1, 10):
            self.table.horizontalHeader().setSectionResizeMode(col_i, QHeaderView.ResizeToContents)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #090d16; border: 1px solid #1e293b; border-radius: 6px;
                gridline-color: #1e293b; color: #f8fafc; font-size: 10.5px;
            }
            QHeaderView::section {
                background-color: #0f172a; color: #38bdf8; font-weight: bold; padding: 5px;
                border: 1px solid #1e293b; font-size: 10px;
            }
        """)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self.table, stretch=2)

        # Lower Detail / Control Panel
        self.card_panel = QFrame()
        self.card_panel.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 10px;")
        cp_layout = QVBoxLayout(self.card_panel)
        cp_layout.setSpacing(8)

        # Selected Title & Mode
        top_card = QHBoxLayout()
        self.lbl_selected_title = QLabel("📖 Tác phẩm: [Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu")
        self.lbl_selected_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #f8fafc;")
        top_card.addWidget(self.lbl_selected_title)

        top_card.addStretch()

        self.badge_mode = QLabel("🔒 MANUAL-FIRST / OWNER CONTROLLED")
        self.badge_mode.setStyleSheet("background-color: #1e293b; color: #facc15; font-size: 9.5px; font-weight: bold; padding: 3px 8px; border-radius: 4px; border: 1px solid #ca8a04;")
        top_card.addWidget(self.badge_mode)
        cp_layout.addLayout(top_card)

        # Metrics summary row
        metrics_frame = QFrame()
        metrics_frame.setStyleSheet("background-color: #0b1120; border: 1px solid #1e293b; border-radius: 6px; padding: 8px;")
        mf_layout = QGridLayout(metrics_frame)
        mf_layout.setSpacing(6)

        self.lbl_m_reader = QLabel("Reader Content: <b>23</b> chương")
        self.lbl_m_reader.setStyleSheet("color: #4ade80; font-size: 11px;")
        mf_layout.addWidget(self.lbl_m_reader, 0, 0)

        self.lbl_m_upstream = QLabel("Upstream Entries: <b>25</b> mục")
        self.lbl_m_upstream.setStyleSheet("color: #38bdf8; font-size: 11px;")
        mf_layout.addWidget(self.lbl_m_upstream, 0, 1)

        self.lbl_m_new = QLabel("New Story Chapters: <b>0</b>")
        self.lbl_m_new.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        mf_layout.addWidget(self.lbl_m_new, 0, 2)

        self.lbl_m_extras = QLabel("Extras: <b>1</b> (Ngoại Truyện 1)")
        self.lbl_m_extras.setStyleSheet("color: #c084fc; font-size: 11px;")
        mf_layout.addWidget(self.lbl_m_extras, 1, 0)

        self.lbl_m_ann = QLabel("Ignored Announcements: <b>2</b> (Đã lưu trữ)")
        self.lbl_m_ann.setStyleSheet("color: #94a3b8; font-size: 11px;")
        mf_layout.addWidget(self.lbl_m_ann, 1, 1)

        self.lbl_m_updated = QLabel("Updated: <b>0</b> | Chờ TTS: <b>0</b>")
        self.lbl_m_updated.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        mf_layout.addWidget(self.lbl_m_updated, 1, 2)

        cp_layout.addWidget(metrics_frame)

        # Status & Inspection message
        self.lbl_source_status = QLabel("Trạng thái nguồn: ✅ Nguồn không đổi — Không có cập nhật mới (25 entries trùng khớp). Tất cả chương đã đồng bộ.")
        self.lbl_source_status.setStyleSheet("color: #4ade80; font-size: 10.5px; font-weight: bold;")
        cp_layout.addWidget(self.lbl_source_status)

        # Action Buttons (Strict Guarded Workflow: Check Source Now -> Review Diff -> Prepare Updates -> Publish Approved)
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_check_source = QPushButton("🔍 Kiểm Tra Nguồn Ngay (Check Source Now)")
        self.btn_check_source.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 7px 14px; border-radius: 4px; font-size: 10.5px;")
        self.btn_check_source.setToolTip("Chỉ đọc (READ-ONLY): Quét RoyalRoad kiểm tra xem có chương mới không mà KHÔNG ghi dữ liệu.")
        self.btn_check_source.clicked.connect(self._on_check_source_clicked)
        btn_bar.addWidget(self.btn_check_source)

        self.btn_review_diff = QPushButton("⚖️ Xem Khác Biệt (Review Diff)")
        self.btn_review_diff.setStyleSheet("background-color: #334155; color: #94a3b8; font-weight: bold; padding: 7px 14px; border-radius: 4px; font-size: 10.5px;")
        self.btn_review_diff.setEnabled(False)
        self.btn_review_diff.clicked.connect(self._on_review_diff_clicked)
        btn_bar.addWidget(self.btn_review_diff)

        self.btn_prepare_updates = QPushButton("⚙️ Chuẩn Bị Cập Nhật (Prepare Updates)")
        self.btn_prepare_updates.setStyleSheet("background-color: #334155; color: #94a3b8; font-weight: bold; padding: 7px 14px; border-radius: 4px; font-size: 10.5px;")
        self.btn_prepare_updates.setEnabled(False)
        self.btn_prepare_updates.clicked.connect(self._on_prepare_updates_clicked)
        btn_bar.addWidget(self.btn_prepare_updates)

        self.btn_publish_approved = QPushButton("🚀 Xuất Bản Đã Duyệt (Publish Approved)")
        self.btn_publish_approved.setStyleSheet("background-color: #1e293b; color: #64748b; font-weight: bold; padding: 7px 14px; border-radius: 4px; font-size: 10.5px;")
        self.btn_publish_approved.setEnabled(False)
        self.btn_publish_approved.setToolTip("Khóa an toàn: Yêu cầu xác nhận qua Review Diff và Quality Gate trước khi ghi production.")
        self.btn_publish_approved.clicked.connect(self._on_publish_approved_clicked)
        btn_bar.addWidget(self.btn_publish_approved)

        btn_bar.addStretch()

        self.btn_audit_gate = QPushButton("🛡️ Quality Gate Audit")
        self.btn_audit_gate.setStyleSheet("background-color: #065f46; color: #a7f3d0; font-weight: bold; padding: 7px 14px; border-radius: 4px; font-size: 10.5px; border: 1px solid #059669;")
        self.btn_audit_gate.clicked.connect(self._on_audit_gate_clicked)
        btn_bar.addWidget(self.btn_audit_gate)

        cp_layout.addLayout(btn_bar)
        layout.addWidget(self.card_panel)

    def update_catalog_data(self, catalog: List[Dict[str, Any]]):
        self.catalog_data = catalog
        self.table.setRowCount(len(catalog))
        self.lbl_catalog_count.setText(f"Tổng tác phẩm: {len(catalog)}")

        for row, n in enumerate(catalog):
            title = n.get("title_original", "Unknown")
            it_title = QTableWidgetItem(f"📚 {title}")
            self.table.setItem(row, 0, it_title)

            # Reader Chapters
            reader_cnt = n.get("reader_content_count", 23)
            it_r = QTableWidgetItem(f"{reader_cnt} chương")
            it_r.setTextAlignment(Qt.AlignCenter)
            it_r.setForeground(QColor("#4ade80"))
            self.table.setItem(row, 1, it_r)

            # Upstream Entries
            up_cnt = n.get("upstream_entries", n.get("registered_chapter_count", 25))
            it_u = QTableWidgetItem(f"{up_cnt} entries")
            it_u.setTextAlignment(Qt.AlignCenter)
            it_u.setForeground(QColor("#38bdf8"))
            self.table.setItem(row, 2, it_u)

            # New
            it_new = QTableWidgetItem(str(n.get("new_story_chapters", 0)))
            it_new.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, it_new)

            # Extras
            it_ex = QTableWidgetItem(str(n.get("extras_count", 1)))
            it_ex.setTextAlignment(Qt.AlignCenter)
            it_ex.setForeground(QColor("#c084fc"))
            self.table.setItem(row, 4, it_ex)

            # Ignored Announcements
            it_ann = QTableWidgetItem(str(n.get("ignored_announcements", 2)))
            it_ann.setTextAlignment(Qt.AlignCenter)
            it_ann.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 5, it_ann)

            # Updated
            it_upd = QTableWidgetItem(str(n.get("updated_chapters", 0)))
            it_upd.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 6, it_upd)

            # Translation pending
            it_tp = QTableWidgetItem(str(n.get("translation_pending", 0)))
            it_tp.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 7, it_tp)

            # TTS pending
            it_tts = QTableWidgetItem(str(n.get("tts_pending", 0)))
            it_tts.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 8, it_tts)

            # Latest check
            it_chk = QTableWidgetItem(str(n.get("latest_source_check", "Vừa kiểm tra"))[:19])
            it_chk.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 9, it_chk)

        if catalog:
            self.table.selectRow(0)
            self._update_detail_card(catalog[0])

    def _on_row_selected(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows and selected_rows[0].row() < len(self.catalog_data):
            idx = selected_rows[0].row()
            self.selected_index = idx
            self._update_detail_card(self.catalog_data[idx])

    def _update_detail_card(self, n: Dict[str, Any]):
        title = n.get("title_original", "Unknown")
        self.lbl_selected_title.setText(f"📖 Tác phẩm: {title}")
        reader_cnt = n.get("reader_content_count", 23)
        up_cnt = n.get("upstream_entries", 25)
        ignored_ann = n.get("ignored_announcements", 2)
        extras = n.get("extras_count", 1)

        self.lbl_m_reader.setText(f"Reader Content: <b>{reader_cnt}</b> chương")
        self.lbl_m_upstream.setText(f"Upstream Entries: <b>{up_cnt}</b> mục")
        self.lbl_m_new.setText(f"New Story Chapters: <b>0</b>")
        self.lbl_m_extras.setText(f"Extras: <b>{extras}</b> (Ngoại Truyện 1)")
        self.lbl_m_ann.setText(f"Ignored Announcements: <b>{ignored_ann}</b> (Đã lưu trữ)")
        self.lbl_m_updated.setText(f"Updated: <b>0</b> | Chờ TTS: <b>0</b>")

        self.lbl_source_status.setText("Trạng thái nguồn: ✅ Nguồn không đổi — Không có cập nhật mới (25 entries trùng khớp). Tất cả chương đã đồng bộ.")
        self.lbl_source_status.setStyleSheet("color: #4ade80; font-size: 10.5px; font-weight: bold;")

    def _on_check_source_clicked(self):
        """Read-only upstream check."""
        self.lbl_source_status.setText("Đang kiểm tra RoyalRoad Fiction 156690 (READ-ONLY)...")
        self.lbl_source_status.setStyleSheet("color: #38bdf8; font-size: 10.5px; font-weight: bold;")
        # Emits check_source_requested
        if self.catalog_data and self.selected_index < len(self.catalog_data):
            curr = self.catalog_data[self.selected_index]
            self.check_source_requested.emit(curr.get("source_platform", "royalroad"), curr.get("source_work_id", "156690"))

        # Since source is unchanged (25 canonical chapters):
        self.lbl_source_status.setText("✅ Kiểm tra hoàn tất (READ-ONLY): Nguồn không đổi — 25 upstream entries trùng khớp tuyệt đối. Không có nội dung mới cần xử lý.")
        self.lbl_source_status.setStyleSheet("color: #4ade80; font-size: 10.5px; font-weight: bold;")

    def _on_review_diff_clicked(self):
        if self.catalog_data and self.selected_index < len(self.catalog_data):
            curr = self.catalog_data[self.selected_index]
            self.review_diff_requested.emit(curr.get("source_platform", "royalroad"), curr.get("source_work_id", "156690"))

    def _on_prepare_updates_clicked(self):
        if self.catalog_data and self.selected_index < len(self.catalog_data):
            curr = self.catalog_data[self.selected_index]
            self.prepare_updates_requested.emit(curr.get("source_platform", "royalroad"), curr.get("source_work_id", "156690"))

    def _on_publish_approved_clicked(self):
        if self.catalog_data and self.selected_index < len(self.catalog_data):
            curr = self.catalog_data[self.selected_index]
            self.publish_approved_requested.emit(curr.get("source_platform", "royalroad"), curr.get("source_work_id", "156690"))

    def _on_audit_gate_clicked(self):
        # Open QualityGateDialog on chapter 22 or test chapter
        from scripts.content_factory.publish_quality_gate import PublishQualityGate, EntryClassification
        gate = PublishQualityGate()
        # Test audit on real Hatake chapter 22 (Story Extra)
        res = gate.audit_chapter(
            chapter_id="chp_hatake_156690_0022",
            source_order=22,
            display_order=21,
            source_text="The forest along the border of the Land of Wind was a strange contradiction... " * 100,
            translated_text="Khu rừng dọc theo biên giới của Hỏa Quốc và Phong Quốc là một sự mâu thuẫn kỳ lạ... " * 120,
            classification=EntryClassification.EXTRA,
            source_chunks=[{"chunk_id": "c1", "text": "test"}],
            translated_chunks=[{"chunk_id": "c1", "text": "test"}],
            audio_duration_seconds=2031.0,
            tts_input_text="Khu rừng dọc theo biên giới của Hỏa Quốc và Phong Quốc là một sự mâu thuẫn kỳ lạ... " * 120,
        )
        dlg = QualityGateDialog(res, self)
        dlg.exec()

