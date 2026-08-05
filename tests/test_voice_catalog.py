"""Test doc Voice.json + tim kiem / loc / sap xep / yeu thich."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from desktop_app.models import VoiceEntry, slugify
from desktop_app.voice_catalog import (
    VoiceCatalog,
    VoiceCatalogError,
    find_catalog_path,
    voice_sort_key,
)

REAL_CATALOG = Path(__file__).resolve().parent.parent / "Voice.json"


class TestRealCatalog(unittest.TestCase):
    """Doc dung file Voice.json thuc te cua repo."""

    def setUp(self) -> None:
        if not REAL_CATALOG.is_file():
            self.skipTest("Không có Voice.json trong repo")
        self.catalog = VoiceCatalog()
        self.catalog.load(REAL_CATALOG)

    def test_loads_all_voices_dynamically(self) -> None:
        # Voice.json thuc te co 129 giong — khong hardcode con so trong code app
        self.assertGreater(self.catalog.count, 100)
        self.assertEqual(self.catalog.count, len(json.loads(REAL_CATALOG.read_text("utf-8"))) - self.catalog.skipped_entries)

    def test_three_legacy_voices_still_present(self) -> None:
        """3 giong cua ban Gradio cu van phai co, khong bi mat chuc nang."""
        wanted = {
            "BV421_vivn_streaming": "Nhỏ Ngọt Ngào",
            "BV074_streaming": "Cô Gái Hoạt Ngôn",
            "multi_female_richgirl_uranus_bigtts": "Review Phim new",
        }
        by_type = {v.voice_type: v for v in self.catalog.voices}
        for voice_type, display in wanted.items():
            self.assertIn(voice_type, by_type)
            self.assertEqual(by_type[voice_type].display_name, display)
            self.assertTrue(by_type[voice_type].resource_id)

    def test_languages_available(self) -> None:
        langs = self.catalog.languages()
        self.assertIn("vi-VN", langs)
        self.assertGreater(len(langs), 3)

    def test_filter_by_language(self) -> None:
        vi = self.catalog.filter(language="vi-VN")
        self.assertTrue(vi)
        for voice in vi:
            self.assertTrue(voice.lang == "vi-VN" or voice.lan == "vi")

    def test_search_by_name_and_type(self) -> None:
        by_type = self.catalog.filter(query="BV421_vivn_streaming")
        self.assertTrue(any(v.voice_type == "BV421_vivn_streaming" for v in by_type))

        by_name = self.catalog.filter(query="Nhỏ Ngọt")
        self.assertTrue(any(v.voice_type == "BV421_vivn_streaming" for v in by_name))

        # Tim khong dau cung phai ra ket qua
        no_accent = self.catalog.filter(query="nho ngot ngao")
        self.assertTrue(any(v.voice_type == "BV421_vivn_streaming" for v in no_accent))

    def test_search_no_result(self) -> None:
        self.assertEqual(self.catalog.filter(query="zzz_khong_ton_tai_zzz"), [])

    def test_duplicate_voice_types_get_unique_uids(self) -> None:
        """Voice.json thuc te co voice_type trung — uid phai van duy nhat."""
        uids = [v.uid for v in self.catalog.voices]
        self.assertEqual(len(uids), len(set(uids)))

    def test_sort_modes(self) -> None:
        ascending = self.catalog.filter(sort_mode="name_asc")
        keys = [voice_sort_key(v) for v in ascending]
        self.assertEqual(keys, sorted(keys))

        descending = self.catalog.filter(sort_mode="name_desc")
        self.assertEqual(
            [voice_sort_key(v) for v in descending], sorted(keys, reverse=True)
        )

    def test_non_latin_names_sort_deterministically(self) -> None:
        """Ten tieng Trung/Thai/Nhat khong duoc dinh chung mot khoa fallback."""
        non_latin = [
            v for v in self.catalog.voices
            if not slugify(v.label, fallback="")
        ]
        if not non_latin:
            self.skipTest("Catalog không có tên ngoài chữ Latin")
        keys = {voice_sort_key(v) for v in non_latin}
        self.assertGreater(len(keys), 1, "Mỗi tên phải có khóa sắp xếp riêng")

    def test_sort_by_language(self) -> None:
        by_lang = self.catalog.filter(sort_mode="lang_asc")
        langs = [v.language.lower() for v in by_lang]
        self.assertEqual(langs, sorted(langs))

        by_type = [v.voice_type for v in self.catalog.filter(sort_mode="type_asc")]
        self.assertEqual(by_type, sorted(by_type, key=str.lower))

        catalog_order = self.catalog.filter(sort_mode="catalog")
        self.assertEqual(catalog_order[0].voice_type, self.catalog.voices[0].voice_type)

    def test_favorites_roundtrip(self) -> None:
        first = self.catalog.voices[0]
        self.assertFalse(self.catalog.is_favorite(first.uid))
        self.assertTrue(self.catalog.toggle_favorite(first.uid))
        self.assertIn(first.uid, self.catalog.favorites)

        only_fav = self.catalog.filter(favorites_only=True)
        self.assertEqual([v.uid for v in only_fav], [first.uid])

        self.assertFalse(self.catalog.toggle_favorite(first.uid))
        self.assertEqual(self.catalog.filter(favorites_only=True), [])

    def test_prune_favorites_removes_unknown(self) -> None:
        self.catalog.set_favorites(["khong_ton_tai|123", self.catalog.voices[0].uid])
        removed = self.catalog.prune_favorites()
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.catalog.favorites), 1)

    def test_resolve_ignores_missing(self) -> None:
        uid = self.catalog.voices[0].uid
        resolved = self.catalog.resolve([uid, "khong_ton_tai|0"])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].uid, uid)

    def test_find_catalog_path(self) -> None:
        self.assertIsNotNone(find_catalog_path())


class TestCatalogEdgeCases(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, name: str, content: str) -> Path:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_missing_file(self) -> None:
        with self.assertRaises(VoiceCatalogError):
            VoiceCatalog().load(self.dir / "khong_co.json")

    def test_invalid_json(self) -> None:
        path = self._write("bad.json", "{ khong phai json")
        with self.assertRaises(VoiceCatalogError):
            VoiceCatalog().load(path)

    def test_empty_list(self) -> None:
        path = self._write("empty.json", "[]")
        with self.assertRaises(VoiceCatalogError):
            VoiceCatalog().load(path)

    def test_entries_missing_voice_type_are_skipped(self) -> None:
        path = self._write(
            "partial.json",
            json.dumps(
                [
                    {"display_name": "Không có voice_type"},
                    {"voice_type": "ok_voice", "display_name": "Ổn"},
                ],
                ensure_ascii=False,
            ),
        )
        catalog = VoiceCatalog()
        catalog.load(path)
        self.assertEqual(catalog.count, 1)
        self.assertEqual(catalog.skipped_entries, 1)

    def test_missing_optional_fields_are_tolerated(self) -> None:
        """Chi voice_type la bat buoc; field khac thieu thi hien '' chu khong crash."""
        path = self._write("min.json", json.dumps([{"voice_type": "only_type"}]))
        catalog = VoiceCatalog()
        catalog.load(path)
        voice = catalog.voices[0]
        self.assertEqual(voice.label, "only_type")     # fallback ve voice_type
        self.assertEqual(voice.resource_id, "")
        self.assertEqual(voice.language, "")

    def test_dict_wrapper_format(self) -> None:
        path = self._write(
            "wrapped.json", json.dumps({"voices": [{"voice_type": "v1", "display_name": "Một"}]})
        )
        catalog = VoiceCatalog()
        catalog.load(path)
        self.assertEqual(catalog.count, 1)

    def test_extra_unknown_fields_preserved(self) -> None:
        path = self._write(
            "extra.json",
            json.dumps([{"voice_type": "v1", "display_name": "Một", "gender": "female"}]),
        )
        catalog = VoiceCatalog()
        catalog.load(path)
        self.assertEqual(catalog.voices[0].extra.get("gender"), "female")

    def test_reload(self) -> None:
        path = self._write("r.json", json.dumps([{"voice_type": "a"}]))
        catalog = VoiceCatalog()
        catalog.load(path)
        self.assertEqual(catalog.count, 1)
        path.write_text(json.dumps([{"voice_type": "a"}, {"voice_type": "b"}]), encoding="utf-8")
        catalog.reload()
        self.assertEqual(catalog.count, 2)


class TestVoiceEntry(unittest.TestCase):
    def test_slug_strips_vietnamese_diacritics(self) -> None:
        self.assertEqual(slugify("Nhỏ Ngọt Ngào"), "nho_ngot_ngao")
        self.assertEqual(slugify("Cô Gái Hoạt Ngôn"), "co_gai_hoat_ngon")
        self.assertEqual(slugify("Review Phim new"), "review_phim_new")
        self.assertEqual(slugify("Đường Đi Khó"), "duong_di_kho")

    def test_slug_fallback(self) -> None:
        self.assertEqual(slugify("", fallback="x"), "x")
        self.assertEqual(slugify("###"), "input")

    def test_slug_windows_safe(self) -> None:
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, slugify(f"ten{ch}file"))

    def test_from_dict_rejects_non_dict(self) -> None:
        self.assertIsNone(VoiceEntry.from_dict("khong phai dict"))
        self.assertIsNone(VoiceEntry.from_dict({"display_name": "thieu voice_type"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
