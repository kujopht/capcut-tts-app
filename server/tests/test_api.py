"""
Test backend web - chay HOAN TOAN offline.

Khong goi API TTS that: `tts_bridge.synthesize_chapter` duoc thay bang ban gia
lap, nen test khong cham vao CapCut / Edge / Piper.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import JobStatus, job_fingerprint


def _fake_synthesize(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                     on_progress=None, cancel=None) -> Dict[str, Any]:
    """Thay the pipeline TTS that: ghi ra vai byte roi bao thanh cong."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\x00" * 4096)
    if on_progress:
        on_progress(1, 1)
    return {"size_bytes": 4096, "total_parts": 1, "voice_id": voice_id, "provider": "mock"}


class ApiTestCase(unittest.TestCase):
    """Moi test dung mot server sach de khong phu thuoc thu tu chay."""

    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_synth = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = _fake_synthesize
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._real_synth

    # -- tro giup -------------------------------------------------------------

    def _register(self, email="a@example.com", password="matkhau123") -> str:
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": password})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["token"]

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _novel(self, token: str, title="Tiểu thuyết thử") -> str:
        r = self.client.post("/api/novels", json={"title": title}, headers=self._auth(token))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["novel"]["novel_id"]

    def _chapter(self, token: str, novel_id: str, content="Nội dung chương thử nghiệm.") -> str:
        r = self.client.post("/api/chapters",
                             json={"novel_id": novel_id, "title": "Chương 1", "content": content},
                             headers=self._auth(token))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["chapter"]["chapter_id"]


class TestHealth(ApiTestCase):
    def test_health_ok(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_health_never_leaks_secrets(self):
        body = r'{}'.format(self.client.get("/api/health").text).lower()
        for word in ("api_key", "secret", "access_key", "password"):
            self.assertNotIn(word, body, f"healthcheck không được lộ '{word}'")

    def test_health_reports_mock_mode_by_default(self):
        data = self.client.get("/api/health").json()
        self.assertEqual(data["data_backend"], "mock")
        self.assertEqual(data["storage_backend"], "local")


class TestAuth(ApiTestCase):
    def test_register_and_me(self):
        token = self._register()
        r = self.client.get("/api/auth/me", headers=self._auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["email"], "a@example.com")
        self.assertEqual(r.json()["profile"]["tier"], "free")

    def test_duplicate_email_rejected(self):
        self._register()
        r = self.client.post("/api/auth/register",
                             json={"email": "a@example.com", "password": "matkhau123"})
        self.assertEqual(r.status_code, 400)

    def test_short_password_rejected(self):
        r = self.client.post("/api/auth/register",
                             json={"email": "b@example.com", "password": "ngan"})
        self.assertIn(r.status_code, (400, 422))

    def test_wrong_password_rejected(self):
        self._register()
        r = self.client.post("/api/auth/login",
                             json={"email": "a@example.com", "password": "saibet"})
        self.assertEqual(r.status_code, 401)

    def test_no_token_is_401(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_bad_token_is_401(self):
        r = self.client.get("/api/auth/me", headers=self._auth("tok_khong_co_that"))
        self.assertEqual(r.status_code, 401)

    def test_password_is_not_stored_in_plain_text(self):
        self._register(password="matkhaubimat")
        for salt, hashed in server_main.identity._passwords.values():
            self.assertNotIn("matkhaubimat", hashed)


class TestAuthorization(ApiTestCase):
    def test_cannot_add_chapter_to_someone_elses_novel(self):
        owner = self._register("owner@example.com")
        novel_id = self._novel(owner)
        intruder = self._register("intruder@example.com")

        r = self.client.post("/api/chapters",
                             json={"novel_id": novel_id, "title": "Chen ngang", "content": "x"},
                             headers=self._auth(intruder))
        self.assertEqual(r.status_code, 403)

    def test_cannot_publish_someone_elses_novel(self):
        owner = self._register("owner@example.com")
        novel_id = self._novel(owner)
        intruder = self._register("intruder@example.com")
        r = self.client.post(f"/api/novels/{novel_id}/publish", headers=self._auth(intruder))
        self.assertEqual(r.status_code, 403)

    def test_cannot_read_someone_elses_job(self):
        owner = self._register("owner@example.com")
        novel_id = self._novel(owner)
        chapter_id = self._chapter(owner, novel_id)
        job_id = self.client.post("/api/jobs",
                                  json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(owner)).json()["job"]["job_id"]

        intruder = self._register("intruder@example.com")
        r = self.client.get(f"/api/jobs/{job_id}", headers=self._auth(intruder))
        self.assertEqual(r.status_code, 403)

    def test_job_list_only_shows_own_jobs(self):
        owner = self._register("owner@example.com")
        novel_id = self._novel(owner)
        chapter_id = self._chapter(owner, novel_id)
        self.client.post("/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                         headers=self._auth(owner))
        intruder = self._register("intruder@example.com")
        r = self.client.get("/api/jobs", headers=self._auth(intruder))
        self.assertEqual(r.json()["count"], 0)

    def test_library_only_lists_published_novels(self):
        owner = self._register("owner@example.com")
        novel_id = self._novel(owner)
        self.assertEqual(self.client.get("/api/novels").json()["count"], 0)
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self._auth(owner))
        self.assertEqual(self.client.get("/api/novels").json()["count"], 1)

    def test_mine_requires_auth(self):
        self.assertEqual(self.client.get("/api/novels?mine=true").status_code, 401)


class TestJobIdempotency(ApiTestCase):
    def test_same_content_and_voice_reuses_job(self):
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id)

        first = self.client.post("/api/jobs",
                                 json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                 headers=self._auth(token)).json()
        second = self.client.post("/api/jobs",
                                  json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(token)).json()

        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["job"]["job_id"], second["job"]["job_id"])

    def test_different_voice_creates_new_job(self):
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id)

        a = self.client.post("/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                             headers=self._auth(token)).json()
        b = self.client.post("/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v2"},
                             headers=self._auth(token)).json()
        self.assertNotEqual(a["job"]["job_id"], b["job"]["job_id"])
        self.assertFalse(b["reused"])

    def test_different_rate_creates_new_job(self):
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id)
        a = self.client.post("/api/jobs",
                             json={"chapter_id": chapter_id, "voice_id": "mock:v1", "rate": "1.0"},
                             headers=self._auth(token)).json()
        b = self.client.post("/api/jobs",
                             json={"chapter_id": chapter_id, "voice_id": "mock:v1", "rate": "1.25"},
                             headers=self._auth(token)).json()
        self.assertNotEqual(a["job"]["job_id"], b["job"]["job_id"])

    def test_fingerprint_is_stable_and_sensitive(self):
        base = job_fingerprint("noi dung", "edge:x", "1.0", 2000)
        self.assertEqual(base, job_fingerprint("noi dung", "edge:x", "1.0", 2000))
        self.assertNotEqual(base, job_fingerprint("khac", "edge:x", "1.0", 2000))
        self.assertNotEqual(base, job_fingerprint("noi dung", "edge:y", "1.0", 2000))
        self.assertNotEqual(base, job_fingerprint("noi dung", "edge:x", "1.5", 2000))
        self.assertNotEqual(base, job_fingerprint("noi dung", "edge:x", "1.0", 500))


class TestJobLifecycle(ApiTestCase):
    def _wait(self, token: str, job_id: str, timeout: float = 10.0) -> Dict[str, Any]:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{job_id}", headers=self._auth(token)).json()["job"]
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.05)
        self.fail("job không kết thúc trong thời gian chờ")

    def test_job_reaches_completed_and_produces_audio(self):
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id)

        job_id = self.client.post("/api/jobs",
                                  json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(token)).json()["job"]["job_id"]
        job = self._wait(token, job_id)

        self.assertEqual(job["status"], JobStatus.COMPLETED.value)
        self.assertTrue(job["output_key"])
        self.assertEqual(job["progress"], 100)
        self.assertTrue(job["finished_at"])

        # Truyen da xuat ban thi ai cung nghe duoc
        novel_id = self.client.get(
            f"/api/chapters/{chapter_id}", headers=self._auth(token)
        ).json()["chapter"]["novel_id"]
        self.client.post(f"/api/novels/{novel_id}/publish", headers=self._auth(token))

        audio = self.client.get(f"/api/audio/{chapter_id}")
        self.assertEqual(audio.status_code, 200)
        self.assertEqual(audio.headers["content-type"], "audio/mpeg")
        self.assertGreater(len(audio.content), 0)

    def test_failing_provider_marks_job_failed_with_reason(self):
        def boom(*a, **k):
            raise tts_bridge.TtsBridgeError("network_error", "Mất kết nối tới nguồn giọng.")

        tts_bridge.synthesize_chapter = boom
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id)
        job_id = self.client.post("/api/jobs",
                                  json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(token)).json()["job"]["job_id"]
        job = self._wait(token, job_id)

        self.assertEqual(job["status"], JobStatus.FAILED.value)
        self.assertEqual(job["error_kind"], "network_error")
        self.assertIn("Mất kết nối", job["error_message"])
        self.assertIsNone(job["output_key"])

    def test_failed_job_is_not_reused(self):
        def boom(*a, **k):
            raise tts_bridge.TtsBridgeError("network_error", "hỏng")

        tts_bridge.synthesize_chapter = boom
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id)
        first = self.client.post("/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                 headers=self._auth(token)).json()
        self._wait(token, first["job"]["job_id"])

        second = self.client.post("/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                                  headers=self._auth(token)).json()
        self.assertFalse(second["reused"], "job thất bại phải được chạy lại, không tái dùng")

    def test_empty_chapter_rejected(self):
        token = self._register()
        novel_id = self._novel(token)
        chapter_id = self._chapter(token, novel_id, content="   ")
        r = self.client.post("/api/jobs", json={"chapter_id": chapter_id, "voice_id": "mock:v1"},
                             headers=self._auth(token))
        self.assertEqual(r.status_code, 400)

    def test_audio_missing_returns_404(self):
        self.assertEqual(self.client.get("/api/audio/chp_khong_co").status_code, 404)


class TestNoVoiceFallback(ApiTestCase):
    def test_bridge_never_substitutes_a_voice(self):
        """Giong khong ton tai phai bao loi, KHONG duoc am tham doi giong khac."""
        tts_bridge.synthesize_chapter = self._real_synth
        with self.assertRaises(tts_bridge.TtsBridgeError) as ctx:
            tts_bridge.resolve_voice("khong_ton_tai:xyz")
        self.assertEqual(ctx.exception.kind, "voice_not_found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
