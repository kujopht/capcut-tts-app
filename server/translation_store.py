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
from typing import Dict, List, Optional

from server.adapters import NotFoundError, PermissionDenied
from server.translation import GlossaryEntry, TranslationJobStatus
from server.translation_domain import TranslationJob, TranslationProject


class MockTranslationStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projects: Dict[str, TranslationProject] = {}
        self._jobs: Dict[str, TranslationJob] = {}
        #: project_id -> {term_id: GlossaryEntry}
        self._glossary: Dict[str, Dict[str, GlossaryEntry]] = {}

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
                if (j.project_id == project_id
                        and j.status not in (TranslationJobStatus.COMPLETED,
                                             TranslationJobStatus.FAILED,
                                             TranslationJobStatus.CANCELLED)):
                    return j
        return None

    def jobs_for_project(self, project_id: str) -> List[TranslationJob]:
        with self._lock:
            ra = [j for j in self._jobs.values() if j.project_id == project_id]
        return sorted(ra, key=lambda j: j.created_at, reverse=True)

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
