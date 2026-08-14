"""
V4 visual completion, vong 2 — XP that duoc cong tu hanh dong THAT: xuat
ban truyen, them chuong vao truyen da xuat ban, mot lan nghe hop le.
"""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack, Chapter, Novel, PublishState
from server.gamification_store import MockGamificationStore


class XpWiringTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.gamification_store = MockGamificationStore()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "u@example.com") -> tuple[str, str]:
        resp = self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"})
        body = resp.json()
        return body["token"], body["profile"]["user_id"]

    def xp(self, uid: str) -> int:
        return server_main.gamification_store.get_progress(uid).xp


class PublishNovelXpTest(XpWiringTestCase):
    def test_xuat_ban_truyen_moi_cong_xp_mot_lan(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(owner_id=uid, title="Truyện"))
        resp = self.client.post(f"/api/novels/{novel.novel_id}/publish",
                                headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.xp(uid), 50)  # publish_first_novel

    def test_xuat_ban_lai_idempotent_khong_cong_them_xp(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(owner_id=uid, title="Truyện"))
        self.client.post(f"/api/novels/{novel.novel_id}/publish", headers=self.auth(token))
        self.client.post(f"/api/novels/{novel.novel_id}/publish", headers=self.auth(token))
        self.assertEqual(self.xp(uid), 50)

    def test_xuat_ban_truyen_co_san_chuong_cong_xp_cho_tung_chuong(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(owner_id=uid, title="Truyện"))
        server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="C1"))
        server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="C2"))
        self.client.post(f"/api/novels/{novel.novel_id}/publish", headers=self.auth(token))
        # 50 (truyen dau) + 20 (chuong dau) + 10 + 10 (hai chuong) = 90
        self.assertEqual(self.xp(uid), 90)

    def test_truyen_thu_hai_khong_cong_lai_publish_first_novel(self):
        token, uid = self.user()
        n1 = server_main.store.create_novel(Novel(owner_id=uid, title="A"))
        n2 = server_main.store.create_novel(Novel(owner_id=uid, title="B"))
        self.client.post(f"/api/novels/{n1.novel_id}/publish", headers=self.auth(token))
        xp_sau_truyen_1 = self.xp(uid)
        self.client.post(f"/api/novels/{n2.novel_id}/publish", headers=self.auth(token))
        # Chi +0 tu "publish_first_novel" (da cong roi), khong co chuong nao
        # trong truyen B nen khong co XP chuong.
        self.assertEqual(self.xp(uid), xp_sau_truyen_1)


class CreateChapterXpTest(XpWiringTestCase):
    def test_them_chuong_vao_truyen_nhap_chua_cong_xp(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(Novel(owner_id=uid, title="Truyện"))
        self.client.post("/api/chapters", headers=self.auth(token),
                         json={"novel_id": novel.novel_id, "title": "C1",
                               "content": "noi dung"})
        self.assertEqual(self.xp(uid), 0)

    def test_them_chuong_vao_truyen_da_xuat_ban_cong_xp_ngay(self):
        token, uid = self.user()
        novel = server_main.store.create_novel(
            Novel(owner_id=uid, title="Truyện", state=PublishState.PUBLISHED))
        resp = self.client.post("/api/chapters", headers=self.auth(token),
                                json={"novel_id": novel.novel_id, "title": "C1",
                                      "content": "noi dung"})
        self.assertEqual(resp.status_code, 201)
        # publish_first_chapter (20) + publish_chapter (10) = 30
        self.assertEqual(self.xp(uid), 30)


class ListenXpTest(XpWiringTestCase):
    def _chuong_co_audio(self, uid: str):
        novel = server_main.store.create_novel(
            Novel(owner_id=uid, title="Truyện", state=PublishState.PUBLISHED))
        chapter = server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=uid, title="C1"))
        server_main.store.create_track(AudioTrack(
            chapter_id=chapter.chapter_id, owner_id=uid, voice_id="v",
            object_key="k", content_hash="h", duration_seconds=60.0))
        return chapter

    def test_nghe_hop_le_cong_xp_cho_nguoi_nghe_khong_phai_tac_gia(self):
        _, tac_gia = self.user("tac-gia@example.com")
        token_nguoi_nghe, nguoi_nghe = self.user("nguoi-nghe@example.com")
        chapter = self._chuong_co_audio(tac_gia)

        resp = self.client.post("/api/listens", headers=self.auth(token_nguoi_nghe),
                                json={"chapter_id": chapter.chapter_id,
                                      "listened_seconds": 45})
        self.assertTrue(resp.json()["credited"])
        self.assertEqual(self.xp(nguoi_nghe), 5)  # listen_milestone_qualified
        self.assertEqual(self.xp(tac_gia), 0)  # XP khong roi vao tac gia

    def test_nghe_khach_an_danh_khong_cong_xp_cho_ai(self):
        # `evaluate_listen` KHONG tinh khach an danh (V1) — nen ca uy tin tac
        # gia LAN xp nguoi nghe deu khong co gi de cong.
        _, tac_gia = self.user("tac-gia2@example.com")
        chapter = self._chuong_co_audio(tac_gia)
        resp = self.client.post("/api/listens",
                                json={"chapter_id": chapter.chapter_id,
                                      "listened_seconds": 45})
        self.assertFalse(resp.json()["credited"])
        self.assertEqual(self.xp(tac_gia), 0)

    def test_nghe_lai_cung_chuong_trong_24h_khong_cong_them_xp(self):
        _, tac_gia = self.user("tac-gia3@example.com")
        token, nguoi_nghe = self.user("nguoi-nghe3@example.com")
        chapter = self._chuong_co_audio(tac_gia)
        self.client.post("/api/listens", headers=self.auth(token),
                         json={"chapter_id": chapter.chapter_id, "listened_seconds": 45})
        resp2 = self.client.post("/api/listens", headers=self.auth(token),
                                 json={"chapter_id": chapter.chapter_id, "listened_seconds": 45})
        self.assertFalse(resp2.json()["credited"])
        self.assertEqual(self.xp(nguoi_nghe), 5)


if __name__ == "__main__":
    unittest.main()
