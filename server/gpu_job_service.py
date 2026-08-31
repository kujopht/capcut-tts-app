"""
`GPUJobService` — tang DIEU PHOI GENERIC cho moi cong viec GPU bat dong bo
(image generation hom nay, dich thuat Hy-MT2 hom nay, TTS/video/LoRA training
sau nay — xem `server/gpu_job_domain.py::GPUJobType`).

KIEN TRUC (yeu cau CUNG cua mission):

    Application -> GPUJobService -> ProviderAdapter -> Beam hom nay / provider khac sau nay

`GPUJobService` KHONG BAO GIO goi truc tiep Beam hay bat ky ha tang GPU cu
the nao — no chi biet Protocol `GPUJobProviderAdapter` duoi day. Mot adapter
Beam THAT se duoc viet o MOT file KHAC sau nay, implement dung Protocol nay —
CHUA viet/wire dem nay (mission cam goi mang that toi Beam).

HOP DONG STATUS-POLLING (item 2 cua mission) — day la phan "khong can route
HTTP that dem nay, chi can hop dong Python-level on dinh":

    - `get_job_status(job_id)` -> `GPUJob` DAY DU, DOC THANG tu kho (khong
      goi provider) — day la thao tac client-facing, RE, dung cho da so lan
      client hoi ("job toi the nao roi?").
    - `get_job_status(job_id, refresh=True)` -> CUNG `GPUJob`, nhung truoc
      khi tra ve, service se CHU DONG hoi provider (`adapter.poll()`, va
      `adapter.fetch_result()` neu da xong) de cap nhat kho — day la thao
      tac WORKER-facing (mot vong lap doi soat that, tuong tu
      `server/worker.py` cho TTS, se goi voi `refresh=True`).
    - `get_job_status_response(job_id, refresh=...)` -> `GPUJobStatusResponse`
      (`server/gpu_job_domain.py`), MOT hinh dang ON DINH, JSON-serializable
      qua `.to_dict()` — thiet ke de MOT route FastAPI tuong lai o
      `server/main.py` boc THANG, khong phai suy doan lai hinh dang:

        {
          "job_id": ..., "job_type": ..., "status": ..., "provider": ...,
          "model": ..., "created_at": ..., "started_at": ...,
          "completed_at": ..., "attempts": ..., "error_class": ...,
          "error_message": ..., "output_ref": ...,  # chi co khi COMPLETED
          "usage_metadata": {...}, "cost_metadata": {...},
        }

JUDGMENT CALLS (ghi ro de nguoi doc/mo rong sau nay khong phai doan lai):

1. RETRY CLASSIFICATION — `classify_error(exc)` duoi day map MOT exception
   THAT (do adapter nem ra) sang mot chuoi `error_class` on dinh; chinh
   sach "chuoi do co duoc thu lai hay khong" nam o
   `gpu_job_domain.classify_error_class()` (tang domain, khong phai o day)
   de `GPUJob.is_retryable()` tu tra loi duoc ma khong phu thuoc nguoc vao
   module nay. Loi TAM THOI (timeout/mang/rate-limit/qua tai provider) duoc
   THU LAI submit toi da `MAX_JOB_ATTEMPTS` lan (hang so don gian, CHUA co
   backoff/jitter — nen mong, khong phai bo may retry day du); loi VINH VIEN
   (validation/content-policy/auth/model khong ton tai/het han muc) chuyen
   `FAILED` NGAY, khong thu lai — dot GPU rat dat, thu lai mot loi khong bao
   gio tu sua chi dot tien vo ich.

2. CANCELLATION SEMANTICS — job dang `QUEUED` (chua tung goi
   `adapter.submit()` thanh cong, hoac da submit that bai va dang cho retry)
   huy NGAY TAI CHO, KHONG hoi adapter (chua tieu ton GPU nao ma phai huy).
   Job dang `PROVISIONING`/`RUNNING`: service goi MOT yeu cau huy best-effort
   toi `adapter.cancel()`, roi coi job la `CANCELLED` NGAY LAP TUC ve phia
   MINH — KHONG cho adapter xac nhan xong moi doi trang thai, va KHONG chan
   (block) cho mot grace period. Day la lua chon DON GIAN NHAT AN TOAN cho
   PHAM VI mot nen mong dong bo, khong co worker/poller that dang chay: mot
   worker THAT sau nay (kieu `server/worker.py`) can tu kiem tra lai VOI
   provider (poll) truoc khi coi output cua mot job "da huy" la rac an toan
   de bo — ghi ro o day de nguoi viet worker that khong bi bat ngo.

3. IDEMPOTENCY DEDUPE RULE — `idempotency_key` TUONG MINH (khi caller
   truyen) LUON thang `input_hash` NGAM DINH lam khoa chong trung. MOT job
   KHONG-TERMINAL (QUEUED/PROVISIONING/RUNNING) VOI CUNG khoa -> tra ve
   NGUYEN job do, KHONG tao job moi, KHONG goi lai `adapter.submit()`. MOT
   job da `COMPLETED` voi cung khoa CUNG duoc tra ve nguyen (ket qua da co
   san, sinh lai la dot GPU-giay vo ich). MOT job da `FAILED`/`CANCELLED`
   voi cung khoa thi DUOC PHEP tao job MOI (mot LUOT thu moi, `attempts`
   bat dau lai tu 0) — vi mot caller goi lai VOI CUNG idempotency_key SAU
   KHI lan truoc that bai/bi huy gan nhu chac chan dang CHU DONG muon thu
   lai, khong phai mot request goi nham lan hai.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Protocol

from server.domain import now_iso
from server.gpu_job_domain import (
    MAX_JOB_ATTEMPTS,
    GPUJob,
    GPUJobStatus,
    GPUJobStatusResponse,
    GPUJobType,
    classify_error_class,
    compute_input_hash,
)

#: Trang thai coi la "da co ket qua/khong con gi de thu lai" cho MUC DICH
#: dedupe (judgment call 3 o tren) — KHAC voi `GPUJob._TERMINAL_STATUSES`:
#: o day CHI hai trang thai nay moi cho phep tao job MOI voi cung khoa.
_DEDUPE_ALLOWS_NEW_ATTEMPT = frozenset({GPUJobStatus.FAILED, GPUJobStatus.CANCELLED})


class GPUJobNotFoundError(KeyError):
    """Khong tim thay job voi `job_id` da cho trong kho."""


def classify_error(exc: BaseException) -> str:
    """
    Map MOT exception THAT (do `GPUJobProviderAdapter` nem ra luc submit/
    poll/fetch) sang MOT `error_class` chuoi on dinh, ghi len `GPUJob`.

    Nen mong DON GIAN: phan loai theo KIEU exception, khong phai phan tich
    noi dung message (that ra khong dang tin cho phan loai an toan). Mo
    rong sau nay (vd bat mot exception rieng cua Beam SDK khi adapter that
    duoc viet) chi can them MOT nhanh o day — KHONG can dong den
    `gpu_job_domain.py`, noi giu chinh sach "chuoi nay co duoc thu lai hay
    khong" (xem `classify_error_class`).

    Loai KHONG nhan dien duoc luon anh xa ve `"unknown_error"`, va
    `classify_error_class("unknown_error")` tra ve `"permanent"` theo mac
    dinh AN TOAN cua tang domain — fail closed, khong fail open.
    """
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "network_error"
    if isinstance(exc, PermissionError):
        return "authentication_error"
    if isinstance(exc, ValueError):
        return "validation_error"
    return "unknown_error"


# -----------------------------------------------------------------------------
# Kho luu job — Protocol + ban mock trong bo nho
# -----------------------------------------------------------------------------


class GPUJobStore(Protocol):
    """Giao dien BEN VUNG cho `GPUJob` — mot ban Appwrite THAT (cung
    nguyen tac voi `server/appwrite_translation_store.py`) se implement
    Protocol nay sau, khong dong cham gi den `GPUJobService`."""

    def save(self, job: GPUJob) -> GPUJob: ...

    def get(self, job_id: str) -> Optional[GPUJob]: ...

    def find_by_idempotency_key(self, key: str) -> Optional[GPUJob]: ...

    def list_pending(self) -> List[GPUJob]: ...


class MockGPUJobStore:
    """
    Kho TRONG BO NHO cho test/dev — KHONG ben vung, mirror
    `MockTranslationStore` (`server/translation_store.py`) ve triet ly.

    `_by_idempotency_key` chi giu MOI khoa -> job_id CUA LAN `save()` GAN
    NHAT: khi mot khoa duoc tai su dung cho MOT job MOI (sau khi job cu
    FAILED/CANCELLED — xem judgment call 3 o docstring dau module), tra cuu
    tu nhien tra ve job MOI NHAT, dung y muon.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, GPUJob] = {}
        self._by_idempotency_key: Dict[str, str] = {}

    def save(self, job: GPUJob) -> GPUJob:
        with self._lock:
            self._jobs[job.job_id] = job
            if job.idempotency_key:
                self._by_idempotency_key[job.idempotency_key] = job.job_id
            return job

    def get(self, job_id: str) -> Optional[GPUJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def find_by_idempotency_key(self, key: str) -> Optional[GPUJob]:
        with self._lock:
            job_id = self._by_idempotency_key.get(key)
            return self._jobs.get(job_id) if job_id else None

    def list_pending(self) -> List[GPUJob]:
        with self._lock:
            return [job for job in self._jobs.values() if not job.is_terminal()]


# -----------------------------------------------------------------------------
# Adapter provider — Protocol (day la RANH GIOI duy nhat toi Beam/GPU that)
# -----------------------------------------------------------------------------


class GPUJobProviderAdapter(Protocol):
    """
    MOT provider GPU THAT (Beam hom nay, provider khac sau nay). Day la
    THU DUY NHAT `GPUJobService` phu thuoc de lam viec THAT su voi GPU —
    khong co import beam/torch/httpx nao trong `GPUJobService` hay
    `GPUJob`, TAT CA di qua bon phuong thuc duoi day.

    MOT `BeamGPUJobProviderAdapter` implement Protocol nay se duoc viet o
    MOT file khac sau nay — KHONG viet/wire dem nay.
    """

    def submit(self, job: GPUJob, input_data: Any) -> str:
        """Gui `input_data` toi provider cho `job` nay. Tra ve
        `provider_job_ref` (dinh danh job phia provider). NEM exception khi
        that bai — `GPUJobService` se bat va phan loai qua `classify_error`."""
        ...

    def poll(self, job: GPUJob) -> GPUJobStatus:
        """Hoi provider trang thai HIEN TAI cua `job` (dung
        `job.provider_job_ref`). NEM exception khi khong lien lac duoc."""
        ...

    def cancel(self, job: GPUJob) -> bool:
        """Yeu cau provider HUY `job`. Best-effort — xem judgment call 2
        o docstring dau module ve y nghia gia tri tra ve/exception."""
        ...

    def fetch_result(self, job: GPUJob) -> str:
        """Lay ve `output_ref` (KHONG PHAI bytes) sau khi `poll()` bao
        `COMPLETED`. Adapter THAT se tu luu bytes qua mot `OutputStorage`
        (`server/gpu_job_storage.py`) va tra ve `output_ref` cua no."""
        ...


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------


class GPUJobService:
    """Xem docstring dau module cho kien truc/hop dong day du."""

    def __init__(self, store: GPUJobStore,
                 provider_adapters: Dict[str, GPUJobProviderAdapter]) -> None:
        self._store = store
        self._adapters: Dict[str, GPUJobProviderAdapter] = dict(provider_adapters)

    def _adapter_for(self, provider: str) -> GPUJobProviderAdapter:
        try:
            return self._adapters[provider]
        except KeyError:
            raise ValueError(
                f"Không có adapter đã đăng ký cho provider '{provider}'."
            ) from None

    def _require_job(self, job_id: str) -> GPUJob:
        job = self._store.get(job_id)
        if job is None:
            raise GPUJobNotFoundError(job_id)
        return job

    # -- submit ---------------------------------------------------------

    def submit_job(self, job_type: GPUJobType, provider: str, model: str,
                    input_data: Any,
                    idempotency_key: Optional[str] = None) -> GPUJob:
        """
        Tao (hoac tai su dung) MOT `GPUJob` va gui toi provider.

        Xem judgment call 3 (docstring dau module) cho quy tac dedupe day
        du. Nem `ValueError` NGAY neu `provider` chua co adapter dang ky —
        TRUOC khi tao/luu bat ky job nao, de khong de lai mot job mo coi
        trong kho khi caller go sai ten provider.
        """
        adapter = self._adapter_for(provider)
        input_hash = compute_input_hash(input_data)
        dedup_key = idempotency_key or input_hash

        existing = self._store.find_by_idempotency_key(dedup_key)
        if existing is not None and existing.status not in _DEDUPE_ALLOWS_NEW_ATTEMPT:
            return existing

        job = GPUJob(
            job_type=job_type, provider=provider, model=model,
            status=GPUJobStatus.QUEUED, input_hash=input_hash,
            idempotency_key=dedup_key,
        )
        self._store.save(job)
        self._attempt_submit(job, adapter, input_data)
        return job

    def _attempt_submit(self, job: GPUJob, adapter: GPUJobProviderAdapter,
                         input_data: Any) -> None:
        """Vong lap SUBMIT-RETRY dong bo — xem judgment call 1. Chay NGAY
        LAP TUC (khong backoff that), phu hop pham vi mot nen mong."""
        while True:
            job.attempts += 1
            try:
                job.provider_job_ref = adapter.submit(job, input_data)
            except Exception as exc:  # noqa: BLE001 - phai bat MOI loi tu adapter de phan loai duoc, khong de crash service
                error_class = classify_error(exc)
                job.error_class = error_class
                job.error_message = str(exc)
                if (classify_error_class(error_class) == "retryable"
                        and job.attempts < MAX_JOB_ATTEMPTS):
                    self._store.save(job)
                    continue
                job.status = GPUJobStatus.FAILED
                job.completed_at = now_iso()
                self._store.save(job)
                return
            else:
                job.status = GPUJobStatus.PROVISIONING
                job.started_at = now_iso()
                job.error_class = None
                job.error_message = None
                self._store.save(job)
                return

    # -- status -----------------------------------------------------------

    def get_job_status(self, job_id: str, *, refresh: bool = False) -> GPUJob:
        """Xem hop dong day du trong docstring dau module. `refresh=False`
        (mac dinh) chi doc kho, khong goi provider — an toan de goi tu MOI
        request cua client dang cho."""
        job = self._require_job(job_id)
        if not refresh or job.is_terminal():
            return job
        return self._refresh_from_provider(job)

    def get_job_status_response(self, job_id: str, *,
                                 refresh: bool = False) -> GPUJobStatusResponse:
        return GPUJobStatusResponse.from_job(
            self.get_job_status(job_id, refresh=refresh))

    def _refresh_from_provider(self, job: GPUJob) -> GPUJob:
        """Thao tac WORKER-facing: hoi THAT provider va cap nhat kho. Loi
        TAM THOI luc poll KHONG lam doi trang thai job (job that tren
        provider co the van dang chay binh thuong — chi la lan hoi nay
        khong lien lac duoc, se thu lai o lan poll sau); loi VINH VIEN luc
        poll chuyen job `FAILED` ngay."""
        adapter = self._adapter_for(job.provider)
        try:
            new_status = adapter.poll(job)
        except Exception as exc:  # noqa: BLE001
            error_class = classify_error(exc)
            if classify_error_class(error_class) == "permanent":
                job.status = GPUJobStatus.FAILED
                job.error_class = error_class
                job.error_message = str(exc)
                job.completed_at = now_iso()
                self._store.save(job)
            return job

        if new_status is GPUJobStatus.COMPLETED:
            try:
                job.output_ref = adapter.fetch_result(job)
            except Exception as exc:  # noqa: BLE001
                job.status = GPUJobStatus.FAILED
                job.error_class = classify_error(exc)
                job.error_message = f"fetch_result thất bại: {exc}"
                job.completed_at = now_iso()
                self._store.save(job)
                return job
            job.status = GPUJobStatus.COMPLETED
            job.completed_at = now_iso()
        elif new_status is GPUJobStatus.FAILED:
            job.status = GPUJobStatus.FAILED
            # Protocol `poll()` chi tra ve MOT trang thai, khong kem chi
            # tiet loi - khong the phan loai retryable/permanent tu day,
            # nen coi la VINH VIEN (an toan, gionng chinh sach mac dinh
            # cua `classify_error_class`) neu chua co error_class nao khac.
            job.error_class = job.error_class or "provider_reported_failure"
            job.completed_at = now_iso()
        elif new_status is GPUJobStatus.CANCELLED:
            job.status = GPUJobStatus.CANCELLED
            job.completed_at = now_iso()
        else:
            if (job.started_at is None
                    and new_status in (GPUJobStatus.PROVISIONING, GPUJobStatus.RUNNING)):
                job.started_at = now_iso()
            job.status = new_status
        self._store.save(job)
        return job

    # -- cancel -----------------------------------------------------------

    def cancel_job(self, job_id: str) -> GPUJob:
        """Xem judgment call 2 (docstring dau module) cho ngu nghia day du.
        Huy MOT job da o trang thai ket thuc la NO-OP (tra ve nguyen job,
        khong nem loi) — huy hai lan khong nen la mot loi cua caller."""
        job = self._require_job(job_id)
        if job.is_terminal():
            return job
        if job.status is GPUJobStatus.QUEUED:
            job.status = GPUJobStatus.CANCELLED
            job.completed_at = now_iso()
            self._store.save(job)
            return job
        adapter = self._adapter_for(job.provider)
        try:
            adapter.cancel(job)
        except Exception as exc:  # noqa: BLE001 - best-effort, xem judgment call 2
            job.error_message = f"Yêu cầu huỷ tới provider thất bại: {exc}"
        job.status = GPUJobStatus.CANCELLED
        job.completed_at = now_iso()
        self._store.save(job)
        return job
