import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from scripts.router_v3.benchmark_report import format_markdown_table


class TestBenchmarkReport(unittest.TestCase):
    def test_two_row_input_produces_four_lines_total(self):
        rows = [
            {"worker": "Worker 1", "task": "Test Task A", "seconds": 1.234},
            {"worker": "Worker 2", "task": "Test Task B", "seconds": 5.6},
        ]
        result = format_markdown_table(rows)
        lines = result.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0], "| Worker | Task | Time |")
        self.assertEqual(lines[1], "| --- | --- | --- |")
        self.assertEqual(lines[2], "| Worker 1 | Test Task A | 1.23s |")
        self.assertEqual(lines[3], "| Worker 2 | Test Task B | 5.60s |")

    def test_empty_list_produces_header_and_separator(self):
        rows = []
        result = format_markdown_table(rows)
        lines = result.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "| Worker | Task | Time |")
        self.assertEqual(lines[1], "| --- | --- | --- |")

    def test_seconds_formatted_with_two_decimal_places_even_when_given_int(self):
        rows = [
            {"worker": "Worker 1", "task": "Test Task A", "seconds": 5},
        ]
        result = format_markdown_table(rows)
        lines = result.splitlines()
        self.assertEqual(lines[2], "| Worker 1 | Test Task A | 5.00s |")

if __name__ == '__main__':
    unittest.main()
