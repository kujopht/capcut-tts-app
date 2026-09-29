"""
Hop dong KHO LUU TRU cua nhan tin + ban trong bo nho (mock/test).

`ChatService` (nghiep vu) CHI noi chuyen voi `ChatRepository` va `ChatEventSource`. Kho that:
`appwrite.py::LegacyAppwriteChatRepository` (API Databases — Appwrite 1.9.6 production) va
`appwrite.py::TablesDBChatRepository` (API TablesDB — Cloud 2.x staging) — CUNG hop dong, CUNG nghiep vu,
CUNG giao dien; khac nhau DUY NHAT o duong dan/ten khoa cua API.

BA NGU NGHIA ma moi kho PHAI giu (va `InMemoryChatRepository` mo phong DUNG nhu vay):

1. `create_message`/`create_conversation`/`create_member` voi ID da ton tai -> `RepoConflict`.
2. PHAT TAN DUNG MOT LAN: `stage_fanout` chuan bi (co the SONG SONG voi cac phep kiem), `commit_fanout`
   ap dung — tao hang DANH DAU (`chat_fanouts/f<message_id>`) CUNG giao dich voi phep tang "chua doc".
   Do that tren Cloud 2.3 (2026-09-28): tao trung rowId trong transaction -> commit 409
   `transaction_conflict` va KHONG thao tac nao duoc ap dung -> `RepoConflict` = da phat tan roi.
   Service CHI commit sau khi tin da tao (hoac la lan gui lai cua chinh minh); con lai `discard_fanout`.
3. Chan = hang `user_blocks` DUNG dinh dang #229 (`block_row_id`, `kind="block"`, quyen doc: nguoi chan).

Realtime (`subscribe`): chi day su kien ma nguoi xem CO QUYEN DOC — Appwrite lam dieu nay bang quyen
theo hang (do that: nguoi thu ba khong nhan su kien cua hoi thoai A-B); ban bo nho loc bang `readers`.
Luu y do that: hang TAO ben trong transaction KHONG phat su kien Realtime tren Cloud 2.3 — vi vay tin
nhan duoc tao NGOAI giao dich (xem `service.send`).
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Tuple

from server.messaging.domain import Block, ChatEvent, Conversation, Member, Message, RepoConflict, iso_ms


class ChatRepository(Protocol):
    # ---- hoi thoai
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]: ...
    def create_conversation(self, c: Conversation) -> Conversation: ...
    # ---- tin
    def create_message(self, m: Message) -> Message: ...
    def get_message(self, message_id: str) -> Optional[Message]: ...
    def list_messages(self, conversation_id: str, *, before_id: Optional[str] = None,
                      after_id: Optional[str] = None, limit: int = 30) -> List[Message]:
        """`after_id` -> TANG dan theo thoi gian, sau tin do (bu khoang trong sau khi noi lai).
        Con lai -> GIAM dan (moi nhat truoc), cu hon `before_id` neu co (trang lich su)."""
        ...
    def latest_message(self, conversation_id: str) -> Optional[Message]: ...
    def count_unread(self, conversation_id: str, recipient_id: str, after_iso: str) -> int: ...
    # ---- thanh vien
    def get_members(self, conversation_id: str) -> Dict[str, Member]: ...
    def create_member(self, m: Member) -> Member: ...
    def update_member(self, member_id: str, fields: Dict[str, Any]) -> Member: ...
    def list_members(self, user_id: str, *, limit: int = 50) -> List[Member]: ...
    # ---- phat tan (DUNG MOT LAN)
    def stage_fanout(self, message_id: str, recipient_member_id: str) -> Any: ...
    def commit_fanout(self, handle: Any) -> None:
        """`RepoConflict` = tin nay DA phat tan (lan gui truoc / request song song)."""
        ...
    def discard_fanout(self, handle: Any) -> None: ...
    # ---- chan (hang `user_blocks` dinh dang #229, chi kind="block")
    def blocks_between(self, user_a: str, user_b: str) -> List[Block]: ...
    def create_block(self, b: Block) -> Block: ...
    def delete_block(self, block_id: str) -> None: ...
    def list_blocks(self, blocker_id: str) -> List[Block]: ...


class ChatEventSource(Protocol):
    def subscribe(self, viewer_id: str, credential: str, *, heartbeat_s: float = 15.0
                  ) -> AsyncIterator[Optional[ChatEvent]]:
        """Luong su kien cua MOT nguoi xem, xac thuc bang credential CUA HO (khong bao gio khoa may
        chu) — nen kho luu tru tu loc theo quyen doc. `None` = nhip tim (khong co su kien)."""
        ...


# =============================================================================== trong bo nho


class _Hub:
    """Pub/sub trong tien trinh, an toan luong: ghi (luong bat ky) -> hang doi asyncio cua tung nguoi xem."""

    def __init__(self) -> None:
        self._khoa = threading.Lock()
        self._subs: List[Tuple[str, asyncio.AbstractEventLoop, asyncio.Queue]] = []

    def add(self, viewer: str, loop: asyncio.AbstractEventLoop, q: asyncio.Queue) -> None:
        with self._khoa:
            self._subs.append((viewer, loop, q))

    def remove(self, q: asyncio.Queue) -> None:
        with self._khoa:
            self._subs = [s for s in self._subs if s[2] is not q]

    def publish(self, ev: ChatEvent, readers: List[str]) -> None:
        with self._khoa:
            subs = list(self._subs)
        for viewer, loop, q in subs:
            if viewer in readers:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, ev)
                except RuntimeError:  # vong lap da dong — nguoi xem da roi di
                    pass

    def count(self, viewer: Optional[str] = None) -> int:
        with self._khoa:
            return sum(1 for s in self._subs if viewer is None or s[0] == viewer)


class InMemoryChatRepository:
    """Ban mo phong cho DATA_BACKEND=mock va test. Thu tu tin: (created_at, thu tu chen) — nhu Appwrite
    sap theo cot roi theo `$sequence` noi bo."""

    def __init__(self) -> None:
        self._khoa = threading.RLock()
        self._tin: Dict[str, Message] = {}
        self._thu_tu: Dict[str, int] = {}
        self._tv: Dict[str, Member] = {}
        self._ht: Dict[str, Conversation] = {}
        self._chan: Dict[str, Block] = {}
        self._danh_dau: set = set()
        self.hub = _Hub()
        #: Dem lan goi — test kiem "khong goi kho" o nhanh loi.
        self.calls: Dict[str, int] = {}

    def _dem(self, ten: str) -> None:
        self.calls[ten] = self.calls.get(ten, 0) + 1

    # ---- hoi thoai
    def get_conversation(self, conversation_id):
        with self._khoa:
            return self._ht.get(conversation_id)

    def create_conversation(self, c: Conversation) -> Conversation:
        with self._khoa:
            if c.id in self._ht:
                raise RepoConflict(c.id)
            self._ht[c.id] = c
        return c

    # ---- tin
    def create_message(self, m: Message) -> Message:
        self._dem("create_message")
        with self._khoa:
            if m.id in self._tin:
                raise RepoConflict(m.id)
            self._tin[m.id] = m
            self._thu_tu[m.id] = len(self._thu_tu)
        self.hub.publish(ChatEvent("create", message=m), m.readers)
        return m

    def get_message(self, message_id: str) -> Optional[Message]:
        with self._khoa:
            return self._tin.get(message_id)

    def _cua(self, cid: str) -> List[Message]:
        ds = [m for m in self._tin.values() if m.conversation_id == cid]
        return sorted(ds, key=lambda m: (iso_ms(m.created_at), self._thu_tu[m.id]))

    def list_messages(self, conversation_id, *, before_id=None, after_id=None, limit=30):
        self._dem("list_messages")
        with self._khoa:
            ds = self._cua(conversation_id)
        if after_id:
            ids = [m.id for m in ds]
            if after_id not in ids:
                return ds[:limit]
            return ds[ids.index(after_id) + 1:][:limit]
        ds = list(reversed(ds))
        if before_id:
            ids = [m.id for m in ds]
            if before_id not in ids:
                return []
            ds = ds[ids.index(before_id) + 1:]
        return ds[:limit]

    def latest_message(self, conversation_id):
        with self._khoa:
            ds = self._cua(conversation_id)
        return ds[-1] if ds else None

    def count_unread(self, conversation_id, recipient_id, after_iso):
        self._dem("count_unread")
        moc = iso_ms(after_iso) if after_iso else ""
        with self._khoa:
            return sum(1 for m in self._cua(conversation_id)
                       if m.recipient_id == recipient_id and (not moc or iso_ms(m.created_at) > moc))

    # ---- thanh vien
    def get_members(self, conversation_id):
        with self._khoa:
            return {m.user_id: m for m in self._tv.values() if m.conversation_id == conversation_id}

    def create_member(self, m: Member) -> Member:
        with self._khoa:
            if m.id in self._tv:
                raise RepoConflict(m.id)
            self._tv[m.id] = m
        self.hub.publish(ChatEvent("create", member=m), [m.user_id])
        return m

    def update_member(self, member_id, fields):
        with self._khoa:
            cu = self._tv[member_id]
            moi = replace(cu, **fields)
            self._tv[member_id] = moi
        self.hub.publish(ChatEvent("update", member=moi), [moi.user_id])
        return moi

    def list_members(self, user_id, *, limit=50):
        with self._khoa:
            ds = [m for m in self._tv.values() if m.user_id == user_id and m.last_message_id]
        return sorted(ds, key=lambda m: iso_ms(m.last_at), reverse=True)[:limit]

    # ---- phat tan
    def stage_fanout(self, message_id, recipient_member_id):
        return (message_id, recipient_member_id)

    def commit_fanout(self, handle):
        message_id, recipient_member_id = handle
        self._dem("fanout")
        with self._khoa:
            if message_id in self._danh_dau:
                raise RepoConflict(message_id)
            self._danh_dau.add(message_id)
            cu = self._tv[recipient_member_id]
            moi = replace(cu, unread_count=cu.unread_count + 1)
            self._tv[recipient_member_id] = moi
        self.hub.publish(ChatEvent("update", member=moi), [moi.user_id])

    def discard_fanout(self, handle):
        return None

    def fanout(self, message_id, recipient_member_id):
        """Tien ich cho test: chuan bi + commit ngay."""
        self.commit_fanout(self.stage_fanout(message_id, recipient_member_id))

    # ---- chan (chi kind="block" — "mute" cua #229 la tat tieng NOI DUNG, khong chan tin nhan)
    def blocks_between(self, user_a, user_b):
        with self._khoa:
            return [b for b in self._chan.values()
                    if b.kind == "block" and {b.blocker_id, b.blocked_id} == {user_a, user_b}]

    def create_block(self, b: Block) -> Block:
        with self._khoa:
            if b.id in self._chan:
                raise RepoConflict(b.id)
            self._chan[b.id] = b
        return b

    def delete_block(self, block_id):
        with self._khoa:
            self._chan.pop(block_id, None)

    def list_blocks(self, blocker_id):
        with self._khoa:
            return [b for b in self._chan.values() if b.blocker_id == blocker_id and b.kind == "block"]


class InMemoryEventSource:
    """Realtime cua `InMemoryChatRepository`: cung ngu nghia loc theo nguoi doc nhu Appwrite."""

    def __init__(self, repo: InMemoryChatRepository) -> None:
        self.repo = repo

    async def subscribe(self, viewer_id: str, credential: str, *, heartbeat_s: float = 15.0):
        q: asyncio.Queue = asyncio.Queue()
        self.repo.hub.add(viewer_id, asyncio.get_running_loop(), q)
        try:
            yield None  # "da san sang" — giong Appwrite tra `authentication` thanh cong
            while True:
                try:
                    yield await asyncio.wait_for(q.get(), heartbeat_s)
                except asyncio.TimeoutError:
                    yield None
        finally:
            self.repo.hub.remove(q)
