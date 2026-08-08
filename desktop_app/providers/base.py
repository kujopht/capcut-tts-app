"""
Nen tang cho he thong TTS nhieu nguon (provider).

Module nay KHONG import PySide6, KHONG goi mang va KHONG import edge_tts/piper,
nen unit test chay duoc hoan toan offline.

Khai niem chinh:
    Voice           - mo ta mot giong doc, thong nhat cho moi provider
    VoiceStatus     - trang thai kha dung cua tung giong
    TTSProvider     - giao dien ma moi provider phai thoa man
    ProviderError   - loi da phan loai, khong lam sap ung dung
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from desktop_app.models import ErrorKind, slugify

# -----------------------------------------------------------------------------
# Dinh danh provider
# -----------------------------------------------------------------------------

PROVIDER_CAPCUT = "capcut"
PROVIDER_EDGE = "edge"
PROVIDER_PIPER = "piper"

#: Ten hien thi tieng Viet cho tung provider
PROVIDER_LABELS: Dict[str, str] = {
    PROVIDER_CAPCUT: "CapCut",
    PROVIDER_EDGE: "Edge TTS",
    PROVIDER_PIPER: "Piper local",
}


def provider_label(provider_id: str) -> str:
    return PROVIDER_LABELS.get(provider_id, provider_id or "—")


# -----------------------------------------------------------------------------
# Trang thai kha dung
# -----------------------------------------------------------------------------


class VoiceStatus(str, Enum):
    """
    Trang thai kha dung cua mot giong.

    LUU Y QUAN TRONG: "co trong catalog" KHONG dong nghia voi "dang kha dung".
    Giong built-in luon xuat hien trong catalog nhung mac dinh la UNKNOWN cho
    toi khi co probe that su.
    """

    UNKNOWN = "unknown"
    CHECKING = "checking"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_INSTALLED = "not_installed"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]

    @property
    def dot(self) -> str:
        """
        Ky tu cham mau. LUON di kem chu (xem `badge`) de nguoi dung khong phai
        dua vao mau sac - yeu cau tiep can duoc.
        """
        return _STATUS_DOTS[self]

    @property
    def badge(self) -> str:
        """Chuoi hien thi trong bang: cham mau + chu."""
        return f"{self.dot} {self.label}"

    @property
    def is_usable(self) -> bool:
        """Co nen cho phep dua vao hang doi khong."""
        return self in (VoiceStatus.AVAILABLE, VoiceStatus.DEGRADED, VoiceStatus.UNKNOWN)


_STATUS_LABELS: Dict[VoiceStatus, str] = {
    VoiceStatus.UNKNOWN: "Chưa kiểm tra",
    VoiceStatus.CHECKING: "Đang kiểm tra",
    VoiceStatus.AVAILABLE: "Khả dụng",
    VoiceStatus.DEGRADED: "Chập chờn",
    VoiceStatus.UNAVAILABLE: "Không khả dụng",
    VoiceStatus.NOT_INSTALLED: "Chưa tải model",
}

_STATUS_DOTS: Dict[VoiceStatus, str] = {
    VoiceStatus.UNKNOWN: "○",
    VoiceStatus.CHECKING: "◐",
    VoiceStatus.AVAILABLE: "●",
    VoiceStatus.DEGRADED: "◍",
    VoiceStatus.UNAVAILABLE: "✕",
    VoiceStatus.NOT_INSTALLED: "⬇",
}


@dataclass(frozen=True)
class StatusInfo:
    """Trang thai cua mot giong tai mot thoi diem."""

    status: VoiceStatus = VoiceStatus.UNKNOWN
    reason: str = ""
    checked_at: Optional[float] = None       # time.time(), None = chua kiem tra

    @property
    def badge(self) -> str:
        return self.status.badge

    def tooltip(self, voice_label: str = "") -> str:
        """Tooltip phai noi ro LY DO, khong chi mau sac."""
        lines: List[str] = []
        if voice_label:
            lines.append(voice_label)
        lines.append(f"Trạng thái: {self.status.label}")
        if self.reason:
            lines.append(f"Lý do: {self.reason}")
        lines.append(f"Kiểm tra lúc: {format_checked_at(self.checked_at)}")
        return "\n".join(lines)


def status_badge(status: VoiceStatus, provider: str = "") -> str:
    """
    Nhan hien thi cua trang thai, co tinh den dac thu tung nguon.

    NOT_INSTALLED co hai nghia khac nhau: Piper la "chua tai model", con Edge
    la "chua cai goi phu thuoc". Hien thi phai noi dung thu nguoi dung can lam.
    """
    if status is VoiceStatus.NOT_INSTALLED and provider == PROVIDER_EDGE:
        return f"{status.dot} Chưa cài gói"
    return status.badge


def format_checked_at(checked_at: Optional[float]) -> str:
    """Doi timestamp thanh chuoi ngan gon tieng Viet."""
    if not checked_at:
        return "Chưa kiểm tra"
    import time as _time

    delta = max(0.0, _time.time() - float(checked_at))
    if delta < 60:
        return "Vừa xong"
    if delta < 3600:
        return f"{int(delta // 60)} phút trước"
    if delta < 86400:
        return f"{int(delta // 3600)} giờ trước"
    return _time.strftime("%Y-%m-%d %H:%M", _time.localtime(float(checked_at)))


# -----------------------------------------------------------------------------
# Loi provider
# -----------------------------------------------------------------------------


class ProviderError(Exception):
    """
    Loi da phan loai tu mot provider.

    Provider hong KHONG duoc lam sap ung dung: moi loi deu phai tro thanh
    ProviderError de hang doi ghi nhan roi chay tiep cac job khac.
    """

    def __init__(self, kind: ErrorKind, message: str, detail: str = ""):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail

    @property
    def is_fatal_for_queue(self) -> bool:
        return bool(getattr(self.kind, "is_fatal_for_queue", False))

    def __str__(self) -> str:  # pragma: no cover - chi de debug
        return self.message


class ProviderCancelled(Exception):
    """Nguoi dung huy giua chung."""


# -----------------------------------------------------------------------------
# Voice thong nhat
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Voice:
    """
    Mot giong doc, dung chung cho MOI provider.

    Edge va Piper KHONG bi ep dung `voice_type` / `resource_id` cua CapCut:
    hai field do chi co gia tri voi provider CapCut va rong voi cac provider khac.

    Trang thai kha dung (status/reason/checked_at) KHONG nam trong day: no la
    du lieu runtime co han su dung, do `AvailabilityStore` quan ly va tra ve
    qua `StatusInfo`. Nho vay catalog van bat bien va cache TTL hoat dong dung.
    """

    provider: str
    voice_key: str                       # duy nhat trong pham vi provider
    engine_voice_id: str                 # gia tri thuc su truyen cho engine
    display_name: str = ""
    description: str = ""                # mo ta ngan hien trong tooltip/bang
    language: str = ""
    gender: str = ""
    model_path: Optional[str] = None     # chi voi provider local (Piper)
    supports_rate: bool = True
    output_format: str = "mp3"
    installed: bool = True               # False = thieu model/goi phu thuoc
    capcut_resource_id: str = ""         # CHI CapCut dung
    builtin: bool = False                # giong built-in luon co trong catalog
    extra: Dict[str, Any] = field(default_factory=dict, compare=False)

    # -- dinh danh ------------------------------------------------------------

    @property
    def id(self) -> str:
        """Khoa on dinh dang `provider:voice_id`."""
        return f"{self.provider}:{self.voice_key}"

    @property
    def uid(self) -> str:
        """Ten cu dung khap noi trong giao dien/favorite - giu de tuong thich."""
        return self.id

    @property
    def label(self) -> str:
        return self.display_name or self.engine_voice_id or self.voice_key

    @property
    def slug(self) -> str:
        return slugify(self.label, fallback="voice")

    @property
    def provider_label(self) -> str:
        return provider_label(self.provider)

    @property
    def is_local(self) -> bool:
        return self.provider == PROVIDER_PIPER

    # -- tuong thich nguoc voi code CapCut hien co ---------------------------

    @property
    def voice_type(self) -> str:
        """CHI co y nghia voi CapCut. Rong voi Edge/Piper."""
        return self.engine_voice_id if self.provider == PROVIDER_CAPCUT else ""

    @property
    def resource_id(self) -> str:
        """CHI co y nghia voi CapCut. Rong voi Edge/Piper."""
        return self.capcut_resource_id if self.provider == PROVIDER_CAPCUT else ""

    # -- tim kiem -------------------------------------------------------------

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        needle = needle.strip().lower()
        haystacks = [
            (self.display_name or "").lower(),
            (self.engine_voice_id or "").lower(),
            (self.voice_key or "").lower(),
            (self.language or "").lower(),
            (self.provider or "").lower(),
            self.provider_label.lower(),
            slugify(self.display_name or ""),
        ]
        if self.provider == PROVIDER_CAPCUT and self.capcut_resource_id:
            haystacks.append(self.capcut_resource_id.lower())
        needle_slug = slugify(needle, fallback="")
        for hay in haystacks:
            if needle and needle in hay:
                return True
            if needle_slug and needle_slug in hay:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "provider": self.provider,
            "display_name": self.display_name,
            "language": self.language,
            "engine_voice_id": self.engine_voice_id,
            "supports_rate": self.supports_rate,
            "output_format": self.output_format,
            "installed": self.installed,
        }
        if self.gender:
            data["gender"] = self.gender
        if self.model_path:
            data["model_path"] = self.model_path
        if self.provider == PROVIDER_CAPCUT:
            data["voice_type"] = self.voice_type
            data["resource_id"] = self.resource_id
        return data


# -----------------------------------------------------------------------------
# Kha nang cua provider
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderCapabilities:
    """Provider lam duoc gi - giao dien dua vao day de bat/tat chuc nang."""

    provider_id: str
    display_name: str
    supports_rate: bool = True
    supports_cancel: bool = False
    requires_network: bool = True
    requires_model: bool = False
    output_format: str = "mp3"
    rate_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "supports_rate": self.supports_rate,
            "supports_cancel": self.supports_cancel,
            "requires_network": self.requires_network,
            "requires_model": self.requires_model,
            "output_format": self.output_format,
        }


@dataclass
class SynthesisResult:
    """Ket qua tao audio cho MOT part."""

    file_path: str
    file_size: int
    provider: str
    attempts: int = 1
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProbeResult:
    """Ket qua kiem tra that su mot giong."""

    status: VoiceStatus
    reason: str = ""
    bytes_produced: int = 0

    @property
    def ok(self) -> bool:
        return self.status == VoiceStatus.AVAILABLE


#: Cau ngan duy nhat duoc phep dung khi probe that.
PROBE_TEXT = "Xin chào."


# -----------------------------------------------------------------------------
# Giao dien provider
# -----------------------------------------------------------------------------


@runtime_checkable
class TTSProvider(Protocol):
    """
    Giao dien ma moi provider TTS phai thoa man.

    Queue, preview va tao audio CHI duoc di qua giao dien nay - khong duoc goi
    thang CapCutClient hay bat ky SDK nao nua.
    """

    provider_id: str

    def get_capabilities(self) -> ProviderCapabilities:
        """Provider nay lam duoc gi."""
        ...

    def list_voices(self) -> List[Voice]:
        """
        Danh sach giong cua provider.

        Phai LUON tra ve giong built-in ke ca khi offline hoac chua cai goi
        phu thuoc - trang thai kha dung duoc bao rieng qua probe.
        """
        ...

    def probe_voice(self, voice: Voice, cancel: Optional[Any] = None) -> ProbeResult:
        """
        Kiem tra that su mot giong bang cau ngan PROBE_TEXT.

        Phai tao ra du lieu audio hop le moi duoc coi la AVAILABLE. File probe
        KHONG duoc giu lai sau khi xong.
        """
        ...

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: "Any",
        cancel: Optional[Any] = None,
        rate: str = "1.0",
        progress: Optional[Callable[[str], None]] = None,
    ) -> SynthesisResult:
        """Tao audio cho MOT part va ghi vao `dest`."""
        ...

    def close(self) -> None:
        """Giai phong tai nguyen (session HTTP, model da nap...)."""
        ...


class BaseProvider:
    """
    Phan dung chung cho cac provider.

    `cancel` dung chung giao dien voi CancelToken cua tts_service (co
    `is_set()` / `raise_if_set()` / `wait()`), nen cac provider deu huy duoc
    neu backend cho phep.
    """

    provider_id: str = ""

    def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover - bi ghi de
        raise NotImplementedError

    def list_voices(self) -> List[Voice]:  # pragma: no cover - bi ghi de
        raise NotImplementedError

    def probe_voice(self, voice: Voice, cancel: Optional[Any] = None) -> ProbeResult:  # pragma: no cover
        raise NotImplementedError

    def synthesize(
        self,
        text: str,
        voice: Voice,
        dest: Any,
        cancel: Optional[Any] = None,
        rate: str = "1.0",
        progress: Optional[Callable[[str], None]] = None,
    ) -> SynthesisResult:  # pragma: no cover - bi ghi de
        raise NotImplementedError

    def close(self) -> None:
        """Mac dinh khong giu tai nguyen nao."""

    # -- tro giup dung chung --------------------------------------------------

    @staticmethod
    def _check_cancel(cancel: Optional[Any]) -> None:
        if cancel is None:
            return
        raise_if_set = getattr(cancel, "raise_if_set", None)
        if callable(raise_if_set):
            try:
                raise_if_set()
                return
            except Exception as exc:  # StopRequested cua tts_service
                raise ProviderCancelled(str(exc) or "Đã dừng theo yêu cầu") from exc
        if getattr(cancel, "is_set", lambda: False)():
            raise ProviderCancelled("Đã dừng theo yêu cầu")

    @staticmethod
    def _require_text(text: str) -> str:
        if not (text or "").strip():
            raise ProviderError(ErrorKind.EMPTY_TEXT, "Phần văn bản này rỗng")
        return text
