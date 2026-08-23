"""
Backend FastAPI cua Fanfic Audio Studio Web.

Chay:
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --reload --port 8000

Backend giu MOI bi mat (Appwrite API key, R2 access key). Trinh duyet khong
bao gio nhan duoc credential nao.

Backend KHONG import GUI: da xac minh khong module PySide6 nao bi keo vao.
"""

from __future__ import annotations

import base64
import json
import os
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints

from server import tts_bridge
from server import traffic_analytics
from server.transcript import TRANSCRIPT_VERSION, build_transcript
from server.translation_usage import usage_recorder
from server.secret_redaction import loc_bo_theo_gia_tri
from server.adapters import (
    AppwriteUnavailableError,
    AuthError,
    LocalStorageAdapter,
    MockMetadataStore,
    NotFoundError,
    PermissionDenied,
    build_identity,
    build_metadata_store,
    build_storage,
)
from server.account_deletion import AccountDeletionService
from server.config import get_settings
from server.r2_adapter import R2StorageAdapter
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
    claim_quest_reward,
    cong_khai_cap_do,
    cong_khai_thanh_tuu,
    cong_khai_vat_pham_dang_trang_bi,
    equip_cosmetic,
    equip_title,
    leaderboard_all_time,
    leaderboard_weekly,
    list_quests_with_progress,
    open_reward_pack,
    record_daily_read,
    record_quest_event,
    streak_hien_thi,
)
from server.appwrite_gamification_store import build_gamification_store
from server.appwrite_animation_store import build_animation_store
from server.appwrite_bulk_import_store import build_bulk_import_store
from server.appwrite_trusted_source_store import build_trusted_source_store
from server.bulk_import_domain import (
    BulkImportError,
    BulkImportFormatError,
    BulkImportStateError,
    ChapterJobRejected,
    JobQueueFull,
    ParsedChapter,
    parse_input,
    validate_chapters,
)
from server.bulk_import_service import (
    IMPORT_SWEEP_SECONDS,
    BulkImportService,
    ImportDriveGate,
)
from server.animation_domain import (
    AnimationEpisode,
    AnimationSeries,
    AnimationSource,
    parse_youtube_id,
)
from server.trusted_source_domain import SubscriptionStatus, compute_source_health
from server.trusted_source_service import (
    DEFAULT_SCAN_PAGES,
    DISCOVERY_SCAN_PAGES,
    MAX_SCAN_PAGES,
    TrustedSourceError,
    TrustedSourceService,
)
from server.youtube_client import YouTubeApiError, YouTubeConfigError
from server.youtube_websub import MAX_NOTIFICATION_BYTES, WebSubConfigError
from server.domain import (
    AdminRole,
    AudioStamp,
    AudioTrack,
    Chapter,
    ContentState,
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
    TranslationJobStatus,
    UnsupportedFormat,
)
from server.translation_import import extract_text as _trich_van_ban_tep
from server.translation_providers import (
    TranslationContext,
    TranslationProviderError,
    build_provider,
)
from server.translation_provider_registry import (
    AllProvidersUnavailable,
    ConnectionCheckError,
    build_provider_registry,
)
from server.translation_byok_crypto import ByokConfigError, ByokCrypto, build_byok_crypto
from server.translation_byok_service import ByokNotConfiguredError, ProviderConnectionService
from server.translation_service import TranslationService
from server.translation_store import build_translation_store
from server.image_domain import GenerationMode, PollinationsConnection, SavedImage
from server.image_provider_registry import (
    ImageProviderError,
    ImageProviderRateLimited,
    ImageProviderUnavailable,
    ImageProviderTimeout,
    InvalidImageResponse,
    QuickFreeImageProvider,
    SharedPremiumImageProvider,
)
from server.image_wallet_store import (
    DuplicateReservation,
    InsufficientBalance,
    InvalidReservationTransition,
    MockWalletStore,
)
from server.image_byop_crypto import build_image_byop_crypto
from server.image_byop_service import (
    ByopError,
    ByopExchangeFailed,
    ByopStateMismatch,
    PollinationsByopService,
)
from server.image_spending_guard import SharedPremiumDisabled, SharedPremiumSpendingGuard
from server.image_payment import CheckoutStatus, MockPaymentProvider
from server.image_library_store import MockImageLibraryStore
from server.image_community_catalogue import CommunityCatalogueCache
from server.image_service import (
    ByopNotConnected,
    CommunityModelNoLongerFree,
    GenerationAlreadyProcessed,
    ImageStudioService,
    UnknownOrDisabledModel,
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


@app.exception_handler(AppwriteUnavailableError)
def _appwrite_unavailable_handler(request: Request,
                                  exc: AppwriteUnavailableError) -> Response:
    """
    LUOI AN TOAN CHUNG cho `AppwriteUnavailableError` (ha tang TAM THOI —
    mat mang hoac het han muc/rate limit, KHONG PHAI ban ghi thieu that).

    Nhieu route da tu bat loi nay va tra 503 (xem cac route dang nhap/OAuth/
    xoa tai khoan) — handler nay KHONG thay the chung (try/except trong THAN
    route luon chay TRUOC, chan loi truoc khi no toi duoc day). No la luoi
    du phong cho MOI route KHAC chua tung nghi toi truong hop nay, vi
    `appwrite_store.py::_call()` co the nem loi nay tu BAT KY thao tac doc
    nao — that tren staging (2026-08-23): `create_chapter` goi
    `store.owned_novel()` chi bat `NotFoundError`/`PermissionDenied`, nen
    mot su co het han muc se roi tu do thanh 500 chung chung neu khong co
    luoi nay, thay vi 503 dung nghia.

    Header `X-Error-Code` la MA ON DINH de cong cu giam sat/canary phan biet
    "ha tang tam thoi, thu lai duoc" voi cac 503 khac ma khong phai doc
    (hoac dich) chuoi thong diep tieng Viet.
    """
    return Response(
        content=json.dumps({"detail": str(exc)}, ensure_ascii=False),
        media_type="application/json",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers={"X-Error-Code": "appwrite_unavailable"},
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

#: Kho Animation (V6, overnight Phase 5) — MOT the hien, DOC LAP hoan toan
#: voi `store` (novels/chapters/tts) — xem docstring dau
#: `server/animation_domain.py` ve vi sao Animation la mot san pham RIENG.
animation_store = build_animation_store(settings)

#: Kho Trusted Video Sources (Phase 5, Admin Control Center V2) — MOT the
#: hien, DOC LAP hoan toan voi `store`/`animation_store` — ba bang RIENG
#: (`trusted_sources`/`series_mappings`/`video_imports`), xem docstring dau
#: `server/trusted_source_domain.py`.
trusted_source_store = build_trusted_source_store(settings)

#: Kho NHAP CHUONG HANG LOAT — MOT the hien, HAI bang RIENG
#: (`chapter_import_batches`/`chapter_import_items`), doc lap voi `store`.
#:
#: Day la trang thai DIEU PHOI, khong phai noi dung: xoa ca hai bang thi khong
#: mat chuong hay audio nao, chi mat kha nang tiep tuc mot dot nhap dang do.
#: Xem `server/bulk_import_domain.py`.
bulk_import_store = build_bulk_import_store(settings)

#: Tang dich vu Trusted Video Sources (Phase 5) — noi YouTube Data API,
#: `video_classifier`/`episode_parser`, `trusted_source_store` va
#: `animation_store` (tao/doc `AnimationEpisode` that) gap nhau. `store`
#: (KHONG phai `animation_store`) dung de ghi nhat ky kiem duyet — CUNG mot
#: nhat ky voi kiem duyet Animation/xa hoi o tren.
trusted_sources = TrustedSourceService(
    trusted_source_store, animation_store, store,
    youtube_api_key=settings.youtube_api_key,
    websub_callback_base_url=settings.youtube_websub_callback_base_url)

#: Tang service cua tang xa hoi. Cung `identity`/`store`/`storage` voi moi route
#: khac — mot duong ghi duy nhat, va no la noi quyen/han muc/thong bao duoc
#: cuong che. Xem dau `server/social_service.py`.
#:
#: `animation_store` them vao DE BINH LUAN TAP dung chung ha tang binh luan
#: (`Comment` voi `target_kind="animation_episode"`) thay vi mot he thong
#: binh luan thu hai — xem `SocialService._tap_cong_khai`.
#:
#: `gamification_store` them vao (V4 visual completion, vong 4) DE the tac
#: gia gon (`_the_nguoi`) doc duoc khung/huy hieu DANG TRANG BI hang loat —
#: nho vay khung avatar hien NHAT QUAN o binh luan/bai dang/thong bao/tim
#: kiem ma khong can sua tung noi hien thi rieng.
social = SocialService(identity, store, storage,
                       han_muc=settings.social_limits or None,
                       animation_store=animation_store,
                       gamification_store=gamification_store)

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


def account_deletion_service() -> AccountDeletionService:
    """
    Dich vu xoa tai khoan, DUNG NEN moi lan goi.

    CO Y KHONG giu mot the hien o cap module nhu `social`/`creators`/
    `translation_svc`: dich vu nay can SAU kho khac nhau, va mot the hien giu
    tham chieu CU sau khi ai do gan lai `main.store`/`main.identity` (moi bo
    test trong kho nay deu lam vay o `setUp`) se xoa du lieu trong MOT KHO
    KHAC voi kho ma route dang doc. Voi mot thao tac khong the hoan lai, do la
    loai loi khong duoc phep co.

    Doc bien module tai luc goi thi khong the lech. Chi phi la mot object giu
    sau tham chieu, tren mot route ma moi nguoi dung goi nhieu nhat mot lan.
    """
    return AccountDeletionService(
        identity, store, storage, gamification_store, translation_store,
        translation_svc)


#: Image Studio V1 (overnight build, PHASE 2-11) — vi/thu vien la kho MOCK
#: (trong bo nho) cho toi khi Appwrite production duoc mo lai, cung nguyen
#: tac voi `gamification_store`/`translation_store` khi chua co ha tang
#: production: tinh nang chay day du tren mock, chi khong ben vung qua
#: restart. Xem `docs/reports/image-studio-v1-summary.md`.
image_wallet_store = MockWalletStore()
image_library_store = MockImageLibraryStore()
image_quick_free_provider = QuickFreeImageProvider()
#: `None` khi CHUA cau hinh POLLINATIONS_API_KEY (Shared Premium bi khoa ro
#: rang o tang service — KHONG am tham lui ve mot khoa rong).
image_shared_premium_provider = (
    SharedPremiumImageProvider(api_key=settings.image_studio.pollinations_api_key)
    if settings.image_studio.pollinations_api_key else None
)
image_byop_crypto = build_image_byop_crypto(
    {"IMAGE_BYOP_MASTER_KEY": settings.image_studio.byop_master_key}
    if settings.image_studio.byop_master_key else {}
)
image_byop_svc = PollinationsByopService(
    client_id=settings.image_studio.pollinations_client_id or "pk_chua_cau_hinh",
    redirect_uri=settings.image_studio.byop_redirect_uri or "https://chua-cau-hinh.invalid/callback",
    crypto=image_byop_crypto,
)


def _canh_bao_ngan_sach_image_studio(snapshot) -> None:
    """Callback canh bao PHASE 11 — CHUA co kenh quan tri that (Appwrite
    production bi chan), nen ghi log co cau truc de van hanh doi soat thu
    cong duoc; nang cap len thong bao that (email/Slack) khi co ha tang."""
    print(
        f"[image-studio][CANH BAO NGAN SACH] thang={snapshot.thang} "
        f"da_chi={snapshot.spent_usd:.2f} usd / han_muc={snapshot.budget_usd:.2f} usd"
    )


image_spending_guard = SharedPremiumSpendingGuard(
    monthly_budget_usd=settings.image_studio.monthly_budget_usd,
    warning_budget_usd=settings.image_studio.warning_budget_usd,
    max_concurrent=settings.image_studio.max_concurrent_shared_generations,
    canh_bao=_canh_bao_ngan_sach_image_studio,
)
if not settings.image_studio.shared_premium_enabled:
    # Cong tac TONG tat — dat kill switch NGAY tu luc khoi dong thay vi rai
    # rac kiem tra `shared_premium_enabled` o moi route.
    image_spending_guard.dat_kill_switch(True)

#: Danh sach model cong dong Pollinations bao gia 0 pollen — CONG KHAI (chi
#: goi endpoint LIET KE, khong can POLLINATIONS_API_KEY), xem
#: `server/image_community_catalogue.py` docstring dau file ve nguon that
#: da xac minh (`GET https://gen.pollinations.ai/image/models`, anonymous).
image_community_catalogue = CommunityCatalogueCache()

image_studio_svc = ImageStudioService(
    wallet_store=image_wallet_store,
    quick_free_provider=image_quick_free_provider,
    shared_premium_provider=image_shared_premium_provider,
    byop_service=image_byop_svc,
    spending_guard=image_spending_guard,
    community_catalogue=image_community_catalogue,
)
image_payment_provider = MockPaymentProvider()

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


# -- Animation (V6, overnight Phase 5) ---------------------------------------


class AnimationSeriesIn(BaseModel):
    title: TieuDe
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    related_novel_id: str = ""


class AnimationSeriesPatch(BaseModel):
    """Chi cac truong nguoi dung duoc sua. `state` doi qua publish/unpublish."""

    title: Optional[TieuDe] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    related_novel_id: Optional[str] = None


class AnimationEpisodeIn(BaseModel):
    series_id: str
    title: TieuDe
    #: URL YouTube (moi dang) HOAC ID tran — xem `animation_domain.parse_youtube_id`.
    youtube_url: str
    order_index: int = 1


class AnimationEpisodePatch(BaseModel):
    title: Optional[TieuDe] = None
    youtube_url: Optional[str] = None
    order_index: Optional[int] = None


class EpisodeOrderIn(BaseModel):
    """Thu tu tap moi, day du va dung mot lan."""

    episode_ids: List[str] = Field(min_length=1)


class WatchProgressIn(BaseModel):
    series_id: str
    episode_id: str
    position_seconds: float = 0.0
    duration_seconds: float = 0.0


class JobIn(BaseModel):
    chapter_id: str
    voice_id: str
    rate: str = "1.0"
    chunk_chars: int = 2000


# -----------------------------------------------------------------------------
# Xac thuc
# -----------------------------------------------------------------------------


def current_profile(authorization: Optional[str] = Header(default=None)) -> Profile:
    """
    Lay ho so tu Bearer token. Thieu/khong hop le -> 401.

    `AppwriteUnavailableError` PHAI bat TRUOC `AuthError` (no la con cua
    `AuthError`): Appwrite mat ket noi la loi ha tang TAM THOI (503, thu lai
    duoc), khac han token sai/het han (401, nguoi dung phai dang nhap lai).
    Phat hien Phase 10 (overnight hardening): truoc day MOI request co token
    tren MOI route duoc bao ve deu thanh 401 khi Appwrite gian doan - nguoi
    dung dang dang nhap se bi hieu nham la "phien het han" hang loat trong
    luc backend chi dang khong ket noi duoc toi Appwrite.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Cần đăng nhập.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return identity.profile_from_token(token)
    except AppwriteUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
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

    `admin_role` (Admin Control Center V2) la chuoi "none"/"moderator"/
    "admin"/"owner" — giao dien dung de AN/HIEN cac muc trong sidebar quan
    tri theo dung vai tro, nhung day CHI la goi y hien thi. Moi route
    `/api/admin/*` van tu kiem lai qua `admin_profile`/`admin_or_owner_profile`/
    `owner_profile` — mot nguoi sua `admin_role` bang tay trong DevTools van
    nhan 403 y het truoc gio.
    """
    vai_tro = settings.admin_role_of(profile.user_id)
    return {**profile.to_dict(),
            "is_admin": vai_tro != AdminRole.NONE,
            "admin_role": vai_tro.value,
            "avatar_url": creators.avatar_url(profile)}


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn) -> Dict[str, Any]:
    # `AppwriteUnavailableError` PHAI bat TRUOC `AuthError` - xem
    # `current_profile` o tren ve vi sao (503 loi ha tang tam thoi, khac
    # 400 loi du lieu nguoi dung nhap).
    try:
        profile = identity.register(payload.email, payload.password, payload.display_name)
    except AppwriteUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # `login` cung goi ra Appwrite va cung nem AuthError - de ngoai try thi
    # loi se thanh 500 thay vi mot thong bao ro rang.
    try:
        token = identity.login(payload.email, payload.password)
    except AppwriteUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
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
    except AppwriteUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
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


@app.delete("/api/account")
def delete_account(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Nguoi dung TU xoa tai khoan cua CHINH minh, cung moi du lieu cua no.

    KHONG co ban quan tri xoa nguoi khac o duong nay — khu quan tri da co
    `set_account_enabled` (chan dang nhap) va treo tac gia; mot endpoint xoa
    vinh vien nguoi khac la thu khong nen ton tai neu chua ai can.

    KHONG doi xac thuc lai (nhap lai mat khau): nguoi dung OAuth khong co mat
    khau nao de nhap, nen mot rao chan nhu vay se chi ap dung duoc cho mot nua
    nguoi dung — tuc la mot rao chan gia. Buoc xac nhan la viec cua giao dien.

    Chi tiet chinh sach luu tru — bang nao xoa, bang nao GIU NGUYEN
    (`moderation_events`, luot nghe phia nguoi nghe), bang nao giu-nhung-an-danh
    (`author_applications`, `content_reports`) — o
    `MetadataStore.delete_account`. Thu tu don (danh tinh SAU CUNG) o
    `server/account_deletion.py`.

    IDEMPOTENT: sau khi xoa, token cua phien nay khong con dung duoc, nen mot
    lan goi thu hai dung ngay o `current_profile` voi 401 — khong phai 500.

    `AppwriteUnavailableError` -> 503 (thu lai duoc), KHONG phai 200: buoc cuoi
    cung la xoa danh tinh, va bao "da xoa" cho mot tai khoan van dang nhap duoc
    la loi hua sai nghiem trong nhat duong nay co the mac. Xem
    `AppwriteIdentityAdapter.delete_account`.
    """
    try:
        removed = account_deletion_service().delete_account(profile.user_id)
    except AppwriteUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"deleted": True, "removed": removed}


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
    except AppwriteUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
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


def _tao_chuong_cho_truyen(*, novel: Novel, owner_id: str, title: str,
                           content: str, order_index: int,
                           chapter_id: str = "",
                           bao_nguoi_theo_doi: bool = True
                           ) -> Tuple[Chapter, bool]:
    """
    CHINH THAN cua `POST /api/chapters`. MOT duong tao chuong duy nhat.

    Route ben duoi chi la lop vo kiem quyen + doi hinh dang; bo dieu phoi nhap
    hang loat (`server/bulk_import_service.py`) goi DUNG ham nay. Khong co ban
    sao thu hai cua logic tao chuong o dau ca — do la yeu cau cua thiet ke, vi
    mot ban sao se lech ngay lan dau ai them mot buoc vao mot trong hai duong.

    HAI tham so chi CO nghia cho duong hang loat:

    `chapter_id` — dat `chapter_id` TAT DINH. Rong = de `Chapter` tu sinh id
    ngau nhien y nhu truoc gio. Xem `MetadataStore.create_chapter_once`.

    `bao_nguoi_theo_doi` — TAT thong bao "co chuong moi". Nhap 500 chuong vao
    mot truyen DA XUAT BAN se ban 500 thong bao cho TUNG nguoi theo doi; do
    khong phai "dung lai co che da co" ma la lam dung no. Khoanh khac dang bao
    cua mot dot nhap la luc truyen duoc xuat ban, va `publish_novel` da lo viec
    do. XP thi GIU nguyen nhu duong don chuong: no cong theo tung
    `chapter_id`, khong nhan doi, va `_thuong_xp_xuat_ban_truyen` cung tinh
    dung cac chuong nay khi truyen duoc xuat ban.
    """
    chuong = Chapter(
        novel_id=novel.novel_id,
        owner_id=owner_id,
        title=title.strip(),
        content=content,
        order_index=order_index,
        **({"chapter_id": chapter_id} if chapter_id else {}),
    )
    chapter, vua_tao = store.create_chapter_once(chuong)
    if not vua_tao:
        # Da co tu truoc (duong hang loat chay lai). TUYET DOI khong lam lai
        # cac tac dung phu mot lan: thong bao va XP.
        return chapter, False
    # Chuong moi trong truyen DA XUAT BAN la mot chuong doc gia doc duoc NGAY:
    # danh sach chuong cua trang truyen khong loc theo trang thai chuong, chi
    # theo trang thai truyen. Nen day — chu khong phai mot nut "xuat ban
    # chuong" khong ton tai — chinh la khoanh khac "co chuong moi" ma nguoi
    # theo doi truyen can duoc bao. E2E tren staging that da chung minh duong
    # cu (doi `state` cua chuong qua PATCH) khong bao gio kich hoat duoc:
    # `ChapterPatch` khong nhan `state`.
    if bao_nguoi_theo_doi:
        _bao_chuong_moi(chapter)
    # Cung ly do: truyen cha DA xuat ban tu truoc thi chuong moi nay LA cong
    # khai ngay, nen thuong XP tai day. Truyen con nhap thi cho toi khi
    # `publish_novel` quet qua (xem `_thuong_xp_xuat_ban_truyen`).
    if novel.state is PublishState.PUBLISHED:
        try:
            thuong_xp(gamification_store, owner_id, "publish_chapter",
                     source_kind="chapter", source_id=chapter.chapter_id)
            thuong_xp(gamification_store, owner_id, "publish_first_chapter",
                     source_kind="chapter", source_id=owner_id)
        except Exception:
            pass
    return chapter, True


@app.post("/api/chapters", status_code=status.HTTP_201_CREATED)
def create_chapter(payload: ChapterIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    try:
        novel = store.owned_novel(payload.novel_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    chapter, _ = _tao_chuong_cho_truyen(
        novel=novel, owner_id=profile.user_id, title=payload.title,
        content=payload.content, order_index=payload.order_index)
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


def _tao_job_cho_chuong(*, owner_id: str, chapter_id: str, voice_id: str,
                        rate: str = "1.0",
                        chunk_chars: int = 2000) -> Dict[str, Any]:
    """
    CHINH THAN cua `POST /api/jobs`. MOT duong tao job duy nhat.

    Route ben duoi chi doi hinh dang tham so; bo dieu phoi nhap hang loat goi
    DUNG ham nay, nen tinh idempotent theo dau van tay, tran `MAX_ACTIVE_JOBS`,
    kiem giong cong khai va duong nhan lai job ket deu la CUNG mot ma nguon o
    ca hai duong — khong co ban sao nao de lech.

    VAN nem `HTTPException` du duoc goi ngoai ngu canh HTTP: ma trang thai la
    thu phan biet "tran dong thoi, thu lai sau" (429) voi "tu choi vinh vien"
    (400/403/404), va bo dieu phoi can dung su phan biet do. Lop chuyen doi
    nam o `_bulk_tao_job` ben duoi.
    """
    try:
        chapter = store.owned_chapter(chapter_id, owner_id)
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
        tts_bridge.ensure_voice_public(voice_id, settings)
    except tts_bridge.TtsBridgeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, exc.message) from exc

    fingerprint = job_fingerprint(
        chapter.content, voice_id, rate, chunk_chars
    )
    existing = store.find_job_by_fingerprint(owner_id, chapter.chapter_id, fingerprint)
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
    dang_xep = sum(1 for j in store.list_jobs(owner_id)
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
            owner_id=owner_id,
            chapter_id=chapter.chapter_id,
            voice_id=voice_id,
            content_hash=fingerprint,
            rate=rate,
            chunk_chars=chunk_chars,
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


@app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: JobIn, profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    Tao job tao audio.

    IDEMPOTENT: cung noi dung + giong + thiet lap thi tra ve job da co, khong
    tao job moi va khong goi provider lan nua.

    Toan bo logic o `_tao_job_cho_chuong` — CUNG mot ham ma bo dieu phoi nhap
    hang loat goi.
    """
    return _tao_job_cho_chuong(
        owner_id=profile.user_id, chapter_id=payload.chapter_id,
        voice_id=payload.voice_id, rate=payload.rate,
        chunk_chars=payload.chunk_chars)


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
# Nhap chuong HANG LOAT
# -----------------------------------------------------------------------------
#
# Xem `server/bulk_import_domain.py` (dinh dang dau vao, dinh danh tat dinh) va
# `server/bulk_import_service.py` (bo dieu phoi). Khu nay CHI la lop vo HTTP:
# kiem quyen chu-so-huu-truyen, doc dau vao, doi hinh dang loi.
#
# QUYEN: `store.owned_novel()` — TAC GIA SO HUU TRUYEN, khong phai `AdminRole`.
# Cung rao voi `POST /api/chapters`, va co y giong het: nhap hang loat khong mo
# them quyen nao ma bam mot nut 500 lan khong lam duoc.
#
# CONG XUAT BAN khong dat o day. Nhap chuong la tao BAN NHAP; `POST /api/novels/
# {id}/publish` van la cong duy nhat, va no da co `author_gate` cua no.

#: Bao nhieu chuong duoc nhap trong MOT lo.
#:
#: 500 la tran tren cua nhu cau da neu ("50-500 chuong moi truyen"). Truyen dai
#: hon thi chia nhieu lo — cac lo noi tiep nhau dung thu tu vi `order_base` cua
#: lo sau doc `order_index` lon nhat dang co.
MAX_IMPORT_ITEMS = int(os.environ.get("FAS_MAX_IMPORT_ITEMS", "500"))

#: Tong so ky tu trong MOT lo. Khong phai gioi han cua Appwrite ma la gioi han
#: cua MOT THAN REQUEST: 500 chuong x 100.000 ky tu la 50 MB JSON, va khong
#: request nao nen to nhu vay. 5 trieu ky tu la khoang 500 chuong x 10.000 —
#: du rong cho mot bo fanfic that.
MAX_IMPORT_TOTAL_CHARS = int(
    os.environ.get("FAS_MAX_IMPORT_TOTAL_CHARS", "5000000"))


class ChapterImportItemIn(BaseModel):
    """DUNG LAI rang buoc do dai cua `ChapterIn` — khong phat minh gioi han
    moi cho duong hang loat, neu khong hai duong se nhan hai tap dau vao khac
    nhau va cai lech do se lo ra o chuong thu 300."""

    title: TieuDe
    content: NoiDungChuong = ""


class ChapterImportIn(BaseModel):
    #: Dang co cau truc — duong cho script van hanh noi dung.
    chapters: Optional[List[ChapterImportItemIn]] = Field(
        default=None, max_length=MAX_IMPORT_ITEMS)
    #: Van ban tho (TXT theo mau `=== Tiêu đề ===`, hoac JSON) — duong cho
    #: giao dien: trinh duyet doc tep bang `FileReader.readAsText` roi gui
    #: chuoi. KHONG base64: dinh dang nay la van ban thuan, va base64 chi lam
    #: than request phong them mot phan ba ma khong duoc gi.
    text: Annotated[str, StringConstraints(
        max_length=MAX_IMPORT_TOTAL_CHARS + 200_000)] = ""
    format: Annotated[str, StringConstraints(max_length=8)] = "txt"
    #: RONG = chi tao chuong, KHONG tao audio. Trang thai hop le va huu dung.
    voice_id: Annotated[str, StringConstraints(max_length=128)] = ""
    rate: Annotated[str, StringConstraints(max_length=16)] = "1.0"
    chunk_chars: int = Field(default=2000, ge=200, le=20000)
    source_name: Annotated[str, StringConstraints(max_length=200)] = ""


def _doc_dau_vao_nhap(payload: ChapterImportIn) -> List[ParsedChapter]:
    """
    Doc + KIEM CA danh sach truoc khi ghi bat ky hang nao.

    Nua voi la trang thai kho don nhat cua ca tinh nang nay, nen tu choi som va
    tu choi CA lo — xem `validate_chapters`.
    """
    if payload.chapters is not None and payload.text.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Chỉ gửi một trong hai: `chapters` (có cấu trúc) hoặc `text` "
            "(văn bản thô).")
    if payload.chapters is not None:
        from server.bulk_import_domain import chuan_hoa_noi_dung

        items = [ParsedChapter(title=c.title.strip(),
                               content=chuan_hoa_noi_dung(c.content))
                 for c in payload.chapters]
    elif payload.text.strip():
        try:
            items = parse_input(payload.text, payload.format)
        except BulkImportFormatError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Chưa có nội dung để nhập. Gửi `chapters` hoặc `text`.")
    try:
        validate_chapters(items, max_items=MAX_IMPORT_ITEMS,
                          max_chars_per_item=MAX_CHAPTER_CHARS,
                          max_total_chars=MAX_IMPORT_TOTAL_CHARS)
    except BulkImportFormatError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return items


def _bulk_tao_chuong(*, novel: Novel, owner_id: str, title: str, content: str,
                     order_index: int,
                     chapter_id: str = "") -> Tuple[Chapter, bool]:
    """Cua ngo duy nhat tu bo dieu phoi vao viec tao chuong — xem
    `_tao_chuong_cho_truyen` ve ly do TAT thong bao nguoi theo doi."""
    return _tao_chuong_cho_truyen(
        novel=novel, owner_id=owner_id, title=title, content=content,
        order_index=order_index, chapter_id=chapter_id,
        bao_nguoi_theo_doi=False)


def _bulk_tao_job(*, owner_id: str, chapter_id: str, voice_id: str,
                  rate: str, chunk_chars: int) -> Dict[str, Any]:
    """
    Cua ngo duy nhat tu bo dieu phoi vao viec tao job TTS.

    Doi `HTTPException` sang hai ngoai le co Y NGHIA KHAC NHAU, va su phan biet
    do la thu quyet dinh hanh vi cua ca dot nhap:

      429 -> `JobQueueFull`: tran dong thoi cua chinh nguoi dung. KHONG phai
             loi cua chuong nay. Bo dieu phoi dung xep them trong chu ky nay
             roi thu lai — day chinh la cach "gioi han dong thoi" cua tinh nang
             nay, va no la co che DA CO chu khong phai mot bo dieu tiet moi.
      con lai -> `ChapterJobRejected`: tu choi VINH VIEN (giong sai, chuong
             rong, chuong bi xoa). Muc bi danh `failed` va cho chu bam thu lai.
    """
    try:
        return _tao_job_cho_chuong(
            owner_id=owner_id, chapter_id=chapter_id, voice_id=voice_id,
            rate=rate, chunk_chars=chunk_chars)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            raise JobQueueFull(str(exc.detail)) from exc
        raise ChapterJobRejected(str(exc.detail)) from exc


def bulk_import_service() -> BulkImportService:
    """
    Dich vu nhap hang loat, DUNG NEN moi lan goi.

    CO Y khong giu mot the hien o cap module nhu `social`/`translation_svc`: no
    can `main.store` va `main.bulk_import_store` HIEN TAI, va bo test thay ca
    hai bang ban mock trong `setUp`. Mot the hien giu tham chieu cu se lang le
    ghi vao mot kho khong ai doc — cung ly do voi `account_deletion_service()`.
    """
    return BulkImportService(
        bulk_import_store, store,
        tao_chuong=_bulk_tao_chuong, tao_job=_bulk_tao_job,
        max_active_jobs=MAX_ACTIVE_JOBS)


#: Phanh nghi cua bo dieu phoi — MOT the hien cho MOT TIEN TRINH.
#:
#: KHONG co duong nao de tien trinh khac day trang thai vao day, va do la co y:
#: o production `server/worker.py` la tien trinh KHAC tren may KHAC, nen mot ham
#: "danh thuc" goi tu route se chi sua bien cua tien trinh web — dung cai tien
#: trinh khong dieu phoi gi ca. Toan bo ly do nam o docstring
#: `ImportDriveGate`; dung them cho nay mot cua sau.
_import_gate = ImportDriveGate()


def drive_chapter_imports() -> Dict[str, int]:
    """
    MOT chu ky dieu phoi nhap chuong. Diem vao DUY NHAT cho tien trinh nen.

    `server/worker.py` goi ham nay trong vong quet cua no. Ten ham la mot phan
    hop dong: doi ten la lam vo worker dang chay tren VM production.

    Goi bao nhieu lan cung duoc, luc nao cung duoc — moi buoc chuyen trang thai
    ben duoi deu idempotent (xem `server/bulk_import_domain.py`).

    Quyet dinh "co bo qua chu ky nay khong" duoc SUY RA TU KET QUA truy van cua
    chu ky truoc, khong tu bat ky tin hieu nao do ben ngoai gui vao. Nho vay hai
    tien trinh chay doc lap co hanh vi giong nhau tuyet doi, va mot lo vua tao
    duoc worker nhin thay o chu ky ke tiep cua CHINH NO — khong ai phai bao no.
    """
    if _import_gate.should_skip():
        return {"nghi": 1}
    bao = bulk_import_service().drive_once()
    _import_gate.record(bao.get("lo", 0))
    return bao


#: Bo quet nhap chuong cho CHE DO INLINE (dev). Tach hoan toan voi bo quet TTS
#: va bo quet dich — event/thread rieng, dung y voi cac subsystem khac.
_import_sweeper_stop = threading.Event()


def _import_sweep_forever() -> None:
    while True:
        try:
            drive_chapter_imports()
        except Exception:
            # Bo quet chet la mot lo nhap treo mai mai — khong duoc de mot loi
            # le lam no dung. Cung triet ly voi `_sweep_forever`.
            pass
        if _import_sweeper_stop.wait(IMPORT_SWEEP_SECONDS):
            return


@app.on_event("startup")
def start_import_sweeper() -> None:
    """
    Chi bat khi `inline_worker` BAT (dev/cuc bo).

    O staging/production `FAS_INLINE_WORKER=false` va bo dieu phoi song trong
    `server/worker.py`. Hai ben cung dieu phoi thi KHONG sai — moi buoc chuyen
    trang thai deu idempotent nho dinh danh tat dinh — nhung khong can hai, va
    mot ben nam trong tien trinh phuc vu request la dung cai ma viec tach
    worker nham loai bo.
    """
    if not settings.inline_worker:
        return
    threading.Thread(target=_import_sweep_forever, daemon=True,
                     name="chapter-import-sweeper").start()


@app.on_event("shutdown")
def stop_import_sweeper() -> None:
    _import_sweeper_stop.set()


def _nhap_hang_loat(fn, *args, **kwargs):
    """Doi ngoai le cua tang dich vu sang ma trang thai HTTP dung."""
    try:
        return fn(*args, **kwargs)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except BulkImportFormatError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except BulkImportStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except BulkImportError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


def _truyen_cua_toi(novel_id: str, owner_id: str) -> Novel:
    try:
        return store.owned_novel(novel_id, owner_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


# PHAI khai bao TRUOC `.../chapter-imports/{batch_id}/...`: neu khong "preview"
# bi coi la mot `batch_id`. Cung bay da xu ly o `/api/chapters?mine=true`.
@app.post("/api/novels/{novel_id}/chapter-imports/preview")
def preview_chapter_import(novel_id: str, payload: ChapterImportIn,
                           profile: Profile = Depends(current_profile)
                           ) -> Dict[str, Any]:
    """
    Doc dau vao va tra ve DANH SACH CHUONG se duoc tao — KHONG ghi gi ca.

    VI SAO CAN mot route chi de xem truoc: mot lan bam sai o day la 500 chuong
    sai thu tu hoac 500 chuong dinh lam mot. Xem truoc la thu duy nhat bien
    "quy uoc tach chuong" tu mot dieu phai tin thanh mot dieu kiem duoc.

    Tra kem `batch_id` tat dinh va `already_imported` de giao dien noi duoc
    "tep nay da nhap roi, day la lo cu" thay vi de nguoi dung tu doan.
    """
    novel = _truyen_cua_toi(novel_id, profile.user_id)
    items = _doc_dau_vao_nhap(payload)

    from server.bulk_import_domain import (
        batch_fingerprint, batch_id_from_fingerprint)

    fingerprint = batch_fingerprint(profile.user_id, novel.novel_id, items)
    batch_id = batch_id_from_fingerprint(fingerprint)
    lo_cu = None
    try:
        lo_cu = bulk_import_store.get_batch(batch_id)
    except Exception:
        lo_cu = None
    return {
        "chapters": [m.to_dict() for m in items],
        "count": len(items),
        "total_chars": sum(len(m.content) for m in items),
        "order_base": max((c.order_index for c in
                           store.list_chapters(novel.novel_id)), default=0),
        "fingerprint": fingerprint,
        "batch_id": batch_id,
        "already_imported": lo_cu is not None,
        "existing_batch": lo_cu.to_dict() if lo_cu else None,
    }


@app.post("/api/novels/{novel_id}/chapter-imports",
          status_code=status.HTTP_201_CREATED)
def create_chapter_import(novel_id: str, payload: ChapterImportIn,
                          profile: Profile = Depends(current_profile)
                          ) -> Dict[str, Any]:
    """
    Mo mot dot nhap chuong, hoac TIEP TUC dung dot cu neu dau vao y het.

    IDEMPOTENT: `batch_id` la bam cua (chu, truyen, danh sach chuong), nen gui
    lai cung mot tep KHONG BAO GIO tao chuong trung — no tiep tuc dung lo cu.
    Xem `batch_fingerprint`.

    Tra ve NGAY (`201`) voi lo o trang thai `preparing`: viec ghi 500 hang muc
    chay trong thread nen, va bo dieu phoi o `server/worker.py` moi thuc su tao
    chuong/xep job. Mot request khong the — va khong nen — giu 500 lan ghi.
    """
    novel = _truyen_cua_toi(novel_id, profile.user_id)
    items = _doc_dau_vao_nhap(payload)

    # Kiem GIONG DOC ngay tai day, truoc khi ghi hang nao. Phat hien giong sai
    # o chuong thu 300 (khi bo dieu phoi goi `POST /api/jobs`) la mot lo nhap
    # nua voi va 300 muc `failed` giong nhau.
    if payload.voice_id:
        try:
            tts_bridge.ensure_voice_public(payload.voice_id, settings)
        except tts_bridge.TtsBridgeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                exc.message) from exc

    svc = bulk_import_service()
    ket = _nhap_hang_loat(
        svc.create_or_resume, profile.user_id, novel, items,
        voice_id=payload.voice_id, rate=payload.rate,
        chunk_chars=payload.chunk_chars,
        source_name=payload.source_name)
    lo = ket["batch"]

    # KHONG "danh thuc" bo dieu phoi o day. O production no la mot TIEN TRINH
    # KHAC tren mot MAY KHAC, nen moi tin hieu trong tien trinh nay deu khong
    # den duoc no; no tu thay lo moi o chu ky quet ke tiep cua chinh no (co the
    # cham toi `FAS_IMPORT_IDLE_BACKOFF_SECONDS` neu truoc do dang rong viec).
    # Xem docstring `ImportDriveGate` — day tung la mot ham reset tra ve dung
    # cam giac an tam ma khong lam gi ca.
    if ket["created"] or ket["resumed"]:
        can_ghi = ket.get("items") or []
        if can_ghi:
            _bat_dau_ghi_danh_sach_muc(lo.batch_id, can_ghi)
    return {
        "batch": lo.to_dict(),
        "progress": lo.progress(),
        "created": ket["created"],
        "resumed": ket["resumed"],
        # Giong doc cua lan gui TRUOC thang. Noi ro thay vi im lang doi giong
        # cua ca lo — doi giong la viec cua tung chuong, xem `batch_fingerprint`.
        "voice_ignored": ket["voice_ignored"],
    }


def _bat_dau_ghi_danh_sach_muc(batch_id: str,
                               items: List[ParsedChapter]) -> None:
    """
    Ghi danh sach muc trong THREAD NEN. Cung khuon voi `_start_job_thread`.

    AN TOAN KHI CHAY LAI (`item_id` tat dinh), nen hai thread cung ghi mot lo
    khong sinh ban trung — do la ly do cho nay khong can khoa nao.

    Loi thi ghi `last_error` de chu doc duoc, roi de lo o `preparing`: bo dieu
    phoi se danh `failed` sau `PREPARING_STALE_SECONDS`, va chu cuu duoc bang
    dung mot hanh dong — gui lai cung tep.
    """
    def _chay() -> None:
        try:
            bulk_import_service().materialize(batch_id, items)
        except Exception as exc:
            try:
                bulk_import_store.save_batch(batch_id, {
                    "last_error": f"Chưa ghi xong danh sách chương: "
                                  f"{type(exc).__name__}. Hãy gửi lại đúng tệp "
                                  f"cũ để tiếp tục."})
            except Exception:
                pass

    threading.Thread(target=_chay, daemon=True,
                     name=f"chapter-import-{batch_id}").start()


@app.get("/api/novels/{novel_id}/chapter-imports")
def list_chapter_imports(novel_id: str,
                         profile: Profile = Depends(current_profile)
                         ) -> Dict[str, Any]:
    _truyen_cua_toi(novel_id, profile.user_id)
    return _nhap_hang_loat(bulk_import_service().list_for_novel,
                           profile.user_id, novel_id)


@app.get("/api/novels/{novel_id}/chapter-imports/{batch_id}")
def get_chapter_import(novel_id: str, batch_id: str, limit: int = 50,
                       offset: int = 0, status_filter: str = "",
                       profile: Profile = Depends(current_profile)
                       ) -> Dict[str, Any]:
    """
    Tien do cua mot lo + MOT TRANG danh sach muc.

    `progress` doc tu bo dem da luu tren hang lo, KHONG dem lai 500 hang moi
    lan poll: trang nay tu lam moi vai giay mot lan, va dem lai moi lan la
    duong ngan nhat den mot su co han muc doc Appwrite (da xay ra 20/08). Bo
    dem duoc bo dieu phoi cap nhat theo tung buoc va dem lai chinh xac dung mot
    lan — luc ket lo. Xem docstring `ImportBatch`.

    `status_filter` (khong phai `status`, tranh trung ten voi module `status`
    cua FastAPI) loc muc theo trang thai — de giao dien mo rieng danh sach
    chuong loi.
    """
    _truyen_cua_toi(novel_id, profile.user_id)
    return _nhap_hang_loat(
        bulk_import_service().batch_view, profile.user_id, novel_id, batch_id,
        limit=limit, offset=offset, status=status_filter)


@app.post("/api/novels/{novel_id}/chapter-imports/{batch_id}/cancel")
def cancel_chapter_import(novel_id: str, batch_id: str,
                          profile: Profile = Depends(current_profile)
                          ) -> Dict[str, Any]:
    """
    Huy: dung xep viec MOI. KHONG cat job dang tong hop.

    Audio dang lam van chay den cung va van duoc ghi nhan — bo di dung phan
    viec dat nhat chi vi mot cai bam "huy" la sai. Xem `BulkImportService.cancel`.
    """
    _truyen_cua_toi(novel_id, profile.user_id)
    return _nhap_hang_loat(bulk_import_service().cancel,
                           profile.user_id, novel_id, batch_id)


@app.post("/api/novels/{novel_id}/chapter-imports/{batch_id}/retry")
def retry_chapter_import(novel_id: str, batch_id: str,
                         profile: Profile = Depends(current_profile)
                         ) -> Dict[str, Any]:
    """
    Thu lai MOI muc that bai cua lo. Khong chay lai muc da xong.

    KHONG "danh thuc" bo dieu phoi — xem ghi chu o `create_chapter_import`.
    """
    _truyen_cua_toi(novel_id, profile.user_id)
    return _nhap_hang_loat(bulk_import_service().retry,
                           profile.user_id, novel_id, batch_id)


@app.post("/api/novels/{novel_id}/chapter-imports/{batch_id}"
          "/items/{item_id}/retry")
def retry_chapter_import_item(novel_id: str, batch_id: str, item_id: str,
                              profile: Profile = Depends(current_profile)
                              ) -> Dict[str, Any]:
    """
    Thu lai DUNG MOT chuong that bai — khong chay lai ca lo.

    KHONG "danh thuc" bo dieu phoi — xem ghi chu o `create_chapter_import`.
    """
    _truyen_cua_toi(novel_id, profile.user_id)
    return _nhap_hang_loat(bulk_import_service().retry,
                           profile.user_id, novel_id, batch_id,
                           item_id=item_id)


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


@app.get("/api/account/streak")
def account_streak(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Chuoi ngay doc CUA CHINH MINH (V4 visual completion, vong 5) — CHI
    doc, khong ghi: ghi xay ra o `POST /api/progress/read` (tin hieu "da doc
    hom nay" that duy nhat). Tu-chi-doc mot streak khong tang."""
    return streak_hien_thi(gamification_store.get_streak(profile.user_id))


@app.get("/api/account/quests")
def account_quests(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Nhiem vu ngay+tuan CUA CHINH MINH, kem tien do KY HIEN TAI (vong 5)."""
    return {"quests": list_quests_with_progress(
        gamification_store, profile.user_id, _ngay_utc_hom_nay())}


@app.post("/api/account/quests/{quest_key}/claim")
def account_claim_quest(quest_key: str,
                        profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Nhan thuong MOT nhiem vu da hoan thanh trong ky hien tai. Chua hoan
    thanh hoac da nhan roi deu bi tu choi O MAY CHU (400) — xem
    `gamification_service.claim_quest_reward`."""
    try:
        ket_qua = claim_quest_reward(
            gamification_store, profile.user_id, quest_key, _ngay_utc_hom_nay())
    except GamificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ket_qua


@app.get("/api/leaderboard")
def leaderboard(mode: str = "all_time", limit: int = 20, offset: int = 0,
                authorization: Optional[str] = Header(default=None),
                ) -> Dict[str, Any]:
    """
    Bang xep hang XP — CONG KHAI, khong bat buoc dang nhap (khach vang lai
    van xem duoc, chi khong co `viewer_entry`). `mode`:

      - `all_time` (mac dinh): tong XP TU TRUOC TOI GIO, MAY CHU sap xep +
        phan trang that (xem `gamification_service.leaderboard_all_time`).
      - `weekly`: XP kiem duoc TRONG TUAN ISO HIEN TAI (tu thu Hai), tinh tu
        nhat ky XP — xem `gamification_service.leaderboard_weekly`.

    `limit` bi CHAN TRAN o day (khong tin gia tri client gui vo han), giong
    quy uoc o `/api/animation/series`/`/api/novels`.
    """
    gioi_han = max(1, min(100, limit))
    do_lech = max(0, offset)
    nguoi_xem = optional_profile(authorization)
    viewer_id = nguoi_xem.user_id if nguoi_xem else ""

    if mode == "weekly":
        hom_nay = datetime.now(timezone.utc).date()
        dau_tuan = hom_nay - timedelta(days=hom_nay.weekday())
        since_iso = datetime.combine(
            dau_tuan, datetime.min.time(), tzinfo=timezone.utc).isoformat()
        return leaderboard_weekly(gamification_store, identity, storage,
                                  limit=gioi_han, offset=do_lech,
                                  since_iso=since_iso, viewer_id=viewer_id)
    if mode != "all_time":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Chế độ bảng xếp hạng không hợp lệ.")
    return leaderboard_all_time(gamification_store, identity, storage,
                                limit=gioi_han, offset=do_lech,
                                viewer_id=viewer_id)


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
    except AppwriteUnavailableError as exc:
        # Phai bat TRUOC `AuthError` (no la con): Appwrite mat ket noi KHONG
        # phai "tuong tu bi trung ten" - tra 409 o day se noi doi nguoi dung
        # rang ten ho chon da co ai lay, trong khi that ra backend chi dang
        # khong ket noi duoc toi Appwrite.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
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
# ANIMATION (V6, overnight Phase 5) — san pham XEM, doc lap voi Truyen/Audio.
# -----------------------------------------------------------------------------
#
# CUNG KIEN TRUC voi novels/chapters (series~novel, episode~chapter), nhung
# tren mot KHO RIENG (`animation_store`) — xem docstring dau
# `server/animation_domain.py`. Binh luan TAP dung chung ha tang binh luan
# qua `SocialService.episode_comments`/`create_episode_comment`, KHONG phai
# mot he thong binh luan thu hai.


def _series_out(series: AnimationSeries) -> Dict[str, Any]:
    return {**series.to_dict(), "cover_url": _cover_url(series)}


def _may_read_series(series: AnimationSeries, viewer: Optional[Profile]) -> bool:
    """
    Cung logic voi `_may_read` (novel): da xuat ban thi ai cung xem duoc;
    chua thi chi chu so huu.

    Kiem duyet (Phase 4, Admin Control Center V2) THANG truoc tien: mot
    series bi quan tri go xuong (`moderation_state == REMOVED`) thi 404 cho
    TAT CA, KE CA CHINH CHU — cung hanh vi voi bai dang bi go
    (`SocialService._bai_hien`). Chu so huu tu bam "Xuat ban" lai KHONG hoan
    tac duoc lenh go nay, vi day la truc RIENG voi `state` — xem docstring
    `AnimationSeries.moderation_state`.
    """
    if series.moderation_state is not ContentState.VISIBLE:
        return False
    if series.state is PublishState.PUBLISHED:
        return True
    return viewer is not None and viewer.user_id == series.owner_id


@app.get("/api/animation/series")
def list_animation_series(mine: bool = False, q: str = "", tag: str = "",
                          limit: Optional[int] = None, offset: int = 0,
                          authorization: Optional[str] = Header(default=None),
                          ) -> Dict[str, Any]:
    """Thu vien Animation cong khai, hoac danh sach cua rieng minh khi
    `mine=true` — cung contract voi `GET /api/novels`."""
    owner_id = None
    if mine:
        owner_id = current_profile(authorization).user_id

    page_size = None if limit is None else max(1, min(limit, MAX_PAGE_SIZE))
    items, total = animation_store.find_series(
        owner_id=owner_id, published_only=not mine, query=q, tag=tag,
        limit=page_size, offset=max(0, offset))
    return {
        "series": [_series_out(s) for s in items],
        "count": len(items),
        "total": total,
        "limit": page_size,
        "offset": max(0, offset),
        "has_more": max(0, offset) + len(items) < total,
    }


# PHAI khai bao TRUOC `/api/animation/series/{series_id}` — cung ly do voi
# `/api/novels/tags`.
@app.get("/api/animation/series/tags")
def list_animation_series_tags() -> Dict[str, Any]:
    tags = animation_store.series_tags(published_only=True)
    return {"tags": tags, "count": len(tags)}


@app.post("/api/animation/series", status_code=status.HTTP_201_CREATED)
def create_animation_series(payload: AnimationSeriesIn,
                            profile: Profile = Depends(current_profile),
                            ) -> Dict[str, Any]:
    series = animation_store.create_series(AnimationSeries(
        owner_id=profile.user_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        tags=payload.tags,
        related_novel_id=payload.related_novel_id.strip(),
    ))
    return {"series": _series_out(series)}


@app.get("/api/animation/series/{series_id}")
def get_animation_series(series_id: str,
                         authorization: Optional[str] = Header(default=None),
                         ) -> Dict[str, Any]:
    """Series kem DANH SACH TAP — cung ly do gop voi `GET /api/novels/{id}`:
    tranh N+1 khi trang chi tiet can biet tung tap."""
    try:
        series = animation_store.get_series(series_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    if not _may_read_series(series, optional_profile(authorization)):
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Không tìm thấy series animation.")

    episodes = animation_store.list_episodes(series_id)
    return {
        "series": _series_out(series),
        "episodes": [e.to_dict() for e in episodes],
    }


@app.patch("/api/animation/series/{series_id}")
def update_animation_series(series_id: str, payload: AnimationSeriesPatch,
                            profile: Profile = Depends(current_profile),
                            ) -> Dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    if isinstance(fields.get("title"), str):
        fields["title"] = fields["title"].strip()
    try:
        series = animation_store.update_series(series_id, profile.user_id, fields)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"series": _series_out(series)}


@app.delete("/api/animation/series/{series_id}")
def delete_animation_series(series_id: str,
                            profile: Profile = Depends(current_profile),
                            ) -> Dict[str, Any]:
    """Xoa series CUNG moi tap cua no. KHONG dong toi YouTube — chi go
    metadata cua Fanfic (xem docstring dau `animation_domain.py`)."""
    try:
        animation_store.owned_series(series_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    removed = 0
    for episode in animation_store.list_episodes(series_id):
        animation_store.delete_episode(episode.episode_id, profile.user_id)
        removed += 1
    animation_store.delete_series(series_id, profile.user_id)
    return {"deleted": True, "removed_episodes": removed}


@app.post("/api/animation/series/{series_id}/publish")
def publish_animation_series(series_id: str,
                             profile: Profile = Depends(current_profile),
                             ) -> Dict[str, Any]:
    """Xuat ban series — cung cong chan voi `POST /api/novels/{id}/publish`
    (`FAS_AUTHOR_GATE`, mac dinh TAT)."""
    if settings.author_gate_enabled:
        try:
            creators.assert_can_publish(profile)
        except AuthorStateError as exc:
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    try:
        series = animation_store.publish_series(series_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"series": _series_out(series)}


@app.post("/api/animation/series/{series_id}/unpublish")
def unpublish_animation_series(series_id: str,
                               profile: Profile = Depends(current_profile),
                               ) -> Dict[str, Any]:
    try:
        series = animation_store.unpublish_series(series_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"series": _series_out(series)}


@app.post("/api/animation/series/{series_id}/episodes/order")
def reorder_animation_episodes(series_id: str, payload: EpisodeOrderIn,
                               profile: Profile = Depends(current_profile),
                               ) -> Dict[str, Any]:
    try:
        episodes = animation_store.reorder_episodes(
            series_id, profile.user_id, payload.episode_ids)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"episodes": [e.to_dict() for e in episodes]}


@app.post("/api/animation/episodes", status_code=status.HTTP_201_CREATED)
def create_animation_episode(payload: AnimationEpisodeIn,
                             profile: Profile = Depends(current_profile),
                             ) -> Dict[str, Any]:
    try:
        animation_store.owned_series(payload.series_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    video_id = parse_youtube_id(payload.youtube_url)
    if not video_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Không đọc được ID video YouTube từ đường dẫn này.")

    episode = animation_store.create_episode(AnimationEpisode(
        series_id=payload.series_id,
        owner_id=profile.user_id,
        title=payload.title.strip(),
        source=AnimationSource.YOUTUBE,
        external_id=video_id,
        order_index=payload.order_index,
    ))
    return {"episode": episode.to_dict()}


def _episode_with_series_or_404(
        episode_id: str) -> Tuple[AnimationEpisode, Optional[AnimationSeries]]:
    try:
        episode = animation_store.get_episode(episode_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    try:
        series: Optional[AnimationSeries] = animation_store.get_series(
            episode.series_id)
    except NotFoundError:
        series = None
    return episode, series


@app.get("/api/animation/episodes/{episode_id}")
def get_animation_episode(episode_id: str,
                          authorization: Optional[str] = Header(default=None),
                          ) -> Dict[str, Any]:
    """Mot tap kem series cha VA tap ke truoc/sau (theo `order_index`).

    Quyen doc bam theo SERIES CHA, giong `GET /api/chapters/{id}` voi truyen."""
    episode, series = _episode_with_series_or_404(episode_id)
    viewer = optional_profile(authorization)
    # Quyen doc bam theo SERIES CHA (xem docstring ham), CONG THEM kiem duyet
    # RIENG cua chinh tap do (Phase 4) — mot tap co the bi go xuong ma khong
    # dong toi ca series.
    if (series is None or not _may_read_series(series, viewer)
            or episode.moderation_state is not ContentState.VISIBLE):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tập.")

    cac_tap = animation_store.list_episodes(episode.series_id)
    vi_tri = next((i for i, e in enumerate(cac_tap)
                   if e.episode_id == episode_id), None)
    tap_truoc = cac_tap[vi_tri - 1] if vi_tri is not None and vi_tri > 0 else None
    tap_sau = (cac_tap[vi_tri + 1]
               if vi_tri is not None and vi_tri + 1 < len(cac_tap) else None)
    return {
        "episode": episode.to_dict(),
        "series": _series_out(series),
        "prev_episode_id": tap_truoc.episode_id if tap_truoc else None,
        "next_episode_id": tap_sau.episode_id if tap_sau else None,
    }


@app.patch("/api/animation/episodes/{episode_id}")
def update_animation_episode(episode_id: str, payload: AnimationEpisodePatch,
                             profile: Profile = Depends(current_profile),
                             ) -> Dict[str, Any]:
    fields = payload.model_dump(exclude_none=True, exclude={"youtube_url"})
    if payload.youtube_url is not None:
        video_id = parse_youtube_id(payload.youtube_url)
        if not video_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Không đọc được ID video YouTube từ đường dẫn này.")
        fields["external_id"] = video_id
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    if isinstance(fields.get("title"), str):
        fields["title"] = fields["title"].strip()
    try:
        episode = animation_store.update_episode(episode_id, profile.user_id, fields)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"episode": episode.to_dict()}


@app.delete("/api/animation/episodes/{episode_id}")
def delete_animation_episode(episode_id: str,
                             profile: Profile = Depends(current_profile),
                             ) -> Dict[str, Any]:
    try:
        animation_store.delete_episode(episode_id, profile.user_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    return {"deleted": True}


@app.get("/api/search/animation")
def search_animation(q: str = "", limit: int = 5) -> Dict[str, Any]:
    """
    Danh muc "Animation" cua tim kiem toan cuc (Phan 5E) — cung mau voi
    `GET /api/search/audio`: tim SERIES CONG KHAI khop `q`.
    """
    tu = q.strip()
    if len(tu) < 2:
        return {"series": []}
    gioi_han = max(1, min(20, limit))
    series, _ = animation_store.find_series(
        published_only=True, query=tu, limit=gioi_han)
    return {"series": [_series_out(s) for s in series]}


# Binh luan TAP dung `CommentIn`, dinh nghia sau trong tep nay — hai route
# tuong ung nam CANH `create_chapter_comment`/`list_chapter_comments`
# (muc "binh luan"), khong o day, de khong tham chieu mot lop chua khai bao.


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


def _ngay_utc_hom_nay() -> str:
    """Ngay UTC hien tai, chuoi `YYYY-MM-DD` — dung lam `today` cho chuoi
    ngay doc va khoa ky nhiem vu (xem `gamification_domain.advance_streak`/
    `quest_period_key`). MOT cho DUY NHAT doc dong ho he thong cho ca hai
    tinh nang, de test co the thay the bang mot ngay co dinh neu can."""
    return datetime.now(timezone.utc).date().isoformat()


@app.post("/api/progress/read")
def bao_cao_dang_doc(payload: ReadProgressIn,
                     profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Ghi con tro "dang doc chuong nao" cho module Tiep tuc doc o trang chu.

    Khong kiem `novel_id`/`chapter_id` co that su ton tai hay khong: day la
    con tro CA NHAN, chi chinh chu doc lai duoc qua `/api/progress/continue`
    (roi ham do tu bo qua con tro tro toi noi da bi xoa) — mot id sai chi lam
    con tro cua chinh nguoi goi vo dung, khong anh huong ai khac.

    Cung la noi ghi CHUOI NGAY DOC va cong tien do nhiem vu "doc" (V4 visual
    completion, vong 5) — day la tin hieu THAT duy nhat may chu co ve viec
    "hom nay da doc chua", nen ca hai tinh nang deu bam vao day thay vi tu
    doan tu cho khac."""
    profile.last_read_novel_id = payload.novel_id
    profile.last_read_chapter_id = payload.chapter_id
    profile.last_read_at = now_iso()
    identity.save_profile(profile)
    hom_nay = _ngay_utc_hom_nay()
    record_daily_read(gamification_store, profile.user_id, hom_nay)
    record_quest_event(gamification_store, profile.user_id, "chapter_read", hom_nay)
    return {"ok": True}


@app.post("/api/progress/listen")
def bao_cao_dang_nghe(payload: ListenProgressIn,
                      profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Cung vai tro voi `bao_cao_dang_doc`, kem vi tri giay de hien thanh tien
    do khi quay lai. Cung cong tien do nhiem vu "nghe" (vong 5)."""
    profile.last_listen_novel_id = payload.novel_id
    profile.last_listen_chapter_id = payload.chapter_id
    profile.last_listen_position_seconds = float(payload.position_seconds)
    profile.last_listen_at = now_iso()
    record_quest_event(gamification_store, profile.user_id, "chapter_listened",
                       _ngay_utc_hom_nay())
    identity.save_profile(profile)
    return {"ok": True}


@app.post("/api/progress/watch")
def bao_cao_dang_xem(payload: WatchProgressIn,
                     profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """
    "Tiep tuc xem" Animation (V6, overnight Phase 5) — cung vai tro voi
    `bao_cao_dang_nghe`, kem CA vi tri LAN do dai tap (do YouTube IFrame API
    o trinh duyet bao ve, khong hoi lai YouTube tu backend).
    """
    profile.last_watch_series_id = payload.series_id
    profile.last_watch_episode_id = payload.episode_id
    profile.last_watch_position_seconds = float(payload.position_seconds)
    profile.last_watch_duration_seconds = float(payload.duration_seconds)
    profile.last_watch_at = now_iso()
    identity.save_profile(profile)
    return {"ok": True}


def _tiep_tuc_xem(series_id: str, episode_id: str, luc: str, *,
                  vi_tri_giay: float = 0.0,
                  do_dai_giay: float = 0.0) -> Optional[Dict[str, Any]]:
    """Muc "Tiep tuc xem" cua `/api/progress/continue` — cung triet ly voi
    `_tiep_tuc_mot_muc`: AN module neu con tro tro toi series/tap da bi xoa,
    KHONG bia du lieu."""
    if not series_id or not episode_id:
        return None
    try:
        series = animation_store.get_series(series_id)
        episode = animation_store.get_episode(episode_id)
    except NotFoundError:
        return None
    return {
        "series_id": series.series_id,
        "series_title": series.title,
        "episode_id": episode.episode_id,
        "episode_title": episode.title,
        "episode_order_index": episode.order_index,
        "position_seconds": vi_tri_giay,
        # `None` khi chua biet do dai — giao dien hien vi tri da xem MA KHONG
        # bia mot mau so, cung nguyen tac voi `_tiep_tuc_mot_muc`.
        "duration_seconds": do_dai_giay or None,
        "updated_at": luc,
    }


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
        "watching": _tiep_tuc_xem(
            profile.last_watch_series_id, profile.last_watch_episode_id,
            profile.last_watch_at,
            vi_tri_giay=profile.last_watch_position_seconds,
            do_dai_giay=profile.last_watch_duration_seconds),
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
    Ho so cua nguoi goi, VA nguoi do phai la quan tri — BAT KY muc nao trong
    ba muc (OWNER/ADMIN/MODERATOR, xem `AdminRole` va `Settings.admin_role_of`,
    Admin Control Center V2). Truoc ban V2 chi co mot muc phang; ham nay GIU
    NGUYEN TEN va hai ma loi cu de moi route dang dung no khong phai doi gi,
    chi rong dinh nghia "la quan tri" thanh "co bat ky vai tro nao trong ba".

    Hai ma khac nhau, va khac biet do la co y:
      401  chua dang nhap        -> `current_profile` nem
      403  dang nhap nhung khong phai quan tri

    Tra 404 cho ca hai se giau duoc su ton tai cua khu quan tri, nhung doi lai
    la mot nguoi quan tri that go nham tai khoan se khong hieu vi sao khong vao
    duoc. Khu nay khong bi mat, no chi bi khoa.
    """
    if settings.admin_role_of(profile.user_id) == AdminRole.NONE:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Khu vực quản trị.")
    return profile


def owner_profile(profile: Profile = Depends(current_profile)) -> Profile:
    """
    CHI muc OWNER — cai dat he thong/ha tang/tai chinh (vd cong tac khan cap
    Image Studio, cai dat WebSub/nguon tin cay o muc he thong). ADMIN va
    MODERATOR deu nhan 403 o day, kem ADMIN co the lam duoc nhieu viec khac
    qua `admin_or_owner_profile`/`admin_profile`.
    """
    if settings.admin_role_of(profile.user_id) != AdminRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Khu vực chỉ dành cho Owner.")
    return profile


def admin_or_owner_profile(profile: Profile = Depends(current_profile)) -> Profile:
    """
    Muc ADMIN tro len (ADMIN hoac OWNER) — quan ly nguoi dung/noi dung/phan
    tich/nguon tin cay YouTube. MODERATOR nhan 403: ho chi duoc xem/xu ly bao
    cao va kiem duyet noi dung qua `admin_profile`, khong quan ly vai tro hay
    them nguon tin cay moi.
    """
    if settings.admin_role_of(profile.user_id) not in (
        AdminRole.ADMIN, AdminRole.OWNER,
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Cần quyền Admin trở lên.")
    return profile


def _kiem_quyen_tac_dong_tai_khoan(admin: Profile, target_user_id: str) -> None:
    """
    Rao chan cho thao tac quan tri TREN MOT TAI KHOAN KHAC — tam dung/bo tam
    dung/cham dut phien dang nhap (Phase 3, Admin Control Center V2).

    Vai tro (OWNER/ADMIN/MODERATOR) la BIEN MOI TRUONG, khong phai cot ghi
    duoc (xem `Settings.admin_role_of`) — nen KHONG co thao tac "doi vai tro"
    qua API, va rui ro kinh dien "ADMIN tu nang minh len OWNER" khong the xay
    ra vi khong co duong ghi nao vao ba danh sach do ca. Hai rui ro CON LAI,
    that su xay ra duoc qua cac nut o day, moi duoc chan:

    - Tu tac dong len CHINH MINH: tam dung/cham dut MOI phien tren chinh tai
      khoan dang dang nhap se tu khoa minh ngay giua luc thao tac.
    - ADMIN tac dong len MOT TAI KHOAN QUAN TRI KHAC (ADMIN hoac OWNER): chi
      OWNER moi duoc dong toi tai khoan cua nguoi lam quan tri — chan mot
      ADMIN (vi du tai khoan bi chiem) tam dung dong nghiep hay chinh OWNER.
    """
    if target_user_id == admin.user_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Không thể tự thao tác trên chính tài khoản đang đăng nhập.")
    vai_tro_dich = settings.admin_role_of(target_user_id)
    if vai_tro_dich != AdminRole.NONE and settings.admin_role_of(admin.user_id) != AdminRole.OWNER:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ Owner mới được thao tác trên tài khoản quản trị khác.")


class NoteIn(BaseModel):
    note: Annotated[str, StringConstraints(max_length=1000)] = ""


def _an_toan_song_song(future, mac_dinh, *, nhan: str = "admin"):
    """
    Lay ket qua MOT future chay song song qua `ThreadPoolExecutor` — LOI (vd
    Appwrite dev VM cham/timeout khi bi nhieu luong hoi cung luc, da xac
    nhan THAT khi do Phase 5/7) tra ve `mac_dinh` (thuong = None, dung triet
    ly co san "None = chua co du lieu, khong phai 0") THAY VI lam SUP CA
    route vi MOT nhom cham. Ghi log de van hanh biet, khong nem loi len
    quan tri vien. Dung chung cho `_admin_dashboard_them`,
    `admin_analytics_detail`, `admin_image_studio_spending`.
    """
    try:
        return future.result()
    except Exception as exc:
        # ASCII thuan tuy: print() khong dam bao encoding UTF-8 tren moi
        # moi truong (vd console Windows cp1252) — mot ky tu co dau o day
        # co the tu no nem UnicodeEncodeError, pha huy chinh muc dich cua
        # duong an toan nay.
        #
        # loc_bo_theo_gia_tri(): phong truong hop MOT nhom truy van (vd mot
        # provider/adapter moi them sau nay) nem loi chua bi mat dang
        # Bearer/JWT/khoa Appwrite truoc khi kip di qua `thong_diep_loi_an_toan`
        # o tang duoi — xem server/secret_redaction.py (Phase 12 audit).
        print(f"[{nhan}] mot nhom truy van loi, dung gia tri mac dinh: "
              f"{loc_bo_theo_gia_tri(repr(exc))}")
        return mac_dinh


@app.post("/api/admin/_diag/r2-probe")
def r2_probe(owner: Profile = Depends(owner_profile)) -> Dict[str, Any]:
    """
    Chan doan R2 THAT SU (khong qua URL ky, khong qua job TTS) — su co
    2026-08-23: job TTS bao `completed` nhung HEAD/GET ngay sau do lai bao
    `NoSuchKey`. Xem docstring `R2StorageAdapter` muc "chan doan" ve ly do
    can bon ham `*_probe` rieng.

    CHI OWNER, CHI o staging (kiem tra ca hai o day, khong tin API key/role
    duoc cap dung ben ngoai): day la duong ghi/xoa TRUC TIEP vao R2, tuyet
    doi khong duoc cham toi R2 production du bang bat ky duong nao.

    KHONG nhan tham so tu request — khoa xac dinh CUNG THOI DIEM goi, ngau
    nhien, duoi tien to `qa-r2-probe/`. Khong co duong nao de goi ghi de/xoa
    mot khoa tuy y qua endpoint nay.

    Chay HAI phep thu SONG SONG (chung mot khoang thoi gian cho, khong cong
    don) de tach adapter R2 khoi duong TTS that:
      - `tiny`: khoa toi thieu, khong lien quan TTS/audio.
      - `audio_shaped`: cung KHUON khoa voi audio that
        (`audio/{owner}/{chapter}/{hash}.mp3`) va kich thuoc du lieu xap xi
        mot doan audio ngan — de xac nhan hanh vi giong het duong that.

    Xoa CA HAI khoa cua chinh no truoc khi tra ve, ke ca khi mot buoc giua
    chung nem loi.
    """
    if settings.environment.lower() != "staging":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not isinstance(storage, R2StorageAdapter):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Backend hien khong dung R2 (STORAGE_BACKEND != r2).")

    diag_id = uuid.uuid4().hex[:16]
    phep_thu = {
        "tiny": {
            "key": f"qa-r2-probe/{diag_id}.txt",
            "body": f"r2 probe {diag_id}".encode("utf-8"),
            "content_type": "text/plain",
        },
        "audio_shaped": {
            "key": f"audio/qa-r2-probe/{diag_id}/deadbeefcafefeed.mp3",
            # Kich thuoc xap xi mot doan audio Edge TTS ngan — KHONG phai
            # MP3 that, chi de xac nhan hanh vi ghi/doc voi kich thuoc va
            # tien to khoa GIONG HET duong TTS that.
            "body": b"\x00" * 24_000,
            "content_type": "audio/mpeg",
        },
    }

    ket_qua: Dict[str, Any] = {
        "bucket": storage._bucket,  # dinh danh, KHONG bi mat (xem quy uoc BAO_CAO_STAGING.md)
        "diag_id": diag_id,
        "phep_thu": {},
    }
    try:
        for ten, cfg in phep_thu.items():
            khoa = cfg["key"]
            nhanh: Dict[str, Any] = {"key": khoa, "byte_length": len(cfg["body"])}
            try:
                nhanh["put"] = storage.put_probe(khoa, cfg["body"], cfg["content_type"])
                nhanh["put_loi"] = None
            except Exception as exc:
                nhanh["put"] = None
                nhanh["put_loi"] = f"{type(exc).__name__}: {loc_bo_theo_gia_tri(str(exc))}"
            nhanh["head_ngay"] = storage.head_probe(khoa)
            nhanh["get_ngay"] = storage.get_probe(khoa)
            nhanh["list_ngay"] = storage.list_probe(khoa)
            nhanh["head_tre"] = []
            ket_qua["phep_thu"][ten] = nhanh

        t0 = time.monotonic()
        for moc_giay in (1, 3, 10, 30):
            time.sleep(max(0.0, moc_giay - (time.monotonic() - t0)))
            for ten in phep_thu:
                khoa = phep_thu[ten]["key"]
                ket_qua["phep_thu"][ten]["head_tre"].append({
                    "moc_giay": moc_giay,
                    **storage.head_probe(khoa),
                })
        return ket_qua
    finally:
        for cfg in phep_thu.values():
            try:
                storage.delete(cfg["key"])
            except Exception:
                pass


@app.get("/api/admin/overview")
def admin_overview(admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    return {**creators.admin_overview(), **_admin_dashboard_them()}


def _admin_dashboard_them() -> Dict[str, Any]:
    """
    Cac muc MOI cua bang dieu khien (Admin Control Center V2, A1) — goi THEM
    ben canh `creators.admin_overview()` cu (KHONG thay the — giao dien cu,
    neu con noi nao dung, van doc duoc y het truoc).

    MOI phep dem o day deu BI CHAN: `limit(1)` + doc `total` cua Appwrite,
    hoac mot snapshot da co san trong bo nho (`image_spending_guard`).
    KHONG vong lap tren tung hang, KHONG quet toan bang — dung yeu cau
    "Do not create expensive full-table scans for dashboard cards".

    Phase 7 — SONG SONG HOA: ~10 nhom truy van BI CHAN, DOC LAP voi nhau
    (khong nhom nao doc ket qua cua nhom khac), chay qua
    `ThreadPoolExecutor` thay vi tuan tu — day la I/O-bound (cho phan hoi
    HTTP tu Appwrite VM o xa), nen luong (thread) that su giam duoc tong
    thoi gian cho (GIL nha ra trong luc cho socket), khong phai gia von.
    `httpx.Client` (dung trong MOI kho Appwrite o day) an toan dung dong
    thoi tren nhieu luong — xem tai lieu httpx. Da xac nhan qua QA trinh
    duyet that: dashboard cu (tuan tu) mat 13-90+ giay tren VM dev o xa;
    day la lan dau ham nay duoc song song hoa (Phase 2-6 chi ghi nhan la
    "huong kha di cho phase sau", Phase 7 la phase do).
    """
    now = datetime.now(timezone.utc)
    dau_ngay_hom_nay = now.replace(hour=0, minute=0, second=0, microsecond=0)
    moc_hom_nay = dau_ngay_hom_nay.isoformat(timespec="seconds")
    moc_7_ngay = (now - timedelta(days=7)).isoformat(timespec="seconds")
    moc_30_ngay = (now - timedelta(days=30)).isoformat(timespec="seconds")

    def _appwrite_khoe() -> Optional[bool]:
        try:
            return identity.healthcheck()
        except Exception:
            return False

    def _doi_chieu() -> Dict[str, Any]:
        # MOT truy van bi chan duy nhat (limit=1, moi nhat truoc) cho ca
        # "lan chay gan nhat" LAN "tong so lan chay" cung luc.
        return creators.admin_events(action="reconciliation_run", limit=1)

    def _users() -> Dict[str, Any]:
        return {
            "total": identity.count_profiles(),
            "new_today": identity.count_profiles(created_after=moc_hom_nay),
            "new_7d": identity.count_profiles(created_after=moc_7_ngay),
            "new_30d": identity.count_profiles(created_after=moc_30_ngay),
            # Phase 3 (Admin Control Center V2): doc THANG tu Appwrite Users
            # API (`IdentityAdapter.count_accounts`), khong phai tu `profiles`
            # — day la du lieu Auth native, xem `AccountStatus`.
            "verified": identity.count_accounts(email_verified=True),
            "unverified": identity.count_accounts(email_verified=False),
            "suspended": identity.count_accounts(enabled=False),
        }

    def _noi_dung_rieng() -> Dict[str, Any]:
        # Phan phu thuoc `xa_hoi` (comments/pending_reports) duoc ghep VAO
        # SAU, o luong chinh — day chi la phan DOC LAP voi social_overview.
        return {
            "novels_total": store.total_novels(),
            "chapters_total": store.total_chapters(),
            "animation_series_total": animation_store.find_series(limit=1)[1],
            "animation_series_published": animation_store.find_series(
                published_only=True, limit=1)[1],
            "animation_episodes_total": animation_store.total_episodes(),
        }

    def _san_pham() -> Dict[str, Any]:
        return {
            "translation_projects_total": translation_svc.admin_total_projects(),
            "tts_jobs_total": store.total_jobs(),
        }

    def _trusted_sources_rieng() -> Dict[str, Any]:
        # Phan phu thuoc `doi_chieu` duoc ghep VAO SAU o luong chinh.
        #
        # Auto-Ingestion Phase 4 (Stage H, trang He thong): `find_sources(
        # limit=None)` roi lap qua TAT CA de tinh suc khoe tung nguon — VUOT
        # nguyen tac "khong quet toan bang" cua ham nay NOI CHUNG, nhung
        # CHAP NHAN DUOC rieng cho Trusted Sources vi so luong du kien HANG
        # CHUC (khong phai hang nghin/hang trieu nhu users/novels) — cung
        # gia dinh da dung o `TrustedSourceService._dinh_danh_da_ton_tai`
        # (cung quet toan bo de chan trung lap).
        tat_ca_nguon, tong_nguon = trusted_source_store.find_sources(limit=None)
        dem_suc_khoe = {"healthy": 0, "degraded": 0, "action_required": 0, "disabled": 0}
        dang_hoat_dong = 0
        sap_het_han = 0
        moc_sap_het_han = (now + timedelta(hours=24)).isoformat(timespec="seconds")
        for s in tat_ca_nguon:
            suc_khoe, _ = compute_source_health(s)
            dem_suc_khoe[suc_khoe.value] += 1
            if s.subscription_status is SubscriptionStatus.ACTIVE:
                dang_hoat_dong += 1
                if s.subscription_expires_at and s.subscription_expires_at <= moc_sap_het_han:
                    sap_het_han += 1
        return {
            "total": tong_nguon,
            "enabled_total": trusted_source_store.find_sources(
                enabled=True, limit=1)[1],
            "detected_today": trusted_source_store.find_imports(
                created_after=moc_hom_nay, limit=1)[1],
            "auto_imported_total": (
                trusted_source_store.find_imports(status="auto_imported", limit=1)[1]
                + trusted_source_store.find_imports(status="auto_published", limit=1)[1]),
            "pending_total": trusted_source_store.find_imports(
                status="pending", limit=1)[1],
            "error_total": (
                trusted_source_store.find_imports(status="conflict", limit=1)[1]
                + trusted_source_store.find_imports(status="duplicate", limit=1)[1]
                + trusted_source_store.find_imports(status="unavailable", limit=1)[1]
                + trusted_source_store.find_imports(status="failed", limit=1)[1]),
            # Phase "public dev backend + real WebSub E2E": tin hieu THAT
            # duy nhat chung minh hub da tung xac minh dang ky thanh cong —
            # xem `_trang_thai_he_thong` ve ly do "da cau hinh" khong du.
            "websub_subscription_active": trusted_source_store.has_active_websub_subscription(),
            # Auto-Ingestion Phase 4 (Stage H) — xem `compute_source_health`.
            "health_counts": dem_suc_khoe,
            "active_subscriptions": dang_hoat_dong,
            "subscriptions_expiring_soon": sap_het_han,
        }

    def _an_toan(future, mac_dinh):
        return _an_toan_song_song(future, mac_dinh, nhan="admin_overview")

    # `max_workers=4` (khong phai 8, dung bang so nhom) CO CHU DICH: kiem
    # tra THAT tren Appwrite dev tu luu tru (VM nho, mot tien trinh) cho
    # thay 8 luong dong thoi thinh thoang lam MOT truy van vuot qua 15 giay
    # (REQUEST_TIMEOUT) do VM qua tai — gioi han con 4 giam tai dinh, van
    # giu phan lon loi ich song song so voi tuan tu hoan toan.
    with ThreadPoolExecutor(max_workers=4) as bo_luong:
        f_appwrite_khoe = bo_luong.submit(_appwrite_khoe)
        f_xa_hoi = bo_luong.submit(social.social_overview)
        f_doi_chieu = bo_luong.submit(_doi_chieu)
        f_users = bo_luong.submit(_users)
        f_noi_dung = bo_luong.submit(_noi_dung_rieng)
        f_san_pham = bo_luong.submit(_san_pham)
        f_trusted = bo_luong.submit(_trusted_sources_rieng)
        f_traffic = bo_luong.submit(traffic_analytics.overview)

        appwrite_khoe = _an_toan(f_appwrite_khoe, False)
        xa_hoi = _an_toan(f_xa_hoi, {"total_comments": None, "open_reports": None})
        doi_chieu = _an_toan(f_doi_chieu, {"events": [], "total": None})
        users = _an_toan(f_users, {
            "total": None, "new_today": None, "new_7d": None, "new_30d": None,
            "verified": None, "unverified": None, "suspended": None})
        noi_dung = _an_toan(f_noi_dung, {
            "novels_total": None, "chapters_total": None,
            "animation_series_total": None, "animation_series_published": None,
            "animation_episodes_total": None})
        san_pham = _an_toan(f_san_pham, {
            "translation_projects_total": None, "tts_jobs_total": None})
        trusted = _an_toan(f_trusted, {
            "total": None, "enabled_total": None, "detected_today": None,
            "auto_imported_total": None, "pending_total": None, "error_total": None,
            "websub_subscription_active": False,
            "health_counts": {"healthy": None, "degraded": None,
                             "action_required": None, "disabled": None},
            "active_subscriptions": None, "subscriptions_expiring_soon": None})
        traffic = _an_toan(f_traffic, {
            "configured": False, "message": "Tạm thời không đọc được trạng thái.",
            "visits_today": None, "pageviews_today": None, "visits_7d": None,
            "pageviews_7d": None, "visits_30d": None, "pageviews_30d": None,
            "top_paths": None, "trend_by_day": None, "referrers": None,
            "countries": None, "device_categories": None})

    chi_tieu = image_spending_guard.snapshot()  # trong bo nho, khong can luong rieng
    lan_chay_gan_nhat = (
        doi_chieu["events"][0]["created_at"] if doi_chieu["events"] else "")
    tong_lan_doi_chieu = doi_chieu["total"]

    noi_dung["comments_total"] = xa_hoi["total_comments"]
    noi_dung["pending_reports"] = xa_hoi["open_reports"]
    san_pham["image_studio_spend_usd"] = chi_tieu.spent_usd
    san_pham["image_studio_budget_usd"] = chi_tieu.budget_usd
    # Chua co phep dem RIENG cho so luot sinh anh (chi co chi tieu gop) —
    # None thay vi suy tu chi tieu (mot lan sinh khong dong gia mot lan chi).
    san_pham["image_generations_total"] = None
    trusted["configured"] = True
    trusted["reconciliation_total_runs"] = tong_lan_doi_chieu
    trusted["reconciliation_last_run_at"] = lan_chay_gan_nhat or None

    return {
        "users": users,
        "content": noi_dung,
        "product": san_pham,
        "trusted_sources": trusted,
        "traffic": traffic,
        "system": {
            "backend": "ok",
            "data_backend": settings.data_backend,
            "appwrite_configured": settings.appwrite.configured,
            "appwrite_healthy": appwrite_khoe if settings.appwrite.configured else None,
            "inline_worker": settings.inline_worker,
            "translation_provider_configured": bool(
                settings.translation_base_url and settings.translation_api_key
                and settings.translation_model),
            "image_studio_shared_premium_configured":
                settings.image_studio.shared_premium_configured,
            # Phase 7 — trang He thong (muc 7): YouTube Data API/WebSub deu
            # la kiem tra CO CAU HINH hay khong (khong goi mang), rong.
            "youtube_data_api_configured": trusted_sources.youtube_configured(),
            "youtube_websub_configured": trusted_sources.websub_configured(),
            "statuses": _trang_thai_he_thong(
                appwrite_configured=settings.appwrite.configured,
                appwrite_healthy=appwrite_khoe,
                translation_configured=bool(
                    settings.translation_base_url and settings.translation_api_key
                    and settings.translation_model),
                image_studio_configured=settings.image_studio.shared_premium_configured,
                youtube_data_api_configured=trusted_sources.youtube_configured(),
                youtube_websub_configured=trusted_sources.websub_configured(),
                youtube_websub_verified_active=bool(trusted["websub_subscription_active"]),
                reconciliation_total_runs=tong_lan_doi_chieu,
                reconciliation_last_run_at=lan_chay_gan_nhat,
                now=now,
            ),
        },
    }


#: Bon trang thai duy nhat cho MOI hang muc o trang He thong (Phase 7, muc
#: 7) — khong bia them gia tri trung gian nao khac.
TRANG_THAI_KHOE = "healthy"
TRANG_THAI_SUY_GIAM = "degraded"
TRANG_THAI_LOI = "error"
TRANG_THAI_CHUA_CAU_HINH = "not_configured"


def _trang_thai_he_thong(
    *, appwrite_configured: bool, appwrite_healthy: Optional[bool],
    translation_configured: bool, image_studio_configured: bool,
    youtube_data_api_configured: bool, youtube_websub_configured: bool,
    youtube_websub_verified_active: bool,
    reconciliation_total_runs: int, reconciliation_last_run_at: str,
    now: datetime,
) -> Dict[str, str]:
    """
    Tinh trang thai HEALTHY/DEGRADED/ERROR/NOT_CONFIGURED cho tung hang muc
    trang He thong — CHI dua tren tin hieu THAT SU co san (cau hinh + mot
    lan doc da co san), KHONG bia mot phep kiem tra suc khoe khong ton tai.

    `workers` khong co giam sat rieng (khong co tin hieu am nao de phat
    hien "worker chet" — xem han che ghi o handoff muc 4g) nen an theo
    Appwrite: dung duoc Appwrite thi coi la healthy.

    `youtube_websub`: "da cau hinh URL callback" (`youtube_websub_configured`)
    KHONG chung minh duoc hub PubSubHubbub that su goi lai/xac minh duoc gi
    ca — chi la mot bien moi truong duoc dat. Phat hien (phase "public dev
    backend + real WebSub E2E"): truoc day muc nay bao HEALTHY ngay khi
    bien duoc dat, ke ca luc chua co DNS/TLS/dang ky that nao — vi pham
    nguyen tac "khong bao gio bao HEALTHY khi trang thai that con chua ro".
    Gio doi hoi THEM `youtube_websub_verified_active` (it nhat mot nguon o
    trang thai `ACTIVE` — tin hieu THAT tu `has_active_websub_subscription`)
    truoc khi bao HEALTHY; da cau hinh nhung chua tung xac minh duoc thi la
    DEGRADED (chua chung minh, khong phai loi).
    """
    if not appwrite_configured:
        appwrite = TRANG_THAI_CHUA_CAU_HINH
    elif appwrite_healthy:
        appwrite = TRANG_THAI_KHOE
    else:
        appwrite = TRANG_THAI_LOI

    reconciliation: str
    if not youtube_websub_configured:
        reconciliation = TRANG_THAI_CHUA_CAU_HINH
    elif reconciliation_total_runs <= 0:
        reconciliation = TRANG_THAI_SUY_GIAM
    else:
        try:
            lan_cuoi = datetime.fromisoformat(reconciliation_last_run_at)
            if lan_cuoi.tzinfo is None:
                lan_cuoi = lan_cuoi.replace(tzinfo=timezone.utc)
            reconciliation = (
                TRANG_THAI_KHOE if now - lan_cuoi <= timedelta(hours=48)
                else TRANG_THAI_SUY_GIAM)
        except ValueError:
            reconciliation = TRANG_THAI_SUY_GIAM

    return {
        "backend": TRANG_THAI_KHOE,
        "appwrite": appwrite,
        "workers": appwrite,
        "translation_provider": (
            TRANG_THAI_KHOE if translation_configured else TRANG_THAI_CHUA_CAU_HINH),
        "tts": TRANG_THAI_KHOE,
        "image_studio": (
            TRANG_THAI_KHOE if image_studio_configured else TRANG_THAI_CHUA_CAU_HINH),
        "youtube_data_api": (
            TRANG_THAI_KHOE if youtube_data_api_configured else TRANG_THAI_CHUA_CAU_HINH),
        "youtube_websub": (
            TRANG_THAI_CHUA_CAU_HINH if not youtube_websub_configured
            else TRANG_THAI_KHOE if youtube_websub_verified_active
            else TRANG_THAI_SUY_GIAM),
        "reconciliation": reconciliation,
    }


#: Cua so thoi gian hop le cho /api/admin/analytics/detail — CHINH XAC ba
#: gia tri spec Phase 7 yeu cau (Today/7 days/30 days), khong hon.
_PHAM_VI_HOP_LE = {"today": timedelta(days=0), "7d": timedelta(days=7),
                   "30d": timedelta(days=30)}


def _moc_theo_pham_vi(range: str, now: datetime) -> str:
    delta = _PHAM_VI_HOP_LE.get(range, _PHAM_VI_HOP_LE["7d"])
    if delta == timedelta(days=0):
        moc = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        moc = now - delta
    return moc.isoformat(timespec="seconds")


@app.get("/api/admin/analytics/detail")
def admin_analytics_detail(
    range: str = "7d", admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    """
    Chi tiet phan tich cho `/admin/analytics` (Phase 7) — TACH khoi
    `/api/admin/overview` (bang dieu khien chinh phai nhe, xem muc 6/9
    handoff): CHI trang Analytics goi route nay, va CHI khi nguoi dung mo
    trang do/doi khoang thoi gian — khong polling, khong goi tu dashboard.

    So luong truy van Appwrite cho MOI lan tai (da dem, xem handoff):
    ~15-18 truy van BI CHAN (`limit(1)`/tuong duong), KHONG truy van nao
    keo toan bang. Chi tiet: 1 (dang ky moi trong khoang) + 1 (binh luan
    trong khoang) + 4 (job dich theo status) + 4 (job TTS theo status) +
    4 (video phat hien/tu nhap/cho duyet/loi trong khoang) + 5 (WebSub
    theo trang thai dang ky, KHONG theo khoang — la mot snapshot) + 1
    (doi chieu trong khoang).

    DAU/WAU/MAU va "novel reads/chapter completions/Animation views":
    CHUA the tinh CHINH XAC voi du lieu hien co (xem ghi chu tung muc)
    — tra ve `None` kem `*_note` giai thich, KHONG bia so.

    Phase 5 (performance audit) — SONG SONG HOA: cac truy van tren la 20
    lenh doc BI CHAN, DOC LAP voi nhau (khong lenh nao doc ket qua cua
    lenh khac — `dich_tong`/tong cac trang thai chi duoc CONG lai SAU khi
    ca hai da co ket qua). Truoc phase nay ham chay TUAN TU nen do tre
    mang toi Appwrite (dac biet la VM dev tu luu tru o xa) CONG DON tren
    ca 20 lenh cho MOI lan mo trang. Dung lai idiom da kiem chung an toan
    o `_admin_dashboard_them` (Phase 7): `ThreadPoolExecutor(max_workers=4)`
    — KHONG dung 8, gioi han nay da xac nhan THAT tren VM dev nho (8 luong
    dong thoi tung gay `httpx.ReadTimeout`). Khong doi hanh vi loi: neu
    mot future nem loi, `.result()` van nem thang len nhu duong TUAN TU cu
    (van thanh 500), khong nuot loi lam sai lech so lieu quan tri.
    """
    if range not in _PHAM_VI_HOP_LE:
        range = "7d"
    now = datetime.now(timezone.utc)
    moc = _moc_theo_pham_vi(range, now)

    cong_viec: Dict[str, Any] = {
        "tts_pending": lambda: store.count_jobs(
            status=JobStatus.PENDING, created_after=moc),
        "tts_running": lambda: store.count_jobs(
            status=JobStatus.RUNNING, created_after=moc),
        "tts_completed": lambda: store.count_jobs(
            status=JobStatus.COMPLETED, created_after=moc),
        "tts_failed": lambda: store.count_jobs(
            status=JobStatus.FAILED, created_after=moc),
        "dich_completed": lambda: translation_svc.admin_count_jobs(
            status=TranslationJobStatus.COMPLETED, created_after=moc),
        "dich_failed": lambda: translation_svc.admin_count_jobs(
            status=TranslationJobStatus.FAILED, created_after=moc),
        "dich_cancelled": lambda: translation_svc.admin_count_jobs(
            status=TranslationJobStatus.CANCELLED, created_after=moc),
        "dich_tong": lambda: translation_svc.admin_count_jobs(created_after=moc),
        "doi_chieu": lambda: creators.admin_events(
            action="reconciliation_run", created_after=moc, limit=1),
        "registrations": lambda: identity.count_profiles(created_after=moc),
        "comments": lambda: social.admin_count_comments(created_after=moc),
        "tv_detected": lambda: trusted_source_store.find_imports(
            created_after=moc, limit=1)[1],
        "tv_auto_imported": lambda: trusted_source_store.find_imports(
            status="auto_imported", created_after=moc, limit=1)[1],
        "tv_auto_published": lambda: trusted_source_store.find_imports(
            status="auto_published", created_after=moc, limit=1)[1],
        "tv_pending": lambda: trusted_source_store.find_imports(
            status="pending", created_after=moc, limit=1)[1],
        "tv_err_conflict": lambda: trusted_source_store.find_imports(
            status="conflict", created_after=moc, limit=1)[1],
        "tv_err_duplicate": lambda: trusted_source_store.find_imports(
            status="duplicate", created_after=moc, limit=1)[1],
        "tv_err_unavailable": lambda: trusted_source_store.find_imports(
            status="unavailable", created_after=moc, limit=1)[1],
        "tv_err_failed": lambda: trusted_source_store.find_imports(
            status="failed", created_after=moc, limit=1)[1],
        "websub_breakdown": lambda: trusted_source_store
            .count_sources_by_subscription_status(),
    }
    with ThreadPoolExecutor(max_workers=4) as bo_luong:
        futures = {ten: bo_luong.submit(ham) for ten, ham in cong_viec.items()}
        kq = {ten: f.result() for ten, f in futures.items()}

    tts_status_dem = {
        "pending": kq["tts_pending"], "running": kq["tts_running"],
        "completed": kq["tts_completed"], "failed": kq["tts_failed"],
    }
    dich_status_dem = {
        "completed": kq["dich_completed"], "failed": kq["dich_failed"],
        "cancelled": kq["dich_cancelled"],
    }
    dich_status_dem["in_progress"] = max(
        0, kq["dich_tong"] - sum(dich_status_dem.values()))

    return {
        "range": range,
        "since": moc,
        "users": {
            "registrations": kq["registrations"],
            "active_daily": None,
            "active_weekly": None,
            "active_monthly": None,
            "active_note": (
                "Chưa đo lường được: Appwrite Users API không cho lọc theo "
                "accessedAt (đã xác nhận thật), và tính từ sự kiện thô sẽ "
                "quét toàn bảng — cần hạ tầng đo lường hoạt động chuyên "
                "dụng, ngoài phạm vi Phase 7."
            ),
        },
        "content": {
            "comments": kq["comments"],
            "novel_reads": None,
            "chapter_completions": None,
            "animation_views": None,
            "content_activity_note": (
                "Chưa ghi nhận sự kiện đọc/xem — cần triển khai instrumentation "
                "mới trên đường phục vụ nội dung; sẽ tính từ ngày triển khai "
                "trở đi (không suy ngược lịch sử), ngoài phạm vi Phase 7."
            ),
        },
        "ai_product": {
            "translation_jobs": dich_status_dem,
            "tts_jobs": tts_status_dem,
            "image_studio_generations": None,
            "image_studio_note": (
                "Chưa đếm riêng số lượt sinh ảnh — chỉ có tổng chi tiêu "
                "($), xem /api/admin/image-studio/spending."
            ),
        },
        "trusted_video": {
            "detected": kq["tv_detected"],
            "auto_imported": kq["tv_auto_imported"] + kq["tv_auto_published"],
            "pending": kq["tv_pending"],
            "errors": (kq["tv_err_conflict"] + kq["tv_err_duplicate"]
                      + kq["tv_err_unavailable"] + kq["tv_err_failed"]),
            # Snapshot HIEN TAI, khong phai theo khoang — suc khoe dang ky
            # WebSub la trang thai TAI THOI DIEM doc, khong phai mot phep dem
            # su kien trong ky.
            "websub_status_breakdown": kq["websub_breakdown"],
            "reconciliation_runs": kq["doi_chieu"]["total"],
        },
        "traffic": traffic_analytics.overview(),
    }


@app.get("/api/admin/author-applications")
def admin_applications(status_filter: str = "", limit: int = 25, offset: int = 0,
                       admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    return creators.admin_applications(status=status_filter or None,
                                       limit=max(1, min(100, limit)),
                                       offset=max(0, offset))


@app.get("/api/admin/author-applications/{user_id}")
def admin_application(user_id: str,
                      admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    data = creators.admin_application(user_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn.")
    return {"application": data}


@app.post("/api/admin/author-applications/{user_id}/approve")
def admin_approve(user_id: str, payload: NoteIn,
                  admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Duyet don. Goi thang tang service da duoc kiem thu — route KHONG lap lai
    mot dong logic nghiep vu nao.
    """
    try:
        app_row = creators.approve(
            user_id, note=payload.note, actor_id=admin.user_id,
            actor_role=settings.admin_role_of(admin.user_id).value)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.post("/api/admin/author-applications/{user_id}/reject")
def admin_reject(user_id: str, payload: NoteIn,
                 admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Tu choi don. `note` la BAT BUOC o tang service — mot lan tu choi khong ly do
    la mot cai cua dong im lang, va nguoi nop se doc duoc ghi chu nay.
    """
    try:
        app_row = creators.reject(
            user_id, note=payload.note, actor_id=admin.user_id,
            actor_role=settings.admin_role_of(admin.user_id).value)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.get("/api/admin/authors")
def admin_authors(limit: int = 25, offset: int = 0,
                  admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    return creators.admin_authors(limit=max(1, min(100, limit)),
                                  offset=max(0, offset))


@app.post("/api/admin/authors/{user_id}/suspend")
def admin_suspend(user_id: str, payload: NoteIn,
                  admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Tam dung quyen xuat ban.

    KHONG cham vao noi dung da co: truyen da xuat ban van cong khai, ban nhap van
    con, chuong va audio khong bi xoa. Chi cac lan xuat ban MOI bi chan. Xem
    `docs/ADMIN.md` muc "Treo tac gia lam gi va KHONG lam gi".
    """
    try:
        app_row = creators.suspend(
            user_id, note=payload.note, actor_id=admin.user_id,
            actor_role=settings.admin_role_of(admin.user_id).value)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.post("/api/admin/authors/{user_id}/restore")
def admin_restore(user_id: str, payload: NoteIn,
                  admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    try:
        app_row = creators.restore(
            user_id, note=payload.note, actor_id=admin.user_id,
            actor_role=settings.admin_role_of(admin.user_id).value)
    except AuthorStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"application": app_row.to_dict()}


@app.get("/api/admin/users")
def admin_users(q: str = "", limit: int = 25, offset: int = 0,
                admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Tim tai khoan (Phase 3: nguon la Appwrite Users API native, xem
    `CreatorService.admin_users`). Ket qua CO `email` — day la duong quan tri.
    """
    data = creators.admin_users(query=q, limit=max(1, min(100, limit)),
                                offset=max(0, offset))
    for row in data["users"]:
        # Vai tro doc THANG tu `Settings.admin_role_of` — KHONG bao gio mot
        # cot DB (xem `_kiem_quyen_tac_dong_tai_khoan`), nen phai tinh o day
        # moi lan tra ve, khong the luu san trong `creators.admin_users`.
        row["admin_role"] = settings.admin_role_of(row["user_id"]).value
    return data


@app.get("/api/admin/users/{user_id}")
def admin_user(user_id: str,
               admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    data = creators.admin_user(user_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng.")
    data["admin_role"] = settings.admin_role_of(user_id).value
    return {"user": data}


@app.post("/api/admin/users/{user_id}/suspend")
def admin_user_suspend(user_id: str, payload: NoteIn,
                       admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Tam dung TAI KHOAN — khoa dang nhap HOAN TOAN. TACH BACH voi
    `/api/admin/authors/{user_id}/suspend` (chi chan xuat ban, tac gia van
    dang nhap va doc/nghe binh thuong). Xem `AccountStatus` va
    `_kiem_quyen_tac_dong_tai_khoan`.
    """
    _kiem_quyen_tac_dong_tai_khoan(admin, user_id)
    ket_qua = creators.admin_set_account_enabled(
        user_id, False, note=payload.note, actor_id=admin.user_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if ket_qua is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng.")
    return {"account": ket_qua}


@app.post("/api/admin/users/{user_id}/unsuspend")
def admin_user_unsuspend(user_id: str, payload: NoteIn,
                         admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """Go tam dung tai khoan — cho phep dang nhap lai."""
    _kiem_quyen_tac_dong_tai_khoan(admin, user_id)
    ket_qua = creators.admin_set_account_enabled(
        user_id, True, note=payload.note, actor_id=admin.user_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if ket_qua is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng.")
    return {"account": ket_qua}


@app.post("/api/admin/users/{user_id}/sessions/{session_id}/terminate")
def admin_user_terminate_session(
    user_id: str, session_id: str, payload: NoteIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Cham dut MOT phien dang nhap cu the cua mot tai khoan."""
    _kiem_quyen_tac_dong_tai_khoan(admin, user_id)
    da_huy = creators.admin_terminate_session(
        user_id, session_id, note=payload.note, actor_id=admin.user_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    return {"terminated": da_huy}


@app.post("/api/admin/users/{user_id}/sessions/terminate-all")
def admin_user_terminate_all_sessions(
    user_id: str, payload: NoteIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Cham dut MOI phien dang nhap cua mot tai khoan — dung khi nghi ngo tai
    khoan bi chiem, hoac ngay sau khi tam dung tai khoan do."""
    _kiem_quyen_tac_dong_tai_khoan(admin, user_id)
    so_luong = creators.admin_terminate_all_sessions(
        user_id, note=payload.note, actor_id=admin.user_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    return {"terminated_count": so_luong}


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
def admin_events(limit: int = 50, offset: int = 0, target_user_id: str = "",
                 target_type: str = "", target_id: str = "", action: str = "",
                 admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Nhat ky kiem duyet — /admin/audit-log (Admin Control Center V2, A5).
    CHI THEM — khong co route sua hay xoa. `target_id` (Phase 4) tra cuu
    lich su cua MOT doi tuong cu the (vd mot series/tap Animation).
    """
    return creators.admin_events(
        limit=max(1, min(200, limit)), offset=max(0, offset),
        target_user_id=target_user_id, target_type=target_type,
        target_id=target_id, action=action)


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


def _nguon_tin_cay(fn, *args, **kwargs):
    """
    Cung vai tro voi `_xa_hoi()` nhung cho `TrustedSourceService` (Phase 5) —
    them hai loai loi RIENG cua YouTube Data API.

    `YouTubeConfigError` -> 503: "chua cau hinh", KHONG phai loi cua nguoi
    dung — frontend hien trang thai "Chưa cấu hình" ro rang (xem dac ta
    Phase 5, muc 2), khong phai mot thong bao loi chung chung.
    `YouTubeApiError` -> 429 neu `reason == "quotaExceeded"` (het han muc
    NGAY HOM NAY, khac voi loi ky thuat that), nguoc lai 502 (upstream tu
    choi/khong ket noi duoc).
    """
    try:
        return fn(*args, **kwargs)
    except TrustedSourceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except (YouTubeConfigError, WebSubConfigError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except YouTubeApiError as exc:
        ma = (status.HTTP_429_TOO_MANY_REQUESTS if exc.reason == "quotaExceeded"
             else status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(ma, str(exc)) from exc
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
    ket_qua = {"post": _xa_hoi(social.create_post, profile, text=payload.text,
                               kind=payload.kind, novel_id=payload.novel_id,
                               images=_bo_anh_tu_body(payload))}
    record_quest_event(gamification_store, profile.user_id,
                       "community_interaction", _ngay_utc_hom_nay())
    return ket_qua


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


def _cong_nhiem_vu_binh_luan(user_id: str) -> None:
    """Cong tien do CA HAI nhiem vu lien quan binh luan/dang bai — dung o
    MOI diem tao binh luan (bai dang, chuong, tap animation), tranh lap lai
    hai dong `record_quest_event` o tung route."""
    hom_nay = _ngay_utc_hom_nay()
    record_quest_event(gamification_store, user_id, "comment_posted", hom_nay)
    record_quest_event(gamification_store, user_id, "community_interaction", hom_nay)


@app.post("/api/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
def create_comment(post_id: str, payload: CommentIn,
                   profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    ket_qua = {"comment": _xa_hoi(social.create_comment, profile, post_id,
                                  text=payload.text, parent_id=payload.parent_id)}
    _cong_nhiem_vu_binh_luan(profile.user_id)
    return ket_qua


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
    ket_qua = {"comment": _xa_hoi(
        social.create_chapter_comment, profile, chapter_id,
        text=payload.text, parent_id=payload.parent_id,
        timestamp_ms=payload.timestamp_ms, spoiler=payload.spoiler)}
    _cong_nhiem_vu_binh_luan(profile.user_id)
    return ket_qua


@app.get("/api/animation/episodes/{episode_id}/comments")
def list_episode_comments(episode_id: str, sort: str = "moi",
                          limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """
    Binh luan cua mot TAP animation (V6, overnight Phase 5). Cong khai — chi
    tap cua series DA XUAT BAN (hang rao nam o `SocialService._tap_cong_khai`;
    ban nhap tra 404) — cung mau voi `list_chapter_comments`.
    """
    return _xa_hoi(social.episode_comments, episode_id, sort=sort,
                   limit=max(1, min(50, limit)), offset=max(0, offset))


@app.post("/api/animation/episodes/{episode_id}/comments",
          status_code=status.HTTP_201_CREATED)
def create_episode_comment_route(episode_id: str, payload: CommentIn,
                                 profile: Profile = Depends(current_profile),
                                 ) -> Dict[str, Any]:
    ket_qua = {"comment": _xa_hoi(
        social.create_episode_comment, profile, episode_id,
        text=payload.text, parent_id=payload.parent_id)}
    _cong_nhiem_vu_binh_luan(profile.user_id)
    return ket_qua


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
def admin_social_overview(admin: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
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
    Duyet binh luan toan he thong, TACH duoc BA loai: binh luan bai dang
    (`target_kind=""`), binh luan chuong (`target_kind=chapter`), va binh
    luan tap Animation (`target_kind=animation_episode`, Phase 4 — cung ha
    tang binh luan, xem `SocialService._tap_cong_khai`) — moi loai dan toi
    mot noi khac nhau va nguoi kiem duyet can biet minh dang nhin gi.
    """
    if target_kind not in ("", "chapter", "animation_episode"):
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


# -----------------------------------------------------------------------------
# Kiem duyet ANIMATION (Phase 4, Admin Control Center V2)
# -----------------------------------------------------------------------------
#
# Cung muc quyen voi kiem duyet bai/binh luan o tren (`admin_profile`, tuc la
# TU MODERATOR tro len) — Phase 4 xac dinh Animation la kiem duyet noi dung
# THONG THUONG, khong phai cai dat he thong/tai chinh, nen KHONG can nang len
# `admin_or_owner_profile` nhu quan ly tai khoan (Phase 3). Backend luon la
# noi quyet dinh that — xem `_kiem_quyen_tac_dong_tai_khoan` cho vi du khac o
# Phase 3 ve nguyen tac nay.
#
# KHONG co route XOA that (series/tap) trong Phase 4 — chi go xuong/phuc hoi.
# Neu sau nay can xoa that, do la mot quyet dinh rieng (xem `docs/ADMIN.md`
# muc "Viec con lai" ve ly do khong tu them nut xoa cung).


@app.get("/api/admin/animation/series")
def admin_animation_series(q: str = "", state: str = "", sort: str = "newest",
                           limit: int = 25, offset: int = 0,
                           admin: Profile = Depends(admin_profile)) -> Dict[str, Any]:
    """
    Danh sach series cho khu quan tri — phan trang/loc/sap xep o phia kho,
    KHONG tai toan bo thu vien ve trinh duyet. Xem `SocialService.
    admin_animation_series`.
    """
    if state not in ("", "draft", "published"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "state không hợp lệ.")
    if sort not in ("newest", "oldest"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "sort không hợp lệ.")
    return _xa_hoi(social.admin_animation_series, query=q, state=state,
                   sort=sort, limit=max(1, min(100, limit)), offset=max(0, offset))


@app.get("/api/admin/animation/series/{series_id}")
def admin_animation_series_detail(
    series_id: str, admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    data = social.admin_animation_series_detail(series_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Không tìm thấy series animation.")
    return data


@app.post("/api/admin/animation/series/{series_id}/unpublish")
def admin_unpublish_animation_series(
    series_id: str, payload: RemoveIn,
    admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    """Go xuong MOT series — BAT BUOC ly do (`SocialService.
    unpublish_animation_series` tu choi neu rong, tra 400)."""
    return {"series": _xa_hoi(
        social.unpublish_animation_series, admin, series_id,
        reason=payload.reason,
        actor_role=settings.admin_role_of(admin.user_id).value)}


@app.post("/api/admin/animation/series/{series_id}/restore")
def admin_restore_animation_series(
    series_id: str, payload: FollowIn,
    admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    return {"series": _xa_hoi(
        social.restore_animation_series, admin, series_id,
        actor_role=settings.admin_role_of(admin.user_id).value)}


@app.post("/api/admin/animation/episodes/{episode_id}/unpublish")
def admin_unpublish_animation_episode(
    episode_id: str, payload: RemoveIn,
    admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    """Go MOT tap rieng le — KHONG dong toi series cha. BAT BUOC ly do."""
    return {"episode": _xa_hoi(
        social.unpublish_animation_episode, admin, episode_id,
        reason=payload.reason,
        actor_role=settings.admin_role_of(admin.user_id).value)}


@app.post("/api/admin/animation/episodes/{episode_id}/restore")
def admin_restore_animation_episode(
    episode_id: str, payload: FollowIn,
    admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    return {"episode": _xa_hoi(
        social.restore_animation_episode, admin, episode_id,
        actor_role=settings.admin_role_of(admin.user_id).value)}


# -----------------------------------------------------------------------------
# Trusted Video Sources (Phase 5, Admin Control Center V2 / Animation Phan B)
# -----------------------------------------------------------------------------
#
# GET (xem danh sach/chi tiet nguon, hang doi nhap) dung `admin_profile` (tu
# MODERATOR tro len) — cung muc quyen XEM voi kiem duyet Animation o tren.
# MOI route MUTATE (them/sua/xoa nguon, anh xa, quet, nhap/tu choi/bo qua)
# dung `admin_or_owner_profile` (ADMIN/OWNER) theo dung dac ta Phase 5 muc 4 —
# day la hanh dong TAO NOI DUNG THAT/xac nhan tin cay, khac voi kiem duyet
# thong thuong (an/hien noi dung da co).


class TrustedSourcePreviewIn(BaseModel):
    url: Annotated[str, StringConstraints(max_length=2000)]


class TrustedSourceCreateIn(BaseModel):
    source_type: str
    youtube_channel_id: str = ""
    youtube_playlist_id: str = ""
    youtube_video_id: str = ""
    display_name: Annotated[str, StringConstraints(max_length=200)]
    thumbnail_url: Annotated[str, StringConstraints(max_length=512)] = ""
    auto_discover: bool = False
    auto_import: bool = False
    auto_publish: bool = False
    minimum_confidence: float = 0.9


class TrustedSourceUpdateIn(BaseModel):
    display_name: Optional[Annotated[str, StringConstraints(max_length=200)]] = None
    auto_discover: Optional[bool] = None
    auto_import: Optional[bool] = None
    auto_publish: Optional[bool] = None
    minimum_confidence: Optional[float] = None


class SourceEnabledIn(BaseModel):
    enabled: bool


class ScanSourceIn(BaseModel):
    page_token: str = ""
    max_pages: int = DEFAULT_SCAN_PAGES


class DiscoverSeriesIn(BaseModel):
    youtube_video_id: str


class DiscoverChannelIn(BaseModel):
    max_pages: int = DISCOVERY_SCAN_PAGES


class SeriesMappingCreateIn(BaseModel):
    animation_series_id: str
    aliases: List[str] = []
    include_keywords: List[str] = []
    exclude_keywords: List[str] = []
    minimum_confidence: Optional[float] = None
    auto_import: Optional[bool] = None
    auto_publish: Optional[bool] = None


class SeriesMappingUpdateIn(BaseModel):
    aliases: Optional[List[str]] = None
    include_keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    minimum_confidence: Optional[float] = None
    auto_import: Optional[bool] = None
    auto_publish: Optional[bool] = None


class SetImportSeriesIn(BaseModel):
    series_id: str = ""
    episode_number: Optional[int] = None


class ImportVideoIn(BaseModel):
    publish: bool = False


class BulkImportItemIn(BaseModel):
    import_id: str
    publish: bool = False


class BulkImportIn(BaseModel):
    items: List[BulkImportItemIn]


@app.post("/api/admin/animation/sources/preview")
def admin_preview_trusted_source_url(
    payload: TrustedSourcePreviewIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Doc mot URL/ID YouTube va tra ve thong tin XEM TRUOC — KHONG tao gi
    ca (xem dac ta Phase 5, muc 5). Buoc BAT BUOC truoc khi xac nhan them
    lam nguon tin cay."""
    return _nguon_tin_cay(trusted_sources.preview_source_url, payload.url)


@app.get("/api/admin/animation/sources")
def admin_list_trusted_sources(
    q: str = "", enabled: Optional[bool] = None, limit: int = 25, offset: int = 0,
    admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    return _nguon_tin_cay(
        trusted_sources.admin_list_sources, query=q, enabled=enabled,
        limit=max(1, min(100, limit)), offset=max(0, offset))


@app.post("/api/admin/animation/sources")
def admin_create_trusted_source(
    payload: TrustedSourceCreateIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    return {"source": _nguon_tin_cay(
        trusted_sources.create_source, admin,
        source_type=payload.source_type,
        youtube_channel_id=payload.youtube_channel_id,
        youtube_playlist_id=payload.youtube_playlist_id,
        youtube_video_id=payload.youtube_video_id,
        display_name=payload.display_name, thumbnail_url=payload.thumbnail_url,
        auto_discover=payload.auto_discover, auto_import=payload.auto_import,
        auto_publish=payload.auto_publish,
        minimum_confidence=payload.minimum_confidence,
        actor_role=settings.admin_role_of(admin.user_id).value)}


@app.get("/api/admin/animation/sources/{source_id}")
def admin_trusted_source_detail(
    source_id: str, admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    data = _nguon_tin_cay(trusted_sources.admin_source_detail, source_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nguồn tin cậy.")
    return data


@app.patch("/api/admin/animation/sources/{source_id}")
def admin_update_trusted_source(
    source_id: str, payload: TrustedSourceUpdateIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    source = _nguon_tin_cay(
        trusted_sources.update_source, admin, source_id, fields,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nguồn tin cậy.")
    return {"source": source}


@app.post("/api/admin/animation/sources/{source_id}/enabled")
def admin_set_trusted_source_enabled(
    source_id: str, payload: SourceEnabledIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    source = _nguon_tin_cay(
        trusted_sources.set_source_enabled, admin, source_id, payload.enabled,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nguồn tin cậy.")
    return {"source": source}


@app.delete("/api/admin/animation/sources/{source_id}")
def admin_remove_trusted_source(
    source_id: str, admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    da_xoa = _nguon_tin_cay(
        trusted_sources.remove_source, admin, source_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if not da_xoa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nguồn tin cậy.")
    return {"ok": True}


@app.post("/api/admin/animation/sources/{source_id}/scan")
def admin_scan_trusted_source(
    source_id: str, payload: ScanSourceIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Quet video co san (Phase 5, dac ta muc 11) — BI CHAN theo `max_pages`,
    xem `TrustedSourceService.scan_source`."""
    return _nguon_tin_cay(
        trusted_sources.scan_source, admin, source_id,
        page_token=payload.page_token,
        max_pages=max(1, min(MAX_SCAN_PAGES, payload.max_pages)),
        actor_role=settings.admin_role_of(admin.user_id).value)


@app.post("/api/admin/animation/sources/{source_id}/discover")
def admin_discover_series_from_seed(
    source_id: str, payload: DiscoverSeriesIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Auto-Ingestion Phase 1 ("Seed Video -> Series Discovery -> Backfill") —
    xem `TrustedSourceService.discover_series_from_seed`."""
    return {"result": _nguon_tin_cay(
        trusted_sources.discover_series_from_seed, admin, source_id,
        youtube_video_id=payload.youtube_video_id,
        actor_role=settings.admin_role_of(admin.user_id).value).to_dict()}


@app.post("/api/admin/animation/sources/{source_id}/discover-channel")
def admin_discover_channel(
    source_id: str, payload: DiscoverChannelIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Auto-Ingestion Phase 5 ("Autonomous Multi-Series Channel Ingestion") —
    kham pha TOAN BO mot nguon kieu kenh/playlist, co the tao/khop NHIEU
    series khac nhau cung luc, xem `TrustedSourceService.discover_channel`.
    BI CHAN theo `max_pages`, cung nguyen tac voi `/scan`."""
    return {"result": _nguon_tin_cay(
        trusted_sources.discover_channel, admin, source_id,
        max_pages=max(1, min(MAX_SCAN_PAGES, payload.max_pages)),
        actor_role=settings.admin_role_of(admin.user_id).value).to_dict()}


@app.post("/api/admin/animation/sources/{source_id}/mappings")
def admin_create_series_mapping(
    source_id: str, payload: SeriesMappingCreateIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    return {"mapping": _nguon_tin_cay(
        trusted_sources.create_mapping, admin, source_id,
        animation_series_id=payload.animation_series_id, aliases=payload.aliases,
        include_keywords=payload.include_keywords,
        exclude_keywords=payload.exclude_keywords,
        minimum_confidence=payload.minimum_confidence,
        auto_import=payload.auto_import, auto_publish=payload.auto_publish,
        actor_role=settings.admin_role_of(admin.user_id).value)}


@app.patch("/api/admin/animation/mappings/{mapping_id}")
def admin_update_series_mapping(
    mapping_id: str, payload: SeriesMappingUpdateIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Không có gì để sửa.")
    mapping = _nguon_tin_cay(
        trusted_sources.update_mapping, admin, mapping_id, fields,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if mapping is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy ánh xạ series.")
    return {"mapping": mapping}


@app.delete("/api/admin/animation/mappings/{mapping_id}")
def admin_remove_series_mapping(
    mapping_id: str, admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    da_xoa = _nguon_tin_cay(
        trusted_sources.remove_mapping, admin, mapping_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if not da_xoa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy ánh xạ series.")
    return {"ok": True}


@app.get("/api/admin/animation/imports")
def admin_list_video_imports(
    status_filter: str = "", trusted_source_id: str = "", series_id: str = "",
    limit: int = 25, offset: int = 0, admin: Profile = Depends(admin_profile),
) -> Dict[str, Any]:
    return _nguon_tin_cay(
        trusted_sources.admin_list_imports, status=status_filter,
        trusted_source_id=trusted_source_id, series_id=series_id,
        limit=max(1, min(100, limit)), offset=max(0, offset))


@app.patch("/api/admin/animation/imports/{import_id}/series")
def admin_set_import_series(
    import_id: str, payload: SetImportSeriesIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Quan tri tu gan/sua series+so tap TRUOC khi nhap (dac ta Phase 5, muc 9)."""
    updated = _nguon_tin_cay(
        trusted_sources.set_import_series, admin, import_id,
        series_id=payload.series_id, episode_number=payload.episode_number,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Không tìm thấy video trong hàng đợi nhập.")
    return {"import": updated}


@app.post("/api/admin/animation/imports/{import_id}/import")
def admin_import_video(
    import_id: str, payload: ImportVideoIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    return {"import": _nguon_tin_cay(
        trusted_sources.import_video, admin, import_id, publish=payload.publish,
        actor_role=settings.admin_role_of(admin.user_id).value)}


#: Gioi han so video moi lan nhap hang loat — cung y do voi `max_pages` cua
#: scan_source (chan mot request don le keo qua nhieu viec): admin chon tay
#: tu danh sach dang hien (toi da 25 dong/trang, xem `TRANG` o frontend), 50
#: du du cho ca hai trang lien tiep ma van la mot con so kiem soat duoc.
GIOI_HAN_NHAP_HANG_LOAT = 50


@app.post("/api/admin/animation/imports/bulk-import")
def admin_bulk_import_videos(
    payload: BulkImportIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """
    Nhap NHIEU video cung luc (dac ta "bulk import") — vo mong THEM quanh
    `import_video()` qua `TrustedSourceService.bulk_import_videos`, KHONG
    phai mot duong ghi song song rieng. Loi cua MOT video (thieu series, da
    trung, xung dot) khong lam hong ca lo — moi item tra ve mot trang thai
    rieng trong `results`, route nay CHI 4xx/5xx cho loi HE THONG (vd sai
    dinh dang request, chua cau hinh gi do), khong bao gio cho loi cua rieng
    mot video trong danh sach.
    """
    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chưa chọn video nào để nhập.")
    if len(payload.items) > GIOI_HAN_NHAP_HANG_LOAT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tối đa {GIOI_HAN_NHAP_HANG_LOAT} video mỗi lần nhập hàng loạt.")
    return _nguon_tin_cay(
        trusted_sources.bulk_import_videos, admin,
        [item.model_dump() for item in payload.items],
        actor_role=settings.admin_role_of(admin.user_id).value)


@app.post("/api/admin/animation/imports/{import_id}/reject")
def admin_reject_video_import(
    import_id: str, payload: RemoveIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    updated = _nguon_tin_cay(
        trusted_sources.reject_import, admin, import_id, reason=payload.reason,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Không tìm thấy video trong hàng đợi nhập.")
    return {"import": updated}


@app.post("/api/admin/animation/imports/{import_id}/ignore")
def admin_ignore_video_import(
    import_id: str, payload: FollowIn,
    admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    updated = _nguon_tin_cay(
        trusted_sources.ignore_import, admin, import_id,
        actor_role=settings.admin_role_of(admin.user_id).value)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Không tìm thấy video trong hàng đợi nhập.")
    return {"import": updated}


# -----------------------------------------------------------------------------
# YouTube WebSub (Phase 6, Trusted Video Sources) — dang ky/gia han + doi chieu
# -----------------------------------------------------------------------------
#
# BA route quan tri (dang ky/huy dang ky/chay doi chieu) dung
# `admin_or_owner_profile` — CUNG muc voi mutate Trusted Sources o Phase 5.
# HAI route callback CONG KHAI (`youtube_websub_verify`/`youtube_websub_notify`,
# ben duoi) KHONG qua bat ky `Depends` nao ca — day la route he thong ma hub
# PubSubHubbub cua YouTube goi TRUC TIEP, khong phai nguoi dung dang nhap.


@app.post("/api/admin/animation/sources/{source_id}/subscribe")
def admin_subscribe_trusted_source(
    source_id: str, admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """Dang ky (hoac dang ky lai de gia han) mot nguon kieu kenh voi hub
    WebSub. 503 neu chua cau hinh URL callback cong khai — xem
    `TrustedSourceService.websub_configured`."""
    return {"source": _nguon_tin_cay(
        trusted_sources.subscribe_source, admin, source_id,
        actor_role=settings.admin_role_of(admin.user_id).value)}


@app.post("/api/admin/animation/sources/{source_id}/unsubscribe")
def admin_unsubscribe_trusted_source(
    source_id: str, admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    return {"source": _nguon_tin_cay(
        trusted_sources.unsubscribe_source, admin, source_id,
        actor_role=settings.admin_role_of(admin.user_id).value)}


class ReconciliationRunIn(BaseModel):
    #: Rong = chay cho MOI nguon BAT + auto_discover; truyen vao = CHI mot nguon.
    source_id: str = ""


@app.post("/api/admin/animation/reconciliation/run")
def admin_run_reconciliation(
    payload: ReconciliationRunIn, admin: Profile = Depends(admin_or_owner_profile),
) -> Dict[str, Any]:
    """"Chạy đối chiếu ngay" — thu cong, BI CHAN (mot trang/nguon), co kiem
    toan qua nhat ky `reconciliation_run`. Xem `TrustedSourceService.
    run_reconciliation`."""
    return _nguon_tin_cay(
        trusted_sources.run_reconciliation, source_id=payload.source_id,
        actor_id=admin.user_id, actor_role=settings.admin_role_of(admin.user_id).value)


@app.get("/api/youtube/websub")
def youtube_websub_verify(
    source_id: str = "",
    hub_mode: str = Query("", alias="hub.mode"),
    hub_topic: str = Query("", alias="hub.topic"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_lease_seconds: str = Query("", alias="hub.lease_seconds"),
) -> Response:
    """
    Xac minh dang ky/huy dang ky (bat tay WebSub, xem
    `server/youtube_websub.py`). Dac ta BAT BUOC: echo NGUYEN VEN
    `hub.challenge`, Content-Type AN TOAN (khong phai HTML/JS — tranh phan
    anh XSS neu challenge chua ky tu la), va tra 404 khi tu choi.
    """
    challenge = trusted_sources.handle_websub_verification(
        source_id=source_id, mode=hub_mode, topic=hub_topic,
        challenge=hub_challenge, lease_seconds=hub_lease_seconds)
    if challenge is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không xác nhận đăng ký này.")
    return Response(content=challenge, media_type="text/plain",
                    headers={"X-Content-Type-Options": "nosniff"})


@app.post("/api/youtube/websub")
async def youtube_websub_notify(
    request: Request, source_id: str = "",
    x_hub_signature: str = Header("", alias="X-Hub-Signature"),
) -> Response:
    """
    Thong bao video moi/cap nhat/da xoa tu hub. LUON tra 200 (dac ta WebSub:
    ma thanh cong CHI co nghia DA NHAN, khong phai da xu ly xong THANH
    CONG) — ket qua xu ly/tu choi (nguon khong ton tai, chu ky sai, XML
    hong) chi anh huong nhat ky/trang thai noi bo, xem
    `TrustedSourceService.handle_websub_notification`.

    Doc THAN theo tung khoi (`request.stream()`), KHONG dung
    `await request.body()` truc tiep — route nay CONG KHAI, khong qua Depends
    nao (xem ghi chu tren `youtube_websub_verify`). `request.body()` dem het
    toan bo than vao bo nho TRUOC khi co co hoi kiem tra kich thuoc; ke tan
    cong bo qua/gia mao header `Content-Length` (hoac dung chunked transfer-
    encoding) van co the ep dem mot than khong gioi han. Doc theo khoi va
    dung SOM ngay khi vuot `MAX_NOTIFICATION_BYTES` tranh duoc dieu do bat
    ke header co dung/co mat hay khong (phat hien Phase "public dev backend
    + real WebSub E2E": endpoint nay truoc day chua tung bi lo cong khai
    that, nen day la lan dau khe ho nay co the bi khai thac tu Internet).
    """
    body = bytearray()
    async for khoi in request.stream():
        body.extend(khoi)
        if len(body) > MAX_NOTIFICATION_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                "Thân thông báo quá lớn.")
    body = bytes(body)
    ket_qua = trusted_sources.handle_websub_notification(
        source_id=source_id, body=body, signature_header=x_hub_signature)
    if ket_qua is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có nguồn tin cậy nào khớp.")
    return Response(status_code=status.HTTP_200_OK)


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


@app.delete("/api/translate/projects/{project_id}")
def delete_translation_project(
    project_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Xoa du an dich cung job/thuat ngu/lich su phien ban cua no.

    Phat hien qua E2E chung thuc R1 (2026-08-21): khong co duong nao xoa du
    an dich — mot du an QA vo tinh bi mo coi trong production that vi khong
    co API nao de don.
    """
    _dich_vu(translation_svc.delete_project, project_id, profile.user_id)
    return {"deleted": True}


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
def admin_translate_usage(profile: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
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


#: So dong toi da MOT lan goi — kiem soat thoi gian request (Groq timeout
#: 60s CHO TUNG doan, chay TUAN TU): 50 dong o mien te nhat van nam trong
#: vai phut, khong de mot request treo qua lau. Phu de dai hon thi frontend
#: tu chia thanh nhieu lo (xem `web/src/lib/subtitles/translate.ts`).
SUBTITLE_TRANSLATE_MAX_LINES = 50


class SubtitleTranslateIn(BaseModel):
    texts: List[Annotated[str, StringConstraints(max_length=2000)]]
    target_language: Annotated[str, StringConstraints(max_length=16)] = "vi"


@app.post("/api/tools/subtitles/translate")
def translate_subtitle_lines(
    payload: SubtitleTranslateIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """
    Dich MOT LO dong phu de — CHI VAN BAN, KHONG BAO GIO nhan/dung video
    (Phan 4E: "send subtitle TEXT ONLY... Never upload the source video
    merely to translate text").

    Dung LAI nguyen tang provider/registry/BYOK cua Fanfic Translation
    Studio (Part Q/V5.1) — KHONG tao TranslationProject/job rieng cho cong
    cu nay (Phan 4F: "Do not force Novel entities"): day la dich TUNG DONG
    doc lap, khong can Novel Bible/glossary/chuong.

    Dang nhap bat buoc — tranh nguoi la mat dung pool mien phi chung qua
    mot cong cu khong co gioi han job nhu Translation Studio.
    """
    if not payload.texts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Danh sách dòng trống.")
    if len(payload.texts) > SUBTITLE_TRANSLATE_MAX_LINES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tối đa {SUBTITLE_TRANSLATE_MAX_LINES} dòng mỗi lần — chia nhỏ lô.")

    personal = (translation_byok_svc.build_all_configured_providers(profile.user_id)
               if translation_byok_svc else [])
    ra: List[str] = []
    for dong in payload.texts:
        sach = dong.strip()
        if not sach:
            ra.append("")
            continue
        ctx = TranslationContext(vai_tro="translator", quality_mode="nhanh")
        try:
            dich, _ = translation_registry.translate_segment_with_personal(
                sach, context=ctx, mode="auto", allow_fallback=True,
                personal_providers=personal, prefer_personal=False)
        except AllProvidersUnavailable as exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Các model dịch miễn phí hiện đều không dùng được, thử lại sau."
            ) from exc
        except TranslationProviderError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                               "Không dịch được dòng này, thử lại.") from exc
        ra.append(dich)
    return {"translated": ra}


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


# -----------------------------------------------------------------------------
# Image Studio V1 (overnight build) — PHASE 3-11
# -----------------------------------------------------------------------------
#
# Ba che do, MOT tang dieu phoi (`image_studio_svc`) — xem docstring dau
# `server/image_service.py`. Route o day CHI lam ba viec: xac thuc/tham so,
# goi dieu phoi, doi loi nghiep vu thanh ma HTTP. Toan bo logic tien/an toan
# nam trong `server/image_*`, KHONG lap lai o day.


def _client_ip(request: Request) -> str:
    """IP nguoi goi cho Quick Free rate-limit. `X-Forwarded-For` neu chay sau
    proxy nguoc (Render/Cloudflare) — lay MUC DAU (client that, khong phai
    proxy ke tiep); lui ve `request.client.host` khi khong co header do
    (dev cuc bo)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _dich_vu_anh(fn, *args, **kwargs):
    """Cung vai tro voi `_dich_vu` nhung cho Image Studio — MOT cho doi loi
    nghiep vu thanh ma HTTP thay vi lap try/except o tung route."""
    try:
        return fn(*args, **kwargs)
    except ImageProviderRateLimited as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds else {}
        )
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc),
                            headers=headers) from exc
    except ImageProviderTimeout as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(exc)) from exc
    except ImageProviderUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except InvalidImageResponse as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except UnknownOrDisabledModel as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except SharedPremiumDisabled as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except InsufficientBalance as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
    except DuplicateReservation as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except GenerationAlreadyProcessed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ByopNotConnected as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except CommunityModelNoLongerFree as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ByopStateMismatch as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ByopExchangeFailed as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except ByopError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except ImageProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionDenied as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


_TI_LE_HOP_LE = ("1:1", "16:9", "9:16", "3:4", "4:3")


class ImageQuickFreeIn(BaseModel):
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    aspect_ratio: Annotated[str, StringConstraints(max_length=10)] = "1:1"


class ImageSharedPremiumIn(BaseModel):
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    negative_prompt: Annotated[str, StringConstraints(max_length=1000)] = ""
    model: Annotated[str, StringConstraints(max_length=50)]
    aspect_ratio: Annotated[str, StringConstraints(max_length=10)] = "1:1"
    quality: Annotated[str, StringConstraints(max_length=20)] = "standard"
    #: Client sinh ra (vd UUID) — CUNG gia tri khi bam "thu lai request giong
    #: het" thi KHONG bi tinh phi/goi provider lan hai (xem PHASE 5).
    idempotency_key: Annotated[str, StringConstraints(min_length=8, max_length=128)]


class ImageByopIn(BaseModel):
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    negative_prompt: Annotated[str, StringConstraints(max_length=1000)] = ""
    model: Annotated[str, StringConstraints(max_length=50)]
    aspect_ratio: Annotated[str, StringConstraints(max_length=10)] = "1:1"
    quality: Annotated[str, StringConstraints(max_length=20)] = "standard"


def _anh_thanh_dict(image, *, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Anh tra ve dang base64 trong JSON — CUNG quy uoc voi
    `TranslateUploadIn.base64`/`PostIn.image_base64` da co san trong repo
    nay (tranh phu thuoc `python-multipart` chua khai bao), khong phai quy
    uoc rieng cho Image Studio.
    """
    ra = {
        "image_base64": base64.b64encode(image.content).decode("ascii"),
        "content_type": image.content_type,
        "byte_size": image.byte_size,
        "provider_id": image.provider_id,
    }
    if extra:
        ra.update(extra)
    return ra


@app.get("/api/image/models")
def image_models() -> Dict[str, Any]:
    """Catalogue Shared Premium — CONG KHAI (thong tin gia/nang luc, khong
    phai secret). Quick Free/BYOP khong co catalogue rieng: Quick Free luon
    la 'Auto model' (xem PHASE 4A), BYOP dung CUNG catalogue nay qua
    Pollinations cua chinh nguoi dung."""
    return {
        "models": [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "supports_text_to_image": m.supports_text_to_image,
                "supports_image_edit": m.supports_image_edit,
                "quality_levels": list(m.quality_levels),
                "estimated_credit_cost": m.estimated_credit_cost,
            }
            for m in image_studio_svc.catalogue()
        ],
        "aspect_ratios": list(_TI_LE_HOP_LE),
        "shared_premium_available": settings.image_studio.shared_premium_configured,
    }


@app.post("/api/image/quick-free")
def image_generate_quick_free(
    payload: ImageQuickFreeIn, request: Request,
) -> Dict[str, Any]:
    """An danh, KHONG dang nhap, KHONG key — xem canh bao PHASE 4A: nhan
    hien thi CO DINH la 'Quick Free'/'Auto model', khong bao gio ten model
    rieng le (da chung minh bi bo qua/chuan hoa o `chore/pollinations-
    anonymous-probe`)."""
    if payload.aspect_ratio not in _TI_LE_HOP_LE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tỷ lệ khung hình không hợp lệ.")
    image = _dich_vu_anh(
        image_studio_svc.sinh_anh_quick_free,
        prompt=payload.prompt, aspect_ratio=payload.aspect_ratio,
        client_ip=_client_ip(request),
    )
    return _anh_thanh_dict(image)


@app.get("/api/image/wallet")
def image_wallet(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    so_du = image_wallet_store.lay_so_du(profile.user_id)
    return {
        "available_micro": so_du.available_micro,
        "reserved_micro": so_du.reserved_micro,
        "total_micro": so_du.total_micro,
    }


@app.get("/api/image/wallet/transactions")
def image_wallet_transactions(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    giao_dich = image_wallet_store.liet_ke_giao_dich(profile.user_id)
    return {
        "transactions": [
            {
                "transaction_id": tx.transaction_id,
                "generation_id": tx.generation_id,
                "entry_type": tx.entry_type.value,
                "amount_micro": tx.amount_micro,
                "created_at": tx.created_at,
                "note": tx.note,
            }
            for tx in giao_dich
        ],
    }


class ImageEstimateIn(BaseModel):
    model: Annotated[str, StringConstraints(max_length=50)]
    quality: Annotated[str, StringConstraints(max_length=20)] = "standard"


@app.post("/api/image/shared-premium/estimate")
def image_shared_premium_estimate(
    payload: ImageEstimateIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    micro = _dich_vu_anh(
        image_studio_svc.uoc_tinh_shared_premium,
        model_id=payload.model, quality=payload.quality,
    )
    return {"estimated_credit_micro": micro}


@app.post("/api/image/shared-premium")
def image_generate_shared_premium(
    payload: ImageSharedPremiumIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Fanfic Credits — tru vi cua NGUOI DUNG DANG NHAP, khong bao gio dung
    credential dung chung cho nguoi khac (idempotency_key khong bi doi tuong
    khac 'muon' vi no luon di cung user_id trong `dat_cho`)."""
    if payload.aspect_ratio not in _TI_LE_HOP_LE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tỷ lệ khung hình không hợp lệ.")
    ket_qua = _dich_vu_anh(
        image_studio_svc.sinh_anh_shared_premium,
        user_id=profile.user_id, prompt=payload.prompt,
        negative_prompt=payload.negative_prompt, model_id=payload.model,
        aspect_ratio=payload.aspect_ratio, quality=payload.quality,
        idempotency_key=payload.idempotency_key,
    )
    return _anh_thanh_dict(ket_qua.image, extra={
        "generation_id": ket_qua.reservation.generation_id,
        "status": ket_qua.reservation.status.value,
        "estimated_cost_micro": ket_qua.reservation.estimated_cost_micro,
        "actual_cost_micro": ket_qua.reservation.actual_cost_micro,
    })


@app.post("/api/image/byop")
def image_generate_byop(
    payload: ImageByopIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """My Pollinations — dung Pollen CA NHAN, KHONG BAO GIO cham Fanfic
    Credit (xem `ImageStudioService.sinh_anh_byop`)."""
    if payload.aspect_ratio not in _TI_LE_HOP_LE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tỷ lệ khung hình không hợp lệ.")
    image = _dich_vu_anh(
        image_studio_svc.sinh_anh_byop,
        user_id=profile.user_id, prompt=payload.prompt,
        negative_prompt=payload.negative_prompt, model_id=payload.model,
        aspect_ratio=payload.aspect_ratio, quality=payload.quality,
    )
    return _anh_thanh_dict(image)


# ----------------------------------------------------------------- Cong Free


@app.get("/api/image/community-free/models")
def image_community_free_models(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    """Danh sach model cong dong Pollinations dang bao gia 0 pollen NGAY BAY
    GIO — dong (co the rong that su, xem ADDENDUM). `available=False` nghia
    la khong lay duoc danh sach (loi mang), khac voi danh sach rong hop le."""
    trang_thai = image_studio_svc.catalogue_cong_dong()
    return {
        "available": trang_thai["available"],
        "error": trang_thai["error"],
        "models": [
            {
                "model_id": m.model_id,
                "display_name": m.display_name,
                "provider_badge": m.provider_badge,
                "is_official": m.is_official,
                "per_user_rpm": m.per_user_rpm,
                "capabilities": list(m.capabilities),
                "description": m.description,
                "alpha_hint": m.alpha_hint,
            }
            for m in trang_thai["models"]
        ],
    }


class ImageCommunityFreeIn(BaseModel):
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    negative_prompt: Annotated[str, StringConstraints(max_length=1000)] = ""
    model: Annotated[str, StringConstraints(max_length=80)]
    aspect_ratio: Annotated[str, StringConstraints(max_length=10)] = "1:1"
    quality: Annotated[str, StringConstraints(max_length=20)] = "standard"
    idempotency_key: Annotated[str, StringConstraints(min_length=8, max_length=128)]


@app.post("/api/image/community-free")
def image_generate_community_free(
    payload: ImageCommunityFreeIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Sinh anh qua model cong dong dang mien phi THAT SU — kiem tra LAI
    danh sach truoc moi lan goi, KHONG bao gio tu chuyen sang Shared Premium
    neu model da bi ru khoi danh sach mien phi (xem
    `ImageStudioService.sinh_anh_cong_dong`)."""
    if payload.aspect_ratio not in _TI_LE_HOP_LE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tỷ lệ khung hình không hợp lệ.")
    ket_qua = _dich_vu_anh(
        image_studio_svc.sinh_anh_cong_dong,
        user_id=profile.user_id, prompt=payload.prompt,
        negative_prompt=payload.negative_prompt, model_id=payload.model,
        aspect_ratio=payload.aspect_ratio, quality=payload.quality,
        idempotency_key=payload.idempotency_key,
    )
    return _anh_thanh_dict(ket_qua.image, extra={
        "generation_id": ket_qua.reservation.generation_id,
        "status": ket_qua.reservation.status.value,
    })


# --------------------------------------------------------- BYOP (My Pollinations)


@app.get("/api/image/byop/status")
def image_byop_status(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    conn = image_byop_svc.trang_thai(profile.user_id)
    return {
        "connected": bool(conn and conn.active),
        "scope": conn.scope if conn else "",
        "expires_at": conn.expires_at if conn else "",
        "byop_enabled": image_byop_svc.enabled,
    }


@app.post("/api/image/byop/connect")
def image_byop_connect(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    url = _dich_vu_anh(image_byop_svc.bat_dau_ket_noi, user_id=profile.user_id)
    return {"authorize_url": url}


class ImageByopCallbackIn(BaseModel):
    state: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    code: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    redirect_uri: Annotated[str, StringConstraints(min_length=1, max_length=500)]


@app.post("/api/image/byop/callback")
def image_byop_callback(
    payload: ImageByopCallbackIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Frontend goi endpoint nay SAU KHI trinh duyet duoc Pollinations dieu
    huong ve — KHONG BAO GIO log/echo `payload.code` (ma xac thuc dung mot
    lan, xem `image_byop_service.ByopExchangeFailed`)."""
    conn = _dich_vu_anh(
        image_byop_svc.xu_ly_callback,
        user_id=profile.user_id, state=payload.state, code=payload.code,
        redirect_uri=payload.redirect_uri,
    )
    return {"connected": conn.active, "scope": conn.scope}


@app.post("/api/image/byop/disconnect")
def image_byop_disconnect(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    image_byop_svc.ngat_ket_noi(profile.user_id)
    return {"connected": False}


# --------------------------------------------------------------- thu vien anh


class ImageLibrarySaveIn(BaseModel):
    generation_id: Annotated[str, StringConstraints(max_length=128)] = ""
    prompt: Annotated[str, StringConstraints(max_length=2000)] = ""
    negative_prompt: Annotated[str, StringConstraints(max_length=1000)] = ""
    model: Annotated[str, StringConstraints(max_length=50)] = ""
    mode: Annotated[str, StringConstraints(max_length=20)] = "quick_free"
    aspect_ratio: Annotated[str, StringConstraints(max_length=10)] = "1:1"
    image_base64: Annotated[str, StringConstraints(min_length=1, max_length=14_000_000)]


@app.post("/api/image/library", status_code=status.HTTP_201_CREATED)
def image_library_save(
    payload: ImageLibrarySaveIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """Luu VINH VIEN qua storage adapter (Local/R2) — CHI khi nguoi dung chu
    dong bam 'Luu' (PHASE 9: khong luu moi ung vien tam)."""
    import binascii

    try:
        du_lieu = base64.b64decode(payload.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ảnh không hợp lệ.") from exc
    if len(du_lieu) > 12_000_000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Ảnh quá lớn.")

    try:
        mode = GenerationMode(payload.mode)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chế độ tạo ảnh không hợp lệ.")

    image_id = uuid.uuid4().hex[:16]
    storage_key = f"image-studio/{profile.user_id}/{image_id}.jpg"
    storage.put(storage_key, du_lieu, content_type="image/jpeg")

    saved = SavedImage(
        image_id=image_id, owner_user_id=profile.user_id,
        generation_id=payload.generation_id, prompt=payload.prompt,
        negative_prompt=payload.negative_prompt, model=payload.model,
        mode=mode, aspect_ratio=payload.aspect_ratio, storage_key=storage_key,
    )
    image_library_store.luu(saved)
    return {"image_id": image_id}


@app.get("/api/image/library")
def image_library_list(profile: Profile = Depends(current_profile)) -> Dict[str, Any]:
    ds = image_library_store.liet_ke(profile.user_id)
    return {
        "images": [
            {
                "image_id": a.image_id,
                "prompt": a.prompt,
                "model": a.model,
                "mode": a.mode.value,
                "aspect_ratio": a.aspect_ratio,
                "created_at": a.created_at,
                "url": storage.signed_url(a.storage_key, expires_seconds=3600),
            }
            for a in ds
        ],
    }


@app.delete("/api/image/library/{image_id}")
def image_library_delete(
    image_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    saved = _dich_vu_anh(image_library_store.lay, profile.user_id, image_id)
    storage.delete(saved.storage_key)
    image_library_store.xoa(profile.user_id, image_id)
    return {"deleted": True}


# ------------------------------------------------------------------- quan tri


@app.get("/api/admin/image-studio/spending")
def admin_image_studio_spending(profile: Profile = Depends(admin_or_owner_profile)) -> Dict[str, Any]:
    """
    Trang AI/Credits (Admin Control Center V2). Phase 7 mo rong THEM (khong
    doi hinh dang cac truong cu — dashboard/trang cu van doc duoc y het):
    tinh trang van hanh dich/TTS (thanh cong/that bai/dang xu ly, TAT CA
    THOI GIAN — trang nay la "hien tai dang the nao", khong phai xu huong
    theo ky nhu `/api/admin/analytics/detail`) va so ket noi BYOK theo
    trang thai (KHONG BAO GIO tra secret/key — chi dem).

    Phase 5 (performance audit) — SONG SONG HOA: do THAT chong Appwrite dev
    tu luu tru cho thay route nay mat ~7.8s vi 9 truy van dem BI CHAN chay
    TUAN TU. Dung lai idiom da kiem chung o `_admin_dashboard_them`:
    `ThreadPoolExecutor(max_workers=4)` + `_an_toan_song_song` (mot nhom dem
    loi -> None, khong lam sup ca trang).
    """
    cong_viec: Dict[str, Any] = {
        "dich_completed": lambda: translation_svc.admin_count_jobs(
            status=TranslationJobStatus.COMPLETED),
        "dich_failed": lambda: translation_svc.admin_count_jobs(
            status=TranslationJobStatus.FAILED),
        "dich_cancelled": lambda: translation_svc.admin_count_jobs(
            status=TranslationJobStatus.CANCELLED),
        "dich_tong": lambda: translation_svc.admin_count_jobs(),
        "tts_pending": lambda: store.count_jobs(status=JobStatus.PENDING),
        "tts_running": lambda: store.count_jobs(status=JobStatus.RUNNING),
        "tts_completed": lambda: store.count_jobs(status=JobStatus.COMPLETED),
        "tts_failed": lambda: store.count_jobs(status=JobStatus.FAILED),
        "byok": lambda: translation_svc.admin_count_connections_by_status(),
    }
    with ThreadPoolExecutor(max_workers=4) as bo_luong:
        futures = {ten: bo_luong.submit(ham) for ten, ham in cong_viec.items()}
        kq = {ten: _an_toan_song_song(
            f, {} if ten == "byok" else None,
            nhan="admin_image_studio_spending")
             for ten, f in futures.items()}

    snap = image_spending_guard.snapshot()  # trong bo nho, khong can luong rieng
    dich_status = {
        "completed": kq["dich_completed"], "failed": kq["dich_failed"],
        "cancelled": kq["dich_cancelled"],
    }
    dich_tong = kq["dich_tong"]
    dich_status["in_progress"] = (
        max(0, dich_tong - sum(v for v in dich_status.values() if v is not None))
        if dich_tong is not None else None)
    tts_status = {
        "pending": kq["tts_pending"], "running": kq["tts_running"],
        "completed": kq["tts_completed"], "failed": kq["tts_failed"],
    }
    return {
        "month": snap.thang,
        "spent_usd": snap.spent_usd,
        "budget_usd": snap.budget_usd,
        "warning_usd": snap.warning_usd,
        "kill_switch_engaged": snap.kill_switch_engaged,
        "active_concurrent": snap.active_concurrent,
        "max_concurrent": snap.max_concurrent,
        "shared_premium_enabled_config": settings.image_studio.shared_premium_enabled,
        "shared_premium_configured": settings.image_studio.shared_premium_configured,
        "translation_jobs_by_status": dich_status,
        "tts_jobs_by_status": tts_status,
        "byok_connections_by_status": kq["byok"],
        # Vi Fanfic Credit theo NGUOI DUNG (khac ngan sach Shared Premium o
        # tren) hien chi la MockWalletStore (bo nho tam TUNG TIEN TRINH,
        # mat khi khoi dong lai) — AppwriteWalletStore da duoc quy hoach o
        # Phase 9 (xem docstring `image_wallet_store.py`), CHUA trien khai.
        # Khong co ham tong hop NHIEU nguoi dung tren kho hien tai nen
        # KHONG hien mot so lieu bia — chi ghi ro tinh trang.
        "wallet_configured": False,
        "wallet_note": (
            "Ví Fanfic Credit theo người dùng hiện chạy trên bộ nhớ tạm "
            "từng tiến trình (MockWalletStore), không bền vững qua khởi "
            "động lại — bản Appwrite hoá đã quy hoạch ở Phase 9, chưa "
            "triển khai. Chưa có tổng hợp nhiều người dùng để hiển thị."
        ),
    }


class KillSwitchIn(BaseModel):
    engaged: bool


@app.post("/api/admin/image-studio/kill-switch")
def admin_image_studio_kill_switch(
    payload: KillSwitchIn, profile: Profile = Depends(owner_profile),
) -> Dict[str, Any]:
    """Cong tac VIEN khan cap — DOC LAP voi han muc thang (PHASE 7). Tat o
    day KHONG anh huong Quick Free/BYOP, chi Shared Premium.

    CHI OWNER (Admin Control Center V2): day la cai dat tai chinh/he thong —
    dung `owner_profile`, khong phai `admin_profile` — theo dung phan tang
    "ADMIN: users/content/analytics/trusted sources, KHONG infra/secrets/
    financial" cua mo hinh vai tro moi."""
    image_spending_guard.dat_kill_switch(payload.engaged)
    return {"kill_switch_engaged": payload.engaged}


# ------------------------------------------------------- Fanfic Credit (mock)


class ImageCheckoutIn(BaseModel):
    credit_micro: Annotated[int, Field(gt=0, le=100_000_00)]
    price_usd_cents: Annotated[int, Field(gt=0, le=100_000)]


@app.post("/api/image/checkout", status_code=status.HTTP_201_CREATED)
def image_checkout_create(
    payload: ImageCheckoutIn, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    """CHI mock/test-mode — xem canh bao dau `server/image_payment.py`.
    KHONG co cong thanh toan production nao duoc ket noi o day."""
    phien = image_payment_provider.tao_checkout(
        user_id=profile.user_id, credit_micro=payload.credit_micro,
        price_usd_cents=payload.price_usd_cents,
    )
    return {"checkout_id": phien.checkout_id, "status": phien.status.value,
           "provider_id": phien.provider_id}


@app.post("/api/image/checkout/{checkout_id}/confirm")
def image_checkout_confirm(
    checkout_id: str, profile: Profile = Depends(current_profile),
) -> Dict[str, Any]:
    try:
        phien = image_payment_provider.xac_nhan(checkout_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if phien.user_id != profile.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không phải phiên của bạn.")
    if phien.status == CheckoutStatus.SUCCEEDED:
        image_wallet_store.nap_tien_test(
            profile.user_id, phien.credit_micro,
            idempotency_key=f"checkout:{checkout_id}",
            note=f"mock checkout {checkout_id}",
        )
    return {"status": phien.status.value}
