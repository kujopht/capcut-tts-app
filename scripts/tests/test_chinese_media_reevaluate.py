"""Danh gia lai do dai cho cac muc DA nam trong hang doi.

Hai bat bien de mat nhat neu ai do sua vo y:

1. **Hoan la HOAN, khong phai vut.** Mot muc bi loai vi nguong cu phai quay
   lai duoc khi nguong doi. Neu khong, "deferred" chi la mot cach noi giam
   cua "da xoa".
2. **Khong dong bang mot muc dang co tien do that.** Danh dau `SKIPPED` len
   mot muc da co transcript/ban dich/draft se vut di cong viec da tra tien
   roi — va lam mat dau vet trong `last_error`.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import chinese_media_reevaluate as reeval  # noqa: E402
import chinese_media_watcher as watcher  # noqa: E402
from server.domain import ChineseMediaQueueItem  # noqa: E402
from server.scraper import media_eligibility as me  # noqa: E402

STAGES = reeval.STAGES


def make_item(**over) -> ChineseMediaQueueItem:
    base = dict(item_id="cmq_a", source_id="tepi_dongman", platform="youtube",
                series_slug="tepi_dongman", episode_ref="vid1", title="Tap 1",
                source_url="https://www.youtube.com/watch?v=vid1",
                rights_mode="REFERENCE_ONLY")
    base.update(over)
    return ChineseMediaQueueItem(**base)


def deferred(**over) -> ChineseMediaQueueItem:
    fields = {f"{s}_state": "SKIPPED" for s in STAGES}
    fields["last_error"] = me.evaluate(38019, 7200).as_last_error()
    fields.update(over)
    return make_item(**fields)


class FakeStore:
    def __init__(self, items=()):
        self.items = {i.item_id: i for i in items}
        self.updates = []

    def list_queue_items_by_state(self, *, stage, state, limit=50, offset=0):
        out = [i for i in self.items.values() if getattr(i, stage) == state]
        return out[offset:offset + limit]

    def update_queue_item(self, item_id, **fields):
        self.updates.append((item_id, dict(fields)))
        item = self.items[item_id]
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        return item


def probe(seconds, state="ok"):
    return watcher.DurationProbe(seconds, state, "")


class ClassificationTest(unittest.TestCase):
    def test_deferred_item_is_recognised(self):
        self.assertTrue(reeval.already_ineligible(deferred()))

    def test_a_plain_skipped_item_is_not_mistaken_for_deferred(self):
        """Moi cong doan `SKIPPED` nhung KHONG co dau `INELIGIBLE:` thi khong
        phai muc bi hoan — vd mot muc bi bo qua vi ly do khac."""
        fields = {f"{s}_state": "SKIPPED" for s in STAGES}
        self.assertFalse(reeval.already_ineligible(make_item(**fields)))

    def test_real_progress_is_detected(self):
        for over in ({"transcript_key": "transcripts/x.json"},
                     {"novel_id": "nov_1"},
                     {"subtitle_state": "DONE"}):
            with self.subTest(over=over):
                self.assertTrue(reeval.has_real_progress(make_item(**over)))

    def test_a_fresh_item_has_no_progress(self):
        self.assertFalse(reeval.has_real_progress(make_item()))


class DeferIsReversibleTest(unittest.TestCase):
    """Bat bien #1 — hoan phai quay lai duoc."""

    def _run(self, store, argv):
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(3600)):
            reeval.main(argv)

    def test_raising_the_threshold_restores_a_deferred_item(self):
        item = deferred()
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(3600)), \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main(["--recheck-ineligible", "--max-seconds", "7200"])

        for s in STAGES:
            self.assertEqual(getattr(item, f"{s}_state"), "PENDING")
        self.assertEqual(item.last_error, "")
        self.assertEqual(item.attempts, 0)

    def test_without_the_flag_a_deferred_item_is_left_alone(self):
        item = deferred()
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds") as p, \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main([])
        p.assert_not_called()
        self.assertEqual(store.updates, [])

    def test_dry_run_restores_nothing(self):
        item = deferred()
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(3600)), \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main(["--recheck-ineligible", "--dry-run"])
        self.assertEqual(store.updates, [])
        self.assertEqual(item.transcript_state, "SKIPPED")


class ProgressIsNeverFrozenTest(unittest.TestCase):
    """Bat bien #2 — khong vut di cong viec da tra tien roi."""

    def test_an_item_with_a_checkpoint_is_never_deferred(self):
        item = make_item(transcript_key="transcripts/x.json")
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(38019)) as p, \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main([])

        p.assert_not_called()
        self.assertEqual(store.updates, [])
        self.assertEqual(item.transcript_state, "PENDING")


class DeferralTest(unittest.TestCase):
    def test_a_long_source_is_deferred_with_its_reason(self):
        item = make_item()
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(38019)), \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main([])

        for s in STAGES:
            self.assertEqual(getattr(item, f"{s}_state"), "SKIPPED")
        self.assertTrue(me.is_ineligible_marker(item.last_error))
        self.assertIn("10h33m39s", item.last_error)

    def test_an_unavailable_source_says_so(self):
        item = make_item()
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(None, "unavailable")), \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main([])
        self.assertIn("khong con truy cap duoc", item.last_error)

    def test_an_eligible_item_is_left_pending(self):
        item = make_item()
        store = FakeStore([item])
        with mock.patch.object(reeval, "probe_duration_seconds",
                               return_value=probe(1339)), \
             mock.patch("server.appwrite_store.AppwriteMetadataStore",
                        return_value=store), \
             mock.patch("server.config.load_settings"):
            reeval.main([])
        self.assertEqual(store.updates, [])
        self.assertEqual(item.transcript_state, "PENDING")


if __name__ == "__main__":
    unittest.main()
