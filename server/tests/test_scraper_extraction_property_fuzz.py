"""
Overnight mega task, Phase 5 ("extraction property/fuzz testing") —
kiem thu THUOC TINH (property-based, GIOI HAN, khong phai fuzz campaign
vo han) quanh `content_extraction.extract_content_v3` (Phase 6).

CACH LAM: MOT chuong "vang" (golden fixture) + MOT danh sach BIEN DOI DOM
CO KIEM SOAT (moi bien doi la MOT ham thuan, tat dinh, khong ngau nhien
that su) — ap TUNG bien doi rieng le VA phoi hop vai bien doi, kiem tra
CAC THUOC TINH phai luon dung bat ke bien doi nao:

  1. Van ban CHINH (cac cau vang) van con trong ket qua trich xuat.
  2. Thu tu doan van KHONG bi dao lon (cau 1 truoc cau 2 truoc cau 3).
  3. "Rac" (sidebar/quang cao/dieu huong chen vao) KHONG chiem uu the
     (khong tro thanh container duoc chon).
  4. KHONG nem ngoai le nao (crash).
  5. Thoi gian chay KHONG bung no theo cap so nhan (kiem tra co tinh,
     khong phai benchmark chinh xac — xem Phase 8 rieng cho do luong that).
  6. Ket qua KHONG "phinh to" bat thuong so voi golden goc (rac boilerplate
     khong bi gop nham vao van ban chinh).

Cac bien doi CO KIEM SOAT (khong "fuzz that su" theo nghia ngau nhien):
nested wrappers, thuoc tinh la vo hai, dao thu tu sidebar, tieu de nhan
doi, chen khoi dieu huong, doi kieu boc doan van, node rong, bien the
HTML entity, Unicode, long nhau hong co chu dich.
"""
from __future__ import annotations

import time
import unittest

from server.scraper.content_extraction import extract_content_v3

_CAU_1 = "Đây là câu văn đầu tiên của chương thật, đủ dài để có ý nghĩa."
_CAU_2 = "Đây là câu văn thứ hai, tiếp nối mạch truyện một cách tự nhiên."
_CAU_3 = "Đây là câu văn thứ ba, kết thúc đoạn văn mẫu cho bài kiểm tra này."
_TIEU_DE = "Chương 7: Thử Nghiệm"

_GOLDEN = (
    '<html><head><title>{title}</title></head><body>'
    '<nav>menu linh tinh không liên quan</nav>'
    '<article><h1>{title}</h1>'
    '<p>{c1}</p><p>{c2}</p><p>{c3}</p>'
    '</article>'
    '<footer>chân trang linh tinh</footer>'
    '</body></html>'
).format(title=_TIEU_DE, c1=_CAU_1, c2=_CAU_2, c3=_CAU_3)


def _bien_doi_nested_wrapper(html: str) -> str:
    """Boc noi dung chuong trong nhieu lop div long nhau vo nghia."""
    return html.replace(
        f"<p>{_CAU_1}</p>",
        f'<div><div><div><p>{_CAU_1}</p></div></div></div>')


def _bien_doi_thuoc_tinh_vo_hai(html: str) -> str:
    """Them thuoc tinh la (data-*, aria-*, style rong) khong lien quan."""
    return html.replace(
        "<article>",
        '<article data-tracking-id="abc123" aria-label="noi dung" '
        'style="" data-random-xyz="999">')


def _bien_doi_dao_thu_tu_sidebar(html: str) -> str:
    """Doi thu tu: sidebar/nav xuat hien SAU noi dung thay vi truoc."""
    return html.replace(
        '<nav>menu linh tinh không liên quan</nav>', ""
    ).replace(
        "</article>", "</article><nav>menu linh tinh không liên quan</nav>")


def _bien_doi_tieu_de_nhan_doi(html: str) -> str:
    """Tieu de xuat hien HAI LAN (mot lan that trong <h1>, mot lan trong
    mot the <span> khong lien quan ve mat cau truc)."""
    return html.replace(
        "<h1>{}</h1>".format(_TIEU_DE),
        f"<span class=\"breadcrumb\">{_TIEU_DE}</span><h1>{_TIEU_DE}</h1>")


def _bien_doi_chen_khoi_dieu_huong(html: str) -> str:
    """Chen mot khoi dieu huong chuong (prev/next) VAO GIUA cac doan van."""
    return html.replace(
        f"<p>{_CAU_2}</p>",
        f'<div class="chapter-nav"><a href="/prev">Chương trước</a>'
        f'<a href="/next">Chương sau</a></div><p>{_CAU_2}</p>')


def _bien_doi_doi_kieu_boc_doan_van(html: str) -> str:
    """Doi <p> thanh <div> cho MOT doan (mot so site tron lan the boc)."""
    return html.replace(f"<p>{_CAU_2}</p>", f"<div>{_CAU_2}</div>")


def _bien_doi_node_rong(html: str) -> str:
    """Them nhieu the rong (khong van ban) xen giua noi dung."""
    return html.replace(
        f"<p>{_CAU_1}</p><p>{_CAU_2}</p>",
        f'<p>{_CAU_1}</p><p></p><div></div><span> </span><p>{_CAU_2}</p>')


def _bien_doi_html_entity(html: str) -> str:
    """Dung HTML entity thay vi ky tu Unicode truc tiep o mot so cho."""
    return html.replace("Đây là", "Đây l&#224;")


def _bien_doi_unicode_dac_biet(html: str) -> str:
    """Them ky tu Unicode dac biet (emoji, zero-width space) xen vao."""
    return html.replace(_CAU_3, _CAU_3 + " ​\U0001f4d6​")


def _bien_doi_long_nhau_hong_co_chu_dich(html: str) -> str:
    """The MO co dinh dang la (thieu dau `>` truoc mot the con, khien
    `html.parser` doc nham mot phan thanh thuoc tinh) — NHUNG VAN DONG
    dung, khong de lai mot the mo VINH VIEN boc het noi dung phia sau
    (xem ghi chu duoi: mot phien ban SOM cua bien doi nay VO Y de div
    KHONG BAO GIO dong, khien MOI noi dung sau do bi coi la con cua no —
    neu class do TRUNG voi mot tu khoa reject-hint (vd "widget"), CA
    CHUONG that su bi loai theo, tra ve RONG/LOW mot cach AN TOAN (dung
    thiet ke, khong phai crash) nhung khong con kiem duoc thuoc tinh "van
    ban chinh con giu duoc" nua — da sua fixture nay de CHI kiem tra dinh
    dang la CUC BO, khong lam sai lech ca cay tai lieu)."""
    return html.replace(
        "<article>", '<article><div class="thong-bao-la"<span>lỗi cấu trúc</span></div>')


_BIEN_DOI = [
    ("nested_wrapper", _bien_doi_nested_wrapper),
    ("thuoc_tinh_vo_hai", _bien_doi_thuoc_tinh_vo_hai),
    ("dao_thu_tu_sidebar", _bien_doi_dao_thu_tu_sidebar),
    ("tieu_de_nhan_doi", _bien_doi_tieu_de_nhan_doi),
    ("chen_khoi_dieu_huong", _bien_doi_chen_khoi_dieu_huong),
    ("doi_kieu_boc_doan_van", _bien_doi_doi_kieu_boc_doan_van),
    ("node_rong", _bien_doi_node_rong),
    ("html_entity", _bien_doi_html_entity),
    ("unicode_dac_biet", _bien_doi_unicode_dac_biet),
    ("long_nhau_hong_co_chu_dich", _bien_doi_long_nhau_hong_co_chu_dich),
]

#: Tran thoi gian XU LY MOT bien doi (giay) — kiem tra co tinh "khong bung
#: no", KHONG phai benchmark chinh xac (xem Phase 8). Rong rai co y.
_TRAN_THOI_GIAN_GIAY = 2.0
#: Ty le PHINH TO toi da so voi golden goc — trich xuat KHONG duoc "phinh"
#: qua muc chi vi mot bien doi khong lien quan them mot vai the.
_TY_LE_PHINH_TO_TOI_DA = 3.0


def _xac_nhan_thuoc_tinh(test_case, html: str, ten_bien_doi: str) -> None:
    t0 = time.perf_counter()
    ket_qua = extract_content_v3(html, chapter_title=_TIEU_DE)
    thoi_gian = time.perf_counter() - t0

    test_case.assertLess(
        thoi_gian, _TRAN_THOI_GIAN_GIAY,
        f"[{ten_bien_doi}] xu ly qua lau ({thoi_gian:.2f}s) — nghi ngo bung no")

    text = ket_qua.clean_text
    test_case.assertIn(_CAU_1[:30], text, f"[{ten_bien_doi}] mat câu 1")
    test_case.assertIn(_CAU_2[:30], text, f"[{ten_bien_doi}] mat câu 2")
    test_case.assertIn(_CAU_3[:30], text, f"[{ten_bien_doi}] mat câu 3")

    # Thu tu KHONG bi dao lon.
    vi_tri_1 = text.find(_CAU_1[:30])
    vi_tri_2 = text.find(_CAU_2[:30])
    vi_tri_3 = text.find(_CAU_3[:30])
    test_case.assertTrue(
        vi_tri_1 < vi_tri_2 < vi_tri_3,
        f"[{ten_bien_doi}] thu tu doan van bi dao lon")

    # "Rac" khong chiem uu the — menu/footer khong duoc xuat hien trong
    # ket qua (container duoc chon phai la vung noi dung, khong phai body
    # gom ca rac).
    test_case.assertNotIn("menu linh tinh", text, f"[{ten_bien_doi}] rac lan vao ket qua")
    test_case.assertNotIn("chân trang linh tinh", text, f"[{ten_bien_doi}] rac lan vao ket qua")

    # Khong "phinh to" bat thuong.
    do_dai_golden = len(extract_content_v3(_GOLDEN, chapter_title=_TIEU_DE).clean_text)
    test_case.assertLessEqual(
        len(text), do_dai_golden * _TY_LE_PHINH_TO_TOI_DA,
        f"[{ten_bien_doi}] ket qua phinh to bat thuong so voi golden")


class SingleMutationPropertyTest(unittest.TestCase):
    """MOI bien doi rieng le phai giu nguyen cac thuoc tinh cot loi."""

    def test_golden_tu_no_giu_dung_thuoc_tinh(self):
        _xac_nhan_thuoc_tinh(self, _GOLDEN, "golden_goc")


def _tao_test_don(ten, ham):
    def test(self):
        html_bien_doi = ham(_GOLDEN)
        self.assertNotEqual(html_bien_doi, _GOLDEN, f"[{ten}] bien doi khong co tac dung gi (fixture sai)")
        _xac_nhan_thuoc_tinh(self, html_bien_doi, ten)
    return test


for _ten, _ham in _BIEN_DOI:
    setattr(SingleMutationPropertyTest, f"test_bien_doi_{_ten}", _tao_test_don(_ten, _ham))


class CombinedMutationPropertyTest(unittest.TestCase):
    """PHOI HOP nhieu bien doi CUNG LUC — cac thuoc tinh van phai giu
    nguyen du chong nhieu lop bien doi khac nhau."""

    def test_phoi_hop_tat_ca_bien_doi_cung_luc(self):
        html = _GOLDEN
        for _ten, ham in _BIEN_DOI:
            html = ham(html)
        _xac_nhan_thuoc_tinh(self, html, "phoi_hop_tat_ca")

    def test_phoi_hop_ba_bien_doi_manh_nhat(self):
        # nested wrapper + chen dieu huong + long nhau hong — ba loai CO
        # KHA NANG gay nhieu nhat cho bo diem cau truc, phoi hop rieng.
        html = _bien_doi_nested_wrapper(_GOLDEN)
        html = _bien_doi_chen_khoi_dieu_huong(html)
        html = _bien_doi_long_nhau_hong_co_chu_dich(html)
        _xac_nhan_thuoc_tinh(self, html, "phoi_hop_ba_manh_nhat")


class DeeplyNestedScaleTest(unittest.TestCase):
    """Doi chung voi RecursionError da sua truoc do (commit 04410fe) — o
    day kiem tra THUOC TINH "khong bung no thoi gian", khong chi "khong
    crash" (da co test rieng cho crash trong test_scraper_content_extraction.py)."""

    def test_long_nhau_rat_sau_khong_bung_no_thoi_gian(self):
        sau = 2000
        html = (
            '<html><body><nav>rác</nav><article><h1>{t}</h1>'.format(t=_TIEU_DE)
            + "<div>" * sau
            + f"<p>{_CAU_1}</p><p>{_CAU_2}</p><p>{_CAU_3}</p>"
            + "</div>" * sau
            + "</article></body></html>"
        )
        t0 = time.perf_counter()
        ket_qua = extract_content_v3(html, chapter_title=_TIEU_DE)
        thoi_gian = time.perf_counter() - t0
        self.assertLess(thoi_gian, 5.0, f"long nhau {sau} cap qua lau: {thoi_gian:.2f}s")
        self.assertIn(_CAU_1[:30], ket_qua.clean_text)


if __name__ == "__main__":
    unittest.main()
