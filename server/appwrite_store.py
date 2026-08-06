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
        self._endpoint = settings.endpoint.rstrip("/")
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
        perms = [
            f'read("user:{owner_id}")',
            f'update("user:{owner_id}")',
            f'delete("user:{owner_id}")',
        ]
        if public_read:
            perms.append('read("any")')
        return perms

    def _create(self, collection: str, doc_id: str, data: Dict[str, Any],
                owner_id: str, public_read: bool = False) -> Dict[str, Any]:
        return self._call("POST", self._docs(collection), payload={
            "documentId": doc_id,
            "data": data,
            "permissions": self._owner_permissions(owner_id, public_read),
        })

    def _get(self, collection: str, doc_id: str) -> Dict[str, Any]:
        return self._call("GET", f"{self._docs(collection)}/{doc_id}")

    def _list(self, collection: str, queries: List[str]) -> List[Dict[str, Any]]:
        data = self._call("GET", self._docs(collection), params={"queries": queries})
        return list(data.get("documents") or [])

    def _update(self, collection: str, doc_id: str, data: Dict[str, Any],
                permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"data": data}
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
        queries: List[str] = ['orderDesc("created_at")']
        if owner_id:
            queries.append(f'equal("owner_id", ["{owner_id}"])')
        if published_only:
            queries.append('equal("state", ["published"])')
        return [_novel_from_doc(d) for d in self._list(COL_NOVELS, queries)]

    def publish_novel(self, novel: Novel) -> Novel:
        """Xuat ban: cap nhat trang thai VA mo quyen doc cong khai."""
        novel.state = PublishState.PUBLISHED
        novel.updated_at = now_iso()
        self._update(
            COL_NOVELS, novel.novel_id,
            {"state": novel.state.value, "updated_at": novel.updated_at},
            permissions=self._owner_permissions(novel.owner_id, public_read=True),
        )
        return novel

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
                f'equal("novel_id", ["{novel_id}"])',
                'orderAsc("order_index")',
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
            f'equal("owner_id", ["{owner_id}"])',
            f'equal("chapter_id", ["{chapter_id}"])',
            f'equal("content_hash", ["{fingerprint}"])',
        ])
        for doc in docs:
            job = _job_from_doc(doc)
            if job.status != JobStatus.FAILED:
                return job
        return None

    def list_jobs(self, owner_id: str, chapter_id: Optional[str] = None) -> List[TtsJob]:
        queries = [f'equal("owner_id", ["{owner_id}"])', 'orderDesc("created_at")']
        if chapter_id:
            queries.append(f'equal("chapter_id", ["{chapter_id}"])')
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
            f'equal("chapter_id", ["{chapter_id}"])',
            'orderDesc("created_at")',
            'limit(1)',
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
