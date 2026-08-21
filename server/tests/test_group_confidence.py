"""Test cho `server.series_discovery_domain.group_confidence` (Auto-Ingestion
Phase 5 pre-merge hardening — chinh sach tin cay BA HANG cho cum ung vien
series MOI). Thuan, khong I/O — dung fixture toi thieu (dict + fingerprint),
khong can TrustedSourceService/store."""

from __future__ import annotations

import unittest

from server.series_discovery_domain import group_confidence
from server.series_fingerprint import SeriesFingerprint, extract_fingerprint


def _video(video_id: str, title: str) -> dict:
    return {"video_id": video_id, "title": title, "channel_id": "UCabc",
            "channel_title": "Kênh test"}


def _muc(video_id: str, title: str) -> tuple:
    v = _video(video_id, title)
    fp = extract_fingerprint(title, channel_id=v["channel_id"], channel_title=v["channel_title"])
    return (v, fp)


class GroupConfidenceTest(unittest.TestCase):
    def test_cum_3_video_tap_mach_lac_la_high(self):
        nhom = [_muc(f"v{i}", f"Tiên Nghịch Tập {i}") for i in (1, 2, 3)]
        hang, diem, tin_hieu = group_confidence(nhom)
        self.assertEqual(hang, "high")
        self.assertGreaterEqual(diem, 0.55)
        self.assertTrue(tin_hieu)

    def test_cum_2_video_tap_mach_lac_la_high(self):
        nhom = [_muc("v1", "Tiên Nghịch Tập 1"), _muc("v2", "Tiên Nghịch Tập 2")]
        hang, diem, _ = group_confidence(nhom)
        self.assertEqual(hang, "high")

    def test_singleton_khong_co_tin_hieu_la_low(self):
        nhom = [_muc("v1", "Vlog ngày cuối tuần")]
        hang, diem, _ = group_confidence(nhom)
        self.assertEqual(hang, "low")
        self.assertLess(diem, 0.10)

    def test_singleton_co_so_tap_la_medium(self):
        nhom = [_muc("v1", "Tiên Nghịch Tập 5")]
        hang, diem, _ = group_confidence(nhom)
        self.assertEqual(hang, "medium")
        self.assertGreaterEqual(diem, 0.10)
        self.assertLess(diem, 0.55)

    def test_singleton_compilation_khong_co_tap_don_le_bi_phat(self):
        nhom = [_muc("v1", "Tiên Nghịch Trọn Bộ Full")]
        hang, diem, tin_hieu = group_confidence(nhom)
        self.assertIn(hang, ("low", "medium"))
        self.assertTrue(any("không" in t and "tập đơn lẻ" in t for t in tin_hieu))

    def test_nguon_playlist_cong_them_diem_nhung_khong_du_mot_minh(self):
        nhom = [_muc("v1", "Tiên Nghịch Tập 5")]
        _hang_khong_playlist, diem_khong, _ = group_confidence(nhom, is_playlist=False)
        hang_playlist, diem_co, _ = group_confidence(nhom, is_playlist=True)
        self.assertGreater(diem_co, diem_khong)
        self.assertNotEqual(hang_playlist, "high", "playlist mot minh khong du de HIGH")

    def test_diem_gioi_han_trong_khoang_0_1(self):
        nhom = [_muc("v1", "Vlog linh tinh không liên quan gì cả")]
        _hang, diem, _ = group_confidence(nhom)
        self.assertGreaterEqual(diem, 0.0)
        self.assertLessEqual(diem, 1.0)

    def test_hai_video_yeu_gan_ket_thap_khong_tu_dong_high(self):
        """2 video CHI mot co so tap (video kia khong co tin hieu tap nao)
        VA fingerprint KHAC nhau hoan toan (mo phong bang tay — trong THUC
        TE `_gom_nhom_ung_vien` chi gom cac video CUNG `normalized_key` vao
        chung mot `nhom`, nen truong hop "cung nhom nhung fingerprint khac
        nhau" nay khong xay ra tu pipeline that; no chi kiem tra rieng
        nhanh "gan_ket_cao" cua `group_confidence` nhu mot ham thuan) —
        tong diem khong du de dat HIGH, chi MEDIUM."""
        v1 = _video("v1", "Tiên Nghịch Tập 1")
        fp1 = SeriesFingerprint(
            raw_title=v1["title"], canonical_name="Tiên Nghịch",
            normalized_key="tien nghich")
        v2 = _video("v2", "Một video khác không có số tập")
        fp2 = SeriesFingerprint(
            raw_title=v2["title"], canonical_name="mot video khac",
            normalized_key="mot video khac")
        nhom = [(v1, fp1), (v2, fp2)]
        hang, diem, _ = group_confidence(nhom)
        self.assertNotEqual(hang, "high")
        self.assertEqual(hang, "medium")

    def test_hai_video_cung_ten_chi_mot_co_so_tap_van_la_high(self):
        """Cum THAT (nhu tu `_gom_nhom_ung_vien`, gom theo `normalized_key`
        CHINH XAC): 2 video CUNG mot ten chinh tac, nhung CHI MOT video co
        so tap don le doc duoc (video kia la ban "Trọn Bộ" cung series) —
        PHAI la HIGH, vi ban Tron Bo van la bang chung gan ket that ve CUNG
        mot series (khong phai trung ten ngau nhien). Day la hanh vi CO CHU
        DICH, khong phai loi — doi chieu voi
        `test_dai_tap_gom_dung_series_nhung_cho_duyet`
        (`test_channel_discovery.py`), noi video "Tron Bo" van vao CUNG
        mot cum HIGH nhung ban than no khong duoc tinh la confident_import
        (xac nhan lai khi review PR #22, 2026-08-21 — xem ghi chu tai
        `_TRONG_SO_CUM` trong `series_discovery_domain.py`)."""
        v1 = _video("v1", "Tiên Nghịch Tập 1")
        fp1 = extract_fingerprint(
            v1["title"], channel_id=v1["channel_id"], channel_title=v1["channel_title"])
        v2 = _video("v2", "Tiên Nghịch Full Trọn Bộ")
        fp2 = extract_fingerprint(
            v2["title"], channel_id=v2["channel_id"], channel_title=v2["channel_title"])
        self.assertEqual(fp1.normalized_key, fp2.normalized_key,
                          "tien de: hai fingerprint phai CUNG mot key de mo phong dung cum that")
        nhom = [(v1, fp1), (v2, fp2)]
        hang, diem, _ = group_confidence(nhom)
        self.assertEqual(hang, "high")
        self.assertGreaterEqual(diem, 0.55)


if __name__ == "__main__":
    unittest.main()
