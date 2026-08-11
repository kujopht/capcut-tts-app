"""
Chinh sach thuan cua tang xa hoi — `server/social.py`.

Khong dung kho, khong dung may chu. Moi bai o day kiem mot QUY TAC, va quy tac
la thu se bi doi — nen chung duoc ghim o day thay vi duoc suy ra tu hanh vi cua
mot route.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from server.social import (
    CHINH_SACH_ANH,
    COMMENT_MAX_CHARS,
    FEED_MAX_PAGE_SIZE,
    HAN_MUC_MAC_DINH,
    HanMuc,
    POST_MAX_CHARS,
    POST_MAX_IMAGES,
    REPLY_MAX_DEPTH,
    RateLimited,
    SocialError,
    clean_text,
    comment_like_key,
    doan_khoa,
    kich_thuoc_trang,
    kiem_anh,
    kiem_han_muc,
    mo_ta_gioi_han,
    notification_key,
    object_key,
    parent_hop_le,
    post_like_key,
    report_key,
    story_follow_key,
    tron_bang_tin,
    user_follow_key,
)

BAY_GIO = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


class ChuanHoaVanBanTest(unittest.TestCase):
    def test_cat_khoang_trang_hai_dau(self):
        self.assertEqual(clean_text("  chào  ", toi_da=50, ten="X"), "chào")

    def test_rong_thi_tu_choi_khi_bat_buoc(self):
        with self.assertRaises(SocialError):
            clean_text("   ", toi_da=50, ten="Bình luận")

    def test_rong_duoc_phep_khi_khong_bat_buoc(self):
        # Bai chi co anh, khong co chu — hop le.
        self.assertEqual(clean_text("", toi_da=50, ten="X", bat_buoc=False), "")

    def test_vuot_tran_thi_tu_choi_kem_so_that(self):
        with self.assertRaises(SocialError) as ctx:
            clean_text("x" * 51, toi_da=50, ten="Bài")
        self.assertIn("51", str(ctx.exception))

    def test_bo_ky_tu_dieu_khien(self):
        """
        `U+202E` dao chieu doc chuoi. Mot ten tep hay mot binh luan chua no co
        the hien ra khac hoan toan voi noi dung that.
        """
        ra = clean_text("an‮toan\x00", toi_da=50, ten="X")
        self.assertNotIn("‮", ra)
        self.assertNotIn("\x00", ra)

    def test_giu_xuong_dong_va_tab(self):
        self.assertIn("\n", clean_text("a\nb", toi_da=50, ten="X"))
        self.assertIn("\t", clean_text("a\tb", toi_da=50, ten="X"))

    def test_gom_dong_trong_thua(self):
        """Mot bai toan dong trong chiem ca man hinh nguoi khac trong bang tin."""
        self.assertEqual(clean_text("a\n\n\n\n\n\nb", toi_da=50, ten="X"),
                         "a\n\nb")

    def test_khong_loc_html(self):
        """
        Tang hien thi cua React thoat chuoi san. Mot bo loc HTML o day se lam
        hong nhung bai viet noi VE ma nguon.
        """
        self.assertIn("<div>", clean_text("thẻ <div> là gì", toi_da=50, ten="X"))


class KhoaTatDinhTest(unittest.TestCase):
    """
    Khoa phai TAT DINH va DUOI 36 KY TU — Appwrite gioi han `rowId` o do.
    """

    def test_tat_dinh(self):
        self.assertEqual(user_follow_key("a", "b"), user_follow_key("a", "b"))

    def test_khong_doi_xung(self):
        """A theo doi B khac B theo doi A. Gop hai chieu la mot loi ngu nghia."""
        self.assertNotEqual(user_follow_key("a", "b"), user_follow_key("b", "a"))

    def test_moi_loai_mot_tien_to_rieng(self):
        """
        Cung mot cap gia tri o hai bang phai ra hai khoa khac nhau. Khong the
        thi mot luot thich va mot lan theo doi co the dung nhau.
        """
        khoa = {
            user_follow_key("a", "b"),
            story_follow_key("a", "b"),
            post_like_key("a", "b"),
            comment_like_key("a", "b"),
        }
        self.assertEqual(len(khoa), 4)

    def test_do_dai_duoi_tran_cua_appwrite(self):
        dai = "u" * 64
        for khoa in (user_follow_key(dai, dai), story_follow_key(dai, dai),
                     post_like_key(dai, dai), report_key(dai, "post", dai),
                     notification_key(dai, "follow", dai, dai, now=BAY_GIO)):
            self.assertLessEqual(len(khoa), 36)
            self.assertTrue(khoa.isascii())

    def test_bao_cao_theo_ca_loai_lan_doi_tuong(self):
        self.assertNotEqual(report_key("a", "post", "x"),
                            report_key("a", "comment", "x"))


class ThongBaoChongLapTest(unittest.TestCase):
    def test_cung_ngay_thi_cung_khoa(self):
        a = notification_key("u", "post_like", "actor", "p", now=BAY_GIO)
        b = notification_key("u", "post_like", "actor", "p",
                             now=BAY_GIO + timedelta(hours=6))
        self.assertEqual(a, b)

    def test_ngay_khac_thi_khoa_khac(self):
        """
        Theo NGAY chu khong phai "mot lan mai mai": bo theo doi roi theo doi lai
        sau ba thang la mot su kien that, va nguoi nhan nen biet.
        """
        a = notification_key("u", "follow", "actor", "", now=BAY_GIO)
        b = notification_key("u", "follow", "actor", "",
                             now=BAY_GIO + timedelta(days=2))
        self.assertNotEqual(a, b)

    def test_doi_tuong_khac_thi_khoa_khac(self):
        """Hai binh luan khac nhau tren cung mot bai la hai thong bao."""
        a = notification_key("u", "post_comment", "actor", "c1", now=BAY_GIO)
        b = notification_key("u", "post_comment", "actor", "c2", now=BAY_GIO)
        self.assertNotEqual(a, b)

    def test_nguoi_gay_khac_thi_khoa_khac(self):
        a = notification_key("u", "post_like", "x", "p", now=BAY_GIO)
        b = notification_key("u", "post_like", "y", "p", now=BAY_GIO)
        self.assertNotEqual(a, b)


class HanMucTest(unittest.TestCase):
    def test_duoi_tran_thi_qua(self):
        kiem_han_muc("post", 9, HanMuc(so_lan=10, phut=60))

    def test_dung_tran_thi_chan(self):
        """`>=`, khong phai `>`: lan thu 10 voi tran 10 phai bi chan."""
        with self.assertRaises(RateLimited):
            kiem_han_muc("post", 10, HanMuc(so_lan=10, phut=60))

    def test_thong_diep_noi_ro_con_so(self):
        with self.assertRaises(RateLimited) as ctx:
            kiem_han_muc("post", 99, HanMuc(so_lan=10, phut=60))
        self.assertIn("10", str(ctx.exception))
        self.assertIn("60", str(ctx.exception))

    def test_ten_khong_biet_thi_bo_qua(self):
        """Khong nem: mot ten la khong phai mot ly do chan nguoi dung."""
        kiem_han_muc("khong-co-thuc", 10_000)

    def test_moc_bat_dau_lui_dung_cua_so(self):
        muc = HanMuc(so_lan=5, phut=30)
        moc = muc.moc_bat_dau(BAY_GIO)
        self.assertEqual(moc, (BAY_GIO - timedelta(minutes=30))
                         .isoformat(timespec="seconds"))

    def test_du_bon_han_muc_mac_dinh(self):
        self.assertEqual(set(HAN_MUC_MAC_DINH),
                         {"post", "comment", "follow", "report"})

    def test_binh_luan_thoang_hon_dang_bai(self):
        """Mot cuoc trao doi that co nhip nhanh hon viec dang bai."""
        self.assertGreater(HAN_MUC_MAC_DINH["comment"].so_lan,
                           HAN_MUC_MAC_DINH["post"].so_lan)


class ChinhSachAnhTest(unittest.TestCase):
    def test_khong_co_video_o_bat_ky_muc_nao(self):
        for cs in CHINH_SACH_ANH.values():
            for mime in cs.mime:
                self.assertTrue(mime.startswith("image/"), mime)

    def test_khong_nhan_svg(self):
        """SVG la XML va co the chua script — day la mot be mat tan cong."""
        for cs in CHINH_SACH_ANH.values():
            self.assertNotIn("image/svg+xml", cs.mime)

    def test_mot_anh_moi_bai(self):
        self.assertEqual(POST_MAX_IMAGES, 1)

    def test_tu_choi_mime_la(self):
        with self.assertRaises(SocialError):
            kiem_anh("post", mime="application/pdf", so_byte=100)

    def test_tu_choi_tep_rong(self):
        with self.assertRaises(SocialError):
            kiem_anh("post", mime="image/webp", so_byte=0)

    def test_tu_choi_qua_to(self):
        with self.assertRaises(SocialError) as ctx:
            kiem_anh("post", mime="image/webp", so_byte=5 * 1024 * 1024)
        self.assertIn("MB", str(ctx.exception))

    def test_nhan_anh_hop_le_va_tra_ve_chinh_sach(self):
        cs = kiem_anh("post", mime="image/webp", so_byte=1000)
        self.assertEqual(cs.khong_gian, "posts")

    def test_bo_tham_so_sau_dau_cham_phay(self):
        kiem_anh("post", mime="image/webp; charset=binary", so_byte=1000)

    def test_loai_la_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            kiem_anh("banner", mime="image/webp", so_byte=100)

    def test_anh_bai_nho_hon_bia(self):
        """Bia la thu nhin dau tien o trang truyen; anh bai chi la kem theo."""
        self.assertLess(CHINH_SACH_ANH["post"].toi_da_byte,
                        CHINH_SACH_ANH["cover"].toi_da_byte)


class KhoaDoiTuongTest(unittest.TestCase):
    def test_khong_gian_ten_theo_loai(self):
        self.assertTrue(object_key("post", user_id="u1", subject_id="p1")
                        .startswith("posts/"))
        self.assertTrue(object_key("avatar", user_id="u1", subject_id="")
                        .startswith("avatars/"))
        self.assertTrue(object_key("cover", user_id="u1", subject_id="n1")
                        .startswith("covers/"))

    def test_KHONG_BAO_GIO_co_email_trong_khoa(self):
        """
        Khoa doi tuong xuat hien trong URL da ky, trong log truy cap, trong
        thong bao loi va trong bang dieu khien cua nha cung cap. Mot dia chi
        email o do la du lieu ca nhan bi ro ri sang moi noi do, va khong co cach
        nao thu hoi mot khoa da phat ra.
        """
        khoa = object_key("post", user_id="ai@vidu.vn", subject_id="p1")
        self.assertNotIn("@", khoa)
        self.assertNotIn(".vn", khoa)

    def test_khong_thoat_ra_khoi_khong_gian_ten(self):
        """`../` trong id khong duoc tro ra ngoai tien to."""
        khoa = object_key("post", user_id="../../etc", subject_id="p1")
        self.assertNotIn("..", khoa)
        self.assertTrue(khoa.startswith("posts/"))

    def test_doan_khoa_chi_giu_ky_tu_an_toan(self):
        self.assertEqual(doan_khoa("a b/c?d"), "a_b_c_d")

    def test_doan_khoa_rong_khong_tao_duong_dan_rong(self):
        self.assertEqual(doan_khoa(""), "_")

    def test_loai_la_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            object_key("video", user_id="u", subject_id="s")


class BangTinTest(unittest.TestCase):
    def test_bai_theo_doi_len_truoc(self):
        ra = tron_bang_tin([{"post_id": "a"}], [{"post_id": "b"}], 10)
        self.assertEqual([x["post_id"] for x in ra], ["a", "b"])

    def test_khong_trung(self):
        """Mot bai vua tu nguoi minh theo doi vua o kham pha chi hien MOT lan."""
        ra = tron_bang_tin([{"post_id": "a"}],
                           [{"post_id": "a"}, {"post_id": "b"}], 10)
        self.assertEqual([x["post_id"] for x in ra], ["a", "b"])

    def test_ton_trong_gioi_han(self):
        ra = tron_bang_tin([{"post_id": str(i)} for i in range(30)], [], 5)
        self.assertEqual(len(ra), 5)

    def test_bo_qua_ban_ghi_thieu_id(self):
        ra = tron_bang_tin([{"post_id": ""}, {"post_id": "a"}], [], 10)
        self.assertEqual([x["post_id"] for x in ra], ["a"])

    def test_kich_thuoc_trang_co_tran(self):
        self.assertEqual(kich_thuoc_trang(10_000), FEED_MAX_PAGE_SIZE)

    def test_kich_thuoc_trang_mac_dinh_khi_thieu(self):
        self.assertEqual(kich_thuoc_trang(None), kich_thuoc_trang(0))
        self.assertGreater(kich_thuoc_trang(None), 0)

    def test_so_am_ve_mac_dinh(self):
        self.assertEqual(kich_thuoc_trang(-5), kich_thuoc_trang(None))


class TraLoiMotCapTest(unittest.TestCase):
    def test_dung_mot_cap(self):
        self.assertEqual(REPLY_MAX_DEPTH, 1)

    def test_tra_loi_binh_luan_goc_thi_duoc(self):
        parent_hop_le("c1", "")

    def test_tra_loi_mot_tra_loi_thi_tu_choi(self):
        """
        Tu choi NGAY tai day thay vi am tham gan vao dau do — mot cai cay lech
        la thu rat kho don sau nay.
        """
        with self.assertRaises(SocialError):
            parent_hop_le("c2", "c1")

    def test_thieu_cha_thi_tu_choi(self):
        with self.assertRaises(SocialError):
            parent_hop_le("", "")


class MoTaGioiHanTest(unittest.TestCase):
    """`/api/limits` la HOP DONG voi giao dien — hinh dang cua no duoc ghim."""

    def test_co_du_cac_khoa_giao_dien_can(self):
        ra = mo_ta_gioi_han()
        for khoa in ("post_max_chars", "comment_max_chars", "post_max_images",
                     "image", "rate"):
            self.assertIn(khoa, ra)

    def test_con_so_khop_hang_so_that(self):
        ra = mo_ta_gioi_han()
        self.assertEqual(ra["post_max_chars"], POST_MAX_CHARS)
        self.assertEqual(ra["comment_max_chars"], COMMENT_MAX_CHARS)

    def test_moi_loai_anh_deu_co_tran_va_mime(self):
        for loai, muc in mo_ta_gioi_han()["image"].items():
            self.assertGreater(muc["max_bytes"], 0, loai)
            self.assertTrue(muc["mime"], loai)
            self.assertTrue(muc["preferred_mime"], loai)

    def test_KHONG_lo_bi_mat_nao(self):
        """
        Endpoint nay CONG KHAI. Mot ngay nao do ai them mot truong vao day ma
        khong nghi ky, nen bai nay ghim lai: khong khoa nao duoc chua chuoi
        goi nho toi bi mat.
        """
        chu = repr(mo_ta_gioi_han()).lower()
        for xau in ("key", "secret", "token", "password", "api"):
            self.assertNotIn(xau, chu)


if __name__ == "__main__":
    unittest.main()
