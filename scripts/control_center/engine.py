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

import re
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

from scripts.control_center import leader
from scripts.control_center.bootstrap import la_kho_git
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

#: Viec ket thuc bao lau thi con duoc phep "thuat lai" o o chat.
#:
#: Co han vi mot ly do cu the: mo lai ung dung sau mot tuan KHONG duoc do
#: nguoc ca tram ket qua cu vao hoi thoai. Rong rai du de che truong hop
#: that (tat may giua chung, bam Dung, mot nhip dieu phoi truot).
TRAN_QUET_KET_QUA = 1800.0

#: Mot viec `FAILED` phai LANG bao lau thi luoi an toan moi thuat lai.
#:
#: Duong dieu phoi ghi `FAILED` xuong so TRUOC khi quyet dinh thu lai; roi
#: vao khe do ma bao ngay thi nguoi dung doc "hong" cho mot viec sap chay
#: lai. Duong dieu phoi van tu bao ngay lap tuc sau khi da quyet dinh, nen
#: cho o day khong lam cham truong hop binh thuong.
CHO_LANG_KET_QUA = 8.0

#: Dau hieu NHAN DANG truong hop "khai rong ma dia co doi" cua cong `diff`.
#:
#: Lay tu `router_v3/pool/validation.cong_diff`. Chuoi nay chi duoc sinh o
#: DUNG mot nhanh, nhanh doi hoi `status=="ok" and not khai and that` — nen
#: no la dau hieu chinh xac, khong phai suy doan. Khoa lai bang bai kiem.
DAU_HIEU_KHAI_THIEU = "worker không khai sửa gì nhưng đĩa đổi"


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
                 max_parallel: int = 3,
                 leader_bat: bool = False):
        self.root = Path(root) if root else Path.cwd()
        self.store = store if store is not None else ControlStore(root=self.root)
        self.max_parallel = max(1, max_parallel)
        self.owner = owner_id()
        # `probe=False` mac dinh: dung Control Center KHONG duoc goi mang.
        # Do suc khoe that la mot thao tac cham va ton mot luot moi provider;
        # no thuoc ve nut "lam moi", khong thuoc ve ham dung.
        self._fabric = fabric
        self._probe = probe
        #: Moc lan do suc khoe gan nhat. `0.0` = CHUA BAO GIO do.
        #:
        #: Khong the de mac dinh `probe=False` co nghia la "khong bao gio do":
        #: `dung_fabric` dat moi runtime o `OFFLINE`/`last_seen=0`, va
        #: `Scheduler.decide` loai sach ca 42 ung vien voi ly do "runtime
        #: KHONG nhan dispatch". Duong mac dinh cua ban phat hanh
        #: (`router-cc`, khong co `--probe`) vi vay KHONG BAO GIO giao duoc
        #: viec nao — moi viec nam `WAITING` vinh vien. Da do that: mot luot
        #: chung minh READ+WRITE cho 901s, 0 luot, khong placement nao.
        #:
        #: Nen do LUOI: khong do luc dung (giu dung y "khong goi mang luc
        #: khoi dong"), do lan dau khi THAT SU can mot placement.
        self._lan_do_cuoi = 0.0
        #: Fabric do BEN GOI dua vao (bo kiem, hoac mot phien dac biet). Ta
        #: KHONG duoc do suc khoe cai do: no la fabric dung tay, va
        #: `do_suc_khoe` goi that ra `agy`/`codex`. Mot bo kiem offline se
        #: bien thanh bo kiem goi mang.
        self._fabric_ngoai = fabric is not None
        self._executor_factory = executor_factory
        self._ctx: Dict[str, ProjectContext] = {}
        self._khoa = threading.Lock()
        self._dang_chay: Dict[str, threading.Thread] = {}
        self._dung_lai = threading.Event()
        self._luong_vong: Optional[threading.Thread] = None
        self._usage: Optional[UsageReporter] = None
        self._dinh_kem = None
        #: Leader CO BAT khong. MAC DINH TAT, va day la mot lua chon can
        #: giai thich: `chat()` co Leader se SINH MOT TIEN TRINH AGENT. Mot
        #: mac dinh "bat" bien moi bo kiem goi `chat()` thanh mot bo kiem
        #: goi ra nha cung cap — cham, gion, va ton quota that.
        #:
        #: Nen: cac diem vao THAT (desktop/web/TUI) bat tuong minh; moi thu
        #: khac giu hanh vi cu, tat dinh. Co bai kiem doi ba diem vao do
        #: phai bat, de "tat dinh cho bo kiem" khong lang le thanh "tat cho
        #: ca san pham".
        self.leader_bat = bool(leader_bat)
        #: Phien Leader AM theo du an. Giu ngoai `_ctx` vi no song lau hon
        #: mot lan `ctx` bi lam moi, va vi dong no phai la mot hanh vi
        #: tuong minh (`shutdown`), khong phai mot tac dung phu.
        self._leader_phien: Dict[str, object] = {}
        self._khoa_leader = threading.Lock()
        #: Viec DA bao ket qua ve o chat. Chan bao HAI LAN cung mot ket qua
        #: — vong lap dieu phoi co the thay lai mot viec da ket thuc.
        self._da_bao_ket_qua: set = set()

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
            if self._probe:
                # Da do ngay luc nap: dung moc lai de nhip dau tien khong
                # do lan thu hai (moi lan do ton mot luot moi provider).
                self._lan_do_cuoi = time.time()
        return self._fabric

    #: Han dung cua mot lan do suc khoe. Qua han thi do lai truoc khi ket
    #: luan "khong co worker nao" — neu khong, mot provider vua song lai se
    #: bi coi la chet cho tan phien.
    HAN_DO_SUC_KHOE = 300.0

    def _dam_bao_suc_khoe(self, ly_do: str) -> bool:
        """Dò sức khoẻ nếu chưa từng dò, hoặc lần dò cuối đã quá hạn.

        Gọi NGAY TRƯỚC khi cần một placement, không phải lúc dựng — dò thật
        gọi ra `agy`/`codex` nên nó không thuộc về hàm dựng.

        Trả `True` nếu vừa dò. Không bao giờ nâng ngoại lệ ra ngoài: dò hỏng
        thì fabric giữ nguyên trạng thái cũ và việc vẫn `WAITING` với lý do
        đọc được — fail closed, không đoán là provider đang sống.
        """
        if self._fabric_ngoai:
            return False
        if time.time() - self._lan_do_cuoi < self.HAN_DO_SUC_KHOE:
            return False
        try:
            FC.do_suc_khoe(self.fabric)
        except Exception as exc:                              # noqa: BLE001
            self.store.ghi_su_kien(
                "FABRIC_PROBE_FAILED", level="WARN",
                detail=f"dò sức khoẻ hỏng ({ly_do}): "
                       f"{type(exc).__name__}: {exc}"[:400])
            # Van danh dau da do: neu khong, moi tick se lai goi ra mang.
            self._lan_do_cuoi = time.time()
            return False
        self._lan_do_cuoi = time.time()
        # `Fabric.runtimes` la DICT (`runtime_id -> WorkerRuntime`); duyet
        # truc tiep se cho ra CHUOI. Da vap dung loi nay khi viet bai kiem.
        rts = list(self.fabric.runtimes.values())
        song = [r for r in rts if r.dispatchable
                and str(getattr(r, "status", "")).upper().find("OFFLINE") < 0]
        self.store.ghi_su_kien(
            "FABRIC_PROBED",
            detail=f"dò sức khoẻ ({ly_do}): {len(song)}/"
                   f"{len(rts)} runtime nhận dispatch")
        return True

    @property
    def dinh_kem(self) -> "KhoDinhKem":
        """Kho đính kèm. Dựng lười: mở app ra xem sổ thì không cần nó."""
        if self._dinh_kem is None:
            from scripts.control_center.attachments import KhoDinhKem
            self._dinh_kem = KhoDinhKem(self.store, goc=self.root)
        return self._dinh_kem

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
        # Lam am Leader NGAY khi co du an dau tien.
        #
        # `start()` cung goi, nhung tren mot ban cai moi (EXE ngoai kho git)
        # luc `start()` chua co du an nao — nen neu chi am o do thi tin nhan
        # dau tien cua nguoi dung van chiu tron ~8 giay khoi dong nguoi.
        # Do that o luot nghiem thu: 14.5s cho cau chao dau.
        self._am_leader_nen()
        return project

    def projects(self) -> List[Project]:
        return self.store.projects()

    #: Du an MAC DINH cua ban phat hanh. `bootstrap.du_an_mac_dinh()` la
    #: nguon su that; lap lai ten o day chi de `xoa_project` biet cai gi
    #: KHONG duoc xoa nham.
    DU_AN_MAC_DINH = ("fanfic", "router")

    def xoa_project(self, project_id: str, *,
                    xac_nhan: bool = False) -> Dict[str, int]:
        """Gỡ MỘT dự án khỏi sổ. Dành cho dọn trạng thái thử nghiệm/demo.

        `xac_nhan=True` là bắt buộc. Đây là thao tác không hoàn tác được, và
        một tham số mặc định an toàn là thứ chặn nó xảy ra do gọi nhầm.

        TỪ CHỐI xoá dự án mặc định của bản phát hành (`fanfic`, `router`) —
        chúng là dự án THẬT của người dùng, không phải đồ thử. Muốn bỏ thì
        `archived`, đừng xoá.

        KHÔNG chạm tới worktree trên đĩa. Xem `ControlStore.xoa_project`.
        """
        if not xac_nhan:
            raise ValueError(
                f"xoá {project_id!r} là thao tác không hoàn tác được — "
                f"truyền `xac_nhan=True` nếu thật sự muốn.")
        if project_id in self.DU_AN_MAC_DINH:
            raise ValueError(
                f"{project_id!r} là dự án mặc định của bản phát hành, không "
                f"phải trạng thái thử nghiệm. Dùng `archived` nếu muốn ẩn nó.")
        p = self.store.project(project_id)
        if p is None:
            return {}
        # TU CHOI khi con viec DANG CHAY.
        #
        # Xoa giua chung thi agent van chay tiep, nhung moi hang cua no da
        # biet mat: `ghi_ket_qua` thanh no-op, `doi_trang_thai` nem
        # `StoreError`, va toan bo ket qua mat. Te hon: `lm.tra()` o duoi
        # nha MOI khoa cua du an — ke ca khoa PRODUCTION, thu ma `reclaim()`
        # co y khong bao gio dung toi — trong khi mot agent van dang ghi.
        # Worktree thi con nguyen tren dia nhung khong con hang nao noi ai
        # so huu, nen lan `doi_soat()` sau dang ky lai no nhu mot cay RANH.
        dang = [t.task_id for t in self.store.tasks(project_id)
                if t.state is TaskState.RUNNING]
        with self._khoa:
            dang += [x for x in self._dang_chay if x.startswith(project_id + ".")]
        if dang:
            raise ValueError(
                f"{project_id!r} còn {len(dang)} việc ĐANG CHẠY "
                f"({sorted(set(dang))[:3]}) — dừng chúng trước "
                f"(`stop`), nếu không kết quả của chúng sẽ mất và khoá của "
                f"chúng bị nhả trong khi agent vẫn đang ghi.")
        # Nha khoa TRUOC khi xoa hang: neu du an bien mat truoc, `tra()`
        # khong con biet khoa nao thuoc ve no.
        lm = LockManager(self.store)
        for t in self.store.tasks(project_id):
            lm.tra(project_id, t.task_id)
        with self._khoa:
            self._ctx.pop(project_id, None)
        dem = self.store.xoa_project(project_id)
        self.store.ghi_su_kien(
            "PROJECT_REMOVED", level="WARNING",
            detail=(f"đã gỡ dự án {project_id!r} ({p.name}) khỏi sổ: "
                    f"{dem}. Worktree trên đĩa KHÔNG bị đụng tới."),
            meta={"project_id": project_id, "deleted": dem})
        return dem

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

    def chat(self, project_id: str, text: str, *,
             attachment_ids: Optional[Sequence[str]] = None) -> Dict:
        """Ý định người dùng -> việc được quản lý. Đây là CỔNG VÀO của V0.1.

        Việc GATED KHÔNG vào hàng đợi. Nó được tạo ở `BLOCKED` kèm câu hỏi
        cụ thể — người dùng phải mở khoá bằng `mo_khoa_gated()`. Cho phép nó
        `QUEUED` rồi chặn ở bước sau là để một lỗi lập lịch duy nhất đủ để
        nó chạy.

        `attachment_ids` (V0.2): những đính kèm người dùng gửi CÙNG tin
        nhắn này. Chúng được gán cho ĐÚNG những việc do tin nhắn này sinh
        ra, và không cho việc nào khác — xem `attachments.py` bất biến #4.
        Chỉ nhận **mã**, không nhận đường dẫn: frontend không có cách nào
        bảo tầng này đọc một tệp tuỳ ý.
        """
        ctx = self.ctx(project_id)
        tin = self.store.them_chat(project_id, "user", text)

        # Gan dinh kem vao TIN NHAN truoc khi phan ra, de neu phan ra hong
        # thi dinh kem van con o tin nhan chu khong mo coi.
        dk_hop_le: List[str] = []
        for aid in (attachment_ids or ()):
            dk = self.store.dinh_kem(aid)
            if dk is None or dk.project_id != project_id:
                # FAIL CLOSED: ma la, hoac ma cua DU AN KHAC -> bo qua va
                # ghi lai. Khong nem ngoai le vi mot ma xau khong duoc lam
                # mat ca tin nhan nguoi dung vua go.
                self.store.ghi_su_kien(
                    "ATTACHMENT_REJECTED", project_id=project_id,
                    level="WARN",
                    detail=f"mã đính kèm không thuộc dự án này: {aid!r}")
                continue
            self.store.gan_dinh_kem_cho_message(aid, tin.message_id)
            dk_hop_le.append(aid)

        # V0.3: ĐI QUA LEADER. Một tin nhắn KHÔNG còn mặc nhiên thành việc.
        #
        # Leader quyết CHAT/STATUS/CONTROL/WORK trong MỘT lượt (ảnh chụp dự
        # án được đính kèm sẵn, nên câu hỏi trạng thái không cần lượt thứ
        # hai và không cần một agent nào). Chỉ WORK mới xuống tới bộ phân
        # rã + Router V4 như cũ.
        qd = self._leader_quyet_dinh(ctx, text)
        if qd is not None and qd.y_dinh != leader.WORK:
            return self._leader_khong_uy_thac(ctx, qd, tin, dk_hop_le)

        goal = text
        if qd is not None:
            for a in qd.actions:
                if a.loai == "delegate_work":
                    goal = str(a.tham_so.get("objective") or text)
                    break

        kh: PlanResult = ctx.planner.plan(goal, ctx.project)
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

        # Cap dinh kem cho DUNG nhung viec vua sinh ra tu tin nhan nay.
        for aid in dk_hop_le:
            for t in tao:
                self.store.gan_dinh_kem_cho_task(aid, t.task_id)
            if tao:
                self.store.ghi_su_kien(
                    "ATTACHMENT_GRANTED", project_id=project_id,
                    detail=f"{aid} -> {', '.join(t.task_id for t in tao)}",
                    meta={"attachment_id": aid,
                          "task_ids": [t.task_id for t in tao]})

        # Loi cua LEADER dan dau, ke hoach cua bo phan ra di sau. Nguoi dung
        # can biet "chuyen gi sap xay ra" bang mot cau, khong phai bang mot
        # bang ke hoach.
        tra_loi = kh.render()
        if qd is not None and qd.reply:
            tra_loi = qd.reply + "\n\n" + tra_loi
        self.store.them_chat(project_id, "assistant", tra_loi,
                             meta={"plan": kh.to_dict(),
                                   "task_ids": [t.task_id for t in tao],
                                   "attachment_ids": list(dk_hop_le),
                                   "leader": (qd.to_dict() if qd else None),
                                   "loai": "delegation"})
        return {"reply": tra_loi, "tasks": [t.to_dict() for t in tao],
                "plan": kh.to_dict(), "message_id": tin.message_id,
                "attachment_ids": list(dk_hop_le),
                "leader": (qd.to_dict() if qd else None)}

    # -- Leader --------------------------------------------------------------

    def leader_ban_ghi(self, project_id: str) -> leader.BanGhiLeader:
        """Danh tính Leader của dự án, tạo mới nếu chưa có. BỀN qua khởi lại."""
        d = self.store.leader(project_id)
        if d is None:
            bg = leader.BanGhiLeader.moi(project_id)
            self.store.luu_leader(bg.to_dict())
            self.store.ghi_su_kien(
                "LEADER_CREATED", project_id=project_id,
                detail=f"{bg.provider}/{bg.model} thread={bg.thread_id}")
            return bg
        return leader.BanGhiLeader(
            project_id=d["project_id"], thread_id=d.get("thread_id", ""),
            che_do=d.get("che_do") or "AUTO",
            provider=d.get("provider") or leader.PROVIDER_LEADER,
            model=d.get("model") or leader.MODEL_LEADER,
            context=d.get("context") or {},
            created_at=d.get("created_at") or time.time(),
            updated_at=d.get("updated_at") or time.time())

    def anh_chup_du_an(self, project_id: str):
        """`AnhChupDuAn` — TẤT ĐỊNH, chỉ đọc sổ + `git`. Không agent nào."""
        from scripts.control_center import snapshot as _snap
        ctx = self.ctx(project_id)
        bg = self.leader_ban_ghi(project_id)
        return _snap.chup(self.store, ctx.project, che_do=bg.che_do,
                          usage=self._usage_neu_do_duoc(project_id))

    def _usage_neu_do_duoc(self, project_id: str) -> Dict:
        """Usage ĐO ĐƯỢC từ sổ của chính Control Center.

        Chỉ lấy phần `cuc_bo()` — phần luôn là ACTUAL vì nó đếm trong sổ
        mình tự ghi. KHÔNG hỏi nhà cung cấp ở đây: một câu "project tới đâu
        rồi?" không được biến thành một lượt gọi CLI, và một nguồn không đo
        được thì phải ở `UNAVAILABLE` chứ không phải `0`.
        """
        try:
            ds = UsageReporter(self.store).cuc_bo(project_id)
        except Exception:                                   # noqa: BLE001
            return {}
        # `value is None` = UNAVAILABLE. Bo han khoi anh chup thay vi dien
        # 0 — `UsageMetric.__post_init__` cam mau thuan do o tang duoi, va
        # anh chup khong duoc pha luat do o tang tren.
        return {m.label: m.value for m in ds if m.value is not None}

    def _leader_quyet_dinh(self, ctx, text: str):
        """Hỏi Leader. `None` nghĩa là KHÔNG hỏi được — rơi về đường cũ.

        Rơi về đường cũ (phân rã + Router) khi Leader không dùng được là có
        chủ ý: mất Leader thì mất sự tiện, nhưng KHÔNG được mất khả năng
        giao việc. Và mọi lần rơi đều được ghi lại — một sự tiện lặng lẽ
        biến mất là cách một sản phẩm xấu đi mà không ai biết.
        """
        pid = ctx.project.project_id
        if not self.leader_bat and pid not in self._leader_phien:
            return None            # tat -> hanh vi V0.2, tat dinh
        try:
            bg = self.leader_ban_ghi(pid)
            anh = self.anh_chup_du_an(pid)
            ls = [m.to_dict() for m in self.store.chat(pid, limit=40)]
            nn = leader.dung_nhac_nho(anh, ls, text)
            ph = self._phien_leader(pid, bg)
            van = ph.hoi(nn)
            qd = leader.doc_quyet_dinh(van)
            self.store.ghi_su_kien(
                "LEADER_DECISION", project_id=pid,
                detail=f"{qd.y_dinh}: {[a.loai for a in qd.actions]}",
                meta={"y_dinh": qd.y_dinh, "model": bg.model,
                      "actions": [a.to_dict() for a in qd.actions]})
            return qd
        except Exception as exc:                            # noqa: BLE001
            self.store.ghi_su_kien(
                "LEADER_UNAVAILABLE", project_id=pid, level="WARNING",
                detail=(f"{type(exc).__name__}: {exc}"[:400]
                        + " — rơi về phân rã trực tiếp"))
            return None

    def _phien_leader(self, project_id: str, bg):
        with self._khoa_leader:
            ph = self._leader_phien.get(project_id)
            if ph is None:
                # Tra BAC tu fabric, khong chi dua ten cho `PhienLeader`:
                # chan Astra theo ten la mot chot chuoi, con theo bac thi
                # chan duoc ca mot model cao cap mang ten khac.
                bac = 0
                try:
                    m = self.fabric.models.get(bg.model)
                    bac = int(getattr(m, "premium_tier", 0) or 0)
                except Exception:                           # noqa: BLE001
                    bac = 0
                ph = leader.PhienLeader(model=bg.model, premium_tier=bac)
                self._leader_phien[project_id] = ph
            return ph

    def _leader_khong_uy_thac(self, ctx, qd, tin, dk_hop_le) -> Dict:
        """CHAT / STATUS / CONTROL — trả lời, có thể điều khiển, KHÔNG tạo việc."""
        pid = ctx.project.project_id
        ket: List[Dict] = []
        de_xuat: List[Dict] = []
        for a in qd.actions:
            if a.loai in leader.HANH_DONG_TU_CHAY:
                ket.append(self._chay_dieu_khien(pid, a))
            elif a.loai in leader.HANH_DONG_DE_XUAT:
                # KHONG tu chay. Xem `HANH_DONG_TU_CHAY` cho ly do day du:
                # van ban di vao ngu canh Leader khong hoan toan do nguoi
                # dung viet, nen mot hanh dong pha huy hoac mo cong bao mat
                # phai co NGUOI bam.
                de_xuat.append({"loai": a.loai,
                                "task_id": str(a.tham_so.get("task_id") or "")})
                self.store.ghi_su_kien(
                    "LEADER_DE_XUAT", project_id=pid,
                    task_id=str(a.tham_so.get("task_id") or ""),
                    level="WARNING",
                    detail=(f"Leader đề xuất {a.loai} — KHÔNG tự chạy, cần "
                            f"người bấm"))
        loi = qd.reply
        for k in ket:
            if k.get("loi"):
                loi += f"\n\n(!) {k['loi']}"
            elif k.get("ok"):
                loi += f"\n\n✓ {k['ok']}"
        for d in de_xuat:
            nhan = {"approve_gate": "DUYỆT CỔNG", "cancel_task": "HUỶ",
                    "reassign_task": "GIAO LẠI"}.get(d["loai"], d["loai"])
            loi += (f"\n\n⚠ Mình **không tự** {nhan} được — việc này cần "
                    f"bạn bấm. Mở `{d['task_id']}` ở tab Tasks rồi xác nhận.")
        self.store.them_chat(pid, "assistant", loi,
                             meta={"leader": qd.to_dict(),
                                   "loai": qd.y_dinh.lower(),
                                   "ket_qua_dieu_khien": ket,
                                   "attachment_ids": list(dk_hop_le)})
        return {"reply": loi, "tasks": [], "plan": None,
                "message_id": tin.message_id,
                "attachment_ids": list(dk_hop_le),
                "leader": qd.to_dict(), "control": ket}

    def _bao_ket_qua_ve_chat(self, ctx, task_id: str) -> Optional[Dict]:
        """Việc kết thúc -> MỘT tin nhắn assistant trong đúng hội thoại đó.

        Ba tính chất phải giữ, và mỗi cái ứng với một chế độ hỏng thật:

        * **Đúng một lần.** Vòng lặp điều phối có thể thấy lại một việc đã
          kết thúc; báo hai lần thì người dùng đọc hai lần cùng một kết
          quả và không biết cái nào mới.
        * **Đúng hội thoại.** `project_id` lấy từ CHÍNH việc đó, không lấy
          từ ngữ cảnh đang mở — một kết quả rơi nhầm vào hội thoại khác là
          lỗi tệ hơn cả không báo.
        * **Chưa xong thì chưa báo.** Việc còn được xếp lại để thử tiếp thì
          chưa phải kết quả cuối.
        """
        t = self.store.task(task_id)
        if t is None:
            return None
        tt = t.state.value if hasattr(t.state, "value") else str(t.state)
        if tt not in ("DONE", "FAILED", "BLOCKED"):
            return None            # con dang chay / da duoc xep lai
        # KHOA THEO `(task_id, state)`, va no BEN tren dia.
        #
        # Theo ma viec thoi thi mot viec GATED (`BLOCKED` -> nguoi duyet ->
        # `DONE`) se bi lan `BLOCKED` chiem cho, va ket qua `DONE` THAT
        # khong bao gio toi duoc o chat. Ben tren dia vi bo nho trong rong
        # sau moi lan khoi dong lai.
        if self.store.da_bao_ket_qua(task_id, tt):
            return None

        pb = ((t.result or {}).get("envelope") or {}) if t.result else {}
        van = self._soan_ket_qua(t, tt, pb)
        # GHI TRUOC, DANH DAU SAU. Danh dau truoc roi `them_chat` nem (dia
        # day, so hong) thi ket qua mat vinh vien — dau da danh, chat thi
        # rong.
        #
        # `t.project_id`, KHONG phai `ctx` — xem docstring.
        tin = self.store.them_chat(
            t.project_id, "assistant", van,
            meta={"loai": "ket_qua", "task_id": task_id, "state": tt,
                  "worker": pb.get("worker"), "model": pb.get("model"),
                  "provider": pb.get("provider"),
                  "duration": pb.get("duration"),
                  "raw_log_ref": pb.get("raw_log_ref"),
                  "failure_reason": pb.get("failure_reason") or ""})
        self.store.ghi_da_bao_ket_qua(task_id, tt,
                                      project_id=t.project_id,
                                      message_id=tin.message_id)
        self.store.ghi_su_kien(
            "RESULT_TO_CHAT", project_id=t.project_id, task_id=task_id,
            detail=f"{tt} -> tin nhắn #{tin.message_id}")
        return {"message_id": tin.message_id, "text": van}

    def _quet_ket_qua_chua_bao(self) -> int:
        """Việc đã KẾT THÚC mà chưa có câu trả lời nào trong chat -> báo.

        Lưới an toàn cho **mọi** đường kết thúc, không chỉ đường điều phối
        bình thường. Đã vấp thật ở nghiệm thu V0.3: người dùng bấm Dừng,
        việc sang `FAILED` qua `stop()` — một đường KHÔNG đi qua chỗ báo
        kết quả — và ô chat im lặng. Đúng cái "huy hiệu FAILED không lời
        giải thích" mà V0.3 sinh ra để bỏ.

        Cũng che luôn trường hợp tắt máy giữa chừng: lần mở sau, việc đã
        kết thúc vẫn được thuật lại đúng một lần (`_da_bao_roi` đọc bảng
        chat nên nó bền qua khởi động lại).

        Chỉ xét việc kết thúc GẦN ĐÂY — quét cả lịch sử mỗi nhịp là một
        phép O(n) vô ích trên một cái sổ chạy hàng tuần.
        """
        n, bay_gio = 0, time.time()
        for p in self.projects():
            for t in self.store.tasks(p.project_id):
                tt = t.state.value if hasattr(t.state, "value") else str(t.state)
                if tt not in ("DONE", "FAILED", "BLOCKED"):
                    continue
                # MOC THOI GIAN: `ended_at` la 0 voi mot viec GATED duoc
                # tao THANG o `BLOCKED` (khong qua `doi_trang_thai`). Dung
                # `if t.ended_at and …` thi 0 la falsy va chot tuoi khong
                # chan duoc gi — mo app sau mot tuan se do lai moi viec
                # BLOCKED cu vao hoi thoai nhu tin moi.
                moc = t.ended_at or t.updated_at or t.created_at or bay_gio
                if (bay_gio - moc) > TRAN_QUET_KET_QUA:
                    continue
                # CHO LANG cho FAILED: duong dieu phoi ghi `FAILED` xuong
                # so TRUOC khi `_thu_lai_neu_dang` xep viec lai. Nhip 1.0s
                # roi dung vao cua so do se bao "❌ Hỏng" cho mot viec sap
                # duoc thu lai — mot cau tra loi SAI gui cho nguoi dung.
                #
                # Duong dieu phoi tu bao ngay sau khi da quyet dinh thu
                # lai, nen phep quet nay chi la luoi an toan; cho vai giay
                # khong lam mat gi.
                if tt == "FAILED" and (bay_gio - moc) < CHO_LANG_KET_QUA:
                    continue
                try:
                    if self._bao_ket_qua_ve_chat(self.ctx(p.project_id),
                                                 t.task_id):
                        n += 1
                except Exception:                           # noqa: BLE001
                    pass
        return n

    @staticmethod
    def _soan_ket_qua(t, tt: str, pb: Dict) -> str:
        """Câu người dùng đọc. Ngắn, cụ thể, không phải bãi nhật ký."""
        d = []
        if tt == "DONE":
            d.append(f"✅ Xong: {t.title}")
        elif tt == "BLOCKED":
            d.append(f"⛔ Bị chặn: {t.title}")
        else:
            d.append(f"❌ Hỏng: {t.title}")

        tom = str(pb.get("summary") or "").strip()
        if tom:
            d += ["", tom]
        elif tt == "DONE":
            d += ["", "(worker không để lại tóm tắt nào — xem Chi tiết việc.)"]

        if tt != "DONE":
            ly = str(pb.get("failure_reason") or "").strip()
            if ly:
                d += ["", f"Lý do: `{ly}`"]
            if t.blocked_reason:
                d += ["", f"Cần bạn quyết: {t.blocked_reason}"]

        ch = list(pb.get("changes") or [])
        if ch:
            d += ["", "Tệp đã đổi:"] + [f"  • {c}" for c in ch[:12]]
            if len(ch) > 12:
                d.append(f"  … và {len(ch) - 12} tệp nữa")
        for nhan, khoa in (("Phát hiện", "findings"), ("Rủi ro", "risks"),
                           ("Việc tiếp", "followups")):
            v = [str(x) for x in (pb.get(khoa) or [])][:5]
            if v:
                d += ["", f"{nhan}:"] + [f"  • {x[:200]}" for x in v]
        te = pb.get("tests") or {}
        if isinstance(te, dict) and (te.get("passed") or te.get("failed")):
            d += ["", f"Test: {te.get('passed', 0)} đạt / "
                      f"{te.get('failed', 0)} hỏng"]
        if pb.get("commit"):
            d += ["", f"Commit: `{pb['commit']}`"]

        cho = []
        if pb.get("worker"):
            cho.append(f"{pb['worker']}/{pb.get('model') or '?'}")
        if pb.get("duration"):
            cho.append(f"{float(pb['duration']):.0f}s")
        if cho:
            d += ["", f"_({' · '.join(cho)} · `{t.task_id}`)_"]
        return "\n".join(d)

    def _chay_dieu_khien(self, project_id: str, a) -> Dict:
        """Thực hiện MỘT hành động điều khiển. Fail closed, có dấu vết."""
        tid = str(a.tham_so.get("task_id") or "")
        t = self.store.task(tid)
        if t is None or t.project_id != project_id:
            return {"loi": f"không có việc {tid!r} trong dự án này"}
        try:
            if a.loai == "pause_task":
                self.pause(tid, reason="Leader (người dùng yêu cầu)")
                return {"ok": f"đã tạm dừng {tid}"}
            if a.loai == "resume_task":
                self.resume(tid)
                return {"ok": f"đã cho chạy tiếp {tid}"}
            # `cancel_task` / `reassign_task` / `approve_gate` KHONG o day,
            # va do khong phai bo sot — xem `leader.HANH_DONG_TU_CHAY`.
            # Chung la DE XUAT; nguoi bam. Dac biet `approve_gate`: de
            # Leader goi `mo_khoa_gated` la pha dung bat bien ma docstring
            # cua chinh ham do tuyen bo.
            if a.loai in leader.HANH_DONG_DE_XUAT:
                return {"loi": f"{a.loai} cần người bấm, Leader không tự chạy"}
        except Exception as exc:                            # noqa: BLE001
            return {"loi": f"{a.loai} {tid}: {type(exc).__name__}: {exc}"[:300]}
        return {"loi": f"hành động {a.loai!r} chưa nối"}

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
        # GHI DAU DUYET LEN CHINH VIEC, khong chi vao nhat ky su kien.
        #
        # Mot su kien la thu doc lai duoc, khong phai thu KIEM duoc luc lap
        # lich. Bo lap lich can tra loi "viec nay da duoc duyet chua" bang
        # mot phep doc re, ngay tren hang cua no — xem `_da_duyet_cong`.
        hd = dict(t.contract or {})
        pq = dict(hd.get("_permission") or {})
        pq["approved_by"] = str(approved_by)[:80]
        pq["approved_at"] = time.time()
        pq["approval_note"] = str(note)[:300]
        hd["_permission"] = pq
        t.contract = hd
        self.store.luu_task(t)

        self.store.ghi_su_kien(
            "GATE_APPROVED", project_id=t.project_id, task_id=task_id,
            level="ALERT",
            detail=f"người dùng ({approved_by}) mở cổng: {t.gate_reason}",
            meta={"approved_by": approved_by, "note": note,
                  "gate_reason": t.gate_reason})
        return self.store.doi_trang_thai(task_id, TaskState.QUEUED,
                                         reason="người dùng đã duyệt cổng")

    @staticmethod
    def _da_duyet_cong(t: Task) -> bool:
        """Việc GATED này đã được NGƯỜI duyệt chưa.

        Việc không GATED thì luôn `True` — không có cổng nào để duyệt.
        """
        if t.permission != PermissionClass.GATED.value:
            return True
        pq = (t.contract or {}).get("_permission") or {}
        return bool(pq.get("approved_by"))

    # -- 3. Vong lap dieu phoi ----------------------------------------------

    def tick(self) -> Dict:
        """Một nhịp điều phối. Trả về những gì nhịp này đã làm.

        Hàm này KHÔNG chặn: mọi việc chạy trong luồng riêng. Một `tick` chỉ
        quyết định và giao; nó không bao giờ đợi một agent.
        """
        da_giao: List[str] = []
        cho: List[Dict] = []
        # LUOI AN TOAN cho "ket qua phai ve toi o chat". Chay TRUOC phep
        # kiem tran song song: mot viec da ket thuc thi khong con chiem khe
        # nao, va cau tra loi cua no khong duoc phai cho mot khe trong.
        try:
            self._quet_ket_qua_chua_bao()
        except Exception:                                   # noqa: BLE001
            pass
        with self._khoa:
            đang = len([t for t in self._dang_chay.values() if t.is_alive()])
            self._dang_chay = {k: v for k, v in self._dang_chay.items()
                               if v.is_alive()}
        if đang >= self.max_parallel:
            return {"dispatched": [], "waiting": [],
                    "note": f"đã chạm trần {self.max_parallel} việc song song"}

        san_sang = [(p.project_id, t) for p in self.projects()
                    for t in self._san_sang(p.project_id)]
        # Chi do khi THAT SU co viec cho giao. Mo Control Center ra xem sổ
        # thi khong goi mang lan nao.
        if san_sang:
            self._dam_bao_suc_khoe(f"{len(san_sang)} việc chờ giao")
        for _pid, t in san_sang:
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
            # LƯỚI CUỐI CỦA CỔNG AN TOÀN, và nó nằm ĐÚNG ở đây có lý do.
            #
            # `chat()` đã đặt việc GATED vào thẳng `BLOCKED`, nhưng đó là MỘT
            # đường. Bất kỳ đường nào khác đưa nó về `QUEUED` đều mở cổng mà
            # không ai duyệt. Đã có một đường như thế và nó CHẠY ĐƯỢC THẬT:
            #
            #     pause(việc GATED)   BLOCKED -> PAUSED   (hợp lệ)
            #     resume(việc đó)     PAUSED  -> QUEUED   (hợp lệ)
            #     -> tick() giao việc, agent chạy, KHÔNG một lần duyệt nào
            #
            # Sửa riêng `resume()` là bịt đúng một lỗ và để ngỏ mọi lỗ chưa
            # nghĩ ra. Kiểm ở CỔNG VÀO của bộ lập lịch thì mọi đường — hiện
            # tại và về sau — đều phải đi qua đây.
            if not self._da_duyet_cong(t):
                self.store.doi_trang_thai(
                    t.task_id, TaskState.BLOCKED, force=True,
                    reason=(f"việc GATED chưa được duyệt ({t.gate_reason}) — "
                            f"đưa lại BLOCKED. Chỉ `mo_khoa_gated()` mới mở "
                            f"được cổng này."))
                self.store.ghi_su_kien(
                    "GATE_REASSERTED", project_id=t.project_id,
                    task_id=t.task_id, level="ALERT",
                    detail=(f"việc GATED lọt vào hàng đợi mà chưa có ai duyệt "
                            f"— đã chặn lại trước khi giao"))
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

        LƯỚI CUỐI CHO KHOÁ. Mọi lối thoát ĐÃ BIẾT bên trong `_giao_khong_luoi`
        đều nhả khoá bằng tay, nhưng "đã biết" là chỗ hỏng: một
        `sqlite3.OperationalError` lúc `claim_task`, hay một `KeyError` từ
        `fabric.model()`, sẽ thoát ra ngoài, bị `tick()` nuốt thành
        `TICK_FAILED`, và khoá đã giành KHÔNG BAO GIỜ được nhả.

        Với khoá FILESYSTEM/SERVICE thì nó tự lành sau TTL. Với khoá
        PRODUCTION thì KHÔNG — `reclaim()` cố ý không nhả chúng. Nghĩa là một
        lỗi SQLite nhất thời có thể khoá vĩnh viễn một tài nguyên production
        cho tới khi có người gỡ tay. Đó là cái giá quá đắt cho một ngoại lệ
        không lường trước, nên ở đây có `finally`.
        """
        ctx = self.ctx(t.project_id)
        lm = LockManager(self.store)
        giao_duoc = False
        try:
            kq = self._giao_khong_luoi(t, ctx, lm)
            giao_duoc = bool(kq.get("dispatched"))
            return kq
        except Exception as exc:                          # noqa: BLE001
            self.store.ghi_su_kien(
                "DISPATCH_CRASHED", project_id=t.project_id,
                task_id=t.task_id, level="ERROR",
                detail=f"{type(exc).__name__}: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": f"{type(exc).__name__}: {exc}"[:200]}
        finally:
            # Giao ĐƯỢC thì luồng `_chay` sở hữu khoá và sẽ tự nhả trong
            # `finally` của nó. Chỉ nhả ở đây khi việc KHÔNG được giao —
            # nhả nhầm lúc agent đang chạy còn tệ hơn không nhả.
            if not giao_duoc:
                try:
                    lm.tra(t.project_id, t.task_id)
                except Exception:                         # noqa: BLE001
                    pass

    def _hop_dong_kem_dinh_kem(self, t: Task) -> Dict:
        """Hợp đồng + danh sách đính kèm ĐƯỢC CẤP cho đúng việc này.

        Chèn ở lúc GIAO, không lúc tạo: đính kèm được gán sau khi việc đã
        được tạo (`chat()` phải có `task_id` mới gán được), và người dùng
        còn có thể cấp thêm về sau. Dựng lại đoạn này mỗi lượt giao thì nó
        luôn khớp với quyền hiện tại.

        Agent nhận **đường dẫn cục bộ** và tự đọc bằng công cụ đọc tệp của
        nó. Không tệp nào được tải lên đâu.
        """
        hd = dict(t.contract or {})
        try:
            mo = self.dinh_kem.mo_ta_cho_agent(t.task_id)
        except Exception as exc:                          # noqa: BLE001
            # Khong de mot loi o tang dinh kem lam chet ca luot giao.
            self.store.ghi_su_kien(
                "ATTACHMENT_DESC_FAILED", project_id=t.project_id,
                task_id=t.task_id, level="WARN",
                detail=f"{type(exc).__name__}: {exc}"[:200])
            return hd
        if mo:
            hd["objective"] = ((hd.get("objective") or "")
                               + "\n" + mo)
        return hd

    def _giao_khong_luoi(self, t: Task, ctx: "ProjectContext",
                         lm: LockManager) -> Dict:
        """Thân thật của `_giao`. Thứ tự giành tài nguyên cố định — xem
        docstring module."""
        try:
            hd = TaskContract.from_dict(self._hop_dong_kem_dinh_kem(t))
        except (ContractError, KeyError, ValueError) as exc:
            self.store.doi_trang_thai(
                t.task_id, TaskState.FAILED,
                reason=f"hợp đồng hỏng: {type(exc).__name__}: {exc}"[:400])
            return {"task_id": t.task_id, "dispatched": False,
                    "reason": "hợp đồng hỏng"}

        # (1) khoa tai nguyen
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

    #: Ly do hong KHONG BAO GIO duoc thu lai tu dong.
    #:
    #: `security_gate` lay thang tu Router V4: thu lai chi tang co hoi lot
    #: mot thay doi chua thu giong credential (xem `orchestrator.py`).
    #: `tool_permission_denied` la mot buc tuong CAU HINH — chay lai y het
    #: se bi tu choi y het, chi ton them mot luot quota.
    KHONG_THU_LAI = frozenset({
        "security_gate", "requires_decision", "tool_permission_denied",
        "codex_security_shaped_refusal", "no_eligible_placement",
        # `repo_path` khong phai kho git: doi nha cung cap khong sua duoc
        # gi ca, va moi luot thu lai chi tao them mot phien vo ich.
        "project_repo_invalid",
    })

    #: Ly do KHONG PHU THUOC CHO CHAY — hong o day thi hong o mọi nơi.
    #:
    #: CHI nhung ly do nay moi bi phep "hong y het thi thoi" ap dung. Danh
    #: sach HEP co chu y, va day la ly do:
    #:
    #: Mot lan hong LAP LAI chua chac la loi cau hinh. Hai tai khoan cung
    #: het quota van co the con tai khoan thu ba; hai lan `timeout` van co
    #: the do may ban nhat thoi. Chan thu lai trong nhung truong hop do
    #: chinh la chế độ hỏng "bao FAILED trong khi mot nha cung cap khoe
    #: khac dang lam duoc" — doi mot bao thu lai lay mot loi bo sot.
    #:
    #: Nen: chi chan khi ly do TU NO da noi "day la cau hinh".
    LY_DO_KHONG_PHU_THUOC_CHO = frozenset({
        "session_start_failed",     # switch/launcher/thong dich hong
        "no_model_pinned",          # fabric chua ghim model
        "executor_error",           # hop dong/worktree hong truoc khi chay
        "no_session",               # ban cu cua `session_start_failed`
    })

    #: Thu PHAI bo khoi chu ky vi no doi theo TUNG CHO CHAY, khong theo
    #: ban chat cua loi. Danh tinh tai khoan la cai quan trong nhat: thong
    #: diep that cua adapter la "switch acc1 hỏng: …", nen cung mot loi cau
    #: hinh o AG01/AG02/AG03 ra BA chu ky khac nhau va phep so KHONG BAO
    #: GIO khop — tuc la rao chong bao thu lai chet lang le, dung cho lop
    #: loi no duoc viet ra de chan.
    _XOA_KHOI_CHU_KY = re.compile(
        r"\bacc\d+\b"                      # acc1, acc2, … (danh tinh)
        r"|\bAG\d{2}\b"                    # AG01, AG02, …  (khe)
        r"|\bs-[0-9a-f]{6,}\b"             # id phien
        r"|\b\d+(?:\.\d+)?s\b"             # so giay
        r"|\b(?:19|20)\d{2}-\d{2}-\d{2}\b"  # ngay thang
        r"|\b\d{4,}\b",                    # pid, cong, moc thoi gian
        re.IGNORECASE)

    @classmethod
    def _chu_ky_hong(cls, pb) -> str:
        """Chữ ký NGẮN của một lần hỏng, để so hai lượt với nhau.

        Gồm `failure_reason` và phần ĐẦU của câu tóm tắt, sau khi đã **bỏ
        mọi thứ đổi theo chỗ chạy** — tên tài khoản, mã khe, id phiên, số
        giây, pid. Không chuẩn hoá thì phép so vô dụng: adapter Antigravity
        ghi `f"switch {self._acc} hỏng: …"`, nên đúng một lỗi cấu hình ở
        AG01/AG02/AG03 ra ba chữ ký khác nhau, không chữ ký nào khớp chữ ký
        nào, và rào chống bão thử lại **không bao giờ nổ**.

        Cắt phần đầu chứ không lấy cả câu cũng vì thế: đuôi câu hay mang
        đường dẫn tạm và mã băm chỉ sống một lượt.
        """
        ly_do = (getattr(pb, "failure_reason", "") or "").strip()
        tom = " ".join((getattr(pb, "summary", "") or "").split())
        tom = cls._XOA_KHOI_CHU_KY.sub("·", tom)[:80]
        return f"{ly_do}|{tom}" if (ly_do or tom) else ""

    def _lan_hong_truoc(self, task_id: str) -> Dict:
        """Meta của lần hỏng TRƯỚC lần vừa xong.

        BỎ QUA bản ghi đầu tiên có chủ ý: `TASK_FINISHED` của lượt hiện tại
        đã được ghi TRƯỚC khi đường thử lại chạy, nên bản ghi mới nhất
        chính là lượt đang xét. So nó với chính nó thì lượt thử lại đầu
        tiên nào cũng bị từ chối.
        """
        hong = []
        for e in self.store.su_kien(task_id=task_id, limit=40):
            if e.get("kind") != "TASK_FINISHED":
                continue
            m = e.get("meta") or {}
            if m.get("ok") or not m.get("fail_sig"):
                continue
            hong.append(m)
            if len(hong) >= 2:
                break
        return hong[1] if len(hong) >= 2 else {}

    def _doi_soat_khai_thieu(self, ctx: "ProjectContext", task_id: str,
                             hd: TaskContract, kq: ExecutionResult) -> bool:
        """ĐỐI SOÁT lời khai thiếu với TRẠNG THÁI THẬT — vẫn FAIL CLOSED.

        Đây KHÔNG phải hạ cổng `diff` xuống mức cảnh báo. Cổng đó giữ nguyên
        trong Router V4, không sửa một dòng. Ở đây Control Center làm một
        việc KHÁC và CHẶT HƠN: thay vì tin danh sách worker khai, nó lấy
        danh sách THẬT từ `git` rồi kiểm lại chính danh sách đó.

        Chỉ áp đúng MỘT trường hợp hẹp — cái mà `cong_diff` gọi là "worker
        không khai sửa gì nhưng đĩa đổi":

            worker báo `ok`  +  `changes` RỖNG  +  đĩa CÓ đổi
            +  cổng `diff` là cổng DUY NHẤT hỏng

        Mọi trường hợp khác giữ nguyên `FAILED`. Đặc biệt KHÔNG đụng tới
        chiều ngược lại ("khai có sửa mà đĩa SẠCH") — đó là thất bại im lặng
        thật sự, và nó phải hỏng.

        Điều kiện để CHẤP NHẬN, tất cả phải đúng:

          1. mọi tệp đổi THẬT nằm trong `allowed_scope` và không chạm
             `forbidden_scope` (`TaskContract.scope_violations`, hàm thuần);
          2. `scope_violations` do tầng kiểm định tính cũng rỗng;
          3. cổng `security` ĐẠT — nó vốn đã chạy trên diff THẬT của đĩa
             (`_diff_van_ban` đọc cả tệp chưa theo dõi), nên nó là phán
             quyết trên tập THẬT chứ không phải trên lời khai;
          4. mọi cổng khác (`shape`, `scope`, `tests`, `artifacts`, …) ĐẠT.

        Một tệp đổi ngoài phạm vi ⇒ TỪ CHỐI, việc ở lại `FAILED`. Đó chính
        là chỗ bất biến được giữ: chấp nhận ở đây KHÔNG BAO GIỜ dựa vào lời
        khai, và không bao giờ bỏ qua một thay đổi chưa được kiểm.

        Trả `True` nghĩa là đã đối soát xong và việc được đi tiếp; lúc đó
        `changes` trong phong bì được ĐIỀN LẠI bằng tập THẬT, để mọi báo cáo
        về sau nói đúng thứ đã xảy ra.
        """
        bc = kq.validation
        if bc is None or bc.passed:
            return False
        if bc.failed_gates != ["diff"]:
            return False                    # con cong khac hong -> giu FAILED

        pb = kq.envelope
        khai = {str(t).replace("\\", "/").strip("/") for t in pb.changes if t}
        that = sorted({str(t).replace("\\", "/").strip("/")
                       for t in bc.files_changed_observed if t})
        # CHI trường hợp khai RỖNG mà đĩa CÓ đổi.
        if khai or not that:
            return False
        # KHONG duoc hoi `pb.status` o day — no da BI GHI DE.
        #
        # `Executor.run` dat `pb.status = "failed"` va
        # `failure_reason = f"gate_{hong[0]}"` NGAY KHI bat ky cong nao hong
        # (executor.py). Nen dieu kien "worker bao ok" khong bao gio con dung
        # o dau ra cua Executor, va ban truoc cua ham nay CHET CUNG tren
        # duong that: no luon thoat o day. Bai kiem cu khong bat duoc vi no
        # tu dung mot `ResultEnvelope(status="ok")` canh mot cong `diff`
        # hong — mot to hop production khong sinh ra.
        #
        # Nguon su that con lai la CHINH CONG `diff`: thong diep duoi day chi
        # duoc sinh o DUNG mot nhanh cua `cong_diff`, nhanh doi hoi
        # `kq.status == "ok" and not khai and that`. Nen khop no la khop
        # chinh xac dieu kien can, khong phai doan.
        #
        # `test_thong_diep_cong_diff_khong_doi` khoa lai chuoi nay: neu V4
        # doi loi van, bai kiem do hong NGAY thay vi doi soat am tham chet.
        chi_tiet = next((g.detail for g in bc.gates
                         if g.name == "diff" and not g.passed), "")
        if not chi_tiet.startswith(DAU_HIEU_KHAI_THIEU):
            return False

        vi_pham = sorted(set(hd.scope_violations(that))
                         | set(bc.scope_violations))
        if vi_pham:
            self.store.ghi_su_kien(
                "UNDERDECLARED_CHANGES_REJECTED",
                project_id=ctx.project.project_id, task_id=task_id,
                level="ALERT",
                detail=(f"worker không khai gì, và {len(vi_pham)} tệp đổi "
                        f"THẬT nằm NGOÀI phạm vi — giữ FAILED"),
                meta={"actual": that[:50], "violations": vi_pham[:50]})
            return False

        # Bat buoc moi cong con lai DAT (gom `security`, da chay tren diff
        # THAT cua dia). `failed_gates == ["diff"]` o tren da bao dam dieu
        # nay; kiem lai tuong minh de mot lan sua ve sau khong lam mat no.
        khong_dat = [g.name for g in bc.gates
                     if not g.passed and g.name != "diff"]
        if khong_dat:
            return False

        pb.changes = that                   # bao cao noi dung THAT
        pb.warnings.append(
            f"worker KHÔNG khai `changes` nhưng đĩa đổi {len(that)} tệp. "
            f"Đã đối soát với `git`: mọi tệp đều trong phạm vi và mọi cổng "
            f"khác đều đạt, nên việc được tính là xong. Danh sách `changes` "
            f"đã được điền lại bằng tập THẬT.")
        self.store.ghi_su_kien(
            "UNDERDECLARED_CHANGES", project_id=ctx.project.project_id,
            task_id=task_id, level="WARNING",
            detail=(f"khai 0 tệp, đĩa đổi {len(that)} tệp — đã đối soát và "
                    f"kiểm lại phạm vi/bảo mật trên tập THẬT"),
            meta={"declared": [], "actual": that[:50],
                  "gates": [g.name for g in bc.gates if g.passed]})
        return True

    def _viec_dang_co_lease(self, ctx: "ProjectContext") -> set:
        """`task_id` nao dang giu mot lease Router V4 CON HAN.

        Day la tin hieu LIEN TIEN TRINH dang tin duy nhat: lease song trong
        SQLite, co TTL va nhip tim, va chu cua no dap nhip trong khi luot
        agent dang bay. Mot tien trinh Control Center thu hai doc duoc no, va
        nho vay biet dung dung vao viec cua tien trinh thu nhat.

        Khong doc duoc so lease thi tra tap RONG co chu dich: luc do
        `recover()` quay ve hanh vi cu (dua tren phien), tuc than trong theo
        chieu "coi la mo coi". Chieu do chi mat mot luot; chieu nguoc lai la
        hai agent cung ghi mot cay.
        """
        try:
            return {l.task_id for l in ctx.leases.all()
                    if l.task_id and l.con_han()}
        except Exception:                                 # noqa: BLE001
            return set()

    def _nha_khoa_mo_coi(self, project_id: str) -> List[str]:
        """BẤT BIẾN: một khoá chỉ được giữ bởi một việc ĐANG CHẠY.

        Chủ khoá ở bất kỳ trạng thái nào khác — `BLOCKED`, `FAILED`, `DONE`,
        `QUEUED`, `WAITING` — là khoá MỒ CÔI: việc giữ nó đã không còn chạy,
        nhưng khoá vẫn chặn mọi việc khác cho tới hết TTL (1 giờ).

        Vì sao cần RIÊNG chỗ này chứ không chỉ nhả lúc gỡ việc mồ côi khỏi
        `RUNNING`: một lượt `recover()` TRƯỚC ĐÓ có thể đã chuyển việc sang
        `BLOCKED` mà chưa nhả khoá (đúng thứ đã xảy ra 2026-09-08). Từ đó
        việc không còn ở `RUNNING` nữa nên vòng lặp kia không bao giờ thấy
        nó, và khoá kẹt lại vĩnh viễn. Kiểm theo TRẠNG THÁI CHỦ KHOÁ bắt
        được cả hai trường hợp.

        THẬN TRỌNG: `_giao()` giành khoá TRƯỚC khi `claim_task` lật việc
        sang `RUNNING`. Nên chỉ nhả khi việc đó cũng KHÔNG nằm trong
        `_dang_chay` — nếu không sẽ cướp khoá của một việc đang được giao.
        """
        with self._khoa:
            bay = set(self._dang_chay)
        # Viec dang co lease SONG = dang chay o mot tien trinh khac. Khoa cua
        # no khong phai khoa mo coi.
        try:
            bay |= self._viec_dang_co_lease(self.ctx(project_id))
        except Exception:                                 # noqa: BLE001
            pass
        lm = LockManager(self.store)
        da_nha: List[str] = []
        for l in self.store.locks(project_id):
            # KHOA PRODUCTION KHONG BAO GIO TU VE — ke ca o day.
            #
            # `LockKind.tu_thu_hoi_duoc` la mot bat bien cua ca he, khong
            # phai mot chi tiet cua `reclaim()`. Mot khoa production "mo coi"
            # co the la mot cutover dang chay lau hon du kien; doan sai la
            # tha viec thu hai vao giua no. Bao cho nguoi, dung tu nha.
            # (Da vap: ban dau ham nay nha ca khoa production va lam hong
            # dung bai kiem giu bat bien do.)
            if not l.kind.tu_thu_hoi_duoc:
                continue
            if not l.holder_task or l.holder_task in bay:
                continue
            t = self.store.task(l.holder_task)
            if t is None:
                # Chu khoa khong con ton tai -> chac chan mo coi.
                pass
            elif t.state is TaskState.RUNNING:
                continue
            if self.store.xoa_lock(l.lock_id, holder_task=l.holder_task):
                da_nha.append(l.lock_id)
                self.store.ghi_su_kien(
                    "LOCK_ORPHANED", project_id=project_id,
                    task_id=l.holder_task, level="WARNING",
                    detail=(f"nhả khoá mồ côi {l.kind.value} {l.resource!r} — "
                            f"chủ đang ở "
                            f"{t.state.value if t else '(không còn)'}, "
                            f"không phải RUNNING"))
        return da_nha

    def _thu_lai_neu_dang(self, ctx: ProjectContext, task_id: str, pb,
                          session_id: str, placement_key: str = "") -> None:
        """Thử lại một việc hỏng — CÓ TRẦN, và đổi chỗ chạy.

        VÌ SAO CẦN: `Executor.run()` chạy đúng MỘT lượt. Đường thử lại của
        Router V4 nằm trong `RouterV4._chay_co_thu_lai`, mà Control Center cố
        ý không đi qua (nó cần giữ placement của phiên). Không có gì ở đây
        thì một lần nhà cung cấp hắt hơi là việc hỏng vĩnh viễn — với một hệ
        chạy qua đêm không người trực, đó là chế độ hỏng thường gặp nhất.

        VÌ SAO PHẢI CÓ TRẦN: thử lại vô hạn là "bão thử lại", đúng chế độ
        hỏng số 4 mà `leases.py` liệt kê. `attempts` do `claim_task` tự tăng
        nên trần này đếm được, không tin vào bộ nhớ.

        VÌ SAO DỪNG PHIÊN: lượt sau phải chạy ở CHỖ KHÁC. Nhả phiên hiện tại
        rồi để `decide()` chọn lại — cùng cơ chế `reassign`, không phải một
        đường định tuyến thứ hai. Lặp lại đúng bài học của V4: "từ lượt 2,
        ĐỔI placement".
        """
        t = self.store.task(task_id)
        if t is None:
            return
        ly_do = (pb.failure_reason or "").strip()

        # HONG Y HET O MOT CHO KHAC = loi khong phu thuoc placement.
        #
        # Thu lai co ich khi lan hong la CUC BO: mot tai khoan het quota,
        # mot tien trinh chet. No vo ich — va ton dung mot luot quota moi
        # lan — khi nguyen nhan nam o CAU HINH, vi luot sau se hong y het.
        # Da vap that (2026-09-09): mot loi `sys.executable` trong ban dong
        # goi lam ba runtime AG01/AG02/AG03 hong lien tiep trong 6 giay,
        # cung mot cau chu.
        #
        # Khong doan xem ly do nao la "tat dinh" — DO. Neu chu ky hong cua
        # lan nay trung lan truoc MA CHO CHAY DA KHAC, thi doi cho nua chi
        # lap lai ket qua.
        ck = self._chu_ky_hong(pb)
        truoc = self._lan_hong_truoc(task_id)
        cho_nay = placement_key or (pb.worker or "")
        if ly_do in self.LY_DO_KHONG_PHU_THUOC_CHO \
                and truoc and ck and truoc.get("fail_sig") == ck \
                and truoc.get("placement") and truoc["placement"] != cho_nay:
            self.store.ghi_su_kien(
                "RETRY_REFUSED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=(f"KHÔNG thử lại: đã hỏng Y HỆT ({ck}) ở "
                        f"{truoc['placement']} rồi ở {cho_nay} — lỗi không "
                        f"phụ thuộc chỗ chạy, đổi chỗ nữa chỉ tốn quota"),
                meta={"fail_sig": ck,
                      "placements": [truoc["placement"], cho_nay]})
            return

        if ly_do in self.KHONG_THU_LAI or pb.requires_decision:
            self.store.ghi_su_kien(
                "RETRY_REFUSED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=(f"KHÔNG thử lại {ly_do!r} — chạy lại y hệt sẽ hỏng y "
                        f"hệt, chỉ tốn thêm một lượt quota"))
            return
        if t.attempts >= MAX_ATTEMPTS:
            self.store.ghi_su_kien(
                "RETRY_EXHAUSTED", project_id=t.project_id, task_id=task_id,
                level="WARNING",
                detail=f"đã cạn {MAX_ATTEMPTS} lượt thử — để người xem")
            return

        if t.owner_session:
            ctx.sessions.dung(
                t.owner_session, state=SessionState.STOPPED,
                reason=f"thử lại {task_id} ở chỗ khác (lượt {t.attempts})")
        t.owner_session = ""
        self.store.luu_task(t)
        self.store.doi_trang_thai(
            task_id, TaskState.QUEUED, force=True,
            reason=(f"thử lại tự động lượt {t.attempts + 1}/{MAX_ATTEMPTS} "
                    f"sau lỗi {ly_do or 'không rõ'}"))
        self.store.ghi_su_kien(
            "RETRY_QUEUED", project_id=t.project_id, task_id=task_id,
            detail=(f"lượt {t.attempts}/{MAX_ATTEMPTS} hỏng ({ly_do}); nhả "
                    f"phiên cũ để lượt sau chọn chỗ khác"))

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
                    # `continue`, KHONG `return`. Ban dau cho nay thoat han
                    # sau MOT ngoai le — va `sqlite3.OperationalError:
                    # database is locked` la chuyen binh thuong khi hai tien
                    # trinh Control Center cung ghi. Mot lan nghen o dia the
                    # la giet luon ca vong nhip: `lm.gia_han` ngung chay,
                    # sau LOCK_TTL (3600s) khoa cua viec het han, va mot viec
                    # khac CUOP duoc khoa trong khi agent thu nhat VAN DANG
                    # GHI. Hop dong cho phep `max_wall_time` 2400s cong thu
                    # lai, nen viec chay qua mot tieng khong phai ngoai le.
                    continue
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
            # CONG VAO: `repo_path` cua du an phai la mot kho git THAT.
            #
            # Kiem o day, mot lan, voi mot cau doc duoc — thay vi de
            # `git rev-parse HEAD` ne ra giua duong dieu phoi. Su co that
            # (2026-09-09): mot du an duoc gieo tro vao chinh thu muc EXE
            # (khong phai kho git), va viec dau tien nguoi dung go chet
            # bang `WorktreeError: not a git repository` — mot cau khong
            # noi cho ai biet phai sua gi, o mot cho khong ai ngo toi.
            #
            # Day KHONG phai loi cua nha cung cap: doi sang AG02 hay Codex
            # deu hong y het. Nen no FAILED va khong fallback — nhung phai
            # FAILED voi ly do dung.
            if not la_kho_git(ctx.project.repo_path):
                self.store.ghi_su_kien(
                    "PROJECT_REPO_INVALID", project_id=ctx.project.project_id,
                    task_id=task_id, session_id=session_id, level="ERROR",
                    detail=(f"repo_path của dự án không phải kho git: "
                            f"{ctx.project.repo_path!r}. Router làm việc "
                            f"trên kho git — sửa đường dẫn dự án rồi gửi "
                            f"lại. Không nhà cung cấp nào chạy được việc "
                            f"này, nên KHÔNG chuyển sang chỗ khác."),
                    meta={"repo_path": str(ctx.project.repo_path)})
                self.store.doi_trang_thai(
                    task_id, TaskState.FAILED, force=True,
                    reason=(f"project_repo_invalid: {ctx.project.repo_path!r} "
                            f"không phải kho git"))
                ctx.sessions.ket_thuc_viec(session_id, task_id, ok=False)
                return

            ctx.fabric.mark_started(p.runtime_id, task_id)
            self.store.ghi_su_kien(
                "TASK_STARTED", project_id=ctx.project.project_id,
                task_id=task_id, session_id=session_id,
                detail=f"{p.key} @ {hd.execution.max_wall_time:.0f}s trần")

            # `base_sha` CHI tinh khi viec that su can mot worktree.
            #
            # Truoc day no duoc tinh vo dieu kien, ngay trong danh sach doi
            # so — nen `git rev-parse HEAD` chay cho CA nhung viec CHI DOC
            # khong bao gio cham toi git. Hau qua that (2026-09-09): mot
            # viec `analysis` voi `worktree_required=false` chet vi
            # `WorktreeError: not a git repository` TRUOC KHI
            # `Executor.run()` kip duoc vao — khong adapter nao duoc goi,
            # khong tien trinh nao duoc sinh, `result_json` rong.
            #
            # Mot viec khong can git thi khong duoc phep chet vi git.
            base = (ctx.worktrees.base_sha()
                    if hd.execution.worktree_required else "")
            kq = ctx.executor.run(
                hd, p, base_sha=base,
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
                if self._doi_soat_khai_thieu(ctx, task_id, hd, kq):
                    moi = map_envelope_status(
                        "ok",
                        need_review=hd.verification.independent_review_required)

            # UPDATE HEP, khong phai doc-sua-ghi. Xem `store.ghi_ket_qua`:
            # `luu_task` ghi ca cot `state`, nen luu mot doi tuong doc tu
            # TRUOC luot agent se nuot mat mot lenh `pause` nguoi dung vua bam.
            self.store.ghi_ket_qua(task_id, result=kq.to_dict(),
                                   worktree=kq.worktree, branch=kq.branch)

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
                      "placement": p.key, "duration": round(pb.duration, 2),
                      "fail_sig": self._chu_ky_hong(pb)})
            ctx.sessions.ket_thuc_viec(session_id, task_id, ok=kq.ok, pid=pid)
            if moi is TaskState.FAILED:
                self._thu_lai_neu_dang(ctx, task_id, pb, session_id,
                                       placement_key=p.key)
            # KET QUA PHAI VE TOI O CHAT. Day la yeu cau CHAN PHAT HANH.
            #
            # Mot huy hieu DONE ma khong co cau tra loi thi khong phai la
            # xong: nguoi dung phai mo tab Logs moi biet chuyen gi da xay
            # ra, va do dung la thu V0.3 sinh ra de bo.
            #
            # Goi SAU khi da ghi trang thai + su kien + da quyet dinh thu
            # lai: neu viec con duoc thu lai thi chua phai luc bao ket qua.
            #
            # BOC RIENG. Loi goi nay nam trong `try` lon cua `_chay`, ma
            # nhanh `except` cua no EP viec sang FAILED bang `force=True`.
            # Mot ngoai le trong buoc dang chat (dia day, so kho tho) se
            # lat mot viec DA XONG thanh HONG — doi mot loi hien thi lay
            # mot loi du lieu. Luoi an toan o `tick()` se thuat lai sau.
            try:
                self._bao_ket_qua_ve_chat(ctx, task_id)
            except Exception as exc:                        # noqa: BLE001
                self.store.ghi_su_kien(
                    "RESULT_TO_CHAT_FAILED", project_id=ctx.project.project_id,
                    task_id=task_id, level="WARNING",
                    detail=f"{type(exc).__name__}: {exc}"[:300])
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
        """Tiếp tục một việc đã tạm dừng.

        `resume` KHÔNG phải một cách duyệt cổng. Một việc GATED chưa ai duyệt
        thì quay về `BLOCKED`, không phải `QUEUED` — nếu không thì
        `pause` rồi `resume` là một đường vòng đầy đủ quanh cổng an toàn
        (đã kiểm: nó chạy được thật trước bản này).
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if not self._da_duyet_cong(t):
            self.store.ghi_su_kien(
                "GATE_HELD", project_id=t.project_id, task_id=task_id,
                level="ALERT",
                detail=("`resume` KHÔNG mở được cổng an toàn — việc vẫn "
                        "BLOCKED cho tới khi có người duyệt"))
            return self.store.doi_trang_thai(
                task_id, TaskState.BLOCKED, force=True,
                reason=(f"{t.gate_reason} — `resume` không phải là duyệt. "
                        f"Dùng `mo_khoa_gated()` (phím `g` trên giao diện)."))
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

        HAI THỨ HÀM NÀY TỪ CHỐI LÀM, và cả hai đều từng làm được:

        1. **Việc đã DONE.** Bản trước dùng `force=True`, tức đi vòng qua
           TOÀN BỘ bảng chuyển trạng thái — `DONE` không còn là ngõ cụt nữa.
           Bấm `r` trên một việc `DONE` sẽ chạy lại nó và `ghi_ket_qua()` ghi
           đè kết quả cũ: báo cáo, danh sách `changes`, và cả phần `findings`
           mà review độc lập vừa gộp vào đều biến mất. `r` nằm ngay cạnh
           `o`/`s` trên một bảng dùng lúc 3 giờ sáng.

           `FAILED` thì VẪN giao lại được: không có kết quả nào đáng giữ, và
           "hỏng rồi, thử chỗ khác" đúng là việc `reassign` sinh ra để làm.
           Bỏ `force=True` là đủ — bảng chuyển đã cho `FAILED -> QUEUED` và
           đã cấm `DONE -> QUEUED`; để bảng đó lên tiếng thay vì dựng một
           luật thứ hai song song với nó.
        2. **Việc ĐANG chạy.** `sessions.dung()` gọi `worktrees.nha()`, tức
           xoá chủ sở hữu cây làm việc TRONG KHI luồng `_chay` vẫn đang ghi
           vào đúng cây đó — và `assert_exclusive` mất tác dụng ngay lúc nó
           cần nhất. Muốn dừng một việc đang chạy thì dùng `stop()`, hàm có
           cắt tiến trình thật và có hộp xác nhận.
        """
        t = self.store.task(task_id)
        if t is None:
            raise KeyError(task_id)
        if t.state is TaskState.DONE:
            raise TransitionError(
                f"{task_id} đã DONE — `reassign` KHÔNG chạy lại một việc đã "
                f"xong, vì làm vậy sẽ ghi đè mất kết quả và cả phát hiện của "
                f"review độc lập. Muốn làm lại thì tạo một việc mới.")
        with self._khoa:
            dang_bay = task_id in self._dang_chay
        if dang_bay or t.state is TaskState.RUNNING:
            raise TransitionError(
                f"{task_id} đang chạy — `reassign` sẽ nhả cây làm việc trong "
                f"khi agent vẫn đang ghi vào đó. Dùng `stop()` trước.")

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
                                         reason="giao lại")

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
            # VIEC DANG DUOC MOT TIEN TRINH KHAC CHAY -> KHONG DUOC DUNG VAO.
            #
            # `recover()` chay vo dieu kien moi lan mo Control Center, ke ca
            # `--headless` chi de xem mot anh chup. Neu mot TUI khac dang
            # chay mot viec, ban truoc se: thay `sessions.pid IS NULL` (pid
            # chi duoc ghi luc KET THUC viec), dat phien ve IDLE va XOA
            # `current_task`, roi coi viec RUNNING la mo coi -> dua ve QUEUED
            # va NHA KHOA cua mot agent dang ghi. Hai agent giam chung mot
            # cay; va khi luot that ket thuc, `QUEUED -> DONE` nem
            # `TransitionError` nen ca viec lam dung bi ghi thanh FAILED.
            #
            # Lease cua Router V4 la tin hieu LIEN TIEN TRINH dung cho viec
            # nay: no song trong SQLite, co TTL + nhip tim, va mang `task_id`.
            # Viec nao con lease SONG thi that su dang chay o dau do — de yen.
            dang_thue = self._viec_dang_co_lease(ctx)
            if dang_thue:
                bc.setdefault("leased", []).extend(sorted(dang_thue))
            bc["sessions"][p.project_id] = ctx.sessions.recover(
                bo_qua_viec=dang_thue)
            bc["worktrees"][p.project_id] = ctx.worktrees.doi_soat()
            bc.setdefault("stale_locks", []).extend(
                self._nha_khoa_mo_coi(p.project_id))

            for t in self.store.tasks(p.project_id, states=(TaskState.RUNNING,)):
                # "PHIEN CON SONG" KHONG DU — phai la "phien DANG CHAY DUNG
                # VIEC NAY".
                #
                # Ban dau cho nay chi hoi phien co con song khong. Nhung mot
                # phien RANH (IDLE, `current_task` rong) van "con song", nen
                # mot viec ma phien chu da bo lai se o `RUNNING` VINH VIEN:
                # `recover()` bo qua no, va bo lap lich khong bao gio nhat no
                # len vi no khong o QUEUED/WAITING.
                #
                # Do that 2026-09-08: `rev2.tda87-1` ket o RUNNING qua BA lan
                # goi `--headless` lien tiep, moi lan deu chay `recover()`.
                # Day dung la che do hong ma `recover()` ton tai de chan, va
                # no song sot duoc vi phep kiem hoi sai cau hoi.
                if t.task_id in dang_thue:
                    continue                  # tien trinh khac dang chay
                s = (self.store.session(t.owner_session)
                     if t.owner_session else None)
                if s is not None and s.state.alive and \
                        s.current_task == t.task_id:
                    continue                  # that su dang chay -> de yen
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
                # VIEC DA RA KHOI `RUNNING` THI KHOA CUA NO PHAI VE THEO.
                #
                # Khong nha o day thi khoa cua mot viec mo coi con giu toi
                # het TTL (1 tieng), va MOI viec khac cham cung tai nguyen
                # phai CHO het tieng do — trong khi viec giu khoa thi da
                # khong con chay nua. Do that 2026-09-08: mot luot chung
                # minh bi cat giua chung de lai hai khoa, va lan chay ke
                # tiep ket o `WAITING` vinh vien.
                #
                # An toan vi ta VUA XAC MINH viec nay khong con phien nao
                # dang chay no — day chinh la dieu kien de vao nhanh nay.
                nha = LockManager(self.store).tra(p.project_id, t.task_id)
                if nha:
                    self.store.ghi_su_kien(
                        "LOCK_RELEASED_ON_RECOVER", project_id=p.project_id,
                        task_id=t.task_id, level="WARNING",
                        detail=(f"nhả {nha} khoá của một việc mồ côi — nó "
                                f"không còn chạy nữa"))
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

    def _am_leader_nen(self) -> None:
        """Mở sẵn phiên Leader ở NỀN, cho dự án đầu tiên.

        Khởi động nguội `agy` mất ~8 giây (đo được). Không làm ấm trước thì
        tin nhắn ĐẦU TIÊN của người dùng — thường là một câu chào — phải
        chờ trọn 8 giây đó, và ấn tượng đầu về sản phẩm là "chậm". Đo
        được ở lượt nghiệm thu: lần đầu 14.8s, các lần sau 4.8–6.4s.

        Best-effort tuyệt đối: chạy ở luồng nền, nuốt mọi lỗi. Không ấm
        được thì lượt đầu chỉ chậm như cũ, KHÔNG hỏng.
        """
        if not self.leader_bat:
            return

        def _lam() -> None:
            try:
                ps = self.projects()
                if not ps:
                    return
                pid = ps[0].project_id
                bg = self.leader_ban_ghi(pid)
                ph = self._phien_leader(pid, bg)
                if ph.mo():
                    self.store.ghi_su_kien(
                        "LEADER_WARM", project_id=pid,
                        detail=f"phiên Leader đã ấm ({bg.model})")
            except Exception:                               # noqa: BLE001
                pass                # am truoc chi la tien nghi

        threading.Thread(target=_lam, daemon=True, name="cc-leader-warm").start()

    def start(self, *, interval: float = TICK_SECONDS) -> None:
        """Chạy vòng lặp điều phối trong nền."""
        if self._luong_vong is not None and self._luong_vong.is_alive():
            return
        self._dung_lai.clear()
        self._am_leader_nen()

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
        # Phien Leader la tien trinh `agy` AM cua CHINH ta — dong no la
        # dung, khac han voi mot luot agent dang bay cua worker.
        with self._khoa_leader:
            ph = list(self._leader_phien.values())
            self._leader_phien.clear()
        for x in ph:
            try:
                x.dong()
            except Exception:                             # noqa: BLE001
                pass
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
