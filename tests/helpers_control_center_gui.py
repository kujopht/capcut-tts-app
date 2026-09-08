"""Backend GIẢ cho bộ kiểm giao diện — không đĩa, không git, không mạng.

VÌ SAO GIẢ, KHÔNG DÙNG THẬT: `ControlCenter` thật cần một kho git, một tệp
SQLite, và (khi có việc chờ) một lượt dò sức khoẻ gọi ra `agy`. Bộ kiểm
giao diện chỉ cần biết *widget vẽ đúng cái nó được đưa hay không*, nên buộc
nó dựng cả bộ máy kia sẽ làm bài kiểm chậm, giòn, và có lúc gọi mạng.

Bài kiểm LÁT CẮT DỌC thật (agent thật, worktree thật) đã có ở
`scripts/tests/test_control_center_slice.py` từ V0.1 — tệp này không thay
thế nó và không cố giả vờ làm nó.

Hình dạng dữ liệu ở đây phải khớp `ControlCenter.snapshot()` THẬT. Đó là
chỗ dễ lệch nhất, nên `tests/test_control_center_gui_views.py` có một bài
đối chiếu khoá lại đúng các khoá mà `snapshot()` sinh ra.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional


class _SoGia:
    """Phần `store` mà cửa sổ chạm tới (chỉ `tasks()`)."""

    def __init__(self, chu: "CCGia"):
        self._chu = chu

    def tasks(self, project_id: str = "", **_kw) -> List:
        class _T:
            def __init__(self, d: Dict):
                self.task_id = d.get("task_id", "")
                self.state = d.get("state", "")
                self.blocked_reason = d.get("blocked_reason", "")
                self.gate_reason = d.get("gate_reason", "")
        return [_T(t) for t in self._chu._tasks]


class _UsageGia:
    def __init__(self, chu: "CCGia"):
        self._chu = chu

    def report(self, project_id: str = "", **_kw) -> Dict:
        return self._chu._usage


class CCGia:
    """`ControlCenter` giả với đúng bề mặt mà giao diện dùng."""

    def __init__(self, *, tasks: Optional[List[Dict]] = None,
                 sessions: Optional[List[Dict]] = None,
                 chat: Optional[List[Dict]] = None,
                 locks: Optional[List[Dict]] = None,
                 usage: Optional[Dict] = None):
        self.root = "C:/tmp/gia"
        self.max_parallel = 3
        self._tasks = list(tasks or [])
        self._sessions = list(sessions or [])
        self._chat = list(chat or [])
        self._locks = list(locks or [])
        self._usage = usage or {"metrics": []}
        self.store = _SoGia(self)
        self.usage = _UsageGia(self)
        #: Ghi lai moi loi goi ghi, de bai kiem khang dinh "bam nut co goi
        #: dung ham backend" ma khong can backend thật.
        self.da_goi: List[tuple] = []

    # -- doc -----------------------------------------------------------------

    def projects(self) -> List:
        class _P:
            def __init__(self, pid, ten, duong):
                self.project_id, self.name, self.repo_path = pid, ten, duong
        return [_P("fanfic", "Fanfic", "C:/repo/fanfic"),
                _P("router", "Router", "C:/repo/router")]

    def snapshot(self, project_id: str = "") -> Dict:
        return {
            "projects": [{"project_id": "fanfic", "name": "Fanfic",
                          "repo_path": "C:/repo/fanfic"},
                         {"project_id": "router", "name": "Router",
                          "repo_path": "C:/repo/router"}],
            "selected": project_id or "fanfic",
            "ts": time.time(),
            "tasks": self._tasks,
            "sessions": self._sessions,
            "locks": self._locks,
            "worktrees": [],
            "events": [],
            "chat": self._chat,
            "in_flight": [],
        }

    def log_cua_viec(self, task_id: str, **_kw) -> str:
        return f"=== VIỆC {task_id} ===\ndòng 1\ndòng 2\n"

    # -- ghi -----------------------------------------------------------------

    def start(self, **_kw) -> None:
        self.da_goi.append(("start",))

    def shutdown(self) -> None:
        self.da_goi.append(("shutdown",))

    def chat(self, project_id: str, text: str) -> Dict:
        self.da_goi.append(("chat", project_id, text))
        return {"reply": "ok", "tasks": [], "plan": {}}

    def pause(self, task_id: str, **_kw):
        self.da_goi.append(("pause", task_id))

    def resume(self, task_id: str):
        self.da_goi.append(("resume", task_id))

    def stop(self, task_id: str, **_kw):
        self.da_goi.append(("stop", task_id))

    def mo_khoa_gated(self, task_id: str, **_kw):
        self.da_goi.append(("mo_khoa_gated", task_id))

    def them_project(self, p):
        self.da_goi.append(("them_project", getattr(p, "project_id", "")))
        return p


def viec_mau() -> List[Dict]:
    """Bốn việc phủ đúng các trạng thái giao diện phải vẽ khác nhau."""
    gio = time.time()
    return [
        {"task_id": "fanfic.t1", "project_id": "fanfic",
         "title": "Backend wiring", "objective": "nối hàng đợi",
         "state": "RUNNING", "priority": 5, "dependencies": [],
         "owner_session": "s-abc123", "permission": "AUTO",
         "worktree": "C:\\repo\\.router\\worktrees\\AG01\\t1",
         "branch": "router/AG01/t1", "attempts": 1,
         "started_at": gio - 75, "updated_at": gio - 2, "ended_at": None,
         "gate_reason": "", "blocked_reason": ""},
        {"task_id": "fanfic.t2", "project_id": "fanfic",
         "title": "Artwork integration", "objective": "ghép ảnh",
         "state": "QUEUED", "priority": 5, "dependencies": [],
         "owner_session": "", "permission": "AUTO", "worktree": "",
         "branch": "", "attempts": 0, "started_at": None,
         "updated_at": gio - 30, "ended_at": None,
         "gate_reason": "", "blocked_reason": ""},
        {"task_id": "fanfic.t3", "project_id": "fanfic",
         "title": "Tests", "objective": "chạy bộ kiểm",
         "state": "WAITING", "priority": 4, "dependencies": ["fanfic.t1"],
         "owner_session": "", "permission": "AUTO", "worktree": "",
         "branch": "", "attempts": 0, "started_at": None,
         "updated_at": gio - 20, "ended_at": None,
         "gate_reason": "", "blocked_reason": ""},
        {"task_id": "fanfic.t4", "project_id": "fanfic",
         "title": "Production proof", "objective": "deploy",
         "state": "BLOCKED", "priority": 9, "dependencies": [],
         "owner_session": "", "permission": "GATED", "worktree": "",
         "branch": "", "attempts": 0, "started_at": None,
         "updated_at": gio - 10, "ended_at": None,
         "gate_reason": "production_deploy",
         "blocked_reason": "Việc này deploy production — cần bạn duyệt rõ ràng"},
    ]


def phien_mau() -> List[Dict]:
    gio = time.time()
    return [{"session_id": "s-abc123", "project_id": "fanfic",
             "provider": "antigravity", "runtime_id": "AG01",
             "model_id": "claude-opus-4-6-thinking", "state": "BUSY",
             "worktree": "C:\\repo\\.router\\worktrees\\AG01\\t1",
             "branch": "router/AG01/t1", "pid": 1736, "scope": "",
             "current_task": "fanfic.t1", "task_count": 1, "note": "",
             "created_at": gio - 80, "last_activity": gio - 3}]


def chat_mau() -> List[Dict]:
    gio = time.time()
    return [
        {"message_id": 1, "project_id": "fanfic", "role": "user",
         "text": "Nối hàng đợi, ghép ảnh, chạy test, rồi deploy production",
         "ts": gio - 100, "meta": {}},
        {"message_id": 2, "project_id": "fanfic", "role": "router",
         "text": "Đã phân rã thành 4 việc.", "ts": gio - 99,
         "meta": {"task_ids": ["fanfic.t1", "fanfic.t2", "fanfic.t3",
                               "fanfic.t4"],
                  "plan": {"tasks": [
                      {"task_id": "t1", "title": "Backend wiring"},
                      {"task_id": "t2", "title": "Artwork integration"},
                      {"task_id": "t3", "title": "Tests"},
                      {"task_id": "t4", "title": "Production proof"}]}}},
    ]


def usage_mau() -> Dict:
    return {"metrics": [
        {"label": "lượt agent hôm nay", "value": 12, "unit": "lượt",
         "confidence": "ESTIMATED", "note": "đếm cục bộ từ sổ"},
        {"label": "quota Antigravity AG01", "value": None, "unit": "%",
         "confidence": "UNAVAILABLE",
         "note": "nhà cung cấp không có số đọc được bằng máy"},
        {"label": "việc đã xong", "value": 3, "unit": "việc",
         "confidence": "ACTUAL", "note": "từ sổ Control Center"},
    ]}


def cau_gia(**kw):
    """Một `Cau` thật, nhưng nối tới `CCGia`. Không chạy đồng hồ làm mới."""
    from scripts.control_center.gui.bridge import Cau
    cc = CCGia(tasks=kw.pop("tasks", viec_mau()),
               sessions=kw.pop("sessions", phien_mau()),
               chat=kw.pop("chat", chat_mau()),
               locks=kw.pop("locks", []),
               usage=kw.pop("usage", usage_mau()))
    return Cau(cc=cc, **kw)
