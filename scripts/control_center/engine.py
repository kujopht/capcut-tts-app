"""Bộ máy Control Center — nơi mọi thứ nối vào Router V4.

ĐÂY LÀ LÁT CẮT DỌC của V0.1:

    ô chat -> phân rã việc -> quyết định định tuyến -> tạo/dùng lại worktree
    -> dựng phiên agent -> chạy -> phát sự kiện -> ghi sổ -> Pause/Stop
    -> sống sót qua khởi động lại

RANH GIỚI VỚI ROUTER V4, và vì sao nó nằm ở đúng chỗ này:

Control Center KHÔNG lập lịch lại, KHÔNG chấm điểm lại, KHÔNG dựng adapter,
KHÔNG kiểm định lại kết quả. Bốn thứ đó là Router V4 và chúng đã được đập
thật (xem `docs/reports/ROUTER_V4_REAL_PROOF.md`). Cái Control Center thêm
vào là thứ V4 cố ý không có: **trạng thái sống lâu hơn một mission**.

Cụ thể, `RouterV4.run_task()` tự chọn placement cho từng việc — đúng cho một
mission chạy một lần. Nhưng nó không thể DÙNG LẠI một phiên, vì với nó phiên
không tồn tại. Nên ở đây ta gọi thẳng `Executor.run(contract, placement)` với
placement do `SessionManager` đã chốt, và mượn lease khe runtime của V4 để
hai tầng không giao trùng một khe. Mọi cơ chế bên trong `Executor` — adapter,
worktree, cổng kiểm định, bằng chứng thắng lời khai — chạy y nguyên.

THỨ TỰ GIÀNH TÀI NGUYÊN LÀ CỐ ĐỊNH, và đảo nó là tạo ra deadlock:

    1. khoá tài nguyên (LockManager)   — rẻ nhất, nhả nhanh nhất
    2. quyết định phiên (SessionManager)
    3. lease khe runtime (Router V4)
    4. nhận việc (claim, nguyên tử)

Nhả thì theo thứ tự NGƯỢC LẠI, luôn luôn, trong `finally`.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.router_v3.worktree import WorktreeError, WorktreeHandle
from scripts.router_v4 import fabric_config as FC
from scripts.router_v4.contract import ContractError, TaskContract
from scripts.router_v4.envelope import RawLogStore
from scripts.router_v4.executor import Executor, ExecutionResult
from scripts.router_v4.history import BenchmarkStore
from scripts.router_v4.leases import LeaseStore, owner_id
from scripts.router_v4.runtime import Fabric, Placement
from scripts.router_v4.modes import hop_dong_review
from scripts.router_v4.scheduler import Demand, Scheduler

from scripts.control_center.locks import LockManager
from scripts.control_center.model import (LockKind, PermissionClass, Project,
                                          Session, SessionAction, SessionState,
                                          Task, TaskState, TransitionError,
                                          map_envelope_status)
from scripts.control_center.permissions import PermissionEnvelope, envelope_for
from scripts.control_center.planner import PlannedTask, PlanResult, RulePlanner
from scripts.control_center.sessions import SessionManager, dao_pid
from scripts.control_center.store import ControlStore
from scripts.control_center.usage import UsageReporter
from scripts.control_center.worktrees import WorktreeCoordinator

#: Bao nhieu luot cho MOI viec truoc khi bo cuoc. Trung `MAX_ATTEMPTS` cua
#: `router_v4/orchestrator.py` co chu dich — hai tang dem cung mot cach.
MAX_ATTEMPTS = 3

#: Nhip vong lap dieu phoi. Du nhanh de bang dieu khien thay thay doi, du
#: cham de khong quay CPU khi khong co viec.
TICK_SECONDS = 1.0


@dataclass
class ProjectContext:
    """Mọi thứ gắn với MỘT dự án. Dựng lười — mở dự án mới không dò gì cả."""

    project: Project
    fabric: Fabric
    scheduler: Scheduler
    executor: Executor
    sessions: SessionManager
    worktrees: WorktreeCoordinator
    leases: LeaseStore
    planner: RulePlanner
    logs: RawLogStore


class ControlCenter:
    """Mặt tiền của Control Center. Dựng rẻ; không khởi động agent nào."""

    def __init__(self, *, root: Optional[Path] = None,
                 store: Optional[ControlStore] = None,
                 fabric: Optional[Fabric] = None,
                 executor_factory=None,
                 probe: bool = False,
                 max_parallel: int = 3):
        self.root = Path(root) if root else Path.cwd()
        self.store = store if store is not None else ControlStore(root=self.root)
        self.max_parallel = max(1, max_parallel)
        self.owner = owner_id()
        # `probe=False` mac dinh: dung Control Center KHONG duoc goi mang.
        # Do suc khoe that la mot thao tac cham va ton mot luot moi provider;
        # no thuoc ve nut "lam moi", khong thuoc ve ham dung.
        self._fabric = fabric
        self._probe = probe
        self._executor_factory = executor_factory
        self._ctx: Dict[str, ProjectContext] = {}
        self._khoa = threading.Lock()
        self._dang_chay: Dict[str, threading.Thread] = {}
        self._dung_lai = threading.Event()
        self._luong_vong: Optional[threading.Thread] = None
        self._usage: Optional[UsageReporter] = None

    # -- 0. Fabric dung chung ------------------------------------------------

    @property
    def fabric(self) -> Fabric:
        """Fabric DÙNG CHUNG cho mọi dự án.

        Cố ý dùng chung: `WorkerRuntime` mang `running_tasks` và hạn mức
        đồng thời của một TÀI KHOẢN THẬT. Hai dự án dựng hai fabric riêng sẽ
        mỗi bên tưởng AG01 đang rảnh, và cùng đẩy việc vào một tài khoản chỉ
        có 3 khe. Tài khoản là tài nguyên toàn cục, nên sổ của nó cũng phải
        toàn cục.
        """
        if self._fabric is None:
            f, _w, _e = FC.nap(root=self.root, probe=self._probe)
            self._fabric = f
        return self._fabric

    @property
    def usage(self) -> UsageReporter:
        if self._usage is None:
            self._usage = UsageReporter(self.store, fabric=self.fabric)
        return self._usage

    # -- 1. Du an ------------------------------------------------------------

    def them_project(self, project: Project) -> Project:
        self.store.luu_project(project)
        self.store.ghi_su_kien("PROJECT_ADDED", project_id=project.project_id,
                               detail=f"{project.name} @ {project.repo_path}")
        return project

    def projects(self) -> List[Project]:
        return self.store.projects()

    def ctx(self, project_id: str) -> ProjectContext:
        """Ngữ cảnh của một dự án. Dựng một lần, giữ lại."""
        with self._khoa:
            c = self._ctx.get(project_id)
            if c is not None:
                return c
        p = self.store.project(project_id)
        if p is None:
            raise KeyError(f"không có dự án {project_id!r}")

        goc = Path(p.repo_path)
        f = self.fabric
        sched = Scheduler(f, history=BenchmarkStore(root=goc))
        wt = WorktreeCoordinator(project_id, goc, self.store)
        logs = RawLogStore(root=goc)

        if self._executor_factory is not None:
            ex = self._executor_factory(p, f)
        else:
            ex = Executor(f, root=goc, worktrees=wt.manager, logs=logs)
        # Phien so huu worktree, nen Executor phai HOI phien thay vi tu tao.
        ex.worktree_provider = self._cap_worktree(project_id)

        sm = SessionManager(project_id, self.store, fabric=f, scheduler=sched,
                            worktrees=wt, max_sessions=self.max_parallel)
        ctx = ProjectContext(
            project=p, fabric=f, scheduler=sched, executor=ex, sessions=sm,
            worktrees=wt, leases=LeaseStore(root=self.root),
            planner=RulePlanner(default_write_scope=self._scope_mac_dinh(p)),
            logs=logs)
        with self._khoa:
            self._ctx[project_id] = ctx
        return ctx

    @staticmethod
    def _scope_mac_dinh(p: Project) -> Tuple[str, ...]:
        """Phạm vi ghi mặc định khai trong `resources` với tiền tố `write:`.

        Không có thì bộ lập kế hoạch KHÔNG đoán — việc bị hạ xuống chỉ đọc
        kèm ghi chú. Xem `planner.RulePlanner.plan`.
        """
        return tuple(r.split(":", 1)[1] for r in p.resources
                     if str(r).startswith("write:") and ":" in r)

    def _cap_worktree(self, project_id: str):
        """Hook cho `Executor.worktree_provider` — trả cây của PHIÊN.

        Trả `None` khi không tra được phiên: `Executor` sẽ tự tạo cây mới,
        tức là lùi về đúng hành vi Router V4 vốn có. Không bao giờ ném từ
        đây — một lỗi tra sổ không được phép làm hỏng một lượt chạy đã tới
        tận bước dựng cây.
        """
        def _lay(c: TaskContract, p: Placement, base_sha: str, attempt: int):
            try:
                t = self.store.task(c.task_id)
                if t is None or not t.owner_session:
                    return None
                s = self.store.session(t.owner_session)
                if s is None or not s.worktree:
                    return None
                h = self.store.worktree(s.worktree)
                if h is None or not Path(s.worktree).exists():
                    return None
                return WorktreeHandle(
                    worker_id=s.runtime_id, task_id=c.task_id,
                    path=Path(s.worktree), branch=s.branch,
                    base_sha=h.get("base_sha", "") or base_sha)
            except Exception:                             # noqa: BLE001
                return None
        return _lay

    # -- 2. O chat -----------------------------------------------------------

    def chat(self, project_id: str, text: str) -> Dict:
        """Ý định người dùng -> việc được quản lý. Đây là CỔNG VÀO của V0.1.

        Việc GATED KHÔNG vào hàng đợi. Nó được tạo ở `BLOCKED` kèm câu hỏi
        cụ thể — người dùng phải mở khoá bằng `mo_khoa_gated()`. Cho phép nó
        `QUEUED` rồi chặn ở bước sau là để một lỗi lập lịch duy nhất đủ để
        nó chạy.
        """
        ctx = self.ctx(project_id)
        self.store.them_chat(project_id, "user", text)

        kh: PlanResult = ctx.planner.plan(text, ctx.project)
        tao: List[Task] = []
        for pt in kh.tasks:
            gated = pt.envelope.gated
            t = Task(
                task_id=f"{project_id}.{pt.task_id}",
                project_id=project_id, title=pt.title, objective=pt.objective,
                state=TaskState.BLOCKED if gated else TaskState.QUEUED,
                priority=pt.priority,
                dependencies=tuple(f"{project_id}.{d}"
                                   for d in pt.dependencies),
                contract=self._hop_dong_dict(pt, project_id),
                permission=pt.envelope.decision.value,
                gate_reason=pt.envelope.ly_do(),
                blocked_reason=(pt.envelope.cau_hoi_cho_nguoi_dung()
                                if gated else ""),
                resources=tuple(f"{k.value}:{r}" for k, r in pt.resources))
            self.store.luu_task(t)
            tao.append(t)
            self.store.ghi_su_kien(
                "TASK_CREATED", project_id=project_id, task_id=t.task_id,
                level="WARNING" if gated else "INFO",
                detail=f"{pt.kind}: {pt.title}",
                meta={"permission": t.permission, "kind": pt.kind,
                      "scope": list(pt.contract.allowed_scope)})

        tra_loi = kh.render()
        self.store.them_chat(project_id, "router", tra_loi,
                             meta={"plan": kh.to_dict(),
                                   "task_ids": [t.task_id for t in tao]})
        return {"reply": tra_loi, "tasks": [t.to_dict() for t in tao],
                "plan": kh.to_dict()}

    @staticmethod
    def _hop_dong_dict(pt: PlannedTask, project_id: str) -> Dict:
        """Hợp đồng đã gắn `task_id` có tiền tố dự án + phong bì quyền.

        Phong bì được RENDER VÀO mục tiêu, không chỉ lưu bên cạnh: agent
        phải đọc được ranh giới của nó trong đúng văn bản nó nhận. Một
        trường JSON mà agent không bao giờ thấy thì không phải là một rào.
        """
        d = pt.contract.to_dict()
        d["task_id"] = f"{project_id}.{pt.task_id}"
        d["dependencies"] = [f"{project_id}.{x}" for x in pt.dependencies]
        d["objective"] = (pt.objective + "\n\n" +
                          pt.envelope.render_for_agent())
        d["_permission"] = pt.envelope.to_dict()
        return d

    def mo_khoa_gated(self, task_id: str, *, approved_by: str = "user",
                      note: str = "") -> Task:
        """Người dùng cho phép một việc GATED chạy. CHỈ người mới gọi được.

        Không có đường tự động nào tới hàm này. Nó tồn tại để việc mở cổng
        là một hành vi CÓ DẤU VẾT: ai duyệt, lúc nào, với ghi chú gì.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if t.permission != PermissionClass.GATED.value:
            return t
        self.store.ghi_su_kien(
            "GATE_APPROVED", project_id=t.project_id, task_id=task_id,
            level="ALERT",
            detail=f"người dùng ({approved_by}) mở cổng: {t.gate_reason}",
            meta={"approved_by": approved_by, "note": note,
                  "gate_reason": t.gate_reason})
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="người dùng đã duyệt cổng")

    # -- 3. Vong lap dieu phoi ----------------------------------------------

    def tick(self) -> Dict:
        """Một nhịp điều phối. Trả về những gì nhịp này đã làm.

        Hàm này KHÔNG chặn: mọi việc chạy trong luồng riêng. Một `tick` chỉ
        quyết định và giao; nó không bao giờ đợi một agent.
        """
        da_giao: List[str] = []
        cho: List[Dict] = []
        with self._khoa:
            đang = len([t for t in self._dang_chay.values() if t.is_alive()])
            self._dang_chay = {k: v for k, v in self._dang_chay.items()
                               if v.is_alive()}
        if đang >= self.max_parallel:
            return {"dispatched": [], "waiting": [],
                    "note": f"đã chạm trần {self.max_parallel} việc song song"}

        for p in self.projects():
            for t in self._san_sang(p.project_id):
                with self._khoa:
                    if len(self._dang_chay) >= self.max_parallel:
                        break
                    if t.task_id in self._dang_chay:
                        continue
                kq = self._giao(t)
                if kq.get("dispatched"):
                    da_giao.append(t.task_id)
                else:
                    cho.append(kq)
        return {"dispatched": da_giao, "waiting": cho}

    def _san_sang(self, project_id: str) -> List[Task]:
        """Việc đủ điều kiện chạy: QUEUED/WAITING + mọi phụ thuộc đã DONE.

        Phụ thuộc HỎNG thì việc con không bao giờ chạy — đánh dấu ngay thay
        vì để nó nằm `WAITING` mãi mãi và trông như đang tiến triển.
        """
        ra: List[Task] = []
        tat_ca = {t.task_id: t for t in self.store.tasks(project_id)}
        for t in tat_ca.values():
            if t.state not in (TaskState.QUEUED, TaskState.WAITING):
                continue
            deps = [tat_ca.get(d) for d in t.dependencies]
            if any(d is not None and d.state is TaskState.FAILED for d in deps):
                self.store.doi_trang_thai(
                    t.task_id, TaskState.BLOCKED,
                    reason="phụ thuộc đã hỏng — không tự chạy tiếp")
                continue
            # Mot viec REVIEW phu thuoc vao CHA cua no, nhung cha chi thoat
            # `REVIEW` SAU KHI review chay xong. Doi cha phai `DONE` truoc
            # thi hai ben khoa nhau vinh vien: cha cho review, review cho
            # cha. Nen voi dung quan he cha-con nay, `REVIEW` la du dieu
            # kien — do chinh la trang thai "da xong phan viec, dang cho
            # kiem cheo".
            #
            # Not loi nay hep co chu dich: chi ap cho `parent_id` cua chinh
            # viec do, khong ap cho phu thuoc thuong. Mot viec thuong van
            # phai cho phu thuoc `DONE` that.
            chua = [d.task_id for d in deps
                    if d is not None and d.state is not TaskState.DONE
                    and not (d.task_id == t.parent_id
                             and d.state is TaskState.REVIEW)]
            if chua:
                if t.state is not TaskState.WAITING:
                    self.store.doi_trang_thai(
                        t.task_id, TaskState.WAITING,
                        reason=f"chờ {', '.join(chua)}")
                continue
            ra.append(t)
        ra.sort(key=lambda x: (x.priority, x.created_at))
        return ra

    def _giao(self, t: Task) -> Dict:
        """Thử giao MỘT việc. Không chặn, không ném.

        Thứ tự giành tài nguyên cố định — xem docstring module. Mỗi bước
        hỏng đều nhả sạch những gì đã giành ở bước trước.
        """
        ctx = self.ctx(t.project_id)
        try:
            hd = TaskContract.from_dict(t.contract)
        except (ContractError, KeyError, ValueError) as exc:
            self.store.doi_trang_thai(
                t.task_id, TaskState.FAILED,
                reason=f"hợp đồng hỏng: {type(exc).__name__}: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": "hợp đồng hỏng"}

        # (1) khoa tai nguyen
        lm = LockManager(self.store)
        xin = [(LockKind(r.split(":", 1)[0]), r.split(":", 1)[1])
               for r in t.resources if ":" in r]
        grant = lm.xin(t.project_id, xin, task_id=t.task_id) if xin else None
        if grant is not None and not grant.granted:
            self._sang_waiting(t, grant.reason)
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": grant.reason, "conflict": grant.to_dict()}

        # (2) quyet dinh phien
        try:
            nhu_cau = Demand.from_contracts(
                [TaskContract.from_dict(x.contract)
                 for x in self.store.tasks(
                     t.project_id, states=(TaskState.QUEUED, TaskState.WAITING))
                 if x.contract])
        except (ContractError, ValueError):
            nhu_cau = None

        qd = ctx.sessions.decide(
            t, hd, demand=nhu_cau,
            conflicting_task=(grant.conflict_holder_task
                              if grant is not None and not grant.granted
                              else ""))
        self.store.ghi_su_kien(
            "SESSION_DECISION", project_id=t.project_id, task_id=t.task_id,
            detail=f"{qd.action.value}: {qd.reason}"[:400], meta=qd.to_dict())

        if qd.action is SessionAction.WAIT:
            lm.tra(t.project_id, t.task_id)
            self._sang_waiting(t, qd.reason)
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": qd.reason, "decision": qd.to_dict()}

        try:
            if qd.action is SessionAction.REUSE:
                s = ctx.sessions.reuse(qd.session_id, t, contract=hd)
            else:
                s = ctx.sessions.create(qd, t, contract=hd)
        except (WorktreeError, ValueError) as exc:
            lm.tra(t.project_id, t.task_id)
            self.store.doi_trang_thai(
                t.task_id, TaskState.BLOCKED,
                reason=f"không cấp được cây làm việc: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": str(exc)[:200]}

        # (3) lease KHE runtime cua Router V4
        khoa_lease = self._muon_lease(ctx, s.runtime_id, t.task_id)
        if khoa_lease is None:
            lm.tra(t.project_id, t.task_id)
            ly_do = (f"runtime {s.runtime_id} hết khe đồng thời — chờ lượt "
                     f"sau thay vì đẩy thêm vào một tài khoản đã đầy")
            self._sang_waiting(t, ly_do)
            return {"task_id": t.task_id, "dispatched": False, "reason": ly_do}

        # (4) NHAN VIEC — nguyen tu. Truoc buoc nay moi thu deu hoan tac duoc.
        if not self.store.claim_task(t.task_id, s.session_id):
            ctx.leases.release(khoa_lease, self.owner)
            lm.tra(t.project_id, t.task_id)
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": "việc đã bị một vòng lập lịch khác nhận trước"}

        # ĐỌC LẠI việc sau khi `claim`. Bản `t` trong tay đã CŨ: `claim_task`
        # đổi trạng thái bằng một câu `UPDATE` thẳng xuống SQL (nó phải vậy
        # để nguyên tử), nên ghi đè bằng đối tượng cũ sẽ kéo trạng thái từ
        # `RUNNING` ngược về `QUEUED` — và việc coi như chưa từng được nhận.
        # Đây đúng là chế độ hỏng "đọc–sửa–ghi" mà docstring của `store.py`
        # cảnh báo; nó lọt vào ngay lần dựng đầu tiên.
        t = self.store.task(t.task_id) or t
        # Chi ghi worktree cho viec THAT SU co ghi. Mot viec CHI DOC dung
        # lai mot phien tung chay viec co ghi se thua huong `s.worktree`,
        # va bang dieu khien se hien no nhu the viec do so huu cay ay —
        # sai, va sai theo huong nguy hiem: nguoi van hanh doc bang se
        # tuong mot viec chi doc dang sua tep o do.
        if hd.execution.worktree_required:
            t.worktree, t.branch = s.worktree, s.branch
        t.owner_session = s.session_id
        self.store.luu_task(t)
        ctx.sessions.bat_dau_viec(s.session_id, t.task_id)

        luong = threading.Thread(
            target=self._chay, name=f"cc-{t.task_id}", daemon=True,
            args=(ctx, t.task_id, hd, Placement(s.runtime_id, s.model_id),
                  s.session_id, khoa_lease))
        with self._khoa:
            self._dang_chay[t.task_id] = luong
        luong.start()
        return {"task_id": t.task_id, "dispatched": True,
                "session_id": s.session_id, "placement": s.placement_key,
                "action": qd.action.value}

    def _dat_review(self, ctx: ProjectContext, task_id: str,
                    hd: TaskContract, p: Placement) -> None:
        """Đặt một việc REVIEW ĐỘC LẬP làm CON của việc vừa xong.

        VÌ SAO PHẢI CÓ: không có bước này, `REVIEW` là ngõ cụt — việc xong,
        hợp đồng đòi review, và nó nằm đó mãi mãi. Một trạng thái không ai
        đưa ra khỏi được thì tệ hơn là không có trạng thái đó.

        ĐỘC LẬP THẬT, không chỉ trên danh nghĩa: `hop_dong_review()` của
        Router V4 loại HỌ MODEL của tác giả (`exclude_families`) và KHÔNG
        cấp `repo_write`. Một reviewer cùng họ với tác giả, hoặc sửa được
        thứ nó vừa chấm, không phải kiểm tra độc lập.

        Việc review là CON (`parent_id`) chứ không phải anh em: nó không tồn
        tại nếu không có việc cha, và bảng điều khiển phải xếp nó dưới cha
        thay vì thành một dòng lơ lửng không ai hiểu từ đâu ra.
        """
        try:
            ho = ctx.fabric.model(p.model_id).model_family
        except KeyError:
            ho = ""
        rid = f"{task_id}-review"
        if self.store.task(rid) is not None:
            return                            # da dat roi — khong nhan doi
        try:
            hd_review = hop_dong_review(hd, author_family=ho, review_id=rid)
        except (ContractError, ValueError) as exc:
            self.store.ghi_su_kien(
                "REVIEW_SKIPPED", project_id=ctx.project.project_id,
                task_id=task_id, level="WARNING",
                detail=f"không dựng được hợp đồng review: {exc}"[:300])
            return

        cha = self.store.task(task_id)
        d = hd_review.to_dict()
        # Reviewer phai DOC duoc ket qua no dang cham. Voi viec CO GHI, ket
        # qua nam trong worktree co lap, KHONG nam o goc kho — bang chung
        # that 2026-09-03: mot nut review bao "khong tim thay tep" trong khi
        # tep CO ton tai, chi la o worktree cua nut truoc.
        if cha is not None and cha.worktree:
            d["objective"] += (
                f"\n\nĐỌC KẾT QUẢ Ở ĐÂY (không phải ở gốc kho): "
                f"{cha.worktree}\nnhánh: {cha.branch}")
        self.store.luu_task(Task(
            task_id=rid, project_id=ctx.project.project_id,
            title=f"review độc lập: {(cha.title if cha else task_id)}"[:120],
            objective=d["objective"], state=TaskState.QUEUED,
            priority=(cha.priority - 1 if cha else 40),
            parent_id=task_id, dependencies=(task_id,), contract=d,
            permission=PermissionClass.AUTO.value))
        self.store.ghi_su_kien(
            "REVIEW_QUEUED", project_id=ctx.project.project_id, task_id=rid,
            detail=(f"review độc lập cho {task_id}; loại họ model "
                    f"{ho or '(không rõ)'} để tác giả không tự chấm bài"),
            meta={"parent": task_id, "exclude_family": ho})

    def _khep_review(self, t: Task) -> None:
        """Việc review xong -> đóng việc CHA.

        Phát hiện của reviewer KHÔNG tự động làm việc cha thất bại — nó là
        thông tin cho người tích hợp, đúng như `RouterV4.run_task` đã quyết.
        Nhưng nó PHẢI hiện ra: một lượt review tốn tiền mà không ai thấy kết
        quả thì chỉ là đốt quota.
        """
        cha = self.store.task(t.parent_id)
        if cha is None or cha.state is not TaskState.REVIEW:
            return
        pb = ((t.result or {}).get("envelope") or {})
        pham = list(pb.get("findings") or [])
        if t.state is TaskState.FAILED:
            self.store.doi_trang_thai(
                cha.task_id, TaskState.BLOCKED,
                reason=(f"review độc lập ({t.task_id}) không chạy được — "
                        f"kết quả CHƯA được kiểm tra chéo"))
            return
        self.store.doi_trang_thai(
            cha.task_id, TaskState.DONE,
            reason=(f"review độc lập xong: {len(pham)} phát hiện"
                    if pham else "review độc lập không thấy vấn đề"))
        if pham:
            c = self.store.task(cha.task_id)
            if c is not None:
                kq = dict(c.result or {})
                env = dict(kq.get("envelope") or {})
                env["findings"] = list(env.get("findings") or []) + [
                    f"[review/{pb.get('model', '?')}] {x}" for x in pham[:10]]
                kq["envelope"] = env
                c.result = kq
                self.store.luu_task(c)
            self.store.ghi_su_kien(
                "REVIEW_FINDINGS", project_id=cha.project_id,
                task_id=cha.task_id, level="WARNING",
                detail=f"{len(pham)} phát hiện từ review độc lập",
                meta={"findings": pham[:10], "reviewer": pb.get("model", "")})

    def _sang_waiting(self, t: Task, reason: str) -> None:
        if t.state is not TaskState.WAITING:
            try:
                self.store.doi_trang_thai(t.task_id, TaskState.WAITING,
                                          reason=reason[:400])
            except TransitionError:
                pass

    def _muon_lease(self, ctx: ProjectContext, runtime_id: str,
                    task_id: str) -> Optional[str]:
        """Giành MỘT KHE của runtime — cùng ngữ nghĩa `RouterV4._muon_lease`.

        Khoá theo KHE (`AG01#0`), không theo runtime. Bằng chứng thật
        2026-09-03: khoá theo runtime ép AG01 (3 khe) xuống 1 việc một lúc
        và "song song" mất sạch ý nghĩa. Lặp lại đúng ngữ nghĩa ở đây để
        Control Center và một lượt `run_mission` của V4 chạy cạnh nhau mà
        không giao trùng khe.
        """
        r = ctx.fabric.runtimes.get(runtime_id)
        for i in range(max(1, r.concurrency if r else 1)):
            khoa = f"{runtime_id}#{i}"
            if ctx.leases.acquire(khoa, self.owner, task_id=task_id) is not None:
                return khoa
        return None

    # -- 4. Chay mot viec ----------------------------------------------------

    def _chay(self, ctx: ProjectContext, task_id: str, hd: TaskContract,
              p: Placement, session_id: str, khoa_lease: str) -> None:
        """Chạy MỘT việc trên MỘT placement. Chạy trong luồng riêng.

        Không bao giờ để một ngoại lệ thoát ra: luồng này chết im lặng sẽ để
        việc kẹt ở `RUNNING` mãi mãi, khoá không được nhả, và bảng điều
        khiển nói dối. Mọi đường ra đều đi qua `finally`.
        """
        t0 = time.time()
        kq: Optional[ExecutionResult] = None
        lm = LockManager(self.store)
        nhip = threading.Event()

        def _dap_nhip() -> None:
            # Viec dai hon TTL van phai giu duoc lease VA khoa cua no.
            while not nhip.wait(20.0):
                try:
                    con_giu = ctx.leases.heartbeat(khoa_lease, self.owner)
                    lm.gia_han(ctx.project.project_id, task_id)
                except Exception:                         # noqa: BLE001
                    return
                if con_giu:
                    continue
                # LEASE DA BI CUOP. Hop dong cua `LeaseStore.heartbeat` noi
                # ro: `False` nghia la ta khong con so huu khe do nua.
                #
                # KHONG giet luot dang bay, va day la mot danh doi CO Y CHON,
                # khong phai bo sot: TTL 90s / nhip 20s nghia la phai truot
                # BON nhip lien tiep moi mat lease — gan nhu chac chan la mot
                # lan SQLite kho tho, khong phai mot bo lap lich thu hai that
                # su. Giet mot luot agent dang chay dung 60 giay vi mot cai
                # nac cua o dia la doi mot hong hiem lay mot hong thuong xuyen.
                #
                # Nhung cung KHONG im lang: neu that su co hai chu, do la
                # dung che do hong ma lease ton tai de chan, va no phai hien
                # ra o muc ALERT chu khong chim trong log. Ngung dap nhip —
                # tiep tuc dap la gia vo con so huu mot thu da mat.
                self.store.ghi_su_kien(
                    "LEASE_LOST", project_id=ctx.project.project_id,
                    task_id=task_id, session_id=session_id, level="ALERT",
                    detail=(f"lease {khoa_lease} đã bị chủ khác giành — việc "
                            f"này KHÔNG còn sở hữu khe đó. Lượt đang bay vẫn "
                            f"chạy nốt (giết nó vì một lần nghẽn sổ còn tệ "
                            f"hơn), nhưng nếu thấy sự kiện này thì CÓ một bộ "
                            f"lập lịch thứ hai đang chạy — kiểm tra ngay."),
                    meta={"lease": khoa_lease, "owner": self.owner})
                return

        tim = threading.Thread(target=_dap_nhip, daemon=True,
                               name=f"cc-hb-{task_id}")
        tim.start()
        try:
            ctx.fabric.mark_started(p.runtime_id, task_id)
            self.store.ghi_su_kien(
                "TASK_STARTED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id,
                detail=f"{p.key} @ {hd.execution.max_wall_time:.0f}s trần")

            kq = ctx.executor.run(
                hd, p, base_sha=ctx.worktrees.base_sha(),
                attempt=max(1, (self.store.task(task_id) or Task(
                    task_id, "", "", "")).attempts))

            pb = kq.envelope
            pid = dao_pid(ctx.executor._cache.get(p.key))
            moi = map_envelope_status(
                pb.status,
                need_review=hd.verification.independent_review_required)
            # Cong kiem dinh cua V4 THANG loi khai cua worker. `kq.ok` da gop
            # ca hai; dung `pb.status` mot minh se de mot ket qua "ok" vuot
            # qua mot cong `diff`/`scope` hong.
            if moi is not TaskState.BLOCKED and not kq.ok:
                moi = TaskState.FAILED

            t = self.store.task(task_id)
            if t is not None:
                t.result = kq.to_dict()
                t.worktree = kq.worktree or t.worktree
                t.branch = kq.branch or t.branch
                self.store.luu_task(t)

            ly_do = pb.failure_reason or ""
            if pb.requires_decision:
                ly_do = (pb.decision_request or ly_do or
                         "agent yêu cầu một quyết định")
            self.store.doi_trang_thai(task_id, moi, reason=ly_do[:600],
                                      session_id=session_id)
            if moi is TaskState.REVIEW:
                self._dat_review(ctx, task_id, hd, p)
            self.store.ghi_su_kien(
                "TASK_FINISHED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id,
                level=("INFO" if moi in (TaskState.DONE, TaskState.REVIEW)
                       else "ERROR"),
                detail=f"{moi.value} sau {time.time()-t0:.1f}s — {pb.summary}"[:600],
                meta={"status": pb.status, "ok": kq.ok,
                      "raw_log_ref": pb.raw_log_ref, "changes": pb.changes[:20],
                      "findings": pb.findings[:10], "risks": pb.risks[:10],
                      "placement": p.key, "duration": round(pb.duration, 2)})
            ctx.sessions.ket_thuc_viec(session_id, task_id, ok=kq.ok, pid=pid)
            # Viec vua xong la mot REVIEW -> khep viec CHA lai. Lam sau khi
            # da ghi trang thai/su kien cua chinh no, de neu buoc khep hong
            # thi ket qua review van con nguyen tren so.
            xong = self.store.task(task_id)
            if xong is not None and xong.parent_id:
                self._khep_review(xong)

        except Exception as exc:                          # noqa: BLE001
            self.store.ghi_su_kien(
                "TASK_CRASHED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id, level="ERROR",
                detail=f"{type(exc).__name__}: {exc}"[:600])
            try:
                self.store.doi_trang_thai(
                    task_id, TaskState.FAILED, force=True,
                    reason=f"luồng điều phối hỏng: {type(exc).__name__}: {exc}"[:400])
            except Exception:                             # noqa: BLE001
                pass
            ctx.sessions.ket_thuc_viec(session_id, task_id, ok=False)
        finally:
            nhip.set()
            try:
                ctx.fabric.mark_finished(
                    p.runtime_id, task_id, ok=bool(kq and kq.ok),
                    model_id=p.model_id,
                    seconds=kq.envelope.duration if kq else time.time() - t0)
            except Exception:                             # noqa: BLE001
                pass
            ctx.leases.release(khoa_lease, self.owner)
            lm.tra(ctx.project.project_id, task_id)
            with self._khoa:
                self._dang_chay.pop(task_id, None)

    # -- 5. Dieu khien ------------------------------------------------------

    def pause(self, task_id: str, *, reason: str = "người dùng tạm dừng") -> Task:
        """Tạm dừng một việc.

        Việc CHƯA chạy thì dừng ngay và sạch. Việc ĐANG chạy thì `PAUSED`
        được ghi nhận nhưng lượt đang bay vẫn chạy nốt — nói rõ như vậy thay
        vì giả vờ đã dừng: `Executor.run` là đồng bộ, và cách duy nhất cắt
        nó giữa chừng là giết tiến trình agent (đó là `stop`, không phải
        `pause`).
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        dang_chay = t.state is TaskState.RUNNING
        t2 = self.store.doi_trang_thai(
            task_id, TaskState.PAUSED,
            reason=reason + (" (lượt đang bay vẫn chạy nốt)" if dang_chay else ""))
        if t.owner_session:
            self.ctx(t.project_id).sessions.drain(
                t.owner_session, reason=f"việc {task_id} bị tạm dừng")
        return t2

    def resume(self, task_id: str) -> Task:
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if t.owner_session:
            s = self.store.session(t.owner_session)
            if s is not None and s.state is SessionState.DRAINING:
                self.store.dat_trang_thai_session(
                    s.session_id, SessionState.IDLE, note="tiếp tục")
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="người dùng tiếp tục")

    def stop(self, task_id: str, *, reason: str = "người dùng dừng") -> Task:
        """Dừng hẳn một việc VÀ cắt lượt agent đang bay nếu có.

        Cắt thật = gọi `adapter.cancel()`, và với mọi adapter trong kho này
        `cancel()` nghĩa là GIẾT tiến trình (adapter tự ghi rõ như vậy). Kết
        quả của lượt đang chạy mất — đó là cái giá của việc dừng thật, và nó
        được ghi vào sự kiện thay vì giấu đi.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        ctx = self.ctx(t.project_id)
        s = self.store.session(t.owner_session) if t.owner_session else None
        cat = False
        if s is not None:
            ad = ctx.executor._cache.get(s.placement_key)
            if ad is not None and hasattr(ad, "cancel"):
                try:
                    ad.cancel()
                    cat = True
                except Exception as exc:                  # noqa: BLE001
                    self.store.ghi_su_kien(
                        "AGENT_CANCEL_FAILED", project_id=t.project_id,
                        task_id=task_id, session_id=s.session_id,
                        level="WARNING", detail=f"{type(exc).__name__}: {exc}"[:300])
            ctx.sessions.dung(s.session_id, reason=reason,
                              state=SessionState.STOPPED)
        t2 = self.store.doi_trang_thai(
            task_id, TaskState.FAILED, force=True,
            reason=reason + ("; đã cắt tiến trình agent, kết quả lượt đang "
                             "chạy bị mất" if cat else "; không có tiến trình "
                             "agent nào để cắt"))
        LockManager(self.store).tra(t.project_id, task_id)
        self.store.ghi_su_kien(
            "TASK_STOPPED", project_id=t.project_id, task_id=task_id,
            level="WARNING", detail=reason[:300], meta={"agent_killed": cat})
        return t2

    def reassign(self, task_id: str, *,
                 exclude_runtime: str = "") -> Task:
        """Giao lại việc cho một phiên/placement KHÁC.

        Nhả phiên hiện tại rồi đưa việc về `QUEUED`. Lượt sau, `decide()` sẽ
        không thấy phiên cũ trong danh sách sống nữa nên tự chọn chỗ khác —
        không cần một đường định tuyến thứ hai.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        ctx = self.ctx(t.project_id)
        if t.owner_session:
            ctx.sessions.dung(
                t.owner_session, state=SessionState.STOPPED,
                reason=f"giao lại {task_id}"
                       + (f" (tránh {exclude_runtime})" if exclude_runtime else ""))
        t.owner_session = ""
        self.store.luu_task(t)
        self.store.ghi_su_kien(
            "TASK_REASSIGNED", project_id=t.project_id, task_id=task_id,
            detail=f"nhả phiên cũ; sẽ chọn chỗ mới ở nhịp sau")
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="giao lại", force=True)

    # -- 6. Phuc hoi ---------------------------------------------------------

    def recover(self) -> Dict:
        """Đối soát MỌI trạng thái với thực tế. Chạy lúc khởi động.

        Bốn nhóm, theo thứ tự an toàn tăng dần:

            1. khoá  — hết hạn thì thu, TRỪ khoá production (cần người).
            2. phiên — có PID sống thì gắn lại; chết thì `DEAD`.
            3. worktree — đối soát với đĩa; chỉ đánh dấu, KHÔNG xoá.
            4. việc  — `RUNNING` mà chủ đã chết thì về `QUEUED` để chạy lại,
                       trừ khi đã cạn lượt thử.

        Việc `RUNNING` mồ côi KHÔNG bị đánh `FAILED` ngay: một tiến trình
        agent có thể vẫn đang chạy thật (Control Center tắt không giết nó).
        Đưa về `QUEUED` để nó được xét lại là hành vi thu hồi được; đánh
        `FAILED` thì mất luôn công việc đã làm.
        """
        bc: Dict = {"locks": {}, "sessions": {}, "worktrees": {}, "tasks": []}
        bc["locks"] = LockManager(self.store).reclaim()

        for p in self.projects():
            ctx = self.ctx(p.project_id)
            bc["sessions"][p.project_id] = ctx.sessions.recover()
            bc["worktrees"][p.project_id] = ctx.worktrees.doi_soat()

            song = {s.session_id for s in
                    self.store.sessions(p.project_id, alive_only=True)}
            for t in self.store.tasks(p.project_id, states=(TaskState.RUNNING,)):
                if t.owner_session and t.owner_session in song:
                    continue                  # phien con song -> de yen
                if t.attempts >= MAX_ATTEMPTS:
                    self.store.doi_trang_thai(
                        t.task_id, TaskState.BLOCKED, force=True,
                        reason=(f"đang RUNNING khi Control Center tắt và đã "
                                f"cạn {MAX_ATTEMPTS} lượt thử — cần người xem"))
                else:
                    self.store.doi_trang_thai(
                        t.task_id, TaskState.QUEUED, force=True,
                        reason=("phiên chủ không còn sau khởi động lại — đưa "
                                "về hàng đợi để xét lại"))
                bc["tasks"].append(t.task_id)
        self.store.ghi_su_kien(
            "RECOVERED", level="WARNING",
            detail=(f"phục hồi: {len(bc['tasks'])} việc mồ côi, "
                    f"{len(bc['locks'].get('reclaimed', []))} khoá thu hồi, "
                    f"{len(bc['locks'].get('needs_human', []))} khoá "
                    f"production CẦN NGƯỜI"),
            meta=bc)
        return bc

    # -- 7. Vong lap nen -----------------------------------------------------

    def start(self, *, interval: float = TICK_SECONDS) -> None:
        """Chạy vòng lặp điều phối trong nền."""
        if self._luong_vong is not None and self._luong_vong.is_alive():
            return
        self._dung_lai.clear()

        def _vong() -> None:
            while not self._dung_lai.wait(interval):
                try:
                    self.tick()
                except Exception as exc:                  # noqa: BLE001
                    # Vong lap dieu phoi KHONG duoc chet vi mot nhip hong —
                    # nhung cung KHONG duoc im lang. Mot `pass` o day nghia
                    # la bang dieu khien tiep tuc ve trong khi khong con gi
                    # duoc giao nua.
                    self.store.ghi_su_kien(
                        "TICK_FAILED", level="ERROR",
                        detail=f"{type(exc).__name__}: {exc}"[:400])

        self._luong_vong = threading.Thread(target=_vong, daemon=True,
                                            name="cc-scheduler")
        self._luong_vong.start()
        self.store.ghi_su_kien("ENGINE_STARTED",
                               detail=f"nhịp {interval}s, trần "
                                      f"{self.max_parallel} việc song song")

    def stop_engine(self, *, timeout: float = 5.0) -> None:
        self._dung_lai.set()
        if self._luong_vong is not None:
            self._luong_vong.join(timeout=timeout)
        self.store.ghi_su_kien("ENGINE_STOPPED", detail="vòng lặp đã dừng")

    def shutdown(self) -> None:
        """Đóng sạch. KHÔNG giết agent đang chạy và KHÔNG xoá worktree.

        Tắt Control Center không được phép phá công việc đang dở: một lượt
        agent đang bay vẫn chạy nốt, và `recover()` ở lần khởi động sau sẽ
        đối soát lại. Đây là điều kiện để "sống sót qua khởi động lại" có
        nghĩa gì đó.
        """
        self.stop_engine()
        with self._khoa:
            ctxs = list(self._ctx.values())
        for c in ctxs:
            try:
                c.leases.close()
            except Exception:                             # noqa: BLE001
                pass

    # -- 8. Doc trang thai ---------------------------------------------------

    def snapshot(self, project_id: str = "") -> Dict:
        """Ảnh chụp cho giao diện. Chỉ ĐỌC sổ — không gọi mạng, không dò."""
        ps = self.projects()
        pid = project_id or (ps[0].project_id if ps else "")
        d: Dict = {"projects": [p.to_dict() for p in ps],
                   "selected": pid, "ts": time.time()}
        if not pid:
            return d
        d["tasks"] = [t.to_dict() for t in self.store.tasks(pid)]
        d["sessions"] = [s.to_dict() for s in self.store.sessions(pid)]
        d["locks"] = LockManager(self.store).snapshot(pid)
        d["worktrees"] = self.store.worktrees(pid)
        d["events"] = self.store.su_kien(project_id=pid, limit=200)
        d["chat"] = [m.to_dict() for m in self.store.chat(pid, limit=100)]
        with self._khoa:
            d["in_flight"] = sorted(self._dang_chay)
        return d

    def log_cua_viec(self, task_id: str, *, limit: int = 400) -> str:
        """Nhật ký của một việc: sự kiện + nhật ký THÔ của agent nếu có.

        Nhật ký thô nằm trên đĩa sau `raw_log_ref` (đó là cách Router V4 giữ
        ngữ cảnh nhỏ). Đọc nó qua `RawLogStore.read`, hàm đã chặn đi ngang
        thư mục — `raw_log_ref` đến từ phong bì, và phong bì chịu ảnh hưởng
        của worker.
        """
        t = self.store.task(task_id)
        if t is None:
            return f"không có việc {task_id!r}"
        d = [f"=== VIỆC {task_id} — {t.state.value} ===",
             f"tiêu đề : {t.title}",
             f"phiên   : {t.owner_session or '(chưa có)'}",
             f"worktree: {t.worktree or '(không)'}",
             f"nhánh   : {t.branch or '(không)'}",
             f"lượt thử: {t.attempts}",
             ""]
        if t.blocked_reason:
            d += ["LÝ DO CHẶN:", t.blocked_reason, ""]
        d.append("=== SỰ KIỆN ===")
        for e in reversed(self.store.su_kien(task_id=task_id, limit=limit)):
            gio = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
            d.append(f"[{gio}] {e['level']:<7} {e['kind']:<18} {e['detail']}")

        ref = ((t.result or {}).get("envelope") or {}).get("raw_log_ref", "")
        if ref:
            ctx = self.ctx(t.project_id)
            tho = ctx.logs.read(ref)
            d += ["", f"=== NHẬT KÝ THÔ CỦA AGENT ({ref}) ==="]
            d.append(tho if tho else "(không đọc được — tệp không còn?)")
        return "\n".join(d)
