"""Tương thích ngược V3 -> V4 (mission #23) + nạp fabric từ cấu hình thật.

Mục đích: chứng minh Router V3 KHÔNG bị thay thế. Các nguyên thuỷ V3 vẫn
chạy, và một DAG V3 dịch được sang mission V4 mà không mất quan hệ phụ
thuộc hay phạm vi ghi.
"""
from __future__ import annotations

import unittest

from scripts.router_v3.dag import RiskClass, TaskDag, TaskNode
from scripts.router_v3.registry import ExecutionType, WorkerSpec
from scripts.router_v4 import compat
from scripts.router_v4.capabilities import Reasoning
from scripts.router_v4.runtime import Placement


class TestDichNut(unittest.TestCase):
    def test_nut_co_ghi_thanh_hop_dong_can_worktree(self):
        n = TaskNode(id="T1", objective="sửa module",
                     write_scope=("pkg/a",),
                     required_capabilities=("implement",))
        c = compat.node_to_contract(n)
        c.validate()
        self.assertTrue(c.requirements.repo_write)
        self.assertTrue(c.execution.worktree_required)
        self.assertEqual(c.allowed_scope, ("pkg/a",))

    def test_nut_chi_doc_khong_doi_quyen_ghi(self):
        n = TaskNode(id="T2", objective="khảo sát",
                     required_capabilities=("recon",))
        c = compat.node_to_contract(n)
        c.validate()
        self.assertFalse(c.requirements.repo_write)
        self.assertFalse(c.execution.worktree_required)
        self.assertTrue(c.requirements.repo_read)

    def test_rui_ro_cao_thanh_suy_luan_cao_va_doi_review(self):
        n = TaskNode(id="T3", objective="đổi auth",
                     required_capabilities=("security_review",),
                     risk_class=RiskClass.HIGH)
        c = compat.node_to_contract(n)
        self.assertIs(c.requirements.reasoning_level, Reasoning.HIGH)
        self.assertTrue(c.verification.independent_review_required)
        self.assertGreaterEqual(c.impact, 0.7)

    def test_nut_media_thanh_yeu_cau_da_phuong_thuc(self):
        n = TaskNode(id="T4", objective="QA video",
                     required_capabilities=("media_agent",))
        c = compat.node_to_contract(n)
        self.assertTrue(c.requirements.multimodal)

    def test_nut_khong_nhan_duoc_tap_nang_luc_TOI_THIEU(self):
        """Suy diễn rộng tay sẽ tạo rào cứng không ai yêu cầu rồi loại sạch
        ứng viên — nên nút không nhãn chỉ được `repo_read`."""
        n = TaskNode(id="T5", objective="việc chung chung")
        c = compat.node_to_contract(n)
        self.assertEqual(c.requirements.hard,
                         frozenset({"repo_read", "structured_output"}))


class TestDichDag(unittest.TestCase):
    def test_giu_nguyen_phu_thuoc_va_thu_tu(self):
        dag = TaskDag([
            TaskNode(id="A", objective="a"),
            TaskNode(id="B", objective="b"),
            TaskNode(id="E", objective="e", dependencies=("A", "B")),
        ])
        md = compat.dag_to_mission(dag, mission_id="m1")
        self.assertEqual(set(md.ids()), {"A", "B", "E"})
        self.assertEqual(md.contract("E").dependencies, ("A", "B"))
        self.assertEqual(md.waves(), [["A", "B"], ["E"]])

    def test_dag_v3_co_ghi_chong_nhau_da_duoc_chap_nhan_thi_khong_bi_tu_choi_lai(self):
        dag = TaskDag([TaskNode(id="A", objective="a", write_scope=("pkg",)),
                       TaskNode(id="B", objective="b", write_scope=("pkg/x",))],
                      allow_overlapping_writes=True)
        md = compat.dag_to_mission(dag)       # khong duoc nem
        self.assertEqual(len(md), 2)

    def test_duong_toi_han_van_tinh_duoc_sau_khi_dich(self):
        dag = TaskDag([
            TaskNode(id="A", objective="a", estimated_seconds=10),
            TaskNode(id="B", objective="b", dependencies=("A",),
                     estimated_seconds=20),
        ])
        md = compat.dag_to_mission(dag)
        duong, giay = md.critical_path()
        self.assertEqual(duong, ["A", "B"])
        self.assertEqual(giay, 30.0)


class TestDichNguoc(unittest.TestCase):
    def test_hop_dong_v4_ve_nut_v3(self):
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import Execution, TaskContract
        c = TaskContract(task_id="X", objective="o",
                         requirements=Requirements(repo_read=True,
                                                   repo_write=True, coding=True),
                         allowed_scope=("pkg",),
                         execution=Execution(worktree_required=True))
        c.validate()
        n = compat.contract_to_node(c)
        self.assertEqual(n.id, "X")
        self.assertEqual(n.write_scope, ("pkg",))
        self.assertIn("implement", n.required_capabilities)

    def test_spec_khong_co_model_khong_sinh_placement_ao(self):
        s = WorkerSpec(worker_id="W", provider_family="antigravity",
                       execution_type=ExecutionType.LOCAL_CLI, pool="P")
        self.assertIsNone(compat.spec_to_placement(s))
        s2 = WorkerSpec(worker_id="W", provider_family="antigravity",
                        execution_type=ExecutionType.LOCAL_CLI, pool="P",
                        model="m1")
        self.assertEqual(compat.spec_to_placement(s2), Placement("W", "m1"))


class TestNapCauHinhThat(unittest.TestCase):
    """Cấu hình đi kèm mã PHẢI nạp được và thoả mọi bất biến — nếu không,
    Router V4 hỏng ngay từ dòng đầu tiên trên máy thật."""

    def setUp(self):
        from scripts.router_v4 import fabric_config as FC
        self.f, self.w, self.esc = FC.nap(probe=False)

    def test_fabric_that_hop_le(self):
        self.f.validate()
        self.assertGreaterEqual(len(self.f.runtimes), 11)
        self.assertGreaterEqual(len(self.f.models), 8)

    def test_tam_khe_AG_deu_co_mat(self):
        for i in range(1, 9):
            self.assertIn(f"AG{i:02d}", self.f.runtimes)

    def test_khe_chua_cap_phat_bao_OFFLINE_chu_khong_gia_vo_san_sang(self):
        from scripts.router_v4.runtime import RuntimeStatus
        for i in range(3, 9):
            r = self.f.runtime(f"AG{i:02d}")
            self.assertFalse(r.provisioned)
            self.assertEqual(r.trang_thai_hien_tai(), RuntimeStatus.OFFLINE)
            self.assertIn("hồ sơ Windows", r.needs_provisioning)

    def test_moi_runtime_AG_la_mot_TAI_KHOAN_rieng(self):
        ho_so = [self.f.runtime(f"AG{i:02d}").auth_profile for i in range(1, 9)]
        self.assertEqual(len(set(ho_so)), 8, "8 khe phải là 8 hồ sơ xác thực")

    def test_ag01_la_vat_chua_NHIEU_model_khong_phai_worker_gemini(self):
        r = self.f.runtime("AG01")
        ho = {self.f.model(m).model_family for m in r.supported_models}
        self.assertIn("gemini", ho)
        self.assertIn("claude", ho)
        self.assertIn("gpt", ho)

    def test_gpt_oss_va_claude_dung_chung_be_quota(self):
        a = self.f.pool_cua_placement(Placement("AG01", "gpt-oss-120b-medium"))
        b = self.f.pool_cua_placement(Placement("AG01", "claude-opus-4-6-thinking"))
        c = self.f.pool_cua_placement(Placement("AG01", "gemini-3.8-flash-high"))
        self.assertIsNotNone(a)
        self.assertEqual(a.pool_id, b.pool_id,
                         "GPT-OSS KHÔNG miễn phí — nó rút cùng bể với Claude")
        self.assertNotEqual(a.pool_id, c.pool_id)

    def test_hai_tai_khoan_AG_co_HAI_be_gemini_doc_lap(self):
        a = self.f.pool_cua_placement(Placement("AG01", "gemini-3.8-flash-high"))
        b = self.f.pool_cua_placement(Placement("AG02", "gemini-3.8-flash-high"))
        self.assertNotEqual(a.pool_id, b.pool_id,
                            "quota gắn với TÀI KHOẢN — gộp chung sẽ khiến một "
                            "tài khoản hết quota kéo cả hai xuống")

    def test_dem_tai_khoan_khong_thoi_phong(self):
        dem = self.f.dem_tai_khoan()
        self.assertEqual(dem.get("antigravity"), 1,
                         "chỉ AG01 đã cấp phát — 51 placement không phải 51 "
                         "tài khoản")

    def test_khong_co_vai_tro_dong_cung_trong_cau_hinh(self):
        """Không runtime nào được khai kiểu 'AG01 = coding'."""
        import json
        from scripts.router_v4 import fabric_config as FC
        tho = FC.duong_mac_dinh().read_text(encoding="utf-8").lower()
        for xau in ('"role"', '"task_type"', 'ag01 = ', 'ag02 = '):
            self.assertNotIn(xau, tho, f"cấu hình chứa vai trò đóng cứng: {xau}")

    def test_trong_so_va_leo_thang_nap_duoc(self):
        self.assertGreater(self.w.capability_match, 0)
        self.assertGreater(self.esc.nguong_hypotheses, self.esc.nguong_critic)

    def test_cau_hinh_cham_cong_cu_xoay_tai_khoan_bi_tu_choi(self):
        import tempfile
        from pathlib import Path
        from scripts.router_v4 import fabric_config as FC
        from scripts.router_v4.runtime import FabricError
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fabric.json"
            p.write_text('{"runtimes":[{"runtime_id":"X","provider":"antigravity",'
                         '"auth_profile":"p","notes":"chạy acc.cmd 2 trước"}]}',
                         encoding="utf-8")
            with self.assertRaises(FabricError):
                FC.nap(path=p, probe=False)

    def test_bien_moi_truong_tuy_y_khong_mo_rong_duoc(self):
        from scripts.router_v4 import fabric_config as FC
        from scripts.router_v4.runtime import FabricError
        with self.assertRaises(FabricError):
            FC._thay_bien("${AWS_SECRET_ACCESS_KEY}")
        self.assertNotIn("${", FC._thay_bien("windows-user:${USERNAME}"))


class TestKhongDungCoNguyHiem(unittest.TestCase):
    """Mission cấm `--dangerously-skip-permissions`. Kiểm bằng mã, không
    bằng lời hứa trong tài liệu."""

    def test_adapter_antigravity_khong_bao_gio_bat_co_do(self):
        from scripts.router_v3.pool.adapters import PoolAntigravityAdapter
        a = PoolAntigravityAdapter("AG01", model="m",
                                   dangerously_skip_permissions=True)
        # Ngay ca khi noi goi CO TINH bat, `start_session` phai ep ve False.
        try:
            a.start_session(workspace=None)
        except Exception:
            pass
        self.assertFalse(a._dsp)

    def test_viec_chi_doc_khong_xin_quyen_ghi(self):
        from scripts.router_v3.pool.adapters import PoolAntigravityAdapter
        a = PoolAntigravityAdapter("AG01", model="m")
        try:
            a.start_session(workspace=None)
        except Exception:
            pass
        self.assertFalse(a._allow_edits)


if __name__ == "__main__":
    unittest.main()
