"""
Provider Piper local (chay hoan toan tren may, khong can mang).

Tuong thich model cua bo nghimestudio/nghitts: moi giong la mot cap file
`<ten>.onnx` + `<ten>.onnx.json`.

KHONG dung Vue, Vite hay QtWebEngine - chi ONNX thuan qua goi `piper`.

Goi `piper` duoc import LAZY. Chua cai goi, hoac chua tai model, thi ung dung
van chay va giong chi bao trang thai "Chưa tải model".

Piper sinh WAV. De giu nguyen pipeline output hien tai (part_XXX.mp3 roi ghep
bang ffmpeg), WAV duoc chuyen sang MP3 ngay sau khi tao.
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable, List, Optional

from desktop_app.models import ErrorKind
from desktop_app.providers.base import (
    PROBE_TEXT,
    PROVIDER_PIPER,
    BaseProvider,
    ProbeResult,
    ProviderCancelled,
    ProviderCapabilities,
    ProviderError,
    SynthesisResult,
    Voice,
    VoiceStatus,
)
from desktop_app.providers.builtin_catalog import PIPER_PREFERRED_KEY, piper_builtin_voices
from desktop_app.providers.piper_models import PiperModelManager

MIN_AUDIO_BYTES = 512

#: Thong bao khi Windows Smart App Control chan thanh phan native cua Piper
#: (espeakbridge la DLL chua ky). Model VAN hop le va da cai - chi la khong
#: chay duoc tren may dang bat Smart App Control.
APP_CONTROL_BLOCKED_MESSAGE = (
    "Không thể chạy – Windows Smart App Control đã chặn thành phần Piper."
)


def is_blocked_by_app_control(exc: BaseException) -> bool:
    """Loi nay co phai do Smart App Control chan DLL cua Piper khong."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "application control policy" in text
        or ("espeakbridge" in text and "dll load failed" in text)
    )


def rate_to_length_scale(rate: str) -> float:
    """
    Doi he so toc do ("1.25") sang `length_scale` cua Piper.

    Piper dung do DAI: doc nhanh hon = length_scale nho hon, nen lay nghich dao.
    """
    try:
        multiplier = float(str(rate).strip() or "1.0")
    except (TypeError, ValueError):
        return 1.0
    if multiplier <= 0:
        return 1.0
    return 1.0 / multiplier


class PiperLocalProvider(BaseProvider):
    """Provider cho Piper chay cuc bo."""

    provider_id = PROVIDER_PIPER

    def __init__(
        self,
        module: Any = None,
        manager: Optional[PiperModelManager] = None,
        ffmpeg_path: Optional[str] = None,
    ):
        self._module = module
        self._manager = manager or PiperModelManager()
        self._ffmpeg_path = ffmpeg_path
        self._loaded: dict = {}

    # -- goi phu thuoc --------------------------------------------------------

    @property
    def module(self):
        """Import lazy. Tra None neu chua cai goi piper."""
        if self._module is None:
            try:
                import piper  # noqa: WPS433 - co y import lazy

                self._module = piper
            except ImportError:
                return None
        return self._module

    @property
    def manager(self) -> PiperModelManager:
        return self._manager

    @property
    def installed(self) -> bool:
        return self.module is not None

    def close(self) -> None:
        self._loaded.clear()

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=PROVIDER_PIPER,
            display_name="Piper local",
            supports_rate=True,
            supports_cancel=False,   # mot lan synthesize la khoi tinh toan lien mach
            requires_network=False,
            requires_model=True,
            output_format="mp3",
            rate_hint="Quy đổi sang length_scale của Piper (nghịch đảo tốc độ)",
        )

    # -- danh sach giong ------------------------------------------------------

    def list_voices(self) -> List[Voice]:
        """
        Giong built-in LUON co mat, kem trang thai model that tren dia.

        Model nguoi dung tu them vao thu muc models cung duoc liet ke.
        """
        from dataclasses import replace

        voices: List[Voice] = []
        seen: set[str] = set()

        for voice in piper_builtin_voices():
            model = self._manager.find(voice.voice_key)
            voices.append(
                replace(
                    voice,
                    installed=model.installed,
                    model_path=str(model.onnx_path) if model.installed else None,
                )
            )
            seen.add(voice.voice_key)

        # Model nguoi dung tu bo sung
        for name in self._manager.installed_names():
            if name in seen:
                continue
            model = self._manager.find(name)
            seen.add(name)
            voices.append(
                Voice(
                    provider=PROVIDER_PIPER,
                    voice_key=name,
                    engine_voice_id=name,
                    display_name=name,
                    language="",
                    model_path=str(model.onnx_path) if model.installed else None,
                    supports_rate=True,
                    output_format="wav",
                    installed=model.installed,
                )
            )
        return voices

    # -- giong mac dinh -------------------------------------------------------

    def default_voice_key(self) -> Optional[str]:
        """
        Giong Piper mac dinh.

        Ngoc Huyen duoc UU TIEN lam mac dinh ngay khi model cua no da cai hop le;
        neu chua co thi lay giong Piper da cai dau tien theo thu tu catalog.
        Chua cai model nao thi tra None.
        """
        preferred = self._manager.find(PIPER_PREFERRED_KEY)
        if preferred.installed:
            return PIPER_PREFERRED_KEY
        for voice in self.list_voices():
            if voice.installed:
                return voice.voice_key
        return None

    def default_voice(self) -> Optional[Voice]:
        key = self.default_voice_key()
        if key is None:
            return None
        for voice in self.list_voices():
            if voice.voice_key == key:
                return voice
        return None

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
        if voice.provider != PROVIDER_PIPER:
            raise ProviderError(
                ErrorKind.PROVIDER_UNKNOWN,
                f"Giọng '{voice.label}' không thuộc nguồn Piper local",
            )

        module = self.module
        if module is None:
            raise ProviderError(
                ErrorKind.PROVIDER_NOT_INSTALLED,
                "Chưa cài gói piper-tts nên không dùng được giọng Piper local",
                "pip install -r requirements-gui.txt",
            )

        model = self._manager.find(voice.voice_key)
        if not model.installed:
            raise ProviderError(
                ErrorKind.MODEL_NOT_INSTALLED,
                f"Chưa tải model cho giọng '{voice.label}': {model.status_reason}",
                str(self._manager.models_dir),
            )

        self._check_cancel(cancel)
        if progress:
            progress("Đang tổng hợp bằng Piper (chạy trên máy)...")

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="fas_piper_"))
        wav_path = tmp_dir / "piper.wav"

        try:
            self._synthesize_wav(module, model, text, wav_path, rate)
            self._check_cancel(cancel)
            if progress:
                progress("Đang chuyển WAV sang MP3...")
            size = self._wav_to_mp3(wav_path, dest)
        except ProviderCancelled:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            if is_blocked_by_app_control(exc):
                raise ProviderError(
                    ErrorKind.PROVIDER_NOT_INSTALLED, APP_CONTROL_BLOCKED_MESSAGE, str(exc)
                ) from exc
            raise ProviderError(
                ErrorKind.MODEL_INVALID, f"Lỗi khi chạy Piper: {exc}", str(exc)
            ) from exc
        finally:
            try:
                wav_path.unlink(missing_ok=True)
                tmp_dir.rmdir()
            except OSError:
                pass

        return SynthesisResult(
            file_path=str(dest),
            file_size=size,
            provider=PROVIDER_PIPER,
            detail={"model": str(model.onnx_path), "length_scale": rate_to_length_scale(rate)},
        )

    def _load_voice(self, module: Any, model) -> Any:
        """Nap model (cache theo duong dan de khong nap lai moi part)."""
        key = str(model.onnx_path)
        if key in self._loaded:
            return self._loaded[key]

        loader = getattr(module, "PiperVoice", None)
        if loader is None or not hasattr(loader, "load"):
            raise ProviderError(
                ErrorKind.PROVIDER_NOT_INSTALLED,
                "Gói piper đã cài nhưng không có PiperVoice.load — sai phiên bản",
            )
        try:
            loaded = loader.load(str(model.onnx_path), config_path=str(model.config_path))
        except TypeError:
            # Mot so phien ban dung tham so vi tri
            loaded = loader.load(str(model.onnx_path), str(model.config_path))
        self._loaded[key] = loaded
        return loaded

    def _synthesize_wav(self, module: Any, model, text: str, target: Path, rate: str) -> None:
        """
        Goi Piper sinh WAV.

        piper-tts 1.6 dung `synthesize_wav(text, wav_file, syn_config=...)`, trong
        do toc do doc nam trong `SynthesisConfig(length_scale=...)`.

        Cac ban cu hon nhan `length_scale` truc tiep, nen thu lan luot. Neu
        khong khop kieu nao thi bao loi ro rang thay vi doan mo - va tuyet doi
        khong duoc lang le bo qua toc do doc.
        """
        piper_voice = self._load_voice(module, model)
        length_scale = rate_to_length_scale(rate)

        syn_config = None
        config_cls = getattr(module, "SynthesisConfig", None)
        if config_cls is not None:
            try:
                syn_config = config_cls(length_scale=length_scale)
            except TypeError:
                syn_config = None

        method = getattr(piper_voice, "synthesize_wav", None)
        if not callable(method):
            raise ProviderError(
                ErrorKind.PROVIDER_NOT_INSTALLED,
                "Gói piper-tts không có synthesize_wav — phiên bản không tương thích",
            )

        # Dat san dinh dang WAV TRUOC khi tong hop.
        #
        # Neu de trong, mot loi that su ben trong Piper (vi du DLL espeak bi
        # chan) se bi che mat boi `wave.Error: # channels not specified` luc
        # dong file - nguoi dung nhan duoc thong bao vo nghia thay vi nguyen nhan.
        sample_rate = 22050
        config = getattr(piper_voice, "config", None)
        if config is not None:
            sample_rate = int(getattr(config, "sample_rate", sample_rate) or sample_rate)

        wav_file = wave.open(str(target), "wb")
        try:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            if syn_config is not None:
                method(text, wav_file, syn_config=syn_config)
            else:
                # Ban cu: length_scale la tham so truc tiep
                try:
                    method(text, wav_file, length_scale=length_scale)
                except TypeError:
                    method(text, wav_file)
        finally:
            try:
                wav_file.close()
            except Exception:
                pass

    def _wav_to_mp3(self, wav_path: Path, dest: Path) -> int:
        """
        Chuyen WAV sang MP3 de dong bo voi pipeline output hien tai.

        Thieu ffmpeg thi bao loi phan loai ro, khong lam sap ung dung.
        """
        from desktop_app.output_manager import find_ffmpeg

        ffmpeg = find_ffmpeg(self._ffmpeg_path)
        if not ffmpeg:
            raise ProviderError(
                ErrorKind.MERGE_FFMPEG_MISSING,
                "Piper tạo ra WAV nhưng chưa có ffmpeg để chuyển sang MP3",
                "Cài ffmpeg hoặc chọn đường dẫn ffmpeg trong Cài đặt.",
            )

        tmp = dest.with_suffix(dest.suffix + ".part")
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(tmp),
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            tmp.unlink(missing_ok=True)
            raise ProviderError(ErrorKind.TIMEOUT, "ffmpeg quá thời gian chuyển đổi", str(exc)) from exc
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise ProviderError(ErrorKind.MERGE_ERROR, f"Không chạy được ffmpeg: {exc}", str(exc)) from exc

        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            raise ProviderError(
                ErrorKind.MERGE_ERROR,
                "ffmpeg không chuyển được WAV sang MP3",
                (proc.stderr or "")[:600],
            )

        try:
            size = tmp.stat().st_size
        except OSError as exc:
            raise ProviderError(ErrorKind.DISK_ERROR, f"Không đọc được file kết quả: {exc}") from exc

        if size < MIN_AUDIO_BYTES:
            tmp.unlink(missing_ok=True)
            raise ProviderError(
                ErrorKind.AUDIO_INVALID, f"File MP3 chỉ {size} byte — không hợp lệ"
            )

        try:
            tmp.replace(dest)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise ProviderError(ErrorKind.DISK_ERROR, f"Không ghi được file audio: {exc}") from exc
        return size

    # -- kiem tra giong -------------------------------------------------------

    def probe_voice(self, voice: Voice, cancel: Optional[Any] = None) -> ProbeResult:
        """Probe THAT bang cau ngan. Chua co model thi bao NOT_INSTALLED ngay."""
        if self.module is None:
            return ProbeResult(
                VoiceStatus.NOT_INSTALLED,
                "Chưa cài gói piper-tts (pip install -r requirements-gui.txt)",
            )

        model = self._manager.find(voice.voice_key)
        if not model.installed:
            return ProbeResult(VoiceStatus.NOT_INSTALLED, model.status_reason)

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
            if exc.message == APP_CONTROL_BLOCKED_MESSAGE:
                return ProbeResult(VoiceStatus.UNAVAILABLE, APP_CONTROL_BLOCKED_MESSAGE)
            return ProbeResult(_status_for(exc.kind), exc.message)
        except Exception as exc:
            if is_blocked_by_app_control(exc):
                return ProbeResult(VoiceStatus.UNAVAILABLE, APP_CONTROL_BLOCKED_MESSAGE)
            return ProbeResult(VoiceStatus.UNAVAILABLE, f"Lỗi ngoài dự kiến: {exc}")
        finally:
            try:
                dest.unlink(missing_ok=True)
                tmp_dir.rmdir()
            except OSError:
                pass


def _status_for(kind: ErrorKind) -> VoiceStatus:
    if kind in (ErrorKind.MODEL_NOT_INSTALLED, ErrorKind.PROVIDER_NOT_INSTALLED):
        return VoiceStatus.NOT_INSTALLED
    if kind in (ErrorKind.TIMEOUT, ErrorKind.MERGE_FFMPEG_MISSING):
        return VoiceStatus.DEGRADED
    return VoiceStatus.UNAVAILABLE
