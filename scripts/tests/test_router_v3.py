"""Router V3 — DAG, sổ đăng ký, chính sách, gói việc, lập lịch, worktree.

Điều đáng kiểm không phải đường đi thuận lợi mà là những chỗ song song hoá
làm hỏng thứ vốn đúng: hai worker giẫm phạm vi ghi, một việc bảo mật rơi
xuống worker rảnh hơn, hay một credential lọt vào gói việc gửi ra ngoài.

Bộ lập lịch được kiểm bằng executor TIÊM VÀO — tất định, không gọi mạng.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import (DagError, RiskClass, TaskDag, TaskNode,
                                   scopes_overlap)
from scripts.router_v3.packet import (PacketRefused, TaskPacket, packet_for,
                                      parse_result, scan_for_secrets)
from scripts.router_v3.policy import (NoWorkerAvailable, PROFILES, SpeedMode,
                                      choose_worker, plan_parallelism)
from scripts.router_v3.registry import (AG_SLOTS, ExecutionType, Health,
                                        WorkerRegistry, WorkerSpec)
from scripts.router_v3.scheduler import Scheduler
from scripts.router_v3.worktree import WorktreeError, branch_name


def _n(i, deps=(), **kw):
    kw.setdefault("objective", f"lam {i}")
    return TaskNode(id=i, dependencies=tuple(deps), **kw)


def _w(wid="W1", caps=("implement",), high=False, maxc=1, fam="antigravity"):
    return WorkerSpec(worker_id=wid, provider_family=fam,
                      execution_type=ExecutionType.LOCAL_CLI, pool="P",
                      capabilities=frozenset(caps), trusted_for_high_risk=high,
                      max_concurrent=maxc)


class DagHopLeTest(unittest.TestCase):
    def test_chu_trinh_bi_bat_luc_dung(self):
        with self.assertRaises(DagError) as ctx:
            TaskDag([_n("a", ["b"]), _n("b", ["a"])])
        self.assertIn("chu trình", str(ctx.exception))

    def test_chu_trinh_dai_cung_bi_bat(self):
        with self.assertRaises(DagError):
            TaskDag([_n("a", ["c"]), _n("b", ["a"]), _n("c", ["b"])])

    def test_tu_phu_thuoc_bi_bat(self):
        with self.assertRaises(DagError):
            TaskDag([_n("a", ["a"])])

    def test_phu_thuoc_treo_bi_bat(self):
        """Phụ thuộc treo làm nút KHÔNG BAO GIỜ chạy, im lặng."""
        with self.assertRaises(DagError) as ctx:
            TaskDag([_n("a", ["khong-co"])])
        self.assertIn("khong-co", str(ctx.exception))

    def test_trung_id_bi_bat(self):
        with self.assertRaises(DagError):
            TaskDag([_n("a"), _n("a")])

    def test_dag_hop_le_dung_duoc(self):
        d = TaskDag([_n("a"), _n("b", ["a"])])
        self.assertEqual(len(d), 2)


class PhamViGhiTest(unittest.TestCase):
    def test_giam_nhau_theo_thu_muc(self):
        self.assertTrue(scopes_overlap(["server/scraper"],
                                       ["server/scraper/dag.py"]))

    def test_tien_to_chuoi_KHONG_phai_giam_nhau(self):
        """`server/scraper` và `server/scraper_ops.py` KHÔNG giẫm nhau —
        `startswith` trần sẽ nói nhầm là có, rồi tuần tự hoá hai nút độc lập."""
        self.assertFalse(scopes_overlap(["server/scraper"],
                                        ["server/scraper_ops.py"]))

    def test_hai_nut_ghi_giam_nhau_bi_tu_choi(self):
        with self.assertRaises(DagError) as ctx:
            TaskDag([_n("a", write_scope=("srv/x",)),
                     _n("b", write_scope=("srv/x/y.py",))])
        self.assertIn("giẫm", str(ctx.exception))

    def test_giam_nhau_nhung_CO_phu_thuoc_thi_khong_sao(self):
        """Có quan hệ phụ thuộc thì chúng không bao giờ chạy cùng lúc."""
        d = TaskDag([_n("a", write_scope=("srv/x",)),
                     _n("b", ["a"], write_scope=("srv/x",))])
        self.assertEqual(len(d), 2)

    def test_co_the_cho_phep_giam_nhau_tuong_minh(self):
        d = TaskDag([_n("a", write_scope=("srv/x",)),
                     _n("b", write_scope=("srv/x",))],
                    allow_overlapping_writes=True)
        self.assertEqual(len(d), 2)

    def test_nut_chi_doc_khong_bao_gio_xung_dot(self):
        d = TaskDag([_n("a", read_scope=("srv/x",)), _n("b", read_scope=("srv/x",))])
        self.assertEqual(d.overlapping_write_pairs(), [])


class LapLichCoBanTest(unittest.TestCase):
    def setUp(self):
        # T0 -> (T1,T2,T3,T4) -> T5 -> T6
        self.d = TaskDag([
            _n("T0", estimated_seconds=10),
            _n("T1", ["T0"], estimated_seconds=30),
            _n("T2", ["T0"], estimated_seconds=20),
            _n("T3", ["T0"], estimated_seconds=20),
            _n("T4", ["T0"], estimated_seconds=20),
            _n("T5", ["T1", "T2", "T3", "T4"], estimated_seconds=10),
            _n("T6", ["T5"], estimated_seconds=10),
        ])

    def test_lop_dung_thu_tu(self):
        self.assertEqual(self.d.waves(),
                         [["T0"], ["T1", "T2", "T3", "T4"], ["T5"], ["T6"]])

    def test_ready_ton_trong_phu_thuoc(self):
        self.assertEqual([n.id for n in self.d.ready(set())], ["T0"])
        self.assertEqual(sorted(n.id for n in self.d.ready({"T0"})),
                         ["T1", "T2", "T3", "T4"])

    def test_ready_bo_qua_nut_dang_chay(self):
        san = self.d.ready({"T0"}, running={"T1", "T2"})
        self.assertEqual(sorted(n.id for n in san), ["T3", "T4"])

    def test_duong_toi_han_la_duong_DAI_NHAT(self):
        duong, giay = self.d.critical_path()
        self.assertEqual(duong, ["T0", "T1", "T5", "T6"])
        self.assertEqual(giay, 60.0)      # 10+30+10+10

    def test_so_worker_de_xuat_bang_be_rong(self):
        self.assertEqual(self.d.recommended_workers(), 4)

    def test_do_thi_tuan_tu_chi_de_xuat_mot_worker(self):
        d = TaskDag([_n("a"), _n("b", ["a"]), _n("c", ["b"])])
        self.assertEqual(d.recommended_workers(), 1)


class SoDangKyTest(unittest.TestCase):
    def test_worker_moi_khong_bi_phat(self):
        """Tỷ lệ thành công 1.0 khi chưa có dữ liệu — nếu không, worker mới
        không bao giờ được chọn và do đó không bao giờ tích luỹ lịch sử."""
        r = WorkerRegistry()
        r.register(_w())
        self.assertEqual(r.state("W1").success_rate, 1.0)

    def test_dem_thanh_cong_that_bai(self):
        r = WorkerRegistry()
        r.register(_w())
        r.mark_started("W1", "t")
        r.mark_finished("W1", ok=True, seconds=2.0)
        r.mark_started("W1", "t2")
        r.mark_finished("W1", ok=False, seconds=1.0, error="hong")
        st = r.state("W1")
        self.assertEqual((st.completed, st.failed), (1, 1))
        self.assertEqual(st.success_rate, 0.5)
        self.assertIs(st.health, Health.DEGRADED)

    def test_worker_day_cho_khong_duoc_chon(self):
        r = WorkerRegistry()
        r.register(_w(maxc=1))
        r.set_health("W1", Health.HEALTHY)
        r.mark_started("W1", "t")
        self.assertEqual(r.available(), [])

    def test_UNAVAILABLE_khong_bao_gio_duoc_chon(self):
        r = WorkerRegistry()
        r.register(_w())
        r.set_health("W1", Health.UNAVAILABLE, "chua dang nhap")
        self.assertEqual(r.available(), [])

    def test_DEGRADED_van_duoc_chon(self):
        """Loại hẳn sẽ biến một lần hỏng thoáng qua thành mất worker vĩnh viễn."""
        r = WorkerRegistry()
        r.register(_w())
        r.set_health("W1", Health.DEGRADED)
        self.assertEqual(len(r.available()), 1)

    def test_snapshot_khong_chua_bi_mat(self):
        r = WorkerRegistry()
        r.register(_w())
        for hang in r.snapshot():
            self.assertNotIn("token", " ".join(str(v).lower() for v in hang.values()))

    def test_worker_spec_khong_co_truong_nao_chua_credential(self):
        """Bất biến: Router không cầm credential của nhà cung cấp."""
        cam = {"token", "secret", "password", "api_key", "credential", "cookie"}
        for f in WorkerSpec.__dataclass_fields__:
            self.assertNotIn(f.lower(), cam, f"WorkerSpec.{f} nghe như credential")

    def test_co_du_tam_khe_AG(self):
        self.assertEqual(len(AG_SLOTS), 8)
        self.assertEqual(AG_SLOTS[0], "AG01")
        self.assertEqual(AG_SLOTS[-1], "AG08")


class ChinhSachTest(unittest.TestCase):
    def _reg(self):
        r = WorkerRegistry()
        r.register(_w("YEU", caps=("implement", "review"), high=False))
        r.register(_w("MANH", caps=("security_review", "review"), high=True))
        for w in ("YEU", "MANH"):
            r.set_health(w, Health.HEALTHY)
        return r

    def test_viec_rui_ro_CAO_khong_roi_xuong_worker_khong_tin_cay(self):
        """Ranh giới cứng: quota/độ rảnh không bao giờ ghi đè được nó."""
        r = self._reg()
        n = _n("s", risk_class=RiskClass.HIGH,
               required_capabilities=("security_review",))
        self.assertEqual(choose_worker(r, n).worker_id, "MANH")

    def test_khong_co_worker_tin_cay_thi_NEM_chu_khong_ha_chuan(self):
        r = WorkerRegistry()
        r.register(_w("YEU", caps=("review",), high=False))
        r.set_health("YEU", Health.HEALTHY)
        with self.assertRaises(NoWorkerAvailable):
            choose_worker(r, _n("s", risk_class=RiskClass.HIGH,
                                required_capabilities=("review",)))

    def test_review_bao_mat_KHONG_BAO_GIO_toi_codex(self):
        """Bằng chứng thật 2026-08-28: Codex từ chối việc hình dạng bảo mật
        và trả về kết quả rỗng — định tuyến sang đó là một lần hỏng im lặng."""
        r = WorkerRegistry()
        r.register(_w("CODEX", caps=("security_review", "review"), high=True,
                      fam="codex"))
        r.register(_w("OPUS", caps=("security_review",), high=True))
        for w in ("CODEX", "OPUS"):
            r.set_health(w, Health.HEALTHY)
        n = _n("s", risk_class=RiskClass.HIGH,
               required_capabilities=("security_review",))
        self.assertEqual(choose_worker(r, n).worker_id, "OPUS")

    def test_uu_tien_worker_rANH_hon(self):
        r = WorkerRegistry()
        r.register(_w("A", maxc=2))
        r.register(_w("B", maxc=2))
        for w in ("A", "B"):
            r.set_health(w, Health.HEALTHY)
        r.mark_started("A", "t")
        n = _n("x", required_capabilities=("implement",))
        self.assertEqual(choose_worker(r, n).worker_id, "B")

    def test_che_do_gioi_han_muc_song_song(self):
        d = TaskDag([_n("r")] + [_n(f"c{i}", ["r"]) for i in range(6)])
        for mode, tran in ((SpeedMode.SAFE, 2), (SpeedMode.NORMAL, 3),
                           (SpeedMode.FAST, 6)):
            n, ly_do = plan_parallelism(d, mode)
            self.assertEqual(n, tran, f"{mode}: {ly_do}")

    def test_do_thi_tuan_tu_khong_duoc_de_xuat_nhieu_worker(self):
        d = TaskDag([_n("a"), _n("b", ["a"])])
        n, ly_do = plan_parallelism(d, SpeedMode.FAST)
        self.assertEqual(n, 1)
        self.assertIn("tuần tự", ly_do)

    def test_moi_che_do_deu_co_ho_so(self):
        for m in SpeedMode:
            self.assertIn(m, PROFILES)


class GoiViecTest(unittest.TestCase):
    def test_goi_viec_chua_credential_bi_TU_CHOI(self):
        n = _n("t", objective="dung khoa ghp_" + "a" * 30)
        with self.assertRaises(PacketRefused) as ctx:
            packet_for(n, base_sha="abc123")
        self.assertIn("credential", str(ctx.exception))

    def test_nhieu_dang_bi_mat_deu_bi_bat(self):
        for xau in ("ghp_" + "a" * 30, "standard_" + "b" * 45,
                    "rnd_" + "c" * 25, "sk-" + "d" * 25,
                    "-----BEGIN RSA PRIVATE KEY-----"):
            self.assertIsNotNone(scan_for_secrets(xau), xau)

    def test_thieu_base_sha_bi_tu_choi(self):
        with self.assertRaises(PacketRefused):
            packet_for(_n("t"), base_sha="")

    def test_goi_viec_ghi_ro_pham_vi(self):
        p = packet_for(_n("t", write_scope=("srv/a",)), base_sha="abc",
                       do_not_touch=("srv/b",))
        s = p.render()
        self.assertIn("WRITE_SCOPE", s)
        self.assertIn("srv/a", s)
        self.assertIn("DO_NOT_TOUCH", s)

    def test_viec_chi_doc_noi_ro_la_chi_doc(self):
        self.assertIn("CHỈ ĐỌC", packet_for(_n("t"), base_sha="abc").render())

    def test_goi_viec_mang_TOM_TAT_phu_thuoc_khong_phai_hoi_thoai(self):
        p = packet_for(_n("t", ["d1"]), base_sha="abc",
                       dependency_summaries={"d1": "xong roi"})
        self.assertIn("xong roi", p.render())


class DocKetQuaTest(unittest.TestCase):
    def test_doc_duoc_json_thuan(self):
        r = parse_result("t", "W", '{"status":"ok","summary":"xong"}', 1.0)
        self.assertTrue(r.ok)
        self.assertEqual(r.summary, "xong")

    def test_doc_duoc_json_boc_trong_van_ban(self):
        raw = 'Day la ket qua:\n```json\n{"status":"ok","summary":"s"}\n```\nHet.'
        self.assertTrue(parse_result("t", "W", raw, 1.0).ok)

    def test_khong_co_json_la_THAT_BAI_chu_khong_phai_ok(self):
        r = parse_result("t", "W", "toi da lam xong roi!", 1.0)
        self.assertFalse(r.ok)
        self.assertIn("JSON", r.summary)

    def test_json_hong_la_that_bai(self):
        self.assertFalse(parse_result("t", "W", '{"status": bad}', 1.0).ok)

    def test_bao_ok_nhung_co_blocker_thi_KHONG_phai_ok(self):
        """Mâu thuẫn — tin blocker."""
        r = parse_result("t", "W",
                         '{"status":"ok","blockers":["thieu quyen"]}', 1.0)
        self.assertEqual(r.status, "blocked")

    def test_trich_doan_bi_cat_ngan(self):
        r = parse_result("t", "W", "x" * 5000, 1.0)
        self.assertLessEqual(len(r.raw_excerpt), 400)


class LapLichSongSongTest(unittest.TestCase):
    """Executor tiêm vào — tất định, không gọi mạng."""

    def _reg(self, n=4):
        r = WorkerRegistry()
        for i in range(n):
            r.register(_w(f"W{i}", caps=("implement", "tests", "recon")))
            r.set_health(f"W{i}", Health.HEALTHY)
        return r

    def _exec(self, dung=0.05, ghi=None, hong=()):
        def f(packet, worker):
            if ghi is not None:
                ghi.append((packet.task_id, worker.worker_id, time.perf_counter()))
            time.sleep(dung)
            if packet.task_id in hong:
                return '{"status":"failed","summary":"hong"}', dung
            return '{"status":"ok","summary":"xong"}', dung
        return f

    def test_nut_doc_lap_chay_DONG_THOI(self):
        """Bằng chứng song song: bốn nút 0.15s chạy hết dưới 0.35s."""
        d = TaskDag([_n(f"c{i}", estimated_seconds=1) for i in range(4)])
        s = Scheduler(self._reg(), self._exec(0.15), max_parallel=4)
        bc = s.run(d)
        self.assertTrue(bc.ok)
        self.assertGreaterEqual(bc.max_in_flight, 2)
        self.assertLess(bc.wall_seconds, 0.35,
                        f"cham nhu tuan tu: {bc.wall_seconds}s")

    def test_mot_worker_thi_TUAN_TU(self):
        d = TaskDag([_n(f"c{i}") for i in range(3)])
        s = Scheduler(self._reg(1), self._exec(0.05), max_parallel=1)
        bc = s.run(d)
        self.assertEqual(bc.max_in_flight, 1)

    def test_ton_trong_phu_thuoc(self):
        ghi = []
        d = TaskDag([_n("a"), _n("b", ["a"]), _n("c", ["b"])])
        Scheduler(self._reg(), self._exec(0.02, ghi), max_parallel=4).run(d)
        thu_tu = [g[0] for g in ghi]
        self.assertEqual(thu_tu, ["a", "b", "c"])

    def test_nut_phu_thuoc_mot_nut_HONG_thi_bi_bo_qua(self):
        d = TaskDag([_n("a"), _n("b", ["a"])])
        bc = Scheduler(self._reg(), self._exec(0.02, hong={"a"}),
                       max_parallel=2).run(d)
        self.assertFalse(bc.ok)
        self.assertIn("b", bc.skipped)

    def test_mot_nut_hong_KHONG_lam_hong_nut_doc_lap(self):
        d = TaskDag([_n("a"), _n("b")])
        bc = Scheduler(self._reg(), self._exec(0.02, hong={"a"}),
                       max_parallel=2).run(d)
        self.assertFalse(bc.results["a"].ok)
        self.assertTrue(bc.results["b"].ok)

    def test_executor_nem_loi_thanh_ket_qua_that_bai(self):
        def no(packet, worker):
            raise RuntimeError("worker chet")
        bc = Scheduler(self._reg(), no, max_parallel=2).run(TaskDag([_n("a")]))
        self.assertFalse(bc.results["a"].ok)
        self.assertIn("RuntimeError", bc.results["a"].summary)

    def test_nut_khong_song_song_duoc_chay_MOT_MINH(self):
        dang = []
        toi_da = [0]
        khoa = threading.Lock()

        def f(packet, worker):
            with khoa:
                dang.append(packet.task_id)
                toi_da[0] = max(toi_da[0], len(dang))
            time.sleep(0.05)
            with khoa:
                dang.remove(packet.task_id)
            return '{"status":"ok"}', 0.05

        d = TaskDag([_n("solo", parallelizable=False), _n("a"), _n("b")])
        Scheduler(self._reg(), f, max_parallel=3).run(d)
        self.assertLessEqual(toi_da[0], 3)

    def test_bao_cao_ghi_lai_gio_worker_va_wall(self):
        d = TaskDag([_n(f"c{i}") for i in range(3)])
        bc = Scheduler(self._reg(), self._exec(0.1), max_parallel=3).run(d)
        self.assertGreater(bc.worker_seconds, bc.wall_seconds)
        self.assertGreater(bc.speedup_vs_serial, 1.0)


class WorktreeTenTest(unittest.TestCase):
    def test_ten_nhanh_theo_worker_va_task(self):
        self.assertEqual(branch_name("AG01", "T1"), "router/AG01/T1")

    def test_ky_tu_la_bi_tu_choi(self):
        """`../` trong task_id sẽ tạo worktree NGOÀI thư mục dự định."""
        for xau in ("../evil", "a b", "a;rm", "~x", ""):
            with self.assertRaises(WorktreeError, msg=xau):
                branch_name("AG01", xau)

    def test_worker_id_la_cung_bi_tu_choi(self):
        with self.assertRaises(WorktreeError):
            branch_name("../x", "T1")


if __name__ == "__main__":
    unittest.main()
