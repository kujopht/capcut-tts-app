"""
Backend FastAPI cua Fanfic Audio Studio Web.

Chay:
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --reload --port 8000

Backend giu MOI bi mat (Appwrite API key, R2 access key). Trinh duyet khong
bao gio nhan duoc credential nao.

Backend KHONG import GUI: da xac minh khong module PySide6 nao bi keo vao.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional
from urllib.parse import quote

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
from server.creator import (
    AuthorStateError,
    RANK_TIERS,
    UsernameError,
    UsernameTaken,
    suggest_username,
)
from server.creator_service import CreatorService
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

#: Tang service cua tac gia. MOT the hien, dung chung identity va store voi
#: cac route khac — khong co duong ghi thu hai vao trang thai tac gia.
#:
#: Cac ham DUYET/TU CHOI/TREO cua no KHONG co route nao goi toi. Xem ghi chu o
#: dau `server/creator_service.py`: du an chua co co che phan quyen quan tri,
#: va mot endpoint duyet khong duoc bao ve la mot cai cong mo.
creators = CreatorService(identity, store)

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
#:
#: Do dai cua CHUONG khong lien quan gi o day: mot chuong ba tieng dong ho van
#: chi can lease 90 giay, mien la heartbeat con dap. Chinh so nay chi khi mang
#: toi VM cham den muc hai nhip lien tiep cung truot.
JOB_LEASE_SECONDS = int(os.environ.get("FAS_JOB_LEASE_SECONDS", "90"))

#: Chu ky lam moi lease tu trong worker.
JOB_HEARTBEAT_SECONDS = int(os.environ.get("FAS_JOB_HEARTBEAT_SECONDS", "30"))

# Lease phai chiu duoc HAI nhip truot lien tiep, tuc la dai gap ba chu ky. Ngan
# hon thi lease het han giua hai lan dap, va mot job dang chay binh thuong se bi
# bo quet nhan lai — dung cai loi ma ca vong nay sinh ra de tranh.
if JOB_LEASE_SECONDS < JOB_HEARTBEAT_SECONDS * 3:
    raise RuntimeError(
        f"FAS_JOB_LEASE_SECONDS={JOB_LEASE_SECONDS} quá ngắn so với "
        f"FAS_JOB_HEARTBEAT_SECONDS={JOB_HEARTBEAT_SECONDS}. "
        "Lease phải dài ít nhất gấp ba chu kỳ nhịp."
    )

#: So lan chay toi da cho mot job. Vuot thi `failed` kem thong bao ro rang.
JOB_MAX_ATTEMPTS = 3

#: Tiet che luu tien do. Chi ghi khi DU MOT trong hai dieu kien.
#:
#: Callback tien do chay mot lan MOI DOAN. Mot chuong 100.000 ky tu la hon 50
#: doan, va moi lan ghi Appwrite la mot transaction ba luot goi — ghi moi tick
#: la dam nat kho vi mot con so ma nguoi dung khong kip doc.
#:
#: Nguoc lai, KHONG ghi gi ca cung sai, va do la trang thai cu: tien do chi
#: song trong bo nho worker, con `GET /api/jobs/{id}` doc tu kho, nen thanh
#: tien trinh dung im o 0% suot ca job va tai lai trang la mat sach.
#:
#: 3 giay khop voi nhip poll 1500ms cua giao dien: nguoi dung thay so nhay it
#: nhat moi hai lan poll. 5% de mot chuong ngan (it doan, moi doan la mot buoc
#: nhay lon) van cap nhat kip du chua den 3 giay.
JOB_PROGRESS_SECONDS = 3.0
JOB_PROGRESS_PERCENT = 5

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

#: Do dai toi da cua NOI DUNG mot chuong, tinh bang ky tu.
#:
#: Truoc day khong co gioi han nao o may chu. Trang `/studio` co mot rao 20.000
#: ky tu nhung do la rao O TRINH DUYET — goi thang `POST /api/chapters` la di
#: qua, va trang `/write` thi khong co rao nao ca. Tran duy nhat la cot
#: `content` cua Appwrite: 1.000.000 ky tu, tuc la 525 doan, tuc la vai tieng
#: CPU tren may worker cho MOT lan bam nut.
#:
#: 100.000 ky tu la khoang 53 doan, uoc chung hai tieng ruoi audio — da rong
#: rai hon mot chuong fanfic dai (60.000 ky tu, 32 doan) kha nhieu. Doi duoc
#: bang `FAS_MAX_CHAPTER_CHARS` khi co may manh hon.
MAX_CHAPTER_CHARS = int(os.environ.get("FAS_MAX_CHAPTER_CHARS", "100000"))

#: Bao nhieu job cua CUNG mot nguoi duoc xep hang cung luc.
#:
#: Giong Piper chay tren dung MOT may, va concurrency cua no la 1. Khong co
#: tran nay thi mot nguoi dung xep 50 chuong la worker ban ca ngay, con moi
#: nguoi khac cho sau lung ho — khong ai hong gi, nhung dich vu coi nhu dung.
MAX_ACTIVE_JOBS = int(os.environ.get("FAS_MAX_ACTIVE_JOBS", "3"))

NoiDungChuong = Annotated[str, StringConstraints(max_length=MAX_CHAPTER_CHARS)]


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
    content: NoiDungChuong = ""
    order_index: int = 1


class NovelPatch(BaseModel):
    """Chi cac truong nguoi dung duoc sua. `state` doi qua publish/unpublish."""

    title: Optional[TieuDe] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ChapterPatch(BaseModel):
    title: Optional[TieuDe] = None
    # CUNG rang buoc voi `ChapterIn`. Chan luc tao ma khong chan luc sua thi
    # chi la mot buoc vong: tao chuong ngan roi PATCH mot trieu ky tu vao.
    content: Optional[NoiDungChuong] = None
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
    """
    LIVENESS: tien trinh con song va tra loi duoc.

    KHONG cham toi Appwrite hay R2 — mot su co tam thoi cua kho du lieu khong
    duoc lam nen tang hosting giet tien trinh web dang lanh manh. Kiem tra ket
    noi thuoc ve `/api/ready`.

    KHONG bao gio tra ve gia tri bi mat.
    """
    return {
        "status": "ok",
        "service": "fanfic-audio-api",
        "version": app.version,
        **settings.describe(),
        # Duong khoa job da duoc CHUNG MINH chay chua. BA trang thai, va su
        # khac nhau giua chung la quan trong:
        #
        #   null  — chua biet: chua co lan tao job nao di qua duong nay
        #   true  — mot giao dich khoa da commit that
        #   false — da thu va hong; dang chay o duong cu, KHONG co khoa
        #
        # Truoc day cho nay ep ve `bool(...)`, nen "chua biet" hien ra thanh
        # `false`, va co khoi tao lac quan `True` thi hien thanh `true` khi
        # chua he thu gi. Ca hai deu khien mot lan kiem `/api/health` ngay sau
        # deploy tra loi sai — da xay ra that.
        "job_lock_ready": getattr(store, "_job_lock_ready", None),
    }


@app.get("/api/ready")
def ready() -> Response:
    """
    READINESS: cac phu thuoc co that su dung duoc khong.

    Tra 200 khi ca kho metadata lan kho file deu tra loi; 503 khi khong. Nen
    tang hosting dung duong nay de quyet dinh co dua traffic vao hay chua —
    khac han `/api/health`, cai chi noi tien trinh con song.

    Chi dung thao tac DOC, va khong bao gio tra ve gia tri bi mat: chi ten kho
    va dat/khong dat.
    """
    ket_qua: Dict[str, Any] = {
        "service": "fanfic-audio-api",
        "version": app.version,
        "inline_worker": settings.inline_worker,
        "phu_thuoc": {},
    }
    tot = True

    for ten, kiem in (
        ("metadata", lambda: store.list_jobs_by_status(JobStatus.RUNNING)),
        ("storage", lambda: next(iter(storage.list_objects(
            prefix="audio/__readiness__/")), None)),
    ):
        try:
            kiem()
            ket_qua["phu_thuoc"][ten] = {"dat": True}
        except Exception as exc:
            tot = False
            # Chi TEN loai loi. Thong diep co the chua endpoint hoac dinh danh.
            ket_qua["phu_thuoc"][ten] = {"dat": False, "loai_loi": type(exc).__name__}

    ket_qua["status"] = "ready" if tot else "not_ready"
    return Response(
        content=json.dumps(ket_qua, ensure_ascii=False),
        media_type="application/json",
        status_code=(status.HTTP_200_OK if tot
                     else status.HTTP_503_SERVICE_UNAVAILABLE),
    )


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


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Ket thuc phien o PHIA MAY CHU.

    Truoc day khong co duong nay: nut "Dang xuat" chi xoa token trong
    localStorage, con session secret van song nguyen o Appwrite. Nguoi dung
    thay man hinh dang nhap va tin rang minh da thoat, trong khi credential van
    dung duoc — tren may dung chung thi "dang xuat" khong bao ve duoc gi.

    KHONG dung `current_profile`: dang xuat mot token da het han phai thanh
    cong, khong phai 401. Muc tieu la "phien nay khong con dung duoc", va voi
    token hong thi dieu do da dung san.

    Luon tra 200 de client xoa token cuc bo mot cach dut khoat. `da_huy_phien`
    cho biet may chu co that su huy duoc phien hay khong.
    """
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    da_huy = False
    if token:
        try:
            da_huy = bool(identity.logout(token))
        except AuthError:
            # Token khong hop le: phien von da khong dung duoc. Khong phai loi.
            da_huy = False

    return {"da_huy_phien": da_huy}


# -----------------------------------------------------------------------------
# OAuth (Google / Facebook)
# -----------------------------------------------------------------------------

#: DANH SACH TRANG. Ten provider di thang vao URL cua Appwrite, nen nhan bat
#: ky chuoi nao la mo mot open redirect: `?provider=..%2F..%2Fevil` se dua
#: nguoi dung ra khoi Appwrite. Chi hai gia tri nay duoc phep.
OAUTH_PROVIDERS = ("google", "facebook")


def _duong_dan_noi_bo(raw: str) -> str:
    """
    Loc tham so `next`. Tra ve duong dan noi bo an toan, hoac "/".

    PHAI kiem O DAY chu khong chi o trinh duyet. Route nay nhan `next` truc
    tiep tu URL va NHUNG no vao dia chi ma Appwrite se dieu huong trinh duyet
    toi — khong kiem la mot open redirect that su, tren chinh duong dang nhap.
    Doi chieu: `web/src/lib/nav.ts` lam dung viec nay o phia trinh duyet.

    Tung dang bi tu choi, moi dang vi mot ly do:
      `https://x.tld`  tuyet doi, ra ngoai mien
      `//x.tld`        "protocol-relative": trinh duyet hieu la mien khac
      `/\\x.tld`        mot so trinh duyet chuan hoa `\\` thanh `/` -> `//`
      `write`          thieu `/` dau, de ghep nham khi noi chuoi
    """
    value = (raw or "").strip()
    if not value or not value.startswith("/"):
        return "/"
    if value.startswith("//") or "\\" in value:
        return "/"
    if value == "/login" or value.startswith("/login?"):
        return "/"      # dang nhap xong lai ve trang dang nhap = vong lap
    return value


class OAuthExchangeIn(BaseModel):
    """Cap dung-mot-lan lay tu URL callback. KHONG BAO GIO duoc ghi ra log."""

    user_id: str = Field(min_length=1, max_length=128)
    secret: str = Field(min_length=1, max_length=1024)


@app.get("/api/auth/oauth/{provider}")
def oauth_start(provider: str, next: str = "/") -> Response:
    """
    Bat dau dang nhap bang Google/Facebook.

    Tra ve 307 de TRINH DUYET tu di tiep. Khong `fetch` duoc duong nay: buoc
    sau la mot chuoi dieu huong qua Appwrite roi qua Google/Facebook, va no
    phai xay ra trong thanh dia chi cua nguoi dung.
    """
    provider = (provider or "").lower()
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Nhà cung cấp đăng nhập không được hỗ trợ.")

    # Facebook dang TAT theo cau hinh (`FAS_FACEBOOK_LOGIN`).
    #
    # Chi an cai nut o trang dang nhap la chua du: duong dan nay van goi duoc
    # bang tay, va mot duong dang nhap "khong ai thay" thi cung khong ai theo
    # doi khi no hong. Chan o day de trang thai tat la THAT.
    #
    # Phan hien thuc VAN CON nguyen — adapter, luong doi token, cau hinh
    # Appwrite. Bat lai chi la doi mot bien moi truong.
    if provider == "facebook" and not settings.facebook_login_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Đăng nhập bằng Facebook tạm thời chưa khả dụng.")

    dich = _duong_dan_noi_bo(next)
    web = settings.web_base_url.rstrip("/")
    thanh_cong = (f"{web}/auth/callback"
                  f"?provider={provider}&next={quote(dich, safe='')}")
    that_bai = f"{web}/login?error=oauth&provider={provider}"

    try:
        url = identity.oauth_start_url(provider, thanh_cong, that_bai)
    except AuthError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return Response(status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                    headers={"Location": url})


@app.post("/api/auth/oauth/exchange")
def oauth_exchange(payload: OAuthExchangeIn) -> Dict[str, Any]:
    """
    Doi cap dung-mot-lan tu callback lay token cua ung dung.

    Tra ve DUNG hinh dang ma `/api/auth/login` tra ve — `{token, profile}` —
    nen phia trinh duyet khong co he thong phien thu hai nao. Nguoi dung dang
    nhap bang Google, sau buoc nay, khong khac gi nguoi dung dang nhap bang mat
    khau.

    Ho so ung dung duoc lap cho neu chua co: nguoi dung OAuth khong di qua
    `/api/auth/register` nen ho khong co ban ghi ho so nao.
    """
    try:
        token = identity.exchange_oauth_token(payload.user_id, payload.secret)
        profile = identity.profile_from_token(token)
        profile = identity.ensure_profile(profile)
    except AuthError as exc:
        # Thong diep da duoc adapter lam sach. KHONG them chi tiet o day:
        # `user_id` va `secret` khong duoc ro ri ra phan hoi hay log.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return {"token": token, "profile": profile.to_dict()}


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

    CONG CHAN: chi tac gia da duyet duoc xuat ban. Tao va sua ban nhap thi ai
    cung lam duoc — cong chi nam o day, khong o cac route khac. Tra 403 kem
    thong diep dung trang thai de giao dien mo dung luong tiep theo (dang ky /
    dang cho / gui lai / bi treo) thay vi hien mot loi chung.

    Cong nay chi co hieu luc khi `FAS_AUTHOR_GATE` duoc bat, va no MAC DINH TAT.
    Ly do nam o `Settings.author_gate_enabled`: bat truoc khi chay migration
    grandfather la khoa toan bo tac gia hien co ra khoi cong viec cua ho.
    """
    if settings.author_gate_enabled:
        try:
            creators.assert_can_publish(profile)
        except AuthorStateError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
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


def _progress_sink(job: TtsJob, fence: int):
    """
    Tao callback tien do co TIET CHE ghi ben vung.

    Bo nho luon duoc cap nhat ngay — day la thu `/api/jobs` doc khi job chay
    tren cung tien trinh web. Kho ben vung thi chi ghi khi dang ghi, vi
    `GET /api/jobs/{id}` o production doc tu kho, va worker lai o mot may khac.

    GHI KHI DU MOT TRONG BA:
      * `total_parts` vua duoc biet — con so nay den mot lan va giao dien can
        no NGAY de chuyen tu thanh chay vo dinh sang thanh co ty le;
      * da qua `JOB_PROGRESS_SECONDS` tu lan ghi truoc;
      * ty le da nhich them `JOB_PROGRESS_PERCENT` diem tro len.

    Dieu kien theo PHAN TRAM la de chuong ngan van muot: 4 doan thi moi doan
    la 25%, va cho du 3 giay se lam thanh tien trinh nhay giat.

    Ghi hong (mang chap, mat lease) KHONG lam job that bai: tien do la thong
    tin phu, con `save_job_fenced` o cac transition moi la thu quyet dinh ket
    qua. Mat mot lan ghi thi lan sau ghi con so moi hon.
    """
    trang_thai = {"luc": 0.0, "phan_tram": -1, "da_biet_tong": False}

    def progress(done: int, total: int) -> None:
        # Bo nho truoc, va luon luon.
        job.done_parts = done
        job.total_parts = total

        bay_gio = time.monotonic()
        phan_tram = int(round(100.0 * done / total)) if total else 0
        lan_dau_biet_tong = bool(total) and not trang_thai["da_biet_tong"]

        nen_ghi = (
            lan_dau_biet_tong
            or bay_gio - trang_thai["luc"] >= JOB_PROGRESS_SECONDS
            or phan_tram - trang_thai["phan_tram"] >= JOB_PROGRESS_PERCENT
        )
        if not nen_ghi:
            return

        # Cap nhat moc TRUOC khi goi mang: neu lan ghi nay treo lau, cac tick
        # ke tiep khong duoc don nhau xep hang cho no.
        trang_thai["luc"] = bay_gio
        trang_thai["phan_tram"] = phan_tram
        if total:
            trang_thai["da_biet_tong"] = True

        try:
            store.save_progress(job.job_id, fence, WORKER_ID, done, total)
        except Exception:
            # Tien do la thong tin phu. Mot lan ghi hong khong duoc lam hong ca
            # job — ket qua that do cac transition quyet dinh.
            pass

    return progress


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

    # Sink tien do PHAI dung sau khi co `fence` that: moi lan ghi ben vung deu
    # kem fencing token, va o tren `fence` con co the la None.
    progress = _progress_sink(job, fence)

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
                ok = store.renew_lease(job.job_id, fence, WORKER_ID,
                                       _lease_until())
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

        # -- da mat quyen thi BUONG ngay, truoc khi cham vao kho --------------
        #
        # `lost` bat len khi mot nhip heartbeat bi tu choi, tuc la job da thuoc
        # ve worker khac. Truoc day co nay duoc dat nhung KHONG AI DOC: ta van
        # upload, van goi `create_track`, roi moi bi `save_job_fenced` chan o
        # buoc cuoi. Ket qua van dung (khoa object tat dinh, track tim-hoac-tao)
        # nhung do la lam viec thua tren du lieu ma minh khong con quyen.
        #
        # Ra ve TAY TRANG, KHONG goi `_mark_failed`: job khong that bai, no chi
        # doi chu. Ghi `failed` o day la dap len worker dang chay that.
        if lost.is_set():
            return

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


#: Tien trinh NAY co duoc phep chay job hay khong.
#:
#: Khac han `settings.inline_worker`, va su khac biet do quan trong: cai kia noi
#: "WEB co tu chay job khong", con cai nay noi "TIEN TRINH NAY co chay job
#: khong". Gop hai y do vao mot co la mot loi that: worker rieng cung doc
#: `FAS_INLINE_WORKER=false`, nen no se nhan job roi khong chay, va moi vong quet
#: lai dot them mot `attempts` cho den khi job `failed`. Da gap khi dien tap.
_CAN_RUN_JOBS = settings.inline_worker


def enable_job_execution() -> None:
    """
    Cho phep tien trinh nay chay job. CHI `server/worker.py` duoc goi.

    Tien trinh web khong bao gio goi, nen o staging web chi phuc vu request.
    """
    global _CAN_RUN_JOBS
    _CAN_RUN_JOBS = True


def can_run_jobs() -> bool:
    return _CAN_RUN_JOBS


def _start_job_thread(job: TtsJob, text: str, fence: Optional[int],
                      ten: str) -> bool:
    """
    Chay job trong thread nen cua CHINH tien trinh nay.

    Tra ve False va khong lam gi khi tien trinh nay khong duoc phep chay job:
    luc do job da nam ben vung o `pending`/`running` va `server/worker.py` se
    nhan no. Day la MOT cho duy nhat quyet dinh dieu do, nen khong co duong nao
    vo tinh spawn thread trong tien trinh web o staging.
    """
    if not _CAN_RUN_JOBS:
        return False
    thread = threading.Thread(target=_run_job, args=(job, text, fence),
                              daemon=True, name=ten)
    with _job_lock:
        # CHOT CHAN CUOI CUNG trong tien trinh nay.
        #
        # `claim_job` da tu choi cap fence khi lease con song, nhung do la mot
        # kiem tra qua mang: giua luc doc va luc ghi van con khe. Cho nay thi
        # khong — `_job_lock` la khoa trong bo nho, va MOI duong khoi dong job
        # (route tao job, bo quet recovery, duong chay lai) deu di qua day. Neu
        # tien trinh nay dang chay job do roi thi tu choi han.
        dang_chay = _job_threads.get(job.job_id)
        if dang_chay is not None and dang_chay.is_alive():
            return False
        _job_threads[job.job_id] = thread
    thread.start()
    return True


def recover_stale_jobs(pending_min_age_seconds: Optional[int] = None) -> Dict[str, int]:
    """
    Tim job `running` da mat worker va xu ly dung mot lan.

    IDEMPOTENT: chay lai bao nhieu lan cung duoc. Job con lease hop le bi bo qua,
    job da `completed`/`failed` khong nam trong danh sach quet.

    TUYET DOI KHONG danh dau moi job `running` thanh `failed` luc khoi dong — do
    la cach lam pha du lieu cua nguoi dung dang co job chay binh thuong o mot
    tien trinh khac.
    """
    # Job `pending` moi tinh: o che do inline, thread cua route dang lo no, nen
    # bo quet phai cho du lau moi duoc gianh. O worker rieng thi KHONG co thread
    # nao nhu vay — cho 90 giay moi bat dau doc mot job vua tao la vo ly, nen
    # worker truyen 0.
    nguong = (JOB_LEASE_SECONDS if pending_min_age_seconds is None
              else max(0, pending_min_age_seconds))
    report = {"da_quet": 0, "bo_qua_con_lease": 0, "chay_lai": 0,
              "het_luot_thu": 0, "khong_nhan_duoc": 0, "bo_qua_con_moi": 0}
    if not _CAN_RUN_JOBS:
        # Tien trinh nay khong chay job duoc thi cung khong duoc NHAN job. Nhan
        # ma khong chay se tang `attempts` moi vong quet va day job den `failed`
        # trong khi khong he thu tong hop lan nao.
        report["khong_duoc_phep_chay"] = 1
        return report
    try:
        candidates = list(store.list_jobs_by_status(JobStatus.RUNNING))
        # `pending` cung co the bi bo roi: server chet NGAY SAU `create_job` va
        # TRUOC khi thread kip doi sang `running`. Job do khong co lease nao ca,
        # nen loc bang tuoi cua no.
        for job in store.list_jobs_by_status(JobStatus.PENDING):
            if nguong == 0 or _older_than(job.created_at, nguong):
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

        # TIEN TRINH NAY DANG CHAY JOB DO ROI -> bo qua, va bo qua TRUOC khi
        # nhan.
        #
        # `job` o day den tu mot lan doc danh sach qua Appwrite. Ban doc do co
        # the cu hon lan claim vua roi vai giay, nen `lease_is_live()` o tren
        # noi "chua ai giu" trong khi thuc te chinh ta dang tong hop. Truoc day
        # bo quet cu the ma nhan tiep: `claim_job` thay `lease_owner` la chinh
        # minh nen dong y, `attempts` len 2, va mot thread thu hai bat dau goi
        # TTS cho cung mot chuong. Da do that tren staging.
        #
        # Kiem tra o day chu khong chi trong `_start_job_thread` vi thu tu quan
        # trong: nhan xong roi moi phat hien thi da dot mat mot luot `attempts`
        # va cuop lease cua chinh thread dang chay.
        with _job_lock:
            dang_chay = _job_threads.get(job.job_id)
        if dang_chay is not None and dang_chay.is_alive():
            report["bo_qua_dang_chay_o_day"] = (
                report.get("bo_qua_dang_chay_o_day", 0) + 1)
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

        if _start_job_thread(job, chapter.content, fence,
                             f"tts-recover-{job.job_id}"):
            report["chay_lai"] += 1
        else:
            # Khong the xay ra: da chan o dau ham. Neu co, dem rieng chu khong
            # bao "da chay lai" cho mot thu khong chay.
            report["khong_chay_duoc"] = report.get("khong_chay_duoc", 0) + 1
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

    KHI `inline_worker` TAT: khong bat bo quet o day. Recovery la viec cua
    `server/worker.py`. Neu ca hai cung quet thi khong sai — claim nguyen tu lo
    duoc — nhung web se giu job va chay TTS trong tien trinh phuc vu request,
    dung cai ma viec tach worker nham loai bo.
    """
    if not settings.inline_worker:
        return
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

    # CUNG danh sach trang ma `/api/voices` dung. Mot giong bi an khoi danh
    # sach nhung van submit job duoc la lo hong kinh dien — va la trang thai
    # cua he thong nay truoc day: `/api/voices` loc giong cuc bo, con
    # `POST /api/jobs` khong he kiem tra `voice_id`.
    #
    # Kiem o day, TRUOC khi tao job: job da ghi xuong roi moi tu choi thi
    # nguoi dung se thay mot job `failed` thay vi mot loi doc duoc.
    try:
        tts_bridge.ensure_voice_public(payload.voice_id, settings)
    except tts_bridge.TtsBridgeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    fingerprint = job_fingerprint(
        chapter.content, payload.voice_id, payload.rate, payload.chunk_chars
    )
    existing = store.find_job_by_fingerprint(profile.user_id, chapter.chapter_id, fingerprint)
    if existing is not None:
        # Job KET — `running` ma khong con worker nao giu. Truoc day nhanh nay tra
        # lai chinh cai job chet do, mai mai: nguoi dung bam "Tao audio" va nhan
        # ve mot job khong bao gio nhich. Nay thi nhan lai va chay tiep.
        if (existing.is_stale and (existing.attempts or 0) < JOB_MAX_ATTEMPTS
                and _CAN_RUN_JOBS):
            # `_CAN_RUN_JOBS` phai duoc hoi TRUOC KHI NHAN, khong phai sau.
            #
            # O staging/production, tien trinh web chay voi
            # FAS_INLINE_WORKER=false: no khong chay job. Truoc day nhanh nay
            # van nhan job — `_claim_stale_job` khong he hoi ai duoc phep chay —
            # roi `_start_job_thread` tra False va khong lam gi. Cai gia la mot
            # luot `attempts` bi dot va mot lease 90 giay cap cho mot tien trinh
            # se khong bao gio dung den, tuc la worker that phai dung ngoai cho
            # het lease. Bam "Tao audio" du ba lan la job `failed` voi ly do
            # "worker cu bi dung giua chung" — trong khi chua he co lan tong hop
            # nao. Cung mot loi da duoc chan o `recover_stale_jobs`, cho nay bi
            # bo sot.
            fence = _claim_stale_job(existing)
            if fence is not None:
                _start_job_thread(existing, chapter.content, fence,
                                  f"tts-resume-{existing.job_id}")
        elif existing.is_stale and (existing.attempts or 0) >= JOB_MAX_ATTEMPTS:
            # Dieu kien HET LUOT phai viet ra o day, khong duoc dua vao viec
            # "nhanh tren khong khop". Nhanh tren con hoi ca `_CAN_RUN_JOBS`,
            # nen neu chi de `elif existing.is_stale` thi tren tien trinh web
            # (khong chay job duoc) MOI job ket deu roi thang vao day va bi danh
            # `failed` — ke ca job moi thu mot lan, von hoan toan cuu duoc.
            #
            # Nhanh nay thi tien trinh web VAN duoc lam, va co chu y: day chi la
            # mot lan ghi trang thai, khong nhan job va khong dot `attempts`.
            # Job da het luot thu va khong con lease, nen khong worker nao dang
            # giu no. Neu de danh cho bo quet thi luc worker chet nguoi dung se
            # thay mot job "dang chay" vinh vien khong loi giai thich.
            _mark_failed(
                existing, "worker_lost",
                f"Đã thử tạo audio {existing.attempts} lần nhưng lần nào tiến "
                "trình cũng bị dừng giữa chừng. Hãy thử lại, hoặc chia chương "
                "thành phần ngắn hơn.",
            )
        return {"job": store.get_job(existing.job_id).to_dict(), "reused": True}

    # TRAN SO JOB DANG XEP HANG cua chinh nguoi nay.
    #
    # SAU nhanh dung-lai-job-cu o tren, co y: nhanh do khong tao them viec cho
    # worker nao ca, chan no chi lam nguoi dung khong xem lai duoc audio da co.
    #
    # Dem o day chi la mot anh chup — hai request song song deu co the thay 2 va
    # cung tao job thu 3. Chap nhan duoc: day la ran de lich su chu khong phai
    # rao bao mat. Thu that su bao ve may worker la concurrency Piper bang 1.
    dang_xep = sum(1 for j in store.list_jobs(profile.user_id)
                   if j.status in (JobStatus.PENDING, JobStatus.RUNNING))
    if dang_xep >= MAX_ACTIVE_JOBS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Bạn đang có {dang_xep} audio chờ xử lý. Hãy đợi xong bớt rồi tạo "
            f"tiếp (tối đa {MAX_ACTIVE_JOBS} cùng lúc).",
        )

    # transition: (khong co) -> pending. Ghi ben vung NGAY, truoc khi khoi
    # dong thread, de job luon ton tai trong metadata backend du worker chet.
    # transition: (khong co) -> pending, KEM KHOA TAT DINH.
    #
    # `find_job_by_fingerprint` o tren la doc-roi-ghi, va giua hai buoc do co
    # mot khe ho. Da lot qua khe ho do tren production: nam request trong 2
    # giay deu doc thay "chua co" va deu tao mot job cho CUNG mot chuong —
    # nam hang `tts_jobs` cung fingerprint, nam lan chay TTS.
    #
    # `create_job_once` dong khe ho: hang khoa co `rowId` tat dinh nam cung
    # transaction voi hang job, nen chi mot request commit duoc. Ke thua nhan
    # ve job CUA NGUOI THANG va khong duoc khoi dong thread nao.
    job, vua_tao = store.create_job_once(
        TtsJob(
            owner_id=profile.user_id,
            chapter_id=chapter.chapter_id,
            voice_id=payload.voice_id,
            content_hash=fingerprint,
            rate=payload.rate,
            chunk_chars=payload.chunk_chars,
        ),
        fingerprint,
    )

    # Chup trang thai TRUOC khi khoi dong worker: neu doc sau `start()`, worker
    # co the da doi sang `running` va phan hoi "vua tao" se mo ta sai.
    created = job.to_dict()

    if not vua_tao:
        # Thua cuoc. TUYET DOI khong khoi dong thread: nguoi thang da lam viec
        # do, va hai thread cho cung mot job la dung cai loi vong nay chan.
        return {"job": created, "reused": True}

    _start_job_thread(job, chapter.content, None, f"tts-job-{job.job_id}")
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


#: Thu tu uu tien khi chon "job dang ke nhat" cua mot chuong.
#:
#: Job DANG CHAY thang moi thu khac, ke ca mot job hoan tat moi hon: cai nguoi
#: dung can thay sau khi tai lai trang la thanh tien trinh, khong phai ket qua
#: cu. `running` truoc `pending` vi no da co tien do that de hien.
_UU_TIEN_JOB = {
    JobStatus.RUNNING: 0,
    JobStatus.PENDING: 1,
    JobStatus.COMPLETED: 2,
    JobStatus.FAILED: 3,
}


@app.get("/api/chapters/{chapter_id}/jobs/latest")
def latest_job_for_chapter(
    chapter_id: str,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Job dang ke nhat cua mot chuong — de giao dien tim lai sau khi tai lai trang.

    VI SAO CAN: `/write` truoc day giu job DUY NHAT trong state cua React. Tai
    lai trang la mat `job_id`, du job that van dang chay tren worker. Nguoi
    dung khong con duong nao theo doi no, va cach duy nhat de "thay lai tien
    trinh" la bam tao lai — tuc la xep them mot job nua cho mot viec dang chay.

    KHO MOI LA NGUON SU THAT, khong phai localStorage: trinh duyet co the bi
    xoa du lieu, mo o may khac, hoac giu mot `job_id` da bi worker khac thay
    the sau khi lease chet.

    Tra ve `null` khi chuong chua co job nao — do KHONG phai loi.
    """
    # Quyen: `_load_chapter` da kiem chuong ton tai; con so huu thi kiem o day.
    # Loc theo `owner_id` mot lan nua o `list_jobs` la lop thu hai, khong thua:
    # mot chuong co the doi chu so huu trong tuong lai, con job thi khong.
    try:
        chapter = store.get_chapter(chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if chapter.owner_id != profile.user_id:
        # 404 chu khong phai 403: nguoi la khong duoc biet chuong nay co ton tai.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy chương.")

    items = store.list_jobs(profile.user_id, chapter_id)
    if not items:
        return {"job": None}

    # Hai buoc, moi buoc mot tieu chi. Gop ca hai vao mot khoa `sorted` thi
    # phai dao nguoc chuoi thoi gian — mot meo de go sai va kho doc lai.
    uu_tien = min(_UU_TIEN_JOB.get(j.status, 9) for j in items)
    ung_vien = [j for j in items if _UU_TIEN_JOB.get(j.status, 9) == uu_tien]
    chon = max(ung_vien, key=lambda j: j.created_at)
    return {"job": chon.to_dict()}


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


# -----------------------------------------------------------------------------
# Tac gia: don, ho so cong khai, tim kiem, uy tin
# -----------------------------------------------------------------------------
#
# KHONG co route DUYET / TU CHOI / TREO o day, va do la mot quyet dinh an toan
# chu khong phai mot viec con thieu. Du an chua co co che phan quyen quan tri:
# khong vai tro, khong bang admin, khong xac thuc hai buoc. Mo mot endpoint
# duyet ma khong co cai do la tang mot cai cong — bat ky ai doan duoc duong dan
# deu tu phong minh lam tac gia.
#
# Cac thao tac do nam o `CreatorService`, duoc kiem thu day du, va cho trang
# quan tri. Xem `docs/AUTHOR_RANK.md` muc "Viec con lai".


class UsernameIn(BaseModel):
    username: Annotated[str, StringConstraints(min_length=1, max_length=40)]


class BioIn(BaseModel):
    bio: Annotated[str, StringConstraints(max_length=400)] = ""


class ApplyIn(BaseModel):
    pen_name: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    bio: Annotated[str, StringConstraints(max_length=400)] = ""
    genres: List[Annotated[str, StringConstraints(max_length=40)]] = Field(
        default_factory=list)
    intro: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    accepted_rules: bool = False


class ListenIn(BaseModel):
    """
    Bao cao mot lan nghe.

    `listened_seconds` do TRINH DUYET gui, nen no KHONG duoc tin: may chu con ap
    nguong, chan tu nghe, va chan tinh lai trong 24 gio. Mot client noi doi "toi
    nghe 9999 giay" cung chi doi duoc mot lan tinh moi 24 gio cho moi chuong —
    va do la tran ma he thong chap nhan o V1.
    """

    chapter_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    listened_seconds: float = Field(ge=0, le=86_400)


@app.get("/api/creator/me")
def creator_me(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Trang thai tac gia cua chinh minh, trong MOT lan goi."""
    data = creators.creator_state(profile)
    if not data["username"]:
        # Mot GOI Y de dien san vao o nhap, khong phai mot cai ten duoc gan tu
        # dong. Nguoi dung con sua duoc truoc khi no thanh cong khai.
        data["username_suggestion"] = suggest_username(
            profile.display_name, profile.email, identity.all_usernames())
    return data


@app.get("/api/creator/ranks")
def creator_ranks() -> Dict[str, Any]:
    """
    Bang hang, de giao dien ve duoc thang bac ma khong nhung nguong vao code.

    Nguong la CHINH SACH va no se doi. Mot ban frontend cu dang chay trong tab
    cua ai do khong duoc phep ve mot hang khac voi hang may chu cong nhan.
    """
    return {"tiers": [{"key": t.key, "title": t.title,
                       "min_listens": t.min_listens, "level": t.level}
                      for t in RANK_TIERS]}


@app.put("/api/creator/username")
def set_username(payload: UsernameIn,
                 profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        updated = creators.set_username(profile, payload.username)
    except UsernameTaken as exc:
        # Phai bat TRUOC `UsernameError`: `UsernameTaken` la con cua no.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except UsernameError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except AuthError as exc:
        # Ban mock nem AuthError khi index duy nhat cua kho chan — cung mot nghia.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"profile": updated.to_dict()}


@app.put("/api/creator/bio")
def set_bio(payload: BioIn,
            profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"profile": creators.set_bio(profile, payload.bio).to_dict()}


@app.post("/api/creator/apply", status_code=status.HTTP_201_CREATED)
def apply_author(payload: ApplyIn,
                 profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        app_row = creators.apply(
            profile,
            pen_name=payload.pen_name,
            bio=payload.bio,
            genres=payload.genres,
            intro=payload.intro,
            accepted_rules=payload.accepted_rules,
        )
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_public_dict(),
            "author_status": app_row.status.value}


@app.get("/api/users/{username}")
def public_profile_route(username: str) -> Dict[str, Any]:
    """
    Trang cong khai cua mot nguoi dung. KHONG can dang nhap.

    404 cho ca hai truong hop "khong ton tai" va "co nhung chua chon username":
    phan biet ra thi thanh mot cach do xem ai da dang ky.
    """
    data = creators.public_profile_by_username(username)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng.")
    return {"profile": data}


@app.get("/api/search/people")
def search_people(q: str = "", kind: str = "users",
                  limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """
    Tim nguoi. `kind=authors` thi CHI tac gia da duyet.

    Tim o MAY CHU: tai het nguoi dung ve roi loc o trinh duyet la vua cham vua
    la mot cach tai ca danh ba nguoi dung ve may khach.
    """
    limit = max(1, min(50, limit))
    offset = max(0, offset)
    return creators.search_people(q, authors_only=(kind == "authors"),
                                  limit=limit, offset=offset)


@app.post("/api/listens")
def record_listen(payload: ListenIn,
                  authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Ghi nhan mot lan nghe. May chu la nguon su that cho uy tin tac gia.

    KHONG bat buoc dang nhap: khach an danh van goi duoc, va nhan lai
    `credited=false` voi ly do. Tra 401 se lam trinh phat cua khach hien loi cho
    mot viec ho khong lam gi sai.

    Tra ve DUY NHAT `credited` va `reason` — khong tra ve so lan nghe moi cua tac
    gia: nguoi nghe khong can biet, va tra ve thi thanh mot cach dem uy tin cua
    nguoi khac bang cach bam Phat.
    """
    listener: Optional[str] = None
    try:
        listener = current_profile(authorization).user_id
    except HTTPException:
        listener = None

    try:
        chapter = store.get_chapter(payload.chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    # Do dai lay tu TRACK o may chu, khong tu client: nguong tinh theo ti le cho
    # chuong ngan phu thuoc vao no, va de client tu khai do dai la mo mot cach
    # ha nguong xuong con vai giay.
    track = store.track_for_chapter(payload.chapter_id)
    duration = float(track.duration_seconds) if track else 0.0

    return creators.record_listen(
        listener_id=listener,
        chapter_id=payload.chapter_id,
        author_id=chapter.owner_id,
        listened_seconds=float(payload.listened_seconds),
        duration_seconds=duration,
    )
