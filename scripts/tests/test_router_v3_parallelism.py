"""Bộ điều khiển song song động — Router LTS Phase 11.

Bài quyết định: tier phải LUÔN đồng thuận với `recommended_workers()` đã
đo — không được có một trục riêng mâu thuẫn với bề rộng thật (đã vỡ một
lần khi tier tính theo SỐ NÚT thay vì bề rộng, xem policy.py).
"""
from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import TaskDag, TaskNode
from scripts.router_v3.policy import SpeedMode, phan_loai_co_dag, plan_parallelism


def _n(i, deps=(), **kw):
    kw.setdefault("objective", f"lam {i}")
    return TaskNode(id=i, dependencies=tuple(deps), **kw)


class PhanLoaiCoTest(unittest.TestCase):
    def test_tiny_mot_nut(self):
        d = TaskDag([_n("a")])
        self.assertEqual(phan_loai_co_dag(d), ("tiny", 1))

    def test_normal_ba_nut_song_song(self):
        d = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(3)])
        ten, tran = phan_loai_co_dag(d)
        self.assertEqual(ten, "normal")
        self.assertEqual(tran, 3)

    def test_large_nam_nut_song_song(self):
        d = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(5)])
        self.assertEqual(phan_loai_co_dag(d), ("large", 5))

    def test_mega_sau_nut_song_song(self):
        d = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(6)])
        self.assertEqual(phan_loai_co_dag(d), ("mega", 6))

    def test_tier_khong_bao_gio_mau_thuan_voi_be_rong_do_duoc(self):
        """Bai quyet dinh: trong moi truong hop, tran tier >= be rong that
        trong pham vi tier do — tier chi GAN NHAN, khong bao gio ep thap
        hon phep do that."""
        for so_con in range(0, 10):
            d = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(so_con)])
            rong = d.recommended_workers(ceiling=8)
            ten, tran = phan_loai_co_dag(d, ceiling=8)
            self.assertGreaterEqual(tran, min(rong, 6),
                                    f"so_con={so_con}: tran={tran} < rong={rong}")


class ReserveTest(unittest.TestCase):
    def test_reserve_giu_lai_khe(self):
        d = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(6)])
        n_khong_reserve, _ = plan_parallelism(d, SpeedMode.FAST, reserve=0)
        n_co_reserve, ly_do = plan_parallelism(d, SpeedMode.FAST, reserve=2)
        self.assertEqual(n_co_reserve, n_khong_reserve - 2)
        self.assertIn("giữ lại 2 khe", ly_do)

    def test_reserve_khong_lam_am_so_worker(self):
        d = TaskDag([_n("a")])
        n, _ = plan_parallelism(d, SpeedMode.SAFE, reserve=99)
        self.assertGreaterEqual(n, 1)

    def test_tier_mega_tu_noi_qua_6_khi_be_rong_that_lon_hon(self):
        """`phan_loai_co_dag` — tran tier duoc noi khi be rong THAT vuot 6.
        Day la dieu kien CAN de 7-8 kha thi; dieu kien DU con phu thuoc
        tran cua chinh che do dinh tuyen (xem bai duoi)."""
        d8 = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(8)])
        ten, tran = phan_loai_co_dag(d8, ceiling=8)
        self.assertEqual(ten, "mega")
        self.assertGreaterEqual(tran, 6)

    def test_khong_mode_chuan_nao_vuot_6_du_be_rong_lon_hon(self):
        """Ca ba che do (SAFE/NORMAL/FAST) deu co tran <= 6 — "chi dung
        7-8 khi CO CAN CU" nghia la can ca be rong LAN mot tran cho phep
        rieng, khong tu dong xay ra qua ba che do mac dinh."""
        d8 = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(8)])
        for mode in SpeedMode:
            n, _ = plan_parallelism(d8, mode, ceiling=8)
            self.assertLessEqual(n, 6, f"{mode} vuot 6 ma khong co can cu tuong minh")


if __name__ == "__main__":
    unittest.main()
