"""POST /api/import/authorized — Authorized Import ('Import my fanfic')."""
from __future__ import annotations

import base64
import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockImportRecordStore, MockMetadataStore
from server.fandom_registry import FandomRegistry


class AuthorizedImportRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.fandom_registry = FandomRegistry()
        server_main.authorized_import_service.__init__(
            server_main.store, MockImportRecordStore(),
            tao_chuong=server_main._tao_chuong_cho_truyen,
            fandom_registry=server_main.fandom_registry,
            spool_root=server_main.authorized_import_service._spool_root)
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "tacgia@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def _b64(self, text: str) -> str:
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    def test_nhap_txt_that_tra_ve_novel_that_o_draft(self):
        token = self.user()
        raw = "Chương 1\nNội dung chương một.\nChương 2\nNội dung chương hai."
        resp = self.client.post(
            "/api/import/authorized",
            json={
                "filename": "truyen.txt", "format": "txt",
                "base64": self._b64(raw), "title": "Truyện của tôi",
                "rights_basis": "author", "fandom_names": ["Naruto"],
            },
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["novel"]["state"], "draft")
        self.assertEqual(len(body["chapters"]), 2)
        self.assertEqual(body["import_record"]["rights_basis"], "author")
        self.assertEqual(len(body["novel"]["fandom_ids"]), 1)

    def test_novel_thuoc_ve_nguoi_goi_that_khong_lay_tu_body(self):
        token = self.user()
        resp = self.client.post(
            "/api/import/authorized",
            json={"filename": "t.txt", "format": "txt",
                 "base64": self._b64("Chương 1\nND."), "title": "T",
                 "rights_basis": "author"},
            headers=self.auth(token))
        novel_id = resp.json()["novel"]["novel_id"]
        get_resp = self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))
        self.assertEqual(get_resp.status_code, 200)  # chi chu that moi doc duoc DRAFT

    def test_khong_token_bi_tu_choi_401(self):
        resp = self.client.post(
            "/api/import/authorized",
            json={"filename": "t.txt", "format": "txt",
                 "base64": self._b64("x"), "title": "T", "rights_basis": "author"})
        self.assertEqual(resp.status_code, 401)

    def test_rights_basis_khong_hop_le_tra_ve_400(self):
        token = self.user()
        resp = self.client.post(
            "/api/import/authorized",
            json={"filename": "t.txt", "format": "txt",
                 "base64": self._b64("Chương 1\nND."), "title": "T",
                 "rights_basis": "khong-hop-le"},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_base64_hong_tra_ve_400(self):
        token = self.user()
        resp = self.client.post(
            "/api/import/authorized",
            json={"filename": "t.txt", "format": "txt",
                 "base64": "!!!khong-phai-base64!!!", "title": "T",
                 "rights_basis": "author"},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_dinh_dang_khong_ho_tro_tra_ve_400(self):
        token = self.user()
        resp = self.client.post(
            "/api/import/authorized",
            json={"filename": "t.pdf", "format": "pdf",
                 "base64": self._b64("data"), "title": "T",
                 "rights_basis": "author"},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_fandom_chua_biet_khong_chan_nhap_nhung_duoc_bao_ro(self):
        """Mission: 'Never silently invent a fandom if confidence is poor' —
        nghia la KHONG tu doan mot fandom sai, khong phai chan ca luot nhap.
        Ten chua biet duoc bao trong `fandom_match.unmatched` de nguoi dung
        tu sua sau (PATCH), Novel van duoc tao that o DRAFT."""
        token = self.user()
        resp = self.client.post(
            "/api/import/authorized",
            json={"filename": "t.txt", "format": "txt",
                 "base64": self._b64("Chương 1\nND."), "title": "T",
                 "rights_basis": "author", "fandom_names": ["Khong Ton Tai"]},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["novel"]["fandom_ids"], [])
        self.assertEqual(body["fandom_match"]["unmatched"], ["Khong Ton Tai"])


if __name__ == "__main__":
    unittest.main()
