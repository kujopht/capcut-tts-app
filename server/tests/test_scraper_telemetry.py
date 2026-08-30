import json
import threading
import unittest

from server.scraper.harvest_state import ErrorCategory, HarvestState, ItemProgress
from server.scraper.run_state import ScrapeItemStatus
from server.scraper.telemetry import HarvestTelemetry, summarize_run


class HarvestTelemetryTest(unittest.TestCase):
    def test_record_transition_rejects_raw_string(self):
        """Bai quyet dinh: nhan thang str thay vi HarvestState la duong ro
        ri item_id/diagnostic vao telemetry neu nguoi goi lo truyen nham."""
        t = HarvestTelemetry()
        with self.assertRaises(TypeError):
            t.record_transition("item-bi-mat-xyz", HarvestState.FETCHING)
        with self.assertRaises(TypeError):
            t.record_error("Sensitive token leak: sk-secret-123")
        assert t.snapshot() == {"transitions": {}, "errors": {}}

    def test_transitions_and_errors_increment_correctly(self):
        t = HarvestTelemetry()
        assert t.snapshot() == {"transitions": {}, "errors": {}}

        t.record_transition(HarvestState.DISCOVERED, HarvestState.FETCHING)
        t.record_transition(HarvestState.DISCOVERED, HarvestState.FETCHING)
        t.record_transition(HarvestState.FETCHING, HarvestState.PARSED)
        t.record_error(ErrorCategory.NETWORK)
        t.record_error(ErrorCategory.NETWORK)
        t.record_error(ErrorCategory.HTTP_RATE_LIMIT)

        snap = t.snapshot()
        assert snap["transitions"] == {
            "discovered->fetching": 2,
            "fetching->parsed": 1,
        }
        assert snap["errors"] == {
            "network": 2,
            "http_rate_limit": 1,
        }

    def test_reset_zeroes_counters(self):
        t = HarvestTelemetry()
        t.record_transition(HarvestState.DISCOVERED, HarvestState.FETCHING)
        t.record_error(ErrorCategory.PARSE)
        assert len(t.snapshot()["transitions"]) > 0
        assert len(t.snapshot()["errors"]) > 0

        t.reset()
        assert t.snapshot() == {"transitions": {}, "errors": {}}

    def test_thread_safety(self):
        t = HarvestTelemetry()
        num_threads = 10
        increments_per_thread = 100

        def worker():
            for _ in range(increments_per_thread):
                t.record_transition(HarvestState.DISCOVERED, HarvestState.FETCHING)
                t.record_error(ErrorCategory.NETWORK)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        snap = t.snapshot()
        assert snap["transitions"]["discovered->fetching"] == num_threads * increments_per_thread
        assert snap["errors"]["network"] == num_threads * increments_per_thread

    def test_summarize_run_aggregates_correctly(self):
        item1 = ItemProgress(
            item_id="item-1",
            state=HarvestState.COMPLETED,
            attempts=1,
            error_category=ErrorCategory.NONE,
            diagnostic="ok 1",
        )
        item2 = ItemProgress(
            item_id="item-2",
            state=HarvestState.COMPLETED_UNCHANGED,
            attempts=0,
            error_category=ErrorCategory.NONE,
            diagnostic="ok 2",
        )
        item3 = ItemProgress(
            item_id="item-3",
            state=HarvestState.FAILED_PERMANENT,
            attempts=3,
            error_category=ErrorCategory.HTTP_NOT_FOUND,
            diagnostic="404 Not Found",
        )
        item4 = ItemProgress(
            item_id="item-4",
            state=HarvestState.FAILED_PERMANENT,
            attempts=3,
            error_category=ErrorCategory.ROBOTS_DENIED,
            diagnostic="Robots disallowed",
        )

        summary = summarize_run([item1, item2, item3, item4])
        assert summary["states"] == {
            "completed": 1,
            "completed_unchanged": 1,
            "failed_permanent": 2,
        }
        assert summary["persisted"] == {
            "review_ready": 1,
            "skipped": 1,
            "failed": 2,
        }
        assert summary["errors"] == {
            "none": 2,
            "http_not_found": 1,
            "robots_denied": 1,
        }

    def test_explicit_leak_test(self):
        distinctive_id = "item-bi-mat-xyz"
        secret_url = "https://example.com/secret/super-confidential-path"
        secret_diagnostic = "Sensitive token leak: sk-secret-12345678901234567890"

        item = ItemProgress(
            item_id=distinctive_id,
            state=HarvestState.FAILED_PERMANENT,
            attempts=3,
            error_category=ErrorCategory.NETWORK,
            diagnostic=secret_diagnostic,
        )

        t = HarvestTelemetry()
        t.record_transition(item.state, HarvestState.FAILED_PERMANENT)
        t.record_error(item.error_category)

        snap_json = json.dumps(t.snapshot())
        summary_json = json.dumps(summarize_run([item]))

        assert distinctive_id not in snap_json
        assert secret_url not in snap_json
        assert secret_diagnostic not in snap_json
        assert "bi-mat" not in snap_json

        assert distinctive_id not in summary_json
        assert secret_url not in summary_json
        assert secret_diagnostic not in summary_json
        assert "bi-mat" not in summary_json


if __name__ == "__main__":
    unittest.main()
