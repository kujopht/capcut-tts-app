"""
Cache audio nghe thu.

Khoa cache = provider + voice_key + noi dung cau thu. Cung mot giong voi cung
mot cau thi chi goi provider DUNG MOT LAN, cac lan sau phat lai ban da co.

Vi tri: %LOCALAPPDATA%\\FanficAudioStudio\\cache\\preview
- KHONG bao gio ghi vao thu muc output truyen cua nguoi dung.
- KHONG nam trong repo va KHONG duoc dong goi vao installer.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import List, Optional

from desktop_app.providers.piper_models import user_data_dir

#: Bien moi truong de test tro cache sang thu muc tam.
CACHE_DIR_ENV = "FAS_PREVIEW_CACHE_DIR"

#: File nho hon nguong nay coi nhu hong, khong dung lai.
MIN_VALID_BYTES = 512

#: Ban cache cu hon so ngay nay se bi don.
MAX_AGE_DAYS = 14


def preview_cache_dir() -> Path:
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override)
    return user_data_dir() / "cache" / "preview"


def ensure_cache_dir() -> Path:
    target = preview_cache_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def cache_key(provider: str, voice_key: str, text: str) -> str:
    """Khoa on dinh cho mot ban nghe thu."""
    raw = f"{provider}\x1f{voice_key}\x1f{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def cache_path(provider: str, voice_key: str, text: str) -> Path:
    return preview_cache_dir() / f"{cache_key(provider, voice_key, text)}.mp3"


def cached_file(provider: str, voice_key: str, text: str) -> Optional[Path]:
    """
    Ban cache HOP LE, hoac None.

    File rong/hong bi coi nhu khong co de lan sau tao lai.
    """
    path = cache_path(provider, voice_key, text)
    try:
        if path.is_file() and path.stat().st_size >= MIN_VALID_BYTES:
            return path
    except OSError:
        return None
    return None


def prune_old(max_age_days: int = MAX_AGE_DAYS) -> int:
    """Don cac ban cache qua cu. Tra ve so file da xoa. Khong nem exception."""
    base = preview_cache_dir()
    if not base.is_dir():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        for path in base.glob("*.mp3"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed


def clear_all() -> int:
    """Xoa toan bo cache nghe thu."""
    base = preview_cache_dir()
    if not base.is_dir():
        return 0
    removed = 0
    for path in list(base.glob("*.mp3")):
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def list_cached() -> List[Path]:
    base = preview_cache_dir()
    if not base.is_dir():
        return []
    try:
        return sorted(base.glob("*.mp3"))
    except OSError:
        return []
