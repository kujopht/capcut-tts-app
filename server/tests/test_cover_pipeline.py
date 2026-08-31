import base64
import unittest

import httpx

from server.adapters import MockMediaAssetStore
from server.cover_pipeline import (
    CoverGenerationRequest,
    CoverJob,
    CoverJobStatus,
    CoverPipelineService,
    CoverProvider,
    CoverProviderError,
    CoverPromptBuilder,
    HttpImageCoverProvider,
    NotConfiguredCoverProvider,
    wrap_raster_as_overlayable_svg,
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

    def test_run_job_with_non_empty_title_and_raster_provider_succeeds_via_svg_wrap(self):
        """Trước bản vá này, run_job() gọi thẳng render_deterministic_overlay()
        trên PNG thô + tiêu đề — nổ NotImplementedError (quyết định thư viện
        ảnh raster chưa có), ngay cả sau khi HttpImageCoverProvider/
        wrap_raster_as_overlayable_svg đã tồn tại — vì run_job() chưa gọi
        wrapper đó. Đây là con đường THẬT SỰ mọi bìa thật sẽ đi qua (bìa nào
        cũng có tiêu đề), nên hành vi cũ là một lỗ hổng tích hợp thật, không
        phải một giới hạn đã biết trước — phát hiện qua kiểm tra độc lập.
        Giờ run_job() tự cuộn PNG vào SVG (không cần Pillow) trước khi overlay,
        nên job PHẢI thành công, không còn FAILED nữa."""
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

        self.assertEqual(finished_job.status, CoverJobStatus.DONE, finished_job.error_message)
        self.assertIsNotNone(finished_job.media_asset_id)
        asset = self.store.get_asset(finished_job.media_asset_id)
        self.assertTrue(asset.object_key.endswith(".svg"))


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


# ---------------------------------------------------------------------------
#  Tiny real PNG fixture (1x1 red pixel) cho cac test HttpImageCoverProvider
# ---------------------------------------------------------------------------
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
)
_TINY_PNG_BYTES = base64.b64decode(_TINY_PNG_B64)


def _make_a1111_handler():
    """Tra ve response a1111-compatible voi anh base64 that su."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"images": [_TINY_PNG_B64], "parameters": {}},
        )

    return handler


def _make_simple_json_handler():
    """Tra ve response simple-style voi JSON image_base64."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"image_base64": _TINY_PNG_B64},
        )

    return handler


def _make_simple_raw_handler():
    """Tra ve response simple-style voi raw PNG bytes."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "image/png"},
            content=_TINY_PNG_BYTES,
        )

    return handler


def _make_error_handler(status_code: int = 500):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="Internal Server Error")

    return handler


def _req(**overrides) -> CoverGenerationRequest:
    defaults = dict(
        novel_id="nov_test", fandom="Naruto", title="Hidden Leaf Secrets",
        summary="A story.", characters=["Naruto", "Sakura"],
        genres=["Action", "Adventure"], mood="Hopeful",
        visual_style="modern anime style",
    )
    defaults.update(overrides)
    return CoverGenerationRequest(**defaults)


class TestCoverPromptBuilder(unittest.TestCase):
    def test_deterministic_same_input_same_output(self):
        req = _req()
        p1 = CoverPromptBuilder.build_prompt(req)
        p2 = CoverPromptBuilder.build_prompt(req)
        self.assertEqual(p1, p2)

    def test_different_fandom_different_prompt(self):
        p1 = CoverPromptBuilder.build_prompt(_req(fandom="Naruto"))
        p2 = CoverPromptBuilder.build_prompt(_req(fandom="One Piece"))
        self.assertNotEqual(p1, p2)

    def test_different_characters_different_prompt(self):
        p1 = CoverPromptBuilder.build_prompt(_req(characters=["Naruto"]))
        p2 = CoverPromptBuilder.build_prompt(_req(characters=["Luffy", "Zoro"]))
        self.assertNotEqual(p1, p2)

    def test_different_mood_different_prompt(self):
        p1 = CoverPromptBuilder.build_prompt(_req(mood="dark"))
        p2 = CoverPromptBuilder.build_prompt(_req(mood="cheerful"))
        self.assertNotEqual(p1, p2)

    def test_title_never_appears_verbatim_in_prompt(self):
        """Model chi ve art — ten tieu de khong duoc xuat hien trong prompt."""
        title = "Truyen Thu Ngan ve Hat Giong"
        prompt = CoverPromptBuilder.build_prompt(_req(title=title))
        self.assertNotIn(title, prompt)
        # Cung khong xuat hien khong dau/cu trong prompt
        self.assertNotIn("hat giong", prompt.lower())

    def test_empty_optional_fields_still_produces_valid_prompt(self):
        req = CoverGenerationRequest(
            novel_id="n", fandom="", title="", summary="",
        )
        prompt = CoverPromptBuilder.build_prompt(req)
        self.assertIn("anime light novel cover illustration", prompt)
        self.assertIn("high quality", prompt)


class TestWrapRasterAsOverlayableSvg(unittest.TestCase):
    def test_produces_valid_svg_with_embedded_png(self):
        svg_bytes = wrap_raster_as_overlayable_svg(_TINY_PNG_BYTES)
        text = svg_bytes.decode("utf-8")
        self.assertIn("<svg", text)
        self.assertIn("</svg>", text)
        self.assertIn("data:image/png;base64,", text)
        self.assertIn('<image width="100%" height="100%"', text)

    def test_embedded_png_roundtrips_correctly(self):
        svg_text = wrap_raster_as_overlayable_svg(_TINY_PNG_BYTES).decode("utf-8")
        # Trich xuat base64 tu data URI
        start = svg_text.index("base64,") + len("base64,")
        end = svg_text.index('"', start)
        extracted_b64 = svg_text[start:end]
        self.assertEqual(base64.b64decode(extracted_b64), _TINY_PNG_BYTES)

    def test_roundtrip_through_existing_overlay(self):
        """SVG cuon anh co the di qua render_deterministic_overlay ma khong modify."""
        svg_wrapped = wrap_raster_as_overlayable_svg(_TINY_PNG_BYTES)
        service = CoverPipelineService(
            media_asset_store=MockMediaAssetStore(),
            provider=NotConfiguredCoverProvider(),
        )
        result = service.render_deterministic_overlay(svg_wrapped, "Test Title")
        result_text = result.decode("utf-8")
        # Co ca the <image> (anhr goc) LAN ca the <text> (tieu de overlay)
        self.assertIn("<image", result_text)
        self.assertIn("<text", result_text)
        self.assertIn("Test Title", result_text)
        self.assertTrue(result_text.rstrip().endswith("</svg>"))


_MOCK_BASE_URL = "http://fake-gpu.local"


def _mock_client(handler, *, base_url: str = _MOCK_BASE_URL) -> httpx.Client:
    return httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))


class TestHttpImageCoverProviderA1111(unittest.TestCase):
    def test_generate_tra_ve_png_bytes(self):
        client = _mock_client(_make_a1111_handler())
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, client=client)
        result = provider.generate(_req())
        self.assertEqual(result, _TINY_PNG_BYTES)

    def test_generate_with_auth_header(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization", "")
            return httpx.Response(200, json={"images": [_TINY_PNG_B64]})

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_key="sk-test-123",
            client=client)
        provider.generate(_req())
        self.assertEqual(captured["auth"], "Bearer sk-test-123")

    def test_error_500_raises_cover_provider_error(self):
        client = _mock_client(_make_error_handler(500))
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, client=client)
        with self.assertRaises(CoverProviderError) as ctx:
            provider.generate(_req())
        self.assertIn("500", str(ctx.exception))

    def test_malformed_json_response_raises_cover_provider_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, client=client)
        with self.assertRaises(CoverProviderError) as ctx:
            provider.generate(_req())
        self.assertIn("khong dung dinh dang", str(ctx.exception))

    def test_run_job_with_a1111_provider_succeeds_end_to_end(self):
        """PNG that tu a1111 + tieu de that -> run_job() tu cuon SVG (khong
        can Pillow) roi overlay thanh cong, khong con FAILED nua."""
        client = _mock_client(_make_a1111_handler())
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, client=client)
        service = CoverPipelineService(
            media_asset_store=MockMediaAssetStore(), provider=provider)
        job = service.run_job(CoverJob(novel_id="n", request=_req()))
        self.assertEqual(job.status, CoverJobStatus.DONE, job.error_message)
        self.assertIsNotNone(job.media_asset_id)


class TestHttpImageCoverProviderSimple(unittest.TestCase):
    def test_json_response(self):
        client = _mock_client(_make_simple_json_handler())
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_style="simple", client=client)
        result = provider.generate(_req())
        self.assertEqual(result, _TINY_PNG_BYTES)

    def test_raw_bytes_response(self):
        client = _mock_client(_make_simple_raw_handler())
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_style="simple", client=client)
        result = provider.generate(_req())
        self.assertEqual(result, _TINY_PNG_BYTES)

    def test_error_500_raises_cover_provider_error(self):
        client = _mock_client(_make_error_handler(500))
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_style="simple", client=client)
        with self.assertRaises(CoverProviderError) as ctx:
            provider.generate(_req())
        self.assertIn("500", str(ctx.exception))


class TestHttpImageCoverProviderTimeout(unittest.TestCase):
    def test_timeout_raises_cover_provider_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, client=client)
        with self.assertRaises(CoverProviderError) as ctx:
            provider.generate(_req())
        self.assertIn("Loi goi dich vu sinh anh", str(ctx.exception))


class TestRunJobWithHttpProvider(unittest.TestCase):
    def test_success_path_empty_title_stores_png(self):
        """Provider tra PNG + title trong -> overlay giu nguyen, luu thanh cong."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"images": [_TINY_PNG_B64]})

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, client=client)
        service = CoverPipelineService(
            media_asset_store=MockMediaAssetStore(), provider=provider)

        req = CoverGenerationRequest(
            novel_id="nov_http", fandom="Naruto", title="",
            summary="Test.", characters=[], genres=[], mood="",
        )
        job = service.run_job(CoverJob(novel_id="nov_http", request=req))
        self.assertEqual(job.status, CoverJobStatus.DONE)
        self.assertIsNotNone(job.media_asset_id)
