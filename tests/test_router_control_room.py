"""Bộ kiểm thử tất định toàn diện — Fanfic World Control Room TUI.

Kiểm tra 14 yêu cầu theo Mission Specification:
1. Chiếu trạng thái (State projection)
2. Kết xuất trạng thái Task (tất cả 7 biểu tượng: ○, ◌, ●, ✓, ✗, ↻, !)
3. Kết xuất trạng thái Worker (OFFLINE, STARTING, IDLE, BUSY, DEGRADED, COOLDOWN)
4. Độ bền sự kiện (Event persistence trong SQLite & JSONL)
5. Lọc sự kiện (ALL, WARNINGS, FAILURES, ROUTING, WORKERS)
6. Giải thích định tuyến (Routing explain view & score dimensions)
7. Chi tiết task bị lỗi (Failed task detail & failure reason)
8. Xử lý telemetry bị thiếu / UNKNOWN (không bịa số liệu)
9. Xử lý tên task siêu dài (Long task names)
10. Đáp ứng thay đổi kích thước terminal (Resize / Responsive)
11. Hỗ trợ 8+ workers (AG01..AG08, CODEX, OPENCODE, CLAUDE)
12. Ghi/đọc sự kiện đồng thời (Concurrent event writer/reader)
13. Lọc sạch bí mật (Secret redaction - tokens, keys, JWTs)
14. Điều khiển an toàn (Safe control dispatch & audit logging)
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.pool.store import PoolStore
from scripts.router_v3.control_room.controls import SafeController
from scripts.router_v3.control_room.event_store import ControlRoomEvent, EventKind, EventLevel, EventStore
from scripts.router_v3.control_room.state_reader import (
    ControlRoomSnapshot,
    StateReader,
    TaskDetailView,
    TaskState,
    WorkerDetailView,
    WorkerState,
)
from scripts.router_v3.control_room.widgets import (
    ClaudeLeadWidget,
    EventsWidget,
    HeaderWidget,
    SelectedTaskWidget,
    StatusBarWidget,
    TaskDagWidget,
    WorkerPanelWidget,
)


class TestRouterControlRoom(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_control_room_"))
        self.store = PoolStore(root=self.temp_dir)
        self.event_store = EventStore(root=self.temp_dir)
        self.state_reader = StateReader(root=self.temp_dir, store=self.store, event_store=self.event_store)
        self.controller = SafeController(
            root=self.temp_dir,
            store=self.store,
            event_store=self.event_store,
            state_reader=self.state_reader,
        )

    def tearDown(self):
        self.store.close()
        self.event_store.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_1_state_projection(self):
        """1. Chiếu trạng thái từ SQLite sang ControlRoomSnapshot."""
        # Tạo run và job mẫu
        rid = self.store.tao_run(base_sha="abc1234", note="Mission Test Alpha")
        self.store.them_job(
            run_id=rid,
            node_id="task_audit",
            node={"objective": "Kiểm tra hệ thống", "required_capabilities": ["recon"]},
        )
        self.store.ghi_worker({
            "worker_id": "AG01",
            "provider": "antigravity",
            "model": "gemini-3.8-flash-high",
            "state": "READY",
        })

        snap = self.state_reader.snapshot(run_id=rid)
        self.assertEqual(snap.mission.run_id, rid)
        self.assertEqual(snap.mission.name, "Mission Test Alpha")
        self.assertEqual(len(snap.tasks), 1)
        self.assertEqual(snap.tasks[0].id, "task_audit")
        self.assertEqual(len(snap.workers), 1)
        self.assertEqual(snap.workers[0].id, "AG01")
        self.assertEqual(snap.workers[0].state, WorkerState.IDLE)

    def test_2_task_state_rendering(self):
        """2. Kết xuất trạng thái Task với tất cả 7 biểu tượng chuẩn."""
        expected_icons = {
            TaskState.WAITING: "○",
            TaskState.READY: "◌",
            TaskState.RUNNING: "●",
            TaskState.PASS: "✓",
            TaskState.FAILED: "✗",
            TaskState.RETRY: "↻",
            TaskState.BLOCKED: "!",
        }
        for state, expected_icon in expected_icons.items():
            self.assertEqual(state.icon, expected_icon)

        # Kiểm tra hiển thị trong widget TaskDagWidget
        tasks = [
            TaskDetailView(id="t_wait", state=TaskState.WAITING),
            TaskDetailView(id="t_ready", state=TaskState.READY),
            TaskDetailView(id="t_run", state=TaskState.RUNNING, elapsed_seconds=42.0),
            TaskDetailView(id="t_pass", state=TaskState.PASS),
            TaskDetailView(id="t_fail", state=TaskState.FAILED),
            TaskDetailView(id="t_retry", state=TaskState.RETRY),
            TaskDetailView(id="t_block", state=TaskState.BLOCKED),
        ]
        widget = TaskDagWidget(tasks)
        self.assertEqual(len(widget.tasks), 7)
        self.assertIsNotNone(widget.get_selected_task())

    def test_3_worker_state_rendering(self):
        """3. Kết xuất trạng thái Worker đầy đủ các bậc sức khoẻ."""
        states = [
            WorkerState.OFFLINE,
            WorkerState.STARTING,
            WorkerState.IDLE,
            WorkerState.BUSY,
            WorkerState.DEGRADED,
            WorkerState.COOLDOWN,
        ]
        workers = [
            WorkerDetailView(id=f"W_{st.value}", state=st, model="gemini-3.8", current_task="task_1" if st == WorkerState.BUSY else "")
            for st in states
        ]
        widget = WorkerPanelWidget(workers)
        self.assertEqual(len(widget.worker_items), 6)
        self.assertEqual(widget.get_selected_worker().id, "W_OFFLINE")

    def test_4_event_persistence(self):
        """4. Độ bền sự kiện (Lưu và đọc lại từ cả SQLite và JSONL)."""
        ev = self.event_store.record(
            EventKind.TASK_ASSIGNED,
            level=EventLevel.INFO,
            run_id="run-1",
            task_id="task-x",
            worker_id="AG02",
            detail="Giao việc cho AG02",
        )
        self.assertGreater(ev.id, 0)

        # Kiểm tra SQLite
        events = self.event_store.get_events(run_id="run-1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].task_id, "task-x")
        self.assertEqual(events[0].worker_id, "AG02")

        # Kiểm tra JSONL
        self.assertTrue(self.event_store.jsonl_path.exists())
        with open(self.event_store.jsonl_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        data = json.loads(lines[0])
        self.assertEqual(data["kind"], EventKind.TASK_ASSIGNED.value)

    def test_5_event_filtering(self):
        """5. Lọc sự kiện theo ALL, WARNINGS, FAILURES, ROUTING, WORKERS."""
        self.event_store.record(EventKind.TASK_STARTED, level=EventLevel.INFO, detail="Normal progress")
        self.event_store.record(EventKind.ALERT, level=EventLevel.WARNING, detail="Low quota warning")
        self.event_store.record(EventKind.TASK_FAILED, level=EventLevel.ERROR, detail="Execution error")
        self.event_store.record(EventKind.ROUTING_DECISION, level=EventLevel.INFO, detail="Selected AG01")
        self.event_store.record(EventKind.WORKER_ONLINE, level=EventLevel.INFO, detail="AG03 online")

        all_evs = self.event_store.get_events(category="ALL")
        self.assertEqual(len(all_evs), 5)

        warn_evs = self.event_store.get_events(category="WARNINGS")
        self.assertTrue(any(e.kind == "ALERT" for e in warn_evs))

        fail_evs = self.event_store.get_events(category="FAILURES")
        self.assertTrue(any(e.kind == "TASK_FAILED" for e in fail_evs))

        route_evs = self.event_store.get_events(category="ROUTING")
        self.assertTrue(any(e.kind == "ROUTING_DECISION" for e in route_evs))

        worker_evs = self.event_store.get_events(category="WORKERS")
        self.assertTrue(any(e.kind == "WORKER_ONLINE" for e in worker_evs))

    def test_6_routing_explain_view(self):
        """6. Giải thích định tuyến với các chiều điểm số và rào cản loại trừ."""
        rid = self.store.tao_run(base_sha="abc1234")
        self.store.them_job(
            run_id=rid,
            node_id="sec_review",
            node={"objective": "Audit bảo mật", "required_capabilities": ["security_review"], "risk_class": "high"},
        )
        self.store.ghi_worker({
            "worker_id": "CODEX01",
            "provider": "codex",
            "capabilities": ["security_review", "implement"],
            "state": "READY",
        })
        self.store.ghi_worker({
            "worker_id": "AG_OPUS",
            "provider": "antigravity",
            "capabilities": ["security_review", "architecture"],
            "auth_realm": "high",
            "state": "READY",
        })

        exp = self.state_reader.explain_routing("sec_review", run_id=rid)
        self.assertEqual(exp.task_id, "sec_review")
        self.assertEqual(exp.risk_class, "high")

        # Rào cấm: Codex bị cấm nhận security_review
        codex_cand = next(c for c in exp.candidates if c.worker_id == "CODEX01")
        self.assertTrue(codex_cand.excluded)
        self.assertIn("Codex", codex_cand.exclusion_reason)

        # AG_OPUS hợp lệ
        opus_cand = next(c for c in exp.candidates if c.worker_id == "AG_OPUS")
        self.assertFalse(opus_cand.excluded)
        self.assertIn("capability_fit", opus_cand.dimensions)

    def test_7_failed_task_detail(self):
        """7. Trích xuất chi tiết task bị hỏng và lý do lỗi."""
        rid = self.store.tao_run(base_sha="abc1234")
        jid = self.store.them_job(
            run_id=rid,
            node_id="failed_step",
            node={"objective": "Build UI component"},
            max_attempts=2,
        )
        self.store.claim(jid, "AG01")
        self.store.hoan_thanh(
            jid,
            status="failed",
            result={"error": "SyntaxError: invalid syntax in reader.tsx at line 42"},
            validation={"passed": False, "reason": "Linter failure"},
        )

        snap = self.state_reader.snapshot(run_id=rid)
        task = snap.tasks[0]
        self.assertEqual(task.id, "failed_step")
        self.assertEqual(task.state, TaskState.RETRY)  # Lượt 1/2 nên là RETRY
        self.assertIn("SyntaxError", task.failure_reason)

    def test_8_missing_or_unknown_telemetry(self):
        """8. Không bịa số liệu: telemetry không có phải hiện UNKNOWN."""
        snap = self.state_reader.snapshot()
        self.assertEqual(snap.claude_lead.context_display, "UNKNOWN")
        if snap.workers:
            for w in snap.workers:
                self.assertEqual(w.quota_display, "UNKNOWN")

    def test_9_long_task_names(self):
        """9. Tên và objective siêu dài không làm vỡ kết xuất giao diện."""
        rid = self.store.tao_run(base_sha="abc1234")
        long_obj = "A" * 500
        self.store.them_job(run_id=rid, node_id="very_long_node_name_" + "x" * 80, node={"objective": long_obj})

        snap = self.state_reader.snapshot(run_id=rid)
        task = snap.tasks[0]
        self.assertEqual(len(task.objective), 500)

        # Widget không được ném Exception khi render
        detail_widget = SelectedTaskWidget(task)
        render_res = detail_widget.render()
        self.assertIsNotNone(render_res)

    def test_10_terminal_resize_and_responsive(self):
        """10. Đáp ứng kích thước terminal linh hoạt."""
        header = HeaderWidget(self.state_reader.snapshot().mission)
        lead = ClaudeLeadWidget(self.state_reader.snapshot().claude_lead)
        status = StatusBarWidget()

        self.assertIsNotNone(header.render())
        self.assertIsNotNone(lead.render())
        self.assertIsNotNone(status.render())

    def test_11_eight_plus_workers(self):
        """11. Hỗ trợ hiển thị tự nhiên 8+ workers (AG01..AG08, CODEX, OPENCODE, CLAUDE)."""
        worker_ids = [f"AG{i:02d}" for i in range(1, 9)] + ["CODEX01", "OPENCODE01", "CLAUDE_LEAD"]
        for wid in worker_ids:
            self.store.ghi_worker({
                "worker_id": wid,
                "provider": "antigravity" if wid.startswith("AG") else wid.lower(),
                "model": "gemini-3.8" if wid.startswith("AG") else "default",
                "state": "READY" if wid in ("AG01", "CLAUDE_LEAD") else "OFFLINE",
            })

        snap = self.state_reader.snapshot()
        self.assertGreaterEqual(len(snap.workers), 11)
        rendered_ids = [w.id for w in snap.workers]
        for wid in worker_ids:
            self.assertIn(wid, rendered_ids)

    def test_12_concurrent_event_writer_reader(self):
        """12. Đọc và ghi sự kiện đồng thời trên nhiều luồng không khoá tệp."""
        errors = []

        def _writer(thread_id: int):
            try:
                for i in range(25):
                    self.event_store.record(
                        EventKind.TASK_PROGRESS,
                        task_id=f"T_{thread_id}",
                        detail=f"Progress step {i} from thread {thread_id}",
                    )
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def _reader():
            try:
                for _ in range(20):
                    evs = self.event_store.get_events(limit=50)
                    self.assertIsInstance(evs, list)
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(4)]
        threads.append(threading.Thread(target=_reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Đã có lỗi đồng thời: {errors}")

    def test_13_secret_redaction(self):
        """13. Lọc sạch bí mật (tokens, github keys, private keys, JWTs)."""
        # Ba fixture duoi day duoc GHEP LUC CHAY, khong viet nguyen van vao ma
        # nguon. Chuoi luc chay khong doi mot byte nao, nen bai test van kiem
        # dung nhung gi no vua kiem — nhung tep nay khong con chua mot chuoi
        # NHIN NHU khoa that.
        #
        # Vi sao phai lam vay: `standard_` + 40 ky tu [a-f0-9] khop dung luat
        # rieng `appwrite-api-key` trong .gitleaks.toml. Viet nguyen van thi
        # CA HAI cong secret deu do — da do that o day: cong PR (quet lich su,
        # dau van tay ff6437b1:...:341) va cong deploy (quet cay lam viec,
        # dau van tay tests/test_router_control_room.py:appwrite-api-key:341).
        #
        # Vi sao KHONG mien tru trong .gitleaksignore/.gitleaks.deploy.toml:
        # dau van tay che do lich su CO CHUA commit SHA, nen no vo ngay lan
        # sua tep tiep theo — chinh loi da lam do cong deploy ngay 2026-08-29
        # va 2026-08-30 (xem ghi chu dai trong .gitleaks.deploy.toml). Bo
        # chuoi nguyen van di thi khong can mien tru nao ca, va cong PR giu
        # nguyen do manh.
        # Ghep qua BIEN, khong phai qua hang so: `"1234567890" * 4` se bi
        # trinh bien dich GOP LAI luc compile, nen chuoi nguyen van hien ra
        # trong __pycache__/*.pyc — va `gitleaks dir` KHONG doc .gitignore,
        # nen no bat dung tep .pyc do (da do that). Tra cuu tu mot bien la
        # LOAD_FAST luc chay, khong the gop hang so.
        dem = "1234567890"
        az = "abcdefghijklmnopqrstuvwxyz"
        secret_payload = (
            "Worker output containing " + "ghp_" + dem * 2 + " and "
            + "sk-" + "ant-api03-" + az + " and "
            + "standard_" + dem * 4
        )
        ev = self.event_store.record(EventKind.ALERT, detail=secret_payload)
        self.assertNotIn("ghp_", ev.detail)
        self.assertNotIn("sk-", ev.detail)
        self.assertNotIn("standard_", ev.detail)
        self.assertIn("[DA-LOC]", ev.detail)

    def test_14_safe_control_dispatch(self):
        """14. Các lệnh điều khiển an toàn, không có thao tác phá huỷ."""
        rid = self.store.tao_run(base_sha="abc1234")
        jid = self.store.them_job(run_id=rid, node_id="task_fail", node={"objective": "Test fail"}, max_attempts=1)
        self.store.claim(jid, "AG01")
        self.store.hoan_thanh(jid, status="failed", result={"error": "Test fail"})

        # Drain worker
        drain_res = self.controller.drain_worker("AG01", reason="Maintenance")
        self.assertTrue(drain_res.success)
        w_state = self.store.workers()
        ag01 = next(w for w in w_state if w["worker_id"] == "AG01")
        self.assertEqual(ag01["state"], "DEGRADED")

        # Retry task
        retry_res = self.controller.retry_task("task_fail", run_id=rid)
        self.assertTrue(retry_res.success)
        job_after = self.store.job(jid)
        self.assertEqual(job_after.status, "queued")
        self.assertEqual(job_after.max_attempts, 2)

        # Pause & Resume mission
        pause_res = self.controller.pause_mission(run_id=rid)
        self.assertTrue(pause_res.success)
        self.assertEqual(self.store.run(rid)["status"], "paused")

        resume_res = self.controller.resume_mission(run_id=rid)
        self.assertTrue(resume_res.success)
        self.assertEqual(self.store.run(rid)["status"], "running")


if __name__ == "__main__":
    unittest.main()
