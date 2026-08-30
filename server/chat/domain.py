"""
Fanfic AI Chat V1 — chat domain model.

Pure dataclasses, no ORM/DB coupling (persistence is the caller's job, same
principle as `server/scraper/change_detection.py`'s "this module only
classifies, it does not write anything"). Uses this repo's own established
terms (`novel_id`/`chapter_id`/`chapter_index` — see `web/src/lib/api.ts`'s
`NovelBrief`/`Chapter`), not the mission brief's generic "story", to stay
consistent with the existing reader/API surface instead of introducing a
second parallel vocabulary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class ChatScope(str, Enum):
    GENERAL = "general"
    THIS_CHAPTER = "this_chapter"
    THIS_STORY = "this_story"
    CHARACTER = "character"
    SEARCH = "search"
    RECOMMENDATION = "recommendation"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class UserReadingContext:
    """Where a user actually is in a novel right now — the SOLE input the
    anti-spoiler gate (`spoiler_gate.py`) trusts. Never derived from
    anything the user typed in a chat message; always looked up from the
    user's real reading-progress record by the caller before this object
    is constructed."""

    user_id: str
    novel_id: str
    #: 1-based, matching this repo's existing `Chapter.chapter_index`
    #: convention (see `web/src/lib/api.ts`). A user who has read chapters
    #: 1..N has `current_chapter_index = N`.
    current_chapter_index: int
    #: Explicit user opt-out, per the mission brief ("unless the user
    #: explicitly disables spoiler protection") — default ON. Never
    #: inferred, never defaulted to off.
    spoiler_protection_enabled: bool = True


@dataclass(frozen=True)
class ChatContext:
    """Everything about THIS turn that isn't the question text itself."""

    user_reading_context: UserReadingContext
    scope: ChatScope
    #: Chapter the user is currently reading FROM (THIS_CHAPTER scope) —
    #: distinct from `current_chapter_index`, which is progress, not
    #: "where they clicked Ask AI from" (a user can ask about chapter 3
    #: while their overall progress is chapter 87).
    active_chapter_id: Optional[str] = None
    #: User-selected text from the reader, for "Explain this paragraph" -
    #: untrusted content, same as any retrieved chapter text (see
    #: `prompt_builder.py`).
    selected_text: Optional[str] = None
    #: Character name hint for CHARACTER scope ("Who is X?") - a plain
    #: string, not yet resolved to any canonical entity.
    character_hint: Optional[str] = None


@dataclass(frozen=True)
class RetrievalResult:
    """One retrieved chunk, already past the spoiler gate and ranking -
    this is what a citation gets built FROM, never anything else."""

    novel_id: str
    chapter_id: str
    #: 1-based chapter number this chunk came from - the field the
    #: spoiler gate filters on (see `spoiler_gate.enforce_spoiler_boundary`).
    chapter_index: int
    chapter_title: str
    chunk_text: str
    #: Position of this chunk within its chapter's own chunk sequence -
    #: NOT a global index, matches `chunking.ChunkRecord.chunk_order`.
    chunk_order: int
    similarity_score: float
    #: sha256 of the chunk's own source content - lets a caller tell
    #: whether a cited chunk is still the current version of that text.
    content_hash: str
    language: str = ""


@dataclass(frozen=True)
class Citation:
    """UI-facing citation - built ONLY from a `RetrievalResult` that
    actually contributed to an answer, never fabricated. `excerpt` is
    intentionally short (a citation is a pointer, not a content mirror)."""

    novel_id: str
    chapter_id: str
    chapter_index: int
    chapter_title: str
    excerpt: str
    chunk_order: int


@dataclass
class ChatMessage:
    message_id: str
    conversation_id: str
    #: "user" | "assistant" | "system" - a plain string, not an enum, to
    #: match how this repo's other simple status fields work (e.g.
    #: `run_state.ScrapeItemStatus` is the exception that IS an enum
    #: because it drives a real state machine; a chat message role does
    #: not, so a plain string is the honest choice here).
    role: str
    content: str
    created_at: str = field(default_factory=_now_iso)
    #: Empty for user/system messages - only ever populated on an
    #: assistant message, and only from real `Citation`s the pipeline
    #: actually built (see `citation.py`).
    citations: List[Citation] = field(default_factory=list)


@dataclass
class ChatConversation:
    conversation_id: str
    user_id: str
    scope: ChatScope
    #: None for GENERAL/RECOMMENDATION scope (not tied to one novel).
    novel_id: Optional[str] = None
    title: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
