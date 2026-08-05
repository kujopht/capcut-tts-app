"""
Luu/doc cai dat nguoi dung bang QSettings.

Luu y ve du lieu nhay cam:
- Ung dung KHONG luu token/credential.
- Neu nguoi dung chon `device.json`, file duoc COPY vao thu muc du lieu nguoi
  dung (AppData) — khong bao gio luu trong Program Files, khong dong goi vao EXE
  va khong commit vao repo.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSettings, QStandardPaths

from desktop_app import APP_NAME, APP_ORG
from desktop_app.models import (
    DEFAULT_CHUNK_CHARS,
    MAX_WORKERS,
)
from desktop_app.text_chunker import normalize_chunk_size

RATE_CHOICES = ("0.8", "0.9", "1.0", "1.1", "1.2", "1.5")

THEME_DARK = "dark"
THEME_LIGHT = "light"


def documents_dir() -> Path:
    """Thu muc Documents cua nguoi dung (co fallback khi Qt khong tra ve gi)."""
    raw = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    if raw:
        return Path(raw)
    return Path.home() / "Documents"


def default_output_dir() -> Path:
    """%USERPROFILE%\\Documents\\Fanfic Audio Studio\\outputs"""
    return documents_dir() / APP_NAME / "outputs"


def user_data_dir() -> Path:
    """
    Thu muc du lieu nguoi dung (%LOCALAPPDATA%\\FanficAudioStudio), dung cho
    device.json runtime. TUYET DOI khong dung Program Files.

    Lay truc tiep tu bien moi truong de duong dan on dinh, khong phu thuoc vao
    viec QApplication da dat applicationName hay chua.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_ORG
    raw = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if raw:
        return Path(raw)
    return Path.home() / f".{APP_ORG.lower()}"


#: Dat bien moi truong nay tro toi mot file .ini de KHONG dung registry.
#: Dung cho test (khong lam ban cai dat that cua nguoi dung) va cho ban portable.
SETTINGS_FILE_ENV = "FAS_SETTINGS_FILE"


def make_qsettings() -> QSettings:
    """
    Tao QSettings cho ung dung.

    Uu tien file .ini neu bien moi truong FAS_SETTINGS_FILE duoc dat; neu khong
    thi dung noi luu tru mac dinh cua he thong (registry tren Windows).
    """
    override = os.environ.get(SETTINGS_FILE_ENV, "").strip()
    if override:
        path = Path(override)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return QSettings(str(path), QSettings.Format.IniFormat)
    return QSettings(APP_ORG, APP_NAME)


class SettingsManager:
    """Bao boc QSettings voi gia tri mac dinh va kiem tra kieu."""

    def __init__(self, settings: Optional[QSettings] = None):
        self.settings = settings or make_qsettings()

    def sync(self) -> None:
        self.settings.sync()

    # -- thu muc ket qua ------------------------------------------------------

    @property
    def output_dir(self) -> Path:
        raw = self.settings.value("output/dir", "", type=str)
        return Path(raw) if raw else default_output_dir()

    @output_dir.setter
    def output_dir(self, value: Path | str) -> None:
        self.settings.setValue("output/dir", str(value))

    def ensure_output_dir(self) -> Path:
        path = self.output_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -- tham so tao audio ----------------------------------------------------

    @property
    def chunk_chars(self) -> int:
        return normalize_chunk_size(
            self.settings.value("tts/chunk_chars", DEFAULT_CHUNK_CHARS, type=int)
        )

    @chunk_chars.setter
    def chunk_chars(self, value: int) -> None:
        self.settings.setValue("tts/chunk_chars", normalize_chunk_size(value))

    @property
    def rate(self) -> str:
        raw = str(self.settings.value("tts/rate", "1.0", type=str) or "1.0")
        try:
            float(raw)
        except ValueError:
            return "1.0"
        return raw

    @rate.setter
    def rate(self, value: str) -> None:
        self.settings.setValue("tts/rate", str(value))

    @property
    def workers(self) -> int:
        """Concurrency: mac dinh 1, toi da 2 (theo yeu cau de khong spam API)."""
        value = self.settings.value("queue/workers", 1, type=int)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 1
        return max(1, min(MAX_WORKERS, value))

    @workers.setter
    def workers(self, value: int) -> None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 1
        self.settings.setValue("queue/workers", max(1, min(MAX_WORKERS, value)))

    # -- ffmpeg ---------------------------------------------------------------

    @property
    def ffmpeg_path(self) -> str:
        return str(self.settings.value("tools/ffmpeg", "", type=str) or "")

    @ffmpeg_path.setter
    def ffmpeg_path(self, value: str) -> None:
        self.settings.setValue("tools/ffmpeg", str(value or ""))

    # -- theme ----------------------------------------------------------------

    @property
    def theme(self) -> str:
        value = str(self.settings.value("ui/theme", THEME_DARK, type=str) or THEME_DARK)
        return value if value in (THEME_DARK, THEME_LIGHT) else THEME_DARK

    @theme.setter
    def theme(self, value: str) -> None:
        self.settings.setValue("ui/theme", value if value in (THEME_DARK, THEME_LIGHT) else THEME_DARK)

    # -- voice yeu thich ------------------------------------------------------

    @property
    def favorites(self) -> List[str]:
        raw = self.settings.value("voices/favorites", [])
        if isinstance(raw, str):
            raw = [raw] if raw else []
        if raw is None:
            return []
        try:
            return [str(item) for item in raw if str(item).strip()]
        except TypeError:
            return []

    @favorites.setter
    def favorites(self, uids: List[str]) -> None:
        self.settings.setValue("voices/favorites", [str(u) for u in uids])

    # -- device.json ----------------------------------------------------------

    @property
    def device_json_path(self) -> str:
        return str(self.settings.value("api/device_json", "", type=str) or "")

    @device_json_path.setter
    def device_json_path(self, value: str) -> None:
        self.settings.setValue("api/device_json", str(value or ""))

    def runtime_device_path(self) -> Path:
        """Vi tri ban runtime cua device.json trong thu muc du lieu nguoi dung."""
        return user_data_dir() / "device.json"

    def import_device_json(self, source: Path | str) -> Path:
        """
        Copy device.json nguoi dung chon vao thu muc du lieu nguoi dung.
        Tra ve duong dan ban runtime. Nem OSError/ValueError khi that bai.
        """
        src = Path(source)
        if not src.is_file():
            raise ValueError(f"Không tìm thấy file: {src}")
        import json as _json

        try:
            with open(src, "r", encoding="utf-8") as fp:
                data = _json.load(fp)
        except Exception as exc:
            raise ValueError(f"device.json không hợp lệ: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("device.json phải là một object JSON.")

        target = self.runtime_device_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        self.device_json_path = str(target)
        return target

    def clear_device_json(self) -> None:
        """Xoa ban runtime va bo cau hinh (tro ve device mac dinh cua SDK)."""
        target = self.runtime_device_path()
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        self.device_json_path = ""

    def active_device_path(self) -> Optional[str]:
        """Duong dan device.json dang dung, hoac None neu dung device mac dinh."""
        configured = self.device_json_path
        if configured and Path(configured).is_file():
            return configured
        runtime = self.runtime_device_path()
        if runtime.is_file():
            return str(runtime)
        return None

    # -- catalog --------------------------------------------------------------

    @property
    def catalog_path(self) -> str:
        return str(self.settings.value("voices/catalog_path", "", type=str) or "")

    @catalog_path.setter
    def catalog_path(self, value: str) -> None:
        self.settings.setValue("voices/catalog_path", str(value or ""))

    # -- cua so ---------------------------------------------------------------

    def save_window(self, geometry: bytes, state: bytes) -> None:
        self.settings.setValue("ui/geometry", geometry)
        self.settings.setValue("ui/window_state", state)

    def load_geometry(self):
        return self.settings.value("ui/geometry")

    def load_window_state(self):
        return self.settings.value("ui/window_state")

    def save_splitter(self, name: str, state: bytes) -> None:
        self.settings.setValue(f"ui/splitter_{name}", state)

    def load_splitter(self, name: str):
        return self.settings.value(f"ui/splitter_{name}")

    # -- catalog voice da chon (nho lai giua cac phien) -----------------------

    @property
    def last_selected_voices(self) -> List[str]:
        raw = self.settings.value("voices/last_selected", [])
        if isinstance(raw, str):
            raw = [raw] if raw else []
        if raw is None:
            return []
        try:
            return [str(item) for item in raw if str(item).strip()]
        except TypeError:
            return []

    @last_selected_voices.setter
    def last_selected_voices(self, uids: List[str]) -> None:
        self.settings.setValue("voices/last_selected", [str(u) for u in uids])
