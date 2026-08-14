"""
Kho ben vung tren Appwrite cho Novel Translation Studio (V5).

Cung giao dien voi `MockTranslationStore` (`server/translation_store.py`) —
`TranslationService` khong biet dang chay tren kho nao. HOAN TOAN DOC LAP voi
`server/appwrite_store.py`/`appwrite_social.py` (khong ke thua, khong dung
chung bang) — dung y voi nguyen tac da ghi o `MockTranslationStore`: subsystem
dich la MOT the gioi rieng, khong dung chung voi tts_jobs/novels/profiles.

Ba collection RIENG: `translation_projects`, `translation_jobs`,
`translation_glossary`. KHONG co collection "chapters"/"characters"/"memories"
rieng — mo hinh du lieu hien tai (xay o `translation_domain.py`, da chay that
qua 1500+ test) gom chuong/tom-tat trong CHINH `TranslationProject`
(`translated_chapters`/`chapter_summaries`, mang song song voi chi so chuong)
va "nhan vat" la MOT loai (`category=character`) trong `translation_glossary`
— tach chung thanh collection rieng se doi ca tang service dang chay tot, mot
viec lon hon pham vi "them kho ben vung" cua lan sua nay.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from server.adapters import NotFoundError, PermissionDenied
from server.config import AppwriteSettings
from server.translation import (
    GenrePreset,
    GlossaryCategory,
    NamingMode,
    QualityMode,
    TranslationJobStatus,
)
from server.translation_domain import TranslationJob, TranslationProject
from server.translation import GlossaryEntry

COL_PROJECTS = "translation_projects"
COL_JOBS = "translation_jobs"
COL_GLOSSARY = "translation_glossary"

#: Ten thuoc tinh THAT SU muon luu cho tung collection — cung vai tro voi
#: `PERSISTED_FIELDS` o `appwrite_store.py`, nhung tach rieng: doi schema ben
#: do KHONG duoc anh huong toi day va nguoc lai.
_PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_PROJECTS: (
        "project_id", "owner_id", "title", "source_text", "source_language",
        "target_language", "genre", "naming_mode", "quality_mode",
        "custom_instruction", "source_filename", "chapter_summaries",
        "translated_chapters", "imported_to_novel_id", "created_at",
        "updated_at",
    ),
    COL_JOBS: (
        "job_id", "project_id", "owner_id", "status", "current_chapter",
        "total_chapters", "current_chapter_done_segments",
        "current_chapter_total_segments", "retry_count", "error",
        "created_at", "updated_at", "finished_at",
    ),
    COL_GLOSSARY: (
        "term_id", "project_id", "category", "original", "translated",
        "aliases", "note", "locked", "created_at", "updated_at",
    ),
}

REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def q_offset(count: int) -> str:
    return json.dumps({"method": "offset", "values": [int(count)]})


def _project_to_row(p: TranslationProject) -> Dict[str, Any]:
    return {
        "project_id": p.project_id,
        "owner_id": p.owner_id,
        "title": p.title,
        "source_text": p.source_text,
        "source_language": p.source_language,
        "target_language": p.target_language,
        "genre": p.genre.value,
        "naming_mode": p.naming_mode.value,
        "quality_mode": p.quality_mode.value,
        "custom_instruction": p.custom_instruction,
        "source_filename": p.source_filename,
        "chapter_summaries": list(p.chapter_summaries),
        "translated_chapters": list(p.translated_chapters),
        "imported_to_novel_id": p.imported_to_novel_id,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _project_from_row(row: Dict[str, Any]) -> TranslationProject:
    try:
        genre = GenrePreset(str(row.get("genre") or "auto"))
    except ValueError:
        genre = GenrePreset.AUTO
    try:
        naming = NamingMode(str(row.get("naming_mode") or "auto"))
    except ValueError:
        naming = NamingMode.AUTO
    try:
        quality = QualityMode(str(row.get("quality_mode") or "can_bang"))
    except ValueError:
        quality = QualityMode.CAN_BANG
    return TranslationProject(
        project_id=str(row.get("project_id") or row.get("$id") or ""),
        owner_id=str(row.get("owner_id") or ""),
        title=str(row.get("title") or ""),
        source_text=str(row.get("source_text") or ""),
        source_language=str(row.get("source_language") or "zh"),
        target_language=str(row.get("target_language") or "vi"),
        genre=genre,
        naming_mode=naming,
        quality_mode=quality,
        custom_instruction=str(row.get("custom_instruction") or ""),
        source_filename=str(row.get("source_filename") or ""),
        chapter_summaries=list(row.get("chapter_summaries") or []),
        translated_chapters=list(row.get("translated_chapters") or []),
        imported_to_novel_id=str(row.get("imported_to_novel_id") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _job_to_row(j: TranslationJob) -> Dict[str, Any]:
    return {
        "job_id": j.job_id,
        "project_id": j.project_id,
        "owner_id": j.owner_id,
        "status": j.status.value,
        "current_chapter": j.current_chapter,
        "total_chapters": j.total_chapters,
        "current_chapter_done_segments": j.current_chapter_done_segments,
        "current_chapter_total_segments": j.current_chapter_total_segments,
        "retry_count": j.retry_count,
        "error": j.error,
        "created_at": j.created_at,
        "updated_at": j.updated_at,
        "finished_at": j.finished_at,
    }


def _job_from_row(row: Dict[str, Any]) -> TranslationJob:
    try:
        status = TranslationJobStatus(str(row.get("status") or "queued"))
    except ValueError:
        status = TranslationJobStatus.QUEUED
    return TranslationJob(
        job_id=str(row.get("job_id") or row.get("$id") or ""),
        project_id=str(row.get("project_id") or ""),
        owner_id=str(row.get("owner_id") or ""),
        status=status,
        current_chapter=int(row.get("current_chapter") or 0),
        total_chapters=int(row.get("total_chapters") or 0),
        current_chapter_done_segments=int(
            row.get("current_chapter_done_segments") or 0),
        current_chapter_total_segments=int(
            row.get("current_chapter_total_segments") or 0),
        retry_count=int(row.get("retry_count") or 0),
        error=str(row.get("error") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        finished_at=str(row.get("finished_at") or ""),
    )


def _glossary_to_row(e: GlossaryEntry) -> Dict[str, Any]:
    return {
        "term_id": e.term_id,
        "project_id": e.project_id,
        "category": e.category.value,
        "original": e.original,
        "translated": e.translated,
        "aliases": list(e.aliases),
        "note": e.note,
        "locked": e.locked,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }


def _glossary_from_row(row: Dict[str, Any]) -> GlossaryEntry:
    try:
        category = GlossaryCategory(str(row.get("category") or "other"))
    except ValueError:
        category = GlossaryCategory.OTHER
    return GlossaryEntry(
        term_id=str(row.get("term_id") or row.get("$id") or ""),
        project_id=str(row.get("project_id") or ""),
        category=category,
        original=str(row.get("original") or ""),
        translated=str(row.get("translated") or ""),
        aliases=list(row.get("aliases") or []),
        note=str(row.get("note") or ""),
        locked=bool(row.get("locked") or False),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


class AppwriteTranslationStore:
    """Ban Appwrite cua `MockTranslationStore` — cung giao dien, KHAC ha tang."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        """:param client: tiem client gia lap cho test (xem
        `test_translation_contract.py`), thay vi mo ket noi httpx that."""
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho dịch. Cần cả bốn biến "
                "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, "
                "APPWRITE_DATABASE_ID.")
        self._settings = settings
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client
        self._attrs_cache: Dict[str, Set[str]] = {}
        self._pool: Optional[httpx.Client] = None
        #: Khoa CUC BO — giong `MockTranslationStore`, tranh dua request khi
        #: nhieu thread cung sua mot job (worker + request web).
        self._lock = threading.RLock()

    # -- ha tang REST ---------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
            "X-Appwrite-Key": self._settings.api_key,
        }

    def _http(self) -> httpx.Client:
        if self._pool is None:
            self._pool = httpx.Client(timeout=REQUEST_TIMEOUT)
        return self._pool

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        if self._client is not None:
            return self._client.request(method, url, json=payload, params=params,
                                        headers=self._headers())
        try:
            response = self._http().request(method, url, json=payload,
                                            params=params, headers=self._headers())
        except httpx.HTTPError as exc:
            raise NotFoundError(f"Không kết nối được Appwrite: {exc}") from exc
        if response.status_code == 404:
            raise NotFoundError("Không tìm thấy bản ghi.")
        if response.status_code >= 400:
            message = f"Appwrite trả về lỗi {response.status_code}."
            try:
                body = response.json()
                if isinstance(body, dict) and body.get("message"):
                    message = str(body["message"])
            except Exception:
                pass
            raise NotFoundError(message)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _docs(self, collection: str) -> str:
        return f"/v1/databases/{self._db}/collections/{collection}/documents"

    @staticmethod
    def _owner_permissions(owner_id: str) -> List[str]:
        # CHI DOC cho chu so huu — moi ghi di qua backend bang API key, cung
        # ly do voi `AppwriteMetadataStore._owner_permissions`. `owner_id`
        # rong (glossary — khong co truong chu so huu rieng, quyen kiem o
        # tang service qua project) nghia la KHONG cap quyen doc truc tiep
        # nao ca: frontend khong bao gio goi thang Appwrite cho subsystem
        # nay, moi duong deu qua backend bang API key nen dieu do van an toan.
        if not owner_id:
            return []
        return [f'read("user:{owner_id}")']

    def _supported_fields(self, collection: str) -> Optional[Set[str]]:
        cached = self._attrs_cache.get(collection)
        if cached is not None:
            return cached or None
        try:
            meta = self._call(
                "GET", f"/v1/databases/{self._db}/collections/{collection}")
        except Exception:
            return None
        names = {a.get("key") for a in (meta.get("attributes") or [])
                 if a.get("key")}
        self._attrs_cache[collection] = names
        return names or None

    def _writable(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        allowed = _PERSISTED_FIELDS.get(collection)
        fields = ({k: v for k, v in data.items() if k in allowed}
                  if allowed is not None else dict(data))
        available = self._supported_fields(collection)
        if available is None:
            return fields
        return {k: v for k, v in fields.items() if k in available}

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any],
               owner_id: str) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": self._writable(collection, data),
            "permissions": self._owner_permissions(owner_id),
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _update(self, collection: str, doc_id: str,
               data: Dict[str, Any]) -> Dict[str, Any]:
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}",
                          payload={"data": self._writable(collection, data)})

    def _delete(self, collection: str, doc_id: str) -> None:
        self._call("DELETE", f"{self._docs(collection)}/{doc_id}")

    def _list_all(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        offset = 0
        while True:
            data = self._call("GET", self._docs(collection),
                              params={"queries[]": queries + [
                                  q_limit(PAGE_SIZE), q_offset(offset)]})
            page = list(data.get("documents") or [])
            out.extend(page)
            if len(page) < PAGE_SIZE:
                return out
            offset += PAGE_SIZE

    # ======================================================== du an

    def create_project(self, project: TranslationProject) -> TranslationProject:
        self._create(COL_PROJECTS, project.project_id, _project_to_row(project),
                    project.owner_id)
        return project

    def get_project(self, project_id: str) -> TranslationProject:
        return _project_from_row(self._get(COL_PROJECTS, project_id))

    def owned_project(self, project_id: str, owner_id: str) -> TranslationProject:
        p = self.get_project(project_id)
        if p.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu dự án dịch này.")
        return p

    def save_project(self, project: TranslationProject) -> TranslationProject:
        self._update(COL_PROJECTS, project.project_id, _project_to_row(project))
        return project

    def list_projects(self, owner_id: str) -> List[TranslationProject]:
        rows = self._list_all(COL_PROJECTS, [
            q_equal("owner_id", owner_id), q_order_desc("created_at")])
        return [_project_from_row(r) for r in rows]

    # ======================================================== job

    def create_job(self, job: TranslationJob) -> TranslationJob:
        self._create(COL_JOBS, job.job_id, _job_to_row(job), job.owner_id)
        return job

    def get_job(self, job_id: str) -> TranslationJob:
        return _job_from_row(self._get(COL_JOBS, job_id))

    def owned_job(self, job_id: str, owner_id: str) -> TranslationJob:
        j = self.get_job(job_id)
        if j.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu job dịch này.")
        return j

    def save_job(self, job: TranslationJob) -> TranslationJob:
        self._update(COL_JOBS, job.job_id, _job_to_row(job))
        return job

    def active_job_for_project(self, project_id: str) -> Optional[TranslationJob]:
        rows = self._list_all(COL_JOBS, [q_equal("project_id", project_id)])
        for row in rows:
            j = _job_from_row(row)
            if j.status not in (TranslationJobStatus.COMPLETED,
                                TranslationJobStatus.FAILED,
                                TranslationJobStatus.CANCELLED):
                return j
        return None

    def jobs_for_project(self, project_id: str) -> List[TranslationJob]:
        rows = self._list_all(COL_JOBS, [
            q_equal("project_id", project_id), q_order_desc("created_at")])
        return [_job_from_row(r) for r in rows]

    # ======================================================== glossary

    def add_glossary_entry(self, entry: GlossaryEntry) -> GlossaryEntry:
        # KHONG co owner_id rieng tren glossary — quyen doc gan theo project
        # thong qua tang service (`owned_project` da kiem TRUOC khi goi day).
        self._create(COL_GLOSSARY, entry.term_id, _glossary_to_row(entry),
                    owner_id="")
        return entry

    def get_glossary_entry(self, project_id: str, term_id: str) -> GlossaryEntry:
        row = self._get(COL_GLOSSARY, term_id)
        entry = _glossary_from_row(row)
        if entry.project_id != project_id:
            raise NotFoundError("Không tìm thấy thuật ngữ.")
        return entry

    def save_glossary_entry(self, entry: GlossaryEntry) -> GlossaryEntry:
        self._update(COL_GLOSSARY, entry.term_id, _glossary_to_row(entry))
        return entry

    def delete_glossary_entry(self, project_id: str, term_id: str) -> None:
        try:
            entry = self.get_glossary_entry(project_id, term_id)
        except NotFoundError:
            return
        self._delete(COL_GLOSSARY, entry.term_id)

    def list_glossary(self, project_id: str) -> List[GlossaryEntry]:
        rows = self._list_all(COL_GLOSSARY, [q_equal("project_id", project_id)])
        ra = [_glossary_from_row(r) for r in rows]
        return sorted(ra, key=lambda e: e.original)
