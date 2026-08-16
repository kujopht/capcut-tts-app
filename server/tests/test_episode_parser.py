"""Test cho `server/episode_parser.py` — xem docstring dau module do."""

from __future__ import annotations

import unittest

from server.episode_parser import parse_episode_number


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


if __name__ == "__main__":
    unittest.main()
