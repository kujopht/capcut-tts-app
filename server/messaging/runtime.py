"""
Lap rap nhan tin theo moi truong — noi DUY NHAT chon kho luu tru va AI duoc dung chat.

    FAS_CHAT_V1            "1" bat. MAC DINH: bat khi DATA_BACKEND=mock (khong cham du lieu that),
                           TAT khi DATA_BACKEND=appwrite — production CHUA tao bang chat (xem
                           `docs/messaging/CHAT_APPWRITE.md`). Tat -> moi route tra 503 `chat_not_configured`.
    FAS_CHAT_APPWRITE_API  "legacy" (MAC DINH khi DATA_BACKEND=appwrite) — API Databases, Appwrite 1.9.6
                           tu luu tru (production). "tablesdb" — Cloud 2.x (staging, `run_live` dat tuong
                           minh). Gia tri khac -> TU CHOI bat, khong doan. Khong tu do phien ban luc khoi dong.
    FAS_CHAT_LOCAL_FASTPATH "0" tat duong tat CUNG INSTANCE (`local_bus.py`). MAC DINH bat voi kho Appwrite
                           (kho bo nho da giao tuc thi, khong can).
    FAS_CHAT_V1_AUDIENCE   AI dung duoc chat khi FAS_CHAT_V1 bat:
                             "canary" — CHI user ID trong FAS_CHAT_V1_CANARY_USERS; danh sach rong = KHONG AI.
                                        MAC DINH khi DATA_BACKEND=appwrite (fail-closed: bat FAS_CHAT_V1 ma quen
                                        danh sach thi khong mo cho ca production).
                             "all"    — moi nguoi da dang nhap. MAC DINH khi DATA_BACKEND=mock (dev/test).
                           Gia tri khac -> chat TAT, co ly do (khong doan).
    FAS_CHAT_V1_CANARY_USERS  user ID Fanfic (ID tai khoan Appwrite), cach nhau bang dau phay/khoang trang. KHONG
                           nhan email/ten — chi ID. Muc khong dung dang bi bo (chi dem, khong in).

Nghiep vu (`ChatService`), route va giao dien GIONG HET giua hai kho. Tencent Chat KHONG duoc dung cho
tin nhan chu.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet, Mapping, Optional, Tuple

from server.messaging.local_bus import LocalChatBus
from server.messaging.repository import InMemoryChatRepository, InMemoryEventSource
from server.messaging.service import ChatService

log = logging.getLogger("fanfic.messaging")

KHO_APPWRITE = ("legacy", "tablesdb")
KHAN_GIA = ("canary", "all")
#: ID tai khoan Appwrite: BAT DAU bang chu/so, sau do chu, so, `.`, `_`, `-`; toi da 36 ky tu (luat ID cua Appwrite).
#: Email (`@`), duong dan (`/`, `..`), khoang trang KHONG bao gio khop.
_ID_HOP_LE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,35}$")


@dataclass
class MessagingRuntime:
    enabled: bool
    service: Optional[ChatService]
    events: Any
    backend: str  # "memory" | "appwrite-legacy" | "appwrite-tablesdb" | "off"
    reason: str = ""
    heartbeat_s: float = 15.0
    #: Mot luong song toi da ngan nay roi dong (client tu noi lai + bu khoang trong): khong co ket noi
    #: "treo vo han", va phien het han/bi thu hoi duoc kiem lai dinh ky.
    max_stream_s: float = 25 * 60
    #: Duong tat cung instance cho tin moi (`local_bus.py`); `None` = chi Realtime.
    bus: Optional[LocalChatBus] = None
    #: "all" | "canary" — xem docstring module.
    audience: str = "all"
    canary_users: FrozenSet[str] = field(default_factory=frozenset)

    def allows(self, user_id: str) -> bool:
        """Nguoi NAY dung duoc chat khong: may chu bat VA (mo cho tat ca HOAC co trong danh sach canary)."""
        return self.enabled and self.peer_allowed(user_id)

    def peer_allowed(self, user_id: str) -> bool:
        """Nguoi kia co trong khan gia khong (khong xet may chu bat) — canary chi nhan tin voi canary."""
        return self.audience == "all" or (bool(user_id) and user_id in self.canary_users)

    def describe(self) -> dict:
        # CHI so luong canary, khong liet ke ID (describe di vao health/log).
        return {"enabled": self.enabled, "backend": self.backend, "reason": self.reason or None,
                "local_fastpath": self.bus is not None, "audience": self.audience,
                "canary_users": len(self.canary_users) if self.audience == "canary" else None}


def _co(e: Mapping[str, str], ten: str) -> Optional[bool]:
    v = (e.get(ten) or "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return None


def doc_canary(raw: Optional[str]) -> Tuple[FrozenSet[str], int]:
    """(ID hop le, so muc bi bo). Tach bang dau phay / khoang trang; bo muc rong."""
    muc = [x for x in re.split(r"[\s,;]+", raw or "") if x]
    hop_le = frozenset(x for x in muc if _ID_HOP_LE.match(x))
    return hop_le, len(muc) - len([x for x in muc if _ID_HOP_LE.match(x)])


def _khan_gia(e: Mapping[str, str], appwrite: bool) -> Tuple[Optional[str], FrozenSet[str]]:
    kg = (e.get("FAS_CHAT_V1_AUDIENCE") or ("canary" if appwrite else "all")).strip().lower()
    if kg not in KHAN_GIA:
        return None, frozenset()
    ds, bo = doc_canary(e.get("FAS_CHAT_V1_CANARY_USERS"))
    if bo:
        log.warning("messaging: bỏ %d mục không phải user ID trong FAS_CHAT_V1_CANARY_USERS", bo)
    if kg == "canary" and not ds:
        log.warning("messaging: FAS_CHAT_V1_AUDIENCE=canary với danh sách RỖNG — không ai dùng được chat")
    return kg, ds


def build_runtime(settings: Any, *, user_exists: Callable[[str], bool],
                  env: Optional[Mapping[str, str]] = None, blocks: Optional[Any] = None,
                  viewer_of: Optional[Callable[[str], Any]] = None) -> MessagingRuntime:
    """`blocks`: nguon chan CHINH TAC (Social Play V1, #229 — `server/main.py::_ChanQuaSocial`). `None` = doc/
    ghi thang cung hang `user_blocks` qua kho chat (`service.RepoBlocks`). `viewer_of`: cap/thanh tich cua
    nguoi gui cho luat mo khoa nhan dan (`stickers.py`)."""
    e = os.environ if env is None else env
    appwrite = str(getattr(settings, "data_backend", "mock")).lower() == "appwrite"
    bat = _co(e, "FAS_CHAT_V1")
    if bat is None:
        bat = not appwrite
    if not bat:
        return MessagingRuntime(False, None, None, "off",
                                reason="FAS_CHAT_V1 chưa bật" + (" (DATA_BACKEND=appwrite)" if appwrite else ""))
    kg, canary = _khan_gia(e, appwrite)
    if kg is None:
        return MessagingRuntime(False, None, None, "off",
                                reason=f"FAS_CHAT_V1_AUDIENCE={e.get('FAS_CHAT_V1_AUDIENCE')!r} không hợp lệ (canary | all)")
    if not appwrite:
        repo = InMemoryChatRepository()
        return MessagingRuntime(True, ChatService(repo, user_exists=user_exists, blocks=blocks, viewer_of=viewer_of),
                                InMemoryEventSource(repo), "memory", audience=kg, canary_users=canary)
    api = (e.get("FAS_CHAT_APPWRITE_API") or "legacy").strip().lower()
    if api not in KHO_APPWRITE:
        return MessagingRuntime(False, None, None, "off",
                                reason=f"FAS_CHAT_APPWRITE_API={api!r} không hợp lệ (legacy | tablesdb)")
    from server.messaging.appwrite import LegacyAppwriteChatRepository, TablesDBChatRepository
    from server.messaging.realtime import AppwriteRealtimeSource

    repo = (LegacyAppwriteChatRepository if api == "legacy" else TablesDBChatRepository)(settings)
    # Realtime dang ky ten kenh KIEU CU — do that: Cloud 2.3 phat ca hai kieu ten, 1.9.6 phat kieu cu.
    bus = None if _co(e, "FAS_CHAT_LOCAL_FASTPATH") is False else LocalChatBus()
    return MessagingRuntime(True, ChatService(repo, user_exists=user_exists, blocks=blocks, viewer_of=viewer_of),
                            AppwriteRealtimeSource(settings), f"appwrite-{api}", bus=bus, audience=kg,
                            canary_users=canary)
