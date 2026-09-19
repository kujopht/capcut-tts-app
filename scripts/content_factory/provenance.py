"""
Content Provenance Models — Content Factory v2.

Enforces strict separation between:
1. IMPORTED_FANFIC: Real upstream works crawled from external websites.
   - Must retain source_platform, source_work_id, source_url, source_chapter_id,
     source_text_hash, source_status, and Living Novel sync identity.
2. AI_ORIGINAL: Works generated from topics or creative prompts.
   - Must NOT fabricate source URLs or upstream chapter identities.
   - Clearly marks provenance as AI-generated/AI-assisted internal content.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ProvenanceType(str, Enum):
    IMPORTED_FANFIC = "IMPORTED_FANFIC"
    AI_ORIGINAL = "AI_ORIGINAL"


class WorkProvenance(BaseModel):
    """Provenance tracking for a novel work."""
    provenance_type: ProvenanceType
    source_platform: str = Field(..., description="Platform name, e.g. 'royalroad', 'ao3', or 'fanfic_ai_studio'")
    source_work_id: str = Field(..., description="Source-specific identifier or AI internal work ID")
    canonical_source_url: str = Field(default="", description="Original upstream URL (empty for AI_ORIGINAL)")
    original_title: str
    original_author: str
    source_status: str = Field(default="ongoing", description="'ongoing' or 'completed'")
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    # Fields specific to AI_ORIGINAL
    creative_prompt: Optional[str] = None
    ai_model_used: Optional[str] = None

    @field_validator("canonical_source_url")
    @classmethod
    def validate_url(cls, v: str, info) -> str:
        prov = info.data.get("provenance_type")
        if prov == ProvenanceType.AI_ORIGINAL:
            # Do NOT fabricate source URLs for AI_ORIGINAL
            if v and v.startswith(("http://", "https://")):
                raise ValueError("AI_ORIGINAL works must not have fabricated external HTTP source URLs.")
            return ""
        elif prov == ProvenanceType.IMPORTED_FANFIC:
            if not v or not v.startswith(("http://", "https://")):
                raise ValueError("IMPORTED_FANFIC works must provide a valid canonical source URL.")
        return v.strip()


class ChapterProvenance(BaseModel):
    """Provenance tracking for a single chapter."""
    provenance_type: ProvenanceType
    chapter_order: int
    source_chapter_id: Optional[str] = None
    source_title: str
    source_text_hash: str
    source_url: str = ""
    is_ai_generated: bool = False
    ai_generation_timestamp: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def validate_chapter_url(cls, v: str, info) -> str:
        prov = info.data.get("provenance_type")
        if prov == ProvenanceType.AI_ORIGINAL:
            return ""
        return v.strip()
