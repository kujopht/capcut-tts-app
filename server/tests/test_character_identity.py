import unittest

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

    def test_register_new_identity_is_immediately_lookupable(self):
        registry = CharacterIdentityRegistry(seed=False)
        self.assertIsNone(registry.lookup("One Piece", "Luffy"))
        registry.register(CharacterVisualIdentity(
            canonical_name="Monkey D. Luffy", fandom="One Piece",
            aliases=["Luffy"], gender_presentation="male"))
        identity = registry.lookup("One Piece", "Luffy")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.canonical_name, "Monkey D. Luffy")

    def test_lora_and_reference_fields_default_empty_unused_placeholders(self):
        identity = self.registry.lookup("Re:Zero", "Natsuki Subaru")
        self.assertEqual(identity.lora_reference_id, "")
        self.assertEqual(identity.reference_asset_url, "")


if __name__ == "__main__":
    unittest.main()
