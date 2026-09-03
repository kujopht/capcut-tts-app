"""Control Room có chiếu ĐÚNG trạng thái runtime THẬT không? — bằng chứng.

Yêu cầu hợp nhất #4: "AG01..AG08 phải hiện ra từ WorkerRegistry/runtime
state THẬT. Không đóng cứng worker online giả."

Script này chứng minh điều đó bằng cách so **hai nguồn độc lập**:

    Fabric V4  (scripts/router_v4/fabric_config.nap → dò sức khoẻ thật)
    Control Room snapshot (state_reader.StateReader, đường SẢN XUẤT)

Nếu Control Room đóng cứng bất cứ thứ gì, hai bên sẽ lệch. Chỉ đọc, không
phá huỷ, không chạm production.

    python scripts/control_room_projection_proof.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v3.control_room.state_reader import StateReader
from scripts.router_v4 import fabric_config as FC
from scripts.router_v4.antigravity_launcher import ACC_CUA_RUNTIME


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else _ROOT

    print("=" * 74)
    print("BANG CHUNG: Control Room chieu tu RUNTIME THAT (khong hardcode)")
    print("=" * 74)

    # Nguon 1: fabric truc tiep
    fab, _, _ = FC.nap(root=root, probe=True)
    fab_map = {r.runtime_id: r.trang_thai_hien_tai().value
               for r in fab.runtimes.values()}

    # Nguon 2: Control Room duong SAN XUAT (khong tiem store)
    sr = StateReader(root=root)
    snap = sr.snapshot()
    cr_map = {w.id: w.state.value for w in snap.workers}

    print(f"\nnguon Control Room : {snap.worker_source!r}")
    print(f"loi doc trang thai : {snap.errors or 'khong'}")
    print(f"runtime tu fabric  : {len(fab_map)}")
    print(f"worker o Control Room: {len(cr_map)}\n")

    # Control Room dung ten trang thai rieng (IDLE/BUSY/COOLDOWN/OFFLINE/
    # DEGRADED); anh xa tu ten cua fabric de so duoc.
    TUONG_DUONG = {"IDLE": "IDLE", "BUSY": "BUSY", "COOLDOWN": "COOLDOWN",
                   "OFFLINE": "OFFLINE", "DEGRADED": "DEGRADED",
                   "STARTING": "IDLE"}

    lech = []
    print(f"{'RUNTIME':<14}{'FABRIC':<12}{'CONTROL ROOM':<14}KHOP?")
    for rid in sorted(fab_map):
        f_st = fab_map[rid]
        c_st = cr_map.get(rid, "(THIEU)")
        khop = TUONG_DUONG.get(f_st, f_st) == c_st
        if not khop:
            lech.append((rid, f_st, c_st))
        print(f"{rid:<14}{f_st:<12}{c_st:<14}{'OK' if khop else 'LECH'}")

    # Worker o Control Room ma KHONG co trong fabric = hardcode gia.
    gia = sorted(set(cr_map) - set(fab_map))

    ag_cr = sorted(r for r in cr_map if r in ACC_CUA_RUNTIME)
    ag_online = sorted(r for r in ag_cr if cr_map[r] != "OFFLINE")

    print(f"\nkhe AG hien o Control Room : {len(ag_cr)}/8  {ag_cr}")
    print(f"khe AG KHONG offline       : {len(ag_online)}  {ag_online}")
    print(f"worker KHONG co trong fabric (hardcode gia): {gia or 'KHONG CO'}")
    print(f"trang thai lech            : {lech or 'khong'}")

    dat = (snap.worker_source == "fabric_v4" and not gia and not lech
           and len(ag_cr) == 8)
    print("\n" + "=" * 74)
    print(f"KET LUAN: {'PASS' if dat else 'CHUA DAT'}")
    if dat:
        print("  Control Room chieu 1:1 tu fabric V4; khong co worker gia;")
        print(f"  ca 8 khe AG01..AG08 hien ra tu trang thai runtime that.")
    print("=" * 74)

    if a.out:
        Path(a.out).write_text(json.dumps(
            {"worker_source": snap.worker_source, "errors": snap.errors,
             "fabric": fab_map, "control_room": cr_map,
             "ag_slots_shown": ag_cr, "ag_not_offline": ag_online,
             "fake_workers": gia, "mismatches": lech, "pass": dat},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"bao cao: {a.out}")
    return 0 if dat else 1


if __name__ == "__main__":
    sys.exit(main())
