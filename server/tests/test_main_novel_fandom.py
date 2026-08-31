"""
Anime Fanfic Production Canary — `fandom_names` -> `fandom_ids` qua
`POST /api/novels` / `PATCH /api/novels/{id}`, va `publication_mode`.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.fandom_registry import FandomRegistry


class NovelFandomTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.fandom_registry = FandomRegistry()
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def test_tao_novel_voi_fandom_names_duoc_chuan_hoa(self):
        token = self.user()
        resp = self.client.post(
            "/api/novels",
            json={"title": "Fic thu nghiem", "fandom_names": ["BNHA", "Naruto"]},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 201)
        novel = resp.json()["novel"]
        self.assertEqual(len(novel["fandom_ids"]), 2)
        self.assertEqual(novel["publication_mode"], "full_text")

    def test_ten_fandom_chua_biet_tra_ve_400(self):
        token = self.user()
        resp = self.client.post(
            "/api/novels",
            json={"title": "Fic la", "fandom_names": ["Mot Fandom Khong Ton Tai"]},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_publication_mode_metadata_only_va_external_fields(self):
        token = self.user()
        resp = self.client.post(
            "/api/novels",
            json={
                "title": "Ninja's Hero Academia",
                "fandom_names": ["Naruto", "My Hero Academia"],
                "publication_mode": "metadata_only",
                "external_author_name": "some-author",
                "external_source_url": "https://www.fanfiction.net/s/13530962/1/Ninja-s-Hero-Academia",
                "external_chapter_count": 25,
                "language": "en",
            },
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 201)
        novel = resp.json()["novel"]
        self.assertEqual(novel["publication_mode"], "metadata_only")
        self.assertEqual(novel["external_chapter_count"], 25)
        self.assertTrue(novel["external_source_url"])

    def test_publication_mode_khong_hop_le_tra_ve_400(self):
        token = self.user()
        resp = self.client.post(
            "/api/novels",
            json={"title": "T", "publication_mode": "khong-hop-le"},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

    def test_patch_them_fandom_names_sau_khi_tao(self):
        token = self.user()
        novel_id = self.client.post(
            "/api/novels", json={"title": "T"}, headers=self.auth(token)
        ).json()["novel"]["novel_id"]

        resp = self.client.patch(
            f"/api/novels/{novel_id}", json={"fandom_names": ["One Piece"]},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["novel"]["fandom_ids"]), 1)

    def test_patch_fandom_chua_biet_khong_lam_hong_du_lieu_da_co(self):
        token = self.user()
        novel_id = self.client.post(
            "/api/novels", json={"title": "T", "fandom_names": ["Bleach"]},
            headers=self.auth(token)
        ).json()["novel"]["novel_id"]

        resp = self.client.patch(
            f"/api/novels/{novel_id}", json={"fandom_names": ["Khong Ton Tai"]},
            headers=self.auth(token))
        self.assertEqual(resp.status_code, 400)

        get_resp = self.client.get(f"/api/novels/{novel_id}", headers=self.auth(token))
        self.assertEqual(len(get_resp.json()["novel"]["fandom_ids"]), 1)


if __name__ == "__main__":
    unittest.main()
