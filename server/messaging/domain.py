"""
Mo hinh du lieu cua nhan tin Fanfic (Chat V1 text) — KHONG biet Appwrite, Tencent hay HTTP.

Ban ghi (moi kho luu tru tu anh xa sang hang/document cua minh):

* `Conversation` — mot DM: hai thanh vien, luc tao. Hai thanh vien doc duoc.
* `Message`  — mot tin 1:1. `readers` = hai thanh vien: CHI ho doc duoc (quyen theo hang), va
               Realtime cua kho luu tru chi day su kien cho ho.
* `Member`   — trang thai CUA MOT NGUOI trong mot hoi thoai: so chua doc, da doc toi dau, TAT
               TIENG (rieng hoi thoai nay), ban xem truoc tin cuoi (cho hop thu). CHI chinh nguoi do doc.
* `Block`    — A CHAN B o MUC TAI KHOAN. Luu trong `user_blocks` DUNG dinh dang cua #229
               (Social/Profile) — mot he thong chan duy nhat, khong co bang chan rieng cua chat.

Moi lan GHI deu di qua backend (khoa may chu); nguoi dung khong co quyen ghi truc tiep nao.
(Khong nham voi `server/chat/` — do la AI Chat/RAG, mot tinh nang khac.)
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import List, Optional

#: Do dai toi da cua mot tin (ky tu). Xem them `service.lam_sach_van_ban`.
TEXT_MAX = 2000
#: Ban xem truoc tin cuoi trong hop thu.
PREVIEW_MAX = 120


def now_iso() -> str:
    """Thoi diem UTC, do phan giai MILI-giay — dung bang do phan giai kho luu tru giu lai (Appwrite
    luu datetime toi ms), de so sanh `created_at > last_read_at` tren ban goc va ban doc lai nhu nhau."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def iso_ms(value: str) -> str:
    """Chuan hoa moi chuoi ISO (Z/+00:00, micro/mili giay) ve dang `now_iso()` de SO SANH duoc."""
    if not value:
        return ""
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def epoch_ms(value: str) -> int:
    if not value:
        return 0
    return int(datetime.fromisoformat(iso_ms(value)).timestamp() * 1000)


@dataclass(frozen=True)
class Message:
    id: str
    conversation_id: str
    sender_id: str
    recipient_id: str
    client_id: str
    text: str
    created_at: str
    kind: str = "text"

    @property
    def readers(self) -> List[str]:
        return [self.sender_id, self.recipient_id]


@dataclass(frozen=True)
class Member:
    id: str
    conversation_id: str
    user_id: str
    peer_id: str
    unread_count: int = 0
    last_read_at: str = ""
    last_read_message_id: str = ""
    muted: bool = False
    last_message_id: str = ""
    last_text: str = ""
    last_at: str = ""
    last_sender_id: str = ""
    updated_at: str = ""

    def with_(self, **kw) -> "Member":
        return replace(self, **kw)


@dataclass(frozen=True)
class Conversation:
    id: str
    member_a: str
    member_b: str
    created_at: str
    kind: str = "dm"

    @property
    def members(self) -> List[str]:
        return [self.member_a, self.member_b]


@dataclass(frozen=True)
class Block:
    """Mot hang `user_blocks` (#229). `kind="block"` = chan HAI CHIEU; "mute" cua #229 la tat tieng NOI
    DUNG cap tai khoan (mot chieu) — KHONG phai tat tieng hoi thoai (xem `Member.muted`)."""

    id: str
    blocker_id: str
    blocked_id: str
    created_at: str
    kind: str = "block"


@dataclass(frozen=True)
class ChatEvent:
    """Su kien tu Realtime cua kho luu tru, DA chuan hoa. Dung mot trong hai truong."""

    kind: str  # "create" | "update" | "delete"
    message: Optional[Message] = None
    member: Optional[Member] = None


@dataclass
class Page:
    messages: List[Message] = field(default_factory=list)
    #: `None` = het lich su theo huong do.
    cursor: Optional[str] = None


class ChatError(Exception):
    """Loi nghiep vu co MA on dinh (giao dien hien theo ma, khong theo cau chu)."""

    http_status = 400
    code = "chat_invalid"

    def __init__(self, message: str, *, code: Optional[str] = None):
        super().__init__(message)
        if code:
            self.code = code


class ChatInvalid(ChatError):
    http_status, code = 400, "chat_invalid"


class ChatForbidden(ChatError):
    http_status, code = 403, "chat_forbidden"


class ChatNotFound(ChatError):
    http_status, code = 404, "chat_not_found"


class ChatConflict(ChatError):
    """ID da thuoc ve ban ghi KHAC (khong phai lan gui lai cua chinh minh)."""

    http_status, code = 409, "chat_conflict"


class ChatUnavailable(ChatError):
    """Kho luu tru tam thoi khong dung duoc — thu lai duoc."""

    http_status, code = 503, "chat_unavailable"


class ChatNotConfigured(ChatError):
    http_status, code = 503, "chat_not_configured"


class RepoConflict(Exception):
    """Kho luu tru: ban ghi da ton tai / giao dich xung dot. CHI dung ben trong tang kho + service."""
