# -*- coding: utf-8 -*-
"""THẨM QUYỀN của tiêu chí phải NHẤT QUÁN, tất định hay ngữ nghĩa cũng vậy.

Mâu thuẫn đo được (`ex_181f8dd29fbe`, Fanfic thật, 2026-09-12):

* một tiêu chí TẤT ĐỊNH khai `bat_buoc=False` mà hỏng thì KHÔNG chặn được gì
  — `_tong_hop` lọc `bb = [t for t in cham if t.bat_buoc]`;
* nhưng một tiêu chí NGỮ NGHĨA khai `bat_buoc=False` lại chặn được CẢ lần
  thực thi, vì phán xử Reviewer bị áp TOÀN CỤC: `REVISE` -> `THIEU_BANG_CHUNG`
  -> `REPLANNING` -> `BLOCKED`.

Cùng một mức thẩm quyền khai báo, hai cách đối xử. Lần chạy thật: hai tiêu
chí BẮT BUỘC đều ĐẠT, cả hai bước `DONE`, và lần thực thi vẫn `BLOCKED` vì
một tiêu chí "nên có".

Bất biến: **tiêu chí TUỲ CHỌN không có quyền chặn**, bất kể nó được chấm
bằng máy hay bằng phán đoán ngữ nghĩa. Ngoại lệ DUY NHẤT là một phát hiện
AN TOÀN/TOÀN VẸN độc lập.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from scripts.control_center.execution import ke_hoach as KH
from scripts.control_center.execution import kiem_dinh as KD
from scripts.control_center.execution import ket_qua as KQ
from scripts.control_center.execution import y_dinh as YD

TT = KQ.TrangThaiXacMinh
TEP = "docs/reports/_n.md"


def _cay(tep: str = TEP) -> Path:
    d = Path(tempfile.mkdtemp(prefix="tq-"))
    if tep:
        p = d / tep
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# ghi chú\nV09-OK\n", encoding="utf-8")
    return d


def _tc_tat_dinh(mo: str, *, bat_buoc: bool, duong: str = TEP):
    return KH.TieuChiNghiemThu(
        mo_ta=mo, bat_buoc=bat_buoc,
        cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": duong}),))


def _tc_ngu_nghia(mo: str, *, bat_buoc: bool):
    return KH.TieuChiNghiemThu(mo_ta=mo, bat_buoc=bat_buoc, cach_kiem=())


def _pb(px: str, ly: str = "chưa đủ tốt", doc_lap: bool = True) -> Dict:
    return {"phan_xu": px, "doc_lap": doc_lap, "suy_giam": False,
            "provider": "gia", "model": "gia", "ly_do": ly}


class _Nen(unittest.TestCase):
    """Nền chung: một bước GHI đã ĐẠT, một cây thật."""

    def setUp(self):
        self.cay = _cay()
        self.mg = KD.MoiGioiKiem(str(self.cay))
        self.y = YD.tao_y_dinh(project_id="demo", goal="viết một ghi chú",
                               cau_nguoi_dung="viết một ghi chú")

    def tearDown(self):
        shutil.rmtree(self.cay, ignore_errors=True)

    def _cham(self, *tieu_chi, phan_bien: Optional[Dict] = None,
              tep_con: bool = True):
        if not tep_con:
            (self.cay / TEP).unlink()
        b = KH.BuocKeHoach(
            buoc_id="a", tieu_de="a", muc_tieu="ghi",
            che_do_ghi=KH.CheDoGhi.GHI, artifact_mong_doi=(TEP,),
            cach_kiem=((KH.CachKiem.TEP_TON_TAI, {"duong": TEP}),))
        kh = KH.KeHoachThucThi(execution_id=self.y.execution_id, buoc=(b,),
                               nghiem_thu=tuple(tieu_chi))
        kq = KQ.HopDongKetQua(
            task_id="t.a", buoc_id="a", status="ok", summary="đã tạo",
            files_changed=(TEP,), artifacts=(TEP,), worktree=str(self.cay))
        return KD.kiem_dinh_thuc_thi(self.y, kh, {"a": kq}, moi_gioi=self.mg,
                                     moi_gioi_khac=[self.mg],
                                     phan_bien=phan_bien)


class TestTatDinh(_Nen):
    """1–2: đường TẤT ĐỊNH — chuẩn để so sánh."""

    def test_01_BAT_BUOC_tat_dinh_hong_thi_CHAN(self):
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        tep_con=False)
        self.assertIs(bc.trang_thai, TT.KHONG_DAT)
        self.assertFalse(bc.dat)

    def test_02_TUY_CHON_tat_dinh_hong_thi_KHONG_chan(self):
        # Bước vẫn ĐẠT (tệp của nó có); chỉ TIÊU CHÍ tuỳ chọn trỏ một tệp
        # KHÁC không tồn tại — để cô lập đúng thứ đang đo là thẩm quyền của
        # tiêu chí, không phải sức khoẻ của bước.
        bc = self._cham(_tc_tat_dinh("tệp phụ nên có", bat_buoc=False,
                                     duong="docs/reports/_khong_co.md"))
        self.assertEqual(bc.buoc_hong, (), bc.ly_do)
        self.assertTrue(bc.dat, f"tiêu chí NÊN CÓ đã chặn: {bc.ly_do}")


class TestNguNghia(_Nen):
    """3–6: đường NGỮ NGHĨA phải theo ĐÚNG luật thẩm quyền đó."""

    def test_03_BAT_BUOC_REVISE_thi_chua_dat(self):
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("nội dung có đúng không", bat_buoc=True),
                        phan_bien=_pb("REVISE"))
        self.assertIs(bc.trang_thai, TT.THIEU_BANG_CHUNG)
        self.assertFalse(bc.dat)

    def test_04_BAT_BUOC_REJECT_thi_CHAN(self):
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("nội dung có đúng không", bat_buoc=True),
                        phan_bien=_pb("REJECT"))
        self.assertIs(bc.trang_thai, TT.KHONG_DAT)
        self.assertFalse(bc.dat)

    def test_05_TUY_CHON_REVISE_thi_SUY_GIAM_khong_chan(self):
        """Đây CHÍNH LÀ hình dạng đã làm hỏng Scenario C."""
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("ghi chú có hữu ích không",
                                      bat_buoc=False),
                        phan_bien=_pb("REVISE"))
        self.assertIs(bc.trang_thai, TT.SUY_GIAM, bc.ly_do)
        self.assertTrue(bc.dat, "tiêu chí NÊN CÓ vẫn chặn được — bất biến vỡ")

    def test_06_TUY_CHON_REJECT_cung_KHONG_chan(self):
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("ghi chú có hữu ích không",
                                      bat_buoc=False),
                        phan_bien=_pb("REJECT"))
        self.assertIs(bc.trang_thai, TT.SUY_GIAM, bc.ly_do)
        self.assertTrue(bc.dat)


class TestAnToanVanChan(_Nen):
    """7: ngoại lệ DUY NHẤT — an toàn/toàn vẹn luôn thắng."""

    def test_07_TUY_CHON_nhung_neu_la_AN_TOAN_thi_CHAN(self):
        bc = self._cham(
            _tc_tat_dinh("tệp phải có", bat_buoc=True),
            _tc_ngu_nghia("tài liệu có hay không", bat_buoc=False),
            phan_bien=_pb("REVISE",
                          "bản vá xoá credential production trong .env"))
        self.assertIs(bc.trang_thai, TT.KHONG_DAT, bc.ly_do)
        self.assertFalse(bc.dat)
        self.assertTrue(any(p.pham_vi is KD.PhamViPhanXu.AN_TOAN
                            for p in bc.phat_hien))

    def test_07b_chuoi_vo_hai_KHONG_bi_coi_la_an_toan(self):
        """Danh sách AN TOÀN phải HẸP — không bắt nhầm lời chê thường."""
        bc = self._cham(
            _tc_tat_dinh("tệp phải có", bat_buoc=True),
            _tc_ngu_nghia("tài liệu có hay không", bat_buoc=False),
            phan_bien=_pb("REVISE", "ghi chú hơi ngắn, nên thêm ví dụ"))
        self.assertTrue(bc.dat, bc.ly_do)


class TestKetQuaVaCanhBao(_Nen):
    """8 + 12: xong-nhưng-suy-giảm, và lời chê KHÔNG được biến mất."""

    def test_08_bat_buoc_dat_cong_TUY_CHON_REVISE_la_ket_thuc_THANH_CONG(self):
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("hữu ích không", bat_buoc=False),
                        phan_bien=_pb("REVISE"))
        self.assertTrue(bc.dat)
        self.assertIs(bc.trang_thai, TT.SUY_GIAM)

    def test_12_loi_che_duoc_GIU_LAI_nguyen_van(self):
        ly = "nội dung chưa nói rõ bước tiếp theo cho người đọc"
        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("hữu ích không", bat_buoc=False),
                        phan_bien=_pb("REVISE", ly))
        self.assertTrue(bc.canh_bao, "cảnh báo bị nuốt mất")
        self.assertIn(ly[:30], bc.ly_do + " " + " ".join(
            p.ly_do for p in bc.canh_bao))
        self.assertIn("cảnh báo", bc.render().lower())
        # Và nó phải đi được vào ký ức / sổ dưới dạng dữ liệu.
        self.assertTrue(bc.to_dict()["canh_bao"])


class TestVongPhanHoi(_Nen):
    """12b: lịch sử chất lượng phải ghi ĐÚNG kết quả suy giảm.

    Không được làm tròn theo cả hai hướng: không ghi "hỏng" cho một lần thực
    thi đã đạt mọi tiêu chí bắt buộc, và cũng không ghi "đạt hoàn hảo" cho
    một lần bị Reviewer chê.
    """

    def test_12b_lich_su_ghi_thanh_cong_NHUNG_giu_nhan_SUY_GIAM(self):
        from scripts.control_center.execution import phan_hoi as PH
        from scripts.control_center.execution.tiep_noi import DeXuat

        bc = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("hữu ích không", bat_buoc=False),
                        phan_bien=_pb("REVISE"))
        qs = PH.dung_quan_sat(
            self.y, bc,
            de_xuat=DeXuat(ma="dx1", project_id="demo", message_id="m1",
                           tom_tat="viết một ghi chú", tu_vai="strategist",
                           provider="gia", model="gia-1", runtime_id="R1"),
            phan_bien=_pb("REVISE"))
        self.assertIsNotNone(qs)
        self.assertTrue(qs.thanh_cong, "ghi HỎNG cho một lần đã đạt mọi tiêu "
                                       "chí bắt buộc")
        self.assertEqual(qs.xac_minh, "SUY_GIAM",
                         "nhãn suy giảm bị làm tròn thành đạt hoàn hảo")
        self.assertEqual(qs.phan_xu, "REVISE")


class TestQuyTrachNhiem(_Nen):
    """9–10: lời chê KHUNG BÁO CÁO không được tính cho agent."""

    def test_10_che_KHUNG_BAO_CAO_khong_thanh_worker_that_bai(self):
        bc = self._cham(
            _tc_tat_dinh("tệp phải có", bat_buoc=True),
            _tc_ngu_nghia("hữu ích không", bat_buoc=True),   # BẮT BUỘC!
            phan_bien=_pb("REVISE",
                          "Câu “BƯỚC CHƯA CHỨNG MINH: (không)” mâu thuẫn với "
                          "dòng [THIEU_BANG_CHUNG] ngay trên"))
        rt = [p for p in bc.phat_hien
              if p.nguon is KD.NguonPhatHien.ROUTER_PACKET]
        self.assertTrue(rt, "không nhận ra lời chê nhắm vào gói tin Router")
        self.assertFalse(rt[0].chan_duoc,
                         "lời chê gói tin của Router lại chặn được worker")

    def test_09_goi_tin_phan_biet_sieu_du_lieu_Router_voi_hien_vat_agent(self):
        """Gói tin phải NÓI RÕ mục nào do ai sinh."""
        import inspect
        from scripts.control_center import engine as EN
        src = inspect.getsource(EN.ControlCenter._phan_bien_ket_qua)
        for muc in ("MỤC TIÊU GỐC", "TIÊU CHÍ NGHIỆM THU",
                    "HIỆN VẬT DO AGENT TẠO", "BẰNG CHỨNG THỰC THI",
                    "SIÊU DỮ LIỆU CỦA ROUTER"):
            self.assertIn(muc, src, f"gói tin thiếu mục {muc!r}")
        # Mâu thuẫn cũ phải được GIẢI THÍCH, không phải giấu đi: gói tin nói
        # rõ "bước" và "tiêu chí" là hai thứ khác nhau.
        self.assertIn("HAI thứ khác nhau", src)
        # Và nhãn cũ không còn được in ở mục trông như lời khai của agent —
        # nó nằm dưới mục SIÊU DỮ LIỆU CỦA ROUTER.
        i_rt = src.find("SIÊU DỮ LIỆU CỦA ROUTER")
        i_bu = src.find("bước chưa chứng minh được")
        self.assertGreater(i_bu, i_rt,
                           "dòng trạng thái bước vẫn nằm ngoài mục siêu dữ "
                           "liệu của Router")


class TestKhongDeQuyPhanXu(_Nen):
    """11: chấm lại không được biến một kết quả BẮT BUỘC đạt thành BLOCKED."""

    def test_11_cham_lai_voi_phan_xu_khong_ha_cap_ket_qua_bat_buoc(self):
        khong = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                           _tc_ngu_nghia("hữu ích không", bat_buoc=False))
        co = self._cham(_tc_tat_dinh("tệp phải có", bat_buoc=True),
                        _tc_ngu_nghia("hữu ích không", bat_buoc=False),
                        phan_bien=_pb("REVISE"))
        # Trước: không phán xử -> THIEU_BANG_CHUNG (chưa ai chấm ngữ nghĩa).
        # Sau: có phán xử REVISE trên tiêu chí TUỲ CHỌN -> vẫn phải ĐẠT.
        self.assertTrue(co.dat,
                        f"chấm lại đã hạ cấp kết quả: {khong.trang_thai.value}"
                        f" -> {co.trang_thai.value}")


if __name__ == "__main__":
    unittest.main()
