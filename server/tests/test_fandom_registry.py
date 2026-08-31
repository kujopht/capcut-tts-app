"""Fandom normalization — server/fandom_registry.py + server/domain.py::Fandom."""
from __future__ import annotations

import unittest

from server.domain import Fandom, FandomMediaType, Novel, NovelStatus, PublicationMode
from server.fandom_registry import FandomRegistry, UnknownFandomError


class SeedAliasTest(unittest.TestCase):
    def setUp(self):
        self.reg = FandomRegistry()

    def test_bnha_mha_va_ten_day_du_quy_ve_cung_fandom(self):
        canonical = self.reg.resolve("My Hero Academia")
        self.assertEqual(self.reg.resolve("BNHA").fandom_id, canonical.fandom_id)
        self.assertEqual(self.reg.resolve("MHA").fandom_id, canonical.fandom_id)
        self.assertEqual(
            self.reg.resolve("Boku no Hero Academia").fandom_id, canonical.fandom_id)

    def test_khong_phan_biet_hoa_thuong_va_khoang_trang_thua(self):
        canonical = self.reg.resolve("Naruto")
        self.assertEqual(self.reg.resolve("  naruto  ").fandom_id, canonical.fandom_id)
        self.assertEqual(self.reg.resolve("NARUTO").fandom_id, canonical.fandom_id)

    def test_ten_chua_biet_tra_ve_none_qua_lookup(self):
        self.assertIsNone(self.reg.lookup("Mot Fandom Khong Ton Tai Nao Do"))

    def test_ten_chua_biet_nem_loi_ro_rang_qua_resolve(self):
        with self.assertRaises(UnknownFandomError):
            self.reg.resolve("Mot Fandom Khong Ton Tai Nao Do")


class RegisterAndAddAliasTest(unittest.TestCase):
    def setUp(self):
        self.reg = FandomRegistry(seed=False)  # trong, tu dang ky de kiem soat

    def test_dang_ky_fandom_moi_va_tra_cuu_lai_duoc(self):
        self.reg.register(Fandom(
            canonical_name="Jujutsu Kaisen", media_type=FandomMediaType.MANGA,
            aliases=["JJK"]))
        self.assertEqual(self.reg.resolve("Jujutsu Kaisen").canonical_name, "Jujutsu Kaisen")
        self.assertEqual(self.reg.resolve("JJK").canonical_name, "Jujutsu Kaisen")

    def test_them_alias_cho_fandom_da_dang_ky(self):
        fandom = self.reg.register(Fandom(canonical_name="Naruto"))
        self.reg.add_alias("Naruto", "Naruto Shippuuden", source_name="FanFiction.net")
        self.assertEqual(self.reg.resolve("Naruto Shippuuden").fandom_id, fandom.fandom_id)
        self.assertIn("FanFiction.net", self.reg.get(fandom.fandom_id).source_names)

    def test_them_alias_cho_fandom_chua_dang_ky_nem_loi(self):
        with self.assertRaises(UnknownFandomError):
            self.reg.add_alias("Khong Ton Tai", "alias-nao-do")


class ClassifyManyTest(unittest.TestCase):
    def test_crossover_giu_lai_phan_da_khop_va_bao_phan_chua_khop(self):
        reg = FandomRegistry()
        result = reg.classify_many(["Naruto", "My Hero Academia", "Mot OC Fandom La"])
        self.assertEqual(len(result["matched"]), 2)
        self.assertEqual(result["unmatched"], ["Mot OC Fandom La"])


class NovelPublicationModeTest(unittest.TestCase):
    def test_mac_dinh_full_text_tuong_thich_nguoc(self):
        novel = Novel(owner_id="u1", title="T")
        self.assertEqual(novel.publication_mode, PublicationMode.FULL_TEXT)
        self.assertEqual(novel.fandom_ids, [])
        self.assertEqual(novel.characters, [])
        self.assertEqual(novel.pairings, [])
        self.assertEqual(novel.status, NovelStatus.ONGOING)
        self.assertEqual(novel.to_dict()["publication_mode"], "full_text")
        self.assertEqual(novel.to_dict()["characters"], [])
        self.assertEqual(novel.to_dict()["pairings"], [])
        self.assertEqual(novel.to_dict()["status"], "ongoing")

    def test_metadata_only_giu_duoc_external_source_url(self):
        novel = Novel(
            owner_id="svc_harvester", title="Ninja's Hero Academia",
            publication_mode=PublicationMode.METADATA_ONLY,
            external_source_url="https://www.fanfiction.net/s/13530962/1/Ninja-s-Hero-Academia",
            external_author_name="some-author",
            external_chapter_count=25, language="en")
        data = novel.to_dict()
        self.assertEqual(data["publication_mode"], "metadata_only")
        self.assertEqual(data["external_chapter_count"], 25)
        self.assertTrue(data["external_source_url"])

    def test_novel_taxonomy_characters_pairings_status_round_trip(self):
        novel = Novel(
            owner_id="u1",
            title="Naruto: The New Beginning",
            characters=["Uzumaki Naruto", "Uchiha Sasuke", "Haruno Sakura"],
            pairings=["Naruto/Hinata", "Sasuke/Sakura"],
            status=NovelStatus.COMPLETED,
        )
        self.assertEqual(novel.characters, ["Uzumaki Naruto", "Uchiha Sasuke", "Haruno Sakura"])
        self.assertEqual(novel.pairings, ["Naruto/Hinata", "Sasuke/Sakura"])
        self.assertEqual(novel.status, NovelStatus.COMPLETED)

        data = novel.to_dict()
        self.assertEqual(data["characters"], ["Uzumaki Naruto", "Uchiha Sasuke", "Haruno Sakura"])
        self.assertEqual(data["pairings"], ["Naruto/Hinata", "Sasuke/Sakura"])
        self.assertEqual(data["status"], "completed")

    def test_novel_status_enum_values(self):
        self.assertEqual(NovelStatus.ONGOING.value, "ongoing")
        self.assertEqual(NovelStatus.COMPLETED.value, "completed")
        self.assertEqual(NovelStatus.HIATUS.value, "hiatus")
        self.assertEqual(NovelStatus("ongoing"), NovelStatus.ONGOING)
        self.assertEqual(NovelStatus("completed"), NovelStatus.COMPLETED)
        self.assertEqual(NovelStatus("hiatus"), NovelStatus.HIATUS)


if __name__ == "__main__":
    unittest.main()
