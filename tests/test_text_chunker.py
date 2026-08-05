"""Test chia van ban dai: khong cat giua tu, uu tien ranh gioi doan/cau."""

from __future__ import annotations

import unittest

from desktop_app.models import DEFAULT_CHUNK_CHARS, MAX_CHUNK_CHARS, MIN_CHUNK_CHARS
from desktop_app.text_chunker import chunk_text, estimate_part_count, normalize_chunk_size


class TestChunkBasics(unittest.TestCase):
    def test_empty_text(self) -> None:
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   \n\n "), [])
        self.assertEqual(chunk_text(None), [])

    def test_short_text_single_part(self) -> None:
        text = "Xin chào bạn."
        self.assertEqual(chunk_text(text, 2000), [text])
        self.assertEqual(estimate_part_count(text, 2000), 1)

    def test_default_limit_is_2000(self) -> None:
        self.assertEqual(DEFAULT_CHUNK_CHARS, 2000)
        self.assertEqual(normalize_chunk_size(None), 2000)

    def test_normalize_clamps(self) -> None:
        self.assertEqual(normalize_chunk_size(10), MIN_CHUNK_CHARS)
        self.assertEqual(normalize_chunk_size(999999), MAX_CHUNK_CHARS)
        self.assertEqual(normalize_chunk_size("khong phai so"), DEFAULT_CHUNK_CHARS)
        self.assertEqual(normalize_chunk_size(1234), 1234)


class TestChunkBoundaries(unittest.TestCase):
    def test_every_chunk_within_limit(self) -> None:
        text = " ".join(f"Câu số {i} nói về một điều gì đó khá dài dòng." for i in range(400))
        for limit in (200, 500, 1000, 2000):
            chunks = chunk_text(text, limit)
            self.assertTrue(chunks)
            for chunk in chunks:
                self.assertLessEqual(len(chunk), limit, f"limit={limit}")

    def test_never_splits_inside_a_word(self) -> None:
        """Ghep lai cac chunk phai cho ra dung tap tu ban dau."""
        text = " ".join(f"từ{i}" for i in range(500))
        chunks = chunk_text(text, 300)
        self.assertGreater(len(chunks), 1)
        rejoined = " ".join(chunks).split()
        self.assertEqual(rejoined, text.split())

    def test_prefers_paragraph_boundary(self) -> None:
        para_a = "A" * 400
        para_b = "B" * 400
        chunks = chunk_text(f"{para_a}\n\n{para_b}", 500)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], para_a)
        self.assertEqual(chunks[1], para_b)

    def test_merges_small_paragraphs(self) -> None:
        text = "\n\n".join(["Đoạn ngắn."] * 10)
        chunks = chunk_text(text, 2000)
        self.assertEqual(len(chunks), 1)

    def test_splits_long_paragraph_at_sentence(self) -> None:
        sentence = "Đây là một câu tiếng Việt hoàn chỉnh có dấu chấm. "
        chunks = chunk_text(sentence * 40, 400)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks[:-1]:
            self.assertTrue(
                chunk.rstrip().endswith("."),
                f"Chunk phải kết thúc ở ranh giới câu: ...{chunk[-40:]!r}",
            )

    def test_splits_at_vietnamese_ellipsis_and_question(self) -> None:
        text = ("Anh có nghe thấy không? " * 20) + ("Ừ, đã muộn rồi… " * 20)
        chunks = chunk_text(text, 300)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks[:-1]:
            self.assertTrue(chunk.rstrip()[-1] in "?….")

    def test_falls_back_to_clause_boundary(self) -> None:
        text = ", ".join(["mệnh đề khá dài không có dấu chấm nào cả"] * 30)
        chunks = chunk_text(text, 300)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 300)

    def test_single_huge_word_is_hard_split(self) -> None:
        """Truong hop bat buoc: mot 'tu' dai hon gioi han."""
        text = "x" * 1000
        chunks = chunk_text(text, 300)
        self.assertEqual(len(chunks), 4)
        self.assertEqual("".join(chunks), text)

    def test_no_empty_chunks(self) -> None:
        text = "Đoạn một.\n\n\n\n\nĐoạn hai.\n\n\n" + ("dài " * 500)
        for chunk in chunk_text(text, 250):
            self.assertTrue(chunk.strip())

    def test_content_preserved_ignoring_whitespace(self) -> None:
        """
        Ghep cac chunk lai (bang dau cach) phai cho ra dung tap tu ban dau:
        khong mat tu, khong them tu, khong cat giua tu.
        Khoang trang o ranh gioi chunk co the bi lược — moi chunk la mot request
        rieng nen dieu do khong anh huong ket qua doc.
        """
        text = "\n\n".join(f"Đoạn {i}: " + ("nội dung tiếng Việt " * 30) for i in range(10))
        chunks = chunk_text(text, 400)
        self.assertEqual(
            " ".join(chunks).split(),
            text.split(),
            "Không được mất hay thêm từ khi chia",
        )

    def test_vietnamese_diacritics_intact(self) -> None:
        text = ("Đường về nhà thật xa xôi và mưa rơi rất nhiều. " * 60)
        for chunk in chunk_text(text, 300):
            self.assertNotIn("�", chunk)
        self.assertIn("Đường", chunk_text(text, 300)[0])

    def test_crlf_input(self) -> None:
        text = "Dòng 1\r\n\r\nDòng 2"
        chunks = chunk_text(text, 2000)
        self.assertEqual(len(chunks), 1)
        self.assertNotIn("\r", chunks[0])

    def test_estimate_matches_chunk_count(self) -> None:
        text = "Câu tiếng Việt khá dài. " * 300
        for limit in (200, 700, 2000):
            self.assertEqual(estimate_part_count(text, limit), len(chunk_text(text, limit)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
