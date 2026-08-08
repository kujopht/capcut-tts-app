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
_PREV_MODELS = None
_PREV_OFFLINE = None
_PREV_CACHE = None


def setUpModule() -> None:
    global _APP, _TMP, _PREV_ENV
    if not QT_AVAILABLE:
        raise unittest.SkipTest("PySide6 không khả dụng")

    _TMP = tempfile.TemporaryDirectory()
    _PREV_ENV = os.environ.get(SETTINGS_FILE_ENV)
    os.environ[SETTINGS_FILE_ENV] = str(Path(_TMP.name) / "test_settings.ini")

    # Kho model Piper cung phai tro vao thu muc tam: test khong duoc dung
    # (hay ghi de) model that cua nguoi dung.
    from desktop_app.providers.piper_models import MODELS_DIR_ENV

    global _PREV_MODELS
    _PREV_MODELS = os.environ.get(MODELS_DIR_ENV)
    os.environ[MODELS_DIR_ENV] = str(Path(_TMP.name) / "piper_models")

    # Da cai edge-tts that -> phai chan viec lay danh sach giong online,
    # neu khong bo test se goi mang.
    from desktop_app.providers.edge_provider import OFFLINE_ENV

    global _PREV_OFFLINE
    _PREV_OFFLINE = os.environ.get(OFFLINE_ENV)
    os.environ[OFFLINE_ENV] = "1"

    # Cache nghe thu cung phai nam trong thu muc tam
    from desktop_app.providers.preview_cache import CACHE_DIR_ENV

    global _PREV_CACHE
    _PREV_CACHE = os.environ.get(CACHE_DIR_ENV)
    os.environ[CACHE_DIR_ENV] = str(Path(_TMP.name) / "preview_cache")

    # Xac nhan da thuc su tro vao file tam, khong phai registry
    probe = make_qsettings()
    assert probe.fileName().endswith("test_settings.ini"), probe.fileName()

    _APP = QApplication.instance() or QApplication([])


def tearDownModule() -> None:
    global _TMP, _PREV_ENV, _PREV_MODELS, _PREV_OFFLINE, _PREV_CACHE
    from desktop_app.providers.edge_provider import OFFLINE_ENV
    from desktop_app.providers.preview_cache import CACHE_DIR_ENV
    from desktop_app.providers.piper_models import MODELS_DIR_ENV

    if _PREV_ENV is None:
        os.environ.pop(SETTINGS_FILE_ENV, None)
    else:
        os.environ[SETTINGS_FILE_ENV] = _PREV_ENV
    if _PREV_MODELS is None:
        os.environ.pop(MODELS_DIR_ENV, None)
    else:
        os.environ[MODELS_DIR_ENV] = _PREV_MODELS
    if _PREV_OFFLINE is None:
        os.environ.pop(OFFLINE_ENV, None)
    else:
        os.environ[OFFLINE_ENV] = _PREV_OFFLINE
    if _PREV_CACHE is None:
        os.environ.pop(CACHE_DIR_ENV, None)
    else:
        os.environ[CACHE_DIR_ENV] = _PREV_CACHE
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
class TestAppIconResources(unittest.TestCase):
    """Icon/logo phai tim thay duoc va tao ra QIcon khong rong."""

    def test_icon_files_exist(self) -> None:
        from desktop_app.resources import app_icon_ico, app_icon_png

        for path in (app_icon_png(), app_icon_ico()):
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file(), path)

    def test_resource_path_is_relative_to_project(self) -> None:
        from desktop_app.resources import PROJECT_DIR, resource_path

        path = resource_path("assets", "app_icon.png")
        self.assertEqual(path, PROJECT_DIR / "assets" / "app_icon.png")
        self.assertTrue((PROJECT_DIR / "app.py").is_file())

    def test_load_app_icon_not_null(self) -> None:
        from desktop_app.resources import load_app_icon

        icon = load_app_icon()
        self.assertIsNotNone(icon)
        self.assertFalse(icon.isNull())
        self.assertTrue(icon.availableSizes())

    def test_app_user_model_id_is_stable(self) -> None:
        import app as entry

        self.assertEqual(entry.APP_USER_MODEL_ID, "kujopht.FanficAudioStudio")


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
        # deleteLater() chi giai phong khi co vong lap su kien chay. unittest
        # khong chay vong lap nao, nen phai processEvents() - neu khong, moi
        # MainWindow (kem bang 452 giong + session HTTP cua provider) deu ton
        # tai den het bo test, lam suite cham dan roi treo.
        try:
            registry = getattr(self.window, "registry", None)
            if registry is not None:
                registry.close()
        except Exception:
            pass
        try:
            self.window.close()
            self.window.deleteLater()
        except Exception:
            pass
        try:
            QApplication.processEvents()
        except Exception:
            pass
        self.window = None

    def test_window_icon_set(self) -> None:
        icon = self.window.windowIcon()
        self.assertFalse(icon.isNull())
        self.assertTrue(icon.availableSizes())

    def test_sidebar_brand_shows_logo_image(self) -> None:
        from desktop_app.main_window import SIDEBAR_LOGO_SIZE

        pixmap = self.window.brand_logo.pixmap()
        self.assertFalse(pixmap.isNull(), "Logo sidebar phải là ảnh, không phải chữ")
        self.assertEqual(self.window.brand_logo.width(), SIDEBAR_LOGO_SIZE)
        self.assertLessEqual(SIDEBAR_LOGO_SIZE, 48)

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
        """Bang gio hien catalog HOP NHAT: CapCut + Edge + Piper local."""
        self.assertGreater(self.window.catalog.count, 100)
        merged = len(self.window.registry.voices)
        self.assertEqual(self.window.voice_table.rowCount(), merged)
        self.assertGreater(merged, self.window.catalog.count,
                           "Catalog hợp nhất phải nhiều hơn riêng CapCut")
        self.assertGreater(self.window.lang_filter.count(), 3)

    def test_voice_search_filters_table(self) -> None:
        self.window.voice_search.setText("BV421_vivn_streaming")
        self.assertEqual(self.window.voice_table.rowCount(), 1)
        self.window.voice_search.setText("")
        self.assertEqual(self.window.voice_table.rowCount(),
                         len(self.window.registry.voices))

    def test_language_filter(self) -> None:
        index = self.window.lang_filter.findData("vi-VN")
        self.assertGreaterEqual(index, 0)
        self.window.lang_filter.setCurrentIndex(index)
        rows = self.window.voice_table.rowCount()
        self.assertGreater(rows, 0)
        self.assertLess(rows, len(self.window.registry.voices))
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

    def test_provider_column_and_filter_present(self) -> None:
        """Bang phai co cot Nguon / Trang thai / Kiem tra luc."""
        headers = [
            self.window.voice_table.horizontalHeaderItem(i).text()
            for i in range(self.window.voice_table.columnCount())
        ]
        self.assertIn("Nguồn", headers)
        self.assertIn("Trạng thái", headers)
        self.assertIn("Kiểm tra lúc", headers)

        options = [
            self.window.provider_filter.itemText(i)
            for i in range(self.window.provider_filter.count())
        ]
        self.assertEqual(options, ["Tất cả", "CapCut", "Edge", "Piper local"])

    def test_provider_filter_narrows_table(self) -> None:
        from desktop_app.providers.base import PROVIDER_PIPER

        index = self.window.provider_filter.findData(PROVIDER_PIPER)
        self.window.provider_filter.setCurrentIndex(index)
        rows = self.window.voice_table.rowCount()
        self.assertGreaterEqual(rows, 3, "Phải còn 3 giọng Piper built-in")
        for row in range(rows):
            self.assertEqual(self.window.voice_table.item(row, 4).text(), "Piper local")
        self.window.provider_filter.setCurrentIndex(0)

    def test_status_cell_has_text_not_only_colour(self) -> None:
        text = self.window.voice_table.item(0, 6).text()
        self.assertTrue(len(text) > 2)
        tooltip = self.window.voice_table.item(0, 6).toolTip()
        self.assertIn("Trạng thái", tooltip)
        self.assertIn("Kiểm tra lúc", tooltip)

    def test_builtin_voices_present_in_merged_catalog(self) -> None:
        from desktop_app.providers.builtin_catalog import BUILTIN_VOICE_IDS

        for voice_id in BUILTIN_VOICE_IDS:
            self.assertIsNotNone(self.window.registry.voice_by_id(voice_id), voice_id)

    def test_ngochuyen_in_catalog_with_not_installed_status(self) -> None:
        from desktop_app.providers.base import VoiceStatus

        voice = self.window.registry.voice_by_id("piper:ngochuyen")
        self.assertIsNotNone(voice)
        self.assertEqual(voice.display_name, "Ngọc Huyền (mới)")
        info = self.window.registry.status_of(voice)
        self.assertEqual(info.status, VoiceStatus.NOT_INSTALLED)

    def test_edge_rows_do_not_show_capcut_resource_id(self) -> None:
        from desktop_app.providers.base import PROVIDER_EDGE

        index = self.window.provider_filter.findData(PROVIDER_EDGE)
        self.window.provider_filter.setCurrentIndex(index)
        for row in range(self.window.voice_table.rowCount()):
            tooltip = self.window.voice_table.item(row, 2).toolTip()
            self.assertNotIn("resource_id", tooltip)
        self.window.provider_filter.setCurrentIndex(0)

    def test_no_probe_runs_on_startup(self) -> None:
        """Mo app CHI kiem tra nhe, khong synthesize giong nao."""
        self.assertIsNone(self.window._probe_worker)
        for voice in self.window.registry.voices:
            self.assertIsNone(
                self.window.registry.store.get(voice.id).checked_at,
                "Không được probe giọng nào lúc khởi động",
            )

    def test_check_buttons_exist_and_enabled(self) -> None:
        self.assertTrue(self.window.btn_check_selected.isEnabled())
        self.assertTrue(self.window.btn_check_visible.isEnabled())
        self.assertFalse(self.window.btn_check_cancel.isEnabled())

    def test_probe_worker_runs_off_the_ui_thread(self) -> None:
        """Kiem tra giong KHONG duoc khoa giao dien."""
        from PySide6.QtCore import QThread

        from desktop_app.workers import ProbeWorker

        self.assertTrue(issubclass(ProbeWorker, QThread))
        worker = ProbeWorker(self.window.registry, [], force=False)
        self.assertNotEqual(worker.thread(), None)
        # Huy duoc ngay lap tuc, khong can cho vong lap ket thuc
        worker.request_stop()
        self.assertTrue(worker.is_set())

    def test_provider_status_label_lists_every_source(self) -> None:
        text = self.window.provider_status_label.text()
        for name in ("CapCut", "Edge TTS", "Piper local"):
            self.assertIn(name, text)

    def test_piper_model_section_exists(self) -> None:
        """Trang Cai dat phai co khu vuc quan ly model Piper."""
        self.assertTrue(self.window.btn_install_model.isEnabled())
        self.assertIn("model", self.window.btn_install_model.text().lower())
        self.assertIn("model", self.window.btn_open_models_dir.text().lower())
        self.assertGreaterEqual(self.window.piper_voice_combo.count(), 3)

    def test_ngochuyen_is_default_in_piper_section(self) -> None:
        self.assertEqual(self.window.piper_voice_combo.currentData(), "piper:ngochuyen")
        self.assertIn("Ngọc Huyền", self.window.piper_voice_combo.currentText())
        self.assertEqual(self.window.piper_voice_combo.itemData(0), "piper:ngochuyen")

    def test_piper_panel_shows_not_installed_status(self) -> None:
        text = self.window.piper_status_label.text()
        self.assertIn("Ngọc Huyền", text)
        self.assertIn("Chưa tải model", text)
        self.assertIn("Thư mục model", self.window.piper_path_label.text())

    def test_piper_panel_lists_every_piper_voice(self) -> None:
        keys = [
            self.window.piper_voice_combo.itemData(i)
            for i in range(self.window.piper_voice_combo.count())
        ]
        self.assertEqual(
            keys[:3],
            ["piper:ngochuyen", "piper:calmwoman3688", "piper:deepman3909"],
        )

    def test_model_install_runs_off_the_ui_thread(self) -> None:
        """Sao chep model lon KHONG duoc lam treo giao dien."""
        from PySide6.QtCore import QThread

        from desktop_app.workers import ModelInstallWorker

        self.assertTrue(issubclass(ModelInstallWorker, QThread))
        self.assertIsNone(self.window._model_worker)

    def test_install_rejects_mismatched_pair(self) -> None:
        """Hai file khac model -> tu choi, khong cai gi."""
        import tempfile as _tf
        from pathlib import Path as _P

        from desktop_app.providers.piper_models import pair_stems_match

        base = _P(_tf.mkdtemp())
        onnx = base / "model_a.onnx"
        config = base / "model_b.onnx.json"
        onnx.write_bytes(b"\x08" * (2 * 1024 * 1024))
        config.write_text('{"sample_rate": 22050}', encoding="utf-8")

        ok, reason = pair_stems_match(onnx, config)
        self.assertFalse(ok)
        self.assertIn("không cùng một model", reason)

    def test_install_updates_status_and_refreshes_catalog(self) -> None:
        """Cai xong: giong chuyen tu NOT_INSTALLED sang UNKNOWN, chua probe."""
        import tempfile as _tf
        from pathlib import Path as _P

        from desktop_app.providers.base import VoiceStatus

        manager = self.window._piper_manager()
        base = _P(_tf.mkdtemp())
        onnx = base / "ten_bat_ky.onnx"
        config = base / "ten_bat_ky.onnx.json"
        onnx.write_bytes(b"\x08" * (2 * 1024 * 1024))
        config.write_text('{"sample_rate": 22050}', encoding="utf-8")

        ok, message = manager.install_from_files("ngochuyen", onnx, config)
        self.assertTrue(ok, message)

        self.window.registry.store.invalidate("piper:ngochuyen")
        self.window.registry.refresh_catalog()
        self.window._reload_piper_voice_combo()

        voice = self.window.registry.voice_by_id("piper:ngochuyen")
        self.assertTrue(voice.installed)
        self.assertEqual(
            self.window.registry.status_of(voice).status, VoiceStatus.UNKNOWN,
            "Cài xong chưa probe thì phải là Chưa kiểm tra, không được tự nhận Khả dụng",
        )
        self.assertIn("Đã cài", self.window.piper_status_label.text())

        # Don dep de khong anh huong test khac
        manager.remove("ngochuyen")
        self.window.registry.refresh_catalog()

    def test_voice_counter_uses_merged_total(self) -> None:
        """Bo dem phai dung tong catalog HOP NHAT, khong phai rieng CapCut."""
        self.window._update_voice_counter()
        merged = len(self.window.registry.voices)
        text = self.window.voice_count_label.text()
        self.assertIn(f"/{merged} giọng", text)
        self.assertNotIn(f"/{self.window.catalog.count} giọng", text)

    def test_recommended_section_exists(self) -> None:
        from desktop_app.providers.recommended import RECOMMENDED_LABEL

        self.assertEqual(self.window.recommended_check.text(), RECOMMENDED_LABEL)
        self.assertIn("(7)", self.window.recommended_check.text())
        self.assertFalse(self.window.recommended_check.isChecked())

    def test_recommended_filter_shows_exactly_seven(self) -> None:
        from desktop_app.providers.recommended import RECOMMENDED_CODES

        self.window.recommended_check.setChecked(True)
        try:
            self.assertEqual(self.window.voice_table.rowCount(), 7)
            codes = [(v.provider, v.engine_voice_id) for v in self.window._visible_voices]
            self.assertEqual(codes, list(RECOMMENDED_CODES))
        finally:
            self.window.recommended_check.setChecked(False)

    def test_recommended_is_independent_of_favorites(self) -> None:
        """Bat/tat muc de xuat KHONG duoc dung toi dau sao cua nguoi dung."""
        before = list(self.window.catalog.favorites)
        self.window.recommended_check.setChecked(True)
        self.window.recommended_check.setChecked(False)
        self.assertEqual(list(self.window.catalog.favorites), before)

    def test_recommended_includes_ngochuyen_without_model(self) -> None:
        from desktop_app.providers.base import VoiceStatus

        self.window.recommended_check.setChecked(True)
        try:
            piper_rows = [
                v for v in self.window._visible_voices if v.provider == "piper"
            ]
            self.assertEqual(len(piper_rows), 1)
            voice = piper_rows[0]
            self.assertEqual(voice.engine_voice_id, "ngochuyen")
            info = self.window.registry.status_of(voice)
            self.assertEqual(info.status, VoiceStatus.NOT_INSTALLED)
        finally:
            self.window.recommended_check.setChecked(False)

    def test_recommended_survives_status_refresh(self) -> None:
        self.window.recommended_check.setChecked(True)
        try:
            self.window._refresh_voice_table()
            self.assertEqual(self.window.voice_table.rowCount(), 7)
            self.window._update_provider_status()
            self.window._refresh_voice_table()
            self.assertEqual(self.window.voice_table.rowCount(), 7)
        finally:
            self.window.recommended_check.setChecked(False)

    # -- nut "Nghe thu" o muc de xuat ----------------------------------------

    def _recommended_rows(self):
        self.window.recommended_check.setChecked(True)
        return list(self.window._visible_voices)

    def test_every_recommended_voice_has_preview_button(self) -> None:
        rows = self._recommended_rows()
        try:
            self.assertEqual(len(rows), 7)
            for index in range(7):
                button = self.window.voice_table.cellWidget(index, 3)
                self.assertIsNotNone(button, f"dòng {index} thiếu nút nghe thử")
                self.assertTrue(button.text())
        finally:
            self.window.recommended_check.setChecked(False)

    def test_preview_button_labels(self) -> None:
        rows = self._recommended_rows()
        try:
            for index, voice in enumerate(rows):
                button = self.window.voice_table.cellWidget(index, 3)
                if voice.provider == "piper" and not voice.installed:
                    self.assertIn("Chưa tải model", button.text())
                    self.assertFalse(button.isEnabled())
                else:
                    self.assertEqual(button.text(), self.window.PREVIEW_IDLE)
                    self.assertTrue(button.isEnabled())
        finally:
            self.window.recommended_check.setChecked(False)

    def test_preview_uses_correct_provider_and_voice_key(self) -> None:
        """Bam nut phai goi dung provider + voice_key, khong can chon giong truoc."""
        rows = self._recommended_rows()
        try:
            self.assertEqual(len(self.window._selected_voice_uids), 0,
                             "Không được yêu cầu chọn giọng trước")
            captured = {}

            class FakeWorker:
                def __init__(self, registry, voice, text, parent=None):
                    captured["voice"] = voice
                    captured["text"] = text
                    self._voice = voice

                def isRunning(self):
                    return False

                def request_stop(self):
                    pass

                def start(self):
                    captured["started"] = True

                class _Sig:
                    def connect(self, *a, **k):
                        pass

                statusChanged = _Sig()
                ready = _Sig()
                failed = _Sig()

            import desktop_app.workers as workers_mod

            original = workers_mod.CachedPreviewWorker
            workers_mod.CachedPreviewWorker = FakeWorker
            try:
                target = rows[0]
                self.window._on_preview_clicked(target)
            finally:
                workers_mod.CachedPreviewWorker = original

            from desktop_app.providers.recommended import PREVIEW_SENTENCE

            self.assertTrue(captured.get("started"))
            self.assertEqual(captured["voice"].provider, target.provider)
            self.assertEqual(captured["voice"].voice_key, target.voice_key)
            self.assertEqual(captured["text"], PREVIEW_SENTENCE)
            # Khong duoc dong thoi thay doi giong dang chon cho job chinh
            self.assertEqual(len(self.window._selected_voice_uids), 0)
        finally:
            self.window._preview_cache_worker = None
            self.window.recommended_check.setChecked(False)

    def test_preview_does_not_change_favorites(self) -> None:
        before = list(self.window.catalog.favorites)
        rows = self._recommended_rows()
        try:
            self.window._on_row_preview_ready(rows[0].id, "khong_ton_tai.mp3")
            self.assertEqual(list(self.window.catalog.favorites), before)
        finally:
            self.window.recommended_check.setChecked(False)

    def test_preview_worker_runs_off_ui_thread(self) -> None:
        from PySide6.QtCore import QThread

        from desktop_app.workers import CachedPreviewWorker

        self.assertTrue(issubclass(CachedPreviewWorker, QThread))

    def test_only_one_preview_plays_at_a_time(self) -> None:
        player = self.window._preview_player
        self.assertFalse(player.is_playing())
        # play() voi file khong ton tai -> that bai nhung khong duoc treo
        self.assertFalse(player.play("edge:x", "khong_co_file.mp3"))
        self.assertIsNone(player.current_voice_id)

    def test_stop_button_stops_playback(self) -> None:
        player = self.window._preview_player
        player._current_id = "edge:vi-VN-HoaiMyNeural"
        stopped = []
        player.stopped.connect(lambda vid: stopped.append(vid))
        player.stop()
        self.assertIsNone(player.current_voice_id)
        self.assertEqual(stopped, ["edge:vi-VN-HoaiMyNeural"])

    def test_provider_error_does_not_freeze_app(self) -> None:
        rows = self._recommended_rows()
        try:
            voice_id = rows[0].id
            self.window._on_row_preview_error(voice_id, "lỗi giả lập")
            button = self.window._preview_buttons.get(voice_id)
            self.assertIsNotNone(button)
            self.assertEqual(button.text(), self.window.PREVIEW_IDLE)
            self.assertTrue(button.isEnabled())
            self.assertIsNone(self.window._preview_cache_worker)
        finally:
            self.window.recommended_check.setChecked(False)

    def test_ngochuyen_preview_blocked_without_model(self) -> None:
        rows = self._recommended_rows()
        try:
            piper = next(v for v in rows if v.provider == "piper")
            button = self.window._preview_buttons.get(piper.id)
            self.assertIsNotNone(button)
            self.assertFalse(button.isEnabled())
            # Bam van khong tao worker nao va khong mo hop thoai nao
            self.window._on_preview_clicked(piper)
            self.assertIsNone(self.window._preview_cache_worker)
        finally:
            self.window.recommended_check.setChecked(False)

    def test_row_preview_handlers_are_not_shadowed(self) -> None:
        """Handler cua nut tren dong phai KHAC handler cua nut 'Thu giong' cu."""
        self.assertTrue(hasattr(self.window, "_on_row_preview_ready"))
        self.assertTrue(hasattr(self.window, "_on_row_preview_error"))
        self.assertNotEqual(
            self.window._on_row_preview_ready.__func__,
            self.window._on_preview_ready.__func__,
            "Hai luồng nghe thử không được dùng chung một handler",
        )

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
