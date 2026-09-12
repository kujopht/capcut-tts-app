"""Bài kiểm V0.9 §A + §B — Reviewer TỰ ĐỘNG, và vòng phản hồi chất lượng.

TẤT ĐỊNH, KHÔNG MẠNG, KHÔNG TIẾN TRÌNH MODEL NÀO. Lượt Reviewer được giả
bằng đúng cái callable mà `BoDieuPhoi` nhận ở constructor — đó chính là lý do
nó nhận callable thay vì `HoiDong`.

Hai câu hỏi được khoá lại ở đây:

  §A  bộ điều phối có TỰ gọi phản biện ngữ nghĩa không, và có biết KHI NÀO
      thì KHÔNG nên gọi không;
  §B  một kết quả đã kiểm định có quay về lịch sử VAI dưới dạng một quan sát
      GẮN ĐƯỢC VÀO MODEL không — và có KHÔNG đếm những thứ không đo được
      không.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from scripts.control_center.execution import ke_hoach as KH
from scripts.control_center.execution import ket_qua as KQ
from scripts.control_center.execution import kiem_dinh as KD
from scripts.control_center.execution import phan_hoi as PH
from scripts.control_center.execution import tiep_noi as TN
from scripts.control_center.execution import y_dinh as YD
from scripts.control_center.execution.dieu_phoi import BoDieuPhoi
from scripts.control_center.execution.so import SoThucThi
from scripts.control_center.execution.trang_thai import TrangThaiThucThi as TT
from scripts.control_center.store import ControlStore
from scripts.router_v4.history import MAU_TOI_THIEU, BenchmarkStore, Record

PID = "demo"


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="cc-v09ab-"))


def _so() -> SoThucThi:
    return SoThucThi(ControlStore(_tmp() / "control.db"))


def _y(goal="dựng lại kiến trúc observer cho gọn", **kw) -> YD.YDinhThucThi:
    return YD.tao_y_dinh(project_id=PID, goal=goal, cau_nguoi_dung=goal, **kw)


def _buoc(ma="b1", *, ghi=False, kiem=()) -> KH.BuocKeHoach:
    return KH.BuocKeHoach(buoc_id=ma, tieu_de=ma, muc_tieu=f"làm {ma}",
                          che_do_ghi=KH.CheDoGhi.GHI if ghi
                          else KH.CheDoGhi.DOC,
                          cach_kiem=tuple(kiem))


def _kq(tid="t1", **kw) -> KQ.HopDongKetQua:
    d = {"status": "ok", "summary": "đã làm xong"}
    d.update(kw)
    return KQ.HopDongKetQua(task_id=tid, **d)


def _bc(tt=KQ.TrangThaiXacMinh.DAT, **kw) -> KD.BaoCaoKiemDinh:
    return KD.BaoCaoKiemDinh(execution_id="ex_1", trang_thai=tt,
                             ly_do="x", **kw)


class ViecGia:
    def __init__(self):
        self.tao: List[str] = []
        self.tt: Dict[str, str] = {}
        self._n = 0

    def tao_viec(self, y, b, lan, phien_ban=1) -> str:
        self._n += 1
        t = f"{y.project_id}.{b.buoc_id}-v{phien_ban}#{self._n}"
        self.tao.append(t)
        self.tt[t] = "RUNNING"
        return t

    def doc(self, t): return self.tt.get(t, "")
    def dung(self, t, ly): self.tt[t] = "FAILED"


class ReviewerGia:
    """Đếm mọi lần bị gọi — đó là cách duy nhất chứng minh TỰ ĐỘNG."""

    def __init__(self, phan_xu="ACCEPT", doc_lap=True, tra_none=False):
        self.phan_xu = phan_xu
        self.doc_lap = doc_lap
        self.tra_none = tra_none
        self.so_lan = 0
        self.khoi: List[str] = []

    def __call__(self, y, kh, bc) -> Optional[Dict]:
        self.so_lan += 1
        if self.tra_none:
            return None
        return {"phan_xu": self.phan_xu, "doc_lap": self.doc_lap,
                "suy_giam": not self.doc_lap, "provider": "antigravity",
                "model": "m-khac-ho", "ly_do": "phán xử giả"}


def _bdp(so, vg, rv=None, **kw) -> BoDieuPhoi:
    return BoDieuPhoi(so, tao_viec=vg.tao_viec, trang_thai_viec=vg.doc,
                      dung_viec=vg.dung, goi_phan_bien=rv,
                      moi_gioi=KD.MoiGioiKiem(str(_tmp())), **kw)


# ---------------------------------------------------------------------------
# §A — CHINH SACH GOI REVIEWER
# ---------------------------------------------------------------------------

class Test01ChinhSachGoi(unittest.TestCase):

    def test_tieu_chi_khai_REVIEWER_thi_doi_ngu_nghia(self):
        kh = KH.KeHoachThucThi(
            execution_id="ex", buoc=(_buoc(),),
            nghiem_thu=(KH.TieuChiNghiemThu(
                mo_ta="kiến trúc có hợp lý không",
                cach_kiem=((KH.CachKiem.REVIEWER, {}),)),))
        self.assertEqual(KD.tieu_chi_can_ngu_nghia(kh),
                         ["kiến trúc có hợp lý không"])

    def test_tieu_chi_KHONG_co_phep_kiem_tat_dinh_cung_doi_ngu_nghia(self):
        """Máy không trả lời được thì phải có đường ngữ nghĩa — không thì nó
        vĩnh viễn THIEU_BANG_CHUNG."""
        kh = KH.KeHoachThucThi(
            execution_id="ex", buoc=(_buoc(),),
            nghiem_thu=(KH.TieuChiNghiemThu(mo_ta="redesign có giải quyết "
                                                  "mục tiêu không"),))
        self.assertTrue(KD.tieu_chi_can_ngu_nghia(kh))

    def test_viec_MAY_MOC_thi_KHONG_goi(self):
        y = _y("sửa một lỗi chính tả")
        y.tieu_chi_dat = ()
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id, buoc=(_buoc(),),
            nghiem_thu=(KH.TieuChiNghiemThu(
                mo_ta="test xanh",
                cach_kiem=((KH.CachKiem.TEST_DA_CHAY, {"it_nhat": 1}),)),))
        nen, _ = KD.nen_goi_reviewer(kh, y, _bc())
        self.assertFalse(nen)

    def test_MAY_da_bat_duoc_loi_thi_KHONG_goi(self):
        """Hỏi thêm một model để nghe lại điều đã biết là đốt hạn mức."""
        y = _y()
        kh = KH.KeHoachThucThi(
            execution_id=y.execution_id, buoc=(_buoc(),),
            nghiem_thu=(KH.TieuChiNghiemThu(mo_ta="ngữ nghĩa"),))
        nen, vi = KD.nen_goi_reviewer(
            kh, y, _bc(KQ.TrangThaiXacMinh.KHONG_DAT, buoc_hong=("b1",)))
        self.assertFalse(nen)
        self.assertIn("tất định", vi)

    def test_tieu_chi_do_MAY_khong_dat_thi_KHONG_goi(self):
        y = _y()
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc(),),
                               nghiem_thu=(KH.TieuChiNghiemThu(mo_ta="ngữ nghĩa"),))
        bc = _bc(KQ.TrangThaiXacMinh.KHONG_DAT, tieu_chi=(
            KD.ChamTieuChi("test xanh", KQ.TrangThaiXacMinh.KHONG_DAT,
                           kiem=(KD.KetQuaKiem("TEST_DA_CHAY", False, "2 hỏng"),)),))
        self.assertFalse(KD.nen_goi_reviewer(kh, y, bc)[0])

    def test_cham_production_thi_GOI_du_moi_phep_do_xanh(self):
        y = _y("deploy lên production")
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc(),))
        nen, vi = KD.nen_goi_reviewer(kh, y, _bc())
        self.assertTrue(nen)
        self.assertIn("production", vi)


# ---------------------------------------------------------------------------
# §A — BO DIEU PHOI TU GOI
# ---------------------------------------------------------------------------

class Test02TuDongGoi(unittest.TestCase):

    def _chay(self, rv, *, nghiem_thu, goal="dựng lại kiến trúc observer"):
        so, vg = _so(), ViecGia()
        y = _y(goal)
        y.tieu_chi_dat = ()
        kh = KH.KeHoachThucThi(execution_id=y.execution_id, buoc=(_buoc(),),
                               nghiem_thu=nghiem_thu)
        bdp = _bdp(so, vg, rv)
        bdp.bat_dau(y, kh)
        bdp.tick(y.execution_id)
        tid = vg.tao[0]
        vg.tt[tid] = "DONE"
        bdp.nhan_ket_qua(tid, _kq(tid, summary="đã dựng lại xong"))
        return so, bdp, y.execution_id

    NT_NGU_NGHIA = (KH.TieuChiNghiemThu(
        mo_ta="bản dựng lại có thực sự giải quyết mục tiêu không"),)
    NT_MAY = (KH.TieuChiNghiemThu(
        mo_ta="có artifact", cach_kiem=((KH.CachKiem.CO_ARTIFACT,
                                         {"ten": []}),)),)

    def test_TU_GOI_khi_tieu_chi_doi_ngu_nghia(self):
        rv = ReviewerGia()
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        self.assertEqual(rv.so_lan, 1, "bộ điều phối phải TỰ gọi Reviewer")
        self.assertIs(so.y_dinh(eid).trang_thai, TT.DONE)

    def test_KHONG_goi_khi_chi_co_kiem_may_moc(self):
        rv = ReviewerGia()
        self._chay(rv, nghiem_thu=self.NT_MAY, goal="sửa lỗi chính tả")
        self.assertEqual(rv.so_lan, 0)

    def test_ACCEPT_doc_lap_cho_tieu_chi_ngu_nghia_DAT(self):
        rv = ReviewerGia("ACCEPT", doc_lap=True)
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        self.assertIs(so.y_dinh(eid).trang_thai, TT.DONE)

    def test_ACCEPT_KHONG_doc_lap_chi_toi_SUY_GIAM(self):
        rv = ReviewerGia("ACCEPT", doc_lap=False)
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        bc = bdp.kiem_dinh(eid, phan_bien={"phan_xu": "ACCEPT",
                                           "doc_lap": False})
        self.assertIs(bc.trang_thai, KQ.TrangThaiXacMinh.SUY_GIAM)

    def test_REVISE_vao_duong_sua_co_tran_KHONG_thanh_DONE(self):
        rv = ReviewerGia("REVISE")
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        self.assertIsNot(so.y_dinh(eid).trang_thai, TT.DONE)

    def test_REJECT_KHONG_thanh_DONE(self):
        rv = ReviewerGia("REJECT")
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        self.assertIsNot(so.y_dinh(eid).trang_thai, TT.DONE)

    def test_bat_dong_cua_REVIEWER_KHONG_lam_doi_provider(self):
        """§A.7 — không thử nhà cung cấp khác chỉ vì Reviewer không đồng ý."""
        rv = ReviewerGia("REJECT")
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        sk = [e["kind"] for e in so.su_kien(eid)]
        self.assertNotIn("STEP_RETRY", sk)

    def test_Reviewer_hong_thi_bao_SUY_GIAM_khong_gia_vo(self):
        rv = ReviewerGia(tra_none=True)
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_NGU_NGHIA)
        self.assertEqual(rv.so_lan, 1)
        e = next(x for x in so.su_kien(eid) if x["kind"] == "EXEC_VERIFIED")
        self.assertIn("SUY GIẢM", e["detail"])

    def test_cong_REVIEW_GATE_luon_ghi_ly_do(self):
        rv = ReviewerGia()
        so, bdp, eid = self._chay(rv, nghiem_thu=self.NT_MAY,
                                  goal="sửa lỗi chính tả")
        e = next(x for x in so.su_kien(eid) if x["kind"] == "REVIEW_GATE")
        self.assertIn("BỎ QUA", e["detail"])

    def test_khong_co_duong_ngu_nghia_thi_van_KHONG_DONE(self):
        """Chứng cứ chống rỗng: bỏ callable đi thì tiêu chí ngữ nghĩa treo."""
        so, bdp, eid = self._chay(None, nghiem_thu=self.NT_NGU_NGHIA)
        self.assertIsNot(so.y_dinh(eid).trang_thai, TT.DONE)


# ---------------------------------------------------------------------------
# §B — VONG PHAN HOI CHAT LUONG
# ---------------------------------------------------------------------------

def _dx(ma="dx1", **kw) -> TN.DeXuat:
    d = {"project_id": PID, "message_id": 1, "tom_tat": "tách observer",
         "provider": "antigravity", "model": "m-manh",
         "runtime_id": "AG01", "tu_vai": "strategist"}
    d.update(kw)
    return TN.DeXuat(ma=ma, **d)


class Test03PhanHoi(unittest.TestCase):

    def setUp(self):
        self.kho = BenchmarkStore(_tmp() / "benchmark-reasoning.jsonl")

    def _ghi(self, y, bc, dx=None, **kw):
        qs = PH.dung_quan_sat(y, bc, de_xuat=dx if dx is not None else _dx(),
                              **kw)
        return PH.ghi_phan_hoi(self.kho, qs)

    def test_DAT_sinh_mot_quan_sat_GAN_DUOC_VAO_MODEL(self):
        y = _y()
        y.trang_thai = TT.DONE
        ra = self._ghi(y, _bc(KQ.TrangThaiXacMinh.DAT))
        self.assertIsNotNone(ra)
        r = self.kho.all()[-1]
        self.assertTrue(r.success)
        self.assertEqual(r.model_id, "m-manh")
        self.assertEqual(r.task_type, "ketqua_strategist")
        self.assertEqual(r.project, PID)

    def test_HONG_ghi_that_bai_chu_khong_bo_qua(self):
        y = _y()
        y.trang_thai = TT.FAILED
        y.so_lan_lap_lai = 2
        self._ghi(y, _bc(KQ.TrangThaiXacMinh.KHONG_DAT))
        r = self.kho.all()[-1]
        self.assertFalse(r.success)
        self.assertGreaterEqual(r.retry_count, 2)
        self.assertTrue(r.reassigned)

    def test_HUY_KHONG_sinh_mau_nao(self):
        """Người dùng đổi ý không đo được gì về chất lượng lời khuyên."""
        y = _y()
        y.trang_thai = TT.CANCELLED
        self.assertIsNone(self._ghi(y, _bc()))
        self.assertEqual(self.kho.all(), [])

    def test_cho_tham_quyen_cung_KHONG_sinh_mau(self):
        y = _y("deploy lên production")
        y.trang_thai = TT.WAITING_AUTHORITY
        self.assertIsNone(self._ghi(y, _bc()))

    def test_chi_TRO_CHUYEN_khong_gia_vo_mot_ket_qua(self):
        """Không có báo cáo kiểm định thì không có quan sát nào."""
        y = _y()
        y.trang_thai = TT.DONE
        self.assertIsNone(PH.dung_quan_sat(y, None, de_xuat=_dx()))

    def test_khong_truy_duoc_model_thi_KHONG_ghi_mau_vo_danh(self):
        y = _y()
        y.trang_thai = TT.DONE
        self.assertIsNone(
            PH.dung_quan_sat(y, _bc(), de_xuat=_dx(model="")))
        self.assertIsNone(PH.dung_quan_sat(y, _bc(), de_xuat=None))

    def test_SUY_GIAM_van_tinh_la_thanh_cong(self):
        """Thiếu model khác họ là thiếu sót HẠ TẦNG, không phải lỗi chiến lược."""
        y = _y()
        y.trang_thai = TT.DONE
        self._ghi(y, _bc(KQ.TrangThaiXacMinh.SUY_GIAM))
        self.assertTrue(self.kho.all()[-1].success)

    def test_KHONG_BIA_token_hay_tien(self):
        y = _y()
        y.trang_thai = TT.DONE
        self._ghi(y, _bc(), giay=12.5)
        r = self.kho.all()[-1]
        self.assertIsNone(r.tokens)
        self.assertIsNone(r.cost_usd)
        self.assertEqual(r.wall_seconds, 12.5)

    def test_phan_xu_REVIEWER_di_theo_quan_sat(self):
        y = _y()
        y.trang_thai = TT.DONE
        self._ghi(y, _bc(), phan_bien={"phan_xu": "ACCEPT"})
        self.assertEqual(self.kho.all()[-1].verdict, "ACCEPT")

    def test_NGUONG_MAU_giu_nguyen_KHONG_ha(self):
        self.assertEqual(MAU_TOI_THIEU, 3)
        y = _y()
        y.trang_thai = TT.DONE
        for _ in range(MAU_TOI_THIEU - 1):
            self._ghi(y, _bc())
        self.assertIsNone(PH.tom_tat(self.kho, model_id="m-manh"),
                          "chưa đủ mẫu mà đã tổng hợp")
        self._ghi(y, _bc())
        s = PH.tom_tat(self.kho, model_id="m-manh")
        self.assertIsNotNone(s)
        self.assertEqual(s["samples"], MAU_TOI_THIEU)

    def test_KHONG_tron_voi_lich_su_luot_vai(self):
        """Hai câu hỏi khác nhau thì hai con số khác nhau."""
        self.kho.record(Record(ts=1.0, task_type="reasoning_strategist",
                               provider="antigravity", model_id="m-manh",
                               runtime_id="AG01", wall_seconds=1.0,
                               success=True))
        y = _y()
        y.trang_thai = TT.DONE
        self._ghi(y, _bc())
        loai = {r.task_type for r in self.kho.all()}
        self.assertEqual(loai, {"reasoning_strategist", "ketqua_strategist"})


class Test04KhongDemTrung(unittest.TestCase):
    """Một lần thực thi = ĐÚNG MỘT quan sát, bền qua khởi động lại."""

    def test_ket_luan_chi_chay_mot_lan_nen_chi_mot_mau(self):
        from scripts.control_center.store import ControlStore as CS
        st = CS(_tmp() / "control.db")
        khoa = "exec:ex_1"
        self.assertFalse(st.da_bao_ket_qua(khoa, "DONE"))
        st.ghi_da_bao_ket_qua(khoa, "DONE", project_id=PID, message_id=1)
        # Nhip thu hai (hoac mot lan khoi dong lai) thay dau va BO QUA.
        self.assertTrue(st.da_bao_ket_qua(khoa, "DONE"))

    def test_dau_BEN_tren_dia_chu_khong_trong_RAM(self):
        goc = _tmp()
        from scripts.control_center.store import ControlStore as CS
        a = CS(goc / "control.db")
        a.ghi_da_bao_ket_qua("exec:ex_9", "DONE", project_id=PID)
        a.close()
        b = CS(goc / "control.db")           # "khoi dong lai"
        self.assertTrue(b.da_bao_ket_qua("exec:ex_9", "DONE"))


class Test07BuocDocKhongThanhViecGhi(unittest.TestCase):
    """`CheDoGhi.DOC` là một TUYÊN BỐ, không phải một gợi ý.

    Đo được trên Fanfic THẬT (2026-09-11): bước "đọc tài liệu bàn giao" khai
    `CheDoGhi.DOC` bị `_loai_viec_cua` xếp `documentation` (vì chữ "tài
    liệu"), thành một việc CÓ GHI, và cổng `diff` của Router V4 đánh hỏng ba
    lần liên tiếp với "báo ok cho một việc CÓ GHI nhưng không tệp nào đổi" —
    trong khi agent đã đọc đúng và tóm tắt đúng.
    """

    def _b(self, ma, tieu_de, muc_tieu, ghi=False):
        return KH.BuocKeHoach(buoc_id=ma, tieu_de=tieu_de, muc_tieu=muc_tieu,
                              che_do_ghi=KH.CheDoGhi.GHI if ghi
                              else KH.CheDoGhi.DOC)

    def test_buoc_DOC_luon_ra_loai_CHI_DOC(self):
        from scripts.control_center.engine import _loai_viec_cua
        from scripts.control_center.planner import _CHI_DOC
        for ten, muc in (
                ("đọc tài liệu bàn giao", "ĐỌC docs/HANDOFF.md và tóm tắt"),
                ("đọc cấu trúc bộ kiểm thử", "ĐỌC tests/ và tóm tắt"),
                ("đọc readme", "ĐỌC README.md"),
                ("khảo sát kho", "ĐỌC và tóm tắt")):
            with self.subTest(ten=ten):
                k = _loai_viec_cua(self._b("b", ten, muc))
                self.assertIn(k, _CHI_DOC, f"{ten} -> {k}")

    def test_buoc_GHI_van_ra_dung_loai_cu(self):
        from scripts.control_center.engine import _loai_viec_cua
        self.assertEqual(
            _loai_viec_cua(self._b("b", "viết tài liệu", "viết docs/X.md",
                                   ghi=True)), "documentation")
        self.assertEqual(
            _loai_viec_cua(self._b("b", "thêm bài kiểm", "viết test cho X",
                                   ghi=True)), "testing")
        self.assertEqual(
            _loai_viec_cua(self._b("b", "sửa store", "sửa scripts/store.py",
                                   ghi=True)), "implementation")

    def test_hop_dong_cua_buoc_DOC_KHONG_xin_repo_write(self):
        """Chứng cứ đi tới tận `TaskContract` — nơi cổng `diff` đọc."""
        from scripts.control_center.engine import _loai_viec_cua
        from scripts.control_center.planner import RulePlanner
        b = self._b("b", "đọc tài liệu bàn giao", "ĐỌC docs/HANDOFF.md")
        hd = RulePlanner(default_write_scope=("scripts",))._hop_dong(
            "t1", b.muc_tieu, _loai_viec_cua(b), (),
            cau_goc="ok làm đi", deps=())
        self.assertFalse(hd.requirements.repo_write)
        self.assertFalse(hd.execution.worktree_required)
        self.assertEqual(hd.allowed_scope, ())


class Test06TrienKhaiKhongPhaiDeploy(unittest.TestCase):
    """Một TỪ ĐƠN không được làm trọng tài — luật 22-24, nay cho cổng quyền.

    Đo được ở nghiệm thu thật V0.9: câu uỷ quyền tiếng Việt tự nhiên
    "ok triển khai phần repo-local đó đi" bị xếp `production_deploy`, nên
    KHÔNG CÒN cách nào cho phép một việc trong kho bằng tiếng Việt.
    """

    REPO_LOCAL = (
        "ok triển khai phần repo-local đó đi",
        "triển khai hướng đó",
        "triển khai tính năng tìm kiếm",
        "ok trien khai phan do di",
        "triển khai lại bộ kiểm thử cho gọn",
    )
    VAN_GATED = (
        "triển khai lên production",
        "triển khai worker mới",
        "triển khai bản mới lên máy chủ",
        "trien khai len prod",
        "triển khai fanfic.world",
        "deploy the web",
        "npm run cf:deploy:production",
        "wrangler deploy",
        "cutover sang hạ tầng mới",
        "đẩy lên prod",
    )

    def test_trien_khai_repo_local_KHONG_bi_gated(self):
        from scripts.control_center import permissions as P
        for c in self.REPO_LOCAL:
            with self.subTest(cau=c):
                self.assertEqual(P.classify(c), P.PermissionClass.AUTO, c)

    def test_deploy_THAT_van_bi_gated(self):
        from scripts.control_center import permissions as P
        for c in self.VAN_GATED:
            with self.subTest(cau=c):
                self.assertEqual(P.classify(c), P.PermissionClass.GATED, c)

    def test_y_dinh_repo_local_KHONG_cho_tham_quyen(self):
        y = YD.tao_y_dinh(project_id=PID,
                          goal="dọn nợ kỹ thuật ở scripts/",
                          cau_nguoi_dung="ok triển khai phần repo-local đó đi")
        self.assertIs(y.tham_quyen, YD.LopThamQuyen.REPO_LOCAL)
        self.assertFalse(y.can_tham_quyen_moi)

    def test_y_dinh_cham_production_VAN_cho_tham_quyen(self):
        y = YD.tao_y_dinh(project_id=PID, goal="triển khai lên production",
                          cau_nguoi_dung="ok làm đi")
        self.assertIs(y.tham_quyen, YD.LopThamQuyen.NGOAI)
        self.assertTrue(y.tac_dong_production)


class Test05DeXuatMangNguonGoc(unittest.TestCase):

    def test_so_giu_provider_model_cua_de_xuat(self):
        so = _so()
        so.luu_de_xuat(_dx("dx7"))
        d = so.de_xuat_theo_ma("dx7")
        self.assertEqual((d.provider, d.model, d.runtime_id),
                         ("antigravity", "m-manh", "AG01"))

    def test_ma_la_thi_tra_None(self):
        self.assertIsNone(_so().de_xuat_theo_ma("khong_co"))


if __name__ == "__main__":                      # pragma: no cover
    unittest.main(verbosity=2)
