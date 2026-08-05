"""
Hang doi job: moi cap (input x voice) la mot job.

Module nay la Python thuan (khong import PySide6) de co the unit test doc lap.
Phan noi voi giao dien nam trong `workers.py`, thong qua cac hook callable.

Hanh vi quan trong:
- Concurrency mac dinh 1, toi da 2 worker.
- Cac part cua CUNG mot job luon chay tuan tu (mot job do mot worker xu ly).
- Stop chi co hieu luc sau khi request hien tai ket thuc hoac het timeout —
  khong huy giua duong duoc mot HTTP request dang chay.
- Pause co hieu luc o ranh gioi part/job.
- Mot job loi khong lam dung cac job khac, TRU 403/shark block: khi do hang doi
  dung han de khong gui tiep hang loat request.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from desktop_app.models import (
    GAP_BETWEEN_JOBS,
    GAP_BETWEEN_PARTS,
    ErrorKind,
    InputItem,
    Job,
    JobPart,
    JobState,
    PartState,
    QueueState,
    VoiceEntry,
)
from desktop_app.output_manager import (
    OutputManager,
    adopt_resumed_parts,
    find_resume_parts,
    merge_job_audio,
)
from desktop_app.text_chunker import chunk_text, normalize_chunk_size
from desktop_app.tts_service import CancelToken, StopRequested, TtsError, TtsService


def _noop(*args, **kwargs) -> None:
    return None


@dataclass
class QueueHooks:
    """Cac callback de giao dien theo doi hang doi (co the goi tu worker thread)."""

    job_updated: Callable[[Job], None] = _noop
    queue_changed: Callable[[QueueState], None] = _noop
    message: Callable[[str, str], None] = _noop         # (level, text): info|warn|error
    finished: Callable[[Dict[str, object]], None] = _noop


def estimate_job_count(input_count: int, voice_count: int) -> int:
    """so_input x so_voice"""
    return max(0, int(input_count)) * max(0, int(voice_count))


def build_jobs(
    inputs: Sequence[InputItem],
    voices: Sequence[VoiceEntry],
    chunk_chars: int,
    rate: str = "1.0",
) -> List[Job]:
    """
    Tao danh sach job = (moi input hop le) x (moi voice).

    Input loi/rong bi bo qua (da co `error` de giao dien hien rieng).
    Thu tu: theo input, roi theo voice — de ket qua cua cung mot input nam gan nhau.
    """
    chunk_chars = normalize_chunk_size(chunk_chars)
    jobs: List[Job] = []
    for item in inputs:
        if not item.is_valid:
            continue
        chunks = chunk_text(item.text, chunk_chars)
        if not chunks:
            continue
        for voice in voices:
            job = Job(
                input_name=item.name,
                input_slug=item.slug,
                voice=voice,
                text=item.text,
                rate=rate,
                chunk_chars=chunk_chars,
                input_kind=item.kind,
                input_path=item.path,
            )
            job.parts = [
                JobPart(index=i + 1, text=chunk) for i, chunk in enumerate(chunks)
            ]
            jobs.append(job)
    return jobs


class QueueManager:
    """Dieu phoi viec chay cac job."""

    def __init__(
        self,
        outputs_root: Path | str,
        service_factory: Callable[[], TtsService],
        hooks: Optional[QueueHooks] = None,
        workers: int = 1,
        ffmpeg_path: str = "",
        gap_between_jobs: float = GAP_BETWEEN_JOBS,
        gap_between_parts: float = GAP_BETWEEN_PARTS,
    ):
        self.outputs_root = Path(outputs_root)
        self.service_factory = service_factory
        self.hooks = hooks or QueueHooks()
        self.workers = max(1, min(2, int(workers or 1)))
        self.ffmpeg_path = ffmpeg_path or ""
        self.gap_between_jobs = float(gap_between_jobs)
        self.gap_between_parts = float(gap_between_parts)

        self.jobs: List[Job] = []
        self.state: QueueState = QueueState.IDLE
        self.blocked_reason: str = ""
        self.output_manager = OutputManager(self.outputs_root)
        self.report_path: Optional[str] = None

        self._cancel = CancelToken()
        self._resume_event = threading.Event()
        self._resume_event.set()          # set = dang chay, clear = tam dung
        self._lock = threading.RLock()
        self._next_index = 0
        self._threads: List[threading.Thread] = []
        self._stop_requested = False

    # -- trang thai -----------------------------------------------------------

    def _set_state(self, state: QueueState) -> None:
        self.state = state
        self.hooks.queue_changed(state)

    @property
    def is_active(self) -> bool:
        return self.state in (QueueState.RUNNING, QueueState.PAUSED, QueueState.STOPPING)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            jobs = list(self.jobs)
        return {
            "total": len(jobs),
            "pending": sum(1 for j in jobs if j.state == JobState.PENDING),
            "running": sum(1 for j in jobs if j.state == JobState.RUNNING),
            "success": sum(1 for j in jobs if j.state == JobState.SUCCESS),
            "partial": sum(1 for j in jobs if j.state == JobState.PARTIAL),
            "failed": sum(1 for j in jobs if j.state == JobState.FAILED),
            "stopped": sum(1 for j in jobs if j.state == JobState.STOPPED),
            "skipped": sum(1 for j in jobs if j.state == JobState.SKIPPED),
        }

    def overall_progress(self) -> int:
        """% tien trinh tong, tinh theo tong so part cua tat ca job."""
        with self._lock:
            jobs = list(self.jobs)
        total = sum(max(1, j.total_parts) for j in jobs)
        if not total:
            return 0
        done = sum(j.done_parts for j in jobs)
        return int(round(100.0 * done / total))

    def find_job(self, job_id: str) -> Optional[Job]:
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        return None

    # -- nap job --------------------------------------------------------------

    def set_jobs(self, jobs: List[Job]) -> None:
        if self.is_active:
            raise RuntimeError("Hàng đợi đang chạy, không thể nạp job mới.")
        with self._lock:
            self.jobs = list(jobs)
            self._next_index = 0
        self.blocked_reason = ""
        self.report_path = None
        self._set_state(QueueState.IDLE)

    def clear(self) -> None:
        if self.is_active:
            raise RuntimeError("Hàng đợi đang chạy.")
        with self._lock:
            self.jobs = []
            self._next_index = 0
        self._set_state(QueueState.IDLE)

    # -- dieu khien -----------------------------------------------------------

    def start(self, run_dir: Optional[Path] = None) -> bool:
        """
        Bat dau chay hang doi trong cac worker thread rieng.
        Tra False neu khong co gi de chay hoac dang chay roi.
        """
        if self.is_active:
            return False
        with self._lock:
            pending = [j for j in self.jobs if j.state == JobState.PENDING]
        if not pending:
            return False

        self._cancel = CancelToken()
        self._stop_requested = False
        self._resume_event.set()
        self.blocked_reason = ""

        if run_dir is not None:
            self.output_manager.run_dir = Path(run_dir)
            self.output_manager.run_started_at = datetime.now().isoformat(timespec="seconds")
        elif self.output_manager.run_dir is None:
            self.output_manager.create_run()

        with self._lock:
            self._next_index = 0
        self._set_state(QueueState.RUNNING)

        self._threads = []
        for worker_id in range(self.workers):
            thread = threading.Thread(
                target=self._worker_loop, args=(worker_id,), daemon=True,
                name=f"fas-worker-{worker_id}",
            )
            thread.start()
            self._threads.append(thread)
        return True

    def pause(self) -> None:
        if self.state != QueueState.RUNNING:
            return
        self._resume_event.clear()
        self._set_state(QueueState.PAUSED)
        self.hooks.message(
            "info",
            "Đã tạm dừng. Lệnh có hiệu lực ở ranh giới phần/job — phần đang gửi "
            "vẫn chạy đến khi xong hoặc hết timeout.",
        )

    def resume(self) -> None:
        if self.state != QueueState.PAUSED:
            return
        self._resume_event.set()
        self._set_state(QueueState.RUNNING)
        self.hooks.message("info", "Đã tiếp tục hàng đợi.")

    def stop(self) -> None:
        """
        Yeu cau dung. KHONG huy duoc HTTP request dang chay: lenh chi co hieu luc
        sau khi request hien tai ket thuc hoac het timeout.
        """
        if not self.is_active:
            return
        self._stop_requested = True
        self._cancel.set()
        self._resume_event.set()          # thoat khoi trang thai tam dung
        self._set_state(QueueState.STOPPING)
        self.hooks.message(
            "warn",
            "Đã gửi yêu cầu DỪNG. Không thể hủy một HTTP request đang chạy — "
            "app sẽ dừng sau khi request hiện tại kết thúc hoặc hết timeout "
            "(chậm nhất 30 giây).",
        )

    def wait(self, timeout: Optional[float] = None) -> None:
        """Cho cac worker ket thuc (dung trong test va khi dong app)."""
        for thread in self._threads:
            thread.join(timeout)

    def _block_queue(self, reason: str) -> None:
        """403 / shark block: dung han hang doi."""
        self.blocked_reason = reason
        self._stop_requested = True
        self._cancel.set()
        self._resume_event.set()
        self._set_state(QueueState.BLOCKED)
        self.hooks.message("error", reason)

    # -- retry ----------------------------------------------------------------

    def retry_failed(self) -> int:
        """
        Dua cac job that bai/mot phan/bi dung ve trang thai cho.
        Cac part DA thanh cong duoc giu lai (checkpoint), chi chay lai part con thieu.
        """
        if self.is_active:
            raise RuntimeError("Hàng đợi đang chạy.")
        count = 0
        with self._lock:
            for job in self.jobs:
                if job.state.is_retryable:
                    job.reset_for_retry()
                    count += 1
            self._next_index = 0
        if count:
            self._set_state(QueueState.IDLE)
            for job in self.jobs:
                self.hooks.job_updated(job)
        return count

    def retry_job(self, job_id: str) -> bool:
        """Chay lai mot job cu the."""
        if self.is_active:
            raise RuntimeError("Hàng đợi đang chạy.")
        job = self.find_job(job_id)
        if job is None or not job.state.is_retryable:
            return False
        job.reset_for_retry()
        with self._lock:
            self._next_index = 0
        self._set_state(QueueState.IDLE)
        self.hooks.job_updated(job)
        return True

    # -- vong lap worker ------------------------------------------------------

    def _next_job(self) -> Optional[Job]:
        with self._lock:
            while self._next_index < len(self.jobs):
                job = self.jobs[self._next_index]
                self._next_index += 1
                if job.state == JobState.PENDING:
                    job.state = JobState.RUNNING
                    return job
            return None

    def _wait_if_paused(self) -> bool:
        """Cho trong luc tam dung. Tra False neu bi yeu cau dung."""
        while not self._resume_event.wait(0.2):
            if self._stop_requested:
                return False
        return not self._stop_requested

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Nghi nhung van phan hoi lenh dung. Tra False neu bi dung."""
        if seconds <= 0:
            return not self._stop_requested
        if self._cancel.wait(seconds):
            return False
        return not self._stop_requested

    def _worker_loop(self, worker_id: int) -> None:
        service: Optional[TtsService] = None
        try:
            service = self.service_factory()
        except Exception as exc:
            self.hooks.message("error", f"Không khởi tạo được kết nối API: {exc}")

        first_job = True
        try:
            while True:
                if self._stop_requested or self.state == QueueState.BLOCKED:
                    break
                if not self._wait_if_paused():
                    break

                job = self._next_job()
                if job is None:
                    break

                # Nghi giua cac job de khong spam API
                if not first_job and self.gap_between_jobs > 0:
                    job.message = f"Nghỉ {self.gap_between_jobs:.0f}s trước khi bắt đầu..."
                    self.hooks.job_updated(job)
                    if not self._interruptible_sleep(self.gap_between_jobs):
                        job.state = JobState.SKIPPED
                        job.message = "Đã bỏ qua (hàng đợi dừng)"
                        self.hooks.job_updated(job)
                        break
                first_job = False

                if service is None:
                    job.state = JobState.FAILED
                    job.error_kind = ErrorKind.UNEXPECTED.value
                    job.message = "Không có kết nối API"
                    self.hooks.job_updated(job)
                    continue

                try:
                    self._process_job(job, service)
                except Exception as exc:   # lop bao ve cuoi: khong de app chet
                    job.state = JobState.FAILED
                    job.error_kind = ErrorKind.UNEXPECTED.value
                    job.message = f"Lỗi không mong đợi: {type(exc).__name__}: {exc}"
                    import traceback
                    job.error_detail = traceback.format_exc()[-1500:]
                    self.hooks.job_updated(job)

                self._write_report()
        finally:
            if service is not None:
                service.close()
            self._finish_if_last(worker_id)

    def _finish_if_last(self, worker_id: int) -> None:
        """Worker cuoi cung ket thuc thi tong ket hang doi."""
        alive = [
            t for t in self._threads
            if t.is_alive() and t.name != f"fas-worker-{worker_id}"
        ]
        if alive:
            return

        with self._lock:
            for job in self.jobs:
                if job.state in (JobState.PENDING, JobState.RUNNING):
                    job.state = JobState.SKIPPED
                    job.message = (
                        "Đã bỏ qua (hàng đợi bị chặn)"
                        if self.state == QueueState.BLOCKED
                        else "Đã bỏ qua (hàng đợi dừng)"
                    )
                    self.hooks.job_updated(job)

        self._write_report()

        if self.state == QueueState.BLOCKED:
            final = QueueState.BLOCKED
        elif self._stop_requested:
            final = QueueState.STOPPED
        else:
            final = QueueState.FINISHED
        self._set_state(final)

        summary = self.stats()
        summary["report"] = self.report_path or ""
        summary["run_dir"] = str(self.output_manager.run_dir or "")
        summary["blocked_reason"] = self.blocked_reason
        self.hooks.finished(summary)

    def _write_report(self) -> None:
        try:
            with self._lock:
                jobs = list(self.jobs)
            path = self.output_manager.write_report(
                jobs,
                stopped=self._stop_requested,
                blocked_reason=self.blocked_reason,
            )
            if path:
                self.report_path = path
        except Exception:
            pass

    # -- chay mot job ---------------------------------------------------------

    def _process_job(self, job: Job, service: TtsService) -> None:
        job.state = JobState.RUNNING
        job.started_at = datetime.now().isoformat(timespec="seconds")
        started = time.monotonic()
        job.message = "Đang chuẩn bị..."
        self.hooks.job_updated(job)

        # 1. Thu muc ket qua
        if not job.job_dir:
            try:
                job.job_dir = str(self.output_manager.job_dir(job))
            except Exception as exc:
                job.state = JobState.FAILED
                job.error_kind = ErrorKind.DISK_ERROR.value
                job.message = f"Không tạo được thư mục kết quả: {exc}"
                job.finished_at = datetime.now().isoformat(timespec="seconds")
                self.hooks.job_updated(job)
                return

        # 2. Checkpoint-resume: nhan lai part da thanh cong o lan chay truoc
        try:
            found = find_resume_parts(
                self.outputs_root,
                job.content_hash,
                job.voice.voice_type,
                job.voice.resource_id,
                job.chunk_chars,
                job.total_parts,
            )
            adopted = adopt_resumed_parts(job, found)
            if adopted:
                job.message = f"Tiếp tục từ checkpoint: đã có {adopted}/{job.total_parts} phần"
                self.hooks.job_updated(job)
                self.output_manager.write_manifest(job, extra={"resumed_parts": adopted})
        except Exception:
            pass   # resume that bai thi cu chay lai tu dau, khong lam chet job

        # 3. Chay tung part TUAN TU
        stopped = False
        for part in job.parts:
            if part.state == PartState.SUCCESS:
                continue

            if not self._wait_if_paused():
                stopped = True
                break
            if self._stop_requested:
                stopped = True
                break

            if part.index > 1 and self.gap_between_parts > 0:
                if not self._interruptible_sleep(self.gap_between_parts):
                    stopped = True
                    break

            part.state = PartState.RUNNING
            part.started_at = datetime.now().isoformat(timespec="seconds")
            job.message = f"Phần {part.index}/{job.total_parts}: đang bắt đầu..."
            self.hooks.job_updated(job)

            def progress(text: str, _job: Job = job, _part: JobPart = part) -> None:
                _job.message = f"Phần {_part.index}/{_job.total_parts}: {text}"
                self.hooks.job_updated(_job)

            dest = Path(job.job_dir) / part.file_name
            try:
                result = service.synthesize(
                    text=part.text,
                    voice=job.voice,
                    dest=dest,
                    cancel=self._cancel,
                    rate=job.rate,
                    progress=progress,
                )
                part.state = PartState.SUCCESS
                part.file_path = result.file_path
                part.file_size = result.file_size
                part.task_id = result.task_id
                part.token_masked = result.token_masked
                part.audio_url_host = result.audio_host
                part.attempts = result.attempts
                part.error_kind = None
                part.error_message = ""
                part.finished_at = datetime.now().isoformat(timespec="seconds")
                job.message = f"Xong phần {part.index}/{job.total_parts}"
                # CHECKPOINT sau moi part thanh cong
                self.output_manager.write_manifest(job)
                self.hooks.job_updated(job)

            except StopRequested:
                part.state = PartState.PENDING
                part.finished_at = datetime.now().isoformat(timespec="seconds")
                stopped = True
                break

            except TtsError as exc:
                part.state = PartState.FAILED
                part.error_kind = exc.kind.value
                part.error_message = exc.message
                part.finished_at = datetime.now().isoformat(timespec="seconds")
                job.error_kind = exc.kind.value
                job.error_detail = exc.detail
                job.message = f"Phần {part.index}/{job.total_parts} lỗi: {exc.message}"
                self.output_manager.write_manifest(job)
                self.hooks.job_updated(job)

                if exc.is_fatal_for_queue:
                    job.state = JobState.FAILED
                    job.finished_at = datetime.now().isoformat(timespec="seconds")
                    job.elapsed_seconds = time.monotonic() - started
                    self.output_manager.write_manifest(job)
                    self._block_queue(
                        f"Hàng đợi đã DỪNG vì lỗi nghiêm trọng: {exc.message}. "
                        "Không gửi tiếp request hàng loạt để tránh bị chặn nặng hơn."
                    )
                    return
                # loi thuong: bo qua part nay, tiep tuc part sau
                continue

        # 4. Tong ket + ghep file
        job.elapsed_seconds = time.monotonic() - started
        job.finished_at = datetime.now().isoformat(timespec="seconds")

        if stopped:
            job.state = JobState.STOPPED
            job.error_kind = job.error_kind or ErrorKind.STOPPED.value
            job.message = (
                f"Đã dừng — hoàn thành {job.done_parts}/{job.total_parts} phần "
                "(lần sau có thể tiếp tục từ đây)"
            )
        elif job.done_parts == job.total_parts and job.total_parts > 0:
            merge = merge_job_audio(job, self.ffmpeg_path)
            job.merge_note = merge.note
            if merge.ok:
                job.full_path = merge.path
                job.state = JobState.SUCCESS
                job.message = f"Hoàn thành {job.total_parts} phần"
            else:
                # Cac part van con nguyen — khong bao gia la da co file full
                job.state = JobState.PARTIAL
                job.error_kind = merge.error_kind
                job.message = (
                    f"Đã tạo {job.done_parts}/{job.total_parts} phần nhưng CHƯA ghép được file full"
                )
                if merge.error_kind == ErrorKind.MERGE_FFMPEG_MISSING.value:
                    self.hooks.message("warn", merge.note)
        elif job.done_parts > 0:
            job.state = JobState.PARTIAL
            job.message = (
                f"Chỉ hoàn thành {job.done_parts}/{job.total_parts} phần "
                f"({job.failed_parts} phần lỗi)"
            )
        else:
            job.state = JobState.FAILED
            job.message = job.message or "Thất bại"

        self.output_manager.write_manifest(job)
        self.hooks.job_updated(job)
