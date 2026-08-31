import ast
import inspect
import unittest
from typing import Any, List, Optional

from server import gpu_job_service
from server.gpu_job_domain import GPUJob, GPUJobStatus, GPUJobType, MAX_JOB_ATTEMPTS
from server.gpu_job_service import (
    GPUJobNotFoundError,
    GPUJobService,
    MockGPUJobStore,
    classify_error,
)
from server.gpu_job_storage import MockOutputStorage


class FakeGPUJobProviderAdapter:
    """Adapter GIA cho test - KHONG BAO GIO goi mang that. Hanh vi cua
    submit()/poll()/cancel()/fetch_result() duoc dieu khien tu ben ngoai
    qua cac danh sach/co truyen vao __init__, de moi test dung MOT the hien
    rieng thay vi mot mock framework chung chung."""

    def __init__(self, *, submit_exceptions: Optional[List[Exception]] = None,
                 submit_ref: str = "provider-ref-1",
                 poll_exceptions: Optional[List[Exception]] = None,
                 poll_statuses: Optional[List[GPUJobStatus]] = None,
                 cancel_should_raise: Optional[Exception] = None,
                 fetch_result_ref: str = "r2://covers/out.png",
                 fetch_result_should_raise: Optional[Exception] = None) -> None:
        self._submit_exceptions = list(submit_exceptions or [])
        self._submit_ref = submit_ref
        self._poll_exceptions = list(poll_exceptions or [])
        self._poll_statuses = list(poll_statuses or [])
        self._cancel_should_raise = cancel_should_raise
        self._fetch_result_ref = fetch_result_ref
        self._fetch_result_should_raise = fetch_result_should_raise
        self.submit_calls = 0
        self.poll_calls = 0
        self.cancel_calls = 0
        self.fetch_result_calls = 0

    def submit(self, job: GPUJob, input_data: Any) -> str:
        self.submit_calls += 1
        if self._submit_exceptions:
            raise self._submit_exceptions.pop(0)
        return self._submit_ref

    def poll(self, job: GPUJob) -> GPUJobStatus:
        self.poll_calls += 1
        if self._poll_exceptions:
            raise self._poll_exceptions.pop(0)
        if self._poll_statuses:
            return self._poll_statuses.pop(0)
        return job.status

    def cancel(self, job: GPUJob) -> bool:
        self.cancel_calls += 1
        if self._cancel_should_raise is not None:
            raise self._cancel_should_raise
        return True

    def fetch_result(self, job: GPUJob) -> str:
        self.fetch_result_calls += 1
        if self._fetch_result_should_raise is not None:
            raise self._fetch_result_should_raise
        return self._fetch_result_ref


def _service(adapter: FakeGPUJobProviderAdapter, provider: str = "beam"):
    store = MockGPUJobStore()
    service = GPUJobService(store=store, provider_adapters={provider: adapter})
    return service, store


class TestSubmitJob(unittest.TestCase):
    def test_submit_creates_provisioning_job_and_calls_adapter(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam",
                                  "illustrious-xl", {"prompt": "a cat"})
        self.assertEqual(adapter.submit_calls, 1)
        self.assertEqual(job.status, GPUJobStatus.PROVISIONING)
        self.assertEqual(job.provider_job_ref, "provider-ref-1")
        self.assertEqual(job.attempts, 1)
        self.assertIsNotNone(job.started_at)
        self.assertIs(store.get(job.job_id), job)

    def test_submit_with_unknown_provider_raises_before_creating_job(self):
        adapter = FakeGPUJobProviderAdapter()
        store = MockGPUJobStore()
        service = GPUJobService(store=store, provider_adapters={"beam": adapter})
        with self.assertRaises(ValueError):
            service.submit_job(GPUJobType.IMAGE_GENERATION, "not-registered",
                                "model", {"x": 1})
        self.assertEqual(adapter.submit_calls, 0)
        self.assertEqual(store.list_pending(), [])

    def test_input_hash_is_computed(self):
        adapter = FakeGPUJobProviderAdapter()
        service, _ = _service(adapter)
        job = service.submit_job(GPUJobType.TRANSLATION, "beam", "hy-mt2",
                                  {"text": "hello"})
        self.assertTrue(job.input_hash)
        self.assertEqual(len(job.input_hash), 64)


class TestIdempotency(unittest.TestCase):
    def test_same_explicit_key_returns_same_pending_job(self):
        adapter = FakeGPUJobProviderAdapter()
        service, _ = _service(adapter)
        job1 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"a": 1}, idempotency_key="fixed-key")
        job2 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"a": 1}, idempotency_key="fixed-key")
        self.assertEqual(job1.job_id, job2.job_id)
        self.assertEqual(adapter.submit_calls, 1)

    def test_duplicate_suppression_via_input_hash_without_explicit_key(self):
        adapter = FakeGPUJobProviderAdapter()
        service, _ = _service(adapter)
        job1 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"prompt": "same"})
        job2 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"prompt": "same"})
        self.assertEqual(job1.job_id, job2.job_id)
        self.assertEqual(adapter.submit_calls, 1)

    def test_different_input_creates_different_job(self):
        adapter = FakeGPUJobProviderAdapter()
        service, _ = _service(adapter)
        job1 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"prompt": "a"})
        job2 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"prompt": "b"})
        self.assertNotEqual(job1.job_id, job2.job_id)
        self.assertEqual(adapter.submit_calls, 2)

    def test_resubmit_after_failed_creates_new_attempt(self):
        adapter = FakeGPUJobProviderAdapter(
            submit_exceptions=[ValueError("bad prompt")])
        service, _ = _service(adapter)
        job1 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"a": 1}, idempotency_key="k")
        self.assertEqual(job1.status, GPUJobStatus.FAILED)

        # Adapter thanh cong o lan submit tiep theo (khong con exception hen gio)
        job2 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"a": 1}, idempotency_key="k")
        self.assertNotEqual(job1.job_id, job2.job_id)
        self.assertEqual(job2.status, GPUJobStatus.PROVISIONING)
        self.assertEqual(adapter.submit_calls, 2)

    def test_resubmit_after_cancelled_creates_new_attempt(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job1 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"a": 1}, idempotency_key="k2")
        service.cancel_job(job1.job_id)
        self.assertEqual(store.get(job1.job_id).status, GPUJobStatus.CANCELLED)

        job2 = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                   {"a": 1}, idempotency_key="k2")
        self.assertNotEqual(job1.job_id, job2.job_id)


class TestRetryClassification(unittest.TestCase):
    def test_transient_error_retried_then_succeeds_within_budget(self):
        adapter = FakeGPUJobProviderAdapter(
            submit_exceptions=[TimeoutError("cold start too slow"),
                                TimeoutError("still slow")])
        service, _ = _service(adapter)
        job = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                  {"a": 1})
        self.assertEqual(job.status, GPUJobStatus.PROVISIONING)
        self.assertEqual(job.attempts, 3)
        self.assertEqual(adapter.submit_calls, 3)
        self.assertIsNone(job.error_class)

    def test_transient_error_exhausts_max_attempts_then_fails(self):
        adapter = FakeGPUJobProviderAdapter(
            submit_exceptions=[TimeoutError("x")] * 10)
        service, _ = _service(adapter)
        job = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                  {"a": 1})
        self.assertEqual(job.status, GPUJobStatus.FAILED)
        self.assertEqual(job.attempts, MAX_JOB_ATTEMPTS)
        self.assertEqual(adapter.submit_calls, MAX_JOB_ATTEMPTS)
        self.assertEqual(job.error_class, "timeout")
        self.assertFalse(job.is_retryable())

    def test_permanent_error_fails_immediately_without_retry(self):
        adapter = FakeGPUJobProviderAdapter(
            submit_exceptions=[ValueError("bad request")])
        service, _ = _service(adapter)
        job = service.submit_job(GPUJobType.IMAGE_GENERATION, "beam", "m",
                                  {"a": 1})
        self.assertEqual(job.status, GPUJobStatus.FAILED)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(adapter.submit_calls, 1)
        self.assertEqual(job.error_class, "validation_error")

    def test_classify_error_maps_common_exception_types(self):
        self.assertEqual(classify_error(TimeoutError()), "timeout")
        self.assertEqual(classify_error(ConnectionError()), "network_error")
        self.assertEqual(classify_error(PermissionError()), "authentication_error")
        self.assertEqual(classify_error(ValueError()), "validation_error")
        self.assertEqual(classify_error(RuntimeError()), "unknown_error")


class TestCancellation(unittest.TestCase):
    def test_cancel_queued_job_does_not_call_adapter(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.QUEUED)
        store.save(job)
        result = service.cancel_job(job.job_id)
        self.assertEqual(result.status, GPUJobStatus.CANCELLED)
        self.assertEqual(adapter.cancel_calls, 0)
        self.assertIsNotNone(result.completed_at)

    def test_cancel_running_job_calls_adapter_best_effort(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     provider_job_ref="ref-1")
        store.save(job)
        result = service.cancel_job(job.job_id)
        self.assertEqual(result.status, GPUJobStatus.CANCELLED)
        self.assertEqual(adapter.cancel_calls, 1)

    def test_cancel_running_job_still_cancels_locally_if_adapter_cancel_fails(self):
        adapter = FakeGPUJobProviderAdapter(
            cancel_should_raise=ConnectionError("provider unreachable"))
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.PROVISIONING,
                     provider_job_ref="ref-1")
        store.save(job)
        result = service.cancel_job(job.job_id)
        self.assertEqual(result.status, GPUJobStatus.CANCELLED)
        self.assertIn("provider unreachable", result.error_message)

    def test_cancel_terminal_job_is_noop(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.COMPLETED,
                     output_ref="r2://x.png")
        store.save(job)
        result = service.cancel_job(job.job_id)
        self.assertEqual(result.status, GPUJobStatus.COMPLETED)
        self.assertEqual(adapter.cancel_calls, 0)

    def test_cancel_unknown_job_raises_not_found(self):
        adapter = FakeGPUJobProviderAdapter()
        service, _ = _service(adapter)
        with self.assertRaises(GPUJobNotFoundError):
            service.cancel_job("gpu_does_not_exist")


class TestGetJobStatus(unittest.TestCase):
    def test_no_refresh_reads_store_only(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING)
        store.save(job)
        result = service.get_job_status(job.job_id)
        self.assertEqual(result.status, GPUJobStatus.RUNNING)
        self.assertEqual(adapter.poll_calls, 0)

    def test_refresh_terminal_job_does_not_poll(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.COMPLETED,
                     output_ref="r2://x.png")
        store.save(job)
        result = service.get_job_status(job.job_id, refresh=True)
        self.assertEqual(result.status, GPUJobStatus.COMPLETED)
        self.assertEqual(adapter.poll_calls, 0)

    def test_refresh_completes_job_and_fetches_output_ref(self):
        adapter = FakeGPUJobProviderAdapter(
            poll_statuses=[GPUJobStatus.COMPLETED],
            fetch_result_ref="r2://covers/final.png")
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     provider_job_ref="ref-1")
        store.save(job)
        result = service.get_job_status(job.job_id, refresh=True)
        self.assertEqual(result.status, GPUJobStatus.COMPLETED)
        self.assertEqual(result.output_ref, "r2://covers/final.png")
        self.assertIsNotNone(result.completed_at)
        self.assertEqual(adapter.fetch_result_calls, 1)

    def test_refresh_transient_poll_error_leaves_job_unchanged(self):
        adapter = FakeGPUJobProviderAdapter(
            poll_exceptions=[ConnectionError("temporary blip")])
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     provider_job_ref="ref-1")
        store.save(job)
        result = service.get_job_status(job.job_id, refresh=True)
        self.assertEqual(result.status, GPUJobStatus.RUNNING)
        self.assertIsNone(result.error_class)

    def test_refresh_permanent_poll_error_fails_job(self):
        adapter = FakeGPUJobProviderAdapter(
            poll_exceptions=[ValueError("auth revoked")])
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     provider_job_ref="ref-1")
        store.save(job)
        result = service.get_job_status(job.job_id, refresh=True)
        self.assertEqual(result.status, GPUJobStatus.FAILED)
        self.assertEqual(result.error_class, "validation_error")

    def test_refresh_provider_reported_failure(self):
        adapter = FakeGPUJobProviderAdapter(poll_statuses=[GPUJobStatus.FAILED])
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     provider_job_ref="ref-1")
        store.save(job)
        result = service.get_job_status(job.job_id, refresh=True)
        self.assertEqual(result.status, GPUJobStatus.FAILED)
        self.assertEqual(result.error_class, "provider_reported_failure")

    def test_get_job_status_response_hides_output_ref_until_completed(self):
        adapter = FakeGPUJobProviderAdapter()
        service, store = _service(adapter)
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", status=GPUJobStatus.RUNNING,
                     output_ref="should-not-leak")
        store.save(job)
        response = service.get_job_status_response(job.job_id)
        self.assertIsNone(response.output_ref)

    def test_get_job_status_unknown_job_raises_not_found(self):
        adapter = FakeGPUJobProviderAdapter()
        service, _ = _service(adapter)
        with self.assertRaises(GPUJobNotFoundError):
            service.get_job_status("gpu_does_not_exist")


class TestMockGPUJobStore(unittest.TestCase):
    def test_save_get_roundtrip(self):
        store = MockGPUJobStore()
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m")
        store.save(job)
        self.assertIs(store.get(job.job_id), job)

    def test_get_missing_returns_none(self):
        store = MockGPUJobStore()
        self.assertIsNone(store.get("gpu_nope"))

    def test_find_by_idempotency_key(self):
        store = MockGPUJobStore()
        job = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                     model="m", idempotency_key="k")
        store.save(job)
        self.assertIs(store.find_by_idempotency_key("k"), job)
        self.assertIsNone(store.find_by_idempotency_key("other"))

    def test_list_pending_excludes_terminal_jobs(self):
        store = MockGPUJobStore()
        pending = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                          model="m", status=GPUJobStatus.RUNNING)
        done = GPUJob(job_type=GPUJobType.IMAGE_GENERATION, provider="beam",
                      model="m", status=GPUJobStatus.COMPLETED)
        store.save(pending)
        store.save(done)
        self.assertEqual(store.list_pending(), [pending])


class TestMockOutputStorage(unittest.TestCase):
    def test_save_load_roundtrip(self):
        storage = MockOutputStorage()
        ref = storage.save("gpu_1", b"fake-image-bytes", "image/png")
        self.assertEqual(storage.load(ref), b"fake-image-bytes")
        self.assertEqual(storage.content_type_of(ref), "image/png")

    def test_load_missing_ref_raises_key_error(self):
        storage = MockOutputStorage()
        with self.assertRaises(KeyError):
            storage.load("mock://does-not-exist")

    def test_distinct_refs_for_multiple_saves(self):
        storage = MockOutputStorage()
        ref1 = storage.save("gpu_1", b"a", "image/png")
        ref2 = storage.save("gpu_1", b"b", "image/png")
        self.assertNotEqual(ref1, ref2)
        self.assertEqual(storage.load(ref1), b"a")
        self.assertEqual(storage.load(ref2), b"b")


class TestGPUJobServiceModuleIsProviderNeutral(unittest.TestCase):
    """server/gpu_job_service.py depende SOLO du Protocol GPUJobProviderAdapter
    - khong import beam/torch/diffusers/httpx/vllm o cap module, giong
    server/gpu_job_domain.py."""

    _FORBIDDEN_MODULES = {"beam", "torch", "diffusers", "httpx", "vllm", "PIL"}

    def test_no_provider_specific_top_level_imports(self):
        source = inspect.getsource(gpu_job_service)
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
            f"server/gpu_job_service.py imports provider-specific "
            f"module(s) {forbidden_found} - GPUJobService must only depend "
            f"on the GPUJobProviderAdapter Protocol for provider work.")


if __name__ == "__main__":
    unittest.main()
