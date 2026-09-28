"""
Test TICH HOP THAT tren Appwrite STAGING (Appwrite Cloud, project `fanfic-staging`).

KHONG chay trong CI va khong chay trong `unittest discover` thuong: `setUpModule` bo qua ca
module tru khi `FAS_STAGING_LIVE=1` — co nay CHI do `scripts.staging.run_live` dat, sau guard
+ xac minh chi doc, trong mot tien trinh con da duoc khoa vao dich staging. Module con kiem
guard lan NUA trong chinh tien trinh test (lop cuoi).

Bam dung thu tu kiem cua `docs/migrations/SOCIAL_PLAY_V1_TEST_APPWRITE.md` §5: community (dang
bai/binh luan/sua/xoa/like/feed/cursor/fandom/chan/bao cao), ho so (bio/fandom/accent/avatar/
khung), quyen, trung lap/idempotency, XP nguyen tu duoi dong thoi THAT (luong + Appwrite that),
quyet toan game DUNG MOT LAN ke ca khi nhieu worker cung thay "pending", bang xep hang, han muc
dem tren chinh du lieu Appwrite.

Moi lan chay dung tai khoan MOI `qa-<run>-*@example.test` — ket luan khong phu thuoc du lieu
cua lan truoc. Don bang `python -m scripts.staging.reset --du-lieu --apply`.
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import unittest
import uuid
from typing import Any, Callable, Dict, List, Tuple

LIVE = os.environ.get("FAS_STAGING_LIVE") == "1"
RUN = os.environ.get("FAS_STAGING_RUN_ID") or uuid.uuid4().hex[:8]
#: Mat khau NGAU NHIEN theo tien trinh, cho tai khoan tong hop — khong in, khong luu.
MAT_KHAU = "Qa-" + uuid.uuid4().hex

main: Any = None
client: Any = None

# X thang: hang 7 cot 3..7; O danh hang 0 — giong `test_games_routes`.
NUOC_X = [7 * 15 + c for c in range(3, 8)]
NUOC_O = [0 * 15 + c for c in range(0, 4)]


def setUpModule() -> None:
    global main, client
    if not LIVE:
        raise unittest.SkipTest("Chỉ chạy qua `python -m scripts.staging.run_live` (FAS_STAGING_LIVE=1).")
    from scripts.staging import guard
    from scripts.staging.bi_mat import CauHinhStaging

    guard.kiem_dich(CauHinhStaging(endpoint=os.environ["APPWRITE_ENDPOINT"],
                                   project_id=os.environ["APPWRITE_PROJECT_ID"],
                                   database_id=os.environ["APPWRITE_DATABASE_ID"],
                                   api_key=os.environ["APPWRITE_API_KEY"]))
    if os.environ.get("DATA_BACKEND") != "appwrite" or os.environ.get("STORAGE_BACKEND") != "local":
        raise RuntimeError("Tiến trình test staging phải có DATA_BACKEND=appwrite, STORAGE_BACKEND=local.")
    from fastapi.testclient import TestClient

    from server import main as m

    main = m
    client = TestClient(m.app)


_dem = [0]
_khoa_dem = threading.Lock()


def nguoi(ten: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Tai khoan tong hop MOI qua CHINH route dang ky (Appwrite Users + profiles that)."""
    from server.rate_limit import limiter

    with _khoa_dem:
        _dem[0] += 1
        n = _dem[0]
    # Bo dem Tier (chong spam dang ky theo IP) cua CHINH tien trinh test — khong lien quan Appwrite.
    limiter.reset()
    email = f"qa-{RUN}-{ten}-{n}@example.test"
    r = client.post("/api/auth/register", json={"email": email, "password": MAT_KHAU, "display_name": f"QA {ten} {n}"})
    if r.status_code != 201:
        raise AssertionError(f"đăng ký {ten}: {r.status_code} {r.text[:300]}")
    body = r.json()
    return body["profile"], {"Authorization": f"Bearer {body['token']}"}


def ho_so(tk: Dict[str, str]):
    return main.identity.profile_from_token(tk["Authorization"].split(" ", 1)[1])


def _chay_dong_thoi(viec: List[Callable[[], Any]]) -> Tuple[List[Any], List[BaseException]]:
    rao = threading.Barrier(len(viec))
    kq: List[Any] = [None] * len(viec)
    loi: List[BaseException] = []

    def boc(i, f):
        def chay():
            rao.wait()
            try:
                kq[i] = f()
            except BaseException as exc:  # noqa: BLE001 — gom lai, kiem sau
                loi.append(exc)
        return chay

    ts = [threading.Thread(target=boc(i, f)) for i, f in enumerate(viec)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(120)
    return kq, loi


def _png_b64(size=(320, 320), color=(40, 90, 160)) -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _khoa(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class A_KetNoiVaCauHinhTest(unittest.TestCase):
    def test_backend_dung_appwrite_staging_va_cac_co_dang_bat(self):
        s = main.settings
        self.assertEqual(s.data_backend, "appwrite")
        self.assertEqual(s.environment, "staging")
        self.assertTrue(s.appwrite.configured)
        self.assertTrue(s.social_v1_schema)
        self.assertTrue(s.xp_atomic_enabled)
        self.assertTrue(s.games_v1_enabled)
        r = client.get("/api/games/config")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["enabled"])

    def test_health_khong_lo_bi_mat(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200, r.text)
        than = r.text
        self.assertNotIn(os.environ["APPWRITE_API_KEY"], than)


class B_CommunityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.an, cls.tk_an = nguoi("an")
        cls.binh, cls.tk_binh = nguoi("binh")
        cls.chi, cls.tk_chi = nguoi("chi")

    def _bai(self, tk, text, **kw) -> Dict[str, Any]:
        r = client.post("/api/posts", json={"text": text, **kw}, headers=tk)
        self.assertIn(r.status_code, (200, 201), r.text)
        return r.json()["post"]

    def test_dang_bai_idempotent_theo_client_key(self):
        k = _khoa("pk")
        r1 = client.post("/api/posts", json={"text": "Lần 1", "client_key": k}, headers=self.tk_an)
        self.assertEqual(r1.status_code, 201, r1.text)
        r2 = client.post("/api/posts", json={"text": "Lần 2 khác hẳn", "client_key": k}, headers=self.tk_an)
        self.assertEqual(r2.status_code, 200, r2.text)
        a, b = r1.json()["post"], r2.json()["post"]
        self.assertTrue(b["replayed"])
        self.assertEqual(a["post_id"], b["post_id"])
        self.assertEqual(b["text"], "Lần 1")
        # Nguoi khac CUNG client_key -> bai rieng, khong va cham.
        c = self._bai(self.tk_binh, "Của Bình", client_key=k)
        self.assertNotEqual(c["post_id"], a["post_id"])

    def test_sua_xoa_chi_chu_bai_va_khach_khong_dang_duoc(self):
        bai = self._bai(self.tk_an, "Bài để sửa")
        pid = bai["post_id"]
        self.assertEqual(client.patch(f"/api/posts/{pid}", json={"text": "Bình sửa trộm"},
                                      headers=self.tk_binh).status_code, 403)
        r = client.patch(f"/api/posts/{pid}", json={"text": "An sửa"}, headers=self.tk_an)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["post"]["text"], "An sửa")
        self.assertTrue(r.json()["post"].get("edited_at"))
        self.assertEqual(client.delete(f"/api/posts/{pid}", headers=self.tk_binh).status_code, 403)
        self.assertEqual(client.delete(f"/api/posts/{pid}", headers=self.tk_an).status_code, 200)
        self.assertEqual(client.get(f"/api/posts/{pid}").status_code, 404)
        self.assertEqual(client.post("/api/posts", json={"text": "Khách"}).status_code, 401)

    def test_binh_luan_idempotent_dem_mot_lan_va_quyen_sua(self):
        pid = self._bai(self.tk_an, "Bài gốc")["post_id"]
        k = _khoa("ck")
        r1 = client.post(f"/api/posts/{pid}/comments", json={"text": "Cmt 1", "client_key": k}, headers=self.tk_binh)
        r2 = client.post(f"/api/posts/{pid}/comments", json={"text": "Khác", "client_key": k}, headers=self.tk_binh)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200), r2.text)
        cid = r1.json()["comment"]["comment_id"]
        self.assertEqual(r2.json()["comment"]["comment_id"], cid)
        self.assertEqual(client.get(f"/api/posts/{pid}").json()["post"]["comment_count"], 1)
        ds = client.get(f"/api/posts/{pid}/comments").json()
        self.assertIn(cid, json.dumps(ds))
        self.assertEqual(client.patch(f"/api/comments/{cid}", json={"text": "An sửa của Bình"},
                                      headers=self.tk_an).status_code, 403)
        self.assertEqual(client.patch(f"/api/comments/{cid}", json={"text": "Bình tự sửa"},
                                      headers=self.tk_binh).status_code, 200)

    def test_like_hai_lan_chi_tinh_mot(self):
        pid = self._bai(self.tk_an, "Like tôi")["post_id"]
        for _ in range(2):
            self.assertEqual(client.post(f"/api/posts/{pid}/like", json={}, headers=self.tk_binh).status_code, 200)
        self.assertEqual(client.get(f"/api/posts/{pid}").json()["post"]["like_count"], 1)
        client.delete(f"/api/posts/{pid}/like", headers=self.tk_binh)
        self.assertEqual(client.get(f"/api/posts/{pid}").json()["post"]["like_count"], 0)

    def test_feed_cursor_va_loc_fandom(self):
        p_n = self._bai(self.tk_an, f"Naruto {RUN}", fandom_id="naruto")["post_id"]
        p_o = self._bai(self.tk_an, f"One Piece {RUN}", fandom_id="one-piece")["post_id"]
        r = client.get("/api/feed?scope=latest&fandom=naruto&limit=20")
        self.assertEqual(r.status_code, 200, r.text)
        ids = [it["post_id"] for it in r.json()["items"]]
        self.assertIn(p_n, ids)
        self.assertNotIn(p_o, ids)
        t1 = client.get("/api/feed?scope=latest&limit=1").json()
        self.assertEqual(len(t1["items"]), 1)
        self.assertTrue(t1["next_cursor"])
        t2 = client.get(f"/api/feed?scope=latest&limit=1&cursor={t1['next_cursor']}").json()
        self.assertEqual(len(t2["items"]), 1)
        self.assertNotEqual(t1["items"][0]["post_id"], t2["items"][0]["post_id"])
        self.assertEqual(client.get("/api/feed?scope=latest&cursor=%23%23hong").status_code, 400)

    def test_chan_an_bai_va_danh_sach_chan(self):
        pid = self._bai(self.tk_an, f"Bài của An {RUN}")["post_id"]
        self.assertEqual(client.post(f"/api/users/{self.an['user_id']}/block", json={},
                                     headers=self.tk_chi).status_code, 200)
        self.assertIn(self.an["user_id"], json.dumps(client.get("/api/me/blocks", headers=self.tk_chi).json()))
        ids = [it["post_id"] for it in client.get("/api/feed?scope=latest&limit=30", headers=self.tk_chi).json()["items"]]
        self.assertNotIn(pid, ids)
        self.assertEqual(client.delete(f"/api/users/{self.an['user_id']}/block", headers=self.tk_chi).status_code, 200)

    def test_bao_cao_va_khong_lo_email_token(self):
        pid = self._bai(self.tk_an, "Bài bị báo cáo")["post_id"]
        r = client.post("/api/reports", json={"target_kind": "post", "target_id": pid, "reason": "spam"},
                        headers=self.tk_binh)
        self.assertIn(r.status_code, (200, 201), r.text)
        r2 = client.post("/api/reports", json={"target_kind": "post", "target_id": pid, "reason": "spam"},
                         headers=self.tk_binh)
        self.assertLess(r2.status_code, 500, r2.text)
        than = client.get("/api/feed?scope=latest&limit=30").text
        self.assertNotIn("@example.test", than, "bảng tin lộ email")
        self.assertNotIn(self.tk_an["Authorization"].split(" ", 1)[1], than)


class C_HoSoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.u, cls.tk = nguoi("hoso")

    def test_bio_fandom_accent_luu_that(self):
        from server.social import ACCENT_PRESETS

        r = client.put("/api/me/profile", json={"bio": f"Xin chào {RUN}", "fandom_ids": ["naruto", "one-piece"],
                                                 "accent": ACCENT_PRESETS[0]}, headers=self.tk)
        self.assertEqual(r.status_code, 200, r.text)
        me = client.get("/api/auth/me", headers=self.tk).json()["profile"]
        self.assertEqual(me["bio"], f"Xin chào {RUN}")
        self.assertEqual(me["fandom_ids"], ["naruto", "one-piece"])
        self.assertEqual(me["accent"], ACCENT_PRESETS[0])

    def test_fandom_sai_khong_ghi_gi(self):
        truoc = client.get("/api/auth/me", headers=self.tk).json()["profile"]["bio"]
        r = client.put("/api/me/profile", json={"bio": "Không được lưu", "fandom_ids": ["khong-ton-tai"]}, headers=self.tk)
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(client.get("/api/auth/me", headers=self.tk).json()["profile"]["bio"], truoc)

    def test_avatar_luu_that_va_co_url(self):
        r = client.put("/api/me/profile", json={"avatar": {"data": _png_b64(), "mime": "image/png"}}, headers=self.tk)
        self.assertEqual(r.status_code, 200, r.text)
        p = r.json()["profile"]
        self.assertTrue(p["avatar_key"].startswith(f"avatars/{self.u['user_id']}/"), p["avatar_key"])
        me = client.get("/api/auth/me", headers=self.tk).json()["profile"]
        self.assertEqual(me["avatar_key"], p["avatar_key"])
        r = client.put("/api/me/profile", json={"avatar": {"data": "cmFj", "mime": "image/png"}}, headers=self.tk)
        self.assertEqual(r.status_code, 400, r.text)

    def test_khung_chi_trang_bi_duoc_khi_so_huu(self):
        from server.gamification_domain import CosmeticInventoryItem

        r = client.put("/api/me/profile", json={"frame": "khung_go"}, headers=self.tk)
        self.assertIn(r.status_code, (400, 403), f"trang bị khung chưa sở hữu: {r.status_code} {r.text[:200]}")
        main.gamification_store.grant_cosmetic(CosmeticInventoryItem(user_id=self.u["user_id"], cosmetic_key="khung_go"))
        r = client.put("/api/me/profile", json={"frame": "khung_go"}, headers=self.tk)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("khung_go", json.dumps(client.get("/api/account/cosmetics", headers=self.tk).json()))
        self.assertIn("khung_go", json.dumps(r.json()["profile"].get("equipped_cosmetics")))
        r = client.put("/api/me/profile", json={"frame": None}, headers=self.tk)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("khung_go", json.dumps(r.json()["profile"].get("equipped_cosmetics")))


class D_XpNguyenTuTest(unittest.TestCase):
    """Duong CAS + transaction 3 thao tac cua Appwrite THAT, luong THAT."""

    def test_cong_dong_thoi_khong_mat_khong_trung(self):
        from server.gamification_domain import XpLedgerEntry

        u, _ = nguoi("xp")
        uid = u["user_id"]
        kho = main.gamification_store
        entries = [XpLedgerEntry(entry_id=f"xp_{RUN}_{i}", user_id=uid, event_type="game_match_completed",
                                 source_kind="game_match", source_id=f"stg_{RUN}_{i}", xp_awarded=2)
                   for i in range(8)]
        # Moi entry bi gui HAI lan cung luc — lan thu hai phai la no-op, khong cong hai lan.
        viec = [lambda e=e: kho.award_xp_atomic(e) for e in entries for _ in range(2)]
        _, loi = _chay_dong_thoi(viec)
        self.assertEqual(loi, [], loi)
        self.assertEqual(kho.get_progress(uid).xp, 16)
        so_cai = [e for e in kho.list_xp_events(uid) if e.source_id.startswith(f"stg_{RUN}_")]
        self.assertEqual(len(so_cai), 8)
        self.assertEqual(sum(e.xp_awarded for e in so_cai), 16)

    def test_ghi_khong_doi_du_lieu_khong_khoa_xp_vinh_vien(self):
        """HOI QUY Cloud 2.3 (do that 2026-09-28): cap nhat KHONG doi du lieu van commit nhung GIU
        `$updatedAt`. Truoc ban sua `fix/xp-cas-noop-update`, marker CAS (xp, `$updatedAt`) trung dung
        trang thai hien tai -> MOI lan ghi sau (ke ca cong XP) xung dot VINH VIEN. Sau ban sua: moi lan
        ghi nguyen tu dat `updated_at` moi nen `$updatedAt` luon tien."""
        from server import gamification_service as gsv
        from server.gamification_domain import XpLedgerEntry

        u, _ = nguoi("noop")
        uid = u["user_id"]
        kho = main.gamification_store

        def e(i):
            return XpLedgerEntry(entry_id=f"xn_{RUN}_{i}", user_id=uid, event_type="game_match_completed",
                                 source_kind="game_match", source_id=f"stn_{RUN}_{i}", xp_awarded=2)

        kho.award_xp_atomic(e(0))
        truoc = kho.get_progress(uid)
        for _ in range(2):
            gsv.equip_title(kho, uid, "")  # khong doi gi ve mat nghiep vu (danh xung dang la mac dinh)
        for i in (1, 2):
            self.assertIsNotNone(kho.award_xp_atomic(e(i)), "cộng XP sau lần ghi không đổi dữ liệu phải thành công")
        sau = kho.get_progress(uid)
        self.assertEqual((truoc.xp, sau.xp), (2, 6))
        self.assertNotEqual(sau.updated_at, truoc.updated_at)
        so_cai = [x for x in kho.list_xp_events(uid) if x.source_id.startswith(f"stn_{RUN}_")]
        self.assertEqual((len(so_cai), sum(x.xp_awarded for x in so_cai)), (3, 6))

    def test_doi_danh_xung_dong_thoi_khong_de_len_xp(self):
        from server import gamification_service as gsv
        from server.gamification_domain import XpLedgerEntry

        from server.appwrite_adapter import AppwriteUnavailableError

        u, _ = nguoi("title")
        uid = u["user_id"]
        kho = main.gamification_store
        entries = [XpLedgerEntry(entry_id=f"xt_{RUN}_{i}", user_id=uid, event_type="game_match_completed",
                                 source_kind="game_match", source_id=f"stt_{RUN}_{i}", xp_awarded=2) for i in range(6)]
        viec = [lambda e=e: kho.award_xp_atomic(e) for e in entries]
        viec += [lambda: gsv.equip_title(kho, uid, "") for _ in range(4)]
        _, loi = _chay_dong_thoi(viec)
        # Duoi tranh chap THAT (10 writer, cung mot hang, qua mang toi SGP) mot so luot co the het luot thu CAS
        # -> AppwriteUnavailableError (API tra 503, client thu lai). KHONG hop le: loi khac, mat hay trung XP.
        self.assertTrue(all(isinstance(e, (gsv.GamificationError, AppwriteUnavailableError)) for e in loi), loi)
        tam_thoi = sum(isinstance(e, AppwriteUnavailableError) for e in loi)
        print(f"\n[XP-HON-HOP] loi_tam_thoi={tam_thoi}/{len(viec)} (het luot thu CAS)", flush=True)
        so_cai = lambda: [e for e in kho.list_xp_events(uid) if e.source_id.startswith(f"stt_{RUN}_")]  # noqa: E731
        self.assertEqual(kho.get_progress(uid).xp, sum(e.xp_awarded for e in so_cai()),
                         "tiến độ lệch sổ cái: mất hoặc trùng một lượt cộng")
        # Client thu lai TUAN TU moi entry: da ghi thi la no-op (idempotent), chua ghi thi ghi dung mot lan.
        for e in entries:
            kho.award_xp_atomic(e)
        self.assertEqual(kho.get_progress(uid).xp, 12)
        self.assertEqual(len(so_cai()), 6)


class E_GamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.x, cls.tk_x = nguoi("gx")
        cls.o, cls.tk_o = nguoi("go")

    def _phong_dang_choi(self) -> str:
        r = client.post("/api/games/rooms", json={"game": "caro"}, headers=self.tk_x)
        self.assertEqual(r.status_code, 200, r.text)
        code = r.json()["room"]["code"]
        self.assertEqual(client.post("/api/games/rooms/join", json={"code": code.lower()}, headers=self.tk_o).status_code, 200)
        for tk in (self.tk_x, self.tk_o):
            r = client.post(f"/api/games/rooms/{code}/ready", json={"ready": True}, headers=tk)
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["room"]["status"], "playing")
        return code

    def _danh_het(self, code: str) -> Dict[str, Any]:
        room = {}
        for k in range(5):
            r = client.post(f"/api/games/rooms/{code}/move", json={"index": NUOC_X[k], "move_no": 2 * k}, headers=self.tk_x)
            self.assertEqual(r.status_code, 200, r.text)
            room = r.json()["room"]
            if k < 4:
                r = client.post(f"/api/games/rooms/{code}/move", json={"index": NUOC_O[k], "move_no": 2 * k + 1},
                                headers=self.tk_o)
                self.assertEqual(r.status_code, 200, r.text)
        return room

    def _xp(self, tk) -> int:
        return client.get("/api/account/progress", headers=tk).json()["xp"]

    def test_van_caro_quyet_toan_dung_mot_lan_ke_ca_nhieu_worker_cung_luc(self):
        from server import games_service as gs

        xp_x0, xp_o0 = self._xp(self.tk_x), self._xp(self.tk_o)
        code = self._phong_dang_choi()
        room = self._danh_het(code)
        self.assertEqual((room["status"], room["winner"], room["settlement"]), ("finished", "x", "settled"))
        self.assertEqual(self._xp(self.tk_x) - xp_x0, 5)
        self.assertEqual(self._xp(self.tk_o) - xp_o0, 2)
        # Nhieu worker cung thay mot ban "pending" CU cua chinh van do (dung la cuoc dua ma
        # `settle_pending` song song gap) — quyet toan phai la no-op, khong cong them XP nao.
        goc = main.games_store.get_room_by_code(code)
        self.assertIsNotNone(goc)
        goc.settlement = "pending"
        _, loi = _chay_dong_thoi([lambda: gs.settle(main.games_store, main.gamification_store, goc) for _ in range(5)])
        self.assertEqual(loi, [], loi)
        self.assertEqual(self._xp(self.tk_x) - xp_x0, 5)
        self.assertEqual(self._xp(self.tk_o) - xp_o0, 2)
        self.assertEqual(len(main.games_store.list_results_for_source(f"{goc.room_id}-1")), 2)

    def test_sau_khi_ket_thuc_body_khong_doi_duoc_ket_qua(self):
        code = self._phong_dang_choi()
        self._danh_het(code)
        xp = self._xp(self.tk_x)
        for duong, body, tk in ((f"/api/games/rooms/{code}/resign", {"winner": "o", "xp": 999}, self.tk_x),
                                (f"/api/games/rooms/{code}/move", {"index": 200, "move_no": 9, "winner": "o"}, self.tk_o),
                                (f"/api/games/rooms/{code}/claim-timeout", {"xp": 50}, self.tk_o)):
            r = client.post(duong, json=body, headers=tk)
            self.assertEqual(r.status_code, 409, f"{duong}: {r.text[:200]}")
        self.assertEqual(self._xp(self.tk_x), xp)

    def test_bang_xep_hang_co_nguoi_thang(self):
        # unittest chay theo thu tu chu cai: bai nay chay TRUOC cac van o bai khac — tu choi mot van voi
        # hai tai khoan MOI (khong dung tran cap-doi-thu cua cap x/o o cac bai khac).
        cu = (self.x, self.tk_x, self.o, self.tk_o)
        try:
            self.x, self.tk_x = nguoi("bxhx")
            self.o, self.tk_o = nguoi("bxho")
            self._danh_het(self._phong_dang_choi())
            x_id, o_id = self.x["user_id"], self.o["user_id"]
        finally:
            self.x, self.tk_x, self.o, self.tk_o = cu
        r = client.get("/api/games/leaderboard?game=caro&limit=100")
        self.assertEqual(r.status_code, 200, r.text)
        diem = {it["user_id"]: it["points"] for it in r.json()["items"]}
        self.assertEqual(diem.get(x_id), 3, "người thắng chưa có trên bảng xếp hạng")
        self.assertEqual(diem.get(o_id), 0)
        self.assertEqual(client.get("/api/games/leaderboard?game=chess").status_code, 400)

    def test_memory_khong_lo_bo_cuc_va_chi_chu_luot(self):
        r = client.post("/api/games/memory/runs", json={"difficulty": "easy"}, headers=self.tk_x)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("layout", r.text)
        rid = r.json()["run"]["run_id"]
        r = client.post(f"/api/games/memory/runs/{rid}/flip", json={"index": 0, "seq": 0}, headers=self.tk_x)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("layout", r.text)
        self.assertEqual(client.get(f"/api/games/memory/runs/{rid}", headers=self.tk_o).status_code, 403)
        self.assertEqual(client.post(f"/api/games/memory/runs/{rid}/flip", json={"index": 1, "seq": 1},
                                     headers=self.tk_o).status_code, 403)
        self.assertEqual(client.post(f"/api/games/memory/runs/{rid}/abandon", json={}, headers=self.tk_x).status_code, 200)


class F_HanMucVaDongThoiTest(unittest.TestCase):
    def test_han_muc_dang_bai_dem_tren_du_lieu_appwrite(self):
        u, tk = nguoi("hanmuc")
        khoa_dau = _khoa("hm")
        ma = []
        for i in range(12):  # FAS_SOCIAL_LIMITS=post:12/60 (run_live)
            r = client.post("/api/posts", json={"text": f"bài {i}", "client_key": khoa_dau if i == 0 else ""}, headers=tk)
            ma.append(r.status_code)
        self.assertEqual(ma, [201] * 12)
        self.assertEqual(client.post("/api/posts", json={"text": "bài 13"}, headers=tk).status_code, 429)
        # Gui lai client_key cu KHONG bi tinh vao han muc.
        self.assertEqual(client.post("/api/posts", json={"text": "x", "client_key": khoa_dau}, headers=tk).status_code, 200)

    def test_cung_client_key_dong_thoi_chi_mot_bai(self):
        u, tk = nguoi("dongthoi")
        p = ho_so(tk)
        k = _khoa("dt")
        kq, loi = _chay_dong_thoi([lambda: main.social.create_post(p, text="đua", client_key=k) for _ in range(6)])
        ids = {r["post_id"] for r in kq if r}
        self.assertEqual(len(ids), 1, (ids, loi))
        so_bai = [it for it in client.get(f"/api/users/{u['user_id']}/posts").json().get("items", [])
                  if it.get("post_id") in ids]
        self.assertLessEqual(len(so_bai), 1)

    def test_like_dong_thoi_mot_nguoi_chi_mot_like(self):
        _, tk_a = nguoi("likeA")
        _, tk_b = nguoi("likeB")
        pid = client.post("/api/posts", json={"text": "đua like"}, headers=tk_a).json()["post"]["post_id"]
        pb = ho_so(tk_b)
        _, loi = _chay_dong_thoi([lambda: main.social.like_post(pb, pid) for _ in range(6)])
        self.assertLessEqual(len(loi), 5, loi)
        self.assertEqual(client.get(f"/api/posts/{pid}").json()["post"]["like_count"], 1)


if __name__ == "__main__":
    unittest.main()
