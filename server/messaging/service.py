"""
Nghiep vu nhan tin 1:1 — KHONG BIET kho luu tru (xem `repository.py`).

Moi thao tac duoc goi THEO NGUOI KIA (`peer_chat_id`): hoi thoai = `dm_id(toi, nguoi_kia)`, nen nguoi
goi LUON la thanh vien cua hoi thoai ho cham toi. Khong co API nao nhan mot "conversation_id" tuy y —
truy cap trai phep vao hoi thoai A-B tu tai khoan C khong co duong nao de dien ta.

GUI TIN (`send`) — thu tu la co chu dich:
  1. chan (hai chieu) -> 403 `chat_blocked`; nguoi kia khong ton tai -> 404; gui cho chinh minh -> 400;
  2. tao tin voi ID do CLIENT chon (`m_<client_id>`) NGOAI giao dich -> Realtime day ngay cho CA HAI
     thanh vien (hang tao trong giao dich khong phat Realtime tren Cloud 2.3 — do that). ID da ton tai
     cua CHINH nguoi gui trong CHINH hoi thoai nay = lan gui lai -> tra tin cu (idempotent); cua ai
     khac -> 409;
  3. `fanout`: +1 "chua doc" cho nguoi nhan, DUNG MOT LAN ke ca khi hai lan gui lai chay song song
     (hang danh dau + giao dich, xem `repository.py`). Lan gui lai sau mot su co giua buoc 2 va 3 se
     tu HOAN TAT buoc 3;
  4. ban xem truoc hop thu = tin MOI NHAT that (doc lai tu kho), khong phai "tin vua gui" — hai tin
     sat nhau khong the de ban xem truoc lui ve tin cu mai mai.

DA DOC (`mark_read`): "chua doc" = so tin GUI CHO TOI co `created_at` > `last_read_at`. Dem LAI tu kho
(khong tru dan), roi dem lai lan nua sau khi ghi — mot tin den dung luc do khong bi nuot.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from server.messaging.domain import (
    PREVIEW_MAX,
    TEXT_MAX,
    Block,
    ChatConflict,
    ChatEvent,
    ChatForbidden,
    ChatInvalid,
    ChatNotFound,
    ChatUnavailable,
    Member,
    Message,
    Page,
    RepoConflict,
    epoch_ms,
    iso_ms,
    now_iso,
)
from server.messaging.ids import (
    block_row_id,
    chat_user_id,
    dm_id,
    fanfic_user_id_from_chat,
    member_row_id,
    message_row_id,
)
from server.messaging.repository import ChatRepository

_DIEU_KHIEN = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩]")
TRANG_TOI_DA = 50


def lam_sach_van_ban(text: Any) -> str:
    """Bo ky tu dieu khien/an (ke ca dao chieu bidi), chuan hoa xuong dong, cat khoang trang hai dau."""
    t = _DIEU_KHIEN.sub("", str(text or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not t:
        raise ChatInvalid("Tin nhắn trống.", code="chat_empty")
    if len(t) > TEXT_MAX:
        raise ChatInvalid(f"Tin nhắn quá dài (tối đa {TEXT_MAX} ký tự).", code="chat_too_long")
    return t


class ChatService:
    def __init__(self, repo: ChatRepository, *, user_exists: Callable[[str], bool],
                 clock: Callable[[], str] = now_iso) -> None:
        self.repo = repo
        self._co_nguoi = user_exists
        self._gio = clock

    # ------------------------------------------------------------------ nguoi kia
    def resolve_peer(self, me: str, peer_chat_id: str) -> str:
        peer = fanfic_user_id_from_chat((peer_chat_id or "").strip())
        if not peer:
            raise ChatNotFound("Không tìm thấy người này.", code="chat_peer_not_found")
        if peer == me:
            raise ChatInvalid("Không thể nhắn tin cho chính mình.", code="chat_self")
        if not self._co_nguoi(peer):
            raise ChatNotFound("Không tìm thấy người này.", code="chat_peer_not_found")
        return peer

    def _dam_bao_thanh_vien(self, cid: str, me: str, peer: str) -> Dict[str, Member]:
        tv = self.repo.get_members(cid)
        for uid, kia in ((me, peer), (peer, me)):
            if uid in tv:
                continue
            try:
                tv[uid] = self.repo.create_member(Member(id=member_row_id(cid, uid), conversation_id=cid,
                                                         user_id=uid, peer_id=kia, updated_at=self._gio()))
            except RepoConflict:  # request song song vua tao — doc lai
                tv = {**tv, **self.repo.get_members(cid)}
        if me not in tv or peer not in tv:
            raise ChatUnavailable("Chưa tạo được hội thoại — thử lại.")
        return tv

    # ------------------------------------------------------------------ gui
    def send(self, me: str, peer_chat_id: str, client_id: str, text: Any) -> Tuple[Message, bool]:
        peer = self.resolve_peer(me, peer_chat_id)
        van_ban = lam_sach_van_ban(text)
        try:
            mid = message_row_id(client_id)
        except ValueError as exc:
            raise ChatInvalid("Mã tin nhắn không hợp lệ.", code="chat_bad_client_id") from exc
        if self.repo.blocks_between(me, peer):
            raise ChatForbidden("Không gửi được tin nhắn cho người này.", code="chat_blocked")
        cid = dm_id(me, peer)
        tv = self._dam_bao_thanh_vien(cid, me, peer)
        moi = Message(id=mid, conversation_id=cid, sender_id=me, recipient_id=peer, client_id=client_id,
                      text=van_ban, created_at=self._gio())
        try:
            tin, tao_moi = self.repo.create_message(moi), True
        except RepoConflict:
            tin, tao_moi = self.repo.get_message(mid), False
            if tin is None:
                raise ChatUnavailable("Không đọc lại được tin nhắn — thử lại.")
            if tin.sender_id != me or tin.conversation_id != cid:
                raise ChatConflict("Mã tin nhắn đã được dùng.", code="chat_id_taken")
        try:
            self.repo.fanout(tin.id, tv[peer].id)
        except RepoConflict:
            pass  # da phat tan (lan gui truoc / request song song) — DUNG MOT LAN
        self._cap_nhat_xem_truoc(cid, tv)
        return tin, tao_moi

    def _cap_nhat_xem_truoc(self, cid: str, tv: Dict[str, Member]) -> None:
        cuoi = self.repo.latest_message(cid)
        if cuoi is None:
            return
        for m in self.repo.get_members(cid).values() or tv.values():
            if m.last_message_id == cuoi.id:
                continue
            if m.last_at and iso_ms(m.last_at) > iso_ms(cuoi.created_at):
                continue  # mot request khac da ghi ban MOI HON
            self.repo.update_member(m.id, {"last_message_id": cuoi.id, "last_text": cuoi.text[:PREVIEW_MAX],
                                           "last_at": cuoi.created_at, "last_sender_id": cuoi.sender_id,
                                           "updated_at": self._gio()})

    # ------------------------------------------------------------------ doc
    def _con_tro(self, cid: str, message_id: Optional[str]) -> Optional[str]:
        if not message_id:
            return None
        m = self.repo.get_message(message_id)
        # Cung MOT cau tra loi cho "khong ton tai" va "cua hoi thoai khac" — khong do duoc ID nguoi khac.
        if m is None or m.conversation_id != cid:
            raise ChatInvalid("Con trỏ không hợp lệ.", code="chat_bad_cursor")
        return m.id

    def history(self, me: str, peer_chat_id: str, *, before: Optional[str] = None,
                after: Optional[str] = None, limit: int = 30) -> Page:
        peer = self.resolve_peer(me, peer_chat_id)
        cid = dm_id(me, peer)
        n = max(1, min(int(limit or 30), TRANG_TOI_DA))
        if after:
            ds = self.repo.list_messages(cid, after_id=self._con_tro(cid, after), limit=n)
            return Page(messages=ds, cursor=ds[-1].id if len(ds) == n else None)
        ds = self.repo.list_messages(cid, before_id=self._con_tro(cid, before), limit=n)
        return Page(messages=list(reversed(ds)), cursor=ds[-1].id if len(ds) == n else None)

    def conversations(self, me: str, *, limit: int = TRANG_TOI_DA) -> Tuple[List[Member], int]:
        ds = self.repo.list_members(me, limit=max(1, min(limit, TRANG_TOI_DA)))
        return ds, sum(m.unread_count for m in ds if not m.muted)

    # ------------------------------------------------------------------ da doc / tat tieng / chan
    def mark_read(self, me: str, peer_chat_id: str, up_to: Optional[str] = None) -> Optional[Member]:
        peer = self.resolve_peer(me, peer_chat_id)
        cid = dm_id(me, peer)
        cua_toi = self.repo.get_members(cid).get(me)
        if cua_toi is None:
            return None  # chua co tin nao — khong co gi de danh dau
        if up_to:
            moc_tin = self.repo.get_message(self._con_tro(cid, up_to))
        else:
            moc_tin = self.repo.latest_message(cid)
        moc = iso_ms(moc_tin.created_at) if moc_tin else iso_ms(self._gio())
        moc = max(moc, iso_ms(cua_toi.last_read_at)) if cua_toi.last_read_at else moc
        n = self.repo.count_unread(cid, me, moc)
        moi = self.repo.update_member(cua_toi.id, {
            "last_read_at": moc, "last_read_message_id": moc_tin.id if moc_tin else cua_toi.last_read_message_id,
            "unread_count": n, "updated_at": self._gio()})
        # Mot "+1" cua tin den dung luc nay co the bi lenh ghi tren de len — dem lai MOT lan nua.
        n2 = self.repo.count_unread(cid, me, moc)
        if n2 != moi.unread_count:
            moi = self.repo.update_member(cua_toi.id, {"unread_count": n2})
        return moi

    def set_muted(self, me: str, peer_chat_id: str, muted: bool) -> Member:
        peer = self.resolve_peer(me, peer_chat_id)
        cid = dm_id(me, peer)
        cua_toi = self._dam_bao_thanh_vien(cid, me, peer)[me]
        return self.repo.update_member(cua_toi.id, {"muted": bool(muted), "updated_at": self._gio()})

    def set_blocked(self, me: str, peer_chat_id: str, blocked: bool) -> bool:
        peer = self.resolve_peer(me, peer_chat_id)
        bid = block_row_id(me, peer)
        if blocked:
            try:
                self.repo.create_block(Block(id=bid, blocker_id=me, blocked_id=peer, created_at=self._gio()))
            except RepoConflict:
                pass
        else:
            self.repo.delete_block(bid)
        return blocked

    def blocked_chat_ids(self, me: str) -> List[str]:
        return [chat_user_id(b.blocked_id) for b in self.repo.list_blocks(me)]

    # ------------------------------------------------------------------ hinh dang tra ve
    @staticmethod
    def message_dto(viewer: str, m: Message) -> Dict[str, Any]:
        kia = m.recipient_id if m.sender_id == viewer else m.sender_id
        return {"id": m.id, "client_id": m.client_id, "peer_id": chat_user_id(kia),
                "from_me": m.sender_id == viewer, "text": m.text, "time": epoch_ms(m.created_at)}

    @staticmethod
    def member_dto(m: Member) -> Dict[str, Any]:
        return {"peer_id": chat_user_id(m.peer_id), "unread": int(m.unread_count or 0), "muted": bool(m.muted),
                "last_text": m.last_text, "last_time": epoch_ms(m.last_at),
                "last_from_me": bool(m.last_sender_id) and m.last_sender_id == m.user_id,
                "last_message_id": m.last_message_id}

    def event_dto(self, viewer: str, ev: Optional[ChatEvent]) -> Optional[Dict[str, Any]]:
        """Su kien kho -> hinh dang cho trinh duyet. Loc LAN NUA theo nguoi xem (phong thu chieu sau:
        kho da loc theo quyen doc, nhung mot kho cau hinh sai khong duoc lam lot tin cua nguoi khac)."""
        if ev is None or ev.kind == "delete":
            return None
        if ev.message is not None:
            if viewer not in ev.message.readers:
                return None
            return {"type": "message", "message": self.message_dto(viewer, ev.message)}
        if ev.member is not None:
            if ev.member.user_id != viewer or not ev.member.last_message_id:
                return None
            return {"type": "conversation", "conversation": self.member_dto(ev.member)}
        return None
