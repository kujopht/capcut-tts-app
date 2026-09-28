"""
Lap rap nhan tin theo moi truong — noi DUY NHAT chon kho luu tru.

    FAS_CHAT_V1            "1" bat. MAC DINH: bat khi DATA_BACKEND=mock (khong cham du lieu that),
                           TAT khi DATA_BACKEND=appwrite — production CHUA tao bang chat (xem
                           `docs/messaging/CHAT_APPWRITE.md`). Tat -> moi route tra 503 `chat_not_configured`.
    FAS_CHAT_APPWRITE_API  "legacy" (MAC DINH khi DATA_BACKEND=appwrite) — API Databases, Appwrite 1.9.6
                           tu luu tru (production). "tablesdb" — Cloud 2.x (staging, `run_live` dat tuong
                           minh). Gia tri khac -> TU CHOI bat, khong doan. Khong tu do phien ban luc khoi dong.

Nghiep vu (`ChatService`), route va giao dien GIONG HET giua hai kho. Tencent Chat KHONG duoc dung cho
tin nhan chu.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from server.messaging.repository import InMemoryChatRepository, InMemoryEventSource
from server.messaging.service import ChatService

KHO_APPWRITE = ("legacy", "tablesdb")


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
    api = (e.get("FAS_CHAT_APPWRITE_API") or "legacy").strip().lower()
    if api not in KHO_APPWRITE:
        return MessagingRuntime(False, None, None, "off",
                                reason=f"FAS_CHAT_APPWRITE_API={api!r} không hợp lệ (legacy | tablesdb)")
    from server.messaging.appwrite import LegacyAppwriteChatRepository, TablesDBChatRepository
    from server.messaging.realtime import AppwriteRealtimeSource

    repo = (LegacyAppwriteChatRepository if api == "legacy" else TablesDBChatRepository)(settings)
    # Realtime dang ky ten kenh KIEU CU — do that: Cloud 2.3 phat ca hai kieu ten, 1.9.6 phat kieu cu.
    return MessagingRuntime(True, ChatService(repo, user_exists=user_exists), AppwriteRealtimeSource(settings),
                            f"appwrite-{api}")
