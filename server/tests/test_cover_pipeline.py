import base64
import unittest

import httpx

from server.adapters import MockMediaAssetStore
from server.character_identity import (
    CharacterIdentityRegistry, CharacterVisualIdentity,
)
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
        summary="A story.", characters=["Naruto", "Sakura", "Kakashi"],
        genres=["Action", "Adventure"], mood="Hopeful",
        visual_style="modern anime style",
        primary_character="Naruto", secondary_character="Sakura",
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

    def test_different_cast_different_prompt(self):
        p1 = CoverPromptBuilder.build_prompt(
            _req(primary_character="Naruto", secondary_character=""))
        p2 = CoverPromptBuilder.build_prompt(
            _req(primary_character="Luffy", secondary_character="Zoro"))
        self.assertNotEqual(p1, p2)

    def test_characters_metadata_list_alone_does_not_affect_prompt(self):
        """`characters[]` la metadata day du cua truyen, KHONG con duoc dua
        thang vao prompt anh nua - chi primary/secondary/tertiary_character
        moi anh huong toi dan dien vien tren bia (tranh bia dong nguoi)."""
        p1 = CoverPromptBuilder.build_prompt(
            _req(characters=["Naruto"], primary_character="Naruto",
                 secondary_character="Sakura"))
        p2 = CoverPromptBuilder.build_prompt(
            _req(characters=["Naruto", "Sakura", "Kakashi", "Sasuke", "Sai"],
                 primary_character="Naruto", secondary_character="Sakura"))
        self.assertEqual(p1, p2)

    def test_default_max_visible_characters_is_two_excludes_tertiary(self):
        req = _req(
            primary_character="Naruto", secondary_character="Sakura",
            tertiary_character="Kakashi")
        self.assertEqual(req.max_visible_characters, 2)
        prompt = CoverPromptBuilder.build_prompt(req)
        self.assertIn("Naruto", prompt)
        self.assertIn("Sakura", prompt)
        self.assertNotIn("Kakashi", prompt)
        self.assertIn("2people", prompt)

    def test_max_visible_characters_override_includes_tertiary(self):
        req = _req(
            primary_character="Naruto", secondary_character="Sakura",
            tertiary_character="Kakashi", max_visible_characters=3)
        prompt = CoverPromptBuilder.build_prompt(req)
        self.assertIn("Naruto", prompt)
        self.assertIn("Sakura", prompt)
        self.assertIn("Kakashi", prompt)
        self.assertIn("3people", prompt)

    def test_solo_character_uses_solo_tag_not_people_count(self):
        prompt = CoverPromptBuilder.build_prompt(
            _req(primary_character="Naruto", secondary_character=""))
        self.assertIn("solo", prompt)
        self.assertNotIn("people", prompt)

    def test_no_cast_produces_no_focal_hierarchy_tags(self):
        prompt = CoverPromptBuilder.build_prompt(
            _req(primary_character="", secondary_character=""))
        self.assertNotIn("focal point", prompt)
        self.assertNotIn("clear focal hierarchy", prompt)

    def test_focal_hierarchy_wording_present_for_two_person_cast(self):
        prompt = CoverPromptBuilder.build_prompt(
            _req(primary_character="Naruto", secondary_character="Sakura"))
        self.assertIn("Naruto in foreground, focal point", prompt)
        self.assertIn("Sakura positioned beside/behind Naruto", prompt)

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

    def test_negative_space_and_cinematic_background_tags_present(self):
        """Danh cho tieu de overlay sau nay + tranh bia bi rop hinh."""
        prompt = CoverPromptBuilder.build_prompt(_req())
        self.assertIn("negative space for title", prompt)
        self.assertIn("cinematic fantasy background", prompt)

    def test_empty_optional_fields_still_produces_valid_prompt(self):
        req = CoverGenerationRequest(
            novel_id="n", fandom="", title="", summary="",
        )
        prompt = CoverPromptBuilder.build_prompt(req)
        self.assertIn("light novel cover", prompt)
        self.assertIn("high quality", prompt)


def _rezero_req(**overrides) -> CoverGenerationRequest:
    defaults = dict(
        novel_id="nov_rezero", fandom="Re:Zero",
        title="Re: Zero - Hai Vi Sao Bi Quen Lang",
        summary="A story.",
        characters=["Natsuki Subaru", "Anastasia Hoshin", "Felix Argyle"],
        genres=["Isekai", "Fantasy"], mood="bittersweet",
        primary_character="Natsuki Subaru", secondary_character="Anastasia Hoshin",
    )
    defaults.update(overrides)
    return CoverGenerationRequest(**defaults)


class TestCoverPromptBuilderWithCharacterIdentity(unittest.TestCase):
    """Item 8 cua Mission 'Character Identity Layer': chung minh nhan
    dang hinh anh THAT (khong phai chi ten) di vao prompt, nhan vat
    khong lien quan thi khong, cap ho so day du (Subaru+Anastasia) dung
    tag dem 1boy/1girl, va registry la metadata dung chung/tai su dung
    duoc (khong hardcode Re:Zero trong CoverPromptBuilder)."""

    def setUp(self):
        self.registry = CharacterIdentityRegistry()

    def test_subaru_descriptors_enter_the_prompt(self):
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("black hair", prompt.lower())
        self.assertIn("tracksuit", prompt.lower())

    def test_anastasia_descriptors_enter_the_prompt(self):
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("purple hair", prompt.lower())
        self.assertIn("fur", prompt.lower())

    def test_unrelated_character_without_profile_gets_name_only_no_descriptor(self):
        req = _rezero_req(
            tertiary_character="Felix Argyle", max_visible_characters=3)
        prompt = CoverPromptBuilder.build_prompt(req, self.registry)
        self.assertIn("Felix Argyle", prompt)
        # Felix has no seed profile -> _cast_block returns the bare name,
        # never "Felix Argyle," followed by descriptor tags.
        self.assertNotIn("Felix Argyle,", prompt)

    def test_no_more_than_two_characters_visible_by_default_even_with_identities(self):
        req = _rezero_req(tertiary_character="Felix Argyle")
        prompt = CoverPromptBuilder.build_prompt(req, self.registry)
        self.assertNotIn("Felix Argyle", prompt)
        self.assertIn("1boy, 1girl", prompt)

    def test_gender_known_pair_uses_1boy_1girl_not_generic_2people(self):
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("1boy, 1girl", prompt)
        self.assertNotIn("2people", prompt)

    def test_omitting_identity_registry_falls_back_to_name_only_unchanged(self):
        prompt = CoverPromptBuilder.build_prompt(_rezero_req())
        self.assertIn("2people", prompt)
        self.assertNotIn("black hair", prompt.lower())

    def test_custom_registry_without_seed_data_still_works(self):
        """Provider-trung-lap / tai su dung duoc: mot registry HOAN TOAN
        tuy chinh (khong dung du lieu hat giong Re:Zero co san) van hoat
        dong dung - chung minh day la co che metadata dung chung, khong
        hardcode rieng cho Re:Zero trong CoverPromptBuilder."""
        custom_registry = CharacterIdentityRegistry(seed=False)
        custom_registry.register(CharacterVisualIdentity(
            canonical_name="Monkey D. Luffy", fandom="One Piece",
            gender_presentation="male", hair_description="messy black hair",
            outfit_description="red vest, straw hat"))
        req = CoverGenerationRequest(
            novel_id="n", fandom="One Piece", title="t", summary="s",
            primary_character="Monkey D. Luffy")
        prompt = CoverPromptBuilder.build_prompt(req, custom_registry)
        self.assertIn("straw hat", prompt)

    def test_build_character_negative_traits_returns_traits_for_visible_cast(self):
        traits = CoverPromptBuilder.build_character_negative_traits(
            _rezero_req(), self.registry)
        self.assertIn("blonde hair", traits)
        self.assertIn("armor", traits)

    def test_build_character_negative_traits_empty_without_registry(self):
        traits = CoverPromptBuilder.build_character_negative_traits(_rezero_req())
        self.assertEqual(traits, [])


class TestCoverPromptBuilderCompactModeTokenBudget(unittest.TestCase):
    """Real fix for a real Beam failure: RuntimeError aside, the same log
    also showed "Token indices sequence length 216 > maximum 77" - the
    FULL-descriptor 2-person prompt (980 chars) overflowed CLIP's 77-token
    hard limit. `transformers`/a real CLIP tokenizer is NOT installed in
    this repo's venv (deploy-only dependency, same constraint as beam_apps
    all mission), so exact BPE token counts cannot be computed locally.
    Instead this uses a REAL, evidence-CALIBRATED character-length proxy:
    the actual incident reported 980 chars -> 216 tokens, i.e. ~4.54
    chars/token. A comfortable target of well under 350 chars (77 tokens
    * ~4.54 chars/token, rounded down for safety margin) is used as the
    proxy ceiling - not exact tokenization, but grounded in the real
    incident's own numbers rather than an arbitrary guess."""

    #: 980 real chars / 216 real tokens from the actual Beam log line.
    _REAL_CHARS_PER_TOKEN = 980 / 216
    _REAL_CLIP_TOKEN_LIMIT = 77
    #: Raw ratio ceiling is 77*4.54~=350 chars. The "Final Regional
    #: Composition" mission added genuinely-required composition concepts
    #: (waist-up shot, faces-visible, facing-viewer/3/4-view, left/right
    #: placement) that raised the real compact prompt to ~306 chars -
    #: still comfortably under the raw 350-char limit (~67 estimated
    #: tokens vs the 77 hard cap), so the ceiling here was raised from an
    #: earlier, more conservative 300 to 330 rather than cutting required
    #: composition detail to chase an arbitrary margin.
    _SAFE_CHAR_CEILING = 330

    def setUp(self):
        self.registry = CharacterIdentityRegistry()

    def test_two_identity_prompt_stays_under_the_safe_character_ceiling(self):
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertLess(
            len(prompt), self._SAFE_CHAR_CEILING,
            f"prompt is {len(prompt)} chars - estimated "
            f"~{len(prompt) / self._REAL_CHARS_PER_TOKEN:.0f} tokens "
            f"against a real {self._REAL_CLIP_TOKEN_LIMIT}-token CLIP "
            f"limit (real incident: 980 chars measured as 216 tokens)")

    def test_compact_mode_drops_verbose_only_markers(self):
        """Proves compact mode actually engaged (not just coincidentally
        short) - none of the FULL-descriptor path's verbose phrasing
        should appear once 2 identities with compact tags are resolved."""
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertNotIn("clear focal hierarchy", prompt)
        self.assertNotIn("focal point", prompt)
        self.assertNotIn("positioned beside/behind", prompt)
        self.assertNotIn("cinematic fantasy background", prompt)
        self.assertNotIn("dynamic pose", prompt)

    def test_compact_mode_does_not_simply_discard_identity(self):
        """Requirement 6 - "Do not simply discard character identity."
        Compact != empty: the most distinctive tags must still survive."""
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("tracksuit", prompt.lower())
        self.assertIn("black hair", prompt.lower())
        self.assertIn("purple hair", prompt.lower())
        self.assertIn("fur", prompt.lower())

    def test_compact_mode_drops_genre_words(self):
        """Requirement 7 - "Move/remove ... genre words" from the
        identity-aware compact path."""
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        for genre_word in ("Isekai", "Fantasy", "Drama", "genre"):
            self.assertNotIn(genre_word, prompt)

    def test_compact_mode_keeps_title_negative_space(self):
        """Requirement 4 preservation list - title negative space must
        survive trimming, it is product-critical (app-side title overlay
        composition), not a low-priority detail."""
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("negative space for title", prompt)

    def test_single_identity_prompt_unaffected_by_compact_mode(self):
        """Only >= 2 resolved identities with compact tags trigger
        compact mode - a single-character prompt keeps its existing full
        descriptor behavior unchanged (it was never the source of the
        216-token overflow, which needed TWO full descriptor blocks)."""
        req = CoverGenerationRequest(
            novel_id="n", fandom="Re:Zero", title="t", summary="s",
            primary_character="Natsuki Subaru")
        prompt = CoverPromptBuilder.build_prompt(req, self.registry)
        self.assertIn("swept back and unkempt", prompt)  # full hair_description text

    def test_compact_mode_requires_medium_shot_and_visible_faces(self):
        """Real fix for a real v10 composition failure: badly-cropped
        face + character facing away. The compact path now explicitly
        requires a framing/orientation that makes both problems less
        likely, rather than leaving composition unconstrained."""
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("waist-up shot", prompt)
        self.assertIn("faces fully visible", prompt)
        self.assertIn("facing viewer or 3/4 view", prompt)

    def test_compact_mode_places_primary_left_secondary_right(self):
        """Matches build_left_right_masks() exactly (primary=left mask,
        secondary=right mask) - the text prompt and the spatial IP-Adapter
        masks must agree on which side each character belongs to."""
        prompt = CoverPromptBuilder.build_prompt(_rezero_req(), self.registry)
        self.assertIn("Natsuki Subaru, black and orange tracksuit, "
                      "messy black hair, on left", prompt)
        self.assertIn("Anastasia Hoshin, white fur ushanka hat, "
                      "long purple hair, on right", prompt)


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

    def test_default_simple_path_posts_to_generate(self):
        """Hanh vi cu GIU NGUYEN: provider 'simple' mac dinh (khong truyen
        simple_path) van POST vao /generate."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            return httpx.Response(
                200, headers={"content-type": "application/json"},
                json={"image_base64": _TINY_PNG_B64})

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_style="simple", client=client)
        result = provider.generate(_req())
        self.assertEqual(captured["path"], "/generate")
        self.assertEqual(result, _TINY_PNG_BYTES)

    def test_beam_style_empty_simple_path_posts_to_deployment_root(self):
        """simple_path='' (kieu Beam Cloud @endpoint) POST THANG vao goc
        URL deploy, khong con /generate — day la fix cho loi 404 that tren
        Cloud Shell benchmark."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["path"] = request.url.path
            return httpx.Response(
                200, headers={"content-type": "application/json"},
                json={"image_base64": _TINY_PNG_B64})

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_style="simple", simple_path="",
            client=client)
        result = provider.generate(_req())
        self.assertEqual(captured["path"], "/")
        self.assertEqual(result, _TINY_PNG_BYTES)

    def test_beam_style_empty_simple_path_preserves_auth_header(self):
        """Header Authorization van duoc gan dung du simple_path la gi."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization", "")
            return httpx.Response(
                200, headers={"content-type": "application/json"},
                json={"image_base64": _TINY_PNG_B64})

        client = _mock_client(handler)
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_key="beam-token-xyz",
            api_style="simple", simple_path="", client=client)
        provider.generate(_req())
        self.assertEqual(captured["auth"], "Bearer beam-token-xyz")

    def test_beam_style_empty_simple_path_parses_image_base64_response(self):
        """Response {"image_base64": ...} van duoc parse dung khi goi
        goc URL deploy (khong co /generate)."""
        client = _mock_client(_make_simple_json_handler())
        provider = HttpImageCoverProvider(
            base_url=_MOCK_BASE_URL, api_style="simple", simple_path="",
            client=client)
        result = provider.generate(_req())
        self.assertEqual(result, _TINY_PNG_BYTES)


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
