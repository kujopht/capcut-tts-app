import tempfile
import unittest
from pathlib import Path

from server.scraper.routing_history_prune import prune


class RoutingHistoryPruneTest(unittest.TestCase):
    def test_file_under_limit_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.jsonl"
            lines = ["line%d\n" % i for i in range(10)]
            p.write_text("".join(lines), encoding="utf-8")

            result = prune(p, max_lines=5000)

            self.assertEqual(result, 0)
            self.assertEqual(p.read_text(encoding="utf-8"), "".join(lines))

    def test_file_over_limit_trimmed_keeping_last(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.jsonl"
            lines = ["line%d\n" % i for i in range(50)]
            p.write_text("".join(lines), encoding="utf-8")

            result = prune(p, max_lines=10)

            self.assertEqual(result, 40)
            kept = p.read_text(encoding="utf-8").splitlines()
            self.assertEqual(kept, ["line%d" % i for i in range(40, 50)])

    def test_nonexistent_file_returns_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "missing.jsonl"
            self.assertEqual(prune(p, max_lines=1000), 0)

    def test_at_limit_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.jsonl"
            lines = ["line%d\n" % i for i in range(10)]
            p.write_text("".join(lines), encoding="utf-8")

            self.assertEqual(prune(p, max_lines=10), 0)
            self.assertEqual(p.read_text(encoding="utf-8"), "".join(lines))

    def test_accepts_string_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "history.jsonl"
            lines = ["line%d\n" % i for i in range(20)]
            p.write_text("".join(lines), encoding="utf-8")

            result = prune(str(p), max_lines=5)

            self.assertEqual(result, 15)
            self.assertEqual(
                p.read_text(encoding="utf-8").splitlines(),
                ["line%d" % i for i in range(15, 20)],
            )


if __name__ == "__main__":
    unittest.main()
