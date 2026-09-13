"""
Hang doi render — de tien trinh WEB khong con so huu mot lan ma hoa dai phut.

PR #202 co `RenderProvider` va chay ngay trong tien trinh web. Du cho phat
trien; khong du cho production, vi ba ly do cu the:

  * mot lan render chay 2-20 phut giu mot luong cua may chu HTTP suot thoi
    gian do;
  * khoi dong lai may chu giua chung thi job bien mat KHONG dau vet, va du
    an ket o `RENDERING` vinh vien;
  * khong co cach nao chay render tren mot may khac.

Tep nay dinh nghia HOP DONG hang doi: xep hang, GIU CHO (lease) co han,
nhip tim, hoan tat, that bai, thu lai co tran. Bo chay cuc bo cua #202 tro
thanh MOT nguoi tieu thu cua hang doi nay, va mot bo chay tren may khac se
la mot nguoi tieu thu khac — khong phai sua tang dich vu.

GIU CHO CO HAN chu khong phai "danh dau dang chay": mot worker chet giua
chung thi khong ai bao ai ca. Han giu cho la cach DUY NHAT mot hang doi tu
phuc hoi ma khong can ai theo doi worker.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from server.domain import new_id, now_iso

#: Giu cho bao lau moi lan. Ngan hon mot lan render dai — worker phai danh
#: nhip tim de giu tiep. Worker chet thi cho tu nha sau chung nay giay.
LEASE_GIAY = 120.0

#: So lan thu lai TOI DA cho mot job. Tran co chu dich: mot job hong vi tep
#: nguon hong se hong MAI, va thu vo han la mot vong lap dot tai nguyen.
TRAN_THU_LAI = 3


class RenderJobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class RenderJob:
    owner_id: str
    #: `VideoProject.project_id` — thu that su duoc render.
    video_project_id: str
    #: Khoa CHONG TRUNG. Hai lan bam Render cua cung mot ban du an phai ra
    #: cung mot job, khong phai hai job cung ma hoa mot thu.
    idempotency_key: str
    state: RenderJobState = RenderJobState.QUEUED
    attempts: int = 0
    #: Worker dang giu cho — rong khi khong ai giu.
    lease_owner: str = ""
    lease_expires_at: float = 0.0
    #: 0..1 khi bo chay bao duoc; `None` khi khong do duoc. KHONG bia.
    progress: Optional[float] = None
    error: str = ""
    output_object_key: str = ""
    job_id: str = field(default_factory=lambda: new_id("rjb"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def dang_giu(self, *, now: Optional[float] = None) -> bool:
        curr = time.time() if now is None else now
        return bool(self.lease_owner) and curr < self.lease_expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "video_project_id": self.video_project_id,
            "state": self.state.value,
            "attempts": self.attempts,
            "progress": self.progress,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MockRenderQueue:
    """Hang doi trong bo nho — MOT tien trinh.

    Giao dien nay la thu ban production se hien thuc lai (Redis/SQS/bang
    SQL). Moi phep doi trang thai deu di qua day, nen ban that chi phai giu
    dung nhung bat bien o duoi chu khong phai doan lai chung.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: Dict[str, RenderJob] = {}

    # -- xep hang -------------------------------------------------------------

    def xep_hang(self, owner_id: str, video_project_id: str,
                 idempotency_key: str) -> RenderJob:
        """Xep MOT job. Cung `idempotency_key` tra lai job cu.

        Chong trung o day chu khong o tang tren: hai yeu cau gan nhau co the
        den tu hai luong khac nhau, va chi cho nay nhin thay ca hai.
        """
        with self._lock:
            for j in self._job.values():
                if (j.owner_id == owner_id
                        and j.idempotency_key == idempotency_key
                        and j.state in (RenderJobState.QUEUED,
                                        RenderJobState.RUNNING)):
                    return j
            j = RenderJob(owner_id=owner_id,
                          video_project_id=video_project_id,
                          idempotency_key=idempotency_key)
            self._job[j.job_id] = j
            return j

    # -- phia worker ----------------------------------------------------------

    def nhan_viec(self, worker_id: str, *, lease_giay: float = LEASE_GIAY,
                  now: Optional[float] = None) -> Optional[RenderJob]:
        """Giu cho MOT job dang cho. `None` khi khong con gi.

        Job dang chay ma HET HAN giu cho cung duoc nhan lai — do chinh la
        cach mot worker chet duoc don dep ma khong ai phai theo doi no.
        """
        curr = time.time() if now is None else now
        with self._lock:
            for j in sorted(self._job.values(), key=lambda x: x.created_at):
                san_sang = (
                    j.state is RenderJobState.QUEUED
                    or (j.state is RenderJobState.RUNNING
                        and not j.dang_giu(now=curr)))
                if not san_sang:
                    continue
                if j.attempts >= TRAN_THU_LAI:
                    # Het lan thu — dong lai thay vi quay mai.
                    j.state = RenderJobState.FAILED
                    j.error = j.error or "Đã thử lại quá số lần cho phép."
                    j.lease_owner = ""
                    j.updated_at = now_iso()
                    continue
                j.state = RenderJobState.RUNNING
                j.attempts += 1
                j.lease_owner = worker_id
                j.lease_expires_at = curr + lease_giay
                j.updated_at = now_iso()
                return j
        return None

    def nhip_tim(self, job_id: str, worker_id: str, *,
                 progress: Optional[float] = None,
                 lease_giay: float = LEASE_GIAY,
                 now: Optional[float] = None) -> bool:
        """Gia han giu cho. `False` neu cho da thuoc ve worker khac.

        Tra `False` la tin hieu cho worker DUNG LAI: job da bi nguoi khac
        nhan, va hai worker cung ghi mot dau ra la cach tao ra mot tep hong.
        """
        curr = time.time() if now is None else now
        with self._lock:
            j = self._job.get(job_id)
            if j is None or j.lease_owner != worker_id:
                return False
            j.lease_expires_at = curr + lease_giay
            if progress is not None:
                j.progress = max(0.0, min(1.0, float(progress)))
            j.updated_at = now_iso()
            return True

    def hoan_tat(self, job_id: str, worker_id: str, *,
                 output_object_key: str) -> bool:
        if not output_object_key:
            raise ValueError("Hoàn tất phải kèm tệp kết quả.")
        with self._lock:
            j = self._job.get(job_id)
            if j is None or j.lease_owner != worker_id:
                return False
            j.state = RenderJobState.DONE
            j.output_object_key = output_object_key
            j.progress = 1.0
            j.error = ""
            j.lease_owner = ""
            j.updated_at = now_iso()
            return True

    def that_bai(self, job_id: str, worker_id: str, *, loi: str,
                 thu_lai: bool = True) -> bool:
        """Bao hong. Con lan thu va `thu_lai` thi ve lai hang doi."""
        with self._lock:
            j = self._job.get(job_id)
            if j is None or j.lease_owner != worker_id:
                return False
            j.error = loi or "Render thất bại."
            j.lease_owner = ""
            if thu_lai and j.attempts < TRAN_THU_LAI:
                j.state = RenderJobState.QUEUED
            else:
                j.state = RenderJobState.FAILED
            j.updated_at = now_iso()
            return True

    # -- phia doc -------------------------------------------------------------

    def lay(self, owner_user_id: str, job_id: str) -> Optional[RenderJob]:
        with self._lock:
            j = self._job.get(job_id)
        return j if j is not None and j.owner_id == owner_user_id else None

    def cho_du_an(self, owner_user_id: str,
                  video_project_id: str) -> List[RenderJob]:
        with self._lock:
            ds = [j for j in self._job.values()
                  if j.owner_id == owner_user_id
                  and j.video_project_id == video_project_id]
        return sorted(ds, key=lambda x: x.created_at, reverse=True)

    def dem_cho(self) -> int:
        with self._lock:
            return sum(1 for j in self._job.values()
                       if j.state is RenderJobState.QUEUED)
