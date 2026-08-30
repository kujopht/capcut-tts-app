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
    """Evaluates items to find non-terminal items that are due for harvesting."""

    @staticmethod
    def due(
        items: Iterable[ItemProgress],
        *,
        now: Optional[float] = None,
    ) -> List[str]:
        """Return item_ids of non-terminal items due for execution."""
        curr_now = time.time() if now is None else now
        ra: List[str] = []
        for item in items:
            if item.is_terminal:
                continue
            check_time = next_check_at(item, now=curr_now)
            if check_time <= curr_now:
                ra.append(item.item_id)
        return ra


class HarvestScheduler:
    """Coordinates picking batches of due items with lease acquisition."""

    def __init__(self, lease_table: Optional[LeaseTable] = None) -> None:
        self.lease_table = lease_table if lease_table is not None else LeaseTable()

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
        due_item_ids = Watcher.due(items, now=curr_now)
        claimed: List[str] = []
        for item_id in due_item_ids:
            if len(claimed) >= limit:
                break
            if self.lease_table.claim(item_id, owner, ttl_seconds, now=curr_now):
                claimed.append(item_id)
        return claimed
