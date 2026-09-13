# -*- coding: utf-8 -*-
"""VỆ SINH KHUNG NHÌN — lịch sử GIỮ NGUYÊN, ô hiện tại phải đọc được.

Dogfood thật: sau đợt nghiệm thu v0.9, ô chat/trạng thái Fanfic bị lấp bởi
hàng chục `ex_…` của kịch bản test (WAITING_AUTHORITY/BLOCKED), làm việc THẬT
khó đọc.

Ba điều bài kiểm này khoá lại, và điều thứ ba quan trọng nhất:
lịch sử còn nguyên · ô hiện tại sạch · **việc THẬT không bao giờ bị ẩn nhầm**.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.execution import ke_hoach as KH
from scripts.control_center.execution import y_dinh as YD
from scripts.control_center.execution.so import SoThucThi, la_nghiem_thu
from scripts.control_center.execution.trang_thai import TrangThaiThucThi as TT
from scripts.control_center.store import ControlStore


class TestNhanDienNghiemThu(unittest.TestCase):
    """Bộ nhận dạng bám HIỆN VẬT của bài kiểm, không bám từ chung."""

    def _y(self, goal: str):
        return YD.tao_y_dinh(project_id="demo", goal=goal, cau_nguoi_dung=goal)

    def test_01_nhan_ra_hien_vat_nghiem_thu(self):
        for g in ("viết ghi chú vào docs/reports/_v09_ghi_chu_sua.md",
                  "tệp phải chứa V09-ACCEPT-HANDOFF",
                  "docs/reports/_v09_ghi_chu_khoidonglai.md chứa V09-RESTART-OK"):
            self.assertTrue(la_nghiem_thu(self._y(g)), g)

    def test_02_KHONG_bat_nham_viec_that(self):
        """Người dùng hoàn toàn có thể nói "nghiệm thu" trong việc THẬT."""
        for g in ("làm cho tôi bộ nghiệm thu cho module thanh toán",
                  "sửa scraper cho fanfic.world",
                  "viết tài liệu nghiệm thu API"):
            self.assertFalse(la_nghiem_thu(self._y(g)), g)


class TestLocKhungNhin(unittest.TestCase):

    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ve-sinh-"))
        self.so = SoThucThi(ControlStore(self.d / "control.db"))

    def tearDown(self):
        self.so.store.close()
        shutil.rmtree(self.d, ignore_errors=True)

    def _tao(self, goal: str, tt: TT):
        y = YD.tao_y_dinh(project_id="demo", goal=goal, cau_nguoi_dung=goal)
        self.so.luu(y)
        self.so.luu_ke_hoach(KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=(KH.BuocKeHoach(buoc_id="a", tieu_de="a", muc_tieu="a"),)))
        # Đi theo ĐƯỜNG HỢP LỆ của máy trạng thái — `force` không mở được
        # bảng chuyển, và đó là bảng đang làm đúng việc của nó.
        duong = {
            TT.DONE: (TT.PLANNED, TT.READY, TT.RUNNING, TT.VERIFYING, TT.DONE),
            TT.RUNNING: (TT.PLANNED, TT.READY, TT.RUNNING),
            TT.BLOCKED: (TT.PLANNED, TT.READY, TT.BLOCKED),
            TT.WAITING_AUTHORITY: (TT.PLANNED, TT.READY,
                                   TT.WAITING_AUTHORITY),
        }.get(tt, ())
        for b in duong:
            # `BLOCKED`/`WAITING_AUTHORITY` bắt buộc nói VÌ SAO — luật đó có
            # lý do và bài kiểm tôn trọng nó.
            self.so.doi_trang_thai(
                y.execution_id, b,
                ly_do=("cần người xem" if b in (TT.BLOCKED,
                                                TT.WAITING_AUTHORITY) else ""))
        return y

    def test_03_LICH_SU_GIU_NGUYEN(self):
        """Mặc định KHÔNG lọc — lịch sử đọc được đầy đủ."""
        self._tao("viết vào docs/reports/_v09_ghi_chu_sua.md", TT.DONE)
        self._tao("sửa scraper cho fanfic.world", TT.DONE)
        self.assertEqual(len(self.so.danh_sach("demo")), 2)

    def test_04_o_hien_tai_AN_nghiem_thu_da_xong(self):
        self._tao("viết vào docs/reports/_v09_ghi_chu_sua.md", TT.DONE)
        that = self._tao("sửa scraper cho fanfic.world", TT.DONE)
        ds = self.so.danh_sach("demo", gom_nghiem_thu=False)
        self.assertEqual([y.execution_id for y in ds], [that.execution_id])

    def test_05_viec_THAT_khong_bao_gio_bi_an(self):
        """Vế quan trọng nhất: bộ lọc sai hướng này thì tệ hơn vấn đề."""
        ids = []
        for g, t in (("sửa scraper cho fanfic.world", TT.DONE),
                     ("dọn worktree cũ", TT.BLOCKED),
                     ("triển khai web", TT.WAITING_AUTHORITY)):
            ids.append(self._tao(g, t).execution_id)
        ds = self.so.danh_sach("demo", gom_nghiem_thu=False)
        for i in ids:
            self.assertIn(i, [y.execution_id for y in ds])

    def test_06_nghiem_thu_DANG_SONG_van_hien(self):
        """Một lần nghiệm thu đang chạy có thể đang GIỮ tài nguyên — phải thấy."""
        y = self._tao("viết vào docs/reports/_v09_ghi_chu_sua.md", TT.RUNNING)
        ds = self.so.danh_sach("demo", gom_nghiem_thu=False)
        self.assertIn(y.execution_id, [x.execution_id for x in ds])

    def test_07_nghiem_thu_BLOCKED_da_ket_thuc_thi_an(self):
        """`BLOCKED` là trạng thái CHỜ NGƯỜI, không phải kết thúc — vẫn hiện."""
        y = self._tao("viết vào docs/reports/_v09_ghi_chu_sua.md", TT.BLOCKED)
        ds = self.so.danh_sach("demo", gom_nghiem_thu=False)
        self.assertIn(y.execution_id, [x.execution_id for x in ds],
                      "một lần nghiệm thu đang CHỜ NGƯỜI bị giấu mất")

    def test_08_khong_xoa_gi(self):
        y = self._tao("viết vào docs/reports/_v09_ghi_chu_sua.md", TT.DONE)
        self.so.danh_sach("demo", gom_nghiem_thu=False)
        self.assertIsNotNone(self.so.y_dinh(y.execution_id),
                             "bộ lọc đã XOÁ dữ liệu thay vì chỉ ẩn")

    def test_09_cau_trang_thai_khong_bi_lap_boi_nghiem_thu(self):
        from scripts.control_center.execution.dieu_phoi import cau_trang_thai
        for i in range(4):
            self._tao(f"viết vào docs/reports/_v09_ghi_chu_{i}.md", TT.DONE)
        that = self._tao("sửa scraper cho fanfic.world", TT.DONE)
        van = cau_trang_thai(self.so, "demo")
        self.assertIn(that.execution_id, van,
                      "việc THẬT bị đẩy khuất khỏi ô trạng thái")


if __name__ == "__main__":
    unittest.main()
