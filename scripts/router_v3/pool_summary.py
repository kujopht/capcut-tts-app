"""Tóm tắt worker theo pool — Router V3.

Cho `WorkerRegistry`, nhóm worker_id theo tên pool để biết mỗi pool
đang có những worker nào.
"""
from __future__ import annotations

from typing import Dict, List


def by_pool(registry):
    """Take a scripts.router_v3.registry.WorkerRegistry. Returns a dict
    mapping each pool name (registry.spec(worker_id).pool) to a sorted
    list of worker_ids assigned to that pool, using only the public
    registry.ids() and registry.spec(worker_id) API (no private
    attributes). A pool with only one worker still appears with a
    single-element list.
    """
    result: Dict[str, List[str]] = {}
    for wid in registry.ids():
        pool = registry.spec(wid).pool
        result.setdefault(pool, []).append(wid)
    for pool in result:
        result[pool].sort()
    return result
