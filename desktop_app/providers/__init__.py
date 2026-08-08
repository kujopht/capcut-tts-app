"""
He thong TTS nhieu nguon cho Fanfic Audio Studio.

Ba nguon giong:
    capcut  - API CapCut (bao logic da kiem chung, khong doi hanh vi)
    edge    - Microsoft Edge TTS qua goi `edge_tts`
    piper   - Piper chay cuc bo, model .onnx + .onnx.json

Queue, preview va tao audio deu di qua `ProviderRegistry`.
"""

from desktop_app.providers.availability import (
    CIRCUIT_FAILURE_THRESHOLD,
    CIRCUIT_OPEN_SECONDS,
    PROBE_TTL_SECONDS,
    AvailabilityStore,
    CircuitBreaker,
)
from desktop_app.providers.base import (
    PROBE_TEXT,
    PROVIDER_CAPCUT,
    PROVIDER_EDGE,
    PROVIDER_LABELS,
    PROVIDER_PIPER,
    BaseProvider,
    ProbeResult,
    ProviderCancelled,
    ProviderCapabilities,
    ProviderError,
    StatusInfo,
    SynthesisResult,
    TTSProvider,
    Voice,
    VoiceStatus,
    format_checked_at,
    provider_label,
)
from desktop_app.providers.builtin_catalog import (
    BUILTIN_VOICE_IDS,
    edge_builtin_voices,
    piper_builtin_voices,
)
from desktop_app.providers.capcut_provider import CapCutProvider
from desktop_app.providers.edge_provider import EdgeTTSProvider
from desktop_app.providers.piper_models import PiperModel, PiperModelManager, piper_models_dir
from desktop_app.providers.piper_provider import PiperLocalProvider
from desktop_app.providers.registry import ProviderRegistry, build_default_registry

__all__ = [
    "PROBE_TEXT",
    "PROBE_TTL_SECONDS",
    "CIRCUIT_FAILURE_THRESHOLD",
    "CIRCUIT_OPEN_SECONDS",
    "PROVIDER_CAPCUT",
    "PROVIDER_EDGE",
    "PROVIDER_PIPER",
    "PROVIDER_LABELS",
    "BUILTIN_VOICE_IDS",
    "AvailabilityStore",
    "CircuitBreaker",
    "BaseProvider",
    "TTSProvider",
    "Voice",
    "VoiceStatus",
    "StatusInfo",
    "ProbeResult",
    "SynthesisResult",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderCancelled",
    "CapCutProvider",
    "EdgeTTSProvider",
    "PiperLocalProvider",
    "PiperModel",
    "PiperModelManager",
    "ProviderRegistry",
    "build_default_registry",
    "edge_builtin_voices",
    "piper_builtin_voices",
    "piper_models_dir",
    "provider_label",
    "format_checked_at",
    "piper_models_dir",
]
