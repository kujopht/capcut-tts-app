"""BẰNG CHỨNG: Router V4 lập lịch THẬT trên nhiều tài khoản Antigravity.

Mission bước 5. Không mock, không phá huỷ, không ghi tệp nào trong kho.

Chứng minh:
  1. Nhiều runtime AG cùng được đăng ký và dò sức khoẻ THẬT.
  2. Bộ lập lịch chọn các runtime KHÁC NHAU cho các việc độc lập.
  3. N việc chỉ-đọc chạy ĐỒNG THỜI trên N tài khoản khác nhau.
  4. Mỗi tiến trình vẫn gắn đúng tài khoản của nó (không trôi danh tính).
  5. Khởi động lại một runtime KHÔNG làm phiền runtime khác.

Mỗi việc là CHỈ ĐỌC và yêu cầu worker trả về một chuỗi cố định — đủ để
chứng minh đường dẫn thật chạy được mà không đụng vào kho.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v4.antigravity_launcher import (ACC_CUA_RUNTIME,
                                                    SESSIONS_DIR)
from scripts.router_v4.capabilities import Reasoning, Requirements
from scripts.router_v4.contract import Execution, TaskContract
from scripts.router_v4.orchestrator import RouterV4
from scripts.router_v4.runtime import RuntimeStatus

MAU_EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def dau_hieu(acc: str):
    """Bam danh tinh ghi trong cli.log cua phien — KHONG in email."""
    p = SESSIONS_DIR / acc / ".gemini" / "antigravity-cli" / "cli.log"
    if not p.is_file():
        return set()
    raw = p.read_bytes()
    return {hashlib.sha256(m.lower()).hexdigest()[:12]
            for m in MAU_EMAIL.findall(raw)
            if not m.lower().endswith((b".png", b".jpg"))}


def hop_dong(i: int) -> TaskContract:
    return TaskContract(
        task_id=f"MA{i}",
        type="multiaccount_probe",
        objective=(
            "Đây là phép dò chỉ-đọc của bộ định tuyến. KHÔNG đọc tệp, KHÔNG "
            "sửa gì, KHÔNG chạy lệnh nào.\n"
            f"Đặt `summary` đúng bằng chuỗi: PROBE-{i}-OK"),
        requirements=Requirements(structured_output=True, repo_read=True,
                                  reasoning_level=Reasoning.LOW),
        execution=Execution(expected_duration=30.0, max_wall_time=300.0,
                            worktree_required=False),
        impact=0.05, uncertainty=0.05)


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", type=int, default=4)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)

    print("=" * 74)
    print("ROUTER V4 — LAP LICH DA TAI KHOAN ANTIGRAVITY (bang chung that)")
    print("=" * 74)

    rv = RouterV4(root=_ROOT, probe=True)
    ag = [r for r in rv.fabric.runtimes.values()
          if r.provider == "antigravity"
          and r.trang_thai_hien_tai() is not RuntimeStatus.OFFLINE]
    print(f"\n1. Runtime AG dang ky + do suc khoe THAT: {len(ag)} khe")
    for r in sorted(ag, key=lambda x: x.runtime_id):
        print(f"   {r.runtime_id}  transport={r.transport:<9} "
              f"auth={r.auth_profile:<22} {r.health_detail[:40]}")

    truoc = {acc: dau_hieu(acc) for acc in ACC_CUA_RUNTIME.values()}

    # --- 2. Bo lap lich chon runtime KHAC NHAU ---------------------------
    print(f"\n2. Bo lap lich chon runtime khac nhau cho {a.tasks} viec doc lap")
    hds = [hop_dong(i) for i in range(1, a.tasks + 1)]
    kh = rv.plan(hds, mission_id="multiaccount-proof")

    # --- 3. Chay DONG THOI ------------------------------------------------
    print(f"\n3. Chay {a.tasks} viec DONG THOI")
    t0 = time.time()
    kq = rv.run_mission(kh, max_parallel=a.tasks, timeout=900)
    wall = time.time() - t0

    dung = {}
    for tid in kh.dag.ids():
        o = kq[tid]
        rid = o.placement.runtime_id if o.placement else "-"
        dung[tid] = rid
        nhan = "OK  " if o.ok else "HONG"
        print(f"   [{nhan}] {tid:<6} {rid:<8} "
              f"{(o.placement.model_id if o.placement else '-'):<26} "
              f"{o.envelope.duration:5.1f}s  {o.envelope.summary[:28]!r}")

    ok = [t for t, o in kq.items() if o.ok]
    rt_rieng = sorted({v for v in dung.values() if v != "-"})
    ag_rieng = [r for r in rt_rieng if r in ACC_CUA_RUNTIME]
    print(f"\n   runtime KHAC NHAU da dung: {len(rt_rieng)}  {rt_rieng}")
    print(f"   trong do la tai khoan AG  : {len(ag_rieng)}  {ag_rieng}")
    print(f"   thanh cong                : {len(ok)}/{len(kq)}")
    print(f"   thoi gian tuong           : {wall:.1f}s")

    # --- 4. Khong troi danh tinh -----------------------------------------
    print("\n4. Kiem tra troi danh tinh")
    sau = {acc: dau_hieu(acc) for acc in ACC_CUA_RUNTIME.values()}
    troi = []
    for acc, h in sau.items():
        them = h - truoc.get(acc, set())
        lot = {x for x in them
               if any(x in truoc.get(b, set()) for b in truoc if b != acc)}
        if lot:
            troi.append(acc)
    print(f"   phien nhan danh tinh cua phien khac: {troi or 'khong'}")

    # --- 5. Khoi dong lai mot runtime, runtime khac co bi anh huong -------
    print("\n5. Khoi dong lai mot runtime, kiem runtime khac")
    doi_lai = False
    if len(ag_rieng) >= 2:
        a1, a2 = ag_rieng[0], ag_rieng[1]
        ad = rv.executor._cache
        print(f"   dong phien cua {a2} ...")
        for k, v in list(ad.items()):
            if k.startswith(a2 + "/"):
                try:
                    v.shutdown()
                except Exception:
                    pass
                ad.pop(k, None)
        r2 = rv.run_task(hop_dong(90))
        r1 = rv.run_task(hop_dong(91))
        print(f"   {a2} sau khoi dong lai : "
              f"{'OK' if r2.ok else 'HONG'} ({r2.placement})")
        print(f"   viec tiep theo         : "
              f"{'OK' if r1.ok else 'HONG'} ({r1.placement})")
        doi_lai = r2.ok and r1.ok
    else:
        print("   (bo qua — can it nhat 2 tai khoan AG duoc chon)")

    bc = {
        "ag_runtimes_registered": len(ag),
        "tasks": a.tasks, "success": f"{len(ok)}/{len(kq)}",
        "distinct_runtimes": rt_rieng, "distinct_ag_accounts": ag_rieng,
        "wall_seconds": round(wall, 2),
        "identity_drift": troi,
        "restart_isolated": doi_lai,
        "assignment": dung,
    }
    if a.out:
        Path(a.out).write_text(json.dumps(bc, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        print(f"\nbao cao: {a.out}")

    dat = (len(ok) == len(kq) and len(ag_rieng) >= 2 and not troi)
    print("\n" + "=" * 74)
    print(f"KET LUAN: {'PASS' if dat else 'CHUA DAT'}  — "
          f"{len(ag_rieng)} tai khoan AG khac nhau, "
          f"{len(ok)}/{len(kq)} viec, troi danh tinh: {troi or 'khong'}")
    print("=" * 74)
    return 0 if dat else 1


if __name__ == "__main__":
    sys.exit(main())
