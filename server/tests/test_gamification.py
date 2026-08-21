"""V4 visual completion, Phan G-J — thanh tuu tinh tai cho."""

from __future__ import annotations

import unittest

from server.gamification import (
    ACHIEVEMENTS,
    NGUONG_PHUT_NGHE_THU_VIEN,
    RARITIES,
    tinh_trang_thanh_tuu,
)


def trang_thai_rong():
    return tinh_trang_thanh_tuu(
        so_truyen_xuat_ban=0, so_chuong_xuat_ban=0,
        ky_tu_da_tong_hop=0, phut_da_nghe=0)


class KhoaKhongTrungRankTest(unittest.TestCase):
    def test_khoa_thanh_tuu_khong_trung_khoa_hang_tac_gia(self):
        # Hai truc doc lap — trung khoa se lam lan mot huy hieu thanh cai kia.
        from server.creator import RANK_TIERS
        khoa_hang = {t.key for t in RANK_TIERS}
        khoa_thanh_tuu = {a.key for a in ACHIEVEMENTS}
        self.assertEqual(khoa_hang & khoa_thanh_tuu, set())

    def test_ten_hien_thi_khong_trung_ten_hang_tac_gia(self):
        # Cung tinh than: tranh hai the "Người Kể Chuyện" cho hai y nghia khac
        # nhau tren cung mot trang ho so.
        from server.creator import RANK_TIERS
        ten_hang = {t.title for t in RANK_TIERS}
        ten_thanh_tuu = {a.name for a in ACHIEVEMENTS}
        self.assertEqual(ten_hang & ten_thanh_tuu, set())


class HamThuanTest(unittest.TestCase):
    def test_khong_du_lieu_thi_chua_dat_thanh_tuu_nao(self):
        for t in trang_thai_rong():
            self.assertFalse(t.dat_duoc, t.dinh_nghia.key)

    def test_dinh_dang_du_du_lieu_thi_dat_ca_ba_thanh_tuu_nhi_phan(self):
        ket_qua = tinh_trang_thanh_tuu(
            so_truyen_xuat_ban=1, so_chuong_xuat_ban=1,
            ky_tu_da_tong_hop=1, phut_da_nghe=0)
        theo_khoa = {t.dinh_nghia.key: t.dat_duoc for t in ket_qua}
        self.assertTrue(theo_khoa["chuong_dau_tien"])
        self.assertTrue(theo_khoa["cat_tieng"])
        self.assertTrue(theo_khoa["ra_mat_tieu_thuyet"])
        self.assertFalse(theo_khoa["dem_dai_thu_vien"])

    def test_tien_do_nghe_dung_cap_o_nguong_khong_vuot_qua(self):
        ket_qua = tinh_trang_thanh_tuu(
            so_truyen_xuat_ban=0, so_chuong_xuat_ban=0,
            ky_tu_da_tong_hop=0, phut_da_nghe=NGUONG_PHUT_NGHE_THU_VIEN + 500)
        dem_dai = next(t for t in ket_qua if t.dinh_nghia.key == "dem_dai_thu_vien")
        self.assertTrue(dem_dai.dat_duoc)
        # Hien_tai KHONG duoc vuot muc_tieu — thanh tien do se tran qua 100%.
        self.assertEqual(dem_dai.tien_do, (NGUONG_PHUT_NGHE_THU_VIEN, NGUONG_PHUT_NGHE_THU_VIEN))

    def test_ham_thuan_khong_ngau_nhien_khong_doc_dong_ho(self):
        a = tinh_trang_thanh_tuu(
            so_truyen_xuat_ban=2, so_chuong_xuat_ban=5,
            ky_tu_da_tong_hop=100, phut_da_nghe=45)
        b = tinh_trang_thanh_tuu(
            so_truyen_xuat_ban=2, so_chuong_xuat_ban=5,
            ky_tu_da_tong_hop=100, phut_da_nghe=45)
        self.assertEqual(a, b)

    def test_moi_dinh_nghia_co_do_hiem_hop_le(self):
        for a in ACHIEVEMENTS:
            self.assertIn(a.rarity, RARITIES, a.key)

    def test_moi_khoa_duy_nhat(self):
        khoa = [a.key for a in ACHIEVEMENTS]
        self.assertEqual(len(khoa), len(set(khoa)))


if __name__ == "__main__":
    unittest.main()
