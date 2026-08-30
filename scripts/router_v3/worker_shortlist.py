"""Shortlist worker theo ty le thanh cong — danh sach co chon ra nd."""
from __future__ import annotations

from typing import List, Dict


def top_by_success_rate(snapshot_rows, n=3):
    """snapshot_rows is a list of dicts like scripts.router_v3.registry.
    WorkerRegistry.snapshot() rows (each has "worker_id" and "success_rate"
    keys). Return a list of up to n worker_id strings, sorted by
    success_rate descending; ties broken by worker_id ascending
    (alphabetical). Pure function, standard library only.
    """
    rows = [r for r in snapshot_rows if r.get("worker_id") is not None]
    rows.sort(key=lambda r: (-r["success_rate"], r["worker_id"]))
    return [r["worker_id"] for r in rows[:n]]