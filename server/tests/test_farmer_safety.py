"""Farmer — cac tinh chat AN TOAN.

Day la nhung bat bien ma neu vo, farmer se lam hong thu khac chu khong chi
tu no that bai:

1. **Fail closed o moi cong.** Khong kiem duoc trung lap, khong do duoc dia,
   khong danh gia duoc -> KHONG san xuat. Doan bua o bat ky cong nao trong
   ba cong nay deu tao ban trung tren production, lam day dia cua hai worker
   dung chung may, hoac xuat ban noi dung chua ai duyet.
2. **Khong bia thi khong xuat ban.** Cong CUNG, khong phai "nen co".
3. **Khu trung lap tat dinh.** Cung nguon -> cung khoa, khong phu thuoc thoi
   gian/thu tu/tieu de.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from server.farmer.covers import CoverGate, CoverRequired
from server.farmer.dedup import (
    LANE_AUDIO, LANE_TEXT, DedupError, DedupIndex, work_key,
)
from server.farmer.quotas import FarmerQuotas, QuotaExceeded
from server.farmer.review import (
    QualityReviewer, ReviewUnavailable, _parse_verdict,
)
from server.domain import MediaAsset, MediaProcessingState, MediaType, StorageTier
from server.llm_gateway.provider import LLMCompletion, LLMProviderError


# --------------------------------------------------------------- dedup ----
class WorkKeyTest(unittest.TestCase):
    def test_same_source_gives_same_key(self):
        a = work_key(LANE_TEXT, "https://example.com/story/1")
        b = work_key(LANE_TEXT, "https://example.com/story/1")
        self.assertEqual(a.key, b.key)

    def test_key_survives_url_noise(self):
        """`?utm_source=`, dau `/` cuoi, hoa/thuong host — cung mot tac pham."""
        goc = work_key(LANE_TEXT, "https://example.com/story/1")
        for bien_the in ("https://example.com/story/1/",
                         "https://example.com/story/1?utm_source=fb",
                         "https://EXAMPLE.com/story/1"):
            with self.subTest(url=bien_the):
                self.assertEqual(work_key(LANE_TEXT, bien_the).key, goc.key)

    def test_lanes_do_not_collide(self):
        """Cung URL o hai lan la hai cong viec khac — san pham cuoi khac han."""
        self.assertNotEqual(work_key(LANE_TEXT, "https://e.com/a").key,
                            work_key(LANE_AUDIO, "https://e.com/a").key)

    def test_key_is_prefixed_and_not_confusable(self):
        k = work_key(LANE_TEXT, "https://e.com/a").key
        self.assertTrue(k.startswith("fw_"))
        self.assertFalse(k.startswith(("cmq_", "nov_")))

    def test_bad_lane_and_empty_url_are_refused(self):
        with self.assertRaises(ValueError):
            work_key("khong_co_lan_nay", "https://e.com/a")
        with self.assertRaises(ValueError):
            work_key(LANE_TEXT, "")


class _Store:
    def __init__(self, *, queue=None, novels=None, raise_on=None):
        self._queue = queue or {}
        self._novels = novels or []
        self._raise_on = raise_on

    def get_queue_item(self, item_id):
        if self._raise_on == "queue":
            raise RuntimeError("mang hong")
        if item_id not in self._queue:
            raise _NotFound("Khong tim thay ban ghi.")
        return self._queue[item_id]

    def find_novels(self, owner_id=None, limit=None, **kw):
        if self._raise_on == "novels":
            raise RuntimeError("mang hong")
        return list(self._novels), len(self._novels)


class _NotFound(Exception):
    pass


_NotFound.__name__ = "NotFoundError"


class _Novel:
    def __init__(self, url):
        self.external_source_url = url


class DedupFailClosedTest(unittest.TestCase):
    def test_missing_queue_item_is_not_yet_farmed(self):
        idx = DedupIndex(_Store(queue={}))
        self.assertFalse(idx.audio_already_queued("cmq_x"))

    def test_existing_queue_item_is_already_farmed(self):
        idx = DedupIndex(_Store(queue={"cmq_x": object()}))
        self.assertTrue(idx.audio_already_queued("cmq_x"))

    def test_store_failure_raises_instead_of_reporting_not_farmed(self):
        """Doc 'mang hong' thanh 'chua gat' se gat lai lan hai va tao ban
        trung tren production."""
        idx = DedupIndex(_Store(raise_on="queue"))
        with self.assertRaises(DedupError):
            idx.audio_already_queued("cmq_x")

    def test_text_dedup_matches_on_canonical_url(self):
        idx = DedupIndex(_Store(novels=[_Novel("https://e.com/a?utm_source=x")]))
        self.assertTrue(idx.text_already_farmed("https://e.com/a/"))

    def test_text_dedup_reports_new_source_as_new(self):
        idx = DedupIndex(_Store(novels=[_Novel("https://e.com/a")]))
        self.assertFalse(idx.text_already_farmed("https://e.com/khac"))

    def test_text_dedup_fails_closed_on_store_error(self):
        idx = DedupIndex(_Store(raise_on="novels"))
        with self.assertRaises(DedupError):
            idx.text_already_farmed("https://e.com/a")

    def test_hitting_the_scan_ceiling_fails_closed(self):
        """Cham tran quet nghia la co the co ban ghi cu hon khong nhin thay —
        tao ban trung am tham la ket qua te nhat."""
        from server.farmer import dedup as d
        nhieu = [_Novel(f"https://e.com/{n}") for n in range(d.NOVEL_SCAN_LIMIT)]
        idx = DedupIndex(_Store(novels=nhieu))
        with self.assertRaises(DedupError):
            idx.text_already_farmed("https://e.com/moi")


# -------------------------------------------------------------- quotas ----
class DiskGuardTest(unittest.TestCase):
    def test_low_disk_blocks_new_work(self):
        q = FarmerQuotas(min_free_disk_bytes=10 ** 12)
        with mock.patch.object(FarmerQuotas, "free_disk_bytes", return_value=1):
            with self.assertRaises(QuotaExceeded):
                q.check_disk()

    def test_unmeasurable_disk_fails_closed(self):
        """Khong DO duoc cung la mot lan tu choi — doan 'chac con cho' roi tai
        tiep chinh la cach lam day dia cua hai worker dung chung may nay."""
        q = FarmerQuotas()
        with mock.patch.object(FarmerQuotas, "free_disk_bytes",
                               side_effect=OSError("duong dan bien mat")):
            with self.assertRaises(QuotaExceeded):
                q.check_disk()

    def test_healthy_disk_allows_work(self):
        q = FarmerQuotas(min_free_disk_bytes=1)
        with mock.patch.object(FarmerQuotas, "free_disk_bytes", return_value=10 ** 12):
            q.check_disk()

    def test_slot_checks_disk_before_taking_the_slot(self):
        """Cong dia dong thi KHONG duoc chiem khe — mot may sap day khong nen
        nhan them viec chi de roi that bai o giua."""
        q = FarmerQuotas(max_concurrent_downloads=1, min_free_disk_bytes=10 ** 12)
        with mock.patch.object(FarmerQuotas, "free_disk_bytes", return_value=1):
            self.assertIsNone(q.try_slot(FarmerQuotas.DOWNLOAD, check_disk=True))
        self.assertEqual(q.snapshot().in_flight[FarmerQuotas.DOWNLOAD], 0)


class HarvesterTokenTest(unittest.TestCase):
    """Token dich vu phai lay duoc TREN LINUX.

    Su co that (2026-09-08): farmer sap lien tuc tren may san xuat vi
    `harvester_token()` hoi thang `fanfic_credential_broker`, von doc Windows
    Credential Manager qua DPAPI va nem ngay tren Linux. `--dry-run` bo qua
    token nen khong bai test cuc bo nao cham toi duong do.
    """

    def test_environment_is_read_before_the_windows_only_broker(self):
        from server.farmer.adapters import ENV_HARVESTER_TOKEN, harvester_token

        with mock.patch.dict("os.environ", {ENV_HARVESTER_TOKEN: "tok-tu-systemd"}):
            with mock.patch.dict("sys.modules", {"fanfic_credential_broker": None}):
                self.assertEqual(harvester_token(), "tok-tu-systemd")

    def test_a_broker_that_cannot_run_here_is_not_fatal(self):
        """Broker nem tren Linux — do KHONG phai loi, chi la duong khong ap
        dung. Loi that la 'khong co token o dau ca'."""
        from server.farmer import adapters

        broker_gia = mock.Mock()
        broker_gia.fetch.side_effect = RuntimeError(
            "this broker requires Windows Credential Manager")
        with mock.patch.dict("os.environ", {adapters.ENV_HARVESTER_TOKEN: ""}), \
             mock.patch.dict("sys.modules",
                             {"fanfic_credential_broker": broker_gia}):
            with self.assertRaises(RuntimeError) as ctx:
                adapters.harvester_token()
        # Thong diep phai noi ro PHAI LAM GI, ca tren Linux lan Windows.
        self.assertIn("farmer.env", str(ctx.exception))
        self.assertIn("store --name", str(ctx.exception))

    def test_the_broker_still_works_on_windows(self):
        from server.farmer import adapters

        broker_gia = mock.Mock()
        broker_gia.fetch.return_value = "tok-tu-broker"
        with mock.patch.dict("os.environ", {adapters.ENV_HARVESTER_TOKEN: ""}), \
             mock.patch.dict("sys.modules",
                             {"fanfic_credential_broker": broker_gia}):
            self.assertEqual(adapters.harvester_token(), "tok-tu-broker")


class SingleInstanceTest(unittest.TestCase):
    """DUNG MOT farmer. Hai ban cung luc se gianh cung mot muc trong hang doi
    va tra tien TTS hai lan cho mot tac pham — dieu `content_queue` khong tu
    chan duoc (Appwrite khong co cap nhat co dieu kien)."""

    def test_a_second_instance_is_refused(self):
        """Hai farmer la hai TIEN TRINH khac nhau — nen mo phong mot PID khac
        dang giu khoa, chu khong phai cung tien trinh nay xin hai lan."""
        from server.farmer.quotas import AlreadyRunning, SingleInstanceLock
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as d:
            khoa = SingleInstanceLock(work_dir=d)
            with open(khoa.path, "w", encoding="utf-8") as fh:
                fh.write(str(os.getpid() + 1))       # mot tien trinh KHAC
            with mock.patch.object(SingleInstanceLock, "_con_song",
                                   return_value=True):
                with self.assertRaises(AlreadyRunning):
                    khoa.acquire()

    def test_reacquiring_in_the_same_process_is_idempotent(self):
        """Mot tien trinh xin lai khoa CUA CHINH NO khong duoc tu khoa minh."""
        from server.farmer.quotas import SingleInstanceLock
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as d:
            a = SingleInstanceLock(work_dir=d)
            a.acquire()
            try:
                SingleInstanceLock(work_dir=d).acquire()     # khong duoc nem
            finally:
                a.release()

    def test_a_dead_holders_lock_is_reclaimed(self):
        from server.farmer.quotas import SingleInstanceLock
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as d:
            khoa = SingleInstanceLock(work_dir=d)
            with open(khoa.path, "w", encoding="utf-8") as fh:
                fh.write("999999")          # PID khong con song
            with mock.patch.object(SingleInstanceLock, "_con_song",
                                   return_value=False):
                khoa.acquire()              # thu hoi duoc
            khoa.release()

    def test_an_unreadable_lock_fails_closed(self):
        """Khong doc duoc PID -> coi nhu CON SONG. Thu hoi nham mot khoa dang
        duoc giu la cach tao ra dung hai farmer."""
        from server.farmer.quotas import AlreadyRunning, SingleInstanceLock
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as d:
            khoa = SingleInstanceLock(work_dir=d)
            with open(khoa.path, "w", encoding="utf-8") as fh:
                fh.write("khong-phai-so")
            with self.assertRaises(AlreadyRunning):
                khoa.acquire()

    def test_the_lock_releases_on_exit(self):
        from server.farmer.quotas import SingleInstanceLock
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as d:
            with SingleInstanceLock(work_dir=d) as khoa:
                self.assertTrue(os.path.exists(khoa.path))
            self.assertFalse(os.path.exists(khoa.path))


class QuotaShapeTest(unittest.TestCase):
    def test_downloads_are_bounded_by_concurrency_not_total(self):
        """Tai ve la chan tren DONG THOI: chay 100 lan, moi lan mot, la
        binh thuong."""
        q = FarmerQuotas(max_concurrent_downloads=1, min_free_disk_bytes=1)
        for _ in range(5):
            with q.slot(FarmerQuotas.DOWNLOAD):
                pass  # tra khe moi lan -> khong bao gio cham tran

    def test_a_second_concurrent_download_is_refused(self):
        q = FarmerQuotas(max_concurrent_downloads=1, min_free_disk_bytes=1)
        with q.slot(FarmerQuotas.DOWNLOAD):
            with self.assertRaises(QuotaExceeded):
                with q.slot(FarmerQuotas.DOWNLOAD):
                    pass

    def test_reviews_are_bounded_by_count_per_round(self):
        """Danh gia TON TIEN moi lan goi. Gioi han dong thoi khong bao ve
        duoc gi: mot farmer don luong se lan luot goi ma khong bao gio cham
        tran 'hai cai cung luc'."""
        q = FarmerQuotas(max_review_requests=2)
        for _ in range(2):
            with q.slot(FarmerQuotas.REVIEW):
                pass
        with self.assertRaises(QuotaExceeded):
            with q.slot(FarmerQuotas.REVIEW):
                pass

    def test_tts_is_bounded_by_count_per_round(self):
        q = FarmerQuotas(max_tts_jobs=1)
        with q.slot(FarmerQuotas.TTS):
            pass
        with self.assertRaises(QuotaExceeded):
            with q.slot(FarmerQuotas.TTS):
                pass

    def test_reset_usage_opens_the_next_round(self):
        q = FarmerQuotas(max_review_requests=1)
        with q.slot(FarmerQuotas.REVIEW):
            pass
        q.reset_usage()
        with q.slot(FarmerQuotas.REVIEW):
            pass  # vong moi -> ngan sach moi

    def test_a_typo_in_env_does_not_open_the_gate(self):
        from server.farmer import quotas as qm
        for bad in ("khong-phai-so", "0", "-5", "  "):
            with self.subTest(value=bad):
                with mock.patch.dict("os.environ", {qm.ENV_MAX_TTS: bad}):
                    self.assertEqual(FarmerQuotas().max_tts_jobs,
                                     qm.DEFAULT_MAX_TTS_JOBS)


# -------------------------------------------------------------- review ----
class _Provider:
    def __init__(self, text="", exc=None):
        self._text, self._exc = text, exc

    def complete(self, *, system, user, model, max_output_tokens):
        if self._exc:
            raise self._exc
        return LLMCompletion(text=self._text, provider_name="gemini", model=model)


class ReviewGateTest(unittest.TestCase):
    def test_approval_needs_both_verdict_and_score(self):
        """Model doi khi noi 'approve' kem diem thap. Nguong la tieng noi
        cuoi cung, va no la cua ta chu khong phai cua model."""
        p = _Provider('{"score": 40, "verdict": "approve", "reasons": [], "language": "vi"}')
        v = QualityReviewer(p, min_score=70).review(title="t", body="x" * 50, lane="text")
        self.assertFalse(v.approved)
        self.assertTrue(any("nguong" in r for r in v.reasons))

    def test_a_good_work_is_approved(self):
        p = _Provider('{"score": 88, "verdict": "approve", "reasons": ["mach lac"], "language": "vi"}')
        v = QualityReviewer(p, min_score=70).review(title="t", body="x" * 50, lane="text")
        self.assertTrue(v.approved)
        self.assertEqual(v.score, 88)

    def test_rejection_is_a_normal_result_not_an_error(self):
        p = _Provider('{"score": 10, "verdict": "reject", "reasons": ["rac"], "language": "vi"}')
        v = QualityReviewer(p).review(title="t", body="x" * 50, lane="text")
        self.assertFalse(v.approved)

    def test_provider_failure_fails_closed(self):
        """Khong danh gia duoc KHAC 'da danh gia va bi tu choi'. Ben goi phai
        khong san xuat, chu khong duoc coi la duyet."""
        p = _Provider(exc=LLMProviderError("het han muc"))
        with self.assertRaises(ReviewUnavailable):
            QualityReviewer(p).review(title="t", body="x" * 50, lane="text")

    def test_unparseable_response_fails_closed(self):
        for rac in ("khong phai json", "", "{", '{"score": "cao"}',
                    '{"score": 300, "verdict": "approve"}',
                    '{"score": 90, "verdict": "co le"}'):
            with self.subTest(raw=rac[:20]):
                with self.assertRaises(ReviewUnavailable):
                    QualityReviewer(_Provider(rac)).review(
                        title="t", body="x" * 50, lane="text")

    def test_empty_body_is_rejected_without_calling_the_api(self):
        """Khong can tra tien de biet mot tac pham rong thi khong dat."""
        p = mock.Mock()
        v = QualityReviewer(p).review(title="t", body="   ", lane="text")
        self.assertFalse(v.approved)
        p.complete.assert_not_called()

    def test_fenced_json_is_accepted(self):
        """Model hay boc JSON trong ```json du da duoc dan dung — that bai vi
        mot cai rao ma la lang phi mot lan goi co tra phi."""
        data = _parse_verdict('```json\n{"score": 80, "verdict": "approve"}\n```')
        self.assertEqual(data["score"], 80)


# -------------------------------------------------------------- covers ----
class _AssetStore:
    def __init__(self, assets=None):
        self.assets = list(assets or [])
        self._n = 0

    def list_assets(self, owner_id):
        return [a for a in self.assets if a.owner_id == owner_id]

    def create_asset(self, asset):
        self._n += 1
        asset.asset_id = f"ast_{self._n}"
        self.assets.append(asset)
        return asset


def _cover_asset(novel_id):
    a = MediaAsset(owner_id=novel_id, media_type=MediaType.IMAGE,
                   storage_tier=StorageTier.HOT,
                   object_key=f"covers/{novel_id}/x.svg",
                   content_hash="h", processing_state=MediaProcessingState.READY)
    a.asset_id = "ast_co_san"
    return a


def _other_image(novel_id):
    a = MediaAsset(owner_id=novel_id, media_type=MediaType.IMAGE,
                   storage_tier=StorageTier.HOT,
                   object_key=f"illustrations/{novel_id}/y.png",
                   content_hash="h", processing_state=MediaProcessingState.READY)
    a.asset_id = "ast_minh_hoa"
    return a


class CoverGateTest(unittest.TestCase):
    def test_publishing_without_a_cover_is_blocked(self):
        gate = CoverGate(mock.Mock(), _AssetStore())
        with self.assertRaises(CoverRequired):
            gate.assert_publishable("nov_1")

    def test_publishing_with_a_cover_is_allowed(self):
        gate = CoverGate(mock.Mock(), _AssetStore([_cover_asset("nov_1")]))
        self.assertEqual(gate.assert_publishable("nov_1"), "ast_co_san")

    def test_a_non_cover_image_does_not_satisfy_the_gate(self):
        """Mot minh hoa trong chuong khong phai anh bia — neu tinh la co, ta
        se xuat ban mot o trong."""
        gate = CoverGate(mock.Mock(), _AssetStore([_other_image("nov_1")]))
        with self.assertRaises(CoverRequired):
            gate.assert_publishable("nov_1")

    def test_ensure_cover_reuses_an_existing_one(self):
        pipeline = mock.Mock()
        gate = CoverGate(pipeline, _AssetStore([_cover_asset("nov_1")]))
        out = gate.ensure_cover(novel_id="nov_1", title="T")
        self.assertTrue(out.reused)
        pipeline.run_job.assert_not_called()

    def test_provider_falls_back_to_a_deterministic_background(self):
        """Khong cau hinh endpoint sinh anh -> nen SVG tat dinh, KHONG phai
        khong co bia. Mot farmer dung han vi endpoint anh chet se khong san
        xuat duoc gi; mot bia don gian van dua tac pham len trang."""
        from server.cover_pipeline import PlaceholderCoverProvider
        from server.farmer.covers import ENV_COVER_URL, build_cover_provider

        with mock.patch.dict("os.environ", {ENV_COVER_URL: ""}):
            self.assertIsInstance(build_cover_provider(), PlaceholderCoverProvider)

    def test_configured_endpoint_is_used_when_present(self):
        from server.cover_pipeline import HttpImageCoverProvider
        from server.farmer.covers import ENV_COVER_URL, build_cover_provider

        with mock.patch.dict("os.environ",
                             {ENV_COVER_URL: "https://covers.example/gen"}):
            self.assertIsInstance(build_cover_provider(), HttpImageCoverProvider)

    def test_a_failed_generation_raises_rather_than_reporting_success(self):
        from server.cover_pipeline import CoverJobStatus

        pipeline = mock.Mock()
        job = mock.Mock(status=CoverJobStatus.FAILED, media_asset_id=None,
                        error_message="provider chet")
        pipeline.run_job.return_value = job
        gate = CoverGate(pipeline, _AssetStore())
        with self.assertRaises(CoverRequired):
            gate.ensure_cover(novel_id="nov_1", title="T")


if __name__ == "__main__":
    unittest.main()
