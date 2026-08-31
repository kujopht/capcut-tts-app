import unittest

from server.cover_quality_checklist import CoverQualityEvaluation


class TestCoverQualityEvaluationConstruction(unittest.TestCase):
    def test_default_construction_is_all_falsy(self):
        evaluation = CoverQualityEvaluation()
        self.assertEqual(evaluation.character_count, 0)
        self.assertFalse(evaluation.primary_identity_recognizable)
        self.assertFalse(evaluation.production_ready)
        self.assertEqual(evaluation.notes, "")

    def test_constructs_with_filled_in_manual_evaluation(self):
        evaluation = CoverQualityEvaluation(
            character_count=2,
            primary_identity_recognizable=True,
            secondary_identity_recognizable=True,
            identity_blending_observed=False,
            duplicate_people_observed=False,
            faces_visible=True,
            composition_acceptable=True,
            text_artifact_observed=False,
            production_ready=True,
            notes="Bo cuc dep, ca hai nhan vat deu ro net.",
        )
        self.assertTrue(evaluation.production_ready)
        self.assertEqual(evaluation.character_count, 2)


class TestCoverQualityEvaluationDictRoundTrip(unittest.TestCase):
    def test_to_dict_contains_all_mission_fields(self):
        evaluation = CoverQualityEvaluation(character_count=1)
        data = evaluation.to_dict()
        expected_keys = {
            "character_count",
            "primary_identity_recognizable",
            "secondary_identity_recognizable",
            "identity_blending_observed",
            "duplicate_people_observed",
            "faces_visible",
            "composition_acceptable",
            "text_artifact_observed",
            "production_ready",
            "notes",
        }
        self.assertEqual(set(data.keys()), expected_keys)

    def test_from_dict_round_trips_to_equal_object(self):
        original = CoverQualityEvaluation(
            character_count=3,
            duplicate_people_observed=True,
            notes="Co mot nguoi thua o goc phai.",
        )
        rebuilt = CoverQualityEvaluation.from_dict(original.to_dict())
        self.assertEqual(original, rebuilt)

    def test_from_dict_raises_on_unknown_key(self):
        with self.assertRaises(TypeError):
            CoverQualityEvaluation.from_dict({"not_a_real_field": True})


if __name__ == "__main__":
    unittest.main()
