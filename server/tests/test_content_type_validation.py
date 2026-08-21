"""
Regression test (Post-R1 Phase 3, P3): mot bao cao cu cho rang mot so route
tra 500 thay vi 422 khi Content-Type khong hop le. Da dieu tra lai voi CODE
HIEN TAI (khong tin bao cao cu) va KHONG tai hien duoc — moi route body deu
di qua duong `RequestValidationError` mac dinh cua FastAPI (422) hoac bi
Starlette tu choi giai ma (400), khong co route nao tu parse body thu cong
ma bo qua duong nay. Test nay CHOT LAI hanh vi dung hien tai, de bat regression
neu sau nay co ai vo tinh them mot route tu doc `request.body()`/`request.json()`
ma khong qua Pydantic.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server import tts_bridge
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.tests.voice_stub import dung_registry_gia


def _fake_synthesize(text, voice_id, dest, rate="1.0", chunk_chars=2000,
                     on_progress=None, cancel=None) -> Dict[str, Any]:
    from pathlib import Path
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"\x00" * 4096)
    if on_progress:
        on_progress(1, 1)
    return {"size_bytes": 4096, "total_parts": 1, "voice_id": voice_id, "provider": "mock"}


class ContentTypeValidationTest(unittest.TestCase):
    """Moi route co body deu phai tra 4xx (khong bao gio 500) khi
    Content-Type/than request khong hop le — bat ke co dang nhap hay khong."""

    def setUp(self) -> None:
        dung_registry_gia(self)
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_synth = tts_bridge.synthesize_chapter
        tts_bridge.synthesize_chapter = _fake_synthesize
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        tts_bridge.synthesize_chapter = self._real_synth

    def _register(self, email="a@example.com", password="matkhau123") -> str:
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": password})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["token"]

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _kiem_khong_500(self, method: str, path: str, *, headers=None,
                        content=b"", ten: str = "") -> None:
        r = self.client.request(method, path, headers=headers, content=content)
        self.assertLess(
            r.status_code, 500,
            f"{ten or path}: mong 4xx nhung nhan {r.status_code} — {r.text[:200]}")

    def test_dang_ky_content_type_sai_khong_500(self):
        cases = [
            ("khong Content-Type", {}, b'{"email":"a@example.com","password":"matkhau123"}'),
            ("text/plain", {"Content-Type": "text/plain"}, b'{"email":"a@example.com","password":"matkhau123"}'),
            ("multipart sai", {"Content-Type": "multipart/form-data; boundary=x"}, b"--x\r\n\r\n--x--"),
            ("json cat cut", {"Content-Type": "application/json"}, b'{"email":"a@example'),
            ("body rong", {"Content-Type": "application/json"}, b""),
        ]
        for ten, headers, content in cases:
            with self.subTest(ten=ten):
                self._kiem_khong_500("POST", "/api/auth/register", headers=headers,
                                     content=content, ten=f"register/{ten}")

    def test_tao_truyen_content_type_sai_khong_500(self):
        token = self._register()
        h = self._auth(token)
        cases = [
            ("text/plain", {**h, "Content-Type": "text/plain"}, b'{"title":"x"}'),
            ("json cat cut", {**h, "Content-Type": "application/json"}, b'{"title":"x'),
            ("body rong", {**h, "Content-Type": "application/json"}, b""),
        ]
        for ten, headers, content in cases:
            with self.subTest(ten=ten):
                self._kiem_khong_500("POST", "/api/novels", headers=headers,
                                     content=content, ten=f"novels/{ten}")

    def test_tao_du_an_dich_content_type_sai_khong_500(self):
        token = self._register()
        h = self._auth(token)
        cases = [
            ("text/plain", {**h, "Content-Type": "text/plain"}, b'{"title":"x"}'),
            ("json cat cut", {**h, "Content-Type": "application/json"}, b'{"title":"x'),
        ]
        for ten, headers, content in cases:
            with self.subTest(ten=ten):
                self._kiem_khong_500("POST", "/api/translate/projects", headers=headers,
                                     content=content, ten=f"translate-projects/{ten}")

    def test_utf8_khong_hop_le_tra_4xx_khong_500(self):
        """Chuoi byte KHONG phai UTF-8 hop le trong than request — Starlette
        tu choi giai ma (400), khong phai 500."""
        r = self.client.post(
            "/api/auth/register",
            headers={"Content-Type": "application/json"},
            content=b"\xff\xfe\x00\x01invalid-utf8")
        self.assertLess(r.status_code, 500, r.text[:200])


if __name__ == "__main__":
    unittest.main()
