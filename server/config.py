"""
Cau hinh backend web.

NGUYEN TAC BAO MAT: moi bi mat (Appwrite API key, R2 access key) CHI song o
backend, doc tu bien moi truong. Khong hard-code endpoint/project id, va
tuyet doi khong gui bi mat nao xuong trinh duyet.

Thieu credential KHONG lam backend chet: he thong tu lui ve adapter mock de
lap trinh duoc ngay tu dau.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

#: Thu muc du lieu runtime cua backend (audio tam, kho file mock).
#: Nam trong server/var/ va da duoc .gitignore chan.
SERVER_ROOT = Path(__file__).resolve().parent
DEFAULT_VAR_DIR = SERVER_ROOT / "var"

#: File cau hinh cuc bo cua backend. Duong dan tinh theo VI TRI MODULE NAY,
#: khong theo thu muc lam viec - chay tu repo root hay tu bat cu dau cung nap
#: dung mot file. File KHONG duoc commit (.gitignore da chan).
DEFAULT_ENV_FILE = SERVER_ROOT / ".env"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def env_file_path() -> Optional[Path]:
    """
    File `.env` se duoc nap.

    Mac dinh la `server/.env`. Bien `FAS_ENV_FILE` cho phep tro sang file khac
    - bo test dung de tach khoi `server/.env` that tren may lap trinh vien.
    Dat `FAS_ENV_FILE` thanh chuoi rong = khong nap file nao.
    """
    raw = os.environ.get("FAS_ENV_FILE")
    if raw is None:
        return DEFAULT_ENV_FILE
    raw = raw.strip()
    return Path(raw) if raw else None


def load_env_file() -> Optional[Path]:
    """
    Nap file `.env` vao `os.environ`. Tra ve file da nap, hoac None.

    THU TU UU TIEN: bien da co trong process environment LUON THANG file
    (`override=False`). Nho vay bien that do CI / production / shell tiem vao
    khong bao gio bi mot file `.env` cu ky ghi de.

    Khong co file KHONG phai loi: che do mock/local van chay binh thuong.

    Ham nay khong lam thay doi nguyen tac fail-fast. No chi dua gia tri TOI
    duoc `Settings.validate()`; viec thieu/sai cau hinh van dung ngay o do.
    """
    path = env_file_path()
    if path is None or not path.is_file():
        return None
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=path, override=False)
    return path


class ConfigError(RuntimeError):
    """Cau hinh sai hoac thieu - dung ngay thay vi chay o che do khong mong muon."""


def _env_bool(name: str, default: bool) -> bool:
    """
    Doc bien moi truong dang co bat/tat.

    Gia tri KHONG hieu duoc -> ConfigError, khong am tham lay mac dinh. Dat
    `FAS_INLINE_WORKER=flase` (sai chinh ta) ma he thong lang le chay o che do
    inline la dung cai bay phai tranh.
    """
    raw = _env(name, "").lower()
    if raw == "":
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(
        f"{name} phải là true/false (hoặc 1/0, yes/no, on/off), "
        f"nhận được {raw!r}."
    )


def _env_list(name: str, default: str) -> List[str]:
    raw = _env(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class AppwriteSettings:
    """Cau hinh Appwrite. Thieu bat ky truong nao thi coi nhu chua cau hinh."""

    endpoint: str = ""
    project_id: str = ""
    api_key: str = ""
    database_id: str = ""
    #: Khoa RIENG cho viec quan schema (`APPWRITE_SCHEMA_API_KEY`), tuy chon.
    #:
    #: VI SAO TACH: khoa runtime cua backend chi can quyen DOCUMENTS — cap them
    #: `collections.write` cho no la trao quyen sua schema cho moi tien trinh
    #: dang cam khoa do (Render, worker). Migration la viec lam TU MAY VAN
    #: HANH, thua thot, co nguoi ngoi canh — nen no cam mot khoa rieng, va
    #: khoa do khong bao gio len Render.
    #:
    #: KHONG bao gio xuat hien trong `describe()`, health, log hay loi. Chi
    #: `scripts/setup_appwrite.py` doc no.
    schema_api_key: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.project_id and self.api_key and self.database_id)

    @property
    def api_base(self) -> str:
        """
        Goc API, KHONG kem `/v1`.

        Appwrite cong bo endpoint da kem san `/v1` (vi du
        `https://sgp.cloud.appwrite.io/v1`), con moi duong dan trong code deu
        bat dau bang `/v1/`. Ghep thang se thanh `/v1/v1/...` va Appwrite tra
        ve trang 404 HTML - dung nhu loi da gap khi chay that.

        Chuan hoa o DUNG MOT CHO va chap nhan ca hai dang endpoint, co `/v1`
        hay khong deu ra cung ket qua.
        """
        base = (self.endpoint or "").strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return base


@dataclass(frozen=True)
class R2Settings:
    """Cau hinh Cloudflare R2 (API tuong thich S3)."""

    account_id: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    bucket: str = ""

    @property
    def configured(self) -> bool:
        return bool(
            self.account_id and self.access_key_id and self.secret_access_key and self.bucket
        )

    @property
    def endpoint_url(self) -> str:
        if not self.account_id:
            return ""
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


#: Che do du lieu/luu tru. Tuong minh de khong bao gio "vo tinh" chay mock.
DATA_BACKENDS = ("mock", "appwrite")
STORAGE_BACKENDS = ("local", "r2")


@dataclass(frozen=True)
class ImageStudioSettings:
    """Cau hinh Image Studio V1 (overnight build) — PHASE 7.

    `POLLINATIONS_API_KEY` la khoa SERVER-SIDE cho Shared Premium — KHONG
    BAO GIO gui xuong trinh duyet, khong bao gio xuat hien trong
    `describe()`. `POLLINATIONS_CLIENT_ID` (dang `pk_...`) NGUOC LAI la
    publishable — an toan de lo, dung cho luong BYOP OAuth.
    """

    #: Cong tac TONG cho Shared Premium — Quick Free/BYOP KHONG bi anh huong.
    shared_premium_enabled: bool = False
    monthly_budget_usd: float = 20.0
    warning_budget_usd: float = 15.0
    max_cost_per_request_usd: float = 0.10
    max_concurrent_shared_generations: int = 3
    markup_multiplier: float = 1.0
    disabled_models: Tuple[str, ...] = ()

    pollinations_api_key: str = ""
    pollinations_client_id: str = ""
    byop_master_key: str = ""
    byop_redirect_uri: str = ""

    @property
    def shared_premium_configured(self) -> bool:
        return self.shared_premium_enabled and bool(self.pollinations_api_key)

    @property
    def byop_configured(self) -> bool:
        return bool(
            self.pollinations_client_id and self.byop_master_key and self.byop_redirect_uri
        )

    def describe(self) -> dict:
        """KHONG BAO GIO chua `pollinations_api_key`/`byop_master_key` —
        chi co/khong co, giong `AppwriteSettings.configured` o tren."""
        return {
            "shared_premium_enabled": self.shared_premium_enabled,
            "shared_premium_configured": self.shared_premium_configured,
            "byop_configured": self.byop_configured,
            "monthly_budget_usd": self.monthly_budget_usd,
            "warning_budget_usd": self.warning_budget_usd,
            "max_cost_per_request_usd": self.max_cost_per_request_usd,
            "max_concurrent_shared_generations": self.max_concurrent_shared_generations,
            "disabled_models": list(self.disabled_models),
        }


@dataclass(frozen=True)
class Settings:
    """Toan bo cau hinh backend."""

    environment: str = "development"
    #: "mock" (mac dinh) hoac "appwrite"
    data_backend: str = "mock"
    #: "local" (mac dinh) hoac "r2"
    storage_backend: str = "local"
    cors_origins: List[str] = field(default_factory=list)

    #: Co bat/tat dang nhap bang Facebook. Doc tu `FAS_FACEBOOK_LOGIN`.
    #:
    #: MAC DINH TAT. Toan bo phan hien thuc Facebook VAN CON — adapter, route,
    #: cau hinh Appwrite, credential o Meta — chi la khong chao ban ra ngoai.
    #: Bat lai la doi mot bien moi truong, khong phai viet lai ma nguon.
    #:
    #: Tat o day cung dong luon `/api/auth/oauth/facebook`. Chi an cai nut la
    #: chua du: duong dan do van goi duoc bang tay, va mot duong dang nhap
    #: "khong ai thay" thi cung khong ai theo doi khi no hong.
    facebook_login_enabled: bool = False

    #: Co bat CONG CHAN XUAT BAN theo trang thai tac gia. Doc tu `FAS_AUTHOR_GATE`.
    #:
    #: MAC DINH TAT, va day khong phai su rut re — day la thu tu trien khai bat
    #: buoc. Moi ho so dang ton tai deu co `author_status = "none"`, ke ca nhung
    #: nguoi da xuat ban muoi truyen. Bat cong nay TRUOC khi chay migration
    #: grandfather la khoa toan bo tac gia hien co ra khoi chinh cong viec cua ho,
    #: va no am tham: ho bam "Xuat ban" va nhan mot loi 403.
    #:
    #: Thu tu dung:
    #:   1. trien khai ma nguon nay (cong TAT — khong ai thay gi doi)
    #:   2. chay `scripts.grandfather_authors --apply`
    #:   3. doi soat, roi moi dat `FAS_AUTHOR_GATE=1`
    #:
    #: Xem `docs/AUTHOR_RANK.md` muc "Ke hoach migration".
    author_gate_enabled: bool = False

    #: Cac `user_id` duoc quyen QUAN TRI. Doc tu `FAS_ADMIN_USER_IDS`, ngan cach
    #: bang dau phay. MAC DINH RONG — khong ai la quan tri.
    #:
    #: VI SAO O BIEN MOI TRUONG chu khong phai mot cot trong bang `profiles`:
    #:
    #:   1. Khong the LEO THANG qua ung dung. Moi duong ghi cua he thong deu di
    #:      qua Appwrite; neu quyen quan tri la mot truong du lieu thi bat ky lo
    #:      hong ghi nao — mot route quen kiem, mot quyen document dat sai — deu
    #:      tro thanh mot duong tu phong minh lam quan tri. Mot bien moi truong
    #:      thi khong co API nao cham toi duoc.
    #:   2. KHONG can migration. Bat quyen quan tri khong doi mot dong du lieu
    #:      nao, va tat no cung vay.
    #:   3. Doi danh sach la mot thao tac VAN HANH co chu y: sua bien roi khoi
    #:      dong lai, co dau vet trong lich su cau hinh.
    #:
    #: Danh doi: doi quan tri phai khoi dong lai tien trinh. Voi mot he thong co
    #: mot hoac hai quan tri thi do la cai gia dung.
    #:
    #: Xem `docs/ADMIN.md` de biet cach tao quan tri dau tien cho production.
    admin_user_ids: tuple = ()

    #: Muc QUAN TRI CAO NHAT (Admin Control Center V2) — toan quyen, bao gom
    #: ca cai dat ha tang/bi mat/tai chinh ma `admin_user_ids` (muc ADMIN)
    #: KHONG duoc chieu toi. Doc tu `FAS_OWNER_USER_IDS`, CUNG triet ly voi
    #: `admin_user_ids`: bien moi truong, khong phai cot du lieu. Xem
    #: `admin_role_of`.
    owner_user_ids: tuple = ()

    #: Muc quan tri HEP NHAT — chi xem/xu ly bao cao va kiem duyet noi dung
    #: (go xuat ban, xoa binh luan, treo user vi ly do kiem duyet). KHONG co
    #: quyen quan ly vai tro, nguon tin cay YouTube, hay cai dat he
    #: thong/tai chinh. Doc tu `FAS_MODERATOR_USER_IDS`.
    moderator_user_ids: tuple = ()

    #: Han muc chong spam cua tang xa hoi, GHI DE len mac dinh trong
    #: `server/social.py`. Doc tu `FAS_SOCIAL_LIMITS` dang
    #: `post:10/60,comment:40/60` (so lan / so phut).
    #:
    #: VI SAO CO THE CAU HINH: nguong dung o staging va nguong dung o that khong
    #: giong nhau. Mot phien kiem thu tu dong tao ba muoi bai trong hai phut se
    #: cham tran ngay, va luc do lua chon con lai la sua ma nguon roi trien khai
    #: lai — giua mot phien kiem thu. Mac dinh van la con so an toan; bien nay
    #: chi de NOI LONG co y thuc o mot moi truong cu the.
    social_limits: dict = field(default_factory=dict)

    #: Goc cua giao dien web. Doc tu `FAS_WEB_BASE_URL`.
    #:
    #: Backend can biet cho nay de dung URL callback cho OAuth: Appwrite se
    #: DIEU HUONG TRINH DUYET toi do sau khi Google/Facebook xac thuc xong.
    #: Khong the suy tu `Origin` cua request: buoc bat dau OAuth la mot lan
    #: dieu huong cua trinh duyet, khong phai `fetch`, nen khong co header
    #: `Origin` dang tin.
    #:
    #: Mac dinh la dev server; production PHAI dat tuong minh.
    web_base_url: str = "http://localhost:3000"

    var_dir: Path = DEFAULT_VAR_DIR
    appwrite: AppwriteSettings = field(default_factory=AppwriteSettings)
    r2: R2Settings = field(default_factory=R2Settings)
    image_studio: ImageStudioSettings = field(default_factory=ImageStudioSettings)

    #: KHONG con la cong chan cho giong cuc bo — xem `local_voices` ngay duoi.
    #:
    #: Giu lai vi `/api/health` van bao ra no va vi no mo ta dung mot su that ve
    #: moi truong. Nhung mot co BAT-TAT-TAT-CA la dung cai co the vo tinh mo mot
    #: giong chua ai kiem tra: doi mot bien moi truong la ca ba giong Piper
    #: built-in cung hien ra, ke ca hai giong khong co model. Quyet dinh giong
    #: nao duoc phuc vu phai la mot DANH SACH, khong phai mot boolean.
    allow_unverified_local_voices: bool = True

    #: Danh sach TRANG voice_id cuc bo duoc phuc vu. Mac dinh dung mot giong.
    #:
    #: Doc tu `FAS_LOCAL_VOICES` (ngan cach bang dau phay). `server/tts_bridge.py`
    #: con giao them mot vong nua: id nao khong thuoc bo NghiTTS trong catalog
    #: thi bi bo qua, nen mot lan go nham khong bien thanh mot giong la duoc
    #: cong bo.
    #:
    #: `piper:ngochuyen` la mac dinh vi no la giong DUY NHAT da probe that tren
    #: may nay: nap duoc model, sinh MP3 22050 Hz doc duoc, co tieng noi that.
    #: Hai giong NghiTTS con lai chua co model nen khong duoc quang ba — quang
    #: ba mot giong khong worker nao chay duoc chi tao ra job nam mai.
    local_voices: Tuple[str, ...] = ("piper:ngochuyen",)

    #: Ngon ngu duoc phuc vu tren WEB. Doc tu `FAS_PUBLIC_VOICE_LANGUAGES`.
    #:
    #: So khop theo TIEN TO ma ngon ngu, nen "vi" bat duoc ca "vi-VN".
    #:
    #: Day la pham vi cua RIENG web. Registry van giu du 452 giong moi thu
    #: tieng — desktop app va ma cu van dung chung registry do, va xoa giong
    #: nuoc ngoai khoi registry la pha ho. Mo lai them ngon ngu sau nay chi la
    #: doi mot bien moi truong, khong phai sua ma nguon.
    public_voice_languages: Tuple[str, ...] = ("vi",)

    #: Tien trinh web co tu chay job TTS trong thread nen hay khong.
    #:
    #: `True` (mac dinh) — hanh vi cu, tien va cho may lap trinh vien: mot tien
    #: trinh lam ca hai viec.
    #:
    #: `False` — web CHI phuc vu request. Job nam lai `pending` trong kho cho
    #: `server/worker.py` nhan. Bat buoc dung o staging/production: restart web
    #: khong duoc giet job dang chay, va mot request handler khong phai cho o
    #: chay lau.
    #:
    #: CANH BAO VAN HANH: dat `False` ma khong chay worker nao thi job se nam
    #: `pending` mai. `/api/health` bao ra `inline_worker` de thay ngay.
    inline_worker: bool = True

    #: Cho phep `inline_worker` o moi truong that. Chi dat khi CO Y — xem
    #: `deploy/RUNBOOK.md` muc "Rollback ve che do inline (khan cap)".
    allow_inline_worker_in_real_env: bool = False

    #: Nhu `inline_worker` o tren nhung cho subsystem DICH (V5) — TACH RIENG
    #: co tinh, khong dung chung mot co voi TTS: hai duong ong hoan toan doc
    #: lap (bang rieng, worker rieng — `server/translation_worker.py`), nen
    #: mot noi co the tat inline ma khong anh huong noi kia (vi du: tat
    #: inline cho dich [do tre mang cua LLM that co the vuot timeout HTTP]
    #: nhung van de TTS chay inline vi audio tong hop nhanh hon nhieu).
    translation_inline_worker: bool = True

    #: Da nap duoc file `.env` hay chua. Bao ra o `/api/health` de nguoi van
    #: hanh biet ngay file cau hinh co thuc su co tac dung khong - chinh la
    #: cai bay da tung lam ca buoi kiem chung chay tren mock.
    env_file_loaded: bool = False

    #: Cau hinh provider dich V5 (Novel Translation Studio) — endpoint tuong
    #: thich OpenAI chat completions (KHONG phai import goi `docutranslate`
    #: — xem ghi chu kien truc trong `translation_providers.py`). Ba truong
    #: nay TRUOC DAY chi ton tai trong docstring cua `build_provider`, chua
    #: bao gio thuc su duoc doc tu `.env` — nen mot key that duoc dien vao
    #: van im lang khong co tac dung gi (`TranslationService` mac dinh goi
    #: `build_provider(None)`, luon ra mock). Rong = chua cau hinh, van chay
    #: duoc tren mock — dung y voi moi truong dev/test chua co key that.
    translation_base_url: str = ""
    translation_api_key: str = ""
    translation_model: str = ""

    #: YouTube Data API v3 (Phase 5, Trusted Video Sources) — RONG = chua
    #: cau hinh, cac route/service lien quan phai bao trang thai "chua cau
    #: hinh" ro rang (xem `server/youtube_client.py::YouTubeConfigError`),
    #: KHONG bao gio am tham lui ve mock hay gia lap ket qua.
    youtube_api_key: str = ""

    #: Goc URL cong khai (vd "https://api.fanfic.world") de dang ky WebSub
    #: voi hub PubSubHubbub cua YouTube (Phase 6) — RONG trong dev cuc bo
    #: (YouTube khong goi toi localhost duoc), cac route/nut lien quan phai
    #: bao "chua cau hinh" ro rang (xem
    #: `TrustedSourceService.websub_configured`), KHONG bao gio dang ky voi
    #: mot URL noi bo/khong that.
    youtube_websub_callback_base_url: str = ""

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in ("development", "dev", "local")

    @property
    def storage_mode(self) -> str:
        return self.storage_backend

    @property
    def identity_mode(self) -> str:
        return self.data_backend

    def admin_role_of(self, user_id: str) -> "AdminRole":
        """
        Muc quan tri THAT SU cua mot user_id — nguon su that DUY NHAT cho moi
        phep kiem quyen quan tri (Admin Control Center V2).

        Thu tu kiem TU CAO XUONG THAP: mot user_id co the (do sai sot cau
        hinh) nam trong nhieu danh sach cung luc — luc do OWNER thang, khong
        cong don quyen. Import `AdminRole` cuc bo trong ham (khong o dau tep)
        de tranh vong lap import: `domain.py` khong dong gi toi `config.py`,
        nhung nhieu module import ca hai theo thu tu khac nhau.
        """
        from server.domain import AdminRole

        if user_id in self.owner_user_ids:
            return AdminRole.OWNER
        if user_id in self.admin_user_ids:
            return AdminRole.ADMIN
        if user_id in self.moderator_user_ids:
            return AdminRole.MODERATOR
        return AdminRole.NONE

    def validate(self) -> None:
        """
        Kiem tra cau hinh khi khoi dong. FAIL FAST: da chon che do cloud ma
        thieu/sai bien thi dung han, TUYET DOI khong am tham lui ve mock.
        """
        if self.data_backend not in DATA_BACKENDS:
            raise ConfigError(
                f"DATA_BACKEND phải là một trong {DATA_BACKENDS}, nhận được {self.data_backend!r}."
            )
        if self.storage_backend not in STORAGE_BACKENDS:
            raise ConfigError(
                f"STORAGE_BACKEND phải là một trong {STORAGE_BACKENDS}, "
                f"nhận được {self.storage_backend!r}."
            )
        if self.data_backend == "appwrite" and not self.appwrite.configured:
            raise ConfigError(
                "DATA_BACKEND=appwrite nhưng thiếu cấu hình. Cần đủ bốn biến: "
                "APPWRITE_ENDPOINT, APPWRITE_PROJECT_ID, APPWRITE_API_KEY, "
                "APPWRITE_DATABASE_ID."
            )
        if self.storage_backend == "r2" and not self.r2.configured:
            raise ConfigError(
                "STORAGE_BACKEND=r2 nhưng thiếu cấu hình. Cần đủ bốn biến: "
                "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET."
            )
        # CORS: production khong duoc dung wildcard khi van gui credentials
        if not self.is_development and "*" in self.cors_origins:
            raise ConfigError(
                "Không được dùng CORS wildcard '*' cùng credentials ở chế độ production. "
                "Hãy liệt kê rõ origin trong FAS_CORS_ORIGINS."
            )

        # Kiem CUOI CUNG co chu dich. Cac kiem o tren noi ve cau hinh THIEU hoac
        # SAI; cai nay noi ve HINH DANG TRIEN KHAI. Dat truoc chung thi mot cau
        # hinh vua thieu CORS vua sai hinh dang se bao nhAm cai it co ban hon —
        # va no da tung che mat loi wildcard trong bo test.
        #
        # Moi truong THAT ma web van tu chay job: restart web se giet job dang
        # chay, va mot request handler phai cho TTS chay xong. O goi Free cua
        # Render con te hon — service ngu sau 15 phut, ngu ngay giua chung.
        # Van cho phep, nhung phai TUONG MINH: xem `deploy/RUNBOOK.md` muc
        # "Rollback ve che do inline (khan cap)".
        if (not self.is_development and self.inline_worker
                and not self.allow_inline_worker_in_real_env):
            raise ConfigError(
                f"FAS_ENV={self.environment!r} nhưng FAS_INLINE_WORKER vẫn bật. "
                "Ở môi trường thật, web không được tự chạy job TTS: restart web "
                "sẽ giết job đang chạy giữa chừng. "
                "Cách đúng: đặt FAS_INLINE_WORKER=false và chạy một tiến trình "
                "`python -m server.worker`. "
                "Nếu thật sự cố ý (chữa cháy tạm), đặt thêm "
                "FAS_ALLOW_INLINE_WORKER_IN_REAL_ENV=true."
            )

    def describe(self) -> dict:
        """Tom tat cau hinh - KHONG bao gio chua gia tri bi mat."""
        return {
            "environment": self.environment,
            "identity": self.identity_mode,
            "storage": self.storage_mode,
            "data_backend": self.data_backend,
            "storage_backend": self.storage_backend,
            "appwrite_configured": self.appwrite.configured,
            "r2_configured": self.r2.configured,
            "allow_unverified_local_voices": self.allow_unverified_local_voices,
            # Bao ra de nguoi van hanh thay NGAY giong cuc bo nao dang duoc
            # phuc vu, thay vi phai doan tu bien moi truong. Day la id giong,
            # khong phai bi mat.
            "local_voices": list(self.local_voices),
            "public_voice_languages": list(self.public_voice_languages),
            # Bao ra de nguoi van hanh thay ngay duong dang nhap nao dang mo.
            "facebook_login_enabled": self.facebook_login_enabled,
            "author_gate_enabled": self.author_gate_enabled,
            # CHI so luong, KHONG bao gio la danh sach: `/api/health` la
            # cong khai, va lo ra `user_id` cua quan tri la chi dung dich.
            # `admin_count` giu TEN CU (tuong thich nguoc: mot vai cong cu van
            # doc truong nay) nhung nay la TONG ca ba muc; hai truong rieng
            # them de nhin ro phan bo giua cac muc.
            "admin_count": (
                len(self.owner_user_ids) + len(self.admin_user_ids)
                + len(self.moderator_user_ids)
            ),
            "owner_count": len(self.owner_user_ids),
            "moderator_count": len(self.moderator_user_ids),
            "env_file_loaded": self.env_file_loaded,
            "inline_worker": self.inline_worker,
            "translation_inline_worker": self.translation_inline_worker,
            "translation_provider_configured": bool(
                self.translation_base_url and self.translation_api_key
                and self.translation_model),
            "image_studio": self.image_studio.describe(),
        }


def _social_limits() -> dict:
    """
    Doc `FAS_SOCIAL_LIMITS` dang `post:10/60,comment:40/60`.

    Muc nao sai cu phap thi BO QUA muc do va giu mac dinh, khong nem loi. Ly do:
    bien nay chi NOI LONG mot nguong an toan. Mot dau phay thua trong bien moi
    truong ma lam backend khong khoi dong duoc la mot cai gia qua dat cho mot
    tham so tuy chon — trong khi bo qua no chi co nghia la nguong an toan van
    duoc dung.
    """
    from server.social import HanMuc

    raw = _env("FAS_SOCIAL_LIMITS", "")
    ra: dict = {}
    for muc in raw.split(","):
        muc = muc.strip()
        if not muc or ":" not in muc:
            continue
        ten, _, phan = muc.partition(":")
        so, _, phut = phan.partition("/")
        try:
            ra[ten.strip()] = HanMuc(so_lan=int(so), phut=int(phut or 60))
        except ValueError:
            continue
    return ra


def _local_voices() -> Tuple[str, ...]:
    """
    Doc `FAS_LOCAL_VOICES`. Khong dat -> giu mac dinh cua `Settings`.

    Dat bang chuoi RONG la co y tat het giong cuc bo, khac han voi khong dat.
    Phan biet duoc hai cai do la quan trong: "tat het" phai lam duoc ma khong
    can sua ma nguon.
    """
    raw = os.environ.get("FAS_LOCAL_VOICES")
    if raw is None:
        return Settings.local_voices
    return tuple(v.strip() for v in raw.split(",") if v.strip())


def _public_voice_languages() -> Tuple[str, ...]:
    """
    Doc `FAS_PUBLIC_VOICE_LANGUAGES`. Khong dat -> giu mac dinh.

    Chuoi RONG nghia la KHONG GIOI HAN ngon ngu — khac han `FAS_LOCAL_VOICES`,
    o do chuoi rong nghia la tat het. Hai bien, hai y nghia nguoc nhau, va do la
    co y: mot ben la danh sach cho phep (rong = khong cho ai), ben kia la bo loc
    thu hep (rong = khong loc gi).
    """
    raw = os.environ.get("FAS_PUBLIC_VOICE_LANGUAGES")
    if raw is None:
        return Settings.public_voice_languages
    return tuple(v.strip().lower() for v in raw.split(",") if v.strip())


def load_settings() -> Settings:
    """
    Doc cau hinh tu bien moi truong.

    NAP `.env` TRUOC TIEN - truoc khi doc bat ky bien nao va truoc khi tang
    tren chon adapter. Bien co san trong process environment van thang.
    """
    env_file = load_env_file()

    environment = _env("FAS_ENV", "development")
    var_dir = Path(_env("FAS_VAR_DIR")) if _env("FAS_VAR_DIR") else DEFAULT_VAR_DIR

    allow_local = _env("FAS_ALLOW_UNVERIFIED_LOCAL_VOICES", "").lower()
    if allow_local in ("1", "true", "yes"):
        allow_unverified = True
    elif allow_local in ("0", "false", "no"):
        allow_unverified = False
    else:
        # Mac dinh: chi bat khi dang o development
        allow_unverified = environment.lower() in ("development", "dev", "local")

    return Settings(
        environment=environment,
        data_backend=_env("DATA_BACKEND", "mock").lower(),
        storage_backend=_env("STORAGE_BACKEND", "local").lower(),
        cors_origins=_env_list("FAS_CORS_ORIGINS", "http://localhost:3000"),
        web_base_url=_env("FAS_WEB_BASE_URL", "http://localhost:3000").rstrip("/"),
        facebook_login_enabled=_env_bool("FAS_FACEBOOK_LOGIN", False),
        author_gate_enabled=_env_bool("FAS_AUTHOR_GATE", False),
        admin_user_ids=tuple(
            x for x in _env_list("FAS_ADMIN_USER_IDS", "") if x.strip()
        ),
        owner_user_ids=tuple(
            x for x in _env_list("FAS_OWNER_USER_IDS", "") if x.strip()
        ),
        moderator_user_ids=tuple(
            x for x in _env_list("FAS_MODERATOR_USER_IDS", "") if x.strip()
        ),
        social_limits=_social_limits(),
        var_dir=var_dir,
        appwrite=AppwriteSettings(
            endpoint=_env("APPWRITE_ENDPOINT"),
            project_id=_env("APPWRITE_PROJECT_ID"),
            api_key=_env("APPWRITE_API_KEY"),
            schema_api_key=_env("APPWRITE_SCHEMA_API_KEY"),
            database_id=_env("APPWRITE_DATABASE_ID"),
        ),
        r2=R2Settings(
            account_id=_env("R2_ACCOUNT_ID"),
            access_key_id=_env("R2_ACCESS_KEY_ID"),
            secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
            bucket=_env("R2_BUCKET"),
        ),
        allow_unverified_local_voices=allow_unverified,
        local_voices=_local_voices(),
        public_voice_languages=_public_voice_languages(),
        inline_worker=_env_bool("FAS_INLINE_WORKER", True),
        allow_inline_worker_in_real_env=_env_bool(
            "FAS_ALLOW_INLINE_WORKER_IN_REAL_ENV", False),
        translation_inline_worker=_env_bool(
            "FAS_TRANSLATION_INLINE_WORKER", True),
        env_file_loaded=env_file is not None,
        translation_base_url=_env("TRANSLATION_BASE_URL"),
        translation_api_key=_env("TRANSLATION_API_KEY"),
        translation_model=_env("TRANSLATION_MODEL"),
        youtube_api_key=_env("YOUTUBE_API_KEY"),
        youtube_websub_callback_base_url=_env("YOUTUBE_WEBSUB_CALLBACK_BASE_URL"),
        image_studio=_image_studio_settings(),
    )


def _image_studio_settings() -> ImageStudioSettings:
    """
    So VD mac dinh (20/15 USD, 3 dong thoi) la con so KHOI DONG hop ly cho
    MOT chu site nho — KHONG hard-code trong logic nghiep vu (PHASE 7 yeu
    cau ro: "Do not hard-code the example numbers"), CHI la default cua
    dataclass, doi duoc hoan toan qua bien moi truong ma khong sua code.
    """
    def _float(name: str, default: float) -> float:
        raw = _env(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            raise ConfigError(f"{name} phải là số, nhận được {raw!r}.")

    def _int(name: str, default: int) -> int:
        raw = _env(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ConfigError(f"{name} phải là số nguyên, nhận được {raw!r}.")

    return ImageStudioSettings(
        shared_premium_enabled=_env_bool("IMAGE_SHARED_PREMIUM_ENABLED", False),
        monthly_budget_usd=_float("IMAGE_MONTHLY_BUDGET_USD", 20.0),
        warning_budget_usd=_float("IMAGE_WARNING_BUDGET_USD", 15.0),
        max_cost_per_request_usd=_float("IMAGE_MAX_COST_PER_REQUEST_USD", 0.10),
        max_concurrent_shared_generations=_int(
            "IMAGE_MAX_CONCURRENT_SHARED_GENERATIONS", 3),
        markup_multiplier=_float("IMAGE_MARKUP_MULTIPLIER", 1.0),
        disabled_models=tuple(_env_list("IMAGE_DISABLED_MODELS", "")),
        pollinations_api_key=_env("POLLINATIONS_API_KEY"),
        pollinations_client_id=_env("POLLINATIONS_CLIENT_ID"),
        byop_master_key=_env("IMAGE_BYOP_MASTER_KEY"),
        byop_redirect_uri=_env("IMAGE_BYOP_REDIRECT_URI"),
    )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Dung trong test de doc lai bien moi truong."""
    global _settings
    _settings = None
