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


if __name__ == "__main__":
    unittest.main()
