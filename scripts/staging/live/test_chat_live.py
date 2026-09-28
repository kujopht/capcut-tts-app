"""
Test TICH HOP THAT cho nhan tin tren Appwrite — CUNG mot bo test cho HAI kho:

    python -m scripts.staging.run_live --mo-dun test_chat_live                      # legacy (mac dinh)
    python -m scripts.staging.run_live --mo-dun test_chat_live --chat-api tablesdb  # TablesDB

`FAS_CHAT_APPWRITE_API` (legacy | tablesdb) chon `LegacyAppwriteChatRepository` (databases/collections/
documents — dung API production 1.9.6 dang co) hay `TablesDBChatRepository` (tables/rows, Cloud 2.3).
Moi truy cap THANG vao Appwrite o duoi cung di theo API do, nen chay tren 1.9.6 that (khong co TablesDB)
cung dung — do la bai kiem tuong duong production.

KHONG chay trong CI. `setUpModule` bo qua ca module tru khi `FAS_STAGING_LIVE=1` (CHI `run_live` dat,
sau guard + xac minh chi doc, trong tien trinh con da khoa vao staging). Kiem guard lan NUA o day.

Backend THAT (`server.main`, DATA_BACKEND=appwrite, `FAS_CHAT_V1=1`) chay tren UVICORN THAT trong tien
trinh nay — luong SSE di qua middleware that, va moi luong mo mot WebSocket THAT toi Appwrite Realtime
bang session cua CHINH nguoi xem. Tai khoan: `qa-<run>-*@example.test` (don bang `scripts.staging.reset`).

Nhom kiem: quyen DM (ca truy cap THANG vao Appwrite bang session nguoi thu ba), giao Realtime, chua doc/
da doc, noi lai, phan trang, gui idempotent (ke ca dong thoi), chan/tat tieng, nhieu tab.
"""
from __future__ import annotations

import json
import os
import statistics
import threading
import time
import unittest
import uuid
from typing import Any, Dict, List

#: Hai dich, moi dich mot rao RIENG: staging Cloud 2.3 (`scripts.staging.run_live`) hoac may kiem 1.9.6
#: dung mot lan tren loopback (`scripts.chat_parity.run_parity`).
PARITY = os.environ.get("FAS_CHAT_PARITY") == "1"
LIVE = os.environ.get("FAS_STAGING_LIVE") == "1" or PARITY
RUN = os.environ.get("FAS_STAGING_RUN_ID") or uuid.uuid4().hex[:8]
MAT_KHAU = "Qa-" + uuid.uuid4().hex
API = (os.environ.get("FAS_CHAT_APPWRITE_API") or "legacy").strip().lower()


def duong(bang: str, hang: str = "") -> str:
    """Duong REST THANG vao Appwrite theo API dang kiem (1.9.6 KHONG co /tablesdb)."""
    db = os.environ["APPWRITE_DATABASE_ID"]
    goc = (f"/tablesdb/{db}/tables/{bang}/rows" if API == "tablesdb"
           else f"/databases/{db}/collections/{bang}/documents")
    return goc + (f"/{hang}" if hang else "")


KHOA_ID = "rowId" if API == "tablesdb" else "documentId"
KHOA_DS = "rows" if API == "tablesdb" else "documents"

main: Any = None
GOC = ""
DO: Dict[str, List[float]] = {"gui_ms": [], "realtime_ms": []}


def setUpModule() -> None:
    global main, GOC
    if not LIVE:
        raise unittest.SkipTest("Chỉ chạy qua `scripts.staging.run_live` hoặc `scripts.chat_parity.run_parity`.")
    if PARITY:
        from scripts.chat_parity import guard as rao_parity

        rao_parity.kiem_dich(rao_parity.CauHinhParity.tu_env())
    else:
        from scripts.staging import guard
        from scripts.staging.bi_mat import CauHinhStaging

        guard.kiem_dich(CauHinhStaging(endpoint=os.environ["APPWRITE_ENDPOINT"],
                                       project_id=os.environ["APPWRITE_PROJECT_ID"],
                                       database_id=os.environ["APPWRITE_DATABASE_ID"],
                                       api_key=os.environ["APPWRITE_API_KEY"]))
    if os.environ.get("DATA_BACKEND") != "appwrite":
        raise RuntimeError("Tiến trình test staging phải có DATA_BACKEND=appwrite.")
    import socket

    import uvicorn

    from server import main as m

    if m.messaging_runtime.backend != f"appwrite-{API}":
        raise RuntimeError(f"Nhắn tin không chạy trên kho appwrite-{API}: {m.messaging_runtime.describe()}")
    main = m
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    cong = s.getsockname()[1]
    s.close()
    may = uvicorn.Server(uvicorn.Config(m.app, host="127.0.0.1", port=cong, log_level="warning"))
    threading.Thread(target=may.run, daemon=True).start()
    het = time.time() + 20
    while not may.started and time.time() < het:
        time.sleep(0.05)
    GOC = f"http://127.0.0.1:{cong}"


def tearDownModule() -> None:
    if DO["gui_ms"]:
        noi = "loopback, Appwrite 1.9.6" if PARITY else "tới SGP"
        print(f"\n[DO] gửi tin (HTTP, {noi}, kho {API}): trung vị {statistics.median(DO['gui_ms']):.0f} ms, "
              f"max {max(DO['gui_ms']):.0f} ms, n={len(DO['gui_ms'])}", flush=True)
    if DO["realtime_ms"]:
        print(f"[DO] gửi -> nhận qua Realtime: trung vị {statistics.median(DO['realtime_ms']):.0f} ms, "
              f"max {max(DO['realtime_ms']):.0f} ms, n={len(DO['realtime_ms'])}", flush=True)


_dem = [0]
_khoa = threading.Lock()


def http():
    import httpx

    return httpx.Client(base_url=GOC, timeout=httpx.Timeout(60.0))


def nguoi(ten: str):
    from server.messaging.ids import chat_user_id
    from server.rate_limit import limiter

    with _khoa:
        _dem[0] += 1
        n = _dem[0]
    limiter.reset()  # bo dem Tier theo IP cua CHINH tien trinh test
    email = f"qa-{RUN}-{ten}-{n}@example.test"
    with http() as c:
        r = c.post("/api/auth/register", json={"email": email, "password": MAT_KHAU, "display_name": f"QA {ten} {n}"})
    if r.status_code != 201:
        raise AssertionError(f"đăng ký {ten}: {r.status_code} {r.text[:200]}")
    b = r.json()
    uid = b["profile"]["user_id"]
    return {"uid": uid, "cid": chat_user_id(uid), "hd": {"Authorization": f"Bearer {b['token']}"}, "token": b["token"]}


_cli_dem = [0]


def cli_moi() -> str:
    """client_id hop le ([A-Za-z0-9]{16,32}), duy nhat theo lan chay."""
    with _khoa:
        _cli_dem[0] += 1
        return f"L{RUN}{_cli_dem[0]:010d}"[:32]


def gui(a, b, text="xin chào", client_id=None):
    t0 = time.time()
    with http() as c:
        r = c.post(f"/api/chat/dm/{b['cid']}/messages", headers=a["hd"],
                   json={"client_id": client_id or cli_moi(), "text": text})
    if r.status_code == 200:
        DO["gui_ms"].append((time.time() - t0) * 1000)
    return r


def hop_thu(u) -> Dict[str, Any]:
    with http() as c:
        r = c.get("/api/chat/conversations", headers=u["hd"])
    assert r.status_code == 200, r.text
    return r.json()


def nghe(u) -> Dict[str, Any]:
    import httpx

    st: Dict[str, Any] = {"events": [], "ready": threading.Event(), "dung": threading.Event(), "status": None}

    def chay():
        try:
            with httpx.Client(base_url=GOC, timeout=httpx.Timeout(90.0)) as c, \
                    c.stream("GET", "/api/chat/stream", headers=u["hd"]) as r:
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
                            st["events"].append((ten or "data", d, time.time()))
                        ten = None
                    if st["dung"].is_set():
                        return
        except Exception as exc:  # noqa: BLE001
            st["loi"] = repr(exc)
    st["thread"] = threading.Thread(target=chay, daemon=True)
    st["thread"].start()
    if not st["ready"].wait(30):
        raise AssertionError(f"luồng không sẵn sàng: status={st['status']} {st.get('loi', '')}")
    return st


def cho(st, dk, giay=15.0):
    het = time.time() + giay
    while time.time() < het:
        m = next((e for e in st["events"] if dk(e[1])), None)
        if m:
            return m
        time.sleep(0.05)
    return None


def dong(*sts):
    for st in sts:
        st["dung"].set()
    for st in sts:
        st["thread"].join(20)


def appwrite_nhu(u, method, path, body=None):
    """Goi THANG Appwrite bang SESSION cua nguoi dung (khong khoa API) — nhu mot ke tan cong nam token."""
    import httpx

    return httpx.request(method, os.environ["APPWRITE_ENDPOINT"] + path, json=body, timeout=30,
                         headers={"X-Appwrite-Project": os.environ["APPWRITE_PROJECT_ID"],
                                  "X-Appwrite-Session": u["token"], "Content-Type": "application/json"})


class A_KetNoiTest(unittest.TestCase):
    def test_phien_nhan_tin_tren_appwrite_khong_tencent(self):
        a = nguoi("ss")
        with http() as c:
            r = c.post("/api/chat/session", headers=a["hd"])
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["provider"], d["environment"], d["userId"]), ("fanfic", f"appwrite-{API}", a["cid"]))
        self.assertNotIn("userSig", d)


class B_QuyenDmTest(unittest.TestCase):
    def test_khach_chinh_minh_nguoi_khong_ton_tai(self):
        a = nguoi("qa")
        with http() as c:
            self.assertEqual(c.get("/api/chat/conversations").status_code, 401)
            self.assertEqual(c.get("/api/chat/stream").status_code, 401)
        self.assertEqual(gui(a, a).json()["detail"]["code"], "chat_self")
        r = gui(a, {"cid": "fw_khongtontai0000000"})
        self.assertEqual((r.status_code, r.json()["detail"]["code"]), (404, "chat_peer_not_found"))

    def test_nguoi_thu_ba_khong_doc_duoc_du_bang_api_hay_thang_vao_appwrite(self):
        a, b, c = nguoi("pa"), nguoi("pb"), nguoi("pc")
        r = gui(a, b, "bí mật A-B")
        self.assertEqual(r.status_code, 200, r.text)
        mid = r.json()["message"]["id"]
        with http() as cl:
            # C chi dien ta duoc hoi thoai CUA C: lich su C-A rong, con tro cua A-B bi tu choi
            self.assertEqual(cl.get(f"/api/chat/dm/{a['cid']}/messages", headers=c["hd"]).json()["messages"], [])
            x = cl.get(f"/api/chat/dm/{a['cid']}/messages?before={mid}", headers=c["hd"])
            self.assertEqual((x.status_code, x.json()["detail"]["code"]), (400, "chat_bad_cursor"))
        # THANG vao Appwrite bang session: B doc duoc (quyen theo hang dung), C thi KHONG
        self.assertEqual(appwrite_nhu(b, "GET", duong("chat_messages", mid)).status_code, 200)
        self.assertEqual(appwrite_nhu(c, "GET", duong("chat_messages", mid)).status_code, 404)
        ds = appwrite_nhu(c, "GET", duong("chat_messages")).json()
        self.assertFalse(any(r.get("$id") == mid for r in ds.get(KHOA_DS, [])), "C liệt kê thấy tin A-B")
        # Hang hoi thoai: hai thanh vien doc duoc, nguoi thu ba khong
        from server.messaging.ids import dm_id

        hid = dm_id(a["uid"], b["uid"])
        self.assertEqual(appwrite_nhu(a, "GET", duong("chat_conversations", hid)).status_code, 200)
        self.assertEqual(appwrite_nhu(c, "GET", duong("chat_conversations", hid)).status_code, 404)
        # Khong ai TU GHI duoc: quyen cap bang rong
        w = appwrite_nhu(c, "POST", duong("chat_messages"),
                         {KHOA_ID: "unique()", "data": {"conversation_id": "x", "sender_id": c["uid"], "recipient_id": a["uid"],
                                                        "client_id": "x" * 20, "text": "giả", "created_at": "2026-09-28T00:00:00Z"}})
        self.assertIn(w.status_code, (401, 403), w.text[:200])
        u = appwrite_nhu(b, "PATCH", duong("chat_messages", mid), {"data": {"text": "sửa lén"}})
        self.assertIn(u.status_code, (401, 403), "thành viên cũng không được sửa thẳng")


class C_GuiIdempotentTest(unittest.TestCase):
    def test_gui_lai_tuan_tu_va_dong_thoi_mot_tin_mot_lan_chua_doc(self):
        a, b = nguoi("ia"), nguoi("ib")
        k = cli_moi()
        r1, r2 = gui(a, b, "lần đầu", k), gui(a, b, "lần hai", k)
        self.assertEqual((r1.json()["created"], r2.json()["created"], r2.json()["message"]["text"]), (True, False, "lần đầu"))
        k2 = cli_moi()
        rao = threading.Barrier(6)
        ma: List[int] = []

        def mot():
            rao.wait()
            ma.append(gui(a, b, "cùng lúc", k2).status_code)
        ts = [threading.Thread(target=mot) for _ in range(6)]
        [t.start() for t in ts]
        [t.join(120) for t in ts]
        self.assertTrue(all(x == 200 for x in ma), ma)
        with http() as c:
            ds = c.get(f"/api/chat/dm/{a['cid']}/messages", headers=b["hd"]).json()["messages"]
        self.assertEqual(len(ds), 2, "đúng HAI tin (một mỗi client_id)")
        self.assertEqual(hop_thu(b)["items"][0]["unread"], 2, "chưa đọc tăng ĐÚNG MỘT LẦN mỗi tin")


class D_ChuaDocTest(unittest.TestCase):
    def test_chua_doc_da_doc_toi_moc_va_tat_tieng(self):
        a, b, c = nguoi("ua"), nguoi("ub"), nguoi("uc")
        ids = [gui(a, b, f"tin {i}").json()["message"]["id"] for i in range(3)]
        self.assertEqual(hop_thu(b)["items"][0]["unread"], 3)
        self.assertEqual(hop_thu(a)["items"][0]["unread"], 0)
        with http() as cl:
            self.assertEqual(cl.post(f"/api/chat/dm/{a['cid']}/read", headers=b["hd"], json={"up_to": ids[1]}).json()
                             ["conversation"]["unread"], 1)
            cl.post(f"/api/chat/dm/{a['cid']}/read", headers=b["hd"], json={})
            self.assertEqual(hop_thu(b)["unread_total"], 0)
            gui(c, b, "từ C")
            cl.post(f"/api/chat/dm/{c['cid']}/mute", headers=b["hd"], json={"muted": True})
            h = hop_thu(b)
            theo = {it["peer_id"]: it for it in h["items"]}
            self.assertEqual((theo[c["cid"]]["unread"], theo[c["cid"]]["muted"], h["unread_total"]), (1, True, 0))


class E_PhanTrangTest(unittest.TestCase):
    def test_lui_khong_trung_khong_sot_va_tien_sau_con_tro(self):
        a, b = nguoi("ga"), nguoi("gb")
        sv = main.messaging_runtime.service
        for i in range(23):
            sv.send(a["uid"], b["cid"], cli_moi(), f"tin {i:02d}")
        thay, tro, trang = [], None, 0
        with http() as c:
            while True:
                d = c.get(f"/api/chat/dm/{a['cid']}/messages?limit=10" + (f"&before={tro}" if tro else ""), headers=b["hd"]).json()
                thay = [m["text"] for m in d["messages"]] + thay
                trang += 1
                tro = d["cursor"]
                if not tro:
                    break
            self.assertEqual((trang, thay), (3, [f"tin {i:02d}" for i in range(23)]))
            moc = c.get(f"/api/chat/dm/{a['cid']}/messages?limit=1", headers=b["hd"]).json()["messages"][0]["id"]
            for i in range(2):
                gui(a, b, f"mới {i}")
            d = c.get(f"/api/chat/dm/{a['cid']}/messages?after={moc}", headers=b["hd"]).json()
            self.assertEqual([m["text"] for m in d["messages"]], ["mới 0", "mới 1"])


class F_ChanTest(unittest.TestCase):
    def test_chan_hai_chieu_va_bo_chan(self):
        from server.messaging.ids import block_row_id

        a, b = nguoi("ba"), nguoi("bb")
        self.assertEqual(gui(a, b).status_code, 200)
        with http() as c:
            c.post(f"/api/chat/dm/{b['cid']}/block", headers=a["hd"], json={"blocked": True})
            for x, y in ((b, a), (a, b)):
                r = gui(x, y)
                self.assertEqual((r.status_code, r.json()["detail"]["code"]), (403, "chat_blocked"))
            self.assertEqual(c.get("/api/chat/blocks", headers=a["hd"]).json()["items"], [b["cid"]])
            self.assertEqual(c.get("/api/chat/blocks", headers=b["hd"]).json()["items"], [], "B không biết mình bị chặn")
            # Lich su cu VAN CON cho ca hai; tin bi tu choi khong cong chua doc
            self.assertEqual(len(c.get(f"/api/chat/dm/{b['cid']}/messages", headers=a["hd"]).json()["messages"]), 1)
            self.assertEqual(hop_thu(b)["items"][0]["unread"], 1)
        # CHAN MUC TAI KHOAN = mot hang `user_blocks` DINH DANG #229 (cung khoa voi chan o trang ca nhan);
        # chi NGUOI CHAN doc duoc hang do.
        bid = block_row_id(a["uid"], b["uid"])
        h = appwrite_nhu(a, "GET", duong("user_blocks", bid))
        self.assertEqual(h.status_code, 200, h.text[:200])
        self.assertEqual({k: h.json()[k] for k in ("block_id", "blocker_id", "blocked_id", "kind")},
                         {"block_id": bid, "blocker_id": a["uid"], "blocked_id": b["uid"], "kind": "block"})
        self.assertEqual(appwrite_nhu(b, "GET", duong("user_blocks", bid)).status_code, 404)
        with http() as c:
            c.post(f"/api/chat/dm/{b['cid']}/block", headers=a["hd"], json={"blocked": False})
        self.assertEqual(appwrite_nhu(a, "GET", duong("user_blocks", bid)).status_code, 404)
        self.assertEqual(gui(b, a).status_code, 200)

    def test_chan_tu_phia_bi_chan_cung_chan_nguoi_chan(self):
        """B chan A: A khong gui duoc cho B, va B cung khong gui duoc cho A (chan hai chieu)."""
        a, b = nguoi("bc"), nguoi("bd")
        self.assertEqual(gui(a, b).status_code, 200)
        with http() as c:
            c.post(f"/api/chat/dm/{a['cid']}/block", headers=b["hd"], json={"blocked": True})
        for x, y in ((a, b), (b, a)):
            r = gui(x, y)
            self.assertEqual((r.status_code, r.json()["detail"]["code"]), (403, "chat_blocked"))
        with http() as c:
            c.post(f"/api/chat/dm/{a['cid']}/block", headers=b["hd"], json={"blocked": False})
        self.assertEqual(gui(a, b).status_code, 200)


class G_RealtimeTest(unittest.TestCase):
    def test_giao_qua_appwrite_realtime_nhieu_tab_nguoi_thu_ba_khong_nhan(self):
        a, b, c = nguoi("ra"), nguoi("rb"), nguoi("rc")
        sa, sb1, sb2, sc = nghe(a), nghe(b), nghe(b), nghe(c)
        try:
            for i in range(3):
                t0 = time.time()
                mid = gui(a, b, f"realtime {i}").json()["message"]["id"]
                for st in (sa, sb1, sb2):
                    e = cho(st, lambda d, mid=mid: d.get("type") == "message" and d["message"]["id"] == mid)
                    self.assertIsNotNone(e, f"tin {i} không tới một luồng (Realtime Appwrite)")
                    if st is sb1:
                        DO["realtime_ms"].append((e[2] - t0) * 1000)
            tin = next(d["message"] for _, d, _ in sb1["events"] if d.get("type") == "message")
            self.assertEqual((tin["from_me"], tin["peer_id"]), (False, a["cid"]))
            self.assertIsNotNone(cho(sb1, lambda d: d.get("type") == "conversation" and d["conversation"]["unread"] >= 1))
            with http() as cl:  # DA TAB: doc o tab 1 -> tab 2 thay unread = 0
                cl.post(f"/api/chat/dm/{a['cid']}/read", headers=b["hd"], json={})
            self.assertIsNotNone(cho(sb2, lambda d: d.get("type") == "conversation" and d["conversation"]["unread"] == 0))
            time.sleep(2)
            self.assertEqual(sc["events"], [], "người thứ ba KHÔNG được nhận gì — Appwrite lọc theo quyền hàng")
            than = json.dumps([e[1] for e in sa["events"] + sb1["events"]], ensure_ascii=False)
            self.assertNotIn("@example.test", than)
            self.assertNotIn(b["token"], than)
        finally:
            dong(sa, sb1, sb2, sc)


class H_NoiLaiTest(unittest.TestCase):
    def test_mat_ket_noi_bu_khoang_trong_roi_nhan_tiep(self):
        a, b = nguoi("na"), nguoi("nb")
        sb = nghe(b)
        m1 = gui(a, b, "trước khi rớt").json()["message"]["id"]
        self.assertIsNotNone(cho(sb, lambda d: d.get("type") == "message"))
        dong(sb)
        for i in range(3):
            gui(a, b, f"lúc rớt {i}")
        sb2 = nghe(b)
        try:
            with http() as c:
                d = c.get(f"/api/chat/dm/{a['cid']}/messages?after={m1}", headers=b["hd"]).json()
            self.assertEqual([m["text"] for m in d["messages"]], ["lúc rớt 0", "lúc rớt 1", "lúc rớt 2"])
            mid = gui(a, b, "sau khi nối lại").json()["message"]["id"]
            self.assertIsNotNone(cho(sb2, lambda d: d.get("type") == "message" and d["message"]["id"] == mid))
        finally:
            dong(sb2)
