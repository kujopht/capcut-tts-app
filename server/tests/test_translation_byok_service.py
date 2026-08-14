"""`server/translation_byok_service.py` — ProviderConnectionService (V5.1)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from server.adapters import NotFoundError
from server.translation import TranslationError
from server.translation_byok_crypto import ByokCrypto, sinh_master_key_moi
from server.translation_byok_service import (
    ByokNotConfiguredError,
    ProviderConnectionService,
    SUPPORTED_BYOK_PROVIDERS,
)
from server.translation_provider_registry import ConnectionCheckError
from server.translation_store import MockTranslationStore

KHOA_TEST = sinh_master_key_moi()


def _svc(crypto=True):
    store = MockTranslationStore()
    return ProviderConnectionService(
        store, crypto=ByokCrypto.tu_moi_truong(KHOA_TEST) if crypto else None)


class ChuaCauHinhTest(unittest.TestCase):
    """Server chua bat BYOK (khong co master key) — moi thao tac lien quan
    ma hoa PHAI nem loi ro rang, KHONG am tham lam gi khac."""

    def setUp(self):
        self.svc = _svc(crypto=False)

    def test_connect_nem_byok_not_configured(self):
        with self.assertRaises(ByokNotConfiguredError):
            self.svc.connect("u1", "groq", "gsk_x")

    def test_build_configured_provider_tra_none_khong_nem_loi(self):
        self.assertIsNone(self.svc.build_configured_provider("u1", "groq"))

    def test_list_van_hoat_dong_binh_thuong(self):
        # Liet ke (khong ma hoa gi) van phai chay duoc du chua bat BYOK.
        self.assertEqual(self.svc.list_connections("u1"), [])


class ConnectTest(unittest.TestCase):
    def setUp(self):
        self.svc = _svc()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_connect_thanh_cong_luu_dung_last4_khong_luu_plaintext(self, kiem_tra):
        conn = self.svc.connect("u1", "groq", "gsk_abcdefgh1234AB42")
        self.assertEqual(conn.last4, "AB42")
        self.assertNotIn("gsk_abcdefgh1234AB42", conn.encrypted_secret)
        kiem_tra.assert_called_once()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_connect_that_bai_khong_luu_gi(self, kiem_tra):
        kiem_tra.side_effect = ConnectionCheckError("INVALID_KEY", "sai key")
        with self.assertRaises(ConnectionCheckError):
            self.svc.connect("u1", "groq", "gsk_sai")
        self.assertEqual(self.svc.list_connections("u1"), [])

    def test_provider_khong_ho_tro_bi_tu_choi(self):
        with self.assertRaises(TranslationError):
            self.svc.connect("u1", "openai", "sk_x")

    def test_key_rong_bi_tu_choi(self):
        with self.assertRaises(TranslationError):
            self.svc.connect("u1", "groq", "   ")

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_ket_noi_lai_thay_the_khong_tao_ban_ghi_thu_hai(self, kiem_tra):
        self.svc.connect("u1", "groq", "gsk_cu_00000000AAAA")
        self.svc.connect("u1", "groq", "gsk_moi_00000000BBBB")
        ds = self.svc.list_connections("u1")
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0].last4, "BBBB")


class TestConnectionTest(unittest.TestCase):
    def setUp(self):
        self.svc = _svc()

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_kiem_tra_lai_thanh_cong_cap_nhat_last_verified_at(self, kiem_tra):
        self.svc.connect("u1", "groq", "gsk_x0000000000AB42")
        conn = self.svc.test_connection("u1", "groq")
        self.assertTrue(conn.last_verified_at)
        self.assertEqual(kiem_tra.call_count, 2)  # 1 luc connect, 1 luc test

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_kiem_tra_chua_ket_noi_nem_not_found(self, kiem_tra):
        with self.assertRaises(NotFoundError):
            self.svc.test_connection("u1", "groq")


class DeleteTest(unittest.TestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_xoa_roi_khong_con_dung_duoc(self, kiem_tra):
        svc = _svc()
        svc.connect("u1", "groq", "gsk_x0000000000AB42")
        svc.delete("u1", "groq")
        self.assertIsNone(svc.build_configured_provider("u1", "groq"))
        self.assertEqual(svc.list_connections("u1"), [])


class BuildConfiguredProviderTest(unittest.TestCase):
    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def test_provider_dung_duoc_giai_ma_dung_key(self, kiem_tra):
        svc = _svc()
        svc.connect("u1", "groq", "gsk_x0000000000AB42", selected_model="qwen/qwen3.6-27b")
        cp = svc.build_configured_provider("u1", "groq")
        self.assertIsNotNone(cp)
        self.assertEqual(cp.credential_source, "personal")
        self.assertEqual(cp.model_id, "qwen/qwen3.6-27b")

    def test_chua_ket_noi_tra_none(self):
        svc = _svc()
        self.assertIsNone(svc.build_configured_provider("u1", "groq"))


class OwnershipIsolationTest(unittest.TestCase):
    """Part D — het suc quan trong: nguoi dung B khong bao gio dung duoc
    provider cua nguoi dung A, ke ca goi thang qua service nay."""

    @patch("server.translation_byok_service.kiem_tra_ket_noi_groq")
    def setUp(self, kiem_tra):
        self.svc = _svc()
        self.svc.connect("user-a", "groq", "gsk_cua_a_00000AAAA")

    def test_nguoi_dung_khac_khong_lay_duoc_provider(self):
        self.assertIsNone(self.svc.build_configured_provider("user-b", "groq"))

    def test_nguoi_dung_khac_khong_test_duoc(self):
        with self.assertRaises(NotFoundError):
            self.svc.test_connection("user-b", "groq")

    def test_nguoi_dung_khac_xoa_khong_anh_huong(self):
        self.svc.delete("user-b", "groq")
        cp = self.svc.build_configured_provider("user-a", "groq")
        self.assertIsNotNone(cp)  # ket noi cua A van con nguyen

    def test_nguoi_dung_khac_khong_thay_trong_list(self):
        self.assertEqual(self.svc.list_connections("user-b"), [])


if __name__ == "__main__":
    unittest.main()
