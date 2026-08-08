"""
Test hang doi: so job = file x voice, pause/resume/stop, retry,
checkpoint-resume, 403 chan hang doi, 429 khong chan.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from desktop_app.models import (
    ErrorKind,
    InputItem,
    InputKind,
    JobState,
    PartState,
    QueueState,
)
from desktop_app.output_manager import find_resume_parts, load_manifest
from desktop_app.queue_manager import QueueHooks, QueueManager, build_jobs, estimate_job_count
from desktop_app.text_importer import make_text_item
from desktop_app.tts_service import TtsError
from tests.mocks import StubTtsService, fail_part, fail_with, make_voice

LONG_TEXT = "\n\n".join(f"Đoạn số {i}. " + ("nội dung tiếng Việt " * 30) for i in range(6))


def wait_until(predicate, timeout: float = 8.0, step: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


class QueueTestBase(unittest.TestCase):
    """
    Nen tang cho test hang doi.

    ffmpeg duoc GIA LAP o day: cac part trong test la byte gia (khong phai MP3
    that) nen ffmpeg that se tu choi. Viec ghep bang ffmpeg that duoc kiem tra
    rieng trong tests/test_output_manager.py (voi MP3 that do ffmpeg sinh ra).
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "outputs"
        self.root.mkdir(parents=True)
        self.voice_a = make_voice("BV421_vivn_streaming", "Nhỏ Ngọt Ngào", "111")
        self.voice_b = make_voice("BV074_streaming", "Cô Gái Hoạt Ngôn", "222")
        self.states: list[str] = []
        self.messages: list[tuple[str, str]] = []
        self.finished = threading.Event()
        self.summary: dict = {}
        self.ffmpeg_calls: list = []

        def fake_ffmpeg(args, cwd=None):
            self.ffmpeg_calls.append((args, cwd))
            target = Path(cwd) / args[-1] if cwd else Path(args[-1])
            target.write_bytes(b"MERGED" * 64)
            return 0, ""

        self._patchers = [
            mock.patch("desktop_app.output_manager.find_ffmpeg", return_value="fake-ffmpeg.exe"),
            mock.patch("desktop_app.output_manager._run_ffmpeg", side_effect=fake_ffmpeg),
        ]
        for patcher in self._patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in self._patchers:
            patcher.stop()
        self.tmp.cleanup()

    def hooks(self) -> QueueHooks:
        def on_finished(summary):
            self.summary = dict(summary)
            self.finished.set()

        return QueueHooks(
            job_updated=lambda job: None,
            queue_changed=lambda state: self.states.append(
                state.value if hasattr(state, "value") else str(state)
            ),
            message=lambda level, text: self.messages.append((level, text)),
            finished=on_finished,
        )

    def make_queue(self, service: StubTtsService, workers: int = 1, ffmpeg: str = "") -> QueueManager:
        return QueueManager(
            outputs_root=self.root,
            service_factory=lambda: service,
            hooks=self.hooks(),
            workers=workers,
            ffmpeg_path=ffmpeg,
            gap_between_jobs=0.0,
            gap_between_parts=0.0,
        )

    def run_queue(self, queue: QueueManager, timeout: float = 20.0) -> None:
        queue.output_manager.create_run()
        self.assertTrue(queue.start(run_dir=queue.output_manager.run_dir))
        queue.wait(timeout)
        self.assertTrue(self.finished.wait(timeout), "Hàng đợi không kết thúc đúng hạn")


# -----------------------------------------------------------------------------
# So luong job
# -----------------------------------------------------------------------------


class TestJobCount(unittest.TestCase):
    def test_estimate_formula(self) -> None:
        self.assertEqual(estimate_job_count(3, 4), 12)
        self.assertEqual(estimate_job_count(0, 5), 0)
        self.assertEqual(estimate_job_count(5, 0), 0)
        self.assertEqual(estimate_job_count(1, 129), 129)

    def test_build_jobs_is_cross_product(self) -> None:
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(3)]
        voices = [make_voice(f"v{i}", f"Giọng {i}", str(i)) for i in range(4)]
        jobs = build_jobs(inputs, voices, 2000)
        self.assertEqual(len(jobs), 12)
        self.assertEqual(len({(j.input_name, j.voice.uid) for j in jobs}), 12)

    def test_invalid_inputs_are_excluded(self) -> None:
        good = make_text_item("Có nội dung", name="ok")
        empty = make_text_item("   ", name="rong")
        broken = InputItem(name="loi", kind=InputKind.FILE, path="x.txt", error="không đọc được")
        jobs = build_jobs([good, empty, broken], [make_voice()], 2000)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].input_name, "ok")

    def test_long_text_creates_multiple_parts(self) -> None:
        jobs = build_jobs([make_text_item(LONG_TEXT, name="dai")], [make_voice()], 500)
        self.assertEqual(len(jobs), 1)
        self.assertGreater(jobs[0].total_parts, 1)
        self.assertEqual([p.index for p in jobs[0].parts], list(range(1, jobs[0].total_parts + 1)))

    def test_part_file_names(self) -> None:
        jobs = build_jobs([make_text_item(LONG_TEXT, name="dai")], [make_voice()], 400)
        names = [p.file_name for p in jobs[0].parts]
        self.assertEqual(names[0], "part_001.mp3")
        self.assertEqual(names[1], "part_002.mp3")

    def test_chunk_size_normalized(self) -> None:
        jobs = build_jobs([make_text_item("Ngắn", name="a")], [make_voice()], 5)
        self.assertGreaterEqual(jobs[0].chunk_chars, 200)


# -----------------------------------------------------------------------------
# Chay binh thuong
# -----------------------------------------------------------------------------


class TestQueueRun(QueueTestBase):
    def test_single_job_single_part_success(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a], 2000))
        self.run_queue(queue)

        job = queue.jobs[0]
        self.assertEqual(job.state, JobState.SUCCESS)
        self.assertEqual(job.done_parts, 1)
        self.assertTrue(Path(job.full_path).is_file())
        self.assertEqual(queue.state, QueueState.FINISHED)

    def test_output_directory_structure(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("Xin chào", name="Chương 1")], [self.voice_a], 2000))
        self.run_queue(queue)

        job_dir = Path(queue.jobs[0].job_dir)
        run_dir = Path(queue.output_manager.run_dir)
        # outputs/<timestamp>/<ten_input>/<ten_voice>/
        self.assertEqual(job_dir.parent.parent, run_dir)
        self.assertEqual(job_dir.name, "nho_ngot_ngao")
        self.assertEqual(job_dir.parent.name, "chuong_1")
        self.assertTrue((job_dir / "part_001.mp3").is_file())
        self.assertTrue((job_dir / "manifest.json").is_file())
        self.assertTrue((job_dir / "chuong_1_nho_ngot_ngao_full.mp3").is_file())
        self.assertTrue((run_dir / "report.json").is_file())

    def test_multi_part_sequential_and_ordered(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue)

        job = queue.jobs[0]
        self.assertGreater(job.total_parts, 2)
        self.assertEqual(job.done_parts, job.total_parts)
        # cac part cua cung job chay tuan tu theo dung thu tu
        self.assertEqual(service.calls, [p.text for p in job.parts])

    def test_multiple_voices_run_sequentially_by_default(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service, workers=1)
        jobs = build_jobs(
            [make_text_item("Xin chào", name="a")], [self.voice_a, self.voice_b], 2000
        )
        queue.set_jobs(jobs)
        self.run_queue(queue)
        self.assertEqual(len(service.calls), 2)
        self.assertTrue(all(j.state == JobState.SUCCESS for j in queue.jobs))

    def test_worker_limit_capped_at_two(self) -> None:
        queue = self.make_queue(StubTtsService(), workers=9)
        self.assertEqual(queue.workers, 2)

    def test_two_workers_complete_all_jobs(self) -> None:
        service = StubTtsService(delay=0.01)
        queue = self.make_queue(service, workers=2)
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(4)]
        queue.set_jobs(build_jobs(inputs, [self.voice_a], 2000))
        self.run_queue(queue)
        self.assertTrue(all(j.state == JobState.SUCCESS for j in queue.jobs))
        self.assertEqual(len(service.calls), 4)

    def test_manifest_content(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        item = make_text_item("Xin chào Việt Nam", name="a")
        queue.set_jobs(build_jobs([item], [self.voice_a], 2000))
        self.run_queue(queue)

        data = load_manifest(Path(queue.jobs[0].job_dir) / "manifest.json")
        self.assertIsNotNone(data)
        for field in (
            "content_sha256", "input_kind", "voice_type", "resource_id",
            "rate", "chunk_chars", "parts", "started_at", "finished_at", "full_audio",
        ):
            self.assertIn(field, data, field)
        self.assertEqual(data["voice_type"], "BV421_vivn_streaming")
        self.assertEqual(data["resource_id"], "111")
        self.assertEqual(len(data["content_sha256"]), 64)
        self.assertEqual(data["parts"][0]["state"], "success")

    def test_manifest_never_contains_raw_token(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a], 2000))
        self.run_queue(queue)
        raw = (Path(queue.jobs[0].job_dir) / "manifest.json").read_text("utf-8")
        self.assertIn("đã che", raw)
        self.assertNotIn("tok-secret-value", raw)

    def test_report_summary(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a], 2000))
        self.run_queue(queue)
        report = load_manifest(Path(queue.output_manager.run_dir) / "report.json")
        self.assertEqual(report["summary"]["success"], 1)
        self.assertFalse(report["stopped_by_user"])

    def test_runs_do_not_overwrite_each_other(self) -> None:
        for _ in range(2):
            self.finished.clear()
            service = StubTtsService()
            queue = self.make_queue(service)
            queue.set_jobs(build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a], 2000))
            self.run_queue(queue)
        run_dirs = [p for p in self.root.iterdir() if p.is_dir()]
        self.assertEqual(len(run_dirs), 2, [p.name for p in run_dirs])


# -----------------------------------------------------------------------------
# Loi
# -----------------------------------------------------------------------------


class TestQueueErrors(QueueTestBase):
    def test_one_failed_job_does_not_stop_others(self) -> None:
        def behaviour(text, index):
            if index == 0:
                raise TtsError(ErrorKind.READ_TIMEOUT, "giả lập read timeout")

        service = StubTtsService(behaviour=behaviour)
        queue = self.make_queue(service)
        queue.set_jobs(
            build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a, self.voice_b], 2000)
        )
        self.run_queue(queue)

        self.assertEqual(queue.jobs[0].state, JobState.FAILED)
        self.assertEqual(queue.jobs[0].error_kind, ErrorKind.READ_TIMEOUT.value)
        self.assertEqual(queue.jobs[1].state, JobState.SUCCESS)
        self.assertEqual(queue.state, QueueState.FINISHED)

    def test_failed_part_continues_to_next_part(self) -> None:
        service = StubTtsService(behaviour=fail_part(2, ErrorKind.TASK_FAILED))
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue)

        job = queue.jobs[0]
        self.assertEqual(job.state, JobState.PARTIAL)
        self.assertEqual(job.failed_parts, 1)
        self.assertEqual(job.done_parts, job.total_parts - 1)
        self.assertIsNone(job.full_path, "Không được tạo file full khi thiếu part")

    def test_http_403_blocks_whole_queue(self) -> None:
        service = StubTtsService(behaviour=fail_with(ErrorKind.HTTP_403, "403 giả lập"))
        queue = self.make_queue(service)
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(4)]
        queue.set_jobs(build_jobs(inputs, [self.voice_a], 2000))
        self.run_queue(queue)

        self.assertEqual(queue.state, QueueState.BLOCKED)
        self.assertIn("DỪNG", queue.blocked_reason)
        self.assertEqual(queue.jobs[0].state, JobState.FAILED)
        self.assertTrue(all(j.state == JobState.SKIPPED for j in queue.jobs[1:]))
        # Chi goi API dung 1 lan roi dung han, khong gui tiep hang loat
        self.assertEqual(len(service.calls), 1)
        self.assertTrue(any(level == "error" for level, _ in self.messages))

    def test_shark_block_blocks_whole_queue(self) -> None:
        service = StubTtsService(behaviour=fail_with(ErrorKind.SHARK_BLOCK, "shark giả lập"))
        queue = self.make_queue(service)
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(3)]
        queue.set_jobs(build_jobs(inputs, [self.voice_a], 2000))
        self.run_queue(queue)
        self.assertEqual(queue.state, QueueState.BLOCKED)
        self.assertEqual(len(service.calls), 1)

    def test_http_429_does_not_block_queue(self) -> None:
        """429 chi lam job that bai (sau khi service da tu backoff), khong chan hang doi."""
        service = StubTtsService(behaviour=fail_with(ErrorKind.HTTP_429, "429 giả lập"))
        queue = self.make_queue(service)
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(3)]
        queue.set_jobs(build_jobs(inputs, [self.voice_a], 2000))
        self.run_queue(queue)

        self.assertEqual(queue.state, QueueState.FINISHED)
        self.assertEqual(len(service.calls), 3, "Các job sau vẫn phải được thử")
        self.assertTrue(all(j.state == JobState.FAILED for j in queue.jobs))

    def test_unexpected_exception_does_not_kill_queue(self) -> None:
        def behaviour(text, index):
            if index == 0:
                raise RuntimeError("lỗi lạ")

        service = StubTtsService(behaviour=behaviour)
        queue = self.make_queue(service)
        queue.set_jobs(
            build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a, self.voice_b], 2000)
        )
        self.run_queue(queue)
        self.assertEqual(queue.jobs[0].state, JobState.FAILED)
        self.assertEqual(queue.jobs[0].error_kind, ErrorKind.UNEXPECTED.value)
        self.assertEqual(queue.jobs[1].state, JobState.SUCCESS)

    def test_service_factory_failure_is_handled(self) -> None:
        def bad_factory():
            raise RuntimeError("không tạo được service")

        queue = QueueManager(
            outputs_root=self.root,
            service_factory=bad_factory,
            hooks=self.hooks(),
            gap_between_jobs=0.0,
            gap_between_parts=0.0,
        )
        queue.set_jobs(build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a], 2000))
        self.run_queue(queue)
        self.assertEqual(queue.jobs[0].state, JobState.FAILED)
        self.assertTrue(any(level == "error" for level, _ in self.messages))


# -----------------------------------------------------------------------------
# Pause / Resume / Stop
# -----------------------------------------------------------------------------


class TestQueueControls(QueueTestBase):
    def test_pause_then_resume(self) -> None:
        service = StubTtsService(delay=0.05)
        queue = self.make_queue(service)
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(6)]
        queue.set_jobs(build_jobs(inputs, [self.voice_a], 2000))

        queue.output_manager.create_run()
        queue.start(run_dir=queue.output_manager.run_dir)

        self.assertTrue(wait_until(lambda: len(service.calls) >= 1))
        queue.pause()
        self.assertEqual(queue.state, QueueState.PAUSED)

        time.sleep(0.25)
        frozen = len(service.calls)
        time.sleep(0.25)
        self.assertLessEqual(
            len(service.calls) - frozen, 1,
            "Khi tạm dừng không được nhận thêm job mới (ngoài job đang chạy)",
        )

        queue.resume()
        self.assertEqual(queue.state, QueueState.RUNNING)
        self.assertTrue(self.finished.wait(20))
        self.assertEqual(len(service.calls), 6)
        self.assertTrue(all(j.state == JobState.SUCCESS for j in queue.jobs))
        self.assertIn("paused", self.states)

    def test_stop_skips_remaining_jobs(self) -> None:
        service = StubTtsService(delay=0.05)
        queue = self.make_queue(service)
        inputs = [make_text_item(f"Nội dung {i}", name=f"in{i}") for i in range(8)]
        queue.set_jobs(build_jobs(inputs, [self.voice_a], 2000))

        queue.output_manager.create_run()
        queue.start(run_dir=queue.output_manager.run_dir)
        self.assertTrue(wait_until(lambda: len(service.calls) >= 1))
        queue.stop()

        self.assertTrue(self.finished.wait(20))
        self.assertEqual(queue.state, QueueState.STOPPED)
        self.assertLess(len(service.calls), 8, "Phải còn job chưa được gửi")
        self.assertTrue(any(j.state == JobState.SKIPPED for j in queue.jobs))
        # Thong bao phai noi ro khong huy duoc request dang chay
        self.assertTrue(
            any("không thể hủy" in text.lower() for _, text in self.messages),
            self.messages,
        )

    def test_stop_message_is_honest_about_http(self) -> None:
        queue = self.make_queue(StubTtsService(delay=0.05))
        queue.set_jobs(build_jobs([make_text_item("a", name="a")], [self.voice_a], 2000))
        queue.output_manager.create_run()
        queue.start(run_dir=queue.output_manager.run_dir)
        queue.stop()
        self.assertTrue(self.finished.wait(20))
        joined = " ".join(text for _, text in self.messages).lower()
        self.assertIn("timeout", joined)

    def test_pause_when_not_running_is_noop(self) -> None:
        queue = self.make_queue(StubTtsService())
        queue.pause()
        self.assertEqual(queue.state, QueueState.IDLE)
        queue.resume()
        self.assertEqual(queue.state, QueueState.IDLE)

    def test_start_twice_is_rejected(self) -> None:
        service = StubTtsService(delay=0.1)
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("a", name="a")], [self.voice_a], 2000))
        queue.output_manager.create_run()
        self.assertTrue(queue.start(run_dir=queue.output_manager.run_dir))
        self.assertFalse(queue.start())
        self.assertTrue(self.finished.wait(20))

    def test_start_with_no_pending_jobs(self) -> None:
        queue = self.make_queue(StubTtsService())
        queue.set_jobs([])
        self.assertFalse(queue.start())

    def test_set_jobs_while_running_raises(self) -> None:
        service = StubTtsService(delay=0.1)
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("a", name="a")], [self.voice_a], 2000))
        queue.output_manager.create_run()
        queue.start(run_dir=queue.output_manager.run_dir)
        with self.assertRaises(RuntimeError):
            queue.set_jobs([])
        self.assertTrue(self.finished.wait(20))

    def test_stats_and_progress(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.assertEqual(queue.overall_progress(), 0)
        self.run_queue(queue)
        self.assertEqual(queue.overall_progress(), 100)
        self.assertEqual(queue.stats()["success"], 1)


# -----------------------------------------------------------------------------
# Retry
# -----------------------------------------------------------------------------


class TestRetry(QueueTestBase):
    def test_retry_failed_reruns_only_failed_jobs(self) -> None:
        attempts = {"n": 0}

        def behaviour(text, index):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise TtsError(ErrorKind.READ_TIMEOUT, "lần đầu lỗi")

        service = StubTtsService(behaviour=behaviour)
        queue = self.make_queue(service)
        queue.set_jobs(
            build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a, self.voice_b], 2000)
        )
        self.run_queue(queue)
        self.assertEqual(queue.jobs[0].state, JobState.FAILED)
        self.assertEqual(queue.jobs[1].state, JobState.SUCCESS)

        # Retry: chi job that bai duoc dat lai
        self.finished.clear()
        count = queue.retry_failed()
        self.assertEqual(count, 1)
        self.assertEqual(queue.jobs[0].state, JobState.PENDING)
        self.assertEqual(queue.jobs[1].state, JobState.SUCCESS)

        self.run_queue(queue)
        self.assertEqual(queue.jobs[0].state, JobState.SUCCESS)

    def test_retry_keeps_successful_parts(self) -> None:
        service = StubTtsService(behaviour=fail_part(2, ErrorKind.TASK_FAILED))
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue)

        job = queue.jobs[0]
        total = job.total_parts
        done_before = job.done_parts
        self.assertEqual(job.state, JobState.PARTIAL)

        self.finished.clear()
        service.behaviour = None            # lan nay khong loi
        service.calls.clear()
        queue.retry_failed()
        self.run_queue(queue)

        self.assertEqual(job.state, JobState.SUCCESS)
        self.assertEqual(job.done_parts, total)
        # Chi chay lai dung so part con thieu, khong lam lai part da xong
        self.assertEqual(len(service.calls), total - done_before)

    def test_retry_single_job(self) -> None:
        service = StubTtsService(behaviour=fail_with(ErrorKind.TASK_FAILED))
        queue = self.make_queue(service)
        queue.set_jobs(
            build_jobs([make_text_item("Xin chào", name="a")], [self.voice_a, self.voice_b], 2000)
        )
        self.run_queue(queue)
        self.assertTrue(all(j.state == JobState.FAILED for j in queue.jobs))

        target = queue.jobs[1]
        self.finished.clear()
        service.behaviour = None
        self.assertTrue(queue.retry_job(target.job_id))
        self.assertEqual(target.state, JobState.PENDING)
        self.assertEqual(queue.jobs[0].state, JobState.FAILED)

        self.run_queue(queue)
        self.assertEqual(target.state, JobState.SUCCESS)
        self.assertEqual(queue.jobs[0].state, JobState.FAILED)

    def test_retry_unknown_job_returns_false(self) -> None:
        queue = self.make_queue(StubTtsService())
        self.assertFalse(queue.retry_job("khong-ton-tai"))

    def test_retry_success_job_returns_false(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("a", name="a")], [self.voice_a], 2000))
        self.run_queue(queue)
        self.assertFalse(queue.retry_job(queue.jobs[0].job_id))

    def test_retry_while_running_raises(self) -> None:
        service = StubTtsService(delay=0.1)
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item("a", name="a")], [self.voice_a], 2000))
        queue.output_manager.create_run()
        queue.start(run_dir=queue.output_manager.run_dir)
        with self.assertRaises(RuntimeError):
            queue.retry_failed()
        self.assertTrue(self.finished.wait(20))


# -----------------------------------------------------------------------------
# Checkpoint / resume
# -----------------------------------------------------------------------------


class TestResumeCheckpoint(QueueTestBase):
    def test_checkpoint_written_after_each_part(self) -> None:
        seen = []

        def behaviour(text, index):
            # Doc manifest ngay truoc khi tao part tiep theo
            job_dir = Path(self.root).glob("*/*/*/manifest.json")
            seen.append(len(list(job_dir)))

        service = StubTtsService(behaviour=behaviour)
        queue = self.make_queue(service)
        queue.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue)
        # Tu part thu 2 tro di, manifest checkpoint da ton tai
        self.assertGreaterEqual(max(seen), 1)

    def test_find_resume_parts_matches_same_content_and_voice(self) -> None:
        service = StubTtsService(behaviour=fail_part(3, ErrorKind.TASK_FAILED))
        queue = self.make_queue(service)
        jobs = build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400)
        queue.set_jobs(jobs)
        self.run_queue(queue)

        job = queue.jobs[0]
        found = find_resume_parts(
            self.root, job.content_hash, self.voice_a.voice_type,
            self.voice_a.resource_id, job.chunk_chars, job.total_parts,
        )
        self.assertEqual(len(found), job.done_parts)
        self.assertNotIn(3, found)

    def test_find_resume_parts_ignores_other_voice(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        jobs = build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400)
        queue.set_jobs(jobs)
        self.run_queue(queue)
        job = queue.jobs[0]

        self.assertEqual(
            find_resume_parts(
                self.root, job.content_hash, self.voice_b.voice_type,
                self.voice_b.resource_id, job.chunk_chars, job.total_parts,
            ),
            {},
        )

    def test_find_resume_parts_ignores_different_chunk_size(self) -> None:
        service = StubTtsService()
        queue = self.make_queue(service)
        jobs = build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400)
        queue.set_jobs(jobs)
        self.run_queue(queue)
        job = queue.jobs[0]
        self.assertEqual(
            find_resume_parts(
                self.root, job.content_hash, self.voice_a.voice_type,
                self.voice_a.resource_id, 999, job.total_parts,
            ),
            {},
        )

    def test_new_run_resumes_from_previous_run(self) -> None:
        """Mo phong app bi dong: lan chay sau tiep tuc tu part con thieu."""
        service = StubTtsService(behaviour=fail_part(3, ErrorKind.TASK_FAILED))
        queue1 = self.make_queue(service)
        queue1.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue1)

        job1 = queue1.jobs[0]
        total = job1.total_parts
        done_first = job1.done_parts
        self.assertLess(done_first, total)

        # Lan chay hoan toan moi (QueueManager moi, run dir moi)
        self.finished.clear()
        self.states.clear()
        service2 = StubTtsService()
        queue2 = self.make_queue(service2)
        queue2.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue2)

        job2 = queue2.jobs[0]
        self.assertEqual(job2.state, JobState.SUCCESS)
        self.assertEqual(job2.done_parts, total)
        # Chi tao lai cac part con thieu
        self.assertEqual(len(service2.calls), total - done_first)
        # Ket qua lan chay cu KHONG bi ghi de
        self.assertTrue(Path(job1.job_dir).is_dir())
        self.assertNotEqual(job1.job_dir, job2.job_dir)
        # Part duoc tiep tuc phai co mat trong thu muc moi
        self.assertTrue((Path(job2.job_dir) / "part_001.mp3").is_file())

    def test_resume_copies_do_not_touch_old_run(self) -> None:
        service = StubTtsService(behaviour=fail_part(2, ErrorKind.TASK_FAILED))
        queue1 = self.make_queue(service)
        queue1.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue1)
        old_part = Path(queue1.jobs[0].job_dir) / "part_001.mp3"
        before = old_part.read_bytes()

        self.finished.clear()
        queue2 = self.make_queue(StubTtsService())
        queue2.set_jobs(build_jobs([make_text_item(LONG_TEXT, name="dai")], [self.voice_a], 400))
        self.run_queue(queue2)

        self.assertTrue(old_part.is_file())
        self.assertEqual(before, old_part.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
