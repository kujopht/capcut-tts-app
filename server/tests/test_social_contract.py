"""
HOP DONG giua kho mock va kho Appwrite cho BAY bang cua tang xa hoi.

VI SAO CAN, va vi sao no la bo test quan trong nhat trong nhom nay:

Toan bo `test_social_service.py` va `test_social_routes.py` chay tren kho MOCK.
Neu ban Appwrite lech ngu nghia du mot cho — tra `None` thay vi nem, dem sai
tong so, cho phep ghi hai lan cung mot khoa, sap xep nguoc — thi TOAN BO nhung
bai kia van xanh va he thong van hong o production. Bo test nay la thu duy nhat
chan duoc loai loi do.

Cach lam: chay CUNG mot kich ban tren CA HAI kho va doi soat ket qua. Appwrite
duoc thay bang `FakeAppwrite` cua `test_appwrite_v2_contract` — mot ban gia lap
REST trong bo nho co CUONG CHE tinh duy nhat cua `rowId`, hieu `select`,
`greaterThanEqual` va `DELETE`. No khong phai Appwrite that, nhung no du de bat
dung loai loi ma bo test nay ton tai vi no.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from server.adapters import MockMetadataStore
from server.domain import (
    Comment,
    ContentReport,
    ContentState,
    Notification,
    NotificationKind,
    Post,
    PostKind,
    PostLike,
    ReportReason,
    ReportStatus,
    StoryFollow,
    UserFollow,
    now_iso_us,
)
from server.social import (
    notification_key,
    post_like_key,
    report_key,
    story_follow_key,
    user_follow_key,
)
from server.tests.test_appwrite_v2_contract import FakeAppwrite, _kho_appwrite

BAY_GIO = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class HopDongXaHoi(unittest.TestCase):
    """
    Moi bai duoi day chay tren CA HAI kho.

    `_cac_kho()` tra ve cap `(ten, kho)` de thong bao that bai noi ro ban nao
    lech — "mock" hay "appwrite".
    """

    def _cac_kho(self):
        return [("mock", MockMetadataStore()),
                ("appwrite", _kho_appwrite(FakeAppwrite()))]

    # -- tien ich dung chung -------------------------------------------------

    @staticmethod
    def _bai(kho, tac_gia="u1", text="Một bài", **kw) -> Post:
        bai = Post(author_user_id=tac_gia, text=text, **kw)
        kho.create_post(bai)
        return bai

    @staticmethod
    def _theo_doi(kho, a="u1", b="u2") -> bool:
        return kho.follow_user(UserFollow(follower_id=a, target_id=b,
                                          follow_id=user_follow_key(a, b)))

    # ===================================================== THEO DOI NGUOI

    def test_theo_doi_lan_dau_tra_True_lan_hai_tra_False(self):
        """
        Co nay quyet dinh CO GUI THONG BAO HAY KHONG. Hai ban lech o day nghia
        la o production nguoi dung nhan thong bao lap moi lan ai do bam lai.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertTrue(self._theo_doi(kho))
                self.assertFalse(self._theo_doi(kho))

    def test_bo_theo_doi_roi_theo_doi_lai_duoc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._theo_doi(kho)
                self.assertTrue(kho.unfollow_user(user_follow_key("u1", "u2")))
                self.assertTrue(self._theo_doi(kho))

    def test_bo_theo_doi_khi_chua_co_tra_False(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertFalse(kho.unfollow_user(user_follow_key("u1", "u2")))

    def test_is_following(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                khoa = user_follow_key("u1", "u2")
                self.assertFalse(kho.is_following_user(khoa))
                self._theo_doi(kho)
                self.assertTrue(kho.is_following_user(khoa))

    def test_dem_nguoi_theo_doi_theo_LO(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for a in ("u1", "u2", "u3"):
                    self._theo_doi(kho, a, "ngoi-sao")
                self._theo_doi(kho, "u1", "it-nguoi")
                dem = kho.follower_counts(["ngoi-sao", "it-nguoi", "khong-ai"])
                self.assertEqual(dem["ngoi-sao"], 3)
                self.assertEqual(dem["it-nguoi"], 1)
                # Nguoi khong co ai theo doi phai ra 0, KHONG phai vang mat —
                # giao dien doc thang tu dict nay.
                self.assertEqual(dem["khong-ai"], 0)

    def test_dem_dang_theo_doi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for b in ("u2", "u3"):
                    self._theo_doi(kho, "u1", b)
                self.assertEqual(kho.following_counts(["u1"])["u1"], 2)

    def test_co_dang_theo_doi_cho_ca_TRANG(self):
        """Ham chan N+1 cua co "đang theo dõi"."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._theo_doi(kho, "toi", "a")
                self._theo_doi(kho, "toi", "c")
                self._theo_doi(kho, "nguoi-khac", "b")
                co = kho.following_flags("toi", ["a", "b", "c", "d"])
                self.assertEqual(co, {"a", "c"})

    def test_co_dang_theo_doi_voi_danh_sach_rong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertEqual(kho.following_flags("toi", []), set())

    def test_danh_sach_dang_theo_doi_MOI_NHAT_truoc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for b in ("cu", "giua", "moi"):
                    kho.follow_user(UserFollow(
                        follower_id="toi", target_id=b,
                        follow_id=user_follow_key("toi", b),
                        created_at=now_iso_us()))
                self.assertEqual(kho.following_user_ids("toi")[0], "moi")

    def test_danh_sach_dang_theo_doi_ton_trong_tran(self):
        """
        Tran nay khong phai trang tri: danh sach di vao mot truy van
        `author_user_id IN (...)`, va Appwrite gioi han do dai truy van.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(10):
                    self._theo_doi(kho, "toi", f"u{i}")
                self.assertEqual(len(kho.following_user_ids("toi", limit=4)), 4)

    def test_dem_theo_doi_trong_cua_so_thoi_gian(self):
        """Dau vao cua han muc chong spam."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                cu = (BAY_GIO - timedelta(hours=5)).isoformat(
                    timespec="microseconds")
                kho.follow_user(UserFollow(follower_id="toi", target_id="a",
                                           follow_id="f-cu", created_at=cu))
                kho.follow_user(UserFollow(
                    follower_id="toi", target_id="b", follow_id="f-moi",
                    created_at=BAY_GIO.isoformat(timespec="microseconds")))
                moc = (BAY_GIO - timedelta(hours=1)).isoformat(
                    timespec="microseconds")
                self.assertEqual(kho.count_follows_since("toi", moc), 1)

    # ===================================================== THEO DOI TRUYEN

    def test_theo_doi_truyen_tach_biet_voi_theo_doi_nguoi(self):
        """
        BANG RIENG. Theo doi truyen KHONG duoc lam tang so nguoi theo doi cua
        ai — gop hai con so lai la mot con so khong ai giai thich duoc.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.follow_story(StoryFollow(
                    follower_id="u1", novel_id="n1",
                    follow_id=story_follow_key("u1", "n1")))
                self.assertEqual(kho.follower_counts(["n1"])["n1"], 0)
                self.assertEqual(kho.story_follower_counts(["n1"])["n1"], 1)

    def test_nguoi_theo_doi_truyen_de_phat_thong_bao(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for u in ("u1", "u2"):
                    kho.follow_story(StoryFollow(
                        follower_id=u, novel_id="n1",
                        follow_id=story_follow_key(u, "n1")))
                self.assertEqual(set(kho.story_follower_ids("n1")),
                                 {"u1", "u2"})

    def test_truyen_dang_theo_doi(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.follow_story(StoryFollow(
                    follower_id="u1", novel_id="n1",
                    follow_id=story_follow_key("u1", "n1")))
                self.assertEqual(kho.followed_story_ids("u1"), ["n1"])
                self.assertEqual(kho.story_following_flags("u1", ["n1", "n2"]),
                                 {"n1"})

    # =============================================================== BAI DANG

    def test_tao_va_doc_lai_MOI_TRUONG(self):
        """
        Mot truong bi quen trong `PERSISTED_FIELDS` hay trong `_post_from` se im
        lang tra ve gia tri mac dinh — loai loi khong ai thay cho toi khi mot
        nguoi dung hoi vi sao bai cua ho mat anh.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bai = self._bai(kho, text="Nội dung", kind=PostKind.STORY_UPDATE,
                                novel_id="n1", image_key="posts/u1/p1/anh.webp",
                                image_mime="image/webp", image_width=800,
                                image_height=600, image_bytes=1234)
                doc = kho.get_post(bai.post_id)
                for truong in ("author_user_id", "text", "novel_id", "image_key",
                               "image_mime", "image_width", "image_height",
                               "image_bytes"):
                    self.assertEqual(getattr(doc, truong),
                                     getattr(bai, truong), truong)
                self.assertIs(doc.kind, PostKind.STORY_UPDATE)
                self.assertIs(doc.state, ContentState.VISIBLE)

    def test_bai_khong_ton_tai_tra_None_KHONG_nem(self):
        """
        Hai ban phai giong nhau o day. Mot ban nem va mot ban tra None nghia la
        tang dich vu xu ly dung o mock roi thanh 500 o that.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertIsNone(kho.get_post("khong-co"))

    def test_luu_va_doc_lai_trang_thai_kiem_duyet(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bai = self._bai(kho)
                bai.state = ContentState.REMOVED
                bai.removed_by = "qt1"
                bai.removed_reason = "spam"
                kho.save_post(bai)
                doc = kho.get_post(bai.post_id)
                self.assertIs(doc.state, ContentState.REMOVED)
                self.assertEqual(doc.removed_by, "qt1")
                self.assertEqual(doc.removed_reason, "spam")

    def test_danh_sach_loc_bai_da_go(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._bai(kho, text="Còn hiện")
                da_go = self._bai(kho, text="Đã gỡ")
                da_go.state = ContentState.REMOVED
                kho.save_post(da_go)
                ds, tong = kho.list_posts()
                self.assertEqual(tong, 1)
                self.assertEqual(ds[0].text, "Còn hiện")
                # Duong QUAN TRI thay ca hai.
                self.assertEqual(kho.list_posts(include_removed=True)[1], 2)

    def test_danh_sach_theo_tac_gia(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._bai(kho, tac_gia="u1")
                self._bai(kho, tac_gia="u2")
                ds, tong = kho.list_posts(author_ids=["u1"])
                self.assertEqual(tong, 1)
                self.assertEqual(ds[0].author_user_id, "u1")

    def test_danh_sach_nhieu_tac_gia_la_truy_van_IN(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for u in ("u1", "u2", "u3"):
                    self._bai(kho, tac_gia=u)
                self.assertEqual(kho.list_posts(author_ids=["u1", "u3"])[1], 2)

    def test_danh_sach_RONG_khac_han_None(self):
        """
        Gop hai truong hop nay la mot loi kinh dien: mot nguoi chua theo doi ai
        se thay bang tin cua TOAN he thong.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._bai(kho)
                self.assertEqual(kho.list_posts(author_ids=[])[1], 0)
                self.assertEqual(kho.list_posts(author_ids=None)[1], 1)

    def test_danh_sach_MOI_NHAT_truoc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(3):
                    self._bai(kho, text=f"Bài {i}", created_at=now_iso_us())
                self.assertEqual(kho.list_posts()[0][0].text, "Bài 2")

    def test_phan_trang_tong_DOC_LAP_voi_limit(self):
        """
        Appwrite tra `total` doc lap voi `limit` — ma phan trang dua vao do. Ban
        mock phai giong.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(5):
                    self._bai(kho, text=f"Bài {i}", created_at=now_iso_us())
                ds, tong = kho.list_posts(limit=2)
                self.assertEqual(len(ds), 2)
                self.assertEqual(tong, 5)

    def test_tim_theo_noi_dung(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._bai(kho, text="Chuyện về Luffy")
                self._bai(kho, text="Chuyện khác")
                self.assertEqual(kho.list_posts(query="Luffy")[1], 1)

    def test_dem_bai_theo_LO_chi_tinh_bai_con_hien(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self._bai(kho, tac_gia="u1")
                da_go = self._bai(kho, tac_gia="u1")
                da_go.state = ContentState.REMOVED
                kho.save_post(da_go)
                self._bai(kho, tac_gia="u2")
                dem = kho.post_counts(["u1", "u2", "u3"])
                self.assertEqual(dem["u1"], 1)
                self.assertEqual(dem["u2"], 1)
                self.assertEqual(dem["u3"], 0)

    def test_doc_nhieu_bai_theo_id(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                a, b = self._bai(kho), self._bai(kho)
                ra = kho.posts_by_ids([a.post_id, b.post_id, "khong-co"])
                self.assertEqual(set(ra), {a.post_id, b.post_id})

    def test_cong_don_bo_dem_khong_xuong_duoi_khong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bai = self._bai(kho)
                self.assertEqual(kho.bump_post_counter(bai.post_id,
                                                       "like_count", 1), 1)
                self.assertEqual(kho.bump_post_counter(bai.post_id,
                                                       "like_count", -5), 0)

    def test_cong_don_bai_khong_ton_tai_tra_khong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertEqual(
                    kho.bump_post_counter("khong-co", "like_count", 1), 0)

    def test_xoa_bai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bai = self._bai(kho)
                self.assertTrue(kho.delete_post(bai.post_id))
                self.assertIsNone(kho.get_post(bai.post_id))
                self.assertFalse(kho.delete_post(bai.post_id))

    # ============================================================ LUOT THICH

    def test_thich_hai_lan_bi_khoa_tat_dinh_chan(self):
        """
        Day la cho tinh duy nhat quan trong nhat cua ca tang xa hoi. Khong co
        no, hai lan bam nhanh lien tiep tao hai hang va so dem sai vinh vien.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                lk = PostLike(post_id="p1", user_id="u1",
                              like_id=post_like_key("u1", "p1"))
                self.assertTrue(kho.like_post(lk))
                self.assertFalse(kho.like_post(lk))
                self.assertEqual(kho.count_post_likes("p1"), 1)

    def test_bo_thich_roi_thich_lai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                khoa = post_like_key("u1", "p1")
                kho.like_post(PostLike(post_id="p1", user_id="u1", like_id=khoa))
                self.assertTrue(kho.unlike_post(khoa))
                self.assertFalse(kho.has_liked(khoa))
                self.assertTrue(kho.like_post(
                    PostLike(post_id="p1", user_id="u1", like_id=khoa)))

    def test_co_da_thich_cho_ca_TRANG(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for p in ("p1", "p3"):
                    kho.like_post(PostLike(post_id=p, user_id="toi",
                                           like_id=post_like_key("toi", p)))
                kho.like_post(PostLike(post_id="p2", user_id="khac",
                                       like_id=post_like_key("khac", "p2")))
                co = kho.liked_flags("toi", ["p1", "p2", "p3"])
                self.assertEqual(co, {"p1", "p3"})

    # ============================================================== BINH LUAN

    def test_tao_va_doc_lai_binh_luan(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bl = Comment(post_id="p1", author_user_id="u1", text="Hay",
                             parent_id="c0")
                kho.create_comment(bl)
                doc = kho.get_comment(bl.comment_id)
                self.assertEqual(doc.text, "Hay")
                self.assertEqual(doc.parent_id, "c0")

    def test_binh_luan_khong_ton_tai_tra_None(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertIsNone(kho.get_comment("khong-co"))

    def test_binh_luan_CU_NHAT_truoc(self):
        """Nguoc voi bang tin — mot cuoc trao doi doc theo thu tu no dien ra."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(3):
                    kho.create_comment(Comment(post_id="p1",
                                               author_user_id="u1",
                                               text=f"BL {i}",
                                               created_at=now_iso_us()))
                ds, _ = kho.list_comments("p1")
                self.assertEqual([c.text for c in ds], ["BL 0", "BL 1", "BL 2"])

    def test_loc_theo_binh_luan_cha(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                goc = Comment(post_id="p1", author_user_id="u1", text="Gốc")
                kho.create_comment(goc)
                kho.create_comment(Comment(post_id="p1", author_user_id="u2",
                                           text="Trả lời",
                                           parent_id=goc.comment_id))
                self.assertEqual(kho.list_comments("p1", parent_id="")[1], 1)
                self.assertEqual(
                    kho.list_comments("p1", parent_id=goc.comment_id)[1], 1)

    def test_tra_loi_cua_NHIEU_binh_luan_goc_mot_luot(self):
        """Khong co ham nay thi mot trang 20 binh luan goc thanh 20 truy van."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                goc = []
                for i in range(2):
                    c = Comment(post_id="p1", author_user_id="u1",
                                text=f"Gốc {i}", created_at=now_iso_us())
                    kho.create_comment(c)
                    goc.append(c)
                for c in goc:
                    for j in range(2):
                        kho.create_comment(Comment(
                            post_id="p1", author_user_id="u2",
                            text=f"TL {j}", parent_id=c.comment_id,
                            created_at=now_iso_us()))
                gom = kho.replies_for([c.comment_id for c in goc])
                self.assertEqual(len(gom[goc[0].comment_id]), 2)
                self.assertEqual(len(gom[goc[1].comment_id]), 2)

    def test_tra_loi_ton_trong_so_hien_san(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                goc = Comment(post_id="p1", author_user_id="u1", text="Gốc")
                kho.create_comment(goc)
                for j in range(5):
                    kho.create_comment(Comment(
                        post_id="p1", author_user_id="u2", text=f"TL {j}",
                        parent_id=goc.comment_id, created_at=now_iso_us()))
                gom = kho.replies_for([goc.comment_id], moi_cha=2)
                self.assertEqual(len(gom[goc.comment_id]), 2)

    def test_tra_loi_voi_danh_sach_rong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertEqual(kho.replies_for([]), {})

    def test_dem_binh_luan_chi_tinh_cai_con_hien(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_comment(Comment(post_id="p1", author_user_id="u1",
                                           text="Hiện"))
                go = Comment(post_id="p1", author_user_id="u1", text="Gỡ",
                             state=ContentState.REMOVED)
                kho.create_comment(go)
                self.assertEqual(kho.count_post_comments("p1"), 1)

    def test_xoa_binh_luan(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bl = Comment(post_id="p1", author_user_id="u1", text="X")
                kho.create_comment(bl)
                self.assertTrue(kho.delete_comment(bl.comment_id))
                self.assertFalse(kho.delete_comment(bl.comment_id))

    # =============================================================== THONG BAO

    def test_thong_bao_trung_khoa_chi_tao_MOT_lan(self):
        """Toan bo co che chong lap la tinh duy nhat cua khoa nay."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                khoa = notification_key("u1", "post_like", "u2", "p1",
                                        now=BAY_GIO)
                note = Notification(user_id="u1",
                                    kind=NotificationKind.POST_LIKE,
                                    actor_id="u2", subject_id="p1",
                                    notification_id=khoa)
                self.assertTrue(kho.create_notification_once(note))
                self.assertFalse(kho.create_notification_once(note))
                self.assertEqual(kho.list_notifications("u1")[1], 1)

    def test_tao_va_doc_lai_moi_truong_thong_bao(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_notification_once(Notification(
                    user_id="u1", kind=NotificationKind.COMMENT_REPLY,
                    actor_id="u2", subject_id="c1", subject_kind="comment",
                    preview="Xem trước", notification_id="n1"))
                doc = kho.list_notifications("u1")[0][0]
                self.assertIs(doc.kind, NotificationKind.COMMENT_REPLY)
                self.assertEqual(doc.actor_id, "u2")
                self.assertEqual(doc.subject_id, "c1")
                self.assertEqual(doc.subject_kind, "comment")
                self.assertEqual(doc.preview, "Xem trước")
                self.assertFalse(doc.read)

    def test_thong_bao_MOI_NHAT_truoc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(3):
                    kho.create_notification_once(Notification(
                        user_id="u1", actor_id=f"u{i}", preview=f"P{i}",
                        notification_id=f"n{i}", created_at=now_iso_us()))
                self.assertEqual(kho.list_notifications("u1")[0][0].preview,
                                 "P2")

    def test_dem_chua_doc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(2):
                    kho.create_notification_once(Notification(
                        user_id="u1", notification_id=f"n{i}"))
                self.assertEqual(kho.count_unread("u1"), 2)
                kho.mark_notification_read("u1", "n0")
                self.assertEqual(kho.count_unread("u1"), 1)

    def test_KHONG_danh_dau_duoc_thong_bao_nguoi_khac(self):
        """
        `user_id` la mot phan cua DIEU KIEN o CA HAI ban. Mot ban bo qua no la
        mot duong cham vao thong bao cua nguoi khac chi bang cach doan id.
        """
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_notification_once(Notification(
                    user_id="u1", notification_id="n1"))
                self.assertFalse(kho.mark_notification_read("nguoi-khac", "n1"))
                self.assertEqual(kho.count_unread("u1"), 1)

    def test_danh_dau_tat_ca(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(3):
                    kho.create_notification_once(Notification(
                        user_id="u1", notification_id=f"n{i}"))
                kho.create_notification_once(Notification(
                    user_id="u2", notification_id="khac"))
                self.assertEqual(kho.mark_all_read("u1"), 3)
                self.assertEqual(kho.count_unread("u1"), 0)
                # KHONG cham vao thong bao cua nguoi khac.
                self.assertEqual(kho.count_unread("u2"), 1)

    def test_chi_lay_thong_bao_chua_doc(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(2):
                    kho.create_notification_once(Notification(
                        user_id="u1", notification_id=f"n{i}"))
                kho.mark_notification_read("u1", "n0")
                self.assertEqual(
                    kho.list_notifications("u1", unread_only=True)[1], 1)

    # ================================================================= BAO CAO

    def test_bao_cao_trung_khoa_chi_MOT_hang(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bc = ContentReport(reporter_id="u1", target_kind="post",
                                   target_id="p1", target_owner_id="u2",
                                   reason=ReportReason.SPAM,
                                   report_id=report_key("u1", "post", "p1"))
                self.assertTrue(kho.create_report_once(bc))
                self.assertFalse(kho.create_report_once(bc))
                self.assertEqual(kho.count_reports(), 1)

    def test_tao_va_doc_lai_moi_truong_bao_cao(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_report_once(ContentReport(
                    reporter_id="u1", target_kind="comment", target_id="c1",
                    target_owner_id="u2", reason=ReportReason.COPYRIGHT,
                    detail="Sao chép", report_id="r1"))
                doc = kho.get_report("r1")
                self.assertEqual(doc.target_kind, "comment")
                self.assertEqual(doc.target_owner_id, "u2")
                self.assertIs(doc.reason, ReportReason.COPYRIGHT)
                self.assertEqual(doc.detail, "Sao chép")
                self.assertIs(doc.status, ReportStatus.OPEN)

    def test_bao_cao_khong_ton_tai_tra_None(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                self.assertIsNone(kho.get_report("khong-co"))

    def test_hang_doi_bao_cao_CU_NHAT_truoc(self):
        """Thu tu duy nhat khong lam ai bi bo quen vinh vien."""
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i in range(3):
                    kho.create_report_once(ContentReport(
                        reporter_id=f"u{i}", target_id="p1", report_id=f"r{i}",
                        created_at=now_iso_us()))
                ds, _ = kho.list_reports()
                self.assertEqual([r.report_id for r in ds], ["r0", "r1", "r2"])

    def test_loc_bao_cao_theo_trang_thai(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_report_once(ContentReport(
                    reporter_id="u1", target_id="p1", report_id="r1"))
                xong = ContentReport(reporter_id="u2", target_id="p2",
                                     report_id="r2",
                                     status=ReportStatus.RESOLVED)
                kho.create_report_once(xong)
                self.assertEqual(kho.list_reports(status=ReportStatus.OPEN)[1], 1)
                self.assertEqual(kho.count_reports(ReportStatus.OPEN), 1)
                self.assertEqual(kho.count_reports(), 2)

    def test_loc_bao_cao_theo_loai_doi_tuong(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                kho.create_report_once(ContentReport(
                    reporter_id="u1", target_kind="post", target_id="p1",
                    report_id="r1"))
                kho.create_report_once(ContentReport(
                    reporter_id="u1", target_kind="comment", target_id="c1",
                    report_id="r2"))
                self.assertEqual(kho.list_reports(target_kind="comment")[1], 1)

    def test_luu_ket_qua_xu_ly_bao_cao(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                bc = ContentReport(reporter_id="u1", target_id="p1",
                                   report_id="r1")
                kho.create_report_once(bc)
                bc.status = ReportStatus.DISMISSED
                bc.resolution_note = "Không vi phạm"
                bc.resolved_by = "qt1"
                kho.save_report(bc)
                doc = kho.get_report("r1")
                self.assertIs(doc.status, ReportStatus.DISMISSED)
                self.assertEqual(doc.resolution_note, "Không vi phạm")
                self.assertEqual(doc.resolved_by, "qt1")

    def test_dem_bao_cao_dang_mo_theo_LO(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                for i, tid in enumerate(["p1", "p1", "p2"]):
                    kho.create_report_once(ContentReport(
                        reporter_id=f"u{i}", target_id=tid, report_id=f"r{i}"))
                xong = ContentReport(reporter_id="u9", target_id="p3",
                                     report_id="r9",
                                     status=ReportStatus.RESOLVED)
                kho.create_report_once(xong)
                dem = kho.reports_for_targets(["p1", "p2", "p3", "p4"])
                self.assertEqual(dem["p1"], 2)
                self.assertEqual(dem["p2"], 1)
                # Da xu ly thi khong con dem la "dang mo".
                self.assertEqual(dem["p3"], 0)
                self.assertEqual(dem["p4"], 0)

    def test_dem_bao_cao_trong_cua_so_thoi_gian(self):
        for ten, kho in self._cac_kho():
            with self.subTest(kho=ten):
                cu = (BAY_GIO - timedelta(hours=5)).isoformat(
                    timespec="microseconds")
                kho.create_report_once(ContentReport(
                    reporter_id="u1", target_id="p1", report_id="r-cu",
                    created_at=cu))
                kho.create_report_once(ContentReport(
                    reporter_id="u1", target_id="p2", report_id="r-moi",
                    created_at=BAY_GIO.isoformat(timespec="microseconds")))
                moc = (BAY_GIO - timedelta(hours=1)).isoformat(
                    timespec="microseconds")
                self.assertEqual(kho.count_reports_since("u1", moc), 1)


class QuyenTaiLieuTest(unittest.TestCase):
    """
    Quyen tren tung hang Appwrite. Ban mock khong co khai niem nay, nen cac bai
    duoi day CHI chay tren ban Appwrite — day la mot dieu ma chi ban that lam.
    """

    def setUp(self) -> None:
        self.fake = FakeAppwrite()
        self.kho = _kho_appwrite(self.fake)

    def test_bao_cao_KHONG_cap_quyen_doc_cho_client_nao(self):
        """
        Hang bao cao chua `resolution_note` — ghi chu noi bo cua quan tri. Moi
        duong doc hop le deu di qua backend bang API key (API key bo qua
        permission), nen danh sach quyen rong khong hong chuc nang nao: no chi
        dong duong doc THANG tu trinh duyet.
        """
        self.kho.create_report_once(ContentReport(
            reporter_id="u1", target_id="p1", report_id="r1"))
        self.assertEqual(self.fake.perms["content_reports/r1"], [])

    def test_thong_bao_cap_quyen_cho_NGUOI_NHAN_khong_phai_nguoi_gay(self):
        self.kho.create_notification_once(Notification(
            user_id="nguoi-nhan", actor_id="nguoi-gay", notification_id="n1"))
        perms = self.fake.perms["notifications/n1"]
        self.assertIn('read("user:nguoi-nhan")', perms)
        self.assertNotIn('read("user:nguoi-gay")', perms)

    def test_bai_dang_co_quyen_doc_cong_khai(self):
        bai = Post(author_user_id="u1", text="X")
        self.kho.create_post(bai)
        self.assertIn('read("any")', self.fake.perms[f"posts/{bai.post_id}"])

    def test_khong_hang_nao_cap_quyen_GHI_cho_client(self):
        """
        Moi thao tac ghi di qua backend bang API key. Mot quyen `update` tren
        hang cua chinh minh la du de doi `state` cua bai da bi go, hoac doi
        `like_count` thanh mot con so bat ky.
        """
        bai = Post(author_user_id="u1", text="X")
        self.kho.create_post(bai)
        self.kho.create_comment(Comment(post_id=bai.post_id,
                                        author_user_id="u1", text="Y",
                                        comment_id="c1"))
        self.kho.like_post(PostLike(post_id=bai.post_id, user_id="u1",
                                    like_id="lk1"))
        self.kho.create_notification_once(Notification(user_id="u1",
                                                       notification_id="n1"))
        for khoa, perms in self.fake.perms.items():
            for p in perms:
                self.assertTrue(p.startswith("read("),
                                f"{khoa} có quyền không phải read: {p}")


class SchemaTest(unittest.TestCase):
    """
    Ma nguon va lop khai bao schema phai khop nhau.

    Ba nguon co the LECH, va moi cap lech la mot loai loi rieng:
      - `SOCIAL_PERSISTED_FIELDS` <-> `scripts/setup_appwrite.py`:
        gui mot thuoc tinh chua ton tai thi Appwrite tu choi CA document.
      - `to_dict()` <-> `SOCIAL_PERSISTED_FIELDS`: mot truong khong duoc liet ke
        se im lang khong bao gio duoc luu.
    """

    def _schema(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "setup_appwrite", "scripts/setup_appwrite.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.SCHEMA

    BAY_BANG = ("user_follows", "story_follows", "posts", "post_likes",
                "comments", "notifications", "content_reports")

    def test_schema_khai_du_bay_bang(self):
        schema = self._schema()
        for ten in self.BAY_BANG:
            self.assertIn(ten, schema)

    def test_moi_truong_duoc_luu_deu_co_cot_trong_schema(self):
        from server.appwrite_social import SOCIAL_PERSISTED_FIELDS

        schema = self._schema()
        for bang, truong in SOCIAL_PERSISTED_FIELDS.items():
            cot = {a[0] for a in schema[bang]["attributes"]}
            for t in truong:
                self.assertIn(t, cot, f"{bang}.{t} thiếu cột trong schema")

    def test_moi_truong_cua_ban_ghi_deu_duoc_liet_ke(self):
        from server.appwrite_social import (COL_COMMENTS, COL_NOTIFICATIONS,
                                            COL_POSTS, COL_POST_LIKES,
                                            COL_REPORTS, COL_STORY_FOLLOWS,
                                            COL_USER_FOLLOWS,
                                            SOCIAL_PERSISTED_FIELDS)

        mau = [
            (COL_USER_FOLLOWS, UserFollow(follower_id="a", target_id="b")),
            (COL_STORY_FOLLOWS, StoryFollow(follower_id="a", novel_id="n")),
            (COL_POSTS, Post(author_user_id="a")),
            (COL_POST_LIKES, PostLike(post_id="p", user_id="u")),
            (COL_COMMENTS, Comment(post_id="p", author_user_id="a")),
            (COL_NOTIFICATIONS, Notification(user_id="u")),
            (COL_REPORTS, ContentReport(reporter_id="u")),
        ]
        for bang, ban_ghi in mau:
            duoc_luu = set(SOCIAL_PERSISTED_FIELDS[bang])
            for truong in ban_ghi.to_dict():
                self.assertIn(truong, duoc_luu,
                              f"{bang}.{truong} không bao giờ được lưu")

    def test_moi_chi_muc_tro_toi_cot_co_that(self):
        """Mot chi muc tro toi cot khong ton tai lam Appwrite tu choi ca bang."""
        schema = self._schema()
        for ten in self.BAY_BANG:
            cot = {a[0] for a in schema[ten]["attributes"]}
            for chi_muc, _, khoa in schema[ten]["indexes"]:
                for k in khoa:
                    self.assertIn(k, cot, f"{ten}.{chi_muc} trỏ tới {k}")

    def test_enum_nhat_ky_co_du_thao_tac_xa_hoi(self):
        """
        Kiem duyet xa hoi ghi vao CUNG bang `moderation_events`. Mot thao tac
        khong nam trong enum se lam Appwrite tu choi hang — tuc la mat mot dong
        nhat ky, dung luc can no nhat.
        """
        schema = self._schema()
        cot = dict((a[0], a) for a in schema["moderation_events"]["attributes"])
        gia_tri = set(cot["action"][3])
        for hanh_dong in ("post_removed", "post_restored", "comment_removed",
                          "comment_restored", "report_resolved",
                          "report_dismissed"):
            self.assertIn(hanh_dong, gia_tri)


if __name__ == "__main__":
    unittest.main()
