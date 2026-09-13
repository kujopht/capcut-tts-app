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
        """MỚI NHẤT TRƯỚC — y như `ControlStore.su_kien` (`ORDER BY id DESC`).

        Một bản giả trả ngược thứ tự với bản thật là cách một khuyết tật thứ
        tự sống sót qua mọi bài kiểm: đúng chuyện đã xảy ra ở đây.
        """
        ra = [e for e in self.su if not task_id or e["task_id"] == task_id]
        return list(reversed(ra[-limit:]))


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

    def test_12b_lay_ban_MOI_NHAT_chu_khong_phai_ban_CU_NHAT(self):
        """Khuyết tật ĐO ĐƯỢC trên đường thật, và nó vô hiệu hoá bộ ngắt mạch.

        `store.su_kien` trả `ORDER BY id DESC` — mới nhất TRƯỚC. Bản đầu của
        `hien_tai()` gọi `reversed()` rồi lấy phần tử đầu, tức là lấy bản ghi
        CŨ NHẤT. Hậu quả: sau hai lần hỏng liên tiếp `da_dung` vẫn là
        `{'sua_tai_cho': 1}` — mỗi lần hỏng lại nạp ngân sách của lần ĐẦU.
        Ngân sách không bao giờ cạn, và bộ ngắt mạch không bao giờ nổ.
        """
        so = _SoGia()
        s = SoSuCo(so)
        sc = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
        sc.da_dung = {"sua_tai_cho": 1}
        s.ghi(sc)
        sc.da_dung = {"sua_tai_cho": 2}
        s.ghi(sc)
        sc.da_dung = {"sua_tai_cho": 3}
        s.ghi(sc)
        self.assertEqual(SoSuCo(so).hien_tai("p.t1").da_dung,
                         {"sua_tai_cho": 3},
                         "phải lấy bản ghi MỚI NHẤT")

    def test_12c_ngan_sach_TANG_DAN_qua_cac_lan_hong(self):
        """Bài kiểm hành vi cho cùng khuyết tật — đếm phải tiến."""
        so = _SoGia()
        moc = []
        for i in range(3):
            s = SoSuCo(so)
            sc = s.mo_hoac_lay(project_id="p", task_id="p.t1", muc_tieu="g")
            v = s.vong(sc)
            qd = v.xet("AssertionError: expected 3 got 2")
            s.cap_nhat_tu_vong(sc, v, qd)
            s.ghi(sc)
            moc.append(dict(sc.dem_chu_ky))
        dem = [sum(x.values()) for x in moc]
        self.assertEqual(dem, [1, 2, 3],
                         f"đếm chữ ký phải tiến qua các lần hỏng: {dem}")

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

    def _than(self, ten: str) -> str:
        """Thân của MỘT phương thức, cắt tới `def` kế tiếp.

        Cắt cứng `[i:i+5000]` là một cái bẫy: thêm vài dòng chú thích là
        khẳng định rơi ra ngoài cửa sổ và bài kiểm đỏ vì lý do sai. Đã vấp
        đúng như vậy khi viết tệp này.
        """
        van = self._van()
        i = van.index(f"def {ten}")
        j = van.find("\n    def ", i + 10)
        return van[i:j if j > 0 else len(van)]

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
        than = self._than("_dieu_phoi_su_co")
        for x in ("LoaiSuKien.INCIDENT", "LoaiSuKien.REPAIR",
                  "LoaiSuKien.ESCALATION"):
            self.assertIn(x, than, f"thiếu sự kiện {x}")

    def test_17_chi_LEO_THANG_moi_goi_nguoi(self):
        """Hỏng repo-local thường KHÔNG được đánh thức chủ sở hữu."""
        than = self._than("_dieu_phoi_su_co")
        j = than.index("TaskState.BLOCKED")
        truoc = than[:j]
        self.assertIn("HanhDong.CHO_QUOTA", truoc)
        self.assertIn("XEP_LAI", truoc,
                      "các bậc rẻ phải được thử TRƯỚC khi chặn chờ người")

    def test_18_su_co_duoc_GHI_BEN_truoc_khi_hanh_dong(self):
        than = self._than("_dieu_phoi_su_co")
        ghi = than.index("so.ghi(sc")
        hanh = than.index("if hd in XEP_LAI")
        self.assertLess(ghi, hanh,
                        "phải ghi hồ sơ bền TRƯỚC khi hành động, nếu không "
                        "một lần tắt máy giữa chừng mất sạch ngân sách")

    def test_19_v10_hong_thi_LUI_ve_nguyen_lieu_cu(self):
        than = self._than("_dieu_phoi_su_co")
        j = than.index("except Exception")
        self.assertIn("_thu_lai_neu_dang", than[j:j + 400])

    def test_19b_BANG_CHUNG_cong_kiem_dinh_di_VAO_su_co(self):
        """Khuyết tật ĐO ĐƯỢC ở lượt cắm dây đầu tiên.

        Khi việc hỏng vì CỔNG KIỂM ĐỊNH DỰ ÁN, câu giải thích nằm ở `ly_do`
        của chỗ gọi chứ không nằm trong phong bì worker. Lượt đầu không
        truyền nó vào, nên bộ phân loại mù và ghi `loai=UNKNOWN` cho một lần
        hỏng mà ta biết chính xác nguyên nhân.
        """
        van = self._van()
        i = van.index("self._dieu_phoi_su_co(")
        self.assertIn("bang_chung_them=ly_do", van[i:i + 400])
        than = self._than("_dieu_phoi_su_co")
        j = than.index("manh = [")
        self.assertIn("bang_chung_them", than[j:j + 200],
                      "bằng chứng phải là MẢNH ĐẦU của văn bản đem phân loại")

    def test_19c_ha_tang_kiem_hong_KHONG_bi_goi_la_san_pham_sai(self):
        than = self._than("_kiem_du_an_sau_khi_ghi")
        i = than.index("ha_tang_hong")
        self.assertIn("NEEDS_EVIDENCE", than[i:i + 900],
                      "lệnh kiểm hỏng = KHÔNG CÓ phép đo, không phải sản "
                      "phẩm sai")

    def test_20_KHONG_con_duong_worker_success_thang_DONE(self):
        van = self._van()
        i = van.index("self._kiem_du_an_sau_khi_ghi(")
        canh = van.rindex("if moi is TaskState.DONE:", 0, i)
        self.assertLess(canh, i)


# ==========================================================================
# 7. HAI KHUYẾT TẬT LƯỢT CHẠY THẬT THỨ HAI PHƠI RA
# ==========================================================================
class TestChuKyVaPhanLoaiTuDuongThat(unittest.TestCase):
    """Neo vào ĐÚNG chuỗi mà `kiem_du_an` thật sự sinh ra.

    Cả hai bài dưới đây đều dựng văn bản bằng cách GỌI `kiem_du_an`, không
    bằng cách gõ tay lại một chuỗi *trông giống*. Lượt cắm dây đầu tiên hỏng
    đúng vì bài kiểm tự bịa văn bản: mẫu bắt *"kiểm định không đạt"* còn báo
    cáo thật viết *"phép kiểm của dự án KHÔNG đạt"*, và không bài nào thấy.
    """

    def _bao_cao_do(self):
        from scripts.control_center.kiem_du_an import (LenhKiem, LoaiKiem,
                                                       NguonKiem)
        return LenhKiem, LoaiKiem, NguonKiem

    def test_21_ly_do_KHONG_DAT_that_phan_loai_duoc(self):
        """Văn bản THẬT của một lần kiểm đỏ phải ra `VERIFICATION_FAILURE`."""
        from scripts.control_center import kiem_du_an as KD
        ly_do = (f"{KD.MA_KIEM_DO} phép kiểm của dự án KHÔNG đạt: "
                 r"C:\Program Files\nodejs\npm.CMD run test -> rc=1")
        self.assertIsNot(
            phan_loai(ly_do), LoaiHong.UNKNOWN,
            "đường thật đã ghi loai=UNKNOWN cho một lần hỏng biết rõ nguyên "
            "nhân — vì mẫu bắt văn xuôi mà văn xuôi đã đổi lời")
        self.assertIs(phan_loai(ly_do), LoaiHong.VERIFICATION_FAILURE)

    def test_21b_ma_ha_tang_thang_moi_mau_van_xuoi(self):
        """Mã hạ tầng phải thắng cả chữ 'thiếu bằng chứng' lẫn 'test failed'."""
        from scripts.control_center import kiem_du_an as KD
        van = (f"{KD.MA_HA_TANG_HONG} LỆNH KIỂM tự nó hỏng\n"
               "worker nói: thiếu bằng chứng, 1 test failed")
        self.assertIn(phan_loai(van), HA_TANG_KIEM)

    def test_21c_ma_nam_trong_ly_do_that_cua_kiem_du_an(self):
        """Mã phải THẬT SỰ đi vào `ly_do`, không chỉ tồn tại như hằng số."""
        from scripts.control_center import kiem_du_an as KD
        src = Path(KD.__file__).read_text(encoding="utf-8")
        self.assertIn("{MA_KIEM_DO} phép kiểm", src)
        self.assertIn("{MA_HA_TANG_HONG} LỆNH KIỂM", src)

    def test_22_chu_ky_ON_DINH_khi_van_xuoi_model_doi(self):
        """Cùng một lần hỏng + văn xuôi khác nhau = MỘT chữ ký.

        Đo được trên đường thật (2026-09-13): ba lần hỏng của cùng một lệnh
        kiểm cho ra `6ea35e59ee`, `8c8a80a8da`, `9c2097db80`. `dem_chu_ky`
        không bao giờ vượt 1, nên nhánh "lặp chữ ký" là mã CHẾT và vòng chỉ
        dừng được nhờ ngân sách.
        """
        bc = ("KIEM_DU_AN_KHONG_DAT phép kiểm của dự án KHÔNG đạt: "
              r"C:\Program Files\nodejs\npm.CMD run test -> rc=1")
        v = VongSuCo(NganSach(sua_tai_cho=9, lap_lai_ke_hoach=9, lap_chu_ky=99))
        cks = set()
        for loi_ke in ("Tôi đã thêm nút #clear-completed vào index.html.",
                       "Đã bổ sung handler cho việc xoá các mục hoàn thành.",
                       "Cập nhật app.js: thêm listener và cập nhật DOM."):
            qd = v.xet(f"{bc}\n{loi_ke}", van_ban_chu_ky=bc)
            cks.add(qd.chu_ky)
        self.assertEqual(len(cks), 1, f"ba chữ ký cho một lần hỏng: {cks}")
        self.assertEqual(v.dem_chu_ky[cks.pop()], 3)

    def test_22b_van_xuoi_van_duoc_dung_de_PHAN_LOAI(self):
        """Tách vân tay khỏi phân loại, không phải vứt bớt văn bản đi."""
        v = VongSuCo()
        qd = v.xet("worker: MODULE_NOT_FOUND khi nạp tests",
                   van_ban_chu_ky="rc=1")
        self.assertIn(qd.loai, HA_TANG_KIEM,
                      "phân loại phải đọc văn bản ĐẦY ĐỦ, chỉ vân tay mới "
                      "lấy từ bằng chứng hẹp")

    def test_22c_ngat_mach_no_duoc_khi_van_xuoi_doi(self):
        """Lưới thứ hai — lặp chữ ký — phải thật sự chặn được, không chỉ ngân
        sách."""
        bc = "KIEM_DU_AN_KHONG_DAT phép kiểm của dự án KHÔNG đạt: @ -> rc=1"
        v = VongSuCo(NganSach(sua_tai_cho=99, lap_lai_ke_hoach=99,
                              lap_chu_ky=3, hoi_dong=0))
        # Văn xuôi phải khác nhau về TỪ NGỮ, không chỉ khác con số: `chu_ky`
        # đã quy mọi chữ số về `#`, nên "lần thứ 1/2/3" vẫn băm ra một giá
        # trị và bài kiểm sẽ xanh ngay cả khi dây nối bị tháo.
        cuoi = None
        for loi_ke in ("Tôi đã thêm nút vào index.html.",
                       "Đã bổ sung handler xoá mục hoàn thành.",
                       "Cập nhật listener rồi vẽ lại danh sách."):
            cuoi = v.xet(f"{bc}\n{loi_ke}", van_ban_chu_ky=bc)
        self.assertTrue(cuoi.khong_tien_trien)
        self.assertIs(cuoi.hanh_dong, HanhDong.LEO_THANG_CHU_SO_HUU,
                      "ngân sách còn đầy mà vẫn phải dừng: đây là lưới lặp "
                      "chữ ký, không phải lưới ngân sách")

    def test_22d_engine_truyen_bang_chung_lam_VAN_TAY(self):
        van = ENGINE.read_text(encoding="utf-8")
        i = van.index("qd = v.xet(")
        self.assertIn("van_ban_chu_ky=bang_chung_them", van[i:i + 220],
                      "vân tay phải lấy từ bằng chứng Router tính, không từ "
                      "`pb.summary` do model viết")


# ==========================================================================
# 8. LEO THANG PHẢI TỚI ĐƯỢC TRẠNG THÁI VIỆC
# ==========================================================================
class TestLeoThangToiNoi(unittest.TestCase):
    """Khuyết tật thứ BA của dây nối, cũng do lượt chạy thật phát hiện.

    Sổ ghi đủ `ESCALATION HOI_DONG` và đóng sự cố đúng, mà việc vẫn đọc
    `FAILED`: `FAILED -> BLOCKED` không có trong bảng chuyển, `doi_trang_thai`
    bị từ chối, và lời từ chối rơi vào một `except ... pass`. Người vận hành
    nhìn bảng thấy "hỏng", không thấy "đang chờ người".
    """

    def test_23_FAILED_di_duoc_toi_BLOCKED(self):
        from scripts.control_center.model import _CHUYEN_HOP_LE
        self.assertIn(TaskState.BLOCKED, _CHUYEN_HOP_LE[TaskState.FAILED],
                      "leo thang là nửa còn lại của thử-lại; thiếu nó thì "
                      "`HOI_DONG`/`LEO_THANG` không bao giờ tới trạng thái việc")

    def test_23b_van_KHONG_co_duong_FAILED_thang_DONE(self):
        """Nới một mũi tên không được phép nới cổng nghiệm thu."""
        from scripts.control_center.model import _CHUYEN_HOP_LE
        self.assertNotIn(TaskState.DONE,
                         _CHUYEN_HOP_LE[TaskState.FAILED])
        self.assertNotIn(TaskState.REVIEW,
                         _CHUYEN_HOP_LE[TaskState.FAILED])
        # Ghim CHÍNH XÁC tập đích, không chỉ "có chứa": mục đích của bài này
        # là bắt một lần NỚI RỘNG ngoài ý muốn. Ba mũi tên, mỗi cái là một
        # kết cục của bộ điều phối sự cố, và không cái nào tới nghiệm thu:
        #   QUEUED            xếp lại (SUA_TAI_CHO…)
        #   BLOCKED           leo thang (HOI_DONG / LEO_THANG)
        #   WAITING_RESOURCE  chờ tài nguyên (CHO_QUOTA) — V1.0
        self.assertEqual(_CHUYEN_HOP_LE[TaskState.FAILED],
                         frozenset({TaskState.QUEUED, TaskState.BLOCKED,
                                    TaskState.WAITING_RESOURCE}),
                         "chỉ THÊM mũi tên của một kết cục điều phối có "
                         "thật, không nới rộng")

    def test_23c_KHO_THAT_nhan_FAILED_sang_BLOCKED(self):
        """Bảng chuyển cho phép là một chuyện; SỔ có nhận hay không là chuyện
        khác — chỗ lời từ chối thật sự sinh ra là `store.doi_trang_thai`."""
        from scripts.control_center.model import Task
        from scripts.control_center.store import ControlStore

        goc = Path(tempfile.mkdtemp(prefix="cc-leo-thang-"))
        try:
            st = ControlStore(root=goc)
            st.luu_project(Project(project_id="demo", name="Demo",
                                   repo_path=str(goc)))
            t = Task(task_id="demo.x-1", project_id="demo", title="Việc",
                     objective="mục tiêu", state=TaskState.QUEUED)
            st.luu_task(t)
            st.doi_trang_thai(t.task_id, TaskState.RUNNING, force=True)
            st.doi_trang_thai(t.task_id, TaskState.FAILED)
            st.doi_trang_thai(t.task_id, TaskState.BLOCKED,
                              reason="phục hồi tự chủ đã cạn")
            self.assertIs(st.task(t.task_id).state, TaskState.BLOCKED,
                          "leo thang phải TỚI NƠI, không chỉ được bảng cho "
                          "phép trên giấy")
        finally:
            shutil.rmtree(goc, ignore_errors=True)

    def test_24_leo_thang_hong_thi_SO_PHAI_NOI_RA(self):
        van = ENGINE.read_text(encoding="utf-8")
        i = van.index("TaskState.BLOCKED,\n                reason=(f\"phục hồi")
        sau = van[i:i + 900]
        self.assertNotIn("except Exception:                                     "
                         "# noqa: BLE001\n            pass", sau)
        self.assertIn("ESCALATION_KHONG_DAT", sau,
                      "một `except ... pass` ở đây đã biến leo thang thành "
                      "lệnh rỗng một lần rồi; lần sau sổ phải nói ra")


if __name__ == "__main__":
    unittest.main()
