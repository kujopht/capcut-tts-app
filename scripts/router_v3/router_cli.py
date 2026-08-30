"""Giao diện dòng lệnh dùng lại — Router LTS Phase 16.

    python -m scripts.router_v3.router_cli status
    python -m scripts.router_v3.router_cli workers
    python -m scripts.router_v3.router_cli task <node_id>
    python -m scripts.router_v3.router_cli resume
    python -m scripts.router_v3.router_cli doctor

KHÔNG có tiến trình Router nền chạy liên tục trong kiến trúc này — mỗi
mission là một lượt script rời. Vì vậy các lệnh dưới đây đọc TRẠNG THÁI ĐÃ
LƯU (`.router/checkpoints/latest.json`, xem `checkpoint.py`) cộng một lượt
DÒ SỐNG (`registry.default_registry(probe=True)`) cho bức tranh "ngay bây
giờ" — không giả lập một tiến trình không tồn tại.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3 import checkpoint as cp_mod
from scripts.router_v3.registry import default_registry


def _in_trang_thai(a) -> int:
    cp = cp_mod.doc(Path(a.checkpoint) if a.checkpoint else None)
    reg = default_registry(probe=True)

    print("AI ROUTER LTS\n")
    for hang in reg.snapshot():
        tt = "UNAVAILABLE" if hang["health"] == "unavailable" else (
            "BUSY" if hang["current_task"] else "IDLE")
        mach = " [MẠCH MỞ]" if hang.get("circuit_open") else ""
        print(f"{hang['worker_id']:<12} {tt:<12}{mach}")

    print()
    if cp is None:
        print("Chưa có checkpoint nào (.router/checkpoints/latest.json) — "
             "chưa từng chạy hoặc chưa lưu.")
        return 0

    xong = sum(1 for s in cp.dag_state.values() if s == "ok")
    print(f"Nodes: {xong}/{len(cp.dag_state)}")
    print(f"Commits: {len(cp.commits)}")
    print(f"Blockers: {len(cp.blockers)}")
    print(f"Findings: {len(cp.findings)}")
    if cp.next_actions:
        print("\nBước tiếp theo:")
        for b in cp.next_actions:
            print(f"  - {b}")
    return 0


def _in_workers(a) -> int:
    reg = default_registry(probe=True)
    for hang in reg.snapshot():
        print(f"{hang['worker_id']:<12} provider={hang['provider']:<12} "
             f"health={hang['health']:<12} "
             f"success_rate={hang['success_rate']} "
             f"in_flight={hang['in_flight']} "
             f"circuit_opens={hang.get('circuit_opens', 0)}")
    return 0


def _in_task(a) -> int:
    cp = cp_mod.doc(Path(a.checkpoint) if a.checkpoint else None)
    if cp is None:
        print("Chưa có checkpoint nào.")
        return 1
    if a.node_id not in cp.dag_state:
        print(f"Không có nút {a.node_id!r} trong checkpoint gần nhất.")
        return 1
    print(f"{a.node_id}: {cp.dag_state[a.node_id]}")
    if a.node_id in cp.tests:
        print(f"  tests: {cp.tests[a.node_id]}")
    return 0


def _in_resume(a) -> int:
    cp = cp_mod.doc(Path(a.checkpoint) if a.checkpoint else None)
    if cp is None:
        print("Chưa có checkpoint nào — không có gì để resume.")
        return 0
    con_lai = cp.con_lai
    if not con_lai:
        print("Mọi nút trong checkpoint gần nhất đều đã 'ok' — không cần resume.")
        return 0
    print(f"Còn {len(con_lai)} nút cần resume: {', '.join(con_lai)}")
    print("Gọi Scheduler.run(dag, already_done=<kết quả các nút đã 'ok'>) "
         "để chỉ chạy lại các nút này — xem checkpoint.py/scheduler.py.")
    return 0


def _in_doctor(a) -> int:
    van_de = []
    reg = default_registry(probe=True)
    for hang in reg.snapshot():
        if hang["worker_id"] == "CLAUDE_LEAD":
            continue
        if hang["health"] == "unavailable":
            van_de.append(f"{hang['worker_id']}: UNAVAILABLE")

    goc_router = Path.cwd() / ".router"
    if not goc_router.is_dir():
        van_de.append(".router/ chưa tồn tại — chạy `router_init.py <kho>` trước.")

    print("ROUTER DOCTOR\n")
    if not van_de:
        print("Không có vấn đề nào phát hiện được (chỉ kiểm được thứ QUAN SÁT "
             "ĐƯỢC cục bộ — không thay cho một lượt chạy thật).")
        return 0
    for v in van_de:
        print(f"  VẤN ĐỀ: {v}")
    return 1


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(prog="router", description=__doc__)
    ap.add_argument("--checkpoint", default="",
                    help="đường dẫn checkpoint khác mặc định "
                         "(.router/checkpoints/latest.json)")
    sub = ap.add_subparsers(dest="lenh", required=True)
    sub.add_parser("status")
    sub.add_parser("workers")
    tp = sub.add_parser("task")
    tp.add_argument("node_id")
    sub.add_parser("resume")
    sub.add_parser("doctor")
    a = ap.parse_args(argv)

    return {
        "status": _in_trang_thai, "workers": _in_workers,
        "task": _in_task, "resume": _in_resume, "doctor": _in_doctor,
    }[a.lenh](a)


if __name__ == "__main__":
    sys.exit(main())
