"""Hệ thống điều khiển an toàn cho người vận hành — Router V4 Control Room.

RANH GIỚI AN TOÀN TUYỆT ĐỐI:
- KHÔNG có hành động huỷ hoại trực tiếp một phím (destructive operations must NOT be one-key).
- CẤM: publish content, delete content, delete branch, reset --hard, delete worktree,
  kill arbitrary process, thao túng credential.
- Mọi thao tác điều khiển (Drain, Retry, Pause, Resume) đều được ghi nhật ký kiểm toán (audit log)
  vào EventStore.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.router_v3.packet import redact
from scripts.router_v3.pool.store import PoolStore
from scripts.router_v3.control_room.event_store import EventKind, EventLevel, EventStore
from scripts.router_v3.control_room.state_reader import RoutingExplainView, StateReader


class ControlError(RuntimeError):
    pass


@dataclass
class OperationResult:
    success: bool
    message: str
    action: str
    target: str = ""
    audit_event_id: int = 0


class SafeController:
    """Thực thi các lệnh điều phối an toàn trên Router state."""

    def __init__(self, *, root: Optional[Path] = None, store: Optional[PoolStore] = None, event_store: Optional[EventStore] = None, state_reader: Optional[StateReader] = None):
        self.root = Path(root) if root else Path.cwd()
        self.store = store or PoolStore(root=self.root)
        self.event_store = event_store or EventStore(root=self.root)
        self.state_reader = state_reader or StateReader(root=self.root, store=self.store, event_store=self.event_store)

    def drain_worker(self, worker_id: str, *, reason: str = "Operator drain request") -> OperationResult:
        """Đưa worker vào trạng thái rút lui an toàn (không giao việc mới)."""
        w_id = worker_id.strip()
        if not w_id:
            return OperationResult(False, "Worker ID không được để trống", "drain")

        try:
            # Ghi trạng thái worker vào SQLite
            hang = {
                "worker_id": w_id,
                "state": "DEGRADED",
                "detail": f"DRAINED: {reason}",
            }
            self.store.ghi_worker(hang)

            ev = self.event_store.record(
                EventKind.WORKER_DEGRADED,
                level=EventLevel.WARNING,
                worker_id=w_id,
                detail=f"Operator DRAINED worker {w_id}: {reason}",
            )
            return OperationResult(True, f"Đã drain worker {w_id} an toàn", "drain", w_id, ev.id)
        except Exception as e:
            return OperationResult(False, f"Lỗi khi drain worker: {e}", "drain", w_id)

    def undrain_worker(self, worker_id: str) -> OperationResult:
        """Mở lại worker sau khi đã drain."""
        w_id = worker_id.strip()
        if not w_id:
            return OperationResult(False, "Worker ID không được để trống", "undrain")

        try:
            hang = {
                "worker_id": w_id,
                "state": "READY",
                "detail": "Ready for dispatch",
            }
            self.store.ghi_worker(hang)

            ev = self.event_store.record(
                EventKind.WORKER_ONLINE,
                level=EventLevel.INFO,
                worker_id=w_id,
                detail=f"Operator restored worker {w_id} to READY",
            )
            return OperationResult(True, f"Đã phục hồi worker {w_id} sẵn sàng", "undrain", w_id, ev.id)
        except Exception as e:
            return OperationResult(False, f"Lỗi khi phục hồi worker: {e}", "undrain", w_id)

    def retry_task(self, task_id: str, *, run_id: Optional[str] = None) -> OperationResult:
        """Thử lại một công việc bị lỗi sau khi đã hết lượt tự động."""
        t_id = task_id.strip()
        if not t_id:
            return OperationResult(False, "Task ID không được để trống", "retry")

        active_run_id = run_id or self.store.run_gan_nhat() or ""
        job = self.store.job_theo_node(active_run_id, t_id) if active_run_id else None

        if not job:
            return OperationResult(False, f"Không tìm thấy job cho nút {t_id}", "retry", t_id)

        try:
            # Nới trần lượt thử và đưa về hàng đợi
            self.store.dat_max_attempts(job.job_id, job.max_attempts + 1)
            ok = self.store.tra_ve_hang_doi(job.job_id, ly_do="Operator safe retry request")

            if ok:
                ev = self.event_store.record(
                    EventKind.TASK_RETRY,
                    level=EventLevel.INFO,
                    run_id=active_run_id,
                    task_id=t_id,
                    detail=f"Operator requested RETRY for {t_id} (attempt max bumped to {job.max_attempts + 1})",
                )
                return OperationResult(True, f"Đã đưa task {t_id} vào hàng đợi thử lại", "retry", t_id, ev.id)
            else:
                return OperationResult(False, f"Không thể requeue task {t_id}", "retry", t_id)
        except Exception as e:
            return OperationResult(False, f"Lỗi khi retry task: {e}", "retry", t_id)

    def pause_mission(self, *, run_id: Optional[str] = None) -> OperationResult:
        """Tạm dừng mission đang chạy."""
        active_run_id = run_id or self.store.run_gan_nhat() or ""
        if not active_run_id:
            return OperationResult(False, "Không có mission nào đang hoạt động để tạm dừng", "pause")

        try:
            self.store.dat_trang_thai_run(active_run_id, "paused")
            ev = self.event_store.record(
                EventKind.ALERT,
                level=EventLevel.WARNING,
                run_id=active_run_id,
                detail=f"Mission {active_run_id} PAUSED by operator",
            )
            return OperationResult(True, f"Đã tạm dừng mission {active_run_id}", "pause", active_run_id, ev.id)
        except Exception as e:
            return OperationResult(False, f"Lỗi khi tạm dừng mission: {e}", "pause", active_run_id)

    def resume_mission(self, *, run_id: Optional[str] = None) -> OperationResult:
        """Tiếp tục mission sau khi tạm dừng."""
        active_run_id = run_id or self.store.run_gan_nhat() or ""
        if not active_run_id:
            return OperationResult(False, "Không có mission nào để tiếp tục", "resume")

        try:
            self.store.dat_trang_thai_run(active_run_id, "running")
            ev = self.event_store.record(
                EventKind.MISSION_STARTED,
                level=EventLevel.INFO,
                run_id=active_run_id,
                detail=f"Mission {active_run_id} RESUMED by operator",
            )
            return OperationResult(True, f"Đã tiếp tục mission {active_run_id}", "resume", active_run_id, ev.id)
        except Exception as e:
            return OperationResult(False, f"Lỗi khi tiếp tục mission: {e}", "resume", active_run_id)

    def explain_task(self, task_id: str, *, run_id: Optional[str] = None) -> RoutingExplainView:
        """Xem phân tích định tuyến cho một task."""
        return self.state_reader.explain_routing(task_id, run_id=run_id)

    def get_task_log(self, task_id: str, *, max_lines: int = 150) -> str:
        """Đọc an toàn log của task được tham chiếu, lọc sạch bí mật."""
        log_paths = [
            self.root / ".router" / "pool" / "jobs" / f"{task_id}.log",
            self.root / ".router" / "pool" / "daemon.log",
        ]
        found_content = ""
        for lp in log_paths:
            if lp.exists():
                try:
                    with open(lp, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        matched = [line for line in lines if task_id in line]
                        if matched:
                            found_content = "".join(matched[-max_lines:])
                            break
                        elif not found_content:
                            found_content = "".join(lines[-max_lines:])
                except Exception:
                    pass

        if not found_content:
            found_content = f"Chưa có tệp nhật ký trực tiếp cho nút '{task_id}'. Tham chiếu tệp: .router/pool/jobs/{task_id}.log"

        return redact(found_content)
