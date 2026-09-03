"""Bộ đọc trạng thái Router không cào màn hình — Router V4 Control Room.

Nguyên tắc bất biến:
- TUYỆT ĐỐI KHÔNG cào màn hình (no terminal/stdout scraping, no regex on terminal, no OCR).
- Trích xuất 100% từ cấu trúc dữ liệu Router: `PoolStore` (SQLite), `WorkerRegistry`,
  `TaskDag`, `RoutingPolicy`, và `EventStore`.
- Tự động fallback linh hoạt nếu chưa có database hoặc database rỗng.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.packet import redact
from scripts.router_v3.policy import choose_worker, score_worker
from scripts.router_v3.pool.store import PoolStore
from scripts.router_v3.registry import Health, PoolState, WorkerRegistry, WorkerSpec
from scripts.router_v3.control_room.event_store import ControlRoomEvent, EventKind, EventStore


class TaskState(str, Enum):
    WAITING = "WAITING"
    READY = "READY"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAILED = "FAILED"
    RETRY = "RETRY"
    BLOCKED = "BLOCKED"

    @property
    def icon(self) -> str:
        return {
            TaskState.WAITING: "○",
            TaskState.READY: "◌",
            TaskState.RUNNING: "●",
            TaskState.PASS: "✓",
            TaskState.FAILED: "✗",
            TaskState.RETRY: "↻",
            TaskState.BLOCKED: "!",
        }[self]


class WorkerState(str, Enum):
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    COOLDOWN = "COOLDOWN"


@dataclass
class TaskDetailView:
    id: str
    objective: str = ""
    state: TaskState = TaskState.WAITING
    dependencies: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    read_scope: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    risk_class: str = "low"
    expected_output: str = ""
    worker_id: str = ""
    model: str = ""
    provider: str = ""
    attempt: int = 0
    max_attempts: int = 2
    started_at: float = 0.0
    ended_at: float = 0.0
    elapsed_seconds: float = 0.0
    tests_summary: str = "N/A"
    artifacts_count: int = 0
    review_status: str = "N/A"
    failure_reason: str = ""
    raw_log_ref: str = ""
    node_depth: int = 0


@dataclass
class WorkerDetailView:
    id: str
    provider: str = ""
    account: str = "slot 1"
    model: str = ""
    health: str = "healthy"
    state: WorkerState = WorkerState.OFFLINE
    current_task: str = ""
    elapsed_seconds: float = 0.0
    completed_count: int = 0
    failed_count: int = 0
    reliability_pct: float = 100.0
    quota_display: str = "UNKNOWN"
    lane_of: str = ""
    detail: str = ""


@dataclass
class ClaudeLeadView:
    mission: str = "Chưa có mission"
    state: str = "IDLE"
    model: str = "Sonnet 5 (Lead)"
    branch: str = "main"
    worktree: str = ""
    current_task: str = "Chờ lệnh điều phối"
    delegated_count: int = 0
    running_workers: int = 0
    pending_decisions: int = 0
    elapsed_seconds: float = 0.0
    context_display: str = "UNKNOWN"
    heavy_work_warning: bool = False


@dataclass
class MissionView:
    run_id: str = ""
    name: str = "Fanfic World Mission"
    status: str = "IDLE"
    created_at: float = 0.0
    updated_at: float = 0.0
    elapsed_seconds: float = 0.0
    base_sha: str = ""
    mode: str = "normal"
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    running_tasks: int = 0


@dataclass
class RoutingCandidateScore:
    worker_id: str
    total_score: float
    dimensions: Dict[str, float]
    selected: bool = False
    excluded: bool = False
    exclusion_reason: str = ""


@dataclass
class RoutingExplainView:
    task_id: str
    objective: str
    required_capabilities: List[str]
    risk_class: str
    selected_worker: str = ""
    selected_model: str = ""
    candidates: List[RoutingCandidateScore] = field(default_factory=list)
    fallback_candidate: str = ""
    diversity_bonus_applied: bool = False


@dataclass
class ControlRoomSnapshot:
    mission: MissionView
    claude_lead: ClaudeLeadView
    tasks: List[TaskDetailView]
    workers: List[WorkerDetailView]
    events: List[ControlRoomEvent]
    alerts: List[str]
    worktrees: List[Dict[str, str]]
    timestamp: float = 0.0
    #: Loi DOC TRANG THAI, da loc bi mat. KHONG BAO GIO nuot am tham:
    #: mot bang dieu khien hien thi so lieu cu ma khong bao gi ca la thu
    #: te hon mot bang dieu khien bao "khong doc duoc".
    errors: List[str] = field(default_factory=list)
    #: Nguon lay danh sach worker: "fabric_v4" (trang thai runtime THAT) hay
    #: "pool_store" (bang SQLite cua tang V3, co the CU). Hien ra de nguoi
    #: van hanh biet minh dang nhin gi.
    worker_source: str = "" 


class StateReader:
    """Đọc và phóng chiếu trạng thái Router từ SQLite và tệp cấu trúc."""

    def __init__(self, *, root: Optional[Path] = None,
                 store: Optional[PoolStore] = None,
                 event_store: Optional[EventStore] = None,
                 fabric=None, use_fabric: Optional[bool] = None):
        """
        :param use_fabric: lay danh sach worker tu Fabric V4 (trang thai
            runtime THAT) thay vi bang `workers` cua PoolStore.

            MAC DINH THONG MINH, va day la diem quan trong: neu nguoi goi
            TIEM `store` tuong minh thi mac dinh la KHONG dung fabric. Ly do:
            mot `store` duoc tiem nghia la "doc DUNG nguon nay" — kiem thu va
            `proof_run` deu lam vay tren mot thu muc tam. Neu tang doc van
            voi ra trang thai TOAN MAY thi no bo qua nguon duoc tiem, va moi
            bai kiem tro thanh phu thuoc vao may dang chay. Da vap that: mot
            bai kiem dung 1 worker trong store tam nhan ve 11 runtime cua may.

            Truyen `use_fabric=True` de ep dung fabric ke ca khi co store.
        """
        self.root = Path(root) if root else Path.cwd()
        self._store_da_tiem = store is not None
        self.store = store or PoolStore(root=self.root)
        self.event_store = event_store or EventStore(root=self.root)
        self.use_fabric = ((not self._store_da_tiem) if use_fabric is None
                           else bool(use_fabric))
        self._fabric_cache = fabric
        self._fabric_probed_at = time.time() if fabric is not None else 0.0
        self._loi_doc: List[str] = []

    #: Bao lau moi do lai suc khoe THAT cua fabric (giay). Do lai moi lan
    #: ve khung hinh se goi `codex login status` va mot loat HTTP moi ~2s —
    #: vua vo ich vua lam nhieu chinh thu dang do.
    CHU_KY_DO_FABRIC = 20.0

    def _doc_worker(self) -> "tuple[List[Dict], str]":
        """Danh sach worker + NGUON cua no.

        Uu tien Fabric V4 (trang thai runtime THAT, co do suc khoe). Roi ve
        bang `workers` cua PoolStore neu Fabric khong nap duoc — va NOI RO
        minh da roi ve, thay vi hien so lieu cu nhu that.
        """
        import time as _t
        if not self.use_fabric:
            # Nguoi goi da chi dinh nguon tuong minh — ton trong nó.
            return list(self.store.workers()), "pool_store"
        gio = _t.time()
        if (self._fabric_cache is None
                or gio - self._fabric_probed_at > self.CHU_KY_DO_FABRIC):
            try:
                from scripts.router_v4 import fabric_config as _FC
                f, _, _ = _FC.nap(root=self.root, probe=True)
                self._fabric_cache = f
                self._fabric_probed_at = gio
            except Exception as exc:                      # noqa: BLE001
                # KHONG nuot: ghi lai de bang dieu khien hien duoc.
                self._ghi_loi("fabric_probe", exc)
                self._fabric_cache = None

        f = self._fabric_cache
        if f is None:
            return list(self.store.workers()), "pool_store"

        ra: List[Dict] = []
        for r in sorted(f.runtimes.values(), key=lambda x: x.runtime_id):
            d = r.to_dict()
            # Model HIEN THI: runtime V4 ho tro NHIEU model, nen chon model
            # dang chay neu co, khong thi model dau tien no khai. KHONG bia.
            model = (r.supported_models[0] if r.supported_models else "")
            ra.append({
                "worker_id": r.runtime_id,
                "provider": r.provider,
                "model": model,
                "state": d["status"],
                "active_job": ",".join(r.running_tasks),
                "failure_count": r.failed,
                "quota_signal": self._tin_hieu_quota(f, r),
                "account_slot": 1,
                "lane_of": "",
                "detail": (r.needs_provisioning or r.health_detail or ""),
                "auth_profile": r.auth_profile,
                "concurrency": r.concurrency,
            })
        return ra, "fabric_v4"

    @staticmethod
    def _tin_hieu_quota(f, r) -> str:
        """Tin hieu quota CHI khi DA DO THAT SU. Khong doan, khong lam tron.

        `Source.DECLARED` nghia la con so den tu UI/tai lieu nha cung cap va
        CHUA he duoc do bang may. Hien "75%" cho mot con so nhu vay la bia
        so lieu — dung thu ma bai kiem "khong bia so lieu" cua Control Room
        chan, va no da bat duoc ban dau tien cua ham nay. Chi `PROBED` moi
        duoc hien thanh so; con lai la UNKNOWN.
        """
        from scripts.router_v4.runtime import Placement, Source
        for m in r.supported_models:
            pool = f.pool_cua_placement(Placement(r.runtime_id, m))
            if pool is not None and pool.source is Source.PROBED:
                return f"{pool.health:.0%} (probed)"
        return "UNKNOWN"

    def _ghi_loi(self, o_dau: str, exc: BaseException) -> None:
        """Ghi mot loi doc trang thai, DA LOC bi mat, co gioi han."""
        from scripts.router_v3.packet import redact
        msg = redact(f"{o_dau}: {type(exc).__name__}: {exc}")[:200]
        if msg not in self._loi_doc:
            self._loi_doc.append(msg)
        del self._loi_doc[:-5]

    def get_current_branch(self) -> str:
        try:
            res = subprocess.run(["git", "branch", "--show-current"], cwd=str(self.root), capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return "feat/fanfic-control-room"

    def get_worktrees(self) -> List[Dict[str, str]]:
        worktrees = []
        try:
            res = subprocess.run(["git", "worktree", "list"], cwd=str(self.root), capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        p = parts[0]
                        sha = parts[1]
                        branch = parts[2].strip("[]") if len(parts) > 2 else ""
                        worktrees.append({"path": p, "sha": sha, "branch": branch})
        except Exception:
            pass
        return worktrees

    def snapshot(self, *, run_id: Optional[str] = None, event_category: str = "ALL", event_limit: int = 50) -> ControlRoomSnapshot:
        now = time.time()

        # 1. Xác định run hiện tại
        active_run_id = run_id or self.store.run_gan_nhat() or ""
        run_data = self.store.run(active_run_id) if active_run_id else None

        mission = MissionView()
        if run_data:
            c_at = float(run_data.get("created_at") or now)
            mission.run_id = str(run_data.get("run_id") or "")
            mission.name = str(run_data.get("note") or f"Mission {mission.run_id}")
            mission.status = str(run_data.get("status") or "running").upper()
            mission.created_at = c_at
            mission.updated_at = float(run_data.get("updated_at") or now)
            mission.elapsed_seconds = max(0.0, now - c_at)
            mission.base_sha = str(run_data.get("base_sha") or "")
            mission.mode = str(run_data.get("mode") or "normal")

        # 2. Đọc danh sách jobs & dag
        jobs_list = self.store.jobs(active_run_id) if active_run_id else []
        tasks: List[TaskDetailView] = []
        task_id_to_view: Dict[str, TaskDetailView] = {}

        # Nếu có dag_json trong run
        dag_dict = {}
        if run_data and run_data.get("dag_json"):
            try:
                dag_dict = json.loads(run_data["dag_json"])
            except Exception:
                dag_dict = {}

        # Xây dựng danh sách nút từ jobs và dag_json
        nodes_dict = dag_dict.get("nodes", {})
        if isinstance(nodes_dict, list):
            # Format list of nodes
            nodes_dict = {n.get("id"): n for n in nodes_dict if isinstance(n, dict) and "id" in n}

        all_node_ids = list(nodes_dict.keys())
        for j in jobs_list:
            if j.node_id not in all_node_ids:
                all_node_ids.append(j.node_id)

        # Map trạng thái
        for nid in all_node_ids:
            job = next((j for j in jobs_list if j.node_id == nid), None)
            node_cfg = nodes_dict.get(nid, {})
            if job and job.node:
                node_cfg = {**node_cfg, **job.node}

            # Map status
            status = job.status.lower() if job else "waiting"
            t_state = TaskState.WAITING
            if status == "running":
                t_state = TaskState.RUNNING
            elif status in ("ok", "pass", "completed", "done"):
                t_state = TaskState.PASS
            elif status in ("failed", "error", "timeout"):
                if job and job.attempt < job.max_attempts:
                    t_state = TaskState.RETRY
                else:
                    t_state = TaskState.FAILED
            elif status == "blocked":
                t_state = TaskState.BLOCKED
            elif status == "queued":
                t_state = TaskState.READY

            # Elapsed
            dur = job.duration_seconds if job else 0.0

            # Tests summary
            tests = "N/A"
            if job and job.validation:
                v = job.validation
                if "tests" in v:
                    tests = str(v["tests"])
                elif "passed" in v:
                    tests = "PASS" if v["passed"] else "FAIL"

            # Artifacts
            art_count = 0
            if job and job.result:
                r = job.result
                if "artifacts" in r and isinstance(r["artifacts"], list):
                    art_count = len(r["artifacts"])
                elif "diff" in r:
                    art_count = 1

            # Failure reason
            fail_reason = ""
            if job and job.result and isinstance(job.result, dict):
                fail_reason = str(job.result.get("error") or job.result.get("failure_reason") or "")
            if not fail_reason and job and job.validation and not job.validation.get("passed", True):
                fail_reason = str(job.validation.get("reason") or "Validation check failed")

            view = TaskDetailView(
                id=nid,
                objective=str(node_cfg.get("objective") or nid),
                state=t_state,
                dependencies=list(node_cfg.get("dependencies") or []),
                write_scope=list(node_cfg.get("write_scope") or []),
                read_scope=list(node_cfg.get("read_scope") or []),
                required_capabilities=list(node_cfg.get("required_capabilities") or []),
                risk_class=str(node_cfg.get("risk_class") or "low"),
                expected_output=str(node_cfg.get("expected_output") or ""),
                worker_id=job.worker_id if job else "",
                attempt=job.attempt if job else 0,
                max_attempts=job.max_attempts if job else 2,
                started_at=job.started_at if job else 0.0,
                ended_at=job.ended_at if job else 0.0,
                elapsed_seconds=dur,
                tests_summary=tests,
                artifacts_count=art_count,
                failure_reason=redact(fail_reason),
                raw_log_ref=f".router/pool/jobs/{nid}.log",
            )
            tasks.append(view)
            task_id_to_view[nid] = view

        # Tính toán phân cấp độ sâu DAG
        def _tinh_do_sau(tid: str, visited: Set[str]) -> int:
            if tid in visited:
                return 0
            visited.add(tid)
            tv = task_id_to_view.get(tid)
            if not tv or not tv.dependencies:
                return 0
            return 1 + max(_tinh_do_sau(d, visited.copy()) for d in tv.dependencies if d in task_id_to_view)

        for t in tasks:
            t.node_depth = _tinh_do_sau(t.id, set())

        # Sắp xếp tasks theo độ sâu và id
        tasks.sort(key=lambda x: (x.node_depth, x.id))

        # Cập nhật số liệu mission
        mission.total_tasks = len(tasks)
        mission.completed_tasks = sum(1 for t in tasks if t.state == TaskState.PASS)
        mission.failed_tasks = sum(1 for t in tasks if t.state == TaskState.FAILED)
        mission.running_tasks = sum(1 for t in tasks if t.state == TaskState.RUNNING)

        # 3. Đọc workers — NGUON LA FABRIC V4 THAT
        #
        # Ban dau doan nay doc bang `workers` cua `PoolStore` (SQLite tang
        # V3). Bang do chi duoc ghi khi mot lan chay cua tang pool V3 dong
        # bo no, nen tren mot he da chuyen sang Router V4 no hoac RONG hoac
        # CU — va bang dieu khien se hien AG02..AG08 la OFFLINE trong khi
        # launcher da-tai-khoan that su dang chay ca 8. Fabric V4 la nguon
        # su that ve runtime; bang SQLite chi la du phong.
        db_workers, nguon = self._doc_worker()
        workers: List[WorkerDetailView] = []
        running_worker_count = 0

        for w in db_workers:
            wid = w.get("worker_id", "")
            st_raw = str(w.get("state") or "OFFLINE").upper()
            w_state = WorkerState.OFFLINE
            if st_raw in ("READY", "IDLE"):
                w_state = WorkerState.IDLE
            elif st_raw == "BUSY":
                w_state = WorkerState.BUSY
                running_worker_count += 1
            elif st_raw == "QUOTA_COOLDOWN":
                w_state = WorkerState.COOLDOWN
            elif st_raw in ("DEGRADED", "RATE_LIMITED"):
                w_state = WorkerState.DEGRADED

            # Quota telemetry (chỉ khi có machine-readable signal, không cào GUI)
            q_sig = w.get("quota_signal")
            q_disp = str(q_sig) if q_sig else "UNKNOWN"

            # Reliability
            fc = int(w.get("failure_count") or 0)
            completed_est = max(0, 10 - fc)
            rel = round(max(0.0, min(100.0, 100.0 - (fc * 15.0))), 1)

            # Account display
            slot = w.get("account_slot", 1)
            acc_disp = f"slot {slot}" if slot else (f"làn {w.get('lane_of')}" if w.get("lane_of") else "slot 1")

            workers.append(
                WorkerDetailView(
                    id=wid,
                    provider=str(w.get("provider") or ""),
                    account=acc_disp,
                    model=str(w.get("model") or ""),
                    health="healthy" if fc == 0 else ("degraded" if fc < 3 else "failed"),
                    state=w_state,
                    current_task=str(w.get("active_job") or ""),
                    elapsed_seconds=0.0,
                    completed_count=completed_est,
                    failed_count=fc,
                    reliability_pct=rel,
                    quota_display=q_disp,
                    lane_of=str(w.get("lane_of") or ""),
                    detail=str(w.get("detail") or ""),
                )
            )

        # 4. Phóng chiếu Claude Lead
        lead_worker = next((w for w in workers if "CLAUDE" in w.id.upper() or w.provider == "claude"), None)
        claude_lead = ClaudeLeadView(
            mission=mission.name,
            branch=self.get_current_branch(),
            delegated_count=len(jobs_list),
            running_workers=running_worker_count,
            elapsed_seconds=mission.elapsed_seconds,
        )
        if lead_worker:
            claude_lead.model = lead_worker.model or "Sonnet 5 (Lead)"
            claude_lead.state = "DELEGATING" if mission.running_tasks > 0 else ("INTEGRATING" if mission.completed_tasks > 0 else "PLANNING")
            claude_lead.current_task = lead_worker.current_task or "Orchestrating task DAG"

        # Evidence-based check for ORCHESTRATOR_HEAVY_WORK warning
        # Nếu Claude Lead đang tự chạy 1 task nặng (is_write/implement) trong khi có worker khác rảnh rỗi
        idle_capable_workers = any(w.state == WorkerState.IDLE and "AG" in w.id for w in workers)
        if lead_worker and lead_worker.current_task and idle_capable_workers:
            active_job_lead = next((j for j in jobs_list if j.worker_id == lead_worker.id and j.status == "running"), None)
            if active_job_lead and active_job_lead.node:
                req_caps = active_job_lead.node.get("required_capabilities", [])
                if any(c in req_caps for c in ("implement", "frontend", "recon")):
                    claude_lead.heavy_work_warning = True

        # 5. Đọc sự kiện
        events = self.event_store.get_events(run_id=active_run_id, category=event_category, limit=event_limit)

        # 6. Trích xuất Alerts
        alerts = []
        for e in events:
            if e.level in ("WARNING", "ERROR", "ALERT") or e.kind in (EventKind.TASK_FAILED, EventKind.ALERT, EventKind.WORKER_DEGRADED):
                alerts.append(f"[{e.kind}] {e.detail}")
            if len(alerts) >= 5:
                break

        if claude_lead.heavy_work_warning:
            alerts.insert(0, "ORCHESTRATOR_HEAVY_WORK: Claude Lead is doing implementation while eligible workers are IDLE.")

        return ControlRoomSnapshot(
            mission=mission,
            claude_lead=claude_lead,
            tasks=tasks,
            workers=workers,
            events=events,
            alerts=alerts,
            worktrees=self.get_worktrees(),
            errors=list(self._loi_doc),
            worker_source=nguon,
            timestamp=now,
        )

    def explain_routing(self, task_id: str, *, run_id: Optional[str] = None) -> RoutingExplainView:
        """Giải thích chi tiết quyết định định tuyến theo mọi chiều chấm điểm."""
        active_run_id = run_id or self.store.run_gan_nhat() or ""
        job = self.store.job_theo_node(active_run_id, task_id) if active_run_id else None

        node_cfg = job.node if job and job.node else {"id": task_id}
        node = TaskNode(
            id=task_id,
            objective=node_cfg.get("objective", task_id),
            required_capabilities=tuple(node_cfg.get("required_capabilities", ())),
            risk_class=RiskClass(node_cfg.get("risk_class", "low")),
            preferred_provider=node_cfg.get("preferred_provider"),
        )

        reg = WorkerRegistry()
        db_workers = self.store.workers()
        for w in db_workers:
            wid = w.get("worker_id", "")
            caps_raw = w.get("capabilities")
            if isinstance(caps_raw, list):
                caps = caps_raw
            elif isinstance(caps_raw, str):
                try:
                    caps = json.loads(caps_raw)
                except Exception:
                    caps = [c.strip() for c in caps_raw.split(",") if c.strip()]
            else:
                caps = []
            if isinstance(caps, list) and caps and all(isinstance(c, str) and len(c) == 1 for c in caps):
                joined = "".join(caps)
                try:
                    caps = json.loads(joined)
                except Exception:
                    caps = [joined]
            prov = w.get("provider", "")
            spec = WorkerSpec(
                worker_id=wid,
                provider_family=prov,
                execution_type="local_cli",
                pool="default",
                capabilities=frozenset(caps),
                trusted_for_high_risk=bool(w.get("auth_realm") or "high" in wid.lower()),
            )
            reg.register(spec)
            st_raw = w.get("state", "OFFLINE").upper()
            if st_raw in ("READY", "IDLE"):
                reg.set_health(wid, Health.HEALTHY)
            elif st_raw == "BUSY":
                reg.set_health(wid, Health.HEALTHY)
                reg.mark_started(wid, w.get("active_job", "") or "job")
            else:
                reg.set_health(wid, Health.UNAVAILABLE)

        candidates: List[RoutingCandidateScore] = []
        high_risk = node.risk_class is RiskClass.HIGH

        for wid in reg.ids():
            spec = reg.spec(wid)
            excluded = False
            reason = ""

            reasons = []
            if "security_review" in node.required_capabilities and spec.provider_family == "codex":
                excluded = True
                reasons.append("Hard guard: security_review blocked on Codex")
            if high_risk and not spec.trusted_for_high_risk:
                excluded = True
                reasons.append("Untrusted for HIGH risk class")
            if node.required_capabilities and not (set(node.required_capabilities) & set(spec.capabilities)):
                excluded = True
                reasons.append(f"Missing required capabilities: {list(node.required_capabilities)}")
            reason = "; ".join(reasons)

            sc = score_worker(spec, reg, node)
            dims = {
                "capability_fit": sc.capability_fit,
                "risk_fit": sc.risk_fit,
                "historical_success": sc.historical_success_rate,
                "expected_latency": sc.expected_latency,
                "current_load": sc.current_load,
                "quota_remaining": sc.quota_remaining,
                "provider_preference": sc.provider_preference,
                "total": sc.total,
            }
            candidates.append(
                RoutingCandidateScore(
                    worker_id=wid,
                    total_score=sc.total if not excluded else -999.0,
                    dimensions=dims,
                    excluded=excluded,
                    exclusion_reason=reason,
                )
            )

        # Sort non-excluded descending by total score
        valid_candidates = [c for c in candidates if not c.excluded]
        valid_candidates.sort(key=lambda x: x.total_score, reverse=True)

        selected_id = valid_candidates[0].worker_id if valid_candidates else ""
        fallback_id = valid_candidates[1].worker_id if len(valid_candidates) > 1 else ""

        for c in candidates:
            if c.worker_id == selected_id:
                c.selected = True

        return RoutingExplainView(
            task_id=task_id,
            objective=node.objective,
            required_capabilities=list(node.required_capabilities),
            risk_class=node.risk_class.value,
            selected_worker=selected_id,
            candidates=candidates,
            fallback_candidate=fallback_id,
        )
