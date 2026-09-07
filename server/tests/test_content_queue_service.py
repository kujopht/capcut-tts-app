"""Be mat web cua hang doi san xuat noi dung.

Bat bien quan trong nhat, va la ly do tang dich vu nay ton tai:

    WEB XEP VIEC VA QUAN LY VIEC. WEB KHONG BAO GIO CHAY VIEC.

Ngoai ra, cong quyen ban quyen phai KHONG di vong qua duoc bang mot cu bam
nut: `render` cua mot muc khong phai REHOST_ALLOWED da bi `SKIPPED` boi chinh
sach, va khong route nao duoc phep xep no lai.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from server import content_queue_service as svc
from server.adapters import NotFoundError
from server.domain import ChineseMediaQueueItem


def iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc)
            - timedelta(minutes=minutes_ago)).isoformat()


def make_item(**over) -> ChineseMediaQueueItem:
    base = dict(item_id="cmq_a", source_id="bobo_manju", platform="youtube",
                series_slug="bobo_manju", episode_ref="vid1", title="Tap 1",
                source_url="https://www.youtube.com/watch?v=vid1",
                rights_mode="REFERENCE_ONLY", updated_at=iso(5))
    base.update(over)
    return ChineseMediaQueueItem(**base)


class FakeStore:
    def __init__(self, items=()):
        self.items = {i.item_id: i for i in items}
        self.updates = []

    def list_queue_items_by_state(self, *, stage, state, limit=50, offset=0):
        out = [i for i in self.items.values() if getattr(i, stage) == state]
        return out[offset:offset + limit]

    def get_queue_item(self, item_id):
        if item_id not in self.items:
            raise NotFoundError(f"khong co {item_id}")
        return self.items[item_id]

    def update_queue_item(self, item_id, **fields):
        self.updates.append((item_id, dict(fields)))
        item = self.items[item_id]
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        return item


class RightsGateTest(unittest.TestCase):
    """Cong quyen KHONG duoc di vong qua bang duong web."""

    def test_render_cannot_be_requeued_for_non_rehost_items(self):
        for mode in ("REFERENCE_ONLY", "EMBED_ONLY"):
            with self.subTest(rights_mode=mode):
                store = FakeStore([make_item(rights_mode=mode,
                                             render_state="FAILED")])
                with self.assertRaises(svc.QueueActionError) as ctx:
                    svc.requeue_stage(store, "cmq_a", "render", actor_id="u1")
                self.assertIn(mode, str(ctx.exception))
                self.assertEqual(store.updates, [],
                                 "khong duoc ghi gi khi cong quyen tu choi")

    def test_a_skipped_stage_is_never_requeuable(self):
        store = FakeStore([make_item(render_state="SKIPPED")])
        with self.assertRaises(svc.QueueActionError):
            svc.requeue_stage(store, "cmq_a", "render", actor_id="u1")
        self.assertEqual(store.updates, [])

    def test_render_requeue_allowed_only_for_rehost_allowed(self):
        store = FakeStore([make_item(rights_mode="REHOST_ALLOWED",
                                     render_state="FAILED")])
        out = svc.requeue_stage(store, "cmq_a", "render", actor_id="u1")
        self.assertEqual(out["item"]["stages"]["render"], "PENDING")


class RequeueRulesTest(unittest.TestCase):
    def test_done_stage_cannot_be_requeued(self):
        store = FakeStore([make_item(transcript_state="DONE")])
        with self.assertRaises(svc.QueueActionError):
            svc.requeue_stage(store, "cmq_a", "transcript", actor_id="u1")
        self.assertEqual(store.updates, [])

    def test_failed_stage_is_requeued_and_budget_reset(self):
        store = FakeStore([make_item(transcript_state="FAILED", attempts=3,
                                     last_error="transcript: no")])
        out = svc.requeue_stage(store, "cmq_a", "transcript", actor_id="u1")
        self.assertEqual(out["item"]["stages"]["transcript"], "PENDING")
        self.assertEqual(out["item"]["attempts"], 0)
        self.assertIn("u1", out["item"]["last_error"])

    def test_a_freshly_running_stage_is_not_stolen(self):
        """Xep lai mot cong doan dang thuc su chay se tao ra ban tieu thu thu
        hai cho chinh muc do — dung dieu ca tang nay ton tai de ngan."""
        store = FakeStore([make_item(transcript_state="RUNNING",
                                     updated_at=iso(5))])
        with self.assertRaises(svc.QueueActionError):
            svc.requeue_stage(store, "cmq_a", "transcript", actor_id="u1")
        self.assertEqual(store.updates, [])

    def test_a_long_stuck_running_stage_can_be_reclaimed(self):
        store = FakeStore([make_item(
            transcript_state="RUNNING",
            updated_at=iso(svc.RUNNING_REQUEUE_MIN_AGE_MINUTES + 10))])
        out = svc.requeue_stage(store, "cmq_a", "transcript", actor_id="u1")
        self.assertEqual(out["item"]["stages"]["transcript"], "PENDING")

    def test_unreadable_timestamp_is_never_reclaimed(self):
        store = FakeStore([make_item(transcript_state="RUNNING",
                                     updated_at="khong-phai-ngay")])
        with self.assertRaises(svc.QueueActionError):
            svc.requeue_stage(store, "cmq_a", "transcript", actor_id="u1")

    def test_unknown_stage_is_rejected_before_touching_the_store(self):
        store = FakeStore([make_item()])
        with self.assertRaises(svc.QueueActionError):
            svc.requeue_stage(store, "cmq_a", "khong_ton_tai", actor_id="u1")
        self.assertEqual(store.updates, [])


class ViewTest(unittest.TestCase):
    def test_overall_reports_failed_over_running(self):
        item = make_item(transcript_state="DONE", translation_state="RUNNING",
                         subtitle_state="FAILED")
        self.assertEqual(svc.item_view(item)["overall"], "FAILED")

    def test_overall_complete_needs_every_stage_terminal(self):
        item = make_item(transcript_state="DONE", translation_state="DONE",
                         subtitle_state="DONE", dub_state="SKIPPED",
                         draft_state="DONE", render_state="SKIPPED")
        self.assertEqual(svc.item_view(item)["overall"], "COMPLETE")

    def test_waiting_is_distinguished_from_broken(self):
        waiting = make_item(last_error="transcript: CHO: can --audio")
        broken = make_item(last_error="translation: JSONDecodeError")
        self.assertTrue(svc.item_view(waiting)["waiting"])
        self.assertFalse(svc.item_view(broken)["waiting"])

    def test_checkpoint_presence_is_exposed_without_leaking_the_key(self):
        view = svc.item_view(make_item(transcript_key="transcripts/x/y.json"))
        self.assertTrue(view["has_transcript_checkpoint"])
        self.assertNotIn("transcript_key", view)


class ListingTest(unittest.TestCase):
    def test_every_item_is_listed_exactly_once(self):
        items = [make_item(item_id=f"cmq_{n}",
                           transcript_state=st)
                 for n, st in enumerate(
                     ["PENDING", "RUNNING", "DONE", "SKIPPED", "FAILED"])]
        out = svc.list_items(FakeStore(items), limit=50)
        self.assertEqual(out["total"], 5)
        self.assertEqual(len({i["item_id"] for i in out["items"]}), 5)

    def test_summary_counts_match_the_cli_shape(self):
        out = svc.summary(FakeStore([make_item()]))
        self.assertEqual(set(out["by_stage"]), set(svc.STAGES))
        self.assertEqual(out["by_stage"]["transcript"]["PENDING"], 1)
        self.assertEqual(out["total"], 1)

    def test_missing_item_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            svc.get_item(FakeStore([]), "cmq_khong_co")


class NoProcessSpawnTest(unittest.TestCase):
    """Bat bien trung tam, kiem bang MA chu khong bang loi hua: khong mot
    duong nao trong tang nay duoc phep khoi chay mot tien trinh."""

    #: Kiem tren CAY CU PHAP, khong phai tren van ban: chinh docstring cua tang
    #: nay co chu "subprocess" (de noi rang no KHONG dung), nen mot phep tim
    #: chuoi se bao dong gia va day nguoi ta toi cho xoa loi giai thich.
    BANNED_MODULES = {"subprocess", "threading", "multiprocessing",
                      "concurrent", "asyncio", "signal", "pty"}
    BANNED_CALLS = {"system", "popen", "spawn", "fork", "execv", "Popen",
                    "run", "call", "check_output", "create_task",
                    "add_task", "Thread", "Process"}

    def _tree(self):
        import ast
        from pathlib import Path

        import server.content_queue_service as module

        return ast, ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def test_service_imports_no_process_machinery(self):
        ast, tree = self._tree()
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        offending = found & self.BANNED_MODULES
        self.assertEqual(offending, set(),
                         f"tang web khong duoc chay viec: import {offending}")

    def test_service_calls_nothing_that_starts_work(self):
        ast, tree = self._tree()
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        offending = called & self.BANNED_CALLS
        self.assertEqual(offending, set(),
                         f"tang web khong duoc chay viec: goi {offending}")

    def test_the_guard_would_actually_catch_a_violation(self):
        """Mot bai test canh gac vo dung con te hon khong co: chung minh no
        that su bat duoc, bang cach cho no doc mot doan vi pham."""
        import ast

        bad = ast.parse("import subprocess\nsubprocess.run(['x'])\n")
        mods = {a.name.split(".")[0]
                for n in ast.walk(bad) if isinstance(n, ast.Import)
                for a in n.names}
        calls = {n.func.attr for n in ast.walk(bad)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertTrue(mods & self.BANNED_MODULES)
        self.assertTrue(calls & self.BANNED_CALLS)


if __name__ == "__main__":
    unittest.main()
