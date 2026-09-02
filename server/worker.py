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
  - `main.drive_chapter_imports()` — MOT chu ky dieu phoi cua cac lo nhap chuong
    hang loat. Cung khong sao chep gi: no goi lai chinh than cua
    `POST /api/chapters` va `POST /api/jobs`. O DAY vi day la ngu canh nen duy
    nhat song qua restart cua backend, va mot lo 500 chuong can dung dieu do.
    Khoi `try` RIENG, khong dinh gi vao chu ky poll / nhip / lease cua job TTS.

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
from typing import Any, Dict, Optional

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


def _ep_utf8() -> None:
    """
    Ep stdout/stderr ve UTF-8.

    Console Windows mac dinh la cp1252. Mot dong log co dau tieng Viet se nem
    `UnicodeEncodeError` va lam CHET worker — da gap that: thong bao
    "FAS_ENV không khớp" lam tien trinh sap ngay truoc khi kip in ly do.

    `errors="replace"` de mot ky tu la khong bao gio quan trong hon viec worker
    con song.
    """
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ep_utf8()


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


def chay(doi_moi_truong: Optional[str] = None) -> int:
    settings = get_settings()
    settings.validate()          # FAIL FAST y het web

    # CHONG TRO NHAM TAI NGUYEN.
    #
    # `server/config.py` mac dinh nap `server/.env` — file cua may lap trinh
    # vien, tro vao tai nguyen DEV. Chay worker ma quen `FAS_ENV_FILE` thi no
    # lang le xu ly job cua dev bang credential dev. Khong co gi bao loi ca.
    #
    # `--require-env staging` bien im lang do thanh mot lan dung han: file dev
    # ghi `FAS_ENV=development`, khong khop, worker thoat ngay.
    if doi_moi_truong and settings.environment.lower() != doi_moi_truong.lower():
        _ghi("dung_vi_sai_moi_truong",
             mong_doi=doi_moi_truong, thuc_te=settings.environment,
             thong_diep=("FAS_ENV không khớp. Nhiều khả năng đang nạp nhầm file "
                         "cấu hình — kiểm tra FAS_ENV_FILE."))
        return 2

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

        # NHAP CHUONG HANG LOAT — bo dieu phoi cua lo nhap (xem
        # `server/bulk_import_service.py`).
        #
        # O DAY chu khong o tien trinh web: mot lo 500 chuong khong nam trong
        # mot vong request/response, va yeu cau "tiep tuc duoc sau khi backend
        # restart" doi mot tien trinh nen SONG LAU — tien trinh nay.
        #
        # KHONG dong vao chu ky poll, nhip, hay lease cua khoi tren: mot khoi
        # `try` RIENG, khong ghi vao `bao_cao`, khong doi `_nhip`. Mot lo nhap
        # loi tuyet doi khong duoc lam mat recovery cua job TTS.
        try:
            nhap = api.drive_chapter_imports()
            # Chi ghi khi CO viec that. `{"nghi": 1}` (phanh nghi luc rong
            # viec, xem `main.IMPORT_IDLE_BACKOFF_SECONDS`) va mot chu ky khong
            # doi gi deu KHONG duoc ghi: mot dong log moi 3 giay noi rang khong
            # co gi xay ra la mot dong log khong ai doc duoc nua.
            if nhap.get("lo") and any(v for k, v in nhap.items() if k != "lo"):
                _ghi("nhap_chuong", **nhap)
        except Exception as exc:
            _ghi("loi_nhap_chuong", loai=type(exc).__name__)

        # DRIVE ARCHIVE RETRY — xem `server/scraper/raw_archive.py`. Cung
        # nguyen tac voi khoi nhap chuong o tren: khoi `try` RIENG, chi ghi
        # log khi CO viec that, mot lan Drive loi tuyet doi khong duoc lam
        # mat vong quet TTS ben canh. Duong nhanh khi hang doi rong chi la
        # mot lan kiem tra file ton tai — khong dang ke so voi chu ky 3s.
        try:
            tu_rclone = api.drain_archive_queue()
            if tu_rclone.get("da_thu"):
                _ghi("drive_archive_retry", **tu_rclone)
        except Exception as exc:
            _ghi("loi_drive_archive", loai=type(exc).__name__)

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


def _doc_tham_so(argv):
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m server.worker",
        description="Tien trinh worker TTS. Chay rieng, khong nam trong web.")
    p.add_argument("--check", action="store_true",
                   help="Doc tep nhip roi thoat. Dung lam healthcheck.")
    p.add_argument("--require-env", metavar="TEN",
                   help="Thoat neu FAS_ENV khac TEN. Chong chay nham vao tai "
                        "nguyen dev khi quen dat FAS_ENV_FILE.")
    return p.parse_args(argv)


if __name__ == "__main__":
    tham_so = _doc_tham_so(sys.argv[1:])
    if tham_so.check:
        sys.exit(kiem_tra())
    sys.exit(chay(tham_so.require_env))
