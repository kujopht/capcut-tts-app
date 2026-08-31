import ast
import inspect
import unittest

from server import character_identity
from server.character_identity import (
    CharacterIdentityRegistry, CharacterVisualIdentity,
)


class TestCharacterVisualIdentity(unittest.TestCase):
    def test_count_tag_category_male(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F", gender_presentation="male")
        self.assertEqual(identity.count_tag_category(), "boy")

    def test_count_tag_category_female(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F", gender_presentation="female")
        self.assertEqual(identity.count_tag_category(), "girl")

    def test_count_tag_category_unknown_when_unset(self):
        identity = CharacterVisualIdentity(canonical_name="A", fandom="F")
        self.assertEqual(identity.count_tag_category(), "")

    def test_count_tag_category_unknown_for_unrecognized_value(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F", gender_presentation="unspecified")
        self.assertEqual(identity.count_tag_category(), "")

    def test_to_prompt_descriptor_joins_present_fields(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F",
            hair_description="black hair", eye_description="brown eyes",
            outfit_description="tracksuit",
            distinctive_traits=["athletic build"])
        self.assertEqual(
            identity.to_prompt_descriptor(),
            "black hair, brown eyes, tracksuit, athletic build")

    def test_to_prompt_descriptor_empty_when_no_fields_set(self):
        identity = CharacterVisualIdentity(canonical_name="A", fandom="F")
        self.assertEqual(identity.to_prompt_descriptor(), "")

    def test_to_prompt_descriptor_never_includes_name(self):
        identity = CharacterVisualIdentity(
            canonical_name="Natsuki Subaru", fandom="Re:Zero",
            hair_description="black hair")
        self.assertNotIn("Natsuki Subaru", identity.to_prompt_descriptor())

    def test_to_compact_prompt_descriptor_returns_at_most_max_tags(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F",
            compact_visual_tags=["tag1", "tag2", "tag3"])
        self.assertEqual(identity.to_compact_prompt_descriptor(max_tags=2),
                          "tag1, tag2")

    def test_to_compact_prompt_descriptor_empty_when_unset(self):
        identity = CharacterVisualIdentity(canonical_name="A", fandom="F")
        self.assertEqual(identity.to_compact_prompt_descriptor(), "")

    def test_to_compact_prompt_descriptor_default_max_tags_is_two(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F",
            compact_visual_tags=["tag1", "tag2", "tag3", "tag4"])
        self.assertEqual(identity.to_compact_prompt_descriptor(), "tag1, tag2")


class TestCharacterIdentityRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = CharacterIdentityRegistry()

    def test_seed_subaru_lookup_by_canonical_name(self):
        identity = self.registry.lookup("Re:Zero", "Natsuki Subaru")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.canonical_name, "Natsuki Subaru")
        self.assertEqual(identity.gender_presentation, "male")

    def test_seed_subaru_lookup_by_alias(self):
        identity = self.registry.lookup("Re:Zero", "Subaru")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.canonical_name, "Natsuki Subaru")

    def test_seed_anastasia_lookup_by_canonical_name(self):
        identity = self.registry.lookup("Re:Zero", "Anastasia Hoshin")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.gender_presentation, "female")

    def test_lookup_is_case_and_accent_insensitive(self):
        identity = self.registry.lookup("re:zero", "NATSUKI SUBARU")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.canonical_name, "Natsuki Subaru")

    def test_lookup_wrong_fandom_returns_none(self):
        """Tranh nham nhan vat trung ten khac fandom - khoa tra cuu PHAI
        gom ca fandom, khong chi ten."""
        identity = self.registry.lookup("Naruto", "Natsuki Subaru")
        self.assertIsNone(identity)

    def test_lookup_unknown_character_returns_none_not_raises(self):
        identity = self.registry.lookup("Re:Zero", "Roswaal L Mathers")
        self.assertIsNone(identity)

    def test_source_provenance_is_recorded_for_seed_characters(self):
        for identity in self.registry.list_all():
            self.assertTrue(
                identity.source_provenance,
                f"{identity.canonical_name} missing source_provenance")

    def test_seed_characters_have_compact_visual_tags(self):
        """Real fix requirement - the two seed characters (Subaru,
        Anastasia) are exactly the pair whose FULL descriptors together
        overflowed CLIP's 77-token budget (real Beam log: "Token indices
        sequence length 216 > maximum 77"). Both must have compact tags
        so CoverPromptBuilder's compact mode actually engages for them."""
        for identity in self.registry.list_all():
            self.assertTrue(
                identity.compact_visual_tags,
                f"{identity.canonical_name} missing compact_visual_tags")
            self.assertLessEqual(
                len(identity.to_compact_prompt_descriptor()), 60,
                f"{identity.canonical_name}'s compact descriptor is "
                f"unexpectedly long for a token-budget-constrained tag")

    def test_register_new_identity_is_immediately_lookupable(self):
        registry = CharacterIdentityRegistry(seed=False)
        self.assertIsNone(registry.lookup("One Piece", "Luffy"))
        registry.register(CharacterVisualIdentity(
            canonical_name="Monkey D. Luffy", fandom="One Piece",
            aliases=["Luffy"], gender_presentation="male"))
        identity = registry.lookup("One Piece", "Luffy")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.canonical_name, "Monkey D. Luffy")

    def test_lora_field_defaults_empty_unused_placeholder(self):
        identity = self.registry.lookup("Re:Zero", "Natsuki Subaru")
        self.assertEqual(identity.lora_reference_id, "")

    def test_reference_conditioning_fields_default_empty(self):
        identity = self.registry.lookup("Re:Zero", "Natsuki Subaru")
        self.assertEqual(identity.reference_images, [])
        self.assertEqual(identity.reference_strength, 0.0)
        self.assertEqual(identity.reference_source, "")
        self.assertFalse(identity.has_reference_images())

    def test_has_reference_images_true_when_set(self):
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F",
            reference_images=["reference_images/a.png"],
            reference_strength=0.6, reference_source="fan art, example.com")
        self.assertTrue(identity.has_reference_images())

    def test_reference_images_supports_multiple_paths_per_character(self):
        """Item 3 cua mission 'Reference-Conditioned Cover V1' - schema ho
        tro NHIEU anh/nhan vat (vd nhieu goc chup de trung binh embedding
        sau nay), du code dieu kien hoa THAT trong beam_apps hien chi
        dung anh dau tien (xem docstring cua truong nay)."""
        identity = CharacterVisualIdentity(
            canonical_name="A", fandom="F",
            reference_images=["ref1.png", "ref2.png", "ref3.png"])
        self.assertEqual(len(identity.reference_images), 3)
        self.assertTrue(identity.has_reference_images())


class TestCharacterIdentityModuleIsProviderNeutral(unittest.TestCase):
    """Item 9 cua mission 'Reference-Conditioned Cover V1' - kiem tra THAT
    (AST, khong chi doc docstring) rang server/character_identity.py
    khong import beam/torch/diffusers/PIL - metadata nhan vat phai doc
    lap voi bat ky provider sinh anh cu the nao."""

    _FORBIDDEN_MODULES = {"beam", "torch", "diffusers", "PIL"}

    def test_no_provider_specific_top_level_imports(self):
        source = inspect.getsource(character_identity)
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
            f"server/character_identity.py imports provider-specific "
            f"module(s) {forbidden_found} - this module must stay "
            f"provider-neutral (metadata only).")


if __name__ == "__main__":
    unittest.main()
