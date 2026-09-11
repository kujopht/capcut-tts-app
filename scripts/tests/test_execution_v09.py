"""Bài kiểm V0.9 — vòng kín thực thi (ý định, kế hoạch, kiểm định, phục hồi).

TẤT ĐỊNH, KHÔNG MẠNG, KHÔNG TIẾN TRÌNH MODEL NÀO. Việc con được giả bằng ba
hàm (`tao_viec`/`trang_thai_viec`/`dung_viec`) mà `BoDieuPhoi` nhận ở
constructor — đó chính là lý do nó nhận callable thay vì `ControlCenter`.

Mỗi lớp khoá lại MỘT tính chất mà nếu mất đi thì v0.9 mất nghĩa. Thứ tự các
lớp theo đúng thứ tự mục của yêu cầu.
"""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from scripts.control_center.execution import chi_phi as CP
from scripts.control_center.execution import ghi_nho as GN
from scripts.control_center.execution import ke_hoach as KH
from scripts.control_center.execution import ket_qua as KQ
from scripts.control_center.execution import kiem_dinh as KD
from scripts.control_center.execution import lap_ke_hoach as LKH
from scripts.control_center.execution import phuc_hoi as PH
from scripts.control_center.execution import tiep_noi as TN
from scripts.control_center.execution import y_dinh as YD
from scripts.control_center.execution.dieu_phoi import (BoDieuPhoi,
                                                        TrangThaiBuoc,
                                                        cau_ket_thuc,
                                                        cau_trang_thai)
from scripts.control_center.execution.so import SoThucThi, tien_do
from scripts.control_center.execution.trang_thai import (ChuyenTrangThaiLoi,
                                                         KET_THUC,
                                                         TrangThaiThucThi as TT,
                                                         co_the_chuyen,
                                                         kiem_chuyen)
from scripts.control_center.model import LockKind, Project
from scripts.control_center.planner import RulePlanner
from scripts.control_center.store import ControlStore

PID = "demo"


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="cc-v09-"))


def _so() -> SoThucThi:
    return SoThucThi(ControlStore(_tmp() / "control.db"))


def _y(goal: str = "sửa bug ở scripts/control_center/store.py rồi chạy test",
       cau: str = "", **kw) -> YD.YDinhThucThi:
    return YD.tao_y_dinh(project_id=PID, goal=goal, cau_nguoi_dung=cau or goal,
                         **kw)


def _buoc(ma: str, *, ghi: bool = False, phu=(), tai_nguyen=(), kiem=(),
          artifact=()) -> KH.BuocKeHoach:
    return KH.BuocKeHoach(
        buoc_id=ma, tieu_de=ma, muc_tieu=f"làm {ma}",
        phu_thuoc=tuple(phu),
        tai_nguyen=tuple(tai_nguyen),
        che_do_ghi=KH.CheDoGhi.GHI if ghi else KH.CheDoGhi.DOC,
        artifact_mong_doi=tuple(artifact),
        cach_kiem=tuple(kiem))


def _kq(task_id="t1", *, status="ok", **kw) -> KQ.HopDongKetQua:
    d = {"summary": "đã làm xong", "files_changed": (),
         "artifacts": (), "tests_run": {}}
    d.update(kw)
    return KQ.HopDongKetQua(task_id=task_id, status=status, **d)


class ViecGia:
    """Bộ ba hàm giả thay cho Router V4. Đếm mọi lần tạo việc."""

    def __init__(self) -> None:
        self.tao: List[str] = []
        self.trang_thai: Dict[str, str] = {}
        self.da_dung: List[str] = []
        self.da_nha: List[str] = []
        self._n = 0

    def tao_viec(self, y, b, lan, phien_ban=1) -> str:
        self._n += 1
        tid = f"{y.project_id}.{b.buoc_id}-v{phien_ban}#{self._n}"
        self.tao.append(tid)
        self.trang_thai[tid] = "RUNNING"
        return tid

    def xong(self, tid: str, tt: str = "DONE") -> None:
        self.trang_thai[tid] = tt

    def doc(self, tid: str) -> str:
        return self.trang_thai.get(tid, "")

    def dung(self, tid: str, ly_do: str) -> None:
        self.da_dung.append(tid)
        self.trang_thai[tid] = "FAILED"

    def nha(self, pid: str, tid: str) -> int:
        self.da_nha.append(tid)
        return 1


def _bdp(so: SoThucThi, vg: ViecGia, **kw) -> BoDieuPhoi:
    return BoDieuPhoi(so, tao_viec=vg.tao_viec, trang_thai_viec=vg.doc,
                      dung_viec=vg.dung, nha_tai_nguyen=vg.nha, **kw)


# ---------------------------------------------------------------------------
# §5 — may trang thai
# ---------------------------------------------------------------------------

class Test01MayTrangThai(unittest.TestCase):

    def test_RUNNING_DONE_bi_CAM_CUNG(self):
        """Luật quan trọng nhất của §5. Một `force` cũng không mở được."""
        self.assertFalse(co_the_chuyen(TT.RUNNING, TT.DONE))
        with self.assertRaises(ChuyenTrangThaiLoi) as e:
            kiem_chuyen("ex_1", TT.RUNNING, TT.DONE)
        self.assertIn("VERIFYING", str(e.exception))

    def test_moi_duong_toi_DONE_di_qua_VERIFYING(self):
        di_toi_done = [s for s in TT if co_the_chuyen(s, TT.DONE) and s is not TT.DONE]
        self.assertEqual(di_toi_done, [TT.VERIFYING])

    def test_DONE_va_CANCELLED_la_ngo_cut(self):
        for s in (TT.DONE, TT.CANCELLED):
            self.assertFalse(any(co_the_chuyen(s, x) for x in TT if x is not s))

    def test_ba_trang_thai_ket_thuc(self):
        self.assertEqual(KET_THUC, {TT.DONE, TT.FAILED, TT.CANCELLED})

    def test_FAILED_chi_quay_lai_qua_REPLANNING(self):
        self.assertTrue(co_the_chuyen(TT.FAILED, TT.REPLANNING))
        self.assertFalse(co_the_chuyen(TT.FAILED, TT.RUNNING))

    def test_so_CUONG_CHE_bang_chuyen(self):
        so = _so()
        y = _y()
        so.luu(y)
        so.doi_trang_thai(y.execution_id, TT.PLANNED)
        so.doi_trang_thai(y.execution_id, TT.READY)
        so.doi_trang_thai(y.execution_id, TT.RUNNING)
        with self.assertRaises(ChuyenTrangThaiLoi):
            so.doi_trang_thai(y.execution_id, TT.DONE, force=True)


# ---------------------------------------------------------------------------
# §1 — thao luan KHONG phai thuc thi
# ---------------------------------------------------------------------------

class Test02TiepNoi(unittest.TestCase):

    def test_cau_hoi_chien_luoc_KHONG_phai_tiep_noi(self):
        for c in ("theo m Fanfic nên làm gì tiếp?",
                  "kiến trúc Fanfic nên thay đổi thế nào để scale?",
                  "có nên migrate Appwrite/storage architecture không?"):
            self.assertFalse(TN.xet_tiep_noi(c).la_tiep_noi, c)

    def test_cac_cau_XIN_LAM_mo_cua(self):
        for c in ("ok làm đi", "triển khai hướng đó", "fix cái này",
                  "build feature này", "ok triển khai phần repo-local đó đi",
                  "go ahead", "tiến hành đi"):
            self.assertTrue(TN.xet_tiep_noi(c).la_tiep_noi, c)

    def test_HOAN_thang_XIN_LAM(self):
        """"khoan làm đã" chứa "làm đ…" — hoãn phải được kiểm TRƯỚC."""
        for c in ("khoan làm đã", "chưa làm vội", "đừng triển khai",
                  "hold on", "để sau"):
            th = TN.xet_tiep_noi(c)
            self.assertFalse(th.la_tiep_noi, c)
            self.assertTrue(th.bi_hoan, c)

    def test_noi_ve_de_xuat_moi_nhat_chua_dung(self):
        cu = TN.DeXuat(ma="dx1", project_id=PID, message_id=1,
                       tom_tat="tách observer", ts=time.time() - 100)
        moi = TN.DeXuat(ma="dx2", project_id=PID, message_id=3,
                        tom_tat="dọn nợ test", ts=time.time())
        kn = TN.giai_quyet("ok làm đi", [cu, moi])
        self.assertTrue(kn.noi_duoc)
        self.assertEqual(kn.de_xuat.ma, "dx2")
        self.assertIn("dọn nợ test", kn.muc_tieu)

    def test_de_xuat_DA_DUNG_khong_duoc_noi_lai(self):
        d = TN.DeXuat(ma="dx1", project_id=PID, message_id=1, tom_tat="x",
                      execution_id="ex_cu")
        self.assertFalse(TN.giai_quyet("ok làm đi", [d]).noi_duoc)

    def test_de_xuat_QUA_HAN_khong_noi(self):
        d = TN.DeXuat(ma="dx1", project_id=PID, message_id=1, tom_tat="x",
                      ts=time.time() - TN.HAN_NOI_GIAY - 10)
        self.assertFalse(TN.giai_quyet("ok làm đi", [d]).noi_duoc)

    def test_van_ban_KHONG_do_nguoi_dung_go_thi_KHONG_noi(self):
        """Tóm tắt worker / câu commit có chữ "ok làm đi" không khởi động gì."""
        d = TN.DeXuat(ma="dx1", project_id=PID, message_id=1, tom_tat="x")
        self.assertFalse(TN.giai_quyet("ok làm đi", [d], nguon="worker").noi_duoc)

    def test_thu_hep_pham_vi_duoc_ghi_vao_muc_tieu(self):
        d = TN.DeXuat(ma="dx1", project_id=PID, message_id=1,
                      tom_tat="dọn nợ kỹ thuật")
        kn = TN.giai_quyet("ok triển khai phần repo-local đó đi", [d])
        self.assertTrue(kn.noi_duoc)
        self.assertIn("repo-local", kn.muc_tieu.lower())


# ---------------------------------------------------------------------------
# §2/§4 — y dinh + tham quyen
# ---------------------------------------------------------------------------

class Test03YDinhThamQuyen(unittest.TestCase):

    def test_viec_trong_kho_la_REPO_LOCAL_KHONG_can_duyet(self):
        y = _y("sửa scripts/control_center/store.py rồi chạy test")
        self.assertIs(y.tham_quyen, YD.LopThamQuyen.REPO_LOCAL)
        self.assertIs(y.duyet, YD.TrangThaiDuyet.KHONG_CAN)
        self.assertFalse(y.can_tham_quyen_moi)

    def test_deploy_production_la_NGOAI_va_CHO_NGUOI(self):
        y = _y("deploy lên production rồi restart worker")
        self.assertIs(y.tham_quyen, YD.LopThamQuyen.NGOAI)
        self.assertIs(y.duyet, YD.TrangThaiDuyet.CHO_NGUOI)
        self.assertTrue(y.can_tham_quyen_moi)
        self.assertTrue(y.tac_dong_production)

    def test_NGOAI_khong_bao_gio_o_KHONG_CAN_du_dung_constructor_tho(self):
        y = YD.YDinhThucThi(execution_id="ex_x", project_id=PID, goal="g",
                            tham_quyen=YD.LopThamQuyen.NGOAI,
                            duyet=YD.TrangThaiDuyet.KHONG_CAN)
        self.assertIs(y.duyet, YD.TrangThaiDuyet.CHO_NGUOI)

    def test_quet_CA_muc_tieu_LAN_cau_goc(self):
        """Bộ lập kế hoạch diễn đạt lại thành câu vô hại — câu gốc vẫn bị quét."""
        y = YD.tao_y_dinh(project_id=PID, goal="cập nhật cấu hình worker",
                          cau_nguoi_dung="deploy lên production đi")
        self.assertIs(y.tham_quyen, YD.LopThamQuyen.NGOAI)

    def test_khong_luu_dong_suy_nghi(self):
        y = _y("làm việc A <thinking>bí mật nội tâm</thinking> phần còn lại")
        self.assertNotIn("thinking", y.goal.lower())
        self.assertNotIn("bí mật nội tâm", y.goal)

    def test_cau_hoi_tham_quyen_NEU_DICH_DANH_thao_tac(self):
        y = _y("deploy lên production")
        c = YD.cau_hoi_tham_quyen(y)
        self.assertIn("production_deploy", c)
        self.assertIn("WAITING_AUTHORITY", c)
        self.assertIn("ok làm đi", c)

    def test_tieu_chi_rut_tu_cau_nguoi_dung(self):
        y = _y("sửa bug, test phải pass và không được đụng production")
        self.assertTrue(y.tieu_chi_dat)


# ---------------------------------------------------------------------------
# §3/§10/§17 — ke hoach, DAG, phien ban
# ---------------------------------------------------------------------------

class Test04KeHoachDAG(unittest.TestCase):

    def test_chu_trinh_bi_BAT(self):
        with self.assertRaises(KH.KeHoachLoi) as e:
            KH.kiem_dag([_buoc("a", phu=("b",)), _buoc("b", phu=("a",))])
        self.assertIn("CHU TRÌNH", str(e.exception))

    def test_phu_thuoc_la_bi_BAT(self):
        with self.assertRaises(KH.KeHoachLoi):
            KH.kiem_dag([_buoc("a", phu=("khong_co",))])

    def test_cac_lop_KHONG_tuan_tu_hoa_viec_doc_lap(self):
        lop = KH.cac_lop([_buoc("a"), _buoc("b"), _buoc("c", phu=("a", "b"))])
        self.assertEqual(lop, [["a", "b"], ["c"]])

    def test_READ_READ_song_song_duoc(self):
        b = [_buoc("a", tai_nguyen=((LockKind.FILESYSTEM, "docs", "read"),)),
             _buoc("b", tai_nguyen=((LockKind.FILESYSTEM, "docs", "read"),))]
        self.assertEqual(KH.nhom_song_song(b, ["a", "b"]), ["a", "b"])

    def test_READ_WRITE_giao_nhau_thi_KHONG(self):
        b = [_buoc("a", tai_nguyen=((LockKind.FILESYSTEM, "docs", "read"),)),
             _buoc("b", tai_nguyen=((LockKind.FILESYSTEM, "docs", "write"),))]
        self.assertEqual(KH.nhom_song_song(b, ["a", "b"]), ["a"])

    def test_WRITE_WRITE_giao_TIEN_TO_thi_KHONG(self):
        b = [_buoc("a", tai_nguyen=((LockKind.FILESYSTEM, "web", "write"),)),
             _buoc("b", tai_nguyen=((LockKind.FILESYSTEM, "web/admin", "write"),))]
        self.assertEqual(KH.nhom_song_song(b, ["a", "b"]), ["a"])

    def test_WRITE_khac_cay_thi_song_song_duoc(self):
        b = [_buoc("a", tai_nguyen=((LockKind.FILESYSTEM, "web", "write"),)),
             _buoc("b", tai_nguyen=((LockKind.FILESYSTEM, "server", "write"),))]
        self.assertEqual(KH.nhom_song_song(b, ["a", "b"]), ["a", "b"])

    def test_ban_v2_PHAI_noi_vi_sao(self):
        with self.assertRaises(KH.KeHoachLoi):
            KH.KeHoachThucThi(execution_id="ex", phien_ban=2, buoc=(_buoc("a"),))

    def test_ban_moi_GIU_tieu_chi_nghiem_thu(self):
        nt = (KH.TieuChiNghiemThu(mo_ta="test phải pass"),)
        v1 = KH.KeHoachThucThi(execution_id="ex", buoc=(_buoc("a"),),
                               nghiem_thu=nt)
        v2 = v1.ban_moi(buoc=(_buoc("a"), _buoc("b")), ly_do="a hỏng")
        self.assertEqual(v2.nghiem_thu, nt)
        self.assertEqual(v2.phien_ban, 2)

    def test_bo_tieu_chi_nghiem_thu_bi_NEU_RA(self):
        v1 = KH.KeHoachThucThi(
            execution_id="ex", buoc=(_buoc("a"),),
            nghiem_thu=(KH.TieuChiNghiemThu(mo_ta="test phải pass"),))
        v2 = v1.ban_moi(buoc=(_buoc("a"),), ly_do="hạ chuẩn", nghiem_thu=())
        self.assertTrue(any("BỎ tiêu chí" in x for x in KH.so_sanh_ban(v1, v2)))

    def test_ban_cu_KHONG_bi_xoa(self):
        so = _so()
        y = _y()
        so.luu(y)
        v1 = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc("a"),))
        so.luu_ke_hoach(v1)
        so.luu_ke_hoach(v1.ban_moi(buoc=(_buoc("a"), _buoc("b")), ly_do="x"))
        ds = so.cac_ban_ke_hoach(y.execution_id)
        self.assertEqual([p.phien_ban for p in ds], [1, 2])
        self.assertEqual([p.dang_hieu_luc for p in ds], [False, True])


# ---------------------------------------------------------------------------
# §6 — hop dong ket qua + chan DONE gia
# ---------------------------------------------------------------------------

class Test05HopDongKetQua(unittest.TestCase):

    def test_luot_RONG_khong_phai_DONE(self):
        pq = KQ.du_bang_chung(_kq(summary=""))
        self.assertIs(pq.muc, KQ.MucBangChung.CHUA_DU)
        self.assertIn("No output produced", pq.ly_do)

    def test_ma_thoat_0_mot_minh_KHONG_du_cho_buoc_GHI(self):
        b = _buoc("a", ghi=True)
        pq = KQ.du_bang_chung(_kq(summary="xong rồi nhé"), b)
        self.assertIs(pq.muc, KQ.MucBangChung.CHUA_DU)
        self.assertTrue(any("đĩa" in x for x in pq.thieu))

    def test_buoc_GHI_co_tep_doi_thi_DU(self):
        b = _buoc("a", ghi=True)
        pq = KQ.du_bang_chung(_kq(files_changed=("scripts/x.py",)), b)
        self.assertIs(pq.muc, KQ.MucBangChung.DU)

    def test_artifact_thieu_duoc_NEU_DICH_DANH(self):
        b = _buoc("a", ghi=True, artifact=("scripts/moi.py",))
        pq = KQ.du_bang_chung(_kq(files_changed=("scripts/khac.py",)), b)
        self.assertIs(pq.muc, KQ.MucBangChung.CHUA_DU)
        self.assertTrue(any("scripts/moi.py" in x for x in pq.thieu))

    def test_ok_ma_test_hong_la_MAU_THUAN(self):
        pq = KQ.du_bang_chung(_kq(summary="ok",
                                  tests_run={"ran": True, "passed": 3,
                                             "failed": 2}))
        self.assertIs(pq.muc, KQ.MucBangChung.MAU_THUAN)

    def test_status_khac_ok_khong_bi_doi_chung_minh(self):
        self.assertIs(KQ.du_bang_chung(_kq(status="failed", summary="")).muc,
                      KQ.MucBangChung.DU)


# ---------------------------------------------------------------------------
# §7/§8 — kiem dinh
# ---------------------------------------------------------------------------

class Test06KiemDinh(unittest.TestCase):

    def test_buoc_GHI_khong_khai_phep_kiem_thi_THIEU_BANG_CHUNG(self):
        b = _buoc("a", ghi=True)
        tt, _ = KD.kiem_dinh_buoc(b, _kq(files_changed=("x.py",)))
        self.assertIs(tt, KQ.TrangThaiXacMinh.THIEU_BANG_CHUNG)

    def test_buoc_DOC_khong_can_phep_kiem(self):
        tt, _ = KD.kiem_dinh_buoc(_buoc("a"), _kq(summary="đã khảo sát xong"))
        self.assertIs(tt, KQ.TrangThaiXacMinh.DAT)

    def test_khong_co_ket_qua_la_THIEU_BANG_CHUNG(self):
        tt, _ = KD.kiem_dinh_buoc(_buoc("a"), None)
        self.assertIs(tt, KQ.TrangThaiXacMinh.THIEU_BANG_CHUNG)

    def test_moi_gioi_TU_CHOI_duong_dan_ngoai_kho(self):
        mg = KD.MoiGioiKiem(str(_tmp()))
        with self.assertRaises(KD.KiemLoi):
            mg.tep_ton_tai(duong="../../etc/passwd")

    def test_moi_gioi_TU_CHOI_tep_bi_mat(self):
        mg = KD.MoiGioiKiem(str(_tmp()))
        for x in (".env", "server/.env", "khoa.pem"):
            with self.assertRaises(KD.KiemLoi, msg=x):
                mg.chuoi_trong_tep(duong=x, chuoi="TOKEN")

    def test_unittest_module_TU_CHOI_chuoi_khong_phai_ten_module(self):
        mg = KD.MoiGioiKiem(str(_tmp()))
        for x in ("a; rm -rf /", "-m http.server", "a/b.py", "a b"):
            with self.assertRaises(KD.KiemLoi, msg=x):
                mg.unittest_module(module=x)

    def test_REVIEWER_khong_phai_phep_kiem_tat_dinh(self):
        mg = KD.MoiGioiKiem(str(_tmp()))
        with self.assertRaises(KD.KiemLoi):
            mg.chay(KH.CachKiem.REVIEWER, {})

    def test_tep_ton_tai_that(self):
        g = _tmp()
        (g / "co.txt").write_text("xin chào", encoding="utf-8")
        mg = KD.MoiGioiKiem(str(g))
        self.assertTrue(mg.chay(KH.CachKiem.TEP_TON_TAI,
                                {"duong": "co.txt"}).dat)
        self.assertFalse(mg.chay(KH.CachKiem.TEP_TON_TAI,
                                 {"duong": "khong.txt"}).dat)

    def test_moi_buoc_DONE_van_KHONG_du_khi_tieu_chi_goc_chua_co_bang_chung(self):
        """§8: 4 agent báo DONE không phải thành công."""
        y = _y("fix multi-agent concurrency")
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=(_buoc("a"), _buoc("b"), _buoc("c"), _buoc("d")),
            nghiem_thu=(KH.TieuChiNghiemThu(
                mo_ta="chạy đồng thời thật + ngữ nghĩa khoá đúng"),))
        bc = KD.kiem_dinh_thuc_thi(
            y, kh, {m: _kq(summary="xong") for m in "abcd"})
        self.assertEqual(len(bc.buoc_dat), 4)
        self.assertIs(bc.trang_thai, KQ.TrangThaiXacMinh.THIEU_BANG_CHUNG)
        self.assertFalse(bc.dat)

    def test_tieu_chi_NGUOI_DUNG_khong_buoc_duoc_van_HIEN_RA(self):
        y = _y("sửa X", cau="sửa X, phải không được đụng production")
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc("a"),))
        bc = KD.kiem_dinh_thuc_thi(y, kh, {"a": _kq(summary="xong")})
        self.assertTrue(any(t.trang_thai is KQ.TrangThaiXacMinh.THIEU_BANG_CHUNG
                            for t in bc.tieu_chi))

    def test_ke_hoach_co_GHI_ma_khong_tieu_chi_thi_SUY_GIAM_khong_phai_DAT(self):
        y = _y("sửa X")
        y.tieu_chi_dat = ()
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=(_buoc("a", ghi=True,
                        kiem=((KH.CachKiem.TEST_DA_CHAY, {"it_nhat": 1}),)),))
        bc = KD.kiem_dinh_thuc_thi(
            y, kh, {"a": _kq(files_changed=("x.py",),
                             tests_run={"ran": True, "passed": 4, "failed": 0})},
            moi_gioi=KD.MoiGioiKiem(str(_tmp())))
        self.assertIs(bc.trang_thai, KQ.TrangThaiXacMinh.SUY_GIAM)

    def test_reviewer_dong_y_ma_KHONG_doc_lap_chi_toi_SUY_GIAM(self):
        y = _y("sửa X")
        y.tieu_chi_dat = ()
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id, buoc=(_buoc("a"),),
            nghiem_thu=(KH.TieuChiNghiemThu(
                mo_ta="đọc xong tài liệu",
                cach_kiem=((KH.CachKiem.CO_ARTIFACT, {"ten": []}),)),))
        bc = KD.kiem_dinh_thuc_thi(
            y, kh, {"a": _kq(summary="xong")},
            moi_gioi=KD.MoiGioiKiem(str(_tmp())),
            phan_bien={"phan_xu": "ACCEPT", "doc_lap": False})
        self.assertIs(bc.trang_thai, KQ.TrangThaiXacMinh.SUY_GIAM)
        self.assertIs(bc.doc_lap, False)

    def test_reviewer_REJECT_lam_hong(self):
        y = _y("sửa X")
        y.tieu_chi_dat = ()
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id, buoc=(_buoc("a"),),
            nghiem_thu=(KH.TieuChiNghiemThu(
                mo_ta="ok", cach_kiem=((KH.CachKiem.CO_ARTIFACT, {"ten": []}),)),))
        bc = KD.kiem_dinh_thuc_thi(
            y, kh, {"a": _kq(summary="xong")},
            moi_gioi=KD.MoiGioiKiem(str(_tmp())),
            phan_bien={"phan_xu": "REJECT", "doc_lap": True, "ly_do": "sai"})
        self.assertIs(bc.trang_thai, KQ.TrangThaiXacMinh.KHONG_DAT)

    def test_can_phan_bien_chi_khi_that_su_can(self):
        y = _y("sửa X")
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc("a"),))
        self.assertFalse(KD.can_phan_bien(kh, y))
        self.assertTrue(KD.can_phan_bien(kh, _y("deploy lên production")))


# ---------------------------------------------------------------------------
# §9/§19 — phan loai hong, tran, chi phi
# ---------------------------------------------------------------------------

class Test07PhucHoi(unittest.TestCase):

    def test_loi_CAU_HINH_QUYEN_tach_khoi_loi_viec(self):
        cd = PH.phan_loai_hong(loi="thư mục chưa được tin cậy")
        self.assertIs(cd.loai, PH.LoaiHong.CAU_HINH_QUYEN)
        self.assertTrue(cd.loai.la_cau_hinh)
        self.assertIs(cd.hanh_dong, PH.HanhDongPhucHoi.DUNG_CHO_NGUOI)

    def test_cau_hinh_duoc_kiem_TRUOC_nang_luc(self):
        """"permission denied" cũng khớp NANG_LUC — cấu hình phải thắng."""
        cd = PH.phan_loai_hong(loi="permission profile not loaded: settings.json")
        self.assertIs(cd.loai, PH.LoaiHong.CAU_HINH_QUYEN)

    def test_blocked_la_THAM_QUYEN_khong_phai_hong(self):
        cd = PH.phan_loai_hong(ket_qua=_kq(status="blocked"))
        self.assertIs(cd.loai, PH.LoaiHong.THAM_QUYEN)

    def test_quota_thi_DINH_TUYEN_LAI(self):
        cd = PH.phan_loai_hong(loi="429 rate limit exceeded")
        self.assertIs(cd.loai, PH.LoaiHong.PROVIDER)
        self.assertIs(cd.hanh_dong, PH.HanhDongPhucHoi.DINH_TUYEN_LAI)

    def test_phu_thuoc_hong_thi_BO_QUA_khong_thu_lai(self):
        cd = PH.phan_loai_hong(phu_thuoc_hong=True)
        self.assertIs(cd.hanh_dong, PH.HanhDongPhucHoi.BO_QUA)

    def test_tran_thu_lai_CO_BIEN(self):
        ns = PH.NganSachPhucHoi(so_lan_thu_theo_buoc={"a": PH.TRAN_THU_LAI_BUOC})
        cd = PH.ap_tran(PH.phan_loai_hong(loi="process died"), ns, "a")
        self.assertIs(cd.hanh_dong, PH.HanhDongPhucHoi.LAP_LAI_KE_HOACH)

    def test_can_ca_hai_tran_thi_DUNG_CHO_NGUOI(self):
        ns = PH.NganSachPhucHoi(
            so_lan_thu_theo_buoc={"a": PH.TRAN_THU_LAI_BUOC},
            so_lan_lap_ke_hoach=PH.TRAN_LAP_KE_HOACH)
        cd = PH.ap_tran(PH.phan_loai_hong(loi="process died"), ns, "a")
        self.assertIs(cd.hanh_dong, PH.HanhDongPhucHoi.DUNG_CHO_NGUOI)

    def test_khong_provider_shop_vo_han(self):
        ns = PH.NganSachPhucHoi(
            so_lan_dinh_tuyen_lai={"a": PH.TRAN_DINH_TUYEN_LAI})
        cd = PH.ap_tran(PH.phan_loai_hong(loi="429 quota"), ns, "a")
        self.assertIsNot(cd.hanh_dong, PH.HanhDongPhucHoi.DINH_TUYEN_LAI)

    def test_chi_phi_KHONG_BIA_token(self):
        so = CP.SoChiPhi("ex")
        so.them(CP.LanThu("a", provider="antigravity", model="m", giay=12.0))
        d = {m.label: m for m in so.do_duoc()}
        self.assertIsNone(d["tokens"].value)
        self.assertEqual(d["tokens"].confidence.value, "UNAVAILABLE")
        self.assertIsNone(d["cost_usd"].value)
        self.assertEqual(d["thời gian tường"].confidence.value, "ACTUAL")

    def test_hong_nhieu_tren_model_cao_cap_thi_de_nghi_ha_bac(self):
        so = CP.SoChiPhi("ex")
        for _ in range(CP.NGUONG_HA_BAC):
            so.them(CP.LanThu("a", premium_tier=2, thanh_cong=False))
        self.assertTrue(CP.xet_ngan_sach(so).nen_ha_bac)


# ---------------------------------------------------------------------------
# §5/§11/§13/§17 — bo dieu phoi
# ---------------------------------------------------------------------------

class Test08DieuPhoi(unittest.TestCase):

    def _dung(self, *, goal="khảo sát a rồi khảo sát b", buoc=None, nt=()):
        so, vg = _so(), ViecGia()
        y = _y(goal)
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=tuple(buoc or (_buoc("a"), _buoc("b"))), nghiem_thu=tuple(nt))
        bdp = _bdp(so, vg, moi_gioi=KD.MoiGioiKiem(str(_tmp())))
        y = bdp.bat_dau(y, kh)
        return so, vg, bdp, y, kh

    def test_buoc_doc_lap_chay_SONG_SONG(self):
        so, vg, bdp, y, kh = self._dung()
        kq = bdp.tick(y.execution_id)
        self.assertEqual(sorted(kq.da_giao), ["a", "b"])

    def test_viec_NGOAI_dung_o_WAITING_AUTHORITY(self):
        so, vg = _so(), ViecGia()
        y = _y("deploy lên production")
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc("a"),))
        bdp = _bdp(so, vg)
        y = bdp.bat_dau(y, kh)
        self.assertIs(y.trang_thai, TT.WAITING_AUTHORITY)
        bdp.tick(y.execution_id)
        self.assertEqual(vg.tao, [])            # KHONG viec nao duoc tao

    def test_duyet_roi_moi_chay(self):
        so, vg = _so(), ViecGia()
        y = _y("deploy lên production")
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc("a"),))
        bdp = _bdp(so, vg)
        bdp.bat_dau(y, kh)
        bdp.duyet(y.execution_id, boi="user")
        bdp.tick(y.execution_id)
        self.assertEqual(len(vg.tao), 1)

    def test_tu_choi_cong_thi_CANCELLED_va_nha_khoa(self):
        so, vg = _so(), ViecGia()
        y = _y("deploy lên production")
        bdp = _bdp(so, vg)
        bdp.bat_dau(y, KH.KeHoachThucThi(execution_id=y.execution_id,
                                         buoc=(_buoc("a"),)))
        y2 = bdp.duyet(y.execution_id, boi="user", dong_y=False)
        self.assertIs(y2.trang_thai, TT.CANCELLED)

    def test_KHONG_nhan_doi_viec_khi_tick_hai_lan(self):
        so, vg, bdp, y, kh = self._dung()
        bdp.tick(y.execution_id)
        bdp.tick(y.execution_id)
        self.assertEqual(len(vg.tao), 2)

    def test_ket_qua_DAT_day_buoc_ke_tiep(self):
        so, vg, bdp, y, kh = self._dung(
            buoc=(_buoc("a"), _buoc("b", phu=("a",))))
        bdp.tick(y.execution_id)
        self.assertEqual(len(vg.tao), 1)
        tid = vg.tao[0]
        vg.xong(tid)
        bdp.nhan_ket_qua(tid, _kq(tid, summary="khảo sát xong"))
        self.assertEqual(len(vg.tao), 2)

    def test_khong_bao_gio_RUNNING_sang_DONE_truc_tiep(self):
        so, vg, bdp, y, kh = self._dung(buoc=(_buoc("a"),))
        bdp.tick(y.execution_id)
        vg.xong(vg.tao[0])
        bdp.nhan_ket_qua(vg.tao[0], _kq(vg.tao[0], summary="xong"))
        sk = [e["kind"] for e in so.su_kien(y.execution_id)]
        self.assertIn("EXEC_VERIFIED", sk)
        cac = [e["detail"] for e in so.su_kien(y.execution_id)
               if e["kind"] == "EXEC_STATE"]
        self.assertTrue(any("VERIFYING" in x for x in cac))

    def test_thieu_bang_chung_KHONG_thanh_DONE(self):
        so, vg, bdp, y, kh = self._dung(buoc=(_buoc("a", ghi=True),))
        bdp.tick(y.execution_id)
        vg.xong(vg.tao[0])
        bdp.nhan_ket_qua(vg.tao[0], _kq(vg.tao[0], summary="xong rồi nhé"))
        self.assertIsNot(so.y_dinh(y.execution_id).trang_thai, TT.DONE)

    def test_phu_thuoc_hong_thi_bo_qua_con_chau(self):
        so, vg, bdp, y, kh = self._dung(
            buoc=(_buoc("a"), _buoc("b", phu=("a",))))
        bdp.tick(y.execution_id)
        tid = vg.tao[0]
        # ep buoc `a` hong han: mot loi CAU HINH khong thu lai duoc
        bdp.nhan_ket_qua(tid, _kq(tid, status="failed",
                                  summary="thư mục chưa được tin cậy"))
        bs = {b["buoc_id"]: b for b in so.buoc(y.execution_id, 1)}
        self.assertEqual(bs["a"]["state"], TrangThaiBuoc.HONG.value)

    def test_tam_dung_KHONG_giao_them(self):
        so, vg, bdp, y, kh = self._dung()
        bdp.tam_dung(y.execution_id)
        bdp.tick(y.execution_id)
        self.assertEqual(vg.tao, [])

    def test_huy_CO_BIEN_va_GIU_bang_chung(self):
        so, vg, bdp, y, kh = self._dung()
        bdp.tick(y.execution_id)
        n = len(so.su_kien(y.execution_id))
        y2 = bdp.huy(y.execution_id, ly_do="dừng task này")
        self.assertIs(y2.trang_thai, TT.CANCELLED)
        self.assertEqual(sorted(vg.da_dung), sorted(vg.tao))
        self.assertGreater(len(so.su_kien(y.execution_id)), n)  # khong xoa gi
        self.assertTrue(so.buoc(y.execution_id, 1))

    def test_moi_trang_thai_KET_THUC_deu_nha_khoa(self):
        for lam in ("huy", "tu_choi"):
            so, vg = _so(), ViecGia()
            y = _y("deploy lên production" if lam == "tu_choi" else "khảo sát a")
            bdp = _bdp(so, vg)
            bdp.bat_dau(y, KH.KeHoachThucThi(execution_id=y.execution_id,
                                             buoc=(_buoc("a"),)))
            if lam == "huy":
                bdp.tick(y.execution_id)
                bdp.huy(y.execution_id)
            else:
                bdp.duyet(y.execution_id, dong_y=False)
            self.assertIs(so.y_dinh(y.execution_id).trang_thai.ket_thuc, True)

    def test_doi_soat_khoi_dong_KHONG_tao_viec_moi(self):
        so, vg, bdp, y, kh = self._dung()
        bdp.tick(y.execution_id)
        n = len(vg.tao)
        for t in list(vg.tao):
            vg.trang_thai[t] = "DONE"           # tien trinh khong con
        bc = bdp.doi_soat_khoi_dong()
        self.assertEqual(len(vg.tao), n)        # KHONG tao them
        self.assertEqual(len(bc["mo_coi"]), n)

    def test_doi_soat_de_YEN_viec_con_song(self):
        so, vg, bdp, y, kh = self._dung()
        bdp.tick(y.execution_id)
        bc = bdp.doi_soat_khoi_dong()
        self.assertEqual(bc["mo_coi"], [])
        self.assertEqual(len(bc["con_song"]), 2)

    def test_tran_song_sot_qua_khoi_dong_lai(self):
        """Trần đọc TỪ SỔ — một bộ đếm trong RAM sẽ về 0 mỗi lần mở app."""
        so, vg, bdp, y, kh = self._dung(buoc=(_buoc("a"),))
        bdp.tick(y.execution_id)
        bdp2 = _bdp(so, ViecGia())              # "khoi dong lai"
        ns = bdp2.ngan_sach(y.execution_id)
        self.assertEqual(ns.so_lan_thu_theo_buoc.get("a", 0), 0)
        so.luu_buoc(y.execution_id, 1, "a", tang_lan_thu=True)
        so.luu_buoc(y.execution_id, 1, "a", tang_lan_thu=True)
        self.assertEqual(
            _bdp(so, ViecGia()).ngan_sach(y.execution_id)
            .so_lan_thu_theo_buoc.get("a"), 2)

    def test_lap_lai_ke_hoach_CO_TRAN(self):
        so, vg, bdp, y, kh = self._dung(buoc=(_buoc("a"),))
        for i in range(PH.TRAN_LAP_KE_HOACH):
            bdp.lap_lai_ke_hoach(y.execution_id, (_buoc("a"), _buoc(f"x{i}")),
                                 ly_do=f"lần {i}")
        with self.assertRaises(RuntimeError):
            bdp.lap_lai_ke_hoach(y.execution_id, (_buoc("a"),), ly_do="nữa")

    def test_lap_lai_giu_LICH_SU(self):
        so, vg, bdp, y, kh = self._dung(buoc=(_buoc("a"),))
        bdp.lap_lai_ke_hoach(y.execution_id, (_buoc("a"), _buoc("b")),
                             ly_do="a chưa đủ")
        ds = so.cac_ban_ke_hoach(y.execution_id)
        self.assertEqual([p.phien_ban for p in ds], [1, 2])
        self.assertTrue(any("THÊM bước b" in x for x in ds[1].thay_doi))


# ---------------------------------------------------------------------------
# §12/§21 — tra loi tu SO, khong tao viec khao sat
# ---------------------------------------------------------------------------

class Test09TraLoiTuSo(unittest.TestCase):

    def test_xong_chua_bro_tra_loi_tu_SO_khong_tao_viec(self):
        so, vg = _so(), ViecGia()
        y = _y("khảo sát a rồi khảo sát b")
        bdp = _bdp(so, vg)
        bdp.bat_dau(y, KH.KeHoachThucThi(
            execution_id=y.execution_id,
            buoc=(_buoc("a"), _buoc("b", phu=("a",)))))
        bdp.tick(y.execution_id)
        n = len(vg.tao)
        c = cau_trang_thai(so, PID)
        self.assertEqual(len(vg.tao), n)        # 0 viec khao sat
        self.assertIn(y.execution_id, c)
        self.assertIn("0/2", c)

    def test_khong_co_gi_chay_thi_noi_ro(self):
        self.assertIn("không có lần thực thi", cau_trang_thai(_so(), PID).lower())

    def test_cau_ket_thuc_co_du_bon_phan(self):
        y = _y("deploy lên production")
        y.trang_thai = TT.WAITING_AUTHORITY
        y.ly_do_dung = "cần bạn duyệt"
        c = cau_ket_thuc(y, None)
        self.assertIn("cần bạn", c.lower())
        self.assertIn("KHÔNG thay đổi", c)

    def test_cau_ket_thuc_noi_ro_SUY_GIAM(self):
        y = _y("sửa X")
        y.trang_thai = TT.DONE
        bc = KD.BaoCaoKiemDinh(execution_id=y.execution_id,
                               trang_thai=KQ.TrangThaiXacMinh.SUY_GIAM,
                               buoc_dat=("a",), doc_lap=False, ly_do="ok")
        c = cau_ket_thuc(y, bc, ghi_nho=[{"loai": "episodic"}])
        self.assertIn("DEGRADED", c)
        self.assertIn("Ký ức dự án", c)


# ---------------------------------------------------------------------------
# §14 — phan hoi ky uc
# ---------------------------------------------------------------------------

class Test10GhiNho(unittest.TestCase):

    def test_dat_thi_ghi_episodic(self):
        y = _y("sửa X")
        bc = KD.BaoCaoKiemDinh(y.execution_id, KQ.TrangThaiXacMinh.DAT,
                               buoc_dat=("a",), ly_do="ok")
        loai = [b.loai for b in GN.phan_loai_ghi_nho(y, bc)]
        self.assertIn("episodic", loai)
        self.assertNotIn("decision", loai)

    def test_hong_thi_ghi_incident(self):
        y = _y("sửa X")
        bc = KD.BaoCaoKiemDinh(y.execution_id, KQ.TrangThaiXacMinh.KHONG_DAT,
                               buoc_hong=("a",), ly_do="hỏng")
        self.assertEqual([b.loai for b in GN.phan_loai_ghi_nho(y, bc)],
                         ["incident"])

    def test_de_xuat_cua_MODEL_khong_bao_gio_thanh_QUYET_DINH(self):
        y = _y("sửa X")                         # REPO_LOCAL, duyet=KHONG_CAN
        self.assertIsNone(GN.de_xuat_quyet_dinh(y, noi_dung="dùng kiến trúc Z"))

    def test_nguoi_dung_duyet_thi_MOI_thanh_QUYET_DINH(self):
        y = _y("deploy lên production")
        y.duyet = YD.TrangThaiDuyet.DA_DUYET
        y.duyet_boi = "user"
        b = GN.de_xuat_quyet_dinh(y, noi_dung="dùng kiến trúc Z")
        self.assertIsNotNone(b)
        self.assertEqual(b.loai, "decision")
        self.assertEqual(b.tin_cay, "ghi_nhan")   # THAP HON `user_explicit`

    def test_procedural_chi_khi_co_quy_trinh_that(self):
        y = _y("sửa X")
        bc = KD.BaoCaoKiemDinh(y.execution_id, KQ.TrangThaiXacMinh.DAT,
                               buoc_dat=("a",), ly_do="ok")
        self.assertNotIn("procedural",
                         [b.loai for b in GN.phan_loai_ghi_nho(y, bc)])
        self.assertIn("procedural",
                      [b.loai for b in GN.phan_loai_ghi_nho(
                          y, bc, quy_trinh="chạy X rồi Y")])

    def test_ban_ghi_khong_mang_dong_suy_nghi(self):
        y = _y("sửa X")
        bc = KD.BaoCaoKiemDinh(y.execution_id, KQ.TrangThaiXacMinh.DAT,
                               buoc_dat=("a",),
                               ly_do="ok <thinking>đừng lưu cái này</thinking>")
        for b in GN.phan_loai_ghi_nho(y, bc):
            self.assertNotIn("đừng lưu cái này", b.noi_dung)


# ---------------------------------------------------------------------------
# §3 — lap ke hoach tu bo phan ra co san
# ---------------------------------------------------------------------------

class Test11LapKeHoach(unittest.TestCase):

    def setUp(self):
        self.p = Project(project_id=PID, name="Demo", repo_path=str(_tmp()))
        self.planner = RulePlanner(default_write_scope=("scripts",))

    def test_buoc_GHI_luon_co_phep_kiem_tat_dinh(self):
        y = _y("sửa scripts/control_center/store.py rồi chạy test")
        kq = self.planner.plan(y.goal, self.p)
        kh = LKH.tu_plan_result(y, kq, self.p)
        for b in kh.buoc:
            if b.ghi:
                self.assertTrue(b.co_kiem_tat_dinh, b.buoc_id)

    def test_DAG_cua_bo_phan_ra_duoc_GIU(self):
        y = _y("sửa scripts/x.py rồi chạy test rồi viết tài liệu")
        kq = self.planner.plan(y.goal, self.p)
        kh = LKH.tu_plan_result(y, kq, self.p)
        self.assertEqual(len(kh.buoc), len(kq.tasks))
        KH.kiem_dag(kh.buoc)

    def test_cat_theo_pham_vi_KHONG_de_lai_phu_thuoc_treo(self):
        y = _y("sửa scripts/x.py rồi chạy test rồi viết tài liệu")
        kq = self.planner.plan(y.goal, self.p)
        cat = LKH.cat_theo_pham_vi(kq, "tài liệu")
        kh = LKH.tu_plan_result(y, cat, self.p)
        KH.kiem_dag(kh.buoc)                    # khong nem

    def test_cat_khong_khop_thi_GIU_NGUYEN(self):
        y = _y("sửa scripts/x.py rồi chạy test")
        kq = self.planner.plan(y.goal, self.p)
        self.assertEqual(len(LKH.cat_theo_pham_vi(kq, "zzz").tasks),
                         len(kq.tasks))


# ---------------------------------------------------------------------------
# §25 — du lieu / bao mat
# ---------------------------------------------------------------------------

class Test12BaoMat(unittest.TestCase):

    def test_so_KHONG_luu_bi_mat(self):
        so = _so()
        y = _y("sửa X")
        so.luu(y)
        so.ghi_su_kien(y.execution_id, "THU",
                       detail="AKIA1234567890ABCDEF và ghsecret",
                       meta={"token": "ghp_" + "a" * 36})
        van = str(so.su_kien(y.execution_id))
        self.assertNotIn("ghp_" + "a" * 36, van)

    def test_hop_dong_ket_qua_cat_dong_suy_nghi(self):
        k = _kq(summary="xong <thinking>nội tâm</thinking> phần sau")
        self.assertNotIn("nội tâm", k.summary)

    def test_co_lap_du_an(self):
        so = _so()
        a = YD.tao_y_dinh(project_id="A", goal="việc A")
        b = YD.tao_y_dinh(project_id="B", goal="việc B")
        so.luu(a)
        so.luu(b)
        self.assertEqual([x.execution_id for x in so.danh_sach("A")],
                         [a.execution_id])
        self.assertNotIn(b.execution_id, cau_trang_thai(so, "A"))


if __name__ == "__main__":                      # pragma: no cover
    unittest.main(verbosity=2)
