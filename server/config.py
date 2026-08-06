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
from typing import List, Optional

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

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.project_id and self.api_key and self.database_id)


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
class Settings:
    """Toan bo cau hinh backend."""

    environment: str = "development"
    #: "mock" (mac dinh) hoac "appwrite"
    data_backend: str = "mock"
    #: "local" (mac dinh) hoac "r2"
    storage_backend: str = "local"
    cors_origins: List[str] = field(default_factory=list)
    var_dir: Path = DEFAULT_VAR_DIR
    appwrite: AppwriteSettings = field(default_factory=AppwriteSettings)
    r2: R2Settings = field(default_factory=R2Settings)

    #: Giong/model chay cuc bo chua xac minh giay phep. CHI bat o development;
    #: khong duoc danh dau la san sang thuong mai.
    allow_unverified_local_voices: bool = True

    #: Da nap duoc file `.env` hay chua. Bao ra o `/api/health` de nguoi van
    #: hanh biet ngay file cau hinh co thuc su co tac dung khong - chinh la
    #: cai bay da tung lam ca buoi kiem chung chay tren mock.
    env_file_loaded: bool = False

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in ("development", "dev", "local")

    @property
    def storage_mode(self) -> str:
        return self.storage_backend

    @property
    def identity_mode(self) -> str:
        return self.data_backend

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
            "env_file_loaded": self.env_file_loaded,
        }


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
        var_dir=var_dir,
        appwrite=AppwriteSettings(
            endpoint=_env("APPWRITE_ENDPOINT"),
            project_id=_env("APPWRITE_PROJECT_ID"),
            api_key=_env("APPWRITE_API_KEY"),
            database_id=_env("APPWRITE_DATABASE_ID"),
        ),
        r2=R2Settings(
            account_id=_env("R2_ACCOUNT_ID"),
            access_key_id=_env("R2_ACCESS_KEY_ID"),
            secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
            bucket=_env("R2_BUCKET"),
        ),
        allow_unverified_local_voices=allow_unverified,
        env_file_loaded=env_file is not None,
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
