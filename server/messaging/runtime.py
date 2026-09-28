"""
Lap rap nhan tin theo moi truong — noi DUY NHAT chon kho luu tru.

    FAS_CHAT_V1            "1" bat. MAC DINH: bat khi DATA_BACKEND=mock (khong cham du lieu that),
                           TAT khi DATA_BACKEND=appwrite — production chua duoc migrate/kiem cho chat
                           (xem `docs/messaging/CHAT_APPWRITE.md`). Tat -> moi route tra 503
                           `chat_not_configured`, giong ban Tencent truoc day.
    FAS_CHAT_APPWRITE_API  "tablesdb" (mac dinh, duy nhat da hien thuc + kiem tren Cloud 2.3). Gia tri
                           khac (vd "legacy" cho API Databases cu cua 1.9.6) -> TU CHOI bat, khong doan.

Tencent Chat KHONG con can cho tin nhan chu. Tencent/TRTC de danh cho goi thoai/video sau nay
(`server/chat_tencent.py` van ky UserSig, nhung khong route tin nhan nao dung no).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from server.messaging.repository import InMemoryChatRepository, InMemoryEventSource
from server.messaging.service import ChatService


@dataclass
class MessagingRuntime:
    enabled: bool
    service: Optional[ChatService]
    events: Any
    backend: str  # "memory" | "appwrite-tablesdb" | "off"
    reason: str = ""
    heartbeat_s: float = 15.0
    #: Mot luong song toi da ngan nay roi dong (client tu noi lai + bu khoang trong): khong co ket noi
    #: "treo vo han", va phien het han/bi thu hoi duoc kiem lai dinh ky.
    max_stream_s: float = 25 * 60

    def describe(self) -> dict:
        return {"enabled": self.enabled, "backend": self.backend, "reason": self.reason or None}


def _co(e: Mapping[str, str], ten: str) -> Optional[bool]:
    v = (e.get(ten) or "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return None


def build_runtime(settings: Any, *, user_exists: Callable[[str], bool],
                  env: Optional[Mapping[str, str]] = None) -> MessagingRuntime:
    e = os.environ if env is None else env
    appwrite = str(getattr(settings, "data_backend", "mock")).lower() == "appwrite"
    bat = _co(e, "FAS_CHAT_V1")
    if bat is None:
        bat = not appwrite
    if not bat:
        return MessagingRuntime(False, None, None, "off",
                                reason="FAS_CHAT_V1 chưa bật" + (" (DATA_BACKEND=appwrite)" if appwrite else ""))
    if not appwrite:
        repo = InMemoryChatRepository()
        return MessagingRuntime(True, ChatService(repo, user_exists=user_exists), InMemoryEventSource(repo), "memory")
    api = (e.get("FAS_CHAT_APPWRITE_API") or "tablesdb").strip().lower()
    if api != "tablesdb":
        return MessagingRuntime(False, None, None, "off",
                                reason=f"FAS_CHAT_APPWRITE_API={api!r} chưa được hiện thực")
    from server.messaging.appwrite_tablesdb import TablesDBChatRepository
    from server.messaging.realtime import AppwriteRealtimeSource

    repo = TablesDBChatRepository(settings)
    return MessagingRuntime(True, ChatService(repo, user_exists=user_exists), AppwriteRealtimeSource(settings),
                            "appwrite-tablesdb")
