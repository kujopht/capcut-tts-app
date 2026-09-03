"""12 bài kiểm bắt buộc của Router V4 (mission #20) — TẤT ĐỊNH, không mạng.

Mỗi lớp dưới đây khoá một tính chất mà nếu mất đi thì cả kiến trúc V4 mất
nghĩa. Chúng dựng fabric bằng tay (không đọc `config/fabric.json`) để bài
kiểm không vỡ khi ai đó chỉnh cấu hình thật — và ngược lại, để một thay đổi
cấu hình không âm thầm làm bài kiểm nói dối.
"""
from __future__ import annotations

import time
import unittest
from typing import Optional

from scripts.router_v4.capabilities import Priority, Reasoning, Requirements
from scripts.router_v4.contract import ContractError, Execution, TaskContract
from scripts.router_v4.modes import (EscalationPolicy, Mode, chon_che_do,
                                     family_khac, hop_dong_review)
from scripts.router_v4.runtime import (Fabric, FabricError, ModelCapability,
                                       Placement, QuotaPool, RuntimeStatus,
                                       Source, WorkerRuntime)
from scripts.router_v4.scheduler import (Decision, Demand, NoEligiblePlacement,
                                         Scheduler, Weights)

T0 = 1_000_000.0


def _model(mid, *, family, caps, pool="", reasoning=Reasoning.MEDIUM,
           bench=0.7, provider="antigravity", latency=30.0, cost=0.5,
           source=Source.PROBED) -> ModelCapability:
    return ModelCapability(
        model_id=mid, model_family=family, provider=provider,
        capabilities=frozenset(caps),
        capability_source={c: source for c in caps},
        quota_pool=pool, reasoning=reasoning, benchmark_profile=bench,
        latency_profile=latency, cost_profile=cost)


def _rt(rid, *, models, account=None, provider="antigravity", conc=1,
        needs="") -> WorkerRuntime:
    return WorkerRuntime(
        runtime_id=rid, provider=provider, account_id=account or f"acct-{rid}",
        auth_profile=f"profile:{rid}", supported_models=tuple(models),
        concurrency=conc, status=RuntimeStatus.IDLE, needs_provisioning=needs)


def _contract(tid="T", **kw) -> TaskContract:
    req = kw.pop("req", None) or Requirements(repo_read=True)
    c = TaskContract(task_id=tid, objective=kw.pop("objective", "làm việc"),
                     requirements=req, **kw)
    c.validate()
    return c


# ===========================================================================
# 1. Lọc năng lực CỨNG
# ===========================================================================

class Test01LocNangLucCung(unittest.TestCase):
    """Việc cần video+audio -> worker không đa phương thức bị LOẠI, không
    phải bị 'cho điểm thấp'. Đây là ranh giới nhị phân."""

    def setUp(self):
        self.f = Fabric()
        self.f.add_model(_model("mm", family="gemini",
                                caps={"repo_read", "video", "audio",
                                      "structured_output"}))
        self.f.add_model(_model("van-ban", family="gpt",
                                caps={"repo_read", "coding",
                                      "structured_output"}, bench=0.99))
        self.f.add_runtime(_rt("R_MM", models=["mm"]))
        self.f.add_runtime(_rt("R_TXT", models=["van-ban"]))
        self.f.validate()
        self.s = Scheduler(self.f)

    def test_worker_khong_da_phuong_thuc_bi_loai(self):
        c = _contract(req=Requirements(repo_read=True, video=True, audio=True,
                                       structured_output=True))
        d = self.s.decide(c, now=T0)
        self.assertIsNotNone(d.selected)
        self.assertEqual(d.selected.model_id, "mm")
        bi_loai = {x.placement.key: x for x in d.candidates if not x.eligible}
        self.assertIn("R_TXT/van-ban", bi_loai)
        self.assertIn("thiếu năng lực", bi_loai["R_TXT/van-ban"].reason)

    def test_diem_cao_khong_cuu_duoc_thieu_nang_luc(self):
        """`van-ban` có benchmark 0.99 — cao nhất — vẫn bị loại."""
        c = _contract(req=Requirements(repo_read=True, video=True,
                                       structured_output=True))
        d = self.s.decide(c, now=T0)
        self.assertEqual(d.selected.runtime_id, "R_MM")

    def test_khong_ai_thoa_thi_fail_closed(self):
        c = _contract(req=Requirements(repo_read=True, video=True, audio=True,
                                       image=True, shell=True))
        d = self.s.decide(c, now=T0)
        self.assertIsNone(d.selected)
        self.assertIn("Fail closed", d.reason)
        with self.assertRaises(NoEligiblePlacement):
            self.s.select(c, now=T0)


# ===========================================================================
# 2. Phân biệt BỂ QUOTA
# ===========================================================================

class Test02PhanBietBeQuota(unittest.TestCase):
    """Bể Gemini cạn, bể Claude/GPT còn nhiều -> chọn model đổi theo."""

    def setUp(self):
        self.f = Fabric()
        self.f.pool_groups |= {"gem", "claude_gpt"}
        self.f.add_model(_model("gemini-x", family="gemini", pool="gem",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.75))
        self.f.add_model(_model("claude-x", family="claude", pool="claude_gpt",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.75))
        self.f.add_runtime(_rt("AG", models=["gemini-x", "claude-x"],
                               account="acct-ag", conc=2))
        self.gem = QuotaPool(pool_id="acct-ag:gem", account_id="acct-ag",
                             member_models=frozenset({"gemini-x"}),
                             remaining_estimate=1.0, source=Source.PROBED)
        self.cg = QuotaPool(pool_id="acct-ag:claude_gpt", account_id="acct-ag",
                            member_models=frozenset({"claude-x"}),
                            remaining_estimate=1.0, source=Source.PROBED)
        self.f.add_pool(self.gem)
        self.f.add_pool(self.cg)
        self.f.validate()
        self.s = Scheduler(self.f)

    def test_be_gemini_can_thi_chon_claude(self):
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True))
        self.gem.cap_nhat_uoc_luong(0.02, source=Source.PROBED, now=T0)
        self.cg.cap_nhat_uoc_luong(0.95, source=Source.PROBED, now=T0)
        self.assertEqual(self.s.decide(c, now=T0).selected.model_id, "claude-x")

    def test_be_claude_can_thi_chon_gemini(self):
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True))
        self.gem.cap_nhat_uoc_luong(0.95, source=Source.PROBED, now=T0)
        self.cg.cap_nhat_uoc_luong(0.02, source=Source.PROBED, now=T0)
        self.assertEqual(self.s.decide(c, now=T0).selected.model_id, "gemini-x")

    def test_nguon_unknown_khong_dieu_khien_dinh_tuyen(self):
        """Số dư `UNKNOWN` phải trung lập (0.5), không được vừa bịa vừa
        quyết đoán."""
        p = QuotaPool(pool_id="x", account_id="y", source=Source.UNKNOWN,
                      remaining_estimate=0.0)
        self.assertEqual(p.health, 0.5)


# ===========================================================================
# 3. BỂ QUOTA DÙNG CHUNG
# ===========================================================================

class Test03BeQuotaDungChung(unittest.TestCase):
    """GPT-OSS và Claude rút CÙNG một bể — dùng GPT-OSS không 'miễn phí'."""

    def setUp(self):
        self.f = Fabric()
        self.f.pool_groups |= {"claude_gpt", "gem"}
        self.f.add_model(_model("opus", family="claude", pool="claude_gpt",
                                caps={"repo_read", "coding", "structured_output"},
                                reasoning=Reasoning.HIGH, bench=0.9, cost=0.9))
        self.f.add_model(_model("gpt-oss", family="gpt", pool="claude_gpt",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.55, cost=0.5))
        self.f.add_model(_model("gemini", family="gemini", pool="gem",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.7, cost=0.3))
        self.f.add_runtime(_rt("AG", models=["opus", "gpt-oss", "gemini"],
                               account="acct-ag", conc=3))
        self.cg = QuotaPool(pool_id="acct-ag:claude_gpt", account_id="acct-ag",
                            member_models=frozenset({"opus", "gpt-oss"}),
                            source=Source.PROBED)
        self.gem = QuotaPool(pool_id="acct-ag:gem", account_id="acct-ag",
                             member_models=frozenset({"gemini"}),
                             source=Source.PROBED)
        self.f.add_pool(self.cg)
        self.f.add_pool(self.gem)
        self.f.validate()
        self.s = Scheduler(self.f)

    def test_gpt_oss_va_claude_cung_be(self):
        self.assertEqual(self.f.pool_cua_placement(Placement("AG", "opus")).pool_id,
                         self.f.pool_cua_placement(Placement("AG", "gpt-oss")).pool_id)
        self.assertNotEqual(
            self.f.pool_cua_placement(Placement("AG", "gemini")).pool_id,
            self.f.pool_cua_placement(Placement("AG", "opus")).pool_id)

    def test_tieu_thu_gpt_oss_lam_can_be_cua_claude(self):
        """Chạy GPT-OSS phải ghi tiêu thụ vào ĐÚNG bể Claude dùng chung."""
        truoc = self.cg.so_luot_trong_cua_so(now=T0)
        self.f.mark_finished("AG", "t1", ok=True, seconds=1.0,
                             model_id="gpt-oss", now=T0)
        self.assertEqual(self.cg.so_luot_trong_cua_so(now=T0), truoc + 1)
        self.assertEqual(self.gem.so_luot_trong_cua_so(now=T0), 0)

    def test_be_dung_chung_can_thi_ca_hai_model_bi_ha_diem(self):
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True))
        self.cg.cap_nhat_uoc_luong(0.01, source=Source.PROBED, now=T0)
        self.gem.cap_nhat_uoc_luong(0.99, source=Source.PROBED, now=T0)
        d = self.s.decide(c, now=T0)
        self.assertEqual(d.selected.model_id, "gemini",
                         "bể Claude/GPT cạn phải kéo CẢ opus lẫn gpt-oss xuống")


# ===========================================================================
# 4. Đồng thời theo TÀI KHOẢN
# ===========================================================================

class Test04DongThoiTheoTaiKhoan(unittest.TestCase):
    def setUp(self):
        self.f = Fabric()
        self.f.add_model(_model("m", family="gemini",
                                caps={"repo_read", "coding", "structured_output"}))
        self.f.add_runtime(_rt("AG01", models=["m"], conc=1))
        self.f.add_runtime(_rt("AG02", models=["m"], conc=1))
        self.f.validate()
        self.s = Scheduler(self.f)
        self.c = _contract(req=Requirements(repo_read=True, coding=True,
                                            structured_output=True))

    def test_runtime_ban_thi_chon_runtime_khac(self):
        dau = self.s.decide(self.c, now=T0).selected
        self.f.mark_started(dau.runtime_id, "viec-1")
        sau = self.s.decide(self.c, now=T0).selected
        self.assertIsNotNone(sau)
        self.assertNotEqual(sau.runtime_id, dau.runtime_id)

    def test_het_cho_toan_bo_thi_khong_ai_duoc_chon(self):
        self.f.mark_started("AG01", "a")
        self.f.mark_started("AG02", "b")
        d = self.s.decide(self.c, now=T0)
        self.assertIsNone(d.selected)
        self.assertTrue(any("đầy chỗ" in x.reason for x in d.candidates))

    def test_concurrency_lon_hon_1_van_nhan_them(self):
        self.f.runtimes["AG01"].concurrency = 2
        self.f.mark_started("AG01", "a")
        self.f.mark_started("AG02", "b")
        self.assertEqual(self.s.decide(self.c, now=T0).selected.runtime_id, "AG01")


# ===========================================================================
# 5. Giữ năng lực KHAN HIẾM
# ===========================================================================

class Test05GiuNangLucKhanHiem(unittest.TestCase):
    """Hàng đợi sắp tới có nhiều việc đa phương thức -> đừng tiêu worker đa
    phương thức (thứ duy nhất làm được) cho một việc văn bản thuần mà worker
    khác cũng làm được."""

    def setUp(self):
        self.f = Fabric()
        self.f.add_model(_model("gemini-mm", family="gemini",
                                caps={"repo_read", "coding", "video", "audio",
                                      "image", "structured_output"}, bench=0.8))
        self.f.add_model(_model("claude-txt", family="claude", provider="codex",
                                caps={"repo_read", "coding",
                                      "structured_output"}, bench=0.78))
        self.f.add_runtime(_rt("R_G", models=["gemini-mm"]))
        self.f.add_runtime(_rt("R_C", models=["claude-txt"], provider="codex"))
        self.f.validate()
        self.s = Scheduler(self.f)
        self.viec_van_ban = _contract(
            "kien-truc", req=Requirements(repo_read=True, coding=True,
                                          structured_output=True))

    def test_khong_co_nhu_cau_thi_khong_giu_cho(self):
        """Hàng đợi rỗng: giữ chỗ chỉ làm chậm việc hiện tại."""
        d = self.s.decide(self.viec_van_ban, demand=None, now=T0)
        self.assertEqual(d.selected.model_id, "gemini-mm",
                         "không có nhu cầu sắp tới thì model điểm cao nhất thắng")

    def test_nhu_cau_video_lon_thi_nhuong_worker_da_phuong_thuc(self):
        sap_toi = [
            _contract(f"video-{i}",
                      req=Requirements(repo_read=True, video=True,
                                       structured_output=True))
            for i in range(30)
        ] + [self.viec_van_ban]
        d = self.s.decide(self.viec_van_ban,
                          demand=Demand.from_contracts(sap_toi), now=T0)
        self.assertEqual(d.selected.model_id, "claude-txt",
                         "phải để dành Gemini cho 30 việc video sắp tới")

    def test_viec_CAN_video_van_duoc_dung_worker_da_phuong_thuc(self):
        """Giữ chỗ không được cản chính việc cần năng lực đó."""
        sap_toi = [_contract(f"video-{i}",
                             req=Requirements(repo_read=True, video=True,
                                              structured_output=True))
                   for i in range(30)]
        c = _contract("video-now", req=Requirements(repo_read=True, video=True,
                                                    structured_output=True))
        d = self.s.decide(c, demand=Demand.from_contracts(sap_toi), now=T0)
        self.assertEqual(d.selected.model_id, "gemini-mm")


# ===========================================================================
# 6. Đa dạng HỌ MODEL
# ===========================================================================

class Test06DaDangHoModel(unittest.TestCase):
    def setUp(self):
        self.f = Fabric()
        self.f.add_model(_model("gemini-a", family="gemini",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.75))
        self.f.add_model(_model("codex-a", family="codex", provider="codex",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.75))
        self.f.add_runtime(_rt("R_G1", models=["gemini-a"]))
        self.f.add_runtime(_rt("R_G2", models=["gemini-a"]))
        self.f.add_runtime(_rt("R_C", models=["codex-a"], provider="codex"))
        self.f.validate()
        self.s = Scheduler(self.f)

    def test_reviewer_khac_ho_duoc_thuong_diem(self):
        c = _contract("review", req=Requirements(repo_read=True, coding=True,
                                                 structured_output=True))
        d = self.s.decide(c, author_family="gemini", now=T0)
        self.assertEqual(self.f.model(d.selected.model_id).model_family, "codex")
        diem = {x.placement.key: x.score for x in d.candidates if x.eligible}
        self.assertGreater(diem["R_C/codex-a"].independence_bonus, 0.0)
        self.assertEqual(diem["R_G1/gemini-a"].independence_bonus, 0.0)

    def test_tai_khoan_khac_cung_model_KHONG_phai_doc_lap(self):
        """Mission #10 nói thẳng điều này. R_G2 là tài khoản khác nhưng chạy
        đúng model của tác giả — không được coi là độc lập."""
        c = _contract("review", req=Requirements(repo_read=True, coding=True,
                                                 structured_output=True))
        d = self.s.decide(c, author_family="gemini", now=T0)
        diem = {x.placement.key: x.score for x in d.candidates if x.eligible}
        self.assertEqual(diem["R_G2/gemini-a"].independence_bonus, 0.0)
        self.assertFalse(family_khac("gemini", "gemini"))
        self.assertTrue(family_khac("gemini", "codex"))

    def test_da_dang_la_tin_hieu_chu_khong_phai_rao_cung(self):
        """Chỉ còn cùng họ thì vẫn review được — có review hơn không có."""
        self.f.runtimes["R_C"].status = RuntimeStatus.OFFLINE
        c = _contract("review", req=Requirements(repo_read=True, coding=True,
                                                 structured_output=True))
        d = self.s.decide(c, author_family="gemini", now=T0)
        self.assertIsNotNone(d.selected)
        self.assertEqual(self.f.model(d.selected.model_id).model_family, "gemini")

    def test_hop_dong_review_loai_ho_tac_gia_va_khong_cho_ghi(self):
        goc = _contract("impl", req=Requirements(repo_read=True, repo_write=True,
                                                 coding=True),
                        allowed_scope=("pkg",),
                        execution=Execution(worktree_required=True))
        r = hop_dong_review(goc, author_family="gemini")
        self.assertEqual(r.requirements.exclude_families, ("gemini",))
        self.assertFalse(r.requirements.repo_write)
        self.assertEqual(r.allowed_scope, ())


# ===========================================================================
# 7. Lease hết hạn -> thu hồi được
# ===========================================================================

class Test07LeaseHetHan(unittest.TestCase):
    def setUp(self):
        import tempfile
        from scripts.router_v4.leases import LeaseStore
        self._d = tempfile.TemporaryDirectory()
        self.ls = LeaseStore(root=self._d.name, ttl=30.0)

    def tearDown(self):
        self.ls.close()
        try:
            self._d.cleanup()
        except (OSError, PermissionError):
            pass

    def test_hai_chu_khong_cung_giu_mot_runtime(self):
        self.assertIsNotNone(self.ls.acquire("AG01", "chu-A", now=T0))
        self.assertIsNone(self.ls.acquire("AG01", "chu-B", now=T0 + 1))

    def test_lease_het_han_thi_ben_kia_cuop_duoc(self):
        self.ls.acquire("AG01", "chu-A", task_id="t1", now=T0)
        self.assertIsNone(self.ls.acquire("AG01", "chu-B", now=T0 + 10))
        l = self.ls.acquire("AG01", "chu-B", now=T0 + 31)
        self.assertIsNotNone(l, "lease chết phải thu hồi được")
        self.assertEqual(l.owner_id, "chu-B")

    def test_nhip_tim_giu_duoc_lease(self):
        self.ls.acquire("AG01", "chu-A", now=T0)
        self.assertTrue(self.ls.heartbeat("AG01", "chu-A", now=T0 + 20))
        self.assertIsNone(self.ls.acquire("AG01", "chu-B", now=T0 + 40))

    def test_nhip_tim_that_bai_sau_khi_bi_cuop(self):
        """Chủ cũ PHẢI biết mình mất quyền — nếu không, hai tiến trình cùng
        tưởng mình sở hữu runtime (chế độ hỏng 'hai chủ')."""
        self.ls.acquire("AG01", "chu-A", now=T0)
        self.ls.acquire("AG01", "chu-B", now=T0 + 31)
        self.assertFalse(self.ls.heartbeat("AG01", "chu-A", now=T0 + 32))

    def test_reap_don_lease_chet(self):
        self.ls.acquire("AG01", "chu-A", task_id="t1", now=T0)
        self.assertEqual(self.ls.reap(now=T0 + 5), [])
        chet = self.ls.reap(now=T0 + 31)
        self.assertEqual([l.runtime_id for l in chet], ["AG01"])
        self.assertEqual(self.ls.all(), [])


# ===========================================================================
# 8. Thử lại CÓ CHẶN + cooldown
# ===========================================================================

class Test08ThuLaiCoChan(unittest.TestCase):
    def setUp(self):
        self.f = Fabric()
        self.f.add_model(_model("m", family="gemini",
                                caps={"repo_read", "coding", "structured_output"}))
        self.f.add_runtime(_rt("R", models=["m"]))
        self.f.validate()
        self.s = Scheduler(self.f)
        self.c = _contract(req=Requirements(repo_read=True, coding=True,
                                            structured_output=True))

    def test_hong_lien_tuc_dua_runtime_vao_cooldown(self):
        from scripts.router_v4.runtime import NGUONG_COOLDOWN
        for i in range(NGUONG_COOLDOWN):
            self.f.mark_finished("R", f"t{i}", ok=False, seconds=1.0,
                                 model_id="m", now=T0)
        r = self.f.runtime("R")
        self.assertTrue(r.dang_cooldown(now=T0))
        self.assertEqual(r.trang_thai_hien_tai(now=T0), RuntimeStatus.COOLDOWN)
        self.assertIsNone(self.s.decide(self.c, now=T0).selected)

    def test_cooldown_backoff_tang_dan_chu_khong_lap_lai(self):
        from scripts.router_v4.runtime import BACKOFF_COOLDOWN, NGUONG_COOLDOWN
        for i in range(NGUONG_COOLDOWN):
            self.f.mark_finished("R", f"t{i}", ok=False, seconds=1.0,
                                 model_id="m", now=T0)
        dau = self.f.runtime("R").cooldown_until - T0
        self.f.mark_finished("R", "tx", ok=False, seconds=1.0, model_id="m",
                             now=T0)
        sau = self.f.runtime("R").cooldown_until - T0
        self.assertGreater(sau, dau,
                           "backoff phải DÀI HƠN, không lặp cùng độ dài")

    def test_cooldown_het_thi_dung_lai_duoc(self):
        from scripts.router_v4.runtime import NGUONG_COOLDOWN
        for i in range(NGUONG_COOLDOWN):
            self.f.mark_finished("R", f"t{i}", ok=False, seconds=1.0,
                                 model_id="m", now=T0)
        het = self.f.runtime("R").cooldown_until
        self.assertIsNotNone(self.s.decide(self.c, now=het + 1).selected)

    def test_thanh_cong_xoa_dem_hong(self):
        self.f.mark_finished("R", "t1", ok=False, seconds=1.0, model_id="m",
                             now=T0)
        self.f.mark_finished("R", "t2", ok=True, seconds=1.0, model_id="m",
                             now=T0)
        self.assertEqual(self.f.runtime("R").consecutive_failures, 0)


# ===========================================================================
# 9. Phong bì kết quả GỌN
# ===========================================================================

class Test09PhongBiGon(unittest.TestCase):
    def setUp(self):
        import tempfile
        from scripts.router_v4.envelope import RawLogStore
        self._d = tempfile.TemporaryDirectory()
        self.logs = RawLogStore(root=self._d.name)

    def tearDown(self):
        try:
            self._d.cleanup()
        except (OSError, PermissionError):
            pass

    def test_nhat_ky_khong_lo_khong_vao_ngu_canh(self):
        from scripts.router_v4.envelope import from_worker_output
        rac = "x" * 200_000
        tho = (rac + '\n{"status":"ok","summary":"' + "s" * 5000 +
               '","changes":["a.py"]}\n' + rac)
        pb = from_worker_output("T1", tho, worker="R", model="m",
                                seconds=1.0, log_store=self.logs)
        goi = __import__("json").dumps(pb.to_dict())
        self.assertLess(len(goi), 6000,
                        f"phong bì phải GỌN, đang {len(goi)} byte")
        self.assertLessEqual(len(pb.summary), 800)
        self.assertTrue(pb.raw_log_ref)
        self.assertGreater(pb.truncated_bytes, 100_000)

    def test_nhat_ky_tho_van_lay_lai_duoc(self):
        from scripts.router_v4.envelope import from_worker_output
        tho = 'DAU-VET-DOC-NHAT {"status":"ok","summary":"xong"}'
        pb = from_worker_output("T2", tho, log_store=self.logs)
        lai = self.logs.read(pb.raw_log_ref)
        self.assertIn("DAU-VET-DOC-NHAT", lai)

    def test_khong_doc_duoc_json_thi_KHONG_bao_ok(self):
        from scripts.router_v4.envelope import from_worker_output
        pb = from_worker_output("T3", "tôi đã làm xong hết rồi!",
                                log_store=self.logs)
        self.assertEqual(pb.status, "failed")
        self.assertEqual(pb.failure_reason, "no_json_block")

    def test_requires_decision_chan_trang_thai_ok(self):
        from scripts.router_v4.envelope import from_worker_output
        pb = from_worker_output(
            "T4", '{"status":"ok","summary":"xong nửa chừng",'
                  '"requires_decision":true,"decision_request":"dùng A hay B?"}',
            log_store=self.logs)
        self.assertEqual(pb.status, "blocked")
        self.assertTrue(pb.requires_decision)
        self.assertIn("A hay B", pb.decision_request)

    def test_bi_mat_bi_loc_khoi_phong_bi(self):
        from scripts.router_v4.envelope import from_worker_output
        pb = from_worker_output(
            "T5", '{"status":"ok","summary":"token la ghp_' + "A" * 30 + '"}',
            log_store=self.logs)
        self.assertNotIn("ghp_" + "A" * 30, pb.summary)

    def test_raw_log_ref_khong_di_ngang_thu_muc(self):
        self.assertIsNone(self.logs.read("../../../etc/passwd"))


# ===========================================================================
# 10. Phạm vi việc — worker không tự mở rộng
# ===========================================================================

class Test10PhamViViec(unittest.TestCase):
    def test_doi_tep_ngoai_allowed_scope_bi_bat(self):
        c = _contract("impl", req=Requirements(repo_read=True, repo_write=True,
                                               coding=True),
                      allowed_scope=("pkg/a",),
                      execution=Execution(worktree_required=True))
        self.assertEqual(c.scope_violations(["pkg/a/x.py"]), [])
        self.assertEqual(c.scope_violations(["pkg/b/y.py"]), ["pkg/b/y.py"])

    def test_forbidden_scope_thang_allowed_scope(self):
        with self.assertRaises(ContractError) as ctx:
            TaskContract(task_id="x", objective="o",
                         requirements=Requirements(repo_write=True, repo_read=True),
                         allowed_scope=(".github/workflows",),
                         execution=Execution(worktree_required=True)).validate()
        self.assertIn("Cấm luôn thắng", str(ctx.exception))

    def test_duong_cam_luon_duoc_them_du_hop_dong_khong_khai(self):
        c = _contract("impl", req=Requirements(repo_read=True, repo_write=True),
                      allowed_scope=("pkg",),
                      execution=Execution(worktree_required=True))
        self.assertIn(".git", c.forbidden_scope)
        self.assertEqual(c.scope_violations([".git/config"]), [".git/config"])

    def test_viec_chi_doc_ma_sua_tep_la_vi_pham(self):
        c = _contract("recon", req=Requirements(repo_read=True))
        self.assertEqual(c.scope_violations(["bat_ky.py"]), ["bat_ky.py"])

    def test_repo_write_khong_worktree_bi_tu_choi(self):
        with self.assertRaises(ContractError) as ctx:
            TaskContract(task_id="x", objective="o",
                         requirements=Requirements(repo_write=True, repo_read=True),
                         allowed_scope=("pkg",)).validate()
        self.assertIn("worktree_required", str(ctx.exception))

    def test_repo_write_khong_pham_vi_bi_tu_choi(self):
        with self.assertRaises(ContractError):
            TaskContract(task_id="x", objective="o",
                         requirements=Requirements(repo_write=True, repo_read=True),
                         execution=Execution(worktree_required=True)).validate()


# ===========================================================================
# 11. Lập lịch TẤT ĐỊNH
# ===========================================================================

class Test11LapLichTatDinh(unittest.TestCase):
    def _fabric(self) -> Fabric:
        f = Fabric()
        for i in range(4):
            f.add_model(_model(f"m{i}", family=f"fam{i % 2}",
                               caps={"repo_read", "coding", "structured_output"},
                               bench=0.7))
        for i in range(4):
            f.add_runtime(_rt(f"R{i}", models=[f"m{i}"]))
        f.validate()
        return f

    def test_cung_dau_vao_cho_cung_quyet_dinh(self):
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True))
        ket = set()
        for _ in range(12):
            s = Scheduler(self._fabric())
            ket.add(s.decide(c, now=T0).selected.key)
        self.assertEqual(len(ket), 1, f"không tất định: {ket}")

    def test_diem_bang_nhau_pha_hoa_theo_ten(self):
        """Điểm hoà phải phá bằng khoá placement, không phải thứ tự dict."""
        f = self._fabric()
        s = Scheduler(f)
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True))
        d = s.decide(c, now=T0)
        hoa = [x for x in d.candidates
               if x.eligible and abs(x.score.total - d.candidates[0].score.total) < 1e-9]
        if len(hoa) > 1:
            self.assertEqual(d.selected.key, min(x.placement.key for x in hoa))

    def test_trong_so_doi_thi_quyet_dinh_doi(self):
        """Trọng số phải THẬT SỰ điều khiển kết quả — nếu không, 'cấu hình
        được' chỉ là trang trí."""
        f = Fabric()
        f.add_model(_model("re-cham", family="a",
                           caps={"repo_read", "coding", "structured_output"},
                           bench=0.5, cost=0.0, latency=300.0))
        f.add_model(_model("dat-nhanh", family="b",
                           caps={"repo_read", "coding", "structured_output"},
                           bench=0.5, cost=1.0, latency=1.0))
        f.add_runtime(_rt("R1", models=["re-cham"]))
        f.add_runtime(_rt("R2", models=["dat-nhanh"], provider="codex"))
        f.validate()
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True))
        uu_tien_chi_phi = Scheduler(f, weights=Weights(expected_cost=100.0,
                                                       latency=0.0))
        uu_tien_do_tre = Scheduler(f, weights=Weights(expected_cost=0.0,
                                                      latency=100.0))
        self.assertEqual(uu_tien_chi_phi.decide(c, now=T0).selected.model_id,
                         "re-cham")
        self.assertEqual(uu_tien_do_tre.decide(c, now=T0).selected.model_id,
                         "dat-nhanh")

    def test_trong_so_la_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            Weights.from_dict({"khong_ton_tai": 1.0})


# ===========================================================================
# 12. Người vận hành GHIM (override)
# ===========================================================================

class Test12NguoiVanHanhGhim(unittest.TestCase):
    def setUp(self):
        self.f = Fabric()
        self.f.add_model(_model("manh", family="gemini",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.95))
        self.f.add_model(_model("yeu", family="gpt",
                                caps={"repo_read", "coding", "structured_output"},
                                bench=0.2))
        self.f.add_runtime(_rt("R_MANH", models=["manh"]))
        self.f.add_runtime(_rt("R_YEU", models=["yeu"]))
        self.f.validate()
        self.s = Scheduler(self.f)

    def test_ghim_runtime_duoc_ton_trong(self):
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True,
                                       pin_runtime="R_YEU"))
        d = self.s.decide(c, now=T0)
        self.assertEqual(d.selected.runtime_id, "R_YEU")
        self.assertTrue(d.pinned)
        self.assertIn("GHIM", d.reason)

    def test_ghim_model_duoc_ton_trong(self):
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True,
                                       pin_model="yeu"))
        self.assertEqual(self.s.decide(c, now=T0).selected.model_id, "yeu")

    def test_ghim_KHONG_mo_duoc_rao_nang_luc(self):
        """Ghim là override VẬN HÀNH, không phải cửa hậu an toàn. Ghim vào
        một model không đủ năng lực vẫn phải fail closed."""
        c = _contract(req=Requirements(repo_read=True, video=True,
                                       structured_output=True,
                                       pin_runtime="R_YEU"))
        d = self.s.decide(c, now=T0)
        self.assertIsNone(d.selected)

    def test_ghim_vao_runtime_offline_van_fail_closed(self):
        self.f.runtimes["R_YEU"].status = RuntimeStatus.OFFLINE
        c = _contract(req=Requirements(repo_read=True, coding=True,
                                       structured_output=True,
                                       pin_runtime="R_YEU"))
        self.assertIsNone(self.s.decide(c, now=T0).selected)


# ===========================================================================
# Bổ sung: bất biến an toàn của fabric
# ===========================================================================

class TestBatBienAnToan(unittest.TestCase):
    def test_hai_runtime_khong_dung_chung_auth_profile(self):
        f = Fabric()
        f.add_model(_model("m", family="g", caps={"repo_read"}))
        a = _rt("AG01", models=["m"])
        b = _rt("AG02", models=["m"])
        b.auth_profile = a.auth_profile
        f.add_runtime(a)
        f.add_runtime(b)
        with self.assertRaises(FabricError) as ctx:
            f.validate()
        self.assertIn("auth_profile", str(ctx.exception))

    def test_runtime_chua_cap_phat_khong_chiem_ho_so(self):
        f = Fabric()
        f.add_model(_model("m", family="g", caps={"repo_read"}))
        a = _rt("AG03", models=["m"], needs="chưa có hồ sơ")
        b = _rt("AG04", models=["m"], needs="chưa có hồ sơ")
        a.auth_profile = b.auth_profile = "profile:chung"
        f.add_runtime(a)
        f.add_runtime(b)
        f.validate()                          # khong duoc nem

    def test_dem_tai_khoan_khong_dem_placement(self):
        f = Fabric()
        for mid in ("m1", "m2", "m3"):
            f.add_model(_model(mid, family="g", caps={"repo_read"}))
        f.add_runtime(_rt("AG01", models=["m1", "m2", "m3"], account="acct-1"))
        f.validate()
        self.assertEqual(len(f.placements()), 3)
        self.assertEqual(f.dem_tai_khoan(), {"antigravity": 1},
                         "3 placement trên 1 tài khoản KHÔNG phải 3 tài khoản")

    def test_nang_luc_bao_trum_duoc_mo_rong(self):
        m = _model("m", family="g", caps={"video", "repo_write"})
        self.assertIn("multimodal", m.effective_capabilities)
        self.assertIn("repo_read", m.effective_capabilities)


class TestLeoThangCheDo(unittest.TestCase):
    def test_viec_thuong_la_SOLO(self):
        c = _contract(req=Requirements(repo_read=True))
        cd = chon_che_do(TaskContract.from_dict({**c.to_dict(), "impact": 0.2,
                                                 "uncertainty": 0.2}))
        self.assertIs(cd.mode, Mode.SOLO)

    def test_tac_dong_lon_thi_them_critic(self):
        c = _contract(req=Requirements(repo_read=True))
        cd = chon_che_do(TaskContract.from_dict({**c.to_dict(), "impact": 0.8,
                                                 "uncertainty": 0.4}))
        self.assertIs(cd.mode, Mode.PRIMARY_CRITIC)

    def test_tac_dong_lon_va_rat_bat_dinh_thi_chay_gia_thuyet_song_song(self):
        c = _contract(req=Requirements(repo_read=True))
        cd = chon_che_do(TaskContract.from_dict({**c.to_dict(), "impact": 0.9,
                                                 "uncertainty": 0.9}))
        self.assertIs(cd.mode, Mode.PARALLEL_HYPOTHESES)
        self.assertGreaterEqual(cd.replicas, 3)

    def test_lich_su_hong_day_len_leo_thang(self):
        c = TaskContract.from_dict({**_contract(req=Requirements(repo_read=True)).to_dict(),
                                    "impact": 0.4, "uncertainty": 0.4})
        self.assertIs(chon_che_do(c, failure_history=0).mode, Mode.SOLO)
        self.assertIs(chon_che_do(c, failure_history=3).mode,
                      Mode.PARALLEL_HYPOTHESES)

    def test_hop_dong_doi_review_thi_luon_it_nhat_la_critic(self):
        from scripts.router_v4.contract import Verification
        c = TaskContract(task_id="x", objective="o", impact=0.05,
                         uncertainty=0.05,
                         requirements=Requirements(repo_read=True),
                         verification=Verification(independent_review_required=True))
        c.validate()
        self.assertIs(chon_che_do(c).mode, Mode.PRIMARY_CRITIC)


if __name__ == "__main__":
    unittest.main()
