"""Hợp đồng thuê worker (lease) + nhịp tim — Router V4, mission #15.

BỐN CHẾ ĐỘ HỎNG mà lease này tồn tại để chặn:

    1. GIAO TRÙNG      — hai bộ lập lịch cùng giao một việc cho một runtime.
    2. BUSY BỎ HOANG   — tiến trình chạy việc chết, runtime kẹt ở BUSY mãi.
    3. HAI CHỦ         — hai tiến trình cùng tưởng mình sở hữu một runtime.
    4. BÃO THỬ LẠI     — việc hỏng, thử lại ngay, hỏng lại, lặp vô hạn.

CÁCH GIẢI, cố ý đơn giản: một lease là một hàng có HẠN trong SQLite, giành
được bằng MỘT câu `UPDATE` có điều kiện (nguyên tử). Chủ sở hữu phải đập
nhịp tim; hết hạn mà không đập thì lease coi như bỏ, và việc được thu hồi.

KHÔNG DÙNG KHOÁ TIẾN TRÌNH/FILE LOCK: chúng không sống sót qua một tiến
trình bị `taskkill`, và trên Windows một file lock mồ côi phải chờ HĐH dọn.
Lease có HẠN thì tự hết hiệu lực — đó chính là thuộc tính cần.

`owner_id` là danh tính TIẾN TRÌNH (pid + một chuỗi ngẫu nhiên mỗi lần khởi
động), không phải danh tính người dùng hay credential.
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

#: Lease song bao lau neu khong duoc dap nhip. Phai LON HON chu ky dap nhip
#: vai lan — bang nhau nghia la mot lan tre nhe cung lam mat lease.
LEASE_TTL = 90.0
HEARTBEAT_EVERY = 20.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (
    runtime_id  TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    task_id     TEXT NOT NULL DEFAULT '',
    acquired_at REAL NOT NULL,
    expires_at  REAL NOT NULL,
    heartbeat_at REAL NOT NULL
);
"""


def owner_id() -> str:
    """Danh tính tiến trình hiện tại. Mới mỗi lần khởi động có chủ đích:
    một tiến trình khởi động lại KHÔNG được thừa kế lease của bản trước —
    bản trước có thể vẫn đang chạy."""
    return f"pid{os.getpid()}-{uuid.uuid4().hex[:8]}"


@dataclass
class Lease:
    runtime_id: str
    owner_id: str
    task_id: str
    acquired_at: float
    expires_at: float
    heartbeat_at: float

    def con_han(self, *, now: Optional[float] = None) -> bool:
        return (time.time() if now is None else now) < self.expires_at

    def to_dict(self) -> Dict:
        return {"runtime_id": self.runtime_id, "owner_id": self.owner_id,
                "task_id": self.task_id, "acquired_at": self.acquired_at,
                "expires_at": self.expires_at, "heartbeat_at": self.heartbeat_at}


class LeaseStore:
    """Sổ lease. Dùng chung tệp SQLite với sổ việc là được — nhưng tách
    bảng để hai khái niệm không dính vào nhau."""

    def __init__(self, path: Optional[Path] = None, *,
                 root: Optional[Path] = None, ttl: float = LEASE_TTL):
        goc = Path(root) if root else Path.cwd()
        self.path = Path(path) if path else goc / ".router" / "v4" / "pool.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._conn: Optional[sqlite3.Connection] = None
        with self._c() as c:
            c.executescript(SCHEMA)

    def _c(self) -> sqlite3.Connection:
        if self._conn is None:
            c = sqlite3.connect(str(self.path), timeout=30.0,
                                isolation_level=None, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=30000")
            self._conn = c
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- giành / giữ / trả --------------------------------------------------

    def acquire(self, runtime_id: str, owner: str, *, task_id: str = "",
                now: Optional[float] = None) -> Optional[Lease]:
        """Giành lease. `None` nếu người khác đang giữ và CÒN HẠN.

        Ba trường hợp gộp vào MỘT câu lệnh nguyên tử:
          - chưa ai giữ            -> chèn mới
          - người giữ đã HẾT HẠN   -> cướp lại (đây là cách thu hồi BUSY bỏ hoang)
          - chính mình đang giữ    -> gia hạn

        Tách thành `SELECT` rồi `INSERT` sẽ để hai tiến trình cùng thấy "trống"
        rồi cùng chèn — đúng chế độ hỏng số 1 và 3 ở docstring module.
        """
        curr = time.time() if now is None else now
        het = curr + self.ttl
        c = self._c()
        cur = c.execute(
            "INSERT INTO leases (runtime_id, owner_id, task_id, acquired_at, "
            "expires_at, heartbeat_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(runtime_id) DO UPDATE SET "
            "  owner_id=excluded.owner_id, task_id=excluded.task_id, "
            "  acquired_at=excluded.acquired_at, expires_at=excluded.expires_at,"
            "  heartbeat_at=excluded.heartbeat_at "
            "WHERE leases.expires_at <= ? OR leases.owner_id = ?",
            (runtime_id, owner, task_id, curr, het, curr, curr, owner))
        if cur.rowcount != 1:
            return None
        return self.get(runtime_id)

    def heartbeat(self, runtime_id: str, owner: str, *,
                  now: Optional[float] = None) -> bool:
        """Gia hạn. `False` nếu lease đã bị người khác cướp — bên gọi PHẢI
        dừng việc đang chạy: nó không còn sở hữu runtime đó nữa."""
        curr = time.time() if now is None else now
        cur = self._c().execute(
            "UPDATE leases SET heartbeat_at=?, expires_at=? "
            "WHERE runtime_id=? AND owner_id=?",
            (curr, curr + self.ttl, runtime_id, owner))
        return cur.rowcount == 1

    def release(self, runtime_id: str, owner: str) -> bool:
        cur = self._c().execute(
            "DELETE FROM leases WHERE runtime_id=? AND owner_id=?",
            (runtime_id, owner))
        return cur.rowcount == 1

    def get(self, runtime_id: str) -> Optional[Lease]:
        h = self._c().execute("SELECT * FROM leases WHERE runtime_id=?",
                              (runtime_id,)).fetchone()
        return Lease(**dict(h)) if h else None

    def all(self) -> List[Lease]:
        return [Lease(**dict(h)) for h in
                self._c().execute("SELECT * FROM leases ORDER BY runtime_id")]

    def expired(self, *, now: Optional[float] = None) -> List[Lease]:
        """Lease đã chết. Việc gắn với chúng thu hồi được an toàn."""
        curr = time.time() if now is None else now
        return [l for l in self.all() if l.expires_at <= curr]

    def reap(self, *, now: Optional[float] = None) -> List[Lease]:
        """Dọn lease chết và trả về danh sách đã dọn.

        KHÔNG tự động chạy lại việc ở đây: thu hồi là một sự kiện đáng ghi
        nhật ký, và quyết định chạy lại thuộc về bộ chạy việc (có trần thử
        lại). Dọn lease mà tự động nạp lại việc ngay tại đây là cách tạo ra
        bão thử lại — chế độ hỏng số 4.
        """
        chet = self.expired(now=now)
        for l in chet:
            self._c().execute(
                "DELETE FROM leases WHERE runtime_id=? AND owner_id=? "
                "AND expires_at<=?",
                (l.runtime_id, l.owner_id, time.time() if now is None else now))
        return chet
