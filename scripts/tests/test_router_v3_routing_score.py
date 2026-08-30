"""Điểm định tuyến theo nhiều chiều + lịch sử — Router LTS Phase 8 + 9.

Bài quyết định nhất: rào cứng an ninh (`security_review` không bao giờ đi
Codex, việc rủi ro cao chỉ đi worker tin cậy) phải giữ nguyên KỂ CẢ khi
quota/chi phí "hấp dẫn" nghiêng hẳn về phía worker không đủ tin cậy — vì
lọc rào cứng chạy TRƯỚC khi các trọng số này từng được tính tới.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.router_v3.dag import RiskClass, TaskNode
from scripts.router_v3.policy import RoutingScore, choose_worker, score_worker
from scripts.router_v3.registry import ExecutionType, Health, WorkerRegistry, WorkerSpec
from scripts.router_v3.routing_history import BanGhiKetQua, doc_tat_ca, ghi, tong_hop


def _reg_hai_worker(*, worker_tin_cay_re=False):
    r = WorkerRegistry()
    r.register(WorkerSpec(worker_id="RE", provider_family="codex",
                          execution_type=ExecutionType.LOCAL_CLI, pool="P",
                          capabilities=frozenset({"security_review"}),
                          trusted_for_high_risk=worker_tin_cay_re))
    r.register(WorkerSpec(worker_id="TIN_CAY", provider_family="antigravity",
                          execution_type=ExecutionType.LOCAL_CLI, pool="P",
                          capabilities=frozenset({"security_review"}),
                          trusted_for_high_risk=True))
    r.set_health("RE", Health.HEALTHY)
    r.set_health("TIN_CAY", Health.HEALTHY)
    return r


class RaoCungThangQuotaTest(unittest.TestCase):
    def test_security_review_KHONG_BAO_GIO_di_Codex_du_quota_hap_dan(self):
        r = _reg_hai_worker()
        node = TaskNode(id="t", objective="x",
                        required_capabilities=("security_review",),
                        risk_class=RiskClass.HIGH)
        # RE (codex) duoc "quota con day" toi da, TIN_CAY bi coi la het quota
        # — neu quota thang duoc rao cung thi RE se duoc chon. No KHONG duoc.
        chon = choose_worker(r, node, quota_remaining={"RE": 1.0, "TIN_CAY": 0.0})
        self.assertEqual(chon.worker_id, "TIN_CAY")

    def test_rui_ro_cao_khong_tin_cay_bi_loai_du_lich_su_hoan_hao(self):
        r = _reg_hai_worker()
        # RE co lich su hoan hao, TIN_CAY chua co lich su gi — RE VAN bi loai
        # vi khong `trusted_for_high_risk` va viec la RiskClass.HIGH.
        lich_su = {"RE": tong_hop([BanGhiKetQua(provider="codex", success=True)] * 10,
                                  provider="codex")}
        node = TaskNode(id="t", objective="x",
                        required_capabilities=("security_review",),
                        risk_class=RiskClass.HIGH)
        chon = choose_worker(r, node, history=lich_su)
        self.assertEqual(chon.worker_id, "TIN_CAY")


class DiemTheoChieuTest(unittest.TestCase):
    def test_tong_la_tong_cac_chieu(self):
        s = RoutingScore(capability_fit=1.0, risk_fit=2.0)
        self.assertEqual(s.total, 3.0)

    def test_lich_su_lam_lai_cao_ha_diem(self):
        r = _reg_hai_worker()
        node = TaskNode(id="t", objective="x", risk_class=RiskClass.LOW)
        su_tot = tong_hop([BanGhiKetQua(provider="antigravity", success=True,
                                        rework_required=False)] * 5,
                          provider="antigravity")
        su_xau = tong_hop([BanGhiKetQua(provider="antigravity", success=True,
                                        rework_required=True)] * 5,
                          provider="antigravity")
        d_tot = score_worker(r.spec("TIN_CAY"), r, node,
                             history={"TIN_CAY": su_tot})
        d_xau = score_worker(r.spec("TIN_CAY"), r, node,
                             history={"TIN_CAY": su_xau})
        self.assertLess(d_xau.total, d_tot.total)

    def test_khong_co_quota_thi_trung_lap_khong_thien_vi(self):
        r = _reg_hai_worker()
        node = TaskNode(id="t", objective="x", risk_class=RiskClass.LOW)
        d = score_worker(r.spec("TIN_CAY"), r, node, quota_remaining=None)
        self.assertEqual(d.quota_remaining, 0.0)

    def test_hong_lien_tiep_gan_day_ha_diem(self):
        r = _reg_hai_worker()
        node = TaskNode(id="t", objective="x", risk_class=RiskClass.LOW)
        r.state("TIN_CAY").consecutive_failures = 2
        d = score_worker(r.spec("TIN_CAY"), r, node)
        self.assertLess(d.recent_failure_rate, 0.0)

    def test_ngu_canh_phinh_ha_diem_nhe(self):
        r = _reg_hai_worker()
        node = TaskNode(id="t", objective="x", risk_class=RiskClass.LOW)
        r.state("TIN_CAY").context_chars = 50_000
        d = score_worker(r.spec("TIN_CAY"), r, node)
        self.assertLess(d.context_size, 0.0)


class LichSuTrenDiaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rv-hist-"))
        self.duong = self.tmp / "history.jsonl"

    def test_ghi_roi_doc_lai_dung(self):
        ghi(BanGhiKetQua(provider="antigravity", success=True, wall_seconds=5.0),
           duong=self.duong)
        ds = doc_tat_ca(duong=self.duong)
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0].provider, "antigravity")

    def test_dong_hong_khong_lam_hong_ca_lich_su(self):
        ghi(BanGhiKetQua(provider="a"), duong=self.duong)
        with open(self.duong, "a", encoding="utf-8") as f:
            f.write("khong phai json\n")
        ghi(BanGhiKetQua(provider="b"), duong=self.duong)
        ds = doc_tat_ca(duong=self.duong)
        self.assertEqual(len(ds), 2)

    def test_tong_hop_loc_dung_provider(self):
        ghi(BanGhiKetQua(provider="a", success=True), duong=self.duong)
        ghi(BanGhiKetQua(provider="a", success=False), duong=self.duong)
        ghi(BanGhiKetQua(provider="b", success=True), duong=self.duong)
        ds = doc_tat_ca(duong=self.duong)
        th = tong_hop(ds, provider="a")
        self.assertEqual(th.so_luot, 2)
        self.assertEqual(th.ty_le_thanh_cong, 0.5)

    def test_chua_co_ban_ghi_thi_lac_quan(self):
        th = tong_hop([], provider="khong_ton_tai")
        self.assertEqual(th.so_luot, 0)
        self.assertEqual(th.ty_le_thanh_cong, 1.0)

    def test_limit_dong_chi_lay_phan_GAN_NHAT(self):
        for i in range(5):
            ghi(BanGhiKetQua(provider=f"p{i}"), duong=self.duong)
        ds = doc_tat_ca(duong=self.duong, limit_dong=2)
        self.assertEqual([b.provider for b in ds], ["p3", "p4"])

    def test_khong_dat_limit_dong_thi_doc_het_nhu_cu(self):
        for i in range(5):
            ghi(BanGhiKetQua(provider=f"p{i}"), duong=self.duong)
        ds = doc_tat_ca(duong=self.duong)
        self.assertEqual(len(ds), 5)

    def test_tu_choi_ghi_ban_ghi_giong_credential(self):
        with self.assertRaises(ValueError):
            ghi(BanGhiKetQua(provider="a", test_result="sk-" + "x" * 30),
               duong=self.duong)
        self.assertFalse(self.duong.exists())


if __name__ == "__main__":
    unittest.main()
