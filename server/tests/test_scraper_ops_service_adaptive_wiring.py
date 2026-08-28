"""
P2 (Story Harvester V3 overnight hardening) — kiem thu VIEC NOI DAY
(orchestration) cua `scraper_ops_service.confirm_unknown_source` voi
`scrapling_relocation.attempt_adaptive_relocation`, TACH RIENG khoi kiem
thu chinh co che dinh vi lai (xem `test_scraper_adaptive_relocation.py`,
18 test dung Scrapling THAT, khong mock).

O DAY CO Y MOCK `attempt_adaptive_relocation`/`is_scrapling_available`/
`save_verified_element` — muc tieu la kiem tra LOGIC DIEU PHOI dung
(goi khi nao, khong goi khi nao, xu ly ket qua the nao), khong phai lap
lai bang chung "Scrapling tim dung ung vien" (da co o file tren). Mock o
DAY, that o do — hai lop kiem thu bo sung cho nhau, khong trung lap."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from server.scraper.adapters.scrapling_relocation import AdaptiveRelocationOutcome
from server.scraper.http_fetcher import FixtureFetcher
from server.scraper.run_state import MockScrapeRunStore
from server.scraper.self_healing import RelocationConfidence
from server.scraper.site_profile import MockSiteProfileStore, ProfileStatus
from server.scraper_ops_service import ScraperOpsService

_MOD = "server.scraper_ops_service"


def _trang_hop_le(so: int) -> str:
    """CO Y dai/nhieu doan (khong chi mot doan ngan) — phat hien THAT khi
    viet bai test nay: mot fixture chi-mot-doan-ngan khong du diem de Tier
    0 (`content_extraction._score`, nguong HIGH=40) tu dat HIGH, khien cac
    test "khong can Scrapling" that bai VI LY DO SAI (Tier 0 chua du manh,
    khong phai vi logic dieu phoi sai) — xem lich su dieu tra truc tiep
    tren `_score()` truoc khi viet fixture nay."""
    doan = (
        f"đủ dài để vượt ngưỡng tối thiểu cho một vùng nội dung hợp lệ, "
        f"và khác biệt thật sự với các chương khác trong cùng bộ truyện "
        f"thử nghiệm số {so} của trường hợp kiểm thử nối dây, viết thêm "
        f"vài câu nữa cho thật chắc chắn vượt hẳn ngưỡng điểm số cần thiết")
    doan_van = "".join(
        f"<p>Đoạn văn bản thứ {j} của riêng chương số {so}, {doan}.</p>"
        for j in range(1, 5))
    # `<h1>` KHOP chinh xac `chapter_title` (series title do
    # `proposal.work_title` truyen vao `validate_relocated_content`) — neu
    # khong, tien thuong +15 diem "tieu de khop" khong bao gio kich hoat,
    # va Tier 0 khong the vuot nguong HIGH=40 du them bao nhieu doan van
    # (phat hien qua do truc tiep `_score()` truoc khi sua fixture nay).
    return (
        f'<html><head><title>Chương {so}</title></head><body>'
        f'<div class="chapter-content"><h1>Truyện Nối Dây</h1>{doan_van}</div>'
        "</body></html>")


def _dung_svc(base: str, profile_store):
    index = (
        '<html><head><title>Truyện Nối Dây</title></head><body><ul>'
        + "".join(f'<li><a href="/truyen/x/chuong-{i}">Chương {i}</a></li>'
                 for i in range(1, 6))
        + "</ul></body></html>")
    pages = {f"{base}/truyen/x": index}
    for i in range(1, 6):
        pages[f"{base}/truyen/x/chuong-{i}"] = _trang_hop_le(i)
    svc = ScraperOpsService(
        MockScrapeRunStore(), fetcher_factory=lambda **_kw: FixtureFetcher(dict(pages)),
        profile_store=profile_store)
    return svc, pages


class SaveOnFreshConfirmTest(unittest.TestCase):
    """"known-good chapter element -> save/fingerprint" — buoc luu PHAI
    chay tren MOI lan xac nhan thanh cong (khong chi khi DEGRADED)."""

    def test_xac_nhan_lan_dau_luu_dau_van_tay_thich_ung(self):
        profile_store = MockSiteProfileStore()
        svc, _ = _dung_svc("https://noi-day-luu.example", profile_store)

        confirmed = svc.confirm_unknown_source("https://noi-day-luu.example/truyen/x")

        self.assertTrue(confirmed["profile"].adaptive_fingerprint_json)
        saved = profile_store.get("noi-day-luu.example")
        self.assertTrue(saved.adaptive_fingerprint_json)
        fp = json.loads(saved.adaptive_fingerprint_json)
        self.assertEqual(fp.get("tag"), "div")

    def test_scrapling_khong_san_sang_khong_luu_gi_khong_crash(self):
        profile_store = MockSiteProfileStore()
        svc, _ = _dung_svc("https://noi-day-tat.example", profile_store)

        with patch(f"{_MOD}.is_scrapling_available", return_value=False):
            confirmed = svc.confirm_unknown_source("https://noi-day-tat.example/truyen/x")

        self.assertEqual(confirmed["profile"].status, ProfileStatus.LEARNING)
        self.assertEqual(
            profile_store.get("noi-day-tat.example").adaptive_fingerprint_json, "")


class DegradedEscalationOrchestrationTest(unittest.TestCase):
    """Mo phong `attempt_adaptive_relocation` (da duoc CHUNG MINH THAT o
    `test_scraper_adaptive_relocation.py`) de kiem tra CHINH XAC logic
    dieu phoi trong `confirm_unknown_source` — khi nao goi, khi nao
    khong, va xu ly ba muc confidence the nao."""

    def _thiet_lap_degraded(self, base_host: str):
        base = f"https://{base_host}"
        profile_store = MockSiteProfileStore()
        svc, pages = _dung_svc(base, profile_store)
        svc.confirm_unknown_source(f"{base}/truyen/x")
        profile_store.save(base_host, status=ProfileStatus.DEGRADED,
                          consecutive_failures=3,
                          adaptive_fingerprint_json=json.dumps({"tag": "div"}))
        return svc, profile_store, base

    def test_khong_goi_adaptive_khi_tier0_da_HIGH(self):
        """Yeu cau "The normal successful selector path should not
        unnecessarily invoke adaptive relocation" — chuong mau van dung
        `chapter-content` (Tier 0 tu dat HIGH), KHONG duoc goi Scrapling."""
        svc, profile_store, base = self._thiet_lap_degraded("nodai-khong-can.example")
        with patch(f"{_MOD}.attempt_adaptive_relocation") as gia_lap:
            confirmed = svc.confirm_unknown_source(f"{base}/truyen/x")
        gia_lap.assert_not_called()
        self.assertEqual(confirmed["profile"].status, ProfileStatus.LEARNING)

    def test_adaptive_HIGH_khong_mo_ho_nang_ket_qua_len_thanh_cong(self):
        """Ep Tier 0 that bai (patch validate_relocated_content tra ve
        LOW) de buoc phai di qua nhanh adaptive — outcome HIGH PHAI duoc
        chap nhan VA ghi content_fingerprint moi tu candidate_selector."""
        svc, profile_store, base = self._thiet_lap_degraded("nodai-high.example")
        tier0_low = self._ket_qua_gia(RelocationConfidence.LOW)
        adaptive_high = AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.HIGH,
            evidence=["Scrapling định vị lại thành công."],
            clean_text="Nội dung chương đã định vị lại thành công qua Scrapling.",
            is_ambiguous=False, candidate_selector="#reader-2024",
            relocation_attempted=True)
        with patch(f"{_MOD}.validate_relocated_content", return_value=tier0_low), \
             patch(f"{_MOD}.attempt_adaptive_relocation", return_value=adaptive_high) as gia_lap:
            confirmed = svc.confirm_unknown_source(f"{base}/truyen/x")
        gia_lap.assert_called_once()
        self.assertEqual(confirmed["profile"].status, ProfileStatus.LEARNING)
        self.assertEqual(confirmed["profile"].content_fingerprint, "#reader-2024")

    def test_adaptive_MEDIUM_yeu_cau_review_khong_tu_dong_chap_nhan(self):
        svc, profile_store, base = self._thiet_lap_degraded("nodai-medium.example")
        tier0_low = self._ket_qua_gia(RelocationConfidence.LOW)
        adaptive_medium = AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.MEDIUM,
            evidence=["Mơ hồ, cần operator xem lại."],
            clean_text="một ít nội dung", is_ambiguous=True,
            candidate_selector="#maybe", relocation_attempted=True)
        with patch(f"{_MOD}.validate_relocated_content", return_value=tier0_low), \
             patch(f"{_MOD}.attempt_adaptive_relocation", return_value=adaptive_medium):
            with self.assertRaises(ValueError) as ctx:
                svc.confirm_unknown_source(f"{base}/truyen/x")
        self.assertIn("MEDIUM", str(ctx.exception))
        # PHAI VAN con DEGRADED — khong duoc am tham ghi de.
        self.assertEqual(profile_store.get("nodai-medium.example").status,
                         ProfileStatus.DEGRADED)

    def test_adaptive_LOW_giu_nguyen_hanh_vi_tu_choi_cu(self):
        svc, profile_store, base = self._thiet_lap_degraded("nodai-low.example")
        tier0_low = self._ket_qua_gia(RelocationConfidence.LOW)
        adaptive_low = AdaptiveRelocationOutcome(
            confidence=RelocationConfidence.LOW,
            evidence=["Không định vị lại được."], relocation_attempted=True)
        with patch(f"{_MOD}.validate_relocated_content", return_value=tier0_low), \
             patch(f"{_MOD}.attempt_adaptive_relocation", return_value=adaptive_low):
            with self.assertRaises(ValueError):
                svc.confirm_unknown_source(f"{base}/truyen/x")
        self.assertEqual(profile_store.get("nodai-low.example").status,
                         ProfileStatus.DEGRADED)

    def test_tier0_MEDIUM_khong_co_adaptive_van_duoc_chap_nhan_nhu_cu(self):
        """Phat hien qua review doc lap (Codex): nhanh nay (Tier 0 tra ve
        MEDIUM — khong phai LOW — VA khong co dau van tay thich ung/
        Scrapling khong san sang de leo thang) truoc do KHONG co test
        rieng, chi duoc suy ra tu docstring. Xac nhan RO RANG day la hanh
        vi CO CHU DICH (giu nguyen ngu nghia MEDIUM-duoc-chap-nhan cua
        nhanh KHONG-DEGRADED tu truoc PR nay), khong phai mot lo hong bo
        sot: kiem tra cau truc THEM (Phase 5, MEDIUM tu Scrapling) CHI
        nghiem ngat hon KHI THAT SU chay — khong chay duoc thi khong the
        nghiem ngat hon Tier 0 duoc."""
        svc, profile_store, base = self._thiet_lap_degraded("nodai-tier0-medium.example")
        tier0_medium = self._ket_qua_gia(RelocationConfidence.MEDIUM)
        with patch(f"{_MOD}.validate_relocated_content", return_value=tier0_medium), \
             patch(f"{_MOD}.is_scrapling_available", return_value=False), \
             patch(f"{_MOD}.attempt_adaptive_relocation") as gia_lap:
            confirmed = svc.confirm_unknown_source(f"{base}/truyen/x")
        gia_lap.assert_not_called()
        self.assertEqual(confirmed["profile"].status, ProfileStatus.LEARNING)

    def test_khong_co_dau_van_tay_cu_bo_qua_adaptive_hoan_toan(self):
        """Domain DEGRADED nhung CHUA TUNG luu dau van tay (vd tao truoc
        khi tinh nang nay ton tai) — PHAI lui ve hanh vi Tier 0 CU HOAN
        TOAN, khong goi Scrapling (khong co gi de dinh vi lai tu).

        CO Y xay dung SiteProfile DEGRADED TRUC TIEP qua `upsert()` (KHONG
        goi `confirm_unknown_source` truoc) — goi ham do se TU luu dau van
        tay ngay tu lan xac nhan dau tien (dung tinh nang moi cua chinh PR
        nay), khien "chua tung luu dau van tay" khong the tai hien duoc
        qua duong do; mo phong dung mot profile CO TRUOC tinh nang nay."""
        from dataclasses import replace as _replace
        from server.scraper.site_profile import profile_from_proposal
        base = "https://nodai-khong-fp.example"
        profile_store = MockSiteProfileStore()
        svc, pages = _dung_svc(base, profile_store)
        # Xay mot SiteProfile hop le (co chapter_pattern that) nhung KHONG
        # qua confirm_unknown_source — gia lap "profile tu truoc khi co
        # tinh nang luu dau van tay".
        result = svc.discover(f"{base}/truyen/x")
        profile_moi = profile_from_proposal(result["proposal"])
        profile_store.upsert(_replace(
            profile_moi, status=ProfileStatus.DEGRADED, consecutive_failures=3))

        with patch(f"{_MOD}.attempt_adaptive_relocation") as gia_lap:
            confirmed = svc.confirm_unknown_source(f"{base}/truyen/x")
        gia_lap.assert_not_called()
        self.assertEqual(confirmed["profile"].status, ProfileStatus.LEARNING)

    @staticmethod
    def _ket_qua_gia(confidence: RelocationConfidence):
        from server.scraper.self_healing import RelocationValidationResult
        return RelocationValidationResult(
            confidence=confidence, evidence=["Tier 0 giả lập."], clean_text="")


if __name__ == "__main__":
    unittest.main()
