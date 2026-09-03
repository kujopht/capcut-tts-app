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

    def test_trang_thai_khe_AG_khop_voi_THUC_TE_tren_dia(self):
        """Khe AG chỉ được coi là cấp phát khi có bằng chứng TRÊN ĐĨA.

        Bản trước khẳng định thẳng AG03..AG08 luôn OFFLINE. Điều đó đúng cho
        tới khi người vận hành dựng launcher đa-tài-khoản (2026-09-03), rồi
        bài kiểm thành sai. Giờ nó kiểm QUAN HỆ — trạng thái phải khớp với
        việc `saved_profiles/accN.bin` có tồn tại hay không — nên nó đúng ở
        cả hai thế giới và không bao giờ nói dối.
        """
        from scripts.router_v4.antigravity_launcher import (ACC_CUA_RUNTIME,
                                                            profile_ton_tai)
        from scripts.router_v4.runtime import RuntimeStatus
        for i in range(1, 9):
            rid = f"AG{i:02d}"
            r = self.f.runtime(rid)
            acc = ACC_CUA_RUNTIME[rid]
            if profile_ton_tai(acc):
                self.assertTrue(r.provisioned, f"{rid}: có {acc}.bin")
                self.assertEqual(r.transport, "launcher", rid)
            else:
                self.assertFalse(r.provisioned, f"{rid}: không có {acc}.bin")
                self.assertEqual(r.trang_thai_hien_tai(),
                                 RuntimeStatus.OFFLINE, rid)
                self.assertTrue(r.needs_provisioning, rid)

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
        """Đếm TÀI KHOẢN phải khớp số khe CÓ THẬT, không khớp số placement.

        Bản trước đóng cứng `== 1`. Con số đó đúng cho tới khi launcher
        đa-tài-khoản xuất hiện; giờ nó kiểm ĐÚNG THỨ CẦN KIỂM — số tài khoản
        bằng số profile trên đĩa, và LUÔN nhỏ hơn số placement (nhiều model
        trên một tài khoản không phải nhiều tài khoản).
        """
        from scripts.router_v4.antigravity_launcher import (ACC_CUA_RUNTIME,
                                                            profile_ton_tai)
        dem = self.f.dem_tai_khoan()
        mong_doi = sum(1 for acc in ACC_CUA_RUNTIME.values()
                       if profile_ton_tai(acc))
        self.assertEqual(dem.get("antigravity", 0), mong_doi,
                         "số tài khoản AG phải bằng số profile CÓ THẬT trên đĩa")
        self.assertLess(sum(dem.values()), len(self.f.placements()),
                        "số tài khoản phải NHỎ HƠN số placement — nhiều model "
                        "trên một tài khoản không phải nhiều tài khoản")

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


class TestBangChungLanAtLoiKhai(unittest.TestCase):
    """Bằng chứng khách quan thắng lời khai của worker — CẢ HAI CHIỀU.

    Khoá lại một lỗi có thật (lượt chạy bằng chứng 2026-09-03): một worker
    viết ĐÚNG tệp được yêu cầu, biên dịch được, đúng phạm vi — rồi kết thúc
    lượt với phản hồi văn bản RỖNG. Phong bì thành `failed`, việc bị giao
    lại cho worker khác, và cả một lượt làm đúng bị vứt đi ba lần liên tiếp.
    """

    def _executor(self, root):
        from scripts.router_v4.executor import Executor
        from scripts.router_v4.runtime import Fabric
        return Executor(Fabric(), root=root)

    def _hop_dong(self, *, co_bang_chung: bool, co_ghi: bool = True):
        from scripts.router_v4.capabilities import Requirements
        from scripts.router_v4.contract import Execution, TaskContract, Verification
        return TaskContract(
            task_id="T", objective="viết tệp",
            requirements=Requirements(coding=True, repo_read=True,
                                      repo_write=co_ghi),
            allowed_scope=("pkg",) if co_ghi else (),
            execution=Execution(worktree_required=co_ghi),
            verification=(Verification(artifact_checks=("pkg/x.py",))
                          if co_bang_chung else Verification()))

    def _bao_cao(self, *, dat: bool, tep=("pkg/x.py",)):
        from scripts.router_v3.pool.validation import GateResult, ValidationReport
        bc = ValidationReport()
        bc.gates.append(GateResult("diff", dat, ""))
        bc.files_changed_observed = list(tep)
        bc.tests_ran = ["python -m compileall"]
        return bc

    def test_phan_hoi_rong_nhung_bang_chung_dat_thi_duoc_nang_len_ok(self):
        import tempfile
        from scripts.router_v4.envelope import ResultEnvelope
        with tempfile.TemporaryDirectory() as d:
            ex = self._executor(d)
            pb = ResultEnvelope(task_id="T", status="failed",
                                failure_reason="no_json_block")
            ex._bang_chung_lan_at_loi_khai(
                self._hop_dong(co_bang_chung=True), pb,
                self._bao_cao(dat=True), handle=object())
            self.assertEqual(pb.status, "ok")
            self.assertEqual(pb.failure_reason, "")
            self.assertTrue(pb.warnings, "phải ghi rõ đã nâng theo bằng chứng")

    def test_khong_co_bang_chung_khach_quan_thi_KHONG_nang(self):
        """Hợp đồng không có artifact_checks/tests thì một phản hồi rỗng vẫn
        là hỏng — nâng bừa ở đây sẽ biến mọi lượt câm thành 'thành công'."""
        import tempfile
        from scripts.router_v4.envelope import ResultEnvelope
        with tempfile.TemporaryDirectory() as d:
            ex = self._executor(d)
            pb = ResultEnvelope(task_id="T", status="failed",
                                failure_reason="no_json_block")
            ex._bang_chung_lan_at_loi_khai(
                self._hop_dong(co_bang_chung=False), pb,
                self._bao_cao(dat=True), handle=object())
            self.assertEqual(pb.status, "failed")

    def test_cong_kiem_dinh_hong_thi_KHONG_nang(self):
        import tempfile
        from scripts.router_v4.envelope import ResultEnvelope
        with tempfile.TemporaryDirectory() as d:
            ex = self._executor(d)
            pb = ResultEnvelope(task_id="T", status="failed")
            ex._bang_chung_lan_at_loi_khai(
                self._hop_dong(co_bang_chung=True), pb,
                self._bao_cao(dat=False), handle=object())
            self.assertEqual(pb.status, "failed")

    def test_viec_co_ghi_ma_dia_sach_thi_KHONG_nang(self):
        import tempfile
        from scripts.router_v4.envelope import ResultEnvelope
        with tempfile.TemporaryDirectory() as d:
            ex = self._executor(d)
            pb = ResultEnvelope(task_id="T", status="failed")
            ex._bang_chung_lan_at_loi_khai(
                self._hop_dong(co_bang_chung=True), pb,
                self._bao_cao(dat=True, tep=()), handle=object())
            self.assertEqual(pb.status, "failed")


class TestNoiDocPhuThuoc(unittest.TestCase):
    """Nút phụ thuộc phải đọc được kết quả nằm trong worktree CÔ LẬP của
    nút trước. Khoá lại lỗi thật: reviewer báo 'không tìm thấy tệp' trong
    khi tệp có thật — chỉ là ở worktree của nút kia."""

    def _ex(self):
        import tempfile
        from scripts.router_v4.executor import Executor
        from scripts.router_v4.runtime import Fabric
        self._d = tempfile.TemporaryDirectory()
        return Executor(Fabric(), root=self._d.name)

    def test_mot_phu_thuoc_thi_doc_o_worktree_do(self):
        ex = self._ex()
        self.assertEqual(ex._noi_doc_phu_thuoc({"T3": "C:/wt/T3"}), "C:/wt/T3")

    def test_nhieu_worktree_khac_nhau_thi_khong_doan_bua(self):
        ex = self._ex()
        self.assertEqual(
            ex._noi_doc_phu_thuoc({"A": "C:/wt/A", "B": "C:/wt/B"}), "")

    def test_khong_phu_thuoc_co_ghi_thi_rong(self):
        ex = self._ex()
        self.assertEqual(ex._noi_doc_phu_thuoc({"A": ""}), "")
        self.assertEqual(ex._noi_doc_phu_thuoc(None), "")
