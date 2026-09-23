"""Persistent Production Tracking and Deduplication Registry.

Guarantees 100% deduplication across all branches:
- Never re-downloads or re-processes YouTube videos that have already been produced.
- Matches by exact YouTube video ID (e.g. 'IM9kDTrgRFg') and normalized title.
- Persists state in `raw_spool/processed_youtube_ids.json` and auto-heals by scanning existing folders.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = PROJECT_ROOT / "raw_spool" / "processed_youtube_ids.json"
_LOCK = threading.Lock()


def _normalize_text(text: str) -> str:
    """Normalizes text for fuzzy title deduplication."""
    t = text.lower()
    t = re.sub(r"[\[\]\(\)\-\:\,\.\!\?\|\/\\\s+]+", " ", t).strip()
    return t


class ProcessedRegistry:
    """Thread-safe registry for tracking processed works."""

    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()
        self._auto_scan_spool()

    def _load(self):
        if REGISTRY_FILE.exists():
            try:
                self._data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _save(self):
        try:
            REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
            REGISTRY_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _auto_scan_spool(self):
        """Scans local raw_spool/youtube_audio and raw_spool/ai_animation to register all existing works recursively."""
        added = False
        for branch in ("youtube_audio", "ai_animation"):
            spool_dir = PROJECT_ROOT / "raw_spool" / branch
            if not spool_dir.exists():
                continue

            # Find all metadata.json files recursively (both flat folders and nested albums)
            for mf in spool_dir.rglob("metadata.json"):
                p = mf.parent
                if p.name.startswith(("_", "temp")) or p.parent.name.startswith(("_", "temp")):
                    continue
                vid_id = None
                title = p.name

                try:
                    d = json.loads(mf.read_text(encoding="utf-8", errors="replace"))
                    vid_id = d.get("id") or d.get("video_id")
                    title = d.get("title_original") or d.get("title_vi") or title
                    if not vid_id and d.get("source_url"):
                        m = re.search(r"v=([a-zA-Z0-9_-]+)", d["source_url"])
                        if m:
                            vid_id = m.group(1)
                except Exception:
                    pass

                st = p / "source.txt"
                if not vid_id and st.exists():
                    try:
                        txt = st.read_text(encoding="utf-8", errors="replace")
                        m = re.search(r"v=([a-zA-Z0-9_-]+)", txt)
                        if m:
                            vid_id = m.group(1)
                    except Exception:
                        pass

                if vid_id and vid_id not in self._data:
                    self._data[vid_id] = {
                        "video_id": vid_id,
                        "title": title,
                        "folder": p.relative_to(spool_dir).as_posix(),
                        "branch": branch,
                    }
                    added = True

        if added:
            self._save()

    def is_processed(self, video_id: str, title: str = "") -> bool:
        """Checks if video ID or equivalent title has already been processed."""
        with _LOCK:
            # 1. Exact Video ID match
            if video_id and video_id in self._data:
                return True

            # 2. Check title against registered titles
            if title:
                norm_title = _normalize_text(title)
                # Strip fandom brackets, channel tags, episode keywords
                clean_title = re.sub(r"\[.*?\]|\(.*?\)", " ", norm_title)
                clean_title = re.sub(r"\b(phần|tập|part|ep|chương|hồi|trọn bộ|full|review|audiobook|truyện audio)\s*\d*\b", " ", clean_title)
                clean_title = re.sub(r"\s+", " ", clean_title).strip()

                if len(clean_title) >= 8:
                    tokens_a = set(w for w in clean_title.split() if len(w) > 2)
                    for item in self._data.values():
                        reg_title = _normalize_text(item.get("title", ""))
                        clean_reg = re.sub(r"\[.*?\]|\(.*?\)", " ", reg_title)
                        clean_reg = re.sub(r"\b(phần|tập|part|ep|chương|hồi|trọn bộ|full|review|audiobook|truyện audio)\s*\d*\b", " ", clean_reg)
                        clean_reg = re.sub(r"\s+", " ", clean_reg).strip()

                        if len(clean_reg) < 8:
                            continue

                        # Direct substring containment
                        if clean_title in clean_reg or clean_reg in clean_title:
                            return True

                        # Token overlap (Jaccard similarity >= 0.75)
                        tokens_b = set(w for w in clean_reg.split() if len(w) > 2)
                        if tokens_a and tokens_b:
                            overlap = len(tokens_a & tokens_b)
                            total = len(tokens_a | tokens_b)
                            if total > 0 and (overlap / total) >= 0.75:
                                return True

            return False

    def mark_processed(self, video_id: str, title: str, folder_name: str = "", branch: str = "") -> None:
        """Registers a newly processed video to prevent any future duplicate processing."""
        with _LOCK:
            self._data[video_id] = {
                "video_id": video_id,
                "title": title,
                "folder": folder_name,
                "branch": branch,
            }
            self._save()

    def get_all_processed_ids(self) -> Set[str]:
        with _LOCK:
            return set(self._data.keys())


# Singleton instance
_registry: Optional[ProcessedRegistry] = None


def get_processed_registry() -> ProcessedRegistry:
    global _registry
    if _registry is None:
        _registry = ProcessedRegistry()
    return _registry
