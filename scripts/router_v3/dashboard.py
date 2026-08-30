"""Bảng trạng thái — Router V3, Phase 14.

Trong một lượt chạy song song, câu hỏi đầu tiên của người vận hành luôn là
"đang tắc ở đâu". Bảng này trả lời bằng ba con số: nút nào đang chạy, còn bao
nhiêu nút, và đường tới hạn còn bao lâu.

KHÔNG in prompt, không in nội dung, không in credential — chỉ id, trạng thái
và thời gian.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from scripts.router_v3.dag import TaskDag
from scripts.router_v3.registry import WorkerRegistry


def _dong_ho(giay: float) -> str:
    giay = max(0, int(giay))
    return f"{giay // 60:02d}:{giay % 60:02d}"


def render(dag: TaskDag, registry: WorkerRegistry, *,
           done: Set[str], failed: Set[str],
           started_at: Dict[str, float], now: Optional[float] = None,
           task_name: str = "", parallelism: int = 0,
           retries: int = 0) -> str:
    now = now if now is not None else time.perf_counter()
    dong: List[str] = ["ROUTER V3", ""]
    if task_name:
        dong += [f"TASK: {task_name}", ""]

    for hang in registry.snapshot():
        wid = hang["worker_id"]
        if hang["health"] == "unavailable":
            trang_thai, viec, dh = "UNAVAILABLE", "", ""
        elif hang["current_task"]:
            t0 = started_at.get(hang["current_task"])
            trang_thai = "RUNNING"
            viec = hang["current_task"]
            dh = _dong_ho(now - t0) if t0 else ""
        else:
            trang_thai, viec, dh = "IDLE", "", ""
        dong.append(f"{wid:<10} {trang_thai:<12} {viec:<16} {dh}")

    con_lai = [n for n in dag.nodes() if n.id not in done]
    _, tt_tong = dag.critical_path()
    con = sum(n.estimated_seconds for n in con_lai)
    dong += [
        "",
        f"Worker song song   : {parallelism}",
        f"Nut hoan tat       : {len(done)}/{len(dag)}",
        f"Nut that bai       : {len(failed)}",
        f"Thu lai            : {retries}",
        f"Duong toi han      : {_dong_ho(tt_tong)} (uoc luong)",
        f"Cong viec con lai  : {_dong_ho(con)} gio worker (uoc luong)",
    ]
    return "\n".join(dong)


def utilization(registry: WorkerRegistry, wall_seconds: float) -> List[Dict]:
    """Mức tận dụng từng worker trong một lượt chạy.

    `busy_ratio` là thứ nói cho biết có nên thêm worker hay không: gần 1.0
    nghĩa là worker là nút thắt (thêm sẽ giúp); thấp nghĩa là đồ thị hoặc
    phụ thuộc mới là nút thắt, và thêm worker chỉ tốn chi phí điều phối.
    """
    ra = []
    for hang in registry.snapshot():
        ban = hang["avg_seconds"] * hang["completed"]
        ra.append({
            "worker_id": hang["worker_id"],
            "completed": hang["completed"],
            "failed": hang["failed"],
            "busy_seconds": round(ban, 2),
            "busy_ratio": round(ban / wall_seconds, 3) if wall_seconds else 0.0,
        })
    return ra


#: Ngưỡng phân loại độ phình ngữ cảnh cho bảng — cùng bậc với `RecyclePolicy`.
_NGU_CANH = ((20_000, "low"), (45_000, "med"))


def _muc_ngu_canh(chars: int) -> str:
    for tran, nhan in _NGU_CANH:
        if chars < tran:
            return nhan
    return "HIGH"


def render_v32(warm_snapshot, *, registry=None, metrics=None,
               parallelism: int = 0, done: int = 0, total: int = 0,
               task_name: str = "") -> str:
    """Bảng cho Router V3.2 — thêm trạng thái ẤM và độ phình ngữ cảnh.

    `cold_starts_avoided` là con số nói lên giá trị của bể ấm; tổng số lượt
    thì không. Hiển thị nó để người vận hành thấy bể có đang làm việc hay chỉ
    đang tồn tại.

    KHÔNG in prompt, không in nội dung, không in token — chỉ id và số đo.
    """
    dong = ["ROUTER V3.2", ""]
    if task_name:
        dong += [f"TASK: {task_name}", ""]

    theo_id = {h["worker_id"]: h for h in warm_snapshot}
    ten = sorted(theo_id) or []
    for wid in ten:
        h = theo_id[wid]
        tt = {"warm_idle": "WARM-IDLE", "warm_busy": "WARM-BUSY",
              "cold": "COLD", "failed": "FAILED"}.get(h["state"], h["state"])
        dong.append(f"{wid:<10} {tt:<11} {(h.get('family') or '-'):<16} "
                    f"context={_muc_ngu_canh(h.get('context_chars', 0))} "
                    f"turns={h.get('turns', 0)}")

    if registry is not None:
        for hang in registry.snapshot():
            if hang["worker_id"] in theo_id:
                continue
            tt = "UNAVAILABLE" if hang["health"] == "unavailable" else (
                "BUSY" if hang["current_task"] else "IDLE")
            dong.append(f"{hang['worker_id']:<10} {tt:<11} "
                        f"{(hang['current_task'] or '-'):<16}")

    dong.append("")
    if parallelism:
        dong.append(f"Worker song song      : {parallelism}")
    if total:
        dong.append(f"Nut hoan tat          : {done}/{total}")
    if metrics is not None:
        m = metrics.snapshot() if hasattr(metrics, "snapshot") else dict(metrics)
        dong += [
            f"Tranh duoc khoi dong  : {m.get('cold_starts_avoided', 0)}",
            f"Do tre trung binh (am): {m.get('avg_warm_seconds', 0)}s",
            f"So lan tai tao        : {m.get('recycles', 0)}",
            f"Khoi dong lanh        : {m.get('cold_starts', 0)} "
            f"({m.get('cold_start_seconds', 0)}s)",
        ]
    return "\n".join(dong)
