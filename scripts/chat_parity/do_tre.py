"""
Do do tre TUNG THAO TAC cua kho nhan tin (khong qua HTTP cua Fanfic) — de biet thoi gian gui tin di dau.

    (trong tien trinh con da khoa bang rao cua dich: staging hoac may kiem 1.9.6)
    python -m scripts.chat_parity.do_tre [so_lan]

Dung ID TONG HOP (`qa_do_<ngau nhien>`) — khong cham du lieu that; tin/thanh vien tao ra nam trong hoi thoai
cua hai ID gia do. In trung vi / p90 (ms) tung thao tac + ban `send()` day du (khong co route HTTP).
"""
from __future__ import annotations

import json
import secrets
import statistics
import sys
import time
from typing import Callable, Dict, List

import httpx


def main(argv: List[str]) -> int:
    from server.messaging.domain import Member, Message, now_iso
    from server.messaging.ids import dm_id, member_row_id
    from server.main import messaging_runtime as rt

    if not rt.enabled:
        print("nhắn tin chưa bật:", rt.describe())
        return 2
    repo = rt.service.repo
    n = int(argv[0]) if argv else 8
    ra: Dict[str, List[float]] = {}

    def do(ten: str, fn: Callable[[], object]) -> object:
        t = time.perf_counter()
        kq = fn()
        ra.setdefault(ten, []).append((time.perf_counter() - t) * 1000)
        return kq

    goc = repo._goc  # noqa: SLF001 — cung endpoint kho dang dung
    with httpx.Client(timeout=20) as c:
        for _ in range(n):
            do("rtt_health_version", lambda: c.get(goc + "/v1/health/version"))
    a, b = "qa_do_" + secrets.token_hex(6), "qa_do_" + secrets.token_hex(6)
    cid = dm_id(a, b)
    for u, k in ((a, b), (b, a)):
        repo.create_member(Member(id=member_row_id(cid, u), conversation_id=cid, user_id=u, peer_id=k,
                                  updated_at=now_iso()))
    for i in range(n):
        do("get_hang_khong_co", lambda: repo.get_message("m_khongco" + secrets.token_hex(8)))
        do("truy_van_chan", lambda: repo.blocks_between(a, b))
        do("get_members", lambda: repo.get_members(cid))
        gd = do("stage_fanout", lambda: repo.stage_fanout("m_do" + secrets.token_hex(10), member_row_id(cid, b)))
        do("discard_fanout", lambda gd=gd: repo.discard_fanout(gd))
        mid = "m_do" + secrets.token_hex(10)
        do("create_message", lambda mid=mid: repo.create_message(Message(
            id=mid, conversation_id=cid, sender_id=a, recipient_id=b, client_id=mid[2:], text=f"đo {i}",
            created_at=now_iso())))
        gd = repo.stage_fanout(mid, member_row_id(cid, b))
        do("commit_fanout", lambda gd=gd: repo.commit_fanout(gd))
    tv = repo.get_members(cid)
    tom = {k: {"trung_vi": round(statistics.median(v)), "p90": round(sorted(v)[int(len(v) * 0.9) - 1 if len(v) > 1 else 0]),
               "n": len(v)} for k, v in ra.items()}
    tom["_kiem_chua_doc_b"] = tv[b].unread_count  # = n: moi commit +1 DUNG MOT LAN
    tom["_kho"] = rt.describe()
    print(json.dumps(tom, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
