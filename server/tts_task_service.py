"""
Dau vao HTTP cho worker TTS — dich cua Cloud Tasks.

    uvicorn server.tts_task_service:app --port ${PORT:-8080}

VI SAO CO TEP NAY. `server/worker.py` la mot vong lap POLL: no song mai, quet
Appwrite moi 3 giay, va tren Cloud Run Job no dung vao tran 3600 giay roi chet
ma khong ai bat lai. Tra tien 2 vCPU / 4 GiB de hoi mot hang doi rong.
Kien truc dich la NGUOC LAI: khong co ai chay ca cho den khi CO viec, luc do
Cloud Tasks goi mot request, service tong hop trong request do, roi thu nho ve
khong.

KHONG SAO CHEP LOGIC — va day la diem quan trong nhat cua tep nay. Moi ngu
nghia kho tinh deu goi lai DUNG ham ma `server/worker.py` goi:

    store.claim_job()      compare-and-set that su trong mot transaction
    main._run_job()        heartbeat, fencing token, upload truoc ghi sau
    JOB_MAX_ATTEMPTS       cung mot tran so lan thu

Neu mot ngay nao do lease/fencing doi, no doi o MOT cho, va ca hai duong chay
doi theo. Khong co ban sao nao de lech.

TAT MAC DINH. `FAS_TTS_HTTP_ENABLED` khong bat thi moi request tra 503 va
KHONG cham vao Appwrite, khong cham vao R2, khong tao lease. Trien khai toi
cho nay la trien khai TOI, chua phai chuyen huong: AWS van chay, duong tao job
cu van y nguyen.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel

#: Cong bat/tat. Mac dinh TAT — mot lan deploy nham khong duoc phep bat dau
#: nhan viec. Chi `"1"/"true"/"yes"/"on"` moi bat.
_BAT = os.environ.get("FAS_TTS_HTTP_ENABLED", "").strip().lower()
DUOC_BAT = _BAT in {"1", "true", "yes", "on"}


class TaskIn(BaseModel):
    job_id: str


app = FastAPI(title="fanfic tts task worker", docs_url=None, redoc_url=None)


def _api():
    """
    Nap `server.main` MUON, khong phai luc import module.

    Khi cong tat, tien trinh nay khong duoc phep dung ngay ca cau hinh: nap
    `server.main` la doc settings, dung client Appwrite, va `validate()` co the
    nem neu bien moi truong chua day du. Mot ban dark deploy phai khoi dong
    duoc VA tra loi `/healthz` ke ca khi chua cam bien nao vao.
    """
    from server import main as api

    return api


@app.get("/health")
def health() -> Dict[str, Any]:
    """
    Song chua + cong dang bat hay tat. KHONG bao gio lo cau hinh hay bi mat.

    DUONG DAN LA `/health`, KHONG PHAI `/healthz`. Do that tren Cloud Run:
    frontend cua Google nuot `/healthz` va tra ve trang 404 HTML cua CHINH NO —
    request khong bao gio toi uvicorn (log cua service khong co dong nao).
    Moi duong dan khac deu toi noi binh thuong, nen day khong phai loi dinh
    tuyen cua ung dung. Dat lai ten cho nay la tiet kiem mot buoi go loi cho
    nguoi sau.
    """
    return {"ok": True, "enabled": DUOC_BAT}


@app.post("/tasks/tts")
def chay_task(payload: TaskIn, request: Request) -> Dict[str, Any]:
    """
    Chay MOT job TTS, dong bo trong request nay.

    Ma tra ve duoc chon theo cach Cloud Tasks doc chung:

      200  xong, hoac khong con gi de lam (job da terminal). Task duoc ack.
      409  job dang thuoc worker khac (lease con song, hoac thua claim).
           Cloud Tasks se thu lai sau — dung, vi lease se het han.
      404  khong co job/chuong do.
      503  cong dang TAT.
      500  loi that -> Cloud Tasks thu lai theo backoff cua hang doi.
    """
    if not DUOC_BAT:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "FAS_TTS_HTTP_ENABLED chua bat — ban trien khai toi, chua nhan viec.",
        )

    api = _api()
    from server.adapters import NotFoundError
    from server.domain import JobStatus

    # Cho phep tien trinh NAY chay job. Giong het `server/worker.py`: `main`
    # mac dinh chi chay job khi `inline_worker` bat, con o day bien do la
    # `false`. Khong bat tuong minh thi ta se NHAN job roi khong chay no, va
    # moi lan thu lai dot them mot `attempts` cho den khi job `failed` oan.
    api.enable_job_execution()

    try:
        job = api.store.get_job(payload.job_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "khong co job nay") from exc

    if job.status.is_terminal:
        # Ack, khong phai loi: task trung lap la chuyen BINH THUONG voi
        # at-least-once delivery. Tra 200 de Cloud Tasks thoi thu lai.
        return {"job_id": job.job_id, "ket_qua": "da_terminal",
                "status": job.status.value}

    if job.lease_is_live():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "job dang co worker khac giu lease")

    if (job.attempts or 0) >= api.JOB_MAX_ATTEMPTS:
        # CUNG tran, CUNG thong diep nguoi dung doc duoc nhu duong quet.
        api._mark_failed(
            job, "worker_lost",
            f"Đã thử tạo audio {job.attempts} lần nhưng lần nào tiến trình "
            "cũng bị dừng giữa chừng. Hãy thử lại, hoặc chia chương thành "
            "phần ngắn hơn.",
        )
        return {"job_id": job.job_id, "ket_qua": "het_luot_thu"}

    # Giong cuc bo ma MAY NAY khong co model -> NHUONG, khong nhan. Cung ly le
    # nhu `recover_stale_jobs`: nhan mot job minh khong chay duoc roi danh dau
    # `failed` la giet vinh vien mot job ma worker khac lam duoc.
    if not api.tts_bridge.voice_runnable_on_this_machine(job.voice_id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "may nay khong co model cho giong do")

    try:
        chapter = api.store.get_chapter(job.chapter_id)
    except NotFoundError:
        api._mark_failed(job, "chapter_gone", "Chương không còn tồn tại.")
        return {"job_id": job.job_id, "ket_qua": "chuong_da_mat"}

    # CLAIM THAT SU — cung transaction compare-and-set ma worker dung.
    fence = api.store.claim_job(job, api.WORKER_ID, api._lease_until())
    if fence is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "thua claim, worker khac nhan")

    # Chay DONG BO trong request: Cloud Run chi cap CPU trong request, va ta
    # muon ma tra ve phan anh dung ket qua that de Cloud Tasks quyet dinh thu
    # lai hay khong. `_run_job` tu lo heartbeat, fencing va thu tu upload.
    api._run_job(job, chapter.content, fence)

    sau = api.store.get_job(job.job_id)
    if sau.status is JobStatus.COMPLETED:
        return {"job_id": job.job_id, "ket_qua": "hoan_tat",
                "attempts": sau.attempts}
    if sau.status is JobStatus.FAILED:
        # Ack: that bai da duoc ghi ben vung kem ly do. Thu lai o tang hang doi
        # chi lam job xoay vong; duong thu lai dung la lease/`attempts`.
        return {"job_id": job.job_id, "ket_qua": "that_bai",
                "error_kind": sau.error_kind}
    return {"job_id": job.job_id, "ket_qua": sau.status.value}
