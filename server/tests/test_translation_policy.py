"""
Chinh sach thuan cua Novel Translation Studio (V5) — `server/translation.py`.

Cung phong cach voi `test_social_policy.py`: khong dung kho, khong dung may
chu, moi bai kiem MOT quy tac.
"""

from __future__ import annotations

import unittest

from server.translation import (
    GlossaryCategory,
    GlossaryEntry,
    QualityMode,
    TranslationJobStatus,
    ap_dung_khoa_glossary,
    buoc_tiep_theo,
    kiem_glossary_entry,
    tach_chuong,
    tach_doan_trong_chuong,
    uoc_luong,
)


class MayTrangThaiTest(unittest.TestCase):
    def test_thu_tu_day_du_che_do_can_bang(self):
        b = TranslationJobStatus.QUEUED
        duong_di = [b]
        for _ in range(6):
            b = buoc_tiep_theo(b, QualityMode.CAN_BANG)
            duong_di.append(b)
        self.assertEqual(duong_di, [
            TranslationJobStatus.QUEUED, TranslationJobStatus.ANALYZING,
            TranslationJobStatus.GLOSSARY, TranslationJobStatus.TRANSLATING,
            TranslationJobStatus.REVIEWING, TranslationJobStatus.QA,
            TranslationJobStatus.COMPLETED,
        ])

    def test_che_do_nhanh_bo_qua_glossary_va_reviewing(self):
        b = TranslationJobStatus.QUEUED
        duong_di = [b]
        for _ in range(4):
            b = buoc_tiep_theo(b, QualityMode.NHANH)
            duong_di.append(b)
        self.assertEqual(duong_di, [
            TranslationJobStatus.QUEUED, TranslationJobStatus.ANALYZING,
            TranslationJobStatus.TRANSLATING, TranslationJobStatus.QA,
            TranslationJobStatus.COMPLETED,
        ])

    def test_job_ket_thuc_khong_co_buoc_tiep(self):
        with self.assertRaises(ValueError):
            buoc_tiep_theo(TranslationJobStatus.COMPLETED, QualityMode.CAN_BANG)
        with self.assertRaises(ValueError):
            buoc_tiep_theo(TranslationJobStatus.FAILED, QualityMode.NHANH)
        with self.assertRaises(ValueError):
            buoc_tiep_theo(TranslationJobStatus.CANCELLED, QualityMode.VAN_HOC)

    def test_van_hoc_va_can_bang_cung_so_buoc_trang_thai(self):
        """Khac o SO PASS dich (tang service), khong khac o may trang thai."""
        b1, b2 = TranslationJobStatus.QUEUED, TranslationJobStatus.QUEUED
        d1, d2 = [b1], [b2]
        for _ in range(6):
            b1 = buoc_tiep_theo(b1, QualityMode.CAN_BANG)
            b2 = buoc_tiep_theo(b2, QualityMode.VAN_HOC)
            d1.append(b1)
            d2.append(b2)
        self.assertEqual(d1, d2)


class TachChuongTest(unittest.TestCase):
    def test_khong_co_tieu_de_thi_ca_van_ban_la_mot_chuong(self):
        self.assertEqual(tach_chuong("Một đoạn văn không có tiêu đề chương."),
                         ["Một đoạn văn không có tiêu đề chương."])

    def test_van_ban_rong_tra_danh_sach_rong(self):
        self.assertEqual(tach_chuong(""), [])
        self.assertEqual(tach_chuong("   "), [])

    def test_tach_theo_tieu_de_so_a_rap(self):
        vb = "第1章 mở đầu\n内容一。\n第2章 tiếp theo\n内容二。"
        ch = tach_chuong(vb)
        self.assertEqual(len(ch), 2)
        self.assertTrue(ch[0].startswith("第1章"))
        self.assertTrue(ch[1].startswith("第2章"))
        self.assertIn("内容一", ch[0])
        self.assertNotIn("内容二", ch[0])

    def test_tach_theo_tieu_de_chapter_tieng_anh(self):
        vb = "Chapter 1 Intro\nabc\nChapter 2 Next\nxyz"
        ch = tach_chuong(vb)
        self.assertEqual(len(ch), 2)

    def test_loi_mo_dau_ngan_truoc_chuong_dau_khong_mat_noi_dung(self):
        vb = "Lời tựa ngắn.\n第1章 mở đầu\n内容。"
        ch = tach_chuong(vb)
        self.assertEqual(len(ch), 2)
        self.assertIn("Lời tựa", ch[0])

    def test_khong_lam_mat_noi_dung(self):
        """Tong do dai cac chuong (sau strip) khong duoc mat ky tu giua bien."""
        vb = "第1章 A\ndòng một.\ndòng hai.\n第2章 B\ndòng ba."
        ch = tach_chuong(vb)
        toan_bo = "\n".join(ch)
        for doan in ("dòng một", "dòng hai", "dòng ba"):
            self.assertIn(doan, toan_bo)


class TachDoanTest(unittest.TestCase):
    def test_doan_ngan_khong_bi_chia(self):
        self.assertEqual(tach_doan_trong_chuong("Một câu ngắn.", 2000),
                         ["Một câu ngắn."])

    def test_doan_dai_duoc_chia_theo_gioi_han(self):
        vb = ("Đoạn một dài. " * 50) + "\n\n" + ("Đoạn hai dài. " * 50)
        ra = tach_doan_trong_chuong(vb, 300)
        self.assertGreater(len(ra), 1)
        self.assertTrue(all(len(p) <= 320 for p in ra))  # bien nho cho tu cuoi


class GlossaryTest(unittest.TestCase):
    def test_kiem_hop_le(self):
        goc, dich, note = kiem_glossary_entry(
            original="萧炎", translated="Tiêu Viêm", note="nhân vật chính")
        self.assertEqual((goc, dich, note), ("萧炎", "Tiêu Viêm", "nhân vật chính"))

    def test_thieu_tu_goc_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            kiem_glossary_entry(original="  ", translated="Ai đó")

    def test_thieu_ban_dich_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            kiem_glossary_entry(original="萧炎", translated="  ")

    def test_vuot_tran_do_dai_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            kiem_glossary_entry(original="x" * 81, translated="y")

    def test_ap_dung_khoa_ghi_de_de_xuat_cua_provider(self):
        de_xuat = {"萧炎": "Tiêu Diễm", "药老": "Dược Lão"}
        khoa = [GlossaryEntry(
            term_id="t1", project_id="p1", category=GlossaryCategory.CHARACTER,
            original="萧炎", translated="Tiêu Viêm", locked=True)]
        ra = ap_dung_khoa_glossary(de_xuat, khoa)
        self.assertEqual(ra["萧炎"], "Tiêu Viêm")  # bi de xuat cua provider
        self.assertEqual(ra["药老"], "Dược Lão")   # khong khoa -> giu de xuat

    def test_muc_chua_khoa_khong_ghi_de(self):
        de_xuat = {"萧炎": "Tiêu Diễm"}
        chua_khoa = [GlossaryEntry(
            term_id="t1", project_id="p1", category=GlossaryCategory.CHARACTER,
            original="萧炎", translated="Tiêu Viêm", locked=False)]
        ra = ap_dung_khoa_glossary(de_xuat, chua_khoa)
        self.assertEqual(ra["萧炎"], "Tiêu Diễm")


class UocLuongTest(unittest.TestCase):
    def test_van_ban_rong(self):
        u = uoc_luong("")
        self.assertEqual(u["characters"], 0)
        self.assertEqual(u["chapters"], 0)

    def test_dem_chuong_dung(self):
        vb = "第1章 A\nabc\n第2章 B\nxyz\n第3章 C\ndef"
        u = uoc_luong(vb)
        self.assertEqual(u["chapters"], 3)
        self.assertGreater(u["characters"], 0)
        self.assertGreater(u["estimated_tokens"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
