"""Vòng chạy DAG bất đồng bộ — Bể worker tự trị, Phase 6.

QUAN HỆ VỚI `scheduler.py`: đây là anh em BẤT ĐỒNG BỘ, không phải bản thay
thế. `Scheduler.run(dag)` chạy trọn một DAG rồi trả về — hoàn hảo cho một
script một lượt, nhưng nó **chặn**, không huỷ được, không thử lại được, và
chết cùng tiến trình gọi nó. Bể worker cần đúng bốn thứ đó, nên `PoolRunner`
có mô hình thực thi khác:

    Scheduler   : một lượt gọi, giữ trạng thái trong bộ nhớ, chặn tới hết.
    PoolRunner  : `tick()` không chặn, trạng thái ở SQLite, huỷ/thử lại/đổi
                  worker được, sống qua nhiều tiến trình.

Mọi phần THUẦN đều dùng lại, không viết lại: `TaskDag.ready()` mở khoá theo
nút, `routing.chon_worker` chọn worker (rào cứng của `policy.py` bên dưới),
`WorktreeManager` cô lập cây, `packet_for`/`parse_result` giữ hợp đồng,
`validation.kiem_dinh` kiểm kết quả. Phần viết mới ở đây chỉ là VÒNG ĐỜI.

THỬ LẠI RỒI MỚI ĐỔI WORKER (mission #9), và không bao giờ vô hạn:

    lượt 1 hỏng  -> thử lại, CHO PHÉP cùng worker (phần lớn lỗi là thoáng
                    qua: hết giờ, tiến trình chết, một lượt trả rỗng)
    lượt 2+ hỏng -> LOẠI mọi worker đã thử, chọn worker khác (mission: "if a
                    worker fails repeatedly, reassign")
    hết `max_attempts` -> việc hỏng THẬT. Không nới trần tự động.

Có loại hỏng KHÔNG được thử lại dù còn lượt: cổng bảo mật không đạt. Thử
lại một thay đổi chứa thứ giống credential chỉ tạo thêm cơ hội để nó lọt.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.packet import PacketRefused, TaskResult, packet_for
from scripts.router_v3.policy import NoWorkerAvailable
from scripts.router_v3.pool import routing, validation
from scripts.router_v3.pool.store import Job, PoolStore
from scripts.router_v3.registry import WorkerRegistry
from scripts.router_v3.worker_adapter import WorkerAdapter
from scripts.router_v3.worktree import WorktreeError, WorktreeManager

#: Ly do hong KHONG BAO GIO thu lai — thu lai chi tang co hoi lot.
KHONG_THU_LAI = frozenset({
    "security_gate",          # diff co thu giong credential / dung duong cam
    "cancelled",              # nguoi dung chu dong huy
    "packet_refused",         # goi viec chua bi mat -> khong duoc gui di lai
})


def nut_sang_dict(n: TaskNode) -> Dict:
    return {
        "id": n.id, "objective": n.objective,
        "dependencies": list(n.dependencies),
        "write_scope": list(n.write_scope), "read_scope": list(n.read_scope),
        "required_capabilities": list(n.required_capabilities),
        "risk_class": n.risk_class.value, "expected_output": n.expected_output,
        "preferred_provider": n.preferred_provider,
        "parallelizable": n.parallelizable,
        "estimated_seconds": n.estimated_seconds,
    }


def dict_sang_nut(d: Dict) -> TaskNode:
    return TaskNode(
        id=str(d["id"]), objective=str(d.get("objective") or ""),
        dependencies=tuple(d.get("dependencies") or ()),
        write_scope=tuple(d.get("write_scope") or ()),
        read_scope=tuple(d.get("read_scope") or ()),
        required_capabilities=tuple(d.get("required_capabilities") or ()),
        risk_class=RiskClass(str(d.get("risk_class") or "low")),
        expected_output=str(d.get("expected_output") or ""),
        preferred_provider=d.get("preferred_provider") or None,
        parallelizable=bool(d.get("parallelizable", True)),
        estimated_seconds=float(d.get("estimated_seconds") or 60.0))


@dataclass
class RunnerConfig:
    max_parallel: int = 6
    node_timeout: float = 1800.0
    test_timeout: float = 900.0
    #: Lenh test chay o cong kiem dinh cho MOI nut co ghi. Rong = khong chay
    #: (nut co the tu khai `tests_required` rieng).
    default_tests: Tuple[Tuple[str, ...], ...] = ()


class PoolRunner:
    """Chạy các việc trong sổ. Không chặn: `tick()` nạp thêm rồi trả về ngay."""

    def __init__(self, store: PoolStore, registry: WorkerRegistry,
                 adapters: Dict[str, WorkerAdapter], *,
                 worktrees: Optional[WorktreeManager] = None,
                 policy: Optional[routing.RoutingPolicy] = None,
                 config: Optional[RunnerConfig] = None):
        self._store = store
        self._reg = registry
        self._adapters = adapters
        self._wt = worktrees
        self._pol = policy or routing.nap()
        self._cfg = config or RunnerConfig()
        self._dang_chay: Dict[str, threading.Thread] = {}
        self._khoa = threading.Lock()
        self._dung = threading.Event()

    # -- truy van -----------------------------------------------------------

    @property
    def so_dang_chay(self) -> int:
        with self._khoa:
            return len(self._dang_chay)

    def _dag_cua_run(self, run_id: str) -> Optional[TaskDag]:
        r = self._store.run(run_id)
        if r is None:
            return None
        d = json.loads(r["dag_json"] or "{}")
        nodes = [dict_sang_nut(x) for x in (d.get("nodes") or [])]
        if not nodes:
            return None
        # `allow_overlapping_writes` DA duoc kiem luc dung DAG (orchestrator);
        # dung lai o day chi de doc quan he phu thuoc, nen khong kiem lai —
        # kiem lai se tu choi mot DAG da duoc chap nhan co y truoc do.
        return TaskDag(nodes, allow_overlapping_writes=True)

    def san_sang(self, run_id: str) -> List[Job]:
        """Việc đủ điều kiện chạy NGAY: đang `queued`, mọi phụ thuộc đã `ok`.

        Việc có phụ thuộc HỎNG bị đánh dấu `skipped` ngay tại đây — chạy một
        nút mà đầu vào của nó không tồn tại chỉ tốn thời gian worker để nhận
        về một thất bại khó hiểu hơn.
        """
        jobs = self._store.jobs(run_id)
        theo_node = {j.node_id: j for j in jobs}
        ra: List[Job] = []
        for j in jobs:
            if j.status != "queued":
                continue
            if j.cancel_requested:
                self._store.huy_neu_dang_cho(j.job_id)
                continue
            phu = j.node.get("dependencies") or []
            trang_thai = [theo_node[d].status for d in phu if d in theo_node]
            if any(t in ("failed", "blocked", "timeout", "cancelled", "skipped")
                   for t in trang_thai):
                self._store.hoan_thanh(
                    j.job_id, status="skipped",
                    result={"status": "skipped", "worker_id": "",
                            "job_id": j.node_id,
                            "failure_reason": "dependency_failed",
                            "summary": "phụ thuộc hỏng — không dispatch"})
                continue
            if all(t == "ok" for t in trang_thai) and len(trang_thai) == len(phu):
                ra.append(j)
        return ra

    # -- vong chay ----------------------------------------------------------

    def tick(self, run_id: str) -> int:
        """Nạp thêm việc cho tới khi đầy chỗ. Trả về số việc VỪA khởi động."""
        khoi_dong = 0
        for j in self.san_sang(run_id):
            if self.so_dang_chay >= self._cfg.max_parallel:
                break
            nut = dict_sang_nut(j.node)
            # `attempt` la so luot DA chay. 0 = chua chay lan nao.
            #
            #   attempt 0 -> luot dau, khong loai ai
            #   attempt 1 -> THU LAI: van cho phep chinh worker cu, vi phan
            #                lon loi la thoang qua (het gio, tien trinh chet,
            #                mot luot tra rong)
            #   attempt>=2 -> DOI WORKER: loai het worker da thu
            #
            # Loai tu `attempt >= 1` (ban dau viet nham nhu vay) bien "thu
            # lai" thanh "doi worker ngay", va khi be chi co MOT worker hop
            # le thi viec ket o hang doi mai — da vap that trong kiem thu.
            loai_tru = tuple(j.tried) if j.attempt >= 2 else ()
            try:
                worker = routing.chon_worker(self._reg, nut, policy=self._pol,
                                             loai_tru=loai_tru)
            except NoWorkerAvailable as exc:
                # Phan biet HAI thu rat khac nhau:
                #   - worker phu hop dang BAN  -> cho tick sau, binh thuong
                #   - khong con worker nao CO THE lam viec nay  -> hong han
                # Khong phan biet thi truong hop hai quay vong vo tan cho mot
                # thu khong bao gio den, va bo dieu phoi treo toi khi het gio.
                if (j.attempt >= j.max_attempts
                        or not routing.co_ung_vien_kha_thi(
                            self._reg, nut, loai_tru=loai_tru)):
                    self._store.hoan_thanh(
                        j.job_id, status="failed",
                        result={"status": "failed", "worker_id": "",
                                "job_id": j.node_id,
                                "failure_reason": "no_worker_available",
                                "summary": str(exc)[:400]})
                continue
            if not self._store.claim(j.job_id, worker.worker_id):
                continue                      # ai do nhan truoc — binh thuong
            self._reg.mark_started(worker.worker_id, j.node_id)
            t = threading.Thread(target=self._chay_mot, args=(j.job_id,
                                                              worker.worker_id),
                                 name=f"pool-{j.node_id}", daemon=True)
            with self._khoa:
                self._dang_chay[j.job_id] = t
            t.start()
            khoi_dong += 1
        return khoi_dong

    def chay_den_xong(self, run_id: str, *, poll: float = 1.0,
                      timeout: Optional[float] = None) -> str:
        """Chạy tới khi không còn việc nào chờ/chạy. Trả về trạng thái run.

        Dùng trong daemon và trong kiểm thử. Bộ điều phối phía Claude KHÔNG
        gọi hàm này — nó gọi `dispatch` rồi `wait_any`/`wait_all`.
        """
        het = None if timeout is None else time.time() + timeout
        while not self._dung.is_set():
            self.tick(run_id)
            con = [j for j in self._store.jobs(run_id)
                   if j.status in ("queued", "running")]
            if not con and self.so_dang_chay == 0:
                break
            if het is not None and time.time() > het:
                break
            time.sleep(poll)
        jobs = self._store.jobs(run_id)
        tt = ("ok" if jobs and all(j.status == "ok" for j in jobs)
              else "failed" if jobs else "empty")
        self._store.dat_trang_thai_run(run_id, tt)
        return tt

    def dung_lai(self) -> None:
        self._dung.set()

    # -- chay MOT viec ------------------------------------------------------

    def _chay_mot(self, job_id: str, worker_id: str) -> None:
        t0 = time.time()
        handle = None
        kq: Optional[TaskResult] = None
        bao_cao: Optional[validation.ValidationReport] = None
        try:
            j = self._store.job(job_id)
            if j is None:
                return
            nut = dict_sang_nut(j.node)
            r = self._store.run(j.run_id) or {}
            base_sha = r.get("base_sha") or "unknown"

            if nut.is_write:
                if self._wt is None:
                    kq = self._hong(nut.id, worker_id, "no_worktree_manager",
                                    "nút CÓ GHI nhưng không có WorktreeManager "
                                    "— từ chối chạy trên cây làm việc chung")
                    return
                try:
                    handle = self._wt.create(worker_id,
                                             f"{nut.id}-a{j.attempt}",
                                             base_sha=base_sha)
                except WorktreeError as exc:
                    kq = self._hong(nut.id, worker_id, "worktree_failed",
                                    f"không dựng được worktree: {exc}")
                    return

            tom_tat = self._tom_tat_phu_thuoc(j.run_id, nut)
            try:
                goi = packet_for(nut, base_sha=base_sha,
                                 dependency_summaries=tom_tat,
                                 workspace=str(handle.path) if handle else "",
                                 branch=handle.branch if handle else "")
            except PacketRefused as exc:
                kq = self._hong(nut.id, worker_id, "packet_refused", str(exc))
                return

            adapter = self._adapters.get(worker_id)
            if adapter is None:
                kq = self._hong(nut.id, worker_id, "worker_unavailable",
                                f"không có adapter cho {worker_id}")
                return

            if j.cancel_requested:
                kq = self._hong(nut.id, worker_id, "cancelled",
                                "huỷ trước khi gửi", status="cancelled")
                return

            adapter.start_session(workspace=goi.workspace or None)
            kq = adapter.send_task(goi)
            kq.worker_id = worker_id
            if handle is not None:
                kq.branch = handle.branch

            # KIEM DINH — khong bao gio tin `kq.status` mot minh.
            bao_cao = validation.kiem_dinh(
                kq, worktree=(handle.path if handle else None),
                write_scope=nut.write_scope,
                tests=self._lenh_test(nut),
                wt_manager=self._wt, handle=handle,
                test_timeout=self._cfg.test_timeout)
            if not bao_cao.passed:
                hong_cong = bao_cao.failed_gates
                kq.status = "blocked" if "security" in hong_cong else "failed"
                kq.failure_reason = ("security_gate" if "security" in hong_cong
                                     else f"gate_{hong_cong[0]}")
                chi_tiet = "; ".join(
                    g.detail for g in bao_cao.gates if not g.passed)[:400]
                kq.blockers.append(f"kiểm định không đạt ({hong_cong}): {chi_tiet}")
        except Exception as exc:                          # noqa: BLE001
            kq = self._hong(job_id, worker_id, "runner_exception",
                            f"{type(exc).__name__}: {exc}"[:300])
        finally:
            with self._khoa:
                self._dang_chay.pop(job_id, None)
            if kq is None:
                kq = self._hong(job_id, worker_id, "unknown", "không có kết quả")
            kq.started_at = kq.started_at or t0
            kq.ended_at = time.time()
            if not kq.duration_seconds:
                kq.duration_seconds = round(kq.ended_at - kq.started_at, 2)
            self._reg.mark_finished(worker_id, ok=kq.ok,
                                    seconds=kq.duration_seconds,
                                    error="" if kq.ok else kq.summary)
            self._ghi_nhan_quota(worker_id, kq)
            self._ket_thuc(job_id, kq, bao_cao)

    def _hong(self, task_id: str, worker_id: str, ly_do: str, tom_tat: str,
              *, status: str = "failed") -> TaskResult:
        return TaskResult(task_id=task_id, worker_id=worker_id, status=status,
                          failure_reason=ly_do, summary=tom_tat[:400])

    def _tom_tat_phu_thuoc(self, run_id: str, nut: TaskNode) -> Dict[str, str]:
        """Tóm tắt kết quả các nút phụ thuộc — KHÔNG phải hội thoại của chúng.

        Đây là điểm giữ ngữ cảnh nhỏ: một nút tích hợp đọc bốn dòng tóm tắt,
        không phải bốn bản ghi worker đầy đủ.
        """
        ra: Dict[str, str] = {}
        for d in nut.dependencies:
            j = self._store.job_theo_node(run_id, d)
            if j and j.result:
                ra[d] = str(j.result.get("summary") or "")[:400]
        return ra

    def _lenh_test(self, nut: TaskNode) -> Sequence[Sequence[str]]:
        return self._cfg.default_tests if nut.is_write else ()

    def _ghi_nhan_quota(self, worker_id: str, kq: TaskResult) -> None:
        """Nhận diện chạm quota và chuyển worker sang QUOTA_COOLDOWN.

        Chỉ dựa vào thứ nhà cung cấp NÓI RA (văn bản lỗi), không suy đoán từ
        việc worker chậm hay hỏng — đoán sai sẽ khoá một worker khoẻ.
        """
        van_ban = f"{kq.summary} {kq.failure_reason}".lower()
        dau_hieu = ("quota", "rate limit", "rate_limit", "resource_exhausted",
                    "429", "too many requests", "usage limit")
        if any(d in van_ban for d in dau_hieu):
            self._reg.set_quota_cooldown(worker_id, 900.0,
                                         signal=kq.summary[:200])
            self._store.ghi_su_kien("quota_cooldown", job_id=kq.task_id,
                                    detail=f"{worker_id}: 900s")

    def _ket_thuc(self, job_id: str, kq: TaskResult,
                  bao_cao: Optional[validation.ValidationReport]) -> None:
        """Ghi kết quả, hoặc trả về hàng đợi nếu còn lượt và lỗi thử lại được."""
        phong_bi = kq.envelope()
        if bao_cao is not None:
            phong_bi["validation"] = bao_cao.to_dict()
        j = self._store.job(job_id)
        if kq.ok or j is None:
            self._store.hoan_thanh(job_id, status=kq.status, result=phong_bi,
                                   validation=(bao_cao.to_dict()
                                               if bao_cao else None))
            return
        if kq.failure_reason in KHONG_THU_LAI or j.cancel_requested:
            self._store.hoan_thanh(job_id, status=kq.status, result=phong_bi,
                                   validation=(bao_cao.to_dict()
                                               if bao_cao else None))
            return
        if self._store.tra_ve_hang_doi(job_id, ly_do=kq.failure_reason or "failed"):
            # Giu ket qua luot hong lai de chan doan, nhung KHONG dat trang
            # thai cuoi — viec van con song trong hang doi.
            self._store.ghi_su_kien(
                "attempt_failed", run_id=j.run_id, job_id=job_id,
                detail=f"{kq.worker_id}: {kq.failure_reason} — {kq.summary[:150]}")
            return
        self._store.hoan_thanh(job_id, status=kq.status, result=phong_bi,
                               validation=bao_cao.to_dict() if bao_cao else None)
