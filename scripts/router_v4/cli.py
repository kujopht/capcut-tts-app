"""Bảng điều khiển Router V4 — mission #17.

    python -m scripts.router_v4.cli status
    python -m scripts.router_v4.cli workers
    python -m scripts.router_v4.cli models
    python -m scripts.router_v4.cli pools
    python -m scripts.router_v4.cli missions
    python -m scripts.router_v4.cli explain <task_id> --dag plan.json
    python -m scripts.router_v4.cli drain <runtime_id>
    python -m scripts.router_v4.cli resume <runtime_id>
    python -m scripts.router_v4.cli request --need '<json>'

Dùng được từ Warp, nhưng KHÔNG phụ thuộc Warp (mission #18): đây là một
chương trình dòng lệnh thường, đọc/ghi tệp trạng thái trong kho.

KHÔNG IN BÍ MẬT. Bảng chỉ hiện `auth_profile` — một NHÃN CHỈ CHỖ ("hồ sơ
Windows nào giữ phiên"), không bao giờ token/cookie/credential.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v4 import fabric_config as FC
from scripts.router_v4.capabilities import Priority, Reasoning
from scripts.router_v4.contract import TaskContract
from scripts.router_v4.mission import plan as lap_ke_hoach
from scripts.router_v4.orchestrator import Need, RouterV4
from scripts.router_v4.runtime import RuntimeStatus


def _rv4(a) -> RouterV4:
    return RouterV4(root=Path(a.root) if a.root else Path.cwd(),
                    probe=not getattr(a, "no_probe", False))


def _bang_runtime(snap: Dict) -> None:
    rs = snap["runtimes"]
    rong = max([len(r["runtime_id"]) for r in rs] + [10])
    print(f"{'RUNTIME':<{rong}}  {'TRẠNG THÁI':<11} {'PROVIDER':<12} "
          f"{'TÀI KHOẢN':<20} {'ĐỒNG THỜI':<9} VIỆC / GHI CHÚ")
    for r in rs:
        tt = r["status"]
        viec = ",".join(r["running_tasks"]) if r["running_tasks"] else ""
        phu = viec
        if tt == "OFFLINE" and r["needs_provisioning"]:
            phu = r["needs_provisioning"][:60]
        elif tt == "OFFLINE" and r["health_detail"]:
            phu = r["health_detail"][:60]
        elif tt == "COOLDOWN":
            phu = ("drained" if r["drained"] else
                   f"cooldown tới {time.strftime('%H:%M:%S', time.localtime(r['cooldown_until'] or 0))}")
        elif not phu and r["completed"] + r["failed"]:
            phu = (f"xong {r['completed']} hỏng {r['failed']} "
                   f"tin cậy {r['success_rate']:.2f}")
        print(f"{r['runtime_id']:<{rong}}  {tt:<11} {r['provider']:<12} "
              f"{r['account_id']:<20} {r['in_flight']}/{r['concurrency']:<7} {phu}")
    print(f"\nTÀI KHOẢN THẬT (đã cấp phát): "
          + ", ".join(f"{k}={v}" for k, v in snap["accounts"].items())
          + f"   |   placement khả dụng: {len(snap['placements'])}")


def _lenh_status(a) -> int:
    rv = _rv4(a)
    st = rv.status()
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
        return 0
    print("ROUTER V4 — KẾT CẤU THỰC THI\n")
    _bang_runtime(st["fabric"])

    print("\nBỂ QUOTA (chỉ những bể của tài khoản đã cấp phát):")
    da_cap = {r["account_id"] for r in st["fabric"]["runtimes"]
              if r["status"] != "OFFLINE"}
    for p in st["fabric"]["pools"]:
        if p["account_id"] not in da_cap:
            continue
        print(f"  {p['pool_id']:<40} sức khoẻ={p['health']:.2f} "
              f"nguồn={p['source']:<9} đã dùng trong cửa sổ={p['used_in_window']}"
              f"  models={len(p['member_models'])}")

    leases = st["leases"]
    if leases:
        print("\nLEASE ĐANG GIỮ:")
        for l in leases:
            con = max(0, int(l["expires_at"] - time.time()))
            print(f"  {l['runtime_id']:<12} task={l['task_id'] or '-':<24} "
                  f"còn {con}s  chủ={l['owner_id']}")

    if st["leaderboard"]:
        print("\nBENCHMARK (đo thật, không phải tiên nghiệm cấu hình):")
        for r in st["leaderboard"][:8]:
            print(f"  {r['model_id']:<28} chất lượng={r['quality']:.2f} "
                  f"thành công={r['success_rate']:.2f} n={r['samples']} "
                  f"({r['scope']})  {r['avg_wall_seconds']}s")
    else:
        print("\nBENCHMARK: chưa đủ mẫu — bộ lập lịch đang dùng tiên nghiệm "
              "trong config/fabric.json.")

    if st["decisions"]:
        print("\nQUYẾT ĐỊNH GẦN ĐÂY:")
        for tid, d in list(st["decisions"].items())[-6:]:
            print(f"  {tid:<24} -> {d['selected'] or '(không có)':<32} "
                  f"({d['eligible_count']} ứng viên)")
    return 0


def _lenh_workers(a) -> int:
    rv = _rv4(a)
    snap = rv.fabric.snapshot()
    if a.json:
        print(json.dumps(snap["runtimes"], ensure_ascii=False, indent=2))
        return 0
    _bang_runtime(snap)
    return 0


def _lenh_models(a) -> int:
    rv = _rv4(a)
    snap = rv.fabric.snapshot()
    if a.json:
        print(json.dumps(snap["models"], ensure_ascii=False, indent=2))
        return 0
    print(f"{'MODEL':<28} {'HỌ':<10} {'PROVIDER':<12} {'SUY LUẬN':<9} "
          f"{'BỂ QUOTA':<26} NĂNG LỰC")
    for m in snap["models"]:
        do = sum(1 for v in m["capability_source"].values() if v == "probed")
        print(f"{m['model_id']:<28} {m['model_family']:<10} {m['provider']:<12} "
              f"{m['reasoning']:<9} {m['quota_pool']:<26} "
              f"{','.join(m['capabilities'])}")
        print(f"{'':<28} bằng chứng: {do}/{len(m['capabilities'])} năng lực ĐÃ ĐO"
              + (f"  — {m['notes'][:70]}" if m["notes"] else ""))
    return 0


def _lenh_pools(a) -> int:
    rv = _rv4(a)
    snap = rv.fabric.snapshot()
    if a.json:
        print(json.dumps(snap["pools"], ensure_ascii=False, indent=2))
        return 0
    print(f"{'BỂ':<44} {'TÀI KHOẢN':<20} {'SỨC KHOẺ':<9} {'NGUỒN':<10} DÙNG")
    for p in snap["pools"]:
        print(f"{p['pool_id']:<44} {p['account_id']:<20} {p['health']:<9.2f} "
              f"{p['source']:<10} {p['used_in_window']}")
    print("\nGhi chú: `nguồn=declared` nghĩa là số dư lấy từ UI/tài liệu nhà "
          "cung cấp và CHƯA đo được bằng máy — bộ lập lịch chiết khấu nó theo "
          "độ tin cậy thay vì tin tuyệt đối.")
    return 0


def _lenh_explain(a) -> int:
    rv = _rv4(a)
    if a.dag:
        d = json.loads(Path(a.dag).read_text(encoding="utf-8"))
        kh = lap_ke_hoach(d.get("contracts") or d.get("tasks") or d)
        if a.task_id not in kh.dag:
            print(f"Không có việc {a.task_id!r} trong kế hoạch.")
            return 1
        c = kh.dag.contract(a.task_id)
        from scripts.router_v4.scheduler import Demand
        qd = rv.scheduler.decide(
            c, demand=Demand.from_contracts(kh.dag.pending_contracts(())))
        print(qd.explain())
        return 0 if qd.selected else 1
    print(rv.explain(a.task_id))
    return 0


def _lenh_missions(a) -> int:
    goc = Path(a.root) if a.root else Path.cwd()
    p = goc / ".router" / "v4" / "missions.jsonl"
    if not p.exists():
        print("Chưa có mission nào được ghi.")
        return 0
    for dong in p.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
        try:
            d = json.loads(dong)
        except json.JSONDecodeError:
            continue
        t = time.strftime("%m-%d %H:%M", time.localtime(d.get("ts", 0)))
        print(f"{t}  {d.get('mission_id','?'):<16} {d.get('status','?'):<8} "
              f"{d.get('ok',0)}/{d.get('total',0)} việc  "
              f"{d.get('wall_seconds',0)}s  {d.get('note','')[:50]}")
    return 0


def _lenh_drain(a) -> int:
    print(json.dumps(_rv4(a).drain(a.runtime_id), ensure_ascii=False, indent=2))
    return 0


def _lenh_resume(a) -> int:
    print(json.dumps(_rv4(a).resume(a.runtime_id), ensure_ascii=False, indent=2))
    return 0


def _lenh_request(a) -> int:
    """Yêu cầu NĂNG LỰC, không phải tài khoản — đúng cách Claude lead gọi."""
    rv = _rv4(a)
    tho = json.loads(a.need) if a.need else json.loads(
        Path(a.need_file).read_text(encoding="utf-8"))
    ds = tho if isinstance(tho, list) else [tho]
    needs = []
    for d in ds:
        d = dict(d)
        needs.append(Need(
            label=str(d.pop("label", "(không tên)")),
            count=int(d.pop("count", 1)),
            reasoning_level=Reasoning(str(d.pop("reasoning_level", "medium"))),
            latency_priority=Priority(str(d.pop("latency_priority", "balanced"))),
            quality_priority=Priority(str(d.pop("quality_priority", "balanced"))),
            exclude_families=tuple(d.pop("exclude_families", ())),
            **{k: bool(v) for k, v in d.items()}))
    cap = rv.request(needs)
    if a.json:
        print(json.dumps([x.to_dict() for x in cap], ensure_ascii=False, indent=2))
        return 0
    for x in cap:
        print(f"\n{x.need.label}  (xin {x.need.count})")
        for p in x.placements:
            m = rv.fabric.model(p.model_id)
            print(f"   CẤP  {p.key:<40} họ={m.model_family}")
        if x.shortfall:
            print(f"   THIẾU {x.shortfall} — lý do cuối: "
                  f"{x.decisions[-1].reason[:160]}")
    return 0 if all(x.shortfall == 0 for x in cap) else 2


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(prog="router", description=__doc__)
    ap.add_argument("--root", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-probe", action="store_true",
                    help="bỏ dò sức khoẻ (nhanh hơn, kém chính xác hơn)")
    sub = ap.add_subparsers(dest="lenh", required=True)

    sub.add_parser("status")
    sub.add_parser("workers")
    sub.add_parser("models")
    sub.add_parser("pools")
    sub.add_parser("missions")
    p = sub.add_parser("explain")
    p.add_argument("task_id"); p.add_argument("--dag", default="")
    p = sub.add_parser("drain"); p.add_argument("runtime_id")
    p = sub.add_parser("resume"); p.add_argument("runtime_id")
    p = sub.add_parser("request")
    p.add_argument("--need", default=""); p.add_argument("--need-file", default="")

    a = ap.parse_args(argv)
    return {
        "status": _lenh_status, "workers": _lenh_workers, "models": _lenh_models,
        "pools": _lenh_pools, "missions": _lenh_missions,
        "explain": _lenh_explain, "drain": _lenh_drain, "resume": _lenh_resume,
        "request": _lenh_request,
    }[a.lenh](a)


if __name__ == "__main__":
    sys.exit(main())
