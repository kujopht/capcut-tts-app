"""
So dang ky provider - diem dinh tuyen DUY NHAT cua he thong TTS.

Queue, preview va tao audio deu di qua day; khong noi nao duoc goi thang
CapCutClient hay SDK cua Edge/Piper nua.

Nguyen tac quan trong:
- Provider hong KHONG lam sap ung dung va KHONG chan provider khac.
- KHONG BAO GIO tu dong doi sang giong khac. Muon fallback thi nguoi dung
  phai cau hinh ro rang giong thay the.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from desktop_app.models import ErrorKind
from desktop_app.providers.availability import AvailabilityStore, CircuitBreaker
from desktop_app.providers.base import (
    PROVIDER_CAPCUT,
    PROVIDER_EDGE,
    PROVIDER_PIPER,
    ProbeResult,
    ProviderCancelled,
    ProviderCapabilities,
    ProviderError,
    StatusInfo,
    SynthesisResult,
    Voice,
    VoiceStatus,
    provider_label,
    status_badge,
)

#: Thu tu hien thi cac nguon trong giao dien.
PROVIDER_ORDER = (PROVIDER_CAPCUT, PROVIDER_EDGE, PROVIDER_PIPER)


def coerce_voice(voice: Any) -> Voice:
    """
    Chap nhan ca `Voice` thong nhat lan `VoiceEntry` cu cua CapCut.

    Code cu (va cac test bao ve hanh vi CapCut) van truyen VoiceEntry; chuyen
    doi o ranh gioi nay giup khong phai sua rai rac khap noi.
    """
    if isinstance(voice, Voice):
        return voice
    from desktop_app.providers.capcut_provider import voice_from_entry

    if hasattr(voice, "voice_type"):
        return voice_from_entry(voice)
    raise ProviderError(
        ErrorKind.PROVIDER_UNKNOWN, f"Không nhận ra kiểu giọng: {type(voice).__name__}"
    )


class ProviderRegistry:
    """Quan ly cac provider va hop nhat catalog cua chung."""

    def __init__(
        self,
        providers: Optional[Iterable[Any]] = None,
        store: Optional[AvailabilityStore] = None,
        breaker: Optional[CircuitBreaker] = None,
    ):
        self._providers: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._voices: List[Voice] = []
        self._by_id: Dict[str, Voice] = {}
        self._catalog_errors: Dict[str, str] = {}
        self.store = store or AvailabilityStore()
        self.breaker = breaker or CircuitBreaker()
        #: Fallback PHAI do nguoi dung cau hinh ro: {voice_id: voice_id_thay_the}
        self.fallback_map: Dict[str, str] = {}

        for provider in providers or []:
            self.register(provider)

    # -- dang ky --------------------------------------------------------------

    def register(self, provider: Any) -> None:
        provider_id = getattr(provider, "provider_id", "")
        if not provider_id:
            raise ValueError("Provider phải có provider_id")
        with self._lock:
            self._providers[provider_id] = provider

    def get(self, provider_id: str) -> Optional[Any]:
        return self._providers.get(provider_id)

    @property
    def provider_ids(self) -> List[str]:
        known = [p for p in PROVIDER_ORDER if p in self._providers]
        extra = sorted(p for p in self._providers if p not in PROVIDER_ORDER)
        return known + extra

    def capabilities(self) -> Dict[str, ProviderCapabilities]:
        out: Dict[str, ProviderCapabilities] = {}
        for pid, provider in self._providers.items():
            try:
                out[pid] = provider.get_capabilities()
            except Exception:
                continue
        return out

    def close(self) -> None:
        for provider in self._providers.values():
            try:
                provider.close()
            except Exception:
                pass

    # -- catalog hop nhat -----------------------------------------------------

    def refresh_catalog(self) -> List[Voice]:
        """
        Nap lai danh sach giong tu MOI provider.

        Mot provider loi chi lam mat phan cua no; cac provider khac van co mat.
        """
        voices: List[Voice] = []
        errors: Dict[str, str] = {}

        for provider_id in self.provider_ids:
            provider = self._providers[provider_id]
            try:
                items = provider.list_voices() or []
            except Exception as exc:
                errors[provider_id] = f"Không đọc được danh sách giọng: {exc}"
                continue
            for voice in items:
                if isinstance(voice, Voice):
                    voices.append(voice)

        with self._lock:
            self._voices = voices
            self._by_id = {v.id: v for v in voices}
            self._catalog_errors = errors
        return voices

    @property
    def voices(self) -> List[Voice]:
        with self._lock:
            return list(self._voices)

    @property
    def catalog_errors(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._catalog_errors)

    def voice_by_id(self, voice_id: str) -> Optional[Voice]:
        with self._lock:
            return self._by_id.get(voice_id)

    def resolve(self, voice_ids: Iterable[str]) -> List[Voice]:
        """Doi danh sach id thanh Voice, bo qua id khong con ton tai."""
        out: List[Voice] = []
        with self._lock:
            for voice_id in voice_ids:
                voice = self._by_id.get(voice_id)
                if voice is not None:
                    out.append(voice)
        return out

    def filter_voices(
        self,
        query: str = "",
        language: Optional[str] = None,
        provider: Optional[str] = None,
        favorites: Optional[Iterable[str]] = None,
        favorites_only: bool = False,
        recommended_only: bool = False,
        sort_mode: str = "name_asc",
    ) -> List[Voice]:
        """Tim kiem / loc / sap xep tren catalog da hop nhat."""
        from desktop_app.models import slugify
        from desktop_app.providers.recommended import filter_recommended

        result = self.voices

        if recommended_only:
            # Danh sach de xuat co THU TU rieng do nguoi dung chon san,
            # nen tra ve luon, khong ap sort/nhom nguon len tren no.
            result = filter_recommended(result)
            needle = (query or "").strip()
            if needle:
                result = [v for v in result if v.matches(needle)]
            if language:
                lang = language.strip().lower()
                result = [v for v in result if (v.language or "").lower() == lang]
            if provider:
                result = [v for v in result if v.provider == provider]
            return result

        if provider:
            result = [v for v in result if v.provider == provider]
        if language:
            lang = language.strip().lower()
            result = [v for v in result if (v.language or "").lower() == lang]
        if favorites_only:
            favset = set(favorites or [])
            result = [v for v in result if v.id in favset]
        needle = (query or "").strip()
        if needle:
            result = [v for v in result if v.matches(needle)]

        def name_key(voice: Voice) -> str:
            label = voice.label
            return slugify(label, fallback="") or label.lower()

        if sort_mode == "name_desc":
            return sorted(result, key=name_key, reverse=True)
        if sort_mode == "lang_asc":
            return sorted(result, key=lambda v: ((v.language or "").lower(), name_key(v)))
        if sort_mode == "type_asc":
            return sorted(result, key=lambda v: (v.provider, (v.engine_voice_id or "").lower()))
        if sort_mode == "catalog":
            return result
        # Mac dinh: nhom theo nguon (thu tu PROVIDER_ORDER) roi theo ten
        order = {pid: i for i, pid in enumerate(PROVIDER_ORDER)}
        return sorted(result, key=lambda v: (order.get(v.provider, 99), name_key(v)))

    def languages(self) -> List[str]:
        return sorted({v.language for v in self.voices if v.language})

    def providers_present(self) -> List[str]:
        return sorted({v.provider for v in self.voices})

    # -- trang thai -----------------------------------------------------------

    def status_of(self, voice: Voice) -> StatusInfo:
        """
        Trang thai hien tai cua mot giong.

        Model/goi phu thuoc chua co thi bao NOT_INSTALLED ngay ma khong can probe.
        """
        if not voice.installed:
            cached = self.store.get(voice.id)
            if cached.status == VoiceStatus.CHECKING:
                return cached
            reason = (
                "Chưa tải model. Hãy chọn file .onnx và .onnx.json trong Cài đặt."
                if voice.provider == PROVIDER_PIPER
                else "Chưa cài gói phụ thuộc của nguồn này."
            )
            return StatusInfo(VoiceStatus.NOT_INSTALLED, reason, cached.checked_at)
        return self.store.get(voice.id)

    def light_check(self) -> Dict[str, StatusInfo]:
        """
        Kiem tra NHE khi mo ung dung.

        CHI hoi provider xem goi phu thuoc/model co san khong - TUYET DOI khong
        synthesize 127 giong luc khoi dong.
        """
        health: Dict[str, StatusInfo] = {}
        for provider_id in self.provider_ids:
            provider = self._providers[provider_id]
            try:
                caps = provider.get_capabilities()
            except Exception as exc:
                health[provider_id] = StatusInfo(
                    VoiceStatus.UNAVAILABLE, f"Không đọc được thông tin nguồn: {exc}"
                )
                continue

            installed = getattr(provider, "installed", True)
            if not installed:
                health[provider_id] = StatusInfo(
                    VoiceStatus.NOT_INSTALLED,
                    f"Chưa cài gói phụ thuộc của {caps.display_name}",
                )
                continue

            error = self.catalog_errors.get(provider_id)
            if error:
                health[provider_id] = StatusInfo(VoiceStatus.DEGRADED, error)
                continue

            if caps.requires_model:
                ready = sum(1 for v in self.voices if v.provider == provider_id and v.installed)
                if ready == 0:
                    health[provider_id] = StatusInfo(
                        VoiceStatus.NOT_INSTALLED, "Chưa tải model nào"
                    )
                    continue

            if self.breaker.is_open(provider_id):
                health[provider_id] = StatusInfo(
                    VoiceStatus.UNAVAILABLE,
                    f"Tạm ngưng {self.breaker.remaining_seconds(provider_id):.0f}s do lỗi liên tiếp",
                )
                continue

            # Chua probe thi KHONG duoc tuyen bo la kha dung
            health[provider_id] = StatusInfo(VoiceStatus.UNKNOWN, "Chưa kiểm tra giọng nào")
        return health

    def provider_status_line(self) -> str:
        """Chuoi cho thanh trang thai duoi cung: tinh trang tung nguon."""
        health = self.light_check()
        parts: List[str] = []
        for provider_id in self.provider_ids:
            info = health.get(provider_id, StatusInfo())
            # Dung nhan theo tung nguon: Edge thieu GOI, Piper thieu MODEL
            parts.append(
                f"{provider_label(provider_id)}: "
                f"{status_badge(info.status, provider_id)}"
            )
        return " · ".join(parts)

    # -- probe ----------------------------------------------------------------

    def probe(
        self,
        voice: Voice,
        cancel: Optional[Any] = None,
        force: bool = False,
    ) -> StatusInfo:
        """
        Kiem tra that su mot giong.

        Ket qua con hieu luc (< 30 phut) thi dung lai luon, tru khi `force`.
        """
        voice = coerce_voice(voice)
        if not force and self.store.is_fresh(voice.id):
            return self.store.get(voice.id)

        provider = self._providers.get(voice.provider)
        if provider is None:
            return self.store.set(
                voice.id, VoiceStatus.UNAVAILABLE, f"Không có nguồn '{voice.provider}'"
            )

        if self.breaker.is_open(voice.provider):
            remaining = self.breaker.remaining_seconds(voice.provider)
            return self.store.set(
                voice.id,
                VoiceStatus.UNAVAILABLE,
                f"Nguồn đang tạm ngưng {remaining:.0f}s do lỗi liên tiếp",
            )

        self.store.mark_checking(voice.id)
        try:
            result: ProbeResult = provider.probe_voice(voice, cancel)
        except ProviderCancelled:
            self.store.set(voice.id, VoiceStatus.UNKNOWN, "Đã huỷ kiểm tra")
            raise
        except Exception as exc:
            self.breaker.record_failure(voice.provider, str(exc))
            return self.store.set(
                voice.id, VoiceStatus.UNAVAILABLE, f"Lỗi ngoài dự kiến: {exc}"
            )

        if result.status == VoiceStatus.AVAILABLE:
            self.breaker.record_success(voice.provider)
        elif result.status in (VoiceStatus.UNAVAILABLE, VoiceStatus.DEGRADED):
            self.breaker.record_failure(voice.provider, result.reason)

        return self.store.set(voice.id, result.status, result.reason)

    # -- tao audio ------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: Path,
        cancel: Optional[Any] = None,
        rate: str = "1.0",
        progress: Optional[Callable[[str], None]] = None,
    ) -> SynthesisResult:
        """
        Dinh tuyen yeu cau tao audio toi dung provider.

        KHONG tu dong doi giong khac khi loi - chi dung giong thay the neu
        nguoi dung da cau hinh ro trong `fallback_map`.
        """
        voice = coerce_voice(voice)
        provider = self._providers.get(voice.provider)
        if provider is None:
            raise ProviderError(
                ErrorKind.PROVIDER_UNKNOWN,
                f"Không có nguồn giọng '{voice.provider}'",
            )

        if self.breaker.is_open(voice.provider):
            remaining = self.breaker.remaining_seconds(voice.provider)
            raise ProviderError(
                ErrorKind.CIRCUIT_OPEN,
                f"Nguồn {provider_label(voice.provider)} vừa lỗi liên tiếp, "
                f"tạm ngưng thêm {remaining:.0f}s",
            )

        try:
            result = provider.synthesize(
                text=text, voice=voice, dest=dest, cancel=cancel, rate=rate, progress=progress
            )
        except ProviderCancelled:
            raise
        except ProviderError as exc:
            self.breaker.record_failure(voice.provider, exc.message)
            self.store.set(voice.id, _status_for_error(exc.kind), exc.message)
            raise
        except Exception as exc:
            # Provider hong KHONG duoc lam sap ung dung
            self.breaker.record_failure(voice.provider, str(exc))
            raise ProviderError(
                ErrorKind.UNEXPECTED,
                f"Lỗi ngoài dự kiến từ nguồn {provider_label(voice.provider)}: {exc}",
                str(exc),
            ) from exc

        self.breaker.record_success(voice.provider)
        self.store.set(voice.id, VoiceStatus.AVAILABLE, "")
        return result

    # -- fallback do nguoi dung cau hinh --------------------------------------

    def configured_fallback(self, voice: Voice) -> Optional[Voice]:
        """
        Giong thay the DO NGUOI DUNG cau hinh, hoac None.

        Khong co cau hinh thi tra None - he thong tuyet doi khong tu chon giup.
        """
        target_id = self.fallback_map.get(voice.id)
        if not target_id:
            return None
        return self.voice_by_id(target_id)


def _status_for_error(kind: ErrorKind) -> VoiceStatus:
    if kind in (ErrorKind.MODEL_NOT_INSTALLED, ErrorKind.PROVIDER_NOT_INSTALLED):
        return VoiceStatus.NOT_INSTALLED
    if kind in (
        ErrorKind.TIMEOUT,
        ErrorKind.CONNECT_TIMEOUT,
        ErrorKind.READ_TIMEOUT,
        ErrorKind.POLL_TIMEOUT,
        ErrorKind.RATE_LIMIT,
        ErrorKind.HTTP_429,
        ErrorKind.NETWORK_ERROR,
    ):
        return VoiceStatus.DEGRADED
    return VoiceStatus.UNAVAILABLE


def build_default_registry(
    catalog: Any = None,
    service: Any = None,
    ffmpeg_path: Optional[str] = None,
    refresh: bool = True,
) -> ProviderRegistry:
    """
    Tao registry mac dinh gom ca ba nguon.

    `refresh=False` khi chi can dinh tuyen tao audio (worker cua hang doi):
    khoi phai doc lai Voice.json cho tung worker.
    """
    from desktop_app.providers.capcut_provider import CapCutProvider
    from desktop_app.providers.edge_provider import EdgeTTSProvider
    from desktop_app.providers.piper_provider import PiperLocalProvider

    registry = ProviderRegistry(
        providers=[
            CapCutProvider(service=service, catalog=catalog),
            EdgeTTSProvider(),
            PiperLocalProvider(ffmpeg_path=ffmpeg_path),
        ]
    )
    if refresh:
        registry.refresh_catalog()
    return registry
