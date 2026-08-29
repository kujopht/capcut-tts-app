"""Ma trận phân loại thay đổi gia tăng — Story Harvester V4.

Mọi bài đều tất định và dùng `FixtureFetcher`; không bài nào chạm mạng.

Điều đáng kiểm nhất không phải "có nhận ra chương mới không" — mà là các cặp
**dễ lẫn**, nơi đọc nhầm một bên thành bên kia gây mất dữ liệu thật:

* 503 thoáng qua ĐỌC THÀNH "nguồn đã xoá chương" → một chính sách dọn dẹp tự
  động sẽ xoá nội dung thật vì một sự cố mạng.
* Trang hỏng ĐỌC THÀNH "không đổi" → bản sửa của nguồn không bao giờ được nhập.
"""
from __future__ import annotations

import unittest

from server.scraper.change_detection import (
    ChangeKind,
    classify_index,
    detect_metadata_change,
    revalidate,
)
from server.scraper.dedupe import ScrapeState, content_hash
from server.scraper.http_fetcher import FetchError, FetchResult, FixtureFetcher

A = "https://vd.test/truyen/c1"
B = "https://vd.test/truyen/c2"
C = "https://vd.test/truyen/c3"


def _text(html, url):
    return html


def _state(*cap):
    st = ScrapeState()
    for url, noi_dung in cap:
        st.record_success(url, content_hash_value=content_hash(noi_dung))
    return st


def _kind(plan, url):
    for c in plan.changes:
        if c.canonical_url.rstrip("/") == url.rstrip("/"):
            return c.kind
    return None


class ChiTuMucLucTest(unittest.TestCase):
    """Tầng không chạm mạng."""

    def test_khong_co_gi_doi(self):
        plan = classify_index(_state((A, "x"), (B, "y")), [A, B])
        self.assertEqual(plan.counts()["unchanged"], 2)
        self.assertEqual(plan.urls_can_tai, [])

    def test_mot_chuong_moi(self):
        plan = classify_index(_state((A, "x")), [A, B])
        self.assertIs(_kind(plan, B), ChangeKind.NEW_CHAPTER)
        self.assertEqual(len(plan.urls_can_tai), 1)

    def test_nhieu_chuong_moi(self):
        plan = classify_index(_state((A, "x")), [A, B, C])
        self.assertEqual(plan.counts()["new_chapter"], 2)

    def test_chuong_bien_mat_khoi_muc_luc(self):
        plan = classify_index(_state((A, "x"), (B, "y")), [A])
        self.assertIs(_kind(plan, B), ChangeKind.REMOVED_OR_UNAVAILABLE)

    def test_doi_thu_tu_KHONG_phai_thay_doi(self):
        """Đảo thứ tự mục lục không tạo ra thay đổi nào — nhận dạng theo URL
        đã chuẩn hoá, không theo vị trí."""
        plan = classify_index(_state((A, "x"), (B, "y")), [B, A])
        self.assertEqual(plan.counts()["unchanged"], 2)
        self.assertFalse(plan.co_thay_doi)

    def test_bien_the_tracking_param_KHONG_phai_chuong_moi(self):
        """`?utm_source=...` trên cùng một chương từng bị đọc thành chương
        mới — chính là loại trùng lặp mà chuẩn hoá URL sinh ra để chặn."""
        plan = classify_index(_state((A, "x")), [A + "?utm_source=fb"])
        self.assertEqual(plan.counts()["new_chapter"], 0)

    def test_muc_luc_rong_khong_bao_moi_la_da_xoa_het(self):
        """Mục lục rỗng CÓ báo REMOVED — nhưng phải là quyết định của người
        gọi, không phải thứ lớp này tự nuốt. Khoá hành vi lại cho rõ."""
        plan = classify_index(_state((A, "x")), [])
        self.assertIs(_kind(plan, A), ChangeKind.REMOVED_OR_UNAVAILABLE)


class KiemChungQuaMangTest(unittest.TestCase):
    """Tầng nâng phán quyết tạm thành phán quyết đã kiểm chứng."""

    def _chay(self, state, urls, pages, **kw):
        plan = classify_index(state, urls)
        return revalidate(plan, state, FixtureFetcher(pages, **kw),
                          extract_text=_text)

    def test_noi_dung_y_nguyen_la_UNCHANGED(self):
        plan = self._chay(_state((A, "xin chao")), [A], {A: "xin chao"})
        self.assertIs(_kind(plan, A), ChangeKind.UNCHANGED)
        self.assertEqual(plan.urls_can_tai, [])

    def test_noi_dung_da_sua_la_UPDATED(self):
        plan = self._chay(_state((A, "ban cu")), [A], {A: "ban MOI da sua"})
        self.assertIs(_kind(plan, A), ChangeKind.UPDATED_CHAPTER)
        self.assertEqual(plan.urls_can_tai, [A])

    def test_bang_chung_giai_thich_duoc_vi_sao(self):
        plan = self._chay(_state((A, "ban cu")), [A], {A: "ban moi"})
        bc = [c.evidence for c in plan.changes if c.kind is ChangeKind.UPDATED_CHAPTER]
        self.assertTrue(bc and "content_hash" in bc[0], bc)

    def test_304_la_UNCHANGED_va_KHONG_can_tai(self):
        """Đây là chỗ tiết kiệm: một chương không đổi tốn đúng một 304 rỗng."""
        st = _state((A, "xin chao"))
        plan = classify_index(st, [A])
        f = FixtureFetcher({A: "xin chao"}, etags={A: 'W/"v1"'})
        plan = revalidate(plan, st, f, extract_text=_text,
                          validators={A: {"etag": 'W/"v1"'}})
        c = plan.changes[0]
        self.assertIs(c.kind, ChangeKind.UNCHANGED)
        self.assertEqual(c.status_code, 304)

    def test_404_la_REMOVED(self):
        class F:
            def fetch(self, url, **kw):
                return FetchResult(final_url=url, status_code=404,
                                   content_type="", text="")

        st = _state((A, "x"))
        plan = revalidate(classify_index(st, [A]), st, F(), extract_text=_text)
        self.assertIs(_kind(plan, A), ChangeKind.REMOVED_OR_UNAVAILABLE)

    def test_500_la_TRANSIENT_chu_KHONG_phai_da_xoa(self):
        """Cặp dễ lẫn nguy hiểm nhất. Đọc 5xx thành "đã xoá" sẽ khiến một
        chính sách dọn dẹp tự động xoá nội dung thật vì một sự cố mạng."""
        class F:
            def fetch(self, url, **kw):
                return FetchResult(final_url=url, status_code=500,
                                   content_type="", text="")

        st = _state((A, "x"))
        plan = revalidate(classify_index(st, [A]), st, F(), extract_text=_text)
        self.assertIs(_kind(plan, A), ChangeKind.TRANSIENT_FAILURE)
        self.assertNotIn(A, plan.urls_can_tai)

    def test_429_cung_la_TRANSIENT(self):
        class F:
            def fetch(self, url, **kw):
                return FetchResult(final_url=url, status_code=429,
                                   content_type="", text="")

        st = _state((A, "x"))
        plan = revalidate(classify_index(st, [A]), st, F(), extract_text=_text)
        self.assertIs(_kind(plan, A), ChangeKind.TRANSIENT_FAILURE)

    def test_loi_mang_la_TRANSIENT(self):
        class F:
            def fetch(self, url, **kw):
                raise FetchError("het gio")

        st = _state((A, "x"))
        plan = revalidate(classify_index(st, [A]), st, F(), extract_text=_text)
        self.assertIs(_kind(plan, A), ChangeKind.TRANSIENT_FAILURE)

    def test_robots_tu_choi_KHONG_phai_loi_tam_thoi(self):
        """Nguồn cố ý từ chối. Thử lại vô hạn là bỏ qua giới hạn có chủ đích."""
        from server.scraper.http_fetcher import RobotsDisallowedError

        class F:
            def fetch(self, url, **kw):
                raise RobotsDisallowedError("robots tu choi")

        st = _state((A, "x"))
        plan = revalidate(classify_index(st, [A]), st, F(), extract_text=_text)
        self.assertIs(_kind(plan, A), ChangeKind.REMOVED_OR_UNAVAILABLE)

    def test_trang_hong_la_TRANSIENT_chu_KHONG_phai_khong_doi(self):
        """Cặp dễ lẫn thứ hai: nuốt lỗi phân tích thành "không đổi" sẽ khiến
        bản sửa của nguồn không bao giờ được nhập."""
        def no(html, url):
            raise ValueError("HTML hong")

        st = _state((A, "x"))
        plan = revalidate(classify_index(st, [A]), st,
                          FixtureFetcher({A: "<<<"}), extract_text=no)
        self.assertIs(_kind(plan, A), ChangeKind.TRANSIENT_FAILURE)

    def test_ban_ghi_cu_khong_co_hash_thi_coi_la_can_tai_lai(self):
        st = ScrapeState()
        st.record_success(A, content_hash_value="")
        plan = revalidate(classify_index(st, [A]), st,
                          FixtureFetcher({A: "noi dung"}), extract_text=_text)
        self.assertIs(_kind(plan, A), ChangeKind.UPDATED_CHAPTER)

    def test_chuong_moi_KHONG_bi_goi_mang(self):
        """`NEW_CHAPTER` không có gì để so — gọi mạng ở đây là lãng phí thuần."""
        goi = []

        class F:
            def fetch(self, url, **kw):
                goi.append(url)
                return FetchResult(final_url=url, status_code=200,
                                   content_type="text/html", text="x")

        st = _state((A, "x"))
        revalidate(classify_index(st, [A, B]), st, F(), extract_text=_text)
        self.assertNotIn(B, goi)


class NganSachKiemChungTest(unittest.TestCase):
    def test_limit_chan_so_lan_goi_mang(self):
        """Một series 4.000 chương không được biến một lần "kiểm tra cập
        nhật" thành 4.000 request."""
        goi = []

        class F:
            def fetch(self, url, **kw):
                goi.append(url)
                return FetchResult(final_url=url, status_code=200,
                                   content_type="text/html", text="x")

        st = _state((A, "x"), (B, "x"), (C, "x"))
        revalidate(classify_index(st, [A, B, C]), st, F(),
                   extract_text=_text, limit=2)
        self.assertEqual(len(goi), 2)

    def test_muc_vuot_ngan_sach_noi_ro_la_CHUA_kiem_chung(self):
        """Hết ngân sách không được âm thầm nâng thành "đã xác nhận không đổi"."""
        class F:
            def fetch(self, url, **kw):
                return FetchResult(final_url=url, status_code=200,
                                   content_type="text/html", text="x")

        st = _state((A, "x"), (B, "x"))
        plan = revalidate(classify_index(st, [A, B]), st, F(),
                          extract_text=_text, limit=1)
        chua = [c for c in plan.changes if not c.revalidated
                and c.kind is ChangeKind.UNCHANGED]
        self.assertTrue(chua)
        self.assertIn("CHƯA kiểm chứng", chua[0].evidence)


class MetadataTest(unittest.TestCase):
    def test_khong_doi_thi_tra_None(self):
        cu = {"series_title": "T", "series_author": "A"}
        self.assertIsNone(detect_metadata_change(cu, dict(cu)))

    def test_doi_tieu_de_duoc_bao_kem_ten_truong(self):
        c = detect_metadata_change({"series_title": "Cu"}, {"series_title": "Moi"})
        self.assertIs(c.kind, ChangeKind.SOURCE_METADATA_CHANGED)
        self.assertIn("series_title", c.evidence)

    def test_rong_va_thieu_khoa_la_nhu_nhau(self):
        """`""` và khoá vắng mặt không được coi là một thay đổi."""
        self.assertIsNone(detect_metadata_change({"series_author": ""}, {}))


class KeHoachTest(unittest.TestCase):
    def test_urls_can_tai_bo_qua_unchanged_va_transient(self):
        class F:
            def fetch(self, url, **kw):
                if url.rstrip("/") == A.rstrip("/"):
                    return FetchResult(final_url=url, status_code=500,
                                       content_type="", text="")
                return FetchResult(final_url=url, status_code=200,
                                   content_type="text/html", text="x")

        st = _state((A, "x"), (B, "x"))
        plan = revalidate(classify_index(st, [A, B, C]), st, F(), extract_text=_text)
        self.assertEqual(plan.urls_can_tai, [C])

    def test_counts_phu_het_moi_nhan(self):
        plan = classify_index(_state((A, "x")), [A, B])
        self.assertEqual(set(plan.counts()), {k.value for k in ChangeKind})


if __name__ == "__main__":
    unittest.main()
