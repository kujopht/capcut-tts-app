"""
Doc va truy van catalog giong doc tu Voice.json.

Toan bo danh sach giong duoc doc DONG tu file — khong hardcode so luong hay
ten giong nao. Chi dua vao cac field co thuc trong Voice.json
(lan, lang, voice_type, display_name, resource_id, captured_at); field thieu
thi bo qua chu khong phong doan.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from desktop_app.models import VoiceEntry, slugify


class VoiceCatalogError(Exception):
    """Khong doc duoc Voice.json."""


SORT_MODES = (
    ("name_asc", "Tên A → Z"),
    ("name_desc", "Tên Z → A"),
    ("lang_asc", "Ngôn ngữ, rồi tên"),
    ("type_asc", "voice_type A → Z"),
    ("catalog", "Thứ tự trong Voice.json"),
)


def voice_sort_key(voice: VoiceEntry) -> str:
    """
    Khoa sap xep theo ten hien thi.

    Voice.json co ca ten khong dung chu Latin (Trung, Thai, Nhat). Voi cac ten
    do, slugify tra ve rong nen phai lui ve dung chinh ten (chu thuong) —
    neu khong tat ca se dinh vao mot khoa fallback va thu tu thanh ngau nhien.
    """
    label = voice.label or voice.voice_type
    return slugify(label, fallback="") or label.lower()


def default_catalog_paths() -> List[Path]:
    """
    Cac vi tri co the chua Voice.json, theo do uu tien.
    Ho tro ca khi chay tu source va khi da dong goi bang PyInstaller.
    """
    candidates: List[Path] = []
    # PyInstaller: file duoc gom vao thu muc tam _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "Voice.json")
    # Ben canh file exe (--onedir)
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "Voice.json")
    # Chay tu source: <repo>/Voice.json
    candidates.append(Path(__file__).resolve().parent.parent / "Voice.json")
    candidates.append(Path.cwd() / "Voice.json")

    unique: List[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def find_catalog_path() -> Optional[Path]:
    for path in default_catalog_paths():
        if path.is_file():
            return path
    return None


class VoiceCatalog:
    """
    Danh sach giong doc + tim kiem / loc / sap xep / yeu thich.

    `favorites` la tap hop `VoiceEntry.uid` (voice_type|resource_id) — dung uid
    thay vi voice_type vi Voice.json thuc te co voice_type bi trung.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path: Optional[Path] = Path(path) if path else None
        self.voices: List[VoiceEntry] = []
        self.skipped_entries: int = 0
        self._favorites: set[str] = set()
        self._by_uid: Dict[str, VoiceEntry] = {}

    # -- nap du lieu ----------------------------------------------------------

    def load(self, path: Optional[Path] = None) -> List[VoiceEntry]:
        """Doc (hoac doc lai) Voice.json. Nem VoiceCatalogError khi that bai."""
        target = Path(path) if path else (self.path or find_catalog_path())
        if target is None:
            raise VoiceCatalogError(
                "Không tìm thấy Voice.json. Đặt file Voice.json cạnh ứng dụng "
                "hoặc chọn lại đường dẫn trong Cài đặt."
            )
        target = Path(target)
        if not target.is_file():
            raise VoiceCatalogError(f"Không tìm thấy file catalog: {target}")

        try:
            with open(target, "r", encoding="utf-8") as fp:
                raw = json.load(fp)
        except UnicodeDecodeError as exc:
            raise VoiceCatalogError(f"Voice.json không phải UTF-8: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise VoiceCatalogError(f"Voice.json không phải JSON hợp lệ: {exc}") from exc
        except OSError as exc:
            raise VoiceCatalogError(f"Không đọc được Voice.json: {exc}") from exc

        # Ho tro ca dang list thuan va dang {"voices": [...]}
        if isinstance(raw, dict):
            raw = raw.get("voices") or raw.get("data") or []
        if not isinstance(raw, list):
            raise VoiceCatalogError("Voice.json phải là một danh sách các giọng đọc.")

        voices: List[VoiceEntry] = []
        skipped = 0
        seen: set[str] = set()
        for item in raw:
            entry = VoiceEntry.from_dict(item)
            if entry is None:
                skipped += 1
                continue
            if entry.uid in seen:
                skipped += 1
                continue
            seen.add(entry.uid)
            voices.append(entry)

        if not voices:
            raise VoiceCatalogError("Voice.json không có giọng đọc nào hợp lệ.")

        self.path = target
        self.voices = voices
        self.skipped_entries = skipped
        self._by_uid = {v.uid: v for v in voices}
        return voices

    def reload(self) -> List[VoiceEntry]:
        return self.load(self.path)

    # -- truy van -------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.voices)

    @property
    def count(self) -> int:
        return len(self.voices)

    def languages(self) -> List[str]:
        """Danh sach ngon ngu co trong catalog (da sap xep)."""
        return sorted({v.language for v in self.voices if v.language})

    def get(self, uid: str) -> Optional[VoiceEntry]:
        return self._by_uid.get(uid)

    def resolve(self, uids: Iterable[str]) -> List[VoiceEntry]:
        """Doi danh sach uid thanh VoiceEntry, bo qua uid khong con ton tai."""
        out: List[VoiceEntry] = []
        for uid in uids:
            entry = self._by_uid.get(uid)
            if entry is not None:
                out.append(entry)
        return out

    def filter(
        self,
        query: str = "",
        language: Optional[str] = None,
        favorites_only: bool = False,
        sort_mode: str = "name_asc",
    ) -> List[VoiceEntry]:
        """
        Tim kiem theo ten/voice_type, loc theo ngon ngu, loc yeu thich, roi sap xep.
        `language=None` hoac "" nghia la tat ca ngon ngu.
        """
        result = list(self.voices)

        if language:
            lang = language.strip().lower()
            result = [
                v for v in result
                if (v.lang or "").lower() == lang or (v.lan or "").lower() == lang
            ]

        if favorites_only:
            result = [v for v in result if v.uid in self._favorites]

        needle = (query or "").strip()
        if needle:
            result = [v for v in result if v.matches(needle)]

        return self.sort(result, sort_mode)

    @staticmethod
    def sort(voices: Sequence[VoiceEntry], sort_mode: str = "name_asc") -> List[VoiceEntry]:
        items = list(voices)
        if sort_mode == "name_desc":
            return sorted(items, key=voice_sort_key, reverse=True)
        if sort_mode == "lang_asc":
            return sorted(items, key=lambda v: (v.language.lower(), voice_sort_key(v)))
        if sort_mode == "type_asc":
            return sorted(items, key=lambda v: v.voice_type.lower())
        if sort_mode == "catalog":
            return items
        return sorted(items, key=voice_sort_key)

    # -- yeu thich ------------------------------------------------------------

    @property
    def favorites(self) -> List[str]:
        return sorted(self._favorites)

    def set_favorites(self, uids: Iterable[str]) -> None:
        self._favorites = {str(u) for u in uids if u}

    def is_favorite(self, uid: str) -> bool:
        return uid in self._favorites

    def toggle_favorite(self, uid: str) -> bool:
        """Bat/tat yeu thich. Tra ve trang thai moi."""
        if uid in self._favorites:
            self._favorites.discard(uid)
            return False
        self._favorites.add(uid)
        return True

    def favorite_entries(self) -> List[VoiceEntry]:
        return [v for v in self.voices if v.uid in self._favorites]

    def prune_favorites(self) -> int:
        """Bo cac uid yeu thich khong con trong catalog. Tra so luong da bo."""
        stale = {uid for uid in self._favorites if uid not in self._by_uid}
        self._favorites -= stale
        return len(stale)
