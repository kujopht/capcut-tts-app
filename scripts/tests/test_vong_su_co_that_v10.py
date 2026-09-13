# -*- coding: utf-8 -*-
"""VÒNG SỰ CỐ ĐƯỢC CẮM VÀO ĐƯỜNG THẬT — nghiệm thu V1.0.

Chủ sở hữu xem bản nền móng và chỉ ra đúng chỗ còn thiếu:

    "The v1.0 incident loop is tested but not wired."

Đúng như vậy: lần sửa Todo thành công chạy bằng `_thu_lai_neu_dang` của
V0.9, không phải `VongSuCo`. Tệp này khoá lại rằng nay nó ĐÃ được cắm, và —
quan trọng hơn — rằng **tắt dây nối đi thì bài kiểm phải đỏ**.

Ba loại bài trong đây, và loại thứ ba mới là loại khó bịa:

* HÀNH VI — bộ quyết định làm đúng việc trên từng lớp hỏng;
* BỀN — trạng thái sống sót qua khởi động lại, ngân sách KHÔNG được nạp lại;
* CẤU TRÚC — chỗ hỏng THẬT trong `engine` có thật sự đi tới đó không.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project, TaskState
from scripts.control_center.v10.su_co import (HA_TANG_KIEM, HanhDong, LoaiHong,
                                              NganSach, VongSuCo, phan_loai)
from scripts.control_center.v10.su_co_ben import KIND, SoSuCo, SuCoBen

ENGINE = (Path(__file__).resolve().parents[2] / "scripts" / "control_center"
          / "engine.py")


# ==========================================================================
# 1. PHÂN LOẠI DẪN TỚI HÀNH ĐỘNG — hạ tầng ≠ sản phẩm
# ==========================================================================

class TestPhanLoaiDanToiHanhDong(unittest.TestCase):

    def test_01_lenh_kiem_hong_KHONG_phai_ma_san_pham_sai(self):
        """Chính chữ ký đã suýt làm tôi kết luận nhầm trong bài nghiệm thu."""
        van = ("Error: Cannot find module "
               "'C:\\...\\tests'\n  code: 'MODULE_NOT_FOUND'")
        self.assertEqual(phan_loai(van),
                         LoaiHong.INVALID_VERIFICATION_COMMAND)
        qd = VongSuCo().xet(van)
        self.assertEqual(qd.hanh_dong, HanhDong.SUA_HA_TANG_KIEM)
        self.assertIn("không phải mã sản phẩm", qd.ly_do)

    def test_02_cac_dau_hieu_ha_tang_khac(self):
        for van, cho in (
                ("npm ERR! missing script: test",
                 LoaiHong.INVALID_VERIFICATION_COMMAND),
                ("'jest' is not recognized as an internal or external command",
                 LoaiHong.INVALID_VERIFICATION_COMMAND),
                ("no test files found", LoaiHong.TEST_HARNESS_FAILURE),
                ("INTERNALERROR> pytest crashed",
                 LoaiHong.TEST_HARNESS_FAILURE)):
            with self.subTest(van=van[:34]):
                self.assertEqual(phan_loai(van), cho)
                self.assertIn(phan_loai(van), HA_TANG_KIEM)

    def test_03_hong_SAN_PHAM_van_di_duong_sua_ma(self):
        """Thu hẹp không được nuốt mất hỏng thật của sản phẩm."""
        qd = VongSuCo().xet("AssertionError: expected /id=[\"']clear-completed/")
        self.assertEqual(qd.loai, LoaiHong.TEST_FAILURE)
        self.assertEqual(qd.hanh_dong, HanhDong.SUA_TAI_CHO)

    def test_04_rc_khac_0_KHONG_tu_dong_la_loi_san_pham(self):
        """Bất biến chủ sở hữu nêu thẳng ở mục 4."""
        v = VongSuCo()
        ha_tang = v.xet("Cannot find module 'tests' MODULE_NOT_FOUND")
        san_pham = v.xet("1 test failed: expected true")
        self.assertNotEqual(ha_tang.hanh_dong, san_pham.hanh_dong)


# ==========================================================================
# 2. NGẮT MẠCH — không thử lại mù
# ==========================================================================

class TestNgatMach(unittest.TestCase):

    def test_05_cung_chu_ky_ba_lan_thi_DOI_CHIEN_LUOC(self):
        v = VongSuCo()
        cau = "AssertionError: expected 3 got 2"
        hd = [v.xet(cau).hanh_dong for _ in range(3)]
        self.assertTrue(v.lich_su[-1].khong_tien_trien)
        self.assertIn(hd[-1], (HanhDong.HOI_DONG,
                               HanhDong.LEO_THANG_CHU_SO_HUU))
        self.assertNotEqual(hd[-1], HanhDong.SUA_TAI_CHO)

    def test_06_can_ngan_sach_thi_KHONG_lap_vo_han(self):
        v = VongSuCo(NganSach(sua_tai_cho=1, lap_lai_ke_hoach=1,
                              doi_cho_chay=1, hoi_dong=0, lap_chu_ky=99))
        hd = [v.xet(f"loi khac nhau {i} ModuleNotFound{i}").hanh_dong
              for i in range(5)]
        self.assertEqual(hd[-1], HanhDong.LEO_THANG_CHU_SO_HUU)
        # Không bao giờ quay lại các bậc rẻ sau khi đã cạn.
        self.assertEqual(hd[-1], hd[-2])

    def test_07_leo_thang_CO_BANG_CHUNG(self):
        v = VongSuCo(NganSach(sua_tai_cho=0, lap_lai_ke_hoach=0,
                              doi_cho_chay=0, hoi_dong=0))
        qd = v.xet("cái gì đó hỏng")
        self.assertEqual(qd.hanh_dong, HanhDong.LEO_THANG_CHU_SO_HUU)
        self.assertTrue(qd.chu_ky)
        self.assertTrue(qd.ly_do)


# ==========================================================================
# 3. BỀN — khởi động lại KHÔNG nạp lại ngân sách
# ==========================================================================

class _SoGia:
    """Sổ tối thiểu: đủ để `SoSuCo` đọc/ghi, không cần cả Control Center."""

    def __init__(self):
        self.su = []

    def ghi_su_kien(self, kind, *, project_id="", task_id="", level="INFO",
                    detail="", meta=None):
        self.su.append({"kind": kind, "project_id": project_id,
                        "task_id": task_id, "level": level, "detail": detail,
                        "meta": meta, "ts": len(self.su)})

    def su_kien(self, *, task_id="", limit=200, **kw):
        ra = [e for e in self.su if not task_id or e["task_id"] == task_id]
        return ra[-limit:]


class TestBen(unittest.TestCase):

    def test_08_su_co_doc_lai_duoc_sau_khoi_dong_lai(self):
        so = _SoGia()
        s1 = SoSuCo(so)
        sc = s1.mo_hoac_lay(project_id="p", task_id="p.t1",
                            muc_tieu="làm web todo")
        sc.da_dung = {"sua_tai_cho": 2}
        sc.dem_chu_ky = {"TEST_FAILURE:abc": 2}
        s1.ghi(sc)

        # "Khởi động lại": một `SoSuCo` MỚI trên cùng sổ.
        lai = SoSuCo(so).hien_tai("p.t1")
        self.assertIsNotNone(lai)
        self.assertEqual(lai.incident_id, sc.incident_id)
        self.assertEqual(lai.muc_tieu, "làm web todo")
        self.assertEqual(lai.da_dung, {"sua_tai_cho": 2})

    def test_09_ngan_sach_KHONG_duoc_nap_lai(self):
        """Đây là lý do tính bền tồn tại, không phải một tiện nghi."""
        so = _SoGia()
        s = SoSuCo(so)
        sc = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
        v = s.vong(sc)
        for _ in range(2):
            qd = v.xet("loi khac nhau " + str(_))
        s.cap_nhat_tu_vong(sc, v, qd)
        s.ghi(sc)

        sc2 = SoSuCo(so).mo_hoac_lay(project_id="p", task_id="p.t1",
                                     muc_tieu="g")
        v2 = SoSuCo(so).vong(sc2)
        self.assertEqual(v2.da_dung, v.da_dung,
                         "khởi động lại mà ngân sách đầy = vòng lặp vô hạn")
        self.assertEqual(v2.con_lai()["sua_tai_cho"], 0)

    def test_10_KHONG_mo_hai_su_co_cho_cung_mot_viec(self):
        so = _SoGia()
        s = SoSuCo(so)
        a = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
        s.ghi(a)
        b = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
        self.assertEqual(a.incident_id, b.incident_id)

    def test_11_su_co_DA_DONG_thi_lan_sau_mo_ho_so_moi(self):
        so = _SoGia()
        s = SoSuCo(so)
        a = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
        s.dong(a, ly_do="xong")
        b = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
        self.assertNotEqual(a.incident_id, b.incident_id)

    def test_12_muc_tieu_GOC_khong_bi_quen(self):
        so = _SoGia()
        s = SoSuCo(so)
        sc = s.mo_hoac_lay(project_id="p", task_id="p.t1",
                           muc_tieu="mục tiêu gốc của người dùng")
        s.ghi(sc)
        self.assertEqual(SoSuCo(so).hien_tai("p.t1").muc_tieu,
                         "mục tiêu gốc của người dùng")

    def test_13_su_co_mang_NGUON_GOC(self):
        so = _SoGia()
        s = SoSuCo(so)
        sc = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g",
                           execution_id="ex_1")
        s.ghi(sc)
        e = [x for x in so.su if x["kind"] == KIND][-1]
        self.assertEqual(e["project_id"], "p")
        self.assertEqual(e["task_id"], "p.t1")
        self.assertEqual(e["meta"]["execution_id"], "ex_1")


# ==========================================================================
# 4. CẤU TRÚC — dây nối có THẬT trên đường hỏng thật
# ==========================================================================

class TestDayNoiThat(unittest.TestCase):

    def _van(self) -> str:
        return ENGINE.read_text(encoding="utf-8")

    def test_14_duong_hong_THAT_di_vao_bo_dieu_phoi_su_co(self):
        van = self._van()
        i = van.index("if moi in (TaskState.FAILED, TaskState.NEEDS_EVIDENCE)")
        khoi = van[i:i + 700]
        self.assertIn("self._dieu_phoi_su_co(", khoi)

    def test_15_NEEDS_EVIDENCE_cung_di_vao_vong_su_co(self):
        """Thiếu bằng chứng cũng là một sự cố phải xử, không phải ngõ cụt."""
        van = self._van()
        i = van.index("if moi in (TaskState.FAILED, TaskState.NEEDS_EVIDENCE)")
        self.assertIn("NEEDS_EVIDENCE", van[i:i + 120])

    def test_16_bo_dieu_phoi_phat_SU_KIEN_co_kieu(self):
        van = self._van()
        i = van.index("def _dieu_phoi_su_co")
        than = van[i:i + 5000]
        for x in ("LoaiSuKien.INCIDENT", "LoaiSuKien.REPAIR",
                  "LoaiSuKien.ESCALATION"):
            self.assertIn(x, than, f"thiếu sự kiện {x}")

    def test_17_chi_LEO_THANG_moi_goi_nguoi(self):
        """Hỏng repo-local thường KHÔNG được đánh thức chủ sở hữu."""
        van = self._van()
        i = van.index("def _dieu_phoi_su_co")
        than = van[i:i + 5000]
        j = than.index("TaskState.BLOCKED")
        truoc = than[:j]
        self.assertIn("HanhDong.CHO_QUOTA", truoc)
        self.assertIn("XEP_LAI", truoc,
                      "các bậc rẻ phải được thử TRƯỚC khi chặn chờ người")

    def test_18_su_co_duoc_GHI_BEN_truoc_khi_hanh_dong(self):
        van = self._van()
        i = van.index("def _dieu_phoi_su_co")
        than = van[i:i + 5000]
        ghi = than.index("so.ghi(sc")
        hanh = than.index("if hd in XEP_LAI")
        self.assertLess(ghi, hanh,
                        "phải ghi hồ sơ bền TRƯỚC khi hành động, nếu không "
                        "một lần tắt máy giữa chừng mất sạch ngân sách")

    def test_19_v10_hong_thi_LUI_ve_nguyen_lieu_cu(self):
        van = self._van()
        i = van.index("def _dieu_phoi_su_co")
        than = van[i:i + 5000]
        j = than.index("except Exception")
        self.assertIn("_thu_lai_neu_dang", than[j:j + 400])

    def test_20_KHONG_con_duong_worker_success_thang_DONE(self):
        van = self._van()
        i = van.index("self._kiem_du_an_sau_khi_ghi(")
        canh = van.rindex("if moi is TaskState.DONE:", 0, i)
        self.assertLess(canh, i)


if __name__ == "__main__":
    unittest.main()
