"""
In-process, TTL-bounded conversation/message cache — Fanfic AI Assistant
V1 §5, `memory_enabled=false` semantics: "hội thoại mới không được lưu quá
phiên (chỉ giữ trong bộ nhớ tiến trình tối đa 1 giờ)".

`EphemeralConversationStore` NEVER touches `AiRepo`/Appwrite — it is a
plain in-process dict, bounded on TWO axes so a long-running instance with
many memory-off users can't grow without bound:
  - TTL per conversation (default 1 h, refreshed on every read/write —
    "touch"), enforced by lazily purging expired entries.
  - Total conversation count (default 500) — oldest-inserted evicted first
    once the cap is hit, independent of TTL (a defensive backstop, not the
    primary bound).
  - Messages per conversation (default 200) — oldest messages dropped
    first once a single conversation's own history gets long.

This is intentionally NOT a general-purpose cache: it only ever stores
`AiConversation`/`AiMessage` objects already built by
`server/ai_assistant/routes.py`, and only for turns where a request has
already established `memory_enabled=False` for that user at that moment —
routing that decision is `routes.py`'s job, not this module's.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from server.ai_assistant.memory import AiConversation, AiMessage

DEFAULT_TTL_SECONDS = 3600.0
DEFAULT_MAX_CONVERSATIONS = 500
DEFAULT_MAX_MESSAGES_PER_CONVERSATION = 200


@dataclass
class _Entry:
    conversation: AiConversation
    messages: List[AiMessage] = field(default_factory=list)
    expires_at: float = 0.0


class EphemeralConversationStore:
    def __init__(self, *, ttl_seconds: float = DEFAULT_TTL_SECONDS,
                max_conversations: int = DEFAULT_MAX_CONVERSATIONS,
                max_messages: int = DEFAULT_MAX_MESSAGES_PER_CONVERSATION,
                clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._max_conversations = max_conversations
        self._max_messages = max_messages
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: Dict[str, _Entry] = {}
        self._order: List[str] = []  # insertion order, for size-based eviction

    # -- internal, caller already holds self._lock -------------------------
    def _purge_expired_locked(self) -> None:
        now = self._clock()
        expired = [cid for cid, e in self._entries.items() if e.expires_at < now]
        for cid in expired:
            self._entries.pop(cid, None)
            if cid in self._order:
                self._order.remove(cid)

    def _touch_locked(self, cid: str) -> None:
        self._entries[cid].expires_at = self._clock() + self._ttl

    def _evict_if_needed_locked(self) -> None:
        while len(self._entries) > self._max_conversations and self._order:
            oldest = self._order.pop(0)
            self._entries.pop(oldest, None)

    # -- conversations -------------------------------------------------------
    def create_conversation(self, conv: AiConversation) -> AiConversation:
        with self._lock:
            self._purge_expired_locked()
            self._entries[conv.conversation_id] = _Entry(
                conversation=conv, expires_at=self._clock() + self._ttl)
            self._order.append(conv.conversation_id)
            self._evict_if_needed_locked()
        return conv

    def get_conversation(self, conversation_id: str) -> Optional[AiConversation]:
        with self._lock:
            self._purge_expired_locked()
            entry = self._entries.get(conversation_id)
            if entry is None:
                return None
            self._touch_locked(conversation_id)
            return entry.conversation

    def list_conversations(self, user_id: str) -> List[AiConversation]:
        with self._lock:
            self._purge_expired_locked()
            return [e.conversation for e in self._entries.values()
                    if e.conversation.user_id == user_id and not e.conversation.archived]

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._entries.pop(conversation_id, None)
            if conversation_id in self._order:
                self._order.remove(conversation_id)

    # -- messages ------------------------------------------------------------
    def create_message(self, m: AiMessage) -> AiMessage:
        with self._lock:
            self._purge_expired_locked()
            entry = self._entries.get(m.conversation_id)
            if entry is None:
                # The conversation itself already expired/was evicted — the
                # message is dropped silently, same as any other data past
                # its TTL in this store (by design: nothing durable to fall
                # back to for a memory-off conversation).
                return m
            entry.messages.append(m)
            if len(entry.messages) > self._max_messages:
                entry.messages = entry.messages[-self._max_messages:]
            entry.conversation.message_count = len(entry.messages)
            entry.conversation.updated_at = m.created_at
            self._touch_locked(m.conversation_id)
        return m

    def list_messages(self, conversation_id: str, *, limit: int = 50) -> List[AiMessage]:
        with self._lock:
            self._purge_expired_locked()
            entry = self._entries.get(conversation_id)
            if entry is None:
                return []
            self._touch_locked(conversation_id)
            return list(entry.messages[-limit:])

    # -- bulk ------------------------------------------------------------------
    def delete_all_for_user(self, user_id: str) -> None:
        with self._lock:
            for cid in [cid for cid, e in self._entries.items()
                       if e.conversation.user_id == user_id]:
                self._entries.pop(cid, None)
                if cid in self._order:
                    self._order.remove(cid)

    def size(self) -> int:
        """Test/diagnostic hook — number of live (unexpired as of last
        touch) conversations currently held. Never exposed to any route."""
        return len(self._entries)
