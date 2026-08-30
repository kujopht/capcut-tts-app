import unittest

from server.chat.evaluation import run_evaluation_cases


class ChatEvaluationTest(unittest.TestCase):
    def setUp(self):
        self.result = run_evaluation_cases()

    def test_returns_all_eight_case_keys(self):
        expected = {f"case_{i}" for i in range(1, 9)}
        self.assertEqual(set(self.result["cases"].keys()), expected)

    def test_case_3_spoiler_safety_passes(self):
        self.assertTrue(self.result["cases"]["case_3"]["pass"])

    def test_zero_spoiler_violations_across_all_cases(self):
        self.assertEqual(self.result["summary"]["spoiler_violations"], 0)

    def test_case_7_found_the_right_chapter(self):
        self.assertGreater(self.result["summary"]["citation_correctness"], 0)
        self.assertTrue(self.result["cases"]["case_7"]["pass"])

    def test_cost_is_zero_empty_not_fabricated(self):
        self.assertEqual(self.result["summary"]["provider_cost_estimate_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
