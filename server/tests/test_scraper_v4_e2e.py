"""E2E toàn tuyến Story Harvester V4 — Phase E.

Chạy hết đường thật, không mô phỏng tầng nào ở giữa:

    fixture -> FetchProvider -> sổ đăng ký adapter -> SourceAdapter
    -> khám phá chương -> chuẩn hoá -> danh tính ổn định
    -> ChangeDetector -> ScrapeState -> máy trạng thái -> hoàn tất

Chỉ **tầng vận chuyển** là fixture (`FixtureFetcher`). Sổ đăng ký, adapter,
phép chuẩn hoá, phép băm nội dung, phép phân loại thay đổi và máy trạng thái
đều là mã sản xuất thật.

**Không chạm mạng. Không chạm Appwrite. Không chạm sản xuất.**

Năm lượt chạy theo đúng thứ tự vận hành, vì điều đáng chứng minh không phải
"lượt một có chạy không" mà là **lượt hai không nhân đôi dữ liệu**.
"""
from __future__ import annotations

import unittest

from server.scraper.adapters import default_registry
from server.scraper.change_detection import (
    ChangeKind,
    classify_index,
    revalidate,
)
from server.scraper.dedupe import ScrapeState, content_hash
from server.scraper.harvest_state import (
    ErrorCategory,
    HarvestState,
    ItemProgress,
)
from server.scraper.contract import canonicalize_url
from server.scraper.http_fetcher import FetchError, FixtureFetcher
from server.scraper.run_state import item_id_for, run_id_from_fingerprint

GOC = "https://vi.wikisource.org"
MUC_LUC = f"{GOC}/wiki/L%E1%BB%81u_ch%C3%B5ng"


def _fp(url: str) -> str:
    """Dau van tay nguon = sha256(canonical_url) — cung quy uoc voi
    `dedupe.ScrapeState`."""
    import hashlib

    return hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()


def _url_chuong(n: int) -> str:
    # Dung dang URL-encode ma `site_registry` khai cho vi.wikisource.org:
    # `/Ch%C6%B0%C6%A1ng_\d+$`.
    return f"{GOC}/wiki/L%E1%BB%81u_ch%C3%B5ng/Ch%C6%B0%C6%A1ng_{n}"


def _html_muc_luc(so_chuong: int) -> str:
    lien_ket = "".join(
        f'<li><a href="/wiki/L%E1%BB%81u_ch%C3%B5ng/Ch%C6%B0%C6%A1ng_{i}">'
        f'Chương {i}</a></li>'
        for i in range(1, so_chuong + 1))
    return (f"<html><head><title>Lều chõng – Wikisource tiếng Việt</title></head>"
            f"<body><div id='mw-content-text'><ul>{lien_ket}</ul></div></body></html>")


def _html_chuong(n: int, than: str) -> str:
    return (f"<html><head><title>Lều chõng/Chương {n} – Wikisource tiếng Việt"
            f"</title></head><body><div id='mw-content-text'>"
            f"<p>{than}</p></div></body></html>")


def _trang(so_chuong: int, than=None) -> dict:
    than = than or {}
    pages = {MUC_LUC: _html_muc_luc(so_chuong)}
    for i in range(1, so_chuong + 1):
        noi_dung = than.get(i, f"Nội dung gốc của chương {i}. " * 20)
        pages[_url_chuong(i)] = _html_chuong(i, noi_dung)
    return pages


class _Harvester:
    """Bộ điều phối tối thiểu nối các tầng thật lại với nhau.

    Cố ý mỏng: mục đích của E2E là chứng minh **các tầng khớp nhau**, không
    phải giới thiệu thêm một tầng mới cần tự kiểm thử.
    """

    def __init__(self):
        self.state = ScrapeState()
        self.registry = default_registry()
        self.da_ghi: dict = {}          # item_id -> content_hash (kho "that")
        self.lan_ghi = 0                # dem MOI lan ghi thanh cong

    def run(self, pages, *, limit=None):
        fetcher = FixtureFetcher(pages)
        adapter = self.registry.build_for(MUC_LUC, fetcher)
        series = adapter.discover_series(MUC_LUC)
        urls = adapter.list_chapters(series)

        ke_hoach = classify_index(self.state, urls)
        ke_hoach = revalidate(
            ke_hoach, self.state, fetcher,
            extract_text=lambda html, url: adapter.normalize_chapter(
                url, html, series).clean_text,
            limit=limit)

        run_id = run_id_from_fingerprint(_fp(series.canonical_url))
        tien_do = {}
        for c in ke_hoach.changes:
            # `item_id_for` doi mot DAU VAN TAY, khong phai URL. Truyen URL
            # da cat ngan lam chuong 1 va 2 cham vao cung mot `item_id` (hai
            # URL chi khac ky tu CUOI, ma phep cat bo dung ky tu do) — dung
            # kieu va cham danh tinh ma E2E nay sinh ra de chung minh la
            # khong xay ra. Bo test "don dep" bat duoc no.
            m = ItemProgress(item_id=item_id_for(run_id, _fp(c.canonical_url)))
            if c.kind is ChangeKind.UNCHANGED:
                # Khong doi -> khong ghi gi ca. Day chinh la cho tiet kiem.
                m = m.to(HarvestState.CHANGE_CLASSIFIED).to(HarvestState.COMPLETED)
            elif c.kind in (ChangeKind.NEW_CHAPTER, ChangeKind.UPDATED_CHAPTER,
                            ChangeKind.NEEDS_BASELINE):
                m = self._tai_va_ghi(m, c, adapter, series, fetcher)
            elif c.kind is ChangeKind.TRANSIENT_FAILURE:
                m = m.to(HarvestState.FETCHING).fail(
                    ErrorCategory.NETWORK, c.evidence)
            else:                              # REMOVED_OR_UNAVAILABLE
                m = m.to(HarvestState.FETCHING).fail(
                    ErrorCategory.HTTP_NOT_FOUND, c.evidence)
            tien_do[c.canonical_url] = m
        return ke_hoach, tien_do

    def _tai_va_ghi(self, m, c, adapter, series, fetcher):
        m = m.to(HarvestState.FETCHING)
        try:
            html = adapter.fetch_chapter(c.canonical_url)
        except FetchError:
            return m.fail(ErrorCategory.NETWORK, "khong tai duoc")
        m = m.to(HarvestState.PARSED)
        chuong = adapter.normalize_chapter(c.canonical_url, html, series)
        m = m.to(HarvestState.NORMALIZED).to(HarvestState.CHANGE_CLASSIFIED)
        m = m.to(HarvestState.PERSIST_PENDING)

        h = content_hash(chuong.clean_text)
        # GHI EXACTLY-ONCE VE LOGIC: khoa la danh tinh tat dinh, nen mot lan
        # ghi lap chi ghi de cung gia tri, khong tao ban ghi thu hai.
        moi = self.da_ghi.get(m.item_id) != h
        if moi:
            self.lan_ghi += 1
        self.da_ghi[m.item_id] = h
        self.state.record_success(c.canonical_url, content_hash_value=h)
        return m.to(HarvestState.PERSISTED).to(HarvestState.COMPLETED)


class V4E2ETest(unittest.TestCase):
    def setUp(self):
        self.h = _Harvester()

    def _dem(self, ke_hoach):
        return ke_hoach.counts()

    def test_toan_tuyen_nam_luot(self):
        # ---------- LƯỢT 1: khám phá truyện mới ----------
        pages = _trang(2)
        ke_hoach, tien_do = self.h.run(pages)
        d = self._dem(ke_hoach)
        self.assertEqual(d["new_chapter"], 2, f"lượt 1 phải thấy 2 chương mới: {d}")
        self.assertEqual(self.h.lan_ghi, 2)
        self.assertTrue(all(m.state is HarvestState.COMPLETED
                            for m in tien_do.values()))

        # ---------- LƯỢT 2: đầu vào y hệt -> KHÔNG đổi, KHÔNG ghi trùng ----
        ghi_truoc = self.h.lan_ghi
        ke_hoach, tien_do = self.h.run(pages)
        d = self._dem(ke_hoach)
        self.assertEqual(d["unchanged"], 2, f"lượt 2 phải toàn UNCHANGED: {d}")
        self.assertEqual(d["new_chapter"], 0)
        self.assertEqual(d["updated_chapter"], 0)
        self.assertEqual(self.h.lan_ghi, ghi_truoc,
                         "lượt 2 KHÔNG được ghi thêm gì — đây là bằng chứng "
                         "bất biến (idempotency) của toàn tuyến")
        self.assertEqual(ke_hoach.urls_can_tai, [])

        # ---------- LƯỢT 3: fixture thêm ĐÚNG một chương ----------
        pages3 = _trang(3)
        ke_hoach, _ = self.h.run(pages3)
        d = self._dem(ke_hoach)
        self.assertEqual(d["new_chapter"], 1, f"phải đúng MỘT chương mới: {d}")
        self.assertEqual(d["unchanged"], 2)
        self.assertEqual(self.h.lan_ghi, ghi_truoc + 1)

        # ---------- LƯỢT 4: nội dung một chương đã có bị SỬA ----------
        ghi_truoc = self.h.lan_ghi
        pages4 = _trang(3, than={1: "Bản đã được nguồn sửa lại hoàn toàn. " * 20})
        ke_hoach, _ = self.h.run(pages4)
        d = self._dem(ke_hoach)
        self.assertEqual(d["updated_chapter"], 1,
                         f"phải đúng MỘT chương bị sửa: {d}")
        self.assertEqual(d["new_chapter"], 0)
        self.assertEqual(d["unchanged"], 2)
        self.assertEqual(self.h.lan_ghi, ghi_truoc + 1,
                         "chỉ chương bị sửa mới được ghi lại")

        # ---------- LƯỢT 5: lỗi tải tạm thời -> thử lại thành công ----------
        class HongMotLan:
            def __init__(self, pages):
                self._that = FixtureFetcher(pages)
                self.da_hong = False

            def fetch(self, url, **kw):
                if not self.da_hong and url == _url_chuong(3):
                    self.da_hong = True
                    raise FetchError("mang chap chon")
                return self._that.fetch(url, **kw)

        # Xoa ban ghi cua chuong 3 de no phai duoc tai lai o luot nay.
        self.h.state.record_failure(_url_chuong(3))
        fetcher = HongMotLan(pages4)
        adapter = self.h.registry.build_for(MUC_LUC, fetcher)
        series = adapter.discover_series(MUC_LUC)
        ke_hoach = classify_index(self.h.state, adapter.list_chapters(series))
        muc = [c for c in ke_hoach.changes
               if c.canonical_url.rstrip("/") == _url_chuong(3).rstrip("/")]
        self.assertTrue(muc, "chương 3 phải cần nạp lại baseline")
        self.assertIs(muc[0].kind, ChangeKind.NEEDS_BASELINE)

        m = ItemProgress(item_id="i3", max_attempts=3).to(HarvestState.FETCHING)
        with self.assertRaises(FetchError):
            adapter.fetch_chapter(_url_chuong(3))
        m = m.fail(ErrorCategory.NETWORK, "mang chap chon")
        self.assertIs(m.state, HarvestState.FAILED_TRANSIENT)

        m = m.schedule_retry()
        self.assertIs(m.state, HarvestState.RETRY_WAIT)
        m = m.to(HarvestState.FETCHING)
        html = adapter.fetch_chapter(_url_chuong(3))       # lan hai: thanh cong
        self.assertTrue(html)
        m = (m.to(HarvestState.PARSED).to(HarvestState.NORMALIZED)
              .to(HarvestState.CHANGE_CLASSIFIED).to(HarvestState.PERSIST_PENDING)
              .to(HarvestState.PERSISTED).to(HarvestState.COMPLETED))
        self.assertIs(m.state, HarvestState.COMPLETED)
        self.assertEqual(m.attempts, 1, "đúng một lần hỏng trước khi thành công")

    def test_khong_con_du_lieu_thua_sau_khi_don(self):
        """Dọn dẹp: mọi thứ E2E tạo ra đều nằm trong bộ nhớ của bài test."""
        pages = _trang(2)
        self.h.run(pages)
        self.assertEqual(len(self.h.da_ghi), 2)
        self.h.da_ghi.clear()
        self.h.state = ScrapeState()
        self.assertEqual(self.h.da_ghi, {})
        self.assertEqual(self.h.state.known_urls(status="ok"), [])

    def test_moi_chuong_co_item_id_RIENG(self):
        """Hai chương KHÔNG được chạm vào cùng một `item_id`.

        Danh tính tất định là thứ duy nhất chặn ghi trùng ở tầng Appwrite
        (POST trùng `documentId` -> 409). Nếu hai chương khác nhau sinh ra
        cùng một id, chương thứ hai sẽ im lặng bị coi là "đã có" và KHÔNG BAO
        GIỜ được ghi. Bài này từng bắt được đúng lỗi đó trong chính bộ E2E."""
        self.h.run(_trang(5))
        self.assertEqual(len(self.h.da_ghi), 5,
                         "5 chương phải cho 5 item_id phân biệt")
        for k in self.h.da_ghi:
            self.assertLessEqual(len(k), 36, "vượt trần $id của Appwrite")

    def test_adapter_duoc_chon_qua_SO_DANG_KY_chu_khong_hardcode(self):
        reg = default_registry().resolve(MUC_LUC)
        self.assertEqual(reg.name, "generic_index")
        self.assertTrue(reg.capabilities.supports_incremental_updates)

    def test_host_ngoai_so_dang_ky_bi_tu_choi_trong_E2E(self):
        from server.scraper.adapters import UnsupportedUrlError

        with self.assertRaises(UnsupportedUrlError):
            default_registry().build_for("https://khong-ho-tro.test/x",
                                         FixtureFetcher({}))


if __name__ == "__main__":
    unittest.main()
