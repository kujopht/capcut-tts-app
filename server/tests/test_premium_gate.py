"""Khoa tap bang tag `gate:premium-after-N` (3 bo moi: N = 1).

Quy tac (mirror gate login, xem `server/main.py::_premium_gate_after`):
  - Khach an danh + user FREE: doc/nghe duoc cac tap co `order_index <= N`,
    tap sau do tra 403 (chuong) / 403 (audio).
  - User PREMIUM (tier LISTENER_PRO/ULTRA) + chu so huu: doc/nghe full.
  - Truyen khong co gate tag: hanh vi cu khong doi (public = ai cung doc).

Gate song trong `tags` san co nen khong doi schema bang novels; backend boc
ra va loc khoi API public (`_novel_out`), muc luc danh dau `premium_locked`
theo tung viewer.
"""

from __future__ import annotations

import unittest

from server.domain import Tier
from server.tests.test_admin import Base


class PremiumGateTest(Base):
    def setUp(self):
        super().setUp()
        from server.domain import Chapter, Novel

        self.nov = self.store.create_novel(Novel(
            owner_id="svc_harvester", title="Truyện khóa premium",
            description="", tags=["gate:premium-after-1"])).novel_id
        self.chapters = {}
        for i in range(1, 4):
            ch = self.store.create_chapter(Chapter(
                novel_id=self.nov, owner_id="svc_harvester",
                title=f"Tập {i}", content=f"Nội dung tập {i}.",
                order_index=i))
            self.chapters[i] = ch.chapter_id
        r = self.client.post(f"/api/admin/novels/{self.nov}/publish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)

        # Truyen cung gate nhung thuoc ve user thuong (test mien chu so huu).
        self.nov_chu = self.store.create_novel(Novel(
            owner_id=self.thuong["user_id"], title="Truyện của chủ",
            description="", tags=["gate:premium-after-1"])).novel_id
        self.ch_chu = self.store.create_chapter(Chapter(
            novel_id=self.nov_chu, owner_id=self.thuong["user_id"],
            title="Tập 2", content="Của chủ.",
            order_index=2)).chapter_id
        r = self.client.post(f"/api/admin/novels/{self.nov_chu}/publish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)

        # User premium (tier ULTRA).
        self.prem, self.h_prem = self._dang_ky("prem@fanfic.local",
                                               "Người Premium")
        p = self.identity.get_profile(self.prem["user_id"])
        p.tier = Tier.ULTRA
        self.identity.save_profile(p)

        self.nov_mo = self.store.create_novel(Novel(
            owner_id="svc_harvester", title="Truyện không khóa",
            description="", tags=[])).novel_id
        self.ch_mo = self.store.create_chapter(Chapter(
            novel_id=self.nov_mo, owner_id="svc_harvester",
            title="Chương 1", content="Mở cho mọi người.",
            order_index=1)).chapter_id
        r = self.client.post(f"/api/admin/novels/{self.nov_mo}/publish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)

    def test_khach_doc_duoc_tap_trong_nguong(self):
        r = self.client.get(f"/api/chapters/{self.chapters[1]}")
        self.assertEqual(r.status_code, 200, r.text)

    def test_khach_bi_chan_o_tap_khoa_voi_403(self):
        r = self.client.get(f"/api/chapters/{self.chapters[2]}")
        self.assertEqual(r.status_code, 403, r.text)

    def test_khach_bi_chan_audio_tap_khoa(self):
        r = self.client.get(f"/api/audio/{self.chapters[2]}/url")
        self.assertEqual(r.status_code, 403, r.text)

    def test_user_free_bi_chan_o_tap_khoa(self):
        r = self.client.get(f"/api/chapters/{self.chapters[2]}",
                            headers=self.h_thuong)
        self.assertEqual(r.status_code, 403, r.text)

    def test_user_premium_doc_duoc_tap_khoa(self):
        r = self.client.get(f"/api/chapters/{self.chapters[2]}",
                            headers=self.h_prem)
        self.assertEqual(r.status_code, 200, r.text)

    def test_chu_so_huu_doc_duoc_tap_khoa(self):
        r = self.client.get(f"/api/chapters/{self.ch_chu}",
                            headers=self.h_thuong)
        self.assertEqual(r.status_code, 200, r.text)

    def test_muc_luc_danh_dau_premium_locked_theo_viewer(self):
        r = self.client.get(f"/api/novels/{self.nov}")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["novel"]["premium_gate_after"], 1)
        self.assertNotIn("gate:premium-after-1", d["novel"]["tags"])
        rows = {c["order_index"]: c for c in d["chapters"]}
        self.assertFalse(rows[1]["premium_locked"])
        self.assertTrue(rows[2]["premium_locked"])
        # User premium: khong tap nao bi danh dau.
        r = self.client.get(f"/api/novels/{self.nov}", headers=self.h_prem)
        rows = {c["order_index"]: c for c in r.json()["chapters"]}
        self.assertFalse(rows[2]["premium_locked"])

    def test_truyen_khong_gate_giu_hanh_vi_cu(self):
        r = self.client.get(f"/api/chapters/{self.ch_mo}")
        self.assertEqual(r.status_code, 200, r.text)

    def test_kich_hoat_premium_khi_da_xac_minh(self):
        # Mock luon tra email_verified=True (xem adapters.py).
        r = self.client.post("/api/premium/activate", headers=self.h_thuong)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tier"], "ultra")
        r = self.client.get("/api/auth/me", headers=self.h_thuong)
        self.assertEqual(r.json()["profile"]["tier"], "ultra")
        r = self.client.post("/api/premium/activate", headers=self.h_thuong)
        self.assertTrue(r.json()["already"])

    def test_trang_thai_premium(self):
        r = self.client.get("/api/premium/status", headers=self.h_prem)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tier"], "ultra")
        self.assertTrue(r.json()["email_verified"])


if __name__ == "__main__":
    unittest.main()
