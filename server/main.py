"""
Backend FastAPI cua Fanfic Audio Studio Web.

Chay:
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --reload --port 8000

Backend giu MOI bi mat (Appwrite API key, R2 access key). Trinh duyet khong
bao gio nhan duoc credential nao.

Backend KHONG import GUI: da xac minh khong module PySide6 nao bi keo vao.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints

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
    AudioStamp,
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
# Worker recovery
# -----------------------------------------------------------------------------
#
# Job `running` khong co gi chung to worker con song. Truoc day mot worker chet
# giua chung se de job ket `running` VINH VIEN, va te hon: `find_job_by_fingerprint`
# chi loai `failed`, nen nguoi dung bam "Tao audio" se duoc tra lai chinh cai job
# chet do, mai mai.
#
# Cach lam: lease co han, worker dang chay tu lam moi (heartbeat). Het han nghia
# la worker da chet, va chi luc do job moi duoc nhan lai.
#
# CLAIM LA COMPARE-AND-SET THAT. Appwrite Cloud 1.9.6 CO transaction — mot ghi
# chu cu o day tung noi la khong, dieu do sai. `store.claim_job()` goi hai thao
# tac vao MOT transaction: `create` hang `job_claims` voi rowId tat dinh
# "{job_id}-{attempt}" va `update` job row. Uniqueness cua rowId duoc cuong che
# ben trong transaction, nen chi mot worker commit duoc; ke thua nhan None va
# DUNG LAI, khong goi TTS. `attempts` dong vai fencing token cho moi lan ghi sau
# do (`save_job_fenced`).
#
# DOI SCHEMA XONG PHAI RESTART: `AppwriteMetadataStore._supported_fields()` cache
# theo vong doi tien trinh, nen tien trinh dang chay khong thay truong vua them.
#
# Tinh dung dan VAN khong chi dua vao lease. Chay lai mot job la VO HAI vi:
#   - `output_key` la tat dinh theo `content_hash`, hai lan chay ghi cung mot khoa
#     voi cung noi dung;
#   - `store.create_track()` la TIM-HOAC-TAO theo `(chapter_id, content_hash)`,
#     nen khong bao gio sinh hai track cho cung mot ket qua.

#: Lease song bao lau neu khong duoc lam moi. Phai DAI hon chu ky heartbeat kha
#: nhieu, de mot lan tre mang khong lam job bi nguoi khac giat.
JOB_LEASE_SECONDS = 90

#: Chu ky lam moi lease tu trong worker.
JOB_HEARTBEAT_SECONDS = 30

#: So lan chay toi da cho mot job. Vuot thi `failed` kem thong bao ro rang.
JOB_MAX_ATTEMPTS = 3

#: Chu ky quet job ket. Lan quet dau chay ngay luc khoi dong.
JOB_SWEEP_SECONDS = 60

#: Danh tinh cua tien trinh nay. Hai worker khac nhau se co gia tri khac nhau,
#: nen doc lease ra la biet job dang thuoc ai.
WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

_sweeper_stop = threading.Event()


def _lease_until(seconds: int = JOB_LEASE_SECONDS) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="seconds")


# -----------------------------------------------------------------------------
# Schema
# -----------------------------------------------------------------------------


#: Tieu de: CAT khoang trang TRUOC khi do do dai.
#:
#: `Field(min_length=1)` do do dai chuoi THO, nen `""` bi tu choi 422 con `"   "`
#: lot qua roi duoc cat khi luu — cung mot gia tri hieu dung ma hai ket qua khac
#: nhau, va thu nam trong kho la mot tieu de RONG. Rang buoc nay cat truoc roi
#: moi do, nen ca hai deu bi tu choi giong nhau.
TieuDe = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=200)]


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class NovelIn(BaseModel):
    title: TieuDe
    description: str = ""
    tags: List[str] = Field(default_factory=list)


class ChapterIn(BaseModel):
    novel_id: str
    title: TieuDe
    content: str = ""
    order_index: int = 1


class NovelPatch(BaseModel):
    """Chi cac truong nguoi dung duoc sua. `state` doi qua publish/unpublish."""

    title: Optional[TieuDe] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ChapterPatch(BaseModel):
    title: Optional[TieuDe] = None
    content: Optional[str] = None
    order_index: Optional[int] = None


class ChapterOrderIn(BaseModel):
    """Thu tu chuong moi, day du va dung mot lan."""

    chapter_ids: List[str] = Field(min_length=1)


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


#: Tran tren cho `limit`. Khong de client tu xin 10.000 ban ghi mot lan.
MAX_PAGE_SIZE = 60


@app.get("/api/novels")
def list_novels(mine: bool = False, q: str = "", tag: str = "",
                limit: Optional[int] = None, offset: int = 0,
                authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Thu vien cong khai, hoac danh sach cua rieng minh khi `mine=true`.

    Tim kiem (`q`), loc the (`tag`) va phan trang (`limit`/`offset`) do KHO lam,
    khong phai trinh duyet. Truoc day `/fanfic` tai het truyen ve roi loc bang
    JavaScript — du cho vai chuc truyen, khong du cho vai nghin.

    TUONG THICH NGUOC: `limit` mac dinh la None nghia la khong phan trang, tra
    ve het y nhu truoc. Client cu (`mine=true` o trang tac gia, `ensureStudioNovel`)
    khong doi hanh vi mot chut nao. Chi ai truyen `limit` moi duoc phan trang.
    """
    owner_id = None
    if mine:
        owner_id = current_profile(authorization).user_id

    page_size = None if limit is None else max(1, min(limit, MAX_PAGE_SIZE))
    items, total = store.find_novels(
        owner_id=owner_id,
        published_only=not mine,
        query=q,
        tag=tag,
        limit=page_size,
        offset=max(0, offset),
    )
    return {
        "novels": [_novel_out(n) for n in items],
        # `count` giu nguyen y nghia cu: so ban ghi TRONG PHAN HOI NAY
        "count": len(items),
        # `total` la so ban ghi khop dieu kien — de biet con trang sau hay khong
        "total": total,
        "limit": page_size,
        "offset": max(0, offset),
        "has_more": max(0, offset) + len(items) < total,
    }


# PHAI khai bao TRUOC `/api/novels/{novel_id}`: FastAPI so khop theo thu tu khai
# bao, dat sau thi "tags" bi coi la mot `novel_id`.
@app.get("/api/novels/tags")
def list_novel_tags() -> Dict[str, Any]:
    """Cac the dang co tren truyen DA XUAT BAN, cho bo loc o trang kham pha."""
    tags = store.novel_tags(published_only=True)
    return {"tags": tags, "count": len(tags)}


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


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """
    Doc moc thoi gian ISO, tra None neu khong doc duoc.

    KHONG so sanh hai moc thoi gian bang chuoi: `now_iso()` sinh ra
    `2026-08-07T03:01:36+00:00` con Appwrite tra ve
    `2026-08-07T03:01:36.000+00:00`. So sanh chuoi thi `+` (0x2B) nho hon
    `.` (0x2E), nen ban khong co mili giay luon bi coi la som hon — sai thu tu
    o dung cho quan trong nhat.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _audio_outdated(chapter: Chapter, stamp: Optional[AudioStamp]) -> bool:
    """
    Audio hien tai co con khop noi dung chuong hay khong.

    CACH DUNG — so DAU VAN TAY. `AudioTrack.content_hash` la
    `job_fingerprint(noi dung, giong, toc do, kich thuoc doan)` tai luc render.
    Tinh lai dau van tay do voi noi dung HIEN TAI va chinh cac tham so cua track
    ay; khac nhau tuc la noi dung da doi.

    Dung tham so CUA TRACK, khong dung gia tri mac dinh: mot track render o
    `rate=1.5` ma dem so voi `rate=1.0` thi se bi bao cu vinh vien.

    Chinh xac, khong phai phong doan. Sua noi dung roi sua ve dung nguyen ban thi
    dau van tay khop lai va canh bao TU TAT — dieu ma cach do bang moc thoi gian
    khong lam duoc.

    CACH DU PHONG — track cu (tao truoc khi luu `rate`/`chunk_chars`) khong tinh
    lai duoc dau van tay, nen quay ve so moc thoi gian: chuong sua sau khi tao
    audio thi coi la co the khong khop. Bao oan (sua rieng tieu de cung nhay)
    nhung khong bo sot. Khong xoa, khong ghi lai track cu de "nang cap" — du lieu
    cu duoc doc nhu no von co.
    """
    if stamp is None:
        return False

    if stamp.can_verify:
        current = job_fingerprint(chapter.content, stamp.voice_id,
                                  stamp.rate or "", stamp.chunk_chars or 0)
        return current != stamp.content_hash

    made = _parse_iso(stamp.created_at)
    edited = _parse_iso(chapter.updated_at)
    if made is None or edited is None:
        return False
    return edited > made


def _stamp_for(chapter: Chapter, track: Optional[AudioTrack]) -> Optional[AudioStamp]:
    """`AudioStamp` cho MOT chuong, da ghep tham so render tu job."""
    if track is None:
        return None
    stamp = AudioStamp(created_at=track.created_at,
                       content_hash=track.content_hash,
                       voice_id=track.voice_id)
    found = store.job_settings(chapter.owner_id, [track.content_hash])
    settings = found.get(track.content_hash)
    return stamp.with_settings(*settings) if settings else stamp


def _with_job_settings(owner_id: str,
                       stamps: Dict[str, AudioStamp]) -> Dict[str, AudioStamp]:
    """
    Ghep `rate`/`chunk_chars` tu ban ghi job vao tung `AudioStamp`.

    MOT truy van cho ca danh sach — khong phai mot truy van moi chuong, neu khong
    lai thanh dung cai N+1 da bo di.
    """
    if not stamps:
        return stamps
    fingerprints = [s.content_hash for s in stamps.values() if s.content_hash]
    settings_by_hash = store.job_settings(owner_id, fingerprints)
    out: Dict[str, AudioStamp] = {}
    for chapter_id, stamp in stamps.items():
        found = settings_by_hash.get(stamp.content_hash)
        out[chapter_id] = (stamp.with_settings(*found) if found else stamp)
    return out


def _chapter_row(chapter: Chapter, stamp: Optional[AudioStamp]) -> Dict[str, Any]:
    """Mot dong trong danh sach chuong: du de ve badge, khong kem noi dung."""
    return {
        **chapter.to_dict(include_content=False),
        "has_audio": stamp is not None,
        "audio_outdated": _audio_outdated(chapter, stamp),
    }


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
    stamps = _with_job_settings(
        novel.owner_id, store.audio_by_chapter([c.chapter_id for c in chapters]))
    return {
        "novel": _novel_out(novel),
        "chapters": [_chapter_row(c, stamps.get(c.chapter_id)) for c in chapters],
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


@app.post("/api/novels/{novel_id}/chapters/order")
def reorder_chapters(novel_id: str, payload: ChapterOrderIn,
                     profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Dat lai thu tu chuong bang MOT request.

    Vi sao khong de frontend goi `PATCH /api/chapters/{id}` cho tung chuong: doi
    thu tu mot danh sach n chuong se thanh n request — dung cai N+1 vua bo di o
    trang chi tiet truyen. `PATCH` van dung duoc nhu cu cho client cu.

    Danh sach phai gom DUNG cac chuong cua truyen, khong thieu khong thua. Lech
    mot cai thi tra 400 va khong ghi gi ca — do la thu chan viec "sap xep lai"
    ma lam roi mat mot chuong.
    """
    try:
        chapters = store.reorder_chapters(novel_id, profile.user_id,
                                          payload.chapter_ids)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    stamps = _with_job_settings(
        profile.user_id, store.audio_by_chapter([c.chapter_id for c in chapters]))
    return {
        "chapters": [_chapter_row(c, stamps.get(c.chapter_id)) for c in chapters],
    }


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


# PHAI khai bao TRUOC `/api/chapters/{chapter_id}`, neu khong "mine" bi coi la
# mot `chapter_id`. Xem cach lam tuong tu o `/api/novels/tags`.
@app.get("/api/chapters")
def list_my_chapters(mine: bool = False,
                     profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    MOI chuong cua nguoi dang dang nhap, trong MOT request.

    Vi sao co route nay: thu vien audio truoc day goi `/api/novels/{id}` cho TUNG
    truyen chi de dung mot bang tra "chapter_id -> ten chuong". Nguoi co 40 truyen
    ton 42 request, va con so do tang tuyen tinh theo so truyen.

    CHI chuong cua chinh minh. Khong co che do cong khai: danh sach chuong cua
    mot truyen da xuat ban van lay qua `GET /api/novels/{id}`, noi da co san kiem
    tra quyen doc.

    CO Y khong kem noi dung chuong va khong ky URL audio nao: day la du lieu de
    dung DANH SACH. Duong phat van xin rieng qua `/api/audio/{id}/url` dung luc
    bam nghe.
    """
    if not mine:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Route này chỉ trả chương của chính bạn — cần `mine=true`.",
        )
    chapters = store.chapters_for_owner(profile.user_id)
    return {
        "chapters": [c.to_dict(include_content=False) for c in chapters],
        "count": len(chapters),
    }


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
        # Chuong da sua sau khi tao audio -> audio CO THE khong con khop.
        # Chi la canh bao, khong bao gio la ly do de xoa file audio.
        "audio_outdated": _audio_outdated(chapter, _stamp_for(chapter, track)),
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


def _mark_failed(job: TtsJob, kind: str, message: str,
                 fence: Optional[int] = None) -> None:
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
    # Nha lease: khong worker nao con giu job nay
    job.lease_expires_at = None
    job.lease_owner = None
    try:
        if fence is None:
            store.save_job(job)
        elif not store.save_job_fenced(job, fence, WORKER_ID):
            # Mat quyen: khong duoc ghi de len worker dang giu job
            return
    except Exception as exc:
        # Het duong ghi. Van giu trang thai `failed` trong bo nho de client
        # khong bao gio nhan duoc mot thanh cong gia.
        job.error_message = (
            f"{message} | Không lưu được trạng thái thất bại: {type(exc).__name__}"
        )


def _run_job(job: TtsJob, text: str, fence: Optional[int] = None) -> None:
    """
    Chay job o thread nen. Moi loi deu duoc ghi vao job, khong lam sap server.

    MOI transition di qua giao dien metadata — cung mot giao dien cho ban mock
    lan Appwrite, job runner khong bao gio goi thang Appwrite. Chi doi thuoc tinh
    trong bo nho la khong du: ban mock van "dung" vi giu cung tham chieu, con
    Appwrite se mat sach trang thai khi doc lai.

    MOI LAN GHI DEU KEM FENCING TOKEN (`save_job_fenced`). Worker giu lease cu
    chua chet han — no co the chi bi treo — nen phai chan no ghi de len ket qua
    cua worker moi. Ghi khong kem token la mot loi.

    `fence` do nguoi goi cap khi da nhan job; `None` nghia la ham tu nhan (duong
    tao job moi). Nhan that bai -> DUNG LAI, khong goi TTS.

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

    # -- NHAN JOB TRUOC, roi moi nhan trach nhiem don dep -----------------------
    #
    # Cho nay tung nam TRONG `try`, va do la mot loi: duong `return` khi thua
    # claim van di qua `finally`, nen worker THUA xoa tep tam va go ban ghi thread
    # cua worker THANG. Worker thang sau do upload mot tep khong con ton tai, job
    # thanh `failed` va khong sinh track nao. CI tren Linux do duoc ngay; tren
    # Windows thi thua thoat nhanh hon nen cua so hep hon va thuong khong lo ra.
    #
    # Thua thi ra ve TAY TRANG: khong co gi la cua ta thi khong don gi.
    if fence is None:
        fence = store.claim_job(job, WORKER_ID, _lease_until())
        if fence is None:
            return

    # Ten tep tam kem worker va lan thu, khong chi kem `job_id`. Hai worker chay
    # cung mot job KHONG bao gio dung chung mot duong dan, ke ca khi chung chia
    # se `var_dir` qua mot volume.
    dest = settings.var_dir / "tts" / f"{job.job_id}-{WORKER_ID}-{fence}.mp3"

    # Heartbeat: lam moi lease theo chu ky trong khi synthesis dang chay. Khong
    # co no thi mot chuong dai se bi bo quet coi la "worker da chet" va chay lai
    # song song voi chinh no.
    beat_stop = threading.Event()
    #: Bat len khi worker khac da nhan job nay — ta phai buong.
    lost = threading.Event()

    def heartbeat() -> None:
        while not beat_stop.wait(JOB_HEARTBEAT_SECONDS):
            try:
                ok = store.save_job_fenced(
                    replace(job, lease_expires_at=_lease_until(),
                            lease_owner=WORKER_ID),
                    fence, WORKER_ID)
            except Exception:
                # Mang chap chon: bo qua nhip nay. Lease con han tu nhip truoc.
                continue
            if not ok:
                # MAT QUYEN: mot worker khac da nhan job nay. Dung dap nhip nua —
                # neu khong ta se lam moi lease cua NGUOI KHAC.
                lost.set()
                return

    beater = threading.Thread(target=heartbeat, daemon=True,
                              name=f"tts-beat-{job.job_id}")

    try:
        # -- transition: pending -> running ----------------------------------
        # Claim da xong o tren, TRUOC `try`. Tu day tro di ta la chu job.
        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or now_iso()
        job.attempts = fence
        job.lease_owner = WORKER_ID
        job.lease_expires_at = _lease_until()
        beater.start()

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
            # Nha lease: job da xong, khong worker nao con giu no
            lease_expires_at=None,
            lease_owner=None,
        )
        if not store.save_job_fenced(completed, fence, WORKER_ID):
            # Mot worker khac da nhan job giua chung. Ket qua cua ta bi bo, va do
            # la DUNG: worker moi se tu chay va tu ghi. Object da upload trung
            # khoa tat dinh nen khong sinh rac.
            return

        job.output_key = output_key
        job.total_parts = result["total_parts"]
        job.done_parts = result["total_parts"]
        job.status = JobStatus.COMPLETED
        job.finished_at = finished_at
    except tts_bridge.TtsBridgeError as exc:
        _mark_failed(job, exc.kind, exc.message, fence)
    except Exception as exc:
        # Bao gom ca truong hop ghi `completed` nem loi: job se la `failed`,
        # tuyet doi khong phai `completed` gia.
        _mark_failed(job, "unexpected", f"{type(exc).__name__}: {exc}", fence)
    finally:
        beat_stop.set()
        dest.unlink(missing_ok=True)
        with _job_lock:
            # Go DUNG ban ghi cua chinh minh. `_job_threads` khoa theo `job_id`,
            # nen `pop` vo dieu kien se go ban ghi cua worker khac dang chay cung
            # job do — job bien mat khoi so theo doi cua tien trinh du van dang
            # chay.
            if _job_threads.get(job.job_id) is threading.current_thread():
                _job_threads.pop(job.job_id, None)


def _older_than(stamp: Optional[str], seconds: int) -> bool:
    """Moc thoi gian da cu hon `seconds` giay chua. Doc khong duoc -> False."""
    moment = _parse_iso(stamp)
    if moment is None:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment < datetime.now(timezone.utc) - timedelta(seconds=seconds)


def _claim_stale_job(job: TtsJob) -> Optional[int]:
    """
    Nhan mot job da het lease. Tra ve FENCING TOKEN neu thang, None neu thua.

    Uy thac cho `store.claim_job()` — ban Appwrite lam viec nay bang MOT
    transaction gom `create` hang khoa co id tat dinh va `update` job row. Tinh
    duy nhat cua rowId do database cuong che, nen worker thua co commit hong han.
    Da do that: 10 worker dong thoi -> dung mot cai thang.

    Thua thi DUNG LAI. Khong thu lai mu quang: thu lai se cuop mat lease vua duoc
    cap cho worker thang.
    """
    try:
        return store.claim_job(job, WORKER_ID, _lease_until())
    except Exception:
        return None


def recover_stale_jobs() -> Dict[str, int]:
    """
    Tim job `running` da mat worker va xu ly dung mot lan.

    IDEMPOTENT: chay lai bao nhieu lan cung duoc. Job con lease hop le bi bo qua,
    job da `completed`/`failed` khong nam trong danh sach quet.

    TUYET DOI KHONG danh dau moi job `running` thanh `failed` luc khoi dong — do
    la cach lam pha du lieu cua nguoi dung dang co job chay binh thuong o mot
    tien trinh khac.
    """
    report = {"da_quet": 0, "bo_qua_con_lease": 0, "chay_lai": 0,
              "het_luot_thu": 0, "khong_nhan_duoc": 0, "bo_qua_con_moi": 0}
    try:
        candidates = list(store.list_jobs_by_status(JobStatus.RUNNING))
        # `pending` cung co the bi bo roi: server chet NGAY SAU `create_job` va
        # TRUOC khi thread kip doi sang `running`. Job do khong co lease nao ca,
        # nen loc bang tuoi cua no.
        for job in store.list_jobs_by_status(JobStatus.PENDING):
            if _older_than(job.created_at, JOB_LEASE_SECONDS):
                candidates.append(job)
            else:
                report["bo_qua_con_moi"] += 1
    except Exception:
        return report

    for job in candidates:
        report["da_quet"] += 1
        if job.lease_is_live():
            report["bo_qua_con_lease"] += 1
            continue

        if (job.attempts or 0) >= JOB_MAX_ATTEMPTS:
            # Het luot: dung lai voi thong bao nguoi dung doc hieu duoc, thay vi
            # de job xoay vong mai.
            _mark_failed(
                job, "worker_lost",
                f"Đã thử tạo audio {job.attempts} lần nhưng lần nào tiến trình "
                "cũng bị dừng giữa chừng. Hãy thử lại, hoặc chia chương thành "
                "phần ngắn hơn.",
            )
            report["het_luot_thu"] += 1
            continue

        fence = _claim_stale_job(job)
        if fence is None:
            # Worker khac da nhan. Day la ket qua BINH THUONG khi nhieu worker
            # cung quet, khong phai su co.
            report["khong_nhan_duoc"] += 1
            continue

        # Doc lai chuong: noi dung co the da doi tu lan chay truoc.
        try:
            chapter = store.get_chapter(job.chapter_id)
        except NotFoundError:
            _mark_failed(job, "chapter_gone",
                         "Chương của audio này đã bị xoá.")
            continue

        thread = threading.Thread(
            target=_run_job, args=(job, chapter.content, fence), daemon=True,
            name=f"tts-recover-{job.job_id}",
        )
        with _job_lock:
            _job_threads[job.job_id] = thread
        thread.start()
        report["chay_lai"] += 1
    return report


def _sweep_forever() -> None:
    """Quet dinh ky. Lan dau chay ngay, sau do moi `JOB_SWEEP_SECONDS`."""
    while True:
        try:
            recover_stale_jobs()
        except Exception:
            # Bo quet chet la mat recovery — khong duoc de mot loi le lam no dung
            pass
        if _sweeper_stop.wait(JOB_SWEEP_SECONDS):
            return


@app.on_event("startup")
def start_job_sweeper() -> None:
    """
    Bat bo quet job ket khi backend khoi dong.

    Chay trong thread nen: khoi dong khong duoc cho Appwrite tra loi. Bo quet
    KHONG bao gio xoa du lieu va khong bao gio chay che do xoa cua cong cu doi
    soat — hai viec do tach roi hoan toan.
    """
    threading.Thread(target=_sweep_forever, daemon=True,
                     name="tts-job-sweeper").start()


@app.on_event("shutdown")
def stop_job_sweeper() -> None:
    _sweeper_stop.set()


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
        # Job KET — `running` ma khong con worker nao giu. Truoc day nhanh nay tra
        # lai chinh cai job chet do, mai mai: nguoi dung bam "Tao audio" va nhan
        # ve mot job khong bao gio nhich. Nay thi nhan lai va chay tiep.
        if existing.is_stale and (existing.attempts or 0) < JOB_MAX_ATTEMPTS:
            fence = _claim_stale_job(existing)
            if fence is not None:
                thread = threading.Thread(
                    target=_run_job, args=(existing, chapter.content, fence),
                    daemon=True, name=f"tts-resume-{existing.job_id}",
                )
                with _job_lock:
                    _job_threads[existing.job_id] = thread
                thread.start()
        elif existing.is_stale:
            _mark_failed(
                existing, "worker_lost",
                f"Đã thử tạo audio {existing.attempts} lần nhưng lần nào tiến "
                "trình cũng bị dừng giữa chừng. Hãy thử lại, hoặc chia chương "
                "thành phần ngắn hơn.",
            )
        return {"job": store.get_job(existing.job_id).to_dict(), "reused": True}

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
