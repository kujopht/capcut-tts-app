"""
Provider Edge TTS (Microsoft Edge read-aloud).

Dung API Python cua goi `edge_tts`, KHONG goi subprocess CLI.

Goi `edge_tts` duoc import LAZY: neu may chua cai, ung dung van chay binh
thuong va cac giong Edge chi bao trang thai "Chưa tải model"/khong kha dung.
Hai giong built-in (Hoài My, Nam Minh) LUON co trong catalog, ke ca khi khong
lay duoc danh sach giong online.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from desktop_app.models import ErrorKind
from desktop_app.providers.base import (
    PROBE_TEXT,
    PROVIDER_EDGE,
    BaseProvider,
    ProbeResult,
    ProviderCancelled,
    ProviderCapabilities,
    ProviderError,
    SynthesisResult,
    Voice,
    VoiceStatus,
)
from desktop_app.providers.builtin_catalog import edge_builtin_voices

#: Kich thuoc toi thieu de coi la MP3 that (tranh nhan file rong/0 byte).
MIN_AUDIO_BYTES = 512

#: Dat bien nay = 1 de KHONG goi mang lay danh sach giong online.
#: Test dung no de bo test luon chay offline, ke ca khi da cai edge-tts.
OFFLINE_ENV = "FAS_OFFLINE"

#: Edge co the tra ve rong o lan goi dau. Thu lai toi da ngan nay lan.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 3.0)


def rate_to_edge(rate: str) -> str:
    """
    Doi he so toc do cua ung dung ("1.0", "1.25") sang dinh dang Edge ("+25%").

    Edge nhan chuoi phan tram co dau. Gia tri khong doc duoc thi ve "+0%".
    """
    try:
        multiplier = float(str(rate).strip() or "1.0")
    except (TypeError, ValueError):
        return "+0%"
    if multiplier <= 0:
        return "+0%"
    percent = int(round((multiplier - 1.0) * 100))
    return f"{percent:+d}%"


def _run_async(coro):
    """
    Chay coroutine tu code dong bo (worker chay trong QThread rieng).

    Dung asyncio.run() vi worker khong co san event loop.
    """
    return asyncio.run(coro)


class EdgeTTSProvider(BaseProvider):
    """Provider cho Edge TTS."""

    provider_id = PROVIDER_EDGE

    def __init__(self, module: Any = None):
        """:param module: cho phep test tiem module gia lap thay cho edge_tts."""
        self._module = module
        self._online_voices: Optional[List[Voice]] = None

    # -- goi phu thuoc --------------------------------------------------------

    @property
    def module(self):
        """Import lazy. Tra None neu chua cai - KHONG nem exception."""
        if self._module is None:
            try:
                import edge_tts  # noqa: WPS433 - co y import lazy

                self._module = edge_tts
            except ImportError:
                return None
        return self._module

    @property
    def installed(self) -> bool:
        return self.module is not None

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=PROVIDER_EDGE,
            display_name="Edge TTS",
            supports_rate=True,
            supports_cancel=True,      # huy duoc giua cac chunk stream
            requires_network=True,
            requires_model=False,
            output_format="mp3",
            rate_hint="Quy đổi sang phần trăm của Edge, ví dụ 1.25 → +25%",
        )

    # -- danh sach giong ------------------------------------------------------

    def list_voices(self) -> List[Voice]:
        """
        Giong built-in LUON co mat; giong online (neu lay duoc) duoc bo sung them.

        Khong bao gio nem exception: mat mang chi lam mat phan bo sung.
        """
        voices: List[Voice] = []
        seen: set[str] = set()

        for voice in edge_builtin_voices():
            installed_voice = voice if self.installed else _mark_not_installed(voice)
            voices.append(installed_voice)
            seen.add(voice.voice_key)

        for voice in self._fetch_online_voices():
            if voice.voice_key in seen:
                continue
            seen.add(voice.voice_key)
            voices.append(voice)

        return voices

    def _fetch_online_voices(self) -> List[Voice]:
        """Lay danh sach giong online. That bai thi tra list rong."""
        if self._online_voices is not None:
            return self._online_voices
        if os.environ.get(OFFLINE_ENV):
            # Che do offline: chi giu giong built-in, khong cham vao mang
            self._online_voices = []
            return []
        module = self.module
        if module is None:
            self._online_voices = []
            return []
        try:
            raw = _run_async(module.list_voices())
        except Exception:
            # Mat mang / API doi: KHONG duoc lam hong catalog
            self._online_voices = []
            return []

        result: List[Voice] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            short_name = str(item.get("ShortName") or "").strip()
            if not short_name:
                continue
            result.append(
                Voice(
                    provider=PROVIDER_EDGE,
                    voice_key=short_name,
                    engine_voice_id=short_name,
                    display_name=str(
                        item.get("FriendlyName") or item.get("Name") or short_name
                    ).strip(),
                    language=str(item.get("Locale") or "").strip(),
                    gender=str(item.get("Gender") or "").strip(),
                    supports_rate=True,
                    output_format="mp3",
                    installed=True,
                )
            )
        self._online_voices = result
        return result

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
        if voice.provider != PROVIDER_EDGE:
            raise ProviderError(
                ErrorKind.PROVIDER_UNKNOWN,
                f"Giọng '{voice.label}' không thuộc nguồn Edge TTS",
            )

        module = self.module
        if module is None:
            raise ProviderError(
                ErrorKind.PROVIDER_NOT_INSTALLED,
                "Chưa cài gói edge-tts nên không dùng được giọng Edge",
                "pip install -r requirements-gui.txt",
            )

        self._check_cancel(cancel)
        if progress:
            progress("Đang gọi Edge TTS...")

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")

        # Edge thinh thoang tra ve rong o lan goi dau. Thu lai vai lan truoc khi
        # bao hong - mot cu nhap nhay cua dich vu khong duoc lam hong ca part.
        written = 0
        last_error: Optional[ProviderError] = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                written = _run_async(
                    self._stream_to_file(module, text, voice, tmp, rate, cancel, progress)
                )
            except ProviderCancelled:
                tmp.unlink(missing_ok=True)
                raise
            except ProviderError as exc:
                tmp.unlink(missing_ok=True)
                raise
            except Exception as exc:
                error = _translate_error(exc, voice)
                if error.kind not in RETRYABLE_KINDS or attempt >= MAX_ATTEMPTS:
                    tmp.unlink(missing_ok=True)
                    raise error from exc
                last_error = error
                written = 0
            else:
                if written >= MIN_AUDIO_BYTES:
                    break
                last_error = ProviderError(
                    ErrorKind.AUDIO_INVALID,
                    f"Edge TTS chỉ trả về {written} byte — không phải audio hợp lệ",
                )
                if attempt >= MAX_ATTEMPTS:
                    break

            tmp.unlink(missing_ok=True)
            if progress:
                progress(f"Edge TTS lỗi tạm thời, thử lại lần {attempt + 1}/{MAX_ATTEMPTS}...")
            self._check_cancel(cancel)
            time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            self._check_cancel(cancel)

        if written < MIN_AUDIO_BYTES:
            tmp.unlink(missing_ok=True)
            raise last_error or ProviderError(
                ErrorKind.AUDIO_INVALID,
                f"Edge TTS chỉ trả về {written} byte — không phải audio hợp lệ",
            )

        try:
            tmp.replace(dest)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise ProviderError(
                ErrorKind.DISK_ERROR, f"Không ghi được file audio: {exc}", str(exc)
            ) from exc

        return SynthesisResult(
            file_path=str(dest),
            file_size=written,
            provider=PROVIDER_EDGE,
            detail={"edge_rate": rate_to_edge(rate)},
        )

    async def _stream_to_file(
        self,
        module: Any,
        text: str,
        voice: Voice,
        target: Path,
        rate: str,
        cancel: Optional[Any],
        progress: Optional[Callable[[str], None]],
    ) -> int:
        """Nhan audio theo tung chunk; kiem tra huy giua cac chunk."""
        communicate = module.Communicate(
            text, voice.engine_voice_id, rate=rate_to_edge(rate)
        )
        written = 0
        with open(target, "wb") as fp:
            async for chunk in communicate.stream():
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") != "audio":
                    continue
                data = chunk.get("data") or b""
                if not data:
                    continue
                # Huy giua chung: dung ngay, khong tai het phan con lai
                self._check_cancel(cancel)
                fp.write(data)
                written += len(data)
        return written

    # -- kiem tra giong -------------------------------------------------------

    def probe_voice(self, voice: Voice, cancel: Optional[Any] = None) -> ProbeResult:
        """Probe THAT bang cau ngan; phai tao ra audio hop le moi la AVAILABLE."""
        if self.module is None:
            return ProbeResult(
                VoiceStatus.NOT_INSTALLED,
                "Chưa cài gói edge-tts (pip install -r requirements-gui.txt)",
            )

        tmp_dir = Path(tempfile.mkdtemp(prefix="fas_probe_"))
        dest = tmp_dir / "probe.mp3"
        try:
            result = self.synthesize(
                text=PROBE_TEXT, voice=voice, dest=dest, cancel=cancel, rate="1.0"
            )
            return ProbeResult(VoiceStatus.AVAILABLE, "", result.file_size)
        except ProviderCancelled:
            raise
        except ProviderError as exc:
            return ProbeResult(_status_for(exc.kind), exc.message)
        except Exception as exc:
            return ProbeResult(VoiceStatus.UNAVAILABLE, f"Lỗi ngoài dự kiến: {exc}")
        finally:
            try:
                dest.unlink(missing_ok=True)
                tmp_dir.rmdir()
            except OSError:
                pass


def _mark_not_installed(voice: Voice) -> Voice:
    """Danh dau giong Edge la chua dung duoc vi thieu goi phu thuoc."""
    from dataclasses import replace

    return replace(voice, installed=False)


def _translate_error(exc: Exception, voice: Voice) -> ProviderError:
    """Phan loai loi cua edge_tts thanh ErrorKind cua ung dung."""
    text = str(exc).lower()
    name = type(exc).__name__.lower()

    if isinstance(exc, asyncio.TimeoutError) or "timeout" in text or "timeout" in name:
        return ProviderError(ErrorKind.TIMEOUT, f"Edge TTS quá thời gian chờ: {exc}", str(exc))
    if "429" in text or "too many requests" in text or "rate" in text and "limit" in text:
        return ProviderError(ErrorKind.RATE_LIMIT, "Edge TTS giới hạn tần suất", str(exc))
    if "401" in text or "403" in text or "unauthor" in text or "forbidden" in text:
        return ProviderError(ErrorKind.AUTH_ERROR, "Edge TTS từ chối xác thực", str(exc))
    # "No audio was received" la loi CHAP CHON cua dich vu Edge, KHONG phai
    # giong khong ton tai. Phan loai nham thanh VOICE_NOT_FOUND se khien nguoi
    # dung tuong giong hong vinh vien, trong khi chi can thu lai la duoc.
    if "no audio" in text or "noaudioreceived" in name:
        return ProviderError(
            ErrorKind.BAD_RESPONSE,
            "Edge TTS không trả về audio (lỗi chập chờn của dịch vụ)",
            str(exc),
        )
    if "novoice" in text or "not found" in text or "invalid voice" in text:
        return ProviderError(
            ErrorKind.VOICE_NOT_FOUND,
            f"Edge TTS không có giọng '{voice.engine_voice_id}'",
            str(exc),
        )
    if any(word in text for word in ("connect", "dns", "network", "unreachable", "ssl")):
        return ProviderError(ErrorKind.NETWORK_ERROR, f"Lỗi mạng khi gọi Edge TTS: {exc}", str(exc))
    return ProviderError(ErrorKind.UNEXPECTED, f"Lỗi Edge TTS: {exc}", str(exc))


#: Loi TAM THOI - duoc phep thu lai.
RETRYABLE_KINDS = {
    ErrorKind.BAD_RESPONSE,
    ErrorKind.AUDIO_INVALID,
    ErrorKind.NETWORK_ERROR,
    ErrorKind.TIMEOUT,
    ErrorKind.CONNECT_TIMEOUT,
    ErrorKind.READ_TIMEOUT,
}

_DEGRADED_KINDS = {
    ErrorKind.BAD_RESPONSE,
    ErrorKind.TIMEOUT,
    ErrorKind.CONNECT_TIMEOUT,
    ErrorKind.READ_TIMEOUT,
    ErrorKind.RATE_LIMIT,
    ErrorKind.HTTP_429,
    ErrorKind.NETWORK_ERROR,
}


def _status_for(kind: ErrorKind) -> VoiceStatus:
    if kind in _DEGRADED_KINDS:
        return VoiceStatus.DEGRADED
    if kind in (ErrorKind.PROVIDER_NOT_INSTALLED, ErrorKind.MODEL_NOT_INSTALLED):
        return VoiceStatus.NOT_INSTALLED
    return VoiceStatus.UNAVAILABLE
