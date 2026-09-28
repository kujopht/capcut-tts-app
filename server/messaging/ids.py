"""
Dinh danh cua Fanfic Chat — TAT DINH, khong phu thuoc nha cung cap luu tru.

* `chat_user_id(uid)` — ma nguoi dung trong chat (`fw_<uid>`, dao nguoc duoc; ID la -> `fwh_<bam>`).
  Giu dung dinh dang cua Chat V1 (#239) de giao dien, `/api/chat/identities` va cuoc goi
  Tencent/TRTC sau nay (userID <= 32 byte) dung CHUNG mot ma.
* `dm_id(a, b)` — hoi thoai 1:1 cua HAI nguoi, khong phu thuoc thu tu. Vi ID suy ra tu cap nguoi,
  moi route chat duoc goi THEO NGUOI KIA (`/api/chat/dm/{peer}`): nguoi goi luon la thanh vien cua
  hoi thoai ma ho cham toi — khong co tham so "conversation_id" nao de doan/do.
* `message_row_id(client_id)` — client chon `client_id` NGAU NHIEN truoc khi gui; gui lai (mat mang,
  bam lai) dung CUNG id -> may chu nhan ra ban trung -> idempotent, va giao dien khop tin "dang gui"
  voi tin da luu bang CUNG mot id.

Moi ID <= 36 ky tu, chi `[A-Za-z0-9_-]`, bat dau bang chu — hop le o ca Appwrite 1.9.6 lan Cloud 2.x.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

#: Tencent/TRTC: userID toi da 32 byte — giu nguyen de cuoc goi sau nay dung chung ma.
USER_ID_MAX = 32
_HOP_LE = re.compile(r"^[A-Za-z0-9_-]+$")
#: Hai tien to KHAC NHAU o ky tu thu ba (`_` vs `h`) — khong the trung nhau.
TIEN_TO = "fw_"
TIEN_TO_BAM = "fwh_"
#: Client chon: chu/so, 16..32 ky tu (du ngau nhien de khong trung; du ngan cho `m_` + id <= 36).
CLIENT_ID = re.compile(r"^[A-Za-z0-9]{16,32}$")


def _bam(*phan: str, n: int = 32) -> str:
    return hashlib.sha256("|".join(phan).encode("utf-8")).hexdigest()[:n]


def chat_user_id(fanfic_user_id: str) -> str:
    uid = (fanfic_user_id or "").strip()
    if not uid:
        raise ValueError("user_id rỗng")
    if _HOP_LE.match(uid) and len(TIEN_TO) + len(uid) <= USER_ID_MAX:
        return TIEN_TO + uid
    return TIEN_TO_BAM + _bam(uid, n=USER_ID_MAX - len(TIEN_TO_BAM))


def fanfic_user_id_from_chat(chat_id: str) -> Optional[str]:
    """Nguoc cua `chat_user_id` cho dang `fw_<id>`; dang bam (mot chieu) -> None."""
    if not chat_id or chat_id.startswith(TIEN_TO_BAM):
        return None
    if chat_id.startswith(TIEN_TO) and _HOP_LE.match(chat_id) and len(chat_id) <= USER_ID_MAX:
        return chat_id[len(TIEN_TO):] or None
    return None


def dm_id(user_a: str, user_b: str) -> str:
    a, b = sorted((user_a, user_b))
    return "dm_" + _bam("dm", a, b)


def member_row_id(conversation_id: str, user_id: str) -> str:
    return "cm_" + _bam("member", conversation_id, user_id)


def message_row_id(client_id: str) -> str:
    if not CLIENT_ID.match(client_id or ""):
        raise ValueError("client_id không hợp lệ")
    return "m_" + client_id


def block_row_id(blocker_id: str, blocked_id: str, kind: str = "block") -> str:
    """ID hang `user_blocks` — CHINH XAC `server.social.block_key` cua #229 (Social/Profile), de chan qua
    chat va chan qua trang ca nhan la MOT hang, MOT he thong (khong co bang chan rieng cua chat). Khi #229
    vao `main`, thay ham nay bang `from server.social import block_key` — bai test khoa vector dau ra."""
    return "blk_" + hashlib.sha256(f"{blocker_id}\x1f{blocked_id}\x1f{kind}".encode()).hexdigest()[:24]


def conversation_row_id(user_a: str, user_b: str) -> str:
    """Hang `chat_conversations` cua mot DM = chinh `dm_id` (mot hoi thoai, mot ID)."""
    return dm_id(user_a, user_b)
