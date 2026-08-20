"""Test cho `server/video_classifier.py`."""

from __future__ import annotations

import unicodedata
import unittest

from server.trusted_source_domain import SeriesMapping, TrustedSource, TrustedSourceType
from server.video_classifier import NEGATIVE_KEYWORDS, chuan_hoa, classify_video


def _nguon(**kw) -> TrustedSource:
    return TrustedSource(
        source_type=TrustedSourceType.YOUTUBE_CHANNEL,
        youtube_channel_id="UC_kenh_A",
        **kw,
    )


def _anh_xa(**kw) -> SeriesMapping:
    mac_dinh = {
        "trusted_source_id": "tsrc_1", "animation_series_id": "ani_1",
        "aliases": ["tiên nghịch", "renegade immortal"],
    }
    mac_dinh.update(kw)
    return SeriesMapping(**mac_dinh)


class ChuanHoaTest(unittest.TestCase):
    def test_bo_dau_va_thuong_hoa(self):
        self.assertEqual(chuan_hoa("Tiên Nghịch"), "tien nghich")
        self.assertEqual(chuan_hoa("TIÊN NGHỊCH"), "tien nghich")


class ClassifyVideoTest(unittest.TestCase):
    def test_khop_alias_co_dau_va_khong_dau(self):
        nguon = _nguon()
        anh_xa = _anh_xa()
        for tieu_de in ("Tiên Nghịch - Tập 12", "Tien Nghich Tap 12"):
            with self.subTest(tieu_de=tieu_de):
                kq = classify_video(title=tieu_de, channel_id="UC_kenh_A",
                                    trusted_source=nguon, mappings=[anh_xa])
                self.assertEqual(kq.series_id, "ani_1")
                self.assertEqual(kq.episode_number, 12)
                self.assertGreater(kq.confidence, 0.5)

    def test_khong_khop_alias_nao_tra_rong(self):
        nguon = _nguon()
        anh_xa = _anh_xa()
        kq = classify_video(title="Phim khác - Tập 1", channel_id="UC_kenh_A",
                            trusted_source=nguon, mappings=[anh_xa])
        self.assertEqual(kq.series_id, "")
        self.assertEqual(kq.mapping_id, "")

    def test_tu_khoa_loai_tru_mac_dinh_ha_diem_va_danh_dau_excluded(self):
        nguon = _nguon()
        anh_xa = _anh_xa()
        kq = classify_video(title="Tiên Nghịch Trailer chính thức",
                           channel_id="UC_kenh_A", trusted_source=nguon,
                           mappings=[anh_xa])
        self.assertTrue(kq.excluded)
        self.assertLess(kq.confidence, 0.3)

    def test_tu_khoa_loai_tru_rieng_cua_anh_xa(self):
        nguon = _nguon()
        anh_xa = _anh_xa(exclude_keywords=["ost", "cover"])
        kq = classify_video(title="Tiên Nghịch OST đầu phim",
                           channel_id="UC_kenh_A", trusted_source=nguon,
                           mappings=[anh_xa])
        self.assertTrue(kq.excluded)

    def test_kenh_khop_cong_them_diem(self):
        nguon = _nguon()
        anh_xa = _anh_xa()
        khop_kenh = classify_video(title="Tiên Nghịch Tập 5", channel_id="UC_kenh_A",
                                  trusted_source=nguon, mappings=[anh_xa])
        khac_kenh = classify_video(title="Tiên Nghịch Tập 5", channel_id="UC_kenh_KHAC",
                                   trusted_source=nguon, mappings=[anh_xa])
        self.assertGreater(khop_kenh.confidence, khac_kenh.confidence)

    def test_tap_lan_can_cong_them_diem(self):
        nguon = _nguon()
        anh_xa = _anh_xa()
        co_lan_can = classify_video(
            title="Tiên Nghịch Tập 12", channel_id="UC_kenh_A",
            trusted_source=nguon, mappings=[anh_xa],
            episodes_by_series={"ani_1": [11, 13]})
        khong_lan_can = classify_video(
            title="Tiên Nghịch Tập 12", channel_id="UC_kenh_A",
            trusted_source=nguon, mappings=[anh_xa],
            episodes_by_series={"ani_1": [50, 60]})
        self.assertGreater(co_lan_can.confidence, khong_lan_can.confidence)

    def test_nhieu_anh_xa_chon_diem_cao_nhat(self):
        nguon = _nguon()
        a1 = _anh_xa(mapping_id="m1", animation_series_id="ani_1",
                    aliases=["tiên nghịch"])
        a2 = _anh_xa(mapping_id="m2", animation_series_id="ani_2",
                    aliases=["nghịch"])  # tu con chung, khop yeu hon
        kq = classify_video(title="Tiên Nghịch Tập 12", channel_id="UC_kenh_A",
                           trusted_source=nguon, mappings=[a1, a2])
        self.assertEqual(kq.series_id, "ani_1")

    def test_tu_khoa_bao_gom_cong_diem(self):
        nguon = _nguon()
        co_tu_khoa = _anh_xa(include_keywords=["vietsub"])
        kq_co = classify_video(title="Tiên Nghịch Tập 5 Vietsub",
                              channel_id="UC_kenh_A", trusted_source=nguon,
                              mappings=[co_tu_khoa])
        kq_khong = classify_video(title="Tiên Nghịch Tập 5",
                                 channel_id="UC_kenh_A", trusted_source=nguon,
                                 mappings=[co_tu_khoa])
        self.assertGreater(kq_co.confidence, kq_khong.confidence)

    def test_tu_khoa_mong_doi_tu_no_co_the_nhan_dien_mapping(self):
        """UI cho phep de alias rong; tu khoa mong doi da luu phai duoc dung
        lam tin hieu dinh danh, khong bi bo qua boi dieu kien alias cu."""
        nguon = _nguon()
        anh_xa = _anh_xa(
            mapping_id="smap_reincarnation",
            aliases=[],
            include_keywords=["Reincarnation no Kaben"],
        )
        kq = classify_video(
            title="ALL IN ONE | Reincarnation no Kaben Tập 1-13",
            channel_id="UC_kenh_A",
            trusted_source=nguon,
            mappings=[anh_xa],
        )
        self.assertEqual(kq.mapping_id, "smap_reincarnation")
        self.assertEqual(kq.series_id, "ani_1")
        self.assertTrue(any("Reincarnation no Kaben" in s for s in kq.signals))

    def test_khong_co_anh_xa_nao_tra_rong(self):
        nguon = _nguon()
        kq = classify_video(title="Tiên Nghịch Tập 1", channel_id="UC_kenh_A",
                           trusted_source=nguon, mappings=[])
        self.assertEqual(kq.series_id, "")
        self.assertEqual(kq.episode_number, 1)  # van doc duoc so tap

    def test_diem_luon_trong_khoang_0_1(self):
        nguon = _nguon()
        anh_xa = _anh_xa(exclude_keywords=["tiên nghịch"])  # tu loai tru = alias
        kq = classify_video(title="Tiên Nghịch Trailer PV OST",
                           channel_id="UC_KHAC", trusted_source=nguon,
                           mappings=[anh_xa])
        self.assertGreaterEqual(kq.confidence, 0.0)
        self.assertLessEqual(kq.confidence, 1.0)


class FuzzCorpusPhase7Test(unittest.TestCase):
    """
    Corpus fuzz TAT DINH cho Phase 7 — tap trung vao tu khoa loai tru mac
    dinh (OST/trailer/PV/...), tieu de mo ho (khop alias nhung khong doc
    duoc so tap), va Unicode NFC/NFD tren alias/tieu de.
    """

    def test_moi_tu_khoa_loai_tru_mac_dinh_deu_ha_diem_va_danh_dau_excluded(self):
        """Fuzz TOAN BO danh sach `NEGATIVE_KEYWORDS` khai bao san — moi tu
        rieng le, dung nhu MOT TU (co ranh gioi), phai bi phat diem VA danh
        dau `excluded=True`, bat ke tu do la gi trong danh sach."""
        nguon = _nguon()
        anh_xa = _anh_xa()
        for tu in NEGATIVE_KEYWORDS:
            tieu_de = f"Tiên Nghịch {tu.upper()} chính thức"
            with self.subTest(tu_khoa=tu):
                kq = classify_video(title=tieu_de, channel_id="UC_kenh_A",
                                    trusted_source=nguon, mappings=[anh_xa])
                self.assertTrue(kq.excluded, f"'{tu}' phải bị loại trừ")

    def test_tu_khoa_loai_tru_la_mot_phan_cua_tu_khac_khong_bi_nham(self):
        """"pv" trong "pvp", "op" trong "opera"/"operation", "ed" trong
        "edit" KHONG duoc coi la tu khoa loai tru — `_co_tu` doi hoi ranh
        gioi tu ca hai phia."""
        nguon = _nguon()
        anh_xa = _anh_xa()
        for tieu_de in (
            "Tiên Nghịch Tập 12 PVP Championship",
            "Tiên Nghịch Tập 12 Operation Rescue",
            "Tiên Nghịch Tập 12 Edit nhanh",
        ):
            with self.subTest(tieu_de=tieu_de):
                kq = classify_video(title=tieu_de, channel_id="UC_kenh_A",
                                    trusted_source=nguon, mappings=[anh_xa])
                self.assertFalse(kq.excluded, f"'{tieu_de}' không được bị loại trừ")

    def test_khop_alias_nhung_khong_co_so_tap_van_khop_series(self):
        """Tieu de MO HO: khop alias nhung KHONG doc duoc so tap (vi du
        video tong hop/AMV khong danh so) — van phai nhan dien duoc SERIES
        (de quan tri tu gan so tap bang tay), `episode_number` la `None`,
        khong phai loi."""
        nguon = _nguon()
        anh_xa = _anh_xa()
        kq = classify_video(title="Tiên Nghịch AMV tổng hợp cảm động",
                           channel_id="UC_kenh_A", trusted_source=nguon,
                           mappings=[anh_xa])
        self.assertEqual(kq.series_id, "ani_1")
        self.assertIsNone(kq.episode_number)

    def test_alias_nfc_khop_tieu_de_nfd_va_nguoc_lai(self):
        """Alias va tieu de go theo hai kieu chuan hoa Unicode khac nhau
        (NFC/NFD) van phai khop, vi `chuan_hoa()` dua ca hai ve cung mot
        dang truoc khi so sanh."""
        nguon = _nguon()
        anh_xa = _anh_xa(aliases=[unicodedata.normalize("NFD", "Tiên Nghịch")])
        tieu_de_nfc = unicodedata.normalize("NFC", "Tiên Nghịch Tập 9")
        kq = classify_video(title=tieu_de_nfc, channel_id="UC_kenh_A",
                           trusted_source=nguon, mappings=[anh_xa])
        self.assertEqual(kq.series_id, "ani_1")
        self.assertEqual(kq.episode_number, 9)

    def test_nam_phat_hanh_canh_so_tap_khong_lam_sai_so_tap(self):
        """So nam (nam gan lien voi so tap that trong tieu de) khong duoc
        parser doc nham thanh so tap — so tap dau tien (co tu khoa) phai
        duoc uu tien, xem `test_episode_parser.py` cho pham vi day du hon."""
        nguon = _nguon()
        anh_xa = _anh_xa()
        kq = classify_video(title="Tiên Nghịch Tập 12 (2024) 1080p",
                           channel_id="UC_kenh_A", trusted_source=nguon,
                           mappings=[anh_xa])
        self.assertEqual(kq.episode_number, 12)


if __name__ == "__main__":
    unittest.main()
