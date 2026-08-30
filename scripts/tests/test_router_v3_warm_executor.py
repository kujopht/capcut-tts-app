"""Worker ấm làm executor của Scheduler — Router V3.2, Phase 1 + 3.

Không gọi `agy` thật: `WarmAgyWorker` bị thay bằng một bản giả tất định, nên
kiểm được đúng thứ đáng kiểm — tiến trình có được DÙNG LẠI không, hai nút
song song có ghi xen kẽ vào cùng một stdin không, và một nút hỏng có làm sập
cả lượt chạy không.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from unittest import mock

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import TaskDag, TaskNode
from scripts.router_v3.packet import TaskPacket
from scripts.router_v3.registry import (ExecutionType, Health, WorkerRegistry,
                                        WorkerSpec)
from scripts.router_v3.scheduler import Scheduler
from scripts.router_v3.warm_executor import WarmExecutor, family_of
from scripts.router_v3.warm_pool import WarmState


class _WorkerGia:
    """Thay `WarmAgyWorker`. Đếm số lần khởi động để chứng minh dùng lại."""

    def __init__(self, worker_id, **kw):
        self.worker_id = worker_id
        self.cold_starts = 0
        self.cold_start_seconds = 0.0
        self.recycles = []
        self.stats = mock.Mock(turns=0, chars=0, family="")
        self._state = WarmState.COLD
        self.dang_chay = 0
        self.dinh_dong_thoi = 0
        self.hong_voi = kw.pop("hong_voi", set())
        self._khoa = threading.Lock()

    @property
    def state(self):
        return self._state

    def send(self, prompt, family=""):
        from scripts.router_v3.warm_pool import WarmTurn

        if self._state is WarmState.COLD:
            self.cold_starts += 1
            self.cold_start_seconds += 0.05
            self._state = WarmState.WARM_IDLE
        with self._khoa:
            self.dang_chay += 1
            self.dinh_dong_thoi = max(self.dinh_dong_thoi, self.dang_chay)
        time.sleep(0.05)
        with self._khoa:
            self.dang_chay -= 1
        self.stats.turns += 1
        self.stats.family = family
        if any(x in prompt for x in self.hong_voi):
            return WarmTurn(ok=False, error="viec nay hong", seconds=0.05)
        return WarmTurn(ok=True, seconds=0.05,
                        response='{"status":"ok","summary":"xong"}')

    def close(self):
        self._state = WarmState.COLD


def _packet(tid, write=()):
    return TaskPacket(task_id=tid, base_sha="abc123", objective=f"lam {tid}",
                      write_scope=tuple(write))


def _spec(wid):
    return WorkerSpec(worker_id=wid, provider_family="antigravity",
                      execution_type=ExecutionType.LOCAL_CLI, pool="P",
                      capabilities=frozenset({"implement"}), max_concurrent=1)


class HoViecTest(unittest.TestCase):
    def test_hai_tep_cung_thu_muc_la_CUNG_ho_viec(self):
        a = family_of(_packet("a", ["server/scraper/dag.py"]))
        b = family_of(_packet("b", ["server/scraper/policy.py"]))
        self.assertEqual(a, b)

    def test_hai_he_con_KHAC_nhau_la_khac_ho_viec(self):
        a = family_of(_packet("a", ["server/scraper/x.py"]))
        b = family_of(_packet("b", ["web/src/y.tsx"]))
        self.assertNotEqual(a, b)

    def test_khong_co_pham_vi_thi_ho_viec_rong(self):
        self.assertEqual(family_of(_packet("a")), "")

    def test_duong_dan_windows_cung_doc_duoc(self):
        self.assertEqual(family_of(_packet("a", ["server\\scraper\\x.py"])),
                         "server/scraper")


class DungLaiTienTrinhTest(unittest.TestCase):
    """Điểm cốt lõi: KHÔNG dựng tiến trình mới cho mỗi nút."""

    def setUp(self):
        self.patcher = mock.patch(
            "scripts.router_v3.warm_executor.WarmAgyWorker", _WorkerGia)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_nhieu_nut_cung_worker_chi_khoi_dong_MOT_lan(self):
        ex = WarmExecutor(model="m")
        spec = _spec("AG01")
        for i in range(5):
            ex(_packet(f"T{i}", ["server/scraper/x.py"]), spec)
        self.assertEqual(ex.metrics.cold_starts, 1,
                         "phải dùng lại tiến trình, không dựng mới mỗi nút")
        self.assertEqual(ex.metrics.warm_dispatches, 5)
        self.assertEqual(ex.metrics.cold_starts_avoided, 4)

    def test_worker_KHAC_NHAU_co_tien_trinh_rieng(self):
        ex = WarmExecutor(model="m")
        ex(_packet("A", ["server/a.py"]), _spec("AG01"))
        ex(_packet("B", ["server/b.py"]), _spec("AG02"))
        self.assertEqual(ex.metrics.cold_starts, 2)
        self.assertEqual(len(ex.snapshot()), 2)

    def test_nut_hong_KHONG_nem_ma_tra_ket_qua_doc_duoc(self):
        """Một nút hỏng không được làm sập cả lượt chạy."""
        from scripts.router_v3.packet import parse_result

        ex = WarmExecutor(model="m")
        with mock.patch("scripts.router_v3.warm_executor.WarmAgyWorker",
                        lambda wid, **kw: _WorkerGia(wid, hong_voi={"T9"})):
            raw, giay = ex(_packet("T9", ["server/x.py"]), _spec("AG01"))
        kq = parse_result("T9", "AG01", raw, giay)
        self.assertFalse(kq.ok)
        self.assertIn("hong", kq.summary)

    def test_snapshot_khong_lo_noi_dung_viec(self):
        ex = WarmExecutor(model="m")
        ex(_packet("A", ["server/a.py"]), _spec("AG01"))
        for hang in ex.snapshot():
            self.assertNotIn("prompt", hang)
            self.assertNotIn("response", hang)


class AnToanLuongTest(unittest.TestCase):
    def test_MOT_worker_khong_bao_gio_chay_hai_luot_cung_luc(self):
        """Một tiến trình `agy` là MỘT hội thoại nối tiếp. Hai luồng ghi xen
        kẽ vào cùng stdin làm cả hai kết quả hỏng theo cách rất khó lần."""
        gia = _WorkerGia("AG01")
        with mock.patch("scripts.router_v3.warm_executor.WarmAgyWorker",
                        lambda wid, **kw: gia):
            ex = WarmExecutor(model="m")
            spec = _spec("AG01")
            luong = [threading.Thread(
                target=ex, args=(_packet(f"T{i}", ["server/x.py"]), spec))
                for i in range(4)]
            for t in luong:
                t.start()
            for t in luong:
                t.join()
        self.assertEqual(gia.dinh_dong_thoi, 1,
                         f"có {gia.dinh_dong_thoi} lượt chạy đồng thời trên "
                         f"cùng một tiến trình")

    def test_hai_worker_KHAC_nhau_van_chay_song_song(self):
        """Khoá là THEO TỪNG worker, không phải khoá chung — nếu không, bể ấm
        sẽ tuần tự hoá mọi thứ và xoá sạch lợi ích của song song."""
        gia = {}

        def tao(wid, **kw):
            gia[wid] = gia.get(wid) or _WorkerGia(wid)
            return gia[wid]

        with mock.patch("scripts.router_v3.warm_executor.WarmAgyWorker", tao):
            ex = WarmExecutor(model="m")
            t0 = time.perf_counter()
            luong = [threading.Thread(
                target=ex, args=(_packet(f"T{i}", ["server/x.py"]), _spec(f"AG{i}")))
                for i in range(3)]
            for t in luong:
                t.start()
            for t in luong:
                t.join()
            mat = time.perf_counter() - t0
        self.assertLess(mat, 0.14, f"bị tuần tự hoá: {mat:.3f}s cho 3 lượt 0.05s")


class NoiVaoSchedulerTest(unittest.TestCase):
    def setUp(self):
        self.patcher = mock.patch(
            "scripts.router_v3.warm_executor.WarmAgyWorker", _WorkerGia)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_scheduler_chay_duoc_voi_executor_am(self):
        reg = WorkerRegistry()
        for wid in ("AG01", "AG02"):
            reg.register(_spec(wid))
            reg.set_health(wid, Health.HEALTHY)
        ex = WarmExecutor(model="m")
        dag = TaskDag([TaskNode(id=f"T{i}", objective="x",
                                required_capabilities=("implement",))
                       for i in range(4)])
        bc = Scheduler(reg, ex, max_parallel=2, node_timeout=30).run(dag)
        self.assertTrue(bc.ok, [r.summary for r in bc.results.values()])
        self.assertEqual(len(bc.results), 4)
        # Bon nut, hai worker -> nhieu nhat hai lan khoi dong lanh.
        self.assertLessEqual(ex.metrics.cold_starts, 2)
        self.assertGreaterEqual(ex.metrics.cold_starts_avoided, 2)


if __name__ == "__main__":
    unittest.main()


class BangDieuKhienTest(unittest.TestCase):
    def _snap(self, **kw):
        base = {"worker_id": "AG01", "state": "warm_idle", "turns": 3,
                "context_chars": 1000, "family": "server/scraper", "recycles": 0}
        base.update(kw)
        return [base]

    def test_hien_trang_thai_am(self):
        from scripts.router_v3.dashboard import render_v32

        s = render_v32(self._snap(), parallelism=2, done=3, total=6)
        self.assertIn("ROUTER V3.2", s)
        self.assertIn("WARM-IDLE", s)
        self.assertIn("server/scraper", s)
        self.assertIn("3/6", s)

    def test_phan_loai_do_phinh_ngu_canh(self):
        from scripts.router_v3.dashboard import render_v32

        self.assertIn("context=low", render_v32(self._snap(context_chars=100)))
        self.assertIn("context=med", render_v32(self._snap(context_chars=30_000)))
        self.assertIn("context=HIGH", render_v32(self._snap(context_chars=90_000)))

    def test_hien_worker_UNAVAILABLE_tu_so_dang_ky(self):
        from scripts.router_v3.dashboard import render_v32
        from scripts.router_v3.registry import default_registry

        s = render_v32(self._snap(), registry=default_registry(probe=False))
        self.assertIn("AG03", s)

    def test_hien_so_lan_TRANH_DUOC_khoi_dong(self):
        """Đây mới là con số nói lên giá trị của bể ấm, không phải tổng lượt."""
        from scripts.router_v3.dashboard import render_v32
        from scripts.router_v3.warm_executor import WarmMetrics

        m = WarmMetrics(cold_starts=1, warm_dispatches=6, warm_seconds=12.0)
        s = render_v32(self._snap(), metrics=m)
        self.assertIn("Tranh duoc khoi dong  : 5", s)

    def test_bang_KHONG_lo_noi_dung_hay_token(self):
        from scripts.router_v3.dashboard import render_v32

        s = render_v32(self._snap()).lower()
        for cam in ("prompt", "token", "response", "oauth", "password"):
            self.assertNotIn(cam, s)
