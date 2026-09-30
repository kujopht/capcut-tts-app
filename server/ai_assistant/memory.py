"""
AI Assistant memory/storage — Fanfic AI Assistant V1 §5.

`AiRepo` ABC + `InMemoryAiRepo` (dev/test) + `AppwriteAiRepo` (production,
gated behind `FAS_AI_ASSISTANT_V1` and never applied to a live schema by
this mission — see `scripts/setup_appwrite.py`). Same repo-pattern split as
`server/messaging/{repository,appwrite}.py`: one Protocol/ABC, an in-memory
mock with identical semantics, and a real Appwrite-backed implementation —
DELIBERATELY simplified here to the Legacy Appwrite 1.9.6 documents API
ONLY (`/v1/databases/{db}/collections/{c}/documents`), matching this
project's actual production Appwrite version — messaging's dual
Legacy/TablesDB split exists because Chat V1 also targets a 2.x staging
tier that this feature does not (see docs/ai/AI_ASSISTANT_V1.md
"Implementation notes" for this and other deliberate simplifications).

Data policy (§5, enforced HERE, not just described):
  - Every message's `content` is passed through `secret_redaction` before
    it is persisted — mirrors the exact policy already used for logging.
  - `memory_enabled=false`: conversations/messages for that user are kept
    ONLY in an in-process, TTL-bounded cache (`_EphemeralStore`, default
    1 hour) — never reach durable storage, whichever repo is in use.
  - `delete_all_memory` removes conversations+messages+summaries+
    preferences; projects survive unless `include_projects=True`.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from server.secret_redaction import loc_bo_theo_gia_tri, thong_diep_loi_an_toan


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(text: str) -> str:
    """Secret-shaped substrings -> `<redacted>` — applied before ANYTHING
    is persisted or sent to a provider (contract §5)."""
    return loc_bo_theo_gia_tri(text or "")


class RepoConflict(Exception):
    def __init__(self, key: str):
        super().__init__(f"Đã tồn tại: {key}")
        self.key = key


# --------------------------------------------------------------------- domain


@dataclass
class AiConversation:
    conversation_id: str
    user_id: str
    mode: str
    title: str = ""
    context_novel_id: str = ""
    context_chapter_id: str = ""
    context_project_id: str = ""
    #: L12 (review finding): `ContextIn.current_chapter_index` was silently
    #: ignored (retrieval was always called with a hard-coded `1`,
    #: defeating the spoiler-protection chapter cutoff for anyone reading
    #: past chapter 1) — the value now actually reaches `AiConversation` at
    #: creation time and is read back by `retrieve_story_chunks`.
    context_chapter_index: int = 1
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    message_count: int = 0
    archived: bool = False


@dataclass
class AiMessage:
    message_id: str
    conversation_id: str
    user_id: str
    role: str  # "user" | "assistant"
    content: str
    status: str = "complete"  # complete | stopped | error
    citations_json: str = ""
    provider_name: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: str = field(default_factory=now_iso)
    client_id: str = ""


@dataclass
class AiSummary:
    conversation_id: str
    user_id: str
    summary: str = ""
    covers_until_message_id: str = ""
    updated_at: str = field(default_factory=now_iso)


@dataclass
class AiPreferences:
    user_id: str
    memory_enabled: bool = True
    preferences_json: str = "{}"
    updated_at: str = field(default_factory=now_iso)


@dataclass
class AiProject:
    project_id: str
    user_id: str
    title: str = ""
    premise: str = ""
    outline_json: str = "{}"
    characters_json: str = "{}"
    world_json: str = "{}"
    notes: str = ""
    updated_at: str = field(default_factory=now_iso)


@dataclass
class AiUsageDay:
    """Counters ONLY — no message/prompt content anywhere in this record,
    by construction (there is no field for it). This is intentional and is
    why usage metering keeps recording even for a user with
    `memory_enabled=False` (contract §5/§9): counting tokens/requests is
    not "remembering what was said", and the privacy guarantee that
    matters (no content persisted) holds either way."""

    user_id: str
    day: str  # "yyyymmdd"
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    updated_at: str = field(default_factory=now_iso)


@dataclass
class AiEscalation:
    escalation_id: str
    user_id: str
    conversation_id: str
    summary: str
    diagnostics_json: str = "{}"
    status: str = "open"
    created_at: str = field(default_factory=now_iso)


class AiRepo:
    """Duck-typed contract (kept as a plain base class, not `abc.ABC`, to
    match `server/messaging/repository.py::ChatRepository`'s own
    `Protocol`-flavored style) — `InMemoryAiRepo`/`AppwriteAiRepo` implement
    every method below."""

    # conversations
    def create_conversation(self, c: AiConversation) -> AiConversation: ...
    def get_conversation(self, conversation_id: str) -> Optional[AiConversation]: ...
    def list_conversations(self, user_id: str, *, limit: int = 30,
                           cursor: Optional[str] = None) -> List[AiConversation]: ...
    def update_conversation(self, conversation_id: str, fields: Dict[str, Any]) -> AiConversation: ...
    def delete_conversation(self, conversation_id: str) -> None: ...
    def count_conversations(self, user_id: str) -> int: ...
    # messages
    def create_message(self, m: AiMessage) -> AiMessage: ...
    def list_messages(self, conversation_id: str, *, before_id: Optional[str] = None,
                      limit: int = 30) -> List[AiMessage]: ...
    # summaries
    def get_summary(self, conversation_id: str) -> Optional[AiSummary]: ...
    def put_summary(self, s: AiSummary) -> AiSummary: ...
    # preferences
    def get_preferences(self, user_id: str) -> Optional[AiPreferences]: ...
    def put_preferences(self, p: AiPreferences) -> AiPreferences: ...
    # projects
    def create_project(self, p: AiProject) -> AiProject: ...
    def get_project(self, project_id: str) -> Optional[AiProject]: ...
    def list_projects(self, user_id: str) -> List[AiProject]: ...
    def update_project(self, project_id: str, fields: Dict[str, Any]) -> AiProject: ...
    def delete_project(self, project_id: str) -> None: ...
    # usage
    def get_usage_day(self, user_id: str, day: str) -> Optional[AiUsageDay]: ...
    def increment_usage(self, user_id: str, day: str, *, input_tokens: int,
                        output_tokens: int) -> AiUsageDay: ...
    def count_usage_users(self, day: str) -> Optional[int]:
        """Distinct users with any AI usage on `day` (admin overview metric)."""
        ...
    # escalations
    def create_escalation(self, e: AiEscalation) -> AiEscalation: ...
    # bulk delete
    def delete_all_memory(self, user_id: str, *, include_projects: bool = False) -> None: ...


class _TTLCache:
    """Process-memory-only, TTL-bounded — backs `memory_enabled=False`
    conversations (contract §5: "chỉ giữ trong bộ nhớ tiến trình tối đa 1
    giờ"). Never touches durable storage."""

    def __init__(self, *, ttl_seconds: float = 3600.0):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}

    def _purge(self) -> None:
        now = time.monotonic()
        for key in [k for k, exp in self._expiry.items() if exp < now]:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._purge()
            self._data[key] = value
            self._expiry[key] = time.monotonic() + self._ttl

    def get(self, key: str) -> Any:
        with self._lock:
            self._purge()
            return self._data.get(key)

    def pop(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._expiry.pop(key, None)


class InMemoryAiRepo(AiRepo):
    """Reference implementation for dev/test — real semantics (conflict on
    duplicate id, ordering, cascade delete), no persistence beyond process
    lifetime regardless of `memory_enabled`."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conversations: Dict[str, AiConversation] = {}
        self._messages: Dict[str, AiMessage] = {}
        self._summaries: Dict[str, AiSummary] = {}
        self._preferences: Dict[str, AiPreferences] = {}
        self._projects: Dict[str, AiProject] = {}
        self._usage: Dict[str, AiUsageDay] = {}
        self._escalations: Dict[str, AiEscalation] = {}
        self._seq: Dict[str, int] = {}

    def _order(self, mid: str) -> int:
        return self._seq.setdefault(mid, len(self._seq))

    # conversations
    def create_conversation(self, c: AiConversation) -> AiConversation:
        with self._lock:
            if c.conversation_id in self._conversations:
                raise RepoConflict(c.conversation_id)
            self._conversations[c.conversation_id] = c
        return c

    def get_conversation(self, conversation_id: str) -> Optional[AiConversation]:
        with self._lock:
            return self._conversations.get(conversation_id)

    def list_conversations(self, user_id: str, *, limit: int = 30,
                           cursor: Optional[str] = None) -> List[AiConversation]:
        with self._lock:
            items = [c for c in self._conversations.values()
                     if c.user_id == user_id and not c.archived]
        items.sort(key=lambda c: c.updated_at, reverse=True)
        if cursor:
            ids = [c.conversation_id for c in items]
            if cursor in ids:
                items = items[ids.index(cursor) + 1:]
        return items[:limit]

    def update_conversation(self, conversation_id: str, fields: Dict[str, Any]) -> AiConversation:
        with self._lock:
            c = self._conversations[conversation_id]
            for k, v in fields.items():
                setattr(c, k, v)
            c.updated_at = now_iso()
            return c

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._conversations.pop(conversation_id, None)
            self._summaries.pop(conversation_id, None)
            for mid in [m for m, msg in self._messages.items()
                       if msg.conversation_id == conversation_id]:
                self._messages.pop(mid, None)

    def count_conversations(self, user_id: str) -> int:
        with self._lock:
            return sum(1 for c in self._conversations.values() if c.user_id == user_id)

    # messages
    def create_message(self, m: AiMessage) -> AiMessage:
        with self._lock:
            if m.message_id in self._messages:
                raise RepoConflict(m.message_id)
            self._messages[m.message_id] = m
            self._order(m.message_id)
            conv = self._conversations.get(m.conversation_id)
            if conv is not None:
                conv.message_count += 1
                conv.updated_at = now_iso()
        return m

    def list_messages(self, conversation_id: str, *, before_id: Optional[str] = None,
                      limit: int = 30) -> List[AiMessage]:
        with self._lock:
            items = [m for m in self._messages.values() if m.conversation_id == conversation_id]
        items.sort(key=lambda m: self._order(m.message_id))
        if before_id:
            ids = [m.message_id for m in items]
            if before_id in ids:
                items = items[:ids.index(before_id)]
        return items[-limit:]

    # summaries
    def get_summary(self, conversation_id: str) -> Optional[AiSummary]:
        with self._lock:
            return self._summaries.get(conversation_id)

    def put_summary(self, s: AiSummary) -> AiSummary:
        with self._lock:
            self._summaries[s.conversation_id] = s
        return s

    # preferences
    def get_preferences(self, user_id: str) -> Optional[AiPreferences]:
        with self._lock:
            return self._preferences.get(user_id)

    def put_preferences(self, p: AiPreferences) -> AiPreferences:
        with self._lock:
            self._preferences[p.user_id] = p
        return p

    # projects
    def create_project(self, p: AiProject) -> AiProject:
        with self._lock:
            if p.project_id in self._projects:
                raise RepoConflict(p.project_id)
            self._projects[p.project_id] = p
        return p

    def get_project(self, project_id: str) -> Optional[AiProject]:
        with self._lock:
            return self._projects.get(project_id)

    def list_projects(self, user_id: str) -> List[AiProject]:
        with self._lock:
            items = [p for p in self._projects.values() if p.user_id == user_id]
        return sorted(items, key=lambda p: p.updated_at, reverse=True)

    def update_project(self, project_id: str, fields: Dict[str, Any]) -> AiProject:
        with self._lock:
            p = self._projects[project_id]
            for k, v in fields.items():
                setattr(p, k, v)
            p.updated_at = now_iso()
            return p

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            self._projects.pop(project_id, None)

    # usage
    def get_usage_day(self, user_id: str, day: str) -> Optional[AiUsageDay]:
        with self._lock:
            return self._usage.get(f"{user_id}_{day}")

    def count_usage_users(self, day: str) -> Optional[int]:
        with self._lock:
            return sum(1 for u in self._usage.values() if u.day == day)

    def increment_usage(self, user_id: str, day: str, *, input_tokens: int,
                        output_tokens: int) -> AiUsageDay:
        key = f"{user_id}_{day}"
        with self._lock:
            u = self._usage.get(key) or AiUsageDay(user_id=user_id, day=day)
            u.requests += 1
            u.input_tokens += input_tokens
            u.output_tokens += output_tokens
            u.updated_at = now_iso()
            self._usage[key] = u
            return u

    # escalations
    def create_escalation(self, e: AiEscalation) -> AiEscalation:
        with self._lock:
            if e.escalation_id in self._escalations:
                raise RepoConflict(e.escalation_id)
            self._escalations[e.escalation_id] = e
        return e

    # bulk delete
    def delete_all_memory(self, user_id: str, *, include_projects: bool = False) -> None:
        with self._lock:
            for cid in [c for c, conv in self._conversations.items() if conv.user_id == user_id]:
                self.delete_conversation(cid)
            self._preferences.pop(user_id, None)
            if include_projects:
                for pid in [p for p, proj in self._projects.items() if proj.user_id == user_id]:
                    self._projects.pop(pid, None)


# =============================================================================== Appwrite


class AiUnavailable(Exception):
    """Appwrite unreachable/misconfigured — maps to 503 at the route layer,
    same convention as `server/messaging/domain.py::ChatUnavailable`."""


T_CONV, T_MSG, T_SUM, T_PREF, T_PROJ, T_USAGE, T_ESC = (
    "ai_conversations", "ai_messages", "ai_summaries", "ai_preferences",
    "ai_projects", "ai_usage_daily", "ai_support_escalations")

_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class _Loi(Exception):
    def __init__(self, status: int, body: Any):
        super().__init__(thong_diep_loi_an_toan(body, status_code=status))
        self.status = status


class AppwriteAiRepo(AiRepo):
    """Appwrite 1.9.6 self-hosted (production version), Legacy documents
    API ONLY — see module docstring for why this feature does not also
    implement the TablesDB/Cloud-2.x variant `server/messaging/appwrite.py`
    has. `documentSecurity=True`, collection-level `permissions=[]` (no one
    but the server, using its API key, can read/write any row) — matches
    `scripts/setup_appwrite.py::COLLECTION_PERMISSIONS`."""

    def __init__(self, settings: Any, *, client: Optional[httpx.Client] = None) -> None:
        aw = settings.appwrite if hasattr(settings, "appwrite") else settings
        if not (aw.endpoint and aw.project_id and aw.api_key and aw.database_id):
            raise AiUnavailable("Appwrite chưa cấu hình đủ cho AI Assistant.")
        self._base = aw.api_base
        self._db = aw.database_id
        self._headers = {"X-Appwrite-Project": aw.project_id, "X-Appwrite-Key": aw.api_key,
                         "Content-Type": "application/json"}
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    # ------------------------------------------------------------- plumbing
    def _call(self, method: str, path: str, *, body: Any = None,
              queries: Optional[List[str]] = None) -> Any:
        url = f"{self._base}{path}"
        if queries:
            url += "?" + "&".join("queries[]=" + quote(q) for q in queries)
        try:
            r = self._client.request(method, url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise AiUnavailable("Không kết nối được kho AI Assistant.") from exc
        if r.status_code >= 400:
            body_json = None
            try:
                body_json = r.json()
            except ValueError:
                pass
            if r.status_code == 429 or r.status_code >= 500:
                raise AiUnavailable("Kho AI Assistant đang bận — thử lại sau.")
            raise _Loi(r.status_code, body_json)
        return r.json() if r.content else {}

    def _q(self, method: str, attribute: Optional[str] = None, values: Optional[List[Any]] = None) -> str:
        d: Dict[str, Any] = {"method": method}
        if attribute is not None:
            d["attribute"] = attribute
        if values is not None:
            d["values"] = values
        return json.dumps(d, separators=(",", ":"))

    def _collection(self, t: str) -> str:
        return f"/v1/databases/{self._db}/collections/{t}/documents"

    def _get(self, t: str, doc_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self._call("GET", f"{self._collection(t)}/{quote(doc_id)}")
        except _Loi as exc:
            if exc.status == 404:
                return None
            raise AiUnavailable("Không đọc được kho AI Assistant.") from exc

    def _create(self, t: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._call("POST", self._collection(t),
                              body={"documentId": doc_id, "data": data, "permissions": []})
        except _Loi as exc:
            if exc.status == 409:
                raise RepoConflict(doc_id) from exc
            raise AiUnavailable("Không ghi được vào kho AI Assistant.") from exc

    def _update(self, t: str, doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._call("PATCH", f"{self._collection(t)}/{quote(doc_id)}", body={"data": data})
        except _Loi as exc:
            raise AiUnavailable("Không cập nhật được kho AI Assistant.") from exc

    def _delete(self, t: str, doc_id: str) -> None:
        try:
            self._call("DELETE", f"{self._collection(t)}/{quote(doc_id)}")
        except _Loi as exc:
            if exc.status != 404:
                raise AiUnavailable("Không xoá được khỏi kho AI Assistant.") from exc

    def _list(self, t: str, queries: List[str]) -> List[Dict[str, Any]]:
        try:
            b = self._call("GET", self._collection(t), queries=queries)
        except _Loi as exc:
            raise AiUnavailable("Không đọc được kho AI Assistant.") from exc
        return b.get("documents") or []

    # ------------------------------------------------------------- mapping
    @staticmethod
    def _conv_to_row(c: AiConversation) -> Dict[str, Any]:
        # H5 (review finding): `context_novel_id`/`context_chapter_id`/
        # `context_project_id` are `size=64` Appwrite attributes
        # (`scripts/setup_appwrite.py`) — truncated HERE too (routes.py
        # already bounds them at the API boundary) so this repo can never
        # hand Appwrite an over-length value and turn a would-be 400 into
        # an uncaught `AiUnavailable` -> 500 for ANY caller that builds an
        # `AiConversation` directly (tests, future callers).
        return {"user_id": c.user_id, "mode": c.mode, "title": redact(c.title)[:120],
                "context_novel_id": c.context_novel_id[:64], "context_chapter_id": c.context_chapter_id[:64],
                "context_project_id": c.context_project_id[:64],
                "context_chapter_index": int(c.context_chapter_index or 1),
                "created_at": c.created_at,
                "updated_at": c.updated_at, "message_count": c.message_count, "archived": c.archived}

    @staticmethod
    def _row_to_conv(r: Dict[str, Any]) -> AiConversation:
        return AiConversation(
            conversation_id=str(r.get("$id") or ""), user_id=str(r.get("user_id") or ""),
            mode=str(r.get("mode") or "general"), title=str(r.get("title") or ""),
            context_novel_id=str(r.get("context_novel_id") or ""),
            context_chapter_id=str(r.get("context_chapter_id") or ""),
            context_project_id=str(r.get("context_project_id") or ""),
            context_chapter_index=int(r.get("context_chapter_index") or 1),
            created_at=str(r.get("created_at") or ""), updated_at=str(r.get("updated_at") or ""),
            message_count=int(r.get("message_count") or 0), archived=bool(r.get("archived")))

    # ------------------------------------------------------------- conversations
    def create_conversation(self, c: AiConversation) -> AiConversation:
        self._create(T_CONV, c.conversation_id, self._conv_to_row(c))
        return c

    def get_conversation(self, conversation_id: str) -> Optional[AiConversation]:
        r = self._get(T_CONV, conversation_id)
        return self._row_to_conv(r) if r else None

    def list_conversations(self, user_id: str, *, limit: int = 30,
                           cursor: Optional[str] = None) -> List[AiConversation]:
        qs = [self._q("equal", "user_id", [user_id]), self._q("equal", "archived", [False]),
              self._q("orderDesc", "updated_at"), self._q("limit", values=[int(limit)])]
        if cursor:
            qs.append(self._q("cursorAfter", values=[cursor]))
        return [self._row_to_conv(r) for r in self._list(T_CONV, qs)]

    def update_conversation(self, conversation_id: str, fields: Dict[str, Any]) -> AiConversation:
        fields = dict(fields)
        fields["updated_at"] = now_iso()
        r = self._update(T_CONV, conversation_id, fields)
        return self._row_to_conv(r)

    def _delete_all_matching(self, t: str, *, attribute: str, value: str, page_size: int = 100) -> None:
        """H6 (review finding): repeatedly deletes the FIRST `page_size`
        documents still matching `attribute == value` until none are left
        — no cursor bookkeeping needed (unlike a cursor-based "next page",
        this is safe against Appwrite's requirement that a `cursorAfter`
        document still exist: here every deleted document simply drops out
        of the NEXT identical query on its own). A single
        `limit=100`/`limit=1000` page (the previous code) silently left
        every document beyond that page permanently undeleted — for
        `delete_conversation` a conversation with over 1000 messages, for
        `delete_all_memory` a user with over 100 conversations/projects."""
        while True:
            qs = [self._q("equal", attribute, [value]), self._q("limit", values=[page_size])]
            rows = self._list(t, qs)
            if not rows:
                return
            for r in rows:
                rid = str(r.get("$id") or "")
                if rid:
                    self._delete(t, rid)
            if len(rows) < page_size:
                return

    def delete_conversation(self, conversation_id: str) -> None:
        self._delete_all_matching(T_MSG, attribute="conversation_id", value=conversation_id)
        self._delete(T_SUM, conversation_id)
        self._delete(T_CONV, conversation_id)

    def count_conversations(self, user_id: str) -> int:
        qs = [self._q("equal", "user_id", [user_id]), self._q("limit", values=[1])]
        try:
            b = self._call("GET", self._collection(T_CONV),
                           queries=qs)
        except _Loi:
            raise AiUnavailable("Không đếm được hội thoại.")
        return int(b.get("total") or 0)

    # ------------------------------------------------------------- messages
    def create_message(self, m: AiMessage) -> AiMessage:
        data = {"conversation_id": m.conversation_id, "user_id": m.user_id, "role": m.role,
                "content": redact(m.content)[:8000], "status": m.status,
                "citations_json": (m.citations_json or "")[:4000], "provider_name": m.provider_name,
                "model": m.model, "input_tokens": m.input_tokens, "output_tokens": m.output_tokens,
                "created_at": m.created_at, "client_id": m.client_id}
        self._create(T_MSG, m.message_id, data)
        try:
            conv = self.get_conversation(m.conversation_id)
            if conv is not None:
                self.update_conversation(
                    m.conversation_id, {"message_count": conv.message_count + 1})
        except AiUnavailable:
            pass
        return m

    def list_messages(self, conversation_id: str, *, before_id: Optional[str] = None,
                      limit: int = 30) -> List[AiMessage]:
        # H4 (review finding): `orderAsc` + `limit` returned the OLDEST N
        # messages of the conversation — for any conversation with more
        # than `limit` messages, every caller (context building, the
        # conversation-detail route) got the very START of the
        # conversation instead of its most RECENT turns. `orderDesc` gets
        # the newest N as Appwrite sees them; `.reverse()` below restores
        # chronological (oldest-first) order for the return value, which
        # every existing caller already assumes (context builder's own
        # "walk from most recent backwards" logic,
        # `InMemoryAiRepo.list_messages`'s own `items[-limit:]`).
        qs = [self._q("equal", "conversation_id", [conversation_id]),
              self._q("orderDesc", "created_at"), self._q("limit", values=[int(limit)])]
        if before_id:
            qs.append(self._q("cursorAfter", values=[before_id]))
        rows = self._list(T_MSG, qs)
        rows.reverse()
        return [AiMessage(
            message_id=str(r.get("$id") or ""), conversation_id=str(r.get("conversation_id") or ""),
            user_id=str(r.get("user_id") or ""), role=str(r.get("role") or "user"),
            content=str(r.get("content") or ""), status=str(r.get("status") or "complete"),
            citations_json=str(r.get("citations_json") or ""),
            provider_name=str(r.get("provider_name") or ""), model=str(r.get("model") or ""),
            input_tokens=int(r.get("input_tokens") or 0), output_tokens=int(r.get("output_tokens") or 0),
            created_at=str(r.get("created_at") or ""), client_id=str(r.get("client_id") or ""))
            for r in rows]

    # ------------------------------------------------------------- summaries
    def get_summary(self, conversation_id: str) -> Optional[AiSummary]:
        r = self._get(T_SUM, conversation_id)
        if not r:
            return None
        return AiSummary(conversation_id=conversation_id, user_id=str(r.get("user_id") or ""),
                         summary=str(r.get("summary") or ""),
                         covers_until_message_id=str(r.get("covers_until_message_id") or ""),
                         updated_at=str(r.get("updated_at") or ""))

    def put_summary(self, s: AiSummary) -> AiSummary:
        data = {"user_id": s.user_id, "summary": redact(s.summary)[:4000],
                "covers_until_message_id": s.covers_until_message_id, "updated_at": s.updated_at}
        existing = self._get(T_SUM, s.conversation_id)
        if existing is None:
            self._create(T_SUM, s.conversation_id, data)
        else:
            self._update(T_SUM, s.conversation_id, data)
        return s

    # ------------------------------------------------------------- preferences
    def get_preferences(self, user_id: str) -> Optional[AiPreferences]:
        r = self._get(T_PREF, user_id)
        if not r:
            return None
        return AiPreferences(user_id=user_id, memory_enabled=bool(r.get("memory_enabled", True)),
                             preferences_json=str(r.get("preferences_json") or "{}"),
                             updated_at=str(r.get("updated_at") or ""))

    def put_preferences(self, p: AiPreferences) -> AiPreferences:
        data = {"memory_enabled": p.memory_enabled,
                "preferences_json": redact(p.preferences_json)[:2000], "updated_at": p.updated_at}
        existing = self._get(T_PREF, p.user_id)
        if existing is None:
            self._create(T_PREF, p.user_id, data)
        else:
            self._update(T_PREF, p.user_id, data)
        return p

    # ------------------------------------------------------------- projects
    #: H5 (review finding): kept in ONE place, reused by both
    #: `create_project` and `update_project` — `update_project` previously
    #: redacted but never TRUNCATED these fields, so an update (unlike
    #: create) could still hand Appwrite an over-length attribute -> 400 ->
    #: uncaught `AiUnavailable` -> 500. `outline_json`/`characters_json`/
    #: `world_json` are NOT re-sliced by `[:N]` here beyond what
    #: `routes.py::_bounded_json` already rejected with a clean 400 at the
    #: API boundary — truncating a JSON string blindly can corrupt it
    #: (same lesson as `preferences_json`'s own L12 fix); a caller that
    #: bypasses that boundary gets `_Loi`/`AiUnavailable` instead of
    #: silently corrupted data.
    _PROJECT_TEXT_LIMITS = {"title": 120, "premise": 4000, "notes": 4000}

    def create_project(self, p: AiProject) -> AiProject:
        data = {"user_id": p.user_id, "title": redact(p.title)[:120],
                "premise": redact(p.premise)[:4000],
                "outline_json": redact(p.outline_json), "characters_json": redact(p.characters_json),
                "world_json": redact(p.world_json), "notes": redact(p.notes)[:4000],
                "updated_at": p.updated_at}
        self._create(T_PROJ, p.project_id, data)
        return p

    def get_project(self, project_id: str) -> Optional[AiProject]:
        r = self._get(T_PROJ, project_id)
        if not r:
            return None
        return AiProject(project_id=project_id, user_id=str(r.get("user_id") or ""),
                         title=str(r.get("title") or ""), premise=str(r.get("premise") or ""),
                         outline_json=str(r.get("outline_json") or "{}"),
                         characters_json=str(r.get("characters_json") or "{}"),
                         world_json=str(r.get("world_json") or "{}"),
                         notes=str(r.get("notes") or ""), updated_at=str(r.get("updated_at") or ""))

    def list_projects(self, user_id: str) -> List[AiProject]:
        qs = [self._q("equal", "user_id", [user_id]), self._q("orderDesc", "updated_at"),
              self._q("limit", values=[100])]
        rows = self._list(T_PROJ, qs)
        return [self.get_project(str(r.get("$id"))) for r in rows if r.get("$id")]  # type: ignore

    def update_project(self, project_id: str, fields: Dict[str, Any]) -> AiProject:
        fields = dict(fields)
        fields["updated_at"] = now_iso()
        for k in ("title", "premise", "outline_json", "characters_json", "world_json", "notes"):
            if k in fields and isinstance(fields[k], str):
                value = redact(fields[k])
                limit = self._PROJECT_TEXT_LIMITS.get(k)
                fields[k] = value[:limit] if limit else value
        self._update(T_PROJ, project_id, fields)
        return self.get_project(project_id)  # type: ignore

    def delete_project(self, project_id: str) -> None:
        self._delete(T_PROJ, project_id)

    # ------------------------------------------------------------- usage
    def count_usage_users(self, day: str) -> Optional[int]:
        """`total` of rows for that day (one row per user per day, see schema)."""
        try:
            b = self._call("GET", self._collection(T_USAGE),
                           queries=[self._q("equal", "day", [day]), self._q("limit", values=[1])])
        except (_Loi, AiUnavailable):
            return None
        return int((b or {}).get("total") or 0)

    def get_usage_day(self, user_id: str, day: str) -> Optional[AiUsageDay]:
        r = self._get(T_USAGE, f"{user_id}_{day}")
        if not r:
            return None
        return AiUsageDay(user_id=user_id, day=day, requests=int(r.get("requests") or 0),
                         input_tokens=int(r.get("input_tokens") or 0),
                         output_tokens=int(r.get("output_tokens") or 0),
                         updated_at=str(r.get("updated_at") or ""))

    def increment_usage(self, user_id: str, day: str, *, input_tokens: int,
                        output_tokens: int) -> AiUsageDay:
        """Read-modify-write — Appwrite legacy documents API has no atomic
        increment; a small under/overcount is possible under a race
        between two concurrent requests from the SAME user, accepted per
        contract §9 ("Appwrite không có giao dịch ... chấp nhận lệch nhỏ
        khi đua")."""
        doc_id = f"{user_id}_{day}"
        existing = self.get_usage_day(user_id, day)
        if existing is None:
            u = AiUsageDay(user_id=user_id, day=day, requests=1, input_tokens=input_tokens,
                          output_tokens=output_tokens)
            self._create(T_USAGE, doc_id, {
                "user_id": user_id, "day": day, "requests": u.requests,
                "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                "updated_at": u.updated_at})
            return u
        u = AiUsageDay(user_id=user_id, day=day, requests=existing.requests + 1,
                      input_tokens=existing.input_tokens + input_tokens,
                      output_tokens=existing.output_tokens + output_tokens, updated_at=now_iso())
        self._update(T_USAGE, doc_id, {
            "requests": u.requests, "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens, "updated_at": u.updated_at})
        return u

    # ------------------------------------------------------------- escalations
    def create_escalation(self, e: AiEscalation) -> AiEscalation:
        data = {"user_id": e.user_id, "conversation_id": e.conversation_id,
                "summary": redact(e.summary)[:2000],
                "diagnostics_json": redact(e.diagnostics_json)[:4000], "status": e.status,
                "created_at": e.created_at}
        self._create(T_ESC, e.escalation_id, data)
        return e

    # ------------------------------------------------------------- bulk delete
    def delete_all_memory(self, user_id: str, *, include_projects: bool = False) -> None:
        # H6 (review finding): a single `limit=100` page silently left every
        # conversation/project beyond the 100th (project beyond the 100th)
        # permanently undeleted for a user with more than that many — loop
        # a page at a time (each `delete_conversation` call also now
        # paginates ITS OWN message deletion, see `_delete_all_matching`)
        # until none are left.
        while True:
            qs = [self._q("equal", "user_id", [user_id]), self._q("limit", values=[100])]
            rows = self._list(T_CONV, qs)
            if not rows:
                break
            for r in rows:
                cid = str(r.get("$id") or "")
                if cid:
                    self.delete_conversation(cid)
            if len(rows) < 100:
                break
        self._delete(T_PREF, user_id)
        if include_projects:
            self._delete_all_matching(T_PROJ, attribute="user_id", value=user_id)
