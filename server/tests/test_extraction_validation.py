import unittest

from server.scraper.universal.extraction_validation import (
    hashes_are_distinct,
    validate_extracted_content,
)

#: A real, substantial multi-sentence paragraph (200+ chars, several real
#: sentences) — used for the "passes with a high score" case.
_REAL_VI = (
    "Hoang suong khoi tinh giua dem khuya. Ngoi lang im lim trong bong toi, "
    "chi con tieng gio rung khe tren mai nha. Dong ho tren tuong dung lai o "
    "tam gio ba muoi lam. Ngoai song, mot chiec thuyen con lap lo nhung ngoi "
    "sao dau. Cuoc song binh yen tuong chuong se mai nhu vay."
)

_REAL_EN = (
    "The old lighthouse keeper climbed the winding stairs for the last time. "
    "Below him the harbor slept under a blanket of fog. Somewhere a bell "
    "tolled, low and mournful, across the silent water. The sea would miss "
    "his steady lamp."
)


def _nav_labels() -> str:
    label = "Trang chu, Gioi thieu, Lien he, Dang nhap, Dang ky, Tim kiem, "
    return label * 30  # length >> 200, but zero sentence-final punctuation


class ValidatePassesRealContentTest(unittest.TestCase):
    def test_real_vietnamese_paragraph_passes_high_score(self):
        res = validate_extracted_content(_REAL_VI)
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.score, 50.0)
        self.assertGreaterEqual(res.sentence_count, 4)
        self.assertNotIn(
            "khong tim thay cau van thuc su", res.reasons
        )

    def test_real_english_paragraph_passes_high_score(self):
        res = validate_extracted_content(_REAL_EN)
        self.assertTrue(res.passed)
        self.assertGreaterEqual(res.score, 50.0)


class ValidateLengthFloorTest(unittest.TestCase):
    def test_short_text_fails_regardless_of_other_qualities(self):
        res = validate_extracted_content("Doan van ngan. Khong du dai.")
        self.assertFalse(res.passed)
        self.assertLess(res.score, 50.0)
        self.assertTrue(any("toi thieu" in r for r in res.reasons))


class ValidateSentenceDensityTest(unittest.TestCase):
    def test_nav_label_wall_zero_sentences_fails(self):
        res = validate_extracted_content(_nav_labels())
        self.assertEqual(res.sentence_count, 0)
        self.assertFalse(res.passed)
        self.assertTrue(
            any("khong tim thay cau van thuc su" in r for r in res.reasons)
        )


class ValidateBoilerplateRatioTest(unittest.TestCase):
    def test_100_percent_known_boilerplate_drives_ratio_and_low_score(self):
        paragraph = (
            "Day la mot doan van dung lam boilerplate. No doc lai o moi "
            "trang. Vi vay ta danh dau no la boilerplate da biet."
        )
        known = {
            __import__(
                "server.scraper.universal.extraction_validation",
                fromlist=["_paragraph_hash"],
            )._paragraph_hash(paragraph)
        }
        res = validate_extracted_content(
            paragraph, min_length=200, known_content_hashes=known
        )
        self.assertAlmostEqual(res.boilerplate_ratio, 1.0, places=2)
        self.assertFalse(res.passed)
        self.assertTrue(
            any("boilerplate" in r for r in res.reasons)
        )


class ValidateTitleAgreementTest(unittest.TestCase):
    def test_title_present_scores_higher_than_title_absent(self):
        title = "Chuong Mot: Khu Rung Cu"
        body_with = (
            "Chuong Mot: Khu Rung Cu. Hoang dat chan len mot con duong mo "
            "chua tung ai biet. Gio thoi lot xot qua nhung than cay cao "
            "nghe. Anh nghe tieng gi do cu dong sau lung. Con duong dai can "
            "cuoi song nuoc. Noi nay khong the khong co bi mat."
        )
        body_without = (
            "Hoang dat chan len mot con duong mo chua tung ai biet. Gio thoi "
            "lot xot qua nhung than cay cao nghe. Anh nghe tieng gi do cu "
            "dong sau lung. Con duong dai can cuoi song nuoc. Noi nay khong "
            "the khong co bi mat."
        )
        res_with = validate_extracted_content(body_with, expected_title=title)
        res_without = validate_extracted_content(body_without, expected_title=title)
        self.assertGreater(res_with.score, res_without.score)


class ValidateHashTest(unittest.TestCase):
    def test_distinct_texts_distinct_hashes(self):
        a = validate_extracted_content(_REAL_EN)
        b = validate_extracted_content(
            "Hoan toan khac nhau. Mot van ban khong lien quan gi den van "
            "truoc. Noi dung nay hoan toan moi me. Vi vay ma hash phai khac."
        )
        self.assertTrue(hashes_are_distinct(a.content_hash, b.content_hash))
        self.assertNotEqual(a.content_hash, b.content_hash)

    def test_same_text_same_hash_deterministic(self):
        a = validate_extracted_content(_REAL_VI)
        b = validate_extracted_content(_REAL_VI)
        self.assertEqual(a.content_hash, b.content_hash)


class ValidateJunkPatternTest(unittest.TestCase):
    def test_repeated_placeholder_fails(self):
        res = validate_extracted_content("Loading... " * 50)
        self.assertFalse(res.passed)
        self.assertLess(res.score, 50.0)
        self.assertTrue(any("placeholder" in r for r in res.reasons))


class ValidateEmptyAndWhitespaceTest(unittest.TestCase):
    def test_empty_string_fails_cleanly(self):
        res = validate_extracted_content("")
        self.assertFalse(res.passed)
        self.assertLess(res.score, 50.0)
        self.assertTrue(any("toi thieu" in r for r in res.reasons))

    def test_whitespace_only_fails_cleanly(self):
        res = validate_extracted_content("   \n\t   ")
        self.assertFalse(res.passed)
        self.assertLess(res.score, 50.0)
        self.assertTrue(any("toi thieu" in r for r in res.reasons))


if __name__ == "__main__":
    unittest.main()
