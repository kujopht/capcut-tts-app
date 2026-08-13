"""
Tang service cua tac gia, chay tren kho mock.

Bo test nay lo hai thu ma `test_creator_policy` khong lo duoc: cac buoc chuyen
co GHI dung cho hay khong, va co che chong dua/chong farm co that su chan duoc
khong khi co mot cai kho o duoi.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.creator import ALREADY_CREDITED, AuthorStateError, UsernameError
from server.creator_service import CreatorService
from server.domain import AuthorStatus, Novel, PublishState

BAY_GIO = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)


class Base(unittest.TestCase):
    def setUp(self):
        self.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        self.svc = CreatorService(self.identity, self.store)
        self.nguoi = self.identity.register("a@x.local", "matkhau123", "Nam Kujo")
        self.khac = self.identity.register("b@x.local", "matkhau123", "Người Đọc")

    def _nop_don(self, profile=None):
        return self.svc.apply(
            profile or self.nguoi,
            pen_name="Kẻ Dệt Mộng",
            bio="Viết fanfic One Piece.",
            genres=["One Piece", "Phiêu lưu"],
            intro="Tôi viết fanfic đã ba năm.",
            accepted_rules=True,
            now=BAY_GIO,
        )


class ApplicationFlowTest(Base):
    def test_nguoi_dung_moi_khong_duoc_xuat_ban(self):
        self.assertIs(self.nguoi.author_status, AuthorStatus.NONE)
        with self.assertRaises(AuthorStateError) as ctx:
            self.svc.assert_can_publish(self.nguoi)
        self.assertIn("đăng ký tác giả", str(ctx.exception))

    def test_nop_don_thi_sang_pending(self):
        app = self._nop_don()
        self.assertIs(app.status, AuthorStatus.PENDING)
        self.assertIs(self.identity.get_profile(self.nguoi.user_id).author_status,
                      AuthorStatus.PENDING)

    def test_khong_tich_dong_y_quy_dinh_thi_khong_nop_duoc(self):
        with self.assertRaises(AuthorStateError):
            self.svc.apply(self.nguoi, pen_name="X", intro="Xin chào",
                           accepted_rules=False, now=BAY_GIO)

    def test_thieu_gioi_thieu_thi_khong_nop_duoc(self):
        with self.assertRaises(AuthorStateError):
            self.svc.apply(self.nguoi, pen_name="Bút Danh", intro="  ",
                           accepted_rules=True, now=BAY_GIO)

    def test_but_danh_qua_ngan_thi_khong_nop_duoc(self):
        with self.assertRaises(AuthorStateError):
            self.svc.apply(self.nguoi, pen_name="A", intro="Xin chào",
                           accepted_rules=True, now=BAY_GIO)

    def test_dang_cho_duyet_thi_khong_nop_them(self):
        self._nop_don()
        with self.assertRaises(AuthorStateError):
            self._nop_don()

    def test_pending_thi_van_chua_xuat_ban_duoc_nhung_thong_diep_khac(self):
        self._nop_don()
        p = self.identity.get_profile(self.nguoi.user_id)
        with self.assertRaises(AuthorStateError) as ctx:
            self.svc.assert_can_publish(p)
        self.assertIn("chờ duyệt", str(ctx.exception))
        # Va phai noi ro ban nhap van sua duoc — nguoi dung dang lo mat bai.
        self.assertIn("nháp", str(ctx.exception))

    def test_duyet_roi_thi_xuat_ban_duoc(self):
        self._nop_don()
        self.svc.approve(self.nguoi.user_id, note="ổn")
        p = self.identity.get_profile(self.nguoi.user_id)
        self.assertIs(p.author_status, AuthorStatus.APPROVED)
        self.svc.assert_can_publish(p)      # khong nem

    def test_tu_choi_BAT_BUOC_co_ghi_chu(self):
        self._nop_don()
        with self.assertRaises(AuthorStateError):
            self.svc.reject(self.nguoi.user_id, note="")

    def test_ghi_chu_tu_choi_hien_cho_nguoi_nop(self):
        self._nop_don()
        self.svc.reject(self.nguoi.user_id, note="Giới thiệu quá ngắn.")
        p = self.identity.get_profile(self.nguoi.user_id)
        trang_thai = self.svc.creator_state(p)
        self.assertEqual(trang_thai["author_status"], "rejected")
        self.assertEqual(trang_thai["application"]["reviewer_note"],
                         "Giới thiệu quá ngắn.")

    def _dong_dau_tu_choi(self):
        """
        Dat `decided_at` ve MOC CO DINH sau khi tu choi.

        `reject()` dong dau bang dong ho THAT, con bai test tiem
        `now=BAY_GIO+4d` — hai dong ho tron lan, va bai test chi xanh khi gio
        that tinh co nam canh BAY_GIO. Da do duoc: bo test do dung vao hom
        dong ho that troi qua ranh gioi cooldown. Ghim ve BAY_GIO de bai test
        noi ve THOI GIAN TUONG DOI (4 ngay sau khi tu choi), khong phai ve
        hom nay la ngay nao.
        """
        app = self.store.get_application(self.nguoi.user_id)
        app.decided_at = BAY_GIO.isoformat(timespec="seconds")
        self.store.save_application(app)

    def test_nop_lai_sau_thoi_gian_cho_thi_xoa_ghi_chu_cu(self):
        self._nop_don()
        self.svc.reject(self.nguoi.user_id, note="Chưa ổn.")
        self._dong_dau_tu_choi()
        p = self.identity.get_profile(self.nguoi.user_id)
        sau = BAY_GIO + timedelta(days=4)
        self.svc.apply(p, pen_name="Kẻ Dệt Mộng", intro="Tôi viết lại rồi.",
                       accepted_rules=True, now=sau)
        app = self.store.get_application(self.nguoi.user_id)
        self.assertIs(app.status, AuthorStatus.PENDING)
        self.assertEqual(app.reviewer_note, "")
        self.assertEqual(app.attempts, 2)

    def test_nop_lai_GIU_nguyen_khoa_don(self):
        # Doi khoa la lam moi lien ket cu tro toi mot ban ghi khong con.
        app1 = self._nop_don()
        self.svc.reject(self.nguoi.user_id, note="Chưa ổn.")
        self._dong_dau_tu_choi()
        p = self.identity.get_profile(self.nguoi.user_id)
        app2 = self.svc.apply(p, pen_name="X Y", intro="Viết lại.",
                              accepted_rules=True,
                              now=BAY_GIO + timedelta(days=4))
        self.assertEqual(app1.application_id, app2.application_id)
        self.assertEqual(app1.created_at, app2.created_at)

    def test_treo_thi_khong_xuat_ban_duoc_nua(self):
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)
        self.svc.suspend(self.nguoi.user_id, note="Vi phạm.")
        p = self.identity.get_profile(self.nguoi.user_id)
        with self.assertRaises(AuthorStateError) as ctx:
            self.svc.assert_can_publish(p)
        self.assertIn("tạm dừng", str(ctx.exception))

    def test_treo_KHONG_go_xuat_ban_truyen_da_co(self):
        """
        Mot tac gia bi treo van con doc gia. Rut truyen cua ho khoi tay nguoi doc
        la mot hinh phat danh vao nguoi khac.
        """
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)
        truyen = self.store.create_novel(Novel(owner_id=self.nguoi.user_id,
                                               title="Đã xuất bản",
                                               state=PublishState.PUBLISHED))
        self.svc.suspend(self.nguoi.user_id, note="Vi phạm.")
        self.assertIs(self.store.get_novel(truyen.novel_id).state,
                      PublishState.PUBLISHED)

    def test_phuc_hoi_sau_khi_treo(self):
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)
        self.svc.suspend(self.nguoi.user_id, note="x")
        self.svc.restore(self.nguoi.user_id, note="đã xử lý")
        self.assertIs(self.identity.get_profile(self.nguoi.user_id).author_status,
                      AuthorStatus.APPROVED)

    def test_khong_the_duyet_mot_nguoi_chua_nop_don(self):
        with self.assertRaises(AuthorStateError):
            self.svc.approve(self.nguoi.user_id)

    def test_danh_sach_don_cho_duyet(self):
        self._nop_don()
        self._nop_don(self.khac)
        rows, total = self.svc.pending_applications()
        self.assertEqual(total, 2)
        self.assertEqual({r["user_id"] for r in rows},
                         {self.nguoi.user_id, self.khac.user_id})

    def test_trang_thai_creator_gom_du_thu_giao_dien_can(self):
        d = self.svc.creator_state(self.nguoi)
        for khoa in ("author_status", "can_publish", "can_apply",
                     "apply_blocked_reason", "username", "application"):
            self.assertIn(khoa, d)
        self.assertFalse(d["can_publish"])
        self.assertTrue(d["can_apply"])

    def test_tac_gia_da_duyet_thi_trang_thai_co_hang(self):
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)
        d = self.svc.creator_state(self.identity.get_profile(self.nguoi.user_id))
        self.assertEqual(d["rank"]["key"], "tan_but")
        self.assertEqual(d["qualified_listens"], 0)


class UsernameStoreTest(Base):
    def test_dat_va_doc_lai(self):
        self.svc.set_username(self.nguoi, "Kẻ Dệt Mộng")
        self.assertEqual(self.identity.get_profile(self.nguoi.user_id).username,
                         "ke-det-mong")

    def test_hai_nguoi_khong_the_lay_cung_mot_ten(self):
        self.svc.set_username(self.nguoi, "namkujo")
        with self.assertRaises(UsernameError):
            self.svc.set_username(self.khac, "namkujo")

    def test_kiem_trung_KHONG_phan_biet_cach_viet(self):
        self.svc.set_username(self.nguoi, "ke-det-mong")
        with self.assertRaises(UsernameError):
            self.svc.set_username(self.khac, "Kẻ Dệt Mộng")

    def test_doi_ten_cua_chinh_minh_thi_duoc(self):
        self.svc.set_username(self.nguoi, "namkujo")
        self.svc.set_username(self.nguoi, "namkujo")     # khong nem
        self.svc.set_username(self.nguoi, "nam-kujo-2")

    def test_chua_chon_username_thi_KHONG_co_trang_cong_khai(self):
        self.assertIsNone(self.svc.public_profile_by_username(""))
        self.assertIsNone(self.svc.public_profile_by_username("khong-ton-tai"))

    def test_trang_cong_khai_khong_lo_email(self):
        self.svc.set_username(self.nguoi, "namkujo")
        ra = self.svc.public_profile_by_username("namkujo")
        self.assertNotIn("email", ra)
        self.assertEqual(ra["display_name"], "Nam Kujo")

    def test_trang_cong_khai_CHI_liet_ke_truyen_da_xuat_ban(self):
        self.svc.set_username(self.nguoi, "namkujo")
        self.store.create_novel(Novel(owner_id=self.nguoi.user_id, title="Nháp",
                                      state=PublishState.DRAFT))
        self.store.create_novel(Novel(owner_id=self.nguoi.user_id, title="Công khai",
                                      state=PublishState.PUBLISHED))
        ra = self.svc.public_profile_by_username("namkujo")
        self.assertEqual([n["title"] for n in ra["novels"]], ["Công khai"])

    def test_tim_nguoi_CHI_tra_nguoi_da_co_username(self):
        # Chua chon username thi chua co trang cong khai, va hien ho trong ket
        # qua la dua nguoi dung toi mot lien ket khong mo duoc.
        self.svc.set_username(self.nguoi, "namkujo")
        ra = self.svc.search_people("")
        self.assertEqual([p["username"] for p in ra["people"]], ["namkujo"])

    def test_tim_theo_ten_hien_thi_co_dau(self):
        self.svc.set_username(self.khac, "nguoidoc")
        ra = self.svc.search_people("Người Đọc")
        self.assertEqual(len(ra["people"]), 1)

    def test_tim_theo_username_khong_dau(self):
        self.svc.set_username(self.nguoi, "ke-det-mong")
        self.assertEqual(len(self.svc.search_people("Kẻ Dệt")["people"]), 1)

    def test_muc_tac_gia_CHI_tra_nguoi_da_duyet(self):
        self.svc.set_username(self.nguoi, "tacgia")
        self.svc.set_username(self.khac, "nguoidoc")
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)
        ra = self.svc.search_people("", authors_only=True)
        self.assertEqual([p["username"] for p in ra["people"]], ["tacgia"])

    def test_ket_qua_tim_kiem_KHONG_lo_trang_thai_duyet(self):
        self.svc.set_username(self.nguoi, "tacgia")
        self._nop_don()          # dang pending
        ra = self.svc.search_people("")
        self.assertNotIn("author_status", ra["people"][0])
        self.assertFalse(ra["people"][0]["is_author"])

    def test_ket_qua_tim_kiem_gon_KHONG_kem_bio_dai(self):
        self.svc.set_username(self.nguoi, "tacgia")
        self.svc.set_bio(self.nguoi, "x" * 300)
        ra = self.svc.search_people("")
        self.assertNotIn("bio", ra["people"][0])


class ListenCreditTest(Base):
    def setUp(self):
        super().setUp()
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)

    def _nghe(self, listener, giay=60, now=BAY_GIO, dai=600):
        return self.svc.record_listen(
            listener_id=listener, chapter_id="chp_1",
            author_id=self.nguoi.user_id,
            listened_seconds=giay, duration_seconds=dai, now=now)

    def test_nghe_du_lau_thi_cong_mot(self):
        ra = self._nghe(self.khac.user_id)
        self.assertTrue(ra["credited"])
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 1)

    def test_bam_phat_roi_tat_thi_KHONG_cong(self):
        ra = self._nghe(self.khac.user_id, giay=3)
        self.assertFalse(ra["credited"])
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 0)

    def test_tac_gia_tu_nghe_thi_KHONG_cong(self):
        ra = self._nghe(self.nguoi.user_id)
        self.assertFalse(ra["credited"])
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 0)

    def test_nghe_lai_trong_24_gio_KHONG_cong_them(self):
        self._nghe(self.khac.user_id)
        ra = self._nghe(self.khac.user_id, now=BAY_GIO + timedelta(hours=3))
        self.assertFalse(ra["credited"])
        self.assertEqual(ra["reason"], ALREADY_CREDITED)
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 1)

    def test_bam_phat_muoi_lan_lien_tuc_van_chi_cong_mot(self):
        for i in range(10):
            self._nghe(self.khac.user_id, now=BAY_GIO + timedelta(minutes=i))
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 1)

    def test_hom_sau_thi_cong_them(self):
        self._nghe(self.khac.user_id)
        self._nghe(self.khac.user_id, now=BAY_GIO + timedelta(hours=25))
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 2)

    def test_hai_nguoi_khac_nhau_thi_cong_hai(self):
        thu_ba = self.identity.register("c@x.local", "matkhau123", "C")
        self._nghe(self.khac.user_id)
        self._nghe(thu_ba.user_id)
        self.assertEqual(self.store.get_stats(self.nguoi.user_id).qualified_listens, 2)

    def test_khoa_tat_dinh_chan_duoc_cuoc_dua(self):
        """
        Hai request cung luc deu doc thay "chua co" roi cung ghi. Khoa tat dinh
        bien buoc ghi thu hai thanh mot xung dot, nen ket qua la MOT lan cong.
        """
        from server.creator import credit_key
        from server.domain import ListenCredit
        khoa = credit_key(self.khac.user_id, "chp_1", BAY_GIO)
        that = ListenCredit(listener_id=self.khac.user_id,
                            author_id=self.nguoi.user_id,
                            chapter_id="chp_1", credit_id=khoa)
        self.assertTrue(self.store.create_credit_once(that))
        self.assertFalse(self.store.create_credit_once(that))

    def test_dung_lai_ban_tong_hop_tu_bang_su_that(self):
        self._nghe(self.khac.user_id)
        # Gia lap ban tong hop bi lech (mot buoc cong bi mat vi loi mang).
        stats = self.store.get_stats(self.nguoi.user_id)
        stats.qualified_listens = 999
        self.store.save_stats(stats)
        lai = self.svc.recount_listens(self.nguoi.user_id)
        self.assertEqual(lai.qualified_listens, 1)

    def test_hang_len_theo_so_lan_nghe(self):
        stats = self.store.get_stats(self.nguoi.user_id)
        stats.qualified_listens = 250
        self.store.save_stats(stats)
        d = self.svc.creator_state(self.identity.get_profile(self.nguoi.user_id))
        self.assertEqual(d["rank"]["key"], "ke_det_mong")


class GrandfatherTest(Base):
    def test_nguoi_da_co_truyen_xuat_ban_duoc_cong_nhan(self):
        """
        Neu bat co che chan xuat ban ma khong chay buoc nay, moi nguoi dang co
        truyen se mat quyen xuat ban chuong tiep theo cua chinh truyen ho — mot
        loi khoa nguoi dung ra khoi cong viec cua ho, va no am tham.
        """
        self.store.create_novel(Novel(owner_id=self.nguoi.user_id, title="Cũ",
                                      state=PublishState.PUBLISHED))
        ke_hoach = self.svc.grandfather_existing_authors(dry_run=True)
        self.assertEqual(ke_hoach["would_approve"], 1)
        # `dry_run` la MAC DINH va khong doi gi ca.
        self.assertIs(self.identity.get_profile(self.nguoi.user_id).author_status,
                      AuthorStatus.NONE)

        self.svc.grandfather_existing_authors(dry_run=False)
        self.assertIs(self.identity.get_profile(self.nguoi.user_id).author_status,
                      AuthorStatus.APPROVED)
        # Va co mot ban ghi don giai thich vi sao.
        app = self.store.get_application(self.nguoi.user_id)
        self.assertIn("tự động", app.reviewer_note)

    def test_chi_co_ban_nhap_thi_KHONG_duoc_cong_nhan(self):
        self.store.create_novel(Novel(owner_id=self.nguoi.user_id, title="Nháp",
                                      state=PublishState.DRAFT))
        self.assertEqual(
            self.svc.grandfather_existing_authors(dry_run=True)["would_approve"], 0)

    def test_KHONG_tu_dong_bo_treo_cho_ai(self):
        # Treo la mot quyet dinh cua nguoi. Migration khong duoc lat lai no.
        self._nop_don()
        self.svc.approve(self.nguoi.user_id)
        self.svc.suspend(self.nguoi.user_id, note="x")
        self.store.create_novel(Novel(owner_id=self.nguoi.user_id, title="Cũ",
                                      state=PublishState.PUBLISHED))
        ra = self.svc.grandfather_existing_authors(dry_run=False)
        self.assertIs(self.identity.get_profile(self.nguoi.user_id).author_status,
                      AuthorStatus.SUSPENDED)
        self.assertIn("bo_qua_dang_bi_treo", [p["action"] for p in ra["plan"]])

    def test_chay_lai_bao_nhieu_lan_cung_duoc(self):
        self.store.create_novel(Novel(owner_id=self.nguoi.user_id, title="Cũ",
                                      state=PublishState.PUBLISHED))
        self.svc.grandfather_existing_authors(dry_run=False)
        lan_hai = self.svc.grandfather_existing_authors(dry_run=False)
        self.assertEqual(lan_hai["would_approve"], 0)


if __name__ == "__main__":
    unittest.main()
