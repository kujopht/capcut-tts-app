"""Đo tốc độ thật của Router V3 — Phase 12.

Chạy CÙNG một DAG ở nhiều mức song song, dùng worker THẬT, và ghi lại thời
gian đo được. Không ước lượng, không ngoại suy.

    python -m scripts.router_v3.benchmark --levels 1,2,3,4

Vì sao dùng việc nhỏ và độc lập: mục đích là đo **chi phí điều phối và mức
song song thật sự đạt được**, không phải đo model thông minh tới đâu. Việc nhỏ
làm phần chi phí điều phối hiện rõ; việc lớn sẽ giấu nó đi.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import time
from typing import Dict, List, Optional

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.dag import TaskDag, TaskNode
from scripts.router_v3.registry import (ExecutionType, Health, WorkerRegistry,
                                        WorkerSpec)
from scripts.router_v3.scheduler import Scheduler

#: Sáu việc ĐỘC LẬP, kích thước tương đương. Yêu cầu trả JSON đúng hợp đồng
#: gói việc để `parse_result` đọc được — nếu không thì đang đo một thứ khác.
VIEC = [
    "Giai thich ngan gon (1-2 cau) khai niem: idempotency trong he thong phan tan.",
    "Giai thich ngan gon (1-2 cau) khai niem: dependency DAG trong lap lich cong viec.",
    "Giai thich ngan gon (1-2 cau) khai niem: SSRF va vi sao chan dia chi mang rieng.",
    "Giai thich ngan gon (1-2 cau) khai niem: ETag va conditional GET.",
    "Giai thich ngan gon (1-2 cau) khai niem: exactly-once logic tren at-least-once.",
    "Giai thich ngan gon (1-2 cau) khai niem: git worktree dung de co lap.",
]


def _dispatcher():
    spec = importlib.util.spec_from_file_location(
        "_disp_bench", _ROOT / "scripts" / "ai_router_dispatch.py")
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    return d


def build_dag(n: int) -> TaskDag:
    return TaskDag([
        TaskNode(id=f"B{i}", objective=VIEC[i % len(VIEC)],
                 required_capabilities=("recon",), estimated_seconds=6.0)
        for i in range(n)
    ])


def build_registry(slots: int) -> WorkerRegistry:
    """`slots` khe cùng trỏ vào phiên `agy` đã xác thực trên máy này.

    Đây là điểm QUAN TRỌNG và dễ hiểu nhầm: các khe này KHÔNG phải nhiều tài
    khoản. Chúng là các đường thực thi đồng thời trên CÙNG một client đã đăng
    nhập — thứ đã đo được là chạy song song thật. Nhiều tài khoản (AG02..AG08)
    là chuyện khác và cần người vận hành tự đăng nhập.
    """
    reg = WorkerRegistry()
    for i in range(slots):
        wid = f"AG01_s{i}"
        reg.register(WorkerSpec(
            worker_id=wid, provider_family="antigravity",
            execution_type=ExecutionType.LOCAL_CLI, pool="GEMINI_FLASH",
            capabilities=frozenset({"recon", "implement", "tests"}),
            max_concurrent=1))
        reg.set_health(wid, Health.HEALTHY)
    return reg


def make_executor(d, model: str):
    def chay(packet, worker):
        t0 = time.perf_counter()
        r = d.run_worker("GEMINI_FLASH", model, packet.render(), 300, None)
        return (r.get("output") or ""), time.perf_counter() - t0
    return chay


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", default="1,2,3,4")
    ap.add_argument("--tasks", type=int, default=6)
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)

    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    d = _dispatcher()
    model, cach = d.resolve_model("GEMINI_FLASH")
    if not model:
        print("Khong phan giai duoc model — bo qua benchmark.")
        return 2

    muc = [int(x) for x in a.levels.split(",") if x.strip()]
    print(f"Router V3 benchmark | model={model} ({cach}) | {a.tasks} viec doc lap\n")
    print(f"{'workers':>8} {'wall(s)':>9} {'worker(s)':>10} {'tang toc':>9} "
          f"{'ok':>6} {'dinh song song':>15}")
    print("-" * 64)

    ket: List[Dict] = []
    co_so: Optional[float] = None
    for n in muc:
        dag = build_dag(a.tasks)
        reg = build_registry(n)
        s = Scheduler(reg, make_executor(d, model), max_parallel=n,
                      base_sha="benchmark")
        bc = s.run(dag)
        ok = sum(1 for r in bc.results.values() if r.ok)
        if co_so is None:
            co_so = bc.wall_seconds
        hang = {
            "workers": n,
            "wall_seconds": bc.wall_seconds,
            "worker_seconds": round(bc.worker_seconds, 2),
            "speedup_vs_1_worker": round(co_so / bc.wall_seconds, 2)
            if bc.wall_seconds else 0.0,
            "ok": ok,
            "total": len(bc.results),
            "max_in_flight": bc.max_in_flight,
        }
        ket.append(hang)
        print(f"{n:>8} {bc.wall_seconds:>9.2f} {bc.worker_seconds:>10.2f} "
              f"{hang['speedup_vs_1_worker']:>8.2f}x {ok:>3}/{hang['total']:<2} "
              f"{bc.max_in_flight:>15}")

    print("\nGhi chu trung thuc:")
    print("  - `tang toc` so voi muc 1 worker DO DUOC trong chinh lan chay nay.")
    print("  - Cac khe deu tro vao MOT phien agy da xac thuc; day la do muc")
    print("    song song tren mot client, KHONG phai do nhieu tai khoan.")
    if any(h["ok"] < h["total"] for h in ket):
        print("  - CANH BAO: co viec that bai — cac con so khong so sanh duoc.")

    if a.json:
        pathlib.Path(a.json).write_text(
            json.dumps({"model": model, "tasks": a.tasks, "results": ket},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDa ghi {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
