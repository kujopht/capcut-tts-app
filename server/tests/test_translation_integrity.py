"""
`server/translation_integrity.py` — kiem tra tinh ven MOT doan dich, doc lap
voi provider/registry (V6 cerebras-groq-translation).

Tai lieu THAT: benchmark that voi Cerebras GPT-OSS 120B phat hien mot loi
that su tren doan hoi thoai nhieu nhan vat — de sot "到底是谁" chua dich va
bo mat mot phan noi dung. Cac test o day tai lap CHINH XAC mau do, cong voi
cac truong hop KHONG duoc phep bao loi gia (ten rieng Han Viet, dau cau vo
hai, van hoc gop 2 dong thanh 1 cau).
"""

from __future__ import annotations

import unittest

from server.translation_integrity import IntegrityIssue, kiem_tra_tinh_ven, tom_tat_van_de


def _ma(van_de):
    return {v.code for v in van_de}


class HanResidueTest(unittest.TestCase):
    def test_tai_lap_loi_that_tu_benchmark_den_biet_thu(self):
        """Mau CHINH XAC tu benchmark that (2026-08-15): Cerebras GPT-OSS
        120B de sot "到底是誰" (bien the phon chu cua "到底是谁") chua dich."""
        nguon = "\"你到底是谁？\"她厉声问道。\n\"我？\"他冷笑一声，\"你很快就会知道了。\""
        dich_loi = "“Ngươi到底是誰？” cô gắt hỏi.\n“Ta？” anh cười lạnh, “Cô sẽ sớm biết được.”"
        van_de = kiem_tra_tinh_ven(nguon, dich_loi)
        self.assertIn("han_residue", _ma(van_de))

    def test_ban_dich_dung_khong_bao_loi(self):
        nguon = "萧炎看向药老，微微皱眉，低声道：\"师父，这件事你早就知道了，对不对？\""
        dich = ("Tiêu Viêm nhìn về phía Dược Lão, nhíu mày nhẹ nhàng, thì thầm: "
               "\"Thưa sư phụ, ngài đã biết chuyện này từ lâu rồi, phải không?\"")
        self.assertEqual(kiem_tra_tinh_ven(nguon, dich), [])

    def test_ten_rieng_han_viet_khong_bi_coi_la_con_sot(self):
        """Ten rieng da Viet hoa (Tiêu Viêm, Dược Lão) la CHU VIET CO DAU,
        khong phai ky tu Han — khong duoc phep bi flag."""
        nguon = "萧炎和药老一起走进了迷雾之中。"
        dich = "Tiêu Viêm và Dược Lão cùng nhau bước vào trong màn sương mù."
        self.assertEqual(kiem_tra_tinh_ven(nguon, dich), [])

    def test_nguon_khong_co_chu_han_thi_khong_kich_hoat_rule_nay(self):
        """Pass editor/QA: dau vao DA la tieng Viet (khong co chu Han de
        'con sot') — rule han_residue khong duoc kich hoat du dau ra co ky
        tu la (khong nen xay ra, nhung an toan neu co)."""
        nguon = "Tiêu Viêm nhìn về phía Dược Lão."
        dich = "Tiêu Viêm nhìn về phía Dược Lão, khẽ gật đầu."
        self.assertEqual(kiem_tra_tinh_ven(nguon, dich), [])

    def test_dau_cau_cjk_khong_bi_coi_la_ky_tu_han(self):
        """Dau cau ("。", "，", "「」") KHONG nam trong pham vi ky tu Han —
        yeu cau goc: 'Do not reject harmless punctuation'."""
        nguon = "他说：「你好。」"
        dich = "Anh ta nói: \"Xin chào.\""
        self.assertEqual(kiem_tra_tinh_ven(nguon, dich), [])


class MissingDialogueTest(unittest.TestCase):
    def test_thieu_het_hoi_thoai(self):
        nguon = "\"你好吗？\"她问道。"
        dich = "Cô ấy hỏi thăm sức khỏe."
        self.assertIn("missing_dialogue", _ma(kiem_tra_tinh_ven(nguon, dich)))

    def test_giu_du_hoi_thoai_khong_bao_loi(self):
        nguon = "\"你好吗？\"她问道。"
        dich = "\"Cậu khỏe không?\" cô ấy hỏi."
        self.assertNotIn("missing_dialogue", _ma(kiem_tra_tinh_ven(nguon, dich)))


class ParagraphLossTest(unittest.TestCase):
    def test_mat_noi_dung_dang_ke(self):
        nguon = "第一句。\n第二句。\n第三句。\n第四句。"
        dich = "Một câu duy nhất."
        self.assertIn("paragraph_loss", _ma(kiem_tra_tinh_ven(nguon, dich)))

    def test_gop_hai_dong_thanh_mot_cau_van_hoc_khong_bao_loi(self):
        """Gop 2 dong nguon thanh 1 cau dich muot van la BINH THUONG, khong
        phai loi — yeu cau goc: 'Keep conservative enough to avoid false
        positives'."""
        nguon = "他站起身。\n转身离开了房间。"
        dich = "Hắn đứng dậy rồi quay người rời khỏi căn phòng."
        self.assertNotIn("paragraph_loss", _ma(kiem_tra_tinh_ven(nguon, dich)))

    def test_mot_dong_duy_nhat_khong_ap_dung_rule_nay(self):
        nguon = "他站起身。"
        dich = "Hắn đứng dậy."
        self.assertEqual(kiem_tra_tinh_ven(nguon, dich), [])


class TruncationTest(unittest.TestCase):
    def test_cat_cut_o_cuoi(self):
        nguon = "他缓缓地点了点头。"
        dich = "Anh từ từ gật đầu và nói rằng mọi chuyện sẽ"
        self.assertIn("truncated", _ma(kiem_tra_tinh_ven(nguon, dich)))

    def test_ket_thuc_tron_cau_khong_bao_loi(self):
        nguon = "他缓缓地点了点头。"
        dich = "Anh từ từ gật đầu."
        self.assertNotIn("truncated", _ma(kiem_tra_tinh_ven(nguon, dich)))

    def test_ket_thuc_bang_dau_ngoac_dong_khong_bao_loi(self):
        nguon = "他说：「好。」"
        dich = "Anh ta nói: \"Được.\""
        self.assertNotIn("truncated", _ma(kiem_tra_tinh_ven(nguon, dich)))


class GlossaryViolationTest(unittest.TestCase):
    """Yeu cau bo sung "terminology consistency" (sau phat hien "药老" dich
    khong nhat quan giua hai lan goi that: "Dược Lão" vs "Yêu Lão")."""

    def test_tai_lap_mau_that_duoc_lao_vs_yeu_lao(self):
        nguon = "萧炎看向药老，微微皱眉。"
        dich_sai = "Tiêu Viêm nhìn về phía Yêu Lão, khẽ nhíu mày."
        van_de = kiem_tra_tinh_ven(nguon, dich_sai, glossary={"药老": "Dược Lão"})
        self.assertIn("glossary_violation", _ma(van_de))

    def test_dung_thuat_ngu_da_chot_khong_bao_loi(self):
        nguon = "萧炎看向药老，微微皱眉。"
        dich_dung = "Tiêu Viêm nhìn về phía Dược Lão, khẽ nhíu mày."
        van_de = kiem_tra_tinh_ven(nguon, dich_dung, glossary={"药老": "Dược Lão"})
        self.assertNotIn("glossary_violation", _ma(van_de))

    def test_thuat_ngu_khong_xuat_hien_trong_doan_nay_thi_khong_kiem_tra(self):
        """Tu dien co the co CA du an (nhieu nhan vat), nhung CHI kiem tu
        NAO thuc su xuat hien trong doan dang xu ly — tranh canh bao gia
        cho nhung tu khong lien quan doan nay."""
        nguon = "他站起身，转身离开了房间。"
        dich = "Hắn đứng dậy rồi quay người rời khỏi căn phòng."
        van_de = kiem_tra_tinh_ven(nguon, dich, glossary={"药老": "Dược Lão"})
        self.assertNotIn("glossary_violation", _ma(van_de))

    def test_khong_glossary_thi_hanh_vi_cu_khong_doi(self):
        """`glossary=None` (mac dinh) — tuong thich nguoc hoan toan voi
        hanh vi truoc khi co yeu cau nay."""
        nguon = "萧炎看向药老。"
        dich = "Tiêu Viêm nhìn về phía Yêu Lão."
        self.assertEqual(kiem_tra_tinh_ven(nguon, dich), [])

    def test_hai_nhan_vat_khac_nhau_khong_bi_gop_nham(self):
        """Hai tu dien RIENG cho hai nhan vat KHAC nhau — vi pham cua nhan
        vat A khong duoc lam anh huong toi kiem tra cua nhan vat B."""
        glossary = {"药老": "Dược Lão", "萧炎": "Tiêu Viêm"}
        nguon = "萧炎和药老一起走进了迷雾之中。"
        # Chi "萧炎" dung, "药老" SAI ("Dược Sư" khong phai "Dược Lão").
        dich_mot_phan_sai = "Tiêu Viêm và Dược Sư cùng nhau bước vào sương mù."
        van_de = kiem_tra_tinh_ven(nguon, dich_mot_phan_sai, glossary=glossary)
        ma = _ma(van_de)
        self.assertIn("glossary_violation", ma)
        # Chi DUNG MOT vi pham (药老) — "萧炎"/"Tiêu Viêm" dung, khong bi
        # tinh gop nham thanh vi pham thu hai.
        so_vi_pham = sum(1 for v in van_de if v.code == "glossary_violation")
        self.assertEqual(so_vi_pham, 1)

    def test_ca_hai_nhan_vat_dung_khong_bao_loi(self):
        glossary = {"药老": "Dược Lão", "萧炎": "Tiêu Viêm"}
        nguon = "萧炎和药老一起走进了迷雾之中。"
        dich_dung = "Tiêu Viêm và Dược Lão cùng nhau bước vào trong màn sương mù."
        van_de = kiem_tra_tinh_ven(nguon, dich_dung, glossary=glossary)
        self.assertNotIn("glossary_violation", _ma(van_de))


class EmptyOutputTest(unittest.TestCase):
    def test_dich_rong(self):
        van_de = kiem_tra_tinh_ven("你好。", "")
        self.assertEqual(_ma(van_de), {"empty"})

    def test_dich_chi_co_khoang_trang(self):
        van_de = kiem_tra_tinh_ven("你好。", "   \n  ")
        self.assertEqual(_ma(van_de), {"empty"})


class TomTatVanDeTest(unittest.TestCase):
    def test_gop_nhieu_van_de_thanh_mot_chuoi(self):
        van_de = [IntegrityIssue("a", "Lỗi A."), IntegrityIssue("b", "Lỗi B.")]
        self.assertEqual(tom_tat_van_de(van_de), "Lỗi A.; Lỗi B.")

    def test_danh_sach_rong_ra_chuoi_rong(self):
        self.assertEqual(tom_tat_van_de([]), "")


if __name__ == "__main__":
    unittest.main()
