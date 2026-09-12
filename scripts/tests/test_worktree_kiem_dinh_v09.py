# -*- coding: utf-8 -*-
"""BẤT BIẾN: một bước được chấm trong CÂY CỦA CHÍNH NÓ, không phải cây anh em.

Khuyết tật đo được trên Fanfic thật (`ex_8cb881f8d88e`, 2026-09-12):

* hai bước GHI song song, hai worktree cô lập, cả hai `DONE`;
* sổ bước của từng bước ghi `xac_minh=DAT` kèm `TEP_TON_TAI: CÓ`;
* nhưng `kiem_dinh_thuc_thi` chấm LẠI từng bước mà chỉ đưa xuống MỘT môi
  giới — cái của bước ĐẦU TIÊN nó gặp;
* nên bước kia bị chấm trong cây của anh em, không thấy tệp của mình, và bị
  kết luận HỎNG;
* lần thực thi đi thẳng tới `BLOCKED` với lý do *"kiểm định không đạt nhưng
  không xác định được thứ gì để sửa"* — thật sự chẳng có gì hỏng để sửa.

`moi_gioi_khac` ĐÃ được thu thập đúng ở `dieu_phoi.py` và `_cham_tieu_chi`
đã dùng nó đúng; chỉ đường xuống `kiem_dinh_buoc` là bị đứt.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List

from scripts.control_center.execution import ke_hoach as KH
from scripts.control_center.execution import kiem_dinh as KD
from scripts.control_center.execution import ket_qua as KQ
from scripts.control_center.execution import y_dinh as YD

TEP_A = "docs/reports/_a.md"
TEP_B = "docs/reports/_b.md"


def _cay(ten: str, tep: str = "") -> Path:
    d = Path(tempfile.mkdtemp(prefix=f"wt-{ten}-"))
    if tep:
        p = d / tep
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {ten}\nV09-OK\n", encoding="utf-8")
    return d


def _buoc_ghi(ma: str, tep: str) -> KH.BuocKeHoach:
    return KH.BuocKeHoach(
        buoc_id=ma, tieu_de=ma, muc_tieu=f"ghi {tep}",
        che_do_ghi=KH.CheDoGhi.GHI,
        artifact_mong_doi=(tep,),
        cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": tep}),))


def _kq_ghi(ma: str, tep: str, cay: Path) -> KQ.HopDongKetQua:
    return KQ.HopDongKetQua(
        task_id=f"t.{ma}", buoc_id=ma, status="ok",
        summary=f"đã tạo {tep}", files_changed=(tep,), artifacts=(tep,),
        worktree=str(cay))


class TestHaiWorktreeAnhEm(unittest.TestCase):
    """Hai bước GHI song song, hai cây — không bên nào được chấm nhầm cây."""

    def setUp(self):
        self.a = _cay("A", TEP_A)          # bước A ghi tệp A trong cây A
        self.b = _cay("B", TEP_B)          # bước B ghi tệp B trong cây B
        self.mg_a = KD.MoiGioiKiem(str(self.a))
        self.mg_b = KD.MoiGioiKiem(str(self.b))
        self.y = YD.tao_y_dinh(project_id="demo", goal="viết hai ghi chú",
                               cau_nguoi_dung="viết hai ghi chú")
        self.kh = KH.KeHoachThucThi(
            execution_id=self.y.execution_id,
            buoc=(_buoc_ghi("a", TEP_A), _buoc_ghi("b", TEP_B)),
            nghiem_thu=(
                KH.TieuChiNghiemThu(
                    mo_ta=f"{TEP_A} tồn tại",
                    cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_A}),)),
                KH.TieuChiNghiemThu(
                    mo_ta=f"{TEP_B} tồn tại",
                    cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_B}),)),
            ))
        self.kqb = {"a": _kq_ghi("a", TEP_A, self.a),
                    "b": _kq_ghi("b", TEP_B, self.b)}

    def tearDown(self):
        for d in (self.a, self.b):
            shutil.rmtree(d, ignore_errors=True)

    def _cham(self, dau: str = "b"):
        """Chấm cả lần thực thi. `dau` = môi giới CHUNG được truyền xuống.

        Đặt mặc định là cây B để tái hiện đúng cảnh đã hỏng: bước `a` bị chấm
        trong cây của `b`.
        """
        chinh = self.mg_b if dau == "b" else self.mg_a
        return KD.kiem_dinh_thuc_thi(
            self.y, self.kh, self.kqb,
            moi_gioi=chinh, moi_gioi_khac=[self.mg_a, self.mg_b])

    # -- bất biến chính ----------------------------------------------------
    def test_01_khong_buoc_nao_HONG_vi_nhin_nham_cay(self):
        for dau in ("a", "b"):
            with self.subTest(moi_gioi_chung=dau):
                bc = self._cham(dau)
                self.assertEqual(sorted(bc.buoc_hong), [], bc.ly_do)
                self.assertEqual(sorted(bc.buoc_dat), ["a", "b"])

    def test_02_lan_thuc_thi_DAT(self):
        bc = self._cham("b")
        self.assertIs(bc.trang_thai, KQ.TrangThaiXacMinh.DAT, bc.ly_do)
        self.assertTrue(bc.dat)

    def test_03_tieu_chi_gop_thay_ca_A_lan_B(self):
        """Tiêu chí của cả lần thực thi nhìn HỢP của các cây."""
        bc = self._cham("b")
        for t in bc.tieu_chi:
            self.assertIs(t.trang_thai, KQ.TrangThaiXacMinh.DAT,
                          f"{t.mo_ta}: {t.ghi_chu}")

    def test_04_NGUON_GOC_chi_ra_dung_cay_da_cho_bang_chung(self):
        """Phán quyết phải tự giải thích được: bằng chứng đến TỪ CÂY NÀO."""
        tt_a, ds_a = KD.kiem_dinh_buoc(
            self.kh.buoc[0], self.kqb["a"],
            moi_gioi=self.mg_a, khac=[self.mg_b])
        self.assertIs(tt_a, KQ.TrangThaiXacMinh.DAT)
        tep = [k for k in ds_a if k.cach == KH.CachKiem.TEP_TON_TAI.value]
        self.assertTrue(tep, "không có phép kiểm TEP_TON_TAI nào")
        self.assertEqual(Path(tep[0].nguon).resolve(), self.a.resolve(),
                         "bằng chứng bị gán cho cây SAI")

    def test_05_cay_cua_CHINH_no_duoc_thu_TRUOC(self):
        """Không được phẳng hoá: cây riêng thắng, kể cả khi cây kia cũng có."""
        # Cho cây B cũng có tệp A -> nếu thứ tự sai, nguồn gốc sẽ trỏ B.
        p = self.b / TEP_A
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("bản sao ở cây anh em\n", encoding="utf-8")
        _, ds = KD.kiem_dinh_buoc(self.kh.buoc[0], self.kqb["a"],
                                  moi_gioi=self.mg_a, khac=[self.mg_b])
        tep = [k for k in ds if k.cach == KH.CachKiem.TEP_TON_TAI.value]
        self.assertEqual(Path(tep[0].nguon).resolve(), self.a.resolve())

    # -- vế ÂM: không được nới lỏng ----------------------------------------
    def test_06_thieu_hien_vat_o_MOI_cay_duoc_phep_thi_VAN_HONG(self):
        """Đường lui là ĐÓNG — chỉ các cây của lần thực thi này."""
        (self.a / TEP_A).unlink()
        bc = self._cham("a")
        self.assertIn("a", bc.buoc_hong, bc.ly_do)
        self.assertIsNot(bc.trang_thai, KQ.TrangThaiXacMinh.DAT)

    def test_07_KHONG_quet_thu_muc_tuy_y(self):
        """Tệp nằm ở một cây KHÔNG thuộc lần thực thi thì không được tính."""
        ngoai = _cay("NGOAI", TEP_A)
        try:
            (self.a / TEP_A).unlink()
            bc = KD.kiem_dinh_thuc_thi(
                self.y, self.kh, self.kqb,
                moi_gioi=self.mg_a,
                moi_gioi_khac=[self.mg_a, self.mg_b])   # KHÔNG có `ngoai`
            self.assertIn("a", bc.buoc_hong)
        finally:
            shutil.rmtree(ngoai, ignore_errors=True)

    def test_08_mot_buoc_khong_co_worktree_van_cham_duoc(self):
        """Bước chỉ đọc / chưa ghi cây: rơi về môi giới chung, không nổ."""
        self.kqb["a"] = KQ.HopDongKetQua(
            task_id="t.a", buoc_id="a", status="ok", summary="đã tạo",
            files_changed=(TEP_A,), artifacts=(TEP_A,), worktree="")
        bc = self._cham("a")
        self.assertEqual(sorted(bc.buoc_dat), ["a", "b"], bc.ly_do)


#: Gốc mã SẢN XUẤT — bài kiểm không tự soi chính mình.
GOC_MA = Path(__file__).resolve().parents[1]


def _tep_san_xuat():
    for p in GOC_MA.rglob("*.py"):
        d = p.as_posix()
        if "/tests/" in d or "/__pycache__/" in d:
            continue
        yield p


class TestDuMoiChoGoi(unittest.TestCase):
    """MỌI chỗ gọi kiểm định mức-lần-chạy phải dùng CÙNG một bối cảnh.

    Khuyết tật này đã trượt qua tôi HAI lần ở hai chỗ khác nhau, và mỗi lần
    là một bước ĐÃ ĐẠT bị chấm lại trong cây anh em rồi kết luận HỎNG:

    * `dieu_phoi` chấm LẠI sau phán xử Reviewer (`ex_77828ea9f708`, thật):
      lần chấm đầu đúng, Reviewer trả `REVISE`, rồi lần chấm lại báo
      *"1 bước hỏng: ghi_tailieu"* — một bước vừa `STEP_VERIFIED DAT` vài
      giây trước; sau đó sửa chữa + lập lại kế hoạch hai vòng rồi `FAILED`;
    * `engine` chấm lúc KẾT LUẬN để ghi KÝ ỨC và vòng phản hồi chất lượng —
      sai ở đây thì một phán quyết sai được LƯU LẠI vĩnh viễn.

    Nên bài kiểm không kiểm "hai chỗ tôi nhớ", mà quét TOÀN BỘ mã sản xuất
    bằng AST: một chỗ gọi thứ tư trong tương lai cũng bị bắt.
    """

    def _goi(self, ten: str):
        """Mọi lời gọi `ten(...)` trong mã sản xuất -> (tệp, dòng, node)."""
        import ast
        ra = []
        for p in _tep_san_xuat():
            try:
                cay = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(cay):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                nom = (f.attr if isinstance(f, ast.Attribute)
                       else getattr(f, "id", ""))
                if nom == ten:
                    ra.append((p, n.lineno, n))
        return ra

    def test_09_moi_cho_goi_kiem_dinh_thuc_thi_deu_co_moi_gioi_khac(self):
        thieu = [f"{p.relative_to(GOC_MA).as_posix()}:{d}"
                 for p, d, n in self._goi("kiem_dinh_thuc_thi")
                 if not any(k.arg == "moi_gioi_khac" for k in n.keywords)]
        self.assertEqual(
            thieu, [],
            "chỗ gọi `kiem_dinh_thuc_thi` thiếu `moi_gioi_khac` — bước ở cây "
            "anh em sẽ bị chấm HỎNG: " + ", ".join(thieu))

    def test_10_co_it_nhat_BA_cho_goi_duoc_phu(self):
        """Lưới an toàn cho chính bài kiểm trên.

        Nếu một lần tái cấu trúc làm AST không còn thấy lời gọi nào, bài kiểm
        kia sẽ XANH một cách vô nghĩa. Ba đường phải còn: chấm đầu, chấm lại
        sau Reviewer, và chấm lúc kết luận.
        """
        self.assertGreaterEqual(len(self._goi("kiem_dinh_thuc_thi")), 3)

    def test_11_boi_canh_den_TU_HELPER_chinh_tac(self):
        """Không chỗ nào được tự dựng lại bộ môi giới bằng tay.

        Ba chỗ từng cần nó và hai chỗ đã quên — nên phép dựng phải nằm ở MỘT
        nơi (`BoDieuPhoi.canh_kiem`), và mọi chỗ gọi phải lấy từ đó.
        """
        import ast
        xau = []
        for p, d, n in self._goi("kiem_dinh_thuc_thi"):
            try:
                cay = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            # Hàm bao quanh lời gọi này có gọi `canh_kiem` không?
            bao = None
            for h in ast.walk(cay):
                if isinstance(h, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if h.lineno <= d <= (h.end_lineno or d):
                        if bao is None or h.lineno > bao.lineno:
                            bao = h
            if bao is None:
                continue
            if bao.name == "canh_kiem":
                continue
            co = any(isinstance(x, ast.Call)
                     and (getattr(x.func, "attr", "")
                          or getattr(x.func, "id", "")) == "canh_kiem"
                     for x in ast.walk(bao))
            if not co:
                xau.append(f"{p.relative_to(GOC_MA).as_posix()}:{d}"
                           f" (trong {bao.name})")
        self.assertEqual(
            xau, [],
            "chỗ gọi dựng bối cảnh kiểm định bằng tay thay vì qua "
            "`canh_kiem()`: " + ", ".join(xau))

    def test_12_kiem_dinh_buoc_o_tang_BUOC_chi_nhin_cay_CUA_NO(self):
        """Vế đối xứng — KHÔNG được nới cho tầng bước.

        Ở mức BƯỚC, "tệp của tôi có chưa" phải được hỏi trong cây của CHÍNH
        nó. Cho nó nhìn cây anh em là mở đường cho một bước không ghi gì vẫn
        ĐẠT nhờ tệp trùng tên do bước khác tạo.
        """
        import ast
        from scripts.control_center.execution import dieu_phoi as DP
        src = Path(DP.__file__).read_text(encoding="utf-8")
        cay = ast.parse(src)
        thay = 0
        for n in ast.walk(cay):
            if (isinstance(n, ast.Call)
                    and (getattr(n.func, "attr", "")
                         or getattr(n.func, "id", "")) == "kiem_dinh_buoc"):
                thay += 1
                self.assertFalse(
                    any(k.arg == "khac" for k in n.keywords),
                    f"dieu_phoi:{n.lineno} — kiểm định MỨC BƯỚC không được "
                    f"nhìn cây anh em")
        self.assertGreaterEqual(thay, 1, "không còn chỗ gọi nào để kiểm")


class TestChamLaiSauReviewer(unittest.TestCase):
    """Đường CHẤM LẠI sau phán xử Reviewer — đúng đường đã hỏng thật.

    `ex_77828ea9f708`: hai bước GHI song song ở hai cây, cả hai
    `STEP_VERIFIED DAT`; Reviewer trả `REVISE`; lần chấm LẠI báo
    *"1 bước hỏng: ghi_tailieu"*. Bài kiểm này dựng đúng hình dạng đó với một
    Reviewer GIẢ — không model, không mạng.
    """

    def setUp(self):
        from scripts.control_center.execution.dieu_phoi import BoDieuPhoi
        from scripts.control_center.execution.so import SoThucThi
        from scripts.control_center.store import ControlStore

        self.a = _cay("A", TEP_A)
        self.b = _cay("B", TEP_B)
        self.goc = Path(tempfile.mkdtemp(prefix="cham-lai-"))
        self.so = SoThucThi(ControlStore(self.goc / "control.db"))

        self.y = YD.tao_y_dinh(project_id="demo", goal="viết hai ghi chú",
                               cau_nguoi_dung="viết hai ghi chú")
        self.kh = KH.KeHoachThucThi(
            execution_id=self.y.execution_id,
            buoc=(_buoc_ghi("a", TEP_A), _buoc_ghi("b", TEP_B)),
            nghiem_thu=(
                KH.TieuChiNghiemThu(
                    mo_ta=f"{TEP_A} tồn tại",
                    cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_A}),)),
                KH.TieuChiNghiemThu(
                    mo_ta=f"{TEP_B} tồn tại",
                    cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP_B}),)),
                # Tiêu chí NGỮ NGHĨA -> buộc bộ điều phối gọi Reviewer.
                KH.TieuChiNghiemThu(
                    mo_ta="hai ghi chú có đủ cho người đọc không",
                    bat_buoc=False),
            ))
        self.phan_xu = {"phan_xu": "REVISE", "doc_lap": True,
                        "suy_giam": False, "provider": "gia",
                        "model": "gia", "ly_do": "cần rõ hơn"}
        self.goi: List[str] = []          # Reviewer ĐÃ được gọi chưa?

        def _reviewer(*a, **k):
            self.goi.append("x")
            return dict(self.phan_xu)

        self.dp = BoDieuPhoi(
            self.so,
            tao_viec=lambda *a: "t",
            trang_thai_viec=lambda t: "DONE",
            moi_gioi=KD.MoiGioiKiem(str(self.b)),   # cây "chung" = B
            goi_phan_bien=_reviewer)
        self.dp.bat_dau(self.y, self.kh)
        for ma, tep, cay in (("a", TEP_A, self.a), ("b", TEP_B, self.b)):
            self.so.luu_buoc(self.y.execution_id, self.kh.phien_ban, ma,
                             ket_qua=_kq_ghi(ma, tep, cay),
                             state="XONG",
                             xac_minh=KQ.TrangThaiXacMinh.DAT)

    def tearDown(self):
        for d in (self.a, self.b, self.goc):
            shutil.rmtree(d, ignore_errors=True)

    # `chi_doc=True` KHÔNG gọi Reviewer (docstring của `kiem_dinh` nói rõ),
    # nên nó KHÔNG chạm đường chấm lại. Phải gọi đường THẬT.
    def _cham_that(self):
        bc = self.dp.kiem_dinh(self.y.execution_id)
        self.assertTrue(self.goi, "Reviewer chưa từng được gọi — bài kiểm "
                                  "không chạm đường chấm lại")
        return bc

    def test_13_cham_lai_sau_REVISE_khong_bia_ra_buoc_hong(self):
        bc = self._cham_that()
        self.assertIsNotNone(bc)
        self.assertEqual(sorted(bc.buoc_hong), [], bc.ly_do)
        self.assertEqual(sorted(bc.buoc_dat), ["a", "b"], bc.ly_do)

    def test_14_bang_chung_van_tu_dung_cay_sau_khi_cham_lai(self):
        bc = self._cham_that()
        thay = 0
        for t in bc.tieu_chi:
            for k in t.kiem:
                d = str(k.tham_so.get("duong") or "")
                if not k.nguon or not d:
                    continue
                mong = self.a if d == TEP_A else self.b if d == TEP_B else None
                if mong is not None:
                    thay += 1
                    self.assertEqual(Path(k.nguon).resolve(), mong.resolve(),
                                     f"{t.mo_ta}: bằng chứng từ cây SAI")
        self.assertGreaterEqual(thay, 2, "không thấy bằng chứng có nguồn gốc")

    def test_15_ACCEPT_cung_khong_doi_phan_quyet_tat_dinh(self):
        """Reviewer nói ACCEPT cũng không được biến một bước hỏng thành đạt."""
        self.phan_xu["phan_xu"] = "ACCEPT"
        (self.a / TEP_A).unlink()
        bc = self.dp.kiem_dinh(self.y.execution_id)
        self.assertIn("a", bc.buoc_hong, bc.ly_do)


if __name__ == "__main__":
    unittest.main()
