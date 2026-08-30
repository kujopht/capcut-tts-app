"""
Privacy — Fanfic AI Chat V1 Phase 11.

Two concerns:
  - Retention: how long chat history is kept before it's eligible for
    deletion - a pure decision function, matching this repo's own "pure
    decision, store layer does the actual counting/deleting" convention
    (see `server/social.py::kiem_han_muc`'s module docstring for the same
    reasoning).
  - Log redaction: never write a full story excerpt or user question
    verbatim into logs - a short, bounded prefix is enough to debug with,
    matching `change_detection._an_toan`'s existing discipline in this
    repo (strip control characters, bound length).

Secrets never reaching a prompt is enforced by construction, not by a
redaction step here: `prompt_builder.build_prompt` only ever accepts a
question string, retrieval results, and optional selected text - there is
no code path anywhere in `server/chat/` that could pass a user's auth
token, a provider API key, or private profile metadata into it, because
none of those types are ever constructed from user/profile objects in
this package. See `server/tests/test_chat_security_adversarial_extra.py`
(added alongside `evaluation.py`) for a proof of this by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

#: Bound on any user-facing text mirrored into a log line - a log entry is
#: for debugging, never a content archive.
MAX_LOG_EXCERPT_CHARS = 100


@dataclass(frozen=True)
class RetentionPolicy:
    #: How long a conversation (and its messages) stays before it becomes
    #: eligible for deletion. 30 days is a reasonable default for a
    #: reading-companion chat feature - long enough to resume a
    #: conversation about a story across a normal reading session, short
    #: enough that this isn't an indefinite content archive.
    conversation_retention_days: int = 30


DEFAULT_RETENTION_POLICY = RetentionPolicy()


def is_expired(last_updated_at: datetime, *, policy: RetentionPolicy = DEFAULT_RETENTION_POLICY,
              now: Optional[datetime] = None) -> bool:
    """Pure decision - the actual delete is the store layer's job (same
    split as `kiem_han_muc`/the store that counts usage)."""
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=policy.conversation_retention_days)
    return last_updated_at < cutoff


def redact_for_logging(text: str, *, max_len: int = MAX_LOG_EXCERPT_CHARS) -> str:
    """Strip control characters (blocks log injection, same rule as
    `change_detection._an_toan`) and bound length - a log line gets
    enough to debug with, never a full story excerpt or user question."""
    printable = "".join(c for c in str(text) if c.isprintable())
    if len(printable) <= max_len:
        return printable
    return printable[:max_len] + "…"
