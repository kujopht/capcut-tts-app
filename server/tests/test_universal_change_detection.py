import unittest

from server.scraper.change_detection import ChangeKind
from server.scraper.universal.change_detection import (
    UnitChangeKind, classify_index, classify_unit_content,
    from_fiction_change_kind, to_fiction_change_kind,
)


class FictionCompatibilityAliasTest(unittest.TestCase):
    def test_every_unit_kind_maps_to_a_fiction_kind_and_back(self):
        for kind in UnitChangeKind:
            fiction = to_fiction_change_kind(kind)
            self.assertIsInstance(fiction, ChangeKind)
            self.assertEqual(from_fiction_change_kind(fiction), kind)

    def test_new_unit_maps_to_new_chapter(self):
        self.assertEqual(to_fiction_change_kind(UnitChangeKind.NEW_UNIT), ChangeKind.NEW_CHAPTER)

    def test_updated_unit_maps_to_updated_chapter(self):
        self.assertEqual(to_fiction_change_kind(UnitChangeKind.UPDATED_UNIT),
                         ChangeKind.UPDATED_CHAPTER)


class ClassifyIndexTest(unittest.TestCase):
    def test_new_key_is_new_unit(self):
        plan = classify_index(previous_keys=["a"], current_keys=["a", "b"])
        by_key = {c.unit_identity_key: c.kind for c in plan.changes}
        self.assertEqual(by_key["b"], UnitChangeKind.NEW_UNIT)

    def test_missing_key_is_removed(self):
        plan = classify_index(previous_keys=["a", "b"], current_keys=["a"])
        by_key = {c.unit_identity_key: c.kind for c in plan.changes}
        self.assertEqual(by_key["b"], UnitChangeKind.REMOVED_OR_UNAVAILABLE)

    def test_key_in_both_needs_baseline_pending_content_check(self):
        plan = classify_index(previous_keys=["a"], current_keys=["a"])
        self.assertEqual(plan.changes[0].kind, UnitChangeKind.NEEDS_BASELINE)

    def test_empty_previous_all_new(self):
        plan = classify_index(previous_keys=[], current_keys=["a", "b"])
        self.assertEqual(plan.counts()["new_unit"], 2)

    def test_keys_needing_fetch_excludes_unchanged(self):
        plan = classify_index(previous_keys=["a"], current_keys=["a", "b"])
        self.assertIn("b", plan.keys_needing_fetch)


class ClassifyUnitContentTest(unittest.TestCase):
    def test_transient_failure_takes_priority(self):
        change = classify_unit_content("k", previous_content_hash="h1",
                                       new_content_hash="h1", transient=True)
        self.assertEqual(change.kind, UnitChangeKind.TRANSIENT_FAILURE)

    def test_no_new_hash_is_removed(self):
        change = classify_unit_content("k", previous_content_hash="h1", new_content_hash=None)
        self.assertEqual(change.kind, UnitChangeKind.REMOVED_OR_UNAVAILABLE)

    def test_no_previous_hash_is_needs_baseline(self):
        change = classify_unit_content("k", previous_content_hash=None, new_content_hash="h1")
        self.assertEqual(change.kind, UnitChangeKind.NEEDS_BASELINE)

    def test_same_hash_is_unchanged(self):
        change = classify_unit_content("k", previous_content_hash="h1", new_content_hash="h1")
        self.assertEqual(change.kind, UnitChangeKind.UNCHANGED)

    def test_different_hash_is_updated(self):
        change = classify_unit_content("k", previous_content_hash="h1", new_content_hash="h2")
        self.assertEqual(change.kind, UnitChangeKind.UPDATED_UNIT)
        self.assertTrue(change.revalidated)


if __name__ == "__main__":
    unittest.main()
