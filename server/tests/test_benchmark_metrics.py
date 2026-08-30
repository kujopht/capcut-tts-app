import unittest

from scripts.router_v3.benchmark_metrics import compute


class TestBenchmarkMetrics(unittest.TestCase):
    def test_three_workers_known_values(self):
        result = compute(
            {"w1": 4.0, "w2": 6.0, "w3": 8.0},
            10.0,
        )
        self.assertEqual(
            result["utilization"],
            {"w1": 0.4, "w2": 0.6, "w3": 0.8},
        )
        self.assertEqual(result["average_utilization"], 0.6)
        self.assertEqual(result["coordination_overhead_seconds"], 2.0)
        self.assertEqual(result["speedup"], 1.8)

    def test_empty_individual_seconds(self):
        result = compute({}, 10.0)
        self.assertEqual(
            result,
            {
                "utilization": {},
                "average_utilization": 0.0,
                "coordination_overhead_seconds": 0.0,
                "speedup": 0.0,
            },
        )

    def test_single_worker_wall_equals_own_time(self):
        result = compute({"solo": 5.0}, 5.0)
        self.assertEqual(result["utilization"], {"solo": 1.0})
        self.assertEqual(result["average_utilization"], 1.0)
        self.assertEqual(result["coordination_overhead_seconds"], 0.0)
        self.assertEqual(result["speedup"], 1.0)


if __name__ == "__main__":
    unittest.main()
