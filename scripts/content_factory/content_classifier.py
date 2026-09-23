"""
Content Classifier — Content Factory v2.

Classifies upstream fiction entries BEFORE translation into:
- STORY_CHAPTER: Standard story narrative -> translate / publish / TTS
- EXTRA: Side story / Omake / Interlude / Special -> translate / publish / TTS with visible Extra label
- AUTHOR_NOTE: Author notes / status updates -> do not enter canonical reader navigation
- ANNOUNCEMENT: Hiatus / schedule delay / announcement -> do not translate / TTS (archive / ignore)
- UNKNOWN: Ambiguous entries -> require manual review (blocks publish)

Guarantees:
- Never spend LLM or TTS resources on announcements by default.
- Separates source_order from reader display_order.
- Supports persistent per-fiction classification overrides.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from scripts.content_factory.publish_quality_gate import EntryClassification

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PERSISTENT_CLASSIFICATION_DIR = PROJECT_ROOT / "raw_spool" / "classifications"
PERSISTENT_CLASSIFICATION_DIR.mkdir(parents=True, exist_ok=True)

# Regex patterns
ANNOUNCEMENT_TITLE_REGEX = re.compile(
    r"\b(announcement|hiatus|schedule\s*change|update\s*delayed|break|poll|q&a|notice|thông\s*báo|lưu\s*trữ)\b",
    re.IGNORECASE
)
AUTHOR_NOTE_TITLE_REGEX = re.compile(
    r"\b(author\s*note|author's\s*note|a/n:?|a\.n\.:?|ghi\s*chú\s*tác\s*giả|glossary|character\s*sheet)\b",
    re.IGNORECASE
)
EXTRA_TITLE_REGEX = re.compile(
    r"\b(extra|side\s*story|omake|interlude|special|ngoại\s*truyện)\b",
    re.IGNORECASE
)
STANDARD_CHAPTER_REGEX = re.compile(
    r"^(chapter|chương|ch\.|chap\.?|ch[_.\s-]*)\s*[\d.]+",
    re.IGNORECASE
)


class ClassificationDecision(BaseModel):
    entry_type: EntryClassification
    action: str  # TRANSLATE_PUBLISH, TRANSLATE_PUBLISH_EXTRA, ARCHIVE_IGNORE, MANUAL_REVIEW_REQUIRED
    display_in_toc: bool
    display_label: str = ""
    extra_number: Optional[int] = None
    reason: str
    confidence: float = 1.0


class ContentClassifier:
    """Classifies upstream entries and manages reader display ordering."""

    def __init__(self, overrides_file: Optional[Path] = None):
        self.overrides: Dict[str, Dict[int, Any]] = {}
        if overrides_file and overrides_file.exists():
            self.load_overrides(overrides_file)

    def load_overrides(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Handles array format [{"upstream_order": 19, "is_announcement": True...}]
            if isinstance(data, list):
                f_map = {}
                for item in data:
                    ord_num = item.get("order") or item.get("source_order") or item.get("upstream_order")
                    if ord_num:
                        f_map[int(ord_num)] = item
                self.overrides["default"] = f_map
            elif isinstance(data, dict):
                self.overrides["default"] = data
        except Exception:
            pass

    def classify_entry(
        self,
        title: str,
        content: str = "",
        source_order: int = 0,
        work_id: str = "default",
    ) -> ClassificationDecision:
        """Classifies a single chapter entry before any LLM translation is dispatched."""
        # 1. Check persistent overrides first
        work_overrides = self.overrides.get(work_id) or self.overrides.get("default") or {}
        if source_order in work_overrides:
            ov = work_overrides[source_order]
            cls_val = ov.get("classification") or ov.get("entry_type")
            if ov.get("is_announcement") or cls_val == EntryClassification.ANNOUNCEMENT.value or cls_val == "ANNOUNCEMENT":
                return ClassificationDecision(
                    entry_type=EntryClassification.ANNOUNCEMENT,
                    action="ARCHIVE_IGNORE",
                    display_in_toc=False,
                    display_label="[Thông Báo Tác Giả - Đã Lưu Trữ]",
                    reason=f"Khớp cấu hình ghi đè persistent cho chương {source_order} (Announcement).",
                    confidence=1.0,
                )
            if ov.get("is_extra") or cls_val == EntryClassification.EXTRA.value or cls_val == "EXTRA":
                return ClassificationDecision(
                    entry_type=EntryClassification.EXTRA,
                    action="TRANSLATE_PUBLISH_EXTRA",
                    display_in_toc=True,
                    display_label="Ngoại Truyện 1",
                    extra_number=ov.get("extra_number", 1),
                    reason=f"Khớp cấu hình ghi đè persistent cho chương {source_order} (Extra).",
                    confidence=1.0,
                )
            if cls_val == EntryClassification.STORY_CHAPTER.value or cls_val == "STORY_CHAPTER" or (not ov.get("is_announcement") and not ov.get("is_extra")):
                return ClassificationDecision(
                    entry_type=EntryClassification.STORY_CHAPTER,
                    action="TRANSLATE_PUBLISH",
                    display_in_toc=True,
                    reason=f"Khớp cấu hình ghi đè persistent cho chương {source_order} (Story).",
                    confidence=1.0,
                )

        clean_title = (title or "").strip()
        clean_content = (content or "").strip()
        word_count = len(clean_content.split())

        # 2. Check Announcements
        if ANNOUNCEMENT_TITLE_REGEX.search(clean_title):
            return ClassificationDecision(
                entry_type=EntryClassification.ANNOUNCEMENT,
                action="ARCHIVE_IGNORE",
                display_in_toc=False,
                display_label="[Thông Báo Tác Giả - Đã Lưu Trữ]",
                reason=f"Tiêu đề chứa từ khóa thông báo ('{clean_title}').",
                confidence=0.95,
            )

        # 3. Check Author Notes
        if AUTHOR_NOTE_TITLE_REGEX.search(clean_title):
            # If very short, definitely author note
            if word_count < 800:
                return ClassificationDecision(
                    entry_type=EntryClassification.AUTHOR_NOTE,
                    action="ARCHIVE_IGNORE",
                    display_in_toc=False,
                    display_label="[Ghi Chú Tác Giả]",
                    reason=f"Ghi chú tác giả ngắn ({word_count} từ, tiêu đề '{clean_title}').",
                    confidence=0.9,
                )

        # 4. Check Extras / Side Stories
        if EXTRA_TITLE_REGEX.search(clean_title):
            # Extract extra number if present
            num_match = re.search(r"\b(?:extra|ngoại\s*truyện)\s*(\d+)", clean_title, re.IGNORECASE)
            extra_num = int(num_match.group(1)) if num_match else 1
            return ClassificationDecision(
                entry_type=EntryClassification.EXTRA,
                action="TRANSLATE_PUBLISH_EXTRA",
                display_in_toc=True,
                display_label=f"Ngoại Truyện {extra_num}",
                extra_number=extra_num,
                reason=f"Tiêu đề chứa từ khóa ngoại truyện ('{clean_title}').",
                confidence=0.95,
            )

        # 5. Short Content Heuristic with Announcement markers in body
        if 0 < word_count < 400:
            ann_body = re.search(r"\b(taking a break|hiatus|delayed|delay|won't be able to update|sorry for the delay)\b", clean_content, re.IGNORECASE)
            if ann_body:
                return ClassificationDecision(
                    entry_type=EntryClassification.ANNOUNCEMENT,
                    action="ARCHIVE_IGNORE",
                    display_in_toc=False,
                    display_label="[Thông Báo Tác Giả - Đã Lưu Trữ]",
                    reason=f"Nội dung quá ngắn ({word_count} từ) và chứa thông báo tạm ngưng/hoãn ('{ann_body.group(1)}').",
                    confidence=0.88,
                )

        # 6. Standard Chapter Check
        if STANDARD_CHAPTER_REGEX.search(clean_title) or word_count >= 500:
            return ClassificationDecision(
                entry_type=EntryClassification.STORY_CHAPTER,
                action="TRANSLATE_PUBLISH",
                display_in_toc=True,
                reason="Chương truyện cốt truyện chính tiêu chuẩn.",
                confidence=0.98,
            )

        # 7. Fallback to UNKNOWN if short and unrecognizable
        return ClassificationDecision(
            entry_type=EntryClassification.UNKNOWN,
            action="MANUAL_REVIEW_REQUIRED",
            display_in_toc=False,
            reason=f"Không xác định được loại nội dung (tiêu đề: '{clean_title}', độ dài: {word_count} từ).",
            confidence=0.4,
        )

    def calculate_display_orders(
        self,
        entries: List[Dict[str, Any]],
        work_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Takes raw upstream entries (with source_order), classifies them,
        and assigns contiguous display_order 1..N to story/extra entries.
        Announcements and author notes receive display_order = None.
        """
        sorted_entries = sorted(entries, key=lambda e: e.get("source_order", 0))
        results = []
        current_display_order = 1
        extra_counter = 1

        for entry in sorted_entries:
            src_order = entry.get("source_order", 0)
            title = entry.get("title") or entry.get("source_title", "")
            content = entry.get("content") or entry.get("source_text", "")
            
            decision = self.classify_entry(title, content, source_order=src_order, work_id=work_id)

            item = dict(entry)
            item["source_order"] = src_order
            item["classification"] = decision.entry_type.value
            item["action"] = decision.action
            item["display_in_toc"] = decision.display_in_toc

            if decision.display_in_toc:
                item["display_order"] = current_display_order
                if decision.entry_type == EntryClassification.EXTRA:
                    ex_num = decision.extra_number or extra_counter
                    item["reader_title"] = f"Chương {current_display_order} (Ngoại Truyện {ex_num}): {entry.get('clean_title', title)}"
                    extra_counter += 1
                else:
                    clean_t = entry.get('clean_title') or title
                    # Format nicely: "Chương X: Tên"
                    sub_title = re.sub(r"^(Chapter|Chương)\s*\d+[:.\s-]*", "", clean_t, flags=re.IGNORECASE).strip()
                    if sub_title:
                        item["reader_title"] = f"Chương {current_display_order}: {sub_title}"
                    else:
                        item["reader_title"] = f"Chương {current_display_order}"
                current_display_order += 1
            else:
                item["display_order"] = None
                item["reader_title"] = f"Chương {src_order}: {decision.display_label}"

            results.append(item)

        return results
