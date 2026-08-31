"""server/import_pipeline/chapter_split.py"""
from __future__ import annotations

import unittest

from server.import_pipeline.chapter_split import split_into_chapters


class SplitIntoChaptersTest(unittest.TestCase):
    def test_khong_co_mau_nao_tra_ve_mot_chuong_duy_nhat(self):
        ket_qua = split_into_chapters("Chỉ là một đoạn văn bản bình thường.")
        self.assertEqual(len(ket_qua), 1)
        self.assertEqual(ket_qua[0].content, "Chỉ là một đoạn văn bản bình thường.")

    def test_van_ban_rong_tra_ve_danh_sach_rong(self):
        self.assertEqual(split_into_chapters(""), [])
        self.assertEqual(split_into_chapters("   \n  \n "), [])

    def test_tach_dung_theo_mau_chuong_tieng_viet(self):
        text = "Chương 1\nNội dung một.\nChương 2: Tên chương\nNội dung hai."
        ket_qua = split_into_chapters(text)
        self.assertEqual(len(ket_qua), 2)
        self.assertEqual(ket_qua[0].content, "Nội dung một.")
        self.assertEqual(ket_qua[1].title, "Chương 2: Tên chương")
        self.assertEqual(ket_qua[1].content, "Nội dung hai.")

    def test_tach_dung_theo_mau_chapter_tieng_anh(self):
        text = "Chapter 1\nFirst content.\nChapter 2\nSecond content."
        ket_qua = split_into_chapters(text)
        self.assertEqual(len(ket_qua), 2)

    def test_giu_lai_loi_mo_dau_truoc_chuong_dau_tien(self):
        text = "Lời tựa của tác giả.\nChương 1\nNội dung."
        ket_qua = split_into_chapters(text)
        self.assertEqual(len(ket_qua), 2)
        self.assertEqual(ket_qua[0].title, "Lời mở đầu")
        self.assertEqual(ket_qua[1].content, "Nội dung.")

    def test_dong_qua_dai_khong_bi_coi_la_tieu_de(self):
        dong_dai = "Chapter 1 " + "chi la mot cau van rat dai " * 10
        text = f"{dong_dai}\nChương 1\nNội dung thật."
        ket_qua = split_into_chapters(text)
        # Dong dai KHONG duoc coi la tieu de nen roi vao "Loi mo dau"; chi
        # "Chương 1" that su la mot chuong.
        self.assertEqual(len(ket_qua), 2)
        self.assertEqual(ket_qua[0].title, "Lời mở đầu")
        self.assertEqual(ket_qua[1].title, "Chương 1")
        self.assertEqual(ket_qua[1].content, "Nội dung thật.")


if __name__ == "__main__":
    unittest.main()
