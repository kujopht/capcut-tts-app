"""
Overnight Phase 1C — gamification khong bi lam dung.

Cac diem da co test o noi khac (khong lap lai o day, chi liet ke de ro pham
vi da phu): idempotent cong XP theo (user_id, event_type, source_id)
(`test_gamification_contract.py`, `test_gamification_service.py`); xuat ban
lai khong cong XP hai lan, chuong tao trong truyen nhap khong duoc cong ngay
(`test_xp_wiring.py`); danh xung phai mo khoa moi trang bi duoc, vat pham
phai so huu moi trang bi duoc, goi thuong khong reroll duoc bang refresh
(`test_gamification_service.py`).

File nay kiem BA dieu CHUA co test rieng, dung nguyen van tu dac ta overnight
Phan 1C:

  1. "page refresh cannot award" — GOI LAI mot GET nhieu lan khong duoc cong
     XP (khac POST — cac route thuong XP DEU la POST, GET khong bao gio goi
     `thuong_xp`).
  2. "self-like loops do not award" — thich/bo thich lien tuc bai viet cua
     NGUOI KHAC khong lam XP nguoi thich hay tac gia bai viet thay doi, vi
     `community_contribution` CHUA duoc noi vao bat ky route nao (quyet dinh
     co y — mot su kien de lam dung ma chua nghi ra cach chong lam dung thi
     bi BO QUA thay vi lam ho ho, xem `docs/GAMIFICATION_DESIGN.md`).
  3. Un-publish roi xuat ban lai KHONG cong `publish_first_novel`/
     `publish_first_chapter` lan hai — id tat dinh theo (user_id, event_type,
     source_id) khong doi giua hai lan xuat ban, nen `record_xp_event` tu
     choi lan hai du duong di la mot chu ky moi (publish -> unpublish ->
     publish) chu khong phai mot request lap lai don thuan.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import MockIdentityAdapter, MockMetadataStore
from server.gamification_store import MockGamificationStore


class GamificationAbuseResistanceTest(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        server_main.gamification_store = MockGamificationStore()
        self.client = TestClient(server_main.app)

    def _dang_ky(self, email: str) -> str:
        resp = self.client.post("/api/auth/register", json={
            "email": email, "password": "MatKhauManh123!",
            "display_name": email.split("@")[0],
        })
        return resp.json()["token"]

    def _xp(self, tok: str) -> int:
        return self.client.get(
            "/api/account/progress",
            headers={"Authorization": f"Bearer {tok}"}).json()["xp"]

    # ===================================================== 1. refresh

    def test_goi_lai_get_progress_nhieu_lan_khong_cong_them_xp(self):
        tok = self._dang_ky("refresh-qa@example.com")
        truoc = self._xp(tok)
        for _ in range(5):
            self.client.get("/api/account/progress",
                            headers={"Authorization": f"Bearer {tok}"})
        sau = self._xp(tok)
        self.assertEqual(truoc, sau)

    def test_goi_lai_get_novel_nhieu_lan_khong_cong_xp(self):
        tok = self._dang_ky("refresh-novel-qa@example.com")
        novel = self.client.post(
            "/api/novels", headers={"Authorization": f"Bearer {tok}"},
            json={"title": "Truyện Refresh QA", "description": "x",
                  "tags": []}).json()["novel"]
        truoc = self._xp(tok)
        for _ in range(5):
            self.client.get(f"/api/novels/{novel['novel_id']}",
                            headers={"Authorization": f"Bearer {tok}"})
        sau = self._xp(tok)
        self.assertEqual(truoc, sau)

    # ===================================================== 2. tu thich

    def test_thich_bo_thich_lien_tuc_khong_cong_xp_cho_ai(self):
        tac_gia_tok = self._dang_ky("tacgia-thich-qa@example.com")
        nguoi_thich_tok = self._dang_ky("nguoi-thich-qa@example.com")
        bai = self.client.post(
            "/api/posts", headers={"Authorization": f"Bearer {tac_gia_tok}"},
            json={"text": "Bài viết để kiểm tra thích."}).json()["post"]

        xp_tac_gia_truoc = self._xp(tac_gia_tok)
        xp_nguoi_thich_truoc = self._xp(nguoi_thich_tok)

        for _ in range(3):
            self.client.post(
                f"/api/posts/{bai['post_id']}/like",
                headers={"Authorization": f"Bearer {nguoi_thich_tok}"}, json={})
            self.client.delete(
                f"/api/posts/{bai['post_id']}/like",
                headers={"Authorization": f"Bearer {nguoi_thich_tok}"})

        self.assertEqual(self._xp(tac_gia_tok), xp_tac_gia_truoc,
                         "tác giả bài viết không được cộng XP từ lượt thích")
        self.assertEqual(self._xp(nguoi_thich_tok), xp_nguoi_thich_truoc,
                         "người bấm thích không được tự cộng XP cho mình")

    # ===================================================== 3. unpublish/republish

    def test_unpublish_roi_xuat_ban_lai_khong_cong_xp_lan_hai(self):
        tok = self._dang_ky("unpub-republish-qa@example.com")
        novel = self.client.post(
            "/api/novels", headers={"Authorization": f"Bearer {tok}"},
            json={"title": "Truyện Unpublish QA", "description": "x",
                  "tags": []}).json()["novel"]
        self.client.post(
            "/api/chapters", headers={"Authorization": f"Bearer {tok}"},
            json={"novel_id": novel["novel_id"], "title": "C1",
                  "content": "Nội dung."})

        self.client.post(f"/api/novels/{novel['novel_id']}/publish",
                         headers={"Authorization": f"Bearer {tok}"})
        xp_sau_lan_1 = self._xp(tok)
        self.assertGreater(xp_sau_lan_1, 0)

        self.client.post(f"/api/novels/{novel['novel_id']}/unpublish",
                         headers={"Authorization": f"Bearer {tok}"})
        self.client.post(f"/api/novels/{novel['novel_id']}/publish",
                         headers={"Authorization": f"Bearer {tok}"})
        xp_sau_lan_2 = self._xp(tok)

        self.assertEqual(xp_sau_lan_1, xp_sau_lan_2,
                         "unpublish rồi xuất bản lại không được cộng XP lần hai")


if __name__ == "__main__":
    unittest.main()
