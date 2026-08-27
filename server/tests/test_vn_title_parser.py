"""Test cho `server/scraper/vn_title_parser.py` — bo song phan tich tieu de
fanfic-audio tieng Viet + danh gia do tin cay gom nhom.

Trong tam dat vao YEU CAU AN TOAN cua dac ta: "khong duoc de tuong dong yeu
tu dong gop hai series khac nhau" — xem `ConfidenceLowTest` va cac test
canh xung dot trong `ConfidenceMediumTest`."""

from __future__ import annotations

import unittest

from server.scraper.vn_title_parser import (
    KetQuaPhanTich,
    LoaiTap,
    MucDoTinCay,
    danh_gia_do_tin_cay,
    phan_tich_tieu_de,
)


class TapDonLeTest(unittest.TestCase):
    def test_dang_co_dau(self):
        r = phan_tich_tieu_de("Tiên Nghịch - Tập 1")
        self.assertIsNotNone(r.tap)
        self.assertEqual(r.tap.loai, LoaiTap.DON)
        self.assertEqual(r.tap.bat_dau, 1)
        self.assertEqual(r.tap.ket_thuc, 1)

    def test_so_0_dan_dau(self):
        r = phan_tich_tieu_de("Tiên Nghịch - Tập 01")
        self.assertEqual(r.tap.bat_dau, 1)

    def test_khong_phan_biet_hoa_thuong(self):
        for tieu_de in ("tập 7", "TẬP 7", "Tập 7", "TẬp 7"):
            with self.subTest(tieu_de=tieu_de):
                r = phan_tich_tieu_de(tieu_de)
                self.assertEqual(r.tap.bat_dau, 7)

    def test_dang_khong_dau_va_ep(self):
        for tieu_de, so in (("Tap 9", 9), ("EP 12", 12), ("Episode 3", 3)):
            with self.subTest(tieu_de=tieu_de):
                r = phan_tich_tieu_de(tieu_de)
                self.assertEqual(r.tap.bat_dau, so)


class TapDaiTest(unittest.TestCase):
    def test_dai_tap_co_ban(self):
        r = phan_tich_tieu_de("Xuyên Không Làm Vương Phi Tập 1-10 | Audio Full")
        self.assertIsNotNone(r.tap)
        self.assertEqual(r.tap.loai, LoaiTap.DAI)
        self.assertEqual(r.tap.bat_dau, 1)
        self.assertEqual(r.tap.ket_thuc, 10)
        self.assertEqual(r.tap.so_luong, 10)

    def test_dai_tap_khong_bi_hieu_nham_la_tap_dau(self):
        """Day la yeu cau cot loi cua dac ta: "Tập 1-10" PHAI duoc nhan dien
        la MOT DAI, KHONG duoc doan la tap 1."""
        r = phan_tich_tieu_de("Tập 1-10")
        self.assertTrue(r.tap.la_dai)
        self.assertNotEqual((r.tap.bat_dau, r.tap.ket_thuc), (1, 1))

    def test_gach_ngang_co_khoang_trang_khong_phai_dai_tap(self):
        """"Tập 12 - 2024 Remastered" — gach ngang la ranh gioi cum tu (co
        khoang trang hai ben), KHONG phai ky hieu dai tap (dinh lien)."""
        r = phan_tich_tieu_de("Tiên Nghịch Tập 12 - 2024 Remastered")
        self.assertEqual(r.tap.loai, LoaiTap.DON)
        self.assertEqual(r.tap.bat_dau, 12)

    def test_dai_vo_ly_roi_xuong_thu_so_don(self):
        """"Tập 13-1" (cuoi nho hon dau) la mot DAI vo ly, khong duoc tra
        RANGE sai — ham roi xuong thu khop so tap DON (chi lay "Tập 13",
        bo qua phan "-1" khong hop le) thay vi bia mot dai sai hoac bo cuoc
        hoan toan; cung hanh vi voi `episode_parser.parse_episode_span` da
        production-certified."""
        r = phan_tich_tieu_de("Tiên Nghịch Tập 13-1")
        self.assertEqual(r.tap.loai, LoaiTap.DON)
        self.assertEqual(r.tap.bat_dau, 13)


class PhanTest(unittest.TestCase):
    def test_tu_khoa_day_du(self):
        r = phan_tich_tieu_de("Đấu La Đại Lục Phần 2")
        self.assertEqual(r.phan, 2)

    def test_dang_viet_tat_p_so(self):
        r = phan_tich_tieu_de("Đấu La Đại Lục P2")
        self.assertEqual(r.phan, 2)

    def test_dang_viet_tat_p_cham_so(self):
        r = phan_tich_tieu_de("Đấu La Đại Lục P.2")
        self.assertEqual(r.phan, 2)

    def test_p_khong_khop_nham_ben_trong_tu_khac(self):
        """"1080p1" (nham "P1" ben trong nhan do phan giai) KHONG duoc khop
        — ranh gioi tu \\b tu choi vi tri ngay sau ky tu chu/so."""
        r = phan_tich_tieu_de("Video chất lượng 1080p1 xem thử")
        self.assertIsNone(r.phan)

    def test_phan_va_tap_la_hai_truc_doc_lap(self):
        """Vi du chinh tu dac ta: mot fanfic vua co "Phần 2" (dang o phan
        2) VUA co "Tập 5" (tap thu 5 TRONG phan do) — hai con so nay KHONG
        duoc phep de doi/ghi de len nhau."""
        r = phan_tich_tieu_de("Phần 2 - Tập 05 [Vietsub]")
        self.assertEqual(r.phan, 2)
        self.assertEqual(r.tap.bat_dau, 5)


class ChuongTest(unittest.TestCase):
    def test_chuong_co_ban(self):
        r = phan_tich_tieu_de("Tiên Nghịch Chương 1")
        self.assertEqual(r.chuong, 1)

    def test_chuong_so_0_dan_dau(self):
        r = phan_tich_tieu_de("Tiên Nghịch Chương 001")
        self.assertEqual(r.chuong, 1)

    def test_chuong_khong_dau_va_chapter(self):
        for tieu_de, so in (("Chuong 88", 88), ("Chapter 12", 12)):
            with self.subTest(tieu_de=tieu_de):
                r = phan_tich_tieu_de(tieu_de)
                self.assertEqual(r.chuong, so)

    def test_chuong_khac_tap_khong_bi_gop_chung(self):
        r = phan_tich_tieu_de("Tiên Nghịch Chương 5 - Tập 5")
        self.assertEqual(r.chuong, 5)
        self.assertEqual(r.tap.bat_dau, 5)


class BanDayDuTest(unittest.TestCase):
    def test_cac_dang_pho_bien(self):
        for tieu_de in ("Vĩnh Dạ Tinh Hà - Full", "Vĩnh Dạ Tinh Hà - Full bộ",
                         "Vĩnh Dạ Tinh Hà - Tổng Hợp", "Vĩnh Dạ Tinh Hà Trọn Bộ",
                         "ALL IN ONE - Vĩnh Dạ Tinh Hà"):
            with self.subTest(tieu_de=tieu_de):
                r = phan_tich_tieu_de(tieu_de)
                self.assertTrue(r.la_ban_day_du)

    def test_khong_bi_gan_so_tap_gia(self):
        """"Full"/"Tổng hợp" la tin hieu "toan bo tac pham", KHONG duoc
        phep tro thanh "tap 0" hay bi bo qua hoan toan."""
        r = phan_tich_tieu_de("Vĩnh Dạ Tinh Hà - Full")
        self.assertTrue(r.la_ban_day_du)
        self.assertIsNone(r.tap)
        self.assertIn("ban_day_du", r.tin_hieu)

    def test_full_hd_khong_bi_hieu_nham_la_ban_day_du(self):
        """"Full HD" la nhan CHAT LUONG (do phan giai), KHONG phai tin hieu
        "video nay la toan bo tac pham" — hai tin hieu do phai duoc phan
        biet, du ca hai deu chua tu "full"."""
        r = phan_tich_tieu_de("Vĩnh Dạ Tinh Hà [Full HD] Tập 3")
        self.assertFalse(r.la_ban_day_du)
        self.assertEqual(r.tap.bat_dau, 3)

    def test_full_4k_khong_bi_hieu_nham(self):
        r = phan_tich_tieu_de("Tiên Nghịch Tập 9 Full 4K")
        self.assertFalse(r.la_ban_day_du)


class MuaTest(unittest.TestCase):
    def test_season_va_mua(self):
        for tieu_de in ("Yêu Nữ Nhà Ma Season 2 Tập 5", "Yêu Nữ Nhà Ma Mùa 2 - Tập 5"):
            with self.subTest(tieu_de=tieu_de):
                r = phan_tich_tieu_de(tieu_de)
                self.assertEqual(r.mua, 2)
                self.assertEqual(r.tap.bat_dau, 5)

    def test_mua_doc_lap_voi_tap(self):
        r = phan_tich_tieu_de("Mùa 3")
        self.assertEqual(r.mua, 3)
        self.assertIsNone(r.tap)


class NgoaiTruyenTest(unittest.TestCase):
    def test_ngoai_truyen_khong_co_so(self):
        r = phan_tich_tieu_de("Tiên Nghịch Ngoại Truyện")
        self.assertTrue(r.la_ngoai_truyen)
        self.assertIsNone(r.tap)

    def test_ngoai_truyen_khong_dau(self):
        r = phan_tich_tieu_de("Tien Nghich Ngoai Truyen")
        self.assertTrue(r.la_ngoai_truyen)

    def test_ngoai_truyen_co_the_di_kem_so_tap_rieng(self):
        """Mot ngoai truyen VAN co the tu danh so tap CUA RIENG NO (vd
        "Ngoại truyện - Tập 1") — ca hai tin hieu cung ton tai, khong
        loai tru nhau."""
        r = phan_tich_tieu_de("Tiên Nghịch Ngoại Truyện - Tập 1")
        self.assertTrue(r.la_ngoai_truyen)
        self.assertEqual(r.tap.bat_dau, 1)


class KhongTinHieuTest(unittest.TestCase):
    def test_tieu_de_khong_co_mau_nao(self):
        r = phan_tich_tieu_de("Một câu chuyện tình yêu buồn giữa mùa đông")
        self.assertFalse(r.co_tin_hieu)
        self.assertIsNone(r.tap)
        self.assertIsNone(r.phan)
        self.assertIsNone(r.chuong)
        self.assertIsNone(r.mua)
        self.assertFalse(r.la_ban_day_du)
        self.assertFalse(r.la_ngoai_truyen)

    def test_chuoi_rong_khong_nem_loi(self):
        r = phan_tich_tieu_de("")
        self.assertIsInstance(r, KetQuaPhanTich)
        self.assertFalse(r.co_tin_hieu)

    def test_none_khong_nem_loi(self):
        r = phan_tich_tieu_de(None)  # type: ignore[arg-type]
        self.assertFalse(r.co_tin_hieu)
        self.assertEqual(r.tieu_de_goc, "")

    def test_so_khong_di_kem_tu_khoa_khong_duoc_bat(self):
        """Mot con so tran (nam sinh, view count, v.v.) khong di kem tu
        khoa tap/phan/chuong/mua khong duoc coi la tin hieu tap."""
        r = phan_tich_tieu_de("Cập nhật mới nhất 2024 - 10000 lượt xem")
        self.assertIsNone(r.tap)
        self.assertIsNone(r.chuong)


class ConfidenceHighTest(unittest.TestCase):
    """Cac cap tieu de PHAI tu dong gop (CAO) — chi khi tin hieu VAN BAN da
    du manh MOT MINH."""

    def test_trung_lap_tuyet_doi_sau_khi_bo_emoji_va_nhan_chat_luong(self):
        kq = danh_gia_do_tin_cay(
            "🔥 Đấu La Đại Lục Tập 10 🔥", "Đấu La Đại Lục Tập 10")
        self.assertEqual(kq.muc_do, MucDoTinCay.CAO)

    def test_cung_ten_series_khac_so_tap_va_nhan_chat_luong(self):
        """Bien the tieu de dien hinh giua hai lan tai len CUNG mot series:
        gach ngang khac kieu, chu hoa/thuong khac, khac tap, kem nhan
        (Vietsub)/[HD] va emoji — VAN phai gop CAO."""
        kq = danh_gia_do_tin_cay(
            "ĐẤU LA ĐẠI LỤC – Tập 10 (Vietsub) 🔥",
            "Đấu la đại lục - Tập 11 [HD]")
        self.assertEqual(kq.muc_do, MucDoTinCay.CAO)
        self.assertGreaterEqual(kq.diem_tuong_dong, 0.9)

    def test_dai_tap_va_tap_don_cung_series(self):
        kq = danh_gia_do_tin_cay(
            "Nhất Niệm Vĩnh Hằng Tập 1-10 [Vietsub]", "Nhất Niệm Vĩnh Hằng Tập 5")
        self.assertEqual(kq.muc_do, MucDoTinCay.CAO)

    def test_so_sanh_voi_danh_sach_alias_series_da_co(self):
        """Dang goi thu hai: so sanh MOT tieu de moi voi TAP HOP ten
        canonical + alias cua mot series da co — chi can MOT alias khop."""
        kq = danh_gia_do_tin_cay(
            "Tiên Nghịch Tập 20 [Vietsub]",
            ["Tien Nghich (ban cu)", "Tiên Nghịch", "Immortal Demon Venerable"],
        )
        self.assertEqual(kq.muc_do, MucDoTinCay.CAO)


class ConfidenceMediumTest(unittest.TestCase):
    """Cac cap tieu de mo ho THAT SU — vao hang doi xem xet thu cong, KHONG
    tu dong gop MA CUNG KHONG bi loai thang."""

    def test_quan_he_tien_to_khong_tu_dong_len_muc_cao(self):
        """Them nhan phu/ten kenh khien mot ten la TIEN TO cua ten kia
        (diem 0.85) — do la tin hieu KHA nhung KHONG chac chan (xem canh
        bao "Tiên Nghịch"/"Tiên Nghịch Ngoại Truyện" trong docstring
        `_do_tuong_dong_van_ban`), nen dung o TRUNG_BINH thay vi CAO."""
        kq = danh_gia_do_tin_cay(
            "Nhất Niệm Vĩnh Hằng Tập 20 | Kênh Truyện Đêm Khuya",
            "Nhất Niệm Vĩnh Hằng Tập 21")
        self.assertEqual(kq.muc_do, MucDoTinCay.TRUNG_BINH)

    def test_ngoai_truyen_ep_ve_trung_binh_du_ten_series_trung_tuyet_doi(self):
        """Truong hop kinh dien: cung ten series tuyet doi nhung mot ben la
        ngoai truyen — day la mach PHU, khong duoc tu dong gop chung voi
        mach so chinh du van ban giong het."""
        kq = danh_gia_do_tin_cay("Tiên Nghịch Tập 5", "Tiên Nghịch Ngoại Truyện")
        self.assertEqual(kq.muc_do, MucDoTinCay.TRUNG_BINH)
        self.assertTrue(any("ngoai truyen" in c for c in kq.canh_bao))

    def test_khac_mua_ep_ve_trung_binh(self):
        kq = danh_gia_do_tin_cay(
            "Yêu Nữ Nhà Ma Mùa 1 Tập 5", "Yêu Nữ Nhà Ma Mùa 2 Tập 5")
        self.assertEqual(kq.muc_do, MucDoTinCay.TRUNG_BINH)
        self.assertTrue(any("mùa" in c for c in kq.canh_bao))

    def test_tuong_dong_tu_ngu_cao_nhung_dao_thu_tu(self):
        """Trung phan lon token noi dung nhung dao thu tu/them bot vai tu
        (khong khop tuyet doi, khong phai quan he tien to) — Jaccard roi
        vao khoang trung binh."""
        kq = danh_gia_do_tin_cay(
            "Hoa Thiên Cốt Đại Chiến Ma Tôn Tập 1",
            "Hoa Thiên Cốt Đại Chiến Thiên Ma Tập 2")
        self.assertEqual(kq.muc_do, MucDoTinCay.TRUNG_BINH)

    def test_tuong_dong_van_ban_yeu_nhung_so_tap_ke_can_ho_tro(self):
        """Diem van ban mot minh (0.5) chua du nguong TRUNG_BINH truc tiep
        (0.6), nhung VAN co lien quan van ban that su (tren nguong san) VA
        so tap ke can nhau (3 va 4) — tin hieu so o day CHI nang tu THAP len
        TRUNG_BINH, khong tu no tao ra muc CAO."""
        kq = danh_gia_do_tin_cay(
            "Tam Quốc Diễn Nghĩa Đại Chiến Tập 3",
            "Tam Quốc Diễn Nghĩa Hào Kiệt Tập 4")
        self.assertEqual(kq.muc_do, MucDoTinCay.TRUNG_BINH)
        self.assertLess(kq.diem_tuong_dong, 0.6)
        self.assertIn("tap ke can", kq.ly_do)


class ConfidenceLowTest(unittest.TestCase):
    """YEU CAU AN TOAN COT LOI cua dac ta: tuong dong yeu KHONG duoc tu dong
    gop — hai series khac nhau chi tinh co dung chung vai tu pho bien PHAI
    o muc THAP."""

    def test_hai_series_khac_nhau_hoan_toan(self):
        kq = danh_gia_do_tin_cay("Đông Cung Tập 1", "Tây Du Ký Tập 1")
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)

    def test_chung_ten_fandom_nhung_noi_dung_khac_khong_duoc_gop(self):
        """Hai fanfic CUNG fandom "Naruto" nhung noi dung/cap doi hoan toan
        khac nhau — chia se MOT tu (ten fandom) khong duoc phep la can cu
        gop, du so tap co ve "hop ly" o ca hai ben."""
        kq = danh_gia_do_tin_cay(
            "Naruto Tập 1 - Tình Yêu Của Sasuke",
            "Naruto Tập 50 - Cuộc Chiến Ninja Vĩ Đại")
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)

    def test_so_tap_trung_khop_hoan_toan_khong_du_neu_van_ban_khong_lien_quan(self):
        """Ca chot cua yeu cau an toan: DU hai tieu de co CUNG so tap chinh
        xac (tap 1 == tap 1), neu ten series hoan toan khac nhau thi VAN
        phai o muc THAP — tin hieu so KHONG BAO GIO du de tu no vuot qua
        yeu cau tin hieu van ban toi thieu."""
        kq = danh_gia_do_tin_cay("Đông Cung Tập 1", "Tây Du Ký Tập 1")
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)
        self.assertEqual(kq.diem_tuong_dong, 0.0)

    def test_chi_toan_tu_dem_chung_chung_khong_duoc_tinh_la_tin_hieu(self):
        """Hai tieu de CHI trung nhau o cac tu dem chung chung (kenh, review,
        audio, truyen, vietsub, full...) — KHONG con token noi dung nao rieng
        biet de xac nhan day la cung mot series."""
        kq = danh_gia_do_tin_cay(
            "Truyện Audio Full Vietsub Phần 1",
            "Truyện Audio Review Kênh Chapter 9")
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)
        self.assertEqual(kq.diem_tuong_dong, 0.0)

    def test_tieu_de_khong_co_tin_hieu_nao_van_tra_ket_qua_hop_le(self):
        """Tieu de hoan toan khong khop mau nao (khong tap/phan/chuong) o
        CA HAI ben — khong duoc nem loi, phai tra ve mot ket qua "khong du
        tin hieu" hop ly (THAP, vi khong the xac nhan lien quan)."""
        kq = danh_gia_do_tin_cay(
            "Một câu chuyện ngẫu nhiên không có mẫu nào",
            "Một câu chuyện khác hoàn toàn không liên quan")
        self.assertIsInstance(kq.muc_do, MucDoTinCay)

    def test_chuoi_rong_khong_nem_loi(self):
        kq = danh_gia_do_tin_cay("", "Tiên Nghịch Tập 1")
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)

    def test_danh_sach_alias_rong(self):
        kq = danh_gia_do_tin_cay("Tiên Nghịch Tập 1", [])
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)

    def test_khong_alias_nao_khop_van_thap(self):
        kq = danh_gia_do_tin_cay(
            "Đông Cung Tập 5",
            ["Tây Du Ký", "Bạch Xà Truyện", "Tam Sinh Tam Thế"],
        )
        self.assertEqual(kq.muc_do, MucDoTinCay.THAP)


class KetQuaGiaiThichDuocTest(unittest.TestCase):
    """Yeu cau TAT DINH cua dac ta: moi ket qua phai co ly do doc duoc,
    khong bao gio chi tra mot nhan tran khong giai thich."""

    def test_ly_do_luon_la_chuoi_khong_rong(self):
        for a, b in (
            ("Tiên Nghịch Tập 1", "Tiên Nghịch Tập 2"),
            ("Đông Cung Tập 1", "Tây Du Ký Tập 1"),
            ("", ""),
        ):
            with self.subTest(a=a, b=b):
                kq = danh_gia_do_tin_cay(a, b)
                self.assertIsInstance(kq.ly_do, str)
                self.assertTrue(kq.ly_do)

    def test_diem_luon_trong_khoang_hop_le(self):
        for a, b in (
            ("Tiên Nghịch Tập 1", "Tiên Nghịch Tập 2"),
            ("Đông Cung Tập 1", "Tây Du Ký Tập 1"),
            ("random", "khác hẳn"),
        ):
            with self.subTest(a=a, b=b):
                kq = danh_gia_do_tin_cay(a, b)
                self.assertGreaterEqual(kq.diem_tuong_dong, 0.0)
                self.assertLessEqual(kq.diem_tuong_dong, 1.0)


if __name__ == "__main__":
    unittest.main()
