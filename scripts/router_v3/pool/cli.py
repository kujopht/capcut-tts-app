"""Một lệnh, một bảng — Bể worker tự trị, Phase 9.

Mission #13 đòi ĐÚNG một cái nhìn:

    AG01 READY
    AG02 BUSY job-...
    AG03 QUOTA_COOLDOWN
    ...
    OpenCode01 READY
    Codex01 READY/OFFLINE

cộng các nút DAG đang chạy. `python -m scripts.router_v3.pool.cli status`
in đúng thứ đó.

Đây cũng là ranh giới CLI mà bộ điều phối Claude gọi khi không muốn nhúng
Python: mọi động từ của `orchestrator.py` đều có một lệnh con, và `--json`
cho đầu ra đọc được bằng máy.

KHÔNG in bí mật: bảng chỉ hiện `auth_realm` (nhãn chỉ chỗ), không bao giờ
token/cookie. Xem `identity.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.pool import daemon as daemon_mod
from scripts.router_v3.pool import identity as id_mod
from scripts.router_v3.pool.orchestrator import Orchestrator
from scripts.router_v3.pool.runner import dict_sang_nut
from scripts.router_v3.pool.store import PoolStore

_MAU_TRANG_THAI = {
    "READY": "READY", "BUSY": "BUSY", "QUOTA_COOLDOWN": "QUOTA_COOLDOWN",
    "OFFLINE": "OFFLINE", "FAILED": "FAILED",
}


def _dieu_phoi(a) -> Orchestrator:
    goc = Path(a.root) if a.root else Path.cwd()
    return Orchestrator(root=goc, inline=bool(getattr(a, "inline", False)),
                        probe_health=not getattr(a, "no_probe", False))


def _in_bang_worker(hang_ds: List[Dict], *, accounts: Dict[str, int]) -> None:
    rong = max([len(h["worker_id"]) for h in hang_ds] + [10])
    for h in hang_ds:
        tt = _MAU_TRANG_THAI.get(h["state"], h["state"])
        phu = ""
        if h["state"] == "BUSY" and h.get("active_job"):
            phu = f" {h['active_job']}"
        elif h["state"] == "QUOTA_COOLDOWN" and h.get("cooldown_until"):
            con = max(0, int(float(h["cooldown_until"]) - time.time()))
            phu = f" còn {con}s"
        elif h["state"] == "OFFLINE" and h.get("detail"):
            phu = f" — {str(h['detail'])[:70]}"
        nhan = "" if h.get("account_slot", 1) else f" (làn của {h.get('lane_of')})"
        model = f"  {h['model']}" if h.get("model") else ""
        print(f"{h['worker_id']:<{rong}}  {tt:<15}{phu}{nhan}{model}")
    tong = sum(accounts.values())
    print(f"\nTÀI KHOẢN THẬT (không tính làn): {tong} — "
          + ", ".join(f"{k}={v}" for k, v in sorted(accounts.items())))


def _lenh_status(a) -> int:
    d = _dieu_phoi(a)
    st = d.status(a.run_id)
    if a.json:
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
        return 0
    print("BỂ WORKER — TRẠNG THÁI\n")
    _in_bang_worker(st["workers"], accounts=st["accounts"])
    pid = daemon_mod.dang_chay(Path(a.root) if a.root else Path.cwd())
    print(f"\ndaemon: {'ĐANG CHẠY pid=' + str(pid) if pid else 'KHÔNG chạy'}")
    if not st["run_id"]:
        print("\nChưa có lượt chạy nào.")
        return 0
    print(f"\nLƯỢT CHẠY {st['run_id']}  "
          + "  ".join(f"{k}={v}" for k, v in sorted(st["counts"].items())))
    dang = [j for j in st["jobs"] if j["status"] == "running"]
    if dang:
        print("\nNÚT ĐANG CHẠY:")
        for j in dang:
            print(f"  {j['node_id']:<22} {j['worker_id']:<12} "
                  f"lượt {j['attempt']}/{j['max_attempts']}  {j['seconds']}s")
    khac = [j for j in st["jobs"] if j["status"] != "running"]
    if khac:
        print("\nCÁC NÚT KHÁC:")
        for j in khac:
            kd = j.get("validation_passed")
            nhan_kd = "" if kd is None else ("  [kiểm định ĐẠT]" if kd
                                             else "  [kiểm định HỎNG]")
            print(f"  {j['node_id']:<22} {j['status']:<10} "
                  f"{j['worker_id'] or '-':<12} {j['seconds']}s{nhan_kd}")
            if j["summary"]:
                print(f"      {j['summary'][:100]}")
    return 0


def _lenh_workers(a) -> int:
    d = _dieu_phoi(a)
    if a.json:
        print(json.dumps({"workers": d.store.workers(),
                          "accounts": id_mod.dem_tai_khoan(d.identities)},
                         ensure_ascii=False, indent=2, default=str))
        return 0
    _in_bang_worker(d.store.workers(),
                    accounts=id_mod.dem_tai_khoan(d.identities))
    return 0


def _lenh_plan(a) -> int:
    d = _dieu_phoi(a)
    nodes = json.loads(Path(a.dag).read_text(encoding="utf-8"))
    kh = d.plan(nodes.get("nodes") if isinstance(nodes, dict) else nodes)
    print(json.dumps(kh.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _lenh_dispatch(a) -> int:
    d = _dieu_phoi(a)
    nodes = json.loads(Path(a.dag).read_text(encoding="utf-8"))
    kh = d.plan(nodes.get("nodes") if isinstance(nodes, dict) else nodes)
    run_id = d.dispatch_many(kh, note=a.note)
    print(json.dumps({"run_id": run_id, "nodes": [n.id for n in kh.dag.nodes()],
                      "waves": kh.waves,
                      "critical_seconds": kh.critical_seconds},
                     ensure_ascii=False, indent=2))
    return 0


def _lenh_wait(a) -> int:
    d = _dieu_phoi(a)
    rid = a.run_id or d.store.run_gan_nhat() or ""
    if not rid:
        print("không có lượt chạy nào")
        return 1
    if a.any:
        j = d.wait_any(rid, timeout=a.timeout)
        print(json.dumps(d._tom_tat_job(j) if j else {"timeout": True},
                         ensure_ascii=False, indent=2))
        return 0 if j else 2
    jobs = d.wait_all(rid, timeout=a.timeout)
    print(json.dumps([d._tom_tat_job(j) for j in jobs],
                     ensure_ascii=False, indent=2))
    return 0 if all(j.status == "ok" for j in jobs) else 1


def _lenh_result(a) -> int:
    d = _dieu_phoi(a)
    r = d.result(a.job_id, run_id=a.run_id or (d.store.run_gan_nhat() or ""),
                 node_id=a.node_id)
    if r is None:
        print("không tìm thấy")
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0


def _lenh_cancel(a) -> int:
    print(json.dumps(_dieu_phoi(a).cancel(a.job_id), ensure_ascii=False,
                     indent=2))
    return 0


def _lenh_retry(a) -> int:
    print(json.dumps(_dieu_phoi(a).retry(a.job_id), ensure_ascii=False,
                     indent=2))
    return 0


def _lenh_reassign(a) -> int:
    print(json.dumps(_dieu_phoi(a).reassign(a.job_id, worker_id=a.worker_id),
                     ensure_ascii=False, indent=2))
    return 0


def _lenh_events(a) -> int:
    st = PoolStore(root=Path(a.root) if a.root else Path.cwd())
    for e in reversed(st.su_kien(a.run_id, limit=a.limit)):
        t = time.strftime("%H:%M:%S", time.localtime(e["ts"]))
        print(f"{t}  {e['kind']:<18} {e['job_id'] or e['run_id']:<28} "
              f"{e['detail'][:90]}")
    return 0


def _lenh_provision(a) -> int:
    """In đúng việc phải làm để mở thêm một khe danh tính cố định."""
    ds = id_mod.nap(root=Path(a.root) if a.root else Path.cwd())
    chua = [i for i in ds if not i.provisioned]
    if not chua:
        print("Mọi khe đã cấp phát.")
        return 0
    print("KHE CHƯA CẤP PHÁT — mỗi khe cần một phiên xác thực RIÊNG.")
    print("KHÔNG dùng công cụ đổi tài khoản: sao chép blob credential giữa")
    print("các danh tính bị cấm và bị chặn ở `identity.py`.\n")
    for i in chua:
        print(f"  {i.worker_id}  (realm dự kiến: {i.auth_realm})")
        print(f"     {i.needs_provisioning}\n")
    return 0


def main(argv=None) -> int:
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(prog="pool", description=__doc__)
    ap.add_argument("--root", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inline", action="store_true",
                    help="tự chạy việc trong chính tiến trình này thay vì "
                         "dựa vào daemon (dùng cho lượt ngắn/kiểm thử)")
    ap.add_argument("--no-probe", action="store_true",
                    help="bỏ qua dò sức khoẻ (nhanh hơn, kém chính xác hơn)")
    sub = ap.add_subparsers(dest="lenh", required=True)

    s = sub.add_parser("status"); s.add_argument("--run-id", default="")
    sub.add_parser("workers")
    sub.add_parser("provision")
    p = sub.add_parser("plan"); p.add_argument("dag")
    p = sub.add_parser("dispatch")
    p.add_argument("dag"); p.add_argument("--note", default="")
    p = sub.add_parser("wait")
    p.add_argument("--run-id", default=""); p.add_argument("--any",
                                                           action="store_true")
    p.add_argument("--timeout", type=float, default=1800.0)
    p = sub.add_parser("result")
    p.add_argument("--job-id", default=""); p.add_argument("--run-id", default="")
    p.add_argument("--node-id", default="")
    p = sub.add_parser("cancel"); p.add_argument("job_id")
    p = sub.add_parser("retry"); p.add_argument("job_id")
    p = sub.add_parser("reassign")
    p.add_argument("job_id"); p.add_argument("--worker-id", default="")
    p = sub.add_parser("events")
    p.add_argument("--run-id", default=""); p.add_argument("--limit", type=int,
                                                           default=40)
    a = ap.parse_args(argv)

    return {
        "status": _lenh_status, "workers": _lenh_workers, "plan": _lenh_plan,
        "dispatch": _lenh_dispatch, "wait": _lenh_wait, "result": _lenh_result,
        "cancel": _lenh_cancel, "retry": _lenh_retry,
        "reassign": _lenh_reassign, "events": _lenh_events,
        "provision": _lenh_provision,
    }[a.lenh](a)


if __name__ == "__main__":
    sys.exit(main())
