"""Từ vựng miền của Control Center V0.1 — trạng thái, khoá, quyền, mức tin cậy.

VÌ SAO MỘT MODULE RIÊNG: Router V4 đã có từ vựng của NÓ (`RuntimeStatus`,
`Source`, `TaskContract`), và từ vựng đó đúng cho việc **lập lịch một lượt
chạy**. Control Center quản lý thứ sống LÂU HƠN một lượt chạy: một dự án
tồn tại qua nhiều mission, một việc chờ người quyết định qua đêm, một khoá
tài nguyên giữ ngang qua hai phiên. Nhồi các trạng thái đó vào enum của V4
sẽ làm hỏng đúng thứ V4 đang làm tốt.

Ánh xạ hai chiều nằm ở `map_envelope_status` — MỘT chỗ duy nhất. Nếu ánh xạ
rải rác thì hai tầng sẽ lệch nhau lúc nào không biết.

KHÔNG có `bypass` ở bất kỳ đâu trong tệp này. `PermissionClass` chỉ có hai
giá trị, và không giá trị nào nghĩa là "bỏ qua kiểm tra".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple


class TaskState(str, Enum):
    """Vòng đời một việc trong Control Center.

    Tách `WAITING` khỏi `QUEUED` và `BLOCKED` có chủ đích, vì ba thứ này đòi
    ba hành động KHÁC NHAU của người vận hành:

        QUEUED   — sẵn sàng, chỉ đang chờ tới lượt. Không phải làm gì.
        WAITING  — bị chặn bởi thứ SẼ TỰ HẾT: phụ thuộc chưa xong, hoặc một
                   khoá tài nguyên do việc khác đang giữ. Cũng không phải
                   làm gì, nhưng lý do khác hẳn.
        BLOCKED  — bị chặn bởi thứ KHÔNG tự hết: cần người quyết định, cần
                   một thao tác GATED, hoặc worker báo `blocked`. PHẢI có
                   người can thiệp.

    Gộp ba trạng thái này lại (như hàng đợi V3 làm với `queued`) khiến bảng
    điều khiển không trả lời được câu hỏi quan trọng nhất lúc 3 giờ sáng:
    "có việc nào đang chờ TÔI không?"
    """

    QUEUED = "QUEUED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    REVIEW = "REVIEW"
    DONE = "DONE"
    FAILED = "FAILED"
    PAUSED = "PAUSED"

    @property
    def terminal(self) -> bool:
        return self in (TaskState.DONE, TaskState.FAILED)

    @property
    def active(self) -> bool:
        """Việc đang CHIẾM tài nguyên (khoá, phiên, worktree)."""
        return self in (TaskState.RUNNING, TaskState.REVIEW)

    @property
    def needs_human(self) -> bool:
        return self is TaskState.BLOCKED


#: Chuyen trang thai HOP LE. Khoa bang may thay vi bang quy uoc: mot bang
#: dieu khien cho phep `DONE -> RUNNING` se lang le lam hong moi bao cao
#: dua tren dau thoi gian.
_CHUYEN_HOP_LE: Dict["TaskState", FrozenSet["TaskState"]] = {}


class TransitionError(ValueError):
    """Chuyển trạng thái không hợp lệ. Ném NGAY, không âm thầm bỏ qua."""


_CHUYEN_HOP_LE.update({
    TaskState.QUEUED: frozenset({TaskState.WAITING, TaskState.RUNNING,
                                 TaskState.BLOCKED, TaskState.PAUSED,
                                 TaskState.FAILED}),
    TaskState.WAITING: frozenset({TaskState.QUEUED, TaskState.RUNNING,
                                  TaskState.BLOCKED, TaskState.PAUSED,
                                  TaskState.FAILED}),
    TaskState.RUNNING: frozenset({TaskState.REVIEW, TaskState.DONE,
                                  TaskState.FAILED, TaskState.BLOCKED,
                                  TaskState.PAUSED, TaskState.QUEUED}),
    TaskState.BLOCKED: frozenset({TaskState.QUEUED, TaskState.WAITING,
                                  TaskState.PAUSED, TaskState.FAILED,
                                  TaskState.DONE}),
    TaskState.REVIEW: frozenset({TaskState.DONE, TaskState.FAILED,
                                 TaskState.BLOCKED, TaskState.QUEUED,
                                 TaskState.PAUSED}),
    # PAUSED di duoc toi ca trang thai KET THUC, va day khong phai su
    # rong rai — no la he qua truc tiep cua ngu nghia `pause`.
    #
    # `Executor.run` la DONG BO: cach duy nhat cat mot luot dang bay la giet
    # tien trinh agent, va do la `stop`, khong phai `pause`. Nen `pause` mot
    # viec dang RUNNING chi nghia la "dung nhan viec moi"; luot dang bay VAN
    # chay not va VAN tra ve ket qua. Khong cho PAUSED -> DONE thi ket qua
    # that do bi nem di va viec bi danh FAILED oan — da vap that o bai kiem
    # giao dien dau tien.
    TaskState.PAUSED: frozenset({TaskState.QUEUED, TaskState.WAITING,
                                 TaskState.FAILED, TaskState.DONE,
                                 TaskState.REVIEW, TaskState.BLOCKED}),
    TaskState.DONE: frozenset(),
    TaskState.FAILED: frozenset({TaskState.QUEUED}),   # thu lai thu cong
})


def co_the_chuyen(cu: TaskState, moi: TaskState) -> bool:
    return moi is cu or moi in _CHUYEN_HOP_LE.get(cu, frozenset())


def kiem_chuyen(task_id: str, cu: TaskState, moi: TaskState) -> None:
    if not co_the_chuyen(cu, moi):
        raise TransitionError(
            f"{task_id}: {cu.value} -> {moi.value} không hợp lệ. "
            f"Từ {cu.value} chỉ đi được tới "
            f"{sorted(x.value for x in _CHUYEN_HOP_LE.get(cu, frozenset()))}.")


def map_envelope_status(status: str, *, need_review: bool) -> TaskState:
    """`ResultEnvelope.status` của Router V4 -> `TaskState`.

    MỘT chỗ duy nhất làm việc này. `ok` + hợp đồng đòi review độc lập thì
    KHÔNG nhảy thẳng `DONE`: việc còn một cổng nữa, và trạng thái phải nói
    được điều đó.
    """
    s = (status or "").strip().lower()
    if s == "ok":
        return TaskState.REVIEW if need_review else TaskState.DONE
    if s == "blocked":
        return TaskState.BLOCKED
    return TaskState.FAILED


class SessionState(str, Enum):
    """Vòng đời một PHIÊN agent do Control Center quản lý.

    `DEAD` khác `STOPPED`: `STOPPED` là ta chủ động dừng, `DEAD` là tiến
    trình biến mất mà không ai bảo nó biến mất (máy ngủ, `taskkill`, sập).
    Phân biệt được thì lúc phục hồi mới biết nên báo động hay im lặng.
    """

    STARTING = "STARTING"
    IDLE = "IDLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"
    DEAD = "DEAD"

    @property
    def usable(self) -> bool:
        return self in (SessionState.IDLE, SessionState.BUSY)

    @property
    def alive(self) -> bool:
        return self in (SessionState.STARTING, SessionState.IDLE,
                        SessionState.BUSY, SessionState.DRAINING)


class SessionAction(str, Enum):
    """Kết luận của `SessionManager` cho MỘT việc."""

    REUSE = "REUSE"
    CREATE = "CREATE"
    WAIT = "WAIT"


class LockKind(str, Enum):
    """Ba lớp tài nguyên tranh chấp được, xếp theo mức nguy hiểm TĂNG DẦN.

    Thứ tự này có ý nghĩa vận hành, không phải trang trí: `reclaim()` chỉ
    được phép thu hồi khoá hết hạn của hai lớp đầu. Một khoá PRODUCTION hết
    hạn KHÔNG bao giờ tự về — xem `locks.py`.
    """

    FILESYSTEM = "FILESYSTEM"
    SERVICE = "SERVICE"
    PRODUCTION = "PRODUCTION"

    @property
    def tu_thu_hoi_duoc(self) -> bool:
        return self is not LockKind.PRODUCTION


class PermissionClass(str, Enum):
    """Hai lớp, và KHÔNG có lớp thứ ba.

    Cố ý không có `BYPASS`/`SKIP`. Một enum có giá trị "bỏ qua" sẽ được ai
    đó dùng lúc 2 giờ sáng để một việc chạy tiếp, và rào an toàn biến mất
    vĩnh viễn từ đó.
    """

    AUTO = "AUTO"
    GATED = "GATED"


class UsageConfidence(str, Enum):
    """Mức tin cậy của MỘT con số usage.

    `UNAVAILABLE` là một GIÁ TRỊ hợp lệ, không phải lỗi. Bảng usage phải nói
    được "không đo được" thay vì hiện `0` — số 0 đọc thành "đã đo và bằng
    không", và đó là một lời nói dối tốn kém.
    """

    ACTUAL = "ACTUAL"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class UsageMetric:
    """Một số đo usage, LUÔN kèm nguồn gốc niềm tin."""

    label: str
    value: Optional[float]
    confidence: UsageConfidence
    unit: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.confidence is UsageConfidence.UNAVAILABLE and self.value is not None:
            raise ValueError(
                f"{self.label}: UNAVAILABLE mà vẫn có giá trị {self.value!r} — "
                f"mâu thuẫn. Không đo được thì `value` phải là None; điền số "
                f"vào đây chính là bịa số liệu nhà cung cấp.")
        if self.confidence is not UsageConfidence.UNAVAILABLE and self.value is None:
            raise ValueError(
                f"{self.label}: khai {self.confidence.value} nhưng không có "
                f"giá trị — dùng UNAVAILABLE thay vì giả vờ đã đo.")

    def render(self) -> str:
        if self.value is None:
            return f"{self.label}: — (KHÔNG ĐO ĐƯỢC)"
        so = f"{self.value:.2f}".rstrip("0").rstrip(".")
        return f"{self.label}: {so}{self.unit} [{self.confidence.value}]"

    def to_dict(self) -> Dict:
        return {"label": self.label, "value": self.value,
                "confidence": self.confidence.value, "unit": self.unit,
                "note": self.note}


@dataclass
class Project:
    project_id: str
    name: str
    repo_path: str
    default_branch: str = "main"
    #: Tai nguyen DANH SAN cua du an — dung de goi y khoa, khong bat buoc.
    resources: Tuple[str, ...] = ()
    note: str = ""
    archived: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {"project_id": self.project_id, "name": self.name,
                "repo_path": self.repo_path,
                "default_branch": self.default_branch,
                "resources": list(self.resources), "note": self.note,
                "archived": self.archived, "created_at": self.created_at,
                "updated_at": self.updated_at}


@dataclass
class Task:
    task_id: str
    project_id: str
    title: str
    objective: str
    state: TaskState = TaskState.QUEUED
    priority: int = 50                      # thap = gap hon
    parent_id: str = ""
    dependencies: Tuple[str, ...] = ()
    owner_session: str = ""
    mission_id: str = ""
    contract: Dict = field(default_factory=dict)
    permission: str = PermissionClass.AUTO.value
    gate_reason: str = ""
    blocked_reason: str = ""
    resources: Tuple[str, ...] = ()
    attempts: int = 0
    result: Optional[Dict] = None
    worktree: str = ""
    branch: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def runtime_seconds(self) -> float:
        if not self.started_at:
            return 0.0
        return max(0.0, (self.ended_at or time.time()) - self.started_at)

    def to_dict(self) -> Dict:
        return {"task_id": self.task_id, "project_id": self.project_id,
                "title": self.title, "objective": self.objective,
                "state": self.state.value, "priority": self.priority,
                "parent_id": self.parent_id,
                "dependencies": list(self.dependencies),
                "owner_session": self.owner_session,
                "mission_id": self.mission_id, "contract": self.contract,
                "permission": self.permission, "gate_reason": self.gate_reason,
                "blocked_reason": self.blocked_reason,
                "resources": list(self.resources), "attempts": self.attempts,
                "result": self.result, "worktree": self.worktree,
                "branch": self.branch, "created_at": self.created_at,
                "updated_at": self.updated_at, "started_at": self.started_at,
                "ended_at": self.ended_at,
                "runtime_seconds": round(self.runtime_seconds, 2)}


@dataclass
class Session:
    """Một phiên agent SỐNG do Control Center quản lý.

    `scope` là phạm vi ghi phiên này đang sở hữu. Nó quyết định việc sau có
    được DÙNG LẠI phiên này không — xem `sessions.py`. Rỗng = phiên chỉ đọc.
    """

    session_id: str
    project_id: str
    provider: str
    runtime_id: str
    model_id: str
    state: SessionState = SessionState.STARTING
    worktree: str = ""
    branch: str = ""
    pid: Optional[int] = None
    scope: Tuple[str, ...] = ()
    current_task: str = ""
    task_count: int = 0
    note: str = ""
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    @property
    def placement_key(self) -> str:
        return f"{self.runtime_id}/{self.model_id}"

    @property
    def idle_seconds(self) -> float:
        return max(0.0, time.time() - self.last_activity)

    def to_dict(self) -> Dict:
        return {"session_id": self.session_id, "project_id": self.project_id,
                "provider": self.provider, "runtime_id": self.runtime_id,
                "model_id": self.model_id, "placement": self.placement_key,
                "state": self.state.value, "worktree": self.worktree,
                "branch": self.branch, "pid": self.pid,
                "scope": list(self.scope), "current_task": self.current_task,
                "task_count": self.task_count, "note": self.note,
                "created_at": self.created_at,
                "last_activity": self.last_activity,
                "idle_seconds": round(self.idle_seconds, 1)}


@dataclass
class ResourceLock:
    lock_id: str
    project_id: str
    kind: LockKind
    resource: str
    holder_task: str = ""
    holder_session: str = ""
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    note: str = ""

    def con_han(self, *, now: Optional[float] = None) -> bool:
        if not self.expires_at:
            return True                     # khong han = giu den khi tra
        return (time.time() if now is None else now) < self.expires_at

    def to_dict(self) -> Dict:
        return {"lock_id": self.lock_id, "project_id": self.project_id,
                "kind": self.kind.value, "resource": self.resource,
                "holder_task": self.holder_task,
                "holder_session": self.holder_session,
                "acquired_at": self.acquired_at, "expires_at": self.expires_at,
                "live": self.con_han(), "note": self.note}


@dataclass
class ChatMessage:
    message_id: int
    project_id: str
    role: str                               # user | router | system
    text: str
    ts: float = field(default_factory=time.time)
    meta: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {"message_id": self.message_id, "project_id": self.project_id,
                "role": self.role, "text": self.text, "ts": self.ts,
                "meta": self.meta}
