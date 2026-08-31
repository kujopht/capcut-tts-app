"""
Test cho `server/translation_domain.py`'s phan METRICS moi (mission "Hy-MT2
1.8B translation production readiness") + rao chan provider-trung-lap that
(AST, cung ky thuat voi `server/tests/test_character_identity.py`).

Cac mau van ban tieng Anh phong-cach-fanfic dung trong file nay LA DU LIEU
CUC BO/GIA LAP CHO TEST — KHONG BAO GIO goi mang that, KHONG BAO GIO chay
qua mot model that (xem yeu cau goc muc 7: "for LOCAL/MOCKED testing only").
Chung duoc chon de bao phu: hoi thoai day dac, mot nhan vat co danh xung/
ten rieng, mot thanh ngu/cach noi dac thu van hoa, va mot doan dai gan
nguong ngu canh — bon dac diem thuong lam lo ro chat luong dich THAT (khac
voi mot cau tieng Anh trung tinh, don gian).
"""

from __future__ import annotations

import ast
import inspect
import unittest

from server import translation_domain
from server.translation_domain import (
    TranslationRunMetrics,
    _hash_text,
    build_translation_run_metrics,
    detect_source_language,
)

# =============================================================================
# Mau van ban fanfic-oriented — CUC BO, TU VIET (khong scrape, khong ban
# quyen), CHI dung cho test/benchmark cuc bo (xem docstring dau file).
# =============================================================================

#: Hoi thoai day dac — nhieu luot noi qua lai, it van xuoi mieu ta xen giua.
SAMPLE_DIALOGUE_HEAVY = """\
"You're bleeding," Mei said.
"I'm fine."
"You are NOT fine, Kaito."
"It's just a scratch."
"That is not a scratch, that is half your sleeve."
"...Okay, maybe it's a little more than a scratch."
"""

#: Nhan vat co ten rieng + danh xung/title — kiem tra dich co GIU NGUYEN
#: ten rieng va xu ly danh xung nhat quan hay khong (khong bi dich nghia
#: "Sword-sensei" thanh mot cai ten khac, khong bi bo danh xung).
SAMPLE_NAMED_CHARACTER_WITH_HONORIFIC = """\
Sensei Kaito raised the Ashfall Blade over his shoulder. The first-years \
called him "Blade-sensei" behind his back, half in fear and half in awe, \
though he always pretended not to hear it.
"""

#: Thanh ngu/cach noi dac thu van hoa — phep thu THAT ve chat luong dich
#: (nghia bong, khong phai dich tung chu).
SAMPLE_IDIOM = """\
Mei had always worn her heart on her sleeve, so when she finally kept a \
secret from him, Kaito knew something was seriously wrong.
"""

#: Doan dai hon, gan nguong ngu canh thuc te (xem
#: `beam_apps/translation_hymt2_app.py`'s `max_model_len=8192` — doan nay
#: van RAT nho so voi con so do, chi du de dai hon mot doan chunk thong
#: thuong (`DOAN_KY_TU_MOI_LAN_GOI=2000` trong translation_service.py) de
#: kiem tra hanh vi khong bi cat cut som o cap van ban, khong phai de mo
#: phong toan bo 8192 token that).
SAMPLE_LONGER_PASSAGE = ("Kaito had never liked the sound of rain against a "
    "dormitory window, but tonight it felt almost deliberate. " * 40)


class DetectSourceLanguageOnFanficSamplesTest(unittest.TestCase):
    """`detect_source_language` phai nhan dung tieng Anh tren CA BON mau —
    ne kiem thu that (khong doan), khong phai chi tren mot cau ngan don
    gian nhu cac test hien co."""

    def test_all_samples_detected_as_english(self):
        for label, sample in (
            ("dialogue_heavy", SAMPLE_DIALOGUE_HEAVY),
            ("named_character_with_honorific", SAMPLE_NAMED_CHARACTER_WITH_HONORIFIC),
            ("idiom", SAMPLE_IDIOM),
            ("longer_passage", SAMPLE_LONGER_PASSAGE),
        ):
            with self.subTest(label=label):
                self.assertEqual(detect_source_language(sample), "en")


class BuildTranslationRunMetricsTest(unittest.TestCase):
    def test_basic_fields_computed_correctly(self):
        #: Xap xi cung do dai voi nguon (khong phai mot ban dich RUT GON
        #: dang ke) - de test nay chi kiem tra cac TRUONG duoc tinh dung,
        #: khong vo tinh cham vao nguong `possibly_truncated` (co test rieng
        #: cho nguong do o duoi).
        translated = ("Bản dịch tiếng Việt đầy đủ, không bị cắt cụt, có độ "
                      "dài xấp xỉ với văn bản nguồn nhiều dòng hội thoại ở "
                      "trên, không rút gọn nội dung nào cả, giữ nguyên đầy "
                      "đủ từng câu thoại một cách trung thực và tự nhiên.")
        metrics = build_translation_run_metrics(
            source_text=SAMPLE_DIALOGUE_HEAVY, translated_text=translated,
            source_language="en", target_language="vi",
            model_id="tencent/Hy-MT2-1.8B", wall_seconds=2.5,
        )
        self.assertIsInstance(metrics, TranslationRunMetrics)
        self.assertEqual(metrics.source_chars, len(SAMPLE_DIALOGUE_HEAVY))
        self.assertEqual(metrics.translated_chars, len(translated))
        self.assertEqual(metrics.source_text_hash, _hash_text(SAMPLE_DIALOGUE_HEAVY))
        self.assertEqual(metrics.translated_content_hash, _hash_text(translated))
        self.assertFalse(metrics.possibly_truncated)

    def test_hash_is_deterministic_across_calls(self):
        m1 = build_translation_run_metrics(
            source_text=SAMPLE_IDIOM, translated_text="một bản dịch",
            source_language="en", target_language="vi", model_id="m")
        m2 = build_translation_run_metrics(
            source_text=SAMPLE_IDIOM, translated_text="một bản dịch khác",
            source_language="en", target_language="vi", model_id="m")
        self.assertEqual(m1.source_text_hash, m2.source_text_hash)
        self.assertNotEqual(m1.translated_content_hash, m2.translated_content_hash)

    def test_short_output_flagged_possibly_truncated(self):
        """Ban dich RONG so voi mot nguon dai — tin hieu that ve cat cut,
        dung nguong `TRUNCATION_LENGTH_RATIO_THRESHOLD`."""
        metrics = build_translation_run_metrics(
            source_text=SAMPLE_LONGER_PASSAGE, translated_text="Ừ.",
            source_language="en", target_language="vi", model_id="m")
        self.assertTrue(metrics.possibly_truncated)

    def test_empty_source_and_empty_output_not_truncated(self):
        """Nguon rong -> khong co gi de dich -> KHONG phai loi cat cut."""
        metrics = build_translation_run_metrics(
            source_text="", translated_text="",
            source_language="unknown", target_language="vi", model_id="m")
        self.assertFalse(metrics.possibly_truncated)

    def test_reasonable_length_output_not_flagged(self):
        sentence = ("Đây là một câu dịch tiếng Việt có độ dài hợp lý, không "
                    "hề bị cắt cụt hay bỏ sót nội dung nào so với câu nguồn. ")
        #: Lap CUNG so lan voi SAMPLE_LONGER_PASSAGE (x40) de do dai ban
        #: dich XAP XI do dai nguon - ro rang tren nguong, khong phai mot
        #: ban dich rut gon.
        metrics = build_translation_run_metrics(
            source_text=SAMPLE_LONGER_PASSAGE, translated_text=sentence * 40,
            source_language="en", target_language="vi", model_id="m")
        self.assertFalse(metrics.possibly_truncated)

    def test_tokens_optional_default_none(self):
        metrics = build_translation_run_metrics(
            source_text="hi", translated_text="chào",
            source_language="en", target_language="vi", model_id="m")
        self.assertIsNone(metrics.source_tokens)
        self.assertIsNone(metrics.translated_tokens)

    def test_tokens_recorded_when_provided(self):
        metrics = build_translation_run_metrics(
            source_text="hi", translated_text="chào",
            source_language="en", target_language="vi", model_id="m",
            source_tokens=12, translated_tokens=8)
        self.assertEqual(metrics.source_tokens, 12)
        self.assertEqual(metrics.translated_tokens, 8)

    def test_chars_per_second_none_without_wall_time(self):
        metrics = build_translation_run_metrics(
            source_text="hi", translated_text="chào xin chào",
            source_language="en", target_language="vi", model_id="m")
        self.assertIsNone(metrics.chars_per_second())

    def test_chars_per_second_computed_when_wall_time_given(self):
        metrics = build_translation_run_metrics(
            source_text="hi", translated_text="chào xin chào bạn nhé hôm nay",
            source_language="en", target_language="vi", model_id="m",
            wall_seconds=2.0)
        expected = len("chào xin chào bạn nhé hôm nay") / 2.0
        self.assertAlmostEqual(metrics.chars_per_second(), expected)

    def test_to_dict_shape(self):
        metrics = build_translation_run_metrics(
            source_text="hi", translated_text="chào",
            source_language="en", target_language="vi",
            model_id="tencent/Hy-MT2-1.8B", wall_seconds=1.0,
            model_load_seconds=3.2, inference_seconds=0.8,
            source_tokens=5, translated_tokens=4)
        d = metrics.to_dict()
        self.assertEqual(d["model_id"], "tencent/Hy-MT2-1.8B")
        self.assertEqual(d["source_language"], "en")
        self.assertEqual(d["target_language"], "vi")
        self.assertEqual(d["model_load_seconds"], 3.2)
        self.assertEqual(d["inference_seconds"], 0.8)
        self.assertEqual(d["source_tokens"], 5)
        self.assertEqual(d["translated_tokens"], 4)
        self.assertIn("chars_per_second", d)
        self.assertIn("possibly_truncated", d)


class TestTranslationDomainModuleIsProviderNeutral(unittest.TestCase):
    """`server/translation_domain.py` phuc vu CA desktop lan web, va gio
    them `TranslationRunMetrics`/`build_translation_run_metrics` cho benchmark
    Beam — module nay PHAI khong bao gio import beam/torch/diffusers/vllm,
    kiem tra THAT bang AST (cung ky thuat voi
    `server/tests/test_character_identity.py`), khong chi doc docstring."""

    _FORBIDDEN_MODULES = {"beam", "torch", "diffusers", "vllm", "PIL"}

    def test_no_provider_specific_top_level_imports(self):
        source = inspect.getsource(translation_domain)
        tree = ast.parse(source)
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_roots.add(node.module.split(".")[0])
        forbidden_found = imported_roots & self._FORBIDDEN_MODULES
        self.assertEqual(
            forbidden_found, set(),
            f"server/translation_domain.py imports provider-specific "
            f"module(s) {forbidden_found} - this module must stay "
            f"provider-neutral (metadata only).")


if __name__ == "__main__":
    unittest.main()
