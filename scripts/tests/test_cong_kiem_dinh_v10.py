# -*- coding: utf-8 -*-
"""CỔNG KIỂM ĐỊNH: `DONE` phải có BẰNG CHỨNG KHÁCH QUAN — V1.0.

KHUYẾT TẬT ĐO ĐƯỢC (RouterDogfood02, 2026-09-13): một việc có tiêu chí "viết
test và verify" đạt `DONE`, mà bộ kiểm của chính dự án **chưa từng chạy lần
nào**. Cổng `tests` của V4 xanh với dòng "0 lệnh test xanh" — vì không ai đưa
cho nó lệnh nào. Khi cuối cùng có người chạy bộ kiểm đó, nó đỏ 3/5.

Hai nửa của bản vá, và tệp này khoá cả hai:

1. **Khám phá** phép kiểm từ BẰNG CHỨNG CÓ THẬT trong kho — và chỉ từ đó.
2. **Không có phép kiểm nào = THIẾU BẰNG CHỨNG**, không phải `DONE`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.control_center import kiem_du_an as KDA
from scripts.control_center.execution.trang_thai import (TrangThaiThucThi as TT,
                                                         co_the_chuyen)
from scripts.control_center.model import TaskState


class _Kho(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kiem-da-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ghi(self, ten: str, noi_dung: str):
        p = self.tmp / ten
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(noi_dung, encoding="utf-8")
        return p


# ==========================================================================
# 1. KHÁM PHÁ — chỉ từ thứ dự án TỰ KHAI
# ==========================================================================

class TestKhamPha(_Kho):

    def test_01_kho_TRONG_thi_KHONG_bia_lenh_nao(self):
        kh = KDA.kham_pha(self.tmp)
        self.assertFalse(kh.co)
        self.assertTrue(any("KHÔNG tìm được" in x for x in kh.ghi_chu))

    def test_02_doc_scripts_cua_package_json(self):
        self._ghi("package.json", json.dumps(
            {"scripts": {"test": "jest", "build": "tsc -p ."}}))
        kh = KDA.kham_pha(self.tmp)
        self.assertTrue(kh.co)
        khoa = {l.argv[-1] for l in kh.lenh}
        self.assertIn("test", khoa)
        self.assertIn("build", khoa)
        for l in kh.lenh:
            self.assertEqual(l.nguon, KDA.NguonKiem.PACKAGE_JSON)
            self.assertTrue(l.trich, "phải nêu bằng chứng nguyên văn")

    def test_03_KHONG_bia_npm_test_khi_package_json_khong_khai(self):
        """Đây là ranh giới quan trọng nhất của khám phá."""
        self._ghi("package.json", json.dumps({"name": "x", "version": "1.0.0"}))
        kh = KDA.kham_pha(self.tmp)
        self.assertFalse(kh.co)
        self.assertTrue(any("không khai script kiểm nào" in x
                            for x in kh.ghi_chu))

    def test_04_nhan_ra_cau_hinh_pytest(self):
        self._ghi("pyproject.toml", "[tool.pytest.ini_options]\naddopts = '-q'\n")
        kh = KDA.kham_pha(self.tmp)
        self.assertTrue(kh.co)
        self.assertTrue(any(l.nguon is KDA.NguonKiem.PYTEST for l in kh.lenh))

    def test_05_nhan_ra_target_Makefile(self):
        if not shutil.which("make"):
            self.skipTest("máy này không có `make`")
        self._ghi("Makefile", "test:\n\techo hi\n\ndeploy:\n\techo no\n")
        kh = KDA.kham_pha(self.tmp)
        ten = {l.argv[-1] for l in kh.lenh}
        self.assertIn("test", ten)
        self.assertNotIn("deploy", ten, "`deploy` KHÔNG phải một phép kiểm")

    def test_06_TU_CHOI_script_cham_danh_sach_cam(self):
        """`scripts.test` mà chạy deploy thì bị từ chối CẢ DÒNG."""
        self._ghi("package.json", json.dumps(
            {"scripts": {"test": "npm run deploy && jest"}}))
        kh = KDA.kham_pha(self.tmp)
        self.assertFalse(kh.co)
        self.assertTrue(any("danh sách cấm" in x for x in kh.ghi_chu))

    def test_07_lenh_KE_HOACH_thang_va_van_bi_loc_an_toan(self):
        kh = KDA.kham_pha(self.tmp, lenh_ke_hoach=[["python", "-m", "unittest"]])
        self.assertTrue(kh.co)
        self.assertEqual(kh.lenh[0].nguon, KDA.NguonKiem.KE_HOACH)
        xau = KDA.kham_pha(self.tmp,
                           lenh_ke_hoach=[["npx", "wrangler", "deploy"]])
        self.assertFalse(xau.co)

    def test_08_khong_trung_lenh(self):
        self._ghi("pytest.ini", "[pytest]\n")
        self._ghi("pyproject.toml", "[tool.pytest.ini_options]\n")
        kh = KDA.kham_pha(self.tmp)
        self.assertEqual(len(kh.lenh), 1)


# ==========================================================================
# 2. CHẠY — và ba kết cục phải phân biệt được
# ==========================================================================

class TestChay(_Kho):

    def test_09_khong_co_phep_kiem_thi_THIEU_BANG_CHUNG(self):
        bc = KDA.xac_minh(self.tmp)
        self.assertTrue(bc.thieu_bang_chung)
        self.assertFalse(bc.dat)
        self.assertIn("THIẾU BẰNG CHỨNG", bc.ly_do)

    def test_10_lenh_xanh_thi_DAT(self):
        goi = []

        def _gia(argv, **kw):
            goi.append(argv)
            return subprocess.CompletedProcess(argv, 0, "ok", "")
        kh = KDA.kham_pha(self.tmp, lenh_ke_hoach=[["python", "--version"]])
        bc = KDA.chay(kh, self.tmp, runner=_gia)
        self.assertTrue(bc.dat)
        self.assertFalse(bc.thieu_bang_chung)
        self.assertEqual(goi, [["python", "--version"]])

    def test_11_lenh_do_thi_KHONG_DAT_va_neu_ro_lenh_nao(self):
        def _gia(argv, **kw):
            return subprocess.CompletedProcess(argv, 1, "", "3 failed")
        kh = KDA.kham_pha(self.tmp, lenh_ke_hoach=[["python", "-m", "pytest"]])
        bc = KDA.chay(kh, self.tmp, runner=_gia)
        self.assertFalse(bc.dat)
        self.assertFalse(bc.thieu_bang_chung)
        self.assertIn("pytest", bc.ly_do)
        self.assertIn("3 failed", bc.ket_qua[0].duoi)

    def test_12_chay_TRONG_worktree_cua_viec(self):
        """Chạy ở gốc kho thì mọi phép kiểm chấm nhầm cây — bài học V0.9."""
        thay = {}

        def _gia(argv, **kw):
            thay["cwd"] = kw.get("cwd")
            return subprocess.CompletedProcess(argv, 0, "", "")
        kh = KDA.kham_pha(self.tmp, lenh_ke_hoach=[["x"]])
        KDA.chay(kh, self.tmp, runner=_gia)
        self.assertEqual(Path(thay["cwd"]), self.tmp)


# ==========================================================================
# 3. MÁY TRẠNG THÁI — không có đường vòng tới DONE
# ==========================================================================

class TestKhongCoDuongVong(unittest.TestCase):

    def test_13_chi_VERIFIED_di_duoc_toi_DONE(self):
        vao = [s for s in TT if co_the_chuyen(s, TT.DONE) and s is not TT.DONE]
        self.assertEqual(vao, [TT.VERIFIED])

    def test_14_THIEU_BANG_CHUNG_khong_co_duong_toi_DONE(self):
        self.assertFalse(co_the_chuyen(TT.NEEDS_EVIDENCE, TT.DONE))
        self.assertFalse(co_the_chuyen(TT.FAILED_VERIFICATION, TT.DONE))

    def test_15_khong_nhay_coc_qua_VERIFYING(self):
        for s in (TT.RUNNING, TT.READY, TT.PLANNED):
            self.assertFalse(co_the_chuyen(s, TT.VERIFIED), s)

    def test_16_TASK_needs_evidence_khong_di_thang_DONE(self):
        from scripts.control_center.model import co_the_chuyen as tk_chuyen
        self.assertFalse(tk_chuyen(TaskState.NEEDS_EVIDENCE, TaskState.DONE))
        self.assertTrue(tk_chuyen(TaskState.NEEDS_EVIDENCE, TaskState.QUEUED))

    def test_17_NEEDS_EVIDENCE_khong_phai_terminal(self):
        """Nó là một lời mời đi lấy bằng chứng, không phải một kết luận."""
        self.assertFalse(TaskState.NEEDS_EVIDENCE.terminal)
        self.assertTrue(TaskState.NEEDS_EVIDENCE.thieu_bang_chung)


# ==========================================================================
# 4. CẤU TRÚC — cổng phải NẰM TRÊN đường thật
# ==========================================================================

class TestCauTruc(unittest.TestCase):
    """Một cổng đúng mà không ai gọi thì vô dụng — V0.9.3 đã trả giá."""

    def _engine(self) -> str:
        return (Path(__file__).resolve().parents[2] / "scripts"
                / "control_center" / "engine.py").read_text(encoding="utf-8")

    def test_18_cong_duoc_goi_TRUOC_khi_ghi_trang_thai_DONE(self):
        van = self._engine()
        # LỜI GỌI (`self.`), không phải định nghĩa (`def`) — chúng ở hai chỗ
        # khác nhau trong tệp và lấy nhầm thì bài kiểm đo nhầm thứ.
        goi = van.index("self._kiem_du_an_sau_khi_ghi(")
        canh = van.rindex("if moi is TaskState.DONE:", 0, goi)
        self.assertLess(canh, goi,
                        "cổng chỉ chạy cho việc sắp được kết luận DONE")
        self.assertLess(goi - canh, 1500,
                        "lời gọi phải nằm NGAY trong nhánh DONE")
        sau = van.index("doi_trang_thai(task_id, moi", goi)
        self.assertGreater(sau, goi,
                           "phải ghi trạng thái SAU khi cổng đã chạy")

    def test_19_cong_tra_ve_NEEDS_EVIDENCE_khi_khong_co_phep_kiem(self):
        van = self._engine()
        i = van.index("def _kiem_du_an_sau_khi_ghi")
        than = van[i:i + 4000]
        self.assertIn("TaskState.NEEDS_EVIDENCE", than)
        self.assertIn("thieu_bang_chung", than)

    def test_20_loi_o_chinh_cong_KHONG_am_tham_thanh_DONE(self):
        van = self._engine()
        i = van.index("def _kiem_du_an_sau_khi_ghi")
        than = van[i:i + 4000]
        # `except` NGAY SAU lời gọi xác minh — không phải `except` của khối
        # import ở đầu hàm (bản đầu của bài kiểm này bắt nhầm khối đó).
        j = than.index("except Exception", than.index("KDA.xac_minh("))
        self.assertIn("NEEDS_EVIDENCE", than[j:j + 700],
                      "cổng hỏng phải fail-closed, không trả về DONE")


if __name__ == "__main__":
    unittest.main()
