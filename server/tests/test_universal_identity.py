import unittest

from server.scraper.dedupe import source_fingerprint
from server.scraper.universal.acquisition import SourceClass
from server.scraper.universal.identity import (
    CanonicalIdentity, dedupe_identities, normalize_title,
)


class NormalizeTitleTest(unittest.TestCase):
    def test_lowercase_punctuation_whitespace(self):
        self.assertEqual(normalize_title("  The, Story!! -- Part 2  "),
                         "the story part 2")

    def test_idempotent(self):
        once = normalize_title("Hello World")
        self.assertEqual(normalize_title(once), once)


class CanonicalIdentityTest(unittest.TestCase):
    def test_identity_key_prefers_native_id(self):
        a = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="abc123", canonical_url="https://youtube.com/watch?v=abc123")
        b = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="abc123", canonical_url="https://m.youtube.com/watch?v=abc123&feature=share")
        self.assertEqual(a.identity_key(), b.identity_key())

    def test_identity_key_falls_back_to_canonical_url(self):
        a = CanonicalIdentity(source_platform="generic_web", source_type=SourceClass.WEB_FICTION,
                              canonical_url="https://example.com/story/1?utm_source=x")
        b = CanonicalIdentity(source_platform="generic_web", source_type=SourceClass.WEB_FICTION,
                              canonical_url="https://example.com/story/1")
        self.assertEqual(a.identity_key(), b.identity_key())
        self.assertEqual(a.identity_key(), source_fingerprint("https://example.com/story/1"))

    def test_different_native_ids_produce_different_keys(self):
        a = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="abc123")
        b = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="xyz789")
        self.assertNotEqual(a.identity_key(), b.identity_key())

    def test_no_id_and_no_url_raises(self):
        empty = CanonicalIdentity(source_platform="unknown", source_type=SourceClass.UNKNOWN)
        with self.assertRaises(ValueError):
            empty.identity_key()

    def test_same_native_id_different_platform_is_distinct(self):
        a = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="1")
        b = CanonicalIdentity(source_platform="bilibili", source_type=SourceClass.VIDEO_PLATFORM,
                              source_native_id="1")
        self.assertNotEqual(a.identity_key(), b.identity_key())


class DedupeIdentitiesTest(unittest.TestCase):
    def test_removes_duplicates_keeps_first_seen(self):
        a = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="v1", normalized_title="first")
        dup = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                                source_native_id="v1", normalized_title="second-seen-dropped")
        c = CanonicalIdentity(source_platform="youtube", source_type=SourceClass.YOUTUBE,
                              source_native_id="v2")
        result = dedupe_identities([a, dup, c])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].normalized_title, "first")

    def test_empty_input(self):
        self.assertEqual(dedupe_identities([]), [])


if __name__ == "__main__":
    unittest.main()
