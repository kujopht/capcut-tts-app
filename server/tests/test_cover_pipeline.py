import unittest

from server.adapters import MockMediaAssetStore
from server.cover_pipeline import (
    CoverGenerationRequest,
    CoverJob,
    CoverJobStatus,
    CoverPipelineService,
    CoverProvider,
    NotConfiguredCoverProvider,
)
from server.domain import MediaProcessingState, MediaType, StorageTier


class FakeSuccessCoverProvider:
    provider_name: str = "fake_success_provider"

    def generate(self, request: CoverGenerationRequest) -> bytes:
        return b"\x89PNG\r\n\x1a\nfake_image_bytes"


class FakeFailingCoverProvider:
    provider_name: str = "fake_failing_provider"

    def generate(self, request: CoverGenerationRequest) -> bytes:
        raise RuntimeError("GPU worker crashed during cover generation")


class TestCoverPipeline(unittest.TestCase):
    def setUp(self):
        self.store = MockMediaAssetStore()

    def test_cover_generation_request_defaults_and_fields(self):
        req = CoverGenerationRequest(
            novel_id="nov_123",
            fandom="Naruto",
            title="Naruto's New Journey",
            summary="A thrilling adventure.",
        )
        self.assertEqual(req.novel_id, "nov_123")
        self.assertEqual(req.fandom, "Naruto")
        self.assertEqual(req.title, "Naruto's New Journey")
        self.assertEqual(req.summary, "A thrilling adventure.")
        self.assertEqual(req.characters, [])
        self.assertEqual(req.genres, [])
        self.assertEqual(req.mood, "")
        self.assertEqual(req.visual_style, "")

        custom_req = CoverGenerationRequest(
            novel_id="nov_456",
            fandom="One Piece",
            title="Grand Line Chronicles",
            summary="Pirate adventures.",
            characters=["Luffy", "Zoro"],
            genres=["Adventure", "Fantasy"],
            mood="Epic",
            visual_style="Anime 90s",
        )
        self.assertEqual(custom_req.characters, ["Luffy", "Zoro"])
        self.assertEqual(custom_req.genres, ["Adventure", "Fantasy"])
        self.assertEqual(custom_req.mood, "Epic")
        self.assertEqual(custom_req.visual_style, "Anime 90s")

    def test_cover_job_defaults_and_fields(self):
        req = CoverGenerationRequest(
            novel_id="nov_123",
            fandom="Naruto",
            title="Test Title",
            summary="Test Summary",
        )
        job = CoverJob(novel_id="nov_123", request=req)

        self.assertTrue(job.job_id.startswith("cvj_"))
        self.assertEqual(job.novel_id, "nov_123")
        self.assertEqual(job.request, req)
        self.assertEqual(job.status, CoverJobStatus.PENDING)
        self.assertEqual(job.provider_name, "")
        self.assertIsNone(job.media_asset_id)
        self.assertEqual(job.error_message, "")
        self.assertTrue(len(job.created_at) > 0)
        self.assertTrue(len(job.updated_at) > 0)

    def test_not_configured_cover_provider_raises_not_implemented(self):
        provider = NotConfiguredCoverProvider()
        self.assertEqual(provider.provider_name, "not_configured")

        req = CoverGenerationRequest(
            novel_id="nov_123",
            fandom="Bleach",
            title="Soul Society Tale",
            summary="Summary text",
        )
        with self.assertRaises(NotImplementedError) as ctx:
            provider.generate(req)
        self.assertIn("Cover generation model has not been chosen", str(ctx.exception))

    def test_render_deterministic_overlay_behavior(self):
        service = CoverPipelineService(
            media_asset_store=self.store,
            provider=NotConfiguredCoverProvider(),
        )
        base_bytes = b"sample_raw_image_data"

        # Empty title returns base image unchanged
        result_bytes = service.render_deterministic_overlay(base_bytes, "")
        self.assertEqual(result_bytes, base_bytes)

        # Non-empty title raises NotImplementedError
        with self.assertRaises(NotImplementedError) as ctx:
            service.render_deterministic_overlay(base_bytes, "Some Title")
        self.assertIn("Text overlay rendering requires", str(ctx.exception))

    def test_run_job_success_produces_done_job_and_media_asset(self):
        provider = FakeSuccessCoverProvider()
        service = CoverPipelineService(
            media_asset_store=self.store,
            provider=provider,
        )

        req = CoverGenerationRequest(
            novel_id="nov_999",
            fandom="Jujutsu Kaisen",
            title="",  # Empty title skips overlay NotImplementedError
            summary="Curses and sorcery.",
        )
        job = CoverJob(novel_id="nov_999", request=req)

        finished_job = service.run_job(job)

        self.assertEqual(finished_job.status, CoverJobStatus.DONE)
        self.assertEqual(finished_job.provider_name, "fake_success_provider")
        self.assertEqual(finished_job.error_message, "")
        self.assertIsNotNone(finished_job.media_asset_id)

        # Verify MediaAsset was stored in store
        asset = self.store.get_asset(finished_job.media_asset_id)
        self.assertEqual(asset.owner_id, "nov_999")
        self.assertEqual(asset.media_type, MediaType.IMAGE)
        self.assertEqual(asset.storage_tier, StorageTier.HOT)
        self.assertEqual(asset.processing_state, MediaProcessingState.READY)
        self.assertEqual(asset.size_bytes, len(b"\x89PNG\r\n\x1a\nfake_image_bytes"))
        self.assertTrue(asset.object_key.startswith("covers/nov_999/cvj_"))

    def test_run_job_with_failing_provider_produces_failed_job_without_raising(self):
        provider = FakeFailingCoverProvider()
        service = CoverPipelineService(
            media_asset_store=self.store,
            provider=provider,
        )

        req = CoverGenerationRequest(
            novel_id="nov_fail",
            fandom="Demon Slayer",
            title="",
            summary="Demon fighting.",
        )
        job = CoverJob(novel_id="nov_fail", request=req)

        # Should not raise exception
        finished_job = service.run_job(job)

        self.assertEqual(finished_job.status, CoverJobStatus.FAILED)
        self.assertEqual(finished_job.provider_name, "fake_failing_provider")
        self.assertIn("GPU worker crashed during cover generation", finished_job.error_message)
        self.assertIsNone(finished_job.media_asset_id)

    def test_run_job_with_not_configured_provider_produces_failed_job_without_raising(self):
        provider = NotConfiguredCoverProvider()
        service = CoverPipelineService(
            media_asset_store=self.store,
            provider=provider,
        )

        req = CoverGenerationRequest(
            novel_id="nov_not_config",
            fandom="Re:Zero",
            title="",
            summary="Starting life in another world.",
        )
        job = CoverJob(novel_id="nov_not_config", request=req)

        finished_job = service.run_job(job)

        self.assertEqual(finished_job.status, CoverJobStatus.FAILED)
        self.assertEqual(finished_job.provider_name, "not_configured")
        self.assertIn("Cover generation model has not been chosen", finished_job.error_message)
        self.assertIsNone(finished_job.media_asset_id)

    def test_run_job_with_non_empty_title_fails_gracefully_on_deferred_overlay(self):
        provider = FakeSuccessCoverProvider()
        service = CoverPipelineService(
            media_asset_store=self.store,
            provider=provider,
        )

        req = CoverGenerationRequest(
            novel_id="nov_overlay",
            fandom="Fate/stay night",
            title="Unlimited Blade Works",
            summary="Holy Grail War.",
        )
        job = CoverJob(novel_id="nov_overlay", request=req)

        finished_job = service.run_job(job)

        self.assertEqual(finished_job.status, CoverJobStatus.FAILED)
        self.assertIn("Text overlay rendering requires", finished_job.error_message)
        self.assertIsNone(finished_job.media_asset_id)


class TestPlaceholderCoverProvider(unittest.TestCase):
    """Anh bia tam thoi (SVG, khong Pillow) — mission: 'do not leave first
    real works without a visual asset' truoc khi chon model that."""

    def setUp(self):
        self.store = MockMediaAssetStore()

    def test_generate_tra_ve_svg_hop_le(self):
        from server.cover_pipeline import PlaceholderCoverProvider
        provider = PlaceholderCoverProvider()
        req = CoverGenerationRequest(
            novel_id="nov_1", fandom="Naruto", title="T", summary="S")
        svg_bytes = provider.generate(req)
        self.assertTrue(svg_bytes.startswith(b"<svg"))
        self.assertIn(b"</svg>", svg_bytes)

    def test_tat_dinh_cung_fandom_mood_ra_cung_mau(self):
        from server.cover_pipeline import PlaceholderCoverProvider
        provider = PlaceholderCoverProvider()
        req1 = CoverGenerationRequest(
            novel_id="nov_1", fandom="Naruto", title="T", summary="S", mood="dark")
        req2 = CoverGenerationRequest(
            novel_id="nov_2", fandom="Naruto", title="Khac", summary="Khac", mood="dark")
        self.assertEqual(provider.generate(req1), provider.generate(req2))

    def test_run_job_voi_placeholder_thanh_cong_va_de_duoc_svg(self):
        from server.cover_pipeline import PlaceholderCoverProvider
        service = CoverPipelineService(
            media_asset_store=self.store, provider=PlaceholderCoverProvider())
        req = CoverGenerationRequest(
            novel_id="nov_ph", fandom="Naruto", title="Truyện thử nghiệm",
            summary="S")
        job = service.run_job(CoverJob(novel_id="nov_ph", request=req))

        self.assertEqual(job.status, CoverJobStatus.DONE)
        self.assertIsNotNone(job.media_asset_id)
        asset = self.store.get_asset(job.media_asset_id)
        self.assertTrue(asset.object_key.endswith(".svg"))
        self.assertEqual(asset.media_type, MediaType.IMAGE)


class TestSvgTextOverlay(unittest.TestCase):
    def test_chen_tieu_de_vao_svg_va_escape_ky_tu_dac_biet(self):
        service = CoverPipelineService(
            media_asset_store=MockMediaAssetStore(), provider=NotConfiguredCoverProvider())
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
        ket_qua = service.render_deterministic_overlay(svg, "A & B <C>")
        text = ket_qua.decode("utf-8")
        self.assertIn("A &amp; B &lt;C&gt;", text)
        self.assertTrue(text.rstrip().endswith("</svg>"))

    def test_svg_tieu_de_rong_tra_ve_nguyen_ban(self):
        service = CoverPipelineService(
            media_asset_store=MockMediaAssetStore(), provider=NotConfiguredCoverProvider())
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
        self.assertEqual(service.render_deterministic_overlay(svg, ""), svg)
