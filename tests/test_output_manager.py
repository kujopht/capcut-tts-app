"""Test thu muc ket qua, manifest, ghep MP3 (co/khong ffmpeg), ZIP, settings."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from desktop_app.models import ErrorKind, Job, JobPart, PartState
from desktop_app.output_manager import (
    FFMPEG_HELP,
    OutputManager,
    export_zip,
    find_ffmpeg,
    load_manifest,
    merge_job_audio,
)
from desktop_app.queue_manager import build_jobs
from desktop_app.result_library import scan_run, scan_runs
from desktop_app.text_importer import make_text_item
from tests.mocks import FAKE_MP3, make_voice


def make_job(job_dir: Path, parts: int = 3, all_success: bool = True) -> Job:
    job = Job(
        input_name="Chương 1",
        input_slug="chuong_1",
        voice=make_voice(),
        text="Xin chào",
        job_dir=str(job_dir),
    )
    job_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, parts + 1):
        part = JobPart(index=i, text=f"phần {i}")
        path = job_dir / part.file_name
        if all_success or i < parts:
            path.write_bytes(FAKE_MP3)
            part.state = PartState.SUCCESS
            part.file_path = str(path)
            part.file_size = path.stat().st_size
        else:
            part.state = PartState.FAILED
            part.error_kind = ErrorKind.TASK_FAILED.value
        job.parts.append(part)
    return job


class TestRunDirectories(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "outputs"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_run_dir_timestamp_format(self) -> None:
        manager = OutputManager(self.root)
        run = manager.create_run(datetime(2026, 8, 6, 14, 30, 5))
        self.assertEqual(run.name, "2026-08-06_14-30-05")
        self.assertTrue(run.is_dir())

    def test_same_second_does_not_overwrite(self) -> None:
        manager = OutputManager(self.root)
        stamp = datetime(2026, 8, 6, 14, 30, 5)
        first = manager.create_run(stamp)
        second = OutputManager(self.root).create_run(stamp)
        third = OutputManager(self.root).create_run(stamp)
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)
        self.assertEqual(second.name, "2026-08-06_14-30-05_2")
        self.assertEqual(third.name, "2026-08-06_14-30-05_3")

    def test_job_dir_layout(self) -> None:
        manager = OutputManager(self.root)
        run = manager.create_run()
        jobs = build_jobs([make_text_item("Xin chào", name="Chương 1")], [make_voice()], 2000)
        job_dir = manager.job_dir(jobs[0])
        self.assertEqual(job_dir.parent.parent, run)
        self.assertEqual(job_dir.parent.name, "chuong_1")
        self.assertEqual(job_dir.name, "nho_ngot_ngao")

    def test_same_input_reuses_dir_for_multiple_voices(self) -> None:
        manager = OutputManager(self.root)
        manager.create_run()
        voices = [make_voice("v1", "Giọng Một", "1"), make_voice("v2", "Giọng Hai", "2")]
        jobs = build_jobs([make_text_item("Xin chào", name="Chương 1")], voices, 2000)
        dir_a = manager.job_dir(jobs[0])
        dir_b = manager.job_dir(jobs[1])
        self.assertEqual(dir_a.parent, dir_b.parent, "Cùng input thì cùng thư mục cha")
        self.assertNotEqual(dir_a, dir_b)

    def test_duplicate_voice_names_get_separate_dirs(self) -> None:
        """Voice.json that co voice_type trung — thu muc phai khong bi tron."""
        manager = OutputManager(self.root)
        manager.create_run()
        voices = [make_voice("v1", "Tên Trùng", "1"), make_voice("v2", "Tên Trùng", "2")]
        jobs = build_jobs([make_text_item("Xin chào", name="a")], voices, 2000)
        dir_a = manager.job_dir(jobs[0])
        (dir_a / "part_001.mp3").write_bytes(FAKE_MP3)
        dir_b = manager.job_dir(jobs[1])
        self.assertNotEqual(dir_a, dir_b)

    def test_manifest_and_report_written(self) -> None:
        manager = OutputManager(self.root)
        run = manager.create_run()
        job = make_job(run / "chuong_1" / "nho_ngot_ngao")
        path = manager.write_manifest(job)
        self.assertTrue(Path(path).is_file())
        data = load_manifest(path)
        self.assertEqual(data["manifest_version"], 1)
        self.assertIn("app", data)

        report = manager.write_report([job])
        self.assertTrue(Path(report).is_file())
        self.assertEqual(load_manifest(report)["summary"]["total"], 1)

    def test_full_audio_name(self) -> None:
        job = Job(input_name="Chương 1", input_slug="chuong_1", voice=make_voice(), text="x")
        self.assertEqual(
            OutputManager.full_audio_name(job), "chuong_1_nho_ngot_ngao_full.mp3"
        )


class TestMerge(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_single_part_copies_without_ffmpeg(self) -> None:
        job = make_job(self.dir / "job", parts=1)
        with mock.patch("desktop_app.output_manager.find_ffmpeg", return_value=None):
            result = merge_job_audio(job)
        self.assertTrue(result.ok)
        self.assertTrue(Path(result.path).is_file())
        self.assertIn("không cần ffmpeg", result.note)

    def test_missing_ffmpeg_keeps_parts_and_reports_honestly(self) -> None:
        job = make_job(self.dir / "job", parts=3)
        with mock.patch("desktop_app.output_manager.find_ffmpeg", return_value=None):
            result = merge_job_audio(job)

        self.assertFalse(result.ok)
        self.assertIsNone(result.path)
        self.assertEqual(result.error_kind, ErrorKind.MERGE_FFMPEG_MISSING.value)
        self.assertIn("ffmpeg", result.note.lower())
        self.assertIn("giữ nguyên", result.note)
        # Toan bo part van con
        for i in (1, 2, 3):
            self.assertTrue((self.dir / "job" / f"part_{i:03d}.mp3").is_file())
        # Khong tao file full gia
        self.assertFalse((self.dir / "job" / OutputManager.full_audio_name(job)).exists())

    def test_ffmpeg_help_text_has_instructions(self) -> None:
        self.assertIn("ffmpeg", FFMPEG_HELP.lower())
        self.assertIn("Cài đặt", FFMPEG_HELP)

    def test_incomplete_job_is_not_merged(self) -> None:
        job = make_job(self.dir / "job", parts=3, all_success=False)
        result = merge_job_audio(job)
        self.assertFalse(result.ok)
        self.assertIn("2/3", result.note)

    def test_no_successful_parts(self) -> None:
        job = Job(input_name="a", input_slug="a", voice=make_voice(), text="x",
                  job_dir=str(self.dir))
        job.parts = [JobPart(index=1, text="x")]
        result = merge_job_audio(job)
        self.assertFalse(result.ok)

    def test_merge_uses_ffmpeg_in_part_order(self) -> None:
        job = make_job(self.dir / "job", parts=3)
        calls = []

        def fake_run(args, cwd=None):
            calls.append((args, cwd))
            # Gia lap ffmpeg tao ra file dich
            Path(cwd, args[-1]).write_bytes(FAKE_MP3 * 3)
            return 0, ""

        with mock.patch("desktop_app.output_manager.find_ffmpeg", return_value="ffmpeg.exe"), \
             mock.patch("desktop_app.output_manager._run_ffmpeg", side_effect=fake_run):
            result = merge_job_audio(job, "ffmpeg.exe")

        self.assertTrue(result.ok, result.note)
        self.assertIn("stream copy", result.note)
        self.assertEqual(len(calls), 1)
        self.assertIn("concat", calls[0][0])

    def test_merge_falls_back_to_reencode(self) -> None:
        job = make_job(self.dir / "job", parts=2)
        attempts = {"n": 0}

        def fake_run(args, cwd=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return 1, "copy không được"
            Path(cwd, args[-1]).write_bytes(FAKE_MP3 * 2)
            return 0, ""

        with mock.patch("desktop_app.output_manager.find_ffmpeg", return_value="ffmpeg.exe"), \
             mock.patch("desktop_app.output_manager._run_ffmpeg", side_effect=fake_run):
            result = merge_job_audio(job, "ffmpeg.exe")

        self.assertTrue(result.ok)
        self.assertIn("re-encode", result.note)
        self.assertEqual(attempts["n"], 2)

    def test_merge_both_attempts_fail(self) -> None:
        job = make_job(self.dir / "job", parts=2)
        with mock.patch("desktop_app.output_manager.find_ffmpeg", return_value="ffmpeg.exe"), \
             mock.patch("desktop_app.output_manager._run_ffmpeg", return_value=(1, "lỗi")):
            result = merge_job_audio(job, "ffmpeg.exe")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_kind, ErrorKind.MERGE_ERROR.value)
        self.assertTrue((self.dir / "job" / "part_001.mp3").is_file())

    def test_concat_list_is_cleaned_up(self) -> None:
        job = make_job(self.dir / "job", parts=2)
        with mock.patch("desktop_app.output_manager.find_ffmpeg", return_value="ffmpeg.exe"), \
             mock.patch("desktop_app.output_manager._run_ffmpeg", return_value=(1, "x")):
            merge_job_audio(job, "ffmpeg.exe")
        self.assertFalse((self.dir / "job" / "_concat_list.txt").exists())

    def test_find_ffmpeg_prefers_configured_path(self) -> None:
        fake = self.dir / "ffmpeg.exe"
        fake.write_bytes(b"x")
        self.assertEqual(find_ffmpeg(str(fake)), str(fake))

    def test_find_ffmpeg_accepts_directory(self) -> None:
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "ffmpeg.exe").write_bytes(b"x")
        self.assertEqual(find_ffmpeg(str(bin_dir)), str(bin_dir / "ffmpeg.exe"))

    def test_find_ffmpeg_returns_none_when_absent(self) -> None:
        with mock.patch("desktop_app.output_manager.shutil.which", return_value=None), \
             mock.patch("desktop_app.output_manager._FFMPEG_HINTS", ()):
            self.assertIsNone(find_ffmpeg(str(self.dir / "khong_co.exe")))


class TestRealFfmpegMerge(unittest.TestCase):
    """
    Ghep bang ffmpeg THAT voi MP3 that (do chinh ffmpeg sinh ra).
    Tu dong bo qua neu may khong co ffmpeg — dung de xac nhan lenh concat that
    su hoat dong, chu khong chi la mock.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.ffmpeg = find_ffmpeg("")
        if not cls.ffmpeg:
            raise unittest.SkipTest("Máy không có ffmpeg")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "job"
        self.dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_real_mp3(self, path: Path, freq: int, duration: float = 0.3) -> None:
        from desktop_app.output_manager import _run_ffmpeg

        code, err = _run_ffmpeg(
            [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
                "-c:a", "libmp3lame", "-b:a", "64k", str(path),
            ]
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(path.is_file() and path.stat().st_size > 0)

    def test_real_concat_produces_longer_file(self) -> None:
        job = Job(
            input_name="Chương 1", input_slug="chuong_1", voice=make_voice(),
            text="x", job_dir=str(self.dir),
        )
        sizes = []
        for i, freq in enumerate((440, 660, 880), start=1):
            part = JobPart(index=i, text=f"phần {i}")
            path = self.dir / part.file_name
            self._make_real_mp3(path, freq)
            part.state = PartState.SUCCESS
            part.file_path = str(path)
            part.file_size = path.stat().st_size
            sizes.append(part.file_size)
            job.parts.append(part)

        result = merge_job_audio(job, self.ffmpeg)
        self.assertTrue(result.ok, result.note)

        merged = Path(result.path)
        self.assertTrue(merged.is_file())
        self.assertEqual(merged.name, "chuong_1_nho_ngot_ngao_full.mp3")
        # File full phai lon hon bat ky part le nao (da noi 3 part lai)
        self.assertGreater(merged.stat().st_size, max(sizes))
        # Cac part goc van con nguyen
        for i in (1, 2, 3):
            self.assertTrue((self.dir / f"part_{i:03d}.mp3").is_file())
        self.assertFalse((self.dir / "_concat_list.txt").exists())

    def test_real_single_part_copy_matches_bytes(self) -> None:
        job = Job(
            input_name="a", input_slug="a", voice=make_voice(), text="x", job_dir=str(self.dir)
        )
        part = JobPart(index=1, text="phần 1")
        path = self.dir / part.file_name
        self._make_real_mp3(path, 440)
        part.state = PartState.SUCCESS
        part.file_path = str(path)
        part.file_size = path.stat().st_size
        job.parts.append(part)

        result = merge_job_audio(job, self.ffmpeg)
        self.assertTrue(result.ok, result.note)
        self.assertEqual(Path(result.path).read_bytes(), path.read_bytes())


class TestZip(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.run = self.dir / "2026-08-06_10-00-00"
        job_dir = self.run / "chuong_1" / "nho_ngot_ngao"
        job_dir.mkdir(parents=True)
        (job_dir / "part_001.mp3").write_bytes(FAKE_MP3)
        (job_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (self.run / "report.json").write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_zip_contains_all_files(self) -> None:
        path = export_zip(self.run)
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
        self.assertIn("report.json", names)
        self.assertTrue(any(n.endswith("part_001.mp3") for n in names))
        self.assertTrue(any(n.endswith("manifest.json") for n in names))

    def test_zip_placed_outside_source_dir(self) -> None:
        path = Path(export_zip(self.run))
        self.assertEqual(path.parent, self.run.parent)

    def test_zip_does_not_overwrite(self) -> None:
        first = Path(export_zip(self.run))
        second = Path(export_zip(self.run))
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_file() and second.is_file())

    def test_zip_skips_temp_files(self) -> None:
        (self.run / "x.mp3.part").write_bytes(b"x")
        with zipfile.ZipFile(export_zip(self.run)) as zf:
            self.assertFalse(any(n.endswith(".part") for n in zf.namelist()))

    def test_zip_missing_dir_raises(self) -> None:
        with self.assertRaises(ValueError):
            export_zip(self.dir / "khong_co")


class TestResultLibrary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_run(self, name: str, with_manifest: bool = True) -> Path:
        run = self.root / name
        job_dir = run / "chuong_1" / "nho_ngot_ngao"
        job_dir.mkdir(parents=True)
        (job_dir / "part_001.mp3").write_bytes(FAKE_MP3)
        (job_dir / "chuong_1_nho_ngot_ngao_full.mp3").write_bytes(FAKE_MP3)
        if with_manifest:
            (job_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "input_name": "Chương 1",
                        "voice_display_name": "Nhỏ Ngọt Ngào",
                        "voice_type": "BV421_vivn_streaming",
                        "state": "success",
                        "total_parts": 1,
                        "done_parts": 1,
                        "full_audio": str(job_dir / "chuong_1_nho_ngot_ngao_full.mp3"),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (run / "report.json").write_text(
                json.dumps({"started_at": "2026-08-06T10:00:00", "summary": {"success": 1}}),
                encoding="utf-8",
            )
        return run

    def test_scan_run_with_manifest(self) -> None:
        run_dir = self._make_run("2026-08-06_10-00-00")
        run = scan_run(run_dir)
        self.assertIsNotNone(run)
        self.assertTrue(run.has_report)
        self.assertEqual(len(run.jobs), 1)
        job = run.jobs[0]
        self.assertEqual(job.input_name, "Chương 1")
        self.assertEqual(job.voice_label, "Nhỏ Ngọt Ngào")
        self.assertEqual(len(job.audios), 2)
        self.assertTrue(job.audios[0].is_full, "File full phải nằm đầu danh sách")

    def test_scan_run_without_manifest_falls_back_to_disk(self) -> None:
        run_dir = self._make_run("2026-08-06_11-00-00", with_manifest=False)
        run = scan_run(run_dir)
        self.assertIsNotNone(run)
        self.assertEqual(len(run.jobs), 1)
        self.assertFalse(run.has_report)
        self.assertIn("manifest", run.jobs[0].message.lower())

    def test_scan_runs_newest_first(self) -> None:
        self._make_run("2026-08-06_09-00-00")
        self._make_run("2026-08-06_12-00-00")
        runs = scan_runs(self.root)
        self.assertEqual([r.name for r in runs], ["2026-08-06_12-00-00", "2026-08-06_09-00-00"])

    def test_scan_runs_empty_root(self) -> None:
        self.assertEqual(scan_runs(self.root / "khong_co"), [])

    def test_scan_ignores_empty_dirs(self) -> None:
        (self.root / "rong").mkdir()
        self.assertEqual(scan_runs(self.root), [])

    def test_to_dict_serializable(self) -> None:
        self._make_run("2026-08-06_10-00-00")
        data = [r.to_dict() for r in scan_runs(self.root)]
        json.dumps(data, ensure_ascii=False)      # khong nem exception


class TestSettings(unittest.TestCase):
    """Dung file INI tam (truyen truc tiep), khong ghi vao registry nguoi dung."""

    def setUp(self) -> None:
        from PySide6.QtCore import QSettings

        self.tmp = tempfile.TemporaryDirectory()
        self.ini = Path(self.tmp.name) / "test.ini"
        self.qsettings = QSettings(str(self.ini), QSettings.Format.IniFormat)
        self.assertTrue(self.qsettings.fileName().endswith("test.ini"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def manager(self):
        from desktop_app.settings_manager import SettingsManager

        return SettingsManager(self.qsettings)

    def test_defaults(self) -> None:
        from desktop_app.settings_manager import THEME_DARK, default_output_dir

        settings = self.manager()
        self.assertEqual(settings.chunk_chars, 2000)
        self.assertEqual(settings.rate, "1.0")
        self.assertEqual(settings.workers, 1)
        self.assertEqual(settings.theme, THEME_DARK)
        self.assertEqual(settings.output_dir, default_output_dir())
        self.assertEqual(settings.favorites, [])

    def test_default_output_dir_is_documents(self) -> None:
        from desktop_app.settings_manager import default_output_dir

        path = default_output_dir()
        self.assertEqual(path.name, "outputs")
        self.assertEqual(path.parent.name, "Fanfic Audio Studio")
        self.assertEqual(path.parent.parent.name, "Documents")

    def test_workers_clamped_to_two(self) -> None:
        settings = self.manager()
        settings.workers = 9
        self.assertEqual(settings.workers, 2)
        settings.workers = 0
        self.assertEqual(settings.workers, 1)

    def test_chunk_clamped(self) -> None:
        settings = self.manager()
        settings.chunk_chars = 99999
        self.assertEqual(settings.chunk_chars, 5000)
        settings.chunk_chars = 1
        self.assertEqual(settings.chunk_chars, 200)

    def test_favorites_roundtrip(self) -> None:
        settings = self.manager()
        settings.favorites = ["a|1", "b|2"]
        self.qsettings.sync()
        self.assertEqual(sorted(self.manager().favorites), ["a|1", "b|2"])

    def test_bad_rate_falls_back(self) -> None:
        settings = self.manager()
        settings.rate = "không phải số"
        self.assertEqual(settings.rate, "1.0")

    def test_theme_validation(self) -> None:
        from desktop_app.settings_manager import THEME_DARK

        settings = self.manager()
        settings.theme = "mau_gi_do"
        self.assertEqual(settings.theme, THEME_DARK)

    def test_env_override_avoids_registry(self) -> None:
        import os

        from desktop_app.settings_manager import SETTINGS_FILE_ENV, make_qsettings

        target = Path(self.tmp.name) / "override.ini"
        previous = os.environ.get(SETTINGS_FILE_ENV)
        os.environ[SETTINGS_FILE_ENV] = str(target)
        try:
            name = make_qsettings().fileName()
        finally:
            if previous is None:
                os.environ.pop(SETTINGS_FILE_ENV, None)
            else:
                os.environ[SETTINGS_FILE_ENV] = previous
        self.assertTrue(name.endswith("override.ini"), name)
        self.assertNotIn("HKEY", name.upper())

    def test_import_device_json_validates(self) -> None:
        settings = self.manager()
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("khong phai json", encoding="utf-8")
        with self.assertRaises(ValueError):
            settings.import_device_json(bad)

        not_object = Path(self.tmp.name) / "list.json"
        not_object.write_text("[1,2,3]", encoding="utf-8")
        with self.assertRaises(ValueError):
            settings.import_device_json(not_object)

        with self.assertRaises(ValueError):
            settings.import_device_json(Path(self.tmp.name) / "khong_co.json")

    def test_active_device_path_none_by_default(self) -> None:
        settings = self.manager()
        with mock.patch.object(
            type(settings), "runtime_device_path",
            lambda self: Path(self.settings.fileName()).parent / "khong_co_device.json",
        ):
            self.assertIsNone(settings.active_device_path())


class TestMaskSecret(unittest.TestCase):
    def test_mask(self) -> None:
        from desktop_app.models import mask_secret

        masked = mask_secret("supersecrettoken12345")
        self.assertIsNotNone(masked)
        self.assertNotIn("secrettoken", masked)
        self.assertIn("đã che", masked)
        self.assertIsNone(mask_secret(None))
        self.assertIsNone(mask_secret(""))
        self.assertEqual(mask_secret("ab"), "**")


if __name__ == "__main__":
    unittest.main(verbosity=2)
