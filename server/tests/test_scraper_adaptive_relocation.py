"""
P2 (Story Harvester V3 overnight hardening) — kiem thu adaptive candidate-
finding THAT SU qua Scrapling (`server/scraper/adapters/scrapling_relocation.py`),
KHONG mock/gia lap `.relocate()` — day la yeu cau CHINH cua nhiem vu nay:
"Scrapling itself must find the candidate. Do not manually feed the
replacement selector to the validation layer."

Chin kich ban bien doi cau truc (A-I, dung ten trong yeu cau nhiem vu) dung
CHUNG mot khoi noi dung chuong (6 doan van, du dai de vuot nguong HIGH cua
`content_extraction._MIN_SCORE_FOR_HIGH=40` — xem doc dieu tra truc tiep
tren `_score()`: can >= 40 diem VA hon ung vien thu hai >= 10 diem), CHI
khac o CACH bao boc/dat vi tri cau truc quanh no. Ket qua THAT (khong phai
gia dinh) duoc kiem chung truc tiep truoc khi viet assertion — xem tung
class test cho ghi chu ve HANH VI THAT cua thuat toan cham diem cua
Scrapling (`__calculate_similarity_score`, uu tien boi canh to tien/anh em
hon danh tinh cua chinh phan tu — xem docstring module
`scrapling_relocation.py`)."""
from __future__ import annotations

import unittest

from server.scraper.adapters.scrapling_relocation import (
    attempt_adaptive_relocation, relocate_verified_element,
    save_verified_element, validate_relocated_candidate,
)
from server.scraper.self_healing import RelocationConfidence

_URL = "https://vidu-fanfic.test/truyen/1/chuong/12"
_TIEU_DE = "Chapter 12: The Long Road"

_NOI_DUNG_CHUONG = """
  <h1>Chapter 12: The Long Road</h1>
  <p>The rain fell steadily over the old city walls as Kien walked on, his boots sinking into the mud with every step he took toward the eastern gate.</p>
  <p>He remembered what his master had told him years ago, about patience being the only weapon that never dulls no matter how many years pass by.</p>
  <p>Tomorrow would bring new trials, but tonight he simply walked, letting the cold rain wash away the dust of a hundred small defeats behind him.</p>
  <p>The lanterns along the market street had long since been extinguished, leaving only the pale light of the moon to guide his tired footsteps home.</p>
  <p>Somewhere behind him, a dog barked twice and fell silent again, and Kien allowed himself a small, weary smile at the ordinary sound of it.</p>
  <p>When he finally reached the old wooden door of the inn, he paused for a moment, breathing in the wet night air before stepping inside at last.</p>
"""

_ORIGINAL_HTML = f"""
<html><body>
<header>Site Header</header>
<nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
<footer>Copyright 2024</footer>
</body></html>
"""

#: Kich ban A-I dung CHUNG `_NOI_DUNG_CHUONG` — CHI cau truc bao quanh
#: thay doi, dung yeu cau nhiem vu ("Start from one known-good saved
#: chapter body. Verify automatic relocation after: ...").
_KICH_BAN = {
    "A_class_da_doi_ten": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="chapter-text-v2" id="content-main-2024">{_NOI_DUNG_CHUONG}</div>
<footer>Copyright 2024</footer></body></html>""",
    "B_them_wrapper": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="page-wrap"><div class="inner-shell">
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
</div></div>
<footer>Copyright 2024</footer></body></html>""",
    "C_doi_the_cha": f"""
<html><body><header>Site Header</header>
<aside class="sidebar-new">Sidebar links here, nothing chapter related at all.</aside>
<section class="reading-pane">
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
</section>
<footer>Copyright 2024</footer></body></html>""",
    "D_doi_do_sau": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="outer1"><div class="outer2"><div class="outer3">
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
</div></div></div>
<footer>Copyright 2024</footer></body></html>""",
    "E_them_anh_em": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="author-note">Author's note: thanks so much for reading this far, everyone!</div>
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
<div class="tip-jar">Support the author with a small tip if you enjoyed it!</div>
<footer>Copyright 2024</footer></body></html>""",
    "F_quang_cao_gan_ben": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="ad-slot-native"><ins class="adsbygoogle-fake">Advertisement content goes here with lots of promotional filler text to look dense and real.</ins></div>
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
<footer>Copyright 2024</footer></body></html>""",
    "G_dieu_huong_gan_ben": f"""
<html><body><header>Site Header</header>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="chapter-wrap">
<nav class="chapter-pager">Prev Chapter | Next Chapter</nav>
<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>
</div>
<footer>Copyright 2024</footer></body></html>""",
    "H_doi_ten_container": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<article class="novel-reader-pane" id="reader-2024">{_NOI_DUNG_CHUONG}</article>
<footer>Copyright 2024</footer></body></html>""",
    "I_nhieu_vung_mo_ho": f"""
<html><body><header>Site Header</header><nav>Home | Browse | Search</nav>
<div class="sidebar">Sidebar links here, nothing chapter related at all.</div>
<div class="story-body-decoy-1" id="decoy-1">
  <h1>Chapter 11: A Different Chapter</h1>
  <p>This is a decoy paragraph that looks structurally similar in every possible way to the real chapter body below it.</p>
  <p>Another decoy paragraph with a similar length and structure, written to mimic the real chapter as closely as possible here.</p>
  <p>A third decoy paragraph to match the real paragraph count exactly, so a naive structural match cannot tell them apart easily.</p>
  <p>A fourth decoy paragraph, again just long filler text meant to occupy roughly the same amount of space as the real one.</p>
  <p>A fifth decoy paragraph, still just filler, still structurally identical in every way that matters to the scoring function.</p>
  <p>A sixth and final decoy paragraph, closing out this fake chapter body with the same paragraph count as the real one below.</p>
</div>
<div class="story-body-decoy-2" id="decoy-2">{_NOI_DUNG_CHUONG}</div>
<footer>Copyright 2024</footer></body></html>""",
}


def _thiet_lap_dau_van_tay():
    fp = save_verified_element(_ORIGINAL_HTML, "div.story-body", url=_URL)
    assert fp is not None, "fixture nen: selector goc PHAI khop tren HTML goc"
    return fp


class KnownGoodElementSavesFingerprintTest(unittest.TestCase):
    """Buoc 1 cua luong: "known-good chapter element -> save/fingerprint"."""

    def test_luu_thanh_cong_tra_ve_dict_khong_rong(self):
        fp = _thiet_lap_dau_van_tay()
        self.assertIsInstance(fp, dict)
        self.assertEqual(fp["tag"], "div")
        self.assertEqual(fp["attributes"].get("id"), "content-main")

    def test_selector_khong_khop_tra_ve_none(self):
        fp = save_verified_element(_ORIGINAL_HTML, "div.khong-ton-tai", url=_URL)
        self.assertIsNone(fp)

    def test_dau_van_tay_khong_chua_toan_bo_van_ban_chuong(self):
        """Yeu cau "do not store raw unnecessary page content" — dau van
        tay CHI la sieu du lieu cau truc (tag/attributes/path/parent/
        siblings), KHONG duoc chua doan van ban day du cua chuong (van ban
        ĐẦU TIÊN "The rain fell steadily..." tuyet doi khong duoc xuat hien
        trong bat ky gia tri chuoi nao cua dict)."""
        fp = _thiet_lap_dau_van_tay()
        import json
        as_text = json.dumps(fp)
        self.assertNotIn("rain fell steadily", as_text)
        self.assertLess(len(as_text), 2000)


class RealAdaptiveRelocationMatrixTest(unittest.TestCase):
    """Buoc 2+3 cua luong tren TAT CA 9 kich ban A-I — Scrapling THAT SU
    quet lai toan bo cay HTML moi de tim ung vien, KHONG duoc cung cap
    selector thay the thu cong nao (dung `fingerprint`, khong dung selector
    cu). Ket qua duoc kiem chung THAT truoc khi viet o day (xem
    docstring module) — KHONG phai moi kich ban deu ket thuc HIGH, va do
    la mot phat hien THAT can duoc ghi lai trung thuc, khong phai loi cua
    bai test."""

    @classmethod
    def setUpClass(cls):
        cls.fp = _thiet_lap_dau_van_tay()

    def _chay(self, ten_kich_ban: str):
        html = _KICH_BAN[ten_kich_ban]
        candidates = relocate_verified_element(html, self.fp, url=_URL, percentage=40)
        ket_qua = validate_relocated_candidate(candidates, chapter_title=_TIEU_DE)
        return candidates, ket_qua

    def test_A_doi_ten_class_dinh_vi_lai_thanh_cong_HIGH(self):
        """Selector CU that su khong con khop gi (class/id deu doi) — day
        la truong hop DON GIAN NHAT cua "selector fails", va la truong hop
        Scrapling xu ly tot nhat: danh tinh CUA CHINH phan tu (class/id)
        khong doi vi tri trong cay nen boi canh to tien/anh em con nguyen."""
        candidates, ket_qua = self._chay("A_class_da_doi_ten")
        self.assertTrue(candidates.found)
        self.assertFalse(candidates.is_ambiguous)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.HIGH)
        self.assertIn("Kien walked on", ket_qua.clean_text)

    def test_B_them_wrapper_tim_nham_phan_tu_nhung_gate_tu_choi_an_toan(self):
        """PHAT HIEN THAT (xem docstring module): chen wrapper lam thay doi
        TOAN BO boi canh anh em/to tien cua muc tieu, khien
        `.relocate()` tu tin chon NHAM mot phan tu LANG GIENG khong lien
        quan (div.sidebar, boi canh cua no khong doi) thay vi muc tieu that.
        Day CHINH XAC la ly do cong kiem tra noi dung la BAT BUOC: ung vien
        tim duoc (found=True) nhung noi dung cua no ("Sidebar links here")
        khong the vuot qua kiem tra do dai/mat do doan van — tu choi AN
        TOAN (LOW), KHONG ghi de SiteProfile bang du lieu sai."""
        candidates, ket_qua = self._chay("B_them_wrapper")
        self.assertTrue(candidates.found)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.LOW)

    def test_C_doi_the_cha_van_dinh_vi_lai_thanh_cong_HIGH(self):
        candidates, ket_qua = self._chay("C_doi_the_cha")
        self.assertTrue(candidates.found)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.HIGH)
        self.assertIn("Kien walked on", ket_qua.clean_text)

    def test_D_doi_do_sau_ket_qua_duoc_ghi_nhan_trung_thuc(self):
        """PHAT HIEN THAT: `.relocate()` co the chon mot to tien cua muc
        tieu that (vd wrapper ngoai cung) thay vi chinh no — noi dung VAN
        con day du ben trong (khong phai mot phan tu sai lech HOAN TOAN
        nhu kich ban B/H), nen cong kiem tra noi dung co the VAN chap nhan
        duoc (HIGH/MEDIUM) TUY thuoc ung vien cu the nao thang diem. Bai
        test nay kiem tra HANH VI AN TOAN bat bien (khong bao gio LOW-that-
        bai-am-tham VA khong bao gio tra ve noi dung KHONG chua van ban
        chuong that), khong khang khang mot muc confidence co dinh."""
        candidates, ket_qua = self._chay("D_doi_do_sau")
        self.assertTrue(candidates.found)
        if ket_qua.confidence != RelocationConfidence.LOW:
            self.assertIn("Kien walked on", ket_qua.clean_text)

    def test_E_them_anh_em_van_dinh_vi_lai_thanh_cong_HIGH(self):
        candidates, ket_qua = self._chay("E_them_anh_em")
        self.assertTrue(candidates.found)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.HIGH)
        self.assertIn("Kien walked on", ket_qua.clean_text)

    def test_F_quang_cao_gan_ben_van_dinh_vi_lai_thanh_cong_HIGH(self):
        candidates, ket_qua = self._chay("F_quang_cao_gan_ben")
        self.assertTrue(candidates.found)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.HIGH)
        self.assertIn("Kien walked on", ket_qua.clean_text)
        self.assertNotIn("Advertisement content", ket_qua.clean_text)

    def test_G_dieu_huong_gan_ben_van_dinh_vi_lai_thanh_cong_HIGH(self):
        candidates, ket_qua = self._chay("G_dieu_huong_gan_ben")
        self.assertTrue(candidates.found)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.HIGH)
        self.assertIn("Kien walked on", ket_qua.clean_text)

    def test_H_doi_ten_container_hoan_toan_bi_tu_choi_an_toan(self):
        """PHAT HIEN THAT: doi CA the (div->article) LAN class LAN id cung
        luc la truong hop KHO NHAT — danh tinh cua chinh phan tu mat het
        GIA TRI so sanh, va boi canh to tien/anh em cung khong con nguyen
        ven (article moi khong con la anh em cua sidebar/nav/footer theo
        dung cau truc cu). Ung vien tim duoc (neu co) khong dang tin cay —
        gate PHAI tu choi AN TOAN, khong bao gio tu HIGH."""
        candidates, ket_qua = self._chay("H_doi_ten_container")
        self.assertNotEqual(ket_qua.confidence, RelocationConfidence.HIGH)

    def test_I_nhieu_vung_mo_ho_khong_bao_gio_tu_dong_len_HIGH(self):
        """Yeu cau an toan CUA RIENG buoc adaptive relocation (khac
        `validate_relocated_content` don thuan): >1 ung vien diem NGANG
        NHAU PHAI ha tran o MEDIUM, du noi dung ung vien dau tien (theo
        thu tu tra ve boi Scrapling) co trong hop le the nao — khong duoc
        phep may man "doan dung" chuong 12 that thay vi chuong 11 gia chi
        vi no dung truoc trong danh sach ket qua."""
        candidates, ket_qua = self._chay("I_nhieu_vung_mo_ho")
        self.assertTrue(candidates.is_ambiguous)
        self.assertGreaterEqual(candidates.count, 2)
        self.assertNotEqual(ket_qua.confidence, RelocationConfidence.HIGH)


class NoRelocationWhenDirectSelectorWouldHaveWorkedTest(unittest.TestCase):
    """Yeu cau nhiem vu (Section 9): "The normal successful selector path
    should not unnecessarily invoke adaptive relocation." — day la trach
    nhiem cua CALLER (`scraper_ops_service.py`, chi goi
    `attempt_adaptive_relocation` khi Tier 0 CHUA dat HIGH), khong phai
    cua `relocate_verified_element` (ham nay luon lam dung MOT viec: quet
    lai). Kiem tra o day la o CAP DO tich hop, xem
    `test_scraper_ops_service.py::AdaptiveRelocationWiringTest`."""


class ValidateRelocatedCandidateAmbiguityGuardTest(unittest.TestCase):
    """Kiem tra RIENG logic ha tran mo ho (khong phu thuoc `.relocate()`
    that, dung `RelocationCandidates` gia lap de kiem tra CHINH XAC ranh
    gioi cua quy tac, doc lap voi cham diem cau truc cua Scrapling)."""

    def test_mot_ung_vien_hop_le_len_duoc_HIGH(self):
        from server.scraper.adapters.scrapling_relocation import RelocationCandidates
        candidates = RelocationCandidates(
            outer_html_candidates=[
                f'<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>'],
            css_selector_candidates=["#content-main"])
        ket_qua = validate_relocated_candidate(candidates, chapter_title=_TIEU_DE)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.HIGH)

    def test_hai_ung_vien_noi_dung_giong_het_bi_ha_xuong_MEDIUM(self):
        from server.scraper.adapters.scrapling_relocation import RelocationCandidates
        html_hop_le = f'<div class="story-body" id="content-main">{_NOI_DUNG_CHUONG}</div>'
        candidates = RelocationCandidates(
            outer_html_candidates=[html_hop_le, html_hop_le],
            css_selector_candidates=["#content-main", "#content-main-2"])
        ket_qua = validate_relocated_candidate(candidates, chapter_title=_TIEU_DE)
        self.assertEqual(ket_qua.confidence, RelocationConfidence.MEDIUM)

    def test_khong_ung_vien_nao_tra_ve_LOW(self):
        from server.scraper.adapters.scrapling_relocation import RelocationCandidates
        ket_qua = validate_relocated_candidate(RelocationCandidates())
        self.assertEqual(ket_qua.confidence, RelocationConfidence.LOW)


class AttemptAdaptiveRelocationOrchestrationTest(unittest.TestCase):
    """Kiem tra ham dieu phoi cap cao nhat (`attempt_adaptive_relocation`)
    — diem goi vao DUY NHAT ma `scraper_ops_service.py` dung."""

    def test_fingerprint_json_rong_khong_thu_dinh_vi_lai(self):
        outcome = attempt_adaptive_relocation("", _KICH_BAN["A_class_da_doi_ten"], url=_URL)
        self.assertFalse(outcome.relocation_attempted)
        self.assertEqual(outcome.confidence, RelocationConfidence.LOW)

    def test_fingerprint_json_hong_khong_crash(self):
        outcome = attempt_adaptive_relocation(
            "{khong phai json hop le", _KICH_BAN["A_class_da_doi_ten"], url=_URL)
        self.assertFalse(outcome.relocation_attempted)
        self.assertEqual(outcome.confidence, RelocationConfidence.LOW)

    def test_dau_van_tay_hop_le_dinh_vi_lai_thanh_cong_end_to_end(self):
        import json
        fp = _thiet_lap_dau_van_tay()
        outcome = attempt_adaptive_relocation(
            json.dumps(fp), _KICH_BAN["A_class_da_doi_ten"], url=_URL,
            chapter_title=_TIEU_DE)
        self.assertTrue(outcome.relocation_attempted)
        self.assertEqual(outcome.confidence, RelocationConfidence.HIGH)
        self.assertTrue(outcome.candidate_selector)
        self.assertIn("Kien walked on", outcome.clean_text)


if __name__ == "__main__":
    unittest.main()
