"""Quản lý PHIÊN agent — Control Center V0.1, yêu cầu #4 (lõi của bản này).

BA KẾT LUẬN, và chỉ ba:

    REUSE   phạm vi tương thích + đã có phiên sống, khoẻ  -> dùng lại
    CREATE  việc độc lập                                  -> dựng phiên mới
    WAIT    việc xung đột                                 -> xếp hàng, không đua

Quyết định phải GIẢI THÍCH ĐƯỢC. Một bộ chọn phiên không nói được vì sao nó
dựng phiên thứ tư là một bộ chọn không ai gỡ lỗi được lúc 3 giờ sáng, nên
`SessionDecision` mang theo cả chuỗi luật đã xét.

VÌ SAO "PHIÊN" Ở ĐÂY LÀ THẬT, KHÔNG PHẢI MỘT LỚP BỌC HÌNH THỨC:

`router_v4/executor.py` giữ một **cache adapter theo `(runtime, model)`**, và
cache đó chính là thứ giữ tiến trình `agy` ấm giữa hai việc — docstring của
nó nói rõ cache là BẮT BUỘC chứ không phải tối ưu. Một `Session` ở đây là
danh tính BỀN của đúng một mục trong cache đó, cộng thêm worktree nó sở hữu
và phạm vi nó đang giữ. Dùng lại phiên = dùng lại tiến trình đã ấm; không
phải một nhãn dán lên một tiến trình mới.

DỰNG PHIÊN LÀM ĐÚNG SÁU VIỆC đề bài yêu cầu, theo thứ tự:

    1. chọn agent/provider   -> `Scheduler.decide()` của V4, theo NĂNG LỰC
    2. tạo/dùng lại worktree -> `WorktreeCoordinator.ensure_for()`
    3. tạo nhánh             -> `WorktreeManager.create()` (V3) làm luôn
    4. tiêm ngữ cảnh/handoff -> `TaskContract.render()` + phong bì quyền
    5. khởi động tiến trình  -> adapter của V4 qua `Executor`
    6. ghi PID + metadata    -> `_dao_pid()` + `ControlStore.luu_session`

KHÔNG chỗ nào ở đây gõ tên tài khoản hay tên model. Đó là luật kiến trúc
trung tâm của Router V4 và Control Center không được phép phá nó.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v4.contract import TaskContract
from scripts.router_v4.runtime import Fabric, Placement
from scripts.router_v4.scheduler import Decision, Demand, Scheduler
from scripts.control_center.model import (Session, SessionAction, SessionState,
                                          Task)
from scripts.control_center.store import ControlStore
from scripts.control_center.worktrees import WorktreeCoordinator

#: Phien khong hoat dong lau hon nguong nay bi coi la nguoi — van con song
#: nhung khong nen uu tien dung lai. KHONG tu giet: giet mot phien dang cho
#: mot lenh test dai la mat ket qua that.
NGUONG_NGUOI = 900.0

#: Tran phien SONG cung luc trong MOT du an. Tran, khong phai muc tieu.
#: Trung voi tran "3 WRITE worker" cua router toan cuc.
MAX_SESSIONS_MOI_DU_AN = 3


def _giao_nhau_pham_vi(a: Sequence[str], b: Sequence[str]) -> bool:
    """Hai phạm vi ghi có giẫm lên nhau không — so THEO ĐOẠN đường dẫn."""
    x = [str(p).replace("\\", "/").strip("/").lower() for p in a if p]
    y = [str(p).replace("\\", "/").strip("/").lower() for p in b if p]
    for i in x:
        for j in y:
            if i == j or i.startswith(j + "/") or j.startswith(i + "/"):
                return True
    return False


def _pham_vi_chua(ngoai: Sequence[str], trong: Sequence[str]) -> bool:
    """`trong` có nằm GỌN trong `ngoai` không.

    Dùng cho luật REUSE: một phiên chỉ được nhận việc mới nếu phạm vi việc
    đó **không vượt ra ngoài** phạm vi phiên đang sở hữu. Cho phép vượt ra
    nghĩa là phiên âm thầm mở rộng quyền ghi của chính nó qua từng việc —
    đúng thứ `forbidden_scope` của hợp đồng tồn tại để chặn.
    """
    if not trong:
        return True
    if not ngoai:
        return False
    n = [str(p).replace("\\", "/").strip("/").lower() for p in ngoai if p]
    for t in trong:
        tt = str(t).replace("\\", "/").strip("/").lower()
        if not any(tt == i or tt.startswith(i + "/") for i in n):
            return False
    return True


def dao_pid(adapter) -> Optional[int]:
    """Moi tiến trình con của một adapter ra, nếu nó có.

    Không adapter nào trong hợp đồng chín phương thức của V3 hứa cung cấp
    PID — nên hàm này DÒ chứ không đòi, và trả `None` khi không thấy thay vì
    bịa một số. Một `pid` bịa còn tệ hơn không có `pid`: đường phục hồi sẽ
    hỏi hệ điều hành về một tiến trình không liên quan và kết luận sai.

    Ba hình dạng thật trong kho này:
        `CodexAdapter._p`                       -> Popen
        `AntigravityNativeAdapter._worker._p`   -> Popen (WarmAgyWorker)
        `MultiSlotAdapter`                      -> nhiều khe, không một PID
    """
    for duong in (("_p",), ("_worker", "_p"), ("_proc",)):
        o = adapter
        for ten in duong:
            o = getattr(o, ten, None)
            if o is None:
                break
        pid = getattr(o, "pid", None)
        if isinstance(pid, int) and pid > 0:
            return pid
    return None


def tien_trinh_con_song(pid: Optional[int]) -> bool:
    """Tiến trình còn tồn tại không. `False` khi không biết.

    Trên Windows `os.kill(pid, 0)` KHÔNG có nghĩa như trên POSIX, nên dùng
    `OpenProcess` gián tiếp qua `psutil` nếu có, và lùi về một phép thử bảo
    thủ nếu không. Bảo thủ ở đây = trả `False` (coi như đã chết), vì kết
    luận sai theo chiều "còn sống" sẽ khiến đường phục hồi treo một việc
    vĩnh viễn chờ một tiến trình không tồn tại.
    """
    if not pid or pid <= 0:
        return False
    try:
        import psutil                                     # type: ignore
        return psutil.pid_exists(int(pid))
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            ma = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(ma)):
                return False
            return ma.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


@dataclass
class SessionDecision:
    """Kết luận cho MỘT việc, kèm toàn bộ luật đã xét."""

    action: SessionAction
    session_id: str = ""
    placement: Optional[Placement] = None
    routing: Optional[Decision] = None
    reason: str = ""
    #: Luat da xet, theo dung thu tu. Day la thu doc luc go loi.
    trace: Tuple[str, ...] = ()
    wait_on_task: str = ""
    wait_on_session: str = ""

    def to_dict(self) -> Dict:
        return {"action": self.action.value, "session_id": self.session_id,
                "placement": self.placement.key if self.placement else None,
                "reason": self.reason, "trace": list(self.trace),
                "wait_on_task": self.wait_on_task,
                "wait_on_session": self.wait_on_session,
                "routing": self.routing.to_dict() if self.routing else None}

    def explain(self) -> str:
        d = [f"QUYẾT ĐỊNH PHIÊN: {self.action.value}",
             f"  lý do  : {self.reason}"]
        if self.session_id:
            d.append(f"  phiên  : {self.session_id}")
        if self.placement:
            d.append(f"  vị trí : {self.placement.key}")
        if self.trace:
            d.append("  đã xét :")
            d += [f"    {i+1}. {x}" for i, x in enumerate(self.trace)]
        if self.routing is not None:
            d.append("")
            d.append(self.routing.explain())
        return "\n".join(d)


class SessionManager:
    """Chọn / dựng / thu hồi phiên agent cho MỘT dự án."""

    def __init__(self, project_id: str, store: ControlStore, *,
                 fabric: Fabric, scheduler: Scheduler,
                 worktrees: WorktreeCoordinator,
                 max_sessions: int = MAX_SESSIONS_MOI_DU_AN):
        self.project_id = project_id
        self.store = store
        self.fabric = fabric
        self.scheduler = scheduler
        self.worktrees = worktrees
        self.max_sessions = max(1, max_sessions)
        self._khoa = threading.Lock()

    # -- 1. QUYET DINH ------------------------------------------------------

    def decide(self, task: Task, contract: TaskContract, *,
               demand: Optional[Demand] = None,
               conflicting_task: str = "",
               tranh_runtime: Sequence[str] = ()) -> SessionDecision:
        """REUSE / CREATE / WAIT cho một việc. Hàm THUẦN với sổ hiện tại.

        Thứ tự các luật KHÔNG tuỳ tiện — luật chặn đứng trước luật cấp phát,
        vì một việc bị xung đột mà lại được cấp phiên trước rồi mới phát
        hiện xung đột sẽ để lại một phiên mồ côi ở mỗi lần va chạm.

        `tranh_runtime` (V0.6.1, toả): runtime các việc con ANH EM đang chạy.
        Ưu tiên phiên/placement ở runtime KHÁC để N agent thật sự là N tài
        khoản; không còn chỗ khác thì rơi về như cũ — tránh là ưu tiên,
        không phải rào.
        """
        vet: List[str] = []
        pham_vi = tuple(contract.allowed_scope)
        chi_doc = not contract.requirements.repo_write
        tranh = set(tranh_runtime or ())

        # Luat 0 — xung dot tai nguyen da duoc tang tren xac dinh.
        if conflicting_task:
            vet.append(f"tài nguyên đang do việc {conflicting_task} giữ")
            return SessionDecision(
                action=SessionAction.WAIT, wait_on_task=conflicting_task,
                reason=(f"việc {conflicting_task} đang giữ tài nguyên việc này "
                        f"cần — xếp hàng thay vì chạy đua"),
                trace=tuple(vet))

        phien = [s for s in self.store.sessions(self.project_id, alive_only=True)
                 if s.state.usable or s.state is SessionState.STARTING]
        vet.append(f"{len(phien)} phiên đang sống trong dự án")

        # Luat 1 — pham vi GHI giam len mot phien dang BAN -> CHO.
        #
        # Xet TRUOC luat dung lai: mot phien dang chay viec khac tren cung
        # pham vi thi khong duoc dung lai VA cung khong duoc de viec moi
        # dung phien khac chay song song vao do.
        if not chi_doc:
            for s in phien:
                if s.state is SessionState.BUSY and \
                        _giao_nhau_pham_vi(s.scope, pham_vi):
                    vet.append(f"phiên {s.session_id} đang BẬN với phạm vi "
                               f"giẫm lên {list(pham_vi)}")
                    return SessionDecision(
                        action=SessionAction.WAIT, session_id=s.session_id,
                        wait_on_session=s.session_id,
                        wait_on_task=s.current_task,
                        reason=(f"phạm vi ghi {list(pham_vi)} giẫm lên phạm vi "
                                f"phiên {s.session_id} đang chạy "
                                f"({list(s.scope)}) — chờ để không hai agent "
                                f"cùng ghi một chỗ"),
                        trace=tuple(vet))

        # Luat 2 — DUNG LAI mot phien RANH tuong thich.
        ung_vien = [s for s in phien if s.state is SessionState.IDLE]
        vet.append(f"{len(ung_vien)} phiên RẢNH để xét dùng lại")
        if tranh:
            khac = [s for s in ung_vien if s.runtime_id not in tranh]
            if khac or self.scheduler is not None:
                # Con phien o runtime khac (hoac con dung duoc phien moi) ->
                # bo qua phien tren runtime anh em dang dung.
                bo = [s.session_id for s in ung_vien if s.runtime_id in tranh]
                if bo:
                    vet.append(f"toả: bỏ qua {len(bo)} phiên rảnh ở runtime anh em "
                               f"đang chạy {sorted(tranh)}")
                ung_vien = khac
        for s in sorted(ung_vien, key=lambda x: -x.last_activity):
            if s.idle_seconds > NGUONG_NGUOI:
                vet.append(f"bỏ qua {s.session_id}: nguội "
                           f"{s.idle_seconds:.0f}s > {NGUONG_NGUOI:.0f}s")
                continue
            if chi_doc:
                vet.append(f"dùng lại {s.session_id}: việc CHỈ ĐỌC, mọi phiên "
                           f"rảnh đều tương thích")
                return SessionDecision(
                    action=SessionAction.REUSE, session_id=s.session_id,
                    placement=Placement(s.runtime_id, s.model_id),
                    reason=(f"việc chỉ đọc + phiên {s.session_id} đang rảnh và "
                            f"khoẻ — dùng lại tiến trình đã ấm"),
                    trace=tuple(vet))
            if _pham_vi_chua(s.scope, pham_vi):
                vet.append(f"dùng lại {s.session_id}: phạm vi {list(pham_vi)} "
                           f"nằm gọn trong {list(s.scope)}")
                return SessionDecision(
                    action=SessionAction.REUSE, session_id=s.session_id,
                    placement=Placement(s.runtime_id, s.model_id),
                    reason=(f"phạm vi việc nằm gọn trong phạm vi phiên "
                            f"{s.session_id} đang sở hữu — dùng lại"),
                    trace=tuple(vet))
            vet.append(f"bỏ qua {s.session_id}: phạm vi {list(pham_vi)} vượt "
                       f"ra ngoài {list(s.scope)}")

        # Luat 3 — het tran phien -> CHO, khong dung them.
        if len(phien) >= self.max_sessions:
            cho = min(phien, key=lambda x: x.last_activity)
            vet.append(f"đã chạm trần {self.max_sessions} phiên/dự án")
            return SessionDecision(
                action=SessionAction.WAIT, session_id=cho.session_id,
                wait_on_session=cho.session_id, wait_on_task=cho.current_task,
                reason=(f"đã có {len(phien)}/{self.max_sessions} phiên sống — "
                        f"chờ một phiên rảnh ra thay vì mở thêm tiến trình"),
                trace=tuple(vet))

        # Luat 4 — CREATE. Chon placement THEO NANG LUC.
        qd = self.scheduler.decide(contract, demand=demand, exclude=tuple(sorted(tranh)))
        if qd.selected is None and tranh:
            # Het runtime PHAN BIET: roi ve cho phep trung tai khoan anh em,
            # con hon xep hang trong khi be van con khe.
            vet.append(f"toả: không còn runtime ngoài {sorted(tranh)} — cho phép "
                       f"dùng chung tài khoản anh em")
            qd = self.scheduler.decide(contract, demand=demand)
        if qd.selected is None:
            vet.append("bộ lập lịch không tìm được placement đủ điều kiện")
            return SessionDecision(
                action=SessionAction.WAIT, routing=qd,
                reason=(f"chưa có worker đủ năng lực/còn chỗ: {qd.reason}"),
                trace=tuple(vet))
        vet.append(f"dựng phiên mới trên {qd.selected.key}")
        return SessionDecision(
            action=SessionAction.CREATE, placement=qd.selected, routing=qd,
            reason=f"việc độc lập, chưa có phiên tương thích — {qd.reason}",
            trace=tuple(vet))

    # -- 2. DUNG PHIEN ------------------------------------------------------

    def create(self, decision: SessionDecision, task: Task, *,
               contract: TaskContract, base_sha: str = "") -> Session:
        """Hiện thực hoá một quyết định CREATE. Chưa khởi động tiến trình.

        Tiến trình agent chỉ được khởi động khi việc thật sự chạy (trong
        `engine`), không phải lúc đăng ký phiên: dựng tiến trình rồi mới
        phát hiện việc bị chặn là cách đốt quota nhanh nhất.
        """
        if decision.placement is None:
            raise ValueError("quyết định CREATE mà không có placement")
        p = decision.placement
        m = self.fabric.model(p.model_id)
        sid = f"s-{uuid.uuid4().hex[:10]}"

        s = Session(
            session_id=sid, project_id=self.project_id, provider=m.provider,
            runtime_id=p.runtime_id, model_id=p.model_id,
            state=SessionState.STARTING, scope=tuple(contract.allowed_scope),
            current_task=task.task_id,
            note=f"dựng cho {task.task_id}: {decision.reason[:200]}")

        if contract.execution.worktree_required:
            lease = self.worktrees.ensure_for(
                session_id=sid, task_id=task.task_id, base_sha=base_sha,
                runtime_id=p.runtime_id)
            s.worktree, s.branch = lease.path, lease.branch

        self.store.luu_session(s)
        self.store.ghi_su_kien(
            "SESSION_CREATED", project_id=self.project_id,
            task_id=task.task_id, session_id=sid,
            detail=f"{p.key} ({m.provider}) worktree={s.worktree or '(không)'}",
            meta={"placement": p.key, "provider": m.provider,
                  "scope": list(s.scope), "reason": decision.reason})
        return s

    def reuse(self, session_id: str, task: Task, *,
              contract: TaskContract, base_sha: str = "") -> Session:
        """Gắn một việc vào phiên đã có, dùng lại cây làm việc của nó."""
        s = self.store.session(session_id)
        if s is None:
            raise ValueError(f"không có phiên {session_id!r}")
        # Pham vi phien la HOP cua nhung gi no da so huu — mot viec chi doc
        # khong lam phien mat pham vi ghi cu.
        #
        # MO RONG TRUOC khi xin worktree, khong phai sau: `ensure_for` doi
        # chieu thay doi chua commit voi pham vi phien, va viec MOI co the
        # ghi vao mot nhanh pham vi phien chua tung so huu. Mo rong sau se
        # khien chinh cong viec cua viec nay bi coi la "ngoai pham vi" o
        # luot ke tiep va cay bi bo di oan.
        s.scope = tuple(dict.fromkeys(list(s.scope) +
                                      list(contract.allowed_scope)))
        if contract.execution.worktree_required:
            if s.worktree:
                self.worktrees.assert_exclusive(s.worktree, session_id)
            lease = self.worktrees.ensure_for(
                session_id=session_id, task_id=task.task_id, base_sha=base_sha,
                runtime_id=s.runtime_id, scope=s.scope)
            s.worktree, s.branch = lease.path, lease.branch
        s.current_task = task.task_id
        self.store.luu_session(s)
        self.store.ghi_su_kien(
            "SESSION_REUSED", project_id=self.project_id, task_id=task.task_id,
            session_id=session_id, detail=s.placement_key,
            meta={"scope": list(s.scope)})
        return s

    # -- 3. VONG DOI --------------------------------------------------------

    def bat_dau_viec(self, session_id: str, task_id: str, *,
                     pid: Optional[int] = None) -> None:
        s = self.store.session(session_id)
        if s is None:
            return
        s.state = SessionState.BUSY
        s.current_task = task_id
        s.task_count += 1
        if pid is not None:
            s.pid = pid
        self.store.luu_session(s)

    def ket_thuc_viec(self, session_id: str, task_id: str, *,
                      ok: bool, pid: Optional[int] = None) -> None:
        s = self.store.session(session_id)
        if s is None:
            return
        # Phien van SONG sau khi viec xong — do la toan bo diem cua viec dung
        # lai. Chi doi ve IDLE.
        s.state = SessionState.IDLE
        s.current_task = ""
        if pid is not None:
            s.pid = pid
        self.store.luu_session(s)
        self.store.ghi_su_kien(
            "SESSION_IDLE", project_id=self.project_id, task_id=task_id,
            session_id=session_id,
            detail=f"việc {'xong' if ok else 'hỏng'}; phiên giữ ấm để dùng lại")

    def dung(self, session_id: str, *, reason: str = "",
             state: SessionState = SessionState.STOPPED) -> Optional[Session]:
        """Dừng một phiên. KHÔNG xoá worktree của nó."""
        s = self.store.session(session_id)
        if s is None:
            return None
        s.state = state
        s.current_task = ""
        s.note = (reason or s.note)[:500]
        self.store.luu_session(s)
        self.worktrees.nha(session_id, note=f"phiên {state.value}: {reason}"[:280])
        self.store.ghi_su_kien(
            "SESSION_STOPPED", project_id=self.project_id, session_id=session_id,
            level="WARNING" if state is SessionState.DEAD else "INFO",
            detail=f"{state.value}: {reason}"[:400])
        return s

    def drain(self, session_id: str, *, reason: str = "") -> Optional[Session]:
        """Ngừng nhận việc MỚI; việc đang chạy chạy nốt.

        Cùng ngữ nghĩa `drain` của Router V4 ở tầng runtime, áp cho phiên —
        giữ một tên cho một khái niệm để hai tầng không lệch nhau.
        """
        s = self.store.session(session_id)
        if s is None:
            return None
        s.state = SessionState.DRAINING
        s.note = (reason or s.note)[:500]
        self.store.luu_session(s)
        self.store.ghi_su_kien(
            "SESSION_DRAINING", project_id=self.project_id,
            session_id=session_id, detail=reason[:300])
        return s

    # -- 4. PHUC HOI --------------------------------------------------------

    def recover(self, *, bo_qua_viec: Optional[set] = None
                ) -> Dict[str, List[str]]:
        """Đối soát phiên trên sổ với tiến trình THẬT. Chạy lúc khởi động.

        Ba nhóm:
            `reattached` — có PID và tiến trình còn sống -> giữ nguyên.
            `dead`       — có PID nhưng tiến trình đã chết -> `DEAD`.
            `unknown`    — không có PID để kiểm.

        Nhóm thứ ba KHÔNG bị coi là chết. Một phiên không ghi được PID (ví dụ
        `MultiSlotAdapter` nhiều khe, hoặc adapter cầu nối HTTP) vẫn có thể
        đang chạy thật; tuyên bố nó chết sẽ khiến Control Center dựng phiên
        thứ hai chồng lên một tiến trình còn sống. Chúng bị đưa về `IDLE` —
        không được coi là đang bận, cũng không bị giết.
        """
        gan_lai: List[str] = []
        chet: List[str] = []
        khong_ro: List[str] = []
        bo_qua = set(bo_qua_viec or ())
        for s in self.store.sessions(self.project_id, alive_only=True):
            if s.current_task and s.current_task in bo_qua:
                # Mot tien trinh KHAC dang chay dung viec nay (lease con
                # han). Dung vao phien cua no — nhat la XOA `current_task` —
                # se lam vong lap viec o `engine.recover()` tuong viec do mo
                # coi, roi nha khoa cua mot agent dang ghi.
                gan_lai.append(s.session_id)
                continue
            if s.pid is None:
                khong_ro.append(s.session_id)
                if s.state is SessionState.BUSY:
                    self.store.dat_trang_thai_session(
                        s.session_id, SessionState.IDLE, current_task="",
                        note="phục hồi: không có PID để kiểm, coi như rảnh")
                continue
            if tien_trinh_con_song(s.pid):
                gan_lai.append(s.session_id)
                self.store.ghi_su_kien(
                    "SESSION_REATTACHED", project_id=self.project_id,
                    session_id=s.session_id,
                    detail=f"pid {s.pid} còn sống — gắn lại trạng thái")
            else:
                chet.append(s.session_id)
                self.dung(s.session_id, state=SessionState.DEAD,
                          reason=f"pid {s.pid} không còn tồn tại sau khởi động lại")
        return {"reattached": gan_lai, "dead": chet, "unknown": khong_ro}

    def snapshot(self) -> List[Dict]:
        return [s.to_dict() for s in self.store.sessions(self.project_id)]
