"""Tóm tắt worker theo pool — kiểm thử Router V3."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.pool_summary import by_pool
from scripts.router_v3.registry import ExecutionType, WorkerRegistry, WorkerSpec


class PoolSummaryTest(unittest.TestCase):
    def _make_spec(self, worker_id, pool):
        return WorkerSpec(
            worker_id=worker_id,
            provider_family="test",
            execution_type=ExecutionType.LOCAL_CLI,
            pool=pool,
            capabilities=frozenset({"implement"}),
        )

    def test_groups_worker_ids_by_pool(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("Z1", "FLASH"))
        reg.register(self._make_spec("A1", "FLASH"))
        reg.register(self._make_spec("B1", "PRO"))
        reg.register(self._make_spec("C1", "SONNET"))

        result = by_pool(reg)
        self.assertEqual(result["FLASH"], ["A1", "Z1"])
        self.assertEqual(result["PRO"], ["B1"])
        self.assertEqual(result["SONNET"], ["C1"])
        self.assertEqual(set(result), {"FLASH", "PRO", "SONNET"})

    def test_single_worker_pool_is_single_element_list(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("ONLY", "ALONE"))
        result = by_pool(reg)
        self.assertEqual(result, {"ALONE": ["ONLY"]})

    def test_empty_registry(self):
        reg = WorkerRegistry()
        self.assertEqual(by_pool(reg), {})

    def test_sorted_within_pool(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("m", "P"))
        reg.register(self._make_spec("a", "P"))
        reg.register(self._make_spec("z", "P"))
        self.assertEqual(by_pool(reg)["P"], ["a", "m", "z"])


if __name__ == "__main__":
    unittest.main()
