"""Bài kiểm V0.9 §1 — VÒNG TỰ SỬA: v1 hỏng -> sửa CÓ BIÊN -> v2 -> DONE.

Đây là thứ bản v0.9 đầu tiên KHÔNG có, và thiếu nó thì vòng kín dừng ở
`BLOCKED` ngay cả khi hỏng hóc hoàn toàn sửa được: mọi bước đều đạt, chỉ có
MỤC TIÊU GỐC là chưa đạt, và không có bước nào để sửa vì không bước nào hỏng.

Bốn đường ra của §1 đều được khoá ở đây:

    A  sửa được trong thẩm quyền đã cấp -> REPLANNING có biên -> v2
    B  cần nghĩ lại thiết kế          -> Strategist đề xuất, vẫn có biên
    C  cần thẩm quyền MỚI             -> WAITING_AUTHORITY
    D  không sửa được / cạn ngân sách -> BLOCKED kèm lý do ĐÚNG

TẤT ĐỊNH: không mạng, không tiến trình model. Lượt Strategist được giả bằng
đúng cái seam mà engine dùng.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.control_center.execution import ke_hoach as KH
from scripts.control_center.execution import lap_ke_hoach as ELK
from scripts.control_center.model import LockKind

PID = "demo"


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="cc-v09sua-"))


def _kh(*, nghiem_thu=(), buoc=None, phien_ban=1, **kw) -> KH.KeHoachThucThi:
    return KH.KeHoachThucThi(
        execution_id="ex_1", phien_ban=phien_ban,
        # `b1` PHẢI khai một phép kiểm tất định: một bước GHI không khai gì
        # là `THIEU_BANG_CHUNG` theo đúng thiết kế (§6), nên một fixture
        # thiếu nó sẽ làm bài kiểm hỏng vì lý do không liên quan tới §1.
        # `lap_ke_hoach.suy_cach_kiem` gắn sẵn phép kiểm cho mọi bước ghi
        # thật, nên đây là hình dạng ĐÚNG của một kế hoạch sản phẩm.
        buoc=tuple(buoc or (KH.BuocKeHoach(
            buoc_id="b1", tieu_de="b1", muc_tieu="làm b1",
            che_do_ghi=KH.CheDoGhi.GHI,
            cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": "docs/a.md"}),),
            tai_nguyen=((LockKind.FILESYSTEM, "docs/x.md", "write"),)),)),
        nghiem_thu=tuple(nghiem_thu), **kw)


class Test01SuyDuongTuTieuChi(unittest.TestCase):
    """Phạm vi ghi của bước sửa SUY TỪ chính tiêu chí — không rộng hơn."""

    def test_lay_duong_tu_TEP_TON_TAI(self):
        self.assertEqual(
            ELK.duong_cua_tieu_chi(
                ((KH.CachKiem.TEP_TON_TAI, {"duong": "docs/a.md"}),)),
            ("docs/a.md",))

    def test_lay_duong_tu_CHUOI_TRONG_TEP(self):
        self.assertEqual(
            ELK.duong_cua_tieu_chi(
                ((KH.CachKiem.CHUOI_TRONG_TEP,
                  {"duong": "docs/b.md", "chuoi": "X"}),)),
            ("docs/b.md",))

    def test_gop_nhieu_duong_va_khu_trung(self):
        d = ELK.duong_cua_tieu_chi((
            (KH.CachKiem.TEP_TON_TAI, {"duong": "docs/a.md"}),
            (KH.CachKiem.CHUOI_TRONG_TEP, {"duong": "docs/a.md"}),
            (KH.CachKiem.BIEN_DICH_PYTHON, {"duong": ["scripts", "tests"]})))
        self.assertEqual(d, ("docs/a.md", "scripts", "tests"))

    def test_tieu_chi_KHONG_do_duong_nao_thi_rong(self):
        self.assertEqual(ELK.duong_cua_tieu_chi(
            ((KH.CachKiem.TEST_DA_CHAY, {"it_nhat": 1}),)), ())


class Test02BuocSuaTatDinh(unittest.TestCase):
    """(A) Tiêu chí đo một đường dẫn -> sinh được bước sửa CÓ BIÊN."""

    TC = ("tệp docs/a.md phải có chuỗi MARKER",
          ((KH.CachKiem.TEP_TON_TAI, {"duong": "docs/a.md"}),
           (KH.CachKiem.CHUOI_TRONG_TEP,
            {"duong": "docs/a.md", "chuoi": "MARKER"})))

    def test_GIU_NGUYEN_buoc_cu_va_THEM_buoc_sua(self):
        kh = _kh()
        b = ELK.buoc_sua_tieu_chi(kh, [self.TC])
        self.assertEqual(len(b), 2)
        self.assertEqual(b[0].buoc_id, "b1")          # buoc cu GIU NGUYEN
        self.assertTrue(b[1].buoc_id.startswith("sua"))

    def test_buoc_sua_PHU_THUOC_moi_buoc_cu(self):
        kh = _kh()
        b = ELK.buoc_sua_tieu_chi(kh, [self.TC])
        self.assertEqual(set(b[1].phu_thuoc), {"b1"})

    def test_pham_vi_ghi_CHI_la_duong_tieu_chi_DO(self):
        """Rào chặn một bước "sửa cho đạt" đi lang thang khắp kho."""
        kh = _kh()
        b = ELK.buoc_sua_tieu_chi(kh, [self.TC])[1]
        self.assertEqual([r for _k, r, m in b.tai_nguyen if m == "write"],
                         ["docs/a.md"])
        self.assertIs(b.che_do_ghi, KH.CheDoGhi.GHI)

    def test_cach_kiem_cua_buoc_sua_CHINH_LA_cua_tieu_chi(self):
        """Bước chỉ xong khi đúng phép đo đã đánh trượt nó nay xanh."""
        kh = _kh()
        b = ELK.buoc_sua_tieu_chi(kh, [self.TC])[1]
        self.assertEqual([c for c, _ in b.cach_kiem],
                         [KH.CachKiem.TEP_TON_TAI, KH.CachKiem.CHUOI_TRONG_TEP])

    def test_muc_tieu_MANG_bang_chung_va_CAM_noi_pham_vi(self):
        kh = _kh()
        m = ELK.buoc_sua_tieu_chi(kh, [self.TC])[1].muc_tieu
        self.assertIn("MARKER", m)
        self.assertIn("docs/a.md", m)
        self.assertIn("ĐỪNG", m)

    def test_tieu_chi_NGU_NGHIA_thi_KHONG_sinh_buoc_tat_dinh(self):
        kh = _kh()
        self.assertEqual(
            ELK.buoc_sua_tieu_chi(kh, [("bản redesign có hợp lý không", ())]),
            [])

    def test_DAG_cua_ban_sua_van_hop_le(self):
        kh = _kh()
        KH.kiem_dag(ELK.buoc_sua_tieu_chi(kh, [self.TC]))

    def test_khong_sinh_trung_ma_khi_goi_lai(self):
        kh = _kh()
        b = ELK.buoc_sua_tieu_chi(kh, [self.TC], lan=1)
        kh2 = _kh(buoc=b, phien_ban=2, ly_do_sua="x")
        b2 = ELK.buoc_sua_tieu_chi(kh2, [self.TC], lan=1)
        self.assertEqual(b2, [])                       # cung `lan` -> khong them


class Test03BuocSuaTuChienLuoc(unittest.TestCase):
    """(B) Đề xuất của Strategist vẫn BỊ RÀNG BUỘC y như bản tất định."""

    def test_pham_vi_do_BEN_GOI_cap_khong_phai_model_chon(self):
        kh = _kh()
        b = ELK.buoc_tu_de_xuat_sua(kh, muc_tieu="tách observer ra",
                                    duong=["scripts/x.py"])
        self.assertEqual([r for _k, r, m in b[-1].tai_nguyen if m == "write"],
                         ["scripts/x.py"])
        self.assertIn("scripts/x.py", b[-1].muc_tieu)

    def test_GIU_buoc_cu_va_phu_thuoc_dung(self):
        kh = _kh()
        b = ELK.buoc_tu_de_xuat_sua(kh, muc_tieu="x", duong=["docs/a.md"])
        self.assertEqual(b[0].buoc_id, "b1")
        self.assertEqual(set(b[-1].phu_thuoc), {"b1"})

    def test_thieu_pham_vi_hoac_muc_tieu_thi_KHONG_sinh(self):
        kh = _kh()
        self.assertEqual(ELK.buoc_tu_de_xuat_sua(kh, muc_tieu="x", duong=[]), [])
        self.assertEqual(
            ELK.buoc_tu_de_xuat_sua(kh, muc_tieu="  ", duong=["a"]), [])

    def test_cat_dong_suy_nghi_khoi_de_xuat(self):
        kh = _kh()
        b = ELK.buoc_tu_de_xuat_sua(
            kh, muc_tieu="làm X <thinking>nội tâm</thinking> rồi Y",
            duong=["docs/a.md"])
        self.assertNotIn("nội tâm", b[-1].muc_tieu)


class Test04VongSuaDauCuoi(unittest.TestCase):
    """v1 hỏng tiêu chí -> v2 có bước sửa -> kiểm định lại -> DAT.

    Chạy qua `kiem_dinh_thuc_thi` THẬT với một `MoiGioiKiem` trên thư mục
    thật, nên phép đo là phép đo — không phải một cờ bài kiểm tự bật.
    """

    def setUp(self):
        from scripts.control_center.execution import kiem_dinh as KD
        self.goc = _tmp()
        (self.goc / "docs").mkdir(parents=True, exist_ok=True)
        self.mg = KD.MoiGioiKiem(str(self.goc))
        self.KD = KD

    def _y(self):
        from scripts.control_center.execution import y_dinh as YD
        y = YD.tao_y_dinh(project_id=PID, goal="sinh tài liệu có MARKER",
                          cau_nguoi_dung="ok làm đi")
        y.tieu_chi_dat = ()
        return y

    TC = KH.TieuChiNghiemThu(
        mo_ta="docs/a.md phải có chuỗi MARKER",
        cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": "docs/a.md"}),
                   (KH.CachKiem.CHUOI_TRONG_TEP,
                    {"duong": "docs/a.md", "chuoi": "MARKER"})))

    def _kq(self, tid, tep=("docs/a.md",)):
        from scripts.control_center.execution import ket_qua as KQ
        return KQ.HopDongKetQua(task_id=tid, status="ok", summary="xong",
                                files_changed=tuple(tep),
                                worktree=str(self.goc))

    def test_v1_HONG_vi_thieu_MARKER(self):
        y, kh = self._y(), _kh(nghiem_thu=(self.TC,))
        (self.goc / "docs" / "a.md").write_text("nội dung\n", encoding="utf-8")
        bc = self.KD.kiem_dinh_thuc_thi(y, kh, {"b1": self._kq("t1")},
                                        moi_gioi=self.mg)
        self.assertFalse(bc.dat)
        self.assertTrue(any(t.trang_thai.value == "KHONG_DAT"
                            for t in bc.tieu_chi))

    def test_v2_co_buoc_sua_va_DAT_sau_khi_agent_them_MARKER(self):
        y, kh = self._y(), _kh(nghiem_thu=(self.TC,))
        (self.goc / "docs" / "a.md").write_text("nội dung\n", encoding="utf-8")
        tc = [(self.TC.mo_ta, self.TC.cach_kiem)]
        buoc = ELK.buoc_sua_tieu_chi(kh, tc, lan=1)
        self.assertEqual(len(buoc), 2)
        v2 = kh.ban_moi(buoc=buoc, ly_do="tiêu chí chưa đạt")
        self.assertEqual(v2.phien_ban, 2)
        self.assertEqual(v2.nghiem_thu, kh.nghiem_thu)   # tieu chi GIU NGUYEN

        # "agent" cua buoc sua lam dung viec cua no
        (self.goc / "docs" / "a.md").write_text("nội dung\nMARKER\n",
                                                encoding="utf-8")
        kq = {"b1": self._kq("t1"), buoc[1].buoc_id: self._kq("t2")}
        bc = self.KD.kiem_dinh_thuc_thi(y, v2, kq, moi_gioi=self.mg)
        self.assertTrue(bc.dat, bc.ly_do)
        self.assertEqual(bc.trang_thai.value, "DAT")

    def test_v1_VAN_CON_trong_lich_su(self):
        from scripts.control_center.execution.so import SoThucThi
        from scripts.control_center.store import ControlStore
        so = SoThucThi(ControlStore(_tmp() / "c.db"))
        y = self._y()
        kh = KH.KeHoachThucThi(execution_id=y.execution_id,
                               buoc=_kh().buoc, nghiem_thu=(self.TC,))
        so.luu(y)
        so.luu_ke_hoach(kh)
        tc = [(self.TC.mo_ta, self.TC.cach_kiem)]
        so.luu_ke_hoach(kh.ban_moi(buoc=ELK.buoc_sua_tieu_chi(kh, tc),
                                   ly_do="tiêu chí chưa đạt"))
        ban = so.cac_ban_ke_hoach(y.execution_id)
        self.assertEqual([p.phien_ban for p in ban], [1, 2])
        self.assertEqual([p.dang_hieu_luc for p in ban], [False, True])
        self.assertTrue(any("tieu chí" in p.ly_do_sua.lower()
                            or "tiêu chí" in p.ly_do_sua.lower()
                            for p in ban if p.phien_ban == 2))

    def test_KHONG_nhan_doi_buoc_da_DAT(self):
        """Bước đã đạt được GIỮ NGUYÊN, không bị chạy lại."""
        kh = _kh(nghiem_thu=(self.TC,))
        b = ELK.buoc_sua_tieu_chi(kh, [(self.TC.mo_ta, self.TC.cach_kiem)])
        self.assertEqual([x.buoc_id for x in b].count("b1"), 1)
        self.assertEqual(b[0].muc_tieu, kh.buoc[0].muc_tieu)


class Test05DoiSoatKhaiThieuTheoCONG(unittest.TestCase):
    """`_doi_soat_khai_thieu` phải tin CỔNG, không tự suy lại từ `pb.changes`.

    KHUYẾT TẬT ĐÃ LÀM HỎNG CẢ MỘT ĐỢT NGHIỆM THU THẬT (2026-09-12), và nó
    nằm trong mã của ta chứ không ở nhà cung cấp:

    `cong_diff` phán "worker không khai sửa gì" dựa trên `TaskResult.
    files_changed` — bản ĐÃ LỌC, chỉ giữ thứ trông như đường dẫn. Hàm đối
    soát lại đọc `pb.changes` THÔ. Khi model điền một CÂU MÔ TẢ thay vì
    đường dẫn, hai cái nhìn lệch nhau: cổng thấy rỗng (nên báo khai thiếu),
    hàm đối soát thấy có (nên từ chối) — và một việc LÀM ĐÚNG bị đánh hỏng.

    Đo thật: 5/6 lượt worker ghi đúng tệp, đúng phạm vi, mọi cổng khác xanh,
    `diff` là cổng DUY NHẤT hỏng — cả 5 đều `FAILED`.
    """

    def _dung(self, *, changes, observed=("docs/reports/a.md",),
              scope=("docs/reports/a.md",), gates_khac_dat=True):
        from scripts.router_v3.pool.validation import GateResult
        from scripts.router_v4.envelope import ResultEnvelope
        from scripts.control_center.engine import DAU_HIEU_KHAI_THIEU

        class _BC:
            def __init__(s):
                s.passed = False
                s.files_changed_observed = list(observed)
                s.scope_violations = []
                s.gates = [
                    GateResult("shape", True, "status=ok"),
                    GateResult("diff", False,
                               f"{DAU_HIEU_KHAI_THIEU} {list(observed)}"),
                    GateResult("scope", gates_khac_dat, "trong phạm vi"),
                    GateResult("security", True, "không thấy bí mật"),
                    GateResult("artifacts", True, "đủ hiện vật"),
                ]

            @property
            def failed_gates(s):
                return [g.name for g in s.gates if not g.passed]

        class _KQ:
            pass

        kq = _KQ()
        kq.validation = _BC()
        kq.envelope = ResultEnvelope(task_id="t1", status="failed",
                                     summary="đã tạo tệp",
                                     changes=list(changes))
        from scripts.control_center.planner import RulePlanner
        hd = RulePlanner(default_write_scope=("docs",))._hop_dong(
            "t1", "tạo tệp", "documentation", list(scope),
            cau_goc="ok làm đi", deps=())
        return kq, hd

    def _cc(self):
        from scripts.control_center.engine import ControlCenter
        return ControlCenter(root=_tmp(), probe=False)

    def test_CAU_MO_TA_trong_changes_van_duoc_doi_soat(self):
        """Hình dạng ĐÚNG đã làm hỏng nghiệm thu thật."""
        cc = self._cc()
        try:
            kq, hd = self._dung(changes=[
                "Tạo docs/reports/a.md với tiêu đề, 4 gạch đầu dòng và "
                "chuỗi xác nhận bắt buộc."])
            self.assertTrue(cc._doi_soat_khai_thieu(_CtxGia(cc), "t1", hd, kq))
            # `changes` được ĐIỀN LẠI bằng tập THẬT
            self.assertEqual(list(kq.envelope.changes), ["docs/reports/a.md"])
        finally:
            cc.shutdown()

    def test_DUONG_DAN_DUNG_trong_changes_cung_duoc_doi_soat(self):
        cc = self._cc()
        try:
            kq, hd = self._dung(changes=["docs/reports/a.md"])
            self.assertTrue(cc._doi_soat_khai_thieu(_CtxGia(cc), "t1", hd, kq))
        finally:
            cc.shutdown()

    def test_changes_RONG_van_duoc_doi_soat_nhu_cu(self):
        cc = self._cc()
        try:
            kq, hd = self._dung(changes=[])
            self.assertTrue(cc._doi_soat_khai_thieu(_CtxGia(cc), "t1", hd, kq))
        finally:
            cc.shutdown()

    def test_DIA_SACH_thi_VAN_TU_CHOI(self):
        """Bất biến không được nới: khai có sửa mà đĩa SẠCH phải HỎNG."""
        cc = self._cc()
        try:
            kq, hd = self._dung(changes=["docs/reports/a.md"], observed=())
            self.assertFalse(cc._doi_soat_khai_thieu(_CtxGia(cc), "t1", hd, kq))
        finally:
            cc.shutdown()

    def test_TEP_NGOAI_PHAM_VI_thi_VAN_TU_CHOI(self):
        cc = self._cc()
        try:
            kq, hd = self._dung(changes=["mô tả gì đó"],
                                observed=("docs/reports/a.md", "server/.env"),
                                scope=("docs/reports/a.md",))
            self.assertFalse(cc._doi_soat_khai_thieu(_CtxGia(cc), "t1", hd, kq))
        finally:
            cc.shutdown()

    def test_CONG_KHAC_HONG_thi_VAN_TU_CHOI(self):
        cc = self._cc()
        try:
            kq, hd = self._dung(changes=["mô tả"], gates_khac_dat=False)
            self.assertFalse(cc._doi_soat_khai_thieu(_CtxGia(cc), "t1", hd, kq))
        finally:
            cc.shutdown()


class _CtxGia:
    """`ProjectContext` tối thiểu — `_doi_soat_khai_thieu` chỉ cần `project`."""

    def __init__(self, cc):
        from scripts.control_center.model import Project
        self.project = Project(project_id="demo", name="D",
                               repo_path=str(_tmp()))


if __name__ == "__main__":                      # pragma: no cover
    unittest.main(verbosity=2)
