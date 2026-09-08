"""Sổ BỀN của Control Center — dự án, việc, phiên, worktree, khoá, sự kiện.

VÌ SAO SQLITE, VÀ VÌ SAO MỘT SỔ RIÊNG:

Kho này đã có ba sổ SQLite, và mỗi cái đúng cho việc của nó:

    `.router/pool/pool.db`          — hàng đợi việc của MỘT lượt chạy (V3)
    `.router/v4/pool.db`            — lease theo KHE runtime (V4)
    `.router/control_room/events.db`— sự kiện quan sát của TUI

Không cái nào mang khái niệm **dự án**, và không cái nào sống lâu hơn một
mission. Control Center cần đúng hai thứ đó, nên nó thêm sổ thứ tư thay vì
nhồi cột `project_id` vào ba lược đồ đang chạy ổn định — sửa lược đồ của
`pool.db` là sửa thứ production farmer đang dùng.

DÙNG LẠI khuôn đã chứng minh của `router_v3/pool/store.py`: WAL, một kết
nối MỖI LUỒNG, `busy_timeout` 30s, và **nhận việc bằng một câu `UPDATE` có
điều kiện** thay vì `SELECT` rồi `UPDATE`. Ba thứ đó không phải sở thích —
chúng là ba lỗi thật đã vấp trong kho này.

KHÔNG LƯU BÍ MẬT. Mọi văn bản do worker/agent sinh ra đi qua
`packet.redact()` TRƯỚC khi chạm đĩa. `pid` là số hiệu tiến trình, không
phải credential.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.router_v3.packet import redact
from scripts.control_center.model import (ChatMessage, LockKind,
                                          PermissionClass, Project,
                                          ResourceLock, Session, SessionState,
                                          Task, TaskState, kiem_chuyen)

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id     TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    repo_path      TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    resources_json TEXT NOT NULL DEFAULT '[]',
    note           TEXT NOT NULL DEFAULT '',
    archived       INTEGER NOT NULL DEFAULT 0,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    objective      TEXT NOT NULL DEFAULT '',
    state          TEXT NOT NULL DEFAULT 'QUEUED',
    priority       INTEGER NOT NULL DEFAULT 50,
    parent_id      TEXT NOT NULL DEFAULT '',
    owner_session  TEXT NOT NULL DEFAULT '',
    mission_id     TEXT NOT NULL DEFAULT '',
    contract_json  TEXT NOT NULL DEFAULT '{}',
    permission     TEXT NOT NULL DEFAULT 'AUTO',
    gate_reason    TEXT NOT NULL DEFAULT '',
    blocked_reason TEXT NOT NULL DEFAULT '',
    resources_json TEXT NOT NULL DEFAULT '[]',
    attempts       INTEGER NOT NULL DEFAULT 0,
    result_json    TEXT NOT NULL DEFAULT '',
    worktree       TEXT NOT NULL DEFAULT '',
    branch         TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    started_at     REAL NOT NULL DEFAULT 0,
    ended_at       REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS task_deps (
    task_id    TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on)
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    provider      TEXT NOT NULL DEFAULT '',
    runtime_id    TEXT NOT NULL DEFAULT '',
    model_id      TEXT NOT NULL DEFAULT '',
    state         TEXT NOT NULL DEFAULT 'STARTING',
    worktree      TEXT NOT NULL DEFAULT '',
    branch        TEXT NOT NULL DEFAULT '',
    pid           INTEGER,
    scope_json    TEXT NOT NULL DEFAULT '[]',
    current_task  TEXT NOT NULL DEFAULT '',
    task_count    INTEGER NOT NULL DEFAULT 0,
    note          TEXT NOT NULL DEFAULT '',
    created_at    REAL NOT NULL,
    last_activity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS worktrees (
    path         TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    branch       TEXT NOT NULL DEFAULT '',
    base_sha     TEXT NOT NULL DEFAULT '',
    owner_session TEXT NOT NULL DEFAULT '',
    state        TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at   REAL NOT NULL,
    last_checked REAL NOT NULL DEFAULT 0,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS locks (
    lock_id        TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    kind           TEXT NOT NULL,
    resource       TEXT NOT NULL,
    holder_task    TEXT NOT NULL DEFAULT '',
    holder_session TEXT NOT NULL DEFAULT '',
    acquired_at    REAL NOT NULL,
    expires_at     REAL NOT NULL DEFAULT 0,
    note           TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS lock_waiters (
    lock_id   TEXT NOT NULL,
    task_id   TEXT NOT NULL,
    since     REAL NOT NULL,
    PRIMARY KEY (lock_id, task_id)
);
CREATE TABLE IF NOT EXISTS chat (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    ts         REAL NOT NULL,
    role       TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    meta_json  TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS cc_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    task_id    TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL,
    level      TEXT NOT NULL DEFAULT 'INFO',
    detail     TEXT NOT NULL DEFAULT '',
    meta_json  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_tasks_proj  ON tasks(project_id, state);
CREATE INDEX IF NOT EXISTS ix_sess_proj   ON sessions(project_id, state);
CREATE INDEX IF NOT EXISTS ix_locks_res   ON locks(project_id, kind, resource);
CREATE INDEX IF NOT EXISTS ix_chat_proj   ON chat(project_id, message_id DESC);
CREATE INDEX IF NOT EXISTS ix_ev_proj     ON cc_events(project_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_ev_task     ON cc_events(task_id, id DESC);
"""

#: Bao nhieu su kien giu lai. Co han co chu dich: mot bang dieu khien chay
#: hang tuan se lam day dia neu khong.
MAX_EVENTS = 20000


def duong_so(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "control_center" / "control.db"


def _js(x: Any) -> str:
    try:
        return json.dumps(x, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return "{}"


def _un(s: Optional[str], mac_dinh: Any) -> Any:
    if not s:
        return mac_dinh
    try:
        return json.loads(s)
    except (TypeError, ValueError, json.JSONDecodeError):
        return mac_dinh


class StoreError(RuntimeError):
    pass


class ControlStore:
    """Sổ bền của Control Center. An toàn khi nhiều luồng/tiến trình dùng."""

    def __init__(self, path: Optional[Path] = None, *,
                 root: Optional[Path] = None):
        self.path = Path(path) if path else duong_so(root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._ghi = threading.Lock()
        with self._c() as c:
            c.executescript(SCHEMA)

    # -- ket noi ------------------------------------------------------------

    def _c(self) -> sqlite3.Connection:
        """Một kết nối MỖI LUỒNG — cùng lý do như `router_v3/pool/store.py`
        và `router_v4/leases.py`: chia sẻ một `sqlite3.Connection` giữa các
        luồng đã gây `InterfaceError` thật trong kho này (2026-09-03), và
        lỗi đó CHỈ lộ ra dưới tải song song, không lộ ở bài kiểm đơn luồng.
        """
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(str(self.path), timeout=30.0,
                                isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA busy_timeout=30000")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    @contextmanager
    def giao_dich_ghi(self):
        """`BEGIN IMMEDIATE` — TUẦN TỰ HOÁ những người ghi.

        VÌ SAO CẦN, và vì sao `ON CONFLICT` không đủ:

        `INSERT ... ON CONFLICT(lock_id)` chỉ nguyên tử khi hai bên tranh
        ĐÚNG MỘT khoá chính. Luật xung đột của khoá FILESYSTEM là **giao
        nhau tiền tố**, nên `web/admin` và `web/admin/content-queue` — hai
        tài nguyên đụng nhau thật — có HAI `lock_id` khác nhau. Không có
        xung đột khoá chính nào để bắt, và cả hai `INSERT` cùng thành công.

        Đã dựng lại được 3/3 lần bằng một `threading.Barrier`: hai việc cùng
        giữ khoá chồng nhau, đúng chế độ hỏng mà `locks.py` tồn tại để chặn.
        Bài kiểm đồng thời trước đó KHÔNG bắt được vì nó cho hai luồng tranh
        CÙNG MỘT tài nguyên — trường hợp duy nhất mà khoá chính che được.

        `BEGIN IMMEDIATE` giành khoá RESERVED ngay lúc mở, nên người ghi thứ
        hai chờ (tới `busy_timeout`) thay vì đọc một ảnh chụp đã cũ. Đây là
        cách đúng để làm nguyên tử một phép "đọc rồi ghi có điều kiện" trong
        SQLite; `ON CONFLICT` chỉ giải được trường hợp trùng khoá chính.

        Lồng nhau là AN TOÀN (không mở giao dịch thứ hai) — SQLite không có
        giao dịch lồng, và một `BEGIN` thứ hai sẽ ném.
        """
        c = self._c()
        if c.in_transaction:
            yield c                     # da o trong mot giao dich — dung lai
            return
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")

    # -- su kien ------------------------------------------------------------

    def ghi_su_kien(self, kind: str, *, project_id: str = "",
                    task_id: str = "", session_id: str = "",
                    level: str = "INFO", detail: str = "",
                    meta: Optional[Dict] = None) -> int:
        """Ghi một sự kiện. `detail`/`meta` LUÔN qua `redact` trước khi lưu.

        Sự kiện là thứ được đọc lại, sao chép vào báo cáo, dán vào chat. Lọc
        ở CỔNG VÀO chứ không ở chỗ hiển thị: một chỗ hiển thị quên lọc thì
        bí mật đã ra ngoài rồi.
        """
        c = self._c()
        cur = c.execute(
            "INSERT INTO cc_events (ts, project_id, task_id, session_id, "
            "kind, level, detail, meta_json) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), project_id, task_id, session_id, kind, level,
             redact(detail or "")[:2000], redact(_js(meta or {}))))
        eid = int(cur.lastrowid or 0)
        if eid % 1000 == 0:
            try:
                c.execute(
                    "DELETE FROM cc_events WHERE id NOT IN "
                    "(SELECT id FROM cc_events ORDER BY id DESC LIMIT ?)",
                    (MAX_EVENTS,))
            except sqlite3.Error:
                pass
        return eid

    def su_kien(self, *, project_id: str = "", task_id: str = "",
                level: str = "", limit: int = 200,
                after_id: int = 0) -> List[Dict]:
        dk, ts = [], []
        if project_id:
            dk.append("project_id=?")
            ts.append(project_id)
        if task_id:
            dk.append("task_id=?")
            ts.append(task_id)
        if level:
            dk.append("level=?")
            ts.append(level)
        if after_id:
            dk.append("id>?")
            ts.append(after_id)
        sql = "SELECT * FROM cc_events"
        if dk:
            sql += " WHERE " + " AND ".join(dk)
        sql += " ORDER BY id DESC LIMIT ?"
        ts.append(limit)
        ra = []
        for h in self._c().execute(sql, ts):
            d = dict(h)
            d["meta"] = _un(d.pop("meta_json", ""), {})
            ra.append(d)
        return ra

    # -- du an --------------------------------------------------------------

    def luu_project(self, p: Project) -> Project:
        p.updated_at = time.time()
        self._c().execute(
            "INSERT INTO projects (project_id, name, repo_path, "
            "default_branch, resources_json, note, archived, created_at, "
            "updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET name=excluded.name, "
            "repo_path=excluded.repo_path, "
            "default_branch=excluded.default_branch, "
            "resources_json=excluded.resources_json, note=excluded.note, "
            "archived=excluded.archived, updated_at=excluded.updated_at",
            (p.project_id, p.name, p.repo_path, p.default_branch,
             _js(list(p.resources)), p.note, 1 if p.archived else 0,
             p.created_at, p.updated_at))
        return p

    def project(self, project_id: str) -> Optional[Project]:
        h = self._c().execute("SELECT * FROM projects WHERE project_id=?",
                              (project_id,)).fetchone()
        return self._project_tu_hang(h) if h else None

    def xoa_project(self, project_id: str) -> Dict[str, int]:
        """Xoá MỘT dự án và mọi hàng thuộc về nó, trong MỘT giao dịch.

        VÌ SAO CÓ HÀM NÀY: cách dọn duy nhất trước đây là xoá cả tệp
        `control.db` — tức là xoá luôn mọi dự án THẬT, mọi lịch sử việc, mọi
        khoá đang giữ. Đó là một búa tạ, và nó không bao giờ được là cơ chế
        dọn dẹp của bản phát hành.

        Xoá theo phạm vi HẸP và NGUYÊN TỬ: `giao_dich_ghi()` bảo đảm không
        có trạng thái nửa vời (dự án biến mất mà việc của nó còn nằm lại,
        hay ngược lại) nếu có gì hỏng giữa chừng.

        KHÔNG chạm tới ĐĨA. Thư mục `git worktree` thật vẫn nguyên — luật
        "không bao giờ tự xoá worktree" áp ở đây như mọi nơi khác. Hàm này
        chỉ gỡ các HÀNG trong sổ; dọn cây làm việc là việc của người, có chủ
        đích, sau khi đã nhìn.
        """
        dem: Dict[str, int] = {}
        with self.giao_dich_ghi() as c:
            ids = [h["task_id"] for h in c.execute(
                "SELECT task_id FROM tasks WHERE project_id=?", (project_id,))]
            if ids:
                hoi = ",".join("?" * len(ids))
                dem["task_deps"] = c.execute(
                    f"DELETE FROM task_deps WHERE task_id IN ({hoi})",
                    ids).rowcount
                dem["lock_waiters"] = c.execute(
                    f"DELETE FROM lock_waiters WHERE task_id IN ({hoi})",
                    ids).rowcount
            for bang in ("tasks", "sessions", "locks", "worktrees", "chat",
                         "cc_events"):
                dem[bang] = c.execute(
                    f"DELETE FROM {bang} WHERE project_id=?",
                    (project_id,)).rowcount
            dem["projects"] = c.execute(
                "DELETE FROM projects WHERE project_id=?",
                (project_id,)).rowcount
        return {k: v for k, v in dem.items() if v}

    def projects(self, *, include_archived: bool = False) -> List[Project]:
        sql = "SELECT * FROM projects"
        if not include_archived:
            sql += " WHERE archived=0"
        sql += " ORDER BY name"
        return [self._project_tu_hang(h) for h in self._c().execute(sql)]

    @staticmethod
    def _project_tu_hang(h: sqlite3.Row) -> Project:
        return Project(
            project_id=h["project_id"], name=h["name"],
            repo_path=h["repo_path"], default_branch=h["default_branch"],
            resources=tuple(_un(h["resources_json"], [])), note=h["note"],
            archived=bool(h["archived"]), created_at=h["created_at"],
            updated_at=h["updated_at"])

    # -- viec ---------------------------------------------------------------

    def luu_task(self, t: Task) -> Task:
        t.updated_at = time.time()
        c = self._c()
        c.execute(
            "INSERT INTO tasks (task_id, project_id, title, objective, state, "
            "priority, parent_id, owner_session, mission_id, contract_json, "
            "permission, gate_reason, blocked_reason, resources_json, "
            "attempts, result_json, worktree, branch, created_at, updated_at, "
            "started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(task_id) DO UPDATE SET title=excluded.title, "
            "objective=excluded.objective, state=excluded.state, "
            "priority=excluded.priority, parent_id=excluded.parent_id, "
            "owner_session=excluded.owner_session, "
            "mission_id=excluded.mission_id, "
            "contract_json=excluded.contract_json, "
            "permission=excluded.permission, gate_reason=excluded.gate_reason, "
            "blocked_reason=excluded.blocked_reason, "
            "resources_json=excluded.resources_json, "
            "attempts=excluded.attempts, result_json=excluded.result_json, "
            "worktree=excluded.worktree, branch=excluded.branch, "
            "updated_at=excluded.updated_at, started_at=excluded.started_at, "
            "ended_at=excluded.ended_at",
            (t.task_id, t.project_id, t.title, redact(t.objective),
             t.state.value, t.priority, t.parent_id, t.owner_session,
             t.mission_id, _js(t.contract), t.permission,
             redact(t.gate_reason)[:500], redact(t.blocked_reason)[:1000],
             _js(list(t.resources)), t.attempts,
             _js(t.result) if t.result is not None else "",
             t.worktree, t.branch, t.created_at, t.updated_at,
             t.started_at, t.ended_at))
        c.execute("DELETE FROM task_deps WHERE task_id=?", (t.task_id,))
        for d in t.dependencies:
            c.execute("INSERT OR IGNORE INTO task_deps (task_id, depends_on) "
                      "VALUES (?,?)", (t.task_id, d))
        return t

    def task(self, task_id: str) -> Optional[Task]:
        h = self._c().execute("SELECT * FROM tasks WHERE task_id=?",
                              (task_id,)).fetchone()
        return self._task_tu_hang(h) if h else None

    def tasks(self, project_id: str = "", *,
              states: Sequence[TaskState] = (),
              limit: int = 1000) -> List[Task]:
        dk, ts = [], []
        if project_id:
            dk.append("project_id=?")
            ts.append(project_id)
        if states:
            dk.append("state IN (" + ",".join("?" * len(states)) + ")")
            ts.extend(s.value for s in states)
        sql = "SELECT * FROM tasks"
        if dk:
            sql += " WHERE " + " AND ".join(dk)
        sql += " ORDER BY priority ASC, created_at ASC LIMIT ?"
        ts.append(limit)
        return [self._task_tu_hang(h) for h in self._c().execute(sql, ts)]

    def _task_tu_hang(self, h: sqlite3.Row) -> Task:
        deps = tuple(
            r["depends_on"] for r in
            self._c().execute("SELECT depends_on FROM task_deps WHERE "
                              "task_id=? ORDER BY depends_on", (h["task_id"],)))
        return Task(
            task_id=h["task_id"], project_id=h["project_id"], title=h["title"],
            objective=h["objective"], state=TaskState(h["state"]),
            priority=int(h["priority"]), parent_id=h["parent_id"],
            dependencies=deps, owner_session=h["owner_session"],
            mission_id=h["mission_id"], contract=_un(h["contract_json"], {}),
            permission=h["permission"], gate_reason=h["gate_reason"],
            blocked_reason=h["blocked_reason"],
            resources=tuple(_un(h["resources_json"], [])),
            attempts=int(h["attempts"]),
            result=_un(h["result_json"], None) if h["result_json"] else None,
            worktree=h["worktree"], branch=h["branch"],
            created_at=h["created_at"], updated_at=h["updated_at"],
            started_at=h["started_at"], ended_at=h["ended_at"])

    def ghi_ket_qua(self, task_id: str, *, result: Optional[Dict],
                    worktree: str = "", branch: str = "") -> None:
        """Ghi KẾT QUẢ của một việc bằng một `UPDATE` HẸP.

        KHÔNG dùng `luu_task` cho đường này. `luu_task` là một UPSERT ghi ĐỦ
        MỌI CỘT, gồm cả `state` — nên "đọc việc, gắn kết quả, lưu lại" là một
        phép đọc–sửa–ghi kéo dài qua cả một lượt agent. Trong khe đó người
        dùng có thể bấm `p`: `pause()` ghi `PAUSED`, rồi luồng `_chay` lưu
        đối tượng CŨ và kéo trạng thái ngược về `RUNNING`. Lệnh `pause` biến
        mất không dấu vết, và bảng điều khiển nói dối về một lệnh vừa ra.

        `UPDATE` chỉ ba cột thì không đụng tới `state` của ai.
        """
        self._c().execute(
            "UPDATE tasks SET result_json=?, updated_at=?, "
            "  worktree=CASE WHEN ?<>'' THEN ? ELSE worktree END, "
            "  branch=CASE WHEN ?<>'' THEN ? ELSE branch END "
            "WHERE task_id=?",
            (_js(result) if result is not None else "", time.time(),
             worktree, worktree, branch, branch, task_id))

    def doi_trang_thai(self, task_id: str, moi: TaskState, *,
                       reason: str = "", session_id: str = "",
                       force: bool = False) -> Task:
        """Đổi trạng thái việc, KIỂM chuyển hợp lệ trước khi ghi.

        `force` chỉ dành cho đường PHỤC HỒI sau khởi động lại, nơi trạng thái
        trên đĩa có thể đã lỗi thời so với thực tế (tiến trình chết trong
        lúc app không chạy). Mọi đường khác phải đi qua bảng chuyển hợp lệ.
        """
        t = self.task(task_id)
        if t is None:
            raise StoreError(f"không có việc {task_id!r}")
        if not force:
            kiem_chuyen(task_id, t.state, moi)
        cu = t.state
        t.state = moi
        if session_id:
            t.owner_session = session_id
        if moi is TaskState.RUNNING and not t.started_at:
            t.started_at = time.time()
        if moi.terminal:
            t.ended_at = time.time()
        if moi is TaskState.BLOCKED:
            t.blocked_reason = reason or t.blocked_reason
        elif reason:
            t.blocked_reason = ""
        self.luu_task(t)
        self.ghi_su_kien(
            "TASK_STATE", project_id=t.project_id, task_id=task_id,
            session_id=session_id,
            level="WARNING" if moi in (TaskState.BLOCKED, TaskState.FAILED)
            else "INFO",
            detail=f"{cu.value} -> {moi.value}" + (f" ({reason})" if reason else ""),
            meta={"from": cu.value, "to": moi.value, "forced": force})
        return t

    def claim_task(self, task_id: str, session_id: str) -> bool:
        """Nhận việc — NGUYÊN TỬ, đúng khuôn `PoolStore.claim`.

        Điều kiện `state` nằm TRONG câu `UPDATE`. Tách thành `SELECT` rồi
        `UPDATE` sẽ để hai vòng lặp lập lịch (app + CLI, hoặc hai luồng)
        cùng nhận một việc và cùng dựng một phiên cho nó.
        """
        now = time.time()
        cur = self._c().execute(
            "UPDATE tasks SET state='RUNNING', owner_session=?, "
            "started_at=CASE WHEN started_at=0 THEN ? ELSE started_at END, "
            "attempts=attempts+1, updated_at=? "
            "WHERE task_id=? AND state IN ('QUEUED','WAITING')",
            (session_id, now, now, task_id))
        if cur.rowcount == 1:
            self.ghi_su_kien("TASK_CLAIMED", task_id=task_id,
                             session_id=session_id, detail=session_id)
            return True
        return False

    # -- phien --------------------------------------------------------------

    def luu_session(self, s: Session) -> Session:
        s.last_activity = time.time()
        self._c().execute(
            "INSERT INTO sessions (session_id, project_id, provider, "
            "runtime_id, model_id, state, worktree, branch, pid, scope_json, "
            "current_task, task_count, note, created_at, last_activity) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET state=excluded.state, "
            "worktree=excluded.worktree, branch=excluded.branch, "
            "pid=excluded.pid, scope_json=excluded.scope_json, "
            "current_task=excluded.current_task, "
            "task_count=excluded.task_count, note=excluded.note, "
            "last_activity=excluded.last_activity",
            (s.session_id, s.project_id, s.provider, s.runtime_id, s.model_id,
             s.state.value, s.worktree, s.branch, s.pid, _js(list(s.scope)),
             s.current_task, s.task_count, redact(s.note)[:500], s.created_at,
             s.last_activity))
        return s

    def session(self, session_id: str) -> Optional[Session]:
        h = self._c().execute("SELECT * FROM sessions WHERE session_id=?",
                              (session_id,)).fetchone()
        return self._session_tu_hang(h) if h else None

    def sessions(self, project_id: str = "", *,
                 alive_only: bool = False) -> List[Session]:
        dk, ts = [], []
        if project_id:
            dk.append("project_id=?")
            ts.append(project_id)
        if alive_only:
            dk.append("state IN ('STARTING','IDLE','BUSY','DRAINING')")
        sql = "SELECT * FROM sessions"
        if dk:
            sql += " WHERE " + " AND ".join(dk)
        sql += " ORDER BY created_at"
        return [self._session_tu_hang(h) for h in self._c().execute(sql, ts)]

    @staticmethod
    def _session_tu_hang(h: sqlite3.Row) -> Session:
        return Session(
            session_id=h["session_id"], project_id=h["project_id"],
            provider=h["provider"], runtime_id=h["runtime_id"],
            model_id=h["model_id"], state=SessionState(h["state"]),
            worktree=h["worktree"], branch=h["branch"],
            pid=int(h["pid"]) if h["pid"] is not None else None,
            scope=tuple(_un(h["scope_json"], [])),
            current_task=h["current_task"], task_count=int(h["task_count"]),
            note=h["note"], created_at=h["created_at"],
            last_activity=h["last_activity"])

    def dat_trang_thai_session(self, session_id: str, state: SessionState, *,
                               current_task: Optional[str] = None,
                               note: str = "") -> Optional[Session]:
        s = self.session(session_id)
        if s is None:
            return None
        s.state = state
        if current_task is not None:
            s.current_task = current_task
        if note:
            s.note = note
        return self.luu_session(s)

    # -- worktree -----------------------------------------------------------

    def luu_worktree(self, *, path: str, project_id: str, branch: str = "",
                     base_sha: str = "", owner_session: str = "",
                     state: str = "ACTIVE", note: str = "") -> None:
        now = time.time()
        self._c().execute(
            "INSERT INTO worktrees (path, project_id, branch, base_sha, "
            "owner_session, state, created_at, last_checked, note) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(path) DO UPDATE SET branch=excluded.branch, "
            "owner_session=excluded.owner_session, state=excluded.state, "
            "last_checked=excluded.last_checked, note=excluded.note",
            (path, project_id, branch, base_sha, owner_session, state, now,
             now, note[:300]))

    def worktrees(self, project_id: str = "") -> List[Dict]:
        if project_id:
            hs = self._c().execute(
                "SELECT * FROM worktrees WHERE project_id=? ORDER BY path",
                (project_id,))
        else:
            hs = self._c().execute("SELECT * FROM worktrees ORDER BY path")
        return [dict(h) for h in hs]

    def worktree(self, path: str) -> Optional[Dict]:
        h = self._c().execute("SELECT * FROM worktrees WHERE path=?",
                              (path,)).fetchone()
        return dict(h) if h else None

    # -- khoa ---------------------------------------------------------------

    def them_lock(self, l: ResourceLock, *,
                  now: Optional[float] = None) -> bool:
        """Giành khoá. `False` nếu người khác đang giữ và CÒN HẠN. NGUYÊN TỬ.

        Ba trường hợp gộp vào MỘT câu lệnh, đúng khuôn `LeaseStore.acquire`
        của Router V4:

            chưa ai giữ            -> chèn mới
            người giữ đã HẾT HẠN   -> cướp lại
            chính mình đang giữ    -> gia hạn

        Trường hợp thứ hai là lý do `ON CONFLICT DO NOTHING` không đủ: một
        khoá đã hết hạn vẫn CHIẾM khoá chính, nên bản `DO NOTHING` từ chối
        cấp cho người tiếp theo và tài nguyên bị treo vĩnh viễn sau một lần
        tiến trình chết. Đã vấp thật ở bài kiểm đầu tiên.

        `WHERE` KHÔNG BAO GIỜ cướp một khoá PRODUCTION còn trong sổ, kể cả
        khi nó quá hạn — hết hạn không phải là sự cho phép. Xem `locks.py`.
        """
        curr = time.time() if now is None else now
        cur = self._c().execute(
            "INSERT INTO locks (lock_id, project_id, kind, resource, "
            "holder_task, holder_session, acquired_at, expires_at, note) "
            "VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(lock_id) DO UPDATE SET "
            "  holder_task=excluded.holder_task, "
            "  holder_session=excluded.holder_session, "
            "  acquired_at=excluded.acquired_at, "
            "  expires_at=excluded.expires_at, note=excluded.note "
            "WHERE (locks.kind <> 'PRODUCTION' AND locks.expires_at <> 0 "
            "       AND locks.expires_at <= ?) "
            "   OR locks.holder_task = ?",
            (l.lock_id, l.project_id, l.kind.value, l.resource, l.holder_task,
             l.holder_session, l.acquired_at, l.expires_at, l.note[:300],
             curr, l.holder_task))
        return cur.rowcount == 1

    def locks(self, project_id: str = "") -> List[ResourceLock]:
        if project_id:
            hs = self._c().execute(
                "SELECT * FROM locks WHERE project_id=? ORDER BY acquired_at",
                (project_id,))
        else:
            hs = self._c().execute("SELECT * FROM locks ORDER BY acquired_at")
        return [ResourceLock(
            lock_id=h["lock_id"], project_id=h["project_id"],
            kind=LockKind(h["kind"]), resource=h["resource"],
            holder_task=h["holder_task"], holder_session=h["holder_session"],
            acquired_at=h["acquired_at"], expires_at=h["expires_at"],
            note=h["note"]) for h in hs]

    def xoa_lock(self, lock_id: str, *, holder_task: str = "") -> bool:
        if holder_task:
            cur = self._c().execute(
                "DELETE FROM locks WHERE lock_id=? AND holder_task=?",
                (lock_id, holder_task))
        else:
            cur = self._c().execute("DELETE FROM locks WHERE lock_id=?",
                                    (lock_id,))
        if cur.rowcount == 1:
            self._c().execute("DELETE FROM lock_waiters WHERE lock_id=?",
                              (lock_id,))
        return cur.rowcount == 1

    def gia_han_lock(self, lock_id: str, expires_at: float) -> bool:
        cur = self._c().execute("UPDATE locks SET expires_at=? WHERE lock_id=?",
                                (expires_at, lock_id))
        return cur.rowcount == 1

    def them_waiter(self, lock_id: str, task_id: str) -> None:
        self._c().execute(
            "INSERT OR IGNORE INTO lock_waiters (lock_id, task_id, since) "
            "VALUES (?,?,?)", (lock_id, task_id, time.time()))

    def xoa_waiter(self, task_id: str) -> None:
        self._c().execute("DELETE FROM lock_waiters WHERE task_id=?", (task_id,))

    def waiters(self, lock_id: str = "") -> List[Dict]:
        if lock_id:
            hs = self._c().execute(
                "SELECT * FROM lock_waiters WHERE lock_id=? ORDER BY since",
                (lock_id,))
        else:
            hs = self._c().execute("SELECT * FROM lock_waiters ORDER BY since")
        return [dict(h) for h in hs]

    # -- chat ---------------------------------------------------------------

    def them_chat(self, project_id: str, role: str, text: str, *,
                  meta: Optional[Dict] = None) -> ChatMessage:
        now = time.time()
        sach = redact(text or "")
        cur = self._c().execute(
            "INSERT INTO chat (project_id, ts, role, text, meta_json) "
            "VALUES (?,?,?,?,?)",
            (project_id, now, role, sach, redact(_js(meta or {}))))
        return ChatMessage(message_id=int(cur.lastrowid or 0),
                           project_id=project_id, role=role, text=sach,
                           ts=now, meta=meta or {})

    def chat(self, project_id: str, *, limit: int = 200) -> List[ChatMessage]:
        hs = self._c().execute(
            "SELECT * FROM chat WHERE project_id=? ORDER BY message_id DESC "
            "LIMIT ?", (project_id, limit))
        ra = [ChatMessage(message_id=int(h["message_id"]),
                          project_id=h["project_id"], role=h["role"],
                          text=h["text"], ts=h["ts"],
                          meta=_un(h["meta_json"], {})) for h in hs]
        ra.reverse()
        return ra
