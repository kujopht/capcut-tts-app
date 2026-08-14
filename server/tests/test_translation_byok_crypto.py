"""`server/translation_byok_crypto.py` — ma hoa API key ca nhan (V5.1)."""

from __future__ import annotations

import unittest

from server.translation_byok_crypto import (
    ByokConfigError,
    ByokCrypto,
    ByokDecryptError,
    lay_4_ky_tu_cuoi,
    sinh_master_key_moi,
)

KHOA_TEST = sinh_master_key_moi()
KHOA_TEST_KHAC = sinh_master_key_moi()


class MaHoaCoBanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)

    def test_ma_hoa_roi_giai_ma_ra_dung_gia_tri_goc(self):
        ct = self.crypto.ma_hoa("gsk_vidu_bi_mat_123", user_id="u1",
                                provider_id="groq")
        self.assertEqual(
            self.crypto.giai_ma(ct, user_id="u1", provider_id="groq"),
            "gsk_vidu_bi_mat_123")

    def test_ciphertext_khong_chua_plaintext(self):
        bi_mat = "gsk_khong_duoc_lo_ra_ngoai"
        ct = self.crypto.ma_hoa(bi_mat, user_id="u1", provider_id="groq")
        self.assertNotIn(bi_mat, ct)

    def test_hai_lan_ma_hoa_cung_gia_tri_ra_ciphertext_khac_nhau(self):
        """Nonce ngau nhien moi lan — khong duoc phep de doan ban ghi nao
        trung API key qua so sanh ciphertext tinh."""
        ct1 = self.crypto.ma_hoa("gsk_x", user_id="u1", provider_id="groq")
        ct2 = self.crypto.ma_hoa("gsk_x", user_id="u1", provider_id="groq")
        self.assertNotEqual(ct1, ct2)

    def test_ma_hoa_rong_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            self.crypto.ma_hoa("", user_id="u1", provider_id="groq")


class AadRangBuocTest(unittest.TestCase):
    """AAD (user_id, provider_id) — lop phong thu THU HAI, doc lap voi kiem
    tra quyen so huu o tang service."""

    def setUp(self) -> None:
        self.crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)

    def test_giai_ma_voi_sai_user_id_that_bai(self):
        ct = self.crypto.ma_hoa("gsk_x", user_id="u1", provider_id="groq")
        with self.assertRaises(ByokDecryptError):
            self.crypto.giai_ma(ct, user_id="u2", provider_id="groq")

    def test_giai_ma_voi_sai_provider_id_that_bai(self):
        ct = self.crypto.ma_hoa("gsk_x", user_id="u1", provider_id="groq")
        with self.assertRaises(ByokDecryptError):
            self.crypto.giai_ma(ct, user_id="u1", provider_id="cloudflare")

    def test_ciphertext_bi_cop_sang_nguoi_dung_khac_khong_giai_ma_duoc(self):
        """Mo phong dung kich ban that: mot loi logic/thao tac CSDL khien
        `encrypted_secret` cua nguoi dung A nam trong ban ghi cua nguoi dung
        B — PHAI that bai du dung dung master key."""
        ct_cua_a = self.crypto.ma_hoa("gsk_cua_a", user_id="user-a",
                                      provider_id="groq")
        with self.assertRaises(ByokDecryptError):
            self.crypto.giai_ma(ct_cua_a, user_id="user-b", provider_id="groq")


class FailClosedTest(unittest.TestCase):
    def test_sai_master_key_that_bai_kin(self):
        dung = ByokCrypto.tu_moi_truong(KHOA_TEST)
        sai = ByokCrypto.tu_moi_truong(KHOA_TEST_KHAC)
        ct = dung.ma_hoa("gsk_x", user_id="u1", provider_id="groq")
        with self.assertRaises(ByokDecryptError):
            sai.giai_ma(ct, user_id="u1", provider_id="groq")

    def test_ciphertext_hong_that_bai_kin(self):
        crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)
        ct = crypto.ma_hoa("gsk_x", user_id="u1", provider_id="groq")
        hong = ct[:-4] + "abcd"
        with self.assertRaises(ByokDecryptError):
            crypto.giai_ma(hong, user_id="u1", provider_id="groq")

    def test_dinh_dang_sai_hoan_toan_that_bai_kin_khong_crash(self):
        crypto = ByokCrypto.tu_moi_truong(KHOA_TEST)
        for rac in ("", "khong-phai-byok", "byok.v1.thieu-phan", "byok.v2.a.b"):
            with self.assertRaises(ByokDecryptError):
                crypto.giai_ma(rac, user_id="u1", provider_id="groq")

    def test_thieu_master_key_nem_loi_ngay(self):
        with self.assertRaises(ByokConfigError):
            ByokCrypto.tu_moi_truong("")

    def test_master_key_khong_dung_do_dai_nem_loi_ngay(self):
        with self.assertRaises(ByokConfigError):
            ByokCrypto.tu_moi_truong("dGVzdA==")  # "test" base64, qua ngan

    def test_master_key_khong_phai_base64_nem_loi_ngay(self):
        with self.assertRaises(ByokConfigError):
            ByokCrypto.tu_moi_truong("khong-phai-base64!!!")


class Lay4KyTuCuoiTest(unittest.TestCase):
    def test_key_dai_lay_dung_4_ky_tu_cuoi(self):
        self.assertEqual(lay_4_ky_tu_cuoi("gsk_abcdefgh1234AB42"), "AB42")

    def test_khong_bao_gio_tra_ve_toan_bo_key_ngan(self):
        # Ngay ca key "ngan" cung chi lay toi da phan cuoi — khong co nhanh
        # nao tra ve nhieu hon 4 ky tu.
        self.assertLessEqual(len(lay_4_ky_tu_cuoi("ab")), 4)


if __name__ == "__main__":
    unittest.main()
