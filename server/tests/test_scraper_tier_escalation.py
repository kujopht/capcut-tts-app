import unittest

from server.scraper.tier_escalation import (
    EscalationDecision, TierFailureReason, classify_page_signal, decide_escalation,
)


def _page(body: str) -> str:
    return f"<html><body><div>{body}</div></body></html>"


class ClassifyPageSignalTest(unittest.TestCase):
    def test_captcha_duoc_nhan_dien(self):
        html = _page("Please complete the CAPTCHA to continue browsing this site.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.CAPTCHA)

    def test_dang_nhap_duoc_nhan_dien(self):
        html = _page("Vui lòng đăng nhập để đọc tiếp nội dung chương này.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.AUTH_REQUIRED)

    def test_paywall_duoc_nhan_dien(self):
        html = _page("Subscribe to read the rest of this premium chapter today.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.PAYWALL)

    def test_khong_tim_thay_trang_duoc_nhan_dien(self):
        html = _page("404 Not Found — trang không tồn tại trên máy chủ này.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.NOT_FOUND)

    def test_can_javascript_duoc_nhan_dien_khi_van_ban_qua_ngan(self):
        html = _page("Please enable JavaScript to continue.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.JS_REQUIRED)

    def test_khong_gan_javascript_neu_van_ban_du_dai_du_co_nhac_toi(self):
        # Trang co NHAC den javascript nhung van co nhieu van ban khac —
        # khong phai dau hieu "gan nhu trong, can JS render", chi la mot
        # trang binh thuong tinh co nhac toi tu do dau nhung noi khac.
        padding = "Nội dung chương thật sự dài và đầy đủ. " * 10
        html = _page(padding + " Please enable JavaScript to continue reading more.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.NO_STRUCTURE_MATCH)

    def test_mac_dinh_no_structure_match_khi_khong_tin_hieu_nao_khop(self):
        html = _page("Đây là một trang bình thường không có dấu hiệu chặn nào cả.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.NO_STRUCTURE_MATCH)

    def test_captcha_uu_tien_hon_dang_nhap_khi_ca_hai_cung_xuat_hien(self):
        html = _page("Vui lòng đăng nhập, sau đó complete the CAPTCHA to continue.")
        self.assertEqual(classify_page_signal(html), TierFailureReason.CAPTCHA)


class DecideEscalationTest(unittest.TestCase):
    def test_auth_luon_tu_choi_du_tier1_kha_dung(self):
        ket_qua = decide_escalation(TierFailureReason.AUTH_REQUIRED, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)

    def test_captcha_luon_tu_choi_du_tier1_kha_dung(self):
        ket_qua = decide_escalation(TierFailureReason.CAPTCHA, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)

    def test_paywall_luon_tu_choi_du_tier1_kha_dung(self):
        ket_qua = decide_escalation(TierFailureReason.PAYWALL, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)

    def test_not_found_tu_choi_khong_nang_tang(self):
        ket_qua = decide_escalation(TierFailureReason.NOT_FOUND, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)

    def test_js_required_bao_cao_tier_2_khong_tu_dong_lam_gi(self):
        ket_qua = decide_escalation(TierFailureReason.JS_REQUIRED, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.REPORT_NEEDS_TIER_2)

    def test_no_structure_match_nang_tier1_khi_kha_dung(self):
        ket_qua = decide_escalation(TierFailureReason.NO_STRUCTURE_MATCH, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.ESCALATE_TIER_1)

    def test_no_structure_match_tu_choi_khi_tier1_khong_kha_dung(self):
        ket_qua = decide_escalation(TierFailureReason.NO_STRUCTURE_MATCH, tier1_available=False)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)

    def test_mac_dinh_tier1_khong_kha_dung(self):
        ket_qua = decide_escalation(TierFailureReason.NO_STRUCTURE_MATCH)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)

    def test_evidence_khong_bao_gio_nhac_toi_cloakbrowser_hay_stealth(self):
        for reason in TierFailureReason:
            for tier1 in (True, False):
                ket_qua = decide_escalation(reason, tier1_available=tier1)
                lowered = ket_qua.evidence.lower()
                self.assertNotIn("cloakbrowser", lowered)
                self.assertNotIn("stealth", lowered)
                self.assertNotIn("ngụy trang", lowered)


class RouterHardeningInvalidEscalationTriggersTest(unittest.TestCase):
    """Overnight P9 ("direct HTTP vs Scrapling router hardening"): kiem
    tra RO RANG cac vi du KHONG duoc kich hoat nang tang, theo dung danh
    sach yeu cau."""

    def test_mot_loi_mang_tam_thoi_khong_bao_gio_di_toi_tier_escalation(self):
        """Mot loi mang (timeout/ket noi) xay ra TRUOC KHI co bat ky HTML
        nao de phan loai — `classify_page_signal`/`decide_escalation` chi
        nhan MOT chuoi HTML da fetch THANH CONG lam dau vao, khong co
        tham so nao cho "loi mang". Kiem tra kien truc: ham nay khong the
        nao duoc goi neu chua co phan hoi HTML that su — day la thuoc
        tinh CUA CHU KY GOI (`HttpFetcher.fetch` nem `FetchError` truoc
        khi `discovery.py`/adapter co co hoi goi `classify_page_signal`),
        khong phai mot nhanh trong ham can kiem tra rieng."""
        import inspect
        from server.scraper.tier_escalation import classify_page_signal
        sig = inspect.signature(classify_page_signal)
        # Tham so DUY NHAT la HTML da fetch duoc — khong co "loi mang"/
        # "exception" nao co the dua vao day, xac nhan mot loi mang KHONG
        # THE nao kich hoat duong nay (no chi hoat dong tren noi dung DA
        # CO, khong tren that bai fetch).
        self.assertEqual(list(sig.parameters.keys()), ["raw_html"])

    def test_url_bi_hong_that_bai_ro_rang_khong_kich_hoat_escalation(self):
        from server.scraper.discovery import UnknownSiteDiscoveryEngine
        from server.scraper.http_fetcher import FetchError, HttpFetcher

        for url in ("not a url at all", "", "   ", "javascript:alert(1)"):
            # `max_retries=0`/`min_delay_seconds=0`: mot URL hong LA loi
            # VINH VIEN, khong tu khac di khi thu lai — khong can retry/
            # rate-limit that de kiem tra chi rieng "that bai ro rang".
            engine = UnknownSiteDiscoveryEngine(
                HttpFetcher(max_retries=0, min_delay_seconds=0, respect_robots=False))
            with self.assertRaises(FetchError):
                engine.discover(url)

    def test_404_khong_lien_quan_khong_kich_hoat_escalation(self):
        """404 that su (trang khong ton tai) phai tu choi han (Tier 3),
        KHONG BAO GIO duoc coi la "co the nang tang de thu lai"."""
        html = _page("404 Not Found — trang không tồn tại trên máy chủ này.")
        tin_hieu = classify_page_signal(html)
        self.assertEqual(tin_hieu, TierFailureReason.NOT_FOUND)
        ket_qua = decide_escalation(tin_hieu, tier1_available=True)
        self.assertEqual(ket_qua.decision, EscalationDecision.REFUSE_MANUAL_REQUIRED)


if __name__ == "__main__":
    unittest.main()
