"""Kiem thu `compute_source_health` (Auto-Ingestion Phase 4) — ham THUAN,
khong I/O, tinh trang thai suc khoe tong hop cua MOT TrustedSource tu cac
truong da co san. Xem dac ta "Use deterministic rules and test them"."""

import unittest

from server.trusted_source_domain import (
    SourceHealth,
    SubscriptionStatus,
    TrustedSource,
    TrustedSourceType,
    compute_source_health,
)


def _nguon(**overrides) -> TrustedSource:
    mac_dinh = dict(
        source_type=TrustedSourceType.YOUTUBE_CHANNEL,
        youtube_channel_id="UC" + "x" * 22, display_name="Kênh test",
        enabled=True, auto_discover=False,
    )
    mac_dinh.update(overrides)
    return TrustedSource(**mac_dinh)


class SourceHealthTest(unittest.TestCase):
    def test_tam_dung_luon_la_disabled_bat_ke_truong_khac(self):
        nguon = _nguon(enabled=False, auto_discover=True,
                       subscription_status=SubscriptionStatus.FAILED)
        suc_khoe, ly_do = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.DISABLED)
        self.assertTrue(ly_do)

    def test_khong_auto_discover_khong_loi_gi_la_healthy(self):
        nguon = _nguon(auto_discover=False)
        suc_khoe, ly_do = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.HEALTHY)
        self.assertEqual(ly_do, [])

    def test_auto_discover_dang_ky_active_la_healthy(self):
        nguon = _nguon(auto_discover=True, subscription_status=SubscriptionStatus.ACTIVE)
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.HEALTHY)

    def test_auto_discover_chua_tung_dang_ky_la_action_required(self):
        nguon = _nguon(auto_discover=True, subscription_status=SubscriptionStatus.NONE)
        suc_khoe, ly_do = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.ACTION_REQUIRED)
        self.assertTrue(ly_do)

    def test_auto_discover_het_han_la_action_required(self):
        nguon = _nguon(auto_discover=True, subscription_status=SubscriptionStatus.EXPIRED)
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.ACTION_REQUIRED)

    def test_auto_discover_dang_ky_that_bai_la_action_required(self):
        nguon = _nguon(auto_discover=True, subscription_status=SubscriptionStatus.FAILED)
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.ACTION_REQUIRED)

    def test_auto_discover_dang_cho_xac_minh_van_la_healthy(self):
        """PENDING chua phai loi — con dang cho hub xac minh, chua the hanh
        dong gi them, khong nen bao dong som."""
        nguon = _nguon(auto_discover=True, subscription_status=SubscriptionStatus.PENDING)
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.HEALTHY)

    def test_lan_quet_gan_nhat_loi_sau_lan_thanh_cong_la_degraded(self):
        nguon = _nguon(
            last_success_at="2026-08-20T00:00:00.000000+00:00",
            last_error_at="2026-08-20T01:00:00.000000+00:00",
            last_error_message="Lỗi mạng thoáng qua.")
        suc_khoe, ly_do = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.DEGRADED)
        self.assertIn("Lỗi mạng thoáng qua.", ly_do[0])

    def test_loi_truoc_do_nhung_da_thanh_cong_sau_do_la_healthy_tu_phuc_hoi(self):
        nguon = _nguon(
            last_error_at="2026-08-20T00:00:00.000000+00:00",
            last_success_at="2026-08-20T01:00:00.000000+00:00")
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.HEALTHY)

    def test_loi_ma_chua_tung_thanh_cong_lan_nao_la_degraded(self):
        nguon = _nguon(last_error_at="2026-08-20T00:00:00.000000+00:00", last_success_at="")
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.DEGRADED)

    def test_action_required_uu_tien_hon_degraded(self):
        nguon = _nguon(
            auto_discover=True, subscription_status=SubscriptionStatus.EXPIRED,
            last_error_at="2026-08-20T01:00:00.000000+00:00", last_success_at="")
        suc_khoe, _ = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.ACTION_REQUIRED)

    def test_khong_hoat_dong_gan_day_khong_bi_coi_la_benh(self):
        """Dac ta ro: KHONG suy ra khong khoe chi vi chua co video moi gan
        day — nguon hoan toan moi, chua tung quet/dang ky gi, van HEALTHY."""
        nguon = _nguon()
        suc_khoe, ly_do = compute_source_health(nguon)
        self.assertEqual(suc_khoe, SourceHealth.HEALTHY)
        self.assertEqual(ly_do, [])


if __name__ == "__main__":
    unittest.main()
