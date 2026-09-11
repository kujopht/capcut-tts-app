"""Bài kiểm §16 — RÀNG BUỘC quan trọng KHÔNG bị đẩy ra khỏi ngữ cảnh Reviewer.

KHUYẾT TẬT ĐƯỢC SỬA, đo ở nghiệm thu model thật của V0.8: gói Reviewer dùng
2724/3400 token, các khối `vien_nang`/`ky_uc`/`trang_thai_kho` bị cắt, và một
ràng buộc dự án không xác minh được.

YÊU CẦU §16 CẤM cách sửa hiển nhiên (*"Do NOT simply raise context limits
globally"*), nên mọi bài kiểm ở đây chạy với ĐÚNG trần của `vai.HO_SO_VAI` —
không bài nào được nâng trần để đạt.

Bài kiểm chốt là `test_ban_chien_luoc_KHONG_lan_at_rang_buoc`: một bản chiến
lược đủ dài để ăn hết ngân sách vẫn KHÔNG đẩy được khối ràng buộc ra ngoài.
"""
from __future__ import annotations

import unittest
from typing import Dict, List

from scripts.control_center.memory.model import uoc_token
from scripts.control_center.reasoning import ngu_canh as NC
from scripts.control_center.reasoning import rang_buoc as RB
from scripts.control_center.reasoning.vai import VaiTro, ho_so

PID = "fanfic"


def _van(token: int) -> str:
    """Văn bản chèn dài ĐÚNG ~`token` token — vô hại, không mang thông tin.

    Kích thước phải CHÍNH XÁC vì bài kiểm chốt dựng lại đúng tình huống
    2724/3400: khối chiến lược phải VỪA trần (nên KHÔNG bị cắt) mà vẫn ăn
    gần hết ngân sách. Một khối to quá sẽ bị cắt, và lúc đó `rang_buoc` lọt
    vào nhờ phần dư — bài kiểm sẽ xanh vì lý do sai.
    """
    # ASCII co chu dich: `uoc_token` dem BYTE, nen mot chuoi tieng Viet cung
    # so ky tu se ra nhieu token hon ~1.3 lan va kich thuoc bai kiem lech.
    return ("context " * (int(token) * 5 // 2 // 8 + 2))[:int(token) * 5 // 2]


def _bg(n: int, *, dai: int = 120) -> str:
    """Văn bản chèn — dài, vô hại, và cố ý không mang thông tin gì."""
    return "\n".join(f"dòng bối cảnh {i}: " + "x" * dai for i in range(n))


class KyUcGia:
    """`DichVuKyUc` giả — chỉ hai thứ `rang_buoc.dung_khoi` cần."""

    def __init__(self, ban_ghi: Dict[str, List[Dict]]) -> None:
        self._d = ban_ghi
        self.kich_hoat = True

    def liet_ke(self, project_id: str, loai: str, *, limit: int = 100) -> Dict:
        return {"san_sang": True, "ket_qua": list(self._d.get(loai, []))[:limit]}


def _k(ma: str, loai: str, noi: str, *, tin_cay: str = "ghi_nhan",
       trang_thai: str = "hieu_luc", quan_trong: int = 5) -> Dict:
    return {"ma": ma, "trang_thai": trang_thai,
            "noi_dung": noi, "tieu_de": "", "tin_cay": tin_cay,
            "quan_trong": quan_trong}


QD_ASTRA = _k("qd_0001", "decision",
              "GPT-6 Astra chỉ dùng cho lượt RẤT KHÓ ở chế độ MAX",
              tin_cay="user_explicit", quan_trong=9)
RB_PROD = _k("ku_prod", "constraint",
             "KHÔNG BAO GIỜ tự deploy production; mọi thay đổi production "
             "phải có người duyệt")
RB_NHO = _k("ku_nho", "constraint", "báo cáo viết bằng tiếng Việt")
YC_1 = _k("ku_yc", "requirement", "phải có installer cho bản desktop")


class Test01XepHangThamQuyen(unittest.TestCase):

    def test_quyet_dinh_tuyen_bo_tuong_minh_dung_DAU(self):
        k = RB.dung_khoi(KyUcGia({"decision": [QD_ASTRA],
                                  "constraint": [RB_NHO],
                                  "requirement": [YC_1]}), PID)
        self.assertEqual([m.ma for m in k.xep()][0], "qd_0001")

    def test_rang_buoc_AN_TOAN_dung_truoc_rang_buoc_thuong(self):
        k = RB.dung_khoi(KyUcGia({"constraint": [RB_NHO, RB_PROD]}), PID)
        self.assertEqual([m.ma for m in k.xep()], ["ku_prod", "ku_nho"])

    def test_yeu_cau_xep_sau_rang_buoc(self):
        k = RB.dung_khoi(KyUcGia({"constraint": [RB_NHO],
                                  "requirement": [YC_1]}), PID)
        self.assertEqual([m.ma for m in k.xep()], ["ku_nho", "ku_yc"])

    def test_ban_ghi_BI_THAY_THE_khong_vao_khoi(self):
        cu = _k("ku_cu", "constraint", "luật cũ", trang_thai="thay_the")
        k = RB.dung_khoi(KyUcGia({"constraint": [cu, RB_NHO]}), PID)
        self.assertEqual([m.ma for m in k.xep()], ["ku_nho"])

    def test_ky_uc_TAT_thi_khoi_RONG_khong_nem(self):
        self.assertTrue(RB.dung_khoi(None, PID).rong)

    def test_loai_KHONG_phai_luat_thi_khong_vao(self):
        """`episodic`/`incident` là bối cảnh, không phải luật — §16."""
        self.assertNotIn("episodic", RB.LOAI_RANG_BUOC)
        self.assertNotIn("incident", RB.LOAI_RANG_BUOC)

    def test_ban_gon_NEU_TEN_muc_da_luoc(self):
        nhieu = [_k(f"ku_{i}", "constraint", "ràng buộc dài " + "y" * 300)
                 for i in range(12)]
        k = RB.dung_khoi(KyUcGia({"decision": [QD_ASTRA],
                                  "constraint": [RB_PROD] + nhieu}), PID)
        van, luoc = k.render(tran_token=260)
        self.assertTrue(luoc)
        self.assertIn(luoc[0], van)                   # neu DICH DANH
        self.assertIn("qd_0001", van)                 # bac 0 KHONG bao gio bi luoc
        self.assertIn("ku_prod", van)                 # bac 1 cung vay
        self.assertLessEqual(uoc_token(van), 300)


#: Khối ràng buộc THẬT của một dự án đã chạy lâu: hai mục thẩm quyền cao
#: cộng một đuôi ràng buộc phụ. Tổng ~800 token — nhỏ hơn sàn (0.35*3400 =
#: 1190) nhưng LỚN HƠN phần dư còn lại sau một bản chiến lược 2600 token.
#: Đó là toàn bộ hình dạng của khuyết tật 2724/3400.
def _khoi_rb_lon() -> RB.KhoiRangBuoc:
    phu = [_k(f"ku_p{i}", "constraint",
              f"ràng buộc phụ {i}: " + "chi tiết vận hành " * 10)
           for i in range(9)]
    return RB.dung_khoi(KyUcGia({"decision": [QD_ASTRA],
                                 "constraint": [RB_PROD] + phu}), PID)


class Test02SanDanhRieng(unittest.TestCase):
    """Trái tim của §16: sàn ngân sách, không phải trần cao hơn."""

    def _goi(self, vai: VaiTro, khoi: Dict[str, str],
             gon: Dict[str, str] = None):
        return NC.dung_goi(vai, khoi_san_co=khoi, huong_dan="HD",
                           khoi_gon=gon or {})

    def test_tong_san_luon_NHO_HON_MOT(self):
        """§16 cấm nâng trần — sàn phải là phép phân phối lại."""
        for vai, d in NC.SAN_DANH_RIENG.items():
            self.assertLess(sum(d.values()), 1.0, vai)

    def test_tran_vai_KHONG_bi_nang(self):
        """Chứng cứ chống rỗng: hằng số trần của V0.8 phải y nguyên."""
        self.assertEqual(ho_so(VaiTro.REVIEWER).tran_token_ngu_canh, 3400)
        self.assertEqual(ho_so(VaiTro.STRATEGIST).tran_token_ngu_canh, 4200)
        self.assertEqual(ho_so(VaiTro.LEADER).tran_token_ngu_canh, 2500)

    def test_ban_chien_luoc_KHONG_lan_at_rang_buoc(self):
        """BÀI KIỂM CHỐT — chính tình huống 2724/3400 của V0.8.

        `ban_chien_luoc` đứng TRƯỚC `rang_buoc` trong thứ tự nạp của
        Reviewer. Trước V0.9 một bản chiến lược đủ dài ăn hết ngân sách và
        `rang_buoc` biến mất. Với sàn, nó không biến mất được.
        """
        van_rb, _ = _khoi_rb_lon().render()
        khoi = {"yeu_cau_nguoi_dung": "phản biện bản này",
                # VUA tran (khong bi cat), nhung an gan het ngan sach —
                # dung hinh dang cua so do 2724/3400.
                "ban_chien_luoc": _van(2600),
                "rang_buoc": van_rb,
                "vien_nang": _van(400), "ky_uc": _van(400)}
        goi = self._goi(VaiTro.REVIEWER, khoi)
        ten = [x.ten for x in goi.khoi]
        self.assertIn("rang_buoc", ten)
        self.assertNotIn("rang_buoc", goi.da_cat)
        self.assertIn("qd_0001", goi.render())
        self.assertIn("ku_prod", goi.render())
        self.assertLessEqual(goi.token, ho_so(VaiTro.REVIEWER)
                             .tran_token_ngu_canh)

    def test_khong_co_san_thi_rang_buoc_BI_DAY_RA(self):
        """Chứng cứ chống rỗng cho bài kiểm trên: bỏ sàn thì lỗi cũ trở lại."""
        cu = dict(NC.SAN_DANH_RIENG)
        try:
            NC.SAN_DANH_RIENG.clear()
            van_rb, _ = _khoi_rb_lon().render()
            goi = self._goi(VaiTro.REVIEWER,
                            {"yeu_cau_nguoi_dung": "x",
                             "ban_chien_luoc": _van(2600),
                             "rang_buoc": van_rb})
            self.assertIn("rang_buoc", goi.da_cat)
        finally:
            NC.SAN_DANH_RIENG.clear()
            NC.SAN_DANH_RIENG.update(cu)

    def test_ban_GON_duoc_dung_khi_ban_day_du_khong_vua_san(self):
        nhieu = [_k(f"ku_{i}", "constraint", "ràng buộc dài " + "z" * 400)
                 for i in range(40)]
        k = RB.dung_khoi(KyUcGia({"decision": [QD_ASTRA],
                                  "constraint": [RB_PROD] + nhieu}), PID)
        day, _ = k.render()
        san = NC.san_cua(VaiTro.REVIEWER, "rang_buoc",
                         ho_so(VaiTro.REVIEWER).tran_token_ngu_canh)
        gon, _ = k.render(tran_token=san)
        self.assertGreater(uoc_token(day), san)
        goi = self._goi(VaiTro.REVIEWER,
                        {"yeu_cau_nguoi_dung": "x",
                         "ban_chien_luoc": _van(1800),
                         "rang_buoc": day}, {"rang_buoc": gon})
        self.assertIn("rang_buoc", [x.ten for x in goi.khoi])
        self.assertIn("rang_buoc", goi.da_gon)
        self.assertIn("qd_0001", goi.render())

    def test_ke_khai_NOI_RO_khoi_nao_o_ban_gon(self):
        goi = NC.dung_goi(VaiTro.REVIEWER,
                          khoi_san_co={"yeu_cau_nguoi_dung": "x",
                                       "ban_chien_luoc": _bg(400),
                                       "rang_buoc": _bg(300)},
                          khoi_gon={"rang_buoc": "GỌN: một ràng buộc"},
                          huong_dan="HD")
        self.assertEqual(goi.ke_khai()["khoi_da_gon"], ["rang_buoc"])
        self.assertIn("BẢN GỌN", goi.render())

    def test_cau_nguoi_dung_VAN_khong_bao_gio_bi_cat(self):
        goi = NC.dung_goi(VaiTro.REVIEWER,
                          khoi_san_co={"yeu_cau_nguoi_dung": "CÂU THẬT",
                                       "rang_buoc": _bg(400),
                                       "ban_chien_luoc": _bg(400)},
                          huong_dan="HD")
        self.assertIn("CÂU THẬT", goi.render())
        self.assertNotIn("yeu_cau_nguoi_dung", goi.da_cat)

    def test_khoi_khong_co_san_van_bi_cat_nhu_cu(self):
        goi = NC.dung_goi(VaiTro.REVIEWER,
                          khoi_san_co={"yeu_cau_nguoi_dung": "x",
                                       "ban_chien_luoc": _bg(400),
                                       "hoi_thoai": _bg(400)},
                          huong_dan="HD")
        self.assertIn("hoi_thoai", goi.da_cat)

    def test_ket_qua_TAT_DINH(self):
        khoi = {"yeu_cau_nguoi_dung": "x", "ban_chien_luoc": _bg(300),
                "rang_buoc": _bg(50), "ky_uc": _bg(100)}
        a = NC.dung_goi(VaiTro.REVIEWER, khoi_san_co=khoi, huong_dan="HD")
        b = NC.dung_goi(VaiTro.REVIEWER, khoi_san_co=khoi, huong_dan="HD")
        self.assertEqual(a.ke_khai(), b.ke_khai())

    def test_moi_vai_deu_co_san_cho_rang_buoc(self):
        for v in (VaiTro.LEADER, VaiTro.STRATEGIST, VaiTro.REVIEWER):
            self.assertGreater(NC.san_cua(v, "rang_buoc",
                                          ho_so(v).tran_token_ngu_canh), 0, v)


if __name__ == "__main__":                      # pragma: no cover
    unittest.main(verbosity=2)
