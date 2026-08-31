import ast
import inspect
import unittest

from server import gpu_job_domain
from server.gpu_job_domain import (
    MAX_JOB_ATTEMPTS,
    CostMetadata,
    GPUJob,
    GPUJobStatus,
    GPUJobStatusResponse,
    GPUJobType,
    classify_error_class,
    compute_input_hash,
)


class TestGPUJobConstruction(unittest.TestCase):
    def test_minimal_construction_defaults(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="illustrious-xl")
        self.assertEqual(job.status, GPUJobStatus.QUEUED)
        self.assertTrue(job.job_id.startswith("gpu_"))
        self.assertEqual(job.attempts, 0)
        self.assertIsNone(job.output_ref)
        self.assertIsNone(job.provider_job_ref)
        self.assertEqual(job.usage_metadata, {})
        self.assertEqual(job.cost_metadata, {})
        self.assertIsNotNone(job.created_at)
        self.assertIsNone(job.started_at)
        self.assertIsNone(job.completed_at)

    def test_all_job_type_values_exist(self):
        # Item cua mission: TTS/VIDEO/LORA_TRAINING phai TON TAI (future-ready)
        # du khong co logic xu ly nao.
        names = {member.name for member in GPUJobType}
        self.assertEqual(
            names,
            {"IMAGE_GENERATION", "TRANSLATION", "TTS", "VIDEO", "LORA_TRAINING"})

    def test_all_status_values_exist(self):
        names = {member.name for member in GPUJobStatus}
        self.assertEqual(
            names,
            {"QUEUED", "PROVISIONING", "RUNNING", "COMPLETED", "FAILED",
             "CANCELLED"})

    def test_to_dict_shape(self):
        job = GPUJob(job_type=GPUJobType.TRANSLATION, provider="beam",
                     model="hy-mt2", input_hash="abc123")
        data = job.to_dict()
        self.assertEqual(data["job_type"], "translation")
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["input_hash"], "abc123")
        self.assertIn("job_id", data)


class TestIsTerminal(unittest.TestCase):
    def _job(self, status: GPUJobStatus) -> GPUJob:
        return GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                      model="m", status=status)

    def test_queued_not_terminal(self):
        self.assertFalse(self._job(GPUJobStatus.QUEUED).is_terminal())

    def test_provisioning_not_terminal(self):
        self.assertFalse(self._job(GPUJobStatus.PROVISIONING).is_terminal())

    def test_running_not_terminal(self):
        self.assertFalse(self._job(GPUJobStatus.RUNNING).is_terminal())

    def test_completed_is_terminal(self):
        self.assertTrue(self._job(GPUJobStatus.COMPLETED).is_terminal())

    def test_failed_is_terminal(self):
        self.assertTrue(self._job(GPUJobStatus.FAILED).is_terminal())

    def test_cancelled_is_terminal(self):
        self.assertTrue(self._job(GPUJobStatus.CANCELLED).is_terminal())


class TestIsRetryable(unittest.TestCase):
    def test_not_retryable_when_not_failed(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING)
        self.assertFalse(job.is_retryable())

    def test_retryable_when_failed_with_transient_error_and_attempts_left(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.FAILED,
                     error_class="timeout", attempts=1)
        self.assertTrue(job.is_retryable())

    def test_not_retryable_when_attempts_exhausted(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.FAILED,
                     error_class="timeout", attempts=MAX_JOB_ATTEMPTS)
        self.assertFalse(job.is_retryable())

    def test_not_retryable_when_permanent_error_class(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.FAILED,
                     error_class="validation_error", attempts=1)
        self.assertFalse(job.is_retryable())

    def test_not_retryable_when_error_class_unknown(self):
        """Mac dinh AN TOAN cua classify_error_class: khong nam trong
        danh sach retryable => permanent."""
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.FAILED,
                     error_class="something_never_seen_before", attempts=1)
        self.assertFalse(job.is_retryable())


class TestClassifyErrorClass(unittest.TestCase):
    def test_known_retryable_classes(self):
        for cls in ("timeout", "network_error", "provider_unavailable",
                    "rate_limited"):
            self.assertEqual(classify_error_class(cls), "retryable")

    def test_known_permanent_classes(self):
        for cls in ("validation_error", "content_policy_violation",
                    "authentication_error", "invalid_model",
                    "insufficient_quota"):
            self.assertEqual(classify_error_class(cls), "permanent")

    def test_unknown_class_defaults_permanent(self):
        self.assertEqual(classify_error_class("totally_unseen"), "permanent")

    def test_none_defaults_permanent(self):
        self.assertEqual(classify_error_class(None), "permanent")


class TestCostMetadata(unittest.TestCase):
    def test_estimate_computes_estimated_cost(self):
        cost = CostMetadata.estimate(gpu_seconds=10.0, provider_rate=0.05,
                                      cold_or_warm="cold")
        self.assertAlmostEqual(cost.estimated_cost, 0.5)
        self.assertEqual(cost.actual_cost, 0.0)
        self.assertEqual(cost.cold_or_warm, "cold")

    def test_with_actual_computes_actual_cost_keeps_rate(self):
        estimate = CostMetadata.estimate(gpu_seconds=10.0, provider_rate=0.05)
        actual = estimate.with_actual(gpu_seconds=12.5)
        self.assertAlmostEqual(actual.actual_cost, 0.625)
        self.assertEqual(actual.provider_rate, 0.05)
        # ban estimate goc khong bi doi (immutable-style update qua replace)
        self.assertEqual(estimate.actual_cost, 0.0)

    def test_to_dict_from_dict_roundtrip(self):
        cost = CostMetadata.estimate(gpu_seconds=3.0, provider_rate=0.1,
                                      cold_or_warm="warm")
        restored = CostMetadata.from_dict(cost.to_dict())
        self.assertEqual(restored, cost)

    def test_from_dict_empty_gives_zero_defaults(self):
        cost = CostMetadata.from_dict(None)
        self.assertEqual(cost.gpu_seconds, 0.0)
        self.assertEqual(cost.provider_rate, 0.0)
        self.assertEqual(cost.estimated_cost, 0.0)
        self.assertEqual(cost.actual_cost, 0.0)
        self.assertIsNone(cost.cold_or_warm)

    def test_job_cost_and_set_cost_roundtrip(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m")
        cost = CostMetadata.estimate(gpu_seconds=5.0, provider_rate=0.2)
        job.set_cost(cost)
        self.assertEqual(job.cost_metadata["estimated_cost"], 1.0)
        self.assertEqual(job.cost(), cost)


class TestComputeInputHash(unittest.TestCase):
    def test_deterministic_for_same_input(self):
        a = compute_input_hash({"prompt": "hello", "seed": 1})
        b = compute_input_hash({"prompt": "hello", "seed": 1})
        self.assertEqual(a, b)

    def test_key_order_does_not_matter(self):
        a = compute_input_hash({"prompt": "hello", "seed": 1})
        b = compute_input_hash({"seed": 1, "prompt": "hello"})
        self.assertEqual(a, b)

    def test_different_input_gives_different_hash(self):
        a = compute_input_hash({"prompt": "hello"})
        b = compute_input_hash({"prompt": "goodbye"})
        self.assertNotEqual(a, b)

    def test_returns_hex_sha256_length(self):
        h = compute_input_hash({"x": 1})
        self.assertEqual(len(h), 64)
        int(h, 16)  # nem ValueError neu khong phai hex


class TestGPUJobStatusResponse(unittest.TestCase):
    def test_output_ref_hidden_unless_completed(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     output_ref="should_not_leak")
        response = GPUJobStatusResponse.from_job(job)
        self.assertIsNone(response.output_ref)

    def test_output_ref_present_when_completed(self):
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.COMPLETED,
                     output_ref="r2://covers/x.png")
        response = GPUJobStatusResponse.from_job(job)
        self.assertEqual(response.output_ref, "r2://covers/x.png")

    def test_to_dict_shape(self):
        job = GPUJob(job_type=GPUJobType.TRANSLATION, provider="beam",
                     model="hy-mt2", status=GPUJobStatus.QUEUED)
        data = GPUJobStatusResponse.from_job(job).to_dict()
        expected_keys = {
            "job_id", "job_type", "status", "provider", "model",
            "created_at", "started_at", "completed_at", "attempts",
            "error_class", "error_message", "output_ref", "usage_metadata",
            "cost_metadata",
        }
        self.assertEqual(set(data.keys()), expected_keys)
        self.assertEqual(data["job_type"], "translation")
        self.assertEqual(data["status"], "queued")


class TestGPUJobDomainModuleIsProviderNeutral(unittest.TestCase):
    """Tuong tu
    test_character_identity.py::TestCharacterIdentityModuleIsProviderNeutral
    - kiem tra THAT (AST, khong chi doc docstring) rang
    server/gpu_job_domain.py khong import bat ky provider GPU/mang cu the
    nao o cap module."""

    _FORBIDDEN_MODULES = {"beam", "torch", "diffusers", "httpx", "vllm", "PIL"}

    def test_no_provider_specific_top_level_imports(self):
        source = inspect.getsource(gpu_job_domain)
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
            f"server/gpu_job_domain.py imports provider-specific "
            f"module(s) {forbidden_found} - this module must stay "
            f"provider-neutral.")


if __name__ == "__main__":
    unittest.main()
