"""
Lop noi giua hang doi (Python thuan) va giao dien Qt.

Moi thao tac co the cham — goi API, nhap file, ghep MP3, xuat ZIP — deu chay
trong thread rieng. Giao dien khong bao gio bi chan.

Qt tu dong dua signal tu thread khac ve thread giao dien (queued connection),
nen cac hook cua QueueManager co the goi truc tiep tu worker thread.
"""

from __future__ import annotations

import tempfile
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QObject, QThread, Signal

from desktop_app.models import (
    ErrorKind,
    InputItem,
    Job,
    JobState,
    VoiceEntry,
    human_duration,
)
from desktop_app.queue_manager import QueueHooks
from desktop_app.tts_service import CancelToken, StopRequested, TtsError, TtsService


# -----------------------------------------------------------------------------
# Snapshot job (truyen qua signal thay vi truyen object dang bi worker ghi)
# -----------------------------------------------------------------------------


def job_snapshot(job: Job) -> Dict[str, Any]:
    """Anh chup trang thai job de ve len bang, an toan khi doc tu thread khac."""
    return {
        "job_id": job.job_id,
        "input_name": job.input_name,
        "voice_label": job.voice.label,
        "voice_type": job.voice.voice_type,
        "state": job.state.value,
        "message": job.message,
        "progress": job.progress_percent,
        "done_parts": job.done_parts,
        "total_parts": job.total_parts,
        "failed_parts": job.failed_parts,
        "elapsed": human_duration(job.elapsed_seconds) if job.elapsed_seconds else "—",
        "job_dir": job.job_dir or "",
        "full_path": job.full_path or "",
        "error_kind": job.error_kind or "",
        "merge_note": job.merge_note or "",
        "retryable": job.state.is_retryable,
    }


class QueueBridge(QObject):
    """Chuyen cac hook cua QueueManager thanh Qt signal."""

    jobUpdated = Signal(dict)
    queueChanged = Signal(str)
    messagePosted = Signal(str, str)      # (level, text)
    queueFinished = Signal(dict)

    def hooks(self) -> QueueHooks:
        return QueueHooks(
            job_updated=lambda job: self.jobUpdated.emit(job_snapshot(job)),
            queue_changed=lambda state: self.queueChanged.emit(
                state.value if hasattr(state, "value") else str(state)
            ),
            message=lambda level, text: self.messagePosted.emit(str(level), str(text)),
            finished=lambda summary: self.queueFinished.emit(dict(summary)),
        )


# -----------------------------------------------------------------------------
# Nhap file trong thread rieng
# -----------------------------------------------------------------------------


class ImportWorker(QThread):
    """Doc file/thu muc trong thread rieng (thu muc nhieu .docx co the cham)."""

    progress = Signal(int, int, str)          # (da_xong, tong, ten_file)
    finishedWithItems = Signal(list)          # List[InputItem]
    failed = Signal(str)

    def __init__(self, paths: Sequence[Path | str], recursive: bool = True, parent=None):
        super().__init__(parent)
        self._paths = [Path(p) for p in paths]
        self._recursive = recursive

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        from desktop_app.text_importer import (
            collect_supported_files,
            import_file,
        )

        try:
            targets: List[Path] = []
            for path in self._paths:
                if path.is_dir():
                    targets.extend(collect_supported_files(path, recursive=self._recursive))
                else:
                    targets.append(path)

            items: List[InputItem] = []
            total = len(targets)
            for index, target in enumerate(targets, start=1):
                self.progress.emit(index, total, target.name)
                items.append(import_file(target))
            self.finishedWithItems.emit(items)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# -----------------------------------------------------------------------------
# Thu giong (chi chay khi nguoi dung chu dong bam nut)
# -----------------------------------------------------------------------------

PREVIEW_TEXT = "Xin chào, đây là giọng đọc thử của Fanfic Audio Studio."


class PreviewWorker(QThread):
    """
    Tao mot cau ngan de nghe thu mot giong.
    CHI duoc khoi tao khi nguoi dung bam nut — khong bao gio tu dong goi API.
    """

    statusChanged = Signal(str)
    succeeded = Signal(str, str)        # (voice_uid, duong_dan_file)
    failed = Signal(str, str, str)      # (voice_uid, error_kind, message)

    def __init__(
        self,
        voice,
        device_path: Optional[str] = None,
        rate: str = "1.0",
        text: str = PREVIEW_TEXT,
        parent=None,
        registry=None,
    ):
        super().__init__(parent)
        self.voice = voice
        self.device_path = device_path
        self.rate = rate
        self.text = text or PREVIEW_TEXT
        self.registry = registry
        self._cancel = CancelToken()

    def request_stop(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # pragma: no cover - can mang thuc
        """Nghe thu di QUA ProviderRegistry, khong goi thang CapCutClient nua."""
        from desktop_app.providers.base import ProviderCancelled, ProviderError

        registry = self.registry
        owns_registry = False
        if registry is None:
            from desktop_app.providers.registry import build_default_registry

            registry = build_default_registry(
                service=TtsService(device_path=self.device_path), refresh=False
            )
            owns_registry = True

        try:
            temp_dir = Path(tempfile.gettempdir()) / "FanficAudioStudio_preview"
            temp_dir.mkdir(parents=True, exist_ok=True)
            dest = temp_dir / f"preview_{self.voice.slug}.mp3"

            self.statusChanged.emit(f"Đang thử giọng {self.voice.label}...")
            registry.synthesize(
                text=self.text,
                voice=self.voice,
                dest=dest,
                cancel=self._cancel,
                rate=self.rate,
                progress=lambda msg: self.statusChanged.emit(f"{self.voice.label}: {msg}"),
            )
            self.succeeded.emit(self.voice.uid, str(dest))
        except (StopRequested, ProviderCancelled):
            self.failed.emit(self.voice.uid, ErrorKind.STOPPED.value, "Đã hủy thử giọng.")
        except (TtsError, ProviderError) as exc:
            self.failed.emit(self.voice.uid, exc.kind.value, exc.message)
        except Exception as exc:
            self.failed.emit(
                self.voice.uid,
                ErrorKind.UNEXPECTED.value,
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-400:]}",
            )
        finally:
            if owns_registry:
                registry.close()


# -----------------------------------------------------------------------------
# Tac vu ngan chay nen (xuat ZIP, ghep lai file)
# -----------------------------------------------------------------------------


class ZipWorker(QThread):
    """Nen thu muc ket qua thanh ZIP o thread rieng."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, source_dir: Path | str, parent=None):
        super().__init__(parent)
        self.source_dir = Path(source_dir)

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        from desktop_app.output_manager import export_zip

        try:
            self.succeeded.emit(export_zip(self.source_dir))
        except Exception as exc:
            self.failed.emit(f"Không xuất được ZIP: {exc}")


class MergeWorker(QThread):
    """Ghep lai cac part thanh file full (dung khi nguoi dung vua cai ffmpeg)."""

    succeeded = Signal(str, str)        # (job_id, duong_dan_full)
    failed = Signal(str, str)           # (job_id, thong_bao)

    def __init__(self, job: Job, ffmpeg_path: str = "", parent=None):
        super().__init__(parent)
        self.job = job
        self.ffmpeg_path = ffmpeg_path

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        from desktop_app.output_manager import merge_job_audio

        try:
            result = merge_job_audio(self.job, self.ffmpeg_path)
            if result.ok:
                self.job.full_path = result.path
                self.job.merge_note = result.note
                if self.job.state == JobState.PARTIAL and self.job.done_parts == self.job.total_parts:
                    self.job.state = JobState.SUCCESS
                    self.job.message = f"Hoàn thành {self.job.total_parts} phần (đã ghép lại)"
                self.succeeded.emit(self.job.job_id, result.path or "")
            else:
                self.failed.emit(self.job.job_id, result.note)
        except Exception as exc:
            self.failed.emit(self.job.job_id, f"{type(exc).__name__}: {exc}")


class LibraryWorker(QThread):
    """Doc lai thu vien ket qua (quet thu muc outputs) o thread rieng."""

    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, outputs_root: Path | str, parent=None):
        super().__init__(parent)
        self.outputs_root = Path(outputs_root)

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        from desktop_app.result_library import scan_runs

        try:
            self.loaded.emit([run.to_dict() for run in scan_runs(self.outputs_root)])
        except Exception as exc:
            self.failed.emit(f"Không đọc được thư viện kết quả: {exc}")


# -----------------------------------------------------------------------------
# Kiem tra kha dung cua giong (chay NEN, khong khoa giao dien)
# -----------------------------------------------------------------------------


class ProbeWorker(QThread):
    """
    Kiem tra that su mot hoac nhieu giong.

    Yeu cau quan trong:
    - Chay o thread rieng nen giao dien KHONG bao gio bi khoa.
    - Tuan tu, concurrency = 1, co delay giua cac giong de khong spam API.
    - Huy duoc giua chung.
    - Bo qua giong da co ket qua con hieu luc (tru khi `force`).
    """

    progressed = Signal(int, int, str)      # (da_xong, tong, ten_giong)
    voiceChecked = Signal(str, str, str)    # (voice_id, status_value, reason)
    finishedAll = Signal(int, int, bool)    # (da_kiem_tra, bo_qua, bi_huy)

    #: Nghi giua hai lan probe de khong dam lien tuc vao dich vu.
    DELAY_SECONDS = 1.5

    def __init__(self, registry, voices, force: bool = False, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._voices = list(voices)
        self._force = bool(force)
        self._stop = threading.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        from desktop_app.providers.base import ProviderCancelled

        checked = 0
        skipped = 0
        total = len(self._voices)

        for index, voice in enumerate(self._voices, start=1):
            if self._stop.is_set():
                self.finishedAll.emit(checked, skipped, True)
                return

            if not self._force and self._registry.store.is_fresh(voice.id):
                skipped += 1
                self.progressed.emit(index, total, voice.label)
                continue

            self.progressed.emit(index, total, voice.label)
            try:
                info = self._registry.probe(voice, cancel=self, force=self._force)
            except ProviderCancelled:
                self.finishedAll.emit(checked, skipped, True)
                return
            except Exception as exc:
                # Provider hong KHONG duoc lam sap ung dung
                self.voiceChecked.emit(voice.id, "unavailable", f"Lỗi ngoài dự kiến: {exc}")
                checked += 1
                continue

            checked += 1
            self.voiceChecked.emit(voice.id, info.status.value, info.reason)

            if index < total and not self._stop.is_set():
                # Delay co the bi cat ngang khi nguoi dung bam Huy
                self._stop.wait(self.DELAY_SECONDS)

        self.finishedAll.emit(checked, skipped, self._stop.is_set())

    # -- giao dien giong CancelToken de provider huy giua chung ---------------

    def is_set(self) -> bool:
        return self._stop.is_set()

    def raise_if_set(self) -> None:
        if self._stop.is_set():
            from desktop_app.providers.base import ProviderCancelled

            raise ProviderCancelled("Đã huỷ kiểm tra")

    def wait_cancel(self, seconds: float) -> bool:
        return self._stop.wait(seconds)


class ModelInstallWorker(QThread):
    """
    Cai model Piper o thread rieng.

    Model Piper nang vai chuc MB nen viec sao chep + xac minh phai chay nen,
    neu khong giao dien se dung hinh trong luc copy.
    """

    statusChanged = Signal(str)
    finishedInstall = Signal(bool, str, str)   # (thanh_cong, voice_key, thong_diep)

    def __init__(self, manager, voice_key: str, onnx_path, config_path, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._voice_key = voice_key
        self._onnx = Path(onnx_path)
        self._config = Path(config_path)

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        try:
            self.statusChanged.emit("Đang kiểm tra cặp file model...")
            from desktop_app.providers.piper_models import pair_stems_match

            ok, reason = pair_stems_match(self._onnx, self._config)
            if not ok:
                self.finishedInstall.emit(False, self._voice_key, reason)
                return

            self.statusChanged.emit("Đang sao chép và xác minh model...")
            ok, message = self._manager.install_from_files(
                self._voice_key, self._onnx, self._config
            )
            self.finishedInstall.emit(bool(ok), self._voice_key, message)
        except Exception as exc:
            self.finishedInstall.emit(
                False,
                self._voice_key,
                f"Lỗi ngoài dự kiến khi cài model: {type(exc).__name__}: {exc}",
            )


class CachedPreviewWorker(QThread):
    """
    Tao audio nghe thu, co CACHE.

    Da co ban cache hop le thi phat luon, KHONG goi provider lai.
    Toan bo viec goi TTS van di qua ProviderRegistry - khong sao chep logic TTS.
    """

    statusChanged = Signal(str)
    ready = Signal(str, str)            # (voice_id, duong_dan_file)
    failed = Signal(str, str)           # (voice_id, thong_bao_tieng_viet)

    def __init__(self, registry, voice, text: str, parent=None):
        super().__init__(parent)
        self._registry = registry
        self._voice = voice
        self._text = text
        self._cancel = CancelToken()

    def request_stop(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # pragma: no cover - can moi truong Qt
        from desktop_app.providers.base import ProviderCancelled, ProviderError
        from desktop_app.providers.preview_cache import (
            cache_path,
            cached_file,
            ensure_cache_dir,
        )

        voice = self._voice
        try:
            hit = cached_file(voice.provider, voice.voice_key, self._text)
            if hit is not None:
                self.ready.emit(voice.id, str(hit))
                return

            ensure_cache_dir()
            dest = cache_path(voice.provider, voice.voice_key, self._text)
            self.statusChanged.emit(f"Đang tạo bản nghe thử cho {voice.label}...")

            self._registry.synthesize(
                text=self._text,
                voice=voice,
                dest=dest,
                cancel=self._cancel,
                rate="1.0",
            )
            self.ready.emit(voice.id, str(dest))

        except ProviderCancelled:
            self.failed.emit(voice.id, "Đã huỷ nghe thử.")
        except ProviderError as exc:
            self.failed.emit(voice.id, exc.message)
        except Exception as exc:
            # Provider hong KHONG duoc lam treo hay sap ung dung
            self.failed.emit(voice.id, f"Lỗi ngoài dự kiến: {type(exc).__name__}: {exc}")
