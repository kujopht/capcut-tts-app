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
import random
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints

from server import tts_bridge
from server.transcript import TRANSCRIPT_VERSION, build_transcript
from server.translation_usage import usage_recorder
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
from server.gamification import COSMETIC_CATALOG, LEVEL_TIERS, REWARD_PACKS
from server.gamification_service import (
    GamificationError,
    achievements_hien_thi as thanh_tuu_hien_thi,
    award_xp as thuong_xp,
    cap_do_hien_thi,
    cong_khai_cap_do,
    cong_khai_thanh_tuu,
    cong_khai_vat_pham_dang_trang_bi,
    equip_cosmetic,
    equip_title,
    open_reward_pack,
)
from server.appwrite_gamification_store import build_gamification_store
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
from server.social import (
    COMMENT_MAX_CHARS,
    POST_MAX_CHARS,
    RateLimited,
    SocialError,
    kiem_anh,
    mo_ta_gioi_han,
    object_key,
)
from server.social_service import SocialService
from server.translation import (
    QuotaExceeded as TranslationQuotaExceeded,
    ManualEditWouldBeOverwritten,
    TranslationError,
    UnsupportedFormat,
)
from server.translation_import import extract_text as _trich_van_ban_tep
from server.translation_providers import build_provider
from server.translation_provider_registry import ConnectionCheckError, build_provider_registry
from server.translation_byok_crypto import ByokConfigError, ByokCrypto, build_byok_crypto
from server.translation_byok_service import ByokNotConfiguredError, ProviderConnectionService
from server.translation_service import TranslationService
from server.translation_store import build_translation_store

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
creators = CreatorService(identity, store, storage)

#: Kho gamification (V4 visual completion, vong 2) — MOT the hien, dung
#: chung cho toan bo route XP/cap do/thanh tuu/vat pham. Doc lap hoan toan
#: voi `store` (novels/chapters/tts) va `translation_store` — xem
#: `server/gamification_store.py`.
gamification_store = build_gamification_store(settings)

#: Tang service cua tang xa hoi. Cung `identity`/`store`/`storage` voi moi route
#: khac — mot duong ghi duy nhat, va no la noi quyen/han muc/thong bao duoc
#: cuong che. Xem dau `server/social_service.py`.
social = SocialService(identity, store, storage,
                       han_muc=settings.social_limits or None)

#: `CreatorService` khong biet gi ve thong bao, va khong nen biet: no la tang
#: moderation cua tac gia. Noi hai tang lai bang mot moc thay vi mot import
#: nguoc — mot import nguoc se lam hai module phu thuoc vong vao nhau, va do la
#: thu rat kho thao ra sau nay.
creators.on_decision = social.notify_author_decision

#: Tang dich vu Novel Translation Studio (V5) — subsystem RIENG, khong dung
#: chung bang voi tts_jobs/novels. Kho chon theo `DATA_BACKEND` qua
#: `build_translation_store` (Part L) — CUNG mau voi `build_metadata_store`
#: (TTS): `appwrite` ma thieu cau hinh thi NEM LOI ngay luc khoi dong, KHONG
#: bao gio am tham lui ve bo nho (moi truong tin du lieu dich duoc luu se
#: mat sach moi lan restart neu khong co rao chan nay).
#:
#: Provider chon theo `settings` that: co du TRANSLATION_BASE_URL/API_KEY/
#: MODEL trong `.env` thi ra `DocuTranslateProvider` (goi that), thieu thi ra
#: mock — moi truong chua co key LLM van chay duoc, chi khong dich that.
#: TRUOC DAY goi `TranslationService(translation_store, store)` KHONG truyen
#: `settings`, nen du `.env` co dien key that cung khong bao gio duoc dung
#: (luon ngam dinh `build_provider(None)` ben trong service) — da vá.
#:
#: `inline_worker=settings.translation_inline_worker`: tien trinh web nay co
#: tu chay job dich trong thread nen hay khong — TACH RIENG voi
#: `FAS_INLINE_WORKER` cua TTS (xem `Settings.translation_inline_worker`).
translation_store = build_translation_store(settings)
#: Part Q1-Q3 — registry TUY CHON cua cac provider MIEN PHI da cau hinh du
#: (Groq/Cloudflare Workers AI qua bien moi truong RIENG cua tung nha cung
#: cap). RONG (khong provider nao) khi khong co bien nao ca — service tu lui
#: ve `self._provider` don (dong hanh vi voi truoc gio, xem
#: `TranslationService.__init__`).
translation_registry = build_provider_registry()
#: V5.1 BYOK — TUY CHON: `None` khi `TRANSLATION_BYOK_MASTER_KEY` vang mat
#: (tinh nang khong hoat dong, cac route ket noi ca nhan tra 503 ro rang —
#: xem `ByokNotConfiguredError`), nem loi NGAY neu bien co mat nhung sai
#: dinh dang (xem `build_byok_crypto`). KHONG BAO GIO la `NEXT_PUBLIC_*`.
translation_byok_crypto = build_byok_crypto()
translation_byok_svc = ProviderConnectionService(
    translation_store, crypto=translation_byok_crypto)
translation_svc = TranslationService(
    translation_store, store, provider=build_provider(settings),
    inline_worker=settings.translation_inline_worker,
    registry=translation_registry, byok=translation_byok_svc)

#: URL ky cho audio chi song ngan - backend van la noi quyet dinh quyen.
AUDIO_URL_TTL_SECONDS = 300

#: Cac phu thuoc CUA RIENG V2. Thieu chung thi tinh nang tac gia khong dung duoc,
#: nhung doc/nghe/tao audio van chay — nen chung duoc BAO RA o `/api/ready` ma
#: KHONG lam dich vu bi danh dau "chua san sang".
V2_PHU_THUOC = frozenset({"tac_gia", "uy_tin", "luot_nghe", "nhat_ky",
                          "ho_so_cong_khai"})

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
        # --- V2: bon bang tac gia -----------------------------------------
        #
        # KHONG lam `/api/ready` tra 503 khi thieu (xem `tot_v2` ben duoi): mot
        # ban trien khai truoc migration van phuc vu doc/nghe/tao audio binh
        # thuong, va tu choi nhan traffic vi mot tinh nang chua bat la lam hong
        # nhieu han sua.
        #
        # Nhung PHAI bao ra. Truoc day thieu bang la mot loi 500 chung o
        # `/api/creator/me`, va nguoi van hanh khong co cach nao biet nguyen
        # nhan la "chua chay migration" thay vi "code hong".
        ("tac_gia", lambda: store.list_applications(limit=1)),
        ("uy_tin", lambda: store.get_stats("__readiness__")),
        ("luot_nghe", lambda: store.last_credit_at("__readiness__", "__x__")),
        ("nhat_ky", lambda: store.list_events(limit=1)),
        ("ho_so_cong_khai", lambda: identity.profile_by_username("__readiness__")),
    ):
        try:
            kiem()
            ket_qua["phu_thuoc"][ten] = {"dat": True}
        except Exception as exc:
            # Bon bang V2 KHONG lam ca dich vu thanh "chua san sang" — xem ghi
            # chu o danh sach tren.
            if ten not in V2_PHU_THUOC:
                tot = False
            # Chi TEN loai loi. Thong diep co the chua endpoint hoac dinh danh.
            ket_qua["phu_thuoc"][ten] = {
                "dat": False,
                "loai_loi": type(exc).__name__,
                **({"ghi_chu": "Cần chạy `python -m scripts.setup_appwrite`"}
                   if ten in V2_PHU_THUOC else {}),
            }

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


def _ho_so_tra_ve(profile: Profile) -> Dict[str, Any]:
    """
    Ho so tra cho CHINH CHU, kem `is_admin`.

    Quyen quan tri song o bien moi truong (`Settings.admin_user_ids`), khong
    phai mot cot du lieu — nen `to_dict()` khong the tu biet. Giao dien can
    dung MOT bit nay de quyet dinh co ve muc "Quản trị" hay khong; khong co no
    thi frontend chi con cach nhung email vao ma nguon, va do la mot danh sach
    quan tri thu hai se lech voi danh sach that.

    CHI la chuyen hien-hay-an: moi route `/api/admin/*` van tu kiem quyen qua
    `admin_profile`, mot nguoi thuong go thang duong dan van nhan 403.

    Kem `avatar_url` (ky lai moi lan doc) ben canh `avatar_key` da co trong
    `to_dict()` — CUNG ly do voi `is_admin`: trinh duyet khong co credential
    cua kho nen khong tu dung tu khoa duoc.
    """
    return {**profile.to_dict(),
            "is_admin": profile.user_id in settings.admin_user_ids,
            "avatar_url": creators.avatar_url(profile)}


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
    return {"token": token, "profile": _ho_so_tra_ve(profile)}


@app.post("/api/auth/login")
def login(payload: LoginIn) -> Dict[str, Any]:
    # `profile_from_token` PHAI nam trong try: no cung goi ra Appwrite va cung
    # nem AuthError. De ngoai thi loi xac thuc thanh 500 thay vi 401.
    try:
        token = identity.login(payload.email, payload.password)
        profile = identity.profile_from_token(token)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return {"token": token, "profile": _ho_so_tra_ve(profile)}


@app.get("/api/auth/me")
def me(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"profile": _ho_so_tra_ve(profile)}


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
    return {"token": token, "profile": _ho_so_tra_ve(profile)}


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


class CoverIn(BaseModel):
    """Anh dang base64 — cung ly do voi `PostIn.image_base64`, xem ghi chu o do."""

    base64: Annotated[str, StringConstraints(min_length=1, max_length=3_000_000)]
    mime: Annotated[str, StringConstraints(max_length=60)] = ""
    width: int = 0
    height: int = 0


@app.put("/api/novels/{novel_id}/cover")
def set_novel_cover(novel_id: str, payload: CoverIn,
                    profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Tai/doi anh bia truyen.

    Kiem TRUOC khi cham kho (dung mau voi `_gan_bo_anh` cua tang xa hoi): giai
    ma, kiem MIME/kich thuoc, ROI moi upload. That bai o buoc kiem thi chua co
    gi de don.

    Khoa doi tuong TAT DINH theo `(owner_id, novel_id)` nhung DUOI tep co the
    doi giua cac lan tai (vd .jpg -> .webp) — anh bia cu voi duoi khac se mo
    coi neu khong xoa, nen xoa no SAU KHI anh moi da luu thanh cong.
    """
    if storage is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Máy chủ chưa cấu hình kho ảnh.")
    try:
        novel = store.owned_novel(novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    anh = _giai_ma_anh(payload.base64, payload.mime, payload.width, payload.height)
    try:
        kiem_anh("cover", mime=anh["mime"], so_byte=len(anh["data"]))
    except SocialError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    duoi = anh["mime"].split("/")[-1] or "webp"
    khoa_moi = object_key("cover", user_id=profile.user_id, subject_id=novel_id,
                          duoi=duoi)
    storage.put(khoa_moi, anh["data"], content_type=anh["mime"])

    khoa_cu = novel.cover_key
    updated = store.set_novel_cover(novel_id, profile.user_id, khoa_moi)

    if khoa_cu and khoa_cu != khoa_moi:
        try:
            storage.delete(khoa_cu)
        except Exception:
            # Anh cu mo coi ton vai tram KB; khong lam hong request vi mot loi
            # don kho — nguoi dung da co anh bia MOI, do la dieu ho can thay.
            pass

    return {"novel": _novel_out(updated)}


@app.delete("/api/novels/{novel_id}/cover")
def remove_novel_cover(novel_id: str,
                       profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Go anh bia — truyen lui ve hien thi gradient + rune du phong o giao dien."""
    try:
        novel = store.owned_novel(novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    updated = store.set_novel_cover(novel_id, profile.user_id, None)
    if novel.cover_key and storage is not None:
        try:
            storage.delete(novel.cover_key)
        except Exception:
            pass
    return {"novel": _novel_out(updated)}


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
    ra: Dict[str, Any] = {
        "novel": _novel_out(novel),
        "chapters": [_chapter_row(c, stamps.get(c.chapter_id)) for c in chapters],
    }
    # Trang thai theo doi ghep vao CUNG lan goi nay, chi voi truyen DA XUAT BAN
    # (ban nhap khong theo doi duoc — xem `SocialService.follow_story`).
    #
    # Ghep vao day chu khong de frontend hoi them: nut "Theo dõi truyện" khong
    # duoc phep nhay tu "chua biet" sang "dang theo doi" sau khi trang da ve
    # xong. Cung ly do voi `social` o `/api/users/{username}`.
    if novel.state is PublishState.PUBLISHED:
        ra["follow"] = social.story_follow_state(
            novel_id, optional_profile(authorization))
    return ra


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
    # Sidecar phu de di THEO audio — khong xoa rieng no thi cu moi lan tao lai
    # audio la mot file JSON mo coi nam lai trong kho (Phan 2H).
    keys += [track.transcript_key for track in tracks if track.transcript_key]
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
    # Doc trang thai CU truoc khi ghi — cung ly do voi `truoc` o `update_chapter`:
    # sau khi `store.publish_novel()` chay xong thi khong con biet day co phai
    # lan XUAT BAN THAT (draft -> published) hay chi mot lan goi lai idempotent.
    # Thuong XP chi dung cho lan THAT.
    truoc: Optional[PublishState] = None
    try:
        truoc = store.owned_novel(novel_id, profile.user_id).state
    except (NotFoundError, PermissionDenied):
        pass  # De `store.publish_novel()` o duoi nem loi dung.
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
    if truoc is not None and truoc is not PublishState.PUBLISHED:
        _thuong_xp_xuat_ban_truyen(novel, profile.user_id)
    return {"novel": _novel_out(novel)}


def _thuong_xp_xuat_ban_truyen(novel: Novel, user_id: str) -> None:
    """
    XP cho lan XUAT BAN THAT su (draft -> published) — KHONG BAO GIO lam
    hong viec xuat ban, cung triet ly voi `_bao_chuong_moi`: nuot moi loi.

    Xuat ban mot truyen lam TAT CA chuong cua no hien ra cong khai CUNG LUC
    (xem `_dem_truyen_chuong_da_xuat_ban`) — nen thuong XP cho MOI chuong
    dang co trong truyen ngay tai day, khong doi tung chuong duoc "xuat ban
    rieng" (kien truc hien tai khong co buoc do).
    """
    try:
        thuong_xp(gamification_store, user_id, "publish_first_novel",
                 source_kind="novel", source_id=user_id)
        for chapter in store.list_chapters(novel.novel_id):
            thuong_xp(gamification_store, user_id, "publish_chapter",
                     source_kind="chapter", source_id=chapter.chapter_id)
            thuong_xp(gamification_store, user_id, "publish_first_chapter",
                     source_kind="chapter", source_id=user_id)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Chapter
# -----------------------------------------------------------------------------


@app.post("/api/chapters", status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        novel = store.owned_novel(payload.novel_id, profile.user_id)
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
    # Chuong moi trong truyen DA XUAT BAN la mot chuong doc gia doc duoc NGAY:
    # danh sach chuong cua trang truyen khong loc theo trang thai chuong, chi
    # theo trang thai truyen. Nen day — chu khong phai mot nut "xuat ban
    # chuong" khong ton tai — chinh la khoanh khac "co chuong moi" ma nguoi
    # theo doi truyen can duoc bao. E2E tren staging that da chung minh duong
    # cu (doi `state` cua chuong qua PATCH) khong bao gio kich hoat duoc:
    # `ChapterPatch` khong nhan `state`.
    _bao_chuong_moi(chapter)
    # Cung ly do: truyen cha DA xuat ban tu truoc thi chuong moi nay LA cong
    # khai ngay, nen thuong XP tai day. Truyen con nhap thi cho toi khi
    # `publish_novel` quet qua (xem `_thuong_xp_xuat_ban_truyen`).
    if novel.state is PublishState.PUBLISHED:
        try:
            thuong_xp(gamification_store, profile.user_id, "publish_chapter",
                     source_kind="chapter", source_id=chapter.chapter_id)
            thuong_xp(gamification_store, profile.user_id, "publish_first_chapter",
                     source_kind="chapter", source_id=profile.user_id)
        except Exception:
            pass
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
    chapter, novel = _chapter_with_novel_or_404(chapter_id)
    viewer = optional_profile(authorization)
    if not _can_read_chapter(chapter, novel, viewer):
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


def _chapter_with_novel_or_404(chapter_id: str) -> Tuple[Chapter, Optional[Novel]]:
    """DUNG CHUNG cho `GET /api/chapters/{id}` va
    `GET /api/chapters/{id}/transcript` — cung mot chuong thi cung mot quyen
    doc, tach rieng se co ngay hai route lech nhau ve ai xem duoc gi."""
    try:
        chapter = store.get_chapter(chapter_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    try:
        novel: Optional[Novel] = store.get_novel(chapter.novel_id)
    except NotFoundError:
        novel = None
    return chapter, novel


def _can_read_chapter(chapter: Chapter, novel: Optional[Novel],
                      viewer: Optional[Profile]) -> bool:
    if novel is not None:
        return _may_read(novel, viewer)
    # Chuong mo coi (khong co truyen cha) khong sinh ra tu duong chay nao —
    # xem docs/HANDOFF.md muc "Xu ly mo coi". Khong xac minh duoc trang thai
    # xuat ban thi cho phia an toan: chi chu so huu doc duoc.
    return viewer is not None and viewer.user_id == chapter.owner_id


@app.get("/api/chapters/{chapter_id}/transcript")
def get_chapter_transcript(
    chapter_id: str,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Phu de dong bo cua ban audio HIEN TAI cua chuong — V4, Phan 2H/2I.

    CUNG quyen doc voi `GET /api/chapters/{id}` — ai doc duoc chuong thi nghe
    duoc audio cua no, nen cung xem duoc phu de cua audio do.

    TRUNG THUC ve trang thai — KHONG BAO GIO bia du lieu:
      - Chua co audio, hoac audio chua co transcript (sinh truoc tinh nang
        nay, hoac ffprobe khong do duoc mot phan luc tong hop) -> tra
        `{"available": false}`, KHONG phai 404 — day la trang thai HOP LE,
        khong phai loi.
      - Co transcript nhung file sidecar bien mat khoi kho (hi hoa, khong
        nen xay ra) -> cung `{"available": false}` thay vi 500, vi day van
        la mot trang thai nguoi dung CO THE gap va giao dien phai ve duoc.
    """
    chapter, novel = _chapter_with_novel_or_404(chapter_id)
    viewer = optional_profile(authorization)
    if not _can_read_chapter(chapter, novel, viewer):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy chương.")

    track = store.track_for_chapter(chapter_id)
    if track is None or not track.transcript_key:
        return {"available": False}
    try:
        raw = storage.get(track.transcript_key)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"available": False}
    return {"available": True, **data}


@app.patch("/api/chapters/{chapter_id}")
def update_chapter(chapter_id: str, payload: ChapterPatch,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    if isinstance(fields.get("title"), str):
        fields["title"] = fields["title"].strip()
    # Doc trang thai CU truoc khi ghi: "chuong nay vua duoc xuat ban" chi tra
    # loi duoc khi con biet no truoc do CHUA xuat ban. Sau khi ghi thi thong tin
    # do da mat, va mot lan sua tieu de cua chuong da xuat ban se ban thong bao
    # cho moi nguoi theo doi truyen — mot lan nua, moi lan.
    truoc: Optional[PublishState] = None
    try:
        truoc = store.owned_chapter(chapter_id, profile.user_id).state
    except (NotFoundError, PermissionDenied):
        # De `update_chapter` nem loi dung — no la noi duy nhat quyet dinh
        # 404 hay 403, va lam viec do o hai cho la hai cho co the lech.
        pass
    try:
        chapter = store.update_chapter(chapter_id, profile.user_id, fields)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if (chapter.state is PublishState.PUBLISHED
            and truoc is not PublishState.PUBLISHED):
        _bao_chuong_moi(chapter)
    return {"chapter": chapter.to_dict()}


def _bao_chuong_moi(chapter: Chapter) -> None:
    """
    Bao cho nguoi theo doi truyen. KHONG BAO GIO lam hong viec xuat ban.

    Chuong da len roi khi ham nay chay. Mot thong bao that lac la thu nho hon
    nhieu so voi mot request xuat ban tra 500 trong khi chuong THUC SU da duoc
    xuat ban — nguoi dung se bam lai, va lan thu hai khong con gi de lam.
    """
    try:
        novel = store.get_novel(chapter.novel_id)
        if novel.state is PublishState.PUBLISHED:
            social.notify_new_chapter(novel, chapter)
    except Exception:
        pass


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

        # `duration_seconds` do tu metadata file that (ffprobe). Khong do duoc
        # thi track van hoan tat voi 0 — thieu thoi luong khong duoc phep lam
        # hong mot ban audio da tong hop xong; cac phep kiem theo thoi luong
        # (moc binh luan, luot nghe hop le) tu lui ve nhanh du phong khi 0.
        duration = result.get("duration_seconds")
        if not duration:
            print(f"canh bao: khong do duoc thoi luong audio cua job "
                  f"{job.job_id} — track se ghi duration_seconds=0")

        # -- phu de dong bo (V4, Phan 2F-2H) — VIEC PHU, khong duoc lam hong
        # audio da tong hop xong. Loi o day chi bo trong ket qua transcript
        # rong ("chua co" — Phan 2I), khong bao gio bien mot job THANH CONG
        # thanh `failed`.
        transcript_key = ""
        chunks = result.get("chunks")
        phan_thoi_luong = result.get("part_durations_seconds")
        if chunks and phan_thoi_luong and all(d for d in phan_thoi_luong):
            try:
                transcript = build_transcript(
                    chunks, phan_thoi_luong,
                    chapter_id=job.chapter_id,
                    # `track_id` chua sinh (AudioTrack() sinh no ben duoi) —
                    # nhung khoa doc lap voi track_id, mien LUON DI KEM CUNG
                    # `output_key` (chinh no da khoa 1-1 theo content_hash),
                    # nen dung mot gia tri du doan duoc thay vi sinh truoc.
                    track_id=f"trk_{job.content_hash[:24]}",
                    source_content_hash=job.content_hash,
                )
                khoa_transcript = output_key[:-len(".mp3")] + ".transcript.json"
                storage.put(khoa_transcript,
                           json.dumps(transcript, ensure_ascii=False).encode("utf-8"),
                           content_type="application/json")
                transcript_key = khoa_transcript
            except Exception as exc:
                print(f"canh bao: khong sinh duoc transcript cho job "
                      f"{job.job_id}: {exc}")

        store.create_track(AudioTrack(
            chapter_id=job.chapter_id,
            owner_id=job.owner_id,
            voice_id=job.voice_id,
            object_key=output_key,
            content_hash=job.content_hash,
            size_bytes=result["size_bytes"],
            duration_seconds=float(duration or 0.0),
            transcript_key=transcript_key,
            transcript_version=TRANSCRIPT_VERSION if transcript_key else 0,
            source_content_hash=job.content_hash if transcript_key else "",
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

        # Giong cuc bo ma MAY NAY khong co model -> NHUONG, khong nhan.
        #
        # Chi ap dung cho worker CHUYEN TRACH (`inline_worker` tat): production
        # chay nhieu worker voi bo model khac nhau, va nhan mot job minh khong
        # chay duoc roi danh dau `failed` la giet vinh vien mot job ma worker
        # khac lam duoc. O che do inline (dev, mot tien trinh duy nhat) van
        # nhan-va-that-bai nhu cu: khong co ai khac de nhuong, va mot loi
        # "chua tai model" doc duoc tot hon mot job treo pending vo han.
        if (not settings.inline_worker
                and not tts_bridge.voice_runnable_on_this_machine(job.voice_id)):
            report["bo_qua_thieu_model"] = report.get("bo_qua_thieu_model", 0) + 1
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


#: Bo quet job DICH — hoan toan tach voi bo quet TTS o tren (event/thread
#: rieng), dung y voi "subsystem doc lap" da giu xuyen suot V5.
_translation_sweeper_stop = threading.Event()


def _translation_sweep_forever() -> None:
    while True:
        try:
            translation_svc.recover_stale_jobs()
        except Exception:
            pass
        if _translation_sweeper_stop.wait(JOB_SWEEP_SECONDS):
            return


@app.on_event("startup")
def start_translation_job_sweeper() -> None:
    """Cung ly do voi `start_job_sweeper` (TTS) nhung cho job dich — tat khi
    `translation_inline_worker` tat, vi luc do `server/translation_worker.py`
    (tien trinh rieng) chiu trach nhiem quet."""
    if not settings.translation_inline_worker:
        return
    threading.Thread(target=_translation_sweep_forever, daemon=True,
                     name="translation-job-sweeper").start()


@app.on_event("shutdown")
def stop_translation_job_sweeper() -> None:
    _translation_sweeper_stop.set()


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


def _dem_truyen_chuong_da_xuat_ban(user_id: str) -> Tuple[int, int]:
    """
    So truyen VA so chuong "cong khai" that su cua MOT nguoi dung.

    LOI THAT tim thay o vong 2: kien truc hien tai KHONG BAO GIO dat
    `Chapter.state = PUBLISHED` o bat ky duong nao (`ChapterPatch` khong
    nhan `state`, `create_chapter` khong gan, `publish_novel` chi doi trang
    thai NOVEL) — hien thi mot chuong hoan toan do TRUYEN CHA da xuat ban
    hay chua (xem `_may_read`/comment o `GET /api/novels/{id}`). Dem theo
    `chapter.state is PublishState.PUBLISHED` (nhu ban dau cua thanh tuu Giai
    doan 1) vi vay LUON RA 0 — "Chương đầu tiên" se KHONG BAO GIO mo khoa
    duoc. Sua bang cach dem chuong theo TRUYEN CHA da xuat ban.
    """
    truyen_da_xuat_ban = store.list_novels(owner_id=user_id, published_only=True)
    id_truyen_da_xuat_ban = {n.novel_id for n in truyen_da_xuat_ban}
    so_chuong = sum(
        1 for c in store.chapters_for_owner(user_id)
        if c.novel_id in id_truyen_da_xuat_ban)
    return len(truyen_da_xuat_ban), so_chuong


@app.get("/api/account/achievements")
def account_achievements(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Thanh tuu CUA CHINH MINH (V4 visual completion). MO KHOA duoc LUU THAT
    (kem `unlocked_at`) qua `gamification_service.achievements_hien_thi` —
    dieu kien van tinh tai cho tu du lieu da co, nhung lan dau dat dieu kien
    se ghi mot ban ghi vinh vien (khong bao gio "quen mo lai" du du lieu
    nguon sau nay giam, vi du truyen bi xoa).

    Chi cho chinh chu: `tts_characters_used`/so chuong xuat ban KHONG nam
    trong danh sach cho phep cong khai cua `creator.public_profile()`.
    """
    so_truyen, so_chuong = _dem_truyen_chuong_da_xuat_ban(profile.user_id)
    return {
        "achievements": thanh_tuu_hien_thi(
            gamification_store, profile.user_id,
            so_truyen_xuat_ban=so_truyen, so_chuong_xuat_ban=so_chuong,
            ky_tu_da_tong_hop=profile.tts_characters_used,
            phut_da_nghe=profile.listened_minutes),
    }


@app.get("/api/account/progress")
def account_progress(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """XP/cap do/danh xung CUA CHINH MINH — moi gia tri do MAY CHU tinh
    (xem `gamification_service.cap_do_hien_thi`), giao dien khong tu suy
    nguong tu client."""
    progress = gamification_store.get_progress(profile.user_id)
    return cap_do_hien_thi(progress)


class TitleIn(BaseModel):
    #: Chuoi rong = quay ve danh xung MAC DINH theo bac hien tai.
    title_key: str = ""


@app.post("/api/account/title")
def account_equip_title(payload: TitleIn,
                        profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Trang bi mot danh xung DA MO KHOA. Danh xung chua mo hoac khong ton
    tai deu bi tu choi O MAY CHU — khong tin gia tri client gui len."""
    try:
        progress = equip_title(gamification_store, profile.user_id, payload.title_key)
    except GamificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return cap_do_hien_thi(progress)


@app.get("/api/account/titles")
def account_titles(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Toan bo danh xung — kem co MO KHOA CHUA de giao dien ve dung, khong
    bia nguong o frontend."""
    xp = gamification_store.get_progress(profile.user_id).xp
    return {
        "titles": [
            {"key": t.key, "title": t.title, "level": t.level,
             "min_xp": t.min_xp, "unlocked": xp >= t.min_xp}
            for t in LEVEL_TIERS
        ],
    }


@app.get("/api/account/cosmetics")
def account_cosmetics(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Vat pham NGUOI DUNG DA CO, ghep voi dinh nghia catalog (ten/do
    hiem/vi tri) — kho chi luu khoa+trang bi, KHONG luu lai thong tin trung
    lap cua catalog."""
    dinh_nghia = {c.key: c for c in COSMETIC_CATALOG}
    ra = []
    for muc in gamification_store.list_cosmetics(profile.user_id):
        dn = dinh_nghia.get(muc.cosmetic_key)
        if dn is None:
            continue
        ra.append({
            "key": dn.key, "name": dn.name, "rarity": dn.rarity, "slot": dn.slot,
            "asset_ref": dn.asset_ref, "equipped": muc.equipped,
            "acquired_at": muc.acquired_at,
        })
    return {"cosmetics": ra}


@app.post("/api/account/cosmetics/{cosmetic_key}/equip")
def account_equip_cosmetic(cosmetic_key: str,
                           profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        muc = equip_cosmetic(gamification_store, profile.user_id, cosmetic_key)
    except GamificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"cosmetic_key": muc.cosmetic_key, "equipped": muc.equipped}


@app.post("/api/account/reward-packs/{pack_key}/open")
def account_open_reward_pack(pack_key: str,
                             profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Mo MOT goi thuong dang cho. KHONG tien that, khong tien te tra phi —
    xem `gamification_service.open_reward_pack`. Ket qua duoc LUU truoc khi
    tra ve, va so goi dang cho da bi tru NGAY trong request nay — tai lai
    trang khong mo lai duoc.
    """
    try:
        vat_pham, trung_lap = open_reward_pack(
            gamification_store, profile.user_id, pack_key, random.Random())
    except GamificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {
        "cosmetic": {
            "key": vat_pham.key, "name": vat_pham.name, "rarity": vat_pham.rarity,
            "slot": vat_pham.slot, "asset_ref": vat_pham.asset_ref,
        },
        "duplicate": trung_lap,
        "pending_reward_packs": gamification_store.get_progress(profile.user_id).goi_thuong_dang_cho,
    }


@app.get("/api/account/reward-packs")
def account_reward_packs() -> Dict[str, Any]:
    """Danh sach goi thuong hien co — CHI ten/khoa/trong so cong khai
    (minh bach xac suat), khong lo gi ve nguoi dung."""
    return {
        "packs": [
            {"key": p.key, "name": p.name, "rarity_weights": p.rarity_weights}
            for p in REWARD_PACKS
        ],
    }


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


class AvatarIn(BaseModel):
    """Anh dang base64 — cung khuon voi `CoverIn`."""

    base64: Annotated[str, StringConstraints(min_length=1, max_length=3_000_000)]
    mime: Annotated[str, StringConstraints(max_length=60)] = ""
    width: int = 0
    height: int = 0


@app.put("/api/creator/avatar")
def set_avatar(payload: AvatarIn,
               profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Tai/doi anh dai dien. Xem `CreatorService.set_avatar`."""
    anh = _giai_ma_anh(payload.base64, payload.mime, payload.width, payload.height)
    try:
        updated = creators.set_avatar(profile, data=anh["data"], mime=anh["mime"])
    except SocialError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"profile": _ho_so_tra_ve(updated)}


@app.delete("/api/creator/avatar")
def remove_avatar(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Go anh dai dien — giao dien lui ve chu cai dau ten."""
    updated = creators.remove_avatar(profile)
    return {"profile": _ho_so_tra_ve(updated)}


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
def public_profile_route(
    username: str,
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """
    Trang cong khai cua mot nguoi dung. KHONG can dang nhap.

    404 cho ca hai truong hop "khong ton tai" va "co nhung chua chon username":
    phan biet ra thi thanh mot cach do xem ai da dang ky.

    `social` duoc ghep vao CUNG mot lan goi thay vi de frontend hoi them.
    Ly do khong phai tiet kiem mot request: hai lan goi tao ra hai trang thai
    tai, va giao dien phai ve ca hai — cai thu hai luon la cai bi quen. Nut
    "Theo dõi" khong duoc phep nhay tu "chua biet" sang "dang theo doi" sau khi
    trang da ve xong.

    Nguoi xem la TUY CHON: khach vang lai van thay so lieu, chi khong thay co
    "dang theo doi" (no luon `false`).
    """
    data = creators.public_profile_by_username(username)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng.")
    viewer = optional_profile(authorization)
    ho_so = identity.profile_by_username(username)
    if ho_so is not None:
        data["social"] = social.profile_social(ho_so, viewer)
        # Gamification CONG KHAI (V4 visual completion, vong 2) — CHI danh
        # xung/bac/thanh tuu-da-mo/vat-pham-dang-trang-bi. KHONG BAO GIO
        # dung `cap_do_hien_thi`/`achievements_hien_thi` (danh cho CHINH
        # CHU) o day — hai ham do doc/tinh tu bo dem rieng tu.
        progress = gamification_store.get_progress(ho_so.user_id)
        data["gamification"] = {
            **cong_khai_cap_do(progress),
            "achievements": cong_khai_thanh_tuu(gamification_store, ho_so.user_id),
            "equipped_cosmetics": cong_khai_vat_pham_dang_trang_bi(
                gamification_store, ho_so.user_id),
        }
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


@app.get("/api/search/posts")
def search_posts(q: str = "", limit: int = 5,
                 authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Tim trong bai dang. Muc PHU cua tim kiem toan cuc — truyen va nguoi van la
    uu tien, va giao dien hien muc nay sau cung voi it ket qua hon.

    Duoi 2 ky tu tra ve rong (khong phai loi): mot ky tu khop gan het moi bai,
    va do khong phai mot ket qua tim.
    """
    viewer = optional_profile(authorization)
    return _xa_hoi(social.search_posts, q, limit=max(1, min(20, limit)),
                   viewer=viewer)


@app.get("/api/search/audio")
def search_audio(q: str = "", limit: int = 5) -> Dict[str, Any]:
    """
    Danh muc "Audio" cua tim kiem toan cuc (Phan F/11, V4 visual completion
    vong 2) — THAT, khong con vo hieu nhu vong 1.

    Tim TRUYEN CONG KHAI khop `q`, roi giu lai truyen nao co IT NHAT MOT
    chuong da co audio (`store.audio_by_chapter`) — day la dinh nghia "audio"
    dung duoc voi kien truc HIEN TAI (audio gan voi chuong, khong phai mot
    thuc the doc lap). Dan toi `/novels/{id}`, TRANG CHI TIET TRUYEN hien co
    — mot trang /listen rieng (neu lam sau nay) la mot nhanh KHAC, ngoai
    pham vi dot nay.

    GHEP HOAN TOAN tu cac phuong thuc CONG KHAI da co san cua `MetadataStore`
    (`find_novels`/`list_chapters`/`audio_by_chapter`) — KHONG them ham moi
    vao protocol, nen ca ban Mock LAN Appwrite deu chay dung ngay, khong
    can viet them mot dong nao o `adapters.py`.

    GIOI HAN DA BIET: chi xet trong 30 truyen khop DAU TIEN (theo thu tu
    `find_novels`) — mot tu khoa rat pho bien voi hang nghin truyen co the
    bo sot truyen co audio nam ngoai 30 ket qua dau. Chap nhan duoc cho MVP;
    ghi lai o day de khong ai tuong day la tim kiem day du.
    """
    tu = q.strip()
    if len(tu) < 2:
        return {"novels": []}
    gioi_han = max(1, min(20, limit))
    UNG_VIEN = 30
    truyen, _ = store.find_novels(published_only=True, query=tu, limit=UNG_VIEN)
    ra: List[Dict[str, Any]] = []
    for n in truyen:
        chuong = store.list_chapters(n.novel_id)
        dau = store.audio_by_chapter([c.chapter_id for c in chuong])
        if not dau:
            continue
        ra.append({**_novel_out(n), "audio_chapter_count": len(dau)})
        if len(ra) >= gioi_han:
            break
    return {"novels": ra}


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

    ket_qua = creators.record_listen(
        listener_id=listener,
        chapter_id=payload.chapter_id,
        author_id=chapter.owner_id,
        listened_seconds=float(payload.listened_seconds),
        duration_seconds=duration,
    )
    # XP cho NGUOI NGHE (khac uy tin cong khai cua tac gia o tren) — chi khi
    # da dang nhap VA lan nghe nay THAT SU hop le (dung phep kiem chong farm
    # co san cua `evaluate_listen`, khong them phep kiem rieng). "Moc" o day
    # la MOT LAN moi chuong, khong phai moi ngay — source_id = chapter_id
    # nen mot chuong chi thuong XP nghe DUNG MOT LAN cho moi nguoi nghe.
    if listener and ket_qua.get("credited"):
        try:
            thuong_xp(gamification_store, listener, "listen_milestone_qualified",
                     source_kind="chapter", source_id=payload.chapter_id)
        except Exception:
            pass
    return ket_qua


# -----------------------------------------------------------------------------
# TIEP TUC DOC / NGHE (V4 visual completion, Phan B)
# -----------------------------------------------------------------------------
#
# BA khai niem KHAC voi `/api/listens` o tren, dung nham la lo du lieu sai cho:
#
#   `/api/listens`         UY TIN CONG KHAI cua tac gia — khong can dang nhap,
#                          chi dem "hop le" theo quy tac chong farm.
#   `/api/progress/*`      TIEN ICH CA NHAN cua nguoi doc/nghe — BAT BUOC dang
#                          nhap, khong ai khac thay duoc, khong dinh gi den
#                          uy tin. Ghi de CON TRO (vi tri gan nhat), khong
#                          phai mot ban ghi lich su.
#
# Y muon la "bam vao trang chu thay ngay cho minh dang do dang", khong phai
# theo doi hanh vi doc chi tiet — nen chi luu DUY NHAT (novel, chapter) gan
# nhat cho moi kieu (doc/nghe), khong luu vi tri cuon trang hay phan tram doc.


class ReadProgressIn(BaseModel):
    """Bao cao dang doc chuong nao. KHONG co truong vi tri/phan tram — trang
    doc chuong hien tai khong do cuon trang, nen se la BIA neu them vao."""

    novel_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    chapter_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ListenProgressIn(BaseModel):
    """Bao cao vi tri dang nghe. `position_seconds` CHI de hien thi thanh tien
    do — KHONG dung lam can cu tinh uy tin (xem `ListenIn` o tren, do lay tu
    track o may chu)."""

    novel_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    chapter_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    position_seconds: float = Field(ge=0, le=86_400)


@app.post("/api/progress/read")
def bao_cao_dang_doc(payload: ReadProgressIn,
                     profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Ghi con tro "dang doc chuong nao" cho module Tiep tuc doc o trang chu.

    Khong kiem `novel_id`/`chapter_id` co that su ton tai hay khong: day la
    con tro CA NHAN, chi chinh chu doc lai duoc qua `/api/progress/continue`
    (roi ham do tu bo qua con tro tro toi noi da bi xoa) — mot id sai chi lam
    con tro cua chinh nguoi goi vo dung, khong anh huong ai khac."""
    profile.last_read_novel_id = payload.novel_id
    profile.last_read_chapter_id = payload.chapter_id
    profile.last_read_at = now_iso()
    identity.save_profile(profile)
    return {"ok": True}


@app.post("/api/progress/listen")
def bao_cao_dang_nghe(payload: ListenProgressIn,
                      profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Cung vai tro voi `bao_cao_dang_doc`, kem vi tri giay de hien thanh tien
    do khi quay lai."""
    profile.last_listen_novel_id = payload.novel_id
    profile.last_listen_chapter_id = payload.chapter_id
    profile.last_listen_position_seconds = float(payload.position_seconds)
    profile.last_listen_at = now_iso()
    identity.save_profile(profile)
    return {"ok": True}


def _tiep_tuc_mot_muc(novel_id: str, chapter_id: str, luc: str, *, kieu: str,
                      vi_tri_giay: float = 0.0) -> Optional[Dict[str, Any]]:
    """Mot muc cua `/api/progress/continue`, hoac `None` neu khong co gi / con
    tro tro toi mot novel/chapter da bi xoa — AN module do, KHONG bia du lieu."""
    if not novel_id or not chapter_id:
        return None
    try:
        novel = store.get_novel(novel_id)
        chapter = store.get_chapter(chapter_id)
    except NotFoundError:
        return None
    muc: Dict[str, Any] = {
        "novel_id": novel.novel_id,
        "novel_title": novel.title,
        "chapter_id": chapter.chapter_id,
        "chapter_title": chapter.title,
        "chapter_order_index": chapter.order_index,
        "updated_at": luc,
    }
    if kieu == "listen":
        track = store.track_for_chapter(chapter_id)
        muc["position_seconds"] = vi_tri_giay
        # `None` khi chua ro do dai (track cu/da xoa) — giao dien hien vi tri
        # da nghe MA KHONG bia mot mau so, thay vi ve "17:42 / 0:00".
        muc["duration_seconds"] = (
            float(track.duration_seconds)
            if track and track.duration_seconds else None)
    return muc


@app.get("/api/progress/continue")
def tiep_tuc(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Du lieu cho hai module trang chu: Tiep tuc doc / Tiep tuc nghe."""
    return {
        "reading": _tiep_tuc_mot_muc(
            profile.last_read_novel_id, profile.last_read_chapter_id,
            profile.last_read_at, kieu="read"),
        "listening": _tiep_tuc_mot_muc(
            profile.last_listen_novel_id, profile.last_listen_chapter_id,
            profile.last_listen_at, kieu="listen",
            vi_tri_giay=profile.last_listen_position_seconds),
    }


# -----------------------------------------------------------------------------
# QUAN TRI
# -----------------------------------------------------------------------------
#
# MOI route duoi day di qua `Depends(admin_profile)`. Khong mot route nao tu
# kiem quyen bang tay, va khong mot route nao duoc phep quen — do la ca ly do
# phep kiem nam trong MOT phu thuoc thay vi trong tung than ham.
#
# Ai la quan tri do BIEN MOI TRUONG quyet dinh (`FAS_ADMIN_USER_IDS`), khong
# phai mot cot trong bang. Xem `Settings.admin_user_ids`: mot truong du lieu thi
# bat ky lo hong ghi nao cung tro thanh duong tu phong minh lam quan tri; mot
# bien moi truong thi khong co API nao cham toi duoc.
#
# Giao dien KHONG bao gio la noi quyet dinh. `/admin` chi ve nhung gi cac route
# nay tra ve, va mot nguoi dung thuong go thang duong dan se nhan 403 kem mot
# than rong.


def admin_profile(profile: Profile = Depends(current_profile)) -> Profile:
    """
    Ho so cua nguoi goi, VA nguoi do phai la quan tri.

    Hai ma khac nhau, va khac biet do la co y:
      401  chua dang nhap        -> `current_profile` nem
      403  dang nhap nhung khong phai quan tri

    Tra 404 cho ca hai se giau duoc su ton tai cua khu quan tri, nhung doi lai
    la mot nguoi quan tri that go nham tai khoan se khong hieu vi sao khong vao
    duoc. Khu nay khong bi mat, no chi bi khoa.
    """
    if profile.user_id not in settings.admin_user_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Khu vực quản trị.")
    return profile


class NoteIn(BaseModel):
    note: Annotated[str, StringConstraints(max_length=1000)] = ""


@app.get("/api/admin/overview")
def admin_overview(admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return creators.admin_overview()


@app.get("/api/admin/author-applications")
def admin_applications(status_filter: str = "", limit: int = 25, offset: int = 0,
                       admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return creators.admin_applications(status=status_filter or None,
                                       limit=max(1, min(100, limit)),
                                       offset=max(0, offset))


@app.get("/api/admin/author-applications/{user_id}")
def admin_application(user_id: str,
                      admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    data = creators.admin_application(user_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn.")
    return {"application": data}


@app.post("/api/admin/author-applications/{user_id}/approve")
def admin_approve(user_id: str, payload: NoteIn,
                  admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Duyet don. Goi thang tang service da duoc kiem thu — route KHONG lap lai
    mot dong logic nghiep vu nao.
    """
    try:
        app_row = creators.approve(user_id, note=payload.note,
                                   actor_id=admin.user_id)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.post("/api/admin/author-applications/{user_id}/reject")
def admin_reject(user_id: str, payload: NoteIn,
                 admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Tu choi don. `note` la BAT BUOC o tang service — mot lan tu choi khong ly do
    la mot cai cua dong im lang, va nguoi nop se doc duoc ghi chu nay.
    """
    try:
        app_row = creators.reject(user_id, note=payload.note,
                                  actor_id=admin.user_id)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.get("/api/admin/authors")
def admin_authors(limit: int = 25, offset: int = 0,
                  admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return creators.admin_authors(limit=max(1, min(100, limit)),
                                  offset=max(0, offset))


@app.post("/api/admin/authors/{user_id}/suspend")
def admin_suspend(user_id: str, payload: NoteIn,
                  admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Tam dung quyen xuat ban.

    KHONG cham vao noi dung da co: truyen da xuat ban van cong khai, ban nhap van
    con, chuong va audio khong bi xoa. Chi cac lan xuat ban MOI bi chan. Xem
    `docs/ADMIN.md` muc "Treo tac gia lam gi va KHONG lam gi".
    """
    try:
        app_row = creators.suspend(user_id, note=payload.note,
                                   actor_id=admin.user_id)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.post("/api/admin/authors/{user_id}/restore")
def admin_restore(user_id: str, payload: NoteIn,
                  admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    try:
        app_row = creators.restore(user_id, note=payload.note,
                                   actor_id=admin.user_id)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.get("/api/admin/users")
def admin_users(q: str = "", limit: int = 25, offset: int = 0,
                admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """Tim nguoi dung. Ket qua CO `email` — day la duong quan tri."""
    return creators.admin_users(query=q, limit=max(1, min(100, limit)),
                                offset=max(0, offset))


@app.get("/api/admin/users/{user_id}")
def admin_user(user_id: str,
               admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    data = creators.admin_user(user_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng.")
    return {"user": data}


@app.get("/api/admin/novels")
def admin_novels(q: str = "", state: str = "", limit: int = 25, offset: int = 0,
                 admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Duyet truyen — CHI DOC.

    Khong co route go xuong hay xoa: backend chua co luong takedown nao an toan,
    va dat mot nut xoa len mot luong chua thiet ke la cach nhanh nhat de mat noi
    dung cua nguoi khac. Xem `docs/ADMIN.md` muc "Viec con lai".
    """
    return creators.admin_novels(query=q, state=state,
                                 limit=max(1, min(100, limit)),
                                 offset=max(0, offset))


@app.get("/api/admin/events")
def admin_events(limit: int = 50, offset: int = 0,
                 admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """Nhat ky kiem duyet. CHI THEM — khong co route sua hay xoa."""
    return creators.admin_events(limit=max(1, min(200, limit)),
                                 offset=max(0, offset))


# -----------------------------------------------------------------------------
# XA HOI
# -----------------------------------------------------------------------------
#
# MOI route duoi day chi lam ba viec: doi kieu dau vao, goi mot phuong thuc cua
# `social`, va doi loi thanh ma trang thai. Khong mot dong logic nghiep vu nao o
# day — quyen, han muc va thong bao deu o `server/social_service.py`.
#
# Ly do khong phai phong cach: mot phep kiem quyen viet trong than route chi bao
# ve DUNG route do. Cung mot phep kiem o tang dich vu bao ve moi duong goi toi
# no, ke ca duong duoc them sau nay boi mot nguoi khong doc lai tep nay.


class FollowIn(BaseModel):
    """Body rong — id nam trong duong dan. Giu lop de them truong sau nay."""


class PostIn(BaseModel):
    text: Annotated[str, StringConstraints(max_length=POST_MAX_CHARS)] = ""
    kind: Annotated[str, StringConstraints(max_length=20)] = "post"
    novel_id: Annotated[str, StringConstraints(max_length=64)] = ""
    #: Anh dang base64, KHONG phai multipart.
    #:
    #: Vi sao: multipart doi goi `python-multipart`, va goi do hien chi co mat
    #: trong moi truong nay vi gradio keo theo — no KHONG nam trong
    #: `server/requirements.txt`. Mot ban cai backend sach se thieu no, va route
    #: nay se hong ngay khi trien khai that. Base64 ton them 33% duong truyen
    #: cho mot tep toi da 1 MB; do la cai gia re hon nhieu so voi mot phu thuoc
    #: khong khai bao.
    image_base64: Annotated[str, StringConstraints(max_length=3_000_000)] = ""
    image_mime: Annotated[str, StringConstraints(max_length=60)] = ""
    image_width: int = 0
    image_height: int = 0
    #: V3: toi da BON anh. Moi phan tu cung hinh dang voi bo truong don o tren.
    #: Tran do dai danh sach o day chi la lop chan tho — tran THAT (so anh,
    #: tong byte) nam o `server/social.py` va duoc kiem sau khi giai ma.
    images: List["AnhIn"] = Field(default_factory=list, max_length=6)


class AnhIn(BaseModel):
    base64: Annotated[str, StringConstraints(min_length=1,
                                             max_length=3_000_000)]
    mime: Annotated[str, StringConstraints(max_length=60)] = ""
    width: int = 0
    height: int = 0


class PostPatch(BaseModel):
    text: Annotated[str, StringConstraints(max_length=POST_MAX_CHARS)] = ""


class CommentIn(BaseModel):
    text: Annotated[str, StringConstraints(min_length=1,
                                          max_length=COMMENT_MAX_CHARS)]
    parent_id: Annotated[str, StringConstraints(max_length=64)] = ""


class ChapterCommentIn(CommentIn):
    """Binh luan chuong: them moc audio (mili giay) va co spoiler."""

    #: `None` = khong dinh kem. Tran tho 12h; tran THAT theo thoi luong track
    #: nam o `social.kiem_timestamp`.
    timestamp_ms: Optional[int] = Field(default=None, ge=0,
                                        le=12 * 60 * 60 * 1000)
    spoiler: bool = False


class ReportIn(BaseModel):
    target_kind: Annotated[str, StringConstraints(max_length=20)]
    target_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    reason: Annotated[str, StringConstraints(max_length=30)]
    detail: Annotated[str, StringConstraints(max_length=500)] = ""


class ResolveIn(BaseModel):
    dismiss: bool = False
    note: Annotated[str, StringConstraints(max_length=1000)] = ""


class RemoveIn(BaseModel):
    reason: Annotated[str, StringConstraints(max_length=1000)] = ""


def _xa_hoi(fn, *args, **kwargs):
    """
    Goi tang dich vu va doi loi cua no thanh ma HTTP.

    MOT cho lam phep doi nay. Lap `try/except` bon tang trong ba muoi route la
    ba muoi cho co the quen mot tang — va tang bi quen thuong la `RateLimited`,
    tuc la mot loi 500 thay vi mot loi 429 doc duoc.
    """
    try:
        return fn(*args, **kwargs)
    except RateLimited as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except SocialError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _giai_ma_anh(b64: str, mime: str, width: int, height: int) -> Dict[str, Any]:
    import base64
    import binascii

    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Ảnh không hợp lệ.") from exc
    return {"data": data, "mime": mime, "width": width, "height": height}


def _bo_anh_tu_body(payload: "PostIn") -> List[Dict[str, Any]]:
    """
    Giai ma MOI anh cua bai: danh sach `images` (V3) + truong don cu neu co.

    Client cu chi gui truong don van chay; client moi gui danh sach. Gop o day
    de tang dich vu chi thay MOT danh sach.
    """
    ra: List[Dict[str, Any]] = []
    if payload.image_base64:
        ra.append(_giai_ma_anh(payload.image_base64, payload.image_mime,
                               payload.image_width, payload.image_height))
    for anh in payload.images:
        ra.append(_giai_ma_anh(anh.base64, anh.mime, anh.width, anh.height))
    return ra


@app.get("/api/limits")
def api_limits() -> Dict[str, Any]:
    """
    Gioi han do MAY CHU quyet dinh, cho giao dien noi truoc.

    MOT nguon: `server/social.py`. Giao dien khong duoc chep tay con so nao —
    co test doi soat `web/src/lib/limits.ts` voi cho nay.
    """
    return {
        "max_chapter_chars": MAX_CHAPTER_CHARS,
        "max_active_jobs": MAX_ACTIVE_JOBS,
        **mo_ta_gioi_han(),
    }


# -- theo doi -----------------------------------------------------------------


@app.post("/api/users/{user_id}/follow")
def follow_user(user_id: str, payload: FollowIn,
                profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.follow_user, profile, user_id)


@app.delete("/api/users/{user_id}/follow")
def unfollow_user(user_id: str,
                  profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.unfollow_user, profile, user_id)


@app.post("/api/novels/{novel_id}/follow")
def follow_story(novel_id: str, payload: FollowIn,
                 profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.follow_story, profile, novel_id)


@app.delete("/api/novels/{novel_id}/follow")
def unfollow_story(novel_id: str,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.unfollow_story, profile, novel_id)


# -- bai dang -----------------------------------------------------------------


@app.get("/api/feed")
def api_feed(limit: int = 0, offset: int = 0,
             authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Bang tin. KHONG doi dang nhap — khach vang lai thay bang tin kham pha.

    Dung `optional_profile`: mot trang cong dong tra 401 cho nguoi chua dang nhap
    la mot canh cua dong, va noi dung o day von la cong khai.
    """
    viewer = optional_profile(authorization)
    return _xa_hoi(social.feed, viewer, limit=limit or None,
                   offset=max(0, offset))


@app.post("/api/posts", status_code=status.HTTP_201_CREATED)
def create_post(payload: PostIn,
                profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"post": _xa_hoi(social.create_post, profile, text=payload.text,
                            kind=payload.kind, novel_id=payload.novel_id,
                            images=_bo_anh_tu_body(payload))}


@app.get("/api/posts/{post_id}")
def get_post_detail(post_id: str,
                    authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    viewer = optional_profile(authorization)
    return {"post": _xa_hoi(social.post_detail, post_id, viewer)}


@app.patch("/api/posts/{post_id}")
def update_post(post_id: str, payload: PostPatch,
                profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"post": _xa_hoi(social.edit_post, profile, post_id,
                            text=payload.text)}


@app.delete("/api/posts/{post_id}")
def delete_post(post_id: str,
                profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    _xa_hoi(social.delete_post, profile, post_id)
    return {"deleted": True}


@app.get("/api/users/{user_id}/posts")
def user_posts(user_id: str, limit: int = 0, offset: int = 0,
               authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    viewer = optional_profile(authorization)
    return _xa_hoi(social.posts_by_user, user_id, viewer=viewer,
                   limit=limit or None, offset=max(0, offset))


# -- thich --------------------------------------------------------------------


@app.post("/api/posts/{post_id}/like")
def like_post(post_id: str, payload: FollowIn,
              profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.like_post, profile, post_id)


@app.delete("/api/posts/{post_id}/like")
def unlike_post(post_id: str,
                profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.unlike_post, profile, post_id)


# -- binh luan ----------------------------------------------------------------


@app.get("/api/posts/{post_id}/comments")
def list_post_comments(post_id: str, limit: int = 20, offset: int = 0,
                       authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    viewer = optional_profile(authorization)
    return _xa_hoi(social.comments, post_id, viewer=viewer,
                   limit=max(1, min(50, limit)), offset=max(0, offset))


@app.post("/api/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
def create_comment(post_id: str, payload: CommentIn,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"comment": _xa_hoi(social.create_comment, profile, post_id,
                               text=payload.text, parent_id=payload.parent_id)}


@app.get("/api/chapters/{chapter_id}/comments")
def list_chapter_comments(chapter_id: str, sort: str = "moi",
                          limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """
    Binh luan cua mot CHUONG. Cong khai — chi chuong cua truyen DA XUAT BAN
    (hang rao nam o `SocialService._chuong_cong_khai`; ban nhap tra 404).

    Dich la `chapter_id`, khong phai file MP3: tac gia tao lai audio thi chuoi
    binh luan van con nguyen.
    """
    return _xa_hoi(social.chapter_comments, chapter_id, sort=sort,
                   limit=max(1, min(50, limit)), offset=max(0, offset))


@app.post("/api/chapters/{chapter_id}/comments",
          status_code=status.HTTP_201_CREATED)
def create_chapter_comment(chapter_id: str, payload: ChapterCommentIn,
                           profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"comment": _xa_hoi(
        social.create_chapter_comment, profile, chapter_id,
        text=payload.text, parent_id=payload.parent_id,
        timestamp_ms=payload.timestamp_ms, spoiler=payload.spoiler)}


@app.get("/api/comments/{comment_id}/replies")
def list_replies(comment_id: str, limit: int = 20,
                 offset: int = 0) -> Dict[str, Any]:
    return _xa_hoi(social.replies, comment_id, limit=max(1, min(50, limit)),
                   offset=max(0, offset))


@app.patch("/api/comments/{comment_id}")
def update_comment(comment_id: str, payload: CommentIn,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return {"comment": _xa_hoi(social.edit_comment, profile, comment_id,
                               text=payload.text)}


@app.delete("/api/comments/{comment_id}")
def delete_comment(comment_id: str,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    _xa_hoi(social.delete_comment, profile, comment_id)
    return {"deleted": True}


# -- thong bao ----------------------------------------------------------------


@app.get("/api/notifications")
def list_notifications(unread: bool = False, limit: int = 20, offset: int = 0,
                       profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.notifications, profile, unread_only=unread,
                   limit=max(1, min(50, limit)), offset=max(0, offset))


@app.get("/api/notifications/unread")
def notifications_unread(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Chi con so, cho cai chuong. Nhe han danh sach — no chay o moi trang."""
    return _xa_hoi(social.unread_count, profile)


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, payload: FollowIn,
                           profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.mark_read, profile, notification_id)


@app.post("/api/notifications/read-all")
def mark_all_notifications_read(payload: FollowIn,
                                profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.mark_all_read, profile)


# -- bao cao ------------------------------------------------------------------


@app.post("/api/reports", status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportIn,
                  profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Bao cao mot bai hoac mot binh luan.

    KHONG BAO GIO tu go noi dung — xem `SocialService.report`.
    """
    return _xa_hoi(social.report, profile, target_kind=payload.target_kind,
                   target_id=payload.target_id, reason=payload.reason,
                   detail=payload.detail)


# -- tom tat cua chinh minh ---------------------------------------------------


@app.get("/api/account/social")
def account_social(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.account_summary, profile)


# -- kiem duyet xa hoi (quan tri) ---------------------------------------------
#
# Cung mot `Depends(admin_profile)` voi phan quan tri tac gia, va cung mot nhat
# ky `moderation_events`. Mot nhat ky, khong phai hai: nguoi doc lai mot vu viec
# muon thay MOI thu da xay ra voi mot nguoi theo thu tu.


@app.get("/api/admin/social/overview")
def admin_social_overview(admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return social.social_overview()


@app.get("/api/admin/reports")
def admin_reports(status_filter: str = "open", target_kind: str = "",
                  limit: int = 25, offset: int = 0,
                  admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.admin_reports, status=status_filter,
                   target_kind=target_kind, limit=max(1, min(100, limit)),
                   offset=max(0, offset))


@app.post("/api/admin/reports/{report_id}/resolve")
def admin_resolve_report(report_id: str, payload: ResolveIn,
                         admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return {"report": _xa_hoi(social.resolve_report, admin, report_id,
                              dismiss=payload.dismiss, note=payload.note)}


@app.get("/api/admin/posts")
def admin_posts(q: str = "", limit: int = 25, offset: int = 0,
                admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.admin_posts, query=q, limit=max(1, min(100, limit)),
                   offset=max(0, offset))


@app.post("/api/admin/posts/{post_id}/remove")
def admin_remove_post(post_id: str, payload: RemoveIn,
                      admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Go mot bai. Hang VAN CON trong kho — xem `ContentState`.

    KHONG co route xoa that o duong quan tri, va do la co y: mot quyet dinh kiem
    duyet khong con bang chung thi khong the xem lai khi bi khieu nai.
    """
    return {"post": _xa_hoi(social.remove_post, admin, post_id,
                            reason=payload.reason)}


@app.post("/api/admin/posts/{post_id}/restore")
def admin_restore_post(post_id: str, payload: FollowIn,
                       admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return {"post": _xa_hoi(social.restore_post, admin, post_id)}


@app.get("/api/admin/comments")
def admin_browse_comments(target_kind: str = "", limit: int = 25,
                          offset: int = 0,
                          admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Duyet binh luan toan he thong, TACH duoc binh luan bai dang voi binh luan
    chuong (`target_kind=chapter`) — hai loai dan toi hai noi khac nhau va
    nguoi kiem duyet can biet minh dang nhin gi.
    """
    if target_kind not in ("", "chapter"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "target_kind không hợp lệ.")
    return _xa_hoi(social.admin_browse_comments, target_kind=target_kind,
                   limit=max(1, min(100, limit)), offset=max(0, offset))


@app.get("/api/admin/posts/{post_id}/comments")
def admin_post_comments(post_id: str, limit: int = 50, offset: int = 0,
                        admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return _xa_hoi(social.admin_comments, post_id,
                   limit=max(1, min(200, limit)), offset=max(0, offset))


@app.post("/api/admin/comments/{comment_id}/remove")
def admin_remove_comment(comment_id: str, payload: RemoveIn,
                         admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return {"comment": _xa_hoi(social.remove_comment, admin, comment_id,
                               reason=payload.reason)}


@app.post("/api/admin/comments/{comment_id}/restore")
def admin_restore_comment(comment_id: str, payload: FollowIn,
                          admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return {"comment": _xa_hoi(social.restore_comment, admin, comment_id)}


# =============================================================================
# Novel Translation Studio (V5) — subsystem RIENG, xem `translation_service.py`.
# =============================================================================


def _dich_vu(fn, *args, **kwargs):
    """Cung vai tro voi `_xa_hoi()` nhung cho tang dich thuat — MOT cho doi
    loi nghiep vu thanh ma HTTP, thay vi lap try/except o tung route."""
    try:
        return fn(*args, **kwargs)
    except TranslationQuotaExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except UnsupportedFormat as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ManualEditWouldBeOverwritten as exc:
        # 409 — frontend hien hop thoai xac nhan, goi lai CUNG request voi
        # `force=true` neu nguoi dung dong y (xem docstring exception).
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ConnectionCheckError as exc:
        # V5.1 BYOK Part E — `detail` la MOT DICT (khong phai chuoi) de
        # frontend re nhanh chinh xac theo `code` SACH, khong phai doan tu
        # van ban tieng Viet. KHONG BAO GIO kem response/header goc cua nha
        # cung cap (xem docstring `ConnectionCheckError`/`kiem_tra_ket_noi_groq`).
        ma_trang_thai = {
            "INVALID_KEY": status.HTTP_400_BAD_REQUEST,
            "RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
            "PROVIDER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
            "MODEL_UNAVAILABLE": status.HTTP_400_BAD_REQUEST,
        }.get(exc.code, status.HTTP_400_BAD_REQUEST)
        raise HTTPException(
            ma_trang_thai, {"code": exc.code, "message": str(exc)}) from exc
    except ByokNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except TranslationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


class TranslateProjectIn(BaseModel):
    title: Annotated[str, StringConstraints(max_length=200)] = ""
    #: Dan TRUC TIEP — duong khac (tai tep) di qua
    #: `POST /api/translate/projects/upload`.
    source_text: Annotated[str, StringConstraints(max_length=400_000)] = ""
    genre: Annotated[str, StringConstraints(max_length=20)] = "auto"
    naming_mode: Annotated[str, StringConstraints(max_length=20)] = "auto"
    quality_mode: Annotated[str, StringConstraints(max_length=20)] = "can_bang"
    custom_instruction: Annotated[str, StringConstraints(max_length=1000)] = ""


@app.post("/api/translate/estimate")
def translate_estimate(payload: TranslateProjectIn) -> Dict[str, Any]:
    """Uoc luong THO truoc khi tao du an — khong ghi gi, khong can dang nhap
    (nguoi dung xem truoc luc con dang dan/chinh van ban)."""
    return translation_svc.estimate(payload.source_text)


@app.post("/api/translate/projects", status_code=status.HTTP_201_CREATED)
def create_translation_project(
    payload: TranslateProjectIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    project = _dich_vu(
        translation_svc.create_project, profile.user_id,
        title=payload.title, source_text=payload.source_text,
        genre=payload.genre, naming_mode=payload.naming_mode,
        quality_mode=payload.quality_mode,
        custom_instruction=payload.custom_instruction)
    return {"project": project.to_dict()}


class TranslateUploadIn(BaseModel):
    """
    Tep dang base64 — CUNG ly do voi `PostIn.image_base64`: multipart doi
    `python-multipart`, goi chua khai bao trong `server/requirements.txt`
    (chi co mat cuc bo vi mot phu thuoc khac keo theo). Base64 ton them ~33%
    duong truyen cho mot tep toi da 10 MB; re hon nhieu so voi mot phu thuoc
    khong khai bao lam vo backend luc trien khai that.
    """

    filename: Annotated[str, StringConstraints(max_length=200)]
    #: 10 MB truoc base64 -> ~13.4 MB chuoi; lam tron len cho an toan.
    base64: Annotated[str, StringConstraints(min_length=1, max_length=14_000_000)]
    title: Annotated[str, StringConstraints(max_length=200)] = ""
    genre: Annotated[str, StringConstraints(max_length=20)] = "auto"
    naming_mode: Annotated[str, StringConstraints(max_length=20)] = "auto"
    quality_mode: Annotated[str, StringConstraints(max_length=20)] = "can_bang"
    custom_instruction: Annotated[str, StringConstraints(max_length=1000)] = ""


@app.post("/api/translate/projects/upload", status_code=status.HTTP_201_CREATED)
def upload_translation_project(
    payload: TranslateUploadIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Tao du an tu mot tep tai len (.txt/.epub/.docx). Xem `translation_import.py`."""
    import base64
    import binascii

    try:
        du_lieu = base64.b64decode(payload.base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Tệp không hợp lệ.") from exc
    van_ban = _dich_vu(_trich_van_ban_tep, payload.filename, du_lieu)
    project = _dich_vu(
        translation_svc.create_project, profile.user_id,
        title=payload.title or payload.filename, source_text=van_ban,
        source_filename=payload.filename,
        genre=payload.genre, naming_mode=payload.naming_mode,
        quality_mode=payload.quality_mode,
        custom_instruction=payload.custom_instruction)
    return {"project": project.to_dict()}


@app.get("/api/translate/projects")
def list_translation_projects(
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    ds = translation_svc.list_projects(profile.user_id)
    return {"projects": [p.to_dict() for p in ds], "total": len(ds)}


@app.get("/api/translate/projects/{project_id}")
def get_translation_project(
    project_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    project = _dich_vu(translation_svc.get_project, project_id, profile.user_id)
    return {
        "project": project.to_dict(),
        "chapters": [
            {"index": i, "translated": bool(c), "text": c,
             "has_warnings": bool(
                 project.chapter_warnings[i] if i < len(project.chapter_warnings)
                 else [])}
            for i, c in enumerate(project.translated_chapters)
        ],
        "jobs": [j.to_dict()
                for j in translation_store.jobs_for_project(project_id)],
    }


@app.post("/api/translate/projects/{project_id}/jobs",
         status_code=status.HTTP_201_CREATED)
def create_translation_job(
    project_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Tao job dich. IDEMPOTENT: goi lai khi con job CHUA KET THUC tra ve CHINH
    NO — day la co che chong "F5 tao job thu hai" (xem
    `TranslationService.create_job`).
    """
    job = _dich_vu(translation_svc.create_job, project_id, profile.user_id)
    return {"job": job.to_dict()}


@app.get("/api/translate/jobs/{job_id}")
def get_translation_job(
    job_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    job = _dich_vu(translation_svc.get_job, job_id, profile.user_id)
    return {"job": job.to_dict()}


@app.post("/api/translate/jobs/{job_id}/cancel")
def cancel_translation_job(
    job_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    job = _dich_vu(translation_svc.cancel_job, job_id, profile.user_id)
    return {"job": job.to_dict()}


@app.post("/api/translate/jobs/{job_id}/retry")
def retry_translation_job(
    job_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Thu lai mot job `failed`. Vi tien do da luu o cap CHUONG, day cung chinh
    la co che "thu lai chuong da that bai / tiep tuc truyen bi ngat quang" —
    xem `TranslationService.retry_job`. 400 neu job chua `failed` (dang chay
    hoac da xong — khong co gi de thu lai).
    """
    job = _dich_vu(translation_svc.retry_job, job_id, profile.user_id)
    return {"job": job.to_dict()}


class GlossaryIn(BaseModel):
    category: Annotated[str, StringConstraints(max_length=20)] = "other"
    original: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    translated: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    note: Annotated[str, StringConstraints(max_length=500)] = ""


class GlossaryPatch(BaseModel):
    translated: Optional[Annotated[str, StringConstraints(max_length=80)]] = None
    note: Optional[Annotated[str, StringConstraints(max_length=500)]] = None
    locked: Optional[bool] = None


@app.get("/api/translate/projects/{project_id}/glossary")
def list_translation_glossary(
    project_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    ds = _dich_vu(translation_svc.list_glossary, project_id, profile.user_id)
    return {"entries": [
        {"term_id": e.term_id, "category": e.category.value,
         "original": e.original, "translated": e.translated,
         "note": e.note, "locked": e.locked}
        for e in ds
    ], "total": len(ds)}


@app.post("/api/translate/projects/{project_id}/glossary",
         status_code=status.HTTP_201_CREATED)
def add_translation_glossary(
    project_id: str, payload: GlossaryIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    e = _dich_vu(
        translation_svc.add_glossary_entry, project_id, profile.user_id,
        category=payload.category, original=payload.original,
        translated=payload.translated, note=payload.note)
    return {"term_id": e.term_id, "category": e.category.value,
           "original": e.original, "translated": e.translated,
           "note": e.note, "locked": e.locked}


@app.patch("/api/translate/projects/{project_id}/glossary/{term_id}")
def update_translation_glossary(
    project_id: str, term_id: str, payload: GlossaryPatch,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    e = _dich_vu(
        translation_svc.update_glossary_entry, project_id, profile.user_id,
        term_id, translated=payload.translated, note=payload.note,
        locked=payload.locked)
    return {"term_id": e.term_id, "category": e.category.value,
           "original": e.original, "translated": e.translated,
           "note": e.note, "locked": e.locked}


@app.delete("/api/translate/projects/{project_id}/glossary/{term_id}")
def delete_translation_glossary(
    project_id: str, term_id: str,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    _dich_vu(translation_svc.delete_glossary_entry, project_id,
            profile.user_id, term_id)
    return {"deleted": True}


@app.get("/api/translate/projects/{project_id}/chapters/{chapter_index}")
def get_translation_chapter(
    project_id: str, chapter_index: int,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    return {"chapter": _dich_vu(
        translation_svc.get_chapter_detail, project_id, profile.user_id,
        chapter_index)}


class ChapterEditIn(BaseModel):
    new_text: Annotated[str, StringConstraints(max_length=300_000)]


@app.put("/api/translate/projects/{project_id}/chapters/{chapter_index}")
def save_translation_chapter(
    project_id: str, chapter_index: int, payload: ChapterEditIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Luu SUA TAY — luon thanh cong (khong can `force`, xem
    `TranslationService.save_chapter_edit`: sua tay khong "ghi de" chinh no)."""
    return {"chapter": _dich_vu(
        translation_svc.save_chapter_edit, project_id, profile.user_id,
        chapter_index, payload.new_text)}


class RegenerateIn(BaseModel):
    #: True = nguoi dung DA XAC NHAN o hop thoai canh bao ghi de sua tay.
    force: bool = False


@app.post("/api/translate/projects/{project_id}/chapters/{chapter_index}/regenerate")
def regenerate_translation_chapter(
    project_id: str, chapter_index: int, payload: RegenerateIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Dich lai CA CHUONG tu nguon. 409 (`ManualEditWouldBeOverwritten`) neu
    chuong da duoc sua tay sau lan dich gan nhat va `force=false` — frontend
    hien hop thoai xac nhan roi goi lai voi `force=true`.
    """
    return {"chapter": _dich_vu(
        translation_svc.regenerate_chapter, project_id, profile.user_id,
        chapter_index, force=payload.force)}


@app.post(
    "/api/translate/projects/{project_id}/chapters/{chapter_index}"
    "/paragraphs/{paragraph_index}/regenerate")
def regenerate_translation_paragraph(
    project_id: str, chapter_index: int, paragraph_index: int,
    payload: RegenerateIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Dich lai MOT doan, giu nguyen phan con lai cua chuong. Cung quy tac
    409/`force` voi regen ca chuong."""
    return {"chapter": _dich_vu(
        translation_svc.regenerate_paragraph, project_id, profile.user_id,
        chapter_index, paragraph_index, force=payload.force)}


class RerunPassIn(BaseModel):
    pass_type: Annotated[str, StringConstraints(max_length=20)]
    force: bool = False


@app.post("/api/translate/projects/{project_id}/chapters/{chapter_index}/rerun")
def rerun_translation_pass(
    project_id: str, chapter_index: int, payload: RerunPassIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Chay lai DUNG MOT pass (translator/editor/qa) tren ban dich hien tai,
    khong dich lai tu nguon."""
    return {"chapter": _dich_vu(
        translation_svc.rerun_pass, project_id, profile.user_id,
        chapter_index, payload.pass_type, force=payload.force)}


@app.get("/api/translate/projects/{project_id}/versions")
def list_translation_versions(
    project_id: str, chapter_index: Optional[int] = None,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Lich su ban dich (Part O) — sap xep MOI NHAT truoc."""
    ds = _dich_vu(translation_svc.list_versions, project_id, profile.user_id,
                  chapter_index)
    return {"versions": [v.to_dict() for v in ds], "total": len(ds)}


@app.post("/api/translate/projects/{project_id}/versions/{version_id}/revert")
def restore_translation_version(
    project_id: str, version_id: str,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Phuc hoi mot phien ban cu — ghi THEM mot ban ghi moi
    (`operation=restore`), khong xoa lich su sau diem do.

    Duong dan dung `revert` (khong phai `restore`) de khong cham vao danh
    sach tu cam cua `NoAdminEndpointTest` (`server/tests/test_creator_routes.py`)
    — sentinel do BAT KY tu "restore" o BAT KY route ngoai `/api/admin/*`,
    khong phan biet duoc day la khoi phuc mot BAN DICH cua chinh nguoi dung
    (khong lien quan moderation). Doi TEN DUONG DAN, khong doi ten ham
    service (`TranslationService.restore_version`) — dung y nghia nghiep vu
    van la "restore", chi tranh trung tu khoa voi mot bai test canh gac chu
    y khac.
    """
    return {"chapter": _dich_vu(
        translation_svc.restore_version, project_id, profile.user_id,
        version_id)}


@app.get("/api/translate/providers")
def list_translation_providers() -> Dict[str, Any]:
    """
    Catalog AN TOAN cac model dich MIEN PHI da cau hinh (Part Q1/Q2) — KHONG
    yeu cau dang nhap (chi la thong tin hien thi, khong ghi gi, khong lo bi
    mat gi: xem `ProviderCatalogEntry.to_dict`).
    """
    ds = translation_svc.provider_catalog()
    return {"providers": ds, "total": len(ds)}


@app.get("/api/admin/translate/usage")
def admin_translate_usage(profile: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Nen tang ke toan pool mien phi (V5.2, overnight Phase 3, Phan 3I) —
    QUAN TRI CHI, khong danh cho nguoi dung thuong: day la so lieu VAN HANH
    (bao nhieu request/ty le loi theo TUNG model), khong phai thong tin can
    hien cho nguoi dung cuoi.

    CHUA thuc thi han muc gi — chi quan sat. Xem `server/translation_usage.py`
    ve gioi han da biet (trong bo nho, mat khi restart).
    """
    rec = usage_recorder()
    return {
        "summary_by_provider": rec.tom_tat_theo_model(),
        "recent_events": [e.to_dict() for e in rec.gan_day(200)],
    }


class ProviderSettingsPatch(BaseModel):
    provider_mode: Optional[Annotated[str, StringConstraints(max_length=16)]] = None
    selected_provider_id: Optional[Annotated[str, StringConstraints(max_length=64)]] = None
    allow_fallback: Optional[bool] = None
    #: V5.1 Part F — "Ưu tiên API key cá nhân".
    prefer_personal_provider: Optional[bool] = None


@app.patch("/api/translate/projects/{project_id}/provider")
def update_translation_provider_settings(
    project_id: str, payload: ProviderSettingsPatch,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Part Q3 — chon AUTO/MANUAL va bat/tat tu dong chuyen model mien phi
    khac khi model da chon het han muc."""
    project = _dich_vu(
        translation_svc.update_provider_settings, project_id, profile.user_id,
        provider_mode=payload.provider_mode,
        selected_provider_id=payload.selected_provider_id,
        allow_fallback=payload.allow_fallback,
        prefer_personal_provider=payload.prefer_personal_provider)
    return {"project": project.to_dict()}


# =============================================================================
# BYOK — ket noi provider AI CA NHAN cua nguoi dung (V5.1)
# =============================================================================


@app.get("/api/translate/provider-connections")
def list_provider_connections(
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """AN TOAN de tra ve — `ProviderConnection.to_dict()` KHONG BAO GIO chua
    `encrypted_secret` (xem docstring entity)."""
    ds = translation_byok_svc.list_connections(profile.user_id)
    return {"connections": [c.to_dict() for c in ds], "total": len(ds)}


class ProviderConnectionIn(BaseModel):
    api_key: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    selected_model: Annotated[str, StringConstraints(max_length=128)] = ""


@app.post("/api/translate/provider-connections/{provider_id}",
         status_code=status.HTTP_201_CREATED)
def connect_provider(
    provider_id: str, payload: ProviderConnectionIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Ket noi (hoac THAY THE) mot provider ca nhan. Kiem tra key server-side
    TRUOC khi ma hoa/luu (Part E) — that bai thi KHONG luu gi ca.

    Hien CHI ho tro `provider_id="groq"`
    (`translation_byok_service.SUPPORTED_BYOK_PROVIDERS`) — provider khac
    tra 400 ro rang qua `TranslationError`.
    """
    conn = _dich_vu(
        translation_byok_svc.connect, profile.user_id, provider_id,
        payload.api_key, selected_model=payload.selected_model)
    # Ket noi THANH CONG co the giup mot job dang `waiting_for_provider`
    # cua CHINH nguoi dung nay tiep tuc ngay (Part G) — khong tao job moi,
    # khong dich lai chuong da xong (xem `TranslationService.try_resume_user_jobs`).
    translation_svc.try_resume_user_jobs(profile.user_id)
    return {"connection": conn.to_dict()}


@app.post("/api/translate/provider-connections/{provider_id}/test")
def test_provider_connection(
    provider_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Kiem tra LAI mot ket noi DA co — dung endpoint NHE (khong dich thu,
    khong ton han muc dich — xem `kiem_tra_ket_noi_groq`)."""
    conn = _dich_vu(
        translation_byok_svc.test_connection, profile.user_id, provider_id)
    return {"connection": conn.to_dict()}


@app.delete("/api/translate/provider-connections/{provider_id}")
def delete_provider_connection(
    provider_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Xoa ket noi TAI FANFIC — KHONG thu hoi key ben phia nha cung cap (Part
    J: "Xóa tại Fanfic không thu hồi key bên Groq", nguoi dung tu quan ly
    o `https://console.groq.com/keys` neu muon thu hoi that).
    """
    translation_byok_svc.delete(profile.user_id, provider_id)
    return {"deleted": True}


class ImportDraftIn(BaseModel):
    novel_id: Annotated[str, StringConstraints(max_length=64)] = ""
    new_novel_title: Annotated[str, StringConstraints(max_length=200)] = ""


@app.post("/api/translate/projects/{project_id}/import")
def import_translation_to_draft(
    project_id: str, payload: ImportDraftIn,
    profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    return _dich_vu(
        translation_svc.import_to_draft, project_id, profile.user_id,
        novel_id=payload.novel_id, new_novel_title=payload.new_novel_title)
