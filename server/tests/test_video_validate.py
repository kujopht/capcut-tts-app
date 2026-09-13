"""
Kiem tham so video — TU CHOI, khong kep lang le.

Mot gia tri bi kep ve khoang hop le cho ra mot ban render khac cai nguoi
dung yeu cau, va ho khong duoc bao gi. Tru DUNG mot ngoai le duoc ghi ro o
`kiem_cat`.
"""

from __future__ import annotations

import unittest

from server.video_validate import (VideoValidationError, kiem_am_luong,
                                   kiem_ban_va, kiem_cat, kiem_lech,
                                   kiem_mime_phu_de, kiem_mime_video,
                                   kiem_tieu_de)


class AmLuongTest(unittest.TestCase):
    def test_trong_khoang(self):
        self.assertEqual(kiem_am_luong(0.0), 0.0)
        self.assertEqual(kiem_am_luong(2.0), 2.0)

    def test_am_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_am_luong(-0.1)

    def test_qua_lon_bi_tu_choi_chu_khong_bi_kep(self):
        """Kep 50 xuong 2 se cho ra mot tep vo tieng ma khong ai duoc bao."""
        with self.assertRaises(VideoValidationError):
            kiem_am_luong(50)

    def test_NaN_va_vo_cuc_bi_tu_choi(self):
        """NaN khong bang chinh no; `inf` lot qua moi phep so sanh khoang."""
        for xau in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(VideoValidationError):
                kiem_am_luong(xau)

    def test_bool_KHONG_phai_so(self):
        """`True == 1` trong Python — de lot neu chi kiem khoang."""
        with self.assertRaises(VideoValidationError):
            kiem_am_luong(True)

    def test_chuoi_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_am_luong("1.0")


class LechTest(unittest.TestCase):
    def test_am_duoc_phep(self):
        self.assertEqual(kiem_lech(-12.5), -12.5)

    def test_qua_xa_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_lech(99999)


class CatTest(unittest.TestCase):
    def test_ket_thuc_0_nghia_la_toi_het(self):
        self.assertEqual(kiem_cat(5.0, 0.0), (5.0, 0.0))

    def test_ket_thuc_truoc_bat_dau_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_cat(10.0, 5.0)

    def test_bat_dau_ngoai_do_dai_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_cat(90.0, 0.0, dai_nguon=60.0)

    def test_keo_toi_qua_cuoi_thi_KEP_chu_khong_tu_choi(self):
        """Keo con truot toi cuoi la thao tac binh thuong, khong phai loi.

        Day la NGOAI LE DUY NHAT cua nguyen tac "tu choi chu khong kep", va
        no duoc ghi ro o `kiem_cat`.
        """
        d, c = kiem_cat(0.0, 999.0, dai_nguon=60.0)
        self.assertEqual((d, c), (0.0, 0.0))

    def test_qua_dai_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_cat(0.0, 0.0, dai_nguon=10 * 3600.0)


class MimeTest(unittest.TestCase):
    def test_dinh_dang_video_duoc_phep(self):
        kiem_mime_video("video/mp4", 1024)
        kiem_mime_video("video/mp4; codecs=avc1", 1024)

    def test_dinh_dang_la_bi_tu_choi(self):
        """Danh sach CHO PHEP: FFmpeg doc duoc nhieu thu ta khong muon nhan."""
        for xau in ("application/x-msdownload", "image/gif", "text/html", ""):
            with self.assertRaises(VideoValidationError):
                kiem_mime_video(xau, 1024)

    def test_tep_rong_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_mime_video("video/mp4", 0)

    def test_qua_lon_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_mime_video("video/mp4", 900 * 1024 * 1024)

    def test_phu_de(self):
        kiem_mime_phu_de("text/vtt", 100)
        with self.assertRaises(VideoValidationError):
            kiem_mime_phu_de("video/mp4", 100)


class TieuDeTest(unittest.TestCase):
    def test_cat_khoang_trang(self):
        self.assertEqual(kiem_tieu_de("  Dự án  "), "Dự án")

    def test_rong_bi_tu_choi(self):
        for xau in ("", "   "):
            with self.assertRaises(VideoValidationError):
                kiem_tieu_de(xau)

    def test_qua_dai_bi_tu_choi(self):
        with self.assertRaises(VideoValidationError):
            kiem_tieu_de("x" * 200)


class BanVaTest(unittest.TestCase):
    def test_truong_hop_le_di_qua(self):
        ra = kiem_ban_va({"title": "A", "audio_volume": 1.2,
                          "mute_original_audio": True})
        self.assertEqual(ra["title"], "A")
        self.assertEqual(ra["audio_volume"], 1.2)
        self.assertIs(ra["mute_original_audio"], True)

    def test_KHONG_sua_duoc_owner_id(self):
        """Gui thang vao `setattr` se cho phep doi chu so huu."""
        with self.assertRaises(VideoValidationError):
            kiem_ban_va({"owner_id": "ke-khac"})

    def test_KHONG_sua_duoc_render_state(self):
        with self.assertRaises(VideoValidationError):
            kiem_ban_va({"render_state": "ready"})

    def test_KHONG_sua_duoc_output_object_key(self):
        with self.assertRaises(VideoValidationError):
            kiem_ban_va({"output_object_key": "x/y.mp4"})

    def test_truong_la_bi_TU_CHOI_chu_khong_bo_qua_im_lang(self):
        """Giao dien gui nham ten truong ma khong ai bao thi loi song rat lau."""
        with self.assertRaises(VideoValidationError):
            kiem_ban_va({"audio_volumee": 1.0})

    def test_mute_phai_la_bool(self):
        with self.assertRaises(VideoValidationError):
            kiem_ban_va({"mute_original_audio": "true"})

    def test_bo_tham_chieu_bang_chuoi_rong(self):
        self.assertEqual(kiem_ban_va({"audio_track_id": None})["audio_track_id"], "")


if __name__ == "__main__":
    unittest.main()
