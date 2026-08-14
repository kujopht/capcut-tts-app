"""`MockTranslationStore` — CRUD ket noi provider ca nhan (V5.1 BYOK)."""

from __future__ import annotations

import unittest

from server.adapters import NotFoundError
from server.translation_domain import ProviderConnection, id_ket_noi_provider
from server.translation_store import MockTranslationStore


def _conn(user_id="u1", provider_id="groq", secret="byok.v1.a.b", last4="AB42"):
    return ProviderConnection(user_id=user_id, provider_id=provider_id,
                              encrypted_secret=secret, last4=last4)


class ConnectionCrudTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MockTranslationStore()

    def test_luu_roi_doc_lai_dung(self):
        self.store.save_connection(_conn())
        conn = self.store.get_connection("u1", "groq")
        self.assertEqual(conn.last4, "AB42")
        self.assertEqual(conn.encrypted_secret, "byok.v1.a.b")

    def test_chua_ket_noi_nem_not_found(self):
        with self.assertRaises(NotFoundError):
            self.store.get_connection("u1", "groq")

    def test_ket_noi_lai_ghi_de_khong_tao_ban_ghi_thu_hai(self):
        self.store.save_connection(_conn(secret="byok.v1.old.old"))
        self.store.save_connection(_conn(secret="byok.v1.new.new"))
        ds = self.store.list_connections("u1")
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0].encrypted_secret, "byok.v1.new.new")

    def test_liet_ke_chi_dung_user(self):
        self.store.save_connection(_conn(user_id="u1", provider_id="groq"))
        self.store.save_connection(_conn(user_id="u1", provider_id="cloudflare"))
        self.store.save_connection(_conn(user_id="u2", provider_id="groq"))
        ds = self.store.list_connections("u1")
        self.assertEqual({c.provider_id for c in ds}, {"groq", "cloudflare"})

    def test_xoa_ket_noi(self):
        self.store.save_connection(_conn())
        self.store.delete_connection("u1", "groq")
        with self.assertRaises(NotFoundError):
            self.store.get_connection("u1", "groq")

    def test_xoa_khong_ton_tai_khong_nem_loi(self):
        self.store.delete_connection("u1", "groq")  # im lang, khong crash


class OwnershipIsolationTest(unittest.TestCase):
    """Cot loi Part D: khong the doc/xoa ket noi cua nguoi dung khac, KE CA
    biet duoc (hoac doan duoc) connection_id."""

    def setUp(self) -> None:
        self.store = MockTranslationStore()
        self.store.save_connection(_conn(user_id="user-a", secret="byok.v1.a.secret"))

    def test_nguoi_dung_khac_khong_doc_duoc_ket_noi(self):
        with self.assertRaises(NotFoundError):
            self.store.get_connection("user-b", "groq")

    def test_nguoi_dung_khac_xoa_khong_anh_huong_ban_ghi_that(self):
        self.store.delete_connection("user-b", "groq")  # khong lam gi ca
        conn = self.store.get_connection("user-a", "groq")
        self.assertEqual(conn.encrypted_secret, "byok.v1.a.secret")

    def test_connection_id_tat_dinh_nhung_van_bi_chan_boi_kiem_tra_user_id(self):
        """Du connection_id la TAT DINH (co the tinh duoc tu user_id+
        provider_id cua CHINH MINH), no khong giup doan ra ban ghi cua NGUOI
        KHAC vi `get_connection` luon doi chieu lai `conn.user_id`."""
        id_that_cua_a = id_ket_noi_provider("user-a", "groq")
        id_neu_la_b = id_ket_noi_provider("user-b", "groq")
        self.assertNotEqual(id_that_cua_a, id_neu_la_b)
        # Ke ca neu user-b nao do tinh dung id cua user-a, get_connection
        # van doi hoi user_id="user-b" khop voi ban ghi -> khong khop -> 404.
        with self.assertRaises(NotFoundError):
            self.store.get_connection("user-b", "groq")


if __name__ == "__main__":
    unittest.main()
