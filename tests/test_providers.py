"""
Test cho he thong TTS nhieu nguon.

TOAN BO chay OFFLINE: khong goi API CapCut, khong goi Edge TTS, khong tai
model Piper that. Moi provider deu duoc gia lap.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from desktop_app.models import ErrorKind, InputItem, JobState, PartState
from desktop_app.providers.availability import (
    CIRCUIT_FAILURE_THRESHOLD,
    AvailabilityStore,
    CircuitBreaker,
)
from desktop_app.providers.base import (
    PROBE_TEXT,
    PROVIDER_CAPCUT,
    PROVIDER_EDGE,
    PROVIDER_PIPER,
    BaseProvider,
    ProbeResult,
    ProviderCapabilities,
    ProviderError,
    SynthesisResult,
    TTSProvider,
    Voice,
    VoiceStatus,
)
from desktop_app.providers.builtin_catalog import (
    BUILTIN_VOICE_IDS,
    edge_builtin_voices,
    piper_builtin_voices,
)
from desktop_app.providers.piper_models import (
    MODELS_DIR_ENV,
    PiperModelManager,
    pair_stems_match,
    validate_model_pair,
)
from desktop_app.providers.piper_provider import PiperLocalProvider, rate_to_length_scale
from desktop_app.providers.edge_provider import EdgeTTSProvider, rate_to_edge
from desktop_app.providers.registry import ProviderRegistry, coerce_voice

# -----------------------------------------------------------------------------
# Provider gia lap
# -----------------------------------------------------------------------------


def make_voice(provider: str = PROVIDER_CAPCUT, key: str = "v1", **kwargs) -> Voice:
    return Voice(
        provider=provider,
        voice_key=key,
        engine_voice_id=kwargs.pop("engine_voice_id", key),
        display_name=kwargs.pop("display_name", f"Giọng {key}"),
        language=kwargs.pop("language", "vi-VN"),
        **kwargs,
    )


class FakeProvider(BaseProvider):
    """Provider gia lap: dieu khien duoc ket qua tra ve."""

    def __init__(self, provider_id: str, voices=None, fail_with: ErrorKind = None,
                 probe_status: VoiceStatus = VoiceStatus.AVAILABLE, installed: bool = True):
        self.provider_id = provider_id
        self._voices = list(voices or [])
        self.fail_with = fail_with
        self.probe_status = probe_status
        self.installed = installed
        self.synth_calls = 0
        self.probe_calls = 0
        self.closed = False

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id, display_name=self.provider_id.title()
        )

    def list_voices(self):
        return list(self._voices)

    def probe_voice(self, voice, cancel=None) -> ProbeResult:
        self.probe_calls += 1
        if self.fail_with is not None:
            return ProbeResult(VoiceStatus.UNAVAILABLE, f"lỗi giả lập {self.fail_with.value}")
        return ProbeResult(self.probe_status, "", 2048)

    def synthesize(self, text, voice, dest, cancel=None, rate="1.0", progress=None):
        self.synth_calls += 1
        if self.fail_with is not None:
            raise ProviderError(self.fail_with, f"lỗi giả lập {self.fail_with.value}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 4096)
        return SynthesisResult(
            file_path=str(dest), file_size=4096, provider=self.provider_id
        )

    def close(self):
        self.closed = True


class BrokenProvider(BaseProvider):
    """Provider nem exception THO - phai duoc bao boc, khong lam sap app."""

    provider_id = PROVIDER_CAPCUT

    def get_capabilities(self):
        return ProviderCapabilities(provider_id=self.provider_id, display_name="Hỏng")

    def list_voices(self):
        raise RuntimeError("catalog hỏng")

    def probe_voice(self, voice, cancel=None):
        raise RuntimeError("probe nổ")

    def synthesize(self, text, voice, dest, cancel=None, rate="1.0", progress=None):
        raise RuntimeError("synthesize nổ")


# -----------------------------------------------------------------------------
# 1. Provider registry
# -----------------------------------------------------------------------------


class TestProviderRegistry(unittest.TestCase):
    def test_register_and_lookup(self):
        provider = FakeProvider(PROVIDER_EDGE)
        registry = ProviderRegistry(providers=[provider])
        self.assertIs(registry.get(PROVIDER_EDGE), provider)
        self.assertIn(PROVIDER_EDGE, registry.provider_ids)

    def test_provider_must_have_id(self):
        class NoId(BaseProvider):
            provider_id = ""

        with self.assertRaises(ValueError):
            ProviderRegistry(providers=[NoId()])

    def test_fake_provider_satisfies_protocol(self):
        self.assertIsInstance(FakeProvider(PROVIDER_EDGE), TTSProvider)

    def test_close_closes_every_provider(self):
        a, b = FakeProvider(PROVIDER_EDGE), FakeProvider(PROVIDER_PIPER)
        ProviderRegistry(providers=[a, b]).close()
        self.assertTrue(a.closed and b.closed)

    def test_synthesize_routes_to_correct_provider(self):
        capcut = FakeProvider(PROVIDER_CAPCUT)
        edge = FakeProvider(PROVIDER_EDGE)
        registry = ProviderRegistry(providers=[capcut, edge])
        voice = make_voice(PROVIDER_EDGE, "hoaimy")
        with tempfile.TemporaryDirectory() as tmp:
            registry.synthesize("xin chào", voice, Path(tmp) / "a.mp3")
        self.assertEqual(edge.synth_calls, 1)
        self.assertEqual(capcut.synth_calls, 0, "Không được gọi nhầm nguồn khác")

    def test_unknown_provider_raises_classified_error(self):
        registry = ProviderRegistry(providers=[FakeProvider(PROVIDER_EDGE)])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProviderError) as ctx:
                registry.synthesize("x", make_voice("khong_ton_tai"), Path(tmp) / "a.mp3")
        self.assertEqual(ctx.exception.kind, ErrorKind.PROVIDER_UNKNOWN)

    def test_coerce_accepts_legacy_voice_entry(self):
        from desktop_app.models import VoiceEntry

        voice = coerce_voice(VoiceEntry(voice_type="BV421", resource_id="r1", lang="vi-VN"))
        self.assertEqual(voice.provider, PROVIDER_CAPCUT)
        self.assertEqual(voice.engine_voice_id, "BV421")
        self.assertEqual(voice.id, "capcut:BV421|r1")


# -----------------------------------------------------------------------------
# 2. Hop nhat catalog
# -----------------------------------------------------------------------------


class TestCatalogMerge(unittest.TestCase):
    def test_merges_voices_from_all_providers(self):
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_CAPCUT, [make_voice(PROVIDER_CAPCUT, "c1")]),
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")]),
            FakeProvider(PROVIDER_PIPER, [make_voice(PROVIDER_PIPER, "p1")]),
        ])
        registry.refresh_catalog()
        self.assertEqual(len(registry.voices), 3)
        self.assertEqual(set(registry.providers_present()),
                         {PROVIDER_CAPCUT, PROVIDER_EDGE, PROVIDER_PIPER})

    def test_ids_are_stable_and_namespaced(self):
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "vi-VN-HoaiMyNeural")])
        ])
        registry.refresh_catalog()
        self.assertIsNotNone(registry.voice_by_id("edge:vi-VN-HoaiMyNeural"))

    def test_broken_provider_does_not_break_catalog(self):
        """CapCut hong: cac nguon khac VAN co trong catalog."""
        registry = ProviderRegistry(providers=[
            BrokenProvider(),
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")]),
        ])
        registry.refresh_catalog()
        self.assertEqual(len(registry.voices), 1)
        self.assertIn(PROVIDER_CAPCUT, registry.catalog_errors)

    def test_resolve_skips_unknown_ids(self):
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")])
        ])
        registry.refresh_catalog()
        self.assertEqual(len(registry.resolve(["edge:e1", "edge:khong_co"])), 1)


# -----------------------------------------------------------------------------
# 3. Trang thai tung voice
# -----------------------------------------------------------------------------


class TestVoiceStatus(unittest.TestCase):
    def test_default_status_is_unknown_not_available(self):
        """Co trong catalog KHONG dong nghia voi dang kha dung."""
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")])
        ])
        registry.refresh_catalog()
        info = registry.status_of(registry.voice_by_id("edge:e1"))
        self.assertEqual(info.status, VoiceStatus.UNKNOWN)
        self.assertIsNone(info.checked_at)

    def test_probe_sets_available_and_timestamp(self):
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")])
        ])
        registry.refresh_catalog()
        info = registry.probe(registry.voice_by_id("edge:e1"))
        self.assertEqual(info.status, VoiceStatus.AVAILABLE)
        self.assertIsNotNone(info.checked_at)

    def test_each_voice_has_independent_status(self):
        good = make_voice(PROVIDER_EDGE, "good")
        bad = make_voice(PROVIDER_PIPER, "bad")
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_EDGE, [good]),
            FakeProvider(PROVIDER_PIPER, [bad], fail_with=ErrorKind.MODEL_INVALID),
        ])
        registry.refresh_catalog()
        registry.probe(good)
        registry.probe(bad)
        self.assertEqual(registry.status_of(good).status, VoiceStatus.AVAILABLE)
        self.assertEqual(registry.status_of(bad).status, VoiceStatus.UNAVAILABLE)

    def test_status_has_reason_and_tooltip(self):
        bad = make_voice(PROVIDER_EDGE, "bad")
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_EDGE, [bad], fail_with=ErrorKind.NETWORK_ERROR)
        ])
        registry.refresh_catalog()
        info = registry.probe(bad)
        self.assertTrue(info.reason, "Trạng thái lỗi phải có lý do")
        tooltip = info.tooltip(bad.label)
        self.assertIn("Lý do", tooltip)
        self.assertIn("Kiểm tra lúc", tooltip)

    def test_badge_has_text_not_only_colour(self):
        for status in VoiceStatus:
            badge = status.badge
            self.assertTrue(len(badge) > 2, f"{status} phải có chữ kèm chấm màu")
            self.assertIn(status.label, badge)

    def test_broken_provider_probe_does_not_crash(self):
        registry = ProviderRegistry(providers=[BrokenProvider()])
        info = registry.probe(make_voice(PROVIDER_CAPCUT, "c1"))
        self.assertEqual(info.status, VoiceStatus.UNAVAILABLE)


# -----------------------------------------------------------------------------
# 4. Cache TTL
# -----------------------------------------------------------------------------


class TestAvailabilityCache(unittest.TestCase):
    def test_result_is_fresh_within_ttl(self):
        now = [1000.0]
        store = AvailabilityStore(ttl_seconds=1800, clock=lambda: now[0])
        store.set("edge:e1", VoiceStatus.AVAILABLE)
        now[0] += 1799
        self.assertTrue(store.is_fresh("edge:e1"))

    def test_result_expires_after_ttl(self):
        now = [1000.0]
        store = AvailabilityStore(ttl_seconds=1800, clock=lambda: now[0])
        store.set("edge:e1", VoiceStatus.AVAILABLE)
        now[0] += 1801
        self.assertFalse(store.is_fresh("edge:e1"))
        self.assertEqual(store.get("edge:e1").status, VoiceStatus.UNKNOWN)

    def test_probe_not_repeated_while_fresh(self):
        provider = FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")])
        registry = ProviderRegistry(providers=[provider])
        registry.refresh_catalog()
        voice = registry.voice_by_id("edge:e1")
        registry.probe(voice)
        registry.probe(voice)
        registry.probe(voice)
        self.assertEqual(provider.probe_calls, 1, "Probe còn hiệu lực không được chạy lại")

    def test_force_bypasses_cache(self):
        provider = FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")])
        registry = ProviderRegistry(providers=[provider])
        registry.refresh_catalog()
        voice = registry.voice_by_id("edge:e1")
        registry.probe(voice)
        registry.probe(voice, force=True)
        self.assertEqual(provider.probe_calls, 2)

    def test_checking_state_is_not_treated_as_result(self):
        store = AvailabilityStore()
        store.mark_checking("edge:e1")
        self.assertFalse(store.is_fresh("edge:e1"))

    def test_stale_ids_lists_only_unchecked(self):
        store = AvailabilityStore()
        store.set("edge:a", VoiceStatus.AVAILABLE)
        self.assertEqual(store.stale_ids(["edge:a", "edge:b"]), ["edge:b"])


# -----------------------------------------------------------------------------
# 5. Circuit breaker
# -----------------------------------------------------------------------------


class TestCircuitBreaker(unittest.TestCase):
    def test_opens_after_three_consecutive_failures(self):
        breaker = CircuitBreaker()
        for _ in range(CIRCUIT_FAILURE_THRESHOLD - 1):
            breaker.record_failure(PROVIDER_CAPCUT)
            self.assertFalse(breaker.is_open(PROVIDER_CAPCUT))
        breaker.record_failure(PROVIDER_CAPCUT)
        self.assertTrue(breaker.is_open(PROVIDER_CAPCUT))

    def test_success_resets_consecutive_counter(self):
        breaker = CircuitBreaker()
        breaker.record_failure(PROVIDER_CAPCUT)
        breaker.record_failure(PROVIDER_CAPCUT)
        breaker.record_success(PROVIDER_CAPCUT)
        breaker.record_failure(PROVIDER_CAPCUT)
        self.assertFalse(breaker.is_open(PROVIDER_CAPCUT), "Phải là lỗi LIÊN TIẾP")

    def test_closes_again_after_60_seconds(self):
        now = [0.0]
        breaker = CircuitBreaker(open_seconds=60.0, clock=lambda: now[0])
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            breaker.record_failure(PROVIDER_CAPCUT)
        self.assertTrue(breaker.is_open(PROVIDER_CAPCUT))
        now[0] += 59
        self.assertTrue(breaker.is_open(PROVIDER_CAPCUT))
        now[0] += 2
        self.assertFalse(breaker.is_open(PROVIDER_CAPCUT))

    def test_one_provider_does_not_affect_another(self):
        breaker = CircuitBreaker()
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            breaker.record_failure(PROVIDER_CAPCUT)
        self.assertTrue(breaker.is_open(PROVIDER_CAPCUT))
        self.assertFalse(breaker.is_open(PROVIDER_EDGE))
        self.assertFalse(breaker.is_open(PROVIDER_PIPER))

    def test_registry_refuses_synthesize_while_open(self):
        provider = FakeProvider(PROVIDER_CAPCUT, fail_with=ErrorKind.NETWORK_ERROR)
        registry = ProviderRegistry(providers=[provider])
        voice = make_voice(PROVIDER_CAPCUT, "c1")
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(CIRCUIT_FAILURE_THRESHOLD):
                with self.assertRaises(ProviderError):
                    registry.synthesize("x", voice, Path(tmp) / "a.mp3")
            calls_before = provider.synth_calls
            with self.assertRaises(ProviderError) as ctx:
                registry.synthesize("x", voice, Path(tmp) / "b.mp3")
        self.assertEqual(ctx.exception.kind, ErrorKind.CIRCUIT_OPEN)
        self.assertEqual(provider.synth_calls, calls_before,
                         "Mạch mở thì không được gọi provider nữa")


# -----------------------------------------------------------------------------
# 6. CapCut hong nhung Edge/Piper van chay
# -----------------------------------------------------------------------------


class TestProviderIsolation(unittest.TestCase):
    def test_edge_still_works_when_capcut_is_broken(self):
        capcut = FakeProvider(PROVIDER_CAPCUT, fail_with=ErrorKind.HTTP_403)
        edge = FakeProvider(PROVIDER_EDGE)
        registry = ProviderRegistry(providers=[capcut, edge])

        capcut_voice = make_voice(PROVIDER_CAPCUT, "c1")
        edge_voice = make_voice(PROVIDER_EDGE, "e1")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProviderError):
                registry.synthesize("x", capcut_voice, Path(tmp) / "a.mp3")
            result = registry.synthesize("x", edge_voice, Path(tmp) / "b.mp3")
            self.assertEqual(result.provider, PROVIDER_EDGE)
            self.assertTrue(Path(result.file_path).is_file())

    def test_open_circuit_on_capcut_leaves_edge_usable(self):
        capcut = FakeProvider(PROVIDER_CAPCUT, fail_with=ErrorKind.NETWORK_ERROR)
        edge = FakeProvider(PROVIDER_EDGE)
        registry = ProviderRegistry(providers=[capcut, edge])
        capcut_voice = make_voice(PROVIDER_CAPCUT, "c1")

        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(CIRCUIT_FAILURE_THRESHOLD):
                with self.assertRaises(ProviderError):
                    registry.synthesize("x", capcut_voice, Path(tmp) / "a.mp3")
            self.assertTrue(registry.breaker.is_open(PROVIDER_CAPCUT))
            registry.synthesize("x", make_voice(PROVIDER_EDGE, "e1"), Path(tmp) / "c.mp3")
        self.assertEqual(edge.synth_calls, 1)

    def test_raw_exception_is_wrapped_not_propagated(self):
        registry = ProviderRegistry(providers=[BrokenProvider()])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProviderError) as ctx:
                registry.synthesize("x", make_voice(PROVIDER_CAPCUT, "c1"), Path(tmp) / "a.mp3")
        self.assertEqual(ctx.exception.kind, ErrorKind.UNEXPECTED)


# -----------------------------------------------------------------------------
# 7. Model Piper chua tai
# -----------------------------------------------------------------------------


class TestPiperModels(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get(MODELS_DIR_ENV)
        os.environ[MODELS_DIR_ENV] = self._tmp.name
        self.manager = PiperModelManager()

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(MODELS_DIR_ENV, None)
        else:
            os.environ[MODELS_DIR_ENV] = self._prev
        self._tmp.cleanup()

    def test_missing_model_reports_not_downloaded(self):
        model = self.manager.find("calmwoman3688")
        self.assertFalse(model.installed)
        self.assertEqual(model.status_reason, "Chưa tải model")

    def test_models_dir_is_not_program_files(self):
        from desktop_app.providers.piper_models import user_data_dir

        self.assertNotIn("Program Files", str(user_data_dir()))

    def test_onnx_without_config_is_not_installed(self):
        (Path(self._tmp.name) / "calmwoman3688.onnx").write_bytes(b"\x08" * (2 * 1024 * 1024))
        model = self.manager.find("calmwoman3688")
        self.assertFalse(model.installed)
        self.assertIn("Thiếu file cấu hình", model.status_reason)

    def test_tiny_onnx_is_rejected(self):
        base = Path(self._tmp.name)
        (base / "x.onnx").write_bytes(b"\x08" * 10)
        (base / "x.onnx.json").write_text('{"sample_rate": 22050}', encoding="utf-8")
        ok, reason = validate_model_pair(base / "x.onnx", base / "x.onnx.json")
        self.assertFalse(ok)
        self.assertIn("quá nhỏ", reason)

    def test_html_error_page_is_rejected(self):
        base = Path(self._tmp.name)
        (base / "x.onnx").write_bytes(b"<!DOCTYPE html>" + b" " * (2 * 1024 * 1024))
        (base / "x.onnx.json").write_text('{"sample_rate": 22050}', encoding="utf-8")
        ok, reason = validate_model_pair(base / "x.onnx", base / "x.onnx.json")
        self.assertFalse(ok)
        self.assertIn("không phải ONNX", reason)

    def test_config_without_sample_rate_is_rejected(self):
        base = Path(self._tmp.name)
        (base / "x.onnx").write_bytes(b"\x08" * (2 * 1024 * 1024))
        (base / "x.onnx.json").write_text('{"gì đó": 1}', encoding="utf-8")
        ok, reason = validate_model_pair(base / "x.onnx", base / "x.onnx.json")
        self.assertFalse(ok)
        self.assertIn("sample_rate", reason)

    def test_valid_pair_installs_and_is_found(self):
        src = Path(self._tmp.name) / "src"
        src.mkdir()
        onnx = src / "any.onnx"
        config = src / "any.onnx.json"
        onnx.write_bytes(b"\x08" * (2 * 1024 * 1024))
        config.write_text('{"sample_rate": 22050}', encoding="utf-8")

        ok, message = self.manager.install_from_files("calmwoman3688", onnx, config)
        self.assertTrue(ok, message)
        self.assertTrue(self.manager.find("calmwoman3688").installed)
        self.assertIn("calmwoman3688", self.manager.installed_names())

    def test_no_partial_files_left_behind(self):
        base = Path(self._tmp.name)
        leftovers = list(base.glob("*.part"))
        self.assertEqual(leftovers, [])

    def test_piper_voice_reports_not_installed_status(self):
        provider = PiperLocalProvider(module=object(), manager=self.manager)
        voices = provider.list_voices()
        target = next(v for v in voices if v.voice_key == "calmwoman3688")
        self.assertFalse(target.installed)
        self.assertIsNone(target.model_path)

    def test_probe_without_model_returns_not_installed(self):
        provider = PiperLocalProvider(module=object(), manager=self.manager)
        voice = next(v for v in provider.list_voices() if v.voice_key == "deepman3909")
        result = provider.probe_voice(voice)
        self.assertEqual(result.status, VoiceStatus.NOT_INSTALLED)

    def test_synthesize_without_model_raises_classified_error(self):
        provider = PiperLocalProvider(module=object(), manager=self.manager)
        voice = next(v for v in provider.list_voices() if v.voice_key == "deepman3909")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProviderError) as ctx:
                provider.synthesize("xin chào", voice, Path(tmp) / "a.mp3")
        self.assertEqual(ctx.exception.kind, ErrorKind.MODEL_NOT_INSTALLED)

    def test_missing_piper_package_reports_not_installed(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        provider._module = None
        # Gia lap goi chua cai: module property tra None vi import that bai
        result = provider.probe_voice(make_voice(PROVIDER_PIPER, "calmwoman3688"))
        self.assertIn(result.status, (VoiceStatus.NOT_INSTALLED, VoiceStatus.UNAVAILABLE))

    def test_rate_maps_to_inverse_length_scale(self):
        self.assertAlmostEqual(rate_to_length_scale("1.0"), 1.0)
        self.assertAlmostEqual(rate_to_length_scale("2.0"), 0.5)
        self.assertAlmostEqual(rate_to_length_scale("bậy"), 1.0)


# -----------------------------------------------------------------------------
# 8. Edge: giong built-in luon co trong catalog
# -----------------------------------------------------------------------------


class _EdgeWithoutPackage(EdgeTTSProvider):
    """Gia lap may CHUA cai edge-tts, ke ca khi may that da cai."""

    @property
    def module(self):
        return None


class TestEdgeBuiltinCatalog(unittest.TestCase):
    def test_hoai_my_and_nam_minh_are_builtin(self):
        keys = {v.voice_key for v in edge_builtin_voices()}
        self.assertIn("vi-VN-HoaiMyNeural", keys)
        self.assertIn("vi-VN-NamMinhNeural", keys)

    def test_display_names_are_vietnamese(self):
        names = {v.voice_key: v.display_name for v in edge_builtin_voices()}
        self.assertEqual(names["vi-VN-HoaiMyNeural"], "Hoài My")
        self.assertEqual(names["vi-VN-NamMinhNeural"], "Nam Minh")

    def test_builtin_present_even_without_edge_tts_package(self):
        """Chua cai edge_tts: giong VAN phai co trong catalog."""
        provider = _EdgeWithoutPackage()
        voices = provider.list_voices()
        keys = {v.voice_key for v in voices}
        self.assertIn("vi-VN-HoaiMyNeural", keys)
        self.assertIn("vi-VN-NamMinhNeural", keys)

    def test_builtin_present_when_online_list_fails(self):
        class Boom:
            def list_voices(self):
                raise RuntimeError("mất mạng")

        provider = EdgeTTSProvider(module=Boom())
        keys = {v.voice_key for v in provider.list_voices()}
        self.assertIn("vi-VN-HoaiMyNeural", keys)

    def test_in_catalog_does_not_mean_available(self):
        provider = _EdgeWithoutPackage()
        registry = ProviderRegistry(providers=[provider])
        registry.refresh_catalog()
        voice = registry.voice_by_id("edge:vi-VN-HoaiMyNeural")
        self.assertIsNotNone(voice)
        self.assertNotEqual(registry.status_of(voice).status, VoiceStatus.AVAILABLE)

    def test_all_builtin_ids_present_in_full_registry(self):
        registry = ProviderRegistry(providers=[EdgeTTSProvider(module=None),
                                               PiperLocalProvider(module=None)])
        registry.refresh_catalog()
        for voice_id in BUILTIN_VOICE_IDS:
            self.assertIsNotNone(registry.voice_by_id(voice_id), voice_id)

    def test_rate_converts_to_edge_percent(self):
        self.assertEqual(rate_to_edge("1.0"), "+0%")
        self.assertEqual(rate_to_edge("1.25"), "+25%")
        self.assertEqual(rate_to_edge("0.8"), "-20%")
        self.assertEqual(rate_to_edge("bậy"), "+0%")

    def test_edge_voice_does_not_expose_capcut_fields(self):
        for voice in edge_builtin_voices():
            self.assertEqual(voice.voice_type, "", "Edge không được dùng voice_type")
            self.assertEqual(voice.resource_id, "", "Edge không được dùng resource_id")

    def test_piper_voice_does_not_expose_capcut_fields(self):
        for voice in piper_builtin_voices():
            self.assertEqual(voice.voice_type, "")
            self.assertEqual(voice.resource_id, "")


# -----------------------------------------------------------------------------
# 9. Retry tiep tuc tu part con thieu
# -----------------------------------------------------------------------------


class TestRetryResumesMissingParts(unittest.TestCase):
    def test_retry_only_reruns_unfinished_parts(self):
        from desktop_app.queue_manager import build_jobs
        from desktop_app.text_importer import make_text_item

        voice = make_voice(PROVIDER_EDGE, "e1")
        long_text = "Câu văn thử nghiệm để chia phần. " * 40
        jobs = build_jobs([make_text_item(long_text, name="a")], [voice], 200)
        job = jobs[0]
        self.assertGreaterEqual(job.total_parts, 2)

        job.parts[0].state = PartState.SUCCESS
        job.parts[0].file_path = "part_001.mp3"
        job.parts[1].state = PartState.FAILED

        pending = job.pending_parts()
        self.assertTrue(all(p.state != PartState.SUCCESS for p in pending))
        self.assertNotIn(job.parts[0], pending)

        job.reset_for_retry()
        self.assertEqual(job.parts[0].state, PartState.SUCCESS,
                         "Part đã xong phải được GIỮ NGUYÊN")
        self.assertEqual(job.parts[1].state, PartState.PENDING)
        self.assertEqual(job.state, JobState.PENDING)

    def test_completed_part_file_is_preserved(self):
        from desktop_app.queue_manager import build_jobs
        from desktop_app.text_importer import make_text_item

        long_text = "Câu văn thử nghiệm để chia phần. " * 40
        jobs = build_jobs([make_text_item(long_text, name="b")],
                          [make_voice(PROVIDER_EDGE, "e1")], 200)
        job = jobs[0]
        job.parts[0].state = PartState.SUCCESS
        job.parts[0].file_path = "/tmp/part_001.mp3"
        job.parts[0].file_size = 4096
        job.reset_for_retry()
        self.assertEqual(job.parts[0].file_path, "/tmp/part_001.mp3")
        self.assertEqual(job.parts[0].file_size, 4096)


# -----------------------------------------------------------------------------
# 10. Khong tu dong fallback
# -----------------------------------------------------------------------------


class TestNoAutomaticFallback(unittest.TestCase):
    def test_failure_does_not_switch_to_another_voice(self):
        capcut = FakeProvider(PROVIDER_CAPCUT, fail_with=ErrorKind.VOICE_NOT_FOUND)
        edge = FakeProvider(PROVIDER_EDGE)
        registry = ProviderRegistry(providers=[capcut, edge])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProviderError):
                registry.synthesize("x", make_voice(PROVIDER_CAPCUT, "c1"), Path(tmp) / "a.mp3")
        self.assertEqual(edge.synth_calls, 0, "Không được tự ý chuyển sang nguồn khác")

    def test_no_fallback_configured_returns_none(self):
        registry = ProviderRegistry(providers=[FakeProvider(PROVIDER_CAPCUT)])
        self.assertIsNone(registry.configured_fallback(make_voice(PROVIDER_CAPCUT, "c1")))

    def test_fallback_used_only_when_user_configures_it(self):
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_CAPCUT, [make_voice(PROVIDER_CAPCUT, "c1")]),
            FakeProvider(PROVIDER_EDGE, [make_voice(PROVIDER_EDGE, "e1")]),
        ])
        registry.refresh_catalog()
        source = registry.voice_by_id("capcut:c1")
        self.assertIsNone(registry.configured_fallback(source))

        registry.fallback_map["capcut:c1"] = "edge:e1"
        target = registry.configured_fallback(source)
        self.assertIsNotNone(target)
        self.assertEqual(target.id, "edge:e1")


# -----------------------------------------------------------------------------
# Probe dung dung cau ngan va khong de lai file
# -----------------------------------------------------------------------------


class TestNgocHuyenVoice(unittest.TestCase):
    """Ngoc Huyen: giong Piper uu tien, bat buoc co trong catalog mac dinh."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get(MODELS_DIR_ENV)
        os.environ[MODELS_DIR_ENV] = self._tmp.name
        self.manager = PiperModelManager()

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(MODELS_DIR_ENV, None)
        else:
            os.environ[MODELS_DIR_ENV] = self._prev
        self._tmp.cleanup()

    def _make_model_files(self, stem: str = "bat_ky_ten_gi"):
        """Ten file CO Y dat khac ten hien thi - khong duoc suy doan tu ten demo."""
        src = Path(self._tmp.name) / "tai_ve"
        src.mkdir(exist_ok=True)
        onnx = src / f"{stem}.onnx"
        config = src / f"{stem}.onnx.json"
        onnx.write_bytes(b"\x08" * (2 * 1024 * 1024))
        config.write_text('{"sample_rate": 22050}', encoding="utf-8")
        return onnx, config

    def test_always_in_default_catalog(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        keys = [v.voice_key for v in provider.list_voices()]
        self.assertIn("ngochuyen", keys)

    def test_display_name_and_description(self):
        """
        Ten hien thi doi theo bang ten chinh thuc cua bo NghiTTS.

        Luu y HOAN DOI: `ngochuyen` truoc mang ten "Ngọc Huyền (mới)"; hau to
        do nay thuoc ve model `ngochuyennew`. `voice_key` cua ca hai khong doi
        nen model va tep `.onnx` van la nhung thu cu.
        """
        provider = PiperLocalProvider(module=None, manager=self.manager)
        voice = next(v for v in provider.list_voices() if v.voice_key == "ngochuyen")
        self.assertEqual(voice.display_name, "Ngọc Huyền")
        self.assertEqual(voice.description, "Giọng nữ review phim — NghiTTS")

    def test_ngochuyennew_giu_hau_to_moi(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        voice = next(v for v in provider.list_voices()
                     if v.voice_key == "ngochuyennew")
        self.assertEqual(voice.display_name, "Ngọc Huyền (Mới)")

    def test_catalog_order_is_ngochuyen_first(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        keys = [v.voice_key for v in provider.list_voices()]
        self.assertEqual(keys[:3], ["ngochuyen", "calmwoman3688", "deepman3909"])

    def test_appears_before_model_downloaded(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        voice = next(v for v in provider.list_voices() if v.voice_key == "ngochuyen")
        self.assertFalse(voice.installed)
        self.assertIsNone(voice.model_path)

    def test_status_is_not_installed_when_files_missing(self):
        registry = ProviderRegistry(providers=[
            PiperLocalProvider(module=None, manager=self.manager)
        ])
        registry.refresh_catalog()
        voice = registry.voice_by_id("piper:ngochuyen")
        self.assertIsNotNone(voice)
        info = registry.status_of(voice)
        self.assertEqual(info.status, VoiceStatus.NOT_INSTALLED)
        self.assertEqual(VoiceStatus.NOT_INSTALLED.label, "Chưa tải model")

    def test_onnx_filename_is_not_guessed_from_display_name(self):
        """Ten file model do nguoi dung chon, KHONG suy ra tu ten hien thi."""
        onnx, config = self._make_model_files("giong_nu_review_v3")
        ok, message = self.manager.bind("ngochuyen", onnx, config)
        self.assertTrue(ok, message)

        bound = self.manager.binding_for("ngochuyen")
        self.assertIsNotNone(bound)
        self.assertEqual(bound[0].name, "giong_nu_review_v3.onnx")
        self.assertTrue(self.manager.find("ngochuyen").installed)

    def test_becomes_default_piper_voice_after_install(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        self.assertIsNone(provider.default_voice_key(), "Chưa cài thì chưa có mặc định")

        onnx, config = self._make_model_files("bat_ky")
        ok, _ = self.manager.bind("ngochuyen", onnx, config)
        self.assertTrue(ok)

        self.assertEqual(provider.default_voice_key(), "ngochuyen")
        default = provider.default_voice()
        self.assertIsNotNone(default)
        self.assertEqual(default.display_name, "Ngọc Huyền")

    def test_preferred_over_other_installed_models(self):
        """Da cai calmwoman truoc, cai them Ngoc Huyen thi Ngoc Huyen thanh mac dinh."""
        provider = PiperLocalProvider(module=None, manager=self.manager)
        onnx, config = self._make_model_files("calm_src")
        self.manager.install_from_files("calmwoman3688", onnx, config)
        self.assertEqual(provider.default_voice_key(), "calmwoman3688")

        onnx2, config2 = self._make_model_files("nh_src")
        self.manager.bind("ngochuyen", onnx2, config2)
        self.assertEqual(provider.default_voice_key(), "ngochuyen")

    def test_installed_voice_exposes_model_path(self):
        onnx, config = self._make_model_files("nh")
        self.manager.bind("ngochuyen", onnx, config)
        provider = PiperLocalProvider(module=None, manager=self.manager)
        voice = next(v for v in provider.list_voices() if v.voice_key == "ngochuyen")
        self.assertTrue(voice.installed)
        self.assertIsNotNone(voice.model_path)

    def test_installed_but_unproven_is_not_declared_available(self):
        """
        Du hai file da co, van CHUA duoc coi la kha dung:
        con phai nap duoc ONNX va tao ra audio thu hop le.
        """
        onnx, config = self._make_model_files("nh")
        self.manager.bind("ngochuyen", onnx, config)
        registry = ProviderRegistry(providers=[
            PiperLocalProvider(module=None, manager=self.manager)
        ])
        registry.refresh_catalog()
        voice = registry.voice_by_id("piper:ngochuyen")
        self.assertTrue(voice.installed)
        self.assertNotEqual(registry.status_of(voice).status, VoiceStatus.AVAILABLE)

    def test_supports_queue_like_other_voices(self):
        from desktop_app.queue_manager import build_jobs
        from desktop_app.text_importer import make_text_item

        onnx, config = self._make_model_files("nh")
        self.manager.bind("ngochuyen", onnx, config)
        provider = PiperLocalProvider(module=None, manager=self.manager)
        voice = next(v for v in provider.list_voices() if v.voice_key == "ngochuyen")

        jobs = build_jobs([make_text_item("Xin chào các bạn.", name="a")], [voice], 2000)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].voice.id, "piper:ngochuyen")

    def test_mismatched_pair_is_rejected(self):
        src = Path(self._tmp.name) / "xau"
        src.mkdir()
        onnx = src / "a.onnx"
        config = src / "a.onnx.json"
        onnx.write_bytes(b"\x08" * (2 * 1024 * 1024))
        config.write_text("khong phai json", encoding="utf-8")
        ok, reason = self.manager.bind("ngochuyen", onnx, config)
        self.assertFalse(ok)
        self.assertIn("JSON", reason)
        self.assertIsNone(self.manager.binding_for("ngochuyen"))


class TestProbeHygiene(unittest.TestCase):
    def test_probe_text_is_the_short_sentence(self):
        self.assertEqual(PROBE_TEXT, "Xin chào.")

    def test_probe_leaves_no_file_behind(self):
        recorded = {}

        class RecordingProvider(FakeProvider):
            def synthesize(self, text, voice, dest, cancel=None, rate="1.0", progress=None):
                recorded["text"] = text
                recorded["dest"] = Path(dest)
                return super().synthesize(text, voice, dest, cancel, rate, progress)

        from desktop_app.providers.capcut_provider import CapCutProvider

        provider = RecordingProvider(PROVIDER_CAPCUT)
        # dung probe_voice cua CapCutProvider (co don dep file tam)
        real = CapCutProvider.probe_voice.__get__(provider, RecordingProvider)
        result = real(make_voice(PROVIDER_CAPCUT, "c1"))

        self.assertEqual(result.status, VoiceStatus.AVAILABLE)
        self.assertEqual(recorded["text"], PROBE_TEXT)
        self.assertFalse(recorded["dest"].exists(), "File probe phải bị xoá sau khi xong")


class TestModelPairCorrespondence(unittest.TestCase):
    """Hai file phai thuoc CUNG mot model - khong duoc ghep bua."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get(MODELS_DIR_ENV)
        os.environ[MODELS_DIR_ENV] = self._tmp.name
        self.manager = PiperModelManager()
        self.base = Path(self._tmp.name)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(MODELS_DIR_ENV, None)
        else:
            os.environ[MODELS_DIR_ENV] = self._prev
        self._tmp.cleanup()

    def _pair(self, stem):
        onnx = self.base / f"{stem}.onnx"
        config = self.base / f"{stem}.onnx.json"
        onnx.write_bytes(b"\x08" * (2 * 1024 * 1024))
        config.write_text('{"sample_rate": 22050}', encoding="utf-8")
        return onnx, config

    def test_matching_stems_accepted(self):
        onnx, config = self._pair("vi_VN-abc-medium")
        ok, reason = pair_stems_match(onnx, config)
        self.assertTrue(ok, reason)

    def test_mismatched_stems_rejected(self):
        onnx, _ = self._pair("model_a")
        _, config = self._pair("model_b")
        ok, reason = pair_stems_match(onnx, config)
        self.assertFalse(ok)
        self.assertIn("kh\u00f4ng c\u00f9ng m\u1ed9t model", reason)

    def test_install_success_uses_given_voice_key(self):
        """Ten file nguon KHAC ten giong - phai cai duoi dung voice_key."""
        onnx, config = self._pair("ten_file_hoan_toan_khac")
        ok, message = self.manager.install_from_files("ngochuyen", onnx, config)
        self.assertTrue(ok, message)
        self.assertIn("ngochuyen", message)
        self.assertTrue(self.manager.find("ngochuyen").installed)
        self.assertTrue((self.base / "ngochuyen.onnx").is_file())
        self.assertTrue((self.base / "ngochuyen.onnx.json").is_file())

    def test_failed_install_leaves_no_partial_files(self):
        bad_onnx = self.base / "hong.onnx"
        bad_onnx.write_bytes(b"\x08" * 10)          # qua nho -> bi tu choi
        config = self.base / "hong.onnx.json"
        config.write_text('{"sample_rate": 22050}', encoding="utf-8")

        ok, _ = self.manager.install_from_files("ngochuyen", bad_onnx, config)
        self.assertFalse(ok)
        self.assertEqual(list(self.base.glob("*.part")), [],
                         "Cài lỗi không được để lại file tạm")
        self.assertFalse(self.manager.find("ngochuyen").installed)

    def test_status_changes_after_install(self):
        provider = PiperLocalProvider(module=None, manager=self.manager)
        registry = ProviderRegistry(providers=[provider])
        registry.refresh_catalog()

        voice = registry.voice_by_id("piper:ngochuyen")
        self.assertEqual(registry.status_of(voice).status, VoiceStatus.NOT_INSTALLED)

        onnx, config = self._pair("nguon")
        ok, _ = self.manager.install_from_files("ngochuyen", onnx, config)
        self.assertTrue(ok)

        registry.refresh_catalog()
        voice = registry.voice_by_id("piper:ngochuyen")
        self.assertTrue(voice.installed)
        # Da cai nhung CHUA probe -> phai la UNKNOWN, khong duoc tu nhan AVAILABLE
        self.assertEqual(registry.status_of(voice).status, VoiceStatus.UNKNOWN)


class TestRecommendedFanficVoices(unittest.TestCase):
    """Muc "De xuat Audio Fanfic" - danh sach tinh, doi chieu bang MA GIONG."""

    def setUp(self):
        from desktop_app.providers.recommended import RECOMMENDED_CODES

        self.codes = RECOMMENDED_CODES

    def _catalog(self):
        """Catalog gia lap chua DU cac giong de xuat + vai giong nhieu."""
        from desktop_app.providers.recommended import RECOMMENDED_FANFIC_VOICES

        voices = []
        for provider, code, name in RECOMMENDED_FANFIC_VOICES:
            voices.append(
                Voice(
                    provider=provider,
                    voice_key=f"{code}|r1" if provider == PROVIDER_CAPCUT else code,
                    engine_voice_id=code,
                    display_name=name,
                    language="vi-VN",
                    installed=(provider != PROVIDER_PIPER),
                )
            )
        # Giong nhieu, khong duoc lot vao danh sach de xuat
        voices.append(make_voice(PROVIDER_CAPCUT, "khac"))
        voices.append(make_voice(PROVIDER_EDGE, "khac-edge"))
        return voices

    def test_section_exists_with_label(self):
        from desktop_app.providers.recommended import RECOMMENDED_COUNT, RECOMMENDED_LABEL

        # Bay -> tam: them `piper:ngochuyennew` vao muc de xuat.
        self.assertEqual(RECOMMENDED_COUNT, 8)
        self.assertEqual(RECOMMENDED_LABEL, "\u0110\u1ec1 xu\u1ea5t Audio Fanfic (8)")

    def test_exactly_eight_codes_in_order(self):
        expected = [
            (PROVIDER_CAPCUT, "BV074_streaming"),
            (PROVIDER_CAPCUT, "BV074_streaming_dsp"),
            (PROVIDER_CAPCUT, "vi_female_huong"),
            (PROVIDER_CAPCUT, "BV562_streaming"),
            (PROVIDER_CAPCUT, "BV421_vivn_streaming"),
            (PROVIDER_EDGE, "vi-VN-HoaiMyNeural"),
            # Hai giong NghiTTS, LIEN NHAU va dung thu tu nay:
            # "Ngọc Huyền" truoc, "Ngọc Huyền (Mới)" ngay sau.
            (PROVIDER_PIPER, "ngochuyen"),
            (PROVIDER_PIPER, "ngochuyennew"),
        ]
        self.assertEqual(list(self.codes), expected)

    def test_no_duplicate_codes(self):
        self.assertEqual(len(self.codes), len(set(self.codes)))

    def test_filter_returns_exactly_eight_in_order(self):
        from desktop_app.providers.recommended import filter_recommended

        result = filter_recommended(self._catalog())
        self.assertEqual(len(result), len(self.codes))
        self.assertEqual([(v.provider, v.engine_voice_id) for v in result], list(self.codes))

    def test_duplicate_catalog_entries_do_not_duplicate_result(self):
        from desktop_app.providers.recommended import filter_recommended

        catalog = self._catalog()
        catalog += self._catalog()          # nhan doi toan bo catalog
        result = filter_recommended(catalog)
        self.assertEqual(len(result), len(self.codes))

    def test_unavailable_voices_still_listed(self):
        """Giong chua kiem tra / chua kha dung VAN phai hien."""
        from desktop_app.providers.recommended import filter_recommended

        registry = ProviderRegistry(
            providers=[FakeProvider(PROVIDER_CAPCUT, self._catalog())]
        )
        registry.refresh_catalog()
        result = filter_recommended(registry.voices)
        for voice in result:
            self.assertNotEqual(registry.status_of(voice).status, VoiceStatus.AVAILABLE)
        self.assertEqual(len(result), len(self.codes))

    def test_giong_NghiTTS_listed_even_without_model(self):
        from desktop_app.providers.recommended import filter_recommended

        result = filter_recommended(self._catalog())
        piper = [v for v in result if v.provider == PROVIDER_PIPER]
        # HAI giong NghiTTS, dung thu tu: "Ngọc Huyền" roi "Ngọc Huyền (Mới)".
        self.assertEqual([v.engine_voice_id for v in piper],
                         ["ngochuyen", "ngochuyennew"])
        for v in piper:
            self.assertFalse(v.installed)

    def test_matching_is_by_code_not_display_name(self):
        """Doi ten hien thi KHONG duoc lam mat giong khoi danh sach."""
        from dataclasses import replace

        from desktop_app.providers.recommended import filter_recommended

        catalog = [replace(v, display_name="TEN DA DOI") for v in self._catalog()]
        result = filter_recommended(catalog)
        self.assertEqual(len(result), len(self.codes))

    def test_registry_filter_recommended_only(self):
        registry = ProviderRegistry(
            providers=[FakeProvider(PROVIDER_CAPCUT, self._catalog())]
        )
        registry.refresh_catalog()
        result = registry.filter_voices(recommended_only=True)
        self.assertEqual(len(result), len(self.codes))
        self.assertEqual([(v.provider, v.engine_voice_id) for v in result], list(self.codes))

    def test_selected_voice_keeps_provider_and_key(self):
        from desktop_app.providers.recommended import filter_recommended

        result = filter_recommended(self._catalog())
        hoai_my = next(v for v in result if v.engine_voice_id == "vi-VN-HoaiMyNeural")
        self.assertEqual(hoai_my.provider, PROVIDER_EDGE)
        self.assertEqual(hoai_my.id, "edge:vi-VN-HoaiMyNeural")

        co_gai = next(v for v in result if v.engine_voice_id == "BV074_streaming")
        self.assertEqual(co_gai.provider, PROVIDER_CAPCUT)
        self.assertEqual(co_gai.voice_type, "BV074_streaming")

    def test_refresh_does_not_lose_recommended_list(self):
        registry = ProviderRegistry(
            providers=[FakeProvider(PROVIDER_CAPCUT, self._catalog())]
        )
        registry.refresh_catalog()
        self.assertEqual(len(registry.filter_voices(recommended_only=True)),
                         len(self.codes))
        registry.refresh_catalog()
        self.assertEqual(len(registry.filter_voices(recommended_only=True)),
                         len(self.codes))

    def test_real_catalog_has_every_recommended_code(self):
        """Moi ma de xuat phai TON TAI that trong catalog cua ung dung."""
        from desktop_app.providers.capcut_provider import CapCutProvider
        from desktop_app.providers.edge_provider import EdgeTTSProvider
        from desktop_app.providers.piper_provider import PiperLocalProvider
        from desktop_app.providers.recommended import missing_codes

        registry = ProviderRegistry(providers=[
            CapCutProvider(),
            _EdgeWithoutPackage(),
            PiperLocalProvider(module=None),
        ])
        registry.refresh_catalog()
        self.assertEqual(missing_codes(registry.voices), [],
                         "Có mã giọng đề xuất không tồn tại trong catalog")


class TestPreviewCache(unittest.TestCase):
    """Cache audio nghe thu: cung giong + cung cau thi khong goi provider lai."""

    def setUp(self):
        from desktop_app.providers.preview_cache import CACHE_DIR_ENV

        self._tmp = tempfile.TemporaryDirectory()
        self._prev = os.environ.get(CACHE_DIR_ENV)
        os.environ[CACHE_DIR_ENV] = self._tmp.name
        self._env = CACHE_DIR_ENV

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(self._env, None)
        else:
            os.environ[self._env] = self._prev
        self._tmp.cleanup()

    def test_key_depends_on_provider_voice_and_text(self):
        from desktop_app.providers.preview_cache import cache_key

        a = cache_key("edge", "v1", "xin chào")
        self.assertNotEqual(a, cache_key("capcut", "v1", "xin chào"))
        self.assertNotEqual(a, cache_key("edge", "v2", "xin chào"))
        self.assertNotEqual(a, cache_key("edge", "v1", "câu khác"))
        self.assertEqual(a, cache_key("edge", "v1", "xin chào"))

    def test_missing_cache_returns_none(self):
        from desktop_app.providers.preview_cache import cached_file

        self.assertIsNone(cached_file("edge", "v1", "x"))

    def test_valid_cache_is_reused(self):
        from desktop_app.providers.preview_cache import cache_path, cached_file

        path = cache_path("edge", "v1", "x")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00" * 4096)
        self.assertEqual(cached_file("edge", "v1", "x"), path)

    def test_tiny_cache_file_is_ignored(self):
        from desktop_app.providers.preview_cache import cache_path, cached_file

        path = cache_path("edge", "v1", "x")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00" * 10)
        self.assertIsNone(cached_file("edge", "v1", "x"))

    def test_cache_dir_is_not_output_folder(self):
        from desktop_app.providers.preview_cache import preview_cache_dir

        text = str(preview_cache_dir()).lower()
        self.assertNotIn("documents", text)
        self.assertNotIn("outputs", text)

    def test_prune_removes_only_old_files(self):
        from desktop_app.providers.preview_cache import cache_path, prune_old

        old = cache_path("edge", "old", "x")
        new = cache_path("edge", "new", "x")
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b"\x00" * 4096)
        new.write_bytes(b"\x00" * 4096)
        os.utime(old, (0, 0))
        removed = prune_old(max_age_days=1)
        self.assertEqual(removed, 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())


class TestSmartAppControlBlocked(unittest.TestCase):
    """Smart App Control chan DLL cua Piper: bao dung, khong treo, khong fallback."""

    def test_detects_app_control_block(self):
        from desktop_app.providers.piper_provider import is_blocked_by_app_control

        exc = ImportError(
            "DLL load failed while importing espeakbridge: "
            "An Application Control policy has blocked this file."
        )
        self.assertTrue(is_blocked_by_app_control(exc))
        self.assertFalse(is_blocked_by_app_control(ValueError("loi khac")))

    def test_message_is_the_required_vietnamese_text(self):
        from desktop_app.providers.piper_provider import APP_CONTROL_BLOCKED_MESSAGE

        self.assertEqual(
            APP_CONTROL_BLOCKED_MESSAGE,
            "Không thể chạy – Windows Smart App Control "
            "đã chặn thành phần Piper.",
        )

    def test_probe_reports_blocked_reason(self):
        from desktop_app.providers.piper_provider import (
            APP_CONTROL_BLOCKED_MESSAGE,
            PiperLocalProvider,
        )

        class BlockedModule:
            SynthesisConfig = None

            class PiperVoice:
                @staticmethod
                def load(*a, **k):
                    raise ImportError(
                        "DLL load failed while importing espeakbridge: "
                        "An Application Control policy has blocked this file."
                    )

        tmp = tempfile.mkdtemp()
        prev = os.environ.get(MODELS_DIR_ENV)
        os.environ[MODELS_DIR_ENV] = tmp
        try:
            manager = PiperModelManager()
            base = Path(tmp)
            onnx, config = base / "src.onnx", base / "src.onnx.json"
            onnx.write_bytes(b"" * (2 * 1024 * 1024))
            config.write_text('{"sample_rate": 22050}', encoding="utf-8")
            manager.install_from_files("ngochuyen", onnx, config)

            provider = PiperLocalProvider(module=BlockedModule(), manager=manager)
            voice = next(v for v in provider.list_voices() if v.voice_key == "ngochuyen")
            self.assertTrue(voice.installed, "Model phải vẫn ở trạng thái đã cài")

            result = provider.probe_voice(voice)
            self.assertEqual(result.status, VoiceStatus.UNAVAILABLE)
            self.assertEqual(result.reason, APP_CONTROL_BLOCKED_MESSAGE)
        finally:
            if prev is None:
                os.environ.pop(MODELS_DIR_ENV, None)
            else:
                os.environ[MODELS_DIR_ENV] = prev

    def test_blocked_piper_does_not_trigger_fallback(self):
        """Piper bi chan KHONG duoc lam he thong tu chon giong khac."""
        registry = ProviderRegistry(providers=[
            FakeProvider(PROVIDER_PIPER, fail_with=ErrorKind.PROVIDER_NOT_INSTALLED),
            FakeProvider(PROVIDER_EDGE),
        ])
        piper_voice = make_voice(PROVIDER_PIPER, "ngochuyen")
        self.assertIsNone(registry.configured_fallback(piper_voice))


if __name__ == "__main__":
    unittest.main(verbosity=2)
