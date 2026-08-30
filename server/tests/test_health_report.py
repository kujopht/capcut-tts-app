import time
import unittest

from scripts.router_v3.health_report import summarize
from scripts.router_v3.registry import ExecutionType, Health, WorkerRegistry, WorkerSpec


class TestHealthReport(unittest.TestCase):
    def test_summarize_worker_health_and_circuit_open(self):
        reg = WorkerRegistry()

        reg.register(WorkerSpec(
            worker_id="worker_1",
            provider_family="antigravity",
            execution_type=ExecutionType.LOCAL_CLI,
            pool="GEMINI_FLASH",
            capabilities=frozenset({"implement", "tests"}),
        ))
        reg.register(WorkerSpec(
            worker_id="worker_2",
            provider_family="codex",
            execution_type=ExecutionType.LOCAL_CLI,
            pool="CODEX",
            capabilities=frozenset({"review", "implement"}),
        ))
        reg.register(WorkerSpec(
            worker_id="worker_3",
            provider_family="claude",
            execution_type=ExecutionType.NATIVE_LEAD,
            pool="CLAUDE_OPUS",
            capabilities=frozenset({"architecture"}),
        ))

        reg.set_health("worker_1", Health.HEALTHY)
        reg.set_health("worker_2", Health.DEGRADED)
        reg.set_health("worker_3", Health.RATE_LIMITED)

        reg.state("worker_2").circuit_open_until = time.time() + 3600.0

        report = summarize(reg)

        self.assertEqual(report["total"], 3)
        self.assertEqual(report["by_health"], {
            "healthy": 1,
            "degraded": 1,
            "rate_limited": 1,
        })
        self.assertEqual(report["circuit_open_count"], 1)

    def test_summarize_empty_registry(self):
        reg = WorkerRegistry()
        report = summarize(reg)
        self.assertEqual(report, {
            "total": 0,
            "by_health": {},
            "circuit_open_count": 0,
        })


if __name__ == "__main__":
    unittest.main()
