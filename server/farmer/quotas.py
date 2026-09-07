"""Han muc va cong dia — farmer PHAI dung lai truoc khi lam hong may.

May gat la mot t3a.medium: 2 vCPU, 4 GiB RAM, mot dia goc dung chung voi hai
worker production dang chay that (`fanfic-worker-prod`,
`fanfic-translation-worker-prod`). Lam day dia o day khong chi dung farmer —
no lam do ca hai worker do.

Nen moi han muc o day deu **fail closed**: het han muc, hoac khong DO duoc
tinh trang dia, thi KHONG bat dau viec moi. Khong co nhanh nao "cu chay thu
xem sao".

Han muc la CHAN TREN dong thoi, khong phai chi tieu:

    tai ve dong thoi     — I/O mang + ghi dia, thu de lam day dia nhat
    yeu cau danh gia     — moi lan la mot lan goi Gemini co tra phi
    job TTS              — moi job chiem mot khe cua Cloud Run dung chung

Ba con so nay co y NHO. May gat khong phai de chay nhanh; no de chay mai.
"""
from __future__ import annotations

import os
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional

#: Mac dinh cho t3a.medium. Deu doi duoc qua bien moi truong.
DEFAULT_MAX_CONCURRENT_DOWNLOADS = 2
DEFAULT_MAX_REVIEW_REQUESTS = 8
DEFAULT_MAX_TTS_JOBS = 3

#: Con lai duoi nguong nay thi KHONG tai them gi. 5 GiB nghe nhieu, va do la
#: co y: mot tap audio dai co the phinh ra vai GiB khi giai nen sang WAV, va
#: hai worker production dung chung dia nay can cho de tho.
DEFAULT_MIN_FREE_DISK_BYTES = 5 * 1024 * 1024 * 1024

#: Thu muc lam viec cua farmer — do tinh trang dia CHINH O DAY, khong do `/`,
#: vi trong tuong lai no co the la mot volume khac.
DEFAULT_WORK_DIR = "/var/lib/fanfic-farmer/work"

ENV_MAX_DOWNLOADS = "FARMER_MAX_CONCURRENT_DOWNLOADS"
ENV_MAX_REVIEWS = "FARMER_MAX_REVIEW_REQUESTS"
ENV_MAX_TTS = "FARMER_MAX_TTS_JOBS"
ENV_MIN_FREE_DISK = "FARMER_MIN_FREE_DISK_BYTES"
ENV_WORK_DIR = "FARMER_WORK_DIR"


class QuotaExceeded(RuntimeError):
    """Het han muc, hoac cong dia dong. KHONG phai loi — la phanh."""


def _int_env(name: str, mac_dinh: int) -> int:
    """Gia tri xau/am -> quay ve mac dinh, KHONG phai 'khong gioi han'.

    Mot bien moi truong danh sai khong duoc mo toang cong. Cung quy tac voi
    `media_eligibility.max_source_seconds`.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return mac_dinh
    try:
        gia_tri = int(raw)
    except ValueError:
        return mac_dinh
    return gia_tri if gia_tri > 0 else mac_dinh


@dataclass
class QuotaState:
    """Anh chup de bao cao — Router Control Center doc hinh dang nay."""
    max_concurrent_downloads: int
    max_review_requests: int
    max_tts_jobs: int
    min_free_disk_bytes: int
    in_flight: Dict[str, int] = field(default_factory=dict)
    used: Dict[str, int] = field(default_factory=dict)
    free_disk_bytes: int = 0
    disk_ok: bool = False
    disk_error: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "limits": {
                # Hai hinh dang khac nhau, ghi ro trong ten de nguoi doc bao
                # cao khong hieu nham "2" la cung mot loai gioi han.
                "concurrent_downloads": self.max_concurrent_downloads,
                "review_requests_per_round": self.max_review_requests,
                "tts_jobs_per_round": self.max_tts_jobs,
                "min_free_disk_bytes": self.min_free_disk_bytes,
            },
            "in_flight": dict(self.in_flight),
            "used": dict(self.used),
            "disk": {
                "free_bytes": self.free_disk_bytes,
                "ok": self.disk_ok,
                "error": self.disk_error,
            },
        }


class FarmerQuotas:
    """Giu ba chan tren dong thoi + mot cong dia. An toan voi nhieu luong."""

    #: Ten cac han muc — dung lam khoa trong bao cao, giu on dinh vi Router
    #: Control Center se doc chung.
    DOWNLOAD = "download"
    REVIEW = "review"
    TTS = "tts"

    #: Hai HINH DANG han muc khac nhau, va su khac nhau la co that:
    #:
    #:   CONCURRENT — chan tren SO VIEC CHAY CUNG LUC. Dung cho tai ve: cai
    #:     dang bao ve la I/O va cho trong dia tai mot thoi diem. Chay 100
    #:     lan tai, moi lan mot, la binh thuong.
    #:
    #:   PER_ROUND  — chan tren SO LAN GOI trong mot vong. Dung cho danh gia
    #:     va TTS: moi lan goi TON TIEN (Gemini) hoac chiem khe cua mot dich
    #:     vu dung chung (Cloud Run). Gioi han dong thoi khong bao ve duoc gi
    #:     o day — mot farmer don luong se lan luot goi 10.000 lan ma khong
    #:     bao gio cham tran "2 cai cung luc".
    CONCURRENT = "concurrent"
    PER_ROUND = "per_round"

    _SHAPE = {DOWNLOAD: CONCURRENT, REVIEW: PER_ROUND, TTS: PER_ROUND}

    def __init__(self, *,
                 max_concurrent_downloads: Optional[int] = None,
                 max_review_requests: Optional[int] = None,
                 max_tts_jobs: Optional[int] = None,
                 min_free_disk_bytes: Optional[int] = None,
                 work_dir: Optional[str] = None):
        self.max_concurrent_downloads = (
            max_concurrent_downloads
            if max_concurrent_downloads is not None
            else _int_env(ENV_MAX_DOWNLOADS, DEFAULT_MAX_CONCURRENT_DOWNLOADS))
        self.max_review_requests = (
            max_review_requests
            if max_review_requests is not None
            else _int_env(ENV_MAX_REVIEWS, DEFAULT_MAX_REVIEW_REQUESTS))
        self.max_tts_jobs = (
            max_tts_jobs
            if max_tts_jobs is not None
            else _int_env(ENV_MAX_TTS, DEFAULT_MAX_TTS_JOBS))
        self.min_free_disk_bytes = (
            min_free_disk_bytes
            if min_free_disk_bytes is not None
            else _int_env(ENV_MIN_FREE_DISK, DEFAULT_MIN_FREE_DISK_BYTES))
        self.work_dir = work_dir or os.environ.get(ENV_WORK_DIR) or DEFAULT_WORK_DIR

        self._lock = threading.Lock()
        self._in_flight: Dict[str, int] = {
            self.DOWNLOAD: 0, self.REVIEW: 0, self.TTS: 0}
        self._used: Dict[str, int] = {
            self.DOWNLOAD: 0, self.REVIEW: 0, self.TTS: 0}

    # -- cong dia ----------------------------------------------------------
    def free_disk_bytes(self) -> int:
        """Byte trong o thu muc lam viec.

        Do o `work_dir` chu khong o `/`: hai cho co the la hai thiet bi khac
        nhau, va cai dang quan tam la cho farmer THAT SU ghi vao.
        """
        muc_tieu = self.work_dir
        while muc_tieu and not os.path.isdir(muc_tieu):
            cha = os.path.dirname(muc_tieu)
            if cha == muc_tieu:
                break
            muc_tieu = cha
        return shutil.disk_usage(muc_tieu or "/").free

    def check_disk(self) -> None:
        """FAIL CLOSED: khong DO duoc dia cung la mot lan tu choi.

        Neu `disk_usage` nem loi (duong dan bien mat, quyen bi rut), doan la
        "chac con cho" roi tai tiep chinh la cach lam day dia cua hai worker
        production dung chung may nay.
        """
        try:
            con_lai = self.free_disk_bytes()
        except Exception as exc:
            raise QuotaExceeded(
                f"khong do duoc dung luong dia tai {self.work_dir!r} "
                f"({type(exc).__name__}: {exc}) — fail closed") from exc
        if con_lai < self.min_free_disk_bytes:
            raise QuotaExceeded(
                f"dia con {con_lai:,} byte < nguong {self.min_free_disk_bytes:,} "
                "— khong bat dau viec moi")

    # -- chan tren dong thoi ------------------------------------------------
    def _limit_for(self, ten: str) -> int:
        return {
            self.DOWNLOAD: self.max_concurrent_downloads,
            self.REVIEW: self.max_review_requests,
            self.TTS: self.max_tts_jobs,
        }[ten]

    @contextmanager
    def slot(self, ten: str, *, check_disk: bool = False):
        """Giu MOT khe cua mot han muc trong suot khoi lenh.

        `check_disk=True` cho nhung viec GHI RA DIA (tai ve, dung WAV) — cong
        dia duoc kiem TRUOC khi chiem khe, de mot may sap day khong con nhan
        them viec chi de roi that bai o giua.
        """
        if ten not in self._in_flight:
            raise ValueError(f"han muc khong xac dinh: {ten!r}")
        if check_disk:
            self.check_disk()

        with self._lock:
            tran = self._limit_for(ten)
            hinh_dang = self._SHAPE[ten]
            # Dem theo DUNG hinh dang cua tung han muc — xem `_SHAPE`.
            dang_dung = (self._in_flight[ten] if hinh_dang == self.CONCURRENT
                         else self._used[ten])
            if dang_dung >= tran:
                raise QuotaExceeded(
                    f"han muc {ten} ({hinh_dang}) da day ({dang_dung}/{tran})")
            self._in_flight[ten] += 1
            self._used[ten] += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight[ten] -= 1

    def try_slot(self, ten: str, *, check_disk: bool = False):
        """Nhu `slot` nhung tra None thay vi nem, cho vong lap muon bo qua mot
        muc va di tiep thay vi dung ca lan chay."""
        try:
            ctx = self.slot(ten, check_disk=check_disk)
            ctx.__enter__()
            return ctx
        except QuotaExceeded:
            return None

    # -- bao cao ------------------------------------------------------------
    def snapshot(self) -> QuotaState:
        try:
            con_lai = self.free_disk_bytes()
            loi = ""
            ok = con_lai >= self.min_free_disk_bytes
        except Exception as exc:
            con_lai, ok, loi = 0, False, f"{type(exc).__name__}: {exc}"
        with self._lock:
            return QuotaState(
                max_concurrent_downloads=self.max_concurrent_downloads,
                max_review_requests=self.max_review_requests,
                max_tts_jobs=self.max_tts_jobs,
                min_free_disk_bytes=self.min_free_disk_bytes,
                in_flight=dict(self._in_flight),
                used=dict(self._used),
                free_disk_bytes=con_lai,
                disk_ok=ok,
                disk_error=loi,
            )

    def reset_usage(self) -> None:
        """Dat lai bo dem TICH LUY (khong dung toi so dang chay) — goi o dau
        moi vong de `max_review_requests` la 'moi vong', khong phai 'tron
        doi tien trinh'."""
        with self._lock:
            for k in self._used:
                self._used[k] = 0
