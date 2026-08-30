"""Bo test khong mang/kho ben vung cho source-level harvest orchestrator."""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from server.scraper.orchestrator import HarvestOrchestrator, HarvestSourceState
from server.scraper.run_state import ScrapeRunStatus


@dataclass
class FakeRun:
    run_id: str
    source_url: str
    status: Any = ScrapeRunStatus.RUNNING
    source_domain: str = ""
    count_failed: int = 0


class ManualTime:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.base = datetime(2026, 8, 31, tzinfo=timezone.utc)

    def monotonic(self) -> float:
        return self.seconds

    def now(self) -> datetime:
        return self.base + timedelta(seconds=self.seconds)

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


class FakeScraperOpsService:
    """Stand-in cho TOAN BO ScraperOpsService, khong cham fetcher/Appwrite."""

    def __init__(self, runs: List[FakeRun]) -> None:
        self.runs = {run.run_id: run for run in runs}
        self.drive_behaviors: Dict[str, List[Any]] = {}
        self.drive_calls: List[str] = []
        self.start_calls: List[str] = []
        self.update_calls: List[str] = []

    def list_runs(self) -> Dict[str, Any]:
        return {"runs": list(self.runs.values()), "supported_domains": []}

    def drive(self, run_id: str, *, max_chapters=None) -> Dict[str, Any]:
        self.drive_calls.append(run_id)
        queue = self.drive_behaviors.get(run_id, [])
        behavior = queue.pop(0) if queue else None
        if isinstance(behavior, Exception):
            raise behavior
        run = self.runs[run_id]
        return {"run": run, "counts": {}, "progress": {}}

    def start_or_continue(self, url: str) -> Dict[str, Any]:
        self.start_calls.append(url)
        for run in self.runs.values():
            if run.source_url == url:
                run.status = ScrapeRunStatus.RUNNING
                return {"run": run, "progress": {}}
        run_id = "run_started_" + str(len(self.runs) + 1)
        run = FakeRun(run_id, url)
        self.runs[run_id] = run
        return {"run": run, "progress": {}}

    def check_for_updates(self, run_id: str) -> Dict[str, Any]:
        self.update_calls.append(run_id)
        return {"run_id": run_id, "has_changes": False}


def make_orchestrator(
        service: FakeScraperOpsService,
        sources: List[HarvestSourceState],
        manual: ManualTime,
        **kwargs: Any) -> HarvestOrchestrator:
    return HarvestOrchestrator(
        service, sources, sleep_fn=lambda _seconds: None,
        clock_fn=manual.monotonic, now_fn=manual.now, **kwargs)


class CircuitBreakerTest(unittest.TestCase):
    def test_mo_sau_n_loi_lien_tiep_va_ngung_goi_nguon(self):
        manual = ManualTime()
        run = FakeRun("run_broken", "https://royalroad.com/fiction/1/x")
        service = FakeScraperOpsService([run])
        service.drive_behaviors[run.run_id] = [
            RuntimeError("source down"), RuntimeError("still down")]
        source = HarvestSourceState(run_id=run.run_id, source_url=run.source_url)
        orchestrator = make_orchestrator(
            service, [source], manual, failure_threshold=2, max_retries=0,
            circuit_cooldown_seconds=60)

        self.assertEqual(orchestrator.run_one_cycle()["failed"], 1)
        self.assertEqual(orchestrator.run_one_cycle()["failed"], 1)
        skipped = orchestrator.run_one_cycle()

        self.assertEqual(source.circuit_state, "open")
        self.assertEqual(source.consecutive_failures, 2)
        self.assertEqual(skipped["skipped"], 1)
        self.assertEqual(skipped["sources"][0]["reason"], "circuit_open")
        self.assertEqual(service.drive_calls, [run.run_id, run.run_id])

    def test_half_open_thanh_cong_dong_lai_circuit(self):
        manual = ManualTime()
        run = FakeRun("run_recover", "https://royalroad.com/fiction/2/y")
        service = FakeScraperOpsService([run])
        service.drive_behaviors[run.run_id] = [
            OSError("temporary 1"), OSError("temporary 2"), None]
        source = HarvestSourceState(run_id=run.run_id, source_url=run.source_url)
        orchestrator = make_orchestrator(
            service, [source], manual, failure_threshold=2, max_retries=0,
            circuit_cooldown_seconds=10)

        orchestrator.run_one_cycle()
        orchestrator.run_one_cycle()
        self.assertEqual(source.circuit_state, "open")
        manual.advance(10)

        recovered = orchestrator.run_one_cycle()

        self.assertEqual(recovered["succeeded"], 1)
        self.assertEqual(source.circuit_state, "closed")
        self.assertEqual(source.consecutive_failures, 0)
        self.assertIsNotNone(source.last_success_at)
        self.assertEqual(len(service.drive_calls), 3)


class RetryAndIsolationTest(unittest.TestCase):
    def test_rate_limit_bo_qua_nguon_den_khi_du_khoang_cach(self):
        manual = ManualTime()
        run = FakeRun("run_limited", "https://vi.wikisource.org/wiki/Limited")
        service = FakeScraperOpsService([run])
        source = HarvestSourceState(
            run_id=run.run_id, source_url=run.source_url,
            min_interval_seconds=30)
        orchestrator = make_orchestrator(service, [source], manual)

        first = orchestrator.run_one_cycle()
        too_soon = orchestrator.run_one_cycle()
        manual.advance(30)
        due_again = orchestrator.run_one_cycle()

        self.assertEqual(first["succeeded"], 1)
        self.assertEqual(too_soon["sources"][0]["reason"], "rate_limited")
        self.assertEqual(due_again["succeeded"], 1)
        self.assertEqual(service.drive_calls, [run.run_id, run.run_id])

    def test_retry_bounded_voi_exponential_backoff(self):
        manual = ManualTime()
        run = FakeRun("run_flaky", "https://vi.wikisource.org/wiki/Truyen")
        service = FakeScraperOpsService([run])
        service.drive_behaviors[run.run_id] = [
            TimeoutError("one"), TimeoutError("two"), None]
        delays: List[float] = []
        source = HarvestSourceState(run_id=run.run_id, source_url=run.source_url)
        orchestrator = HarvestOrchestrator(
            service, [source], max_retries=2, backoff_base_seconds=0.5,
            backoff_max_seconds=10, failure_threshold=3,
            sleep_fn=delays.append, clock_fn=manual.monotonic,
            now_fn=manual.now)

        result = orchestrator.run_one_cycle()

        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["sources"][0]["attempts"], 3)
        self.assertEqual(delays, [0.5, 1.0])
        self.assertEqual(service.drive_calls, [run.run_id] * 3)
        self.assertEqual(source.total_failures, 0,
                         "Loi transient da recover khong tinh thanh cycle that bai")

    def test_mot_nguon_hong_khong_chan_nguon_khac(self):
        manual = ManualTime()
        broken = FakeRun("run_bad", "https://royalroad.com/fiction/3/bad")
        healthy = FakeRun("run_good", "https://vi.wikisource.org/wiki/Good")
        service = FakeScraperOpsService([broken, healthy])
        service.drive_behaviors[broken.run_id] = [RuntimeError("permanent")]
        source_bad = HarvestSourceState(
            run_id=broken.run_id, source_url=broken.source_url)
        source_good = HarvestSourceState(
            run_id=healthy.run_id, source_url=healthy.source_url)
        orchestrator = make_orchestrator(
            service, [source_bad, source_good], manual,
            max_retries=0, failure_threshold=1)

        result = orchestrator.run_one_cycle()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(service.drive_calls, [broken.run_id, healthy.run_id])
        self.assertEqual(source_bad.circuit_state, "open")
        self.assertIsNotNone(source_good.last_success_at)


class StatusReportTest(unittest.TestCase):
    def test_shape_co_health_last_success_failure_jobs_va_quarantine(self):
        manual = ManualTime()
        queued = FakeRun(
            "run_queue", "https://royalroad.com/fiction/4/q",
            status=ScrapeRunStatus.PLANNING, source_domain="royalroad.com",
            count_failed=2)
        running = FakeRun(
            "run_live", "https://vi.wikisource.org/wiki/Live",
            status=ScrapeRunStatus.RUNNING, source_domain="vi.wikisource.org",
            count_failed=1)
        completed = FakeRun(
            "run_done", "https://vi.wikisource.org/wiki/Done",
            status=ScrapeRunStatus.COMPLETED, source_domain="vi.wikisource.org",
            count_failed=4)
        service = FakeScraperOpsService([queued, running, completed])
        source = HarvestSourceState(
            run_id=running.run_id, source_url=running.source_url,
            consecutive_failures=1, total_failures=3,
            last_success_at="2026-08-30T12:00:00+00:00")
        orchestrator = make_orchestrator(service, [source], manual)

        report = orchestrator.status_report()

        self.assertEqual(set(report), {
            "generated_at", "sources", "jobs", "items_quarantined"})
        self.assertEqual(report["jobs"], {
            "queued_runs": 1, "running_runs": 1})
        self.assertEqual(report["items_quarantined"], 7)
        row = report["sources"][0]
        self.assertEqual(row["health"], "degraded")
        self.assertEqual(row["last_successful_harvest"], source.last_success_at)
        self.assertEqual(row["consecutive_failures"], 1)
        self.assertEqual(row["total_failures"], 3)
        self.assertEqual(row["items_quarantined"], 1)
        self.assertEqual(row["circuit_breaker"]["state"], "closed")


if __name__ == "__main__":
    unittest.main()
