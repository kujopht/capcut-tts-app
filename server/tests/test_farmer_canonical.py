"""Bo cuc kho san xuat chinh tac + dinh danh tat dinh.

Bat bien trung tam, va ly do ca module `canonical.py` ton tai:

    **Mot lan THU LAI khong duoc de ra mot thu muc thu hai.**

Gemini chuan hoa sieu du lieu, va sieu du lieu do CO THE doi giua hai lan
danh gia ("Lều chõng" / "Leu Chong" / "Lều Chõng (bản đầy đủ)"). Neu ten thu
muc bam vao tieu de, mot lan thu lai se tao ban trung — dung dieu khu trung
lap ton tai de ngan. Nen ten duoc dan ra tu DANH TINH NGUON, khong tu tieu de.
"""
from __future__ import annotations

import unittest

from server.farmer import canonical as c


class RetryStabilityTest(unittest.TestCase):
    """Bat bien quan trong nhat."""

    def test_a_changed_title_does_not_change_the_directory(self):
        url = "https://vi.wikisource.org/wiki/Leu_chong"
        d1 = c.canonical_dir(c.BUCKET_FANFIC_TTS, url)
        d2 = c.canonical_dir(c.BUCKET_FANFIC_TTS, url)
        self.assertEqual(d1, d2)
        # Va khong mot ham nao o day nhan tieu de lam tham so — kiem bang
        # chinh chu ky, de mot ban sua sau nay khong len duoc tieu de vao.
        import inspect
        for ten in ("work_id", "canonical_dir", "source_slug"):
            tham_so = inspect.signature(getattr(c, ten)).parameters
            self.assertNotIn("title", tham_so, f"{ten} khong duoc nhan tieu de")

    def test_url_noise_resolves_to_the_same_work(self):
        goc = c.work_id(c.BUCKET_FANFIC_TTS, "https://e.com/story/1")
        for bien_the in ("https://e.com/story/1/",
                         "https://e.com/story/1?utm_source=fb",
                         "https://E.com/story/1"):
            with self.subTest(url=bien_the):
                self.assertEqual(c.work_id(c.BUCKET_FANFIC_TTS, bien_the), goc)

    def test_different_buckets_are_different_works(self):
        self.assertNotEqual(
            c.work_id(c.BUCKET_FANFIC_TTS, "https://e.com/a"),
            c.work_id(c.BUCKET_EXISTING_AUDIO, "https://e.com/a"))

    def test_empty_url_is_refused(self):
        with self.assertRaises(ValueError):
            c.work_id(c.BUCKET_FANFIC_TTS, "")

    def test_unknown_bucket_is_refused(self):
        with self.assertRaises(ValueError):
            c.work_id("works/khong-co", "https://e.com/a")


class SlugTest(unittest.TestCase):
    def test_slug_is_ascii_and_path_safe(self):
        for raw in ("Lều chõng", "Naruto: A Shinobi Story!", "重生官海",
                    "../../etc/passwd", "a/b\\c", "   "):
            with self.subTest(raw=raw):
                s = c.slugify(raw)
                self.assertRegex(s, r"^[a-z0-9-]+$")
                self.assertNotIn("..", s)
                self.assertNotIn("/", s)

    def test_slug_never_empty(self):
        """Chuoi rong se lam hai tac pham khac nhau cham vao cung duong dan."""
        for raw in ("", "   ", "重生", "!!!"):
            with self.subTest(raw=raw):
                self.assertTrue(c.slugify(raw))

    def test_source_slug_comes_from_the_url_not_a_title(self):
        s = c.source_slug("https://vi.wikisource.org/wiki/Leu_chong")
        self.assertIn("leu", s)


class LayoutTest(unittest.TestCase):
    def test_new_output_never_lands_in_the_legacy_archive(self):
        """`FanficWorld/archive/` la LEGACY va phai duoc de yen."""
        duong = c.canonical_dir(c.BUCKET_FANFIC_TTS, "https://e.com/a")
        self.assertTrue(duong.startswith("FanficWorld/production/"))
        self.assertNotIn("FanficWorld/archive", duong)

    def test_bucket_is_chosen_by_lane_not_by_model_output(self):
        """`content_type` cua model la chuoi tu do — no khong duoc phep quyet
        dinh mot duong dan."""
        self.assertEqual(c.bucket_for_lane("text"), c.BUCKET_FANFIC_TTS)
        self.assertEqual(c.bucket_for_lane("audio"), c.BUCKET_EXISTING_AUDIO)
        self.assertEqual(c.bucket_for_lane("audio", chinese_media=True),
                         c.BUCKET_CHINESE_MEDIA)

    def test_artifact_names_are_standard(self):
        url = "https://e.com/a"
        p = c.artifact_path(c.BUCKET_FANFIC_TTS, url, c.ARTIFACT_AUDIO_VI)
        self.assertTrue(p.endswith("/audio/vi.mp3"))
        self.assertEqual(c.ARTIFACT_MANIFEST, "manifest.json")
        self.assertEqual(c.ARTIFACT_SUBTITLE_VI, "subtitles/vi.srt")

    def test_holding_dirs_are_deterministic_too(self):
        url = "https://e.com/a"
        a = c.holding_dir(c.DECISION_QUARANTINE, c.BUCKET_FANFIC_TTS, url)
        b = c.holding_dir(c.DECISION_QUARANTINE, c.BUCKET_FANFIC_TTS, url)
        self.assertEqual(a, b)
        self.assertIn("/quarantine/", a)
        self.assertIn("/rejected/",
                      c.holding_dir(c.DECISION_REJECT, c.BUCKET_FANFIC_TTS, url))


def _manifest(**over) -> c.WorkManifest:
    base = dict(work_id="w_1", bucket=c.BUCKET_FANFIC_TTS,
                canonical_dir="FanficWorld/production/works/fanfic-tts/a-w_1",
                decision=c.DECISION_APPROVE)
    base.update(over)
    return c.WorkManifest(**base)


class ArtworkGateTest(unittest.TestCase):
    def test_no_artwork_means_not_publishable(self):
        m = _manifest()
        self.assertFalse(m.publishable())
        self.assertEqual(sorted(m.missing_required_artwork()),
                         sorted(list(c.REQUIRED_ARTWORK)))

    def test_cover_alone_is_not_enough(self):
        m = _manifest(artifacts={c.ARTIFACT_COVER: "ok"})
        self.assertFalse(m.publishable())
        self.assertEqual(m.missing_required_artwork(), [c.ARTIFACT_BACKGROUND])

    def test_both_artworks_plus_approval_is_publishable(self):
        m = _manifest(artifacts={c.ARTIFACT_COVER: "a", c.ARTIFACT_BACKGROUND: "b"})
        self.assertTrue(m.publishable())

    def test_artwork_without_approval_is_still_not_publishable(self):
        m = _manifest(decision=c.DECISION_QUARANTINE,
                      artifacts={c.ARTIFACT_COVER: "a", c.ARTIFACT_BACKGROUND: "b"})
        self.assertFalse(m.publishable())


class ManifestTest(unittest.TestCase):
    def test_originals_survive_normalization(self):
        """Chuan hoa khong duoc lam mat ban goc — neu phep chuan hoa doi, ta
        con doi chieu duoc."""
        m = _manifest(
            source_url="https://e.com/a?utm_source=x",
            source_title="Tieu de GOC (raw)",
            source_provider_id="ffn:12345",
            source_hashes={"sha256": "abc"},
            source_metadata_raw={"kenh": "abc", "views": 10},
            canonical_title="Tieu de da chuan hoa")
        d = m.as_dict()
        self.assertEqual(d["source"]["title"], "Tieu de GOC (raw)")
        self.assertEqual(d["source"]["url"], "https://e.com/a?utm_source=x")
        self.assertEqual(d["source"]["provider_id"], "ffn:12345")
        self.assertEqual(d["source"]["hashes"]["sha256"], "abc")
        self.assertEqual(d["source"]["metadata_raw"]["views"], 10)
        self.assertEqual(d["normalized"]["canonical_title"], "Tieu de da chuan hoa")

    def test_manifest_exposes_what_control_center_needs(self):
        d = _manifest(canonical_title="T", archive_state="ARCHIVE_PENDING",
                      archive_path="fanfic-gdrive:...").as_dict()
        for khoa in ("work_id", "decision", "canonical_dir"):
            self.assertIn(khoa, d)
        self.assertEqual(d["archive"]["state"], "ARCHIVE_PENDING")


class ReviewDecisionTest(unittest.TestCase):
    def test_low_score_approve_becomes_quarantine_not_reject(self):
        """Model thay dung duoc, chi la diem khong dat nguong tu dong — do la
        viec cho mot nguoi xem lai, khong phai viec de vut di."""
        from server.farmer.review import QualityReviewer
        from server.llm_gateway.provider import LLMCompletion

        class P:
            def complete(self, **kw):
                return LLMCompletion(
                    text='{"score": 40, "verdict": "approve", "reasons": [],'
                         ' "language": "vi", "canonical_title": "T"}',
                    provider_name="gemini", model="m")

        v = QualityReviewer(P(), min_score=70).review(
            title="t", body="x" * 80, lane="text")
        self.assertEqual(v.decision, "quarantine")
        self.assertFalse(v.approved)

    def test_normalized_metadata_is_captured_and_bounded(self):
        from server.farmer.review import QualityReviewer
        from server.llm_gateway.provider import LLMCompletion

        class P:
            def complete(self, **kw):
                return LLMCompletion(
                    text='{"score": 90, "verdict": "approve", "reasons": [],'
                         ' "language": "vi", "canonical_title": "' + "T" * 900 + '",'
                         ' "author": "A", "tags": ["x"], "content_type": "fanfic"}',
                    provider_name="gemini", model="m")

        v = QualityReviewer(P(), min_score=70).review(
            title="t", body="x" * 80, lane="text")
        self.assertTrue(v.approved)
        self.assertEqual(v.author, "A")
        self.assertEqual(v.content_type, "fanfic")
        self.assertLessEqual(len(v.canonical_title), 300,
                             "truong tu model phai bi cat, khong tin do dai")


if __name__ == "__main__":
    unittest.main()
