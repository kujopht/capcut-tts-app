"""Giao diện điều phối Claude gọi — Bể worker tự trị, Phase 7.

ĐÂY LÀ RANH GIỚI DUY NHẤT bộ điều phối (phiên Claude này) cần biết. Nó
KHÔNG mở cửa sổ worker, không gõ prompt, không dán kết quả. Nó gọi mười
động từ:

    plan          — mô tả công việc thành DAG đã kiểm hợp lệ
    dispatch      — giao MỘT nút, trả về ngay (không chặn)
    dispatch_many — giao cả DAG, trả về ngay
    wait_any      — chờ nút ĐẦU TIÊN xong (mở khoá sớm nhất có thể)
    wait_all      — chờ hết
    status        — bể + các nút đang chạy, một cái nhìn
    result        — phong bì kết quả của một nút
    cancel        — huỷ một nút
    retry         — chạy lại một nút đã cạn lượt tự động
    reassign      — buộc một nút sang worker khác

VÌ SAO KHÔNG CHẶN: `Scheduler.run()` chặn tới khi cả DAG xong. Với một
phiên Claude điều phối, chặn nghĩa là không quan sát được gì giữa chừng,
không xen được việc mới, không huỷ được một nhánh đã rõ là sai. `dispatch`
trả về `job_id` ngay và trạng thái nằm trong SQLite, nên phiên Claude đọc
được bất cứ lúc nào — kể cả một phiên Claude KHÁC, sau khi phiên này đóng.

CHẾ ĐỘ CHẠY: bể chạy được theo hai cách, cùng một API.

    có daemon    — `daemon.py` chạy nền, `dispatch` chỉ ghi việc vào sổ.
                   Việc sống tiếp sau khi phiên Claude đóng (mission #12).
    không daemon — `Orchestrator(inline=True)` tự quay `runner.tick()` bên
                   trong `wait_*`. Dùng cho kiểm thử và cho lượt chạy ngắn.

`wait_*` KHÔNG BAO GIỜ chờ vô hạn: mọi hàm chờ đều có `timeout` với giá trị
mặc định hữu hạn. Một bộ điều phối treo vĩnh viễn vì một worker chết là
đúng thứ mission #9 gọi là "infinite-loop".
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v3.dag import DagError, RiskClass, TaskDag, TaskNode
from scripts.router_v3.pool import adapters as ad_mod
from scripts.router_v3.pool import identity as id_mod
from scripts.router_v3.pool import routing
from scripts.router_v3.pool.runner import (PoolRunner, RunnerConfig,
                                           dict_sang_nut, nut_sang_dict)
from scripts.router_v3.pool.store import Job, PoolStore
from scripts.router_v3.registry import (Health, PoolState, WorkerRegistry,
                                        WorkerSpec)
from scripts.router_v3.worker_adapter import WorkerAdapter
from scripts.router_v3.worktree import WorktreeManager

#: Tran cho mac dinh. Huu han co chu dich — xem docstring module.
CHO_MAC_DINH = 1800.0


class OrchestratorError(RuntimeError):
    pass


@dataclass
class PlanResult:
    """Kết quả `plan()` — DAG đã kiểm + những gì đo được về nó."""

    dag: TaskDag
    waves: List[List[str]]
    critical_path: List[str]
    critical_seconds: float
    recommended_workers: int
    total_estimated_seconds: float

    def to_dict(self) -> Dict:
        return {
            "nodes": [n.id for n in self.dag.nodes()],
            "waves": self.waves,
            "critical_path": self.critical_path,
            "critical_seconds": self.critical_seconds,
            "recommended_workers": self.recommended_workers,
            "total_estimated_seconds": self.total_estimated_seconds,
        }


class Orchestrator:
    """Mặt tiền bể worker. Dựng rẻ; không tự khởi động tiến trình worker nào."""

    def __init__(self, *, root: Optional[Path] = None,
                 store: Optional[PoolStore] = None,
                 identities: Optional[Sequence[id_mod.Identity]] = None,
                 registry: Optional[WorkerRegistry] = None,
                 adapters: Optional[Dict[str, WorkerAdapter]] = None,
                 worktrees: Optional[WorktreeManager] = None,
                 policy: Optional[routing.RoutingPolicy] = None,
                 config: Optional[RunnerConfig] = None,
                 inline: bool = False,
                 probe_health: bool = True):
        self.root = Path(root) if root else Path.cwd()
        self.store = store or PoolStore(root=self.root)
        self.identities = list(identities if identities is not None
                               else id_mod.nap(root=self.root))
        id_mod.validate_pool(self.identities)
        self.policy = policy or routing.nap(root=self.root)
        self.registry = registry or self._dung_registry(probe=probe_health)
        self.adapters = (adapters if adapters is not None
                         else ad_mod.dung_tat_ca(self.identities))
        self.worktrees = worktrees if worktrees is not None else \
            WorktreeManager(self.root)
        self.runner = PoolRunner(
            self.store, self.registry, self.adapters,
            worktrees=self.worktrees, policy=self.policy,
            config=config or RunnerConfig(max_parallel=self.policy.max_parallel))
        self.inline = inline
        self._dong_bo_worker()

    # -- dung so dang ky ----------------------------------------------------

    def _dung_registry(self, *, probe: bool) -> WorkerRegistry:
        reg = WorkerRegistry()
        for idn in self.identities:
            reg.register(idn.to_spec())
        for idn in self.identities:
            if not idn.provisioned:
                reg.set_health(idn.worker_id, Health.UNAVAILABLE,
                               idn.needs_provisioning[:200])
                continue
            if idn.provider == "claude":
                reg.set_health(idn.worker_id, Health.HEALTHY)
                continue
            if not probe:
                reg.set_health(idn.worker_id, Health.UNKNOWN, "chưa dò")
                continue
            try:
                a = ad_mod.dung_adapter(idn)
            except ad_mod.AdapterError as exc:
                reg.set_health(idn.worker_id, Health.UNAVAILABLE, str(exc)[:200])
                continue
            if a is None:
                reg.set_health(idn.worker_id, Health.UNAVAILABLE,
                               "chưa ghép/chưa cấp phát")
                continue
            bc = a.health()
            # Adapter NATIVE chua `start_session` bao UNKNOWN — do la dung
            # ("chua biet"), nhung voi mot khe co CLI da xac thuc thi coi la
            # HEALTHY o muc so dang ky, va lan gui viec that se noi su that.
            trang_thai = bc.state
            if trang_thai is Health.UNKNOWN and idn.transport is id_mod.Transport.NATIVE:
                from scripts.router_v3.native_worker import find_agy
                trang_thai = Health.HEALTHY if find_agy() else Health.UNAVAILABLE
            reg.set_health(idn.worker_id, trang_thai, bc.detail)
        return reg

    def _dong_bo_worker(self) -> None:
        """Đẩy trạng thái worker vào sổ để lệnh quan sát đọc được."""
        theo_id = {i.worker_id: i for i in self.identities}
        for hang in self.registry.snapshot():
            idn = theo_id.get(hang["worker_id"])
            hang = dict(hang)
            hang["account_slot"] = idn.account_slot if idn else True
            hang["lane_of"] = idn.lane_of if idn else ""
            if idn and not idn.provisioned:
                hang["detail"] = idn.needs_provisioning
            self.store.ghi_worker(hang)

    def refresh(self) -> None:
        """Dò lại sức khoẻ worker và ghi vào sổ."""
        self.registry = self._dung_registry(probe=True)
        self.runner._reg = self.registry           # cùng một sổ, không hai bản
        self._dong_bo_worker()

    # -- 1. plan ------------------------------------------------------------

    def plan(self, nodes: Sequence[TaskNode] | Sequence[Dict], *,
             allow_overlapping_writes: bool = False) -> PlanResult:
        """Dựng DAG đã kiểm hợp lệ + đo nó.

        Ném `DagError` ngay tại đây với chu trình, phụ thuộc treo, hoặc hai
        nút cùng ghi một chỗ mà không có quan hệ phụ thuộc. Bắt lúc lập kế
        hoạch chứ không lúc chạy: lúc chạy thì đã có worker sửa tệp rồi.
        """
        ds = [n if isinstance(n, TaskNode) else dict_sang_nut(n) for n in nodes]
        dag = TaskDag(ds, allow_overlapping_writes=allow_overlapping_writes)
        duong, giay = dag.critical_path()
        return PlanResult(
            dag=dag, waves=dag.waves(), critical_path=duong,
            critical_seconds=giay,
            recommended_workers=dag.recommended_workers(
                ceiling=self.policy.max_parallel),
            total_estimated_seconds=round(
                sum(n.estimated_seconds for n in dag.nodes()), 2))

    # -- 2/3. dispatch ------------------------------------------------------

    def dispatch_many(self, plan: PlanResult | TaskDag, *,
                      base_sha: str = "", note: str = "",
                      max_attempts: Optional[int] = None) -> str:
        """Giao cả DAG. Trả về `run_id` NGAY — không chờ việc nào chạy xong."""
        dag = plan.dag if isinstance(plan, PlanResult) else plan
        sha = base_sha or self._base_sha()
        ghi = [n for n in dag.nodes() if n.is_write]
        if ghi and self._cay_ban():
            raise OrchestratorError(
                "cây làm việc chính đang BẨN — dọn hoặc commit trước khi giao "
                "việc CÓ GHI. Worktree mới sẽ kế thừa thay đổi chưa commit của "
                "người khác và không ai dựng lại được chuyện gì đã xảy ra.")
        run_id = self.store.tao_run(
            base_sha=sha, note=note,
            dag={"nodes": [nut_sang_dict(n) for n in dag.nodes()]})
        lan = max_attempts or self.policy.max_attempts
        for n in dag.nodes():
            self.store.them_job(run_id=run_id, node_id=n.id,
                                node=nut_sang_dict(n), max_attempts=lan)
        return run_id

    def dispatch(self, node: TaskNode | Dict, *, run_id: str = "",
                 base_sha: str = "", max_attempts: Optional[int] = None
                 ) -> Tuple[str, str]:
        """Giao MỘT nút. Trả `(run_id, job_id)` ngay.

        `run_id` rỗng tạo một lượt chạy mới chỉ có nút này; truyền `run_id`
        có sẵn để thêm nút vào một lượt đang chạy — phụ thuộc của nó được
        giải theo các nút đã có trong lượt đó.
        """
        n = node if isinstance(node, TaskNode) else dict_sang_nut(node)
        if not run_id:
            run_id = self.store.tao_run(base_sha=base_sha or self._base_sha(),
                                        note=f"dispatch {n.id}",
                                        dag={"nodes": [nut_sang_dict(n)]})
        else:
            r = self.store.run(run_id)
            if r is None:
                raise OrchestratorError(f"run {run_id!r} không tồn tại")
            d = json.loads(r["dag_json"] or "{}")
            ds = list(d.get("nodes") or [])
            if all(x.get("id") != n.id for x in ds):
                ds.append(nut_sang_dict(n))
                self.store._ket_noi().execute(
                    "UPDATE runs SET dag_json=?, updated_at=? WHERE run_id=?",
                    (json.dumps({"nodes": ds}, ensure_ascii=False),
                     time.time(), run_id))
        jid = self.store.them_job(
            run_id=run_id, node_id=n.id, node=nut_sang_dict(n),
            max_attempts=max_attempts or self.policy.max_attempts)
        return run_id, jid

    # -- 4/5. cho -----------------------------------------------------------

    def _quay(self, run_id: str) -> None:
        """Một vòng công việc nền khi chạy ở chế độ `inline`."""
        if self.inline:
            self.runner.tick(run_id)

    def wait_any(self, run_id: str, *, timeout: float = CHO_MAC_DINH,
                 poll: float = 0.5,
                 exclude: Sequence[str] = ()) -> Optional[Job]:
        """Chờ việc ĐẦU TIÊN kết thúc. `None` nếu hết giờ.

        `exclude` là các `job_id` đã lấy ở lượt chờ trước — không có nó,
        `wait_any` gọi lần thứ hai sẽ trả lại ngay chính việc cũ và vòng lặp
        điều phối quay tại chỗ.
        """
        bo = set(exclude)
        het = time.time() + timeout
        while time.time() < het:
            self._quay(run_id)
            for j in self.store.jobs(run_id):
                if j.finished and j.job_id not in bo:
                    return j
            if not self._con_viec(run_id):
                return None
            time.sleep(poll)
        return None

    def wait_all(self, run_id: str, *, timeout: float = CHO_MAC_DINH,
                 poll: float = 0.5) -> List[Job]:
        """Chờ hết. Trả về mọi việc — kể cả việc chưa xong khi hết giờ, để
        bên gọi thấy CHÍNH XÁC cái gì còn treo thay vì một danh sách rỗng."""
        het = time.time() + timeout
        while time.time() < het:
            self._quay(run_id)
            if not self._con_viec(run_id):
                break
            time.sleep(poll)
        jobs = self.store.jobs(run_id)
        if jobs and all(j.finished for j in jobs):
            self.store.dat_trang_thai_run(
                run_id, "ok" if all(j.status == "ok" for j in jobs) else "failed")
        return jobs

    def _con_viec(self, run_id: str) -> bool:
        return any(j.status in ("queued", "running")
                   for j in self.store.jobs(run_id))

    # -- 6. status ----------------------------------------------------------

    def status(self, run_id: str = "") -> Dict:
        """Một cái nhìn: bể worker + các nút đang chạy (mission #13)."""
        rid = run_id or self.store.run_gan_nhat() or ""
        jobs = self.store.jobs(rid) if rid else []
        return {
            "run_id": rid,
            "run": self.store.run(rid) if rid else None,
            "workers": self.store.workers(),
            "accounts": id_mod.dem_tai_khoan(self.identities),
            "jobs": [self._tom_tat_job(j) for j in jobs],
            "counts": self._dem(jobs),
            "in_flight": self.runner.so_dang_chay,
        }

    @staticmethod
    def _dem(jobs: Sequence[Job]) -> Dict[str, int]:
        ra: Dict[str, int] = {}
        for j in jobs:
            ra[j.status] = ra.get(j.status, 0) + 1
        return ra

    @staticmethod
    def _tom_tat_job(j: Job) -> Dict:
        return {
            "job_id": j.job_id, "node_id": j.node_id, "status": j.status,
            "worker_id": j.worker_id, "attempt": j.attempt,
            "max_attempts": j.max_attempts, "tried": list(j.tried),
            "seconds": j.duration_seconds,
            "summary": (j.result or {}).get("summary", "")[:200],
            "failure_reason": (j.result or {}).get("failure_reason", ""),
            "branch": (j.result or {}).get("branch", ""),
            "validation_passed": (j.validation or {}).get("passed"),
        }

    # -- 7. result ----------------------------------------------------------

    def result(self, job_id: str = "", *, run_id: str = "",
               node_id: str = "") -> Optional[Dict]:
        """Phong bì kết quả đầy đủ của một việc."""
        j = (self.store.job(job_id) if job_id
             else self.store.job_theo_node(run_id, node_id))
        if j is None:
            return None
        return {
            "job_id": j.job_id, "node_id": j.node_id, "status": j.status,
            "worker_id": j.worker_id, "attempt": j.attempt,
            "tried": list(j.tried), "timing": {
                "started_at": j.started_at, "ended_at": j.ended_at,
                "duration_seconds": j.duration_seconds},
            "envelope": j.result, "validation": j.validation,
        }

    # -- 8. cancel ----------------------------------------------------------

    def cancel(self, job_id: str) -> Dict:
        """Huỷ một việc.

        TRUNG THỰC VỀ GIỚI HẠN: việc còn trong hàng đợi thì huỷ được ngay.
        Việc ĐANG chạy chỉ được ĐÁNH DẤU; adapter native/CLI giết được tiến
        trình con, còn adapter cầu nối thì KHÔNG ngắt được lượt đang bay
        (giao thức cầu nối đồng bộ hoàn toàn — xem `antigravity_adapter.py`).
        Trả về `stopped_now` để bên gọi biết mình đang ở trường hợp nào thay
        vì tưởng đã dừng thật.
        """
        j = self.store.job(job_id)
        if j is None:
            return {"job_id": job_id, "found": False}
        self.store.yeu_cau_huy(job_id)
        ngay = self.store.huy_neu_dang_cho(job_id)
        da_ngat = False
        if not ngay and j.status == "running" and j.worker_id:
            a = self.adapters.get(j.worker_id)
            if a is not None:
                a.cancel()
                da_ngat = True
        return {"job_id": job_id, "found": True, "stopped_now": ngay,
                "adapter_cancel_called": da_ngat,
                "note": ("đã huỷ khi còn trong hàng đợi" if ngay else
                         "đã đánh dấu huỷ; lượt ĐANG chạy có thể vẫn chạy nốt "
                         "nếu giao thức worker không ngắt được")}

    # -- 9. retry -----------------------------------------------------------

    def retry(self, job_id: str, *, extra_attempts: int = 1) -> Dict:
        """Chạy lại một việc đã kết thúc. Chủ động, không phải tự động.

        Nới trần `max_attempts` là hành động của NGƯỜI/bộ điều phối, không
        bao giờ của vòng thử lại tự động — nếu tự động tự nới được trần của
        chính nó thì "bounded" không còn nghĩa gì.
        """
        j = self.store.job(job_id)
        if j is None:
            return {"job_id": job_id, "found": False}
        if j.status == "running":
            return {"job_id": job_id, "found": True, "requeued": False,
                    "note": "đang chạy — huỷ trước rồi mới thử lại"}
        self.store.dat_max_attempts(job_id, j.attempt + max(1, extra_attempts))
        ok = self.store.tra_ve_hang_doi(job_id, ly_do="retry thủ công")
        return {"job_id": job_id, "found": True, "requeued": ok,
                "attempt": j.attempt,
                "max_attempts": j.attempt + max(1, extra_attempts)}

    # -- 10. reassign -------------------------------------------------------

    def reassign(self, job_id: str, *, worker_id: str = "") -> Dict:
        """Buộc một việc sang worker khác.

        Không truyền `worker_id` thì bộ chọn tự tìm worker hợp lệ KHÁC các
        worker đã thử. Truyền tay thì worker đó vẫn phải qua rào cứng — một
        chỉ định thủ công không mở được rào bảo mật/tin cậy.
        """
        j = self.store.job(job_id)
        if j is None:
            return {"job_id": job_id, "found": False}
        if j.status == "running":
            return {"job_id": job_id, "found": True, "reassigned": False,
                    "note": "đang chạy — huỷ trước rồi mới đổi worker"}
        nut = dict_sang_nut(j.node)
        loai_tru = tuple(set(j.tried) | ({j.worker_id} if j.worker_id else set()))
        try:
            chon = routing.chon_worker(self.registry, nut, policy=self.policy,
                                       loai_tru=loai_tru)
        except Exception as exc:                          # NoWorkerAvailable
            return {"job_id": job_id, "found": True, "reassigned": False,
                    "note": str(exc)[:300]}
        if worker_id:
            hop_le = {w.worker_id for w in self.registry.available(
                high_risk=nut.risk_class is RiskClass.HIGH)}
            if worker_id not in hop_le:
                return {"job_id": job_id, "found": True, "reassigned": False,
                        "note": f"{worker_id} không qua được rào cứng cho nút "
                                f"này (risk={nut.risk_class.value}) — chỉ định "
                                f"thủ công KHÔNG mở được rào."}
            chon_id = worker_id
        else:
            chon_id = chon.worker_id
        self.store.dat_max_attempts(job_id, j.attempt + 1)
        ok = self.store.tra_ve_hang_doi(job_id, ly_do=f"reassign -> {chon_id}")
        self.store.ghi_su_kien("reassigned", run_id=j.run_id, job_id=job_id,
                               detail=f"{j.worker_id or '?'} -> {chon_id}")
        return {"job_id": job_id, "found": True, "reassigned": ok,
                "from": j.worker_id, "to": chon_id}

    # -- tien ich -----------------------------------------------------------

    def _base_sha(self) -> str:
        try:
            return self.worktrees.base_sha()
        except Exception:                                 # noqa: BLE001
            return "unknown"

    #: Thu muc trang thai CUA CHINH Router. No khong bao gio thuoc ve mot
    #: base SHA, nen su hien dien cua no khong lam cay "ban" theo nghia ma
    #: phep kiem nay quan tam.
    _BO_QUA_KHI_KIEM_BAN = (".router/",)

    def _cay_ban(self) -> bool:
        """Cây làm việc chính có thay đổi chưa commit nào ĐÁNG KỂ không.

        Cố ý KHÔNG gọi thẳng `WorktreeManager.is_dirty()`: sổ việc, worktree
        và log của bể đều nằm dưới `.router/`, và nếu người dùng chưa thêm
        đường đó vào `.gitignore` thì chính việc bể khởi động sẽ làm cây
        "bẩn" và mọi lượt giao việc CÓ GHI bị từ chối — một vòng luẩn quẩn
        rất khó đoán ra. Bể tự loại trạng thái của chính nó thay vì phụ
        thuộc vào cấu hình `.gitignore` của kho.
        """
        try:
            p = self.worktrees._git("status", "--porcelain")
        except Exception:                                 # noqa: BLE001
            return False
        for dong in (p.stdout or "").splitlines():
            tep = dong[3:].strip().strip('"').replace("\\", "/")
            if " -> " in tep:
                tep = tep.split(" -> ", 1)[1]
            if not tep:
                continue
            if any(tep.startswith(b) or tep == b.rstrip("/")
                   for b in self._BO_QUA_KHI_KIEM_BAN):
                continue
            return True
        return False
