"""
Tests for Full Chapter Long-Text Vietnamese Translator.
"""

import unittest
from scripts.content_factory.full_chapter_translator import (
    chunk_chapter_paragraphs,
    detect_translation_defect,
    clean_model_prefixes,
    count_words,
)


class TestFullChapterTranslator(unittest.TestCase):

    def test_chunking_preserves_paragraphs_and_scene_breaks(self):
        source = (
            "Paragraph one describing Dante awakening in the world of Naruto.\n\n"
            "Paragraph two delving into the physical properties of chakra.\n\n"
            "---\n\n"
            "Paragraph three after the scene break, Sakumo enters the room.\n\n"
            "Paragraph four concluding the morning scene."
        )
        chunks = chunk_chapter_paragraphs(source, max_chunk_words=100, min_chunk_words=10)
        self.assertGreaterEqual(len(chunks), 1)

        # Reconstructed text preserves all content
        reconstructed = "\n\n".join(c["text"] for c in chunks)
        self.assertIn("---", reconstructed)
        self.assertIn("Dante awakening", reconstructed)
        self.assertIn("Sakumo enters", reconstructed)

    def test_chunking_large_paragraphs(self):
        # 300-word paragraph
        large_para = " ".join([f"Sentence number {i} explains ninja engineering." for i in range(50)])
        chunks = chunk_chapter_paragraphs(large_para, max_chunk_words=40, min_chunk_words=10)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(c["word_count"], 55)

    def test_detect_translation_defect(self):
        src = "This is a substantial paragraph of text describing tactical maneuvers in the Leaf Village." * 5
        src_words = count_words(src)

        # 1. Blank output
        self.assertIsNotNone(detect_translation_defect(src, ""))
        self.assertIn("BLANK_OUTPUT", detect_translation_defect(src, ""))

        # 2. Extreme shortage / low ratio
        short_vi = "Dante tỉnh dậy ở Làng Lá."
        defect = detect_translation_defect(src, short_vi)
        self.assertIsNotNone(defect)
        self.assertTrue("EXTREME_SHORTAGE" in defect or "SUSPICIOUS_TRUNCATION" in defect)

        # 3. Cutoff ending
        cutoff_vi = ("Dante nhìn thấy Sakumo đang mài thanh đoản đao chakra ánh trắng quen thuộc, "
                     "tiếng kim loại cọ xát phát ra thanh âm vô cùng êm tai nhưng đột nhiên hắn thấy")
        defect_cutoff = detect_translation_defect(src, cutoff_vi)
        self.assertIsNotNone(defect_cutoff)
        self.assertIn("CUTOFF_DETECTED", defect_cutoff)

        # 4. Accidental summarization marker
        summary_vi = ("Tóm tắt nội dung: Dante là một kỹ sư vật liệu chuyển sinh vào gia tộc Hatake, "
                      "cùng cha Sakumo và em trai Kakashi trải qua những ngày tháng rèn luyện gian khổ.")
        defect_sum = detect_translation_defect(src, summary_vi)
        self.assertIsNotNone(defect_sum)
        self.assertIn("ACCIDENTAL_SUMMARIZATION", defect_sum)

        # 5. Valid translation with terminal punctuation and good word count
        good_vi = ("Dante thức dậy vào sáng sớm và cảm thấy cơ bắp toàn thân đau nhức sau buổi huấn luyện khắc nghiệt. "
                   "Cậu ngồi xuống thiền định, cảm nhận dòng chakra chạy dọc theo kinh mạch như một dòng chất lỏng phi Newton. "
                   "Sakumo bước vào phòng khách, trên tay cầm thanh đoản đao chakra ánh trắng lấp lánh dưới ánh nắng ban mai. "
                   "Kakashi cũng vừa trở về sau buổi rèn luyện kiếm thuật ngoài sân.") * 2
        self.assertIsNone(detect_translation_defect(src, good_vi))

    def test_clean_model_prefixes(self):
        raw_1 = "**Bản dịch:**\n\n> Đây là nội dung đã được dịch hoàn chỉnh."
        self.assertEqual(clean_model_prefixes(raw_1), "Đây là nội dung đã được dịch hoàn chỉnh.")

        raw_2 = "```markdown\nBản dịch tiếng Việt:\nĐây là nội dung chương 1.\n```"
        self.assertEqual(clean_model_prefixes(raw_2), "Đây là nội dung chương 1.")

        raw_3 = "**Đây là đoạn văn bản được bôi đậm.**"
        self.assertEqual(clean_model_prefixes(raw_3), "Đây là đoạn văn bản được bôi đậm.")


if __name__ == "__main__":
    unittest.main()
