"""Route `/api/admin/content-queue/*` — be mat web cua hang doi san xuat.

`test_admin.py::test_moi_route_admin_deu_duoc_bao_ve` da tu dong kiem quyen
cho moi route `/api/admin/*`, ke ca cac route o day. Tep nay kiem phan CON
LAI: hop dong tra ve, va hai ranh gioi khong duoc phep vo:

  1. cong quyen ban quyen khong di vong qua duoc bang mot request;
  2. khong request nao khoi chay mot tien trinh orchestrator.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore, NotFoundError
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


class QueueStore(MockMetadataStore):
    """Mock san co, them dung ba phuong thuc hang doi ma tang dich vu dung."""

    def __init__(self, items=()):
        super().__init__()
        self._queue = {i.item_id: i for i in items}

    def list_queue_items_by_state(self, *, stage, state, limit=50, offset=0):
        out = [i for i in self._queue.values() if getattr(i, stage) == state]
        return out[offset:offset + limit]

    def get_queue_item(self, item_id):
        if item_id not in self._queue:
            raise NotFoundError(f"khong co {item_id}")
        return self._queue[item_id]

    def update_queue_item(self, item_id, **fields):
        item = self._queue[item_id]
        for k, v in fields.items():
            if hasattr(item, k):
                setattr(item, k, v)
        return item


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = QueueStore([make_item()])
        server_main.store = self.store
        self.client = TestClient(server_main.app)

    def admin(self) -> Dict[str, str]:
        resp = self.client.post("/api/auth/register",
                                json={"email": "admin@example.com",
                                      "password": "matkhau123"})
        body = resp.json()
        # `Settings` la dataclass DONG BANG — cung cach `test_admin.py` cap
        # quyen: thay ca doi tuong bang `replace`, khong gan tung truong.
        self.addCleanup(setattr, server_main, "settings", server_main.settings)
        server_main.settings = replace(
            server_main.settings,
            admin_user_ids=(body["profile"]["user_id"],))
        return {"Authorization": f"Bearer {body['token']}"}


class ReadTest(Base):
    def test_listing_returns_stage_states(self):
        resp = self.client.get("/api/admin/content-queue", headers=self.admin())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        item = body["items"][0]
        self.assertEqual(item["item_id"], "cmq_a")
        self.assertEqual(item["stages"]["transcript"], "PENDING")
        self.assertEqual(item["overall"], "PENDING")

    def test_summary_matches_the_cli_shape(self):
        resp = self.client.get("/api/admin/content-queue/summary",
                               headers=self.admin())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["by_stage"]["transcript"]["PENDING"], 1)

    def test_missing_item_is_404_not_500(self):
        resp = self.client.get("/api/admin/content-queue/cmq_khong_co",
                               headers=self.admin())
        self.assertEqual(resp.status_code, 404)

    def test_summary_is_not_swallowed_by_the_item_route(self):
        """`/summary` phai duoc khai bao TRUOC `/{item_id}`, neu khong no se bi
        doc thanh mot item_id ten la "summary" va tra 404."""
        resp = self.client.get("/api/admin/content-queue/summary",
                               headers=self.admin())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("by_stage", resp.json())


class RequeueRouteTest(Base):
    def test_failed_stage_can_be_requeued(self):
        self.store._queue["cmq_a"].transcript_state = "FAILED"
        self.store._queue["cmq_a"].attempts = 3
        resp = self.client.post("/api/admin/content-queue/cmq_a/requeue",
                                json={"stage": "transcript"},
                                headers=self.admin())
        self.assertEqual(resp.status_code, 200)
        item = resp.json()["item"]
        self.assertEqual(item["stages"]["transcript"], "PENDING")
        self.assertEqual(item["attempts"], 0)

    def test_render_requeue_is_refused_for_reference_only(self):
        """CONG QUYEN. Mot cu bam nut khong duoc mo duong render cho noi dung
        chua co quyen phan phoi lai."""
        self.store._queue["cmq_a"].render_state = "FAILED"
        resp = self.client.post("/api/admin/content-queue/cmq_a/requeue",
                                json={"stage": "render"}, headers=self.admin())
        self.assertEqual(resp.status_code, 409)
        self.assertIn("REFERENCE_ONLY", resp.json()["detail"])
        self.assertEqual(self.store._queue["cmq_a"].render_state, "FAILED")

    def test_done_stage_requeue_is_refused(self):
        self.store._queue["cmq_a"].transcript_state = "DONE"
        resp = self.client.post("/api/admin/content-queue/cmq_a/requeue",
                                json={"stage": "transcript"},
                                headers=self.admin())
        self.assertEqual(resp.status_code, 409)

    def test_unknown_stage_is_refused(self):
        resp = self.client.post("/api/admin/content-queue/cmq_a/requeue",
                                json={"stage": "khong_ton_tai"},
                                headers=self.admin())
        self.assertEqual(resp.status_code, 409)

    def test_requeue_of_missing_item_is_404(self):
        resp = self.client.post("/api/admin/content-queue/cmq_khong_co/requeue",
                                json={"stage": "transcript"},
                                headers=self.admin())
        self.assertEqual(resp.status_code, 404)


class NoWorkIsStartedTest(Base):
    def test_a_requeue_only_flips_state_and_starts_nothing(self):
        """Bat bien trung tam: web XEP viec, khong CHAY viec. Neu mot request
        sinh mot tien trinh orchestrator thi so ban tieu thu se bang so nguoi
        bam nut — dung dieu gia dinh MOT-nguoi-ghi cam."""
        import subprocess
        from unittest import mock

        self.store._queue["cmq_a"].transcript_state = "FAILED"
        with mock.patch.object(subprocess, "Popen") as popen, \
             mock.patch.object(subprocess, "run") as run:
            resp = self.client.post("/api/admin/content-queue/cmq_a/requeue",
                                    json={"stage": "transcript"},
                                    headers=self.admin())

        self.assertEqual(resp.status_code, 200)
        popen.assert_not_called()
        run.assert_not_called()
        # Cong doan chi ve PENDING — no VAN chua chay, va se khong chay cho toi
        # khi tien trinh orchestrator duy nhat quet lan sau.
        self.assertEqual(self.store._queue["cmq_a"].transcript_state, "PENDING")


if __name__ == "__main__":
    unittest.main()
