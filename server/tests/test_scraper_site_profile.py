"""Kiem thu `server/scraper/site_profile.py` (Phase 4 Story Harvester V3)."""
from __future__ import annotations

import unittest

from server.scraper.discovery import (
    DiscoveryProposal, PaginationStrategy, SourceConfidence,
)
from server.scraper.contract import ScraperTier
from server.scraper.site_profile import (
    CONSECUTIVE_FAILURE_THRESHOLD, MockSiteProfileStore, ProfileStatus,
    profile_from_proposal,
)


def _proposal() -> DiscoveryProposal:
    return DiscoveryProposal(
        source_url="https://vidu.test/truyen/abc",
        canonical_url="https://vidu.test/truyen/abc",
        work_title="Truyện ABC",
        author="Tác giả",
        description="Mô tả",
        index_url="https://vidu.test/truyen/abc",
        chapter_count_estimate=5,
        chapter_url_pattern=r"/truyen/abc/chuong-\d+",
        content_container_candidate="div.chapter-content",
        pagination_strategy=PaginationStrategy.NONE,
        fetch_tier=ScraperTier.DIRECT_HTTP,
        confidence=SourceConfidence.HIGH,
        evidence=["..."],
        sample_chapter_urls=["https://vidu.test/truyen/abc/chuong-1"],
    )


class ProfileFromProposalTest(unittest.TestCase):
    def test_tao_profile_LEARNING_tu_de_xuat(self):
        profile = profile_from_proposal(_proposal())

        assert profile.domain == "vidu.test"
        assert profile.status == ProfileStatus.LEARNING
        assert profile.revision == 1
        assert profile.chapter_pattern == r"/truyen/abc/chuong-\d+"
        assert profile.content_fingerprint == "div.chapter-content"


class UpsertAndLookupTest(unittest.TestCase):
    def test_upsert_roi_get_tra_ve_dung_profile(self):
        store = MockSiteProfileStore()
        profile = profile_from_proposal(_proposal())

        saved = store.upsert(profile)

        assert saved.created_at
        assert saved.updated_at
        assert store.get("vidu.test") is saved

    def test_upsert_lai_giu_nguyen_created_at_ban_dau(self):
        store = MockSiteProfileStore(now_fn=iter(["t1", "t2"]).__next__)
        profile = profile_from_proposal(_proposal())

        first = store.upsert(profile)
        second = store.upsert(profile)

        assert first.created_at == "t1"
        assert second.created_at == "t1"
        assert second.updated_at == "t2"


class RecordSuccessTest(unittest.TestCase):
    def test_lan_thanh_cong_dau_tien_chuyen_LEARNING_sang_VERIFIED(self):
        store = MockSiteProfileStore()
        store.upsert(profile_from_proposal(_proposal()))

        updated = store.record_success("vidu.test")

        assert updated.status == ProfileStatus.VERIFIED
        assert updated.success_count == 1
        assert updated.consecutive_failures == 0
        assert updated.last_success_at

    def test_thanh_cong_reset_chuoi_loi_lien_tiep(self):
        store = MockSiteProfileStore()
        store.upsert(profile_from_proposal(_proposal()))
        store.record_failure("vidu.test")
        store.record_failure("vidu.test")

        updated = store.record_success("vidu.test")

        assert updated.consecutive_failures == 0
        assert updated.status == ProfileStatus.VERIFIED


class RecordFailureTest(unittest.TestCase):
    def test_duoi_nguong_van_giu_trang_thai(self):
        store = MockSiteProfileStore()
        store.upsert(profile_from_proposal(_proposal()))
        store.record_success("vidu.test")

        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD - 1):
            updated = store.record_failure("vidu.test")

        assert updated.status == ProfileStatus.VERIFIED
        assert updated.consecutive_failures == CONSECUTIVE_FAILURE_THRESHOLD - 1

    def test_du_nguong_chuyen_sang_DEGRADED(self):
        store = MockSiteProfileStore()
        store.upsert(profile_from_proposal(_proposal()))
        store.record_success("vidu.test")

        for _ in range(CONSECUTIVE_FAILURE_THRESHOLD):
            updated = store.record_failure("vidu.test")

        assert updated.status == ProfileStatus.DEGRADED
        assert not updated.is_usable

    def test_DISABLED_khong_bi_record_failure_lam_thay_doi(self):
        store = MockSiteProfileStore()
        store.upsert(profile_from_proposal(_proposal()))
        store.save("vidu.test", status=ProfileStatus.DISABLED)

        updated = store.record_failure("vidu.test")

        assert updated.status == ProfileStatus.DISABLED
        assert not updated.is_usable


class IsUsableTest(unittest.TestCase):
    def test_LEARNING_va_VERIFIED_usable_DEGRADED_va_DISABLED_khong(self):
        base = profile_from_proposal(_proposal())
        assert base.is_usable
        assert base.__class__(**{**base.__dict__, "status": ProfileStatus.VERIFIED}).is_usable
        assert not base.__class__(**{**base.__dict__, "status": ProfileStatus.DEGRADED}).is_usable
        assert not base.__class__(**{**base.__dict__, "status": ProfileStatus.DISABLED}).is_usable
