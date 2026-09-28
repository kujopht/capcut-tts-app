"""
Kho nhan tin tren Appwrite **TablesDB** (`/v1/tablesdb/...`) — dung truc tiep API moi, KHONG qua lop
dich staging. Kiem that tren `fanfic-staging` (Appwrite Cloud 2.3). Appwrite 1.9.6 cung co TablesDB,
nhung production CHUA duoc kiem/bat (`FAS_CHAT_V1` tat); khi can mot ban API Databases cu, hien thuc
`ChatRepository` trong mot tep canh tep nay — nghiep vu va giao dien khong doi.

Bon bang (schema o `scripts/setup_appwrite.py`, rowSecurity BAT, khong cap quyen ghi cho ai):
  chat_messages  quyen: read(A), read(B)
  chat_members   quyen: read(chu hang)
  chat_blocks    quyen: read(nguoi chan)
  chat_fanouts   khong ai doc — hang DANH DAU "da phat tan tin X" (xem `fanout`)

Khoa API CHI o may chu. Loi tra ve khong bao gio chua than loi tho cua Appwrite (co the chua ID/duong).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from server.messaging.domain import Block, ChatUnavailable, Member, Message, RepoConflict, iso_ms, now_iso

log = logging.getLogger("fanfic.messaging")

T_TIN, T_TV, T_CHAN, T_PHAT = "chat_messages", "chat_members", "chat_blocks", "chat_fanouts"
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
                   created_at=iso_ms(str(r.get("created_at") or "")), kind=str(r.get("kind") or "text"))


def row_to_member(r: Dict[str, Any]) -> Member:
    return Member(id=str(r.get("$id") or ""), conversation_id=str(r.get("conversation_id") or ""),
                  user_id=str(r.get("user_id") or ""), peer_id=str(r.get("peer_id") or ""),
                  unread_count=int(r.get("unread_count") or 0), last_read_at=iso_ms(str(r.get("last_read_at") or "")),
                  last_read_message_id=str(r.get("last_read_message_id") or ""), muted=bool(r.get("muted")),
                  last_message_id=str(r.get("last_message_id") or ""), last_text=str(r.get("last_text") or ""),
                  last_at=iso_ms(str(r.get("last_at") or "")), last_sender_id=str(r.get("last_sender_id") or ""),
                  updated_at=iso_ms(str(r.get("updated_at") or "")))


def _row_to_block(r: Dict[str, Any]) -> Block:
    return Block(id=str(r.get("$id") or ""), blocker_id=str(r.get("blocker_id") or ""),
                 blocked_id=str(r.get("blocked_id") or ""), created_at=iso_ms(str(r.get("created_at") or "")))


def _message_data(m: Message) -> Dict[str, Any]:
    return {"conversation_id": m.conversation_id, "sender_id": m.sender_id, "recipient_id": m.recipient_id,
            "client_id": m.client_id, "text": m.text, "created_at": m.created_at, "kind": m.kind}


def _member_data(m: Member) -> Dict[str, Any]:
    d = {"conversation_id": m.conversation_id, "user_id": m.user_id, "peer_id": m.peer_id,
         "unread_count": m.unread_count, "muted": m.muted, "updated_at": m.updated_at or None}
    for k in ("last_read_at", "last_read_message_id", "last_message_id", "last_text", "last_at", "last_sender_id"):
        v = getattr(m, k)
        d[k] = v or None
    return d


def _doc(u: str) -> str:
    return f'read("user:{u}")'


class _Loi(Exception):
    def __init__(self, status: int, kind: str):
        super().__init__(f"{status} {kind}")
        self.status, self.kind = status, kind


class TablesDBChatRepository:
    def __init__(self, settings: Any, *, client: Optional[httpx.Client] = None) -> None:
        aw = settings.appwrite if hasattr(settings, "appwrite") else settings
        if not (aw.endpoint and aw.project_id and aw.api_key and aw.database_id):
            raise ChatUnavailable("Appwrite chưa cấu hình đủ cho tin nhắn.")
        self._goc = aw.api_base + "/v1/tablesdb"
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

    def _rows(self, t: str) -> str:
        return f"/{self._db}/tables/{t}/rows"

    def _get(self, t: str, rid: str) -> Optional[Dict[str, Any]]:
        try:
            return self._goi("GET", f"{self._rows(t)}/{quote(rid)}")
        except _Loi as e:
            if e.status == 404:
                return None
            raise ChatUnavailable("Không đọc được kho tin nhắn.") from e

    def _create(self, t: str, rid: str, data: Dict[str, Any], perms: List[str]) -> Dict[str, Any]:
        try:
            return self._goi("POST", self._rows(t), body={"rowId": rid, "data": data, "permissions": perms})
        except _Loi as e:
            if e.status == 409:
                raise RepoConflict(rid) from e
            log.warning("messaging create %s tra %s %s", t, e.status, e.kind)
            raise ChatUnavailable("Không ghi được vào kho tin nhắn.") from e

    def _list(self, t: str, queries: List[str]) -> Dict[str, Any]:
        try:
            return self._goi("GET", self._rows(t), queries=queries)
        except _Loi as e:
            log.warning("messaging list %s tra %s %s", t, e.status, e.kind)
            raise ChatUnavailable("Không đọc được kho tin nhắn.") from e

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
        return [row_to_message(r) for r in self._list(T_TIN, qs).get("rows", [])]

    def latest_message(self, conversation_id):
        ds = self.list_messages(conversation_id, limit=1)
        return ds[0] if ds else None

    def count_unread(self, conversation_id, recipient_id, after_iso):
        qs = [_q("equal", "conversation_id", [conversation_id]), _q("equal", "recipient_id", [recipient_id])]
        if after_iso:
            qs.append(_q("greaterThan", "created_at", [after_iso]))
        qs.append(_q("limit", values=[1]))
        return int(self._list(T_TIN, qs).get("total") or 0)

    # ------------------------------------------------------------------ thanh vien
    def get_members(self, conversation_id):
        rows = self._list(T_TV, [_q("equal", "conversation_id", [conversation_id]), _q("limit", values=[5])])
        return {m.user_id: m for m in (row_to_member(r) for r in rows.get("rows", []))}

    def create_member(self, m: Member) -> Member:
        self._create(T_TV, m.id, _member_data(m), [_doc(m.user_id)])
        return m

    def update_member(self, member_id, fields):
        data = {k: (v if v != "" else None) for k, v in fields.items()}
        try:
            r = self._goi("PATCH", f"{self._rows(T_TV)}/{quote(member_id)}", body={"data": data})
        except _Loi as e:
            log.warning("messaging update member tra %s %s", e.status, e.kind)
            raise ChatUnavailable("Không cập nhật được hội thoại.") from e
        return row_to_member(r)

    def list_members(self, user_id, *, limit=50):
        rows = self._list(T_TV, [_q("equal", "user_id", [user_id]), _q("orderDesc", "last_at"),
                                 _q("limit", values=[int(limit)])])
        return [m for m in (row_to_member(r) for r in rows.get("rows", [])) if m.last_message_id]

    # ------------------------------------------------------------------ phat tan: DUNG MOT LAN
    def _tx(self, operations: List[Dict[str, Any]]) -> str:
        """Tra 'committed' | 'conflict'. Do that Cloud 2.3: hang tao TRUNG rowId -> commit 409
        `transaction_conflict`, va MOI thao tac khac trong giao dich KHONG duoc ap dung."""
        try:
            tx = self._goi("POST", "/transactions", body={"ttl": 60})
        except _Loi as e:
            raise ChatUnavailable("Không mở được giao dịch.") from e
        tid = quote(str(tx.get("$id") or ""))
        try:
            self._goi("POST", f"/transactions/{tid}/operations", body={"operations": operations})
            r = self._goi("PATCH", f"/transactions/{tid}", body={"commit": True})
        except _Loi as e:
            try:
                self._goi("PATCH", f"/transactions/{tid}", body={"rollback": True})
            except (_Loi, ChatUnavailable):
                pass
            if e.status == 409:
                return "conflict"
            log.warning("messaging tx tra %s %s", e.status, e.kind)
            raise ChatUnavailable("Giao dịch tin nhắn thất bại.") from e
        return "committed" if r.get("status") == "committed" else "conflict"

    def fanout(self, message_id, recipient_member_id):
        dau = "f" + message_id  # <= 36 ky tu (message_id <= 34)
        ops = [{"action": "create", "databaseId": self._db, "tableId": T_PHAT, "rowId": dau,
                "data": {"message_id": message_id, "created_at": now_iso()},
                "permissions": []},
               {"action": "increment", "databaseId": self._db, "tableId": T_TV, "rowId": recipient_member_id,
                "data": {"column": "unread_count", "value": 1}}]
        for _ in range(FANOUT_THU):
            if self._tx(ops) == "committed":
                return
            # Xung dot: CHI coi la "da phat tan" khi hang danh dau THAT SU ton tai — xung dot vi ly do
            # khac (hang thanh vien dang bi ghi) thi thu lai, khong duoc lang le bo "+1".
            if self._get(T_PHAT, dau) is not None:
                raise RepoConflict(message_id)
            time.sleep(0.15)
        raise ChatUnavailable("Chưa cập nhật được số tin chưa đọc — gửi lại sẽ tự hoàn tất.")

    # ------------------------------------------------------------------ chan
    def blocks_between(self, user_a, user_b):
        rows = self._list(T_CHAN, [_q("equal", "blocker_id", [user_a, user_b]),
                                   _q("equal", "blocked_id", [user_a, user_b]), _q("limit", values=[4])])
        return [b for b in (_row_to_block(r) for r in rows.get("rows", [])) if {b.blocker_id, b.blocked_id} == {user_a, user_b}]

    def create_block(self, b: Block) -> Block:
        self._create(T_CHAN, b.id, {"blocker_id": b.blocker_id, "blocked_id": b.blocked_id, "created_at": b.created_at},
                     [_doc(b.blocker_id)])
        return b

    def delete_block(self, block_id):
        try:
            self._goi("DELETE", f"{self._rows(T_CHAN)}/{quote(block_id)}")
        except _Loi as e:
            if e.status != 404:
                raise ChatUnavailable("Không bỏ chặn được.") from e

    def list_blocks(self, blocker_id):
        rows = self._list(T_CHAN, [_q("equal", "blocker_id", [blocker_id]), _q("limit", values=[100])])
        return [_row_to_block(r) for r in rows.get("rows", [])]
