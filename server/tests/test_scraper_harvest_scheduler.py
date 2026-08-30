"""Tests for Story Harvester V4 Phase 7 Scheduler Layer (harvest_scheduler.py)."""
import unittest

from server.scraper.harvest_scheduler import (
    Lease,
    LeaseTable,
    next_check_at,
    Watcher,
    HarvestScheduler,
)
from server.scraper.harvest_state import (
    HarvestState,
    ItemProgress,
    ErrorCategory,
)


class HarvestSchedulerTest(unittest.TestCase):
    def test_lease_claim_conflict_between_two_owners(self):
        """Chiem xung dot (hai owner, mot thang)."""
        table = LeaseTable()
        now = 1000.0

        # Owner 1 claims item_1 for 60s -> succeeds
        assert table.claim("item_1", "worker_1", 60.0, now=now) is True
        assert table.is_leased("item_1", now=now) is True

        # Owner 2 tries to claim item_1 -> fails due to active lease
        assert table.claim("item_1", "worker_2", 60.0, now=now + 10.0) is False

        # Owner 1 re-claims / renews -> succeeds
        assert table.claim("item_1", "worker_1", 60.0, now=now + 20.0) is True

        # Release by wrong owner does nothing
        table.release("item_1", "worker_2")
        assert table.is_leased("item_1", now=now + 20.0) is True

        # Release by true owner frees the lease
        table.release("item_1", "worker_1")
        assert table.is_leased("item_1", now=now + 20.0) is False

        # Owner 2 can now claim it
        assert table.claim("item_1", "worker_2", 60.0, now=now + 20.0) is True

    def test_lease_reclaim_after_expiry(self):
        """Het han cho chiem lai."""
        table = LeaseTable()
        now = 1000.0

        # Owner 1 claims item_1 for 30s
        assert table.claim("item_1", "worker_1", 30.0, now=now) is True
        assert table.is_leased("item_1", now=now + 10.0) is True

        # At now + 35s, lease has expired
        assert table.is_leased("item_1", now=now + 35.0) is False

        # Owner 2 can claim after expiry
        assert table.claim("item_1", "worker_2", 30.0, now=now + 35.0) is True
        assert table.is_leased("item_1", now=now + 35.0) is True

    def test_backoff_grows_with_attempts(self):
        """Backoff tang theo attempts."""
        now = 1000.0
        base = 30.0
        max_d = 3600.0

        # attempts == 0 -> due immediately (returns now)
        p0 = ItemProgress(item_id="it_0", attempts=0, max_attempts=5)
        assert next_check_at(p0, base_delay_seconds=base, max_delay_seconds=max_d, now=now) == now

        # attempts == 1 -> base * 2^1 = 60s
        p1 = ItemProgress(item_id="it_1", attempts=1, max_attempts=5)
        assert next_check_at(p1, base_delay_seconds=base, max_delay_seconds=max_d, now=now) == now + 60.0

        # attempts == 2 -> base * 2^2 = 120s
        p2 = ItemProgress(item_id="it_2", attempts=2, max_attempts=5)
        assert next_check_at(p2, base_delay_seconds=base, max_delay_seconds=max_d, now=now) == now + 120.0

        # attempts == 3 -> base * 2^3 = 240s
        p3 = ItemProgress(item_id="it_3", attempts=3, max_attempts=5)
        assert next_check_at(p3, base_delay_seconds=base, max_delay_seconds=max_d, now=now) == now + 240.0

        # large attempts capped at max_delay
        p_high = ItemProgress(item_id="it_h", attempts=10, max_attempts=10)
        assert next_check_at(p_high, base_delay_seconds=base, max_delay_seconds=300.0, now=now) == now + 300.0

    def test_terminal_items_never_returned(self):
        """Item KET khong bao gio duoc tra ve."""
        now = 1000.0
        items = [
            ItemProgress(item_id="completed", state=HarvestState.COMPLETED),
            ItemProgress(item_id="unchanged", state=HarvestState.COMPLETED_UNCHANGED),
            ItemProgress(item_id="perm_fail", state=HarvestState.FAILED_PERMANENT, attempts=3, max_attempts=3),
            ItemProgress(item_id="cancelled", state=HarvestState.CANCELLED),
            ItemProgress(item_id="active", state=HarvestState.DISCOVERED),
        ]

        due_items = Watcher().due(items, now=now)
        assert due_items == ["active"]
        assert "completed" not in due_items
        assert "unchanged" not in due_items
        assert "perm_fail" not in due_items
        assert "cancelled" not in due_items

    def test_due_skips_not_yet_due_items(self):
        """due() bo qua item chua den han."""
        w = Watcher()
        it_0 = ItemProgress(item_id="it_0", attempts=0)
        it_1 = ItemProgress(item_id="it_1", attempts=1)

        # When evaluated at now = 1000.0, it_0 is due, it_1 is not yet.
        assert w.due([it_0, it_1], now=1000.0) == ["it_0"]

    def test_backed_off_item_eventually_becomes_due(self):
        """Bai quyet dinh: mot item bi backoff PHAI den han lai sau du thoi
        gian, khong duoc mai mai khong den han (bug that: bai kiem cu chi
        kiem 'chua den han NGAY', khong bao gio kiem 'den han SAU do')."""
        w = Watcher()
        it_1 = ItemProgress(item_id="it_1", attempts=1)  # backoff = 60s tu now

        # Cung mot Watcher, hai lan goi cach nhau du 60s -> phai neo tai lan
        # dau (now=1000.0) roi den han o lan hai (now=1060.0).
        assert w.due([it_1], now=1000.0) == []
        assert w.due([it_1], now=1059.9) == []
        assert w.due([it_1], now=1060.0) == ["it_1"]

    def test_new_attempt_recomputes_a_fresh_anchor(self):
        """attempts tang (that bai moi) phai neo lai backoff moi, khong dung
        anchor cu cua attempts truoc."""
        w = Watcher()
        it = ItemProgress(item_id="it", attempts=1)
        assert w.due([it], now=1000.0) == []
        assert w.due([it], now=1060.0) == ["it"]

        # That bai lai -> attempts=2, backoff moi (120s) neo tu THOI DIEM
        # NAY (1060.0), khong phai tu lan neo truoc.
        it2 = ItemProgress(item_id="it", attempts=2)
        assert w.due([it2], now=1060.0) == []
        assert w.due([it2], now=1179.9) == []
        assert w.due([it2], now=1180.0) == ["it"]

    def test_harvest_scheduler_pick_batch(self):
        """Scheduler picks up to limit, claims leases, and skips held items."""
        table = LeaseTable()
        scheduler = HarvestScheduler(lease_table=table)
        now = 1000.0

        items = [
            ItemProgress(item_id="it_1", attempts=0),
            ItemProgress(item_id="it_2", attempts=0),
            ItemProgress(item_id="it_3", attempts=0),
            ItemProgress(item_id="it_4", state=HarvestState.COMPLETED),
        ]

        # Pre-lease it_2 to worker_other
        table.claim("it_2", "worker_other", 60.0, now=now)

        # worker_main picks with limit 2
        # it_1 is claimed, it_2 is skipped, it_3 is claimed, limit 2 reached
        batch = scheduler.pick_batch(items, "worker_main", limit=2, ttl_seconds=60.0, now=now)
        assert batch == ["it_1", "it_3"]

        # Verify table state
        assert table.is_leased("it_1", now=now) is True
        assert table.is_leased("it_2", now=now) is True
        assert table.is_leased("it_3", now=now) is True
        assert table.is_leased("it_4", now=now) is False


if __name__ == "__main__":
    unittest.main()
