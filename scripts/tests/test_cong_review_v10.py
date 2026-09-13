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

    def test_11_luat_B5_da_duoc_CAM_vao_duong_that(self):
        """Chính sách này từng là MÃ CHẾT — định nghĩa, kiểm, không ai gọi.

        Đúng lời chủ sở hữu về vòng sự cố: *"tested but not wired"*. Bài này
        neo rằng nó đã được cắm, và cắm ở ĐÚNG chỗ duy nhất giữ chính sách
        gọi Reviewer.
        """
        from pathlib import Path
        goc = Path(__file__).resolve().parents[2] / "scripts" / "control_center"
        kd = (goc / "execution" / "kiem_dinh.py").read_text(encoding="utf-8")
        self.assertIn("can_review_doc_lap", kd,
                      "`nen_goi_reviewer` phải HỎI luật B5")
        dp = (goc / "execution" / "dieu_phoi.py").read_text(encoding="utf-8")
        i = dp.index("nen_goi_reviewer(")
        self.assertIn("model_da_lam=", dp[i:i + 200],
                      "chỗ gọi phải truyền model ĐÃ VIẾT MÃ, không thì luật "
                      "B5 không bao giờ kích hoạt")

    def test_11c_HANH_VI_gemini_sua_ma_thi_CONG_bat_goi_reviewer(self):
        """Bài neo cấu trúc là chưa đủ — nó bắt được việc XOÁ lời gọi, nhưng
        không bắt được việc VÔ HIỆU HOÁ nó (đã đo: một đột biến làm luật
        không bao giờ kích hoạt mà bộ kiểm vẫn xanh).

        Bài này hỏi thẳng cái cổng: mọi phép đo XANH, không tiêu chí nào đòi
        ngữ nghĩa, không chạm production, rủi ro thấp — mà mã sản phẩm do họ
        Gemini viết, thì vẫn PHẢI gọi phản biện.
        """
        from scripts.control_center.execution import ke_hoach as KH
        from scripts.control_center.execution import y_dinh as YD
        from scripts.control_center.execution.kiem_dinh import (BaoCaoKiemDinh,
                                                                nen_goi_reviewer)

        y = YD.tao_y_dinh(project_id="demo",
                          goal="sửa scripts/app.py cho đúng",
                          cau_nguoi_dung="sửa scripts/app.py cho đúng")
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=(KH.BuocKeHoach(buoc_id="a", tieu_de="a", muc_tieu="làm a"),))
        # Mọi phép đo XANH: không bước hỏng, không tiêu chí đỏ.
        bc = BaoCaoKiemDinh(execution_id=y.execution_id, buoc_dat=("a",))

        nen, _ = nen_goi_reviewer(kh, y, bc)
        self.assertFalse(nen, "không có luật nào -> không tiêu một lượt model")

        nen2, vs2 = nen_goi_reviewer(kh, y, bc,
                                     model_da_lam="gemini-3.1-pro-low",
                                     loai_viec="implementation")
        self.assertTrue(nen2, "họ Gemini viết mã sản phẩm -> BẮT BUỘC phản "
                              "biện, kể cả khi mọi phép đo đều xanh")
        self.assertIn("gemini", vs2.lower())

        nen3, _ = nen_goi_reviewer(kh, y, bc, model_da_lam="claude-sonnet-5",
                                   loai_viec="implementation")
        self.assertFalse(nen3, "luật B5 hẹp có chủ đích — không phải họ nào "
                               "cũng kích hoạt")

    def test_11b_chuoi_loai_viec_o_cho_goi_PHAI_khop_tap_luat(self):
        """Lệch một chữ giữa hai tệp là cả luật thành lệnh rỗng, im lặng."""
        from pathlib import Path

        from scripts.control_center.v10.vai_tro import VIEC_SUA_MA
        dp = (Path(__file__).resolve().parents[2] / "scripts"
              / "control_center" / "execution" / "dieu_phoi.py"
              ).read_text(encoding="utf-8")
        i = dp.index("loai_ma = _k.model,")
        chuoi = dp[i:i + 80].split('"')[1]
        self.assertIn(chuoi, VIEC_SUA_MA,
                      f"chỗ gọi dùng {chuoi!r}, không có trong VIEC_SUA_MA")

    def test_10_nhan_dang_ho_model_dung(self):
        self.assertEqual(ho_model("gemini-3.8-flash-high"), "gemini")
        self.assertEqual(ho_model("claude-sonnet-4-6"), "claude")
        self.assertEqual(ho_model("gpt-6-astra"), "openai")
        self.assertEqual(ho_model("codex-default"), "openai")
        self.assertEqual(ho_model("fable-5-1"), "fable")


if __name__ == "__main__":
    unittest.main()
