"""Test cho `server/series_fingerprint.py` (Auto-Ingestion Phase 1)."""

from __future__ import annotations

import unittest

from server.series_fingerprint import extract_fingerprint, similarity


class ExtractFingerprintTest(unittest.TestCase):
    def test_cac_dang_don_gian_tu_dac_ta(self):
        for tieu_de in (
            "Reincarnation no Kaben Tập 1",
            "Reincarnation no Kaben Tập 2",
            "Reincarnation no Kaben Tập 1-13",
            "Reincarnation no Kaben EP 14",
        ):
            with self.subTest(tieu_de=tieu_de):
                fp = extract_fingerprint(tieu_de, channel_title="Cung Điện Anime")
                self.assertEqual(fp.canonical_name, "Reincarnation no Kaben")

    def test_tieu_de_thuc_nhieu_doan_pipe(self):
        """Tieu de THAT tung gay loi truoc khi sua (Trusted Channels E2E) —
        "ALL IN ONE" (nhan quang cao) VA ten kenh o hai dau khong duoc phep
        lam sai ten series o giua."""
        tieu_de = ("ALL IN ONE | Reincarnation no Kaben Tập 1-13 | "
                   "Sức Mạnh Luân Hồi Được Thức Tỉnh | Cung Điện Anime")
        fp = extract_fingerprint(
            tieu_de, channel_id="UCfYGlQlolrAeqM4TJsTxtEw",
            channel_title="Cung Điện Anime")
        self.assertEqual(fp.canonical_name, "Reincarnation no Kaben")

    def test_doan_chi_la_nhan_quang_cao_khong_duoc_chon(self):
        """Mot doan CHI gom tin hieu tap/tong hop (khong con gi sau khi cat)
        khong du dieu kien lam ten series, du no co tin hieu — tranh chon
        "ALL IN ONE" lam ten thay vi ten series thuc."""
        fp = extract_fingerprint(
            "ALL IN ONE | Tiên Nghịch Tập 5", channel_title="Kenh Z")
        self.assertEqual(fp.canonical_name, "Tiên Nghịch")

    def test_khong_co_dau_phan_cach_van_cat_duoc_tin_hieu_tap(self):
        fp = extract_fingerprint("Tiên Nghịch - Tập 12 [Vietsub]")
        self.assertEqual(fp.canonical_name, "Tiên Nghịch")

    def test_khong_co_tin_hieu_gi_thi_dung_nguyen_tieu_de(self):
        fp = extract_fingerprint("Tiên Nghịch")
        self.assertEqual(fp.canonical_name, "Tiên Nghịch")

    def test_normalized_key_bo_dau_va_thuong_hoa(self):
        fp = extract_fingerprint("Tiên Nghịch Tập 1")
        self.assertEqual(fp.normalized_key, "tien nghich")

    def test_ten_khong_bao_gio_rong(self):
        for tieu_de in ("Tập 1", "ALL IN ONE", "", "Cung Điện Anime"):
            with self.subTest(tieu_de=tieu_de):
                fp = extract_fingerprint(tieu_de, channel_title="Cung Điện Anime")
                self.assertIsInstance(fp.canonical_name, str)


class SimilarityTest(unittest.TestCase):
    def test_cung_series_moi_dang_tieu_de_khac_nhau_giong_1(self):
        seed = extract_fingerprint(
            "Reincarnation no Kaben Tập 1", channel_title="Cung Điện Anime")
        for tieu_de in (
            "Reincarnation no Kaben Tập 2",
            "Reincarnation no Kaben Tập 1-13",
            "ALL IN ONE | Reincarnation no Kaben Tập 1-13 | Sức Mạnh Luân "
            "Hồi Được Thức Tỉnh | Cung Điện Anime",
            "Reincarnation no Kaben EP 14",
        ):
            with self.subTest(tieu_de=tieu_de):
                other = extract_fingerprint(tieu_de, channel_title="Cung Điện Anime")
                self.assertEqual(similarity(seed, other), 1.0)

    def test_series_khac_nhau_giong_0(self):
        a = extract_fingerprint("Reincarnation no Kaben Tập 1")
        b = extract_fingerprint("Tiên Nghịch Tập 1")
        self.assertEqual(similarity(a, b), 0.0)

    def test_fingerprint_rong_khong_gay_loi(self):
        a = extract_fingerprint("")
        b = extract_fingerprint("Tiên Nghịch Tập 1")
        self.assertEqual(similarity(a, b), 0.0)

    def test_tien_to_that_su_giong_085(self):
        a = extract_fingerprint("Tiên Nghịch")
        b = extract_fingerprint("Tiên Nghịch Ngoại Truyện")
        self.assertEqual(similarity(a, b), 0.85)


if __name__ == "__main__":
    unittest.main()
