"""Khoa tap bang tag `gate:login-after-N` (Khó dỗ dành: N = 4).

Quy tac khoa (xem `server/main.py::_login_gate_after`):
  - Khach an danh: doc/nghe duoc cac tap co `order_index <= N`, tap sau do
    tra 403 (chuong) / 403 (audio) thay vi 404 — de giao dien hien nut login
    thay vi "khong tim thay".
  - Nguoi DA DANG NHAP (bat ky ai): doc/nghe full, khong rieng chu so huu.
  - Truyen khong co gate tag: hanh vi cu khong doi (public = ai cung doc).

Gate song trong `tags` san co nen khong doi schema bang novels; backend boc
ra va loc khoi API public (`_novel_out`), muc luc danh dau `locked` cho
khach an danh.
"""

from __future__ import annotations

import unittest

from server.tests.test_admin import Base


class LoginGateTest(Base):
    def setUp(self):
        super().setUp()
        from server.domain import Chapter, Novel

        self.nov = self.store.create_novel(Novel(
            owner_id="svc_harvester", title="Truyện khóa tập",
            description="", tags=["gate:login-after-4"])).novel_id
        self.chapters = {}
        for i in range(1, 7):
            ch = self.store.create_chapter(Chapter(
                novel_id=self.nov, owner_id="svc_harvester",
                title=f"Tập {i}", content=f"Nội dung tập {i}.",
                order_index=i))
            self.chapters[i] = ch.chapter_id
        r = self.client.post(f"/api/admin/novels/{self.nov}/publish",
                             headers=self.h_admin)
        self.assertEqual(r.status_code, 200, r.text)

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
        r = self.client.get(f"/api/chapters/{self.chapters[4]}")
        self.assertEqual(r.status_code, 200, r.text)

    def test_khach_bi_chan_o_tap_khoa_voi_403(self):
        r = self.client.get(f"/api/chapters/{self.chapters[5]}")
        self.assertEqual(r.status_code, 403, r.text)

    def test_khach_bi_chan_audio_tap_khoa(self):
        r = self.client.get(f"/api/audio/{self.chapters[5]}/url")
        self.assertEqual(r.status_code, 403, r.text)

    def test_nguoi_dang_nhap_doc_duoc_tap_khoa(self):
        r = self.client.get(f"/api/chapters/{self.chapters[5]}",
                            headers=self.h_thuong)
        self.assertEqual(r.status_code, 200, r.text)

    def test_muc_luc_danh_dau_locked_va_an_tag_gate(self):
        r = self.client.get(f"/api/novels/{self.nov}")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["novel"]["login_gate_after"], 4)
        self.assertNotIn("gate:login-after-4", d["novel"]["tags"])
        rows = {c["order_index"]: c for c in d["chapters"]}
        self.assertFalse(rows[4]["locked"])
        self.assertTrue(rows[5]["locked"])

    def test_truyen_khong_gate_giu_hanh_vi_cu(self):
        r = self.client.get(f"/api/chapters/{self.ch_mo}")
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == "__main__":
    unittest.main()
