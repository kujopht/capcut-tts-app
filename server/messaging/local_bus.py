"""
Duong tat CUNG INSTANCE cho tin moi: vua tao xong tin trong kho -> day THANG vao luong SSE cua nguoi nhan (va
cac tab khac cua nguoi gui) dang mo tren CHINH tien trinh nay, khong cho vong Appwrite Realtime.

Vi sao: do that staging (VN -> SGP, 2026-09-29) — Realtime cua Cloud giao tin toi nguoi nhan sau trung vi
~1 s ke tu luc gui, trong khi tin DA TON TAI trong kho sau ~370 ms. Duong tat chi NHANH HON, khong thay the:

  * Appwrite Realtime van la nguon CHINH — lien instance, va la thu bu khi mat ket noi. Instance khac / tab o
    instance khac nhan qua Realtime nhu cu;
  * luong SSE BO su kien "tin moi" trung ID (duong tat va Realtime deu toi) — trinh duyet thay DUNG MOT LAN;
  * CHI tin DA TAO THAT (sau `create_message`), CHI toi nguoi gui/nguoi nhan cua chinh tin do (`event_dto` loc
    lai theo nguoi xem lan nua); khong co gi ngoai ChatEvent da co;
  * hang doi co tran: day thi BO (Realtime van giao) — nguoi gui khong bao gio bi cham vi mot luong cham.

Tat bang `FAS_CHAT_LOCAL_FASTPATH=0` (xem `runtime.py`).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Dict, List, Set, Tuple

from server.messaging.domain import ChatEvent, Message

log = logging.getLogger("fanfic.messaging.bus")

_Dk = Tuple[asyncio.AbstractEventLoop, "asyncio.Queue[Tuple[str, object]]"]


def _dat(q: "asyncio.Queue[Tuple[str, object]]", muc: Tuple[str, object]) -> None:
    try:
        q.put_nowait(muc)
    except asyncio.QueueFull:
        pass  # luong nay dang cham — Realtime van giao, khong chan nguoi gui


class LocalChatBus:
    def __init__(self) -> None:
        self._dk: Dict[str, Set[_Dk]] = {}
        self._khoa = threading.Lock()

    def subscribe(self, user_id: str, loop: asyncio.AbstractEventLoop,
                  q: "asyncio.Queue[Tuple[str, object]]") -> Callable[[], None]:
        muc: _Dk = (loop, q)
        with self._khoa:
            self._dk.setdefault(user_id, set()).add(muc)

        def huy() -> None:
            with self._khoa:
                con = self._dk.get(user_id)
                if con is not None:
                    con.discard(muc)
                    if not con:
                        self._dk.pop(user_id, None)

        return huy

    def so_luong(self, user_id: str) -> int:
        with self._khoa:
            return len(self._dk.get(user_id, ()))

    def publish_message(self, m: Message) -> int:
        """Goi tu luong xu ly request (threadpool). Tra so luong SSE da nhan (de test/do)."""
        ev = ChatEvent("create", message=m)
        with self._khoa:
            dich: List[_Dk] = [d for uid in {m.sender_id, m.recipient_id} for d in self._dk.get(uid, ())]
        n = 0
        for loop, q in dich:
            try:
                loop.call_soon_threadsafe(_dat, q, ("local", ev))
                n += 1
            except RuntimeError:  # vong su kien da dong (luong vua ket thuc)
                continue
        return n
