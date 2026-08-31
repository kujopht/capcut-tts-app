import ast
import inspect
import unittest

from server import image_router
from server.image_router import (
    BEAM_RTX4090_PROFILE,
    ImageGenerationCapability,
    ImageGenerationRequirements,
    ImageProviderProfile,
    ImageRouter,
    LatencyClass,
    NoCapableProviderError,
)


def _make_requirements(
    capability=ImageGenerationCapability.PROMPT_ONLY,
    vram_gb=8.0,
    prefer_free=True,
):
    return ImageGenerationRequirements(
        required_capability=capability,
        vram_requirement_gb=vram_gb,
        estimated_latency_class=LatencyClass.MEDIUM,
        prefer_free_or_subsidized_compute=prefer_free,
    )


def _make_profile(
    name,
    capabilities=(ImageGenerationCapability.PROMPT_ONLY,),
    vram_gb=24.0,
    is_free=False,
    is_available=True,
    cost_per_second=0.0002,
):
    return ImageProviderProfile(
        provider_name=name,
        supported_capabilities=list(capabilities),
        gpu_vram_gb=vram_gb,
        is_free_or_subsidized=is_free,
        is_available=is_available,
        cost_per_second_usd=cost_per_second,
    )


class TestImageRouterSelectsFreeComputeFirst(unittest.TestCase):
    def test_prefers_free_candidate_over_cheaper_paid_candidate(self):
        """Item 'prefer free/subsidized compute first' - candidate mien phi
        phai thang du candidate tra phi RE HON, vi mac dinh
        prefer_free_or_subsidized_compute=True khop nguyen tac san xuat cua
        mission."""
        free_candidate = _make_profile(
            "free_provider", is_free=True, cost_per_second=0.01)
        paid_candidate = _make_profile(
            "paid_provider", is_free=False, cost_per_second=0.0001)
        router = ImageRouter()

        chosen = router.select_provider(
            _make_requirements(), [paid_candidate, free_candidate])

        self.assertEqual(chosen.provider_name, "free_provider")

    def test_ignores_free_preference_when_flag_is_off(self):
        free_candidate = _make_profile(
            "free_provider", is_free=True, cost_per_second=0.01)
        paid_candidate = _make_profile(
            "paid_provider", is_free=False, cost_per_second=0.0001)
        router = ImageRouter()

        chosen = router.select_provider(
            _make_requirements(prefer_free=False),
            [paid_candidate, free_candidate],
        )

        self.assertEqual(chosen.provider_name, "paid_provider")


class TestImageRouterSelectsCheapestCapableProvider(unittest.TestCase):
    def test_prefers_cheapest_paid_provider_when_no_free_option(self):
        cheap_paid = _make_profile(
            "cheap_paid", is_free=False, cost_per_second=0.0001)
        expensive_paid = _make_profile(
            "expensive_paid", is_free=False, cost_per_second=0.01)
        router = ImageRouter()

        chosen = router.select_provider(
            _make_requirements(), [expensive_paid, cheap_paid])

        self.assertEqual(chosen.provider_name, "cheap_paid")

    def test_same_candidates_different_outcome_with_extra_profile_no_code_change(self):
        """Bang chung THAT cho tuyen bo 'khong can doi code ung dung' -
        cung mot loi goi select_provider(), CHI danh sach candidates thay
        doi (them mot ho so gia dinh 'vast' re hon) -> ket qua khac di,
        khong sua ImageRouter/select_provider nao ca."""
        router = ImageRouter()
        requirements = _make_requirements()
        beam_only = [_make_profile(
            "beam", is_free=False, cost_per_second=0.0002)]
        beam_and_vast = beam_only + [_make_profile(
            "vast", is_free=False, cost_per_second=0.00005)]

        chosen_before = router.select_provider(requirements, beam_only)
        chosen_after = router.select_provider(requirements, beam_and_vast)

        self.assertEqual(chosen_before.provider_name, "beam")
        self.assertEqual(chosen_after.provider_name, "vast")


class TestImageRouterFallback(unittest.TestCase):
    def test_marks_provider_unavailable_and_falls_back_to_second_provider(self):
        """Mo phong loi tam thoi that: caller chon provider A, goi that bai,
        danh dau A khong san sang, goi lai select_provider() va nhan
        provider B."""
        provider_a = _make_profile(
            "provider_a", is_free=False, cost_per_second=0.0001)
        provider_b = _make_profile(
            "provider_b", is_free=False, cost_per_second=0.0005)
        candidates = [provider_a, provider_b]
        router = ImageRouter()
        requirements = _make_requirements()

        first_choice = router.select_provider(requirements, candidates)
        self.assertEqual(first_choice.provider_name, "provider_a")

        router.mark_provider_unavailable(first_choice, candidates)
        second_choice = router.select_provider(requirements, candidates)

        self.assertEqual(second_choice.provider_name, "provider_b")
        self.assertFalse(provider_a.is_available)


class TestImageRouterRaisesWhenNoCapableProvider(unittest.TestCase):
    def test_raises_when_no_candidate_supports_capability(self):
        provider = _make_profile(
            "beam", capabilities=(ImageGenerationCapability.PROMPT_ONLY,))
        router = ImageRouter()
        requirements = _make_requirements(
            capability=ImageGenerationCapability.REFERENCE_CONDITIONED)

        with self.assertRaises(NoCapableProviderError):
            router.select_provider(requirements, [provider])

    def test_raises_when_no_candidate_has_enough_vram(self):
        provider = _make_profile("small_gpu", vram_gb=4.0)
        router = ImageRouter()
        requirements = _make_requirements(vram_gb=24.0)

        with self.assertRaises(NoCapableProviderError):
            router.select_provider(requirements, [provider])

    def test_raises_when_only_candidate_is_unavailable(self):
        provider = _make_profile("beam", is_available=False)
        router = ImageRouter()

        with self.assertRaises(NoCapableProviderError):
            router.select_provider(_make_requirements(), [provider])

    def test_character_lora_requirement_cleanly_raises_not_silently_downgraded(self):
        """Item mission: loc CHARACTER_LORA hom nay phai raise RO RANG,
        KHONG am tham ha cap ve mot capability khac ma provider co ho tro
        (vd PROMPT_ONLY) - dam bao caller khong vo tinh nhan mot anh sai
        chien luoc ma tuong la LoRA."""
        prompt_only_provider = _make_profile(
            "beam",
            capabilities=(
                ImageGenerationCapability.PROMPT_ONLY,
                ImageGenerationCapability.REFERENCE_CONDITIONED,
            ),
        )
        router = ImageRouter()
        requirements = _make_requirements(
            capability=ImageGenerationCapability.CHARACTER_LORA)

        with self.assertRaises(NoCapableProviderError):
            router.select_provider(requirements, [prompt_only_provider])


class TestBeamRtx4090ProfileIsValidCandidateToday(unittest.TestCase):
    def test_beam_profile_is_capable_for_prompt_only(self):
        router = ImageRouter()
        chosen = router.select_provider(
            _make_requirements(capability=ImageGenerationCapability.PROMPT_ONLY),
            [BEAM_RTX4090_PROFILE],
        )
        self.assertEqual(chosen.provider_name, "beam")

    def test_beam_profile_is_capable_for_reference_conditioned(self):
        router = ImageRouter()
        chosen = router.select_provider(
            _make_requirements(
                capability=ImageGenerationCapability.REFERENCE_CONDITIONED),
            [BEAM_RTX4090_PROFILE],
        )
        self.assertEqual(chosen.provider_name, "beam")

    def test_beam_profile_does_not_yet_support_character_lora(self):
        self.assertNotIn(
            ImageGenerationCapability.CHARACTER_LORA,
            BEAM_RTX4090_PROFILE.supported_capabilities,
        )

    def test_beam_profile_is_not_free_or_subsidized(self):
        """Beam RTX4090 la GPU tinh phi that theo giay - KHONG duoc khai
        bao la free/subsidized chi vi la lua chon duy nhat hom nay."""
        self.assertFalse(BEAM_RTX4090_PROFILE.is_free_or_subsidized)

    def test_beam_profile_uses_real_published_rate(self):
        self.assertAlmostEqual(
            BEAM_RTX4090_PROFILE.cost_per_second_usd, 0.000191667)


class TestImageRouterModuleIsProviderNeutral(unittest.TestCase):
    """Cung ky thuat AST voi
    test_character_identity.py::TestCharacterIdentityModuleIsProviderNeutral
    - server/image_router.py phai la mot ho so dinh tuyen THUAN DU LIEU,
    khong goi bat ky SDK/thu vien GPU/HTTP cu the nao."""

    _FORBIDDEN_MODULES = {"beam", "torch", "diffusers", "PIL", "httpx"}

    def test_no_provider_specific_top_level_imports(self):
        source = inspect.getsource(image_router)
        tree = ast.parse(source)
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_roots.add(node.module.split(".")[0])
        forbidden_found = imported_roots & self._FORBIDDEN_MODULES
        self.assertEqual(
            forbidden_found, set(),
            f"server/image_router.py imports provider-specific module(s) "
            f"{forbidden_found} - this module must stay provider-neutral "
            f"(routing policy over plain data only).")


if __name__ == "__main__":
    unittest.main()
