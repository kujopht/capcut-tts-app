# -*- coding: utf-8 -*-
"""ĐIỂM DỪNG của kịch bản R: chỉ được tắt máy GIỮA LÚC SỬA.

Bài kiểm này bảo vệ một thứ rất dễ tự lừa mình: một bài "khởi động lại giữa
lúc sửa" mà thật ra tắt máy SAU khi việc sửa đã xong sẽ XANH mà không chứng
minh được gì — nó không cho thấy việc sửa RESUME được, không cho thấy khoá
đang giữ được đối soát, không cho thấy một Leader mới đọc nổi một trạng thái
dang dở. Đó đúng là kiểu "xanh vì lý do sai" mà cả đợt này đã gặp vài lần.

Nên `diem_dung_sua()` là hàm THUẦN, và nó phải TỪ CHỐI mọi hình dạng chưa
đúng khoảnh khắc.
"""

from __future__ import annotations

import unittest

from scripts.control_center_v09_real_acceptance import diem_dung_sua


class _Ban:
    def __init__(self, pb: int, hieu_luc: bool = False):
        self.phien_ban = pb
        self.dang_hieu_luc = hieu_luc


def _buoc(ma: str, pb: int, state: str):
    # TÊN CỘT THẬT là `phien_ban`. Bản đầu của bài kiểm này dùng
    # `plan_version` — một khoá KHÔNG TỒN TẠI — nên nó xanh với dữ liệu giả
    # trong khi hàm thật không bao giờ tìm thấy bước nào, và lần chạy R đầu
    # tiên VÔ HIỆU. Bài kiểm dùng đúng hình dạng hàng của `SoThucThi.buoc()`.
    return {"buoc_id": ma, "phien_ban": pb, "state": state}


TRUOT = {"kind": "EXEC_VERIFIED", "detail": "KHONG_DAT: 1/1 tiêu chí ..."}
SUA = {"kind": "PLAN_REVISED", "detail": "v1 -> v2: ..."}


class TestDiemDungSua(unittest.TestCase):

    def test_01_chua_truot_thi_KHONG_duoc_tat(self):
        ok, vs = diem_dung_sua([_Ban(1)], [_buoc("a", 1, "DANG_CHAY")], [])
        self.assertFalse(ok)
        self.assertIn("TRƯỢT", vs)

    def test_02_truot_nhung_chua_co_v2_thi_KHONG_duoc_tat(self):
        ok, vs = diem_dung_sua([_Ban(1)], [_buoc("a", 1, "XONG")], [TRUOT])
        self.assertFalse(ok)
        self.assertIn("PLAN_REVISED", vs)

    def test_03_co_PLAN_REVISED_nhung_v2_chua_ben_thi_KHONG_duoc_tat(self):
        ok, vs = diem_dung_sua([_Ban(1)], [_buoc("a", 1, "XONG")],
                               [TRUOT, SUA])
        self.assertFalse(ok)
        self.assertIn("chưa bền", vs)

    def test_04_v2_chua_co_buoc_nao_thi_KHONG_duoc_tat(self):
        ok, vs = diem_dung_sua([_Ban(1), _Ban(2, True)],
                               [_buoc("a", 1, "XONG")], [TRUOT, SUA])
        self.assertFalse(ok)
        self.assertIn("chưa có bước nào", vs)

    def test_05_MOI_buoc_v2_da_xong_thi_VO_HIEU_khong_phai_DAT(self):
        """Đây là cái bẫy: việc sửa xong trước khi ta kịp tắt máy."""
        ok, vs = diem_dung_sua(
            [_Ban(1), _Ban(2, True)],
            [_buoc("a", 1, "XONG"), _buoc("a", 2, "XONG"),
             _buoc("sua1_1", 2, "XONG")],
            [TRUOT, SUA])
        self.assertFalse(ok, "tắt máy SAU khi sửa xong lại được coi là hợp lệ")
        self.assertIn("đã xong", vs)

    def test_06_con_mot_buoc_v2_do_dang_thi_DUNG_khoanh_khac(self):
        ok, vs = diem_dung_sua(
            [_Ban(1), _Ban(2, True)],
            [_buoc("a", 1, "XONG"), _buoc("a", 2, "XONG"),
             _buoc("sua1_1", 2, "DANG_CHAY")],
            [TRUOT, SUA])
        self.assertTrue(ok, vs)
        self.assertIn("sua1_1", vs)

    def test_07_buoc_CHUA_CHAY_cung_la_do_dang(self):
        ok, _ = diem_dung_sua(
            [_Ban(1), _Ban(2, True)],
            [_buoc("sua1_1", 2, "CHUA_CHAY")], [TRUOT, SUA])
        self.assertTrue(ok)

    def test_08_buoc_HONG_KHONG_phai_do_dang(self):
        """`HONG`/`BO_QUA` là trạng thái CUỐI — không còn gì đang chạy."""
        for st in ("HONG", "BO_QUA"):
            with self.subTest(state=st):
                ok, _ = diem_dung_sua(
                    [_Ban(1), _Ban(2, True)],
                    [_buoc("sua1_1", 2, st)], [TRUOT, SUA])
                self.assertFalse(ok)

    def test_09_chi_xet_buoc_cua_ban_MOI_NHAT(self):
        """Một bước v1 còn dở KHÔNG biến v3 thành 'đang sửa'."""
        ok, vs = diem_dung_sua(
            [_Ban(1), _Ban(2), _Ban(3, True)],
            [_buoc("a", 1, "DANG_CHAY"), _buoc("a", 3, "XONG")],
            [TRUOT, SUA])
        self.assertFalse(ok, vs)

    def test_10_khong_co_gi_thi_KHONG_duoc_tat(self):
        ok, _ = diem_dung_sua([], [], [])
        self.assertFalse(ok)


class TestHinhDangHangThat(unittest.TestCase):
    """Bài kiểm phải dùng ĐÚNG hình dạng hàng mà sổ thật trả về.

    Lần chạy R đầu tiên VÔ HIỆU vì `diem_dung_sua` đọc khoá `plan_version`
    trong khi cột thật tên `phien_ban`; bài kiểm lúc đó cũng dựng dữ liệu giả
    bằng khoá sai nên nó XANH. Hai cái sai khớp nhau thì không ai bắt được —
    nên bài kiểm này neo vào chính `SoThucThi.buoc()`.
    """

    def test_16_hang_that_co_khoa_phien_ban(self):
        import inspect
        from scripts.control_center.execution.so import SoThucThi
        src = inspect.getsource(SoThucThi.buoc)
        self.assertIn("phien_ban", src)
        self.assertNotIn("plan_version", src)

    def test_17_doc_duoc_hang_that_tu_so_that(self):
        """Dựng một sổ THẬT, ghi một bước, rồi cho qua chính hàm điểm dừng."""
        import shutil
        import tempfile
        from pathlib import Path
        from scripts.control_center.execution.so import SoThucThi
        from scripts.control_center.store import ControlStore

        d = Path(tempfile.mkdtemp(prefix="hang-that-"))
        try:
            so = SoThucThi(ControlStore(d / "control.db"))
            hang = {"buoc_id": "b", "phien_ban": 2, "state": "DANG_CHAY"}
            ok, vs = diem_dung_sua([_Ban(1), _Ban(2, True)], [hang],
                                   [TRUOT, SUA])
            self.assertTrue(ok, f"không đọc nổi hàng thật: {vs}")
            so.store.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestDanhTinhTheoLanChay(unittest.TestCase):
    """Hai lần nghiệm thu ĐỘC LẬP không được đụng danh tính của nhau.

    `execution_id` vốn là uuid nên không đụng. Thứ ĐỤNG là `task_id`: nó suy
    từ `buoc_id` (`engine`: `f"{pid}.{b.buoc_id}"`), và bộ nghiệm thu vốn
    dùng hằng số. Giá phải trả, đo được (`ex_16da77a00864`): một phiên của
    lần chạy TRƯỚC còn mang nhãn `BUSY`/`fanfic.ghi_v1`, lần chạy SAU tạo
    đúng `fanfic.ghi_v1`, và luật 1 `WAIT` vĩnh viễn.
    """

    def test_11_hai_lan_chay_ra_hai_ma_buoc_khac_nhau(self):
        from scripts.control_center_v09_real_acceptance import ma_buoc
        a = ma_buoc("ghi_v1", "lan-A")
        b = ma_buoc("ghi_v1", "lan-B")
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("ghi_v1"))

    def test_12_trong_MOT_lan_chay_thi_on_dinh(self):
        """Mọi bước của cùng một lần chạy dùng chung một không gian tên."""
        from scripts.control_center_v09_real_acceptance import ma_buoc
        self.assertEqual(ma_buoc("ghi_v1", "L"), ma_buoc("ghi_v1", "L"))
        self.assertEqual(ma_buoc("x", "L").rsplit("__", 1)[1],
                         ma_buoc("y", "L").rsplit("__", 1)[1])

    def test_13_mac_dinh_dung_khong_gian_ten_cua_lan_chay_hien_tai(self):
        from scripts.control_center_v09_real_acceptance import (LAN_CHAY,
                                                                ma_buoc)
        self.assertTrue(ma_buoc("ghi_v1").endswith("__" + LAN_CHAY))

    def test_14_KHONG_cho_nao_con_dung_ma_buoc_co_dinh(self):
        """Cấu trúc: một lần thêm bước mới không được quay lại tên hằng."""
        import ast
        import inspect
        from scripts import control_center_v09_real_acceptance as H
        cay = ast.parse(inspect.getsource(H))
        xau = []
        for n in ast.walk(cay):
            if not isinstance(n, ast.Call):
                continue
            if (getattr(n.func, "attr", "") or getattr(n.func, "id", "")) \
                    != "BuocKeHoach":
                continue
            for k in n.keywords:
                if k.arg != "buoc_id":
                    continue
                if isinstance(k.value, ast.Constant):
                    xau.append(f"dòng {k.value.lineno}: {k.value.value!r}")
        self.assertEqual(xau, [],
                         "bước dùng `buoc_id` HẰNG — lần chạy sau sẽ đụng "
                         "danh tính lần trước: " + ", ".join(xau))

    def test_15_khoi_dong_lai_KHONG_sinh_danh_tinh_moi(self):
        """`kb_R` đọc lại kế hoạch đã BỀN, không dựng kế hoạch mới.

        Nếu nó gọi `ma_buoc()` lần nữa sau khi mở lại, danh tính sẽ đổi và
        "cùng một execution" thành một lời nói dối. Kiểm bằng cấu trúc: sau
        `cc.shutdown()` trong `kb_R` không được có lời gọi `ma_buoc`.
        """
        import inspect
        from scripts.control_center_v09_real_acceptance import kb_R
        src = inspect.getsource(kb_R)
        sau = src.split("cc.shutdown()", 1)
        self.assertEqual(len(sau), 2, "kb_R không còn tắt máy?")
        self.assertNotIn("ma_buoc(", sau[1],
                         "kb_R sinh danh tính MỚI sau khi khởi động lại")


if __name__ == "__main__":
    unittest.main()
