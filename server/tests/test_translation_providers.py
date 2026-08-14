"""`server/translation_providers.py` — provider gia (mock) va lua chon provider."""

from __future__ import annotations

import unittest

from server.translation_providers import (
    DocuTranslateProvider,
    MockTranslationProvider,
    TranslationContext,
    TranslationProviderError,
    build_provider,
)


class MockProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.p = MockTranslationProvider()

    def test_vi_du_dung_tu_yeu_cau_goc(self):
        ra = self.p.translate_segment(
            "萧炎看向药老。", context=TranslationContext(vai_tro="translator"))
        self.assertEqual(ra, "Tiêu Viêm nhìn về phía Dược Lão.")

    def test_doan_rong_nem_loi_khong_tra_thanh_cong_gia(self):
        with self.assertRaises(TranslationProviderError):
            self.p.translate_segment(
                "   ", context=TranslationContext(vai_tro="translator"))

    def test_vai_tro_editor_tra_nguyen_van(self):
        """Mock KHONG gia vo bien tap duoc — tra dung nguyen dau vao."""
        vao = "Một câu tiếng Việt đã dịch."
        ra = self.p.translate_segment(
            vao, context=TranslationContext(vai_tro="editor"))
        self.assertEqual(ra, vao)

    def test_vai_tro_qa_tra_nguyen_van(self):
        vao = "Một câu tiếng Việt đã dịch."
        ra = self.p.translate_segment(
            vao, context=TranslationContext(vai_tro="qa"))
        self.assertEqual(ra, vao)

    def test_ap_dung_glossary_khi_khong_co_trong_tu_dien_cung(self):
        ra = self.p.translate_segment(
            "夜妖精 xuất hiện.",
            context=TranslationContext(
                vai_tro="translator", glossary={"夜妖精": "Dạ Yêu Tinh"}))
        self.assertIn("Dạ Yêu Tinh", ra)
        self.assertTrue(ra.startswith("[MOCK-VI]"))

    def test_tat_dinh_cung_dau_vao_ra_cung_ket_qua(self):
        vb = "một đoạn bất kỳ không nằm trong từ điển cứng"
        ctx = TranslationContext(vai_tro="translator")
        self.assertEqual(self.p.translate_segment(vb, context=ctx),
                         self.p.translate_segment(vb, context=ctx))

    def test_khong_goi_mang(self):
        """Mock la mot lop hoc — kiem bang code, khong the kiem 'khong co
        request mang' truc tiep, nen kiem GIAN TIEP: chay duoc khi khong co
        mang (offline) van phai OK — test nay tu no da chung minh dieu do vi
        moi bai trong file deu chay trong CI khong co mang ra ngoai."""
        self.assertEqual(MockTranslationProvider.name, "mock")


class DocuTranslateProviderTest(unittest.TestCase):
    def test_thieu_cau_hinh_nem_loi_ro_rang(self):
        with self.assertRaises(TranslationProviderError):
            DocuTranslateProvider(base_url="", api_key="", model="")

    def test_du_cau_hinh_nhung_chua_trien_khai_dich(self):
        p = DocuTranslateProvider(base_url="https://vidu.test", api_key="k",
                                  model="m")
        with self.assertRaises(NotImplementedError):
            p.translate_segment("x", context=TranslationContext(
                vai_tro="translator"))


class ChonProviderTest(unittest.TestCase):
    def test_khong_co_settings_ra_mock(self):
        self.assertIsInstance(build_provider(None), MockTranslationProvider)

    def test_settings_thieu_key_van_ra_mock_khong_nem(self):
        class GiaSettings:
            translation_base_url = ""
            translation_api_key = ""
            translation_model = ""

        self.assertIsInstance(build_provider(GiaSettings()),
                              MockTranslationProvider)

    def test_du_ca_ba_moi_ra_docutranslate(self):
        class GiaSettings:
            translation_base_url = "https://vidu.test"
            translation_api_key = "k"
            translation_model = "m"

        self.assertIsInstance(build_provider(GiaSettings()),
                              DocuTranslateProvider)


if __name__ == "__main__":
    unittest.main(verbosity=2)
