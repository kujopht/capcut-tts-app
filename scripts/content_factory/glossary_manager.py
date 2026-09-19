"""
Persistent Translation Glossary Manager — Content Factory v2.

Maintains per-novel translation glossaries deterministically saved at:
  raw_spool/glossaries/<work_key>.json

Categories:
- character_names (Tên nhân vật)
- locations (Địa danh / Quốc gia / Vùng lãnh thổ)
- techniques (Chiêu thức / Nhẫn thuật / Kỹ năng)
- ranks_titles (Học vị / Cấp bậc / Chức vụ / Danh xưng)
- terminology (Thuật ngữ chuyên môn / Hệ thống sức mạnh)
- preferred_translations (Cụm từ / Phong cách dịch ưu tiên)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GLOSSARIES_DIR = PROJECT_ROOT / "raw_spool" / "glossaries"


class NovelGlossary(BaseModel):
    """Structured glossary for a novel or fanfic work."""
    work_key: str
    character_names: Dict[str, str] = Field(default_factory=dict)
    locations: Dict[str, str] = Field(default_factory=dict)
    techniques: Dict[str, str] = Field(default_factory=dict)
    ranks_titles: Dict[str, str] = Field(default_factory=dict)
    terminology: Dict[str, str] = Field(default_factory=dict)
    preferred_translations: Dict[str, str] = Field(default_factory=dict)
    notes: str = ""
    last_updated: Optional[str] = None

    def get_all_mappings(self) -> Dict[str, str]:
        """Returns unified mapping across all categories."""
        combined: Dict[str, str] = {}
        # Order of precedence: terminology -> techniques -> ranks_titles -> locations -> character_names -> preferred_translations
        combined.update(self.terminology)
        combined.update(self.techniques)
        combined.update(self.ranks_titles)
        combined.update(self.locations)
        combined.update(self.character_names)
        combined.update(self.preferred_translations)
        return combined


class GlossaryManager:
    """Manages reading, persisting, and applying translation glossaries."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or GLOSSARIES_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, work_key: str) -> Path:
        safe_key = re.sub(r"[^a-zA-Z0-9_\-]", "_", work_key.lower().strip())
        return self.base_dir / f"{safe_key}.json"

    def load_glossary(self, work_key: str) -> NovelGlossary:
        """Loads glossary for a given work key, or returns an empty initialized one."""
        path = self._get_path(work_key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return NovelGlossary(**data)
            except Exception:
                pass
        # Return default initialized glossary (pre-seed if recognized work)
        glossary = NovelGlossary(work_key=work_key)
        self._seed_default_terms_if_known(glossary, work_key)
        return glossary

    def save_glossary(self, work_key: str, glossary: NovelGlossary) -> Path:
        """Persists the glossary to disk atomically."""
        import datetime
        glossary.last_updated = datetime.datetime.now(datetime.timezone.utc).isoformat()
        path = self._get_path(work_key)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(glossary.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        tmp_path.replace(path)
        return path

    def add_term(
        self,
        work_key: str,
        category: str,
        original: str,
        translated: str,
        notes: str = ""
    ) -> NovelGlossary:
        """Adds or updates a term in a specified category."""
        glossary = self.load_glossary(work_key)
        target_dict = getattr(glossary, category, None)
        if target_dict is None or not isinstance(target_dict, dict):
            # fallback to preferred_translations
            glossary.preferred_translations[original.strip()] = translated.strip()
        else:
            target_dict[original.strip()] = translated.strip()

        if notes:
            if glossary.notes:
                glossary.notes += f"\n- {notes}"
            else:
                glossary.notes = notes

        self.save_glossary(work_key, glossary)
        return glossary

    def build_gemini_prompt_context(self, work_key: str) -> str:
        """Generates a structured prompt block for Gemini translation."""
        glossary = self.load_glossary(work_key)
        lines = []

        if glossary.character_names:
            names_str = ", ".join(f"{k} -> {v}" for k, v in sorted(glossary.character_names.items()))
            lines.append(f"- Nhân vật: {names_str}")

        if glossary.locations:
            loc_str = ", ".join(f"{k} -> {v}" for k, v in sorted(glossary.locations.items()))
            lines.append(f"- Địa danh: {loc_str}")

        if glossary.ranks_titles:
            ranks_str = ", ".join(f"{k} -> {v}" for k, v in sorted(glossary.ranks_titles.items()))
            lines.append(f"- Cấp bậc / Chức vị: {ranks_str}")

        if glossary.techniques:
            tech_str = ", ".join(f"{k} -> {v}" for k, v in sorted(glossary.techniques.items()))
            lines.append(f"- Chiêu thức / Thuật: {tech_str}")

        if glossary.terminology:
            terms_str = ", ".join(f"{k} -> {v}" for k, v in sorted(glossary.terminology.items()))
            lines.append(f"- Thuật ngữ: {terms_str}")

        if glossary.preferred_translations:
            pref_str = ", ".join(f"{k} -> {v}" for k, v in sorted(glossary.preferred_translations.items()))
            lines.append(f"- Bản dịch ưu tiên: {pref_str}")

        if not lines:
            return ""

        block = (
            "BẮT BUỘC TUÂN THỦ BẢNG THUẬT NGỮ (GLOSSARY) CỐ ĐỊNH SAU ĐÂY:\n"
            + "\n".join(lines)
            + "\nTuyệt đối không tự ý dịch lệch các danh xưng, tên riêng và thuật ngữ trên."
        )
        return block

    def apply_post_translation_consistency(self, text: str, work_key: str) -> str:
        """
        Applies deterministic post-translation replacements for critical terms
        where the LLM might have used an inconsistent variant.
        """
        glossary = self.load_glossary(work_key)
        mappings = glossary.get_all_mappings()
        if not mappings:
            return text

        result = text
        # Sort by key length descending to avoid partial prefix collisions
        sorted_pairs = sorted(mappings.items(), key=lambda x: len(x[0]), reverse=True)
        for original, translated in sorted_pairs:
            if not original or not translated or original == translated:
                continue
            # Match whole words only for ASCII alphanumeric keys
            if re.match(r"^[a-zA-Z0-9_\s]+$", original):
                pattern = r"\b" + re.escape(original) + r"\b"
                result = re.sub(pattern, translated, result, flags=re.IGNORECASE)

        return result

    def _seed_default_terms_if_known(self, glossary: NovelGlossary, work_key: str) -> None:
        """Pre-seeds standard glossaries for known universes / seed works."""
        key_lower = work_key.lower()
        if "hatake" in key_lower or "naruto" in key_lower:
            glossary.character_names.update({
                "Kakashi": "Kakashi",
                "Sakumo": "Sakumo",
                "White Fang": "Nanh Trắng",
                "Minato": "Minato",
                "Kushina": "Kushina",
                "Jiraiya": "Jiraiya",
                "Tsunade": "Tsunade",
                "Orochimaru": "Orochimaru",
                "Hiruzen": "Hiruzen",
                "Danzo": "Danzo",
                "Guy": "Guy",
                "Might Guy": "Might Guy",
                "Obito": "Obito",
                "Rin": "Rin",
            })
            glossary.locations.update({
                "Konoha": "Làng Lá",
                "Leaf Village": "Làng Lá",
                "Mộc Diệp": "Làng Lá",
                "Land of Fire": "Hỏa Quốc",
                "Hidden Leaf": "Làng Lá",
            })
            glossary.ranks_titles.update({
                "Hokage": "Hokage",
                "Jonin": "Thượng nhẫn",
                "Chunin": "Trung nhẫn",
                "Genin": "Hạ nhẫn",
                "Anbu": "Ám bộ",
                "Sannin": "Tam Nhẫn",
            })
            glossary.techniques.update({
                "Chidori": "Chidori",
                "Raikiri": "Raikiri",
                "Rasengan": "Rasengan",
                "Shadow Clone": "Ảnh Phân Thân Thuật",
                "Flying Raijin": "Phi Lôi Thần Thuật",
            })
            glossary.terminology.update({
                "Chakra": "Chakra",
                "Ninjutsu": "Nhẫn thuật",
                "Taijutsu": "Thể thuật",
                "Genjutsu": "Ảo thuật",
                "Sharingan": "Sharingan",
                "Byakugan": "Byakugan",
            })
        elif "one piece" in key_lower or "rocks" in key_lower:
            glossary.character_names.update({
                "Rocks": "Rocks",
                "Whitebeard": "Râu Trắng",
                "Kaido": "Kaido",
                "Big Mom": "Big Mom",
                "Roger": "Roger",
                "Garp": "Garp",
                "Sengoku": "Sengoku",
            })
            glossary.ranks_titles.update({
                "Yonko": "Tứ Hoàng",
                "Admiral": "Đô Đốc",
                "Fleet Admiral": "Thủy Sư Đô Đốc",
                "Vice Admiral": "Phó Đô Đốc",
            })
            glossary.terminology.update({
                "Haki": "Haki",
                "Conqueror's Haki": "Haki Bá Vương",
                "Armament Haki": "Haki Vũ Trang",
                "Observation Haki": "Haki Quan Sát",
                "Devil Fruit": "Trái Ác Quỷ",
            })
