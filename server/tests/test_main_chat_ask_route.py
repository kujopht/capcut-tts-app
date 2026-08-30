"""Fanfic AI Chat V1 - route `/api/chat/ask` (server/main.py)."""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore


class ChatAskTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "doc-gia@example.com") -> str:
        resp = self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"})
        return resp.json()["token"]


class KhongDangNhapTest(ChatAskTestCase):
    def test_khong_token_bi_tu_choi(self):
        resp = self.client.post("/api/chat/ask", json={
            "novel_id": "n1", "question": "hello"})
        self.assertEqual(resp.status_code, 401)


class DangNhapRoiTest(ChatAskTestCase):
    def test_cau_hoi_hop_le_tra_ve_200_dung_hinh_dang(self):
        token = self.user()
        resp = self.client.post(
            "/api/chat/ask",
            json={"novel_id": "n1", "question": "What happened?"},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("answer", body)
        self.assertIn("citations", body)
        self.assertIn("evidence_insufficient", body)

    def test_qua_dai_question_bi_tu_choi_422(self):
        """Bai quyet dinh: review doc lap tim thay ChatAskIn khong gioi han
        do dai truoc ban sua nay - mot client co the gui cau hoi hang
        megabyte, bi nhet vao prompt roi gui cho nha cung cap LLM that."""
        token = self.user()
        resp = self.client.post(
            "/api/chat/ask",
            json={"novel_id": "n1", "question": "x" * 3000},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 422)

    def test_qua_dai_selected_text_bi_tu_choi_422(self):
        token = self.user()
        resp = self.client.post(
            "/api/chat/ask",
            json={"novel_id": "n1", "question": "explain",
                 "selected_text": "x" * 10000},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 422)

    def test_question_vua_duoi_gioi_han_van_duoc_chap_nhan(self):
        token = self.user()
        resp = self.client.post(
            "/api/chat/ask",
            json={"novel_id": "n1", "question": "x" * 2000},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
