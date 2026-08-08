"""
Test endpoint `/api/audio/{chapter_id}/url`.

Vi sao co endpoint nay: the `<audio src>` khong gui duoc header
`Authorization`, con `fetch()` co header do thi chet o buoc redirect sang R2
vi bucket khong mo CORS. Da kiem chung tren trinh duyet that:
`fetch` -> "Failed to fetch"; the `<audio>` -> MEDIA_ERR_SRC_NOT_SUPPORTED.

Diem quan trong nhat: endpoint nay KHONG duoc noi long quyen so voi
`/api/audio/{chapter_id}`.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server.tests.voice_stub import dung_registry_gia
from server import tts_bridge
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore


def _fake_synthesize(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                     on_progress=None, cancel=None) -> Dict[str, Any]:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\xff\xf3d" + b"\x00" * 4093)
    if on_progress:
        on_progress(1, 1)
    return {"size_bytes": 4096, "total_parts": 1, "voice_id": voice_id,
            "provider": "mock"}


class SignedStorage(LocalStorageAdapter):
    """Gia lap kho co URL ky (nhu R2) de di duong `url`."""

    mode = "r2"
    last_download_name: Optional[str] = None

    def signed_url(self, key, expires_seconds=3600, download_name=None):
        SignedStorage.last_download_name = download_name
        extra = "&rcd=attachment" if download_name else ""
        return (f"https://khong-co-that.example/{key}"
                f"?X-Amz-Signature=gia-lap&X-Amz-Expires={expires_seconds}{extra}")


class AudioUrlTestCase(unittest.TestCase):
    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        self._real_synth = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = _fake_synthesize
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._real_synth
        server_main.storage = self._real_storage

    # -- tien ich -------------------------------------------------------------

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _user(self, email: str) -> str:
        return self.client.post("/api/auth/register",
                                json={"email": email, "password": "matkhau123"}
                                ).json()["token"]

    def _chapter_with_audio(self, token: str):
        novel = self.client.post("/api/novels", json={"title": "T"},
                                 headers=self._auth(token)).json()["novel"]["novel_id"]
        chapter = self.client.post(
            "/api/chapters",
            json={"novel_id": novel, "title": "C", "content": "Nội dung."},
            headers=self._auth(token),
        ).json()["chapter"]["chapter_id"]
        job = self.client.post("/api/jobs",
                               json={"chapter_id": chapter, "voice_id": "mock:v1"},
                               headers=self._auth(token)).json()["job"]["job_id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            j = self.client.get(f"/api/jobs/{job}",
                                headers=self._auth(token)).json()["job"]
            if j["status"] in ("completed", "failed"):
                break
            time.sleep(0.02)
        return novel, chapter


class TestAuthorizationIsIdentical(AudioUrlTestCase):
    """Endpoint URL phai chan y het endpoint stream."""

    def test_draft_requires_authentication(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        self.assertEqual(self.client.get(f"/api/audio/{chapter}/url").status_code, 401)

    def test_draft_denied_to_other_user(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        intruder = self._user("ke-la@example.com")
        r = self.client.get(f"/api/audio/{chapter}/url", headers=self._auth(intruder))
        self.assertEqual(r.status_code, 403)

    def test_owner_can_get_url_for_own_draft(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        r = self.client.get(f"/api/audio/{chapter}/url", headers=self._auth(owner))
        self.assertEqual(r.status_code, 200)

    def test_published_chapter_url_is_public(self):
        owner = self._user("chu@example.com")
        novel, chapter = self._chapter_with_audio(owner)
        self.client.post(f"/api/novels/{novel}/publish", headers=self._auth(owner))
        self.assertEqual(self.client.get(f"/api/audio/{chapter}/url").status_code, 200)

    def test_unknown_chapter_is_404(self):
        self.assertEqual(
            self.client.get("/api/audio/chp_khong_co/url").status_code, 404)

    def test_chapter_without_audio_is_404(self):
        token = self._user("chu@example.com")
        novel = self.client.post("/api/novels", json={"title": "T"},
                                 headers=self._auth(token)).json()["novel"]["novel_id"]
        chapter = self.client.post(
            "/api/chapters", json={"novel_id": novel, "title": "C", "content": "x"},
            headers=self._auth(token)).json()["chapter"]["chapter_id"]
        r = self.client.get(f"/api/audio/{chapter}/url", headers=self._auth(token))
        self.assertEqual(r.status_code, 404)

    def test_same_status_as_stream_endpoint_in_every_case(self):
        """Hai endpoint phai tra CUNG ma trang thai o moi tinh huong."""
        owner = self._user("chu@example.com")
        novel, chapter = self._chapter_with_audio(owner)
        intruder = self._user("ke-la@example.com")

        cases = [
            ("an danh", None),
            ("nguoi la", self._auth(intruder)),
            ("chu so huu", self._auth(owner)),
        ]
        for label, headers in cases:
            a = self.client.get(f"/api/audio/{chapter}", headers=headers or {})
            b = self.client.get(f"/api/audio/{chapter}/url", headers=headers or {})
            self.assertEqual(a.status_code, b.status_code,
                             f"{label}: stream={a.status_code} url={b.status_code}")

        self.client.post(f"/api/novels/{novel}/publish", headers=self._auth(owner))
        a = self.client.get(f"/api/audio/{chapter}")
        b = self.client.get(f"/api/audio/{chapter}/url")
        self.assertEqual(a.status_code, b.status_code)


class TestLocalStorageShape(AudioUrlTestCase):
    """Kho cuc bo khong co URL ky -> phai chi duong stream."""

    def test_local_mode_returns_stream_url(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        body = self.client.get(f"/api/audio/{chapter}/url",
                               headers=self._auth(owner)).json()
        self.assertIsNone(body["url"])
        self.assertEqual(body["stream_url"], f"/api/audio/{chapter}")
        self.assertIsNone(body["expires_in"])
        self.assertGreater(body["size_bytes"], 0)


class TestSignedStorageShape(AudioUrlTestCase):
    """Kho co URL ky (R2) -> tra URL de gan thang vao <audio src>."""

    def setUp(self) -> None:
        dung_registry_gia(self)
        super().setUp()
        server_main.storage = SignedStorage(Path(tempfile.mkdtemp()))
        SignedStorage.last_download_name = None

    def test_returns_signed_url_and_no_stream_url(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        body = self.client.get(f"/api/audio/{chapter}/url",
                               headers=self._auth(owner)).json()
        self.assertIn("X-Amz-Signature", body["url"])
        self.assertIsNone(body["stream_url"])
        self.assertEqual(body["expires_in"], server_main.AUDIO_URL_TTL_SECONDS)

    def test_url_is_short_lived(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        body = self.client.get(f"/api/audio/{chapter}/url",
                               headers=self._auth(owner)).json()
        self.assertIn(f"X-Amz-Expires={server_main.AUDIO_URL_TTL_SECONDS}", body["url"])

    def test_download_flag_asks_for_attachment(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        self.client.get(f"/api/audio/{chapter}/url?download=true",
                        headers=self._auth(owner))
        self.assertEqual(SignedStorage.last_download_name, f"{chapter}.mp3")

    def test_without_download_flag_no_attachment(self):
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        self.client.get(f"/api/audio/{chapter}/url", headers=self._auth(owner))
        self.assertIsNone(SignedStorage.last_download_name)

    def test_response_never_leaks_the_object_key_owner_prefix(self):
        """URL co chua key, nhung khong duoc lo them gi ngoai nhung gi can."""
        owner = self._user("chu@example.com")
        _, chapter = self._chapter_with_audio(owner)
        body = self.client.get(f"/api/audio/{chapter}/url",
                               headers=self._auth(owner)).json()
        self.assertEqual(set(body), {"url", "stream_url", "expires_in", "size_bytes"})


class TestR2AdapterDownloadName(unittest.TestCase):
    """`R2StorageAdapter.signed_url` phai gan Content-Disposition khi duoc yeu cau."""

    def _adapter(self):
        from server.config import R2Settings
        from server.r2_adapter import R2StorageAdapter

        adapter = R2StorageAdapter.__new__(R2StorageAdapter)
        adapter._settings = R2Settings(account_id="a", access_key_id="k",
                                       secret_access_key="s", bucket="b")
        adapter._bucket = "b"
        adapter._client = _FakeS3()
        return adapter

    def test_no_disposition_by_default(self):
        adapter = self._adapter()
        adapter.signed_url("a.mp3")
        self.assertNotIn("ResponseContentDisposition", adapter._client.last_params)

    def test_disposition_added_when_download_name_given(self):
        adapter = self._adapter()
        adapter.signed_url("a.mp3", download_name="chuong-1.mp3")
        self.assertEqual(
            adapter._client.last_params["ResponseContentDisposition"],
            'attachment; filename="chuong-1.mp3"')

    def test_quotes_are_stripped_from_filename(self):
        adapter = self._adapter()
        adapter.signed_url("a.mp3", download_name='ac"y\\.mp3')
        self.assertEqual(
            adapter._client.last_params["ResponseContentDisposition"],
            'attachment; filename="acy.mp3"')


class _FakeS3:
    def __init__(self):
        self.last_params: Dict[str, Any] = {}

    def generate_presigned_url(self, op, Params, ExpiresIn):
        self.last_params = dict(Params)
        return f"https://khong-co-that.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"


if __name__ == "__main__":
    unittest.main(verbosity=2)
