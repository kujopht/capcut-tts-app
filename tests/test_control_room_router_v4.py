"""Control Room hợp nhất trên Router V4 — nguồn dữ liệu + chỉ báo lỗi.

Khoá lại hai sửa lỗi của lần hợp nhất:

  1. Danh sách worker đến từ **Fabric V4** (trạng thái runtime thật), không
     từ bảng SQLite của tầng V3 vốn có thể rỗng/cũ. Nhưng nguồn phải TIÊM
     ĐƯỢC — một `store` tiêm tường minh nghĩa là "đọc đúng nguồn này".
  2. `refresh_state()` KHÔNG được nuốt `Exception`. Nó phải giữ TUI sống VÀ
     đưa ra chỉ báo lỗi đã lọc bí mật.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.router_v3.control_room.state_reader import StateReader
from scripts.router_v3.control_room.widgets.status_bar import StatusBarWidget
from scripts.router_v3.pool.store import PoolStore


class TestNguonWorker(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.root = Path(self._d.name)

    def tearDown(self):
        try:
            self._d.cleanup()
        except (OSError, PermissionError):
            pass

    def test_store_tiem_tuong_minh_thi_KHONG_voi_ra_may(self):
        """Bài kiểm quan trọng nhất về tính tất định.

        Một `store` được tiêm nghĩa là "đọc ĐÚNG nguồn này". Nếu tầng đọc
        vẫn với ra trạng thái toàn máy thì mọi bài kiểm Control Room trở
        thành phụ thuộc vào máy đang chạy — đã vấp thật: một bài kiểm dựng
        1 worker trong store tạm nhận về 11 runtime của máy.
        """
        st = PoolStore(root=self.root)
        st.ghi_worker({"worker_id": "CHI_MOT", "state": "READY",
                       "provider": "test"})
        sr = StateReader(root=self.root, store=st)
        self.assertFalse(sr.use_fabric)
        snap = sr.snapshot()
        self.assertEqual(snap.worker_source, "pool_store")
        self.assertEqual([w.id for w in snap.workers], ["CHI_MOT"])
        st.close()

    def test_khong_tiem_store_thi_dung_fabric(self):
        sr = StateReader(root=self.root)
        self.assertTrue(sr.use_fabric)

    def test_ep_use_fabric_ke_ca_khi_co_store(self):
        st = PoolStore(root=self.root)
        sr = StateReader(root=self.root, store=st, use_fabric=True)
        self.assertTrue(sr.use_fabric)
        st.close()

    def test_fabric_tiem_duoc_de_kiem_tat_dinh(self):
        """Fabric giả -> chiếu ra đúng runtime của nó, không dò máy."""
        from scripts.router_v4.runtime import (Fabric, ModelCapability,
                                               RuntimeStatus, WorkerRuntime)
        f = Fabric()
        f.add_model(ModelCapability(model_id="m1", model_family="g",
                                    provider="antigravity",
                                    capabilities=frozenset({"repo_read"})))
        for i in (1, 2):
            f.add_runtime(WorkerRuntime(
                runtime_id=f"AG{i:02d}", provider="antigravity",
                account_id=f"acct-{i}", auth_profile=f"p{i}",
                supported_models=("m1",), status=RuntimeStatus.IDLE))
        f.validate()
        sr = StateReader(root=self.root, fabric=f, use_fabric=True)
        snap = sr.snapshot()
        self.assertEqual(snap.worker_source, "fabric_v4")
        self.assertEqual(sorted(w.id for w in snap.workers), ["AG01", "AG02"])

    def test_khe_chua_cap_phat_hien_OFFLINE_chu_khong_bi_bo_di(self):
        """Khe chưa cấp phát phải HIỆN RA (kèm lý do), không bị ẩn — ẩn đi
        thì người vận hành không biết mình còn khe nào để cấp phát."""
        from scripts.router_v3.control_room.state_reader import WorkerState
        from scripts.router_v4.runtime import (Fabric, ModelCapability,
                                               RuntimeStatus, WorkerRuntime)
        f = Fabric()
        f.add_model(ModelCapability(model_id="m1", model_family="g",
                                    provider="antigravity",
                                    capabilities=frozenset({"repo_read"})))
        f.add_runtime(WorkerRuntime(
            runtime_id="AG07", provider="antigravity", account_id="a7",
            auth_profile="p7", supported_models=("m1",),
            needs_provisioning="chưa có hồ sơ Windows AG07"))
        f.validate()
        snap = StateReader(root=self.root, fabric=f, use_fabric=True).snapshot()
        w = next(w for w in snap.workers if w.id == "AG07")
        self.assertEqual(w.state, WorkerState.OFFLINE)
        self.assertIn("AG07", w.detail)

    def test_khong_bia_quota_cho_nguon_CHUA_DO(self):
        """`declared` = lấy từ UI nhà cung cấp, CHƯA đo -> phải là UNKNOWN.
        Hiện "75%" cho một con số chưa đo là bịa số liệu."""
        from scripts.router_v4.runtime import (Fabric, ModelCapability,
                                               QuotaPool, RuntimeStatus,
                                               Source, WorkerRuntime)
        for nguon, mong_doi in ((Source.DECLARED, "UNKNOWN"),
                                (Source.UNKNOWN, "UNKNOWN"),
                                (Source.PROBED, "probed")):
            with self.subTest(nguon=nguon):
                f = Fabric()
                f.pool_groups.add("g")
                f.add_model(ModelCapability(
                    model_id="m1", model_family="g", provider="antigravity",
                    capabilities=frozenset({"repo_read"}), quota_pool="g"))
                f.add_runtime(WorkerRuntime(
                    runtime_id="AG01", provider="antigravity",
                    account_id="acct-1", auth_profile="p1",
                    supported_models=("m1",), status=RuntimeStatus.IDLE))
                f.add_pool(QuotaPool(pool_id="acct-1:g", account_id="acct-1",
                                     member_models=frozenset({"m1"}),
                                     remaining_estimate=0.75, source=nguon))
                f.validate()
                snap = StateReader(root=self.root, fabric=f,
                                   use_fabric=True).snapshot()
                w = snap.workers[0]
                if mong_doi == "UNKNOWN":
                    self.assertEqual(w.quota_display, "UNKNOWN")
                else:
                    self.assertIn("probed", w.quota_display)


class TestChiBaoLoi(unittest.TestCase):
    """`refresh_state` phải giữ TUI sống NHƯNG không bao giờ im lặng."""

    def test_refresh_state_khong_con_nuot_Exception(self):
        """Kiểm trên MÃ: không được còn `except Exception: pass` trơn."""
        import ast
        p = (Path(__file__).resolve().parents[1] / "scripts" / "router_v3"
             / "control_room" / "app.py")
        cay = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        ham = next((n for n in ast.walk(cay)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "refresh_state"), None)
        self.assertIsNotNone(ham, "không tìm thấy refresh_state")
        for node in ast.walk(ham):
            if not isinstance(node, ast.ExceptHandler):
                continue
            chi_pass = all(isinstance(x, ast.Pass) for x in node.body)
            self.assertFalse(
                chi_pass,
                "refresh_state vẫn nuốt lỗi bằng `pass` trơn — bảng điều "
                "khiển sẽ vẽ lại số liệu CŨ và trông bình thường trong khi "
                "việc đọc đã hỏng")

    def test_refresh_state_co_dem_loi_va_bao_ra(self):
        import ast
        p = (Path(__file__).resolve().parents[1] / "scripts" / "router_v3"
             / "control_room" / "app.py")
        t = p.read_text(encoding="utf-8", errors="replace")
        self.assertIn("_doc_that_bai", t, "phải đếm số lần đọc thất bại")
        self.assertIn("redact(", t, "thông điệp lỗi phải được lọc bí mật")
        self.assertIn("_bao_loi", t, "phải có đường đưa lỗi ra giao diện")

    def test_status_bar_hien_chi_bao_khi_co_loi(self):
        sb = StatusBarWidget()
        self.assertTrue(sb.healthy)
        sb.set_health(errors=["fabric_probe: OSError: hong"], failures=3,
                      source="", last_error="OSError: hong")
        self.assertFalse(sb.healthy)

    def test_status_bar_phan_biet_nguon_that_va_du_phong(self):
        sb = StatusBarWidget()
        sb.set_health(errors=[], source="fabric_v4")
        self.assertTrue(sb.healthy)
        sb.set_health(errors=[], source="pool_store")
        self.assertTrue(sb.healthy)

    def test_loi_doc_fabric_di_vao_snapshot_khong_bi_nuot(self):
        """Dò fabric hỏng -> snapshot mang lỗi VÀ rơi về pool_store, chứ
        không im lặng trả danh sách rỗng."""
        d = tempfile.mkdtemp()
        try:
            sr = StateReader(root=Path(d))
            def _no(*a, **k):
                raise OSError("khong doc duoc cau hinh fabric")
            import scripts.router_v4.fabric_config as FC
            goc = FC.nap
            try:
                FC.nap = _no
                snap = sr.snapshot()
            finally:
                FC.nap = goc
            self.assertEqual(snap.worker_source, "pool_store")
            self.assertTrue(snap.errors, "lỗi dò fabric phải hiện trong snapshot")
            self.assertIn("fabric_probe", snap.errors[0])
        finally:
            # Dong SQLite truoc khi don: tren Windows mot handle con mo lam
            # `TemporaryDirectory` nem PermissionError va bai kiem "hong" vi
            # ly do khong lien quan gi den thu no kiem.
            try:
                sr.store.close()
            except Exception:
                pass
            import shutil
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
