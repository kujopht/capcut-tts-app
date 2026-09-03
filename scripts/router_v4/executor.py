"""Chạy MỘT hợp đồng trên MỘT placement — Router V4.

Đây là chỗ duy nhất V4 chạm vào tiến trình worker thật. Mọi thứ khác
(`scheduler`, `mission`, `modes`) là hàm thuần và kiểm thử được không cần
mạng — tách như vậy có chủ đích: phần khó nhất để tin tưởng là phần quyết
định, và nó phải kiểm được tất định.

DÙNG LẠI, KHÔNG VIẾT LẠI:
    adapter provider   -> `router_v3/pool/adapters.py` (+ `antigravity_adapter`,
                          `opencode_adapter`) — hợp đồng chín phương thức đã có
    cô lập cây làm việc -> `router_v3/worktree.py`
    cổng kiểm định     -> `router_v3/pool/validation.py`

CÁI V4 THÊM: một placement là (runtime, model), nên adapter được dựng theo
CẶP đó chứ không theo một "worker" có model đóng cứng. Cùng một runtime
AG01 chạy Gemini cho việc này và Claude Opus cho việc kia.

KHÔNG BAO GIỜ `--dangerously-skip-permissions`. Việc có ghi dùng
`--mode accept-edits` + `--add-dir <worktree>`; việc chỉ đọc không xin quyền
gì. Xem `router_v3/pool/adapters.PoolAntigravityAdapter`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v3.pool import validation as V
from scripts.router_v3.pool.adapters import (CodexAdapter, MultiSlotAdapter,
                                             PoolAntigravityAdapter)
from scripts.router_v3.opencode_adapter import OpenCodeAdapter
from scripts.router_v3.packet import TaskPacket
from scripts.router_v3.worktree import WorktreeError, WorktreeHandle, WorktreeManager
from scripts.router_v4.contract import TaskContract
from scripts.router_v4.envelope import (RawLogStore, ResultEnvelope,
                                        from_worker_output)
from scripts.router_v4.history import BenchmarkStore, Record
from scripts.router_v4.runtime import Fabric, Placement


class ExecutorError(RuntimeError):
    pass


def _packet_gia(c: TaskContract, *, workspace: str, branch: str,
                deps: Optional[Dict[str, str]] = None) -> TaskPacket:
    """Bọc hợp đồng V4 thành `TaskPacket` để adapter V3 dùng lại được.

    `render()` của packet KHÔNG được dùng — adapter gọi `packet.render()`, nên
    ta ghi đè nó bằng bản render của HỢP ĐỒNG. Nhờ vậy worker nhận đúng hợp
    đồng V4 (có `forbidden_scope`, `stop_conditions`, lược đồ phong bì V4)
    mà không phải sửa một dòng nào trong các adapter đã chạy ổn định.
    """
    p = TaskPacket(
        task_id=c.task_id, base_sha="v4", objective=c.objective,
        dependencies=tuple(c.dependencies), read_scope=tuple(c.inputs),
        write_scope=tuple(c.allowed_scope),
        do_not_touch=tuple(c.forbidden_scope),
        workspace=workspace, branch=branch)
    van_ban = c.render(workspace=workspace, branch=branch,
                       dependency_summaries=deps)
    object.__setattr__(p, "render", lambda: van_ban)      # type: ignore[misc]
    return p


def dung_adapter(f: Fabric, p: Placement, *, timeout: float,
                 cache: Optional[Dict[str, object]] = None):
    """Adapter cho một PLACEMENT. Cache theo `(runtime, model)`.

    Cache là bắt buộc chứ không phải tối ưu: `MultiSlotAdapter` giữ các khe
    song song theo LUỒNG, và dựng một bản mới cho mỗi việc sẽ vứt hết trạng
    thái khe đó đi.
    """
    khoa = p.key
    if cache is not None and khoa in cache:
        return cache[khoa]
    r = f.runtime(p.runtime_id)
    m = f.model(p.model_id)
    if not r.provisioned:
        raise ExecutorError(f"{p.key}: runtime chưa cấp phát — {r.needs_provisioning}")

    if m.provider == "antigravity":
        if r.transport == "launcher":
            from scripts.router_v4.antigravity_launcher import \
                AntigravityLauncherAdapter
            a = AntigravityLauncherAdapter(r.runtime_id, model=m.model_id,
                                           turn_timeout=timeout)
        elif r.transport == "native":
            def _tao():
                return PoolAntigravityAdapter(
                    r.runtime_id, model=m.model_id, allow_edits=True,
                    dangerously_skip_permissions=False, turn_timeout=timeout)
            a = (MultiSlotAdapter(r.runtime_id, _tao, slots=r.concurrency)
                 if r.concurrency > 1 else _tao())
        elif r.transport == "bridge":
            from scripts.router_v3 import worker_identity
            from scripts.router_v3.antigravity_adapter import AntigravityBridgeAdapter
            dt = worker_identity.doc(r.runtime_id)
            if dt is None:
                raise ExecutorError(
                    f"{p.key}: cầu nối chưa ghép — chạy run_bridge.py trong "
                    f"phiên {r.auth_profile}")
            a = AntigravityBridgeAdapter(r.runtime_id, host=r.host,
                                         port=r.port or dt["port"],
                                         token=dt["token"], model=m.model_id,
                                         timeout=timeout)
        else:
            raise ExecutorError(f"{p.key}: transport {r.transport!r} lạ")
    elif m.provider == "codex":
        a = CodexAdapter(r.runtime_id, timeout=timeout, workspace=r.workspace)
    elif m.provider == "opencode":
        a = OpenCodeAdapter(r.runtime_id, host=r.host, port=r.port or 4096,
                            model=m.model_id, timeout=timeout)
    elif m.provider == "claude":
        raise ExecutorError(
            f"{p.key}: CLAUDE_LEAD là chính phiên điều phối — nó lập kế "
            f"hoạch và tích hợp, không nhận dispatch. Bộ lập lịch nên loại "
            f"nó cho việc thực thi.")
    else:
        raise ExecutorError(f"{p.key}: provider lạ {m.provider!r}")

    if cache is not None:
        cache[khoa] = a
    return a


@dataclass
class ExecutionResult:
    envelope: ResultEnvelope
    validation: Optional[V.ValidationReport] = None
    worktree: str = ""
    branch: str = ""

    @property
    def ok(self) -> bool:
        return self.envelope.ok and (self.validation is None
                                     or self.validation.passed)

    def to_dict(self) -> Dict:
        d = {"envelope": self.envelope.to_dict(), "worktree": self.worktree,
             "branch": self.branch, "ok": self.ok}
        if self.validation is not None:
            d["validation"] = self.validation.to_dict()
        return d


class Executor:
    """Chạy hợp đồng. Không quyết định gì — bộ lập lịch đã chọn placement."""

    def __init__(self, fabric: Fabric, *, root: Optional[Path] = None,
                 worktrees: Optional[WorktreeManager] = None,
                 history: Optional[BenchmarkStore] = None,
                 logs: Optional[RawLogStore] = None):
        self.fabric = fabric
        self.root = Path(root) if root else Path.cwd()
        self.worktrees = worktrees if worktrees is not None else \
            WorktreeManager(self.root)
        self.history = history if history is not None else \
            BenchmarkStore(root=self.root)
        self.logs = logs if logs is not None else RawLogStore(root=self.root)
        self._cache: Dict[str, object] = {}
        # Ma NGAN cua LAN CHAY nay, di vao ten worktree/nhanh.
        #
        # Khong co no, chay lai cung mot mission se dung dung ten worktree cu
        # (`AG01/T3-a1`), va `WorktreeManager.create` TU CHOI ghi de — dung
        # nhu thiet ke (khong bao gio de mat bang chung cua mot lan chay
        # truoc), nhung hau qua la lan chay thu hai hong ngay tu nut dau cho
        # toi khi co nguoi don tay. Da vap that trong lan chay bang chung
        # dau tien.
        import uuid as _uuid
        self.run_tag = _uuid.uuid4().hex[:6]

    def run(self, c: TaskContract, p: Placement, *, base_sha: str = "",
            dependency_summaries: Optional[Dict[str, str]] = None,
            dependency_workspaces: Optional[Dict[str, str]] = None,
            attempt: int = 1, reassigned: bool = False) -> ExecutionResult:
        t0 = time.time()
        m = self.fabric.model(p.model_id)
        handle: Optional[WorktreeHandle] = None
        try:
            if c.execution.worktree_required:
                handle = self.worktrees.create(
                    p.runtime_id, f"{c.task_id}-{self.run_tag}-a{attempt}",
                    base_sha=base_sha or self.worktrees.base_sha())

            adapter = dung_adapter(self.fabric, p,
                                   timeout=c.execution.max_wall_time,
                                   cache=self._cache)
            # `ws`   : noi worker LAM VIEC (worktree co lap khi co ghi).
            # `doc`  : thu muc worker duoc DOC. Mot viec chi doc van phai
            #          duoc `--add-dir` tro vao kho, neu khong `agy` khong
            #          thay tep nao ca va moi viec "phan tich kho" tra ve
            #          rong mot cach kho hieu. Nhung no KHONG duoc kem
            #          quyen ghi — xem `PoolAntigravityAdapter.set_write_mode`.
            ws = str(handle.path) if handle else ""
            # NOI DOC cua mot viec CHI DOC.
            #
            # Mac dinh la goc kho. NHUNG neu viec nay phu thuoc vao mot viec
            # CO GHI, ket qua cua viec kia nam trong WORKTREE CO LAP cua no,
            # KHONG nam o goc kho. Bang chung that (luot chay 2026-09-03):
            # nut review T4 bao "khong tim thay scripts/router_v4/report.py"
            # trong khi tep do CO ton tai — chi la o worktree cua T3. Co lap
            # worktree la dung; thieu buoc TRO reviewer sang do moi la loi.
            doc = ws or self._noi_doc_phu_thuoc(dependency_workspaces)
            doc = doc or str(self.root)
            if hasattr(adapter, "set_write_mode"):
                adapter.set_write_mode(bool(handle))
            adapter.start_session(workspace=doc)
            goi = _packet_gia(c, workspace=doc,
                              branch=handle.branch if handle else "",
                              deps=dependency_summaries)
            kq = adapter.send_task(goi)
            giay = time.time() - t0

            # `TaskResult` cua V3 -> phong bi V4.
            #
            # DUNG TU TRUONG DA PHAN TICH, khong doc lai `raw_excerpt`.
            # Bang chung that (2026-09-03): `parse_result` cua V3 CAT
            # `raw_excerpt` con 400 ky tu, nen doc lai chuoi do gan nhu luon
            # gap mot khoi JSON bi cat cut -> `no_json_block` -> moi viec
            # THANH CONG deu bi gan mot `failure_reason` gia va mot `summary`
            # rac. Adapter da doc JSON dung roi; doc lai la vua thua vua sai.
            pb = ResultEnvelope(
                task_id=c.task_id, status=kq.status, summary=kq.summary,
                changes=list(kq.files_changed), findings=list(kq.findings),
                risks=list(kq.blockers), artifacts=list(kq.artifacts),
                worker=p.runtime_id, model=m.model_id, provider=m.provider,
                duration=giay, failure_reason=kq.failure_reason,
                commit=kq.commit)
            if kq.tests:
                from scripts.router_v4.envelope import Tests
                pb.tests = Tests(detail=str(kq.tests)[:240])
            # Nhat ky THO van duoc giu lai tren dia de chan doan — chi la no
            # khong con la nguon de suy ra trang thai nua.
            pb.raw_log_ref = self.logs.write(c.task_id, kq.raw_excerpt or "")
            pb.branch = handle.branch if handle else ""
            pb.started_at, pb.ended_at = t0, time.time()
            pb.duration = giay
            pb.resource_usage.wall_seconds = giay
            pb.resource_usage.retries = max(0, attempt - 1)

            bc = self._kiem_dinh(c, pb, handle)
            self._bang_chung_lan_at_loi_khai(c, pb, bc, handle)
            if bc is not None and not bc.passed:
                hong = bc.failed_gates
                pb.status = "blocked" if "security" in hong else "failed"
                pb.failure_reason = ("security_gate" if "security" in hong
                                     else f"gate_{hong[0]}")
                pb.risks.append(
                    "kiểm định không đạt: "
                    + "; ".join(g.detail for g in bc.gates if not g.passed)[:300])

            self._ghi_lich_su(c, p, pb, bc, reassigned=reassigned)
            return ExecutionResult(envelope=pb, validation=bc,
                                   worktree=ws, branch=pb.branch)
        except (ExecutorError, WorktreeError) as exc:
            giay = time.time() - t0
            pb = ResultEnvelope(
                task_id=c.task_id, status="failed", worker=p.runtime_id,
                model=p.model_id, provider=m.provider, duration=giay,
                failure_reason="executor_error", summary=str(exc)[:600],
                started_at=t0, ended_at=time.time())
            self._ghi_lich_su(c, p, pb, None, reassigned=reassigned)
            return ExecutionResult(envelope=pb)

    @staticmethod
    def _noi_doc_phu_thuoc(dws: Optional[Dict[str, str]]) -> str:
        """Worktree DUY NHAT cua cac phu thuoc, neu chi co dung mot.

        Nhieu phu thuoc CO GHI o cac worktree khac nhau thi khong thu muc
        nao chua ca hai; luc do tra rong (roi ve goc kho) va de duong dan
        tung nhanh trong `dependency_summaries` cho worker tu dieu huong.
        Doan bua mot trong hai se cho reviewer doc nham nua ket qua.
        """
        duong = sorted({v for v in (dws or {}).values() if v})
        return duong[0] if len(duong) == 1 else ""

    def _bang_chung_lan_at_loi_khai(self, c: TaskContract, pb: ResultEnvelope,
                                    bc, handle: Optional[WorktreeHandle]) -> None:
        """BẰNG CHỨNG THẮNG LỜI KHAI — theo cả hai chiều.

        Nguyên tắc "không tin worker tự khai PASS" có một vế đối xứng ít ai
        để ý: cũng KHÔNG nên tin một worker khai HỎNG (hoặc không khai gì)
        khi bằng chứng khách quan nói việc đã xong.

        Bằng chứng thật (lượt chạy bằng chứng 2026-09-03): một worker viết
        ĐÚNG tệp được yêu cầu, đúng phạm vi, nội dung biên dịch được — rồi
        kết thúc lượt với phản hồi văn bản RỖNG. Không có khối JSON nào, nên
        phong bì thành `failed`, việc bị giao lại cho worker khác, và cả một
        lượt làm đúng bị vứt đi. Lặp lại ba lần thì mission "hỏng" trong khi
        trên đĩa đã có đúng thứ cần.

        Nâng trạng thái CHỈ KHI hợp đồng có bằng chứng KHÁCH QUAN và bằng
        chứng đó ĐẠT: mọi cổng kiểm định xanh, và hợp đồng có ít nhất một
        `artifact_checks` hoặc `tests` để kiểm. Không có gì kiểm được thì
        một phản hồi rỗng vẫn là hỏng — đúng như trước.
        """
        if pb.ok or bc is None or not bc.passed:
            return
        co_bang_chung = bool(c.verification.artifact_checks
                             or c.verification.tests)
        if not co_bang_chung:
            return
        # Voi viec CO GHI: phai co thay doi THAT tren dia, trong pham vi.
        if c.execution.worktree_required:
            if not bc.files_changed_observed or bc.scope_violations:
                return
        cu = pb.status
        pb.status = "ok"
        pb.warnings.append(
            f"worker kết thúc với trạng thái {cu!r} (phản hồi không đọc được), "
            f"nhưng MỌI cổng kiểm định đều đạt: "
            f"{len(bc.files_changed_observed)} tệp đổi đúng phạm vi, "
            f"{len(bc.tests_ran)} lệnh test xanh, hiện vật đầy đủ. "
            f"Trạng thái lấy theo BẰNG CHỨNG, không theo lời khai.")
        pb.failure_reason = ""

    def _kiem_dinh(self, c: TaskContract, pb: ResultEnvelope,
                   handle: Optional[WorktreeHandle]):
        """Cổng kiểm định. Việc chỉ đọc chỉ kiểm được hình dạng — nói rõ như
        vậy thay vì để báo cáo trông như đã kiểm đầy đủ."""
        from scripts.router_v3.packet import TaskResult
        gia = TaskResult(task_id=c.task_id, worker_id=pb.worker,
                         status=pb.status, summary=pb.summary,
                         files_changed=list(pb.changes),
                         blockers=list(pb.risks))
        bc = V.kiem_dinh(
            gia, worktree=(handle.path if handle else None),
            write_scope=tuple(c.allowed_scope),
            tests=c.verification.tests,
            wt_manager=self.worktrees, handle=handle,
            test_timeout=min(900.0, c.execution.max_wall_time))
        # Pham vi CAM la cua HOP DONG, kiem bang ham thuan cua no — cong
        # `scope` cua V3 chi biet `write_scope`.
        if handle is not None:
            vi_pham = c.scope_violations(bc.files_changed_observed)
            if vi_pham:
                bc.scope_violations = sorted(set(bc.scope_violations) | set(vi_pham))
                bc.gates.append(V.GateResult(
                    "contract_scope", False,
                    f"đổi tệp ngoài allowed_scope / chạm forbidden_scope: "
                    f"{vi_pham[:5]}"))
        if c.verification.artifact_checks:
            goc = Path(handle.path) if handle else self.root
            thieu = [a for a in c.verification.artifact_checks
                     if not (goc / a).exists()]
            bc.gates.append(V.GateResult(
                "artifacts", not thieu,
                "đủ hiện vật" if not thieu else f"thiếu hiện vật: {thieu[:5]}"))
        return bc

    def _ghi_lich_su(self, c: TaskContract, p: Placement, pb: ResultEnvelope,
                     bc, *, reassigned: bool) -> None:
        m = self.fabric.model(p.model_id)
        self.history.record(Record(
            ts=time.time(), task_type=c.type, provider=m.provider,
            model_id=m.model_id, runtime_id=p.runtime_id,
            wall_seconds=pb.duration, success=pb.ok and (bc is None or bc.passed),
            test_passed=pb.tests.passed, test_failed=pb.tests.failed,
            review_findings=len(pb.findings),
            retry_count=pb.resource_usage.retries, reassigned=reassigned,
            tokens=pb.resource_usage.tokens, cost_usd=pb.resource_usage.cost_usd))

    def shutdown(self) -> None:
        for a in list(self._cache.values()):
            try:
                a.shutdown()                              # type: ignore[attr-defined]
            except Exception:                             # noqa: BLE001
                pass
        self._cache.clear()
