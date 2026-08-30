"""Bản đồ năng lực — kiểm thử Router V3."""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.capability_matrix import matrix
from scripts.router_v3.registry import WorkerRegistry, WorkerSpec, ExecutionType


class CapabilityMatrixTest(unittest.TestCase):
    def _make_spec(self, worker_id, capabilities):
        return WorkerSpec(
            worker_id=worker_id,
            provider_family="test",
            execution_type=ExecutionType.LOCAL_CLI,
            pool="TEST",
            capabilities=frozenset(capabilities),
        )

    def test_basic(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("A", {"recon", "implement"}))
        reg.register(self._make_spec("B", {"implement", "review"}))
        reg.register(self._make_spec("C", {"recon"}))

        result = matrix(reg)
        self.assertEqual(result["recon"], ["A", "C"])
        self.assertEqual(result["implement"], ["A", "B"])
        self.assertEqual(result["review"], ["B"])

    def test_only_declared_capabilities(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("W1", {"tests"}))

        result = matrix(reg)
        self.assertIn("tests", result)
        self.assertNotIn("recon", result)
        self.assertNotIn("frontend", result)

    def test_empty_registry(self):
        reg = WorkerRegistry()
        result = matrix(reg)
        self.assertEqual(result, {})

    def test_overlapping_and_non_overlapping(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("X", {"security_review", "architecture"}))
        reg.register(self._make_spec("Y", {"architecture", "integration"}))
        reg.register(self._make_spec("Z", {"frontend"}))

        result = matrix(reg)
        self.assertEqual(result["security_review"], ["X"])
        self.assertEqual(result["architecture"], ["X", "Y"])
        self.assertEqual(result["integration"], ["Y"])
        self.assertEqual(result["frontend"], ["Z"])

    def test_sorted_order(self):
        reg = WorkerRegistry()
        reg.register(self._make_spec("Z_worker", {"implement"}))
        reg.register(self._make_spec("A_worker", {"implement"}))
        reg.register(self._make_spec("M_worker", {"implement"}))

        result = matrix(reg)
        self.assertEqual(result["implement"], ["A_worker", "M_worker", "Z_worker"])


if __name__ == "__main__":
    unittest.main()
