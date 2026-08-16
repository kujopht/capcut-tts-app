"""
Tang HTTP cua tang xa hoi — `server/main.py`.

Tang dich vu da duoc kiem ky o `test_social_service.py`. Bo nay kiem nhung thu
CHI tang HTTP quyet dinh, va khong lap lai nghiep vu:

  - MA TRANG THAI. 401 khac 403 khac 404 khac 429, va moi lan lan lon la mot
    thong tin bi lo hoac mot nguoi dung khong hieu vi sao bi tu choi.
  - AI la nguoi goi. Luon lay tu TOKEN, khong bao gio tu body — mot route nhan
    `user_id` tu body la mot route ai cung dong vai duoc.
  - CONG QUAN TRI. Anon 401, nguoi thuong 403, quan tri di qua.
"""

from __future__ import annotations

import base64
import os
import unittest

os.environ.setdefault("DATA_BACKEND", "mock")
os.environ.setdefault("STORAGE_BACKEND", "local")

from fastapi.testclient import TestClient       # noqa: E402

from server import main                          # noqa: E402
from server.domain import AuthorStatus, Novel, PublishState   # noqa: E402
from server.social import HanMuc                 # noqa: E402


def _anh_base64(so_byte: int = 500) -> str:
    return base64.b64encode(b"x" * so_byte).decode()


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main.app)
        # Kho mock song trong vong doi tien trinh, nen moi bai phai bat dau tu
        # mot kho SACH — neu khong thi thu tu chay quyet dinh ket qua.
        from server.adapters import MockIdentityAdapter, MockMetadataStore
        from server.creator_service import CreatorService
        from server.social_service import SocialService

        main.identity = MockIdentityAdapter()
        main.store = MockMetadataStore()
        main.social = SocialService(main.identity, main.store, main.storage)
        main.creators = CreatorService(main.identity, main.store)
        main.creators.on_decision = main.social.notify_author_decision

        self.an, self.tk_an = self._nguoi("an@vidu.vn", "An")
        self.binh, self.tk_binh = self._nguoi("binh@vidu.vn", "Bình")
        self.qt, self.tk_qt = self._nguoi("qt@vidu.vn", "Quản trị")
        # Quyen quan tri do BIEN MOI TRUONG quyet dinh — khong co duong nao trong
        # ung dung de tu phong minh. O day ta doi chinh cau hinh cua tien trinh.
        self._admin_cu = main.settings.admin_user_ids
        import dataclasses
        main.settings = dataclasses.replace(
            main.settings, admin_user_ids=(self.qt.user_id,))

        self.an.author_status = AuthorStatus.APPROVED
        main.identity.save_profile(self.an)
        self.truyen = main.store.create_novel(Novel(
            owner_id=self.an.user_id, title="Hải Tặc Mũ Rơm",
            state=PublishState.PUBLISHED))

    def tearDown(self) -> None:
        import dataclasses
        main.settings = dataclasses.replace(main.settings,
                                            admin_user_ids=self._admin_cu)

    def _goi(self, method: str, duong: str, *, headers=None, json=None):
        """
        Goi mot route ma khong phai nho `get`/`delete` co nhan `json=` hay khong.

        `TestClient.get()` va `.delete()` KHONG nhan tham so `json` — chung nem
        `TypeError`. Boc lai o mot cho de cac bai kiem ma trang thai chay vong
        qua nhieu route ma khong phai re nhanh theo phuong thuc.
        """
        kw = {}
        if headers is not None:
            kw["headers"] = headers
        if json is not None and method in ("post", "patch", "put"):
            kw["json"] = json
        return getattr(self.client, method)(duong, **kw)

    def _nguoi(self, email: str, ten: str):
        ho_so = main.identity.register(email, "MatKhau123", ten)
        token = main.identity.login(email, "MatKhau123")
        return ho_so, {"Authorization": f"Bearer {token}"}

    def _bai(self, headers=None, text="Một bài đăng."):
        r = self.client.post("/api/posts", json={"text": text},
                             headers=headers or self.tk_an)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["post"]


class GioiHanTest(Nen):
    def test_api_limits_cong_khai(self):
        r = self.client.get("/api/limits")
        self.assertEqual(r.status_code, 200)
        self.assertIn("post_max_chars", r.json())

    def test_api_limits_kem_chinh_sach_anh(self):
        goi = self.client.get("/api/limits").json()
        self.assertIn("post", goi["image"])
        self.assertGreater(goi["image"]["post"]["max_bytes"], 0)


class DangNhapTest(Nen):
    """Moi route GHI deu doi dang nhap. Thieu mot cai la mot cong mo."""

    def test_cac_route_ghi_deu_tra_401_khi_chua_dang_nhap(self):
        bai = self._bai()
        goi = [
            ("post", f"/api/users/{self.binh.user_id}/follow"),
            ("delete", f"/api/users/{self.binh.user_id}/follow"),
            ("post", f"/api/novels/{self.truyen.novel_id}/follow"),
            ("post", "/api/posts"),
            ("patch", f"/api/posts/{bai['post_id']}"),
            ("delete", f"/api/posts/{bai['post_id']}"),
            ("post", f"/api/posts/{bai['post_id']}/like"),
            ("delete", f"/api/posts/{bai['post_id']}/like"),
            ("post", f"/api/posts/{bai['post_id']}/comments"),
            ("post", "/api/reports"),
            ("get", "/api/notifications"),
            ("get", "/api/notifications/unread"),
            ("post", "/api/notifications/read-all"),
            ("get", "/api/account/social"),
        ]
        for method, duong in goi:
            with self.subTest(duong=duong):
                r = self._goi(method, duong, json={})
                self.assertEqual(r.status_code, 401, f"{method} {duong}")

    def test_token_rac_cung_la_401(self):
        r = self.client.get("/api/notifications",
                            headers={"Authorization": "Bearer rac"})
        self.assertEqual(r.status_code, 401)

    def test_bang_tin_va_bai_xem_duoc_khi_CHUA_dang_nhap(self):
        """Mot trang cong dong tra 401 cho khach la mot canh cua dong."""
        bai = self._bai()
        self.assertEqual(self.client.get("/api/feed").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/posts/{bai['post_id']}").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/posts/{bai['post_id']}/comments")
            .status_code, 200)


class NguoiGoiTuTokenTest(Nen):
    def test_bai_luon_thuoc_ve_chu_token(self):
        """
        Body KHONG co truong tac gia. Neu mot ngay nao do ai them vao, bai nay
        se do — va do la muc dich cua no.
        """
        r = self.client.post("/api/posts",
                             json={"text": "Thử", "author_user_id": self.binh.user_id},
                             headers=self.tk_an)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["post"]["author_user_id"], self.an.user_id)

    def test_khong_gia_mao_duoc_luot_thich_cua_nguoi_khac(self):
        bai = self._bai()
        self.client.post(f"/api/posts/{bai['post_id']}/like",
                         json={"user_id": self.binh.user_id}, headers=self.tk_an)
        # An thich, khong phai Binh.
        r = self.client.get("/api/feed", headers=self.tk_binh)
        self.assertFalse(r.json()["items"][0]["liked"])


class MaTrangThaiTest(Nen):
    def test_sua_bai_nguoi_khac_la_403(self):
        bai = self._bai()
        r = self.client.patch(f"/api/posts/{bai['post_id']}",
                              json={"text": "phá"}, headers=self.tk_binh)
        self.assertEqual(r.status_code, 403)

    def test_bai_khong_ton_tai_la_404(self):
        r = self.client.get("/api/posts/khong-co-bai-nay")
        self.assertEqual(r.status_code, 404)

    def test_tu_theo_doi_minh_la_400(self):
        r = self.client.post(f"/api/users/{self.an.user_id}/follow",
                             json={}, headers=self.tk_an)
        self.assertEqual(r.status_code, 400)

    def test_vuot_han_muc_la_429(self):
        """
        429 chu khong phai 500. Mot nguoi bam nhanh can doc duoc "thu lai sau",
        khong phai mot loi may chu.
        """
        from server.social_service import SocialService

        main.social = SocialService(main.identity, main.store, main.storage,
                                    han_muc={"post": HanMuc(so_lan=1, phut=60)})
        self.client.post("/api/posts", json={"text": "Một"}, headers=self.tk_an)
        r = self.client.post("/api/posts", json={"text": "Hai"},
                             headers=self.tk_an)
        self.assertEqual(r.status_code, 429)

    def test_bai_qua_dai_bi_pydantic_chan_la_422(self):
        r = self.client.post("/api/posts", json={"text": "x" * 5000},
                             headers=self.tk_an)
        self.assertEqual(r.status_code, 422)

    def test_binh_luan_rong_la_422(self):
        bai = self._bai()
        r = self.client.post(f"/api/posts/{bai['post_id']}/comments",
                             json={"text": ""}, headers=self.tk_binh)
        self.assertEqual(r.status_code, 422)

    def test_anh_base64_sai_la_400(self):
        r = self.client.post("/api/posts",
                             json={"text": "", "image_base64": "!!!khong-phai-base64!!!",
                                   "image_mime": "image/webp"},
                             headers=self.tk_an)
        self.assertEqual(r.status_code, 400)

    def test_anh_qua_to_la_400(self):
        r = self.client.post("/api/posts", json={
            "text": "", "image_base64": _anh_base64(2 * 1024 * 1024),
            "image_mime": "image/webp"}, headers=self.tk_an)
        self.assertEqual(r.status_code, 400)


class LuongDayDuTest(Nen):
    def test_theo_doi_roi_bang_tin_thanh_ca_nhan_hoa(self):
        self._bai(headers=self.tk_an, text="Của An")
        r = self.client.get("/api/feed", headers=self.tk_binh)
        self.assertFalse(r.json()["personalized"])
        self.client.post(f"/api/users/{self.an.user_id}/follow", json={},
                         headers=self.tk_binh)
        r = self.client.get("/api/feed", headers=self.tk_binh)
        self.assertTrue(r.json()["personalized"])

    def test_thich_binh_luan_va_thong_bao(self):
        bai = self._bai()
        self.client.post(f"/api/posts/{bai['post_id']}/like", json={},
                         headers=self.tk_binh)
        self.client.post(f"/api/posts/{bai['post_id']}/comments",
                         json={"text": "Hay quá"}, headers=self.tk_binh)
        r = self.client.get("/api/notifications/unread", headers=self.tk_an)
        self.assertEqual(r.json()["unread"], 2)

    def test_danh_dau_da_doc_het(self):
        bai = self._bai()
        self.client.post(f"/api/posts/{bai['post_id']}/like", json={},
                         headers=self.tk_binh)
        r = self.client.post("/api/notifications/read-all", json={},
                             headers=self.tk_an)
        self.assertEqual(r.json()["unread"], 0)

    def test_tra_loi_mot_cap(self):
        bai = self._bai()
        goc = self.client.post(f"/api/posts/{bai['post_id']}/comments",
                               json={"text": "Hỏi"},
                               headers=self.tk_binh).json()["comment"]
        r = self.client.post(f"/api/posts/{bai['post_id']}/comments",
                             json={"text": "Đáp",
                                   "parent_id": goc["comment_id"]},
                             headers=self.tk_an)
        self.assertEqual(r.status_code, 201)
        tl = r.json()["comment"]
        r = self.client.post(f"/api/posts/{bai['post_id']}/comments",
                             json={"text": "Nữa", "parent_id": tl["comment_id"]},
                             headers=self.tk_binh)
        self.assertEqual(r.status_code, 400)

    def test_dang_bai_kem_anh(self):
        r = self.client.post("/api/posts", json={
            "text": "Có ảnh", "image_base64": _anh_base64(),
            "image_mime": "image/webp", "image_width": 800,
            "image_height": 600}, headers=self.tk_an)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["post"]["has_image"])
        self.assertIn("image_url", r.json()["post"])

    def test_theo_doi_truyen(self):
        r = self.client.post(f"/api/novels/{self.truyen.novel_id}/follow",
                             json={}, headers=self.tk_binh)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["following"])

    def test_tom_tat_tai_khoan(self):
        r = self.client.get("/api/account/social", headers=self.tk_an)
        self.assertEqual(r.status_code, 200)
        self.assertIn("rank", r.json())        # An la tac gia da duyet


class CongQuanTriTest(Nen):
    """
    BA ma khac nhau cho ba tinh huong khac nhau, va khac biet do la co y.

    Tra 404 cho ca ba se giau duoc khu quan tri, nhung mot nguoi quan tri that
    go nham tai khoan se khong hieu vi sao khong vao duoc.
    """

    DUONG_QUAN_TRI = [
        ("get", "/api/admin/social/overview"),
        ("get", "/api/admin/reports"),
        ("get", "/api/admin/posts"),
    ]

    def test_khach_vang_lai_nhan_401(self):
        for method, duong in self.DUONG_QUAN_TRI:
            with self.subTest(duong=duong):
                self.assertEqual(
                    self._goi(method, duong, json={}).status_code, 401)

    def test_nguoi_dung_thuong_nhan_403(self):
        for method, duong in self.DUONG_QUAN_TRI:
            with self.subTest(duong=duong):
                r = self._goi(method, duong, json={},
                                                headers=self.tk_binh)
                self.assertEqual(r.status_code, 403)

    def test_quan_tri_di_qua(self):
        for method, duong in self.DUONG_QUAN_TRI:
            with self.subTest(duong=duong):
                r = self._goi(method, duong, json={},
                                                headers=self.tk_qt)
                self.assertEqual(r.status_code, 200, r.text)

    def test_tac_gia_da_duyet_KHONG_phai_la_quan_tri(self):
        """
        Uy tin va quyen quan tri la hai truc doc lap. Mot tac gia hang cao nhat
        van khong duoc doc hang doi bao cao.
        """
        r = self.client.get("/api/admin/reports", headers=self.tk_an)
        self.assertEqual(r.status_code, 403)

    def test_nguoi_thuong_KHONG_go_duoc_bai(self):
        bai = self._bai()
        r = self.client.post(f"/api/admin/posts/{bai['post_id']}/remove",
                             json={"reason": "tôi không thích"},
                             headers=self.tk_binh)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(main.store.get_post(bai["post_id"]).state.value,
                         "visible")


class KiemDuyetQuaHttpTest(Nen):
    def test_bao_cao_roi_quan_tri_go_bai(self):
        bai = self._bai()
        r = self.client.post("/api/reports", json={
            "target_kind": "post", "target_id": bai["post_id"],
            "reason": "spam", "detail": "Quảng cáo"}, headers=self.tk_binh)
        self.assertEqual(r.status_code, 201)

        hang_doi = self.client.get("/api/admin/reports",
                                   headers=self.tk_qt).json()
        self.assertEqual(hang_doi["total"], 1)
        rid = hang_doi["items"][0]["report_id"]

        r = self.client.post(f"/api/admin/posts/{bai['post_id']}/remove",
                             json={"reason": "spam"}, headers=self.tk_qt)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["post"]["state"], "removed")

        r = self.client.post(f"/api/admin/reports/{rid}/resolve",
                             json={"note": "Đã gỡ"}, headers=self.tk_qt)
        self.assertEqual(r.json()["report"]["status"], "resolved")

        # Bai da go KHONG con o bang tin cong khai.
        self.assertEqual(len(self.client.get("/api/feed").json()["items"]), 0)

    def test_phuc_hoi_bai(self):
        bai = self._bai()
        self.client.post(f"/api/admin/posts/{bai['post_id']}/remove",
                         json={"reason": "nhầm"}, headers=self.tk_qt)
        r = self.client.post(f"/api/admin/posts/{bai['post_id']}/restore",
                             json={}, headers=self.tk_qt)
        self.assertEqual(r.json()["post"]["state"], "visible")
        self.assertEqual(len(self.client.get("/api/feed").json()["items"]), 1)

    def test_go_va_phuc_hoi_binh_luan(self):
        bai = self._bai()
        bl = self.client.post(f"/api/posts/{bai['post_id']}/comments",
                              json={"text": "Xấu"},
                              headers=self.tk_binh).json()["comment"]
        r = self.client.post(f"/api/admin/comments/{bl['comment_id']}/remove",
                             json={"reason": "spam"}, headers=self.tk_qt)
        self.assertEqual(r.json()["comment"]["state"], "removed")
        r = self.client.post(f"/api/admin/comments/{bl['comment_id']}/restore",
                             json={}, headers=self.tk_qt)
        self.assertEqual(r.json()["comment"]["state"], "visible")

    def test_thao_tac_kiem_duyet_vao_nhat_ky_CHUNG(self):
        bai = self._bai()
        self.client.post(f"/api/admin/posts/{bai['post_id']}/remove",
                         json={"reason": "spam"}, headers=self.tk_qt)
        r = self.client.get("/api/admin/events", headers=self.tk_qt)
        self.assertIn("post_removed",
                      [e["action"] for e in r.json()["events"]])

    def test_ban_quan_tri_co_state_ban_cong_khai_thi_khong_lo_nguoi_go(self):
        bai = self._bai()
        self.client.post(f"/api/admin/posts/{bai['post_id']}/remove",
                         json={"reason": "spam"}, headers=self.tk_qt)
        quan_tri = self.client.get("/api/admin/posts",
                                   headers=self.tk_qt).json()["items"][0]
        self.assertEqual(quan_tri["removed_by"], self.qt.user_id)
        # Ban cong khai: `removed_by` khong bao gio ra ngoai — do la thu bien
        # mot quyet dinh kiem duyet thanh mot muc tieu ca nhan.
        self.client.post(f"/api/admin/posts/{bai['post_id']}/restore",
                         json={}, headers=self.tk_qt)
        cong_khai = self.client.get("/api/feed").json()["items"][0]
        self.assertNotIn("removed_by", cong_khai)
        self.assertNotIn("removed_reason", cong_khai)


class KiemDuyetAnimationTest(Nen):
    """
    Kiem duyet Animation qua HTTP (Phase 4, Admin Control Center V2).

    `Nen.setUp` khong noi `animation_store` — noi lai o day, va RESET no moi
    bai (khac `main.store`, `main.animation_store` la mot bien module SONG
    xuyen suot tien trinh test, khong tu sach giua cac bai neu khong reset).
    """

    def setUp(self) -> None:
        super().setUp()
        from server.animation_domain import AnimationEpisode, AnimationSeries
        from server.animation_store import MockAnimationStore
        from server.social_service import SocialService

        main.animation_store = MockAnimationStore()
        main.social = SocialService(main.identity, main.store, main.storage,
                                    animation_store=main.animation_store)

        self.series = main.animation_store.create_series(
            AnimationSeries(owner_id=self.an.user_id, title="Series Test"))
        main.animation_store.publish_series(self.series.series_id, self.an.user_id)
        self.tap = main.animation_store.create_episode(AnimationEpisode(
            series_id=self.series.series_id, owner_id=self.an.user_id,
            title="Tập 1", external_id="a" * 11))

    DUONG_QUAN_TRI = [
        ("get", "/api/admin/animation/series"),
    ]

    def test_khach_vang_lai_nhan_401(self):
        for method, duong in self.DUONG_QUAN_TRI:
            with self.subTest(duong=duong):
                self.assertEqual(self._goi(method, duong).status_code, 401)

    def test_nguoi_dung_thuong_nhan_403(self):
        for method, duong in self.DUONG_QUAN_TRI:
            with self.subTest(duong=duong):
                r = self._goi(method, duong, headers=self.tk_binh)
                self.assertEqual(r.status_code, 403)

    def test_quan_tri_thay_danh_sach_va_chi_tiet(self):
        r = self.client.get("/api/admin/animation/series", headers=self.tk_qt)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["total"], 1)
        hang = d["series"][0]
        self.assertEqual(hang["owner"]["display_name"], "An")
        self.assertEqual(hang["episode_count"], 1)

        r = self.client.get(f"/api/admin/animation/series/{self.series.series_id}",
                            headers=self.tk_qt)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["episodes"]), 1)

    def test_khong_ton_tai_tra_404(self):
        r = self.client.get("/api/admin/animation/series/khong_co",
                            headers=self.tk_qt)
        self.assertEqual(r.status_code, 404)

    def test_go_xuong_BAT_BUOC_ly_do(self):
        r = self.client.post(
            f"/api/admin/animation/series/{self.series.series_id}/unpublish",
            json={"reason": ""}, headers=self.tk_qt)
        self.assertEqual(r.status_code, 400)

    def test_go_va_phuc_hoi_series(self):
        r = self.client.post(
            f"/api/admin/animation/series/{self.series.series_id}/unpublish",
            json={"reason": "Vi phạm bản quyền"}, headers=self.tk_qt)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["series"]["moderation_state"], "removed")

        # Cong khai: 404 ngay sau do.
        cong_khai = self.client.get(
            f"/api/animation/series/{self.series.series_id}")
        self.assertEqual(cong_khai.status_code, 404)

        r = self.client.post(
            f"/api/admin/animation/series/{self.series.series_id}/restore",
            json={}, headers=self.tk_qt)
        self.assertEqual(r.json()["series"]["moderation_state"], "visible")
        cong_khai2 = self.client.get(
            f"/api/animation/series/{self.series.series_id}")
        self.assertEqual(cong_khai2.status_code, 200)

    def test_chu_so_huu_KHONG_hoan_tac_duoc_lenh_go_bang_publish_lai(self):
        """Cot loi cua thiet ke: `moderation_state` la truc RIENG voi `state`
        — chu so huu tu bam Xuat ban lai KHONG mo lai duoc noi dung da bi
        quan tri go xuong."""
        self.client.post(
            f"/api/admin/animation/series/{self.series.series_id}/unpublish",
            json={"reason": "Vi phạm"}, headers=self.tk_qt)
        r = self.client.post(
            f"/api/animation/series/{self.series.series_id}/publish",
            headers=self.tk_an)
        self.assertEqual(r.status_code, 200)  # chinh chu van goi duoc route
        cong_khai = self.client.get(
            f"/api/animation/series/{self.series.series_id}")
        self.assertEqual(cong_khai.status_code, 404)  # nhung van khong xem duoc

    def test_go_rieng_mot_tap_khong_dong_series(self):
        r = self.client.post(
            f"/api/admin/animation/episodes/{self.tap.episode_id}/unpublish",
            json={"reason": "Sai nội dung"}, headers=self.tk_qt)
        self.assertEqual(r.status_code, 200, r.text)

        cong_khai = self.client.get(
            f"/api/animation/series/{self.series.series_id}").json()
        self.assertEqual(cong_khai["episodes"], [])   # tap bi go, an di

        r = self.client.post(
            f"/api/admin/animation/episodes/{self.tap.episode_id}/restore",
            json={}, headers=self.tk_qt)
        self.assertEqual(r.status_code, 200)
        cong_khai2 = self.client.get(
            f"/api/animation/series/{self.series.series_id}").json()
        self.assertEqual(len(cong_khai2["episodes"]), 1)

    def test_thao_tac_vao_nhat_ky_CHUNG(self):
        self.client.post(
            f"/api/admin/animation/series/{self.series.series_id}/unpublish",
            json={"reason": "x"}, headers=self.tk_qt)
        r = self.client.get("/api/admin/events", headers=self.tk_qt)
        su_kien = r.json()["events"][0]
        self.assertEqual(su_kien["action"], "content_unpublish")
        self.assertEqual(su_kien["target_type"], "animation_series")
        self.assertEqual(su_kien["target_id"], self.series.series_id)
        self.assertEqual(su_kien["actor_id"], self.qt.user_id)


if __name__ == "__main__":
    unittest.main()
