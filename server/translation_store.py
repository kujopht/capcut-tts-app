"""
Kho trong bo nho cho Novel Translation Studio (V5).

CHUA phai kho ben vung — du lieu chi song trong vong doi tien trinh, dung
mau voi `MockSocialStore`/`MockMetadataStore`. Khi co nhu cau ben vung that,
them mot ban Appwrite cung giao dien VA mot bo test hop dong chay ca hai
(cung triet ly voi `test_social_contract.py`).

Day la MOT MIXIN — `MockTranslationStore` doc lap, khong ke thua tu store
metadata chinh: subsystem dich HOAN TOAN tach biet, khong dung `tts_jobs`
hay bat ky bang nao cua pipeline audio.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any, Dict, List, Optional, Set, Tuple

from server.adapters import NotFoundError, PermissionDenied
from server.translation import TERMINAL_STATUSES, GlossaryEntry, TranslationJobStatus
from server.translation_domain import TranslationJob, TranslationProject, TranslationVersion


class MockTranslationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projects: Dict[str, TranslationProject] = {}
        self._jobs: Dict[str, TranslationJob] = {}
        #: project_id -> {term_id: GlossaryEntry}
        self._glossary: Dict[str, Dict[str, GlossaryEntry]] = {}
        #: (job_id, attempt) da duoc claim — cung vai tro voi `job_claims` cua
        #: Appwrite: mot khoa DA claim khong bao gio claim duoc lan hai, cung
        #: mot lan thu. Xem `MockMetadataStore._claims` (tts) — cung khuon.
        self._claims: Set[Tuple[str, int]] = set()
        #: project_id -> {version_id: TranslationVersion} — Part O.
        self._versions: Dict[str, Dict[str, TranslationVersion]] = {}

    # ======================================================== du an

    def create_project(self, project: TranslationProject) -> TranslationProject:
        with self._lock:
            self._projects[project.project_id] = project
            self._glossary.setdefault(project.project_id, {})
            return project

    def get_project(self, project_id: str) -> TranslationProject:
        with self._lock:
            p = self._projects.get(project_id)
        if p is None:
            raise NotFoundError("Không tìm thấy dự án dịch.")
        return p

    def owned_project(self, project_id: str, owner_id: str) -> TranslationProject:
        p = self.get_project(project_id)
        if p.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu dự án dịch này.")
        return p

    def save_project(self, project: TranslationProject) -> TranslationProject:
        with self._lock:
            self._projects[project.project_id] = project
            return project

    def list_projects(self, owner_id: str) -> List[TranslationProject]:
        with self._lock:
            ra = [p for p in self._projects.values() if p.owner_id == owner_id]
        return sorted(ra, key=lambda p: p.created_at, reverse=True)

    # ======================================================== job

    def create_job(self, job: TranslationJob) -> TranslationJob:
        with self._lock:
            self._jobs[job.job_id] = job
            return job

    def get_job(self, job_id: str) -> TranslationJob:
        with self._lock:
            j = self._jobs.get(job_id)
        if j is None:
            raise NotFoundError("Không tìm thấy job dịch.")
        return j

    def owned_job(self, job_id: str, owner_id: str) -> TranslationJob:
        j = self.get_job(job_id)
        if j.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu job dịch này.")
        return j

    def save_job(self, job: TranslationJob) -> TranslationJob:
        with self._lock:
            self._jobs[job.job_id] = job
            return job

    def active_job_for_project(self, project_id: str) -> Optional[TranslationJob]:
        """
        Job CHUA KET THUC gan voi du an nay, neu co — nen tang cho IDEMPOTENT
        cua `POST .../jobs`: F5/goi lai khong duoc tao job thu hai.
        """
        with self._lock:
            for j in self._jobs.values():
                if j.project_id == project_id and j.status not in TERMINAL_STATUSES:
                    return j
        return None

    def jobs_for_project(self, project_id: str) -> List[TranslationJob]:
        with self._lock:
            ra = [j for j in self._jobs.values() if j.project_id == project_id]
        return sorted(ra, key=lambda j: j.created_at, reverse=True)

    def list_jobs_by_status(self, status: TranslationJobStatus) -> List[TranslationJob]:
        with self._lock:
            items = [j for j in self._jobs.values() if j.status is status]
        return sorted(items, key=lambda j: j.created_at)

    # ======================================================== claim/lease

    def claim_job(self, job: TranslationJob, worker_id: str,
                 lease_expires_at: str) -> Optional[int]:
        """
        Compare-and-set THAT SU — cung khuon voi
        `MockMetadataStore.claim_job` (TTS). Trong bo nho, `self._lock` la
        thu cuong che tinh duy nhat: kiem-va-ghi nam gon trong mot lan giu
        khoa, khong the bi xen ngang.

        Tra ve fencing token (int) khi thang, `None` khi thua — nguoi goi
        PHAI dung lai, khong thu lai mu quang (xem `translation_service.py`).
        """
        with self._lock:
            current = self._jobs.get(job.job_id)
            if current is None or current.status in TERMINAL_STATUSES:
                return None
            if current.lease_is_live():
                # KE CA khi lease la cua chinh `worker_id` — tu nhan lai job
                # cua chinh minh la duong dan toi hai thread cung dich mot
                # chuong, cung ly do voi TTS.
                return None
            fence = (current.attempts or 0) + 1
            key = (job.job_id, fence)
            if key in self._claims:
                return None
            self._claims.add(key)
            self._jobs[job.job_id] = replace(
                current, status=TranslationJobStatus.ANALYZING, attempts=fence,
                lease_owner=worker_id, lease_expires_at=lease_expires_at)
            return fence

    def renew_lease(self, job_id: str, fence: int, worker_id: str,
                    lease_expires_at: str) -> bool:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                return False
            if (current.attempts or 0) != fence or current.lease_owner != worker_id:
                return False
            self._jobs[job_id] = replace(current, lease_expires_at=lease_expires_at,
                                         lease_owner=worker_id)
            return True

    def save_progress(self, job_id: str, fence: int, worker_id: str, **truong) -> bool:
        """
        Ghi NHANH cac truong tien do (khong phai transition trang thai day
        du) — cung ly do voi `TtsJob.save_progress`: chi ghi it truong hay
        doi lien tuc, tranh mot giao dich day du moi lan mot doan dich xong.

        `truong` la BAT KY thuoc tinh nao cua `TranslationJob` (thuong
        `current_chapter`/`current_chapter_done_segments`/
        `current_chapter_total_segments`/`current_pass`).
        """
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                return False
            if (current.attempts or 0) != fence or current.lease_owner != worker_id:
                return False
            self._jobs[job_id] = replace(current, **truong)
            return True

    def save_job_fenced(self, job: TranslationJob, fence: int,
                        worker_id: str) -> bool:
        """Ghi job chi khi nguoi goi CON GIU quyen (fence + lease_owner khop)."""
        with self._lock:
            current = self._jobs.get(job.job_id)
            if current is None:
                return False
            if (current.attempts or 0) != fence or current.lease_owner != worker_id:
                return False
            self._jobs[job.job_id] = replace(job, attempts=fence)
            return True

    # ======================================================== glossary

    def add_glossary_entry(self, entry: GlossaryEntry) -> GlossaryEntry:
        with self._lock:
            bang = self._glossary.setdefault(entry.project_id, {})
            bang[entry.term_id] = entry
            return entry

    def get_glossary_entry(self, project_id: str, term_id: str) -> GlossaryEntry:
        with self._lock:
            muc = self._glossary.get(project_id, {}).get(term_id)
        if muc is None:
            raise NotFoundError("Không tìm thấy thuật ngữ.")
        return muc

    def save_glossary_entry(self, entry: GlossaryEntry) -> GlossaryEntry:
        with self._lock:
            self._glossary.setdefault(entry.project_id, {})[entry.term_id] = entry
            return entry

    def delete_glossary_entry(self, project_id: str, term_id: str) -> None:
        with self._lock:
            self._glossary.get(project_id, {}).pop(term_id, None)

    def list_glossary(self, project_id: str) -> List[GlossaryEntry]:
        with self._lock:
            ra = list(self._glossary.get(project_id, {}).values())
        return sorted(ra, key=lambda e: e.original)

    # ======================================================== lich su ban dich (Part O)

    def add_version(self, version: TranslationVersion) -> TranslationVersion:
        with self._lock:
            self._versions.setdefault(version.project_id, {})[version.version_id] = version
            return version

    def get_version(self, project_id: str, version_id: str) -> TranslationVersion:
        with self._lock:
            v = self._versions.get(project_id, {}).get(version_id)
        if v is None:
            raise NotFoundError("Không tìm thấy phiên bản lịch sử này.")
        return v

    def list_versions(self, project_id: str,
                      chapter_index: Optional[int] = None) -> List[TranslationVersion]:
        with self._lock:
            ra = list(self._versions.get(project_id, {}).values())
        if chapter_index is not None:
            ra = [v for v in ra if v.chapter_index == chapter_index]
        return sorted(ra, key=lambda v: v.created_at, reverse=True)


def build_translation_store(settings) -> Any:
    """
    Chon kho dich theo `DATA_BACKEND` — CUNG MAU voi
    `server.adapters.build_metadata_store` (TTS), nhung chon RIENG cho
    subsystem nay: `DATA_BACKEND=appwrite` co the ap dung cho novels/tts_jobs
    ma van dang mock cho dich (hoac nguoc lai) neu can, vi hai kho hoan toan
    doc lap.

    Part L: "khong bao gio am tham lui ve bo nho khi da cau hinh dung ben
    vung". `AppwriteTranslationStore.__init__` tu nem `AppwriteConfigError`
    khi thieu bat ky bien nao trong bon bien Appwrite bat buoc — ham nay
    KHONG bat loi do, de nem thang len tren: mot moi truong
    tuong minh dat `appwrite` ma thieu cau hinh PHAI CHET NGAY luc khoi dong,
    khong duoc chay tiep roi am tham dung mock (nguoi dung tin du lieu dich
    duoc luu, thuc te moi lan restart la mat sach).
    """
    if settings.data_backend == "appwrite":
        from server.appwrite_translation_store import AppwriteTranslationStore

        return AppwriteTranslationStore(settings.appwrite)
    return MockTranslationStore()
