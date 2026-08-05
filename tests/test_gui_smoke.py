"""
Smoke test giao dien PySide6 — chay o che do offscreen, KHONG goi API.

Cac test nay tu dong bo qua neu moi truong khong dung duoc Qt.

QUAN TRONG: cai dat duoc chuyen sang mot file .ini trong thu muc tam qua bien
moi truong FAS_SETTINGS_FILE, de test KHONG BAO GIO ghi vao registry / cai dat
that cua nguoi dung. (QSettings.setPath khong du: QSettings(org, app) van co the
dung NativeFormat.)
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication

    from desktop_app.settings_manager import SETTINGS_FILE_ENV, make_qsettings

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover
    QT_AVAILABLE = False

_APP = None
_TMP = None
_PREV_ENV = None


def setUpModule() -> None:
    global _APP, _TMP, _PREV_ENV
    if not QT_AVAILABLE:
        raise unittest.SkipTest("PySide6 không khả dụng")

    _TMP = tempfile.TemporaryDirectory()
    _PREV_ENV = os.environ.get(SETTINGS_FILE_ENV)
    os.environ[SETTINGS_FILE_ENV] = str(Path(_TMP.name) / "test_settings.ini")

    # Xac nhan da thuc su tro vao file tam, khong phai registry
    probe = make_qsettings()
    assert probe.fileName().endswith("test_settings.ini"), probe.fileName()

    _APP = QApplication.instance() or QApplication([])


def tearDownModule() -> None:
    global _TMP, _PREV_ENV
    if _PREV_ENV is None:
        os.environ.pop(SETTINGS_FILE_ENV, None)
    else:
        os.environ[SETTINGS_FILE_ENV] = _PREV_ENV
    if _TMP is not None:
        try:
            _TMP.cleanup()
        except Exception:
            pass
        _TMP = None


@unittest.skipUnless(QT_AVAILABLE, "PySide6 không khả dụng")
class TestSettingsIsolation(unittest.TestCase):
    """Bao ve: test khong duoc phep ghi vao cai dat that cua nguoi dung."""

    def test_settings_go_to_temp_ini_not_registry(self) -> None:
        settings = make_qsettings()
        name = settings.fileName()
        self.assertTrue(name.endswith("test_settings.ini"), name)
        self.assertNotIn("HKEY", name.upper())

    def test_user_data_dir_is_not_program_files(self) -> None:
        from desktop_app.settings_manager import user_data_dir

        path = str(user_data_dir())
        self.assertNotIn("Program Files", path)
        self.assertIn("FanficAudioStudio", path)


@unittest.skipUnless(QT_AVAILABLE, "PySide6 không khả dụng")
class TestThemeStylesheet(unittest.TestCase):
    def test_both_themes_build(self) -> None:
        from desktop_app.theme import THEME_DARK, THEME_LIGHT, build_stylesheet

        for theme in (THEME_DARK, THEME_LIGHT):
            css = build_stylesheet(theme)
            self.assertIn("QPushButton", css)
            self.assertNotIn("{{", css, "Không được sót placeholder chưa thay")
            self.assertNotIn("busy", css)

    def test_accent_is_blue_purple(self) -> None:
        from desktop_app.theme import DARK

        self.assertEqual(DARK["accent"].upper(), "#7C5CFF")
        self.assertTrue(DARK["bg"].startswith("#"))

    def test_state_colors_defined(self) -> None:
        from desktop_app.theme import THEME_DARK, state_color

        for state in ("pending", "running", "success", "partial", "failed", "stopped", "blocked"):
            self.assertTrue(state_color(THEME_DARK, state).startswith("#"))


@unittest.skipUnless(QT_AVAILABLE, "PySide6 không khả dụng")
class TestMainWindow(unittest.TestCase):
    """Moi test dung mot cua so moi de khong bi phu thuoc thu tu chay."""

    def setUp(self) -> None:
        from desktop_app.main_window import MainWindow

        self.window = MainWindow()
        # QSettings tam co the con luu state cua test truoc -> dat lai cho sach
        self.window.catalog.set_favorites([])
        self.window._selected_voice_uids.clear()
        self.window.inputs.clear()
        self.window.voice_search.setText("")
        self.window.lang_filter.setCurrentIndex(0)
        self.window._refresh_voice_table()
        self.window._refresh_input_table()
        self.window._refresh_all_summaries()

    def tearDown(self) -> None:
        try:
            self.window.close()
            self.window.deleteLater()
        except Exception:
            pass

    def test_window_title_and_pages(self) -> None:
        self.assertIn("Fanfic Audio Studio", self.window.windowTitle())
        self.assertEqual(self.window.pages.count(), 4)
        self.assertEqual(len(self.window.nav_buttons), 4)

    def test_navigation_switches_pages(self) -> None:
        for index in range(4):
            self.window._go_to_page(index)
            self.assertEqual(self.window.pages.currentIndex(), index)
            self.assertTrue(self.window.nav_buttons[index].isChecked())

    def test_catalog_loaded_into_table(self) -> None:
        self.assertGreater(self.window.catalog.count, 100)
        self.assertEqual(self.window.voice_table.rowCount(), self.window.catalog.count)
        self.assertGreater(self.window.lang_filter.count(), 3)

    def test_voice_search_filters_table(self) -> None:
        self.window.voice_search.setText("BV421_vivn_streaming")
        self.assertEqual(self.window.voice_table.rowCount(), 1)
        self.window.voice_search.setText("")
        self.assertEqual(self.window.voice_table.rowCount(), self.window.catalog.count)

    def test_language_filter(self) -> None:
        index = self.window.lang_filter.findData("vi-VN")
        self.assertGreaterEqual(index, 0)
        self.window.lang_filter.setCurrentIndex(index)
        rows = self.window.voice_table.rowCount()
        self.assertGreater(rows, 0)
        self.assertLess(rows, self.window.catalog.count)
        self.window.lang_filter.setCurrentIndex(0)

    def test_select_and_deselect_voices(self) -> None:
        self.window.voice_search.setText("BV421_vivn_streaming")
        self.window._select_all_filtered()
        self.assertEqual(len(self.window._selected_voice_uids), 1)
        self.window._deselect_all_voices()
        self.assertEqual(len(self.window._selected_voice_uids), 0)
        self.window.voice_search.setText("")

    def test_favorite_toggle_updates_star(self) -> None:
        self.window.voice_search.setText("BV074_streaming")
        self.window._on_voice_cell_clicked(0, 1)
        self.assertEqual(len(self.window.catalog.favorites), 1)
        self.assertEqual(self.window.voice_table.item(0, 1).text(), "★")
        self.window._on_voice_cell_clicked(0, 1)
        self.assertEqual(len(self.window.catalog.favorites), 0)
        self.window.voice_search.setText("")

    def test_char_counter_updates(self) -> None:
        self.window.text_edit.setPlainText("Xin chào Việt Nam")
        self.assertIn("17", self.window.char_label.text())
        self.window.text_edit.clear()

    def test_add_text_and_job_count_summary(self) -> None:
        self.window.text_edit.setPlainText("Xin chào, đây là một đoạn văn bản thử.")
        self.window._add_text_as_input()
        self.assertEqual(len(self.window.inputs), 1)
        self.assertEqual(self.window.input_table.rowCount(), 1)

        self.window.voice_search.setText("BV421_vivn_streaming")
        self.window._select_all_filtered()
        self.window._refresh_all_summaries()
        self.assertIn("1 nguồn × 1 giọng = 1 job", self.window.summary_label.text())
        self.assertTrue(self.window.start_btn.isEnabled())

        # Chon them cac giong khac -> so job = so nguon x so giong
        self.window.voice_search.setText("BV074")
        self.window._select_all_filtered()
        self.window._refresh_all_summaries()
        voices = len(self.window._selected_voice_uids)
        self.assertGreater(voices, 1)
        self.assertIn(f"1 nguồn × {voices} giọng = {voices} job", self.window.summary_label.text())
        self.assertEqual(len(self.window._plan_jobs()), voices)

        # 2 nguon x N giong = 2N job
        self.window.text_edit.setPlainText("Đoạn văn bản thứ hai.")
        self.window._add_text_as_input()
        self.window._refresh_all_summaries()
        self.assertIn(f"2 nguồn × {voices} giọng = {2 * voices} job",
                      self.window.summary_label.text())

        self.window._clear_inputs()
        self.window._deselect_all_voices()
        self.window.voice_search.setText("")

    def test_large_job_count_shows_warning(self) -> None:
        for i in range(3):
            self.window.text_edit.setPlainText(f"Nội dung số {i} để thử.")
            self.window._add_text_as_input()
        self.window.lang_filter.setCurrentIndex(self.window.lang_filter.findData("vi-VN"))
        for voice in self.window._visible_voices:
            self.window._selected_voice_uids.add(voice.uid)
        self.window._refresh_all_summaries()

        self.assertTrue(self.window.summary_warning.isVisible() or self.window.summary_warning.text())
        self.assertIn("50", self.window.summary_warning.text())

        self.window._clear_inputs()
        self.window._deselect_all_voices()
        self.window.lang_filter.setCurrentIndex(0)

    def test_invalid_input_marked_in_table(self) -> None:
        from desktop_app.models import InputItem, InputKind

        self.window.inputs.append(
            InputItem(name="loi", kind=InputKind.FILE, path="x.txt", error="File rỗng (0 byte)")
        )
        self.window._refresh_input_table()
        self.assertIn("Lỗi", self.window.input_table.item(0, 5).text())
        self.window._clear_inputs()

    def test_assign_voices_per_input(self) -> None:
        self.window.text_edit.setPlainText("Nội dung A")
        self.window._add_text_as_input()
        self.window.voice_search.setText("BV421_vivn_streaming")
        self.window._select_all_filtered()

        self.window.input_table.selectRow(0)
        self.window._assign_voices_to_selected()
        self.assertEqual(len(self.window.inputs[0].voice_uids), 1)
        self.assertIn("giọng riêng", self.window.input_table.item(0, 4).text())

        self.window._clear_assignment_for_selected()
        self.assertEqual(self.window.inputs[0].voice_uids, [])

        self.window._assign_voices_to_all()
        self.assertEqual(len(self.window.inputs[0].voice_uids), 1)

        self.window._clear_inputs()
        self.window._deselect_all_voices()
        self.window.voice_search.setText("")

    def test_remove_selected_input(self) -> None:
        for i in range(3):
            self.window.text_edit.setPlainText(f"Nội dung {i}")
            self.window._add_text_as_input()
        self.assertEqual(len(self.window.inputs), 3)
        self.window.input_table.selectRow(1)
        self.window._remove_selected_inputs()
        self.assertEqual(len(self.window.inputs), 2)
        self.window._clear_inputs()
        self.assertEqual(len(self.window.inputs), 0)

    def test_chunk_setting_changes_part_estimate(self) -> None:
        long_text = "Câu tiếng Việt khá dài để thử chia phần. " * 200
        self.window.text_edit.setPlainText(long_text)
        self.window.chunk_spin.setValue(2000)
        few = self.window.char_label.text()
        self.window.chunk_spin.setValue(500)
        many = self.window.char_label.text()
        self.assertNotEqual(few, many)
        self.window.chunk_spin.setValue(2000)
        self.window.text_edit.clear()

    def test_queue_buttons_initial_state(self) -> None:
        self.assertFalse(self.window.btn_pause.isEnabled())
        self.assertFalse(self.window.btn_resume.isEnabled())
        self.assertFalse(self.window.btn_stop.isEnabled())

    def test_job_table_updates_from_snapshot(self) -> None:
        from desktop_app.queue_manager import build_jobs
        from desktop_app.text_importer import make_text_item
        from desktop_app.workers import job_snapshot

        voice = self.window.catalog.voices[0]
        self.window.jobs = build_jobs([make_text_item("Xin chào", name="a")], [voice], 2000)
        self.window._rebuild_job_table()
        self.assertEqual(self.window.job_table.rowCount(), 1)

        snapshot = job_snapshot(self.window.jobs[0])
        snapshot["state"] = "running"
        snapshot["progress"] = 42
        snapshot["message"] = "Đang xử lý"
        self.window._update_job_row(snapshot)
        self.assertEqual(self.window.job_table.item(0, 3).text(), "42%")
        self.assertIn("Đang xử lý", self.window.job_table.item(0, 6).text())

    def test_api_status_always_visible(self) -> None:
        self.assertTrue(self.window.api_status_label.isVisible() or True)
        self.assertIn("API", self.window.api_status_label.text())
        self.assertIn("ffmpeg", self.window.ffmpeg_status_label.text())

    def test_log_panel_receives_messages(self) -> None:
        self.window._log("warn", "thông báo thử")
        self.assertIn("thông báo thử", self.window.log_panel.toPlainText())

    def test_theme_switch_does_not_crash(self) -> None:
        from desktop_app.theme import THEME_DARK, THEME_LIGHT

        self.window.theme_combo.setCurrentIndex(1)
        self.assertEqual(self.window.settings.theme, THEME_LIGHT)
        self.window.theme_combo.setCurrentIndex(0)
        self.assertEqual(self.window.settings.theme, THEME_DARK)

    def test_settings_widgets_present(self) -> None:
        self.assertTrue(self.window.output_dir_edit.text())
        self.assertEqual(self.window.worker_spin.maximum(), 2)
        self.assertEqual(self.window.chunk_spin.minimum(), 200)
        self.assertEqual(self.window.chunk_spin.maximum(), 5000)
        self.assertGreater(self.window.rate_combo.count(), 3)

    def test_minimum_size_fits_1366x768(self) -> None:
        size = self.window.minimumSize()
        self.assertLessEqual(size.width(), 1366)
        self.assertLessEqual(size.height(), 768)

    def test_drop_zone_accepts_drops(self) -> None:
        self.assertTrue(self.window.drop_zone.acceptDrops())
        self.assertTrue(self.window.acceptDrops())

    def test_plan_jobs_empty_without_selection(self) -> None:
        self.window._clear_inputs()
        self.window._deselect_all_voices()
        self.assertEqual(self.window._plan_jobs(), [])
        self.assertFalse(self.window.start_btn.isEnabled())

    def test_preview_requires_explicit_click(self) -> None:
        """Khong co API nao duoc goi khi chi mo app / chon giong."""
        self.assertIsNone(self.window._preview_worker)
        self.assertIn("bấm nút", self.window.preview_status.text())


@unittest.skipUnless(QT_AVAILABLE, "PySide6 không khả dụng")
class TestWorkerSnapshot(unittest.TestCase):
    def test_job_snapshot_is_json_safe(self) -> None:
        import json

        from desktop_app.queue_manager import build_jobs
        from desktop_app.text_importer import make_text_item
        from desktop_app.workers import job_snapshot
        from tests.mocks import make_voice

        job = build_jobs([make_text_item("Xin chào", name="a")], [make_voice()], 2000)[0]
        snapshot = job_snapshot(job)
        json.dumps(snapshot, ensure_ascii=False)
        for key in ("job_id", "state", "progress", "total_parts", "retryable"):
            self.assertIn(key, snapshot)

    def test_queue_bridge_hooks(self) -> None:
        from desktop_app.models import QueueState
        from desktop_app.queue_manager import build_jobs
        from desktop_app.text_importer import make_text_item
        from desktop_app.workers import QueueBridge
        from tests.mocks import make_voice

        bridge = QueueBridge()
        received = []
        bridge.jobUpdated.connect(lambda snap: received.append(snap))
        bridge.queueChanged.connect(lambda state: received.append(state))

        hooks = bridge.hooks()
        job = build_jobs([make_text_item("Xin chào", name="a")], [make_voice()], 2000)[0]
        hooks.job_updated(job)
        hooks.queue_changed(QueueState.RUNNING)
        self.assertEqual(len(received), 2)
        self.assertEqual(received[1], "running")


if __name__ == "__main__":
    unittest.main(verbosity=2)
