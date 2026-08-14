"""
Tien trinh worker DICH — chay RIENG, khong nam trong tien trinh web.

    .venv/Scripts/python.exe -m server.translation_worker

CUNG KIEN TRUC voi `server/worker.py` (TTS) nhung HOAN TOAN DOC LAP: bang
rieng (`translation_jobs`/`translation_job_claims`, khong dung
`tts_jobs`/`job_claims`), instance `TranslationService` rieng, khong import
gi tu `server/worker.py` hay nguoc lai.

VI SAO TACH: cung ly do voi TTS, cong them mot ly do rieng cho dich — provider
that (`DocuTranslateProvider`) goi mot LLM ngoai, co the mat toi 60 giay MOI
DOAN. Chay trong thread nen cua tien trinh web (che do inline) la chap nhan
duoc cho dev/mock (khong do tre), nhung o staging/production voi provider
that, mot chuong nhieu doan giu request handler ban hang phut — dung cai ma
worker rieng ton tai de tranh.

KHONG SAO CHEP LOGIC. Worker nay chi la mot vong lap goi lai dung nhung
phuong thuc cong khai cua `TranslationService`:

  - `translation_svc.recover_stale_jobs()` — quet job CHUA KET THUC da mat
    worker, nhan bang `store.claim_job()` (CAS that su), roi chay
    `translation_svc._run_job()` voi fencing token nhan duoc.

Claim nguyen tu, lease/heartbeat, fencing token, resume tu chuong con thieu
deu la CUNG MOT ma nguon o ca hai che do (inline trong web VA worker rieng).
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

from server.adapters import build_metadata_store
from server.config import get_settings
from server.translation_providers import build_provider
from server.translation_service import TranslationService
from server.translation_store import build_translation_store

#: Chu ky quet. Ngan hon `JOB_SWEEP_SECONDS` cua web vi day la viec DUY NHAT
#: cua tien trinh nay.
POLL_SECONDS = int(os.environ.get("FAS_TRANSLATION_WORKER_POLL_SECONDS", "3"))

#: Cho job dang chay bao lau khi duoc yeu cau dung.
GRACE_SECONDS = int(os.environ.get("FAS_TRANSLATION_WORKER_GRACE_SECONDS", "120"))

_dung = threading.Event()


def _ep_utf8() -> None:
    """Ep stdout/stderr ve UTF-8 — cung ly do voi `server/worker.py`: console
    Windows mac dinh cp1252 se lam worker chet ngay khi in tieng Viet co dau."""
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_ep_utf8()

#: Xay MOT LAN — settings/store/service dung xuyen suot vong doi tien trinh.
_settings = get_settings()
_novel_store = build_metadata_store(_settings)
_translation_store = build_translation_store(_settings)
_svc = TranslationService(
    _translation_store, _novel_store,
    provider=build_provider(_settings),
    # Khoi tao KHONG cho chay job — chi `chay()` duoi day, sau khi kiem tra
    # moi truong, moi goi `enable_job_execution()`. Cung ly do voi
    # `server/worker.py::api.enable_job_execution()`: mot AttributeError o
    # buoc kiem moi truong khong duoc vo tinh cho phep chay job truoc do.
    inline_worker=False,
)

HEARTBEAT_FILE = _settings.var_dir / "translation_worker" / "heartbeat.json"


def _ghi(muc: str, **truong: Any) -> None:
    """Mot dong JSON moi su kien. KHONG BAO GIO ghi noi dung truyen/tieu de
    chuong hay khoa API — chi id do he thong sinh."""
    ban_ghi = {"luc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
               "worker": _svc.worker_id, "muc": muc}
    ban_ghi.update(truong)
    print(json.dumps(ban_ghi, ensure_ascii=False), flush=True)


def _nhip(trang_thai: str, chu_ky: int, bao_cao: Optional[Dict[str, int]]) -> None:
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT_FILE.write_text(json.dumps({
            "worker_id": _svc.worker_id,
            "pid": os.getpid(),
            "trang_thai": trang_thai,
            "chu_ky": chu_ky,
            "luc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "job_dang_chay": _svc.job_threads_alive(),
            "lan_quet_gan_nhat": bao_cao,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _xin_dung(signum: int, _frame: Any) -> None:
    _ghi("nhan_tin_hieu_dung", tin_hieu=signum)
    _dung.set()


def chay(doi_moi_truong: Optional[str] = None) -> int:
    _settings.validate()          # FAIL FAST y het web/worker TTS

    # CHONG TRO NHAM TAI NGUYEN — cung bay da tung gap voi worker TTS: quen
    # `FAS_ENV_FILE` thi worker am tham xu ly du lieu dev bang credential dev.
    if doi_moi_truong and _settings.environment.lower() != doi_moi_truong.lower():
        _ghi("dung_vi_sai_moi_truong",
             mong_doi=doi_moi_truong, thuc_te=_settings.environment,
             thong_diep=("FAS_ENV không khớp. Nhiều khả năng đang nạp nhầm "
                         "file cấu hình — kiểm tra FAS_ENV_FILE."))
        return 2

    if _settings.translation_inline_worker:
        _ghi("canh_bao",
             thong_diep="FAS_TRANSLATION_INLINE_WORKER đang BẬT — web cũng tự "
                        "chạy job dịch. Ở staging/production hãy đặt "
                        "FAS_TRANSLATION_INLINE_WORKER=false.")

    _svc.enable_job_execution()
    assert _svc.can_run_jobs(), "worker phải được phép chạy job"

    _ghi("khoi_dong", pid=os.getpid(), che_do=_settings.describe(),
         chu_ky_giay=POLL_SECONDS, an_han_dung_giay=GRACE_SECONDS,
         chay_job_duoc=_svc.can_run_jobs())

    for tin_hieu in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(tin_hieu, _xin_dung)
        except (ValueError, OSError):
            pass  # Windows khong co du bo tin hieu — kill cuong che van co
                  # duong recovery lo (lease het han, worker khac nhan lai).

    chu_ky = 0
    while not _dung.is_set():
        chu_ky += 1
        bao_cao = None
        try:
            # `pending_min_age_seconds=0`: khong co thread nao trong tien
            # trinh web dang lo job moi (day la worker RIENG), nen nhan ngay.
            bao_cao = _svc.recover_stale_jobs(pending_min_age_seconds=0)
            if bao_cao.get("chay_lai") or bao_cao.get("het_luot_thu"):
                _ghi("da_quet", **bao_cao)
        except Exception as exc:
            _ghi("loi_quet", loai=type(exc).__name__)
        _nhip("dang_chay", chu_ky, bao_cao)
        _dung.wait(POLL_SECONDS)

    # -- dung sach ---------------------------------------------------------
    _ghi("dang_dung", job_dang_chay=_svc.job_threads_alive())
    _svc.stop_accepting_new_jobs()
    han = time.time() + GRACE_SECONDS
    while time.time() < han and _svc.job_threads_alive() > 0:
        _nhip("dang_dung", chu_ky, None)
        time.sleep(1)

    con_lai = _svc.job_threads_alive()
    _nhip("da_dung", chu_ky, None)
    if con_lai:
        _ghi("dung_khi_con_job", con_lai=con_lai,
             thong_diep="job còn lại sẽ được nhận lại sau khi lease hết hạn")
        return 1
    _ghi("da_dung_sach")
    return 0


#: Nhip cu hon bao nhieu giay thi coi la worker da treo.
STALE_SECONDS = int(os.environ.get("FAS_TRANSLATION_WORKER_STALE_SECONDS",
                                   str(POLL_SECONDS * 10 + 30)))


def kiem_tra() -> int:
    """`python -m server.translation_worker --check` — healthcheck cho nen
    tang hosting. Cung khuon voi `server/worker.py::kiem_tra`."""
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
                      "so_job_dang_chay": d.get("job_dang_chay") or 0},
                     ensure_ascii=False))
    return 0 if tuoi <= STALE_SECONDS else 1


def _doc_tham_so(argv):
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m server.translation_worker",
        description="Tien trinh worker dich (V5). Chay rieng, khong nam trong web.")
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
