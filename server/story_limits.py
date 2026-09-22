"""
Gioi han ky tu chuong truyen — chia se giua server.main va farmer.

Tach thanh module doc lap de tranh import cycle:
- `server.main` can doc de dat Pydantic constraint `NoiDungChuong`.
- `server.farmer` can doc de cat chuong va preflight truoc khi POST /api/chapters.
- Ca hai deu khong duoc import cheo nhau chi vi mot hang so.
"""
from __future__ import annotations

import os

DEFAULT_MAX_CHAPTER_CHARS: int = 100_000
ENV_MAX_CHAPTER_CHARS: str = "FAS_MAX_CHAPTER_CHARS"


def get_max_chapter_chars() -> int:
    """Lay gioi han ky tu chuong hien tai tu moi truong hoac mac dinh 100.000."""
    try:
        val = int(os.environ.get(ENV_MAX_CHAPTER_CHARS, str(DEFAULT_MAX_CHAPTER_CHARS)))
        if val <= 0:
            return DEFAULT_MAX_CHAPTER_CHARS
        return val
    except (ValueError, TypeError):
        return DEFAULT_MAX_CHAPTER_CHARS
