"""Cong dieu kien do dai trong duong THU NAP.

Hai bat bien:

1. Muc qua dai KHONG BAO GIO vao hang doi THUC THI. Cach dien dat la moi cong
   doan `SKIPPED` — khac `DONE` (khong lam gia la da xong) va khac `FAILED`
   (khong co gi hong). `collect_work` chi lay `PENDING`/`FAILED`, nen mot muc
   nhu vay khong bao gio bi nhat len.
2. Ly do bi loai duoc giu nguyen van cung sieu du lieu, khong bi xoa.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import chinese_media_watcher as watcher  # noqa: E402
import chinese_media_orchestrator as orch  # noqa: E402
from server.scraper import media_eligibility as me  # noqa: E402
from server.scraper.chinese_media_sources import ChineseMediaSource  # noqa: E402

SOURCE = ChineseMediaSource(
    source_id="bobo_manju", platform="youtube", display_name="波波漫剧",
    channel_id="UCtest", category="AI漫剧", channel_url="https://x")

STAGES = ("transcript", "translation", "subtitle", "dub", "draft", "render")


class FakeStore:
    def __init__(self):
        self.created = []

    def create_queue_item_once(self, item):
        self.created.append(item)
        return item, True

    def list_queue_items_by_state(self, *, stage, state, limit=50, offset=0):
        out = [i for i in self.created if getattr(i, stage) == state]
        return out[offset:offset + limit]


def entries(*ids):
    return [{"video_id": v, "title": f"tap {v}", "published": "",
             "description": ""} for v in ids]


class IngestionGateTest(unittest.TestCase):
    def _poll(self, durations, max_seconds=7200):
        store = FakeStore()

        def probe(v, **k):
            return watcher.DurationProbe(durations[v], "ok", "")

        with mock.patch.object(watcher, "fetch_channel_feed",
                               return_value=entries(*durations)), \
             mock.patch.object(watcher, "probe_duration_seconds",
                               side_effect=probe), \
             mock.patch.object(watcher, "find_source_captions",
                               return_value=None):
            report = watcher.poll_source(SOURCE, store,
                                         max_seconds=max_seconds)
        return store, report

    def test_a_long_source_never_becomes_executable(self):
        store, report = self._poll({"vLong": 38019})
        item = store.created[0]

        self.assertEqual(report["new"], 0)
        self.assertEqual(report["new_ineligible"], 1)
        for s in STAGES:
            self.assertEqual(getattr(item, f"{s}_state"), "SKIPPED")
        # Bat bien that: ban tieu thu khong bao gio nhat no len.
        self.assertEqual(orch.collect_work(store, limit=10), [])

    def test_a_long_source_is_not_marked_done_or_failed(self):
        store, _ = self._poll({"vLong": 111617})
        states = {getattr(store.created[0], f"{s}_state") for s in STAGES}
        self.assertNotIn("DONE", states)
        self.assertNotIn("FAILED", states)

    def test_the_reason_is_preserved_verbatim(self):
        store, _ = self._poll({"vLong": 38019})
        item = store.created[0]
        self.assertTrue(me.is_ineligible_marker(item.last_error))
        self.assertIn("10h33m39s", item.last_error)
        self.assertIn("2h00m00s", item.last_error)

    def test_metadata_is_kept_not_dropped(self):
        store, _ = self._poll({"vLong": 38019})
        item = store.created[0]
        self.assertEqual(item.episode_ref, "vLong")
        self.assertEqual(item.source_url,
                         "https://www.youtube.com/watch?v=vLong")
        self.assertEqual(item.source_id, "bobo_manju")

    def test_a_short_source_enters_the_queue_normally(self):
        store, report = self._poll({"vShort": 102})
        item = store.created[0]
        self.assertEqual(report["new"], 1)
        self.assertEqual(report["new_ineligible"], 0)
        for s in STAGES:
            self.assertEqual(getattr(item, f"{s}_state"), "PENDING")
        self.assertEqual(item.last_error, "")
        self.assertEqual([i.item_id for i in orch.collect_work(store, limit=10)],
                         [item.item_id])

    def _poll_probe(self, probe_result, video="vX"):
        store = FakeStore()
        with mock.patch.object(watcher, "fetch_channel_feed",
                               return_value=entries(video)), \
             mock.patch.object(watcher, "probe_duration_seconds",
                               return_value=probe_result), \
             mock.patch.object(watcher, "find_source_captions",
                               return_value=None):
            report = watcher.poll_source(SOURCE, store, max_seconds=7200)
        return store, report

    def test_an_unprobeable_source_is_refused_fail_closed(self):
        store, report = self._poll_probe(
            watcher.DurationProbe(None, "unprobeable", "yt-dlp khong in gi"))
        self.assertEqual(report["new"], 0)
        self.assertEqual(report["new_ineligible"], 1)
        self.assertIn("fail closed", store.created[0].last_error)

    def test_an_unavailable_source_says_so_instead_of_blaming_the_probe(self):
        """Ca hai deu loai muc ra, nhung chung khac nhau ve TUONG LAI: mot
        video khong do duoc co the do duoc lan sau; mot video da bi go thi
        khong bao gio. Gop chung se lam nguoi van hanh di tim mot loi cong cu
        khong ton tai."""
        store, report = self._poll_probe(
            watcher.DurationProbe(None, "unavailable", "yt-dlp: video unavailable"))
        self.assertEqual(report["new_ineligible"], 1)
        err = store.created[0].last_error
        self.assertIn("khong con truy cap duoc", err)
        self.assertNotIn("fail closed", err)
        self.assertTrue(me.is_ineligible_marker(err))

    def test_the_boundary_is_inclusive_end_to_end(self):
        store, report = self._poll({"vEdge": 7200})
        self.assertEqual(report["new"], 1)
        self.assertEqual(store.created[0].transcript_state, "PENDING")


class ProbeTest(unittest.TestCase):
    def _probe(self, proc):
        with mock.patch.object(watcher.shutil, "which", return_value="yt-dlp"), \
             mock.patch.object(watcher.subprocess, "run", return_value=proc):
            return watcher.probe_duration_seconds("v1")

    def test_missing_yt_dlp_yields_unprobeable_not_a_crash(self):
        with mock.patch.object(watcher.shutil, "which", return_value=None):
            got = watcher.probe_duration_seconds("v1")
        self.assertEqual(got.state, "unprobeable")
        self.assertIsNone(got.seconds)

    def test_probe_parses_a_float_duration(self):
        got = self._probe(mock.Mock(returncode=0, stdout="102.0\n", stderr=""))
        self.assertEqual(got.seconds, 102)
        self.assertEqual(got.state, "ok")

    def test_probe_never_downloads_media(self):
        proc = mock.Mock(returncode=0, stdout="102\n", stderr="")
        with mock.patch.object(watcher.shutil, "which", return_value="yt-dlp"), \
             mock.patch.object(watcher.subprocess, "run",
                               return_value=proc) as run:
            watcher.probe_duration_seconds("v1")
        self.assertIn("--skip-download", run.call_args[0][0])

    def test_probe_failures_are_unprobeable_not_zero(self):
        """Tra 0 se bi `evaluate` doc thanh 'do dai khong tin duoc' — dung ket
        qua, nhung `None` moi la su that: khong do duoc."""
        for proc in (mock.Mock(returncode=1, stdout="", stderr="loi la"),
                     mock.Mock(returncode=0, stdout="NA\n", stderr=""),
                     mock.Mock(returncode=0, stdout="\n", stderr="")):
            with self.subTest(stdout=proc.stdout):
                got = self._probe(proc)
                self.assertIsNone(got.seconds)
                self.assertEqual(got.state, "unprobeable")

    def test_a_removed_video_is_reported_as_unavailable(self):
        """Do that tu production 2026-09-07: 15/15 muc RSS cua KK爱看 tra
        'Video unavailable'. Doc thanh 'khong do duoc' se gui nguoi van hanh
        di san mot loi cong cu khong ton tai."""
        for stderr in ("ERROR: [youtube] X: Video unavailable",
                       "ERROR: Private video. Sign in if you've been granted access",
                       "ERROR: This video is not available in your country"):
            with self.subTest(stderr=stderr[:30]):
                got = self._probe(mock.Mock(returncode=1, stdout="",
                                            stderr=stderr))
                self.assertEqual(got.state, "unavailable")


if __name__ == "__main__":
    unittest.main()
