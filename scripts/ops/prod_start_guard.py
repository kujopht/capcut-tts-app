#!/usr/bin/env python3
"""Rao chan phia MAY DICH: co worker NGOAI dang phuc vu hang doi production
khong?

    prod_start_guard.py --env-file /etc/fanfic-audio/worker-prod.env

Thoat 0 = khong thay worker ngoai nao -> duoc phep bat.
Thoat 1 = CO worker ngoai giu lease con han -> TU CHOI bat.
Thoat 2 = khong ket luan duoc (loi cau hinh/mang) -> TU CHOI, fail closed.

VI SAO CAN, KHI DIEU PHOI DA KIEM GCE
-------------------------------------
`prod_cutover.py pha_canary` co kiem "GCE phai da dung" — nhung no chay
tren may DIEU HANH. Cong dieu hanh tren may AWS nhan verb tu mot hang doi
ma ben khong-dac-quyen ghi duoc, nen mot verb `start` co the toi ma khong
he di qua `pha_canary`. Neu luc do GCE con phuc vu, hai worker cung claim
MOT hang doi production — che do that bai nguy hiem nhat cua ca ke hoach.

Rao chan nay song tren chinh may AWS, nen khong bo qua duoc.

NO CHUNG MINH DUOC GI, VA KHONG CHUNG MINH DUOC GI
-------------------------------------------------
Cong nay **khong** cham GCE (co y: `fanfic_prod_admin.sh` khong bao gio
cham GCE). No suy ra tu DU LIEU CHUNG: mot job `running` co lease CON HAN
ma chu lease khong phai tien trinh tren may nay => co worker khac dang
song va dang lam viec.

Gioi han that, noi thang: khi hang doi RONG, khong co lease nao de doc,
nen cong nay khong phat hien duoc mot GCE dang chay nhung ranh. Doi lai,
khi hang doi rong thi hai worker cung khong the trung viec — khong co viec
nao de trung. Rui ro con lai la cua so giua "GCE ranh" va "job moi toi",
va do la cai ma rao chan trong `pha_canary` che.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))

from scripts.ops.cutover_target import CutoverRefused, nap_env_tu_tep  # noqa: E402


def pid_tren_may_nay(lease_owner: str) -> bool:
    """`WORKER_ID` co dang `<pid>-<hex>`. PID con song tren may nay?"""
    if not lease_owner or "-" not in lease_owner:
        return False
    pid = lease_owner.split("-", 1)[0]
    return pid.isdigit() and Path(f"/proc/{pid}").exists()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", required=True)
    a = ap.parse_args(argv)

    try:
        for k, v in nap_env_tu_tep(a.env_file).items():
            os.environ[k] = v
    except (CutoverRefused, OSError) as exc:
        print(f"  TU CHOI: khong nap duoc env: {exc}")
        return 2

    try:
        from server.config import load_settings
        from server.adapters import build_metadata_store
        from server.domain import JobStatus

        st = load_settings()
        st.validate()
        store = build_metadata_store(st)
        dang_chay = store.list_jobs_by_status(JobStatus.RUNNING)
    except Exception as exc:  # noqa: BLE001
        # Fail closed: khong doc duoc hang doi thi KHONG duoc bat.
        print(f"  TU CHOI: khong doc duoc hang doi: {type(exc).__name__}")
        return 2

    from datetime import datetime, timezone

    ngoai = []
    for j in dang_chay:
        chu = j.lease_owner or ""
        het = j.lease_expires_at
        con_han = False
        if het:
            try:
                t = datetime.fromisoformat(het.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                con_han = t > datetime.now(timezone.utc)
            except ValueError:
                con_han = False
        if con_han and chu and not pid_tren_may_nay(chu):
            ngoai.append((j.job_id, chu))

    print(f"  job running       : {len(dang_chay)}")
    print(f"  lease worker ngoai: {len(ngoai)}")
    if ngoai:
        for jid, chu in ngoai[:5]:
            print(f"    {jid}  lease_owner={chu}")
        print("  TU CHOI: co worker KHAC dang phuc vu hang doi production nay.")
        return 1
    print("  khong thay worker ngoai nao dang giu lease")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
