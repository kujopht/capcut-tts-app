"""
Provider CapCut - BOC logic CapCut hien co, khong thay doi hanh vi.

Toan bo viec goi API van do `desktop_app.tts_service.TtsService` dam nhiem
(timeout, backoff 429, poll 60s, phan loai loi, phat hien shark). Lop nay chi
lam nhiem vu chuyen doi giua model `Voice` thong nhat va `VoiceEntry` cua
CapCut, roi uy quyen xuong duoi.

Package goc `capcut_tts_api` KHONG bi sua doi.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional

from desktop_app.models import ErrorKind, VoiceEntry
from desktop_app.providers.base import (
    PROBE_TEXT,
    PROVIDER_CAPCUT,
    BaseProvider,
    ProbeResult,
    ProviderCancelled,
    ProviderCapabilities,
    ProviderError,
    SynthesisResult,
    Voice,
    VoiceStatus,
)


def voice_from_entry(entry: VoiceEntry) -> Voice:
    """Doi mot ban ghi Voice.json thanh model Voice thong nhat."""
    return Voice(
        provider=PROVIDER_CAPCUT,
        # Voice.json co voice_type bi trung lap, nen khoa phai kem resource_id
        voice_key=f"{entry.voice_type}|{entry.resource_id}",
        engine_voice_id=entry.voice_type,
        display_name=entry.display_name,
        language=entry.language,
        supports_rate=True,
        output_format="mp3",
        installed=True,
        capcut_resource_id=entry.resource_id,
        extra=dict(entry.extra or {}),
    )


def entry_from_voice(voice: Voice) -> VoiceEntry:
    """Doi nguoc lai de goi TtsService (vi TtsService nhan VoiceEntry)."""
    return VoiceEntry(
        voice_type=voice.engine_voice_id,
        display_name=voice.display_name,
        resource_id=voice.capcut_resource_id,
        lang=voice.language,
    )


class CapCutProvider(BaseProvider):
    """Provider cho API CapCut."""

    provider_id = PROVIDER_CAPCUT

    def __init__(self, service: Any = None, catalog: Any = None):
        """
        :param service: TtsService (hoac gia lap trong test). Tao lazy neu None.
        :param catalog: VoiceCatalog da nap Voice.json (hoac gia lap).
        """
        self._service = service
        self._catalog = catalog

    # -- vong doi -------------------------------------------------------------

    @property
    def service(self):
        if self._service is None:
            from desktop_app.tts_service import TtsService

            self._service = TtsService()
        return self._service

    def close(self) -> None:
        if self._service is not None:
            close = getattr(self._service, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

    # -- mo ta ----------------------------------------------------------------

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=PROVIDER_CAPCUT,
            display_name="CapCut",
            supports_rate=True,
            supports_cancel=True,          # CancelToken duoc kiem tra giua cac buoc
            requires_network=True,
            requires_model=False,
            output_format="mp3",
            rate_hint="Hệ số tốc độ, ví dụ 1.0 hoặc 1.25",
        )

    # -- danh sach giong ------------------------------------------------------

    def list_voices(self) -> List[Voice]:
        """Doc Voice.json. Loi doc catalog KHONG duoc lam sap ung dung."""
        catalog = self._catalog
        if catalog is None:
            try:
                from desktop_app.voice_catalog import VoiceCatalog

                catalog = VoiceCatalog()
                catalog.load()
            except Exception:
                return []
            self._catalog = catalog

        entries = getattr(catalog, "voices", None) or []
        return [voice_from_entry(entry) for entry in entries]

    # -- tao audio ------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: Any,
        cancel: Optional[Any] = None,
        rate: str = "1.0",
        progress: Optional[Callable[[str], None]] = None,
    ) -> SynthesisResult:
        self._require_text(text)
        if voice.provider != PROVIDER_CAPCUT:
            raise ProviderError(
                ErrorKind.PROVIDER_UNKNOWN,
                f"Giọng '{voice.label}' không thuộc nguồn CapCut",
            )

        from desktop_app.tts_service import CancelToken, StopRequested, TtsError

        token = cancel if cancel is not None else CancelToken()
        try:
            result = self.service.synthesize(
                text=text,
                voice=entry_from_voice(voice),
                dest=Path(dest),
                cancel=token,
                rate=rate,
                progress=progress,
            )
        except StopRequested as exc:
            raise ProviderCancelled("Đã dừng theo yêu cầu") from exc
        except TtsError as exc:
            # Giu nguyen phan loai loi cua CapCut
            raise ProviderError(exc.kind, exc.message, exc.detail) from exc

        return SynthesisResult(
            file_path=str(result.file_path),
            file_size=int(result.file_size or 0),
            provider=PROVIDER_CAPCUT,
            attempts=int(getattr(result, "attempts", 1) or 1),
            detail={
                "task_id": getattr(result, "task_id", None),
                "token": getattr(result, "token_masked", None),
                "audio_host": getattr(result, "audio_host", None),
            },
        )

    # -- kiem tra giong -------------------------------------------------------

    def probe_voice(self, voice: Voice, cancel: Optional[Any] = None) -> ProbeResult:
        """
        Probe THAT: tao audio cho cau ngan roi xoa file ngay.

        Chi coi la AVAILABLE khi thuc su nhan duoc du lieu audio.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="fas_probe_"))
        dest = tmp_dir / "probe.mp3"
        try:
            result = self.synthesize(
                text=PROBE_TEXT, voice=voice, dest=dest, cancel=cancel, rate="1.0"
            )
            if result.file_size <= 0:
                return ProbeResult(
                    VoiceStatus.UNAVAILABLE, "Máy chủ trả về file audio rỗng"
                )
            return ProbeResult(VoiceStatus.AVAILABLE, "", result.file_size)
        except ProviderCancelled:
            raise
        except ProviderError as exc:
            return ProbeResult(_status_for(exc.kind), exc.message)
        except Exception as exc:  # provider hong khong duoc lam sap app
            return ProbeResult(VoiceStatus.UNAVAILABLE, f"Lỗi ngoài dự kiến: {exc}")
        finally:
            try:
                dest.unlink(missing_ok=True)
                tmp_dir.rmdir()
            except OSError:
                pass


#: Loi tam thoi -> DEGRADED (van dung duoc, chi chap chon);
#: loi ban chat -> UNAVAILABLE.
_DEGRADED_KINDS = {
    ErrorKind.CONNECT_TIMEOUT,
    ErrorKind.READ_TIMEOUT,
    ErrorKind.TIMEOUT,
    ErrorKind.POLL_TIMEOUT,
    ErrorKind.HTTP_429,
    ErrorKind.RATE_LIMIT,
    ErrorKind.NETWORK_ERROR,
}


def _status_for(kind: ErrorKind) -> VoiceStatus:
    if kind in _DEGRADED_KINDS:
        return VoiceStatus.DEGRADED
    if kind in (ErrorKind.MODEL_NOT_INSTALLED, ErrorKind.PROVIDER_NOT_INSTALLED):
        return VoiceStatus.NOT_INSTALLED
    return VoiceStatus.UNAVAILABLE
