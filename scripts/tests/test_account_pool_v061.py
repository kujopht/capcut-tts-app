# -*- coding: utf-8 -*-
"""V0.6.1 — KIỂM TOÁN BỂ TÀI KHOẢN ANTIGRAVITY (Part C).

Số tài khoản được CHỨNG MINH từ sổ đăng ký (`fabric.json` + mẫu khe AG +
lớp phủ launcher), không giả định "8". Mọi bài dùng fabric THẬT của kho
nhưng lớp phủ launcher được GIẢ (`profile_ton_tai` → True cho mọi khe) để
bài chạy được ở CI không có `accN.bin`; không đọc credential, không sinh
`agy`, không chạm mạng.

Chứng minh:
  * Router thấy N khe AG (N từ `AG_SLOTS`), mỗi khe một `auth_profile`
    RIÊNG, tổng chỗ = Σ concurrency.
  * Bộ lập lịch chọn được khe NGOÀI AG01 khi AG01 đầy; failover bỏ khe hỏng;
    một khe OFFLINE/COOLDOWN không làm sập nhà cung cấp; giao đồng thời tôn
    trọng đúng sức chứa từng khe; cooldown có bậc và tự hết.
  * Leader và worker dùng CÙNG bể (Leader ghim AG01) — và từ V0.6.1 chỗ
    Leader chiếm HIỆN RA với bộ lập lịch.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.router_v4 import fabric_config as FC                         # noqa: E402
from scripts.router_v4.capabilities import Requirements                   # noqa: E402
from scripts.router_v4.contract import TaskContract                       # noqa: E402
from scripts.router_v4.runtime import (BACKOFF_COOLDOWN, NGUONG_COOLDOWN,  # noqa: E402
                                       RuntimeStatus)
from scripts.router_v4.scheduler import Scheduler                         # noqa: E402
from scripts.control_center import leader                                 # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NOW = 1_800_000_000.0
#: Danh sach khe AG do SO DANG KY dinh nghia — bai kiem khong tu khai "8".
AG_SLOTS = tuple(FC.AG_SLOTS)


def _fabric_gia_co_du_profile():
    """Fabric thật của kho, lớp phủ launcher GIẢ: mọi khe AG đều có profile."""
    cfg = FC.doc_cau_hinh(root=ROOT)
    with mock.patch("scripts.router_v4.antigravity_launcher.profile_ton_tai",
                    lambda acc: True):
        f = FC.dung_fabric(cfg)
    # Gia lap do suc khoe DAT cho moi khe AG (khong cham mang).
    for r in f.runtimes.values():
        if r.provider == "antigravity" and r.provisioned:
            r.status = RuntimeStatus.IDLE
            r.last_seen = NOW
    return f


def _viec(tid: str, **req) -> TaskContract:
    c = TaskContract(task_id=tid, objective="việc mã nguồn",
                     requirements=Requirements(coding=True, repo_read=True,
                                               pin_provider="antigravity", **req))
    c.validate()
    return c


class TestSoDangKy(unittest.TestCase):

    def setUp(self):
        self.f = _fabric_gia_co_du_profile()
        self.ag = {r.runtime_id: r for r in self.f.runtimes.values()
                   if r.provider == "antigravity"}

    def test_so_khe_tu_so_dang_ky_khong_gia_dinh(self):
        self.assertEqual(sorted(self.ag), sorted(AG_SLOTS))
        self.assertEqual(len(self.ag), len(AG_SLOTS))
        # Moi khe mot ho so xac thuc RIENG (bat bien Fabric.validate).
        self.assertEqual(len({r.auth_profile for r in self.ag.values()}), len(self.ag))
        for r in self.ag.values():
            self.assertTrue(r.provisioned, r.runtime_id)
            self.assertTrue(r.dispatchable, r.runtime_id)
            self.assertEqual(r.transport, "launcher", r.runtime_id)
            self.assertEqual(r.trang_thai_hien_tai(now=NOW), RuntimeStatus.IDLE)
        self.assertEqual(self.f.dem_tai_khoan().get("antigravity"), len(AG_SLOTS))

    def test_tong_cho_la_tong_concurrency_khong_phai_so_khe(self):
        tong = sum(r.concurrency for r in self.ag.values())
        self.assertGreater(tong, len(self.ag), "AG01 khai nhieu hon 1 cho")
        self.assertEqual(self.ag["AG01"].concurrency, 3)
        for rid, r in self.ag.items():
            if rid != "AG01":
                self.assertEqual(r.concurrency, 1, rid)

    def test_khe_thieu_profile_thi_OFFLINE_khong_khai_gia(self):
        cfg = FC.doc_cau_hinh(root=ROOT)
        with mock.patch("scripts.router_v4.antigravity_launcher.profile_ton_tai",
                        lambda acc: acc in ("acc1", "acc2")):
            f = FC.dung_fabric(cfg)
        ag = {r.runtime_id: r for r in f.runtimes.values() if r.provider == "antigravity"}
        self.assertEqual(len(ag), len(AG_SLOTS), "van CO MAT trong so")
        self.assertEqual(sum(r.provisioned for r in ag.values()), 2)
        self.assertEqual(f.dem_tai_khoan().get("antigravity"), 2)
        for rid in AG_SLOTS[2:]:
            self.assertEqual(ag[rid].trang_thai_hien_tai(now=NOW), RuntimeStatus.OFFLINE)
            self.assertTrue(ag[rid].needs_provisioning)


class TestChonVaChuyenDoi(unittest.TestCase):

    def setUp(self):
        self.f = _fabric_gia_co_du_profile()
        self.s = Scheduler(self.f)

    def _chon(self, tid: str, **kw):
        d = self.s.decide(_viec(tid), now=NOW, **kw)
        return d

    def test_chon_duoc_khe_ngoai_AG01_khi_AG01_day(self):
        for i in range(self.f.runtime("AG01").concurrency):
            self.f.mark_started("AG01", f"day-{i}")
        d = self._chon("t1")
        self.assertIsNotNone(d.selected, d.reason)
        self.assertNotEqual(d.selected.runtime_id, "AG01")
        self.assertIn(d.selected.runtime_id, AG_SLOTS)
        ly_do_ag01 = [c.reason for c in d.candidates if c.placement.runtime_id == "AG01"]
        self.assertTrue(ly_do_ag01 and all("đầy chỗ" in x for x in ly_do_ag01))

    def test_failover_bo_khe_da_hong_cho_chinh_viec(self):
        d = self._chon("t1", exclude=("AG01",))
        self.assertIsNotNone(d.selected)
        self.assertNotEqual(d.selected.runtime_id, "AG01")
        d = self._chon("t2", exclude=tuple(AG_SLOTS[:-1]))
        self.assertEqual(d.selected.runtime_id, AG_SLOTS[-1])
        # Loai het -> FAIL CLOSED, ly do noi ro, khong ha chuan.
        d = self._chon("t3", exclude=tuple(AG_SLOTS))
        self.assertIsNone(d.selected)
        self.assertIn("đã thử và hỏng", d.reason)

    def test_mot_khe_khong_san_khong_lam_sap_nha_cung_cap(self):
        self.f.runtime("AG03").status = RuntimeStatus.OFFLINE
        self.f.runtime("AG03").health_detail = "agy: not logged in"
        for _ in range(NGUONG_COOLDOWN):
            self.f.mark_finished("AG04", "x", ok=False, seconds=1.0, now=NOW)
        self.assertEqual(self.f.runtime("AG04").trang_thai_hien_tai(now=NOW),
                         RuntimeStatus.COOLDOWN)
        d = self._chon("t1")
        self.assertIsNotNone(d.selected, d.reason)
        self.assertNotIn(d.selected.runtime_id, ("AG03", "AG04"))
        du = {c.placement.runtime_id for c in d.candidates if c.eligible}
        self.assertGreaterEqual(len(du), len(AG_SLOTS) - 2)

    def test_giao_dong_thoi_ton_trong_suc_chua_tung_khe(self):
        tong = sum(r.concurrency for r in self.f.runtimes.values()
                   if r.provider == "antigravity")
        giao = []
        for i in range(tong + 3):
            d = self._chon(f"t{i}")
            if d.selected is None:
                break
            self.f.mark_started(d.selected.runtime_id, f"t{i}")
            giao.append(d.selected.runtime_id)
            for r in self.f.runtimes.values():
                self.assertLessEqual(r.in_flight, r.concurrency, r.runtime_id)
        self.assertEqual(len(giao), tong, "đúng bằng tổng chỗ, không hơn")
        d = self._chon("thua")
        self.assertIsNone(d.selected)
        self.assertIn("đầy chỗ", d.reason)
        # Trai deu: khong don het vao mot khe truoc khi cham khe khac.
        self.assertGreaterEqual(len(set(giao[:len(AG_SLOTS)])), len(AG_SLOTS) - 1)

    def test_cooldown_co_bac_va_tu_het(self):
        r = self.f.runtime("AG05")
        for _ in range(NGUONG_COOLDOWN - 1):
            self.f.mark_finished("AG05", "x", ok=False, seconds=1.0, now=NOW)
        self.assertNotEqual(r.trang_thai_hien_tai(now=NOW), RuntimeStatus.COOLDOWN)
        self.f.mark_finished("AG05", "x", ok=False, seconds=1.0, now=NOW)
        self.assertEqual(r.trang_thai_hien_tai(now=NOW), RuntimeStatus.COOLDOWN)
        self.assertAlmostEqual(r.cooldown_until, NOW + BACKOFF_COOLDOWN[0])
        self.f.mark_finished("AG05", "x", ok=False, seconds=1.0, now=NOW)
        self.assertAlmostEqual(r.cooldown_until, NOW + BACKOFF_COOLDOWN[1])
        # Trong cooldown: khong duoc chon. Het cooldown: lai chon duoc.
        d = self.s.decide(_viec("a", pin_runtime="AG05"), now=NOW)
        self.assertIsNone(d.selected)
        d = self.s.decide(_viec("b", pin_runtime="AG05"), now=NOW + BACKOFF_COOLDOWN[1] + 1)
        self.assertEqual(d.selected.runtime_id, "AG05")
        # Thanh cong xoa chuoi hong.
        self.f.mark_finished("AG05", "x", ok=True, seconds=1.0, now=NOW + 5000)
        self.assertEqual(r.consecutive_failures, 0)

    def test_tat_dinh(self):
        a = self._chon("t1").selected
        b = self._chon("t1").selected
        self.assertEqual(a.key, b.key)


class TestLeaderVaWorkerCungBe(unittest.TestCase):

    def setUp(self):
        self.f = _fabric_gia_co_du_profile()

    def test_leader_ghim_AG01_la_khe_worker_cung_dung(self):
        ph = leader.PhienLeader(model="claude-sonnet-4-6")   # khong sinh agy
        self.assertEqual(ph.runtime_id, "AG01")
        self.assertIn("AG01", self.f.runtimes)
        self.assertEqual(self.f.runtime("AG01").provider, "antigravity")
        self.assertEqual(leader.PROVIDER_LEADER, "antigravity")

    def test_cho_leader_chiem_hien_ra_voi_bo_lap_lich(self):
        s = Scheduler(self.f)
        r = self.f.runtime("AG01")
        self.assertTrue(leader.chiem_cho_fabric(self.f, "AG01", "LEADER:p1"))
        self.assertEqual(r.in_flight, 1)
        self.assertIn("LEADER:p1", r.running_tasks)
        self.assertTrue(leader.chiem_cho_fabric(self.f, "AG01", "LEADER:p1"), "idempotent")
        self.assertEqual(r.in_flight, 1)
        # Con 2 cho cho worker, khong phai 3.
        n = 0
        while True:
            d = s.decide(_viec(f"w{n}", pin_runtime="AG01"), now=NOW)
            if d.selected is None:
                break
            self.f.mark_started("AG01", f"w{n}")
            n += 1
        self.assertEqual(n, r.concurrency - 1)
        # Tra cho: khong tinh vao completed/failed.
        self.assertTrue(leader.tra_cho_fabric(self.f, "AG01", "LEADER:p1"))
        self.assertNotIn("LEADER:p1", r.running_tasks)
        self.assertEqual((r.completed, r.failed), (0, 0))
        self.assertFalse(leader.tra_cho_fabric(self.f, "AG01", "LEADER:p1"))
        self.assertFalse(leader.chiem_cho_fabric(self.f, "AG99", "LEADER:p1"))


if __name__ == "__main__":
    unittest.main()
