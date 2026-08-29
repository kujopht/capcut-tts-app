"""Máy trạng thái harvest — ma trận chuyển tiếp + sập/khôi phục + đồng thời.

Story Harvester V4, Phase C + D.

Điều đáng kiểm không phải đường đi thuận lợi mà là các cách hỏng **im lặng**:
một lỗi còn-thử-lại-được bị lưu thành `failed` (khởi động lại sẽ bỏ qua nó
vĩnh viễn), một báo lỗi đến muộn lật ngược kết quả đã xong, hay hai worker
cùng ghi một chương thành hai bản.
"""
from __future__ import annotations

import unittest

from server.scraper.harvest_state import (
    ALLOWED,
    ErrorCategory,
    HarvestState,
    InvalidTransition,
    ItemProgress,
    RETRYABLE,
    TERMINAL,
    persisted_status,
    sanitize_diagnostic,
)
from server.scraper.run_state import ScrapeItemStatus


def _muc(state=HarvestState.DISCOVERED, **kw):
    return ItemProgress(item_id="i1", state=state, **kw)


class MaTranChuyenTiepTest(unittest.TestCase):
    def test_moi_trang_thai_deu_co_trong_bang(self):
        """Thiếu một trạng thái trong bảng là fail-closed thành 'không đi đâu
        được' — phải bắt ở đây chứ không phải lúc chạy."""
        for s in HarvestState:
            self.assertIn(s, ALLOWED, f"{s} chưa khai chuyển tiếp")

    def test_duong_di_thuan_loi_day_du(self):
        m = _muc()
        for buoc in (HarvestState.FETCHING, HarvestState.PARSED,
                     HarvestState.NORMALIZED, HarvestState.CHANGE_CLASSIFIED,
                     HarvestState.PERSIST_PENDING, HarvestState.PERSISTED,
                     HarvestState.COMPLETED):
            m = m.to(buoc)
        self.assertIs(m.state, HarvestState.COMPLETED)
        self.assertTrue(m.is_terminal)

    def test_nhay_coc_bi_tu_choi(self):
        """DISCOVERED -> PERSISTED bỏ qua cả tải lẫn phân loại."""
        with self.assertRaises(InvalidTransition):
            _muc().to(HarvestState.PERSISTED)

    def test_di_lui_bi_tu_choi(self):
        with self.assertRaises(InvalidTransition):
            _muc(HarvestState.NORMALIZED).to(HarvestState.FETCHING)

    def test_trang_thai_ket_khong_di_dau_duoc(self):
        for s in TERMINAL:
            self.assertEqual(ALLOWED[s], frozenset(), f"{s} phải là kết")
            with self.assertRaises(InvalidTransition, msg=str(s)):
                _muc(s).to(HarvestState.FETCHING)

    def test_thong_bao_loi_liet_ke_buoc_hop_le(self):
        with self.assertRaises(InvalidTransition) as ctx:
            _muc().to(HarvestState.PERSISTED)
        self.assertIn("fetching", str(ctx.exception))

    def test_khong_doi_thi_di_thang_toi_COMPLETED(self):
        """Chương không đổi thì không ghi gì cả — không đi qua PERSIST."""
        m = _muc(HarvestState.CHANGE_CLASSIFIED).to(HarvestState.COMPLETED)
        self.assertIs(m.state, HarvestState.COMPLETED)


class IdempotentTest(unittest.TestCase):
    def test_ghi_lai_cung_trang_thai_la_khong_thao_tac(self):
        """Một worker bị thử lại sau khi đã ghi thành công không được nổ."""
        m = _muc(HarvestState.PERSISTED)
        self.assertIs(m.to(HarvestState.PERSISTED), m)

    def test_ghi_lai_nhieu_lan_khong_doi_ket_qua(self):
        m = _muc(HarvestState.NORMALIZED)
        for _ in range(5):
            m = m.to(HarvestState.CHANGE_CLASSIFIED)
        self.assertIs(m.state, HarvestState.CHANGE_CLASSIFIED)
        self.assertEqual(m.attempts, 0)

    def test_khong_thao_tac_tren_trang_thai_ket_cung_duoc(self):
        m = _muc(HarvestState.COMPLETED)
        self.assertIs(m.to(HarvestState.COMPLETED), m)


class ChieuXuongTrangThaiLuuTest(unittest.TestCase):
    """Sản xuất chỉ có bốn giá trị enum. Phép chiếu phải an toàn."""

    def test_moi_trang_thai_deu_chieu_duoc(self):
        for s in HarvestState:
            self.assertIsInstance(persisted_status(s), ScrapeItemStatus)

    def test_loi_TAM_THOI_chieu_ve_PENDING_khong_phai_FAILED(self):
        """Đây là chỗ nguy hiểm nhất của phép chiếu: lưu một lỗi còn thử lại
        được thành `failed` sẽ khiến một lần khởi động lại bỏ qua nó vĩnh viễn."""
        self.assertIs(persisted_status(HarvestState.FAILED_TRANSIENT),
                      ScrapeItemStatus.PENDING)
        self.assertIs(persisted_status(HarvestState.RETRY_WAIT),
                      ScrapeItemStatus.PENDING)

    def test_chi_loi_VINH_VIEN_moi_la_FAILED(self):
        self.assertIs(persisted_status(HarvestState.FAILED_PERMANENT),
                      ScrapeItemStatus.FAILED)

    def test_huy_chieu_ve_SKIPPED(self):
        self.assertIs(persisted_status(HarvestState.CANCELLED),
                      ScrapeItemStatus.SKIPPED)

    def test_xong_chieu_ve_REVIEW_READY(self):
        for s in (HarvestState.PERSISTED, HarvestState.COMPLETED):
            self.assertIs(persisted_status(s), ScrapeItemStatus.REVIEW_READY)


class ThuLaiCoTranTest(unittest.TestCase):
    def test_loi_mang_con_thu_lai_duoc(self):
        m = _muc(HarvestState.FETCHING).fail(ErrorCategory.NETWORK, "het gio")
        self.assertIs(m.state, HarvestState.FAILED_TRANSIENT)
        self.assertEqual(m.attempts, 1)

    def test_404_la_VINH_VIEN_ngay_lan_dau(self):
        m = _muc(HarvestState.FETCHING).fail(ErrorCategory.HTTP_NOT_FOUND)
        self.assertIs(m.state, HarvestState.FAILED_PERMANENT)

    def test_robots_tu_choi_la_VINH_VIEN(self):
        """Nguồn cố ý từ chối — thử lại là bỏ qua giới hạn có chủ đích."""
        m = _muc(HarvestState.FETCHING).fail(ErrorCategory.ROBOTS_DENIED)
        self.assertIs(m.state, HarvestState.FAILED_PERMANENT)

    def test_het_luot_thi_thanh_VINH_VIEN(self):
        m = _muc(HarvestState.FETCHING, max_attempts=2)
        m = m.fail(ErrorCategory.NETWORK)
        self.assertIs(m.state, HarvestState.FAILED_TRANSIENT)
        m = m.schedule_retry().to(HarvestState.FETCHING)
        m = m.fail(ErrorCategory.NETWORK)
        self.assertIs(m.state, HarvestState.FAILED_PERMANENT,
                      "vượt trần phải thành vĩnh viễn, không quay vòng mãi")

    def test_vong_thu_lai_khong_the_vo_han(self):
        m = _muc(HarvestState.FETCHING, max_attempts=3)
        for _ in range(10):
            if m.is_terminal:
                break
            m = m.fail(ErrorCategory.NETWORK)
            if m.state is HarvestState.FAILED_TRANSIENT:
                m = m.schedule_retry()
                if m.state is HarvestState.RETRY_WAIT:
                    m = m.to(HarvestState.FETCHING)
        self.assertTrue(m.is_terminal)
        self.assertLessEqual(m.attempts, 3)

    def test_moi_loai_con_thu_lai_deu_nam_trong_RETRYABLE(self):
        for c in (ErrorCategory.NETWORK, ErrorCategory.HTTP_SERVER,
                  ErrorCategory.HTTP_RATE_LIMIT):
            self.assertIn(c, RETRYABLE)
        for c in (ErrorCategory.HTTP_NOT_FOUND, ErrorCategory.ROBOTS_DENIED,
                  ErrorCategory.PARSE):
            self.assertNotIn(c, RETRYABLE)

    def test_bao_loi_den_muon_KHONG_lat_nguoc_ket_qua_da_xong(self):
        """Một worker chậm báo hỏng sau khi mục đã COMPLETED."""
        with self.assertRaises(InvalidTransition):
            _muc(HarvestState.COMPLETED).fail(ErrorCategory.NETWORK)

    def test_xep_thu_lai_chi_tu_failed_transient(self):
        with self.assertRaises(InvalidTransition):
            _muc(HarvestState.FETCHING).schedule_retry()


class ChanDoanTachKhoiPhanLoaiTest(unittest.TestCase):
    def test_phan_loai_va_chan_doan_la_hai_truong_rieng(self):
        m = _muc(HarvestState.FETCHING).fail(ErrorCategory.HTTP_SERVER, "503 tu nguon")
        self.assertIs(m.error_category, ErrorCategory.HTTP_SERVER)
        self.assertIn("503", m.diagnostic)

    def test_chan_doan_bi_cat_va_loc_ky_tu_dieu_khien(self):
        doc = chr(10)
        m = _muc(HarvestState.FETCHING).fail(
            ErrorCategory.PARSE, "dong1" + doc + "GIA MAO" + "A" * 1000)
        self.assertNotIn(doc, m.diagnostic)
        self.assertLessEqual(len(m.diagnostic), 300)

    def test_sanitize_bo_ky_tu_khong_in_duoc(self):
        self.assertEqual(sanitize_diagnostic("a" + chr(0) + "b"), "ab")

    def test_chan_doan_rong_van_hop_le(self):
        m = _muc(HarvestState.FETCHING).fail(ErrorCategory.NETWORK)
        self.assertEqual(m.diagnostic, "")


class SapVaKhoiPhucTest(unittest.TestCase):
    """Trạng thái vòng đời là của MỘT lượt thực thi; sập là mất nó.

    Điều phải đúng: mọi trạng thái giữa chừng đều chiếu về `pending`, nên một
    lần khởi động lại nhặt mục đó lên làm lại từ đầu — không mục nào kẹt.
    """

    def _sap_tai(self, state):
        """Mô phỏng: tiến trình chết ở `state`, chỉ còn trạng thái ĐƯỢC LƯU."""
        luu = persisted_status(state)
        # Khoi dong lai: moi muc `pending` quay ve DISCOVERED.
        return luu, (ItemProgress(item_id="i1", state=HarvestState.DISCOVERED)
                     if luu is ScrapeItemStatus.PENDING else None)

    def test_sap_sau_FETCHING_thi_lam_lai_duoc(self):
        luu, moi = self._sap_tai(HarvestState.FETCHING)
        self.assertIs(luu, ScrapeItemStatus.PENDING)
        self.assertIsNotNone(moi)
        self.assertIs(moi.to(HarvestState.FETCHING).state, HarvestState.FETCHING)

    def test_sap_sau_NORMALIZED_thi_lam_lai_duoc(self):
        luu, moi = self._sap_tai(HarvestState.NORMALIZED)
        self.assertIs(luu, ScrapeItemStatus.PENDING)
        self.assertIsNotNone(moi)

    def test_sap_TRUOC_khi_PERSISTED_thi_lam_lai_duoc(self):
        luu, moi = self._sap_tai(HarvestState.PERSIST_PENDING)
        self.assertIs(luu, ScrapeItemStatus.PENDING)
        self.assertIsNotNone(moi)

    def test_moi_trang_thai_GIUA_CHUNG_deu_chieu_ve_pending(self):
        """Nếu một trạng thái giữa chừng chiếu về `review_ready` hay `failed`,
        mục đó sẽ KẸT sau một lần sập."""
        giua_chung = set(HarvestState) - TERMINAL - {HarvestState.PERSISTED}
        for s in giua_chung:
            self.assertIs(persisted_status(s), ScrapeItemStatus.PENDING,
                          f"{s} không chiếu về pending -> sập là kẹt")

    def test_muc_DA_XONG_khong_bi_lam_lai(self):
        luu, moi = self._sap_tai(HarvestState.COMPLETED)
        self.assertIs(luu, ScrapeItemStatus.REVIEW_READY)
        self.assertIsNone(moi, "mục đã xong không được nhặt lại")

    def test_khoi_dong_lai_mot_dot_DA_COMPLETED_khong_lam_gi(self):
        m = _muc(HarvestState.COMPLETED)
        self.assertTrue(m.is_terminal)
        self.assertIs(m.to(HarvestState.COMPLETED), m)


class WorkerTrungLapTest(unittest.TestCase):
    """Thi hành có thể at-least-once; việc GHI phải exactly-once về logic."""

    def test_hai_worker_cung_muc_ra_cung_danh_tinh(self):
        """Danh tính tất định là thứ chặn bản ghi trùng — không phải khoá.
        Lần ghi thứ hai là POST trùng `documentId` -> 409 -> "đã có"."""
        from server.scraper.run_state import item_id_for, run_id_from_fingerprint

        run_id = run_id_from_fingerprint("a" * 64)
        a = item_id_for(run_id, "b" * 64)
        b = item_id_for(run_id, "b" * 64)
        self.assertEqual(a, b)
        self.assertLessEqual(len(a), 36)

    def test_hai_worker_chay_song_song_hoi_tu_cung_ket_qua(self):
        goc = _muc(HarvestState.CHANGE_CLASSIFIED)
        w1 = goc.to(HarvestState.PERSIST_PENDING).to(HarvestState.PERSISTED)
        w2 = goc.to(HarvestState.PERSIST_PENDING).to(HarvestState.PERSISTED)
        self.assertEqual(w1.state, w2.state)
        self.assertEqual(w1.persisted, w2.persisted)

    def test_worker_cham_ghi_lai_PERSISTED_khong_no(self):
        """Worker thứ hai về đích sau — ghi lại cùng trạng thái là hợp lệ."""
        m = _muc(HarvestState.PERSISTED)
        self.assertIs(m.to(HarvestState.PERSISTED).state, HarvestState.PERSISTED)

    def test_worker_cham_KHONG_the_keo_lui_mot_muc_da_COMPLETED(self):
        with self.assertRaises(InvalidTransition):
            _muc(HarvestState.COMPLETED).to(HarvestState.PERSIST_PENDING)


class HuyTest(unittest.TestCase):
    def test_huy_giua_chung(self):
        m = _muc(HarvestState.FETCHING).cancel()
        self.assertIs(m.state, HarvestState.CANCELLED)
        self.assertIs(m.persisted, ScrapeItemStatus.SKIPPED)

    def test_huy_KHONG_lat_nguoc_muc_da_xong(self):
        m = _muc(HarvestState.COMPLETED)
        self.assertIs(m.cancel().state, HarvestState.COMPLETED)

    def test_huy_hai_lan_la_khong_thao_tac(self):
        m = _muc(HarvestState.FETCHING).cancel()
        self.assertIs(m.cancel().state, HarvestState.CANCELLED)

    def test_huy_duoc_tu_moi_trang_thai_chua_ket(self):
        for s in set(HarvestState) - TERMINAL:
            self.assertIs(_muc(s).cancel().state, HarvestState.CANCELLED, str(s))


class MotMucHongKhongLamHongCaDotTest(unittest.TestCase):
    def test_cac_muc_doc_lap_voi_nhau(self):
        a = ItemProgress(item_id="a", state=HarvestState.FETCHING)
        b = ItemProgress(item_id="b", state=HarvestState.FETCHING)
        a = a.fail(ErrorCategory.HTTP_NOT_FOUND)
        b = b.to(HarvestState.PARSED)
        self.assertIs(a.state, HarvestState.FAILED_PERMANENT)
        self.assertIs(b.state, HarvestState.PARSED, "một mục hỏng không kéo mục khác")


if __name__ == "__main__":
    unittest.main()
