"""
V4 visual completion, Phan B — "Tiep tuc doc" / "Tiep tuc nghe".

Cung khuon voi `test_avatar.py`: dung MockIdentityAdapter/MockMetadataStore
that qua `server_main`, khong goi mang that.
"""

from __future__ import annotations

import unittest
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.domain import AudioTrack, Chapter, Novel, PublishState


class ContinueProgressTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def user(self, email: str = "doc-gia@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def novel_and_chapter(self, owner_id: str) -> tuple[str, str]:
        novel = server_main.store.create_novel(Novel(
            owner_id=owner_id, title="One Piece Fanfic",
            description="", state=PublishState.PUBLISHED))
        chapter = server_main.store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=owner_id, title="Tập 5",
            order_index=5, state=PublishState.PUBLISHED))
        return novel.novel_id, chapter.chapter_id


class KhongDangNhapTest(ContinueProgressTestCase):
    def test_ca_ba_duong_can_dang_nhap(self):
        for resp in (
            self.client.post("/api/progress/read",
                            json={"novel_id": "n", "chapter_id": "c"}),
            self.client.post("/api/progress/listen",
                            json={"novel_id": "n", "chapter_id": "c",
                                  "position_seconds": 1}),
            self.client.get("/api/progress/continue"),
        ):
            self.assertEqual(resp.status_code, 401)


class TrangThaiRongTest(ContinueProgressTestCase):
    def test_nguoi_dung_moi_chua_co_gi_de_tiep_tuc(self):
        token = self.user()
        resp = self.client.get("/api/progress/continue", headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["reading"])
        self.assertIsNone(resp.json()["listening"])


class BaoCaoDocTest(ContinueProgressTestCase):
    def test_bao_cao_doc_roi_doc_lai_dung_tieu_de(self):
        token = self.user()
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)

        resp = self.client.post(
            "/api/progress/read", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id})
        self.assertEqual(resp.status_code, 200)

        muc = self.client.get(
            "/api/progress/continue", headers=self.auth(token)).json()
        self.assertIsNone(muc["listening"])
        doc = muc["reading"]
        self.assertEqual(doc["novel_title"], "One Piece Fanfic")
        self.assertEqual(doc["chapter_title"], "Tập 5")
        self.assertEqual(doc["chapter_order_index"], 5)

    def test_con_tro_moi_ghi_de_con_tro_cu_khong_cong_don(self):
        token = self.user()
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        _, chapter_a = self.novel_and_chapter(uid)
        novel_b, chapter_b = self.novel_and_chapter(uid)

        self.client.post("/api/progress/read", headers=self.auth(token),
                         json={"novel_id": "bo-qua", "chapter_id": chapter_a})
        self.client.post("/api/progress/read", headers=self.auth(token),
                         json={"novel_id": novel_b, "chapter_id": chapter_b})

        doc = self.client.get(
            "/api/progress/continue", headers=self.auth(token)).json()["reading"]
        # Chi CON TRO GAN NHAT — khong phai danh sach ca hai lan bao cao.
        self.assertEqual(doc["chapter_id"], chapter_b)


class BaoCaoNgheTest(ContinueProgressTestCase):
    def test_vi_tri_va_do_dai_hien_dung(self):
        token = self.user()
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)
        server_main.store.create_track(AudioTrack(
            chapter_id=chapter_id, owner_id=uid, voice_id="v",
            object_key="k", content_hash="h", duration_seconds=1864.0))

        self.client.post(
            "/api/progress/listen", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id,
                  "position_seconds": 1062})

        nghe = self.client.get(
            "/api/progress/continue", headers=self.auth(token)).json()["listening"]
        self.assertEqual(nghe["position_seconds"], 1062)
        self.assertEqual(nghe["duration_seconds"], 1864.0)

    def test_chua_co_track_thi_do_dai_la_none(self):
        token = self.user()
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)

        self.client.post(
            "/api/progress/listen", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id,
                  "position_seconds": 30})

        nghe = self.client.get(
            "/api/progress/continue", headers=self.auth(token)).json()["listening"]
        self.assertIsNone(nghe["duration_seconds"])


class BaoCaoNgheDaiHonMotNgayTest(ContinueProgressTestCase):
    """
    Hoi quy cho bug tran 24 gio: `ListenProgressIn.position_seconds` tung bi
    gioi han `le=86_400` (24h), khien track that dai hon 24h (da xac nhan file
    that toi 63 gio) bi 422 va con tro "Tiep tuc nghe" dong bang o ~24h. Bai
    test nay bao 25h/40h/50h PHAI duoc CHAP NHAN va doc lai dung qua
    /api/progress/continue (round-trip qua store that, khong chi validate
    schema suong).
    """

    def _bao_va_doc_lai(self, position_seconds: float) -> Dict:
        token = self.user(f"nghe-dai-{position_seconds}@example.com")
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)

        resp = self.client.post(
            "/api/progress/listen", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id,
                  "position_seconds": position_seconds})
        self.assertEqual(resp.status_code, 200, resp.text)

        nghe = self.client.get(
            "/api/progress/continue", headers=self.auth(token)).json()["listening"]
        self.assertEqual(nghe["position_seconds"], position_seconds)
        return nghe

    def test_25_gio_duoc_chap_nhan(self):
        self._bao_va_doc_lai(90_000)

    def test_40_gio_duoc_chap_nhan(self):
        self._bao_va_doc_lai(144_000)

    def test_50_gio_duoc_chap_nhan(self):
        self._bao_va_doc_lai(180_000)

    def test_vi_tri_am_van_bi_tu_choi(self):
        token = self.user("nghe-am@example.com")
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)

        resp = self.client.post(
            "/api/progress/listen", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id,
                  "position_seconds": -1})
        self.assertEqual(resp.status_code, 422)

    def test_vi_tri_qua_lon_van_bi_tu_choi(self):
        # Van con mot tran an toan (khong phai 24h) de chan du lieu rac —
        # xem docstring `ListenProgressIn`.
        token = self.user("nghe-qua-lon@example.com")
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)

        resp = self.client.post(
            "/api/progress/listen", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id,
                  "position_seconds": 2_000_000})
        self.assertEqual(resp.status_code, 422)


class ConTroToiNoiDaXoaTest(ContinueProgressTestCase):
    def test_chuong_bi_xoa_thi_module_bien_mat_khong_loi(self):
        token = self.user()
        uid = self.client.get("/api/auth/me", headers=self.auth(token)) \
            .json()["profile"]["user_id"]
        novel_id, chapter_id = self.novel_and_chapter(uid)
        self.client.post(
            "/api/progress/read", headers=self.auth(token),
            json={"novel_id": novel_id, "chapter_id": chapter_id})

        # Con tro tro toi mot chuong KHONG TON TAI (vi du: da bi xoa sau do).
        server_main.identity._profiles[uid].last_read_chapter_id = "chuong-da-xoa"

        resp = self.client.get("/api/progress/continue", headers=self.auth(token))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()["reading"])


if __name__ == "__main__":
    unittest.main()
