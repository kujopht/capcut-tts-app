"""Bản đồ năng lực — Router V3.

Cho `WorkerRegistry`, đảo ngược quan hệ capability → workers để biết
mỗi năng lực có thể giao cho worker nào.
"""
from __future__ import annotations

from typing import Dict, List


def matrix(registry) -> Dict[str, List[str]]:
    """Take a scripts.router_v3.registry.WorkerRegistry. Returns a dict
    mapping each capability string to a sorted list of worker_ids that
    declare it, using registry.ids() and registry.spec(worker_id).capabilities
    (public API only). A capability with no workers maps to an empty list;
    only include capabilities that appear on at least one registered
    worker (do not enumerate the full registry.CAPABILITIES set).
    """
    result: Dict[str, List[str]] = {}
    for wid in registry.ids():
        for cap in registry.spec(wid).capabilities:
            result.setdefault(cap, []).append(wid)
    for cap in result:
        result[cap].sort()
    return result
