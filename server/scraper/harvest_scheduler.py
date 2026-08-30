"""Scheduler layer for Story Harvester V4 (Phase 7).

Provides lease management, exponential backoff computation, due watcher,
and batch scheduler for harvesting items without races or stale worker overwrites.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from server.scraper.harvest_state import ItemProgress


@dataclass
class Lease:
    """Lease representing temporary ownership of an item by a worker."""

    item_id: str
    owner: str
    expires_at: float


class LeaseTable:
    """Thread-safe, in-memory table tracking active leases."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._leases: Dict[str, Lease] = {}

    def claim(
        self,
        item_id: str,
        owner: str,
        ttl_seconds: float,
        *,
        now: Optional[float] = None,
    ) -> bool:
        """Claim or renew a lease for an item.

        Returns True if unclaimed, expired, or already held by this same owner.
        Returns False if held by a different owner and not yet expired.
        """
        curr_now = time.time() if now is None else now
        with self._lock:
            existing = self._leases.get(item_id)
            if existing is not None and existing.expires_at > curr_now:
                if existing.owner != owner:
                    return False
            self._leases[item_id] = Lease(
                item_id=item_id,
                owner=owner,
                expires_at=curr_now + ttl_seconds,
            )
            return True

    def release(self, item_id: str, owner: str) -> None:
        """Release a lease if owned by the specified owner. No-op otherwise."""
        with self._lock:
            existing = self._leases.get(item_id)
            if existing is not None and existing.owner == owner:
                del self._leases[item_id]

    def is_leased(self, item_id: str, *, now: Optional[float] = None) -> bool:
        """Check whether an item is actively leased and unexpired."""
        curr_now = time.time() if now is None else now
        with self._lock:
            existing = self._leases.get(item_id)
            if existing is None:
                return False
            return existing.expires_at > curr_now


def next_check_at(
    progress: ItemProgress,
    *,
    base_delay_seconds: float = 30.0,
    max_delay_seconds: float = 3600.0,
    now: Optional[float] = None,
) -> float:
    """Compute the timestamp when an item should next be checked.

    Applies exponential backoff on progress.attempts: min(max_delay, base_delay * 2**attempts).
    If attempts == 0, returns now (due immediately).
    """
    curr_now = time.time() if now is None else now
    if progress.attempts == 0:
        return curr_now
    delay = min(max_delay_seconds, base_delay_seconds * (2 ** progress.attempts))
    return curr_now + delay


class Watcher:
    """Evaluates items to find non-terminal items that are due for harvesting.

    STATEFUL BY NECESSITY: `next_check_at(item, now=X)` always returns
    `X + delay`, so comparing that against the SAME `X` (`check_time <=
    curr_now`) is always False for any item with a real delay — a
    backed-off item could never become due again on a later call. There is
    no persisted "when did this item last fail" field on `ItemProgress`
    (out of scope for this phase, and it's an immutable dataclass anyway),
    so the anchor has to live HERE: the first time an item is seen at a
    given `attempts` count, its due time is computed and cached; later
    calls compare the CURRENT `now` against that cached anchor instead of
    recomputing it. Confirmed as a real bug by independent review
    (2026-08-30) before this fix existed — the original static, stateless
    version passed all 6 tests because none of them checked "due after
    enough time actually passes," only "not due immediately."
    """

    def __init__(self) -> None:
        # item_id -> (attempts at which this anchor was computed, due_at).
        # Keyed by attempts too: a NEW failure (attempts bumped) needs a
        # FRESH anchor, not the stale one from the previous attempt.
        self._anchor: Dict[str, tuple] = {}

    def due(
        self,
        items: Iterable[ItemProgress],
        *,
        now: Optional[float] = None,
    ) -> List[str]:
        """Return item_ids of non-terminal items due for execution."""
        curr_now = time.time() if now is None else now
        con_song: set = set()
        ra: List[str] = []
        for item in items:
            con_song.add(item.item_id)
            if item.is_terminal:
                self._anchor.pop(item.item_id, None)
                continue
            if item.attempts == 0:
                ra.append(item.item_id)
                self._anchor.pop(item.item_id, None)
                continue
            cache = self._anchor.get(item.item_id)
            if cache is None or cache[0] != item.attempts:
                due_at = next_check_at(item, now=curr_now)
                self._anchor[item.item_id] = (item.attempts, due_at)
            else:
                due_at = cache[1]
            if curr_now >= due_at:
                ra.append(item.item_id)
        # Prune items no longer in the input — otherwise an item that
        # disappears (persisted/purged elsewhere) leaks its anchor forever.
        for iid in list(self._anchor):
            if iid not in con_song:
                self._anchor.pop(iid, None)
        return ra


class HarvestScheduler:
    """Coordinates picking batches of due items with lease acquisition.

    NOT safe to call `pick_batch` concurrently from multiple threads under
    the SAME `owner` string: `LeaseTable.claim` deliberately lets an owner
    renew its own lease (needed for heartbeating a long-running claim), so
    two concurrent same-owner calls could both successfully claim and
    return overlapping item_ids. Call it from a single loop per owner —
    that's the only caller shape this phase's foundation code assumes.
    """

    def __init__(self, lease_table: Optional[LeaseTable] = None) -> None:
        self.lease_table = lease_table if lease_table is not None else LeaseTable()
        self.watcher = Watcher()

    def pick_batch(
        self,
        items: Iterable[ItemProgress],
        owner: str,
        *,
        limit: int,
        ttl_seconds: float = 300.0,
        now: Optional[float] = None,
    ) -> List[str]:
        """Pick up to limit due items, claiming leases for them.

        Skips items currently held by a different unexpired lease.
        Returns only the list of successfully claimed item_ids.
        """
        curr_now = time.time() if now is None else now
        due_item_ids = self.watcher.due(items, now=curr_now)
        claimed: List[str] = []
        for item_id in due_item_ids:
            if len(claimed) >= limit:
                break
            if self.lease_table.claim(item_id, owner, ttl_seconds, now=curr_now):
                claimed.append(item_id)
        return claimed
