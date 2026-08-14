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
from dataclasses import replace
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from server.adapters import NotFoundError, PermissionDenied
from server.config import AppwriteSettings
from server.domain import now_iso
from server.translation import (
    TERMINAL_STATUSES,
    GenrePreset,
    GlossaryCategory,
    NamingMode,
    QualityMode,
    TranslationJobStatus,
)
from server.translation_domain import (
    ProviderConnection,
    TranslationJob,
    TranslationProject,
    TranslationVersion,
    id_ket_noi_provider,
)
from server.translation import GlossaryEntry

COL_PROJECTS = "translation_projects"
COL_JOBS = "translation_jobs"
COL_GLOSSARY = "translation_glossary"
#: Khoa cua viec nhan job dich — cung vai tro voi `job_claims` cua TTS: MOT
#: hang cho MOI lan thu cua MOI job, id tat dinh `{job_id}-{attempt}`. Chi
#: ton tai vi tinh DUY NHAT cua rowId ma Appwrite cuong che.
COL_JOB_CLAIMS = "translation_job_claims"
#: Lich su ban dich (Part O) — CONG THEM, khong doi 4 collection cu.
COL_VERSIONS = "translation_versions"
#: Ket noi provider AI ca nhan (V5.1 BYOK) — CONG THEM, collection THU SAU.
COL_PROVIDER_CONNECTIONS = "translation_provider_connections"

#: Ten thuoc tinh THAT SU muon luu cho tung collection — cung vai tro voi
#: `PERSISTED_FIELDS` o `appwrite_store.py`, nhung tach rieng: doi schema ben
#: do KHONG duoc anh huong toi day va nguoc lai.
_PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_PROJECTS: (
        "project_id", "owner_id", "title", "source_text", "source_language",
        "target_language", "genre", "naming_mode", "quality_mode",
        "custom_instruction", "source_filename", "chapter_summaries",
        "translated_chapters", "imported_to_novel_id", "chapter_warnings",
        "provider_mode", "selected_provider_id", "allow_fallback",
        "prefer_personal_provider",
        "created_at", "updated_at",
    ),
    COL_JOBS: (
        "job_id", "project_id", "owner_id", "status", "current_chapter",
        "total_chapters", "current_chapter_done_segments",
        "current_chapter_total_segments", "current_pass", "attempts",
        "lease_owner", "lease_expires_at", "error", "waiting_retry_at",
        "waiting_reason", "waiting_action",
        "created_at", "updated_at", "finished_at",
    ),
    COL_GLOSSARY: (
        "term_id", "project_id", "category", "original", "translated",
        "aliases", "note", "locked", "created_at", "updated_at",
    ),
    COL_VERSIONS: (
        "version_id", "project_id", "chapter_index", "paragraph_index",
        "operation", "pass_type", "previous_text", "new_text", "actor_id",
        "provider_id", "model_id", "created_at",
    ),
    COL_PROVIDER_CONNECTIONS: (
        "connection_id", "user_id", "provider_id", "encrypted_secret",
        "last4", "status", "selected_model", "created_at", "updated_at",
        "last_verified_at",
    ),
}

REQUEST_TIMEOUT = 30.0
PAGE_SIZE = 100
#: Xem `TRANSACTION_TTL_SECONDS` o `appwrite_store.py` — cung gia tri, tach
#: hang so rieng vi module nay HOAN TOAN doc lap.
TRANSACTION_TTL_SECONDS = 60


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
        # `chapter_warnings` la List[List[str]] — Appwrite khong co kieu
        # mang long nhau, nen ma hoa MOI chuong thanh MOT chuoi JSON, luu
        # nhu mot string[] (khop chi so voi `translated_chapters`).
        "chapter_warnings": [json.dumps(w) for w in p.chapter_warnings],
        "provider_mode": p.provider_mode,
        "selected_provider_id": p.selected_provider_id,
        "allow_fallback": p.allow_fallback,
        "prefer_personal_provider": p.prefer_personal_provider,
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
        chapter_warnings=[_giai_ma_canh_bao(w)
                         for w in (row.get("chapter_warnings") or [])],
        provider_mode=str(row.get("provider_mode") or "auto"),
        selected_provider_id=str(row.get("selected_provider_id") or ""),
        allow_fallback=bool(row.get("allow_fallback", True)),
        prefer_personal_provider=bool(row.get("prefer_personal_provider", False)),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _giai_ma_canh_bao(muc: Any) -> List[str]:
    """Giai ma MOT phan tu cua `chapter_warnings` — xem ghi chu ma hoa o
    `_project_to_row`. Doc hong (JSON sai dinh dang) -> rong, khong nem loi."""
    if isinstance(muc, list):
        return list(muc)
    try:
        gia_tri = json.loads(muc)
    except (TypeError, ValueError):
        return []
    return gia_tri if isinstance(gia_tri, list) else []


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
        "current_pass": j.current_pass,
        "attempts": j.attempts,
        "lease_owner": j.lease_owner,
        "lease_expires_at": j.lease_expires_at,
        "error": j.error,
        "waiting_retry_at": j.waiting_retry_at,
        "waiting_reason": j.waiting_reason,
        "waiting_action": j.waiting_action,
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
        current_pass=str(row.get("current_pass") or ""),
        attempts=int(row.get("attempts") or 0),
        lease_owner=str(row.get("lease_owner") or ""),
        lease_expires_at=str(row.get("lease_expires_at") or ""),
        error=str(row.get("error") or ""),
        waiting_retry_at=str(row.get("waiting_retry_at") or ""),
        waiting_reason=str(row.get("waiting_reason") or ""),
        waiting_action=str(row.get("waiting_action") or ""),
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


def _version_to_row(v: TranslationVersion) -> Dict[str, Any]:
    return {
        "version_id": v.version_id,
        "project_id": v.project_id,
        "chapter_index": v.chapter_index,
        "paragraph_index": v.paragraph_index if v.paragraph_index is not None else -1,
        "operation": v.operation,
        "pass_type": v.pass_type,
        "previous_text": v.previous_text,
        "new_text": v.new_text,
        "actor_id": v.actor_id,
        "provider_id": v.provider_id,
        "model_id": v.model_id,
        "created_at": v.created_at,
    }


def _version_from_row(row: Dict[str, Any]) -> TranslationVersion:
    doan_idx = int(row.get("paragraph_index") if row.get("paragraph_index") is not None else -1)
    return TranslationVersion(
        version_id=str(row.get("version_id") or row.get("$id") or ""),
        project_id=str(row.get("project_id") or ""),
        chapter_index=int(row.get("chapter_index") or 0),
        paragraph_index=None if doan_idx < 0 else doan_idx,
        operation=str(row.get("operation") or ""),
        pass_type=str(row.get("pass_type") or ""),
        previous_text=str(row.get("previous_text") or ""),
        new_text=str(row.get("new_text") or ""),
        actor_id=str(row.get("actor_id") or ""),
        provider_id=str(row.get("provider_id") or ""),
        model_id=str(row.get("model_id") or ""),
        created_at=str(row.get("created_at") or ""),
    )


def _connection_to_row(c: ProviderConnection) -> Dict[str, Any]:
    return {
        "connection_id": c.connection_id,
        "user_id": c.user_id,
        "provider_id": c.provider_id,
        "encrypted_secret": c.encrypted_secret,
        "last4": c.last4,
        "status": c.status,
        "selected_model": c.selected_model,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
        "last_verified_at": c.last_verified_at,
    }


def _connection_from_row(row: Dict[str, Any]) -> ProviderConnection:
    return ProviderConnection(
        user_id=str(row.get("user_id") or ""),
        provider_id=str(row.get("provider_id") or ""),
        encrypted_secret=str(row.get("encrypted_secret") or ""),
        last4=str(row.get("last4") or ""),
        status=str(row.get("status") or "unknown"),
        selected_model=str(row.get("selected_model") or ""),
        connection_id=str(row.get("connection_id") or row.get("$id") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        last_verified_at=str(row.get("last_verified_at") or ""),
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
            if j.status not in TERMINAL_STATUSES:
                return j
        return None

    def jobs_for_project(self, project_id: str) -> List[TranslationJob]:
        rows = self._list_all(COL_JOBS, [
            q_equal("project_id", project_id), q_order_desc("created_at")])
        return [_job_from_row(r) for r in rows]

    def list_jobs_by_status(self, status: TranslationJobStatus) -> List[TranslationJob]:
        rows = self._list_all(COL_JOBS, [
            q_equal("status", status.value), q_order_asc("created_at")])
        return [_job_from_row(r) for r in rows]

    # ======================================================== claim/lease
    #
    # CUNG CO CHE voi `AppwriteMetadataStore` (TTS, `server/appwrite_store.py`)
    # — Transactions API that su (`/v1/tablesdb/transactions`), KHONG doc-
    # roi-ghi-lai. Claim gom HAI thao tac trong CUNG mot transaction: tao hang
    # khoa co id tat dinh `{job_id}-{attempt}` (tinh duy nhat do database
    # cuong che) + cap nhat job row (status/attempts/lease). Worker thua co
    # commit HONG HAN, khong ghi duoc gi ca.
    #
    # KHONG co gia lap REST cho Transactions API trong bo test (xem
    # `test_translation_contract.py`) — cung ly do voi TTS: co che nay da
    # duoc xac minh THAT tren Appwrite Cloud (xem docstring
    # `AppwriteMetadataStore.claim_job`), va mot ban gia lap tu viet cho rieng
    # transaction sẽ chi kiem chung LOGIC CUA CHINH MINH, khong kiem chung
    # duoc hanh vi that cua Appwrite. Test tu dong cho claim/lease/fencing
    # chay tren `MockTranslationStore` (`test_translation_worker.py`) — noi
    # do CHINH LA logic CAS duoc kiem, khong phai lop REST.

    def claim_job(self, job: TranslationJob, worker_id: str,
                 lease_expires_at: str) -> Optional[int]:
        current = self.get_job(job.job_id)
        if current.status in TERMINAL_STATUSES:
            return None
        if current.lease_is_live():
            return None

        fence = (current.attempts or 0) + 1
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
        except Exception:
            return None
        tx_id = tx.get("$id")
        if not tx_id:
            return None

        operations = [
            {"action": "create", "databaseId": self._db,
             "tableId": COL_JOB_CLAIMS, "rowId": f"{job.job_id}-{fence}",
             "data": {"job_id": job.job_id, "attempt": fence,
                      "worker_id": worker_id, "created_at": now_iso()}},
            {"action": "update", "databaseId": self._db, "tableId": COL_JOBS,
             "rowId": job.job_id,
             "data": {"status": TranslationJobStatus.ANALYZING.value,
                      "attempts": fence, "lease_owner": worker_id,
                      "lease_expires_at": lease_expires_at}},
        ]
        try:
            self._call("POST", f"/v1/tablesdb/transactions/{tx_id}/operations",
                       payload={"operations": operations})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx_id}",
                                payload={"commit": True})
        except Exception:
            return None
        return fence if result.get("status") == "committed" else None

    def renew_lease(self, job_id: str, fence: int, worker_id: str,
                    lease_expires_at: str) -> bool:
        try:
            current = self.get_job(job_id)
        except NotFoundError:
            return False
        if (current.attempts or 0) != fence or current.lease_owner != worker_id:
            return False
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [{
                           "action": "update", "databaseId": self._db,
                           "tableId": COL_JOBS, "rowId": job_id,
                           "data": {"lease_expires_at": lease_expires_at,
                                    "lease_owner": worker_id}}]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception:
            return False
        return result.get("status") == "committed"

    def save_progress(self, job_id: str, fence: int, worker_id: str,
                      **truong: Any) -> bool:
        """Ghi nhanh mot vai truong tien do — xem `MockTranslationStore.save_progress`."""
        try:
            current = self.get_job(job_id)
        except NotFoundError:
            return False
        if (current.attempts or 0) != fence or current.lease_owner != worker_id:
            return False
        data = {k: v for k, v in truong.items()
               if k in _PERSISTED_FIELDS[COL_JOBS]}
        if not data:
            return True
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [{
                           "action": "update", "databaseId": self._db,
                           "tableId": COL_JOBS, "rowId": job_id,
                           "data": data}]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception:
            # Mang chap chon: mat mot lan ghi tien do la vo hai, lan sau se
            # ghi con so moi hon.
            return False
        return result.get("status") == "committed"

    def save_job_fenced(self, job: TranslationJob, fence: int,
                        worker_id: str) -> bool:
        try:
            current = self.get_job(job.job_id)
        except NotFoundError:
            return False
        if (current.attempts or 0) != fence or current.lease_owner != worker_id:
            return False
        data = self._writable(COL_JOBS, _job_to_row(replace(job, attempts=fence)))
        try:
            tx = self._call("POST", "/v1/tablesdb/transactions",
                            payload={"ttl": TRANSACTION_TTL_SECONDS})
            self._call("POST", f"/v1/tablesdb/transactions/{tx['$id']}/operations",
                       payload={"operations": [{
                           "action": "update", "databaseId": self._db,
                           "tableId": COL_JOBS, "rowId": job.job_id,
                           "data": data}]})
            result = self._call("PATCH", f"/v1/tablesdb/transactions/{tx['$id']}",
                                payload={"commit": True})
        except Exception:
            return False
        return result.get("status") == "committed"

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

    # ======================================================== lich su ban dich (Part O)

    def add_version(self, version: TranslationVersion) -> TranslationVersion:
        self._create(COL_VERSIONS, version.version_id, _version_to_row(version),
                    owner_id="")
        return version

    def get_version(self, project_id: str, version_id: str) -> TranslationVersion:
        row = self._get(COL_VERSIONS, version_id)
        v = _version_from_row(row)
        if v.project_id != project_id:
            raise NotFoundError("Không tìm thấy phiên bản lịch sử này.")
        return v

    def list_versions(self, project_id: str,
                      chapter_index: Optional[int] = None) -> List[TranslationVersion]:
        queries = [q_equal("project_id", project_id)]
        if chapter_index is not None:
            queries.append(q_equal("chapter_index", chapter_index))
        rows = self._list_all(COL_VERSIONS, queries)
        ra = [_version_from_row(r) for r in rows]
        return sorted(ra, key=lambda v: v.created_at, reverse=True)

    # ======================================================== ket noi provider ca nhan (V5.1 BYOK)

    def save_connection(self, connection: ProviderConnection) -> ProviderConnection:
        """Upsert THAT: thu tao truoc (id tat dinh — trung id se bi Appwrite
        tu choi voi 409), khong duoc thi cap nhat. Khong doc-truoc-roi-ghi:
        tranh mot chuyen di REST thua trong duong thanh cong (lan dau)."""
        row = _connection_to_row(connection)
        # KHONG cap quyen doc truc tiep cho client (`owner_id=""` -> khong
        # permission nao) — dung nguyen tac voi glossary: MOI duong doc/ghi
        # deu qua backend bang API key, secret khong bao gio ra ngoai qua
        # Appwrite truc tiep.
        try:
            self._create(COL_PROVIDER_CONNECTIONS, connection.connection_id,
                        row, owner_id="")
        except NotFoundError:
            self._update(COL_PROVIDER_CONNECTIONS, connection.connection_id, row)
        return connection

    def get_connection(self, user_id: str, provider_id: str) -> ProviderConnection:
        muon_id = id_ket_noi_provider(user_id, provider_id)
        try:
            row = self._get(COL_PROVIDER_CONNECTIONS, muon_id)
        except NotFoundError:
            raise NotFoundError("Chưa kết nối provider này.") from None
        conn = _connection_from_row(row)
        if conn.user_id != user_id:
            raise NotFoundError("Chưa kết nối provider này.")
        return conn

    def list_connections(self, user_id: str) -> List[ProviderConnection]:
        rows = self._list_all(COL_PROVIDER_CONNECTIONS,
                              [q_equal("user_id", user_id)])
        ra = [_connection_from_row(r) for r in rows]
        return sorted(ra, key=lambda c: c.created_at)

    def delete_connection(self, user_id: str, provider_id: str) -> None:
        try:
            conn = self.get_connection(user_id, provider_id)
        except NotFoundError:
            return
        self._delete(COL_PROVIDER_CONNECTIONS, conn.connection_id)
