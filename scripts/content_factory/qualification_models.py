"""
Qualification Models — Content Factory v2.

Pydantic models for deep candidate qualification:
- 3-chapter sampling (first, middle, latest narrative).
- Writing quality, dialogue, and prose inspection.
- Crawler cleanliness verification (no comments, footers, navigation).
- 600–1000 word translation trial with candidate-isolated glossary.
- Realistic local factory scale and throughput estimates.
- Standardized factual qualification flags.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class GlossaryComplexity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AuthorNoteDensity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FormatComplexity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ProductionScale(str, enum.Enum):
    COMPACT = "COMPACT"       # < 50 chapters (< 150k words)
    MEDIUM = "MEDIUM"         # 50 - 150 chapters (150k - 500k words)
    LARGE = "LARGE"           # 150 - 400 chapters (500k - 1.2M words)
    MASSIVE = "MASSIVE"       # > 400 chapters (> 1.2M words)


class SampleChapterInspection(BaseModel):
    order: int
    title: str
    url: str
    word_count: int
    character_count: int
    paragraph_count: int
    avg_paragraph_words: float
    dialogue_ratio: float  # Estimated percentage of dialogue vs narration
    author_commentary_detected: bool = False
    stat_blocks_or_tables_detected: bool = False
    unusual_layout_issues: List[str] = Field(default_factory=list)
    naruto_terms_found: List[str] = Field(default_factory=list)
    crawler_clean: bool = True  # True if no comments, nav, reviews, footers leaked
    clean_ending_preview: str = ""


class WritingQualityAnalysis(BaseModel):
    prose_coherence: str = "Tốt"
    dialogue_quality: str = "Tự nhiên"
    grammar_level: str = "Chuẩn"
    ai_repetition_detected: bool = False
    pov_consistency: str = "Nhất quán"
    translation_difficulty: str = "Trung bình"
    summary_observations: str = ""


class TranslationTrialResult(BaseModel):
    source_chapter_order: int
    source_chapter_title: str
    source_excerpt_words: int
    source_excerpt: str
    translated_vietnamese: str
    isolated_glossary: Dict[str, str] = Field(default_factory=dict)
    vietnamese_naturalness: float = 8.5
    character_name_consistency: float = 9.0
    fandom_terminology_accuracy: float = 9.0
    dialogue_readability: float = 8.5
    meaning_preserved: bool = True
    manual_editing_requirement: str = "LOW"  # LOW | MEDIUM | HIGH
    evaluation_notes: str = ""


class RealisticProductionScale(BaseModel):
    sampled_avg_words_per_chapter: int
    total_chapters: int
    estimated_total_source_words: int
    estimated_vietnamese_words: int
    estimated_tts_hours: float
    estimated_storage_mb: float
    approximate_processing_days: float
    throughput_notes: str = ""


class CandidateQualificationReport(BaseModel):
    source_work_id: str
    title: str
    source_platform: str = "royalroad"
    url: str
    inspected_chapters: List[SampleChapterInspection] = Field(default_factory=list)
    writing_quality: WritingQualityAnalysis = Field(default_factory=WritingQualityAnalysis)
    translation_trial: Optional[TranslationTrialResult] = None
    scale_estimate: RealisticProductionScale
    factual_flags: Dict[str, Any] = Field(default_factory=dict)
    qualified_at: str = ""

    def summary_badge(self) -> str:
        flags = self.factual_flags
        scale = flags.get("PRODUCTION_SCALE", "MEDIUM")
        t_ok = "✅ DỊCH TỐT" if flags.get("TRANSLATION_QUALITY_OK") else "⚠️ CẦN EDIT"
        c_ok = "✅ CRAWLER CHUẨN" if flags.get("CRAWLER_COMPATIBLE") else "❌ CRAWLER LỖI"
        return f"{c_ok} | {t_ok} | Quy mô: {scale}"
