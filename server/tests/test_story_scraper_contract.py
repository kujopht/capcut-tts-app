"""
Universal Story Scraper — hop dong nen tang: chuan hoa URL, chong trung
(content_hash/source_fingerprint), va ScrapeState (resume + phat hien
revision). Khong cham mang — thuan logic.
"""
import unittest

from server.scraper.contract import canonicalize_url
from server.scraper.dedupe import ScrapeState, content_hash, source_fingerprint


class CanonicalizeUrlTest(unittest.TestCase):
    def test_bo_tracking_param_nhung_giu_param_that(self):
        a = canonicalize_url("https://example.com/truyen/chuong-1?utm_source=fb&id=5")
        b = canonicalize_url("https://example.com/truyen/chuong-1?id=5")
        self.assertEqual(a, b)

    def test_thu_tu_param_khac_nhau_ra_cung_ket_qua(self):
        a = canonicalize_url("https://example.com/x?b=2&a=1")
        b = canonicalize_url("https://example.com/x?a=1&b=2")
        self.assertEqual(a, b)

    def test_bo_dau_gach_cheo_cuoi_tru_root(self):
        self.assertEqual(
            canonicalize_url("https://example.com/truyen/"),
            canonicalize_url("https://example.com/truyen"),
        )
        # root thi GIU nguyen dau `/` — khong duoc rut gon thanh chuoi rong.
        self.assertEqual(canonicalize_url("https://example.com/"), "https://example.com/")

    def test_scheme_va_host_khong_phan_biet_hoa_thuong(self):
        self.assertEqual(
            canonicalize_url("HTTPS://Example.COM/Truyen"),
            canonicalize_url("https://example.com/Truyen"),
        )

    def test_bo_fragment(self):
        self.assertEqual(
            canonicalize_url("https://example.com/truyen#binh-luan"),
            canonicalize_url("https://example.com/truyen"),
        )

    def test_url_khong_co_scheme_van_ra_dang_hop_le(self):
        """2026-08-26, phat hien qua review — `urlsplit` doc mot chuoi
        khong co `://` nhu duong dan TUONG DOI thuan tuy: toan bo roi vao
        `path`, `netloc` rong, ra ket qua hong dang `https:example.com/x`.
        Admin dan url thuong KHONG go `https://` — day la truong hop THAT."""
        self.assertEqual(
            canonicalize_url("example.com/truyen/chuong-1"),
            "https://example.com/truyen/chuong-1",
        )

    def test_tham_so_that_trung_ten_ngan_voi_tracking_KHONG_bi_xoa(self):
        """2026-08-26, phat hien qua review — khop THEO TIEN TO tren cac
        chuoi ngan/chung nhu "ref"/"si" xoa nham tham so THAT: `size`, `sid`,
        `since`, `referral_code`. Chi `utm_` moi duoc khop tien to (luon co
        hau to doi); moi ten khac phai khop CHINH XAC."""
        giu_nguyen = [
            ("https://example.com/x?size=10", "size"),
            ("https://example.com/x?sid=abc", "sid"),
            ("https://example.com/x?since=2026", "since"),
            ("https://example.com/x?referral_code=xyz", "referral_code"),
        ]
        for url, tham_so in giu_nguyen:
            self.assertIn(tham_so, canonicalize_url(url),
                          f"{tham_so} la tham so THAT, khong duoc xoa")

    def test_tham_so_theo_doi_THAT_van_bi_xoa(self):
        for url in [
            "https://example.com/x?utm_source=fb",
            "https://example.com/x?fbclid=abc",
            "https://example.com/x?ref=xyz",
            "https://example.com/x?si=xyz",
        ]:
            self.assertEqual(canonicalize_url(url), "https://example.com/x")

    def test_youtube_dang_url_khac_nhau_KHONG_tu_gop(self):
        """`canonicalize_url` chi chuan hoa CHUOI — no khong biet
        `youtu.be/ID` va `youtube.com/watch?v=ID` la CUNG mot video. Muc dinh
        nay CO Y: gop hai dang do la trach nhiem cua tang tren (vi du dua
        vao ID trich duoc), khong phai cua ham chuan hoa chuoi thuan tuy."""
        self.assertNotEqual(
            canonicalize_url("https://youtu.be/abc123"),
            canonicalize_url("https://youtube.com/watch?v=abc123"),
        )


class ContentHashTest(unittest.TestCase):
    def test_cung_noi_dung_ra_cung_hash(self):
        self.assertEqual(content_hash("Xin chào"), content_hash("Xin chào"))

    def test_khac_mot_ky_tu_ra_hash_khac(self):
        self.assertNotEqual(content_hash("Xin chào"), content_hash("Xin chào."))


class SourceFingerprintTest(unittest.TestCase):
    def test_hai_bien_the_url_ra_cung_fingerprint(self):
        a = source_fingerprint("https://example.com/c1?utm_source=fb")
        b = source_fingerprint("https://example.com/c1")
        self.assertEqual(a, b)

    def test_tat_dinh_qua_nhieu_lan_goi(self):
        """Cung mot url phai LUON ra cung fingerprint — day la yeu cau cot
        loi de dinh danh dung vi tri nguon on dinh qua nhieu lan chay,
        giong triet ly `trusted_source_id`/`video_import_id`."""
        url = "https://example.com/truyen/chuong-1"
        self.assertEqual(source_fingerprint(url), source_fingerprint(url))


class ScrapeStateTest(unittest.TestCase):
    def test_ghi_thanh_cong_roi_doc_lai_bang_bien_the_url_khac(self):
        state = ScrapeState()
        state.record_success("https://example.com/c1?utm_source=fb",
                              content_hash_value="h1", chapter_number=1)
        # Doc lai BANG MOT BIEN THE URL KHAC (khong co tracking param) —
        # phai tim thay CUNG ban ghi, day la diem chinh cua resume.
        row = state.get(canonicalize_url("https://example.com/c1"))
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["chapter_number"], 1)

    def test_phat_hien_revision_khong_am_tham_ghi_de(self):
        state = ScrapeState()
        state.record_success("https://example.com/c1", content_hash_value="h1")
        row2 = state.record_success("https://example.com/c1", content_hash_value="h2")
        self.assertTrue(row2["is_revision"], "noi dung doi phai duoc gan co, khong am tham qua")
        self.assertEqual(row2["previous_content_hash"], "h1")

    def test_ghi_lai_cung_noi_dung_KHONG_bi_coi_la_revision(self):
        state = ScrapeState()
        state.record_success("https://example.com/c1", content_hash_value="h1")
        row2 = state.record_success("https://example.com/c1", content_hash_value="h1")
        self.assertFalse(row2["is_revision"])

    def test_that_bai_duoc_ghi_de_thu_lai_lan_sau(self):
        state = ScrapeState()
        state.record_failure("https://example.com/c1")
        row = state.get("https://example.com/c1")
        self.assertEqual(row["status"], "failed")

    def test_tuan_tu_hoa_roi_khoi_phuc_lai_dung(self):
        state = ScrapeState()
        state.record_success("https://example.com/c1", content_hash_value="h1", chapter_number=1)
        raw = state.to_json()
        khoi_phuc = ScrapeState.from_json(raw)
        row = khoi_phuc.get("https://example.com/c1")
        self.assertEqual(row["content_hash"], "h1")


if __name__ == "__main__":
    unittest.main()
