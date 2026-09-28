"""
Appwrite Realtime -> luong su kien nhan tin cua MOT nguoi xem.

Backend la lop CHUYEN TIEP mong: trinh duyet chi noi chuyen voi API Fanfic (`/api/chat/stream`, SSE
qua `fetch`) — dung luat "trinh duyet chi biet NEXT_PUBLIC_API_BASE". Voi moi luong, may chu mo MOT
WebSocket toi Appwrite Realtime va xac thuc bang SESSION CUA CHINH NGUOI XEM (khong bao gio khoa API):
Appwrite tu loc su kien theo quyen doc cua hang. Do that tren Cloud 2.3 (2026-09-28):
  * xac thuc `{"type":"authentication","data":{"session":<session secret>}}` -> thanh cong, dung user;
  * nguoi thu ba KHONG nhan su kien cua hang chi A va B doc duoc;
  * hai ket noi cung mot nguoi (hai tab) deu nhan;
  * moi su kien mang CA ten kenh cu (`databases.<db>.collections.<c>.documents`) LAN ten TablesDB —
    dang ky ten CU chay tren ca Cloud 2.x lan Appwrite 1.9.6.
Appwrite la pub/sub, nen nhieu instance backend khong can kenh noi bo nao.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, AsyncIterator, Optional
from urllib.parse import quote

from server.messaging.appwrite_tablesdb import T_TIN, T_TV, row_to_member, row_to_message
from server.messaging.domain import ChatEvent, ChatUnavailable

log = logging.getLogger("fanfic.messaging.realtime")


class RealtimeAuthError(ChatUnavailable):
    code = "chat_realtime_auth"


def _ssl() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover — certifi di kem httpx
        return ssl.create_default_context()


def kenh(database_id: str) -> list:
    return [f"databases.{database_id}.collections.{T_TIN}.documents",
            f"databases.{database_id}.collections.{T_TV}.documents"]


def _bang(channels: list) -> Optional[str]:
    for c in channels or []:
        for t in (T_TIN, T_TV):
            if f".collections.{t}." in c + "." or f".tables.{t}." in c + ".":
                return t
    return None


def event_from_realtime(data: dict) -> Optional[ChatEvent]:
    """Mot su kien Realtime (truong `data`) -> `ChatEvent` chuan hoa; None neu khong phai bang chat."""
    t = _bang(data.get("channels") or [])
    events = data.get("events") or []
    kind = next((k for k in ("create", "update", "delete") if any(e.endswith("." + k) for e in events)), "")
    payload = data.get("payload") or {}
    if not t or not kind or not isinstance(payload, dict) or not payload.get("$id"):
        return None
    if t == T_TIN:
        return ChatEvent(kind, message=row_to_message(payload))
    return ChatEvent(kind, member=row_to_member(payload))


class AppwriteRealtimeSource:
    def __init__(self, settings: Any, *, connect: Any = None) -> None:
        aw = settings.appwrite if hasattr(settings, "appwrite") else settings
        goc = aw.api_base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        self._url = (goc + "/v1/realtime?project=" + quote(aw.project_id)
                     + "".join("&channels[]=" + quote(c) for c in kenh(aw.database_id)))
        self._tls = self._url.startswith("wss://")
        self._connect = connect  # test tiem ket noi gia

    async def subscribe(self, viewer_id: str, credential: str, *, heartbeat_s: float = 15.0
                        ) -> AsyncIterator[Optional[ChatEvent]]:
        if self._connect is not None:
            ws_cm = self._connect(self._url)
        else:
            import websockets

            ws_cm = websockets.connect(self._url, open_timeout=15, close_timeout=3,
                                       ssl=_ssl() if self._tls else None, max_size=2 ** 20)
        try:
            async with ws_cm as ws:
                dau = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if dau.get("type") == "error":
                    raise ChatUnavailable("Realtime từ chối kết nối.")
                await ws.send(json.dumps({"type": "authentication", "data": {"session": credential}}))
                da_xac_thuc = False
                while True:
                    try:
                        m = json.loads(await asyncio.wait_for(ws.recv(), heartbeat_s))
                    except asyncio.TimeoutError:
                        await ws.send(json.dumps({"type": "ping"}))
                        if da_xac_thuc:
                            yield None
                        continue
                    t, d = m.get("type"), m.get("data") or {}
                    if t == "response" and d.get("to") == "authentication":
                        if not d.get("success") or str((d.get("user") or {}).get("$id") or "") != viewer_id:
                            # Session khong phai cua nguoi xem nay -> KHONG phat gi ca.
                            raise RealtimeAuthError("Phiên Realtime không khớp người dùng.")
                        da_xac_thuc = True
                        yield None  # san sang
                    elif t == "error":
                        raise ChatUnavailable("Realtime báo lỗi.")
                    elif t == "event" and da_xac_thuc:
                        ev = event_from_realtime(d)
                        if ev is not None:
                            yield ev
        except (OSError, asyncio.TimeoutError) as exc:
            raise ChatUnavailable("Mất kết nối Realtime.") from exc
        except ChatUnavailable:
            raise
        except Exception as exc:  # websockets.ConnectionClosed, loi giao thuc
            if type(exc).__name__.startswith(("ConnectionClosed", "InvalidStatus", "InvalidHandshake")):
                raise ChatUnavailable("Mất kết nối Realtime.") from exc
            raise
