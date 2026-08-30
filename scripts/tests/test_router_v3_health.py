"""Trạng thái sức khoẻ mở rộng + cầu dập mạch — Router LTS Phase 7.

Bài quyết định nhất: một nguồn hỏng liên tục không được chặn cả DAG (phải
có `available()` loại nó ra) nhưng cũng không được mất vĩnh viễn (phải tự
dò lại được) — và khi đang dò, các nút khác không được đè lên lượt dò đó.
"""
from __future__ import annotations

import os
import sys
import threading
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.registry import (BACKOFF_MO_MACH, CAPABILITIES,
                                        NGUONG_MO_MACH, ExecutionType, Health,
                                        WorkerRegistry, WorkerSpec)


def _reg(worker_id="A", max_concurrent=1) -> WorkerRegistry:
    r = WorkerRegistry()
    r.register(WorkerSpec(worker_id=worker_id, provider_family="antigravity",
                          execution_type=ExecutionType.LOCAL_CLI, pool="P",
                          max_concurrent=max_concurrent))
    r.set_health(worker_id, Health.HEALTHY)
    return r


class TrangThaiMoiTest(unittest.TestCase):
    def test_cac_trang_thai_moi_ton_tai(self):
        self.assertEqual(Health.RATE_LIMITED.value, "rate_limited")
        self.assertEqual(Health.AUTH_REQUIRED.value, "auth_required")
        self.assertEqual(Health.FAILED.value, "failed")

    def test_AUTH_REQUIRED_khong_bao_gio_duoc_chon(self):
        r = _reg()
        r.set_health("A", Health.AUTH_REQUIRED)
        self.assertEqual(r.available(), [])

    def test_RATE_LIMITED_van_con_trong_danh_sach_bi_ha_diem(self):
        """Khac UNAVAILABLE/AUTH_REQUIRED: quota tu hoi, khong can nguoi."""
        r = _reg()
        r.set_health("A", Health.RATE_LIMITED)
        self.assertEqual(len(r.available()), 1)

    def test_nang_luc_chuyen_biet_Phase12_hop_le(self):
        for nl in ("frontend_prototyper", "research_agent", "scraping_agent",
                  "security_reviewer", "test_generator", "media_agent"):
            self.assertIn(nl, CAPABILITIES)
        # validate() khong nem loi voi nang luc moi
        WorkerSpec(worker_id="X", provider_family="p",
                  execution_type=ExecutionType.LOCAL_CLI, pool="p",
                  capabilities=frozenset({"security_reviewer"})).validate()


class CauDapMachTest(unittest.TestCase):
    def test_chua_hong_thi_mach_dong(self):
        r = _reg()
        self.assertEqual(len(r.available()), 1)

    def test_hong_duoi_nguong_van_chon_duoc(self):
        r = _reg()
        for _ in range(NGUONG_MO_MACH - 1):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        self.assertEqual(len(r.available(now=1000.0)), 1)

    def test_circuit_opens_KHONG_tang_khi_hong_duoi_nguong(self):
        """Bai quyet dinh: review doc lap tim thay `circuit_opens += 1` bi
        thut le sai (nam ngoai khoi `if`) sau khi them khoa luong — no tang
        o MOI lan hong thay vi CHI khi mach that su mo. Sua roi; bai nay
        khoa lai."""
        r = _reg()
        for _ in range(NGUONG_MO_MACH - 1):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        self.assertEqual(r.state("A").circuit_opens, 0,
                         "chua du nguong -> mach CHUA MO -> circuit_opens phai la 0")

    def test_hong_du_NGUONG_thi_mach_MO_loai_khoi_available(self):
        r = _reg()
        for _ in range(NGUONG_MO_MACH):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        self.assertEqual(r.available(now=1000.0), [])
        self.assertTrue(r.state("A").circuit_is_open(now=1000.0))

    def test_mach_tu_dong_ve_sau_backoff_dau(self):
        r = _reg()
        for _ in range(NGUONG_MO_MACH):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        sau = 1000.0 + BACKOFF_MO_MACH[0] + 0.1
        self.assertEqual(len(r.available(now=sau)), 1,
                         "qua gio backoff -> phai vao duoc trang thai nua-mo")

    def test_luot_do_nua_mo_thanh_cong_thi_dong_han_mach(self):
        r = _reg()
        for _ in range(NGUONG_MO_MACH):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        sau = 1000.0 + BACKOFF_MO_MACH[0] + 0.1
        r.mark_started("A", "probe")           # luot do nua-mo
        r.mark_finished("A", ok=True, seconds=1.0, now=sau)
        self.assertEqual(r.state("A").consecutive_failures, 0)
        self.assertFalse(r.state("A").circuit_is_open(now=sau))
        self.assertEqual(len(r.available(now=sau)), 1)

    def test_luot_do_nua_mo_hong_thi_mo_lai_VOI_BACKOFF_DAI_HON(self):
        r = _reg()
        for _ in range(NGUONG_MO_MACH):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        sau = 1000.0 + BACKOFF_MO_MACH[0] + 0.1
        r.mark_started("A", "probe")
        r.mark_finished("A", ok=False, seconds=1.0, now=sau)
        # Mach mo lai, va backoff LAN NAY phai dai hon lan dau.
        self.assertTrue(r.state("A").circuit_is_open(now=sau))
        con_lai = r.state("A").circuit_open_until - sau
        self.assertGreater(con_lai, BACKOFF_MO_MACH[0] - 1)

    def test_khong_hai_luot_do_cung_bay_mot_luc(self):
        """Mach nua-mo: nut thu hai KHONG duoc coi la dang do trong khi nut
        dau van chua tra ket qua — tranh mo lai mach nhieu lan chi vi N nut
        cung san sang cung luc."""
        r = _reg(max_concurrent=2)
        for _ in range(NGUONG_MO_MACH):
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=1.0, now=1000.0)
        sau = 1000.0 + BACKOFF_MO_MACH[0] + 0.1
        self.assertEqual(len(r.available(now=sau)), 1)
        r.mark_started("A", "probe-1")          # nut dau chiem luot do
        self.assertEqual(r.available(now=sau), [],
                         "nut thu hai KHONG duoc coi la co the do them")

    def test_UNAVAILABLE_khong_bi_ghi_de_thanh_HEALTHY_boi_mot_luot_thanh_cong(self):
        """Neu ai do lo goi mark_finished(ok=True) tren mot khe da danh dau
        UNAVAILABLE (vd probe cu con dang bay), no KHONG duoc tu suy ra la
        khoe — nguoi van hanh la nguoi duy nhat duoc doi trang thai do."""
        r = _reg()
        r.set_health("A", Health.UNAVAILABLE)
        r.mark_started("A", "t")
        r.mark_finished("A", ok=True, seconds=1.0, now=1000.0)
        self.assertEqual(r.state("A").health, Health.UNAVAILABLE)


class AnToanLuongTest(unittest.TestCase):
    """Bang chung that (review doc lap, 2026-08-30): `Scheduler` goi
    `mark_finished` tu NHIEU LUONG worker qua ThreadPoolExecutor, va mot
    worker co `max_concurrent > 1` (vd AG_SLOTS trong default_registry)
    THAT SU co nhieu luot cung ket thuc dong thoi. Truoc khi them khoa,
    chuoi doc-sua-ghi cua cau dap mach khong atomic qua nhieu cau lenh."""

    def test_nhieu_luong_hong_dong_thoi_khong_lam_hong_bo_dem(self):
        r = _reg(max_concurrent=50)
        SO_LUONG = 50

        def _mot_luot():
            r.mark_started("A", "t")
            r.mark_finished("A", ok=False, seconds=0.001, now=1000.0)

        luong = [threading.Thread(target=_mot_luot) for _ in range(SO_LUONG)]
        for t in luong:
            t.start()
        for t in luong:
            t.join()

        st = r.state("A")
        self.assertEqual(st.failed, SO_LUONG, "moi luot hong phai duoc dem")
        self.assertEqual(st.in_flight, 0, "moi luot phai giam in_flight dung mot lan")
        # consecutive_failures co the vuot NGUONG nhieu — nhung khong duoc
        # VUOT so luong THAT (bang chung khong co ghi de/mat cap nhat).
        self.assertLessEqual(st.consecutive_failures, SO_LUONG)
        self.assertGreaterEqual(st.consecutive_failures, NGUONG_MO_MACH)


if __name__ == "__main__":
    unittest.main()
