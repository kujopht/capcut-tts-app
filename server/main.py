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
from dataclasses import replace
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
    build_metadata_store,
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
settings.validate()   # FAIL FAST neu chon che do cloud ma cau hinh sai
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

identity = build_identity(settings)
storage = build_storage(settings)
store = build_metadata_store(settings)

#: URL ky cho audio chi song ngan - backend van la noi quyet dinh quyen.
AUDIO_URL_TTL_SECONDS = 300

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


class NovelPatch(BaseModel):
    """Chi cac truong nguoi dung duoc sua. `state` doi qua publish/unpublish."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ChapterPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = None
    order_index: Optional[int] = None


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


def optional_profile(authorization: Optional[str] = None) -> Optional[Profile]:
    """
    Ho so cua nguoi goi neu co token hop le, con lai la None. KHONG BAO GIO nem.

    Dung cho cac route doc vua cong khai vua rieng tu: truyen da xuat ban thi ai
    cung xem duoc, truyen nhap thi chi chu so huu. Neu dung `current_profile` o
    day thi khach vang lai bi 401 ngay ca voi truyen cong khai; con neu khong
    xac dinh nguoi goi thi khong the phan biet chu so huu voi nguoi la.

    Token rac duoc coi nhu khong dang nhap, khong phai loi: nguoi dung het han
    phien van doc duoc truyen cong khai nhu khach.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return identity.profile_from_token(authorization.split(" ", 1)[1].strip())
    except AuthError:
        return None


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
    # `login` cung goi ra Appwrite va cung nem AuthError - de ngoai try thi
    # loi se thanh 500 thay vi mot thong bao ro rang.
    try:
        token = identity.login(payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"token": token, "profile": profile.to_dict()}


@app.post("/api/auth/login")
def login(payload: LoginIn) -> Dict[str, Any]:
    # `profile_from_token` PHAI nam trong try: no cung goi ra Appwrite va cung
    # nem AuthError. De ngoai thi loi xac thuc thanh 500 thay vi 401.
    try:
        token = identity.login(payload.email, payload.password)
        profile = identity.profile_from_token(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return {"token": token, "profile": profile.to_dict()}


@app.get("/api/auth/me")
def me(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"profile": profile.to_dict()}


# -----------------------------------------------------------------------------
# Novel
# -----------------------------------------------------------------------------


def _cover_url(novel: Novel) -> Optional[str]:
    """
    URL xem duoc cua anh bia, hoac None neu truyen chua co bia.

    Trinh duyet khong co credential cua kho nen khong tu dung URL tu
    `cover_key` duoc — phai do backend cap, giong het duong audio.

    Kho khong cap URL ky (che do cuc bo) thi tra None: tang tren se dung anh
    bia du phong. Khong bao gio tra ve mot anh gia.
    """
    if not novel.cover_key:
        return None
    return storage.signed_url(novel.cover_key, expires_seconds=AUDIO_URL_TTL_SECONDS)


def _novel_out(novel: Novel) -> Dict[str, Any]:
    """
    Novel cho API.

    THEM `cover_url` vao ben canh `cover_key` da co — chi them, khong doi ten
    va khong bo truong nao, nen client cu van chay nguyen.
    """
    return {**novel.to_dict(), "cover_url": _cover_url(novel)}


def _novel_brief(novel: Novel) -> Dict[str, Any]:
    """Phan truyen kem theo chuong: vua du de hien bia va ten o luong nghe."""
    return {
        "novel_id": novel.novel_id,
        "title": novel.title,
        "state": novel.state.value,
        "cover_key": novel.cover_key,
        "cover_url": _cover_url(novel),
    }


@app.get("/api/novels")
def list_novels(mine: bool = False, profile: Optional[Profile] = None,
                authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Thu vien cong khai, hoac danh sach cua rieng minh khi `mine=true`."""
    if mine:
        owner = current_profile(authorization)
        items = store.list_novels(owner_id=owner.user_id)
    else:
        items = store.list_novels(published_only=True)
    return {"novels": [_novel_out(n) for n in items], "count": len(items)}


@app.post("/api/novels", status_code=status.HTTP_201_CREATED)
def create_novel(payload: NovelIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    novel = store.create_novel(Novel(
        owner_id=profile.user_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        tags=payload.tags,
    ))
    return {"novel": _novel_out(novel)}


def _may_read(novel: Novel, viewer: Optional[Profile]) -> bool:
    """Truyen da xuat ban thi ai cung doc duoc; chua thi chi chu so huu."""
    if novel.state is PublishState.PUBLISHED:
        return True
    return viewer is not None and viewer.user_id == novel.owner_id


@app.get("/api/novels/{novel_id}")
def get_novel(novel_id: str,
              authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Truyen kem DANH SACH CHUONG, moi chuong da co san `has_audio`.

    Truoc day trang chi tiet phai goi `/api/chapters/{id}` cho TUNG chuong chi
    de biet chuong do da co audio chua — mot truyen 12 chuong ton 13 request, va
    con so do tang tuyen tinh theo so chuong. Gop vao day thi luon la 1.

    CO Y khong ky URL audio o day: trang danh sach chua phat gi ca, ky san N
    duong dan la lam viec thua va rai ra nhung URL khong ai dung. Duong phat van
    xin rieng qua `/api/audio/{id}/url` dung luc bam nghe.
    """
    try:
        novel = store.get_novel(novel_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # 404 chu khong phai 403: nguoi la khong can biet truyen nhap nay ton tai.
    if not _may_read(novel, optional_profile(authorization)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tiểu thuyết.")

    chapters = store.list_chapters(novel_id)
    with_audio = store.chapters_with_audio([c.chapter_id for c in chapters])
    return {
        "novel": _novel_out(novel),
        "chapters": [
            {**c.to_dict(include_content=False),
             "has_audio": c.chapter_id in with_audio}
            for c in chapters
        ],
    }


def _purge_chapter(chapter: Chapter) -> Dict[str, int]:
    """
    Xoa mot chuong cung TOAN BO thu phu thuoc vao no.

    THU TU CO CHU DICH: metadata TRUOC, object trong kho SAU.

    Neu lam nguoc lai va buoc thu hai hong, ta con lai `audio_track` tro toi
    file khong con - trinh phat hong ma khong ai biet. Lam theo thu tu nay thi
    truong hop xau nhat chi la object thua trong kho: khong route nao cham toi
    duoc (da kiem chung live), chi ton dung luong. Xem docs/HANDOFF.md muc
    "Xu ly mo coi".
    """
    removed = {"tracks": 0, "jobs": 0, "objects": 0}

    tracks = store.tracks_for_chapter(chapter.chapter_id)
    keys = [track.object_key for track in tracks if track.object_key]
    for track in tracks:
        store.delete_track(track.track_id)
        removed["tracks"] += 1

    for job in store.list_jobs(chapter.owner_id, chapter.chapter_id):
        store.delete_job(job.job_id)
        removed["jobs"] += 1

    store.delete_chapter(chapter.chapter_id, chapter.owner_id)

    # Chi con rac vo hai neu buoc nay hong -> khong de loi lam sap ca thao tac
    for key in keys:
        try:
            if storage.delete(key):
                removed["objects"] += 1
        except Exception:
            pass
    return removed


@app.patch("/api/novels/{novel_id}")
def update_novel(novel_id: str, payload: NovelPatch,
                 profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Sua truyen. Chi chu so huu; `state` khong doi duoc qua day."""
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    if isinstance(fields.get("title"), str):
        fields["title"] = fields["title"].strip()
    try:
        novel = store.update_novel(novel_id, profile.user_id, fields)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"novel": _novel_out(novel)}


@app.delete("/api/novels/{novel_id}")
def delete_novel(novel_id: str,
                 profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Xoa truyen cung moi chuong, job, audio_track va object cua no.

    Kiem quyen so huu TRUOC khi dong vao bat cu thu gi.
    """
    try:
        novel = store.owned_novel(novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    removed = {"chapters": 0, "tracks": 0, "jobs": 0, "objects": 0}
    for chapter in store.list_chapters(novel.novel_id):
        counts = _purge_chapter(chapter)
        removed["chapters"] += 1
        for key in ("tracks", "jobs", "objects"):
            removed[key] += counts[key]

    store.delete_novel(novel.novel_id, profile.user_id)
    return {"deleted": True, "removed": removed}


@app.post("/api/novels/{novel_id}/unpublish")
def unpublish_novel(novel_id: str,
                    profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Gỡ xuất bản: về bản nháp và thu hồi quyền đọc công khai. Idempotent."""
    try:
        novel = store.unpublish_novel(novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Không lưu được trạng thái: {type(exc).__name__}",
        ) from exc
    return {"novel": _novel_out(novel)}


@app.post("/api/novels/{novel_id}/publish")
def publish_novel(novel_id: str, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Xuat ban novel.

    Toan bo thao tac nam trong metadata adapter duoc inject theo cau hinh:
    kiem tra quyen so huu, doi trang thai va GHI BEN VUNG deu do store lam.
    Route khong duoc tu doi thuoc tinh cua novel - lam vay thi ban mock "co ve"
    chay duoc (cung tham chieu) con Appwrite se mat sach thay doi.

    Chu so huu LUON lay tu token da xac minh, khong bao gio tu body.

    IDEMPOTENT: publish lai novel da `published` van tra 200 voi cung novel.
    """
    try:
        novel = store.publish_novel(novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except Exception as exc:
        # Ghi metadata that bai -> BAO LOI. Tuyet doi khong tra ve 200 voi
        # trang thai `published` chi ton tai trong bo nho tien trinh nay.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Không lưu được trạng thái xuất bản: {type(exc).__name__}",
        ) from exc
    return {"novel": _novel_out(novel)}


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
def get_chapter(chapter_id: str,
                authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Mot chuong kem audio va truyen cha.

    Quyen doc bam theo TRUYEN CHA, giong `GET /api/novels/{id}`: chan o route
    truyen ma bo ngo o day thi vo nghia, chi can biet id chuong la doc duoc het
    noi dung cua mot truyen chua xuat ban.
    """
    try:
        chapter = store.get_chapter(chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # Kem theo truyen cha: luong nghe can bia va ten truyen, va nho vay tang
    # tren khong phai goi them mot vong `/api/novels/{id}` nua.
    try:
        novel: Optional[Novel] = store.get_novel(chapter.novel_id)
    except NotFoundError:
        novel = None

    viewer = optional_profile(authorization)
    if novel is not None:
        allowed = _may_read(novel, viewer)
    else:
        # Chuong mo coi (khong co truyen cha) khong sinh ra tu duong chay nao —
        # xem docs/HANDOFF.md muc "Xu ly mo coi". Khong xac minh duoc trang thai
        # xuat ban thi cho phia an toan: chi chu so huu doc duoc.
        allowed = viewer is not None and viewer.user_id == chapter.owner_id
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy chương.")

    track = store.track_for_chapter(chapter_id)
    return {
        "chapter": chapter.to_dict(),
        "audio": track.to_dict() if track else None,
        "novel": _novel_brief(novel) if novel else None,
    }


@app.patch("/api/chapters/{chapter_id}")
def update_chapter(chapter_id: str, payload: ChapterPatch,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    if isinstance(fields.get("title"), str):
        fields["title"] = fields["title"].strip()
    try:
        chapter = store.update_chapter(chapter_id, profile.user_id, fields)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"chapter": chapter.to_dict()}


@app.delete("/api/chapters/{chapter_id}")
def delete_chapter(chapter_id: str,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Xoa chuong cung job, audio_track va object cua no."""
    try:
        chapter = store.owned_chapter(chapter_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"deleted": True, "removed": _purge_chapter(chapter)}


# -----------------------------------------------------------------------------
# TTS job
# -----------------------------------------------------------------------------


def _mark_failed(job: TtsJob, kind: str, message: str) -> None:
    """
    Dua job ve `failed` va GHI LAI qua metadata adapter.

    Khong bao gio de lai output do dang: `output_key` bi xoa nen tang tren
    khong the hieu nham la da co audio dung.
    """
    job.status = JobStatus.FAILED
    job.error_kind = kind
    job.error_message = message
    job.output_key = None
    job.finished_at = job.finished_at or now_iso()
    try:
        store.save_job(job)
    except Exception as exc:
        # Het duong ghi. Van giu trang thai `failed` trong bo nho de client
        # khong bao gio nhan duoc mot thanh cong gia.
        job.error_message = (
            f"{message} | Không lưu được trạng thái thất bại: {type(exc).__name__}"
        )


def _run_job(job: TtsJob, text: str) -> None:
    """
    Chay job o thread nen. Moi loi deu duoc ghi vao job, khong lam sap server.

    MOI transition co y nghia deu di qua `store.save_job()` - cung mot giao dien
    cho ban mock lan Appwrite, job runner khong bao gio goi thang Appwrite.
    Chi doi thuoc tinh trong bo nho la khong du: ban mock van "dung" vi giu
    cung tham chieu, con Appwrite se mat sach trang thai khi doc lai.

    Trang thai `pending` da duoc luu tu truoc boi `store.create_job()`.

    THU TU BAT BUOC: synthesize -> upload -> create_track -> luu `completed`.
    `completed` chi duoc ghi sau khi file da nam trong kho va `output_key` da
    duoc gan, nen khong bao gio co job `completed` ma khong co audio.

    GIOI HAN da biet - CHUA co giao dich phan tan: kho file va kho metadata la
    hai he thong tach roi. Neu ghi `completed` that bai NGAY SAU khi upload
    xong, job se thanh `failed` nhung object da upload van nam lai trong kho
    (rac vo hai, khong duoc cong bo vi `output_key` bi xoa). Doi lai la khong
    bao gio bao thanh cong gia. Xem docs/HANDOFF.md muc "Giới hạn đã biết".
    """
    def progress(done: int, total: int) -> None:
        # Cap nhat trong bo nho thoi: ghi moi tick se dam nat Appwrite.
        # Trang thai ben vung chi ghi o cac transition o duoi.
        job.done_parts = done
        job.total_parts = total

    output_key = f"audio/{job.owner_id}/{job.chapter_id}/{job.content_hash}.mp3"
    dest = settings.var_dir / "tts" / f"{job.job_id}.mp3"

    try:
        # -- transition: pending -> running (luu TRUOC khi synthesis) --------
        job.status = JobStatus.RUNNING
        job.started_at = now_iso()
        store.save_job(job)

        result = tts_bridge.synthesize_chapter(
            text=text,
            voice_id=job.voice_id,
            dest=dest,
            rate=job.rate,
            chunk_chars=job.chunk_chars,
            on_progress=progress,
        )

        # -- dua file vao kho TRUOC, danh dau hoan tat SAU -------------------
        if isinstance(storage, LocalStorageAdapter):
            storage.put_file(output_key, dest)
        else:
            storage.put(output_key, dest.read_bytes())

        store.create_track(AudioTrack(
            chapter_id=job.chapter_id,
            owner_id=job.owner_id,
            voice_id=job.voice_id,
            object_key=output_key,
            content_hash=job.content_hash,
            size_bytes=result["size_bytes"],
        ))

        # -- transition: running -> completed --------------------------------
        # GHI BEN VUNG TRUOC, cong bo trong bo nho SAU. Neu doi thuoc tinh
        # cua `job` truoc roi moi ghi, mot lan poll xen vao giua hai buoc se
        # thay `completed` trong khi metadata chua he duoc luu.
        finished_at = now_iso()
        completed = replace(
            job,
            status=JobStatus.COMPLETED,
            output_key=output_key,
            total_parts=result["total_parts"],
            done_parts=result["total_parts"],
            finished_at=finished_at,
        )
        store.save_job(completed)

        job.output_key = output_key
        job.total_parts = result["total_parts"]
        job.done_parts = result["total_parts"]
        job.status = JobStatus.COMPLETED
        job.finished_at = finished_at
    except tts_bridge.TtsBridgeError as exc:
        _mark_failed(job, exc.kind, exc.message)
    except Exception as exc:
        # Bao gom ca truong hop `store.save_job(completed)` nem loi: job se la
        # `failed`, tuyet doi khong phai `completed` gia.
        _mark_failed(job, "unexpected", f"{type(exc).__name__}: {exc}")
    finally:
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

    # transition: (khong co) -> pending. Ghi ben vung NGAY, truoc khi khoi
    # dong thread, de job luon ton tai trong metadata backend du worker chet.
    job = store.create_job(TtsJob(
        owner_id=profile.user_id,
        chapter_id=chapter.chapter_id,
        voice_id=payload.voice_id,
        content_hash=fingerprint,
        rate=payload.rate,
        chunk_chars=payload.chunk_chars,
    ))

    # Chup trang thai TRUOC khi khoi dong worker: neu doc sau `start()`, worker
    # co the da doi sang `running` va phan hoi "vua tao" se mo ta sai.
    created = job.to_dict()

    thread = threading.Thread(
        target=_run_job, args=(job, chapter.content), daemon=True,
        name=f"tts-job-{job.job_id}",
    )
    with _job_lock:
        _job_threads[job.job_id] = thread
    thread.start()
    return {"job": created, "reused": False}


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


def _may_listen(chapter_id: str, authorization: Optional[str]) -> None:
    """
    Kiem tra quyen nghe TRUOC khi tra bat ky byte audio nao.

    Cho phep khi:
      - chuong thuoc mot tieu thuyet DA XUAT BAN (ai cung nghe duoc), hoac
      - nguoi goi da dang nhap va la CHU SO HUU chuong do.

    Bucket duoc coi la private: khong bao gio tra URL cong khai co dinh.
    """
    try:
        chapter = store.get_chapter(chapter_id)
        novel = store.get_novel(chapter.novel_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if novel.state == PublishState.PUBLISHED:
        return

    # Ban nhap: bat buoc dang nhap va phai dung chu so huu
    profile = current_profile(authorization)
    if chapter.owner_id != profile.user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Bạn không có quyền nghe chương này."
        )


@app.get("/api/audio/{chapter_id}/url")
def audio_url(
    chapter_id: str, download: bool = False,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Tra ve URL PHAT DUOC cho mot chuong, SAU KHI da kiem tra quyen.

    VI SAO CAN ENDPOINT NAY: the `<audio src>` cua trinh duyet khong gui duoc
    header `Authorization`, va `fetch()` co header do thi lai chet o buoc
    redirect sang R2 vi bucket khong mo CORS. Da kiem chung tren trinh duyet
    that: `fetch` -> "Failed to fetch", the `<audio>` -> MEDIA_ERR_SRC_NOT_SUPPORTED.
    Nen frontend can nhan URL ky duoi dang JSON roi tu gan vao `<audio src>`
    (the media khong doi CORS) hoac vao `<a href>` de tai ve.

    Kiem tra quyen dung y het `/api/audio/{chapter_id}` - khong noi long gi.

    `download=true` bat trinh duyet tai ve thay vi phat trong tab.
    """
    _may_listen(chapter_id, authorization)

    track = store.track_for_chapter(chapter_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chương này chưa có audio.")

    name = f"{chapter_id}.mp3" if download else None
    url = storage.signed_url(track.object_key,
                             expires_seconds=AUDIO_URL_TTL_SECONDS,
                             download_name=name)
    return {
        # Kho co URL ky (R2): gan thang vao <audio src> hoac <a href>.
        "url": url,
        # Kho cuc bo: khong co URL ky -> tang tren phai stream qua backend
        # bang fetch co kem token (cung origin nen khong vuong CORS).
        "stream_url": None if url else f"/api/audio/{chapter_id}",
        "expires_in": AUDIO_URL_TTL_SECONDS if url else None,
        "size_bytes": track.size_bytes,
    }


@app.get("/api/audio/{chapter_id}")
def stream_audio(
    chapter_id: str, authorization: Optional[str] = Header(default=None)
) -> Response:
    """
    Tra ve audio cua mot chuong, SAU KHI da kiem tra quyen.

    Ban cuc bo stream qua backend. Voi R2, backend cap URL ky co han ngan
    (mac dinh 5 phut) va chuyen huong - van la backend quyet dinh ai duoc nghe.
    """
    _may_listen(chapter_id, authorization)

    track = store.track_for_chapter(chapter_id)
    if track is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chương này chưa có audio.")

    # URL ky chi duoc cap SAU khi da kiem tra quyen o tren
    url = storage.signed_url(track.object_key, expires_seconds=AUDIO_URL_TTL_SECONDS)
    if url:  # pragma: no cover - duong di cua R2, can credential that
        return Response(status_code=307, headers={"Location": url})

    try:
        data = storage.get(track.object_key)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(content=data, media_type="audio/mpeg")
