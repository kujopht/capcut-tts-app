"""
Tang HTTP cua mini-game — `server/main.py` `/api/games/*` (Social & Play V1 goi C).

Nghiep vu (luat Caro/Memory, quyet toan, tran) da kiem o `test_games_*`. Bo nay
kiem nhung thu CHI tang HTTP quyet dinh:

  - co `FAS_GAMES_V1` TAT: `/config` noi `enabled: false`, moi route khac 404;
  - 401 khi chua dang nhap, 403/404/409 dung nghia, KHONG BAO GIO 500 cho mot
    ma phong/luot la hay mot vi pham luat;
  - nguoi choi LUON lay tu token; body khong dat duoc nguoi thang/XP/diem;
  - mot van hai nguoi qua HTTP -> XP that tren tai khoan + hang so cai + bang
    xep hang theo game; bo cuc Memory khong bao gio nam trong phan hoi;
  - cong quan tri doi soat: nguoi thuong 403, quan tri thay dung entry so cai.
"""

from __future__ import annotations

import dataclasses
import json
import os
import unittest

os.environ.setdefault("DATA_BACKEND", "mock")
os.environ.setdefault("STORAGE_BACKEND", "local")

from fastapi.testclient import TestClient       # noqa: E402

from server import main                          # noqa: E402
from server.gamification_store import MockGamificationStore   # noqa: E402
from server.games_store import MockGamesStore   # noqa: E402

# KHONG goi `rate_limit.limiter.reset()` o day: bo dem la TOAN CUC cho ca suite, reset giua chung
# lam doi ket qua cua bai KHAC chay sau (do that tren Lightning: 77 bai "tu xanh" o suite candidate).
# Bai nay khong can: moi bai dung tai khoan MOI -> khoa rate-limit rieng (usr:<bam token>).

# X thang: hang 7 cot 3..7; O danh hang 0 — khong ai vo tinh tao duong 5 khac.
NUOC_X = [7 * 15 + c for c in range(3, 8)]
NUOC_O = [0 * 15 + c for c in range(0, 4)]


class Nen(unittest.TestCase):
    def setUp(self) -> None:
        from server.adapters import MockIdentityAdapter

        self.client = TestClient(main.app)
        self._cu = (main.identity, main.games_store, main.gamification_store, main.settings)
        main.identity = MockIdentityAdapter()
        main.games_store = MockGamesStore()
        main.gamification_store = MockGamificationStore()
        self.lan, self.tk_lan = self._nguoi("lan@vidu.vn", "Lan")
        self.minh, self.tk_minh = self._nguoi("minh@vidu.vn", "Minh")
        self.hoa, self.tk_hoa = self._nguoi("hoa@vidu.vn", "Hoa")
        main.settings = dataclasses.replace(
            main.settings, games_v1_enabled=True, admin_user_ids=(self.hoa.user_id,))

    def tearDown(self) -> None:
        main.identity, main.games_store, main.gamification_store, main.settings = self._cu

    def _nguoi(self, email: str, ten: str):
        ho_so = main.identity.register(email, "MatKhau123", ten)
        token = main.identity.login(email, "MatKhau123")
        return ho_so, {"Authorization": f"Bearer {token}"}

    def _phong_dang_choi(self) -> str:
        r = self.client.post("/api/games/rooms", json={"game": "caro"}, headers=self.tk_lan)
        self.assertEqual(r.status_code, 200, r.text)
        code = r.json()["room"]["code"]
        r = self.client.post("/api/games/rooms/join", json={"code": code.lower()}, headers=self.tk_minh)
        self.assertEqual(r.status_code, 200, r.text)
        for tk in (self.tk_lan, self.tk_minh):
            r = self.client.post(f"/api/games/rooms/{code}/ready", json={"ready": True}, headers=tk)
            self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["room"]["status"], "playing")
        return code

    def _danh_het(self, code: str) -> dict:
        room = None
        for k in range(5):
            r = self.client.post(f"/api/games/rooms/{code}/move",
                                 json={"index": NUOC_X[k], "move_no": 2 * k}, headers=self.tk_lan)
            self.assertEqual(r.status_code, 200, r.text)
            room = r.json()["room"]
            if k < 4:
                r = self.client.post(f"/api/games/rooms/{code}/move",
                                     json={"index": NUOC_O[k], "move_no": 2 * k + 1}, headers=self.tk_minh)
                self.assertEqual(r.status_code, 200, r.text)
        return room


class CoTatTest(Nen):
    def test_co_tat_config_noi_that_va_moi_route_khac_404(self):
        main.settings = dataclasses.replace(main.settings, games_v1_enabled=False)
        self.assertEqual(self.client.get("/api/games/config").json(), {"enabled": False})
        for method, duong in (("post", "/api/games/rooms"), ("get", "/api/games/leaderboard"),
                              ("post", "/api/games/memory/runs"), ("get", "/api/games/me/history")):
            kw = {"headers": self.tk_lan}
            if method == "post":
                kw["json"] = {"game": "caro", "difficulty": "easy"}
            r = getattr(self.client, method)(duong, **kw)
            self.assertEqual(r.status_code, 404, f"{method} {duong}: {r.text}")

    def test_co_bat_config_co_luat_va_tran(self):
        c = self.client.get("/api/games/config").json()
        self.assertTrue(c["enabled"])
        self.assertEqual(c["rewards"], {"match_completed": 2, "match_won": 3, "run_completed": 2})
        self.assertEqual(c["caps"]["daily_game_xp"], 30)
        self.assertEqual(set(c["memory"]["difficulties"]), {"easy", "normal", "hard"})


class XacThucVaMaLoiTest(Nen):
    def test_chua_dang_nhap_401(self):
        self.assertEqual(self.client.post("/api/games/rooms", json={"game": "caro"}).status_code, 401)
        self.assertEqual(self.client.post("/api/games/memory/runs", json={"difficulty": "easy"}).status_code, 401)
        self.assertEqual(self.client.get("/api/games/me/history").status_code, 401)

    def test_ma_phong_va_luot_la_tra_404_khong_phai_500(self):
        self.assertEqual(self.client.get("/api/games/rooms/ZZZZZZ", headers=self.tk_lan).status_code, 404)
        self.assertEqual(self.client.post("/api/games/rooms/join", json={"code": "ZZZZZZ"},
                                          headers=self.tk_lan).status_code, 404)
        self.assertEqual(self.client.get("/api/games/memory/runs/mr_khongco", headers=self.tk_lan).status_code, 404)
        self.assertEqual(self.client.post("/api/games/memory/runs/mr_khongco/flip", json={"index": 0, "seq": 0},
                                          headers=self.tk_lan).status_code, 404)

    def test_bang_xep_hang_tham_so_sai_400_va_gioi_han_bi_chan(self):
        self.assertEqual(self.client.get("/api/games/leaderboard?game=chess").status_code, 400)
        self.assertEqual(self.client.get("/api/games/leaderboard?game=memory&difficulty=insane").status_code, 400)
        r = self.client.get("/api/games/leaderboard?game=caro&limit=100000")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["limit"], 100)


class VanHaiNguoiQuaHttpTest(Nen):
    def test_van_thang_xp_that_so_cai_va_bang_xep_hang(self):
        code = self._phong_dang_choi()
        # Nguoi thu ba khong vao duoc; chu phong vao lai khong chiem ghe thu hai.
        self.assertEqual(self.client.post("/api/games/rooms/join", json={"code": code},
                                          headers=self.tk_hoa).status_code, 409)
        r = self.client.post("/api/games/rooms/join", json={"code": code}, headers=self.tk_lan)
        self.assertEqual(r.json()["room"]["you"], "x")
        room = self._danh_het(code)
        self.assertEqual(room["status"], "finished")
        self.assertEqual(room["winner"], "x")
        self.assertEqual(len(room["win_line"]), 5)
        self.assertEqual(room["settlement"], "settled")
        self.assertEqual(room["rewards"][self.lan.user_id]["xp"], 5)
        self.assertEqual(room["rewards"][self.minh.user_id]["xp"], 2)
        self.assertEqual(self.client.get("/api/account/progress", headers=self.tk_lan).json()["xp"], 5)
        self.assertEqual(self.client.get("/api/account/progress", headers=self.tk_minh).json()["xp"], 2)

        lich_su = self.client.get("/api/games/me/history", headers=self.tk_lan).json()["items"]
        self.assertEqual(lich_su[0]["outcome"], "win")
        self.assertEqual(sorted(e["event_type"] for e in lich_su[0]["xp_entries"]),
                         ["game_match_completed", "game_match_won"])
        self.assertEqual(lich_su[0]["settlement_state"], "settled")

        bxh = self.client.get("/api/games/leaderboard?game=caro", headers=self.tk_minh).json()
        self.assertEqual([(it["user_id"], it["points"]) for it in bxh["items"]],
                         [(self.lan.user_id, 3), (self.minh.user_id, 0)])
        self.assertIn(bxh["season"], bxh["seasons"])
        self.assertIsNone(bxh["viewer_entry"])  # Minh da nam trong trang.
        # Mua khac va game khac KHONG lan du lieu.
        self.assertEqual(self.client.get("/api/games/leaderboard?game=caro&season=2020-01").json()["items"], [])
        self.assertEqual(self.client.get("/api/games/leaderboard?game=memory&difficulty=easy").json()["items"], [])

    def test_body_khong_dat_duoc_nguoi_thang_xp_hay_diem(self):
        code = self._phong_dang_choi()
        room = self._danh_het(code)
        self.assertEqual(room["winner"], "x")
        # Sau khi ket thuc: moi yeu cau "sua ket qua" deu bi tu choi, so cai khong doi.
        for duong, body, tk in ((f"/api/games/rooms/{code}/resign", {"winner": "o", "xp": 999}, self.tk_lan),
                                (f"/api/games/rooms/{code}/move", {"index": 200, "move_no": 9, "winner": "o"}, self.tk_minh),
                                (f"/api/games/rooms/{code}/claim-timeout", {"xp": 50}, self.tk_minh)):
            r = self.client.post(duong, json=body, headers=tk)
            self.assertEqual(r.status_code, 409, f"{duong}: {r.text}")
        r = self.client.get(f"/api/games/rooms/{code}", headers=self.tk_lan).json()["room"]
        self.assertEqual(r["winner"], "x")
        self.assertEqual(self.client.get("/api/account/progress", headers=self.tk_lan).json()["xp"], 5)
        self.assertEqual(self.client.get("/api/account/progress", headers=self.tk_minh).json()["xp"], 2)

    def test_quan_tri_doi_soat_thay_dung_entry_so_cai(self):
        code = self._phong_dang_choi()
        self._danh_het(code)
        self.assertEqual(self.client.get(f"/api/admin/games/rooms/{code}", headers=self.tk_lan).status_code, 403)
        r = self.client.get(f"/api/admin/games/rooms/{code}", headers=self.tk_hoa)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(len(body["room"]["moves"]), 9)
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(sorted(e["event_type"] for e in body["xp_ledger"][self.lan.user_id]),
                         ["game_match_completed", "game_match_won"])
        self.assertEqual([e["xp_awarded"] for e in body["xp_ledger"][self.minh.user_id]], [2])


class MemoryQuaHttpTest(Nen):
    def test_bo_cuc_khong_bao_gio_nam_trong_phan_hoi_va_chu_luot_duoc_bao_ve(self):
        r = self.client.post("/api/games/memory/runs", json={"difficulty": "easy"}, headers=self.tk_lan)
        self.assertEqual(r.status_code, 200, r.text)
        run = r.json()["run"]
        self.assertNotIn("layout", json.dumps(r.json()))
        self.assertEqual((run["rows"], run["cols"], run["pairs"]), (3, 4, 6))
        r = self.client.post(f"/api/games/memory/runs/{run['run_id']}/flip",
                             json={"index": 0, "seq": 0}, headers=self.tk_lan)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("layout", json.dumps(r.json()))
        self.assertEqual(r.json()["flip"]["index"], 0)
        self.assertEqual(self.client.get(f"/api/games/memory/runs/{run['run_id']}",
                                         headers=self.tk_minh).status_code, 403)
        self.assertEqual(self.client.post(f"/api/games/memory/runs/{run['run_id']}/flip",
                                          json={"index": 1, "seq": 1}, headers=self.tk_minh).status_code, 403)
        self.assertEqual(self.client.post("/api/games/memory/runs", json={"difficulty": "insane"},
                                          headers=self.tk_lan).status_code, 400)


if __name__ == "__main__":
    unittest.main()
