"""Độ dài trường khi ghi lên Appwrite: cắt chẩn đoán, KHÔNG cắt định danh.

Nêu ra qua review độc lập (Codex, 2026-08-29) khi đối chiếu schema trước lúc
cấp phát production. Appwrite từ chối một bản ghi quá dài bằng HTTP 400, và ở
đây 400 nghĩa là cả một đợt quét chết giữa chừng — vì một dòng báo lỗi dài,
hoặc một phần giới thiệu truyện dài hơn bình thường.

Sự phân biệt là điểm chính của bộ bài này:

- Văn bản tự do (tiêu đề, lỗi, cảnh báo, mô tả) -> CẮT. Mất một chút đuôi tốt
  hơn mất cả đợt.
- Định danh (url, hash, fingerprint, id, domain) -> KHÔNG cắt. Một URL bị cắt
  không phải "URL ngắn hơn", nó là MỘT URL KHÁC, và nó làm sai cả việc tải lại
  lẫn việc khử trùng. Ở đó để Appwrite trả 400 thật to mới là đúng.
"""
from __future__ import annotations

import unittest

from server.appwrite_scrape_run_store import (
    COL_ITEMS,
    COL_RUNS,
    _TRAN_VAN_BAN,
    cat_theo_tran,
)
from server.appwrite_site_profile_store import _TRAN_DAU_VAN_TAY, _profile_to_data
from server.scraper.site_profile import SiteProfile


class VanBanTuDoBiCatTest(unittest.TestCase):
    def test_moi_truong_van_ban_deu_bi_cat_dung_tran(self):
        for col, tran in _TRAN_VAN_BAN.items():
            for ten, gioi_han in tran.items():
                data = cat_theo_tran({ten: "x" * (gioi_han + 500)}, tran)
                self.assertEqual(len(data[ten]), gioi_han,
                                 f"{col}.{ten} chưa được cắt")

    def test_gia_tri_vua_du_khong_bi_dong_toi(self):
        """Đúng bằng trần là hợp lệ — cắt thêm sẽ mất dữ liệu vô cớ."""
        tran = _TRAN_VAN_BAN[COL_RUNS]
        nguyen = "y" * tran["series_description"]
        data = cat_theo_tran({"series_description": nguyen}, tran)
        self.assertEqual(data["series_description"], nguyen)

    def test_gia_tri_ngan_giu_nguyen(self):
        tran = _TRAN_VAN_BAN[COL_ITEMS]
        data = cat_theo_tran({"error_message": "ngắn"}, tran)
        self.assertEqual(data["error_message"], "ngắn")

    def test_gia_tri_khong_phai_chuoi_khong_bi_dong_toi(self):
        """`attempts`/`sequence` là số. Một phép cắt vô ý sẽ làm hỏng chúng."""
        tran = {"attempts": 10}
        data = cat_theo_tran({"attempts": 12345678901234}, tran)
        self.assertEqual(data["attempts"], 12345678901234)

    def test_truong_vang_mat_khong_bi_tao_ra(self):
        data = cat_theo_tran({}, _TRAN_VAN_BAN[COL_RUNS])
        self.assertEqual(data, {})


class DinhDanhKhongBiCatTest(unittest.TestCase):
    """Đây là nửa quan trọng hơn: cắt âm thầm ở đây sẽ HỎNG DỮ LIỆU."""

    def test_url_hash_fingerprint_id_khong_nam_trong_bang_tran(self):
        for col, tran in _TRAN_VAN_BAN.items():
            for ten in ("chapter_url", "source_url", "duplicate_of_url",
                        "content_hash", "fingerprint", "source_fingerprint",
                        "run_id", "item_id", "source_domain", "decision"):
                self.assertNotIn(
                    ten, tran,
                    f"{col}.{ten} là ĐỊNH DANH — cắt nó tạo ra một giá trị "
                    f"KHÁC, không phải một giá trị ngắn hơn")

    def test_url_qua_dai_di_qua_nguyen_ven(self):
        """Để Appwrite trả 400 thật to. Hỏng to hơn hỏng âm thầm."""
        dai = "https://vd.test/" + "a" * 4000
        data = cat_theo_tran({"chapter_url": dai}, _TRAN_VAN_BAN[COL_ITEMS])
        self.assertEqual(data["chapter_url"], dai)


class DauVanTayJsonTest(unittest.TestCase):
    """JSON bị cắt là JSON HỎNG — tệ hơn hẳn so với không có dấu vân tay."""

    def _profile(self, dau):
        return SiteProfile(domain="vd.test", adaptive_fingerprint_json=dau)

    def test_json_qua_tran_bi_bo_han_chu_khong_bi_cat(self):
        qua_dai = '{"a": "' + "b" * (_TRAN_DAU_VAN_TAY + 100) + '"}'
        data = _profile_to_data(self._profile(qua_dai))
        self.assertEqual(data["adaptive_fingerprint_json"], "",
                         "JSON quá trần phải bị bỏ hẳn, không cắt thành rác")

    def test_json_vua_van_giu_nguyen(self):
        vua = '{"a": "' + "b" * 100 + '"}'
        data = _profile_to_data(self._profile(vua))
        self.assertEqual(data["adaptive_fingerprint_json"], vua)

    def test_ket_qua_bo_di_van_la_gia_tri_hop_le_cua_truong(self):
        """"" chính là giá trị "chưa học được gì" mà mã nguồn vốn đã lường."""
        qua_dai = "x" * (_TRAN_DAU_VAN_TAY + 1)
        data = _profile_to_data(self._profile(qua_dai))
        self.assertIsInstance(data["adaptive_fingerprint_json"], str)


if __name__ == "__main__":
    unittest.main()
