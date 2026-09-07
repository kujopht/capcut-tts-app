"""Router Control Center V0.1 — phòng điều khiển cho Router V4 đã có.

MỘT DÒNG MÔ TẢ: mở một dự án, gõ mục tiêu vào ô chat, và Router tự phân rã
việc, chọn agent, dựng worktree, dựng/dùng lại phiên, khoá tài nguyên, chạy,
báo cáo — không phải mở tay một terminal Claude/Codex/Antigravity nào.

NÓ KHÔNG THIẾT KẾ LẠI ROUTER V4. Bốn thứ khó nhất — chấm điểm placement theo
năng lực, cô lập worktree, cổng kiểm định "không tin worker tự khai PASS",
và phong bì kết quả — đã có, đã chạy thật, và được dùng NGUYÊN VẸN. Xem
`docs/AI_ROUTER_V4.md` và `docs/reports/ROUTER_V4_REAL_PROOF.md`.

CÁI V0.1 THÊM là thứ Router V4 cố ý không có: **trạng thái sống lâu hơn một
mission**.

    model.py        trạng thái việc/phiên/khoá/quyền + mức tin cậy usage
    store.py        sổ SQLite bền: dự án, việc, phiên, worktree, khoá, chat
    permissions.py  phong bì quyền AUTO/GATED theo từng việc
    locks.py        khoá tài nguyên fs/dịch vụ/production — CHỜ, không đua
    worktrees.py    liên kết việc<->nhánh<->worktree, dùng lại khi an toàn
    sessions.py     REUSE / CREATE / WAIT — lõi của V0.1
    planner.py      ý định trong ô chat -> việc được quản lý
    usage.py        usage kèm nhãn ACTUAL / ESTIMATED / UNAVAILABLE
    engine.py       nối tất cả vào Router V4
    ui/             giao diện Textual (cùng nền với Control Room đã có)

BA BẤT BIẾN KHÔNG ĐƯỢC PHÁ:

1. **Không nới rào an toàn.** Không `--dangerously-skip-permissions`, không
   `bypassPermissions`, `destructive_actions_allowed` luôn `False`, và một
   việc chạm lớp GATED thì DỪNG chờ người — không có cờ nào bật qua.
2. **Không bịa số usage.** Không đo được thì `UNAVAILABLE` với giá trị
   `None`, không phải `0`.
3. **Không tự xoá worktree.** Chỉ đánh dấu. Một cây bẩn là bằng chứng, và
   nó có thể chứa công việc chưa commit của một agent vừa chết.
"""
from scripts.control_center.model import (LockKind, PermissionClass, Project,
                                          ResourceLock, Session, SessionAction,
                                          SessionState, Task, TaskState,
                                          UsageConfidence, UsageMetric)
from scripts.control_center.store import ControlStore

__all__ = [
    "ControlStore", "LockKind", "PermissionClass", "Project", "ResourceLock",
    "Session", "SessionAction", "SessionState", "Task", "TaskState",
    "UsageConfidence", "UsageMetric",
]
