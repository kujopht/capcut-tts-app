import unittest
from types import SimpleNamespace
from scripts.router_v3.checkpoint_diff import diff


class TestCheckpointDiff(unittest.TestCase):
    def test_diff_states(self):
        cp_a = SimpleNamespace(
            dag_state={
                "n_pending_to_ok": "pending",
                "n_ok_to_failed": "ok",
                "n_still_pending": "pending",
                "n_unchanged_ok": "ok",
                "n_unchanged_failed": "failed",
            }
        )
        cp_b = SimpleNamespace(
            dag_state={
                "n_pending_to_ok": "ok",
                "n_ok_to_failed": "failed",
                "n_still_pending": "pending",
                "n_unchanged_ok": "ok",
                "n_unchanged_failed": "failed",
            }
        )

        res = diff(cp_a, cp_b)

        self.assertIn("n_pending_to_ok", res["newly_ok"])
        self.assertNotIn("n_unchanged_ok", res["newly_ok"])

        self.assertIn("n_ok_to_failed", res["newly_failed"])
        self.assertNotIn("n_unchanged_failed", res["newly_failed"])

        self.assertIn("n_still_pending", res["still_pending"])

        self.assertNotIn("n_unchanged_ok", res["newly_ok"])
        self.assertNotIn("n_unchanged_ok", res["newly_failed"])
        self.assertNotIn("n_unchanged_ok", res["still_pending"])

        self.assertNotIn("n_unchanged_failed", res["newly_ok"])
        self.assertNotIn("n_unchanged_failed", res["newly_failed"])
        self.assertNotIn("n_unchanged_failed", res["still_pending"])


if __name__ == "__main__":
    unittest.main()
