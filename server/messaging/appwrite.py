"""
Kho nhan tin tren Appwrite — HAI hien thuc cua CUNG mot `ChatRepository`, KHAC NHAU duy nhat o API:

    LegacyAppwriteChatRepository   /v1/databases/{db}/collections/{c}/documents   documentId  "documents"
                                   Appwrite 1.9.6 tu luu tru (PRODUCTION).
    TablesDBChatRepository         /v1/tablesdb/{db}/tables/{t}/rows               rowId       "rows"
                                   Appwrite Cloud 2.x (STAGING `fanfic-staging`).

Moi logic (quyen, idempotent, phat tan dung mot lan, phan trang, dem chua doc) nam o `_AppwriteChatRepo`
nen hai ban khong the lech nhau. Transaction dung `/v1/tablesdb/transactions` o CA HAI: Appwrite 1.9.6 da
co API nay va production dang dung no cho `job_locks` (`appwrite_store.create_job_once`).

Nam bang (schema o `scripts/setup_appwrite.py`, document/row security BAT, quyen cap bang RONG — khong ai
tao/sua truc tiep; do that tren staging: 401/403):
  chat_conversations  quyen doc: A, B
  chat_messages       quyen doc: A, B
  chat_members        quyen doc: chinh chu
  chat_fanouts        khong ai doc — hang DANH DAU "tin X da phat tan"
  user_blocks         DUNG dinh dang #229 (Social/Profile) — quyen doc: nguoi chan

Khoa API CHI o may chu. Loi tra ve khong bao gio chua than loi tho cua Appwrite.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from server.messaging.domain import (
    Block,
    ChatUnavailable,
    Conversation,
    Member,
    Message,
    RepoConflict,
    iso_ms,
    now_iso,
)

log = logging.getLogger("fanfic.messaging")

T_HT, T_TIN, T_TV, T_PHAT, T_CHAN = "chat_conversations", "chat_messages", "chat_members", "chat_fanouts", "user_blocks"
TIMEOUT = httpx.Timeout(15.0, connect=10.0)
FANOUT_THU = 3


def _q(method: str, attribute: Optional[str] = None, values: Optional[List[Any]] = None) -> str:
    d: Dict[str, Any] = {"method": method}
    if attribute is not None:
        d["attribute"] = attribute
    if values is not None:
        d["values"] = values
    return json.dumps(d, separators=(",", ":"))


def row_to_message(r: Dict[str, Any]) -> Message:
    return Message(id=str(r.get("$id") or ""), conversation_id=str(r.get("conversation_id") or ""),
                   sender_id=str(r.get("sender_id") or ""), recipient_id=str(r.get("recipient_id") or ""),
                   client_id=str(r.get("client_id") or ""), text=str(r.get("text") or ""),
                   created_at=iso_ms(str(r.get("created_at") or "")), kind=str(r.get("kind") or "text"),
                   sticker_id=str(r.get("sticker_id") or ""))


def row_to_member(r: Dict[str, Any]) -> Member:
    return Member(id=str(r.get("$id") or ""), conversation_id=str(r.get("conversation_id") or ""),
                  user_id=str(r.get("user_id") or ""), peer_id=str(r.get("peer_id") or ""),
                  unread_count=int(r.get("unread_count") or 0), last_read_at=iso_ms(str(r.get("last_read_at") or "")),
                  last_read_message_id=str(r.get("last_read_message_id") or ""), muted=bool(r.get("muted")),
                  last_message_id=str(r.get("last_message_id") or ""), last_text=str(r.get("last_text") or ""),
                  last_at=iso_ms(str(r.get("last_at") or "")), last_sender_id=str(r.get("last_sender_id") or ""),
                  updated_at=iso_ms(str(r.get("updated_at") or "")))


def _row_to_conversation(r: Dict[str, Any]) -> Conversation:
    return Conversation(id=str(r.get("$id") or ""), member_a=str(r.get("member_a") or ""),
                        member_b=str(r.get("member_b") or ""), created_at=iso_ms(str(r.get("created_at") or "")),
                        kind=str(r.get("kind") or "dm"))


def _row_to_block(r: Dict[str, Any]) -> Block:
    return Block(id=str(r.get("$id") or r.get("block_id") or ""), blocker_id=str(r.get("blocker_id") or ""),
                 blocked_id=str(r.get("blocked_id") or ""), created_at=iso_ms(str(r.get("created_at") or "")),
                 kind=str(r.get("kind") or "block"))


def _message_data(m: Message) -> Dict[str, Any]:
    d = {"conversation_id": m.conversation_id, "sender_id": m.sender_id, "recipient_id": m.recipient_id,
         "client_id": m.client_id, "text": m.text, "created_at": m.created_at, "kind": m.kind}
    # CHI tin nhan dan mang `sticker_id`: tin chu van ghi duoc vao bang CHUA co cot nay (tuong thich nguoc).
    if m.kind == "sticker":
        d["sticker_id"] = m.sticker_id
    return d


def _member_data(m: Member) -> Dict[str, Any]:
    d = {"conversation_id": m.conversation_id, "user_id": m.user_id, "peer_id": m.peer_id,
         "unread_count": m.unread_count, "muted": m.muted, "updated_at": m.updated_at or None}
    for k in ("last_read_at", "last_read_message_id", "last_message_id", "last_text", "last_at", "last_sender_id"):
        d[k] = getattr(m, k) or None
    return d


def _doc(u: str) -> str:
    return f'read("user:{u}")'


class _Loi(Exception):
    def __init__(self, status: int, kind: str):
        super().__init__(f"{status} {kind}")
        self.status, self.kind = status, kind


class _AppwriteChatRepo:
    #: Ghi de o lop con — DUY NHAT phan khac nhau giua hai API.
    API = ""
    DUONG = ""          # "/v1/databases/{db}/collections/{t}/documents" | "/v1/tablesdb/{db}/tables/{t}/rows"
    KHOA_ID = ""        # "documentId" | "rowId"
    KHOA_DS = ""        # "documents" | "rows"

    def __init__(self, settings: Any, *, client: Optional[httpx.Client] = None) -> None:
        aw = settings.appwrite if hasattr(settings, "appwrite") else settings
        if not (aw.endpoint and aw.project_id and aw.api_key and aw.database_id):
            raise ChatUnavailable("Appwrite chưa cấu hình đủ cho tin nhắn.")
        self._goc = aw.api_base
        self._db = aw.database_id
        self._hd = {"X-Appwrite-Project": aw.project_id, "X-Appwrite-Key": aw.api_key,
                    "Content-Type": "application/json"}
        self._c = client or httpx.Client(timeout=TIMEOUT)

    # ------------------------------------------------------------------ ha tang
    def _goi(self, method: str, path: str, *, body: Any = None, queries: Optional[List[str]] = None) -> Any:
        url = self._goc + path
        if queries:
            url += "?" + "&".join("queries[]=" + quote(q) for q in queries)
        try:
            r = self._c.request(method, url, json=body, headers=self._hd)
        except httpx.HTTPError as exc:
            raise ChatUnavailable("Không kết nối được kho tin nhắn.") from exc
        if r.status_code >= 400:
            try:
                kind = str((r.json() or {}).get("type") or "")
            except ValueError:
                kind = ""
            if r.status_code == 429 or r.status_code >= 500:
                raise ChatUnavailable("Kho tin nhắn đang bận — thử lại sau giây lát.")
            raise _Loi(r.status_code, kind)
        return r.json() if r.content else {}

    def _bang(self, t: str) -> str:
        return self.DUONG.format(db=self._db, t=t)

    def _get(self, t: str, rid: str) -> Optional[Dict[str, Any]]:
        try:
            return self._goi("GET", f"{self._bang(t)}/{quote(rid)}")
        except _Loi as e:
            if e.status == 404:
                return None
            raise ChatUnavailable("Không đọc được kho tin nhắn.") from e

    def _create(self, t: str, rid: str, data: Dict[str, Any], perms: List[str]) -> Dict[str, Any]:
        try:
            return self._goi("POST", self._bang(t), body={self.KHOA_ID: rid, "data": data, "permissions": perms})
        except _Loi as e:
            if e.status == 409:
                raise RepoConflict(rid) from e
            log.warning("messaging[%s] create %s tra %s %s", self.API, t, e.status, e.kind)
            raise ChatUnavailable("Không ghi được vào kho tin nhắn.") from e

    def _list(self, t: str, queries: List[str]) -> Dict[str, Any]:
        try:
            b = self._goi("GET", self._bang(t), queries=queries)
        except _Loi as e:
            log.warning("messaging[%s] list %s tra %s %s", self.API, t, e.status, e.kind)
            raise ChatUnavailable("Không đọc được kho tin nhắn.") from e
        return {"total": int(b.get("total") or 0), "items": b.get(self.KHOA_DS) or []}

    # ------------------------------------------------------------------ hoi thoai
    def get_conversation(self, conversation_id):
        r = self._get(T_HT, conversation_id)
        return _row_to_conversation(r) if r else None

    def create_conversation(self, c: Conversation) -> Conversation:
        self._create(T_HT, c.id, {"kind": c.kind, "member_a": c.member_a, "member_b": c.member_b,
                                  "created_at": c.created_at}, [_doc(c.member_a), _doc(c.member_b)])
        return c

    # ------------------------------------------------------------------ tin
    def create_message(self, m: Message) -> Message:
        self._create(T_TIN, m.id, _message_data(m), [_doc(m.sender_id), _doc(m.recipient_id)])
        return m

    def get_message(self, message_id: str) -> Optional[Message]:
        r = self._get(T_TIN, message_id)
        return row_to_message(r) if r else None

    def list_messages(self, conversation_id, *, before_id=None, after_id=None, limit=30):
        qs = [_q("equal", "conversation_id", [conversation_id])]
        if after_id:
            qs += [_q("orderAsc", "created_at"), _q("cursorAfter", values=[after_id])]
        else:
            qs.append(_q("orderDesc", "created_at"))
            if before_id:
                qs.append(_q("cursorAfter", values=[before_id]))
        qs.append(_q("limit", values=[int(limit)]))
        return [row_to_message(r) for r in self._list(T_TIN, qs)["items"]]

    def latest_message(self, conversation_id):
        ds = self.list_messages(conversation_id, limit=1)
        return ds[0] if ds else None

    def count_unread(self, conversation_id, recipient_id, after_iso):
        qs = [_q("equal", "conversation_id", [conversation_id]), _q("equal", "recipient_id", [recipient_id])]
        if after_iso:
            qs.append(_q("greaterThan", "created_at", [after_iso]))
        qs.append(_q("limit", values=[1]))
        return self._list(T_TIN, qs)["total"]

    # ------------------------------------------------------------------ thanh vien
    def get_members(self, conversation_id):
        rows = self._list(T_TV, [_q("equal", "conversation_id", [conversation_id]), _q("limit", values=[5])])
        return {m.user_id: m for m in (row_to_member(r) for r in rows["items"])}

    def create_member(self, m: Member) -> Member:
        self._create(T_TV, m.id, _member_data(m), [_doc(m.user_id)])
        return m

    def update_member(self, member_id, fields):
        data = {k: (v if v != "" else None) for k, v in fields.items()}
        try:
            r = self._goi("PATCH", f"{self._bang(T_TV)}/{quote(member_id)}", body={"data": data})
        except _Loi as e:
            log.warning("messaging[%s] update member tra %s %s", self.API, e.status, e.kind)
            raise ChatUnavailable("Không cập nhật được hội thoại.") from e
        return row_to_member(r)

    def list_members(self, user_id, *, limit=50):
        rows = self._list(T_TV, [_q("equal", "user_id", [user_id]), _q("orderDesc", "last_at"),
                                 _q("limit", values=[int(limit)])])
        return [m for m in (row_to_member(r) for r in rows["items"]) if m.last_message_id]

    # ------------------------------------------------------------------ phat tan: DUNG MOT LAN
    def _ops(self, message_id: str, recipient_member_id: str) -> List[Dict[str, Any]]:
        return [{"action": "create", "databaseId": self._db, "tableId": T_PHAT, "rowId": "f" + message_id,
                 "data": {"message_id": message_id, "created_at": now_iso()}, "permissions": []},
                {"action": "increment", "databaseId": self._db, "tableId": T_TV, "rowId": recipient_member_id,
                 "data": {"column": "unread_count", "value": 1}}]

    def stage_fanout(self, message_id, recipient_member_id):
        """Mo giao dich + dua thao tac vao (CHUA commit) — chay SONG SONG duoc voi cac phep kiem/tao tin."""
        try:
            tx = self._goi("POST", "/v1/tablesdb/transactions", body={"ttl": 60})
            tid = quote(str(tx.get("$id") or ""))
            self._goi("POST", f"/v1/tablesdb/transactions/{tid}/operations",
                      body={"operations": self._ops(message_id, recipient_member_id)})
        except (_Loi, ChatUnavailable) as e:
            # Chuan bi hong (vd hang thanh vien chua ton tai o tin DAU TIEN): commit se tu chuan bi lai.
            log.info("messaging[%s] stage fanout lui ve tuan tu: %s", self.API, e)
            return {"tid": None, "mid": message_id, "tv": recipient_member_id}
        return {"tid": tid, "mid": message_id, "tv": recipient_member_id}

    def _commit(self, tid: str) -> str:
        try:
            r = self._goi("PATCH", f"/v1/tablesdb/transactions/{tid}", body={"commit": True})
        except _Loi as e:
            self.discard_fanout({"tid": tid})
            if e.status in (404, 409):
                return "conflict"
            log.warning("messaging[%s] commit tra %s %s", self.API, e.status, e.kind)
            raise ChatUnavailable("Giao dịch tin nhắn thất bại.") from e
        return "committed" if r.get("status") == "committed" else "conflict"

    def commit_fanout(self, handle):
        """Do that Cloud 2.3: hang danh dau TRUNG -> commit 409 `transaction_conflict`, KHONG thao tac nao
        duoc ap dung. CHI coi la "da phat tan" khi hang danh dau THAT SU ton tai — xung dot vi ly do khac
        thi dung lai giao dich moi, khong lang le bo "+1"."""
        tid = handle.get("tid")
        for lan in range(FANOUT_THU):
            if tid is None:
                tid = self.stage_fanout(handle["mid"], handle["tv"])["tid"]
                if tid is None:
                    raise ChatUnavailable("Không mở được giao dịch tin nhắn.")
            if self._commit(tid) == "committed":
                return
            tid = None
            if self._get(T_PHAT, "f" + handle["mid"]) is not None:
                raise RepoConflict(handle["mid"])
            time.sleep(0.15 * (lan + 1))
        raise ChatUnavailable("Chưa cập nhật được số tin chưa đọc — gửi lại sẽ tự hoàn tất.")

    def discard_fanout(self, handle):
        tid = (handle or {}).get("tid")
        if not tid:
            return
        try:
            self._goi("PATCH", f"/v1/tablesdb/transactions/{tid}", body={"rollback": True})
        except (_Loi, ChatUnavailable):
            pass  # giao dich tu het han theo `ttl`

    def fanout(self, message_id, recipient_member_id):
        self.commit_fanout(self.stage_fanout(message_id, recipient_member_id))

    # ------------------------------------------------------------------ chan (`user_blocks` cua #229)
    def blocks_between(self, user_a, user_b):
        rows = self._list(T_CHAN, [_q("equal", "blocker_id", [user_a, user_b]), _q("equal", "blocked_id", [user_a, user_b]),
                                   _q("equal", "kind", ["block"]), _q("limit", values=[4])])
        return [b for b in (_row_to_block(r) for r in rows["items"])
                if (b.blocker_id, b.blocked_id) in ((user_a, user_b), (user_b, user_a))]

    def create_block(self, b: Block) -> Block:
        self._create(T_CHAN, b.id, {"block_id": b.id, "blocker_id": b.blocker_id, "blocked_id": b.blocked_id,
                                    "kind": b.kind, "created_at": b.created_at}, [_doc(b.blocker_id)])
        return b

    def delete_block(self, block_id):
        try:
            self._goi("DELETE", f"{self._bang(T_CHAN)}/{quote(block_id)}")
        except _Loi as e:
            if e.status != 404:
                raise ChatUnavailable("Không bỏ chặn được.") from e

    def list_blocks(self, blocker_id):
        rows = self._list(T_CHAN, [_q("equal", "blocker_id", [blocker_id]), _q("equal", "kind", ["block"]),
                                   _q("limit", values=[100])])
        return [_row_to_block(r) for r in rows["items"]]


class LegacyAppwriteChatRepository(_AppwriteChatRepo):
    """Appwrite 1.9.6 tu luu tru (production): databases / collections / documents."""

    API = "legacy"
    DUONG = "/v1/databases/{db}/collections/{t}/documents"
    KHOA_ID = "documentId"
    KHOA_DS = "documents"


class TablesDBChatRepository(_AppwriteChatRepo):
    """Appwrite Cloud 2.x (staging): tablesdb / tables / rows."""

    API = "tablesdb"
    DUONG = "/v1/tablesdb/{db}/tables/{t}/rows"
    KHOA_ID = "rowId"
    KHOA_DS = "rows"
