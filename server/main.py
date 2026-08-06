"""
Backend FastAPI cua Fanfic Audio Studio Web.

Chay:
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --reload --port 8000

Backend giu MOI bi mat (Appwrite API key, R2 access key). Trinh duyet khong
bao gio nhan duoc credential nao.

Backend KHONG import GUI: da xac minh khong module PySide6 nao bi keo vao.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from server import tts_bridge
from server.adapters import (
    AuthError,
    LocalStorageAdapter,
    MockMetadataStore,
    NotFoundError,
    PermissionDenied,
    build_identity,
    build_storage,
)
from server.config import get_settings
from server.domain import (
    AudioTrack,
    Chapter,
    JobStatus,
    Novel,
    Profile,
    PublishState,
    TtsJob,
    job_fingerprint,
    now_iso,
)

app = FastAPI(
    title="Fanfic Audio Studio API",
    version="0.1.0",
    description="Backend MVP cho nền tảng nghe audio tiểu thuyết. Bản riêng tư, chưa thương mại.",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

identity = build_identity(settings)
storage = build_storage(settings)
store = MockMetadataStore()

#: Cac job dang chay nen. Job chay trong thread rieng de API tra ve ngay.
_job_threads: Dict[str, threading.Thread] = {}
_job_lock = threading.RLock()


# -----------------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class NovelIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    tags: List[str] = Field(default_factory=list)


class ChapterIn(BaseModel):
    novel_id: str
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    order_index: int = 1


class JobIn(BaseModel):
    chapter_id: str
    voice_id: str
    rate: str = "1.0"
    chunk_chars: int = 2000


# -----------------------------------------------------------------------------
# Xac thuc
# -----------------------------------------------------------------------------


def current_profile(authorization: Optional[str] = Header(default=None)) -> Profile:
    """Lay ho so tu Bearer token. Thieu/khong hop le -> 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return identity.profile_from_token(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc


# -----------------------------------------------------------------------------
# Healthcheck
# -----------------------------------------------------------------------------


@app.get("/api/health")
def health() -> Dict[str, Any]:
    """Trang thai backend. KHONG bao gio tra ve gia tri bi mat."""
    return {
        "status": "ok",
        "service": "fanfic-audio-api",
        "version": app.version,
        **settings.describe(),
    }


@app.get("/api/voices")
def voices() -> Dict[str, Any]:
    """Danh sach giong doc kem trang thai kha dung."""
    try:
        items = tts_bridge.list_voices(settings)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"Không nạp được danh sách giọng: {exc}"
        ) from exc
    return {"voices": items, "count": len(items)}


# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn) -> Dict[str, Any]:
    try:
        profile = identity.register(payload.email, payload.password, payload.display_name)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    token = identity.login(payload.email, payload.password)
    return {"token": token, "profile": profile.to_dict()}


@app.post("/api/auth/login")
def login(payload: LoginIn) -> Dict[str, Any]:
    try:
        token = identity.login(payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return {"token": token, "profile": identity.profile_from_token(token).to_dict()}


@app.get("/api/auth/me")
def me(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"profile": profile.to_dict()}


# -----------------------------------------------------------------------------
# Novel
# -----------------------------------------------------------------------------


@app.get("/api/novels")
def list_novels(mine: bool = False, profile: Optional[Profile] = None,
                authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Thu vien cong khai, hoac danh sach cua rieng minh khi `mine=true`."""
    if mine:
        owner = current_profile(authorization)
        items = store.list_novels(owner_id=owner.user_id)
    else:
        items = store.list_novels(published_only=True)
    return {"novels": [n.to_dict() for n in items], "count": len(items)}


@app.post("/api/novels", status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    novel = store.create_novel(Novel(
        owner_id=profile.user_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        tags=payload.tags,
    ))
    return {"novel": novel.to_dict()}


@app.get("/api/novels/{novel_id}")
def get_novel(novel_id: str) -> Dict[str, Any]:
    try:
        novel = store.get_novel(novel_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    chapters = store.list_chapters(novel_id)
    return {
        "novel": novel.to_dict(),
        "chapters": [c.to_dict(include_content=False) for c in chapters],
    }


@app.post("/api/novels/{novel_id}/publish")
def publish_novel(novel_id: str, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        novel = store.owned_novel(novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    novel.state = PublishState.PUBLISHED
    novel.updated_at = now_iso()
    return {"novel": novel.to_dict()}


# -----------------------------------------------------------------------------
# Chapter
# -----------------------------------------------------------------------------


@app.post("/api/chapters", status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        store.owned_novel(payload.novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    chapter = store.create_chapter(Chapter(
        novel_id=payload.novel_id,
        owner_id=profile.user_id,
        title=payload.title.strip(),
        content=payload.content,
        order_index=payload.order_index,
    ))
    return {"chapter": chapter.to_dict()}


@app.get("/api/chapters/{chapter_id}")
def get_chapter(chapter_id: str) -> Dict[str, Any]:
    try:
        chapter = store.get_chapter(chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    track = store.track_for_chapter(chapter_id)
    return {
        "chapter": chapter.to_dict(),
        "audio": track.to_dict() if track else None,
    }


# -----------------------------------------------------------------------------
# TTS job
# -----------------------------------------------------------------------------


def _run_job(job: TtsJob, text: str) -> None:
    """Chay job o thread nen. Moi loi deu duoc ghi vao job, khong lam sap server."""
    job.status = JobStatus.RUNNING
    job.started_at = now_iso()

    def progress(done: int, total: int) -> None:
        job.done_parts = done
        job.total_parts = total

    output_key = f"audio/{job.owner_id}/{job.chapter_id}/{job.content_hash}.mp3"
    dest = settings.var_dir / "tts" / f"{job.job_id}.mp3"

    try:
        result = tts_bridge.synthesize_chapter(
            text=text,
            voice_id=job.voice_id,
            dest=dest,
            rate=job.rate,
            chunk_chars=job.chunk_chars,
            on_progress=progress,
        )
        # Dua file vao kho roi moi danh dau hoan tat
        if isinstance(storage, LocalStorageAdapter):
            storage.put_file(output_key, dest)
        else:  # pragma: no cover - duong di cua R2 o Moc 4
            storage.put(output_key, dest.read_bytes())

        job.output_key = output_key
        job.total_parts = result["total_parts"]
        job.done_parts = result["total_parts"]
        job.status = JobStatus.COMPLETED

        store.create_track(AudioTrack(
            chapter_id=job.chapter_id,
            owner_id=job.owner_id,
            voice_id=job.voice_id,
            object_key=output_key,
            content_hash=job.content_hash,
            size_bytes=result["size_bytes"],
        ))
    except tts_bridge.TtsBridgeError as exc:
        job.status = JobStatus.FAILED
        job.error_kind = exc.kind
        job.error_message = exc.message
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_kind = "unexpected"
        job.error_message = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished_at = now_iso()
        dest.unlink(missing_ok=True)
        with _job_lock:
            _job_threads.pop(job.job_id, None)


@app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Tao job tao audio.

    IDEMPOTENT: cung noi dung + giong + thiet lap thi tra ve job da co, khong
    tao job moi va khong goi provider lan nua.
    """
    try:
        chapter = store.owned_chapter(payload.chapter_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    if not (chapter.content or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chương này chưa có nội dung.")

    fingerprint = job_fingerprint(
        chapter.content, payload.voice_id, payload.rate, payload.chunk_chars
    )
    existing = store.find_job_by_fingerprint(profile.user_id, chapter.chapter_id, fingerprint)
    if existing is not None:
        return {"job": existing.to_dict(), "reused": True}

    job = store.create_job(TtsJob(
        owner_id=profile.user_id,
        chapter_id=chapter.chapter_id,
        voice_id=payload.voice_id,
        content_hash=fingerprint,
        rate=payload.rate,
        chunk_chars=payload.chunk_chars,
    ))

    thread = threading.Thread(
        target=_run_job, args=(job, chapter.content), daemon=True,
        name=f"tts-job-{job.job_id}",
    )
    with _job_lock:
        _job_threads[job.job_id] = thread
    thread.start()
    return {"job": job.to_dict(), "reused": False}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        job = store.owned_job(job_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"job": job.to_dict()}


@app.get("/api/jobs")
def list_jobs(chapter_id: Optional[str] = None,
              profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    items = store.list_jobs(profile.user_id, chapter_id)
    return {"jobs": [j.to_dict() for j in items], "count": len(items)}


# -----------------------------------------------------------------------------
# Phat audio
# -----------------------------------------------------------------------------


@app.get("/api/audio/{chapter_id}")
def stream_audio(chapter_id: str) -> Response:
    """
    Tra ve audio cua mot chuong.

    Ban cuc bo stream qua backend. Khi doi sang R2, `storage.signed_url()` se
    tra URL ky san va tang nay chuyen thanh redirect - giao dien khong doi.
    """
    track = store.track_for_chapter(chapter_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chương này chưa có audio.")

    url = storage.signed_url(track.object_key)
    if url:  # pragma: no cover - duong di cua R2 o Moc 4
        return Response(status_code=307, headers={"Location": url})

    try:
        data = storage.get(track.object_key)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(content=data, media_type="audio/mpeg")
