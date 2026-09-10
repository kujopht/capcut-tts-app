# -*- coding: utf-8 -*-
"""V0.6.1 — KHOÁ ĐỌC/GHI + SONG SONG THẬT cho toả (khuyết tật nghiệm thu tay #2).

Câu thật: "gọi 4 agent gemini 3.8, mỗi agent kiểm tra một phần khác nhau của
repo này: 1. README/docs 2. tests 3. source architecture 4. git history không
được trùng phạm vi nhau" → bốn con CHỈ ĐỌC bị tuần tự hoá vì (a) bộ phân rã xếp
"kiểm tra … tests" vào `testing` (GHI, worktree), (b) mọi con sao chép cùng một
khoá FILESYSTEM `README/docs`, (c) khoá không có chế độ — mọi khoá đều độc quyền.
Con 1 chết trong worktree (`tool_permission_denied`), con 2 hỏng `gate_diff` vì
một việc GHI không ghi gì.

Bài kiểm ở đây khoá từng luật mới và giữ nguyên các luật an toàn cũ cho GHI.
Không agent thật: `FakeExecutor` + fabric giả 4 runtime (4 tài khoản, 1 khe/khe).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center import locks as LK                             # noqa: E402
from scripts.control_center import toa as TOA                              # noqa: E402
from scripts.control_center.engine import ControlCenter                    # noqa: E402
from scripts.control_center.locks import GOC, READ, WRITE, LockManager     # noqa: E402
from scripts.control_center.model import LockKind, Project, TaskState      # noqa: E402
from scripts.control_center.planner import RulePlanner                     # noqa: E402
from scripts.control_center.store import ControlStore                      # noqa: E402
from scripts.router_v4.runtime import (Fabric, ModelCapability, QuotaPool,  # noqa: E402
                                       RuntimeStatus, Source, WorkerRuntime)
from scripts.tests.test_control_center_slice import kho_git_tam            # noqa: E402
from scripts.tests.test_toa_v061 import ExecTuyBien, _cho, _chay_toi_xong  # noqa: E402

CAU_KIEM_TRA = ("gọi 4 agent gemini 3.8, mỗi agent kiểm tra một phần khác nhau của repo này:\n"
                "1. README/docs\n2. tests\n3. source architecture\n4. git history\n"
                "không được trùng phạm vi nhau")
CAU_GHI = "gọi 2 agent, mỗi agent sửa một dòng trong web/index.txt"
FS = LockKind.FILESYSTEM


def fabric_gia_4() -> Fabric:
    """Bốn runtime, bốn tài khoản, mỗi cái MỘT khe — để 'bốn tài khoản phân
    biệt cùng lúc' là điều đo được, không phải may rủi."""
    f = Fabric()
    f.pool_groups.add("pool_a")
    for i in range(1, 5):
        tk = f"acct-{i}"
        f.add_pool(QuotaPool(pool_id=f"{tk}:pool_a", account_id=tk,
                             member_models=frozenset({"m-re"}),
                             remaining_estimate=0.8, source=Source.DECLARED))
    f.add_model(ModelCapability(
        model_id="m-re", model_family="ho-y", provider="antigravity",
        capabilities=frozenset({"coding", "repo_read", "repo_write",
                                "structured_output", "long_context"}),
        quota_pool="pool_a", benchmark_profile=0.6, latency_profile=8.0))
    for i in range(1, 5):
        f.add_runtime(WorkerRuntime(
            runtime_id=f"RT{i:02d}", provider="antigravity", account_id=f"acct-{i}",
            auth_profile=f"gia:acct-{i}", supported_models=("m-re",),
            concurrency=1, status=RuntimeStatus.IDLE))
    f.validate()
    return f


# ================================================================ khoa ======

class TestKhoaDocGhi(unittest.TestCase):

    def setUp(self):
        self.root = Path(kho_git_tam())
        self.st = ControlStore(root=self.root)
        self.st.luu_project(Project(project_id="demo", name="Demo", repo_path=str(self.root)))
        self.lm = LockManager(self.st)

    def tearDown(self):
        self.st.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_READ_READ_cung_pham_vi_song_chung(self):
        a = self.lm.xin("demo", [(FS, "docs", READ)], task_id="A")
        b = self.lm.xin("demo", [(FS, "docs", READ)], task_id="B")
        c = self.lm.xin("demo", [(FS, ".", READ)], task_id="C")      # doc ca kho
        self.assertTrue(a.granted and b.granted and c.granted)
        self.assertEqual(len(self.st.locks("demo")), 3)
        self.assertEqual({l.mode for l in self.st.locks("demo")}, {READ})

    def test_READ_WRITE_giao_pham_vi_tranh_chap_ca_hai_chieu(self):
        self.assertTrue(self.lm.xin("demo", [(FS, "docs", READ)], task_id="R").granted)
        w = self.lm.xin("demo", [(FS, "docs/guide", WRITE)], task_id="W")
        self.assertFalse(w.granted)
        self.assertEqual(w.conflict_holder_task, "R")
        self.assertIn("READ", w.reason)
        self.lm.tra("demo", "R")
        self.assertTrue(self.lm.xin("demo", [(FS, "docs/guide", WRITE)], task_id="W").granted)
        r2 = self.lm.xin("demo", [(FS, "docs", READ)], task_id="R2")
        self.assertFalse(r2.granted, "đọc `docs` trong khi `docs/guide` đang bị GHI -> chờ")

    def test_WRITE_WRITE_giao_pham_vi_tranh_chap_va_khong_giao_thi_song_chung(self):
        self.assertTrue(self.lm.xin("demo", [(FS, "web/admin", WRITE)], task_id="A").granted)
        self.assertFalse(self.lm.xin("demo", [(FS, "web/admin/queue", WRITE)], task_id="B").granted)
        self.assertFalse(self.lm.xin("demo", [(FS, "web", WRITE)], task_id="C").granted)
        self.assertTrue(self.lm.xin("demo", [(FS, "server/api", WRITE)], task_id="D").granted)
        self.assertTrue(self.lm.xin("demo", [(FS, "web/administration", WRITE)], task_id="E").granted)

    def test_goc_kho_giao_voi_moi_duong_dan(self):
        self.assertTrue(self.lm.xin("demo", [(FS, ".", WRITE)], task_id="ROOT").granted)
        self.assertFalse(self.lm.xin("demo", [(FS, "docs", READ)], task_id="R").granted)
        self.assertFalse(self.lm.xin("demo", [(FS, "tests", WRITE)], task_id="W").granted)

    def test_chuan_hoa_pham_vi(self):
        for a, b in (("docs/", "docs"), ("docs/**", "docs"), ("docs/*", "docs"),
                     ("Docs\\Sub", "docs/sub"), ("./tests", "tests"), (".", "."), ("*", "."),
                     ("/web/admin/", "web/admin")):
            with self.subTest(a=a):
                self.assertEqual(LK.chuan_hoa(a), b)
        self.assertEqual(LK.chuan_hoa(""), "")                    # rong = khong khoa
        self.assertTrue(LK.xung_dot(FS, "docs/**", "docs/guide/x.md"))
        self.assertFalse(LK.xung_dot(FS, "docs", "docs2"))
        self.assertTrue(LK.xung_dot(FS, "web/index.txt", "web"))
        self.assertFalse(LK.xung_dot(FS, "tests", "source"))
        # Tai nguyen rieng van rieng sau chuan hoa.
        self.assertEqual(len({LK.chuan_hoa(x) for x in ("docs/", "tests/", "server/", ".")}), 4)

    def test_git_doc_khong_giu_khoa_he_tep(self):
        g = self.lm.xin("demo", [(LockKind.GIT, "history", READ)], task_id="G")
        self.assertTrue(g.granted)
        # He tep van tu do ca doc ca ghi (o cho khac nhau); READ goc kho thi
        # PHAI cho vi goc giao voi `docs` dang bi GHI — do la luat, khong phai loi.
        self.assertTrue(self.lm.xin("demo", [(FS, "docs", WRITE)], task_id="W").granted)
        self.assertTrue(self.lm.xin("demo", [(FS, "tests", READ)], task_id="R").granted)
        self.assertFalse(self.lm.xin("demo", [(FS, ".", READ)], task_id="R0").granted)
        # Hai nguoi doc lich su git song chung; ghi worktree git khong dung history.
        self.assertTrue(self.lm.xin("demo", [(LockKind.GIT, "history", READ)], task_id="G2").granted)
        self.assertTrue(self.lm.xin("demo", [(LockKind.GIT, "worktree", WRITE)], task_id="GW").granted)
        self.assertFalse(self.lm.xin("demo", [(LockKind.GIT, "worktree", WRITE)], task_id="GW2").granted)
        self.assertFalse(LK.xung_dot(LockKind.GIT, "history", "worktree"))
        self.assertTrue(LK.xung_dot(LockKind.GIT, "*", "history"))

    def test_dang_cu_khong_che_do_la_WRITE(self):
        self.assertEqual(LK.doc_chuoi_tai_nguyen("FILESYSTEM:web/admin"), (FS, "web/admin", WRITE))
        self.assertEqual(LK.doc_chuoi_tai_nguyen("READ:FILESYSTEM:docs"), (FS, "docs", READ))
        self.assertEqual(LK.doc_chuoi_tai_nguyen("read:git:history"), (LockKind.GIT, "history", READ))
        self.assertIsNone(LK.doc_chuoi_tai_nguyen("LA:x"))
        self.assertEqual(LK.chuoi_tai_nguyen(FS, "docs", READ), "READ:FILESYSTEM:docs")
        a = self.lm.xin("demo", [(FS, "web")], task_id="A")             # 2-tuple = WRITE
        self.assertTrue(a.granted)
        self.assertEqual(self.st.locks("demo")[0].mode, WRITE)
        self.assertFalse(self.lm.xin("demo", [(FS, "web", READ)], task_id="B").granted)

    def test_cung_tai_nguyen_xin_ca_READ_va_WRITE_thi_giu_WRITE(self):
        self.assertTrue(self.lm.xin("demo", [(FS, "docs", READ), (FS, "docs", WRITE)],
                                    task_id="A").granted)
        ds = self.st.locks("demo")
        self.assertEqual([(l.resource, l.mode) for l in ds], [("docs", WRITE)])

    def test_tra_va_reclaim_khong_ro_khoa_READ(self):
        self.lm.xin("demo", [(FS, "docs", READ), (LockKind.GIT, "history", READ)], task_id="A")
        self.lm.xin("demo", [(FS, "docs", READ)], task_id="B")
        self.assertEqual(self.lm.tra("demo", "A"), 2)
        self.assertEqual([l.holder_task for l in self.st.locks("demo")], ["B"])
        self.assertEqual(self.lm.tra("demo", "B"), 1)
        self.assertEqual(self.st.locks("demo"), [])
        self.lm.xin("demo", [(FS, "docs", READ)], task_id="C", ttl=-1.0)
        self.assertEqual(len(self.lm.reclaim()["reclaimed"]), 1)
        self.assertEqual(self.st.locks("demo"), [])

    def test_so_cu_duoc_nang_cot_mode(self):
        c = self.st._c()
        cols = {r[1] for r in c.execute("PRAGMA table_info(locks)")}
        self.assertIn("mode", cols)
        # Hang cu khong co mode (gia lap) -> doc ra WRITE.
        c.execute("INSERT INTO locks (lock_id, project_id, kind, resource, holder_task, "
                  "acquired_at, expires_at) VALUES ('demo:FILESYSTEM:cu','demo','FILESYSTEM',"
                  "'cu','X',?,0)", (time.time(),))
        self.assertEqual([l.mode for l in self.st.locks("demo") if l.resource == "cu"], [WRITE])


# ============================================================ phan loai ====

class TestPhanLoaiDoc(unittest.TestCase):

    def setUp(self):
        self.pl = RulePlanner(default_write_scope=("web",))
        self.pj = Project(project_id="demo", name="Demo", repo_path="C:/x",
                          resources=("write:web",))

    def test_cau_that_la_CHI_DOC_khong_worktree_khoa_READ(self):
        kq = self.pl.plan(CAU_KIEM_TRA, self.pj)
        self.assertTrue(kq.tasks)
        for t in kq.tasks:
            with self.subTest(t=t.task_id):
                self.assertIn(t.kind, ("analysis", "review"), t.kind)
                self.assertFalse(t.contract.requirements.repo_write)
                self.assertFalse(t.contract.execution.worktree_required)
                self.assertTrue(t.resources)
                self.assertTrue(all(m == READ for _k, _r, m in t.resources), t.resources)

    def test_danh_tu_tests_readme_khong_bien_thanh_viec_ghi(self):
        for cau, ky_vong in (("kiểm tra thư mục tests xem còn thiếu gì", "analysis"),
                             ("xem README/docs có lỗi chính tả không", "analysis"),
                             ("review the tests folder", "review"),
                             ("lục lịch sử git tìm commit đổi config", "analysis")):
            with self.subTest(cau=cau):
                self.assertEqual(RulePlanner.loai_viec(cau), ky_vong)

    def test_dong_tu_ghi_van_la_viec_ghi(self):
        """Có động từ GHI thì KHÔNG bao giờ rơi về lớp chỉ-đọc — an toàn ghi
        không được nới để bài đọc qua. Lớp cụ thể (testing/implementation/
        documentation) giữ thứ tự cũ của `_LOAI_VIEC`."""
        from scripts.control_center.planner import _CHI_DOC
        for cau, ky_vong in (("viết test cho chunker", "testing"),
                             ("write tests for the chunker", "testing"),
                             ("run the tests and fix failures", "testing"),
                             ("fix web/admin then test it", None),
                             ("sửa README.md cho đúng", None),
                             ("kiểm tra rồi sửa lỗi trong web/admin", None)):
            with self.subTest(cau=cau):
                kind = RulePlanner.loai_viec(cau)
                self.assertNotIn(kind, _CHI_DOC, cau)
                if ky_vong:
                    self.assertEqual(kind, ky_vong)

    def test_viec_ghi_khoa_WRITE_va_git_doc_them_khoa_GIT(self):
        w = self.pl.plan("fix web/admin", self.pj).tasks[0]
        self.assertIn((FS, "web/admin", WRITE), w.resources)
        g = self.pl.plan("lục git history xem ai đổi cấu hình", self.pj).tasks[0]
        self.assertIn((LockKind.GIT, "history", READ), g.resources)
        self.assertIn((FS, GOC, READ), g.resources)


# ============================================================ nhat ky git ==

class TestNhatKyGit(unittest.TestCase):
    """Router đọc `git log` thay agent headless (không được chạy shell)."""

    def setUp(self):
        self.repo = Path(kho_git_tam())

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *a):
        import subprocess
        subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)

    def test_tom_tat_kho_that_va_khong_phai_kho(self):
        from scripts.control_center.nguon_git import git_nhat_ky_doc
        van = git_nhat_ky_doc(self.repo)
        self.assertIn("nhánh hiện tại: main", van)
        self.assertIn("tổng số commit: 1", van)
        self.assertIn("khởi tạo", van)
        khong = Path(tempfile.mkdtemp(prefix="cc-khong-git-"))
        try:
            self.assertEqual(git_nhat_ky_doc(khong), "")
        finally:
            shutil.rmtree(khong, ignore_errors=True)

    def test_gioi_han_va_loc_bi_mat_trong_thong_diep_commit(self):
        from scripts.control_center.nguon_git import git_nhat_ky_doc
        (self.repo / "web" / "cfg.txt").write_text("x\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "cấu hình AKIA1234567890ABCDEF cho bucket")
        van = git_nhat_ky_doc(self.repo)
        self.assertNotIn("AKIA1234567890ABCDEF", van)
        self.assertIn("[DA-LOC]", van)
        self.assertIn("tổng số commit: 2", van)
        ngan = git_nhat_ky_doc(self.repo, gioi_han_ky_tu=80)
        self.assertLessEqual(len(ngan), 80 + 40)
        self.assertIn("đã cắt", ngan)


# ================================================================= toa =====

class TestToaTaiNguyenCon(unittest.TestCase):

    def test_liet_ke_nhieu_dong_va_phan_vung_rieng(self):
        yc = TOA.xet_toa(CAU_KIEM_TRA)
        self.assertEqual(yc.so_agent, 4)
        self.assertEqual(yc.muc_liet_ke, ("README/docs", "tests", "source architecture", "git history"))
        con = TOA.chia_con(yc, "Kiểm tra repo.", "kiểm tra repo", chi_doc=True)
        tn = [c.tai_nguyen for c in con]
        self.assertEqual(tn[0], ("READ:FILESYSTEM:README/docs",))
        self.assertEqual(tn[1], ("READ:FILESYSTEM:tests",))
        self.assertEqual(tn[2], ("READ:FILESYSTEM:.",))            # khong duong dan -> goc, READ
        self.assertEqual(tn[3], ("READ:GIT:history",))
        self.assertTrue(all(c.che_do == READ for c in con))
        self.assertEqual(len(set(tn)), 4, "bốn tài nguyên riêng, không gộp thành một khoá")
        for c in con:
            self.assertIn("Tài nguyên/phạm vi của bạn: READ", c.muc_tieu)

    def test_con_ghi_giu_WRITE_theo_duong_dan_rieng(self):
        yc = TOA.xet_toa("gọi 2 agent, mỗi agent sửa một module: web/a, server/b")
        con = TOA.chia_con(yc, "Sửa.", "sửa", chi_doc=False, pham_vi_mau=("web",))
        self.assertEqual([c.tai_nguyen for c in con],
                         [("WRITE:FILESYSTEM:web/a",), ("WRITE:FILESYSTEM:server/b",)])
        # Khong co duong dan rieng -> thua pham vi mau (GHI, tuan tu la dung).
        yc2 = TOA.xet_toa("gọi 2 agent sửa file này")
        con2 = TOA.chia_con(yc2, "Sửa.", "sửa", chi_doc=False, pham_vi_mau=("web",))
        self.assertEqual({c.tai_nguyen for c in con2}, {("WRITE:FILESYSTEM:web",)})

    def test_song_song_toi_da_do_tu_khoang_chay(self):
        k = [{"bat_dau": 0.0, "ket_thuc": 10.0}, {"bat_dau": 2.0, "ket_thuc": 12.0},
             {"bat_dau": 3.0, "ket_thuc": 9.0}, {"bat_dau": 11.0, "ket_thuc": 15.0}]
        self.assertEqual(TOA.song_song_toi_da(k), 3)
        self.assertEqual(TOA.song_song_toi_da([{"bat_dau": 0, "ket_thuc": 1},
                                               {"bat_dau": 1, "ket_thuc": 2}]), 1)
        self.assertEqual(TOA.song_song_toi_da([]), 0)


# =============================================================== engine ====

class _Nen(unittest.TestCase):
    def setUp(self):
        self.repo = kho_git_tam()
        self.cc = None

    def tearDown(self):
        if self.cc is not None:
            _cho(lambda: not any(x.is_alive() for x in list(self.cc._dang_chay.values())), giay=20)
            try:
                self.cc.shutdown()
            except Exception:                               # noqa: BLE001
                pass
        shutil.rmtree(self.repo, ignore_errors=True)

    def _cc(self, ex, max_parallel=4):
        cc = ControlCenter(root=self.repo, fabric=fabric_gia_4(), probe=False,
                           max_parallel=max_parallel, executor_factory=lambda p, f: ex)
        cc.them_project(Project(project_id="demo", name="Demo", repo_path=str(self.repo),
                                resources=("write:web",)))
        self.cc = cc
        return cc

    def _cha_con(self):
        ts = {t.task_id: t for t in self.cc.store.tasks("demo")}
        cha = [t for t in ts.values() if ((t.contract or {}).get("_toa") or {}).get("cha")]
        con = sorted([t for t in ts.values() if t.parent_id in ts],
                     key=lambda t: ((t.contract or {}).get("_toa") or {}).get("chi_so") or 0)
        return cha[0], con


class TestBonConDocSongSong(_Nen):

    def test_bon_con_CHI_DOC_chay_dong_thoi_tren_bon_tai_khoan(self):
        ex = ExecTuyBien(cham=1.2)
        cc = self._cc(ex, max_parallel=4)
        kq = cc.chat("demo", CAU_KIEM_TRA)
        cha, con = self._cha_con()
        self.assertEqual(len(con), 4)
        self.assertIn("4/4 worker slots khả dụng", kq["reply"])
        # Tai nguyen theo tung con, READ, khong sao chep.
        self.assertEqual([c.resources for c in con],
                         [("READ:FILESYSTEM:README/docs",), ("READ:FILESYSTEM:tests",),
                          ("READ:FILESYSTEM:.",), ("READ:GIT:history",)])
        for c in con:
            hd = c.contract
            self.assertFalse((hd.get("requirements") or {}).get("repo_write"))
            self.assertFalse((hd.get("execution") or {}).get("worktree_required"))
        # Cha KHONG giu khoa nao.
        self.assertEqual(cha.resources, ())
        # Con "git history" nhan NHAT KY GIT do Router doc (agent headless
        # khong chay duoc `git log`); ba con kia khong bi nhoi them.
        mt = [c.contract.get("objective") or "" for c in con]
        self.assertIn(ControlCenter.DAU_NHAT_KY_GIT, mt[3])
        self.assertIn("khởi tạo", mt[3], "tiêu đề commit của kho tạm phải có trong nhật ký")
        self.assertIn("nhánh hiện tại: main", mt[3])
        for i in (0, 1, 2):
            self.assertNotIn(ControlCenter.DAU_NHAT_KY_GIT, mt[i])
        # Khoa cua MOI con da nha TRUOC khi gop vao cha (khong phai o `finally`
        # cua luong — cha DONE ma khoa con con giu la dieu nghiem thu tay thay).
        vi_pham: List[str] = []
        goc_tong_hop = cc._tong_hop_toa

        def _tong_hop_soi(ctx, cha_id):
            for x in cc.store.tasks("demo"):
                if x.parent_id == cha_id and x.state in (TaskState.DONE, TaskState.FAILED):
                    for l in cc.store.locks("demo"):
                        if l.holder_task == x.task_id:
                            vi_pham.append(f"{x.task_id} {x.state.value} còn giữ {l.resource}")
            return goc_tong_hop(ctx, cha_id)
        cc._tong_hop_toa = _tong_hop_soi
        cc.tick()
        dang = cc.store.tasks("demo", states=(TaskState.RUNNING,))
        cho = cc.store.tasks("demo", states=(TaskState.WAITING,))
        self.assertEqual(len([t for t in dang if t.parent_id]), 4, "cả 4 con chạy ngay")
        self.assertEqual([t.task_id for t in cho if t.parent_id], [])
        self.assertEqual(cc.store.task(cha.task_id).state, TaskState.RUNNING, "cha RUNNING khi con chạy")
        rts = {cc.store.session(t.owner_session).runtime_id for t in dang if t.parent_id}
        self.assertEqual(rts, {"RT01", "RT02", "RT03", "RT04"}, "bốn tài khoản phân biệt")
        # Bon khoa READ song song trong so — khong ai cho khoa.
        khoa = cc.store.locks("demo")
        self.assertEqual(len(khoa), 4)
        self.assertEqual({l.mode for l in khoa}, {READ})
        self.assertFalse(any("tranh chấp" in (e.get("detail") or "")
                             for e in cc.store.su_kien(project_id="demo", limit=200)))
        self.assertTrue(_chay_toi_xong(cc, cha.task_id, giay=40))
        th = cc.store.task(cha.task_id).result["toa"]
        self.assertEqual((th["xong"], th["hong"]), (4, 0))
        self.assertEqual(th["song_song_toi_da"], 4, "khoảng chạy THẬT của 4 con giao nhau")
        self.assertEqual(len(th["khoang_chay"]), 4)
        self.assertEqual(vi_pham, [], "khoá con phải được nhả trước khi gộp vào cha")
        # Khong ro khoa, khong RUNNING/WAITING ton lai.
        self.assertEqual(cc.store.locks("demo"), [])
        self.assertEqual(cc.store.tasks("demo", states=(TaskState.RUNNING, TaskState.WAITING)), [])
        self.assertEqual(cc.store.task(cha.task_id).state, TaskState.DONE)

    def test_hai_con_GHI_cung_pham_vi_van_tuan_tu(self):
        """An toàn GHI không được nới: hai con sửa cùng tệp -> một chờ, cả hai xong."""
        ex = ExecTuyBien(cham=0.8)
        cc = self._cc(ex, max_parallel=4)
        cc.chat("demo", CAU_GHI)
        cha, con = self._cha_con()
        self.assertEqual(len(con), 2)
        self.assertTrue(all(c.resources == ("WRITE:FILESYSTEM:web/index.txt",) for c in con), [c.resources for c in con])
        cc.tick()
        dang = [t for t in cc.store.tasks("demo", states=(TaskState.RUNNING,)) if t.parent_id]
        cho = [t for t in cc.store.tasks("demo", states=(TaskState.WAITING,)) if t.parent_id]
        self.assertEqual((len(dang), len(cho)), (1, 1))
        self.assertTrue(any("tranh chấp" in (e.get("detail") or "") and "WRITE" in (e.get("detail") or "")
                            for e in cc.store.su_kien(project_id="demo", limit=200)))
        self.assertTrue(_chay_toi_xong(cc, cha.task_id, giay=40))
        th = cc.store.task(cha.task_id).result["toa"]
        self.assertEqual(th["xong"], 2)
        self.assertEqual(th["song_song_toi_da"], 1, "GHI cùng chỗ: không bao giờ chạy chồng")
        self.assertEqual(cc.store.locks("demo"), [])

    def test_con_hong_khong_ro_khoa_va_anh_em_van_song_song(self):
        ex = ExecTuyBien(cham=0.6, hong_neu=lambda tid: tid.endswith("-2"))
        cc = self._cc(ex, max_parallel=4)
        cc.chat("demo", CAU_KIEM_TRA)
        cha, con = self._cha_con()
        self.assertTrue(_chay_toi_xong(cc, cha.task_id, giay=60))
        th = cc.store.task(cha.task_id).result["toa"]
        self.assertEqual((th["xong"], th["hong"]), (3, 1))
        self.assertGreaterEqual(th["song_song_toi_da"], 3)
        self.assertEqual(cc.store.locks("demo"), [], "không rò khoá sau khi một con hỏng")
        self.assertEqual(cc.store.tasks("demo", states=(TaskState.RUNNING, TaskState.WAITING)), [])
        self.assertEqual(cc.store.task(cha.task_id).state, TaskState.DONE)

    def test_recover_khong_coi_cha_toa_la_mo_coi(self):
        ex = ExecTuyBien(cham=0.3)
        cc = self._cc(ex, max_parallel=4)
        cc.chat("demo", CAU_KIEM_TRA)
        cha, _ = self._cha_con()
        cc.tick()
        self.assertEqual(cc.store.task(cha.task_id).state, TaskState.RUNNING)
        bc = cc.recover()
        self.assertNotIn(cha.task_id, bc["tasks"])
        self.assertIn(cc.store.task(cha.task_id).state, (TaskState.RUNNING, TaskState.DONE))


if __name__ == "__main__":
    unittest.main()
