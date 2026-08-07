"""
Test bao mat: quyen truy cap audio, chong gia mao danh tinh, va vong doi upload.

Chay HOAN TOAN offline: pipeline TTS va client S3 deu duoc gia lap.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.config import R2Settings
from server.domain import JobStatus


def _fake_synthesize(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                     on_progress=None, cancel=None) -> Dict[str, Any]:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\x00" * 4096)
    if on_progress:
        on_progress(1, 1)
    return {"size_bytes": 4096, "total_parts": 1, "voice_id": voice_id, "provider": "mock"}


class SecurityTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        self._real_synth = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = _fake_synthesize
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._real_synth
        server_main.storage = self._real_storage

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _user(self, email: str) -> str:
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": "matkhau123"})
        return r.json()["token"]

    def _chapter_with_audio(self, token: str):
        novel_id = self.client.post("/api/novels", json={"title": "Truyện"},
                                    headers=self._auth(token)).json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "Chương 1", "content": "Nội dung."},
            headers=self._auth(token),
        ).json()["chapter"]["chapter_id"]
        job_id = self.client.post("/api/jobs",
                                  json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(token)).json()["job"]["job_id"]
        self._wait(token, job_id)
        return novel_id, chapter_id

    def _wait(self, token: str, job_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}",
                                  headers=self._auth(token)).json()["job"]
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.05)
        self.fail("job không kết thúc trong thời gian chờ")


class TestAudioAccess(SecurityTestCase):
    """Audio rieng tu phai duoc bao ve o phia server."""

    def test_draft_audio_requires_authentication(self):
        owner = self._user("owner@example.com")
        _, chapter_id = self._chapter_with_audio(owner)
        r = self.client.get(f"/api/audio/{chapter_id}")
        self.assertEqual(r.status_code, 401)

    def test_draft_audio_denied_to_other_user(self):
        owner = self._user("owner@example.com")
        _, chapter_id = self._chapter_with_audio(owner)
        intruder = self._user("intruder@example.com")
        r = self.client.get(f"/api/audio/{chapter_id}", headers=self._auth(intruder))
        self.assertEqual(r.status_code, 403)

    def test_owner_can_listen_to_own_draft(self):
        owner = self._user("owner@example.com")
        _, chapter_id = self._chapter_with_audio(owner)
        r = self.client.get(f"/api/audio/{chapter_id}", headers=self._auth(owner))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "audio/mpeg")

    def test_published_audio_is_public(self):
        owner = self._user("owner@example.com")
        novel_id, chapter_id = self._chapter_with_audio(owner)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self._auth(owner))
        r = self.client.get(f"/api/audio/{chapter_id}")
        self.assertEqual(r.status_code, 200)

    def test_unknown_chapter_is_404(self):
        self.assertEqual(self.client.get("/api/audio/chp_khong_co").status_code, 404)


class TestIdentitySpoofing(SecurityTestCase):
    """Khong bao gio tin user_id do client tu gui."""

    def test_owner_comes_from_token_not_from_body(self):
        victim = self._user("victim@example.com")
        attacker = self._user("attacker@example.com")
        victim_id = self.client.get("/api/auth/me",
                                    headers=self._auth(victim)).json()["profile"]["user_id"]

        # Ke tan cong co gang tu khai owner_id cua nan nhan
        created = self.client.post(
            "/api/novels",
            json={"title": "Mạo danh", "owner_id": victim_id, "user_id": victim_id},
            headers=self._auth(attacker),
        ).json()["novel"]

        attacker_id = self.client.get("/api/auth/me",
                                      headers=self._auth(attacker)).json()["profile"]["user_id"]
        self.assertEqual(created["owner_id"], attacker_id)
        self.assertNotEqual(created["owner_id"], victim_id)

    def test_job_owner_cannot_be_forged(self):
        victim = self._user("victim@example.com")
        attacker = self._user("attacker@example.com")
        novel_id = self.client.post("/api/novels", json={"title": "T"},
                                    headers=self._auth(victim)).json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "C", "content": "x"},
            headers=self._auth(victim),
        ).json()["chapter"]["chapter_id"]

        # Ke tan cong gui job cho chuong cua nguoi khac -> phai bi tu choi
        r = self.client.post(
            "/api/jobs",
            json={"chapter_id": chapter_id, "voice_id": "mock:v1",
                  "owner_id": "usr_gia_mao"},
            headers=self._auth(attacker),
        )
        self.assertEqual(r.status_code, 403)


class TestUploadLifecycle(SecurityTestCase):
    """Job chi `completed` SAU KHI output da luu thanh cong."""

    def test_completed_only_after_successful_upload(self):
        owner = self._user("owner@example.com")
        _, chapter_id = self._chapter_with_audio(owner)
        detail = self.client.get(f"/api/chapters/{chapter_id}",
                                 headers=self._auth(owner)).json()
        self.assertIsNotNone(detail["audio"])
        self.assertTrue(detail["audio"]["object_key"])

    def test_upload_failure_marks_job_failed(self):
        class BrokenStorage(LocalStorageAdapter):
            def put_file(self, key, source):
                raise OSError("ổ đĩa đầy")

        server_main.storage = BrokenStorage(Path(tempfile.mkdtemp()))

        owner = self._user("owner@example.com")
        novel_id = self.client.post("/api/novels", json={"title": "T"},
                                    headers=self._auth(owner)).json()["novel"]["novel_id"]
        chapter_id = self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "C", "content": "Nội dung."},
            headers=self._auth(owner),
        ).json()["chapter"]["chapter_id"]
        job_id = self.client.post("/api/jobs",
                                  json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(owner)).json()["job"]["job_id"]

        job = self._wait(owner, job_id)
        self.assertEqual(job["status"], JobStatus.FAILED.value)
        self.assertIsNone(job["output_key"], "Upload hỏng thì không được ghi output_key")
        self.assertTrue(job["error_message"])

        # Va khong duoc tao audio_track nao
        self.assertIsNone(
            self.client.get(f"/api/chapters/{chapter_id}",
                            headers=self._auth(owner)).json()["audio"])


class TestR2AdapterWithMockedClient(unittest.TestCase):
    """R2 adapter voi client S3 gia lap - khong cham vao Cloudflare that."""

    def _adapter(self):
        from server.r2_adapter import R2StorageAdapter

        settings = R2Settings(account_id="acc", access_key_id="k",
                              secret_access_key="s", bucket="thu-nghiem")
        adapter = R2StorageAdapter.__new__(R2StorageAdapter)
        adapter._settings = settings
        adapter._bucket = settings.bucket
        adapter._client = _FakeS3()
        return adapter

    def test_put_and_get_roundtrip(self):
        adapter = self._adapter()
        adapter.put("audio/u/c/x.mp3", b"\x00" * 1024, content_type="audio/mpeg")
        self.assertEqual(len(adapter.get("audio/u/c/x.mp3")), 1024)

    def test_content_type_is_recorded(self):
        adapter = self._adapter()
        adapter.put("a.mp3", b"x", content_type="audio/mpeg")
        self.assertEqual(adapter._client.objects["a.mp3"]["ContentType"], "audio/mpeg")

    def test_head_and_size(self):
        adapter = self._adapter()
        adapter.put("a.mp3", b"\x00" * 77)
        self.assertTrue(adapter.exists("a.mp3"))
        self.assertEqual(adapter.size("a.mp3"), 77)
        self.assertFalse(adapter.exists("khong-co.mp3"))
        self.assertEqual(adapter.size("khong-co.mp3"), 0)

    def test_missing_object_raises_not_found(self):
        from server.adapters import NotFoundError

        with self.assertRaises(NotFoundError):
            self._adapter().get("khong-co.mp3")

    def test_signed_url_is_short_lived_and_not_a_public_url(self):
        adapter = self._adapter()
        url = adapter.signed_url("a.mp3", expires_seconds=300)
        self.assertIn("X-Amz-Expires=300", url)
        self.assertIn("X-Amz-Signature", url, "URL phải được ký, không phải public")


class _FakeS3:
    """Client S3 toi gian trong bo nho."""

    def __init__(self):
        self.objects: Dict[str, Dict[str, Any]] = {}

    def put_object(self, Bucket, Key, Body, ContentType="application/octet-stream"):
        self.objects[Key] = {"Body": Body, "ContentType": ContentType}

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        import io

        return {"Body": io.BytesIO(self.objects[Key]["Body"])}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise KeyError(Key)
        return {"ContentLength": len(self.objects[Key]["Body"])}

    def head_bucket(self, Bucket):
        return {}

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return (
            f"https://acc.r2.cloudflarestorage.com/{Params['Bucket']}/{Params['Key']}"
            f"?X-Amz-Expires={ExpiresIn}&X-Amz-Signature=gia-lap"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
