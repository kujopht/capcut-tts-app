"""Mặt tiền điều phối — Router V4.

ĐÂY LÀ THỨ CLAUDE LEAD GỌI. Nó yêu cầu NĂNG LỰC, không yêu cầu tài khoản:

    fab.request([
        Need("2 worker thực thi mạnh", coding=True, repo_write=True,
             reasoning=Reasoning.HIGH, count=2),
        Need("1 worker phân tích kho giá rẻ", repo_read=True,
             latency_priority=Priority.HIGH),
        Need("1 reviewer đa phương thức", image=True),
        Need("1 reviewer độc lập", coding=True, exclude_families=("gemini",)),
    ])

và bộ lập lịch trả về các placement THẬT. Không nơi nào bên gọi gõ "AG03"
hay "gemini-3.8-flash-high".

`run_mission` chạy một DAG: mở khoá theo TỪNG NÚT (không theo lớp — chờ hết
một lớp bắt mọi lớp chịu thời gian của nút chậm nhất), lease cho mỗi runtime,
thử lại có chặn rồi đổi placement, và leo thang chế độ theo `modes.py`.

NGÂN SÁCH NGỮ CẢNH: hàm này trả về PHONG BÌ, không trả về bản ghi thô. Nhật
ký thô nằm trên đĩa sau `raw_log_ref`.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from scripts.router_v3.worktree import WorktreeManager
from scripts.router_v4 import fabric_config as FC
from scripts.router_v4.capabilities import Priority, Reasoning, Requirements
from scripts.router_v4.contract import TaskContract
from scripts.router_v4.envelope import RawLogStore, ResultEnvelope
from scripts.router_v4.executor import Executor, ExecutionResult
from scripts.router_v4.history import BenchmarkStore
from scripts.router_v4.leases import LeaseStore, owner_id
from scripts.router_v4.mission import MissionDag, MissionPlan, plan
from scripts.router_v4.modes import (EscalationPolicy, Mode, ModeDecision,
                                     chon_che_do, hop_dong_gia_thuyet,
                                     hop_dong_review)
from scripts.router_v4.runtime import Fabric, Placement, RuntimeStatus
from scripts.router_v4.scheduler import (Decision, Demand, NoEligiblePlacement,
                                         Scheduler, Weights)

#: Bao nhieu luot cho MOI viec truoc khi bo cuoc. Luot 1 hong -> thu lai
#: (loi thoang qua); tu luot 2 -> DOI placement. Huu han co chu dich.
MAX_ATTEMPTS = 3


@dataclass
class Need:
    """Một YÊU CẦU NĂNG LỰC do Claude lead phát ra. Không tên tài khoản."""

    label: str
    count: int = 1
    coding: bool = False
    repo_read: bool = False
    repo_write: bool = False
    shell: bool = False
    multimodal: bool = False
    image: bool = False
    video: bool = False
    audio: bool = False
    long_context: bool = False
    structured_output: bool = False
    reasoning_level: Reasoning = Reasoning.MEDIUM
    latency_priority: Priority = Priority.BALANCED
    quality_priority: Priority = Priority.BALANCED
    exclude_families: Tuple[str, ...] = ()

    def to_requirements(self) -> Requirements:
        return Requirements(
            coding=self.coding, repo_read=self.repo_read,
            repo_write=self.repo_write, shell=self.shell,
            multimodal=self.multimodal, image=self.image, video=self.video,
            audio=self.audio, long_context=self.long_context,
            structured_output=self.structured_output,
            reasoning_level=self.reasoning_level,
            latency_priority=self.latency_priority,
            quality_priority=self.quality_priority,
            exclude_families=self.exclude_families)


@dataclass
class Allocation:
    need: Need
    placements: List[Placement] = field(default_factory=list)
    shortfall: int = 0
    decisions: List[Decision] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"label": self.need.label, "requested": self.need.count,
                "granted": [p.key for p in self.placements],
                "shortfall": self.shortfall,
                "reasons": [d.reason for d in self.decisions]}


@dataclass
class TaskOutcome:
    task_id: str
    envelope: ResultEnvelope
    placement: Optional[Placement]
    attempts: int
    mode: str = "solo"
    review: Optional[ResultEnvelope] = None
    hypotheses: List[ResultEnvelope] = field(default_factory=list)
    decision: Optional[Decision] = None

    @property
    def ok(self) -> bool:
        return self.envelope.ok

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id, "ok": self.ok, "mode": self.mode,
            "placement": self.placement.key if self.placement else None,
            "attempts": self.attempts,
            "envelope": self.envelope.to_dict(),
            "review": self.review.to_dict() if self.review else None,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "decision": self.decision.to_dict() if self.decision else None,
        }


class RouterV4:
    """Mặt tiền. Dựng rẻ; không khởi động tiến trình worker nào."""

    def __init__(self, *, root: Optional[Path] = None,
                 fabric: Optional[Fabric] = None,
                 weights: Optional[Weights] = None,
                 escalation: Optional[EscalationPolicy] = None,
                 executor: Optional[Executor] = None,
                 leases: Optional[LeaseStore] = None,
                 history: Optional[BenchmarkStore] = None,
                 probe: bool = True):
        self.root = Path(root) if root else Path.cwd()
        if fabric is None:
            fabric, w, esc = FC.nap(root=self.root, probe=probe)
            weights = weights or w
            escalation = escalation or esc
        self.fabric = fabric
        self.weights = weights or Weights()
        self.escalation = escalation or EscalationPolicy()
        self.history = history if history is not None else \
            BenchmarkStore(root=self.root)
        self.scheduler = Scheduler(self.fabric, weights=self.weights,
                                   history=self.history)
        self.executor = executor if executor is not None else \
            Executor(self.fabric, root=self.root, history=self.history)
        self.leases = leases if leases is not None else LeaseStore(root=self.root)
        self.owner = owner_id()
        self._khoa = threading.Lock()
        self.decisions: Dict[str, Decision] = {}

    # -- 1. Yeu cau NANG LUC ------------------------------------------------

    def request(self, needs: Sequence[Need], *,
                demand: Optional[Demand] = None,
                now: Optional[float] = None) -> List[Allocation]:
        """Cấp placement cho một danh sách nhu cầu NĂNG LỰC.

        Cấp lần lượt và LOẠI DẦN placement đã cấp: hai "worker thực thi mạnh"
        phải là hai chỗ khác nhau, nếu không "2 worker" chỉ là một worker
        được đếm hai lần.
        """
        da_cap: Set[str] = set()
        ra: List[Allocation] = []
        for n in needs:
            a = Allocation(need=n)
            for i in range(max(1, n.count)):
                c = TaskContract(
                    task_id=f"need-{len(ra)}-{i}",
                    objective=f"(cấp phát năng lực) {n.label}",
                    requirements=n.to_requirements())
                d = self.scheduler.decide(c, exclude=tuple(da_cap),
                                          demand=demand, now=now)
                a.decisions.append(d)
                if d.selected is None:
                    a.shortfall += 1
                    continue
                a.placements.append(d.selected)
                # Loai theo RUNTIME, khong theo placement: hai model tren
                # CUNG mot tai khoan khong phai hai worker song song doc lap
                # — chung dung chung han muc dong thoi va chung quota.
                da_cap.add(d.selected.runtime_id)
            ra.append(a)
        return ra

    # -- 2. Lap ke hoach ----------------------------------------------------

    def plan(self, contracts, *, mission_id: str = "") -> MissionPlan:
        return plan(contracts, mission_id=mission_id,
                    ceiling=max(1, sum(r.concurrency
                                       for r in self.fabric.runtimes.values()
                                       if r.provisioned)))

    # -- 3. Chay mot mission ------------------------------------------------

    def run_mission(self, mp: MissionPlan, *, base_sha: str = "",
                    max_parallel: int = 4, timeout: float = 3600.0,
                    on_event: Optional[Callable[[str, Dict], None]] = None
                    ) -> Dict[str, TaskOutcome]:
        """Chạy DAG. Mở khoá theo TỪNG NÚT, không theo lớp."""
        d = mp.dag
        ket_qua: Dict[str, TaskOutcome] = {}
        xong: Set[str] = set()
        hong: Set[str] = set()
        dang: Dict[str, threading.Thread] = {}
        het = time.time() + timeout

        def _phat(kind: str, payload: Dict) -> None:
            if on_event:
                try:
                    on_event(kind, payload)
                except Exception:                         # noqa: BLE001
                    pass

        while time.time() < het:
            with self._khoa:
                da_xong = set(xong)
                dang_id = set(dang)
            san = [c for c in d.ready(da_xong, dang_id)
                   if not (set(c.dependencies) & hong)]
            # Nut co phu thuoc HONG thi khong bao gio chay — danh dau ngay.
            for c in d.ready(da_xong, dang_id):
                if set(c.dependencies) & hong:
                    with self._khoa:
                        ket_qua[c.task_id] = TaskOutcome(
                            task_id=c.task_id, placement=None, attempts=0,
                            envelope=ResultEnvelope(
                                task_id=c.task_id, status="blocked",
                                failure_reason="dependency_failed",
                                summary="phụ thuộc hỏng — không dispatch"))
                        xong.add(c.task_id)
                        hong.add(c.task_id)

            for c in san:
                with self._khoa:
                    if len(dang) >= max_parallel:
                        break
                    if c.task_id in dang or c.task_id in xong:
                        continue
                    dang[c.task_id] = None                # type: ignore[assignment]
                nhu_cau = Demand.from_contracts(d.pending_contracts(da_xong))
                t = threading.Thread(
                    target=self._chay_mot_nut,
                    args=(c, d, ket_qua, xong, hong, dang, nhu_cau, base_sha,
                          _phat),
                    name=f"v4-{c.task_id}", daemon=True)
                with self._khoa:
                    dang[c.task_id] = t
                t.start()

            with self._khoa:
                con_chay = [t for t in dang.values() if t is not None]
                da_het = len(xong) >= len(d)
            if da_het and not con_chay:
                break
            if not con_chay and not san and not da_het:
                # Khong co gi chay, khong co gi san sang, ma chua xong ->
                # be tac. Thoat thay vi quay vong den het gio.
                break
            time.sleep(0.4)

        for tid in d.ids():
            if tid not in ket_qua:
                ket_qua[tid] = TaskOutcome(
                    task_id=tid, placement=None, attempts=0,
                    envelope=ResultEnvelope(
                        task_id=tid, status="failed",
                        failure_reason="not_scheduled",
                        summary="chưa từng được lập lịch (hết giờ hoặc bế tắc)"))
        return ket_qua

    def _chay_mot_nut(self, c: TaskContract, d: MissionDag,
                      ket_qua: Dict[str, TaskOutcome], xong: Set[str],
                      hong: Set[str], dang: Dict[str, threading.Thread],
                      nhu_cau: Demand, base_sha: str, phat) -> None:
        try:
            kq = self.run_task(c, demand=nhu_cau, base_sha=base_sha,
                               dependency_summaries=self._tom_tat(c, ket_qua),
                               on_event=phat)
        except Exception as exc:                          # noqa: BLE001
            kq = TaskOutcome(
                task_id=c.task_id, placement=None, attempts=0,
                envelope=ResultEnvelope(
                    task_id=c.task_id, status="failed",
                    failure_reason="orchestrator_exception",
                    summary=f"{type(exc).__name__}: {exc}"[:400]))
        with self._khoa:
            ket_qua[c.task_id] = kq
            xong.add(c.task_id)
            if not kq.ok:
                hong.add(c.task_id)
            dang.pop(c.task_id, None)

    def _tom_tat(self, c: TaskContract,
                 ket_qua: Dict[str, TaskOutcome]) -> Dict[str, str]:
        """Tóm tắt phụ thuộc — KHÔNG phải hội thoại của chúng. Đây là điểm
        giữ ngữ cảnh worker nhỏ: một nút tích hợp đọc bốn dòng, không phải
        bốn bản ghi đầy đủ."""
        ra: Dict[str, str] = {}
        with self._khoa:
            for dep in c.dependencies:
                o = ket_qua.get(dep)
                if o is not None:
                    ra[dep] = o.envelope.summary[:400]
        return ra

    # -- 4. Chay MOT viec, co leo thang + thu lai ---------------------------

    def run_task(self, c: TaskContract, *, demand: Optional[Demand] = None,
                 base_sha: str = "",
                 dependency_summaries: Optional[Dict[str, str]] = None,
                 on_event=None) -> TaskOutcome:
        so_lan_hong = self._dem_hong_truoc(c)
        cd = chon_che_do(c, policy=self.escalation, failure_history=so_lan_hong)
        if on_event:
            on_event("mode", {"task_id": c.task_id, **cd.to_dict()})

        if cd.mode is Mode.PARALLEL_HYPOTHESES:
            return self._chay_gia_thuyet(c, cd, demand=demand,
                                         base_sha=base_sha, on_event=on_event)

        kq = self._chay_co_thu_lai(c, demand=demand, base_sha=base_sha,
                                   dependency_summaries=dependency_summaries,
                                   on_event=on_event)
        kq.mode = cd.mode.value

        if cd.mode is Mode.PRIMARY_CRITIC and kq.ok and kq.placement:
            ho_tac_gia = self.fabric.model(kq.placement.model_id).model_family
            hd_review = hop_dong_review(c, author_family=ho_tac_gia)
            r = self._chay_co_thu_lai(
                hd_review, demand=demand, base_sha=base_sha,
                dependency_summaries={c.task_id: kq.envelope.summary},
                author_family=ho_tac_gia, on_event=on_event)
            kq.review = r.envelope
            # Review tim ra van de KHONG tu dong lam viec that bai — no la
            # thong tin cho nguoi tich hop. Nhung no PHAI hien ra o phong bi,
            # neu khong ca lượt review chi la tot tien.
            if r.envelope.findings:
                kq.envelope.findings.extend(
                    f"[review/{r.envelope.model}] {x}"
                    for x in r.envelope.findings[:10])
        return kq

    def _chay_co_thu_lai(self, c: TaskContract, *, demand, base_sha: str,
                         dependency_summaries=None, author_family: str = "",
                         on_event=None) -> TaskOutcome:
        da_thu: List[str] = []
        cuoi: Optional[ExecutionResult] = None
        chon: Optional[Placement] = None
        qd: Optional[Decision] = None
        for luot in range(1, MAX_ATTEMPTS + 1):
            # Luot 1 khong loai ai; tu luot 2 loai moi placement DA THU.
            loai = tuple(da_thu) if luot >= 2 else ()
            qd = self.scheduler.decide(c, exclude=loai, demand=demand,
                                       author_family=author_family)
            self.decisions[c.task_id] = qd
            if on_event:
                on_event("decision", qd.to_dict())
            if qd.selected is None:
                break
            chon = qd.selected
            lease = self.leases.acquire(chon.runtime_id, self.owner,
                                        task_id=c.task_id)
            if lease is None:
                # Runtime dang bi tien trinh khac giu — thu placement khac
                # thay vi cho, va KHONG tinh la mot luot hong.
                da_thu.append(chon.key)
                continue
            try:
                self.fabric.mark_started(chon.runtime_id, c.task_id)
                cuoi = self.executor.run(
                    c, chon, base_sha=base_sha,
                    dependency_summaries=dependency_summaries,
                    attempt=luot, reassigned=(luot >= 2))
            finally:
                self.fabric.mark_finished(
                    chon.runtime_id, c.task_id,
                    ok=bool(cuoi and cuoi.ok), model_id=chon.model_id,
                    seconds=cuoi.envelope.duration if cuoi else 0.0)
                self.leases.release(chon.runtime_id, self.owner)
            if cuoi.ok:
                break
            da_thu.append(chon.key)
            # Hong CONG BAO MAT khong bao gio thu lai — thu lai chi tang co
            # hoi lot mot thay doi chua thu giong credential.
            if cuoi.envelope.failure_reason == "security_gate":
                break

        if cuoi is None:
            return TaskOutcome(
                task_id=c.task_id, placement=chon, attempts=len(da_thu),
                decision=qd,
                envelope=ResultEnvelope(
                    task_id=c.task_id, status="failed",
                    failure_reason="no_eligible_placement",
                    summary=(qd.reason if qd else "không có ứng viên")[:600]))
        return TaskOutcome(task_id=c.task_id, placement=chon,
                           attempts=max(1, len(da_thu) if not cuoi.ok
                                        else len(da_thu) + 1),
                           envelope=cuoi.envelope, decision=qd)

    def _chay_gia_thuyet(self, c: TaskContract, cd: ModeDecision, *, demand,
                         base_sha: str, on_event=None) -> TaskOutcome:
        """N chẩn đoán song song, mỗi cái trên một HỌ MODEL khác nhau nếu có.

        Chúng chỉ ĐỌC — cho ba worker cùng sửa một thứ rồi hợp nhất là cách
        chắc chắn nhất tạo ra ba nhánh xung đột. Người tích hợp (Claude lead)
        so bằng chứng.
        """
        hds = hop_dong_gia_thuyet(c, cd.replicas)
        ra: List[ResultEnvelope] = []
        luong: List[threading.Thread] = []
        khoa = threading.Lock()
        da_dung_ho: Set[str] = set()

        def _mot(hd: TaskContract) -> None:
            with khoa:
                loai_ho = tuple(da_dung_ho)
            hd2 = TaskContract.from_dict({
                **hd.to_dict(),
                "requirements": {**hd.requirements.to_dict(),
                                 "exclude_families": list(loai_ho)}})
            kq = self._chay_co_thu_lai(hd2, demand=demand, base_sha=base_sha,
                                       on_event=on_event)
            with khoa:
                if kq.placement:
                    da_dung_ho.add(
                        self.fabric.model(kq.placement.model_id).model_family)
                ra.append(kq.envelope)

        for hd in hds:
            t = threading.Thread(target=_mot, args=(hd,), daemon=True)
            luong.append(t)
            t.start()
            # Lech nhip nho de cac luong THAY ho model cua nhau va tu tach
            # ra; khoi dong dong loat thi ca ba cung thay tap rong.
            time.sleep(0.25)
        for t in luong:
            t.join(timeout=c.execution.max_wall_time + 60)

        thanh_cong = [x for x in ra if x.ok]
        gop = ResultEnvelope(
            task_id=c.task_id,
            status="ok" if thanh_cong else "failed",
            summary=(f"{len(thanh_cong)}/{len(ra)} chẩn đoán độc lập trả về "
                     f"kết quả; so bằng chứng ở `hypotheses`."),
            failure_reason="" if thanh_cong else "all_hypotheses_failed")
        for x in ra:
            gop.findings.extend(f"[{x.model}] {f}" for f in x.findings[:5])
            if x.summary:
                gop.followups.append(f"[{x.model}] {x.summary[:200]}")
        return TaskOutcome(task_id=c.task_id, placement=None, attempts=len(ra),
                           envelope=gop, mode=cd.mode.value, hypotheses=ra)

    def _dem_hong_truoc(self, c: TaskContract) -> int:
        s = self.history.summary_for(task_type=c.type)
        if not s:
            return 0
        return int(round((1.0 - s["success_rate"]) * min(3, s["samples"])))

    # -- 5. Van hanh --------------------------------------------------------

    def drain(self, runtime_id: str) -> Dict:
        r = self.fabric.runtimes.get(runtime_id)
        if r is None:
            return {"runtime_id": runtime_id, "found": False}
        r.drained = True
        return {"runtime_id": runtime_id, "found": True, "drained": True,
                "in_flight": r.in_flight,
                "note": "không nhận việc MỚI; việc đang chạy vẫn chạy nốt"}

    def resume(self, runtime_id: str) -> Dict:
        r = self.fabric.runtimes.get(runtime_id)
        if r is None:
            return {"runtime_id": runtime_id, "found": False}
        r.drained = False
        r.cooldown_until = 0.0
        r.consecutive_failures = 0
        return {"runtime_id": runtime_id, "found": True, "drained": False}

    def explain(self, task_id: str) -> str:
        d = self.decisions.get(task_id)
        return d.explain() if d else f"chưa có quyết định nào cho {task_id!r}"

    def status(self, *, now: Optional[float] = None) -> Dict:
        return {
            "fabric": self.fabric.snapshot(now=now),
            "leases": [l.to_dict() for l in self.leases.all()],
            "decisions": {k: v.to_dict() for k, v in self.decisions.items()},
            "leaderboard": self.history.leaderboard(),
        }
