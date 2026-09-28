"""
Nghiep vu nhan tin 1:1 — KHONG BIET kho luu tru (xem `repository.py`).

Moi thao tac duoc goi THEO NGUOI KIA (`peer_chat_id`): hoi thoai = `dm_id(toi, nguoi_kia)`, nen nguoi
goi LUON la thanh vien cua hoi thoai ho cham toi. Khong co API nao nhan mot "conversation_id" tuy y —
truy cap trai phep vao hoi thoai A-B tu tai khoan C khong co duong nao de dien ta.

GUI TIN (`send`) — thu tu la co chu dich:
  1. SONG SONG: nguoi kia ton tai? chan (hai chieu, `user_blocks` cua #229)? thanh vien? + CHUAN BI giao
     dich phat tan (chua commit). Chan -> 403 `chat_blocked` (giao dich chuan bi bi HUY); khong ton tai
     -> 404; gui cho chinh minh -> 400;
  2. tin DAU TIEN: tao `chat_conversations` + hai `chat_members` (idempotent);
  3. tao tin voi ID do CLIENT chon (`m_<client_id>`) NGOAI giao dich -> Realtime day ngay cho CA HAI
     thanh vien (hang tao trong giao dich khong phat Realtime tren Cloud 2.3 — do that). ID da ton tai
     cua CHINH nguoi gui trong CHINH hoi thoai nay = lan gui lai -> tra tin cu (idempotent); cua ai
     khac -> 409 (giao dich bi HUY);
  4. COMMIT phat tan: +1 "chua doc" cho nguoi nhan, DUNG MOT LAN ke ca khi hai lan gui lai chay song
     song (hang danh dau + giao dich, xem `repository.py`). CHI commit sau buoc 3. Lan gui lai sau mot
     su co giua buoc 3 va 4 se tu HOAN TAT buoc 4;
  5. ban xem truoc hop thu = tin MOI NHAT that (doc lai tu kho), cap nhat SAU khi tra loi.

CHAN = muc TAI KHOAN (#229): chan roi thi KHONG ai trong hai nguoi tao duoc tin moi -> khong co tin moi
nao duoc giao. Lich su CU van con, ca hai van doc duoc (khong xoa, khong an). Bo chan -> nhan tiep.
TAT TIENG = rieng MOT hoi thoai (`Member.muted`): tin van den, van dem chua doc cua hoi thoai do, nhung
KHONG tinh vao tong tren nut Tin nhan.

DA DOC (`mark_read`): "chua doc" = so tin GUI CHO TOI co `created_at` > `last_read_at`. Dem LAI tu kho
(khong tru dan), roi dem lai lan nua sau khi ghi — mot tin den dung luc do khong bi nuot.
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from server.messaging.domain import (
    PREVIEW_MAX,
    TEXT_MAX,
    Block,
    ChatConflict,
    ChatEvent,
    Conversation,
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
from server.messaging.stickers import (
    DEFAULT_CATALOG,
    NguoiXem,
    StickerCatalog,
    StickerPack,
    catalog_dto,
    mo_khoa,
    sticker_dto,
)

log = logging.getLogger("fanfic.messaging")
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


#: Cac phep doc DOC LAP cua mot lan gui chay SONG SONG. Do that tren staging (VN -> SGP, 2026-09-28):
#: ~11 lan goi Appwrite tuan tu = trung vi 3,1 s cho nguoi gui.
_POOL = ThreadPoolExecutor(max_workers=16, thread_name_prefix="messaging")
#: "Nguoi nay ton tai" — CHI nho ket qua DUONG (tai khoan bi xoa van bi chan boi 404 o lan het han).
NHO_NGUOI_GIAY = 600.0


class BlockSource(Protocol):
    """Chan MUC TAI KHOAN (`user_blocks`, kind "block"). Nguon CHINH TAC la Social Play V1 (#229) — xem
    `server/main.py::_ChanQuaSocial`; `RepoBlocks` la ban doc/ghi THANG cung hang do (dung khi Social tat)."""

    def blocked_between(self, a: str, b: str) -> bool: ...
    def set_blocked(self, blocker: str, blocked: str, on: bool) -> None: ...
    def blocked_by(self, blocker: str) -> List[str]: ...


class RepoBlocks:
    """Doc/ghi THANG hang `user_blocks` qua kho chat — DUNG dinh dang cua #229 (`social.block_key`). Khong co
    tac dung phu cua Social (bo theo doi hai chieu): chi dung khi nang luc `blocks` cua Social dang TAT."""

    def __init__(self, repo: ChatRepository, clock: Callable[[], str] = now_iso) -> None:
        self._repo, self._gio = repo, clock

    def blocked_between(self, a: str, b: str) -> bool:
        return bool(self._repo.blocks_between(a, b))

    def set_blocked(self, blocker: str, blocked: str, on: bool) -> None:
        bid = block_row_id(blocker, blocked)
        if on:
            try:
                self._repo.create_block(Block(id=bid, blocker_id=blocker, blocked_id=blocked, created_at=self._gio()))
            except RepoConflict:
                pass
        else:
            self._repo.delete_block(bid)

    def blocked_by(self, blocker: str) -> List[str]:
        return [b.blocked_id for b in self._repo.list_blocks(blocker)]


class ChatService:
    def __init__(self, repo: ChatRepository, *, user_exists: Callable[[str], bool],
                 clock: Callable[[], str] = now_iso, blocks: Optional[BlockSource] = None,
                 stickers: StickerCatalog = DEFAULT_CATALOG,
                 viewer_of: Optional[Callable[[str], NguoiXem]] = None) -> None:
        self.repo = repo
        self._co_nguoi = user_exists
        self._gio = clock
        self._nho_nguoi: Dict[str, float] = {}
        self.blocks: BlockSource = blocks or RepoBlocks(repo, clock)
        self.stickers = stickers
        #: Cap/thanh tich cua NGUOI GUI de quyet mo khoa goi nhan dan (may chu quyet). Khong co nguon -> Lv. 0.
        self._nguoi_xem = viewer_of or (lambda _uid: NguoiXem())

    def sticker_catalog(self, me: str) -> Dict[str, Any]:
        return catalog_dto(self._nguoi_xem(me), self.stickers)

    def _kiem_nhan_dan(self, me: str, sticker_id: Optional[str]) -> Tuple[str, Optional[StickerPack]]:
        """Ma hop le -> (nhan thay the, goi can kiem mo khoa — `None` = goi mien phi, khong can I/O)."""
        st = self.stickers.get(sticker_id or "")
        goi = self.stickers.pack(st.pack_id) if st else None
        if st is None or goi is None:
            raise ChatInvalid("Nhãn dán không tồn tại.", code="chat_sticker_unknown")
        return f"Nhãn dán: {st.alt}", (None if goi.unlock.kind == "free" else goi)

    # ------------------------------------------------------------------ nguoi kia
    def _ton_tai(self, uid: str) -> bool:
        luc = self._nho_nguoi.get(uid)
        if luc is not None and time.monotonic() - luc < NHO_NGUOI_GIAY:
            return True
        if self._co_nguoi(uid):
            self._nho_nguoi[uid] = time.monotonic()
            return True
        return False

    @staticmethod
    def _peer_id(me: str, peer_chat_id: str) -> str:
        """Kiem hinh thuc, KHONG goi kho."""
        peer = fanfic_user_id_from_chat((peer_chat_id or "").strip())
        if not peer:
            raise ChatNotFound("Không tìm thấy người này.", code="chat_peer_not_found")
        if peer == me:
            raise ChatInvalid("Không thể nhắn tin cho chính mình.", code="chat_self")
        return peer

    def resolve_peer(self, me: str, peer_chat_id: str) -> str:
        peer = self._peer_id(me, peer_chat_id)
        if not self._ton_tai(peer):
            raise ChatNotFound("Không tìm thấy người này.", code="chat_peer_not_found")
        return peer

    def _dam_bao_thanh_vien(self, cid: str, me: str, peer: str,
                            co_san: Optional[Dict[str, Member]] = None) -> Dict[str, Member]:
        tv = dict(co_san) if co_san is not None else self.repo.get_members(cid)
        if me in tv and peer in tv:
            return tv
        # Tin DAU TIEN (hoac lan tao do dang): hang hoi thoai + hai hang thanh vien la BA phep tao DOC LAP,
        # ID tat dinh, 409 = da co -> tao SONG SONG (do that staging: tuan tu ~3 x 250 ms cho tin dau).
        a, b = sorted((me, peer))

        def tao_hoi_thoai() -> None:
            try:
                self.repo.create_conversation(Conversation(id=cid, member_a=a, member_b=b, created_at=self._gio()))
            except RepoConflict:
                pass

        def tao_thanh_vien(uid: str, kia: str) -> Optional[Member]:
            try:
                return self.repo.create_member(Member(id=member_row_id(cid, uid), conversation_id=cid,
                                                      user_id=uid, peer_id=kia, updated_at=self._gio()))
            except RepoConflict:  # request song song vua tao — doc lai ben duoi
                return None

        f_ht = _POOL.submit(tao_hoi_thoai)
        f_tv = {uid: _POOL.submit(tao_thanh_vien, uid, kia) for uid, kia in ((me, peer), (peer, me)) if uid not in tv}
        f_ht.result()
        doc_lai = False
        for uid, f in f_tv.items():
            m = f.result()
            if m is None:
                doc_lai = True
            else:
                tv[uid] = m
        if doc_lai:
            tv = {**tv, **self.repo.get_members(cid)}
        if me not in tv or peer not in tv:
            raise ChatUnavailable("Chưa tạo được hội thoại — thử lại.")
        return tv

    # ------------------------------------------------------------------ gui
    def send(self, me: str, peer_chat_id: str, client_id: str, text: Any, *,
             kind: str = "text", sticker_id: Optional[str] = None,
             defer: Optional[Callable[..., Any]] = None,
             timing: Optional[Dict[str, float]] = None,
             on_created: Optional[Callable[[Message], Any]] = None) -> Tuple[Message, bool]:
        """`defer(fn)`: chay `fn` SAU khi tra loi (vd `BackgroundTasks.add_task`). Chi ban xem truoc hop
        thu duoc hoan — no idempotent va tu sua o lan gui sau. Tin + "+1 chua doc" LUON xong truoc khi
        tra loi: mot lan gui lai phai tu hoan tat duoc, nen khong buoc nao "con no" duoc hoan.
        `timing`: neu co, ghi mili-giay tung buoc (route dua vao header `Server-Timing`).
        `on_created(tin)`: goi NGAY khi tin MOI da ton tai trong kho (truoc phat tan) — duong tat cung
        instance toi luong SSE cua nguoi nhan (`local_bus.py`). Loi cua no KHONG bao gio lam hong lan gui.
        `kind="sticker"`: `sticker_id` phai co trong catalog va goi cua no MO KHOA cho nguoi gui (may chu
        quyet); `text` bi bo qua — tin luu nhan thay the "Nhãn dán: …"."""
        do = timing if timing is not None else {}
        t0 = time.perf_counter()

        def moc(ten: str) -> None:
            nonlocal t0
            t = time.perf_counter()
            do[ten] = round((t - t0) * 1000, 1)
            t0 = t

        peer = self._peer_id(me, peer_chat_id)
        goi_khoa: Optional[StickerPack] = None
        if kind == "sticker":
            van_ban, goi_khoa = self._kiem_nhan_dan(me, sticker_id)
        elif kind == "text":
            van_ban = lam_sach_van_ban(text)
        else:
            raise ChatInvalid("Loại tin nhắn không hỗ trợ.", code="chat_bad_kind")
        try:
            mid = message_row_id(client_id)
        except ValueError as exc:
            raise ChatInvalid("Mã tin nhắn không hợp lệ.", code="chat_bad_client_id") from exc
        cid = dm_id(me, peer)
        # SONG SONG: ba phep kiem + CHUAN BI giao dich phat tan (ID thanh vien tat dinh -> khong phai cho).
        f_nguoi = _POOL.submit(self._ton_tai, peer)
        f_chan = _POOL.submit(self.blocks.blocked_between, me, peer)
        f_tv = _POOL.submit(self.repo.get_members, cid)
        f_gd = _POOL.submit(self.repo.stage_fanout, mid, member_row_id(cid, peer))
        # Goi nhan dan CO DIEU KIEN (cap/su kien...): doc nguoi gui SONG SONG voi cac phep kiem khac.
        f_mo = _POOL.submit(self._nguoi_xem, me) if goi_khoa is not None else None
        gd: Any = None
        try:
            if not f_nguoi.result():
                raise ChatNotFound("Không tìm thấy người này.", code="chat_peer_not_found")
            if f_chan.result():
                raise ChatForbidden("Không gửi được tin nhắn cho người này.", code="chat_blocked")
            if f_mo is not None and goi_khoa is not None and not mo_khoa(goi_khoa, f_mo.result()):
                raise ChatForbidden(goi_khoa.unlock.label or "Nhãn dán này chưa mở khoá.", code="chat_sticker_locked")
            tv = self._dam_bao_thanh_vien(cid, me, peer, co_san=f_tv.result())
            moc("kiem")
            moi = Message(id=mid, conversation_id=cid, sender_id=me, recipient_id=peer, client_id=client_id,
                          text=van_ban, created_at=self._gio(), kind=kind,
                          sticker_id=(sticker_id or "") if kind == "sticker" else "")
            try:
                tin, tao_moi = self.repo.create_message(moi), True
            except RepoConflict:
                tin, tao_moi = self.repo.get_message(mid), False
                if tin is None:
                    raise ChatUnavailable("Không đọc lại được tin nhắn — thử lại.")
                if tin.sender_id != me or tin.conversation_id != cid:
                    raise ChatConflict("Mã tin nhắn đã được dùng.", code="chat_id_taken")
            if tao_moi and on_created is not None:
                try:
                    on_created(tin)
                except Exception:  # noqa: BLE001 — duong tat hong thi Realtime van giao
                    log.warning("messaging: đường tắt cùng instance bị lỗi (Realtime vẫn giao)", exc_info=True)
            moc("tao_tin")
            # Giao dich phat tan duoc CHUAN BI song song tu dau; chi CHO no o day — sau khi tin da ton tai.
            # (Do that staging: stage ~860 ms > ca ba phep kiem ~270 ms — cho truoc khi tao tin la de
            # tao tin nam SAU stage tren duong gang.) Thu tu CAM KET khong doi: commit chi sau tao tin.
            gd = f_gd.result()
            moc("cho_gd")
        except BaseException:
            # Khong tao duoc tin cua minh -> KHONG BAO GIO commit "+1": huy giao dich da chuan bi. Khong CHO
            # stage xong o day (tra loi 403/404 ngay); huy khi no xong, tren pool.
            if gd is not None:
                _POOL.submit(self.repo.discard_fanout, gd)
            else:
                f_gd.add_done_callback(lambda f: _POOL.submit(self._huy_gd_khi_xong, f))
            raise
        try:
            self.repo.commit_fanout(gd)
        except RepoConflict:
            pass  # da phat tan (lan gui truoc / request song song) — DUNG MOT LAN
        moc("phat_tan")
        if defer is not None:
            defer(self._cap_nhat_xem_truoc_an_toan, cid)
        else:
            self._cap_nhat_xem_truoc(cid)
        return tin, tao_moi

    def _huy_gd_khi_xong(self, f: Any) -> None:
        if f.cancelled() or f.exception() is not None:
            return  # stage hong = khong co giao dich nao de huy (het han tu dong)
        try:
            self.repo.discard_fanout(f.result())
        except Exception:  # noqa: BLE001 — giao dich khong commit se tu het han; chi ghi log
            log.warning("messaging: huỷ giao dịch chuẩn bị bị lỗi (tự hết hạn)", exc_info=True)

    def _cap_nhat_xem_truoc_an_toan(self, cid: str) -> None:
        try:
            self._cap_nhat_xem_truoc(cid)
        except Exception:  # noqa: BLE001 — chay SAU khi tra loi: khong ai nhan loi; lan gui sau tu sua
            log.warning("messaging: cập nhật xem trước bị lỗi (tự sửa ở lần gửi sau)", exc_info=True)

    def _cap_nhat_xem_truoc(self, cid: str) -> None:
        """Chay SAU commit phat tan. Them mot viec: sua cuoc dua "da doc truoc +1". Nguoi nhan dang mo cua so
        nhan tin (qua Realtime / duong tat) va `mark_read` DEM TRUOC khi "+1" cua chinh tin do duoc commit ->
        "+1" roi xuong SAU -> 1 chua doc cho mot tin DA DOC. Dau hieu: moc da doc LA CHINH tin moi nhat
        (`last_read_message_id`, KHONG so thoi gian — hai tin cung mili-giay la chuyen thuong) ma van con chua
        doc -> dem lai tu kho (cung phep dem cua `mark_read`), ghi CHUNG lan cap nhat xem truoc."""
        f_cuoi = _POOL.submit(self.repo.latest_message, cid)
        tv = self.repo.get_members(cid)
        cuoi = f_cuoi.result()
        if cuoi is None:
            return
        for m in tv.values():
            sua: Dict[str, Any] = {}
            if (m.user_id == cuoi.recipient_id and m.unread_count and m.last_read_at
                    and m.last_read_message_id == cuoi.id):
                n = self.repo.count_unread(cid, m.user_id, iso_ms(m.last_read_at))
                if n != m.unread_count:
                    sua["unread_count"] = n
            if m.last_message_id != cuoi.id and not (m.last_at and iso_ms(m.last_at) > iso_ms(cuoi.created_at)):
                # (last_at MOI HON = mot request khac da ghi ban moi hon — khong de len)
                sua.update({"last_message_id": cuoi.id, "last_text": cuoi.text[:PREVIEW_MAX],
                            "last_at": cuoi.created_at, "last_sender_id": cuoi.sender_id})
            if sua:
                sua["updated_at"] = self._gio()
                self.repo.update_member(m.id, sua)

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
        """Chan MUC TAI KHOAN qua nguon chinh tac (`self.blocks`) — chan o chat = chan o trang ca nhan."""
        peer = self.resolve_peer(me, peer_chat_id)
        self.blocks.set_blocked(me, peer, bool(blocked))
        return blocked

    def blocked_chat_ids(self, me: str) -> List[str]:
        return [chat_user_id(uid) for uid in self.blocks.blocked_by(me)]

    # ------------------------------------------------------------------ hinh dang tra ve
    @staticmethod
    def message_dto(viewer: str, m: Message) -> Dict[str, Any]:
        kia = m.recipient_id if m.sender_id == viewer else m.sender_id
        d: Dict[str, Any] = {"id": m.id, "client_id": m.client_id, "peer_id": chat_user_id(kia),
                             "from_me": m.sender_id == viewer, "text": m.text, "time": epoch_ms(m.created_at),
                             "kind": m.kind or "text"}
        if m.kind == "sticker":
            # Ma khong con trong catalog -> `sticker: null`: giao dien hien nhan thay the (`text`).
            d["sticker"] = sticker_dto(m.sticker_id)
        return d

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
