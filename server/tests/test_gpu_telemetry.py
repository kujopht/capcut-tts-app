import ast
import inspect
import unittest

from server import gpu_telemetry
from server.gpu_telemetry import GPUJobTelemetry, MockGPUTelemetryStore


def _make_image_telemetry(**overrides):
    defaults = dict(
        gpu_type="RTX4090",
        provider="beam",
        model_load_seconds=2.5,
        inference_seconds=8.1,
        wall_seconds=12.0,
        queue_or_provisioning_delay_seconds=1.4,
        image_width=1024,
        image_height=1536,
        output_bytes=524288,
        estimated_cost_usd=0.0023,
        success=True,
    )
    defaults.update(overrides)
    return GPUJobTelemetry(**defaults)


class TestGPUJobTelemetryConstruction(unittest.TestCase):
    def test_constructs_with_image_fields(self):
        telemetry = _make_image_telemetry()
        self.assertEqual(telemetry.gpu_type, "RTX4090")
        self.assertEqual(telemetry.provider, "beam")
        self.assertEqual(telemetry.image_width, 1024)
        self.assertIsNone(telemetry.source_chars)

    def test_constructs_with_translation_fields(self):
        telemetry = GPUJobTelemetry(
            gpu_type="cpu",
            provider="edge",
            source_chars=500,
            output_chars=480,
            success=True,
        )
        self.assertEqual(telemetry.source_chars, 500)
        self.assertIsNone(telemetry.image_width)

    def test_failure_records_error_category(self):
        telemetry = _make_image_telemetry(
            success=False, error_category="transient_5xx")
        self.assertFalse(telemetry.success)
        self.assertEqual(telemetry.error_category, "transient_5xx")

    def test_to_dict_round_trips_all_fields(self):
        telemetry = _make_image_telemetry()
        data = telemetry.to_dict()
        self.assertEqual(data["gpu_type"], "RTX4090")
        self.assertEqual(data["image_width"], 1024)
        rebuilt = GPUJobTelemetry(**data)
        self.assertEqual(rebuilt, telemetry)


class TestMockGPUTelemetryStore(unittest.TestCase):
    def test_record_and_list_recent_returns_newest_first(self):
        store = MockGPUTelemetryStore()
        first = _make_image_telemetry(wall_seconds=1.0)
        second = _make_image_telemetry(wall_seconds=2.0)

        store.record(first)
        store.record(second)
        recent = store.list_recent()

        self.assertEqual(recent, [second, first])

    def test_list_recent_respects_limit(self):
        store = MockGPUTelemetryStore()
        for i in range(5):
            store.record(_make_image_telemetry(wall_seconds=float(i)))

        recent = store.list_recent(limit=2)

        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0].wall_seconds, 4.0)
        self.assertEqual(recent[1].wall_seconds, 3.0)

    def test_clear_empties_the_store(self):
        store = MockGPUTelemetryStore()
        store.record(_make_image_telemetry())
        store.clear()
        self.assertEqual(store.list_recent(), [])


class TestGPUTelemetryModuleIsProviderNeutral(unittest.TestCase):
    """Cung ky thuat AST voi
    test_character_identity.py::TestCharacterIdentityModuleIsProviderNeutral -
    server/gpu_telemetry.py phai la mot cau truc du lieu THUAN, khong goi
    bat ky SDK/thu vien GPU/HTTP/telemetry SaaS cu the nao."""

    _FORBIDDEN_MODULES = {"beam", "torch", "diffusers", "PIL", "httpx"}

    def test_no_provider_specific_top_level_imports(self):
        source = inspect.getsource(gpu_telemetry)
        tree = ast.parse(source)
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_roots.add(node.module.split(".")[0])
        forbidden_found = imported_roots & self._FORBIDDEN_MODULES
        self.assertEqual(
            forbidden_found, set(),
            f"server/gpu_telemetry.py imports provider-specific module(s) "
            f"{forbidden_found} - this module must stay a plain, "
            f"provider-neutral data structure.")


if __name__ == "__main__":
    unittest.main()
