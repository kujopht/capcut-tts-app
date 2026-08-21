"""Test cho `server/episode_parser.py` — xem docstring dau module do."""

from __future__ import annotations

import unicodedata
import unittest

from server.episode_parser import (
    EpisodeSpanKind,
    parse_episode_number,
    parse_episode_span,
)


class ParseEpisodeNumberTest(unittest.TestCase):
    def test_cac_dang_yeu_cau_trong_de_bai(self):
        ca = {
            "Tập 12": 12,
            "Tap 12": 12,
            "Tập12": 12,
            "EP 12": 12,
            "EP12": 12,
            "Episode 12": 12,
            "E12": 12,
            "Chương 12": 12,
            "Chapter 12": 12,
            "Part 12": 12,
            "Phần 12": 12,
        }
        for tieu_de, ky_vong in ca.items():
            with self.subTest(tieu_de=tieu_de):
                self.assertEqual(parse_episode_number(tieu_de), ky_vong)

    def test_khong_phan_biet_hoa_thuong(self):
        self.assertEqual(parse_episode_number("tập 5"), 5)
        self.assertEqual(parse_episode_number("EPISODE 7"), 7)
        self.assertEqual(parse_episode_number("cHaPtEr 9"), 9)

    def test_nam_trong_mot_tieu_de_that(self):
        self.assertEqual(
            parse_episode_number("Tiên Nghịch - Tập 45 [Vietsub]"), 45)
        self.assertEqual(
            parse_episode_number("Renegade Immortal Episode 3 (English Sub)"), 3)
        self.assertEqual(parse_episode_number("[HD] Tiên Nghịch EP12"), 12)

    def test_dau_cham_giua_tu_khoa_va_so(self):
        self.assertEqual(parse_episode_number("Tap. 8"), 8)

    def test_khong_khop_thi_tra_none(self):
        self.assertIsNone(parse_episode_number("Tiên Nghịch - Trailer chính thức"))
        self.assertIsNone(parse_episode_number(""))
        self.assertIsNone(parse_episode_number("Vietsub full"))

    def test_so_phi_ly_bi_loai(self):
        self.assertIsNone(parse_episode_number("Tập 99999"))

    def test_uu_tien_tu_khoa_day_du_hon_e_tran(self):
        """"Episode 12" phai doc dung 12 qua nhanh tu khoa day du, khong bi
        nhanh "E12" can thiep sai (vi du bat nham thanh so khac)."""
        self.assertEqual(parse_episode_number("Episode 12"), 12)

    def test_chuoi_rong_hoac_none_khong_loi(self):
        self.assertIsNone(parse_episode_number(""))

    def test_lay_so_tap_DAU_TIEN_khi_co_nhieu_so(self):
        self.assertEqual(parse_episode_number("Tập 12 - 2024 Remastered"), 12)


class FuzzCorpusPhase7Test(unittest.TestCase):
    """
    Corpus fuzz TAT DINH cho Phase 7 (audit do tin cay YouTube/Trusted Video
    Sources) — bao phu: tieng Viet (co/khong dau), tieng Anh, "Ep." co dau
    cham, "E12" hoa/thuong, combo season+episode (BIET la CHUA ho tro, xem
    docstring dau `episode_parser.py` — chi liet ke cac dang duoc cong bo),
    Unicode NFC/NFD, tu khoa loai tru khong duoc parser nay xu ly (do la
    viec cua `video_classifier.py`), so nam trong ngu canh KHONG lien quan
    (nam phat hanh, luot xem), tieu de mo ho.

    Bug tim thay VA DA SUA qua bo corpus nay: `_BARE_E_RE` thieu
    `re.IGNORECASE` nen "e12" (thuong) khong khop trong khi "E12" (hoa)
    khop — mau thuan voi cam ket "khong phan biet hoa/thuong" o dau file.
    Xem `test_e_tran_khong_phan_biet_hoa_thuong` duoi day.
    """

    def test_e_tran_khong_phan_biet_hoa_thuong(self):
        """Bug Phase 7: truoc khi sua, "e12" (thuong) tra None trong khi
        "E12" (hoa) tra 12 — vi pham cam ket case-insensitive cua module."""
        for tieu_de in ("E12", "e12", "Tiên Nghịch e12", "Tiên Nghịch E12",
                        "[HD] tien nghich e5 vietsub"):
            with self.subTest(tieu_de=tieu_de):
                self.assertIsNotNone(parse_episode_number(tieu_de))

    def test_tieng_viet_co_dau_va_khong_dau(self):
        ca = {
            "Tập 1": 1, "TẬP 1": 1, "tập 1": 1, "Tap 1": 1, "TAP 1": 1,
            "Chương 7": 7, "CHƯƠNG 7": 7, "chuong 7": 7,
            "Phần 3": 3, "phan 3": 3,
        }
        for tieu_de, ky_vong in ca.items():
            with self.subTest(tieu_de=tieu_de):
                self.assertEqual(parse_episode_number(tieu_de), ky_vong)

    def test_tieng_anh_cac_dang(self):
        ca = {
            "Episode 12": 12, "episode 12": 12, "EPISODE 12": 12,
            "Ep. 12": 12, "ep. 12": 12, "Ep.12": 12,
            "Ep 12": 12, "EP#12": 12, "Ep #12": 12,
        }
        for tieu_de, ky_vong in ca.items():
            with self.subTest(tieu_de=tieu_de):
                self.assertEqual(parse_episode_number(tieu_de), ky_vong)

    def test_combo_season_episode_CHUA_duoc_ho_tro(self):
        """
        "S01E12"/"S2E12" dinh lien KHONG nam trong danh sach dang duoc cong
        bo o docstring dau file (chi liet ke Tap/Tập/EP/Episode/E12/Chuong/
        Chapter/Phan/Part) — dinh lien nghia la khong co ranh gioi tu `\\b`
        truoc "E" nen `_BARE_E_RE` khong khop. GHI NHAN day la HAN CHE DA
        BIET (khong phai bug — parser chua tung cam ket ho tro dang nay),
        KHONG sua theo FIX POLICY (se la mo rong parser, ngoai pham vi audit
        Phase 7). Dang CO khoang trang ("Season 2 Episode 12") VAN doc dung
        vi "Episode 12" la mot tu khoa day du doc lap.
        """
        self.assertIsNone(parse_episode_number("S01E12"))
        self.assertIsNone(parse_episode_number("S2E12"))
        self.assertEqual(parse_episode_number("Season 2 Episode 12"), 12)

    def test_unicode_nfc_va_nfd_deu_khop(self):
        """Cung mot tieu de go bang hai cach chuan hoa Unicode khac nhau
        (NFC — dau ghep san, NFD — dau tach roi) phai ra CUNG ket qua, vi
        `parse_episode_number` tu chuan hoa NFC truoc khi khop."""
        nfc = unicodedata.normalize("NFC", "Tập 12")
        nfd = unicodedata.normalize("NFD", "Tập 12")
        self.assertNotEqual(nfc, nfd)  # xac nhan hai chuoi THAT SU khac byte
        self.assertEqual(parse_episode_number(nfc), 12)
        self.assertEqual(parse_episode_number(nfd), 12)

    def test_so_trong_ngu_canh_khong_lien_quan_khong_bi_nham(self):
        """So nam phat hanh/luot xem/do phan giai KHONG co tu khoa tap dung
        truoc no thi KHONG duoc coi la so tap."""
        self.assertIsNone(parse_episode_number("Tiên Nghịch (2024)"))
        self.assertIsNone(parse_episode_number("Tiên Nghịch - 1080p 60fps"))
        self.assertIsNone(parse_episode_number("Tiên Nghịch - 10000000 views"))
        self.assertIsNone(parse_episode_number("Tiên Nghịch 4K Remaster"))
        # Nhung neu co tu khoa THAT truoc mot con so canh nam phat hanh, van
        # phai doc dung so tap (khong bi nam sau "an" nham).
        self.assertEqual(parse_episode_number("Tiên Nghịch Tập 12 (2024)"), 12)

    def test_tieu_de_mo_ho_khong_co_tu_khoa(self):
        self.assertIsNone(parse_episode_number("Tiên Nghịch"))
        self.assertIsNone(parse_episode_number("Tiên Nghịch - Full"))
        self.assertIsNone(parse_episode_number("12"))  # so tran, khong tu khoa

    def test_tu_khoa_loai_tru_khong_duoc_parser_nay_xu_ly(self):
        """`parse_episode_number` CHI doc so — no KHONG biet gi ve OST/
        trailer/PV, day la viec cua `video_classifier.classify_video`
        (xem `test_video_classifier.py`). Ghi nhan ranh gioi trach nhiem ro
        rang: mot tieu de "Trailer Tập 3" VAN tra ve 3 o tang nay."""
        self.assertEqual(parse_episode_number("Tiên Nghịch Trailer Tập 3"), 3)
        self.assertEqual(parse_episode_number("Tiên Nghịch OST Tập 1"), 1)


class ParseEpisodeSpanTest(unittest.TestCase):
    """`parse_episode_span` — mo rong Auto-Ingestion Phase 1. Xem docstring
    `EpisodeSpan`/`EpisodeSpanKind` ve ly do can representation nay: KHONG
    duoc thu gon "Tập 1-13" thanh tap 1 mot cach am tham."""

    def test_dai_gach_ngang_dinh_lien(self):
        for tieu_de, (dau, cuoi) in {
            "Tập 1-13": (1, 13),
            "Ep 1-12": (1, 12),
            "ALL IN ONE | Reincarnation no Kaben Tập 1-13 | Sức Mạnh": (1, 13),
        }.items():
            with self.subTest(tieu_de=tieu_de):
                span = parse_episode_span(tieu_de)
                self.assertIsNotNone(span)
                self.assertEqual(span.kind, EpisodeSpanKind.RANGE)
                self.assertEqual((span.start, span.end), (dau, cuoi))
                self.assertEqual(span.count, cuoi - dau + 1)
                self.assertFalse(span.is_single)

    def test_khoang_trang_quanh_gach_khong_phai_dai_tap(self):
        """"Tập 12 - 2024 Remastered" la MOT so tap voi hau to nam phat hanh,
        KHONG PHAI dai tap 12-2024 — gach ngang co khoang trang hai ben la
        ranh gioi cum tu, khac voi dai tap dinh lien "1-13"."""
        span = parse_episode_span("Tiên Nghịch Tập 12 - 2024 Remastered")
        self.assertEqual(span.kind, EpisodeSpanKind.SINGLE)
        self.assertEqual(span.start, 12)

    def test_mot_tap_don_le_van_la_single(self):
        span = parse_episode_span("Reincarnation no Kaben EP 14")
        self.assertEqual(span.kind, EpisodeSpanKind.SINGLE)
        self.assertEqual((span.start, span.end), (14, 14))
        self.assertTrue(span.is_single)
        self.assertEqual(span.count, 1)

    def test_video_tong_hop_ca_series(self):
        for tieu_de in (
            "Reincarnation no Kaben ALL IN ONE",
            "Reincarnation no Kaben FULL",
            "Reincarnation no Kaben Trọn bộ",
            "Reincarnation no Kaben tron bo",
        ):
            with self.subTest(tieu_de=tieu_de):
                span = parse_episode_span(tieu_de)
                self.assertIsNotNone(span)
                self.assertEqual(span.kind, EpisodeSpanKind.COMPILATION)
                self.assertIsNone(span.start)
                self.assertIsNone(span.end)
                self.assertIsNone(span.count)

    def test_khong_khop_gi_tra_none(self):
        self.assertIsNone(parse_episode_span("Tiên Nghịch Trailer chính thức"))
        self.assertIsNone(parse_episode_span(""))
        self.assertIsNone(parse_episode_span("Tiên Nghịch"))

    def test_dai_vo_ly_roi_xuong_so_don(self):
        """Neu dai doc duoc phi ly (cuoi <= dau), roi xuong doc so don thay
        vi tra ve mot RANGE sai."""
        span = parse_episode_span("Tập 13-1")
        self.assertEqual(span.kind, EpisodeSpanKind.SINGLE)
        self.assertEqual(span.start, 13)

    def test_tuong_thich_nguoc_voi_parse_episode_number(self):
        """`parse_episode_span` khong duoc lam sai `parse_episode_number` —
        moi tieu de single-episode phai cho cung so tap qua ca hai ham."""
        for tieu_de in ("Tập 12", "EP12", "Episode 12", "E12", "Tap. 8"):
            with self.subTest(tieu_de=tieu_de):
                so = parse_episode_number(tieu_de)
                span = parse_episode_span(tieu_de)
                self.assertEqual(span.start, so)


if __name__ == "__main__":
    unittest.main()
