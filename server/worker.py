"""
Tien trinh worker TTS — chay RIENG, khong nam trong tien trinh web.

    .venv/Scripts/python.exe -m server.worker

VI SAO TACH: o che do inline, job TTS chay trong thread nen cua tien trinh web.
Restart web la giet job dang chay giua chung; mot chuong dai giu thread song
hang chuc phut trong tien trinh phuc vu request; va khong the scale hai phan doc
lap. Recovery van cuu duoc job (da chung minh live), nhung "cuu duoc" khong phai
ly do de thiet ke nhu vay o staging.

KHONG SAO CHEP LOGIC. Worker nay chi la mot vong lap goi lai dung nhung ham ma
web van dung:

  - `main.recover_stale_jobs()` — quet job `pending` va `running` da mat worker,
    nhan bang `store.claim_job()` (transaction cua Appwrite), roi chay
    `main._run_job()` voi fencing token nhan duoc.
  - `main._run_job()` — tong hop, upload, tao track, ghi `completed`, moi lan ghi
    deu kem fence.

Nho vay claim nguyen tu, lease/heartbeat, fencing token, gioi han so lan thu va
tinh idempotent cua track/object deu la CUNG MOT ma nguon o ca hai che do.

NHIEU WORKER: chay bao nhieu ban cung duoc. Moi ban co `WORKER_ID` rieng, va
claim la compare-and-set that su (uniqueness cua `rowId` trong transaction), nen
mot job chi mot worker thang. Khong can khoa ngoai, khong can hang doi rieng.

DUNG SACH: SIGTERM/SIGINT lam worker ngung nhan job MOI, roi cho cac job dang
chay ket thuc trong `FAS_WORKER_GRACE_SECONDS`. Bi kill cuong che thi lease het
han va worker khac nhan lai — duong recovery da co, khong them gi moi.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from typing import Any, Dict

from server import main as api
from server.config import get_settings

#: Chu ky quet. Ngan hon `JOB_SWEEP_SECONDS` cua web vi day la viec DUY NHAT cua
#: tien trinh nay — job vua tao khong nen cho lau.
POLL_SECONDS = int(os.environ.get("FAS_WORKER_POLL_SECONDS", "3"))

#: Cho job dang chay bao lau khi duoc yeu cau dung.
GRACE_SECONDS = int(os.environ.get("FAS_WORKER_GRACE_SECONDS", "120"))

#: Tep bao "con song", cho healthcheck cua nen tang hosting doc. Worker khong mo
#: cong HTTP nao: no khong phuc vu request, mo cong chi de healthcheck la thu
#: bay khong can thiet.
HEARTBEAT_FILE = get_settings().var_dir / "worker" / "heartbeat.json"

_dung = threading.Event()


def _ghi(muc: str, **truong: Any) -> None:
    """
    Mot dong JSON moi su kien.

    KHONG BAO GIO ghi noi dung chuong, token hay khoa object day du vao day.
    `job_id` va `chapter_id` la dinh danh do he thong sinh, khong phai du lieu
    nguoi dung.
    """
    ban_ghi = {"luc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
               "worker": api.WORKER_ID, "muc": muc}
    ban_ghi.update(truong)
    print(json.dumps(ban_ghi, ensure_ascii=False), flush=True)


def _nhip(trang_thai: str, chu_ky: int, bao_cao: Dict[str, int] | None) -> None:
    """Cap nhat tep heartbeat. Loi ghi tep KHONG duoc lam worker chet."""
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_FILE.write_text(json.dumps({
            "worker_id": api.WORKER_ID,
            "pid": os.getpid(),
            "trang_thai": trang_thai,
            "chu_ky": chu_ky,
            "luc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "job_dang_chay": sorted(api._job_threads),
            "lan_quet_gan_nhat": bao_cao,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _so_job_dang_chay() -> int:
    with api._job_lock:
        return sum(1 for t in api._job_threads.values() if t.is_alive())


def _xin_dung(signum: int, _frame: Any) -> None:
    _ghi("nhan_tin_hieu_dung", tin_hieu=signum)
    _dung.set()


def chay() -> int:
    settings = get_settings()
    settings.validate()          # FAIL FAST y het web

    if settings.inline_worker:
        # Khong phai loi, nhung phai noi ro: web cung dang tu chay job, nen se co
        # hai ben cung quet. Claim nguyen tu khong cho hai ben cung lam mot job,
        # nhung day khong phai hinh dang mong muon o staging.
        _ghi("canh_bao",
             thong_diep="FAS_INLINE_WORKER dang BAT — web cung tu chay job. "
                        "O staging/production hay dat FAS_INLINE_WORKER=false.")

    # BAT BUOC, va phai o day. `main` mac dinh chi chay job khi
    # `inline_worker` bat; worker rieng thi doc dung bien do la `false`. Khong
    # bat tuong minh thi worker se NHAN job roi khong chay, va moi vong quet lai
    # dot them mot `attempts` cho den khi job `failed` oan.
    api.enable_job_execution()
    assert api.can_run_jobs(), "worker phai duoc phep chay job"

    _ghi("khoi_dong", pid=os.getpid(), che_do=settings.describe(),
         chu_ky_giay=POLL_SECONDS, an_han_dung_giay=GRACE_SECONDS,
         chay_job_duoc=api.can_run_jobs())

    for tin_hieu in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(tin_hieu, _xin_dung)
        except (ValueError, OSError):
            # Windows khong co du bo tin hieu; khong sao, kill cuong che van co
            # duong recovery lo.
            pass

    chu_ky = 0
    while not _dung.is_set():
        chu_ky += 1
        bao_cao = None
        try:
            # `pending_min_age_seconds=0`: khong co thread nao trong tien trinh
            # web dang lo job moi, nen nhan ngay thay vi cho het lease.
            bao_cao = api.recover_stale_jobs(pending_min_age_seconds=0)
            if bao_cao.get("chay_lai") or bao_cao.get("het_luot_thu"):
                _ghi("da_quet", **bao_cao)
        except Exception as exc:
            # Mot vong quet loi KHONG duoc lam worker chet — chet la mat recovery.
            _ghi("loi_quet", loai=type(exc).__name__)
        _nhip("dang_chay", chu_ky, bao_cao)
        _dung.wait(POLL_SECONDS)

    # -- dung sach ---------------------------------------------------------
    _ghi("dang_dung", job_dang_chay=_so_job_dang_chay())
    api._sweeper_stop.set()
    han = time.time() + GRACE_SECONDS
    while time.time() < han and _so_job_dang_chay() > 0:
        _nhip("dang_dung", chu_ky, None)
        time.sleep(1)

    con_lai = _so_job_dang_chay()
    _nhip("da_dung", chu_ky, None)
    if con_lai:
        # Khong gia vo la da xong. Job con lai se duoc worker khac nhan sau khi
        # lease het han — dung duong recovery da co.
        _ghi("dung_khi_con_job", con_lai=con_lai,
             thong_diep="job con lai se duoc nhan lai sau khi lease het han")
        return 1
    _ghi("da_dung_sach")
    return 0


#: Nhip cu hon bao nhieu giay thi coi la worker da treo.
STALE_SECONDS = int(os.environ.get("FAS_WORKER_STALE_SECONDS",
                                   str(POLL_SECONDS * 10 + 30)))


def kiem_tra() -> int:
    """
    `python -m server.worker --check` — healthcheck cho nen tang hosting.

    Doc tep nhip. Tra 0 khi nhip con moi, 1 khi cu hoac khong co. Khong mo cong,
    khong goi mang: worker khong phuc vu request nen mo cong HTTP chi de
    healthcheck la them mot thu co the hong ma khong duoc gi.
    """
    from datetime import datetime, timezone

    try:
        d = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"khong doc duoc nhip: {type(exc).__name__}", file=sys.stderr)
        return 1
    try:
        luc = datetime.strptime(d["luc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except Exception:
        print("nhip khong co moc thoi gian doc duoc", file=sys.stderr)
        return 1
    tuoi = (datetime.now(timezone.utc) - luc).total_seconds()
    print(json.dumps({"trang_thai": d.get("trang_thai"), "tuoi_nhip_giay": round(tuoi),
                      "nguong_giay": STALE_SECONDS,
                      "so_job_dang_chay": len(d.get("job_dang_chay") or [])},
                     ensure_ascii=False))
    return 0 if tuoi <= STALE_SECONDS else 1


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(kiem_tra())
    sys.exit(chay())
