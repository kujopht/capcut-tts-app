# -*- coding: utf-8 -*-
"""CỔNG REVIEW CHÉO HỌ MODEL — nghiệm thu V1.0 (yêu cầu 7).

Chủ sở hữu đòi chứng minh: **Gemini viết mã sản phẩm thì Router TỰ ĐỘNG đòi
một người phản biện KHÁC HỌ**, khi còn một họ độc lập đủ năng lực. Và việc
cạo/nghiên cứu của Gemini thì KHÔNG bị đòi review khi đã có kiểm tất định.

Bộ kiểm này chạy trên HỢP ĐỒNG ĐỊNH TUYẾN, tất định, không gọi model nào.
Tình trạng khả dụng THẬT của Sonnet được báo riêng (xem
`V10_RELEASE_ACCEPTANCE.md`) — không trộn hai thứ, và không giả vờ có
Sonnet khi không có.
"""

from __future__ import annotations

import unittest

from scripts.control_center.v10.vai_tro import (Vai, can_review_doc_lap,
                                                chon_reviewer, ho_model)

#: Fabric có ĐỦ một họ độc lập (claude) — trường hợp bình thường.
CO_DOC_LAP = ("gemini-3.8-flash-high", "gemini-3.8-flash-medium",
              "claude-sonnet-4-6", "codex-default")

#: Fabric CHỈ có Gemini — trường hợp suy giảm.
CHI_GEMINI = ("gemini-3.8-flash-high", "gemini-3.8-flash-medium")


class TestGeminiSuaMa(unittest.TestCase):

    def test_01_gemini_sua_ma_san_pham_thi_BAT_BUOC_review(self):
        for loai in ("implementation", "testing", "refactor", "migration"):
            with self.subTest(loai=loai):
                r = can_review_doc_lap(loai_viec=loai,
                                       model_da_lam="gemini-3.8-flash-high")
                self.assertTrue(r.bat_buoc, loai)
                self.assertIn("gemini", r.ho_bi_cam)

    def test_02_reviewer_duoc_chon_KHAC_HO(self):
        r = can_review_doc_lap(loai_viec="implementation",
                               model_da_lam="gemini-3.8-flash-high")
        rv = chon_reviewer(CO_DOC_LAP, ho_bi_cam=r.ho_bi_cam)
        self.assertTrue(rv.co)
        self.assertNotEqual(ho_model(rv.model_id), "gemini")

    def test_03_uu_tien_Sonnet_khi_co(self):
        """Ưu tiên là Sonnet — nhưng chỉ khi fabric THẬT SỰ phơi ra nó."""
        rv = chon_reviewer(CO_DOC_LAP, ho_bi_cam=("gemini",))
        self.assertEqual(rv.model_id, "claude-sonnet-4-6")

    def test_04_roi_xuong_ho_doc_lap_KHAC_khi_khong_co_Sonnet(self):
        rv = chon_reviewer(("gemini-3.8-flash-high", "codex-default"),
                           ho_bi_cam=("gemini",))
        self.assertTrue(rv.co)
        self.assertEqual(ho_model(rv.model_id), "openai")

    def test_05_KHONG_co_ho_doc_lap_thi_BAO_SUY_GIAM(self):
        """Không bao giờ lặng lẽ để cùng họ tự chấm."""
        rv = chon_reviewer(CHI_GEMINI, ho_bi_cam=("gemini",))
        self.assertFalse(rv.co)
        self.assertIn("ĐỘC LẬP", rv.ly_do)

    def test_06_KHONG_BAO_GIO_tra_ve_reviewer_cung_ho(self):
        """Bất biến trung tâm, quét trên nhiều cấu hình fabric."""
        for fab in (CO_DOC_LAP, CHI_GEMINI,
                    ("gemini-3.8-flash-high", "claude-sonnet-4-6"),
                    ("gemini-3.8-flash-medium",)):
            with self.subTest(fab=fab):
                rv = chon_reviewer(fab, ho_bi_cam=("gemini",))
                if rv.co:
                    self.assertNotEqual(ho_model(rv.model_id), "gemini")


class TestViecDuLieuKhongBiDoiOan(unittest.TestCase):

    def test_07_cao_web_co_kiem_schema_thi_KHONG_bat_buoc(self):
        for loai in ("scrape", "monitor", "metadata", "classification",
                     "research", "recon"):
            with self.subTest(loai=loai):
                r = can_review_doc_lap(loai_viec=loai,
                                       model_da_lam="gemini-3.8-flash-high",
                                       co_kiem_schema=True)
                self.assertFalse(r.bat_buoc, loai)
                self.assertIn("schema", r.ly_do)

    def test_08_viec_du_lieu_khong_duoc_mien_khi_sua_MA(self):
        """Một việc `implementation` không thành việc dữ liệu vì có schema."""
        r = can_review_doc_lap(loai_viec="implementation",
                               model_da_lam="gemini-3.8-flash-high",
                               co_kiem_schema=True)
        self.assertTrue(r.bat_buoc)


class TestKhongThuHepOan(unittest.TestCase):

    def test_09_ho_khac_sua_ma_khong_bi_cong_nay_chan(self):
        """Cổng này HẸP có chủ đích — nó nói về Gemini + mã sản phẩm."""
        for m in ("claude-sonnet-4-6", "codex-default"):
            with self.subTest(model=m):
                r = can_review_doc_lap(loai_viec="implementation",
                                       model_da_lam=m)
                self.assertFalse(r.bat_buoc)

    def test_10_nhan_dang_ho_model_dung(self):
        self.assertEqual(ho_model("gemini-3.8-flash-high"), "gemini")
        self.assertEqual(ho_model("claude-sonnet-4-6"), "claude")
        self.assertEqual(ho_model("gpt-6-astra"), "openai")
        self.assertEqual(ho_model("codex-default"), "openai")
        self.assertEqual(ho_model("fable-5-1"), "fable")


if __name__ == "__main__":
    unittest.main()
