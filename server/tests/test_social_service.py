"""
Tang dich vu xa hoi — `server/social_service.py`.

Day la noi QUYEN, HAN MUC va THONG BAO duoc cuong che, nen day cung la noi chung
duoc kiem. Cac bai o day chay tren kho MOCK; bo `test_social_contract.py` chung
minh ban Appwrite cung ngu nghia.

Nhieu bai duoi day kiem mot thu KHONG duoc phep xay ra. Chung quan trong hon cac
bai duong tinh: mot tinh nang hong thi co nguoi bao, con mot phep kiem quyen
thieu thi khong ai bao — cho den khi co nguoi tim ra.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.adapters import (
    LocalStorageAdapter,
    MockIdentityAdapter,
    MockMetadataStore,
    NotFoundError,
    PermissionDenied,
)
from server.creator_service import CreatorService
from server.domain import (
    AuthorStatus,
    ContentState,
    Novel,
    PublishState,
    ReportStatus,
)
from server.social import HanMuc, RateLimited, SocialError
from server.social_service import SocialService


class Nen(unittest.TestCase):
    """Ba nguoi va mot truyen da xuat ban — du cho hau het cac kich ban."""

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        self.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.social = SocialService(self.identity, self.store, self.storage)
        self.creators = CreatorService(self.identity, self.store)
        self.creators.on_decision = self.social.notify_author_decision

        self.an = self.identity.register("an@vidu.vn", "MatKhau123", "An")
        self.binh = self.identity.register("binh@vidu.vn", "MatKhau123", "Bình")
        self.cuc = self.identity.register("cuc@vidu.vn", "MatKhau123", "Cúc")
        # Quan tri chi la mot ho so thuong o tang nay — quyen do
        # `Depends(admin_profile)` o tang route quyet dinh.
        self.qt = self.identity.register("qt@vidu.vn", "MatKhau123", "Quản trị")

        self.an.author_status = AuthorStatus.APPROVED
        self.identity.save_profile(self.an)
        self.truyen = self.store.create_novel(Novel(
            owner_id=self.an.user_id, title="Hải Tặc Mũ Rơm",
            state=PublishState.PUBLISHED))

    def _bai(self, cua=None, text="Một bài đăng thử."):
        return self.social.create_post(cua or self.an, text=text)


class TheoDoiNguoiTest(Nen):
    def test_theo_doi_va_bo_theo_doi(self):
        ra = self.social.follow_user(self.binh, self.an.user_id)
        self.assertTrue(ra["following"])
        self.assertEqual(ra["follower_count"], 1)
        ra = self.social.unfollow_user(self.binh, self.an.user_id)
        self.assertFalse(ra["following"])
        self.assertEqual(ra["follower_count"], 0)

    def test_theo_doi_hai_lan_khong_dem_hai(self):
        """Tinh duy nhat cua khoa tat dinh — khong phai mot phep kiem truoc do."""
        self.social.follow_user(self.binh, self.an.user_id)
        ra = self.social.follow_user(self.binh, self.an.user_id)
        self.assertEqual(ra["follower_count"], 1)

    def test_theo_doi_hai_lan_chi_MOT_thong_bao(self):
        self.social.follow_user(self.binh, self.an.user_id)
        self.social.follow_user(self.binh, self.an.user_id)
        self.assertEqual(self.social.notifications(self.an)["total"], 1)

    def test_khong_tu_theo_doi_minh(self):
        with self.assertRaises(SocialError):
            self.social.follow_user(self.an, self.an.user_id)

    def test_theo_doi_nguoi_khong_ton_tai(self):
        with self.assertRaises(NotFoundError):
            self.social.follow_user(self.binh, "khong-co-nguoi-nay")

    def test_bo_theo_doi_khi_chua_theo_doi_khong_nem(self):
        """Idempotent: bam Bo theo doi hai lan khong duoc thanh mot loi."""
        ra = self.social.unfollow_user(self.binh, self.an.user_id)
        self.assertFalse(ra["following"])

    def test_khong_the_gia_mao_theo_doi_ho_nguoi_khac(self):
        """
        `actor` la ho so lay tu TOKEN, khong phai mot tham so. Khong co duong
        nao trong API nay de Binh tao mot lan theo doi mang ten Cuc.
        """
        self.social.follow_user(self.binh, self.an.user_id)
        xa_hoi_cuc = self.social.profile_social(self.cuc, self.cuc)
        self.assertEqual(xa_hoi_cuc["following_count"], 0)

    def test_dem_nguoi_theo_doi_va_dang_theo_doi_tach_biet(self):
        self.social.follow_user(self.binh, self.an.user_id)
        self.social.follow_user(self.cuc, self.an.user_id)
        self.social.follow_user(self.an, self.binh.user_id)
        goi = self.social.profile_social(self.an, self.binh)
        self.assertEqual(goi["follower_count"], 2)
        self.assertEqual(goi["following_count"], 1)


class TheoDoiTruyenTest(Nen):
    def test_theo_doi_truyen(self):
        ra = self.social.follow_story(self.binh, self.truyen.novel_id)
        self.assertTrue(ra["following"])
        self.assertEqual(ra["follower_count"], 1)

    def test_bang_RIENG_voi_theo_doi_nguoi(self):
        """
        Theo doi truyen KHONG lam tang so nguoi theo doi cua tac gia. Hai bang
        rieng, hai con so rieng — gop lai la mot con so khong ai giai thich duoc.
        """
        self.social.follow_story(self.binh, self.truyen.novel_id)
        self.assertEqual(
            self.social.profile_social(self.an, self.binh)["follower_count"], 0)

    def test_khong_theo_doi_duoc_ban_nhap(self):
        """Cho theo doi ban nhap la mot cach do xem ai dang viet gi."""
        nhap = self.store.create_novel(Novel(owner_id=self.an.user_id,
                                             title="Bản nháp"))
        with self.assertRaises(NotFoundError):
            self.social.follow_story(self.binh, nhap.novel_id)

    def test_truyen_khong_ton_tai(self):
        with self.assertRaises(NotFoundError):
            self.social.follow_story(self.binh, "khong-co")

    def test_thong_bao_chuong_moi_cho_nguoi_theo_doi(self):
        from server.domain import Chapter

        self.social.follow_story(self.binh, self.truyen.novel_id)
        chuong = self.store.create_chapter(Chapter(
            novel_id=self.truyen.novel_id, owner_id=self.an.user_id,
            title="Chương 1", state=PublishState.PUBLISHED))
        so = self.social.notify_new_chapter(self.truyen, chuong)
        self.assertEqual(so, 1)
        ds = self.social.notifications(self.binh)["items"]
        self.assertEqual(ds[0]["kind"], "story_chapter")
        self.assertIn("Hải Tặc", ds[0]["preview"])

    def test_tac_gia_khong_tu_nhan_thong_bao_chuong_cua_minh(self):
        from server.domain import Chapter

        self.social.follow_story(self.an, self.truyen.novel_id)
        chuong = self.store.create_chapter(Chapter(
            novel_id=self.truyen.novel_id, owner_id=self.an.user_id,
            title="Chương 1"))
        self.assertEqual(self.social.notify_new_chapter(self.truyen, chuong), 0)


class BaiDangTest(Nen):
    def test_dang_bai(self):
        bai = self._bai(text="Chào cả nhà.")
        self.assertEqual(bai["text"], "Chào cả nhà.")
        self.assertEqual(bai["author"]["display_name"], "An")
        self.assertTrue(bai["can_edit"])

    def test_bai_rong_khong_anh_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="   ")

    def test_sua_bai_cua_minh(self):
        bai = self._bai()
        ra = self.social.edit_post(self.an, bai["post_id"], text="Đã sửa.")
        self.assertEqual(ra["text"], "Đã sửa.")

    def test_KHONG_sua_duoc_bai_nguoi_khac(self):
        bai = self._bai()
        with self.assertRaises(PermissionDenied):
            self.social.edit_post(self.binh, bai["post_id"], text="phá")

    def test_KHONG_xoa_duoc_bai_nguoi_khac(self):
        bai = self._bai()
        with self.assertRaises(PermissionDenied):
            self.social.delete_post(self.binh, bai["post_id"])

    def test_xoa_bai_cua_minh_la_xoa_THAT(self):
        """Chinh chu thu hoi thu ho da noi — khac han duong kiem duyet."""
        bai = self._bai()
        self.social.delete_post(self.an, bai["post_id"])
        self.assertIsNone(self.store.get_post(bai["post_id"]))

    def test_cap_nhat_truyen_doi_tac_gia_da_duyet(self):
        with self.assertRaises(PermissionDenied):
            self.social.create_post(self.binh, text="Chương mới!",
                                    kind="story_update",
                                    novel_id=self.truyen.novel_id)

    def test_cap_nhat_truyen_doi_dung_chu_so_huu(self):
        self.binh.author_status = AuthorStatus.APPROVED
        self.identity.save_profile(self.binh)
        with self.assertRaises(PermissionDenied):
            self.social.create_post(self.binh, text="Chương mới!",
                                    kind="story_update",
                                    novel_id=self.truyen.novel_id)

    def test_cap_nhat_truyen_kem_the_truyen(self):
        bai = self.social.create_post(self.an, text="Chương 12 đã lên!",
                                      kind="story_update",
                                      novel_id=self.truyen.novel_id)
        self.assertEqual(bai["novel"]["title"], "Hải Tặc Mũ Rơm")

    def test_loai_bai_la_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="x", kind="quang-cao")

    def test_bai_qua_dai_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="x" * 5000)


class AnhBaiTest(Nen):
    def _anh(self, so_byte=1000, mime="image/webp"):
        return {"data": b"x" * so_byte, "mime": mime, "width": 800,
                "height": 600}

    def test_dang_bai_chi_co_anh(self):
        bai = self.social.create_post(self.an, text="", image=self._anh())
        self.assertTrue(bai["has_image"])
        self.assertIn("image_url", bai)

    def test_khoa_doi_tuong_dung_khong_gian_ten(self):
        bai = self.social.create_post(self.an, text="", image=self._anh())
        khoa = self.store.get_post(bai["post_id"]).image_key
        self.assertTrue(khoa.startswith(f"posts/{self.an.user_id}/"))

    def test_khoa_doi_tuong_KHONG_chua_email(self):
        bai = self.social.create_post(self.an, text="", image=self._anh())
        self.assertNotIn("@", self.store.get_post(bai["post_id"]).image_key)

    def test_ban_CONG_KHAI_khong_lo_khoa_doi_tuong(self):
        """
        Khoa tho khong dung truc tiep duoc (kho la rieng tu) va no lo ra cau
        truc khong gian ten. Ra ngoai chi la mot URL da ky.
        """
        bai = self.social.create_post(self.an, text="", image=self._anh())
        self.assertNotIn("image_key", bai)

    def test_anh_qua_to_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="",
                                    image=self._anh(so_byte=5 * 1024 * 1024))

    def test_mime_la_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.create_post(self.an, text="",
                                    image=self._anh(mime="text/html"))

    def test_kich_thuoc_bi_ep_ve_tran(self):
        """Client noi 9999px thi khong duoc tin — con so do di vao HTML."""
        bai = self.social.create_post(self.an, text="", image={
            "data": b"x" * 100, "mime": "image/webp", "width": 99999,
            "height": 99999})
        luu = self.store.get_post(bai["post_id"])
        self.assertLessEqual(luu.image_width, 1600)

    def test_xoa_bai_thi_xoa_ca_anh(self):
        bai = self.social.create_post(self.an, text="", image=self._anh())
        khoa = self.store.get_post(bai["post_id"]).image_key
        self.assertTrue(self.storage.exists(khoa))
        self.social.delete_post(self.an, bai["post_id"])
        self.assertFalse(self.storage.exists(khoa))


class ThichTest(Nen):
    def test_thich_va_bo_thich(self):
        bai = self._bai()
        ra = self.social.like_post(self.binh, bai["post_id"])
        self.assertTrue(ra["liked"])
        self.assertEqual(ra["like_count"], 1)
        ra = self.social.unlike_post(self.binh, bai["post_id"])
        self.assertFalse(ra["liked"])
        self.assertEqual(ra["like_count"], 0)

    def test_thich_hai_lan_van_la_MOT(self):
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        ra = self.social.like_post(self.binh, bai["post_id"])
        self.assertEqual(ra["like_count"], 1)
        self.assertEqual(self.store.count_post_likes(bai["post_id"]), 1)

    def test_bo_thich_khong_lam_am_bo_dem(self):
        bai = self._bai()
        for _ in range(3):
            self.social.unlike_post(self.binh, bai["post_id"])
        self.assertEqual(self.store.get_post(bai["post_id"]).like_count, 0)

    def test_tu_thich_bai_minh_khong_sinh_thong_bao(self):
        bai = self._bai()
        self.social.like_post(self.an, bai["post_id"])
        self.assertEqual(self.social.notifications(self.an)["total"], 0)

    def test_dem_lai_tu_bang_su_that(self):
        """`recount_post` la duong sua khi bo dem cong don bi lech."""
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        luu = self.store.get_post(bai["post_id"])
        luu.like_count = 99                       # gia lap mot lan lech
        self.store.save_post(luu)
        ra = self.social.recount_post(bai["post_id"])
        self.assertEqual(ra["like_count"], 1)

    def test_thich_bai_da_bi_go_thi_khong_thay(self):
        bai = self._bai()
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        with self.assertRaises(NotFoundError):
            self.social.like_post(self.binh, bai["post_id"])


class BinhLuanTest(Nen):
    def test_binh_luan_va_dem(self):
        bai = self._bai()
        self.social.create_comment(self.binh, bai["post_id"], text="Hay quá!")
        self.assertEqual(self.store.get_post(bai["post_id"]).comment_count, 1)

    def test_tra_loi_MOT_cap(self):
        bai = self._bai()
        goc = self.social.create_comment(self.binh, bai["post_id"], text="Hỏi")
        tl = self.social.create_comment(self.an, bai["post_id"], text="Đáp",
                                        parent_id=goc["comment_id"])
        self.assertEqual(tl["parent_id"], goc["comment_id"])

    def test_KHONG_tra_loi_duoc_mot_tra_loi(self):
        bai = self._bai()
        goc = self.social.create_comment(self.binh, bai["post_id"], text="Hỏi")
        tl = self.social.create_comment(self.an, bai["post_id"], text="Đáp",
                                        parent_id=goc["comment_id"])
        with self.assertRaises(SocialError):
            self.social.create_comment(self.cuc, bai["post_id"], text="Nữa",
                                       parent_id=tl["comment_id"])

    def test_tra_loi_phai_cung_bai(self):
        b1, b2 = self._bai(), self._bai(text="Bài hai")
        goc = self.social.create_comment(self.binh, b1["post_id"], text="Hỏi")
        with self.assertRaises(NotFoundError):
            self.social.create_comment(self.an, b2["post_id"], text="Đáp",
                                       parent_id=goc["comment_id"])

    def test_so_tra_loi_len_dung(self):
        bai = self._bai()
        goc = self.social.create_comment(self.binh, bai["post_id"], text="Hỏi")
        self.social.create_comment(self.an, bai["post_id"], text="Đáp",
                                   parent_id=goc["comment_id"])
        self.assertEqual(
            self.store.get_comment(goc["comment_id"]).reply_count, 1)

    def test_KHONG_sua_duoc_binh_luan_nguoi_khac(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"], text="Của Bình")
        with self.assertRaises(PermissionDenied):
            self.social.edit_comment(self.cuc, bl["comment_id"], text="phá")

    def test_KHONG_xoa_duoc_binh_luan_nguoi_khac(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"], text="Của Bình")
        with self.assertRaises(PermissionDenied):
            self.social.delete_comment(self.cuc, bl["comment_id"])

    def test_xoa_binh_luan_giam_bo_dem_cua_bai(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"], text="X")
        self.social.delete_comment(self.binh, bl["comment_id"])
        self.assertEqual(self.store.get_post(bai["post_id"]).comment_count, 0)

    def test_danh_sach_kem_vai_tra_loi_dau(self):
        bai = self._bai()
        goc = self.social.create_comment(self.binh, bai["post_id"], text="Hỏi")
        for i in range(2):
            self.social.create_comment(self.an, bai["post_id"], text=f"Đáp {i}",
                                       parent_id=goc["comment_id"])
        ds = self.social.comments(bai["post_id"])["items"]
        self.assertEqual(len(ds), 1)              # chi binh luan GOC
        self.assertEqual(len(ds[0]["replies"]), 2)

    def test_binh_luan_cu_nhat_truoc(self):
        """Mot cuoc trao doi doc theo thu tu no dien ra."""
        bai = self._bai()
        for i in range(3):
            self.social.create_comment(self.binh, bai["post_id"], text=f"BL {i}")
        ds = self.social.comments(bai["post_id"])["items"]
        self.assertEqual([m["text"] for m in ds], ["BL 0", "BL 1", "BL 2"])

    def test_binh_luan_bi_go_van_tra_ve_nhung_KHONG_kem_noi_dung(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"],
                                        text="Nội dung xấu")
        self.social.remove_comment(self.qt, bl["comment_id"], reason="spam")
        ds = self.social.comments(bai["post_id"])["items"]
        self.assertEqual(ds[0]["state"], "removed")
        self.assertEqual(ds[0]["text"], "")
        self.assertEqual(ds[0]["author_user_id"], "")


class BangTinTest(Nen):
    def test_chua_theo_doi_ai_thi_thay_kham_pha(self):
        """
        Mot bang tin rong o lan dau vao la mot ly do de khong quay lai.
        """
        self._bai(cua=self.an)
        ra = self.social.feed(self.binh)
        self.assertEqual(len(ra["items"]), 1)
        self.assertFalse(ra["personalized"])

    def test_bai_cua_nguoi_theo_doi_len_TRUOC(self):
        self.social.follow_user(self.cuc, self.binh.user_id)
        self._bai(cua=self.an, text="Của An")
        self._bai(cua=self.binh, text="Của Bình")
        ra = self.social.feed(self.cuc)
        self.assertTrue(ra["personalized"])
        self.assertEqual(ra["items"][0]["text"], "Của Bình")

    def test_khach_vang_lai_van_xem_duoc(self):
        self._bai()
        ra = self.social.feed(None)
        self.assertEqual(len(ra["items"]), 1)
        self.assertFalse(ra["items"][0]["can_edit"])
        self.assertFalse(ra["items"][0]["liked"])

    def test_bai_bi_go_KHONG_ra_bang_tin(self):
        bai = self._bai()
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        self.assertEqual(len(self.social.feed(None)["items"]), 0)

    def test_co_da_thich_dung_cho_tung_nguoi(self):
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        self.assertTrue(self.social.feed(self.binh)["items"][0]["liked"])
        self.assertFalse(self.social.feed(self.cuc)["items"][0]["liked"])

    def test_phan_trang(self):
        for i in range(5):
            self._bai(text=f"Bài {i}")
        ra = self.social.feed(None, limit=2)
        self.assertEqual(len(ra["items"]), 2)
        self.assertEqual(ra["total"], 5)

    def test_bai_moi_nhat_truoc(self):
        for i in range(3):
            self._bai(text=f"Bài {i}")
        ra = self.social.feed(None)
        self.assertEqual(ra["items"][0]["text"], "Bài 2")

    def test_tab_bai_viet_cua_mot_nguoi(self):
        self._bai(cua=self.an, text="Của An")
        self._bai(cua=self.binh, text="Của Bình")
        ra = self.social.posts_by_user(self.an.user_id)
        self.assertEqual([m["text"] for m in ra["items"]], ["Của An"])


class ThongBaoTest(Nen):
    def test_du_bay_loai(self):
        """
        Bay loai la HOP DONG voi giao dien va voi lop enum trong schema. Thieu
        mot loai o day nghia la mot su kien khong bao gio duoc bao.
        """
        from server.domain import NotificationKind

        self.assertEqual(
            {k.value for k in NotificationKind},
            {"follow", "post_like", "post_comment", "comment_reply",
             "story_chapter", "author_approved", "author_rejected"})

    def test_dem_chua_doc(self):
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        self.assertEqual(self.social.unread_count(self.an)["unread"], 1)

    def test_danh_dau_da_doc(self):
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        nid = self.social.notifications(self.an)["items"][0]["notification_id"]
        self.social.mark_read(self.an, nid)
        self.assertEqual(self.social.unread_count(self.an)["unread"], 0)

    def test_KHONG_danh_dau_duoc_thong_bao_nguoi_khac(self):
        """
        `user_id` la mot phan cua DIEU KIEN. Khong co no thi ai doan duoc mot id
        la cham vao thong bao cua nguoi khac.
        """
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        nid = self.social.notifications(self.an)["items"][0]["notification_id"]
        self.social.mark_read(self.cuc, nid)
        self.assertEqual(self.social.unread_count(self.an)["unread"], 1)

    def test_danh_dau_tat_ca(self):
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        self.social.create_comment(self.cuc, bai["post_id"], text="Hay")
        ra = self.social.mark_all_read(self.an)
        self.assertEqual(ra["marked"], 2)
        self.assertEqual(ra["unread"], 0)

    def test_ban_cho_nguoi_nhan_KHONG_kem_user_id(self):
        bai = self._bai()
        self.social.like_post(self.binh, bai["post_id"])
        self.assertNotIn("notification_id_of_other", {})
        self.assertNotIn("user_id",
                         self.social.notifications(self.an)["items"][0])

    def test_thong_bao_duyet_don(self):
        self.binh.author_status = AuthorStatus.NONE
        self.identity.save_profile(self.binh)
        self.creators.apply(self.binh, pen_name="Bình", intro="Xin chào",
                            accepted_rules=True)
        self.creators.approve(self.binh.user_id, note="Hoan nghênh",
                              actor_id=self.qt.user_id)
        ds = self.social.notifications(self.binh)["items"]
        self.assertEqual(ds[0]["kind"], "author_approved")

    def test_thong_bao_tu_choi_don(self):
        self.creators.apply(self.cuc, pen_name="Cúc", intro="Xin chào",
                            accepted_rules=True)
        self.creators.reject(self.cuc.user_id, note="Thiếu thông tin",
                             actor_id=self.qt.user_id)
        ds = self.social.notifications(self.cuc)["items"]
        self.assertEqual(ds[0]["kind"], "author_rejected")

    def test_thong_bao_duyet_KHONG_lo_quan_tri_nao(self):
        """
        Cho nguoi nop biet quan tri nao da bam la bien mot quyet dinh he thong
        thanh mot chuyen ca nhan.
        """
        self.creators.apply(self.cuc, pen_name="Cúc", intro="Xin chào",
                            accepted_rules=True)
        self.creators.reject(self.cuc.user_id, note="Thiếu",
                             actor_id=self.qt.user_id)
        ds = self.social.notifications(self.cuc)["items"]
        self.assertEqual(ds[0]["actor_id"], "")

    def test_loi_thong_bao_KHONG_lam_hong_quyet_dinh_kiem_duyet(self):
        def no(*a, **k):
            raise RuntimeError("mạng hỏng")

        self.creators.on_decision = no
        self.creators.apply(self.cuc, pen_name="Cúc", intro="Xin chào",
                            accepted_rules=True)
        self.creators.approve(self.cuc.user_id, actor_id=self.qt.user_id)
        self.assertIs(self.identity.get_profile(self.cuc.user_id).author_status,
                      AuthorStatus.APPROVED)


class BaoCaoTest(Nen):
    def test_bao_cao_bai(self):
        bai = self._bai()
        ra = self.social.report(self.binh, target_kind="post",
                                target_id=bai["post_id"], reason="spam")
        self.assertTrue(ra["created"])

    def test_bao_cao_KHONG_TU_GO_noi_dung(self):
        """
        Neu no tu go duoc, mot nhom nguoi phoi hop bam Bao cao se thanh cong cu
        xoa noi dung cua nguoi ho khong thich.
        """
        bai = self._bai()
        for nguoi in (self.binh, self.cuc):
            self.social.report(nguoi, target_kind="post",
                               target_id=bai["post_id"], reason="spam")
        self.assertIs(self.store.get_post(bai["post_id"]).state,
                      ContentState.VISIBLE)

    def test_bao_cao_hai_lan_chi_MOT_hang(self):
        bai = self._bai()
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        ra = self.social.report(self.binh, target_kind="post",
                                target_id=bai["post_id"], reason="harassment")
        self.assertFalse(ra["created"])
        self.assertEqual(self.store.count_reports(), 1)

    def test_khong_bao_cao_noi_dung_cua_chinh_minh(self):
        bai = self._bai()
        with self.assertRaises(SocialError):
            self.social.report(self.an, target_kind="post",
                               target_id=bai["post_id"], reason="spam")

    def test_ly_do_la_thi_tu_choi(self):
        bai = self._bai()
        with self.assertRaises(SocialError):
            self.social.report(self.binh, target_kind="post",
                               target_id=bai["post_id"], reason="tôi-không-thích")

    def test_loai_doi_tuong_la_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            self.social.report(self.binh, target_kind="user",
                               target_id=self.an.user_id, reason="spam")

    def test_bao_cao_binh_luan(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"], text="Xấu")
        ra = self.social.report(self.cuc, target_kind="comment",
                                target_id=bl["comment_id"], reason="harassment")
        self.assertTrue(ra["created"])


class KiemDuyetTest(Nen):
    def test_go_bai_thi_hang_VAN_CON(self):
        bai = self._bai()
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        luu = self.store.get_post(bai["post_id"])
        self.assertIsNotNone(luu)
        self.assertIs(luu.state, ContentState.REMOVED)
        self.assertEqual(luu.removed_by, self.qt.user_id)

    def test_phuc_hoi_bai(self):
        bai = self._bai()
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        self.social.restore_post(self.qt, bai["post_id"])
        luu = self.store.get_post(bai["post_id"])
        self.assertIs(luu.state, ContentState.VISIBLE)
        self.assertEqual(luu.removed_by, "")

    def test_moi_thao_tac_vao_NHAT_KY(self):
        bai = self._bai()
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        su_kien, _ = self.store.list_events(target_user_id=self.an.user_id)
        self.assertEqual(su_kien[0].action, "post_removed")
        self.assertEqual(su_kien[0].actor_id, self.qt.user_id)

    def test_nhat_ky_CHUNG_voi_kiem_duyet_tac_gia(self):
        """
        Nguoi doc lai mot vu viec muon thay MOI thu da xay ra voi mot nguoi theo
        thu tu, chu khong phai ghep hai danh sach o hai man hinh.
        """
        self.creators.apply(self.cuc, pen_name="Cúc", intro="Chào",
                            accepted_rules=True)
        self.creators.reject(self.cuc.user_id, note="Thiếu",
                             actor_id=self.qt.user_id)
        bai = self._bai(cua=self.cuc)
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        su_kien, _ = self.store.list_events(target_user_id=self.cuc.user_id)
        self.assertEqual({e.action for e in su_kien},
                         {"author_rejected", "post_removed"})

    def test_go_binh_luan_giam_bo_dem(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"], text="Xấu")
        self.social.remove_comment(self.qt, bl["comment_id"], reason="spam")
        self.assertEqual(self.store.get_post(bai["post_id"]).comment_count, 0)

    def test_go_binh_luan_hai_lan_khong_giam_hai(self):
        bai = self._bai()
        bl = self.social.create_comment(self.binh, bai["post_id"], text="Xấu")
        self.social.remove_comment(self.qt, bl["comment_id"], reason="spam")
        self.social.remove_comment(self.qt, bl["comment_id"], reason="spam")
        self.assertEqual(self.store.get_post(bai["post_id"]).comment_count, 0)

    def test_hang_doi_bao_cao_kem_noi_dung(self):
        bai = self._bai(text="Nội dung bị báo")
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        ra = self.social.admin_reports()
        self.assertEqual(ra["total"], 1)
        self.assertEqual(ra["items"][0]["content"]["text"], "Nội dung bị báo")
        self.assertEqual(ra["items"][0]["reporter"]["display_name"], "Bình")

    def test_dong_bao_cao(self):
        bai = self._bai()
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        rid = self.social.admin_reports()["items"][0]["report_id"]
        ra = self.social.resolve_report(self.qt, rid, note="Đã gỡ")
        self.assertEqual(ra["status"], "resolved")
        self.assertEqual(self.social.admin_reports(status="open")["total"], 0)

    def test_bo_qua_bao_cao(self):
        bai = self._bai()
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        rid = self.social.admin_reports()["items"][0]["report_id"]
        ra = self.social.resolve_report(self.qt, rid, dismiss=True,
                                        note="Không vi phạm")
        self.assertEqual(ra["status"], "dismissed")

    def test_dong_bao_cao_KHONG_dong_thoi_go_noi_dung(self):
        bai = self._bai()
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        rid = self.social.admin_reports()["items"][0]["report_id"]
        self.social.resolve_report(self.qt, rid)
        self.assertIs(self.store.get_post(bai["post_id"]).state,
                      ContentState.VISIBLE)

    def test_danh_sach_bai_quan_tri_co_so_bao_cao_dang_mo(self):
        bai = self._bai()
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        ra = self.social.admin_posts()
        self.assertEqual(ra["items"][0]["open_reports"], 1)

    def test_tong_quan_xa_hoi(self):
        bai = self._bai()
        self._bai(text="Bài hai")
        self.social.report(self.binh, target_kind="post",
                           target_id=bai["post_id"], reason="spam")
        self.social.remove_post(self.qt, bai["post_id"], reason="spam")
        ra = self.social.social_overview()
        self.assertEqual(ra["total_posts"], 2)
        self.assertEqual(ra["removed_posts"], 1)
        self.assertEqual(ra["open_reports"], 1)

    def test_bao_cao_khong_ton_tai(self):
        with self.assertRaises(NotFoundError):
            self.social.resolve_report(self.qt, "khong-co")


class HanMucChongSpamTest(Nen):
    def test_chan_dang_bai_qua_nhanh(self):
        chat = SocialService(self.identity, self.store, self.storage,
                            han_muc={"post": HanMuc(so_lan=2, phut=60)})
        chat.create_post(self.an, text="Bài 1")
        chat.create_post(self.an, text="Bài 2")
        with self.assertRaises(RateLimited):
            chat.create_post(self.an, text="Bài 3")

    def test_han_muc_tinh_RIENG_tung_nguoi(self):
        chat = SocialService(self.identity, self.store, self.storage,
                            han_muc={"post": HanMuc(so_lan=1, phut=60)})
        chat.create_post(self.an, text="Của An")
        chat.create_post(self.binh, text="Của Bình")   # khong bi anh huong

    def test_chan_binh_luan_qua_nhanh(self):
        chat = SocialService(self.identity, self.store, self.storage,
                            han_muc={"comment": HanMuc(so_lan=1, phut=60)})
        bai = self._bai()
        chat.create_comment(self.binh, bai["post_id"], text="Một")
        with self.assertRaises(RateLimited):
            chat.create_comment(self.binh, bai["post_id"], text="Hai")

    def test_chan_theo_doi_hang_loat(self):
        chat = SocialService(self.identity, self.store, self.storage,
                            han_muc={"follow": HanMuc(so_lan=1, phut=60)})
        chat.follow_user(self.cuc, self.an.user_id)
        with self.assertRaises(RateLimited):
            chat.follow_user(self.cuc, self.binh.user_id)

    def test_chan_bao_cao_hang_loat(self):
        """Chan mot nguoi bao cao hang loat de dim mot nguoi khac."""
        chat = SocialService(self.identity, self.store, self.storage,
                            han_muc={"report": HanMuc(so_lan=1, phut=60)})
        b1, b2 = self._bai(), self._bai(text="Bài hai")
        chat.report(self.binh, target_kind="post", target_id=b1["post_id"],
                    reason="spam")
        with self.assertRaises(RateLimited):
            chat.report(self.binh, target_kind="post", target_id=b2["post_id"],
                        reason="spam")

    def test_ngoai_cua_so_thi_khong_con_chan(self):
        chat = SocialService(self.identity, self.store, self.storage,
                            han_muc={"post": HanMuc(so_lan=1, phut=60)})
        bai = chat.create_post(self.an, text="Cũ")
        # Day ban ghi cu ra ngoai cua so — cua so TRUOT, khong phai cua so co dinh.
        luu = self.store.get_post(bai["post_id"])
        luu.created_at = (datetime.now(timezone.utc)
                          - timedelta(hours=3)).isoformat()
        self.store.save_post(luu)
        chat.create_post(self.an, text="Mới")


class TomTatTest(Nen):
    def test_tom_tat_tai_khoan_nguoi_thuong(self):
        ra = self.social.account_summary(self.binh)
        self.assertIn("follower_count", ra)
        # Nguoi chua nop don KHONG co o "Hang" — mot loi moi vao mot he thong ho
        # khong o trong.
        self.assertNotIn("rank", ra)

    def test_tom_tat_tai_khoan_tac_gia_da_duyet(self):
        ra = self.social.account_summary(self.an)
        self.assertIn("rank", ra)
        self.assertIn("qualified_listens", ra)
        self.assertEqual(ra["published_novels"], 1)

    def test_dem_bai_va_truyen_theo_doi(self):
        self._bai(cua=self.binh)
        self.social.follow_story(self.binh, self.truyen.novel_id)
        ra = self.social.account_summary(self.binh)
        self.assertEqual(ra["post_count"], 1)
        self.assertEqual(ra["followed_stories"], 1)

    def test_ho_so_xa_hoi_biet_la_chinh_minh(self):
        self.assertTrue(self.social.profile_social(self.an, self.an)["is_self"])
        self.assertFalse(self.social.profile_social(self.an, self.binh)["is_self"])

    def test_tim_bai_dang(self):
        self._bai(text="Chuyện về Luffy và băng Mũ Rơm")
        ra = self.social.search_posts("Luffy")
        self.assertEqual(ra["total"], 1)

    def test_tim_qua_ngan_thi_khong_tra_ve_gi(self):
        """Mot ky tu se khop gan het moi bai — do khong phai mot ket qua tim."""
        self._bai(text="Chuyện về Luffy")
        self.assertEqual(self.social.search_posts("L")["total"], 0)


if __name__ == "__main__":
    unittest.main()
