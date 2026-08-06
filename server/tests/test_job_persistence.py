"""
Test vong doi TTS job: MOI transition phai duoc luu qua metadata adapter.

Vi sao can bo test nay: truoc day `_run_job` chi doi thuoc tinh cua doi tuong
`TtsJob` trong bo nho. Voi `MockMetadataStore` thi van "dung" vi kho luu cung
mot tham chieu - nhung voi Appwrite, moi thay doi trang thai deu bien mat vi
khong ai goi `save_job()`. Cac test duoi day bat dung loi do bang cach GHI LAI
tung loi goi vao metadata interface, khong phu thuoc Appwrite that.

Chay HOAN TOAN offline: pipeline TTS duoc thay bang ban gia lap.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack, JobStatus, TtsJob


# -----------------------------------------------------------------------------
# Do gia: ghi lai thu tu goi
# -----------------------------------------------------------------------------


class RecordingStore(MockMetadataStore):
    """
    Kho metadata ghi lai MOI lan job duoc luu.

    Chi mo rong ban mock - khong cham toi Appwrite. Muc dich la chung minh
    job runner that su goi qua interface chung.
    """

    def __init__(self, calls: List[str]):
        super().__init__()
        self.calls = calls
        #: (status, output_key) tai moi lan ghi ben vung
        self.job_states: List[tuple] = []
        #: Neu dat, `save_job` se nem loi khi job o dung trang thai nay.
        self.fail_on_status: Optional[str] = None

    def create_job(self, job: TtsJob) -> TtsJob:
        self.calls.append(f"create_job:{job.status.value}")
        self.job_states.append((job.status.value, job.output_key))
        return super().create_job(job)

    def save_job(self, job: TtsJob) -> TtsJob:
        self.calls.append(f"save_job:{job.status.value}")
        if self.fail_on_status and job.status.value == self.fail_on_status:
            raise RuntimeError("metadata backend từ chối ghi")
        self.job_states.append((job.status.value, job.output_key))
        return super().save_job(job)

    def create_track(self, track: AudioTrack) -> AudioTrack:
        self.calls.append("create_track")
        return super().create_track(track)

    # -- tien ich cho assertion ----------------------------------------------

    @property
    def saved_statuses(self) -> List[str]:
        """Chuoi trang thai da duoc GHI BEN VUNG, theo thu tu."""
        return [status for status, _ in self.job_states]


class RecordingStorage(LocalStorageAdapter):
    """Kho file ghi lai thoi diem upload."""

    def __init__(self, root: Path, calls: List[str]):
        super().__init__(root)
        self.calls = calls

    def put_file(self, key: str, source: Path) -> str:
        self.calls.append("upload")
        return super().put_file(key, source)


class BrokenStorage(LocalStorageAdapter):
    """Upload luon hong."""

    def put_file(self, key: str, source: Path) -> str:
        raise OSError("ổ đĩa đầy")


# -----------------------------------------------------------------------------
# Nen chung
# -----------------------------------------------------------------------------


class JobLifecycleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: List[str] = []
        self._tmp = tempfile.mkdtemp()

        server_main.identity = MockIdentityAdapter()
        self.store = RecordingStore(self.calls)
        server_main.store = self.store
        self._real_storage = server_main.storage
        server_main.storage = RecordingStorage(Path(self._tmp), self.calls)

        self._real_synth = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = self._make_synth()
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._real_synth
        server_main.storage = self._real_storage

    # -- ban gia lap cua pipeline TTS ----------------------------------------

    def _make_synth(self, error: Optional[Exception] = None):
        """Tao ban gia lap co ghi lai thoi diem duoc goi."""
        calls = self.calls
        snapshots = self.synth_snapshots = []
        store = self.store

        def _synth(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                   on_progress=None, cancel=None) -> Dict[str, Any]:
            calls.append("synthesize")
            # Chup lai nhung gi da duoc GHI truoc khi synthesis bat dau
            snapshots.append(list(store.saved_statuses))
            if error is not None:
                raise error
            dest = Path(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x00" * 4096)
            if on_progress:
                on_progress(1, 1)
            return {"size_bytes": 4096, "total_parts": 1,
                    "voice_id": voice_id, "provider": "mock"}

        return _synth

    def _fail_synthesis(self, error: Exception) -> None:
        tts_bridge.synthesize_chapter = self._make_synth(error=error)

    # -- tien ich HTTP --------------------------------------------------------

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def _chapter(self, token: str, content: str = "Nội dung chương.") -> str:
        novel_id = self.client.post(
            "/api/novels", json={"title": "Truyện"}, headers=self._auth(token)
        ).json()["novel"]["novel_id"]
        return self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "Chương 1", "content": content},
            headers=self._auth(token),
        ).json()["chapter"]["chapter_id"]

    def _submit(self, token: str, chapter_id: str) -> Dict[str, Any]:
        return self.client.post(
            "/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
            headers=self._auth(token),
        ).json()

    def _wait(self, token: str, job_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.client.get(
                f"/api/jobs/{job_id}", headers=self._auth(token)
            ).json()["job"]
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.02)
        self.fail("job không kết thúc trong thời gian chờ")

    def _run_to_end(self, content: str = "Nội dung chương.") -> Dict[str, Any]:
        token = self._user()
        chapter_id = self._chapter(token, content)
        job_id = self._submit(token, chapter_id)["job"]["job_id"]
        return self._wait(token, job_id)


# -----------------------------------------------------------------------------
# 1-3: duong di thanh cong
# -----------------------------------------------------------------------------


class TestSuccessfulTransitions(JobLifecycleTestCase):
    def test_1_new_job_is_persisted_as_pending(self):
        """Job moi phai duoc GHI o trang thai `pending` ngay khi tao."""
        token = self._user()
        chapter_id = self._chapter(token)
        created = self._submit(token, chapter_id)["job"]

        self.assertEqual(created["status"], JobStatus.PENDING.value)
        # Lan ghi ben vung dau tien phai la `pending`, chua co output_key
        self.assertEqual(self.store.job_states[0], (JobStatus.PENDING.value, None))
        self.assertIn(f"create_job:{JobStatus.PENDING.value}", self.calls)

        self._wait(token, created["job_id"])

    def test_2_running_is_saved_before_synthesis(self):
        """`running` phai duoc luu TRUOC khi goi synthesis."""
        self._run_to_end()

        self.assertTrue(self.synth_snapshots, "pipeline TTS chưa được gọi")
        before_synthesis = self.synth_snapshots[0]
        self.assertEqual(
            before_synthesis,
            [JobStatus.PENDING.value, JobStatus.RUNNING.value],
            "phải lưu `running` trước khi bắt đầu tổng hợp",
        )

    def test_3_completed_is_saved_with_output_key_after_upload(self):
        """`completed` duoc luu kem `output_key`, va chi sau khi upload xong."""
        job = self._run_to_end()

        self.assertEqual(job["status"], JobStatus.COMPLETED.value)
        self.assertTrue(job["output_key"], "job hoàn tất phải có output_key")

        final_status, final_key = self.store.job_states[-1]
        self.assertEqual(final_status, JobStatus.COMPLETED.value)
        self.assertTrue(final_key, "`completed` phải được ghi kèm output_key")

        # Upload phai xay ra TRUOC lan ghi `completed`
        self.assertLess(
            self.calls.index("upload"),
            self.calls.index(f"save_job:{JobStatus.COMPLETED.value}"),
        )


# -----------------------------------------------------------------------------
# 4-6: cac duong that bai
# -----------------------------------------------------------------------------


class TestFailureTransitions(JobLifecycleTestCase):
    def test_4_synthesis_failure_is_saved_as_failed(self):
        """Synthesis hong -> luu `failed` kem loi, khong ket o `running`."""
        self._fail_synthesis(
            tts_bridge.TtsBridgeError("voice_not_found", "Không tìm thấy giọng đọc.")
        )
        job = self._run_to_end()

        self.assertEqual(job["status"], JobStatus.FAILED.value)
        self.assertEqual(job["error_kind"], "voice_not_found")
        self.assertTrue(job["error_message"])
        self.assertIn(f"save_job:{JobStatus.FAILED.value}", self.calls)
        self.assertEqual(self.store.saved_statuses[-1], JobStatus.FAILED.value)
        self.assertNotEqual(
            self.store.saved_statuses[-1], JobStatus.RUNNING.value,
            "không được kẹt ở trạng thái `running`",
        )
        # Khong duoc cong bo output do dang
        self.assertIsNone(job["output_key"])
        self.assertNotIn("create_track", self.calls)

    def test_5_upload_failure_saves_failed_and_never_completed(self):
        """Upload hong -> `failed`; tuyet doi khong ghi `completed`."""
        server_main.storage = BrokenStorage(Path(tempfile.mkdtemp()))
        token = self._user()
        chapter_id = self._chapter(token)
        job_id = self._submit(token, chapter_id)["job"]["job_id"]
        job = self._wait(token, job_id)

        self.assertEqual(job["status"], JobStatus.FAILED.value)
        self.assertIsNone(job["output_key"], "upload hỏng thì không được ghi output_key")
        self.assertNotIn(
            f"save_job:{JobStatus.COMPLETED.value}", self.calls,
            "không bao giờ được lưu `completed` khi upload thất bại",
        )
        self.assertNotIn(JobStatus.COMPLETED.value, self.store.saved_statuses)
        # Va khong tao audio_track nao
        self.assertIsNone(
            self.client.get(f"/api/chapters/{chapter_id}").json()["audio"]
        )

    def test_6_metadata_persistence_failure_is_not_reported_as_success(self):
        """Ghi `completed` that bai -> client KHONG duoc nhan thanh cong gia."""
        self.store.fail_on_status = JobStatus.COMPLETED.value

        token = self._user()
        chapter_id = self._chapter(token)
        job_id = self._submit(token, chapter_id)["job"]["job_id"]
        job = self._wait(token, job_id)

        self.assertNotEqual(
            job["status"], JobStatus.COMPLETED.value,
            "không được báo `completed` khi metadata chưa lưu được",
        )
        self.assertEqual(job["status"], JobStatus.FAILED.value)
        self.assertIsNone(job["output_key"])
        self.assertIn("metadata backend từ chối ghi", job["error_message"])
        # Khong lan ghi ben vung nao ket thuc o `completed`
        self.assertNotIn(JobStatus.COMPLETED.value, self.store.saved_statuses)


# -----------------------------------------------------------------------------
# 7-9: thu tu, giao dien va idempotency
# -----------------------------------------------------------------------------


class TestOrderingAndInterface(JobLifecycleTestCase):
    def test_7_call_order_is_synthesize_then_upload_then_save_completed(self):
        """Thu tu bat buoc: synthesize -> upload -> create_track -> completed."""
        self._run_to_end()

        self.assertEqual(
            self.calls,
            [
                f"create_job:{JobStatus.PENDING.value}",
                f"save_job:{JobStatus.RUNNING.value}",
                "synthesize",
                "upload",
                "create_track",
                f"save_job:{JobStatus.COMPLETED.value}",
            ],
        )

    def test_8_transitions_go_through_the_metadata_interface(self):
        """
        Toan bo transition di qua metadata interface, khong can Appwrite that.

        Kho o day chi la ban mock trong bo nho; neu job runner bo qua interface
        (chi doi thuoc tinh) thi khong co lan ghi nao duoc ghi nhan.
        """
        self._run_to_end()

        self.assertEqual(
            self.store.saved_statuses,
            [JobStatus.PENDING.value, JobStatus.RUNNING.value,
             JobStatus.COMPLETED.value],
        )
        self.assertFalse(
            [c for c in self.calls if "appwrite" in c.lower()],
            "job runner không được gọi thẳng Appwrite",
        )

    def test_8b_appwrite_store_exposes_the_same_save_job_interface(self):
        """
        Ban Appwrite phai co CUNG phuong thuc `save_job`.

        Kiem tra tinh, khong tao ket noi mang va khong can credential.
        """
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        for name in ("create_job", "save_job", "get_job", "create_track"):
            self.assertTrue(
                callable(getattr(AppwriteMetadataStore, name, None)),
                f"AppwriteMetadataStore thiếu {name}()",
            )
        self.assertEqual(
            list(inspect.signature(AppwriteMetadataStore.save_job).parameters),
            list(inspect.signature(MockMetadataStore.save_job).parameters),
            "hai kho metadata phải cùng chữ ký save_job()",
        )

    def test_9_idempotency_still_reuses_the_same_job(self):
        """Cung noi dung + giong + thiet lap -> tai dung job, khong tao moi."""
        token = self._user()
        chapter_id = self._chapter(token)

        first = self._submit(token, chapter_id)
        self.assertFalse(first["reused"])
        self._wait(token, first["job"]["job_id"])

        second = self._submit(token, chapter_id)
        self.assertTrue(second["reused"], "phải tái dùng job đã có")
        self.assertEqual(second["job"]["job_id"], first["job"]["job_id"])
        # Khong goi lai pipeline TTS
        self.assertEqual(self.calls.count("synthesize"), 1)

    def test_9b_failed_job_is_not_reused(self):
        """Job `failed` KHONG duoc tai dung - phai chay lai."""
        self._fail_synthesis(tts_bridge.TtsBridgeError("network", "Mất kết nối."))
        token = self._user()
        chapter_id = self._chapter(token)

        first = self._submit(token, chapter_id)
        self._wait(token, first["job"]["job_id"])

        second = self._submit(token, chapter_id)
        self.assertFalse(second["reused"], "job thất bại không được tái dùng")
        self.assertNotEqual(second["job"]["job_id"], first["job"]["job_id"])
        self._wait(token, second["job"]["job_id"])


# -----------------------------------------------------------------------------
# Bao ve: khong ro ri thread
# -----------------------------------------------------------------------------


class TestWorkerCleanup(JobLifecycleTestCase):
    def test_worker_thread_is_released_after_completion(self):
        """Thread nen phai duoc go khoi so theo doi khi job ket thuc."""
        self._run_to_end()
        deadline = time.monotonic() + 3.0
        while server_main._job_threads and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(server_main._job_threads, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
