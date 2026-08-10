"""
Chinh sach tac gia: username, trang thai duyet, hang, va mot lan nghe hop le.

Day la nhung quy tac ma sai mot chut la sai ca he thong uy tin. `server/creator.py`
la Python thuan va moi ham nhan `now`, nen bo test nay dieu khien duoc thoi gian
va khong cham vao mang hay kho nao.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from server import creator
from server.creator import (
    ALREADY_CREDITED,
    CREDITED,
    NOT_AUTHENTICATED,
    OWN_CHAPTER,
    RANK_TIERS,
    TOO_SHORT,
    UsernameError,
    can_publish,
    can_resubmit,
    can_transition,
    credit_key,
    dedupe_day_bucket,
    evaluate_listen,
    next_rank,
    normalize_username,
    public_profile,
    rank_for,
    rank_progress,
    required_seconds,
    searchable_authors,
    suggest_username,
    validate_username,
)
from server.domain import AuthorStatus

BAY_GIO = datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc)


class UsernameTest(unittest.TestCase):
    def test_bo_dau_va_ha_chu_thuong(self):
        # Hai nguoi khong duoc lay hai username ma nguoi doc nhin thay nhu nhau.
        self.assertEqual(normalize_username("Kẻ Dệt Mộng"), "ke-det-mong")
        self.assertEqual(normalize_username("  NamKujo  "), "namkujo")
        self.assertEqual(normalize_username("Đặng.Văn.A"), "dang-van-a")

    def test_hai_cach_viet_cham_cung_mot_o(self):
        self.assertEqual(normalize_username("Kẻ Dệt Mộng"),
                         normalize_username("ke det mong"))

    def test_gach_ngang_lien_tiep_va_o_hai_dau_bi_don(self):
        self.assertEqual(normalize_username("--nam--kujo--"), "nam-kujo")

    def test_do_dai(self):
        with self.assertRaises(UsernameError):
            validate_username("ab")
        with self.assertRaises(UsernameError):
            validate_username("x" * 25)
        self.assertEqual(validate_username("abc"), "abc")

    def test_ky_tu_khong_cho_phep(self):
        for xau in ("nam kujo!", "nam@kujo", "nam/kujo", "nam..kujo!!"):
            with self.assertRaises(UsernameError, msg=xau):
                validate_username(xau)

    def test_ten_bi_giu_lai(self):
        # Hai nhom: duong dan that cua site, va cac ten ngu y quyen han.
        for xau in ("admin", "support", "login", "creator", "u", "official"):
            with self.assertRaises(UsernameError, msg=xau):
                validate_username(xau)

    def test_ten_giu_lai_bat_ca_khi_viet_hoa_co_dau(self):
        with self.assertRaises(UsernameError):
            validate_username("Admin")

    def test_goi_y_tranh_ten_da_co(self):
        self.assertEqual(suggest_username("Nam Kujo", "x@y.z"), "nam-kujo")
        self.assertEqual(suggest_username("Nam Kujo", "x@y.z", ["nam-kujo"]),
                         "nam-kujo-2")

    def test_goi_y_lui_ve_email_khi_ten_hien_thi_khong_dung_duoc(self):
        self.assertEqual(suggest_username("A", "hainam@example.com"), "hainam")

    def test_goi_y_khong_bao_gio_tra_ten_bi_giu_lai(self):
        self.assertNotEqual(suggest_username("Admin", "admin@example.com"), "admin")

    def test_goi_y_khong_vuot_do_dai_toi_da(self):
        ra = suggest_username("x" * 50, "y@z.w")
        self.assertLessEqual(len(ra), creator.USERNAME_MAX)


class TransitionTest(unittest.TestCase):
    def test_khong_co_buoc_nhay_tu_none_sang_approved(self):
        """
        Moi tac gia deu phai di qua mot ban ghi don, ke ca khi duoc grandfather.
        Nho vay lich su luon giai thich duoc "vi sao nguoi nay duoc xuat ban".
        """
        self.assertFalse(can_transition(AuthorStatus.NONE, AuthorStatus.APPROVED))
        self.assertTrue(can_transition(AuthorStatus.NONE, AuthorStatus.PENDING))

    def test_cac_buoc_hop_le(self):
        hop_le = [
            (AuthorStatus.NONE, AuthorStatus.PENDING),
            (AuthorStatus.PENDING, AuthorStatus.APPROVED),
            (AuthorStatus.PENDING, AuthorStatus.REJECTED),
            (AuthorStatus.REJECTED, AuthorStatus.PENDING),
            (AuthorStatus.APPROVED, AuthorStatus.SUSPENDED),
            (AuthorStatus.SUSPENDED, AuthorStatus.APPROVED),
        ]
        for cu, moi in hop_le:
            self.assertTrue(can_transition(cu, moi), f"{cu} -> {moi}")

    def test_cac_buoc_bi_cam(self):
        cam = [
            (AuthorStatus.APPROVED, AuthorStatus.REJECTED),
            (AuthorStatus.SUSPENDED, AuthorStatus.PENDING),
            (AuthorStatus.REJECTED, AuthorStatus.APPROVED),
            (AuthorStatus.PENDING, AuthorStatus.PENDING),
            (AuthorStatus.NONE, AuthorStatus.SUSPENDED),
        ]
        for cu, moi in cam:
            self.assertFalse(can_transition(cu, moi), f"{cu} -> {moi}")

    def test_chi_approved_duoc_xuat_ban(self):
        for s in AuthorStatus:
            self.assertEqual(can_publish(s), s is AuthorStatus.APPROVED)

    def test_cho_nop_lai_sau_khi_bi_tu_choi(self):
        vua_bi = (BAY_GIO - timedelta(days=1)).isoformat()
        duoc, ly_do = can_resubmit(AuthorStatus.REJECTED, vua_bi, now=BAY_GIO)
        self.assertFalse(duoc)
        self.assertIn("ngày", ly_do)

        lau_roi = (BAY_GIO - timedelta(days=5)).isoformat()
        duoc, _ = can_resubmit(AuthorStatus.REJECTED, lau_roi, now=BAY_GIO)
        self.assertTrue(duoc)

    def test_dang_cho_duyet_thi_khong_nop_them(self):
        duoc, ly_do = can_resubmit(AuthorStatus.PENDING, None, now=BAY_GIO)
        self.assertFalse(duoc)
        self.assertIn("chờ duyệt", ly_do)

    def test_moc_thoi_gian_hong_khong_chan_nguoi_dung(self):
        # Du lieu xau khong duoc bien thanh mot cai cua bi khoa im lang.
        duoc, _ = can_resubmit(AuthorStatus.REJECTED, "khong-phai-ngay", now=BAY_GIO)
        self.assertTrue(duoc)


class RankTest(unittest.TestCase):
    def test_nguong_tang_dan_va_bac_lien_tuc(self):
        for truoc, sau in zip(RANK_TIERS, RANK_TIERS[1:]):
            self.assertLess(truoc.min_listens, sau.min_listens)
            self.assertEqual(sau.level, truoc.level + 1)

    def test_khoa_khong_trung_va_ten_khong_trung(self):
        self.assertEqual(len({t.key for t in RANK_TIERS}), len(RANK_TIERS))
        self.assertEqual(len({t.title for t in RANK_TIERS}), len(RANK_TIERS))

    def test_bac_dau_tien_bat_dau_tu_khong(self):
        # Mot tac gia vua duoc duyet phai co hang, khong phai `None`.
        self.assertEqual(RANK_TIERS[0].min_listens, 0)
        self.assertEqual(rank_for(0).key, "tan_but")

    def test_hang_theo_so_lan_nghe(self):
        self.assertEqual(rank_for(0).key, "tan_but")
        self.assertEqual(rank_for(49).key, "tan_but")
        self.assertEqual(rank_for(50).key, "nguoi_ke_chuyen")
        self.assertEqual(rank_for(999).key, "ke_det_mong")
        self.assertEqual(rank_for(20_000).key, "than_but")
        self.assertEqual(rank_for(10_000_000).key, "than_but")

    def test_hang_ke_tiep(self):
        self.assertEqual(next_rank(0).key, "nguoi_ke_chuyen")
        self.assertIsNone(next_rank(20_000))

    def test_chang_duong_toi_hang_sau(self):
        d = rank_progress(50)
        self.assertEqual(d["key"], "nguoi_ke_chuyen")
        self.assertEqual(d["next_at"], 250)
        self.assertEqual(d["remaining"], 200)
        self.assertEqual(d["percent"], 0)

        giua = rank_progress(150)
        self.assertEqual(giua["percent"], 50)

    def test_hang_cao_nhat_thi_day_100_phan_tram(self):
        d = rank_progress(30_000)
        self.assertIsNone(d["next_key"])
        self.assertEqual(d["percent"], 100)
        self.assertEqual(d["remaining"], 0)


class QualifiedListenTest(unittest.TestCase):
    def test_nguong_theo_do_dai(self):
        self.assertEqual(required_seconds(600), 30.0)      # chuong dai
        self.assertEqual(required_seconds(20), 15.0)       # chuong ngan -> 75%
        self.assertEqual(required_seconds(0), 30.0)        # khong biet -> chat nhat

    def test_bam_phat_roi_tat_ngay_KHONG_tinh(self):
        duoc, ly_do = evaluate_listen(
            listener_id="usr_b", author_id="usr_a",
            listened_seconds=2, duration_seconds=600, now=BAY_GIO)
        self.assertFalse(duoc)
        self.assertEqual(ly_do, TOO_SHORT)

    def test_nghe_du_lau_thi_tinh(self):
        duoc, ly_do = evaluate_listen(
            listener_id="usr_b", author_id="usr_a",
            listened_seconds=31, duration_seconds=600, now=BAY_GIO)
        self.assertTrue(duoc)
        self.assertEqual(ly_do, CREDITED)

    def test_chuong_ngan_van_tinh_duoc(self):
        # Mot chuong 24 giay khong bao gio dat nguong 30 giay tuyet doi.
        duoc, _ = evaluate_listen(
            listener_id="usr_b", author_id="usr_a",
            listened_seconds=18, duration_seconds=24, now=BAY_GIO)
        self.assertTrue(duoc)

    def test_khach_an_danh_khong_tinh_o_V1(self):
        duoc, ly_do = evaluate_listen(
            listener_id=None, author_id="usr_a",
            listened_seconds=600, duration_seconds=600, now=BAY_GIO)
        self.assertFalse(duoc)
        self.assertEqual(ly_do, NOT_AUTHENTICATED)

    def test_tac_gia_tu_nghe_KHONG_tinh(self):
        duoc, ly_do = evaluate_listen(
            listener_id="usr_a", author_id="usr_a",
            listened_seconds=600, duration_seconds=600, now=BAY_GIO)
        self.assertFalse(duoc)
        self.assertEqual(ly_do, OWN_CHAPTER)

    def test_tu_nghe_bi_chan_TRUOC_ca_phep_kiem_do_dai(self):
        # Thu tu quan trong: neu kiem do dai truoc thi mot tac gia nghe 2 giay
        # chuong cua minh se nhan ma "chua du lau" — mot thong diep goi y rang
        # nghe lau hon thi se duoc tinh.
        duoc, ly_do = evaluate_listen(
            listener_id="usr_a", author_id="usr_a",
            listened_seconds=1, duration_seconds=600, now=BAY_GIO)
        self.assertEqual(ly_do, OWN_CHAPTER)

    def test_khong_tinh_lai_trong_24_gio(self):
        vua_tinh = (BAY_GIO - timedelta(hours=5)).isoformat()
        duoc, ly_do = evaluate_listen(
            listener_id="usr_b", author_id="usr_a",
            listened_seconds=600, duration_seconds=600,
            last_credit_at=vua_tinh, now=BAY_GIO)
        self.assertFalse(duoc)
        self.assertEqual(ly_do, ALREADY_CREDITED)

    def test_sau_24_gio_thi_tinh_lai(self):
        hom_qua = (BAY_GIO - timedelta(hours=25)).isoformat()
        duoc, _ = evaluate_listen(
            listener_id="usr_b", author_id="usr_a",
            listened_seconds=600, duration_seconds=600,
            last_credit_at=hom_qua, now=BAY_GIO)
        self.assertTrue(duoc)

    def test_khoa_tat_dinh_giong_nhau_trong_cung_ngay(self):
        sang = datetime(2026, 8, 11, 1, 0, tzinfo=timezone.utc)
        toi = datetime(2026, 8, 11, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(credit_key("usr_b", "chp_1", sang),
                         credit_key("usr_b", "chp_1", toi))

    def test_khoa_khac_nhau_khi_doi_nguoi_chuong_hoac_ngay(self):
        hom_sau = BAY_GIO + timedelta(days=1)
        goc = credit_key("usr_b", "chp_1", BAY_GIO)
        self.assertNotEqual(goc, credit_key("usr_c", "chp_1", BAY_GIO))
        self.assertNotEqual(goc, credit_key("usr_b", "chp_2", BAY_GIO))
        self.assertNotEqual(goc, credit_key("usr_b", "chp_1", hom_sau))

    def test_khoa_du_ngan_cho_rowId_cua_appwrite(self):
        # Appwrite gioi han `rowId` 36 ky tu — da do that o `job_locks`.
        self.assertLessEqual(len(credit_key("usr_b", "chp_1", BAY_GIO)), 36)

    def test_so_thu_tu_ngay_tang_dung_mot_moi_ngay(self):
        self.assertEqual(dedupe_day_bucket(BAY_GIO + timedelta(days=1))
                         - dedupe_day_bucket(BAY_GIO), 1)


class PublicFieldTest(unittest.TestCase):
    def _ho_so(self, **thay):
        goc = {
            "user_id": "usr_a",
            "email": "rieng@tu.local",
            "display_name": "Nam Kujo",
            "username": "namkujo",
            "bio": "Viết fanfic One Piece.",
            "tier": "creator_pro",
            "tts_characters_used": 123456,
            "listened_minutes": 999,
            "author_status": "approved",
        }
        goc.update(thay)
        return goc

    def test_email_va_quota_KHONG_bao_gio_ra_ngoai(self):
        ra = public_profile(self._ho_so(), stats={"qualified_listens": 10})
        for khoa in ("email", "tier", "tts_characters_used", "listened_minutes"):
            self.assertNotIn(khoa, ra)

    def test_trang_thai_duyet_KHONG_ra_ngoai(self):
        """
        Biet ai dang bi treo hay bi tu choi la thong tin MODERATION, khong phai
        viec cua nguoi xem trang. Chi mot bit lo ra: co la tac gia hay khong.
        """
        ra = public_profile(self._ho_so(author_status="suspended"))
        self.assertNotIn("author_status", ra)
        self.assertFalse(ra["is_author"])

    def test_ba_trang_thai_khong_phai_approved_deu_ra_cung_mot_ket_qua(self):
        for s in ("pending", "rejected", "suspended", "none"):
            ra = public_profile(self._ho_so(author_status=s))
            self.assertFalse(ra["is_author"], s)
            self.assertNotIn("rank", ra, s)

    def test_tac_gia_da_duyet_thi_co_hang(self):
        ra = public_profile(self._ho_so(),
                            stats={"qualified_listens": 300,
                                   "published_novels": 4})
        self.assertTrue(ra["is_author"])
        self.assertEqual(ra["rank"]["key"], "ke_det_mong")
        self.assertEqual(ra["published_novels"], 4)

    def test_trang_thai_la_bi_coi_nhu_none(self):
        ra = public_profile(self._ho_so(author_status="ai_do_go_sai"))
        self.assertFalse(ra["is_author"])

    def test_loc_tim_kiem_tac_gia_chi_tra_nguoi_da_duyet(self):
        rows = [
            {"user_id": "1", "author_status": "approved"},
            {"user_id": "2", "author_status": "pending"},
            {"user_id": "3", "author_status": "suspended"},
            {"user_id": "4", "author_status": "none"},
            {"user_id": "5", "author_status": "rejected"},
        ]
        ra = searchable_authors(rows)
        self.assertEqual([r["user_id"] for r in ra], ["1"])


if __name__ == "__main__":
    unittest.main()
