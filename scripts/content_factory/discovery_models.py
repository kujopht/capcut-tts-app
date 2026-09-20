"""
Discovery Mode Models — Content Factory v2.

Pydantic models for read-only fiction discovery, deterministic filtering,
and Gemini candidate evaluation.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateState(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    INSPECTED = "INSPECTED"
    WATCHLISTED = "WATCHLISTED"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"  # Added to local pipeline intake only; never publishes automatically


class DeterministicFilterConfig(BaseModel):
    min_chapters: int = 5
    min_words: int = 15000
    max_days_abandoned: int = 365  # Ignored if novel is marked COMPLETED
    reject_inaccessible: bool = True
    reject_already_in_production: bool = True
    reject_previously_rejected: bool = True


class DeterministicFilterResult(BaseModel):
    passed: bool
    rejection_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class GeminiCandidateEvaluation(BaseModel):
    story_quality: float = 0.0      # 0 - 10
    fandom_fit: float = 0.0         # 0 - 10
    translation_value: float = 0.0  # 0 - 10
    catalog_uniqueness: float = 0.0 # 0 - 10
    update_health: float = 0.0      # 0 - 10
    crawlability: float = 0.0       # 0 - 10
    overall_score: float = 0.0      # 0 - 10 (weighted average)
    reasons: str = ""
    risks: str = ""
    potential_translation_issues: List[str] = Field(default_factory=list)
    recommended_for_owner_review: bool = False
    model_used: str = "gemini-3.8-flash-high"
    account_used: Optional[str] = None


class DiscoveredCandidate(BaseModel):
    source_platform: str = "royalroad"
    source_work_id: str
    url: str
    title: str
    author: str = "Unknown Author"
    description: str = ""
    status: str = "ongoing"  # ongoing, completed, hiatus, stub
    chapter_count: int = 0
    estimated_word_count: int = 0
    last_update: str = ""   # ISO string or human-readable
    tags: List[str] = Field(default_factory=list)
    fandom: str = "Fanfiction"
    rating: float = 0.0     # 0.0 - 5.0 from RoyalRoad
    followers: int = 0
    views: int = 0
    pages: int = 0
    avg_chapter_words: int = 0
    crawlability_status: str = "OK"  # OK, CLOUDFLARE_BLOCKED, PARSE_ERROR, NOT_FOUND
    cover_url: str = ""

    # Processing State
    state: CandidateState = CandidateState.DISCOVERED
    rejection_reasons: List[str] = Field(default_factory=list)

    # Evaluation
    deterministic_passed: bool = True
    gemini_eval: Optional[GeminiCandidateEvaluation] = None
    overall_score: float = 0.0

    # Economics estimation
    estimated_translation_cost_usd: float = 0.0
    estimated_tts_hours: float = 0.0

    discovered_at: str = ""
    evaluated_at: Optional[str] = None

    def calculate_estimates(self):
        """Computes average chapter words, translation size and TTS duration."""
        if self.pages > 0 and self.estimated_word_count == 0:
            self.estimated_word_count = self.pages * 275  # ~275 words per standard RR page
        if self.chapter_count > 0 and self.estimated_word_count > 0:
            self.avg_chapter_words = int(self.estimated_word_count / self.chapter_count)
        # Vietnamese Piper / CapCut TTS typically speaks at 150 words per minute (9,000 words per hour)
        if self.estimated_word_count > 0:
            self.estimated_tts_hours = round(self.estimated_word_count / 9000.0, 1)
            # Rough API estimate: ~0.00015 USD per 1000 input/output words for Flash
            self.estimated_translation_cost_usd = round((self.estimated_word_count / 1000.0) * 0.0003, 2)
