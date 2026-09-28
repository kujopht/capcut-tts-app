"""
Nhan tin 1:1 (Chat V1, phan chu) — `server/messaging/`. KHONG goi mang: kho bo nho + Realtime mo phong
(cung ngu nghia loc theo nguoi doc nhu Appwrite), Appwrite gia cho kho TablesDB, WebSocket gia cho
Realtime. Bo sung cho bo test SONG tren fanfic-staging (`scripts/staging/live/test_chat_live.py`).

Nhom kiem (dung yeu cau): quyen DM, giao Realtime, chua doc/da doc, noi lai, phan trang, gui idempotent,
chan/tat tieng, nhieu tab, truy cap hoi thoai trai phep.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import unittest
from typing import Any, Dict, List

import httpx
from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.messaging.appwrite import TablesDBChatRepository
from server.messaging.domain import ChatEvent, Member, Message, RepoConflict
from server.messaging.ids import chat_user_id, dm_id
from server.messaging.realtime import AppwriteRealtimeSource, RealtimeAuthError, event_from_realtime
from server.messaging.repository import InMemoryChatRepository, InMemoryEventSource
from server.messaging.runtime import build_runtime
from server.messaging.service import ChatService
from server.rate_limit import limiter as rate_limit_limiter

MK = "matkhau123"


def cid(n: int) -> str:
    return f"c{n:019d}"  # client_id hop le (20 ky tu)


class MessagingCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        rate_limit_limiter.reset()
        self.rt = server_main.messaging_runtime
        self._cu = (self.rt.service, self.rt.events, self.rt.enabled, self.rt.heartbeat_s, self.rt.max_stream_s)
        self.repo = InMemoryChatRepository()
        self.rt.service = ChatService(self.repo, user_exists=server_main._nguoi_chat_ton_tai)
        self.rt.events = InMemoryEventSource(self.repo)
        self.rt.enabled, self.rt.heartbeat_s, self.rt.max_stream_s = True, 0.3, 6.0
        self.client = TestClient(server_main.app)
        self.sv = self.rt.service

    def tearDown(self) -> None:
        self.rt.service, self.rt.events, self.rt.enabled, self.rt.heartbeat_s, self.rt.max_stream_s = self._cu

    def nguoi(self, ten: str):
        p = server_main.identity.register(f"{ten}@example.com", MK, ten)
        tok = server_main.identity.login(f"{ten}@example.com", MK)
        return p.user_id, chat_user_id(p.user_id), {"Authorization": f"Bearer {tok}"}

    def gui(self, hd, peer, n, text="xin chào"):
        return self.client.post(f"/api/chat/dm/{peer}/messages", headers=hd, json={"client_id": cid(n), "text": text})

    def hop_thu(self, hd):
        r = self.client.get("/api/chat/conversations", headers=hd)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    # ------------------------------------------------------------- nghe SSE o luong rieng
    # `TestClient` cua Starlette GOM HET body roi moi tra — khong kiem duoc mot luong dang mo. Cac bai
    # Realtime chay tren UVICORN THAT (cung app, cung middleware that: han muc, header bao mat...), nen
    # bai test cung chung minh khong middleware nao gom luong SSE lai.
    _may: Any = None

    @classmethod
    def may_that(cls) -> str:
        if MessagingCase._may is None:
            import socket

            import uvicorn

            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            cong = s.getsockname()[1]
            s.close()
            may = uvicorn.Server(uvicorn.Config(server_main.app, host="127.0.0.1", port=cong, log_level="warning"))
            threading.Thread(target=may.run, daemon=True).start()
            het = time.time() + 15
            while not may.started and time.time() < het:
                time.sleep(0.05)
            MessagingCase._may = f"http://127.0.0.1:{cong}"
        return MessagingCase._may

    def nghe(self, hd) -> Dict[str, Any]:
        st: Dict[str, Any] = {"events": [], "ready": threading.Event(), "dung": threading.Event(), "status": None}
        goc = self.may_that()

        def chay():
            with httpx.Client(base_url=goc, timeout=httpx.Timeout(20.0)) as c, \
                    c.stream("GET", "/api/chat/stream", headers=hd) as r:
                st["status"] = r.status_code
                ten = None
                for dong in r.iter_lines():
                    if dong.startswith("event: "):
                        ten = dong[7:]
                    elif dong.startswith("data: "):
                        d = json.loads(dong[6:])
                        if ten == "ready":
                            st["ready"].set()
                        else:
                            st["events"].append((ten or "data", d))
                        ten = None
                    if st["dung"].is_set():
                        break
        st["thread"] = threading.Thread(target=chay, daemon=True)
        st["thread"].start()
        self.assertTrue(st["ready"].wait(5), f"luong không sẵn sàng (status={st['status']})")
        return st

    def cho(self, st, dk, giay=4.0) -> bool:
        het = time.time() + giay
        while time.time() < het:
            if dk(st["events"]):
                return True
            time.sleep(0.05)
        return False

    def dong(self, *sts):
        for st in sts:
            st["dung"].set()
        for st in sts:
            st["thread"].join(8)


class QuyenDmTest(MessagingCase):
    def test_khach_khong_dung_duoc_route_nao(self):
        _, b, _ = self.nguoi("b1")
        for m, u in (("GET", "/api/chat/conversations"), ("GET", f"/api/chat/dm/{b}/messages"),
                     ("GET", "/api/chat/stream"), ("GET", "/api/chat/blocks")):
            self.assertEqual(self.client.request(m, u).status_code, 401, u)
        r = self.client.post(f"/api/chat/dm/{b}/messages", json={"client_id": cid(1), "text": "x"})
        self.assertEqual(r.status_code, 401)

    def test_khong_nhan_cho_chinh_minh_nguoi_khong_ton_tai_hay_id_bam(self):
        _, a, ha = self.nguoi("a1")
        self.assertEqual(self.gui(ha, a, 1).json()["detail"]["code"], "chat_self")
        r = self.gui(ha, "fw_khong_co_ai_ca", 2)
        self.assertEqual((r.status_code, r.json()["detail"]["code"]), (404, "chat_peer_not_found"))
        self.assertEqual(self.gui(ha, "fwh_" + "0" * 28, 3).status_code, 404)
        self.assertEqual(self.gui(ha, "../../etc", 4).status_code, 404)  # route khong khop

    def test_tat_co_503_ro_rang(self):
        _, b, ha = self.nguoi("t1")
        self.rt.enabled = False
        r = self.client.get("/api/chat/conversations", headers=ha)
        self.assertEqual((r.status_code, r.json()["detail"]["code"]), (503, "chat_not_configured"))

    def test_van_ban_rong_qua_dai_va_ky_tu_an(self):
        _, b, ha = self.nguoi("v1")
        self.nguoi("v2")
        _, b, _ = self.nguoi("v3")
        self.assertEqual(self.gui(ha, b, 1, "   ​ ").json()["detail"]["code"], "chat_empty")
        self.assertEqual(self.gui(ha, b, 2, "x" * 2001).json()["detail"]["code"], "chat_too_long")
        r = self.gui(ha, b, 3, "a‮b\u0007c")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["message"]["text"], "abc")
        bad = self.client.post(f"/api/chat/dm/{b}/messages", headers=ha, json={"client_id": "ngan", "text": "x"})
        self.assertEqual(bad.status_code, 422)


class GuiIdempotentTest(MessagingCase):
    def test_gui_lai_cung_client_id_mot_tin_mot_lan_chua_doc(self):
        ua, a, ha = self.nguoi("ia")
        ub, b, hb = self.nguoi("ib")
        r1, r2 = self.gui(ha, b, 7, "lần đầu"), self.gui(ha, b, 7, "lần hai khác chữ")
        self.assertEqual((r1.json()["created"], r2.json()["created"]), (True, False))
        self.assertEqual(r1.json()["message"]["id"], r2.json()["message"]["id"])
        self.assertEqual(r2.json()["message"]["text"], "lần đầu", "lần gửi lại trả tin GỐC")
        self.assertEqual(len(self.repo.list_messages(dm_id(ua, ub))), 1)
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], 1)

    def test_gui_lai_dong_thoi_dung_mot_tin_dung_mot_lan_chua_doc(self):
        ua, a, _ = self.nguoi("ca")
        ub, b, hb = self.nguoi("cb")
        rao = threading.Barrier(8)
        loi: List[BaseException] = []

        def mot():
            rao.wait()
            try:
                self.sv.send(ua, b, cid(42), "cùng lúc")
            except BaseException as exc:  # noqa: BLE001
                loi.append(exc)
        ts = [threading.Thread(target=mot) for _ in range(8)]
        [t.start() for t in ts]
        [t.join(10) for t in ts]
        self.assertEqual(loi, [])
        self.assertEqual(len(self.repo.list_messages(dm_id(ua, ub))), 1)
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], 1)

    def test_client_id_cua_nguoi_khac_409(self):
        ua, a, ha = self.nguoi("xa")
        _, b, _ = self.nguoi("xb")
        _, c, hc = self.nguoi("xc")
        self.assertEqual(self.gui(ha, b, 9).status_code, 200)
        r = self.gui(hc, b, 9)
        self.assertEqual((r.status_code, r.json()["detail"]["code"]), (409, "chat_id_taken"))

    def test_su_co_giua_tao_tin_va_phat_tan_duoc_lan_gui_lai_hoan_tat(self):
        ua, a, _ = self.nguoi("ra")
        ub, b, hb = self.nguoi("rb")
        goc = self.repo.commit_fanout

        def hong(*_a, **_k):
            raise RuntimeError("sập giữa chừng")
        self.repo.commit_fanout = hong
        with self.assertRaises(RuntimeError):
            self.sv.send(ua, b, cid(5), "tin")
        self.repo.commit_fanout = goc
        self.assertEqual(self.hop_thu(hb)["items"], [], "chưa phát tán thì chưa có xem trước")
        _, moi = self.sv.send(ua, b, cid(5), "tin")
        self.assertFalse(moi)
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], 1)


class ThuTuPhatTanTest(MessagingCase):
    """Giao dich phat tan duoc CHUAN BI song song, nhung: tao tin KHONG cho no (do tre), commit LUON sau tao
    tin (dung mot lan), va bi chan thi tra loi NGAY roi huy giao dich khi no chuan bi xong — khong commit."""

    def _ghi(self, cham: float) -> List[str]:
        sk: List[str] = []
        khoa = threading.Lock()

        def boc(ten, fn, truoc=0.0):
            def f(*a, **k):
                if truoc:
                    time.sleep(truoc)
                kq = fn(*a, **k)
                with khoa:
                    sk.append(ten)
                return kq
            return f
        r = self.repo
        r.stage_fanout = boc("stage", r.stage_fanout, cham)
        r.create_message = boc("tao_tin", r.create_message)
        r.commit_fanout = boc("commit", r.commit_fanout)
        r.discard_fanout = boc("huy", r.discard_fanout)
        return sk

    def test_tao_tin_khong_cho_stage_commit_sau_ca_hai(self):
        ua, a, _ = self.nguoi("ta")
        ub, b, hb = self.nguoi("tb")
        sk = self._ghi(0.3)
        self.sv.send(ua, b, cid(61), "một")
        self.assertEqual(sk, ["tao_tin", "stage", "commit"])
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], 1)

    def test_bi_chan_tra_loi_ngay_huy_giao_dich_khong_commit(self):
        from server.messaging.domain import ChatForbidden

        ua, a, _ = self.nguoi("tc")
        ub, b, hb = self.nguoi("td")
        self.sv.set_blocked(ub, a, True)
        sk = self._ghi(0.4)
        t0 = time.perf_counter()
        with self.assertRaises(ChatForbidden):
            self.sv.send(ua, b, cid(62), "bị chặn")
        self.assertLess(time.perf_counter() - t0, 0.3, "403 không được chờ giao dịch chuẩn bị")
        het = time.time() + 3
        while "huy" not in sk and time.time() < het:
            time.sleep(0.02)
        self.assertEqual(sk, ["stage", "huy"])


class DoTreGuiTest(MessagingCase):
    def test_xem_truoc_duoc_hoan_nhung_chua_doc_thi_khong(self):
        ua, a, _ = self.nguoi("da")
        ub, b, hb = self.nguoi("db")
        hoan: List[Any] = []
        self.sv.send(ua, b, cid(1), "tin", defer=lambda f, *a: hoan.append((f, a)))
        tv = self.repo.get_members(dm_id(ua, ub))
        self.assertEqual(tv[ub].unread_count, 1, "+1 chưa đọc PHẢI xong trước khi trả lời")
        self.assertEqual(tv[ub].last_message_id, "", "xem trước được hoãn")
        f, args = hoan[0]
        f(*args)
        self.assertEqual(self.hop_thu(hb)["items"][0]["last_text"], "tin")

    def test_nho_nguoi_ton_tai_chi_ket_qua_duong_va_loi_nen_khong_lam_hong(self):
        ua, a, _ = self.nguoi("ea")
        ub, b, _ = self.nguoi("eb")
        goi: List[str] = []
        goc = self.sv._co_nguoi
        self.sv._co_nguoi = lambda u: (goi.append(u), goc(u))[1]
        for i in range(3):
            self.sv.send(ua, b, cid(10 + i), f"t{i}")
        self.assertEqual(goi, [ub], "người tồn tại chỉ hỏi MỘT lần")
        with self.assertRaises(Exception):
            self.sv.send(ua, "fw_khongtontai00000", cid(20), "x")
        with self.assertRaises(Exception):
            self.sv.send(ua, "fw_khongtontai00000", cid(21), "x")
        self.assertEqual(goi.count("khongtontai00000"), 2, "kết quả ÂM không được nhớ")
        # loi o buoc chay nen chi ghi log, khong nem
        self.repo.latest_message = lambda *_a: (_ for _ in ()).throw(RuntimeError("sập"))
        self.sv._cap_nhat_xem_truoc_an_toan(dm_id(ua, ub))


class ChuaDocVaPhanTrangTest(MessagingCase):
    def test_chua_doc_da_doc_toi_moc_va_tong_tru_tat_tieng(self):
        ua, a, ha = self.nguoi("ua")
        ub, b, hb = self.nguoi("ub")
        ids = [self.gui(ha, b, i, f"tin {i}").json()["message"]["id"] for i in range(3)]
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], 3)
        self.assertEqual(self.hop_thu(ha)["items"][0]["unread"], 0, "tin của mình không tính chưa đọc")
        r = self.client.post(f"/api/chat/dm/{a}/read", headers=hb, json={"up_to": ids[1]})
        self.assertEqual(r.json()["conversation"]["unread"], 1)
        self.client.post(f"/api/chat/dm/{a}/read", headers=hb, json={})
        self.assertEqual(self.hop_thu(hb)["unread_total"], 0)
        # moc da doc khong lui: doc lai moc cu khong lam tang chua doc
        self.client.post(f"/api/chat/dm/{a}/read", headers=hb, json={"up_to": ids[0]})
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], 0)
        # tat tieng: van dem theo hoi thoai, KHONG vao tong
        _, c, hc = self.nguoi("uc")
        self.gui(hc, b, 50)
        self.client.post(f"/api/chat/dm/{c}/mute", headers=hb, json={"muted": True})
        h = self.hop_thu(hb)
        theo = {it["peer_id"]: it for it in h["items"]}
        self.assertEqual((theo[c]["unread"], theo[c]["muted"], h["unread_total"]), (1, True, 0))
        self.client.post(f"/api/chat/dm/{c}/mute", headers=hb, json={"muted": False})
        self.assertEqual(self.hop_thu(hb)["unread_total"], 1)

    def test_phan_trang_lui_khong_trung_khong_sot_va_bu_khoang_trong_tien(self):
        ua, a, ha = self.nguoi("pa")
        ub, b, hb = self.nguoi("pb")
        for i in range(75):
            self.sv.send(ua, b, cid(1000 + i), f"tin {i}")
        thay, con_tro, trang = [], None, 0
        while True:
            q = f"?limit=30" + (f"&before={con_tro}" if con_tro else "")
            d = self.client.get(f"/api/chat/dm/{a}/messages{q}", headers=hb).json()
            thay = [m["text"] for m in d["messages"]] + thay
            trang += 1
            con_tro = d["cursor"]
            if not con_tro:
                break
        self.assertEqual(trang, 3)
        self.assertEqual(thay, [f"tin {i}" for i in range(75)])
        moc = self.repo.list_messages(dm_id(ua, ub), limit=1)[0].id
        for i in range(3):
            self.sv.send(ua, b, cid(2000 + i), f"mới {i}")
        d = self.client.get(f"/api/chat/dm/{a}/messages?after={moc}", headers=hb).json()
        self.assertEqual([m["text"] for m in d["messages"]], ["mới 0", "mới 1", "mới 2"])

    def test_con_tro_cua_hoi_thoai_khac_bi_tu_choi_nhu_con_tro_rac(self):
        ua, a, ha = self.nguoi("ka")
        ub, b, hb = self.nguoi("kb")
        uc, c, hc = self.nguoi("kc")
        id_ab = self.gui(ha, b, 1, "bí mật A-B").json()["message"]["id"]
        for q in (f"before={id_ab}", f"after={id_ab}", "before=m_khongtontai0000000"):
            r = self.client.get(f"/api/chat/dm/{a}/messages?{q}", headers=hc)
            self.assertEqual((r.status_code, r.json()["detail"]["code"]), (400, "chat_bad_cursor"), q)
        r = self.client.post(f"/api/chat/dm/{a}/read", headers=hc, json={"up_to": id_ab})
        self.assertIn(r.status_code, (200, 400))
        self.assertNotIn("bí mật", r.text)


class ChanTest(MessagingCase):
    def test_chan_hai_chieu_bo_chan_va_danh_sach(self):
        ua, a, ha = self.nguoi("ba")
        ub, b, hb = self.nguoi("bb")
        self.assertEqual(self.gui(ha, b, 1).status_code, 200)
        self.assertEqual(self.client.post(f"/api/chat/dm/{b}/block", headers=ha, json={"blocked": True}).status_code, 200)
        for hd, peer, n in ((hb, a, 2), (ha, b, 3)):
            r = self.gui(hd, peer, n)
            self.assertEqual((r.status_code, r.json()["detail"]["code"]), (403, "chat_blocked"))
        self.assertEqual(self.client.get("/api/chat/blocks", headers=ha).json()["items"], [b])
        self.assertEqual(self.client.get("/api/chat/blocks", headers=hb).json()["items"], [], "B không thấy ai chặn mình")
        self.client.post(f"/api/chat/dm/{b}/block", headers=ha, json={"blocked": False})
        self.assertEqual(self.gui(hb, a, 4).status_code, 200)
        self.assertEqual(len(self.repo.list_messages(dm_id(ua, ub))), 2)

    def test_chan_la_hang_user_blocks_229_lich_su_con_va_khong_cong_chua_doc(self):
        from server.messaging.domain import Block
        from server.messaging.ids import block_row_id

        ua, a, ha = self.nguoi("ua1")
        ub, b, hb = self.nguoi("ub1")
        self.gui(ha, b, 1, "trước khi chặn")
        self.client.post(f"/api/chat/dm/{a}/block", headers=hb, json={"blocked": True})
        hang = self.repo._chan[block_row_id(ub, ua)]
        self.assertEqual((hang.blocker_id, hang.blocked_id, hang.kind), (ub, ua, "block"), "đúng hàng #229")
        truoc = self.hop_thu(hb)["items"][0]["unread"]
        self.assertEqual(self.gui(ha, b, 2, "sau khi bị chặn").status_code, 403)
        self.assertEqual(self.hop_thu(hb)["items"][0]["unread"], truoc, "bị chặn: KHÔNG cộng chưa đọc")
        self.assertEqual([m.text for m in self.repo.list_messages(dm_id(ua, ub))], ["trước khi chặn"])
        for hd, peer in ((ha, b), (hb, a)):  # lich su CU van doc duoc o CA HAI phia
            ds = self.client.get(f"/api/chat/dm/{peer}/messages", headers=hd).json()["messages"]
            self.assertEqual([m["text"] for m in ds], ["trước khi chặn"])
        # "mute" cua Social (#229) = an NOI DUNG, KHONG chan tin nhan
        self.client.post(f"/api/chat/dm/{a}/block", headers=hb, json={"blocked": False})
        self.repo.create_block(Block(id=block_row_id(ub, ua, "mute"), blocker_id=ub, blocked_id=ua,
                                     created_at="2026-09-28T00:00:00.000+00:00", kind="mute"))
        self.assertEqual(self.gui(ha, b, 3, "tắt tiếng nội dung không chặn DM").status_code, 200)

    def test_tin_dau_tien_tao_hang_hoi_thoai_cho_hai_nguoi(self):
        ua, a, ha = self.nguoi("hta")
        ub, b, _ = self.nguoi("htb")
        self.assertIsNone(self.repo.get_conversation(dm_id(ua, ub)))
        self.gui(ha, b, 1)
        ht = self.repo.get_conversation(dm_id(ua, ub))
        self.assertEqual(sorted(ht.members), sorted([ua, ub]))
        self.assertEqual(ht.kind, "dm")


class RealtimeTest(MessagingCase):
    def test_giao_cho_hai_ben_nhieu_tab_va_nguoi_thu_ba_khong_nhan_gi(self):
        ua, a, ha = self.nguoi("ra1")
        ub, b, hb = self.nguoi("rb1")
        uc, c, hc = self.nguoi("rc1")
        sa, sb1, sb2, sc = self.nghe(ha), self.nghe(hb), self.nghe(hb), self.nghe(hc)
        try:
            mid = self.gui(ha, b, 11, "chào B").json()["message"]["id"]
            co_tin = lambda evs: any(t == "data" and d.get("type") == "message" and d["message"]["id"] == mid for t, d in evs)  # noqa: E731
            for st in (sa, sb1, sb2):
                self.assertTrue(self.cho(st, co_tin), "tin không tới một luồng của người trong hội thoại")
            tin_b = next(d["message"] for t, d in sb1["events"] if d.get("type") == "message")
            self.assertEqual((tin_b["from_me"], tin_b["peer_id"], tin_b["text"]), (False, a, "chào B"))
            self.assertTrue(self.cho(sb1, lambda evs: any(d.get("type") == "conversation" and d["conversation"]["unread"] == 1
                                                           for _, d in evs)))
            # DA TAB: tab 1 danh dau da doc -> tab 2 nhan hoi thoai unread=0
            self.client.post(f"/api/chat/dm/{a}/read", headers=hb, json={})
            self.assertTrue(self.cho(sb2, lambda evs: any(d.get("type") == "conversation" and d["conversation"]["unread"] == 0
                                                           for _, d in evs)))
            time.sleep(0.5)
            self.assertEqual(sc["events"], [], "người thứ ba KHÔNG được nhận gì của hội thoại A-B")
            than = json.dumps(sa["events"] + sb1["events"], ensure_ascii=False)
            self.assertNotIn("@example.com", than)
            self.assertNotIn("Bearer", than)
        finally:
            self.dong(sa, sb1, sb2, sc)

    def test_noi_lai_bu_khoang_trong_khong_trung(self):
        ua, a, ha = self.nguoi("na")
        ub, b, hb = self.nguoi("nb")
        sb = self.nghe(hb)
        m1 = self.gui(ha, b, 21, "trước khi rớt").json()["message"]["id"]
        self.assertTrue(self.cho(sb, lambda evs: any(d.get("type") == "message" for _, d in evs)))
        self.dong(sb)  # mat ket noi
        for i in range(3):
            self.gui(ha, b, 30 + i, f"lúc rớt {i}")
        sb2 = self.nghe(hb)  # noi lai
        try:
            d = self.client.get(f"/api/chat/dm/{a}/messages?after={m1}", headers=hb).json()
            self.assertEqual([m["text"] for m in d["messages"]], ["lúc rớt 0", "lúc rớt 1", "lúc rớt 2"])
            self.gui(ha, b, 40, "sau khi nối lại")
            self.assertTrue(self.cho(sb2, lambda evs: any(d.get("type") == "message" and d["message"]["text"] == "sau khi nối lại"
                                                           for _, d in evs)))
        finally:
            self.dong(sb2)

    def test_tran_luong_dong_thoi_moi_nguoi_va_tra_cho_khi_dong(self):
        from unittest.mock import patch

        from server.messaging import routes as r

        _, _, ha = self.nguoi("tr")
        with patch.object(r, "LUONG_DONG_THOI_TOI_DA", 1):
            s1 = self.nghe(ha)
            try:
                x = httpx.get(self.may_that() + "/api/chat/stream", headers=ha, timeout=10)
                self.assertEqual((x.status_code, x.json()["detail"]["code"]), (429, "chat_too_many_streams"))
            finally:
                self.dong(s1)
            time.sleep(0.5)
            s2 = self.nghe(ha)  # cho da duoc tra khi luong 1 dong
            self.dong(s2)

    def test_luong_tu_dong_sau_han_song_toi_da(self):
        _, _, ha = self.nguoi("la")
        self.rt.max_stream_s = 0.5
        with self.client.stream("GET", "/api/chat/stream", headers=ha) as r:
            dong = [x for x in r.iter_lines() if x.startswith("event: ")]
        self.assertEqual(dong[0], "event: ready")
        self.assertEqual(dong[-1], "event: bye")
        self.assertEqual(self.repo.hub.count(), 0, "đăng ký phải được gỡ khi luồng đóng")

    def test_event_dto_loc_lan_nua_theo_nguoi_xem(self):
        m = Message(id="m_x", conversation_id="dm_x", sender_id="A", recipient_id="B", client_id=cid(1), text="t",
                    created_at="2026-09-28T00:00:00.000+00:00")
        self.assertIsNone(self.sv.event_dto("C", ChatEvent("create", message=m)))
        tv = Member(id="cm_x", conversation_id="dm_x", user_id="B", peer_id="A", last_message_id="m_x")
        self.assertIsNone(self.sv.event_dto("A", ChatEvent("update", member=tv)))
        self.assertEqual(self.sv.event_dto("B", ChatEvent("update", member=tv))["type"], "conversation")


# ============================================================================ kho Appwrite (gia, HAI API)


class _AppwriteGia:
    """Mo phong DUNG cac hanh vi da DO tren Cloud 2.3, cho CA HAI API (legacy databases/collections/
    documents + tablesdb/tables/rows): 409 khi trung ID; transaction co hang trung -> commit 409
    `transaction_conflict` va khong ap dung gi."""

    def __init__(self, api: str):
        self.api = api
        self.khoa_id, self.khoa_ds = ("documentId", "documents") if api == "legacy" else ("rowId", "rows")
        self.rows: Dict[str, Dict[str, dict]] = {}
        self.goi: List[tuple] = []
        self.tx: Dict[str, list] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        p = request.url.path
        body = json.loads(request.content) if request.content else None
        self.goi.append((request.method, p, body, request.headers.get("x-appwrite-key")))
        if p.startswith("/v1/tablesdb/transactions"):
            parts = p.replace("/v1/tablesdb/", "").strip("/").split("/")
        elif self.api == "legacy":
            assert p.startswith("/v1/databases/"), f"kho legacy goi sai API: {p}"
            parts = p.replace("/v1/databases/", "").strip("/").split("/")  # db, collections, c, documents, id
        else:
            assert p.startswith("/v1/tablesdb/"), f"kho tablesdb goi sai API: {p}"
            parts = p.replace("/v1/tablesdb/", "").strip("/").split("/")   # db, tables, t, rows, id
        if parts[0] == "transactions":
            if request.method == "POST" and len(parts) == 1:
                tid = f"tx{len(self.tx)}"
                self.tx[tid] = []
                return httpx.Response(201, json={"$id": tid})
            tid = parts[1]
            if len(parts) == 3:
                self.tx[tid] += body["operations"]
                return httpx.Response(201, json={})
            if body.get("rollback"):
                return httpx.Response(200, json={"status": "rolledBack"})
            ops = self.tx[tid]
            if any(o["action"] == "create" and o["rowId"] in self.rows.get(o["tableId"], {}) for o in ops):
                return httpx.Response(409, json={"type": "transaction_conflict"})
            for o in ops:
                t = self.rows.setdefault(o["tableId"], {})
                if o["action"] == "create":
                    t[o["rowId"]] = {"$id": o["rowId"], **o["data"]}
                elif o["action"] == "increment":
                    t[o["rowId"]][o["data"]["column"]] = int(t[o["rowId"]].get(o["data"]["column"]) or 0) + o["data"]["value"]
            return httpx.Response(200, json={"status": "committed"})
        t = self.rows.setdefault(parts[2], {})
        if request.method == "POST":
            rid = body[self.khoa_id]
            if rid in t:
                return httpx.Response(409, json={"type": "document_already_exists"})
            t[rid] = {"$id": rid, **body["data"], "$permissions": body["permissions"]}
            return httpx.Response(201, json=t[rid])
        if request.method == "GET" and len(parts) == 5:
            r = t.get(parts[4])
            return httpx.Response(200, json=r) if r else httpx.Response(404, json={"type": "document_not_found"})
        if request.method == "PATCH":
            t[parts[4]].update(body["data"])
            return httpx.Response(200, json=t[parts[4]])
        if request.method == "DELETE":
            return httpx.Response(204) if t.pop(parts[4], None) else httpx.Response(404, json={})
        if request.method == "GET":
            return httpx.Response(200, json={"total": len(t), self.khoa_ds: list(t.values())[:5]})
        return httpx.Response(204)


class _RepoAppwriteChung:
    """CUNG mot bo kiem cho HAI kho — hai kho khong duoc lech nhau."""

    LOP: Any = None
    API = ""
    BANG_TIN = ""

    def setUp(self):
        from types import SimpleNamespace

        self.aw = _AppwriteGia(self.API)
        cfg = SimpleNamespace(endpoint="https://aw.example/v1", project_id="p1", api_key="khoa-may-chu",
                              database_id="db1", api_base="https://aw.example")
        self.repo = self.LOP(cfg, client=httpx.Client(transport=httpx.MockTransport(self.aw)))

    def test_quyen_theo_hang_chi_hai_thanh_vien_va_khoa_chi_o_header(self):
        m = Message(id="m_" + cid(1), conversation_id="dm_1", sender_id="A", recipient_id="B", client_id=cid(1),
                    text="t", created_at="2026-09-28T00:00:00.000+00:00")
        self.repo.create_message(m)
        _, duong, body, khoa = self.aw.goi[-1]
        self.assertEqual(duong, self.BANG_TIN)
        self.assertEqual(body["permissions"], ['read("user:A")', 'read("user:B")'])
        self.assertEqual(khoa, "khoa-may-chu")
        self.assertNotIn("khoa-may-chu", json.dumps(body))
        with self.assertRaises(RepoConflict):
            self.repo.create_message(m)
        self.assertEqual(self.repo.get_message(m.id).text, "t")
        self.assertEqual([x.id for x in self.repo.list_messages("dm_1")], [m.id])

    def test_phat_tan_dung_mot_lan_bang_hang_danh_dau(self):
        self.aw.rows["chat_members"] = {"cm_b": {"$id": "cm_b", "unread_count": 0}}
        self.repo.fanout("m_" + cid(2), "cm_b")
        ops = self.aw.tx["tx0"]
        self.assertEqual([o["action"] for o in ops], ["create", "increment"])
        self.assertEqual(ops[0]["tableId"], "chat_fanouts")
        self.assertEqual(ops[0]["permissions"], [], "hàng đánh dấu không ai đọc được")
        with self.assertRaises(RepoConflict):
            self.repo.fanout("m_" + cid(2), "cm_b")
        self.assertEqual(self.aw.rows["chat_members"]["cm_b"]["unread_count"], 1)

    def test_chuan_bi_roi_huy_khong_ap_dung_gi(self):
        self.aw.rows["chat_members"] = {"cm_b": {"$id": "cm_b", "unread_count": 0}}
        gd = self.repo.stage_fanout("m_" + cid(3), "cm_b")
        self.repo.discard_fanout(gd)
        self.assertTrue(any(b and b.get("rollback") for _, p, b, _ in self.aw.goi if "transactions" in p))
        self.assertEqual(self.aw.rows["chat_members"]["cm_b"]["unread_count"], 0)

    def test_hoi_thoai_va_chan_dung_dinh_dang_229(self):
        from server.messaging.domain import Block, Conversation
        from server.messaging.ids import block_row_id

        self.repo.create_conversation(Conversation(id="dm_x", member_a="A", member_b="B", created_at="2026-09-28T00:00:00.000+00:00"))
        self.assertEqual(self.aw.rows["chat_conversations"]["dm_x"]["$permissions"], ['read("user:A")', 'read("user:B")'])
        self.assertEqual(self.repo.get_conversation("dm_x").members, ["A", "B"])
        bid = block_row_id("A", "B")
        self.repo.create_block(Block(id=bid, blocker_id="A", blocked_id="B", created_at="2026-09-28T00:00:00.000+00:00"))
        hang = self.aw.rows["user_blocks"][bid]
        self.assertEqual((hang["block_id"], hang["kind"], hang["$permissions"]), (bid, "block", ['read("user:A")']))
        self.assertEqual([b.blocker_id for b in self.repo.blocks_between("B", "A")], ["A"])
        self.repo.delete_block(bid)
        self.repo.delete_block(bid)  # idempotent: 404 khong phai loi


class LegacyAppwriteRepoTest(_RepoAppwriteChung, unittest.TestCase):
    """Appwrite 1.9.6 (production): databases / collections / documents."""

    from server.messaging.appwrite import LegacyAppwriteChatRepository as LOP
    API = "legacy"
    BANG_TIN = "/v1/databases/db1/collections/chat_messages/documents"


class TablesDBRepoTest(_RepoAppwriteChung, unittest.TestCase):
    """Appwrite Cloud 2.x (staging): tablesdb / tables / rows."""

    LOP = TablesDBChatRepository
    API = "tablesdb"
    BANG_TIN = "/v1/tablesdb/db1/tables/chat_messages/rows"


class KhoaChanGiong229Test(unittest.TestCase):
    def test_vector_block_key_cua_229(self):
        """`server.social.block_key` cua #229: 'blk_' + sha256(blocker\\x1fblocked\\x1fkind)[:24]."""
        import hashlib

        from server.messaging.ids import block_row_id

        mong = "blk_" + hashlib.sha256("u1\x1fu2\x1fblock".encode()).hexdigest()[:24]
        self.assertEqual(block_row_id("u1", "u2"), mong)
        self.assertNotEqual(block_row_id("u1", "u2"), block_row_id("u2", "u1"), "có hướng: A chặn B ≠ B chặn A")


class RealtimeAppwriteTest(unittest.TestCase):
    PAYLOAD = {"channels": ["databases.db1.collections.chat_messages.documents", "documents", "rows",
                            "tablesdb.db1.tables.chat_messages.rows"],
               "events": ["tablesdb.db1.tables.chat_messages.rows.m_1.create",
                          "databases.db1.collections.chat_messages.documents.m_1.create"],
               "payload": {"$id": "m_1", "conversation_id": "dm_1", "sender_id": "A", "recipient_id": "B",
                           "client_id": cid(1), "text": "chào", "created_at": "2026-09-28T01:02:03.456+00:00"}}

    def test_phan_tich_dung_hinh_dang_do_that_tren_staging(self):
        ev = event_from_realtime(self.PAYLOAD)
        self.assertEqual((ev.kind, ev.message.id, ev.message.text), ("create", "m_1", "chào"))
        tv = event_from_realtime({"channels": ["databases.db1.collections.chat_members.documents"],
                                  "events": ["databases.db1.collections.chat_members.documents.cm_1.update"],
                                  "payload": {"$id": "cm_1", "user_id": "B", "unread_count": 2}})
        self.assertEqual((tv.kind, tv.member.unread_count), ("update", 2))
        self.assertIsNone(event_from_realtime({"channels": ["databases.db1.collections.posts.documents"],
                                               "events": ["x.create"], "payload": {"$id": "p"}}))

    def _chay(self, ws_cm, viewer="B"):
        from types import SimpleNamespace

        cfg = SimpleNamespace(project_id="p1", database_id="db1", api_base="https://aw.example")
        src = AppwriteRealtimeSource(cfg, connect=lambda url: ws_cm)

        async def lay():
            ra = []
            async for ev in src.subscribe(viewer, "phien-cua-B", heartbeat_s=0.2):
                ra.append(ev)
                if len(ra) >= 2:
                    break
            return ra
        return asyncio.run(lay()), src

    def test_xac_thuc_bang_session_nguoi_xem_va_phat_su_kien(self):
        ws = _WsGia([{"type": "connected"}, {"type": "response", "data": {"to": "authentication", "success": True,
                                                                           "user": {"$id": "B"}}},
                     {"type": "event", "data": self.PAYLOAD}])
        ra, src = self._chay(ws)
        self.assertIsNone(ra[0])
        self.assertEqual(ra[1].message.id, "m_1")
        self.assertEqual(json.loads(ws.gui[0]), {"type": "authentication", "data": {"session": "phien-cua-B"}})
        self.assertIn("channels[]=databases.db1.collections.chat_messages.documents", src._url.replace("%2E", "."))

    def test_session_cua_nguoi_khac_khong_phat_gi(self):
        ws = _WsGia([{"type": "connected"}, {"type": "response", "data": {"to": "authentication", "success": True,
                                                                           "user": {"$id": "C"}}},
                     {"type": "event", "data": self.PAYLOAD}])
        with self.assertRaises(RealtimeAuthError):
            self._chay(ws)


class _WsGia:
    def __init__(self, tin):
        self.tin = [json.dumps(t) for t in tin]
        self.gui: List[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def recv(self):
        if self.tin:
            return self.tin.pop(0)
        await asyncio.sleep(10)

    async def send(self, s):
        self.gui.append(s)


class RuntimeTest(unittest.TestCase):
    def test_appwrite_mac_dinh_tat_chon_kho_tuong_minh_mock_bat(self):
        from types import SimpleNamespace

        from server.messaging.appwrite import LegacyAppwriteChatRepository

        cau_hinh = SimpleNamespace(endpoint="https://aw.example/v1", project_id="p1", api_key="k", database_id="db1",
                                   api_base="https://aw.example")
        aw = SimpleNamespace(data_backend="appwrite", appwrite=cau_hinh)
        self.assertFalse(build_runtime(aw, user_exists=lambda u: True, env={}).enabled, "production: TẮT mặc định")
        r = build_runtime(aw, user_exists=lambda u: True, env={"FAS_CHAT_V1": "1"})
        self.assertEqual(r.backend, "appwrite-legacy", "mặc định = API Databases của 1.9.6 (production)")
        self.assertIsInstance(r.service.repo, LegacyAppwriteChatRepository)
        r = build_runtime(aw, user_exists=lambda u: True, env={"FAS_CHAT_V1": "1", "FAS_CHAT_APPWRITE_API": "tablesdb"})
        self.assertEqual(r.backend, "appwrite-tablesdb")
        r = build_runtime(aw, user_exists=lambda u: True, env={"FAS_CHAT_V1": "1", "FAS_CHAT_APPWRITE_API": "mongo"})
        self.assertFalse(r.enabled)
        self.assertIn("mongo", r.reason)
        self.assertTrue(build_runtime(SimpleNamespace(data_backend="mock"), user_exists=lambda u: True, env={}).enabled)
        self.assertFalse(build_runtime(SimpleNamespace(data_backend="mock"), user_exists=lambda u: True,
                                       env={"FAS_CHAT_V1": "0"}).enabled)


if __name__ == "__main__":
    unittest.main()
