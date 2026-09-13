# -*- coding: utf-8 -*-
"""NỀN MÓNG PROJECT LEADER TỰ CHỦ — V1.0.

Hai mươi khẳng định người dùng nêu ở B10, cộng vài bài kiểm CẤU TRÚC cho
những chính sách mà một đường dây chết sẽ không làm bài kiểm nào đỏ.

VÌ SAO CÓ BÀI KIỂM CẤU TRÚC Ở ĐÂY: đêm V0.9.3 vừa chứng minh cái giá của
việc không có chúng — `isinstance(hd, dict)` biến cả một rào an toàn thành
hàm rỗng, và KHÔNG bài kiểm nào đỏ, vì mọi bài kiểm đều gọi hàm đó bằng một
`dict`. Chính sách quan trọng phải được neo bằng một phép đọc cấu trúc,
không chỉ bằng một lần gọi thuận chiều.
"""

from __future__ import annotations

import time
import unittest
from pathlib import Path

from scripts.control_center.v10.han_muc import (BeQuota, SoTaiNguyen, SucKhoe,
                                                doc_tin_hieu_quota)
from scripts.control_center.v10.phien_leader import (KetCucLeader, PhienLeader,
                                                     TrangThaiPhien,
                                                     kich_hoat)
from scripts.control_center.v10.su_co import (HanhDong, LoaiHong, NganSach,
                                              VongSuCo, chu_ky, phan_loai)
from scripts.control_center.v10.su_kien import (BusSuKien, LoaiSuKien,
                                                SuKienDoi)
from scripts.control_center.v10.vai_tro import (CAO_CAP, Vai, can_review_doc_lap,
                                                chon_model, chon_reviewer,
                                                ho_model)

FABRIC = ("gemini-3.8-flash-high", "gemini-3.8-flash-medium",
          "gemini-3.1-pro-low", "claude-sonnet-4-6", "codex-default")


# ==========================================================================
# 1-5. LEADER GIỮ MỤC TIÊU, ĐIỀU TRA, SỬA, KHÔNG TIẾN TRIỂN, CẠN NGÂN SÁCH
# ==========================================================================

class TestVongSuCo(unittest.TestCase):

    def test_01_worker_hong_KHONG_phai_ket_cuc_hop_le(self):
        """"worker hỏng, nhờ người dùng debug" không nằm trong kết cục."""
        ten = {k.value for k in KetCucLeader}
        self.assertEqual(ten, {
            "DONE", "CANCELLED_BY_OWNER", "WAITING_AUTHORITY",
            "UNRECOVERABLE_AFTER_BOUNDED_INVESTIGATION"})

    def test_02_hong_lan_dau_thi_DIEU_TRA_chu_khong_leo_thang(self):
        v = VongSuCo()
        qd = v.xet("AssertionError: expected 3 got 2", failure_reason="")
        self.assertNotEqual(qd.hanh_dong, HanhDong.LEO_THANG_CHU_SO_HUU)
        self.assertEqual(qd.hanh_dong, HanhDong.SUA_TAI_CHO)

    def test_03_sua_duoc_thi_vong_tiep_tuc(self):
        v = VongSuCo()
        self.assertEqual(v.xet("tests failed").hanh_dong, HanhDong.SUA_TAI_CHO)
        self.assertEqual(v.con_lai()["sua_tai_cho"], 1)

    def test_04_CUNG_chu_ky_lap_lai_thi_dung_thu_mu(self):
        v = VongSuCo()
        cau = "ModuleNotFoundError: no module named 'x'"
        qd = None
        for _ in range(3):
            qd = v.xet(cau)
        self.assertTrue(qd.khong_tien_trien)
        self.assertIn(qd.hanh_dong,
                      (HanhDong.HOI_DONG, HanhDong.LEO_THANG_CHU_SO_HUU))

    def test_05_can_ngan_sach_thi_leo_thang_CO_NGHIA(self):
        v = VongSuCo(NganSach(sua_tai_cho=1, lap_lai_ke_hoach=1,
                              doi_cho_chay=1, hoi_dong=0, lap_chu_ky=99))
        for i in range(4):
            qd = v.xet(f"lỗi khác nhau số {i} ModuleNotFound{i}")
        self.assertEqual(qd.hanh_dong, HanhDong.LEO_THANG_CHU_SO_HUU)
        self.assertIn("cạn", qd.ly_do.lower())

    def test_06_tham_quyen_thi_HOI_NGAY_khong_tu_vuot(self):
        v = VongSuCo()
        qd = v.xet("việc cần production_deploy — requires_decision")
        self.assertEqual(qd.hanh_dong, HanhDong.LEO_THANG_CHU_SO_HUU)
        self.assertEqual(qd.loai, LoaiHong.AUTHORITY_FAILURE)

    def test_07_quota_thi_CHO_chu_khong_mua_them(self):
        v = VongSuCo()
        qd = v.xet("Individual quota reached. Resets in 48h57m19s")
        self.assertEqual(qd.hanh_dong, HanhDong.CHO_QUOTA)
        self.assertIn("KHÔNG mua thêm credit", qd.ly_do)

    def test_08_hong_KHONG_phu_thuoc_cho_thi_sua_MOI_TRUONG(self):
        """Đổi model không cứu được `git rev-parse HEAD` — đã đo thật."""
        v = VongSuCo()
        qd = v.xet("không cấp được cây làm việc: git rev-parse HEAD thất bại")
        self.assertEqual(qd.loai, LoaiHong.ENVIRONMENT_FAILURE)
        self.assertEqual(qd.hanh_dong, HanhDong.SUA_MOI_TRUONG)

    def test_09_phan_loai_dung_nhung_chu_ky_THAT_cua_dem_V093(self):
        cap = [
            ("tool_permission_denied … auto-denied", LoaiHong.PERMISSION_FAILURE),
            ("gate_scope: ghi NGOÀI write_scope", LoaiHong.VERIFICATION_FAILURE),
            ("Individual quota reached", LoaiHong.QUOTA_EXHAUSTED),
            ("fatal: ambiguous argument 'HEAD': unknown revision",
             LoaiHong.ENVIRONMENT_FAILURE),
        ]
        for van, cho in cap:
            with self.subTest(van=van[:30]):
                self.assertEqual(phan_loai(van), cho)

    def test_10_chu_ky_bo_qua_so_va_duong_dan(self):
        a = chu_ky(LoaiHong.TEST_FAILURE, "failed at C:\\a\\b.py line 42 after 3.1s")
        b = chu_ky(LoaiHong.TEST_FAILURE, "failed at C:\\x\\y.py line 99 after 7.9s")
        self.assertEqual(a, b, "hai lần cùng nguyên nhân phải cùng chữ ký")


# ==========================================================================
# 7-10. CHÍNH SÁCH REVIEW + VAI TRÒ
# ==========================================================================

class TestVaiVaReview(unittest.TestCase):

    def test_11_gemini_sua_MA_thi_BAT_BUOC_review_doc_lap(self):
        r = can_review_doc_lap(loai_viec="implementation",
                               model_da_lam="gemini-3.8-flash-high")
        self.assertTrue(r.bat_buoc)
        self.assertIn("gemini", r.ho_bi_cam)

    def test_12_gemini_viec_DU_LIEU_co_schema_thi_KHONG_bat_buoc(self):
        r = can_review_doc_lap(loai_viec="scrape",
                               model_da_lam="gemini-3.8-flash-high",
                               co_kiem_schema=True)
        self.assertFalse(r.bat_buoc)
        self.assertIn("schema", r.ly_do)

    def test_12b_viec_du_lieu_KHONG_co_schema_thi_khong_duoc_mien(self):
        r = can_review_doc_lap(loai_viec="scrape",
                               model_da_lam="gemini-3.8-flash-high",
                               co_kiem_schema=False)
        self.assertFalse(r.bat_buoc)   # không thuộc diện mã sản phẩm
        self.assertNotIn("schema", r.ly_do)

    def test_13_reviewer_phai_KHAC_HO___khong_tu_cham_minh(self):
        r = chon_reviewer(FABRIC, ho_bi_cam=("gemini",))
        self.assertTrue(r.co)
        self.assertNotEqual(ho_model(r.model_id), "gemini")

    def test_13b_khong_co_reviewer_doc_lap_thi_NOI_RA(self):
        """Không được lặng lẽ để cùng họ chấm — phải báo suy giảm."""
        r = chon_reviewer(("gemini-3.8-flash-high",), ho_bi_cam=("gemini",))
        self.assertFalse(r.co)
        self.assertIn("ĐỘC LẬP", r.ly_do)

    def test_14_ASTRA_khong_duoc_chon_cho_viec_thuong(self):
        """`qd_0001`: bậc ngoại lệ, KHÔNG phải mặc định."""
        self.assertIn("gpt-6-astra", CAO_CAP)
        r = chon_model(Vai.PRINCIPAL_ARCHITECT,
                       tuple(FABRIC) + ("gpt-6-astra",))
        self.assertNotEqual(r.model_id, "gpt-6-astra")
        self.assertTrue(any("ngoại lệ" in x for x in r.da_roi_xuong))

    def test_14b_ASTRA_chi_khi_leo_thang_TUONG_MINH(self):
        r = chon_model(Vai.PRINCIPAL_ARCHITECT,
                       tuple(FABRIC) + ("gpt-6-astra",),
                       cho_phep_cao_cap=True)
        self.assertEqual(r.model_id, "gpt-6-astra")

    def test_15_roi_xuong_khi_model_uu_tien_khong_co(self):
        r = chon_model(Vai.PROJECT_LEADER, FABRIC)
        self.assertEqual(r.model_id, "claude-sonnet-4-6")
        self.assertFalse(r.la_uu_tien_dau)
        self.assertTrue(r.da_roi_xuong)

    def test_16_khong_co_model_nao_thi_KHONG_lay_bua(self):
        r = chon_model(Vai.RAPID_ENGINEER, ("claude-sonnet-4-6",))
        self.assertFalse(r.co)
        self.assertEqual(r.model_id, "")
        self.assertIn("KHÔNG lấy bừa", r.ly_do)


# ==========================================================================
# 11-13. HẠN MỨC
# ==========================================================================

class TestHanMuc(unittest.TestCase):

    def test_17_khong_do_duoc_thi_UNKNOWN_chu_khong_phai_0(self):
        b = BeQuota(ten="ag-01", provider="antigravity")
        self.assertIsNone(b.con_lai)
        self.assertEqual(b.suc_khoe, SucKhoe.UNKNOWN)
        self.assertFalse(b.do_duoc)
        self.assertTrue(b.con_dung_duoc,
                        "UNKNOWN không được biến thành 'đã cạn'")

    def test_18_be_tach_rieng_thi_giu_TACH_RIENG(self):
        so = SoTaiNguyen()
        so.khai(BeQuota(ten="ag-gemini", ho_model=("gemini",)))
        so.khai(BeQuota(ten="ag-claude", ho_model=("claude",)))
        so.ghi_nhan_tin_hieu("ag-claude",
                             "Individual quota reached. Resets in 48h57m19s")
        self.assertEqual(so.lay("ag-claude").suc_khoe, SucKhoe.EXHAUSTED)
        self.assertEqual(so.lay("ag-gemini").suc_khoe, SucKhoe.UNKNOWN,
                         "đo MỘT tài khoản không được áp cho tài khoản khác")

    def test_18b_be_GOP_thi_ghi_dung_la_gop(self):
        so = SoTaiNguyen()
        so.khai(BeQuota(ten="x", ho_model=("claude", "openai")))
        self.assertEqual(len(so.lay("x").ho_model), 2)

    def test_19_doc_duoc_thoi_diem_reset_tu_cau_that(self):
        sk, khi = doc_tin_hieu_quota(
            "Individual quota reached. Please upgrade your subscription to "
            "increase your limits. Resets in 48h57m19s.", bay_gio=1000.0)
        self.assertEqual(sk, SucKhoe.EXHAUSTED)
        self.assertAlmostEqual(khi, 1000.0 + 48 * 3600 + 57 * 60 + 19, places=0)

    def test_19b_khong_co_tin_hieu_thi_khong_bia_gi(self):
        sk, khi = doc_tin_hieu_quota("mọi thứ bình thường")
        self.assertIsNone(sk)
        self.assertIsNone(khi)

    def test_20_be_da_can_thi_khong_duoc_xep_viec(self):
        so = SoTaiNguyen()
        so.khai(BeQuota(ten="can", suc_khoe=SucKhoe.EXHAUSTED))
        so.khai(BeQuota(ten="chua-biet"))
        ten = [b.ten for b in so.dung_duoc()]
        self.assertNotIn("can", ten)
        self.assertIn("chua-biet", ten)


# ==========================================================================
# 14-15, 17. PHIÊN LEADER
# ==========================================================================

class _RuntimeGia:
    """Runtime giả — đủ để kiểm LUẬT, không giả vờ là runtime thật."""

    ten = "gia"

    def __init__(self, *, san_sang=True, noi_lai_duoc=True):
        self._ss = san_sang
        self._nl = noi_lai_duoc
        self.da_tao: list = []
        self.da_noi: list = []

    def san_sang(self):
        return self._ss

    def tao_phien(self, *, session_id, model):
        self.da_tao.append((session_id, model))
        return True

    def noi_lai(self, *, session_id):
        self.da_noi.append(session_id)
        return self._nl

    def hoi(self, *, session_id, cau):
        return "ok"


class TestPhienLeader(unittest.TestCase):

    def test_21_phien_con_song_thi_NOI_LAI(self):
        rt = _RuntimeGia()
        p = PhienLeader(project_id="p", session_ref="abc-123",
                        session_status=TrangThaiPhien.DANG_SONG,
                        last_seen=time.time())
        kq = kich_hoat(p, runtime=rt)
        self.assertTrue(kq.da_noi_lai)
        self.assertFalse(kq.da_dung_moi)
        self.assertEqual(rt.da_noi, ["abc-123"])

    def test_22_phien_HONG_thi_dung_moi_va_NAP_LAI_boi_canh(self):
        rt = _RuntimeGia(noi_lai_duoc=False)
        p = PhienLeader(project_id="p", session_ref="cu",
                        session_status=TrangThaiPhien.DANG_SONG,
                        last_seen=time.time())
        kq = kich_hoat(p, runtime=rt)
        self.assertTrue(kq.da_dung_moi)
        self.assertTrue(kq.can_nap_boi_canh)
        self.assertNotEqual(p.session_ref, "cu")

    def test_22b_khong_co_phien_thi_dung_moi(self):
        rt = _RuntimeGia()
        kq = kich_hoat(PhienLeader(project_id="p"), runtime=rt)
        self.assertTrue(kq.da_dung_moi)
        self.assertTrue(kq.can_nap_boi_canh)

    def test_23_phien_NGUOI_qua_nguong_thi_KHONG_noi_lai(self):
        rt = _RuntimeGia()
        p = PhienLeader(project_id="p", session_ref="cu",
                        session_status=TrangThaiPhien.DANG_SONG,
                        last_seen=time.time() - 99 * 3600)
        kq = kich_hoat(p, runtime=rt)
        self.assertFalse(kq.da_noi_lai)
        self.assertTrue(kq.da_dung_moi)

    def test_24_phien_qua_nang_thi_XOAY(self):
        rt = _RuntimeGia()
        p = PhienLeader(project_id="p", session_ref="cu", so_luot=500,
                        session_status=TrangThaiPhien.DANG_SONG,
                        last_seen=time.time())
        kq = kich_hoat(p, runtime=rt)
        self.assertTrue(kq.da_xoay)
        self.assertEqual(p.so_luot, 0)

    def test_25_KHONG_co_runtime_thi_UNVERIFIED_chu_khong_gia_vo(self):
        kq = kich_hoat(PhienLeader(project_id="p"), runtime=None)
        self.assertFalse(kq.da_noi_lai)
        self.assertEqual(kq.phien.session_status, TrangThaiPhien.UNVERIFIED)
        self.assertIn("KHÔNG báo là đã nối", kq.ly_do)

    def test_26_phien_ben_qua_khoi_dong_lai(self):
        p = PhienLeader(project_id="p", session_ref="s1", so_luot=7,
                        session_status=TrangThaiPhien.DANG_SONG,
                        last_seen=time.time(), checkpoint_ref="dd-9")
        lai = PhienLeader.from_dict(p.to_dict())
        self.assertEqual(lai.session_ref, "s1")
        self.assertEqual(lai.so_luot, 7)
        self.assertEqual(lai.checkpoint_ref, "dd-9")
        self.assertEqual(lai.session_status, TrangThaiPhien.DANG_SONG)


# ==========================================================================
# 16. SỰ KIỆN ĐỘI
# ==========================================================================

class TestBusSuKien(unittest.TestCase):

    def test_27_su_kien_PHAI_co_nguon_goc(self):
        for thieu in ({"project_id": ""}, {"vai": ""}):
            with self.subTest(thieu=thieu):
                d = {"loai": LoaiSuKien.DECISION, "project_id": "p",
                     "vai": "LEADER"}
                d.update(thieu)
                with self.assertRaises(ValueError):
                    SuKienDoi(**d)

    def test_28_giu_duoc_du_an_va_execution(self):
        bus = BusSuKien()
        bus.phat(SuKienDoi(LoaiSuKien.TASK_RESULT, "p", "AG02",
                           "xong", execution_id="e1", task_id="t1"))
        got = bus.doc(project_id="p", execution_id="e1")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].task_id, "t1")

    def test_29_than_su_kien_CO_TRAN(self):
        sk = SuKienDoi(LoaiSuKien.EVIDENCE, "p", "X", "a" * 99999)
        self.assertLessEqual(len(sk.than), 4100)
        self.assertTrue(sk.than.endswith("(cắt)"))

    def test_30_du_loai_su_kien_nen_mong(self):
        ten = {x.value for x in LoaiSuKien}
        for c in ("PROPOSAL", "CHALLENGE", "EVIDENCE", "DECISION",
                  "TASK_REQUEST", "TASK_RESULT", "INCIDENT", "REPAIR",
                  "REVIEW", "BLOCKER", "ESCALATION"):
            self.assertIn(c, ten)

    def test_31_bus_hong_KHONG_lam_chet_duong_thuc_thi(self):
        class SoHong:
            def ghi_su_kien(self, *a, **k):
                raise RuntimeError("sổ nghẽn")
        bus = BusSuKien(SoHong())
        bus.su_co("p", "LEADER", "có chuyện")      # không được ném
        self.assertEqual(len(bus.doc(project_id="p")), 1)


# ==========================================================================
# 18-20. RANH GIỚI THẨM QUYỀN — bài kiểm CẤU TRÚC
# ==========================================================================

class TestRanhGioi(unittest.TestCase):
    """Chính sách quan trọng phải neo bằng phép đọc cấu trúc.

    V0.9.3 vừa trả giá: `isinstance(hd, dict)` biến một rào an toàn thành
    hàm rỗng mà KHÔNG bài kiểm nào đỏ, vì mọi bài kiểm đều gọi nó thuận
    chiều bằng `dict`.
    """

    def _nguon(self):
        goc = Path(__file__).resolve().parents[2] / "scripts" / "control_center" / "v10"
        return {p.name: p.read_text(encoding="utf-8") for p in goc.glob("*.py")}

    def test_32_V10_KHONG_mo_duong_shell_khong_gioi_han(self):
        for ten, van in self._nguon().items():
            with self.subTest(tep=ten):
                for cam in ("subprocess.", "os.system", "shell=True",
                            "--dangerously-skip-permissions",
                            "--dangerously-bypass", "bypassPermissions"):
                    self.assertNotIn(cam, van,
                                     f"{ten} mở một đường tác động trực tiếp")

    def test_33_V10_KHONG_tu_ghi_vao_dia_hay_kho(self):
        """Kiểm bằng IMPORT và lời gọi, không bằng chuỗi trong văn xuôi.

        Bản đầu của bài kiểm này cấm chuỗi `"git "` ở bất kỳ đâu, nên nó đỏ
        vì một câu GIẢI THÍCH nhắc `git rev-parse`. Cấm chữ trong chú thích
        không đo được gì; cấm khả năng thì có.
        """
        import ast
        goc = (Path(__file__).resolve().parents[2] / "scripts"
               / "control_center" / "v10")
        cam_import = {"subprocess", "shutil", "os", "socket", "requests"}
        for p in sorted(goc.glob("*.py")):
            with self.subTest(tep=p.name):
                cay = ast.parse(p.read_text(encoding="utf-8"))
                for n in ast.walk(cay):
                    if isinstance(n, ast.Import):
                        for a in n.names:
                            self.assertNotIn(a.name.split(".")[0], cam_import,
                                             f"{p.name} import {a.name}")
                    elif isinstance(n, ast.ImportFrom):
                        self.assertNotIn((n.module or "").split(".")[0],
                                         cam_import,
                                         f"{p.name} import từ {n.module}")
                    elif isinstance(n, ast.Call):
                        ten = getattr(n.func, "id", "") or \
                            getattr(n.func, "attr", "")
                        self.assertNotIn(
                            ten, {"open", "write_text", "rmtree", "mkdir",
                                  "system", "Popen", "run"},
                            f"{p.name} gọi {ten}() — tác động phải đi qua "
                            f"Router, không qua tầng này")

    def test_34_luat_qd_0001_KHONG_bi_gan_chet_thanh_mac_dinh(self):
        van = self._nguon()["vai_tro.py"]
        self.assertIn("cho_phep_cao_cap: bool = False", van,
                      "bậc ngoại lệ phải TẮT mặc định")

    def test_35_V10_DA_DUOC_CAM_VAO_engine___va_cam_AN_TOAN(self):
        """Bài kiểm này TRƯỚC ĐÂY đòi điều NGƯỢC LẠI, và nó đã đúng lúc đó.

        Ở bản nền móng, `v10` là thư viện thuần và bất biến là "không module
        V0.9.x nào import nó" — để nền móng còn tháo ra được. Chủ sở hữu xem
        xong đã nói thẳng điều còn thiếu: *"The v1.0 incident loop is tested
        but not wired."* Nên bất biến đổi, và đổi có chủ đích.

        Bất biến MỚI gồm hai nửa, và nửa thứ hai mới là nửa khó:

        1. `engine` THẬT SỰ gọi tầng sự cố V1.0;
        2. nó import TRONG HÀM và có đường lùi — một `v10` hỏng không được
           làm chết cả Control Center, và càng không được làm chết một lượt
           chạy đang bay.
        """
        goc = (Path(__file__).resolve().parents[2] / "scripts"
               / "control_center" / "engine.py")
        van = goc.read_text(encoding="utf-8")
        self.assertIn("from scripts.control_center.v10.su_co_ben import SoSuCo",
                      van, "engine chưa dùng tầng sự cố V1.0")
        i = van.index("def _dieu_phoi_su_co")
        than = van[i:i + 5000]
        # Import NẰM TRONG hàm, không ở đầu module.
        self.assertIn("from scripts.control_center.v10.su_co import HanhDong",
                      than)
        # Và có đường lùi về nguyên liệu cũ khi tầng đó không dùng được.
        j = than.index("except Exception")
        self.assertIn("_thu_lai_neu_dang", than[j:j + 400],
                      "v10 hỏng phải lùi về nguyên liệu cũ, không làm chết "
                      "lượt chạy")

    def test_36_chinh_sach_phuc_hoi_co_DUNG_MOT_chu(self):
        """`_thu_lai_neu_dang` tụt xuống thành NGUYÊN LIỆU.

        Chỗ hỏng thật phải gọi bộ điều phối sự cố, không gọi thẳng nguyên
        liệu — hai chủ sở hữu chính sách là hai ngân sách đếm song song cho
        cùng một việc.
        """
        goc = (Path(__file__).resolve().parents[2] / "scripts"
               / "control_center" / "engine.py")
        van = goc.read_text(encoding="utf-8")
        # Chỗ gọi ở đường hỏng THẬT
        i = van.index("if moi in (TaskState.FAILED, TaskState.NEEDS_EVIDENCE)")
        khoi = van[i:i + 700]
        self.assertIn("self._dieu_phoi_su_co(", khoi)
        self.assertNotIn("self._thu_lai_neu_dang(", khoi,
                         "đường hỏng thật không được gọi thẳng nguyên liệu")
        # `_thu_lai_neu_dang` chỉ được gọi TỪ bộ điều phối (và từ đường lùi).
        cho_goi = [d for d in van.splitlines()
                   if "self._thu_lai_neu_dang(" in d]
        self.assertTrue(cho_goi)
        self.assertLessEqual(len(cho_goi), 2,
                             f"nguyên liệu bị gọi từ quá nhiều nơi: {cho_goi}")


if __name__ == "__main__":
    unittest.main()
