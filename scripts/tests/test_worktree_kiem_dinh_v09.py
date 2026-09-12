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


if __name__ == "__main__":
    unittest.main()
