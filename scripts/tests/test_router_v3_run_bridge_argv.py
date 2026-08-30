"""Nhánh argv an toàn của run_bridge.main — không khởi động worker/cầu nối.

Chỉ phủ nhánh thuần, không tác dụng phụ: khi find_agy() trả None, main()
in thông báo và thoát mã 2 TRƯỚC khi dựng WarmAgyWorker / WorkerBridge.
Không kiểm thử end-to-end (main() sẽ spawn tiến trình thật và block).
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.run_bridge import main


class FindAgyNoneTest(unittest.TestCase):
    def test_khong_co_agy_thoat_2_khong_dung_worker(self):
        buf = io.StringIO()
        with mock.patch("scripts.router_v3.run_bridge.find_agy",
                        return_value=None), \
             mock.patch("scripts.router_v3.run_bridge.WarmAgyWorker") as spy, \
             redirect_stdout(buf):
            rc = main(["--worker-id", "AGTEST"])
        self.assertEqual(rc, 2)
        spy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
