# -*- coding: utf-8 -*-
"""TẠO DỰ ÁN MỚI từ một cái TÊN — V0.9.2.

"+ Dự án mới" cũ chỉ nhận đường dẫn tuyệt đối tới kho ĐÃ CÓ: tốt cho nhận
nuôi, tệ cho bắt đầu từ số không (người dùng phải tự mkdir + `git init` rồi
mới quay lại gõ đường dẫn).

Phần lớn bài kiểm ở đây là những lần PHẢI TỪ CHỐI: ghi đè, vượt thư mục gốc,
tên cấm của Windows. Một bộ tạo dự án dễ dùng mà xoá nhầm thư mục người dùng
thì tệ hơn hẳn cái nó thay thế.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project
from scripts.control_center.tao_du_an import (GOC_MAC_DINH_WIN,
                                              KHOA_THU_MUC_GOC, TaoDuAnLoi,
                                              duong_xem_truoc, kiem_ten, slug,
                                              tao_du_an, thu_muc_goc)


class TestSlug(unittest.TestCase):
    """Tên người gõ -> tên thư mục an toàn."""

    def test_01_bo_dau_tieng_viet(self):
        self.assertEqual(slug("Dự án Điện Ảnh"), "Du-an-Dien-Anh")

    def test_02_gom_ky_tu_la(self):
        self.assertEqual(slug("todo app!! (v2)"), "todo-app-v2")

    def test_03_giu_duoc_ten_thuong(self):
        self.assertEqual(slug("RouterDogfood01"), "RouterDogfood01")

    def test_04_ten_rong_thi_TU_CHOI(self):
        for t in ("", "   ", "!!!", "///"):
            with self.subTest(ten=t):
                with self.assertRaises(TaoDuAnLoi):
                    kiem_ten(t)

    def test_05_ten_CAM_cua_windows_bi_tu_choi(self):
        for t in ("CON", "nul", "com1", "LPT9"):
            with self.subTest(ten=t):
                with self.assertRaises(TaoDuAnLoi):
                    kiem_ten(t)

    def test_06_khong_thoat_ra_ngoai_bang_dau_cham(self):
        """`../` phải bị nghiền thành tên thường, không thành đường lên."""
        for t in ("..", "../../etc", "..\\..\\Windows"):
            with self.subTest(ten=t):
                try:
                    s = kiem_ten(t)
                except TaoDuAnLoi:
                    continue
                self.assertNotIn("..", s)
                self.assertNotIn("/", s)
                self.assertNotIn("\\", s)


class TestTaoDuAn(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tao-da-"))
        self.goc = self.tmp / "RouterProjects"
        self.cc = ControlCenter(root=self.tmp / "data", probe=False,
                                max_parallel=3)

    def tearDown(self):
        try:
            self.cc.shutdown()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    # -- đường HẠNH PHÚC --------------------------------------------------
    def test_07_tao_tu_TEN_va_tu_dung_thu_muc_goc(self):
        kq = tao_du_an(self.cc, "RouterDogfood01", goc=self.goc)
        self.assertTrue(kq.ok, kq.ly_do)
        d = self.goc / "RouterDogfood01"
        self.assertTrue(d.is_dir(), "thư mục gốc chưa được tự tạo")
        self.assertEqual(Path(kq.duong), d)

    def test_08_dung_khung_toi_thieu(self):
        tao_du_an(self.cc, "Khung", goc=self.goc)
        d = self.goc / "Khung"
        self.assertTrue((d / "README.md").is_file())
        self.assertTrue((d / ".gitignore").is_file())
        self.assertTrue((d / "docs").is_dir())

    def test_09_git_da_khoi_tao(self):
        tao_du_an(self.cc, "CoGit", goc=self.goc)
        self.assertTrue((self.goc / "CoGit" / ".git").exists())

    def test_10_gitignore_chan_bi_mat_va_router(self):
        tao_du_an(self.cc, "Ign", goc=self.goc)
        van = (self.goc / "Ign" / ".gitignore").read_text(encoding="utf-8")
        for x in (".env", ".router/", "*.pem"):
            self.assertIn(x, van)

    def test_11_da_dang_ky_vao_so_router(self):
        kq = tao_du_an(self.cc, "DaDangKy", goc=self.goc)
        pj = self.cc.store.project(kq.project_id)
        self.assertIsNotNone(pj)
        self.assertEqual(Path(pj.repo_path), self.goc / "DaDangKy")

    def test_12_vien_nang_dung_duoc_ngay(self):
        kq = tao_du_an(self.cc, "CoNang", goc=self.goc)
        from scripts.control_center import vien_nang_du_an as VN
        muc = VN.dung_muc(self.cc, kq.project_id)
        self.assertIn("danh_tinh", muc)
        self.assertEqual(muc["danh_tinh"]["trang_thai"], "co")

    def test_13_du_an_MOI_thi_so_SACH(self):
        """Dự án mới không được mang theo việc/lần thực thi của dự án khác."""
        kq = tao_du_an(self.cc, "Sach", goc=self.goc)
        self.assertEqual(self.cc.store.tasks(kq.project_id), [])

    # -- những lần PHẢI TỪ CHỐI -------------------------------------------
    def test_14_trung_thu_muc_thi_TU_CHOI_khong_ghi_de(self):
        (self.goc / "Trung").mkdir(parents=True)
        (self.goc / "Trung" / "cua-toi.txt").write_text("dữ liệu", encoding="utf-8")
        kq = tao_du_an(self.cc, "Trung", goc=self.goc)
        self.assertFalse(kq.ok)
        self.assertIn("KHÔNG ghi đè", kq.ly_do)
        self.assertTrue((self.goc / "Trung" / "cua-toi.txt").is_file(),
                        "đã đụng vào dữ liệu có sẵn của người dùng")

    def test_15_ten_co_dau_cham_KHONG_THOAT_duoc_ra_ngoai_goc(self):
        """Bất biến là KHÔNG THOÁT ĐƯỢC, không nhất thiết là bị từ chối.

        `slug()` nghiền `../` thành tên thường nên `"../thoat-ra"` trở thành
        `thoat-ra` NẰM TRONG thư mục gốc — an toàn. `_trong_goc()` là lưới
        thứ hai cho những dạng mà slug không nghiền hết. Điều phải đúng: sau
        lệnh này, không có gì được tạo bên NGOÀI thư mục gốc.
        """
        for t in ("../thoat-ra", "..\\..\\Windows\\Temp\\x", "/etc/passwd"):
            with self.subTest(ten=t):
                kq = tao_du_an(self.cc, t, goc=self.goc)
                if kq.ok:
                    self.assertTrue(
                        Path(kq.duong).resolve().is_relative_to(
                            self.goc.resolve()),
                        f"{t!r} tạo ra {kq.duong} — NGOÀI thư mục gốc")
        self.assertFalse((self.goc.parent / "thoat-ra").exists())
        self.assertFalse((self.goc.parent / "Windows").exists())

    def test_16_ten_rong_thi_TU_CHOI(self):
        kq = tao_du_an(self.cc, "   ", goc=self.goc)
        self.assertFalse(kq.ok)
        self.assertIn("không được để trống", kq.ly_do)

    def test_17_dang_ky_hong_thi_HOAN_TAC_sach(self):
        """Không để lại thư mục mồ côi lẫn bản ghi hỏng."""
        import scripts.control_center.nhan_du_an as ND
        goc_that = ND.nhan_du_an

        def _no(*a, **k):
            raise RuntimeError("sổ nghẽn")
        ND.nhan_du_an = _no
        try:
            kq = tao_du_an(self.cc, "HongDangKy", goc=self.goc)
        finally:
            ND.nhan_du_an = goc_that
        self.assertFalse(kq.ok)
        self.assertFalse((self.goc / "HongDangKy").exists(),
                         "để lại thư mục mồ côi sau khi đăng ký hỏng")
        self.assertIsNone(self.cc.store.project("HongDangKy"))

    def test_18_hoan_tac_KHONG_xoa_thu_muc_goc_co_san(self):
        """Thư mục gốc đã có TRƯỚC thì hoàn tác không được đụng vào."""
        self.goc.mkdir(parents=True)
        (self.goc / "du-an-khac.txt").write_text("x", encoding="utf-8")
        import scripts.control_center.nhan_du_an as ND
        goc_that = ND.nhan_du_an
        ND.nhan_du_an = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
        try:
            tao_du_an(self.cc, "Hong", goc=self.goc)
        finally:
            ND.nhan_du_an = goc_that
        self.assertTrue(self.goc.is_dir(), "đã xoá thư mục gốc của người dùng")
        self.assertTrue((self.goc / "du-an-khac.txt").is_file())


class TestThuMucGoc(unittest.TestCase):
    """Thư mục dự án mặc định là CÀI ĐẶT, và chỉ áp cho dự án TẠO MỚI."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="goc-da-"))
        self.cc = ControlCenter(root=self.tmp / "data", probe=False)

    def tearDown(self):
        try:
            self.cc.shutdown()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_19_mac_dinh_windows(self):
        self.assertEqual(str(thu_muc_goc(None)), GOC_MAC_DINH_WIN)

    def test_20_cai_dat_de_len_mac_dinh(self):
        self.cc.store.luu_cai_dat_ui({KHOA_THU_MUC_GOC: r"D:\Kho"})
        self.assertEqual(str(thu_muc_goc(self.cc.store)), r"D:\Kho")

    def test_21_xem_truoc_duong_dan(self):
        self.cc.store.luu_cai_dat_ui({KHOA_THU_MUC_GOC: str(self.tmp)})
        self.assertEqual(duong_xem_truoc("Todo Dogfood", self.cc.store),
                         str(self.tmp / "Todo-Dogfood"))

    def test_22_xem_truoc_ten_hong_thi_rong(self):
        self.assertEqual(duong_xem_truoc("!!!", self.cc.store), "")

    def test_23_du_an_NHAN_NUOI_khong_bi_doi_cho(self):
        """Dự án nhận nuôi nằm NGUYÊN chỗ của nó, ngoài thư mục mặc định."""
        from scripts.control_center.nhan_du_an import nhan_du_an
        ngoai = self.tmp / "o-cho-khac"
        (ngoai / "docs").mkdir(parents=True)
        kq = nhan_du_an(self.cc, ngoai, ten="ODayThoi")
        self.assertTrue(kq.ok, kq.ly_do)
        pj = self.cc.store.project(kq.project_id)
        self.assertEqual(Path(pj.repo_path), ngoai.resolve())


if __name__ == "__main__":
    unittest.main()
