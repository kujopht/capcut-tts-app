"""
Hop dong giua tang domain va schema Appwrite.

Vi sao can bo test nay: `to_dict()` cua domain la hinh dang cua API, khong phai
hinh dang luu tru. No kem ca truong TINH TOAN (`char_count` cua Chapter,
`progress` cua TtsJob) ma frontend can. Gui thang len Appwrite thi bi tu choi:

    Invalid document structure: Unknown attribute: "char_count"

Loi nay CHI lo ra khi chay that - da xay ra dung nhu vay o buoc live smoke
test. Cac test duoi day bat no ngay khi chay offline.

Cung kiem tra chieu nguoc lai: moi truong trong schema deu phai duoc mot
`to_dict()` nao do sinh ra, neu khong thi thuoc tinh do khong bao gio duoc ghi.
"""

from __future__ import annotations

import unittest

from server.appwrite_store import (
    COL_CHAPTERS,
    COL_JOBS,
    COL_NOVELS,
    COL_TRACKS,
    PERSISTED_FIELDS,
    persistable,
)
from server.domain import AudioTrack, Chapter, Novel, Profile, TtsJob

#: Truong CO Y chi phuc vu API, khong luu vao Appwrite.
DERIVED_ONLY = {
    COL_CHAPTERS: {"char_count"},
    COL_JOBS: {"progress"},
    COL_NOVELS: set(),
    COL_TRACKS: set(),
}


def _samples():
    return {
        COL_NOVELS: Novel(owner_id="usr_1", title="T").to_dict(),
        COL_CHAPTERS: Chapter(novel_id="nov_1", owner_id="usr_1", title="C",
                              content="noi dung").to_dict(),
        COL_JOBS: TtsJob(owner_id="usr_1", chapter_id="chp_1", voice_id="edge:v",
                         content_hash="h").to_dict(),
        COL_TRACKS: AudioTrack(chapter_id="chp_1", owner_id="usr_1", voice_id="v",
                               object_key="k", content_hash="h").to_dict(),
    }


class TestPersistableFiltersDerivedFields(unittest.TestCase):
    def test_char_count_is_never_sent_to_appwrite(self):
        data = Chapter(novel_id="n", owner_id="u", title="C", content="abc").to_dict()
        self.assertIn("char_count", data, "API vẫn phải trả char_count")
        self.assertNotIn("char_count", persistable(COL_CHAPTERS, data))

    def test_progress_is_never_sent_to_appwrite(self):
        data = TtsJob(owner_id="u", chapter_id="c", voice_id="v",
                      content_hash="h").to_dict()
        self.assertIn("progress", data, "API vẫn phải trả progress")
        self.assertNotIn("progress", persistable(COL_JOBS, data))

    def test_no_unknown_attribute_survives_for_any_collection(self):
        for collection, data in _samples().items():
            filtered = persistable(collection, data)
            unknown = set(filtered) - set(PERSISTED_FIELDS[collection])
            self.assertEqual(unknown, set(), f"{collection}: thuộc tính lạ {unknown}")

    def test_exactly_the_derived_fields_are_dropped(self):
        for collection, data in _samples().items():
            dropped = set(data) - set(persistable(collection, data))
            self.assertEqual(
                dropped, DERIVED_ONLY[collection],
                f"{collection}: bỏ đi {dropped}, mong đợi {DERIVED_ONLY[collection]}",
            )

    def test_nothing_persisted_is_accidentally_dropped(self):
        for collection, data in _samples().items():
            kept = set(persistable(collection, data))
            expected = set(data) - DERIVED_ONLY[collection]
            self.assertEqual(kept, expected, f"{collection}: mất trường cần lưu")


class TestSchemaMatchesSetupScript(unittest.TestCase):
    """`PERSISTED_FIELDS` phai khop chinh xac schema ma script setup tao ra."""

    def _script_attributes(self, collection: str) -> set:
        from scripts.setup_appwrite import SCHEMA

        return {key for key, *_ in SCHEMA[collection]["attributes"]}

    def test_every_collection_matches_the_created_schema(self):
        for collection in (COL_NOVELS, COL_CHAPTERS, COL_JOBS, COL_TRACKS):
            self.assertEqual(
                set(PERSISTED_FIELDS[collection]),
                self._script_attributes(collection),
                f"{collection}: PERSISTED_FIELDS lệch với scripts/setup_appwrite.py",
            )

    def test_profile_to_dict_matches_its_schema_exactly(self):
        """`profiles` duoc ghi thang bang `to_dict()`, nen phai khop tuyet doi."""
        from scripts.setup_appwrite import SCHEMA

        expected = {key for key, *_ in SCHEMA["profiles"]["attributes"]}
        actual = set(Profile(user_id="u", email="a@b.c").to_dict())
        self.assertEqual(actual, expected)

    def test_every_schema_attribute_is_produced_by_the_domain(self):
        """Thuoc tinh co trong schema ma domain khong sinh ra = khong bao gio duoc ghi."""
        for collection, data in _samples().items():
            missing = set(PERSISTED_FIELDS[collection]) - set(data)
            self.assertEqual(
                missing, set(), f"{collection}: schema có {missing} nhưng domain không sinh ra"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
