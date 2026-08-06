"""
Kho metadata tren Appwrite Databases.

Cung giao dien voi `MockMetadataStore` nen `main.py` khong phai biet dang chay
che do nao.

NGUYEN TAC:
- Moi truy van deu kiem tra QUYEN SO HUU o phia server. Khong bao gio tin
  `user_id` do client gui len - chu so huu luon lay tu token da xac minh.
- Document permission duoc gan cho dung chu so huu; truyen da xuat ban moi
  them quyen doc cong khai.
- API key CHI dung o phia server.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Dict, List, Optional

import httpx

from server.adapters import NotFoundError, PermissionDenied
from server.config import AppwriteSettings
from server.domain import (
    AudioTrack,
    Chapter,
    JobStatus,
    Novel,
    PublishState,
    TtsJob,
    now_iso,
)

COL_NOVELS = "novels"
COL_CHAPTERS = "chapters"
COL_JOBS = "tts_jobs"
COL_TRACKS = "audio_tracks"

REQUEST_TIMEOUT = 15.0

#: Thuoc tinh THUC SU ton tai trong schema Appwrite (xem docs/APPWRITE_SCHEMA.md
#: va scripts/setup_appwrite.py).
#:
#: `to_dict()` cua tang domain la hinh dang cua API, khong phai hinh dang luu
#: tru: no kem ca cac truong TINH TOAN (`char_count` cua Chapter, `progress`
#: cua TtsJob) ma frontend can. Gui thang len Appwrite thi bi tu choi:
#:     Invalid document structure: Unknown attribute: "char_count"
#: Loc o day de hai hinh dang do tach bach han.
PERSISTED_FIELDS: Dict[str, tuple] = {
    COL_NOVELS: (
        "novel_id", "owner_id", "title", "description", "cover_key",
        "state", "tags", "created_at", "updated_at",
    ),
    COL_CHAPTERS: (
        "chapter_id", "novel_id", "owner_id", "title", "content",
        "order_index", "state", "created_at", "updated_at",
    ),
    COL_JOBS: (
        "job_id", "owner_id", "chapter_id", "voice_id", "content_hash",
        "status", "output_key", "error_kind", "error_message",
        "total_parts", "done_parts", "rate", "chunk_chars",
        "created_at", "started_at", "finished_at",
    ),
    COL_TRACKS: (
        "track_id", "chapter_id", "owner_id", "voice_id", "object_key",
        "content_hash", "duration_seconds", "size_bytes", "created_at",
    ),
}


# -----------------------------------------------------------------------------
# Query
# -----------------------------------------------------------------------------
#
# Appwrite tu ban 1.5 CHI nhan query dang JSON, gui qua tham so `queries[]`.
# Cu phap chuoi cu (`equal("owner_id", ["x"])`) bi tra ve 400:
#     Invalid query: Syntax error
# Da kiem chung tren Appwrite Cloud 1.9.6.
#
# Ma hoa bang `json.dumps` con loai bo luon nguy co QUERY INJECTION: truoc day
# gia tri duoc noi suy thang vao chuoi, mot `owner_id` chua dau nháy co the pha
# vo cau truc query.


def q_equal(attribute: str, *values: Any) -> str:
    return json.dumps({"method": "equal", "attribute": attribute,
                       "values": list(values)})


def q_order_asc(attribute: str) -> str:
    return json.dumps({"method": "orderAsc", "attribute": attribute})


def q_order_desc(attribute: str) -> str:
    return json.dumps({"method": "orderDesc", "attribute": attribute})


def q_limit(count: int) -> str:
    return json.dumps({"method": "limit", "values": [int(count)]})


def persistable(collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Chi giu lai nhung truong that su co trong schema cua collection do."""
    allowed = PERSISTED_FIELDS.get(collection)
    if allowed is None:
        return dict(data)
    return {key: value for key, value in data.items() if key in allowed}


class AppwriteMetadataStore:
    """Novels / chapters / tts_jobs / audio_tracks tren Appwrite."""

    mode = "appwrite"

    def __init__(self, settings: AppwriteSettings, client: Any = None):
        """:param client: cho phep test tiem client gia lap thay cho httpx."""
        from server.appwrite_adapter import AppwriteConfigError

        if not settings.configured:
            raise AppwriteConfigError(
                "Cấu hình Appwrite chưa đủ cho kho metadata. Cần cả bốn biến "
                "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, "
                "APPWRITE_DATABASE_ID."
            )
        self._settings = settings
        # `api_base` da bo `/v1` o cuoi neu co - moi path duoi day tu them `/v1`
        self._endpoint = settings.api_base
        self._db = settings.database_id
        self._client = client

    # -- ha tang --------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        # API key CHI o phia server, khong bao gio ra khoi tien trinh nay
        return {
            "Content-Type": "application/json",
            "X-Appwrite-Project": self._settings.project_id,
            "X-Appwrite-Key": self._settings.api_key,
        }

    def _call(self, method: str, path: str, *, payload: Optional[Dict] = None,
              params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._endpoint}{path}"
        if self._client is not None:
            return self._client.request(method, url, json=payload, params=params,
                                        headers=self._headers())
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.request(method, url, json=payload, params=params,
                                          headers=self._headers())
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
    def _owner_permissions(owner_id: str, public_read: bool = False) -> List[str]:
        """
        Quyen tren document: CHI DOC. Khong client nao duoc ghi thang.

        Truoc day co cap them `update`/`delete` cho chu so huu. Nhung cac
        collection nay chua toan truong do SERVER quyet dinh:

        - `novels.state`      - xuat ban hay chua
        - `tts_jobs.status`   - va `output_key`
        - `audio_tracks.object_key` - tro toi file audio nao

        Nguoi dung nam session/JWT hop le goi thang Appwrite API duoc. Voi
        quyen `update` tren `audio_tracks` cua chinh minh, ho chi can doi
        `object_key` sang key cua nguoi khac la `/api/audio/{chapter}` se phuc
        vu audio cua nguoi do - vuot qua ca `_may_listen()`.

        Moi thao tac ghi deu di qua backend bang API key (API key bo qua
        document permission), nen bo `update`/`delete` khong hong chuc nang.

        `public_read` chi them quyen DOC cong khai cho truyen da xuat ban.
        """
        perms = [f'read("user:{owner_id}")']
        if public_read:
            perms.append('read("any")')
        return perms

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any],
                owner_id: str, public_read: bool = False) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": persistable(collection, data),
            "permissions": self._owner_permissions(owner_id, public_read),
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _list(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        data = self._call("GET", self._docs(collection), params={"queries[]": queries})
        return list(data.get("documents") or [])

    def _update(self, collection: str, doc_id: str, data: Dict[str, Any],
                permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"data": persistable(collection, data)}
        if permissions is not None:
            payload["permissions"] = permissions
        return self._call("PATCH", f"{self._docs(collection)}/{doc_id}", payload=payload)

    # -- novel ---------------------------------------------------------------

    def create_novel(self, novel: Novel) -> Novel:
        self._create(COL_NOVELS, novel.novel_id, novel.to_dict(), novel.owner_id)
        return novel

    def get_novel(self, novel_id: str) -> Novel:
        return _novel_from_doc(self._get(COL_NOVELS, novel_id))

    def owned_novel(self, novel_id: str, owner_id: str) -> Novel:
        novel = self.get_novel(novel_id)
        if novel.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu tiểu thuyết này.")
        return novel

    def list_novels(self, owner_id: Optional[str] = None,
                    published_only: bool = False) -> List[Novel]:
        queries: List[str] = [q_order_desc("created_at")]
        if owner_id:
            queries.append(q_equal("owner_id", owner_id))
        if published_only:
            queries.append(q_equal("state", "published"))
        return [_novel_from_doc(d) for d in self._list(COL_NOVELS, queries)]

    def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
        """
        Xuat ban: cap nhat trang thai VA mo quyen doc cong khai.

        NGUYEN TU: Appwrite cho phep PATCH ca `data` lan `permissions` trong
        MOT request, nen khong ton tai cua so ma trang thai da doi con quyen
        thi chua - hoac ca hai cung doi, hoac khong gi doi ca.

        Quyen sau khi xuat ban: cong khai chi duoc `read`. `update`/`delete`
        VAN chi thuoc chu so huu - khong bao gio mo quyen sua cho public.

        IDEMPOTENT: goi lai tren novel da `published` van gui lai dung PATCH
        do. PATCH khong tao ban ghi trung, va viec ap lai quyen giup TU CHUA
        neu quyen bi lech vi mot lan sua tay tren console Appwrite.
        """
        current = self.owned_novel(novel_id, owner_id)    # 404 / 403 o day

        # Dung `replace()` thay vi doi tai cho: chi cong bo ban `published`
        # SAU KHI PATCH thanh cong. Neu `_update` nem loi thi khong co object
        # nao mang trang thai `published` duoc tra ve.
        published = replace(
            current, state=PublishState.PUBLISHED, updated_at=now_iso()
        )
        self._update(
            COL_NOVELS, published.novel_id,
            {"state": published.state.value, "updated_at": published.updated_at},
            permissions=self._owner_permissions(published.owner_id, public_read=True),
        )
        return published

    # -- chapter -------------------------------------------------------------

    def create_chapter(self, chapter: Chapter) -> Chapter:
        self._create(COL_CHAPTERS, chapter.chapter_id, chapter.to_dict(),
                     chapter.owner_id)
        return chapter

    def get_chapter(self, chapter_id: str) -> Chapter:
        return _chapter_from_doc(self._get(COL_CHAPTERS, chapter_id))

    def owned_chapter(self, chapter_id: str, owner_id: str) -> Chapter:
        chapter = self.get_chapter(chapter_id)
        if chapter.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu chương này.")
        return chapter

    def list_chapters(self, novel_id: str) -> List[Chapter]:
        return [
            _chapter_from_doc(d)
            for d in self._list(COL_CHAPTERS, [
                q_equal("novel_id", novel_id),
                q_order_asc("order_index"),
            ])
        ]

    # -- job -----------------------------------------------------------------

    def create_job(self, job: TtsJob) -> TtsJob:
        self._create(COL_JOBS, job.job_id, job.to_dict(), job.owner_id)
        return job

    def get_job(self, job_id: str) -> TtsJob:
        return _job_from_doc(self._get(COL_JOBS, job_id))

    def owned_job(self, job_id: str, owner_id: str) -> TtsJob:
        job = self.get_job(job_id)
        if job.owner_id != owner_id:
            raise PermissionDenied("Bạn không sở hữu job này.")
        return job

    def find_job_by_fingerprint(self, owner_id: str, chapter_id: str,
                                fingerprint: str) -> Optional[TtsJob]:
        """Idempotency: dua vao index to hop owner_id + chapter_id + content_hash."""
        docs = self._list(COL_JOBS, [
            q_equal("owner_id", owner_id),
            q_equal("chapter_id", chapter_id),
            q_equal("content_hash", fingerprint),
        ])
        for doc in docs:
            job = _job_from_doc(doc)
            if job.status != JobStatus.FAILED:
                return job
        return None

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None) -> List[TtsJob]:
        queries = [q_equal("owner_id", owner_id), q_order_desc("created_at")]
        if chapter_id:
            queries.append(q_equal("chapter_id", chapter_id))
        return [_job_from_doc(d) for d in self._list(COL_JOBS, queries)]

    def save_job(self, job: TtsJob) -> TtsJob:
        """Ghi lai trang thai job sau khi chay xong."""
        self._update(COL_JOBS, job.job_id, job.to_dict())
        return job

    # -- audio track ---------------------------------------------------------

    def create_track(self, track: AudioTrack) -> AudioTrack:
        self._create(COL_TRACKS, track.track_id, track.to_dict(), track.owner_id)
        return track

    def track_for_chapter(self, chapter_id: str) -> Optional[AudioTrack]:
        docs = self._list(COL_TRACKS, [
            q_equal("chapter_id", chapter_id),
            q_order_desc("created_at"),
            q_limit(1),
        ])
        return _track_from_doc(docs[0]) if docs else None


# -----------------------------------------------------------------------------
# Doi document -> dataclass
# -----------------------------------------------------------------------------


def _novel_from_doc(doc: Dict[str, Any]) -> Novel:
    return Novel(
        novel_id=str(doc.get("novel_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        description=str(doc.get("description") or ""),
        cover_key=doc.get("cover_key"),
        state=PublishState(str(doc.get("state") or "draft")),
        tags=list(doc.get("tags") or []),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _chapter_from_doc(doc: Dict[str, Any]) -> Chapter:
    return Chapter(
        chapter_id=str(doc.get("chapter_id") or doc.get("$id") or ""),
        novel_id=str(doc.get("novel_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        title=str(doc.get("title") or ""),
        content=str(doc.get("content") or ""),
        order_index=int(doc.get("order_index") or 1),
        state=PublishState(str(doc.get("state") or "draft")),
        created_at=str(doc.get("created_at") or ""),
        updated_at=str(doc.get("updated_at") or ""),
    )


def _job_from_doc(doc: Dict[str, Any]) -> TtsJob:
    return TtsJob(
        job_id=str(doc.get("job_id") or doc.get("$id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        chapter_id=str(doc.get("chapter_id") or ""),
        voice_id=str(doc.get("voice_id") or ""),
        content_hash=str(doc.get("content_hash") or ""),
        status=JobStatus(str(doc.get("status") or "pending")),
        output_key=doc.get("output_key"),
        error_kind=doc.get("error_kind"),
        error_message=str(doc.get("error_message") or ""),
        total_parts=int(doc.get("total_parts") or 0),
        done_parts=int(doc.get("done_parts") or 0),
        rate=str(doc.get("rate") or "1.0"),
        chunk_chars=int(doc.get("chunk_chars") or 2000),
        created_at=str(doc.get("created_at") or ""),
        started_at=doc.get("started_at"),
        finished_at=doc.get("finished_at"),
    )


def _track_from_doc(doc: Dict[str, Any]) -> AudioTrack:
    return AudioTrack(
        track_id=str(doc.get("track_id") or doc.get("$id") or ""),
        chapter_id=str(doc.get("chapter_id") or ""),
        owner_id=str(doc.get("owner_id") or ""),
        voice_id=str(doc.get("voice_id") or ""),
        object_key=str(doc.get("object_key") or ""),
        content_hash=str(doc.get("content_hash") or ""),
        duration_seconds=float(doc.get("duration_seconds") or 0.0),
        size_bytes=int(doc.get("size_bytes") or 0),
        created_at=str(doc.get("created_at") or ""),
    )
